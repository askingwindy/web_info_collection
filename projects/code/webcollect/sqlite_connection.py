"""SQLite connection policy. Preparation alone enables WAL; workers never switch modes."""
import sqlite3
from pathlib import Path


def connect(path, *, readonly=False, create=False, durable=True, timeout=90, factory=sqlite3.Connection):
    path = Path(path).resolve()
    con = raw_connect(str(path) if create else path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'),
                          uri=not create, timeout=max(0, timeout), factory=factory)
    con.execute('PRAGMA busy_timeout=' + str(max(0, int(timeout * 1000))))
    if readonly:
        con.execute('PRAGMA query_only=ON')
    else:
        con.execute('PRAGMA synchronous=' + ('FULL' if durable else 'NORMAL'))
    return con


def prepare_wal(con):
    if con.in_transaction:
        raise ValueError('WAL preparation requires no active transaction')
    if con.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() != 'wal':
        raise ValueError('WAL preparation failed')


def backup(source, destination):
    """Consistent single-database backup; callers drain writers for multi-store cutover."""
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    from contextlib import closing
    with closing(connect(source, readonly=True)) as src, closing(connect(destination, create=True)) as dst:
        src.backup(dst)


def raw_connect(database, *args, **kwargs):
    """Use sqlite3 unchanged for SQL parameters and returned text."""
    from urllib.parse import urlsplit, unquote
    database=str(database)
    path=unquote(urlsplit(database).path) if database.startswith('file:') else database
    kwargs.setdefault('timeout',90)
    con=sqlite3.connect(database,*args,**kwargs)
    timeout=kwargs['timeout']
    con.execute('PRAGMA busy_timeout='+str(int(timeout*1000)))
    readonly=database.startswith('file:') and 'mode=ro' in database
    if readonly:
        con.execute('PRAGMA query_only=ON')
    else:
        con.execute('PRAGMA synchronous='+('NORMAL' if Path(path).name in ('candidate-pool.sqlite3','site-facts.sqlite3') else 'FULL'))
    return con


from contextvars import ContextVar
operation_deadline = ContextVar('sqlite_operation_deadline',default=None)


def begin_immediate(con, *, timeout=90):
    """Initial BEGIN plus at most three retries; no SQL/external effect was dispatched.

    Busy waits, backoff, stop and the active session deadline share one budget.
    The caller rolls back any transaction if a later statement fails; it is not replayed.
    """
    import os,time
    deadline=min(time.monotonic()+timeout,operation_deadline.get() or float('inf'))
    original=con.execute('PRAGMA busy_timeout').fetchone()[0]
    def stopping():
        return any(os.environ.get(k) and Path(os.environ[k]).exists()
                   for k in ('WEBCOLLECT_STOP_FILE','WEBCOLLECT_PRODUCER_STOP_FILE'))
    try:
        for attempt in range(4):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('SQLite operation deadline expired')
            # Divide the remaining budget among the remaining attempts. A
            # one-second slice exhausted all four attempts after ~11 seconds,
            # cancelling healthy leases despite the configured 90-second wait.
            con.execute('PRAGMA busy_timeout='+str(max(1,int(remaining/(4-attempt)*1000))))
            try:
                con.execute('BEGIN IMMEDIATE')
                return
            except sqlite3.OperationalError as error:
                from .registry_db import is_locked
                error.retry_count=attempt
                if is_locked(error):
                    from traceback import extract_stack
                    error.sqlite_database = Path(con.execute('PRAGMA database_list').fetchone()[2]).name
                    caller = next((frame for frame in reversed(extract_stack(limit=10)[:-1])
                                   if frame.name not in ('__enter__','_transaction','transaction')), None)
                    error.sqlite_operation = caller.name if caller else None
                if attempt==3 or not is_locked(error):raise
                from .failure_policy import retry_event
                retry_event(error,attempt+1,operation='begin_immediate')
                if stopping():raise InterruptedError('SQLite retry stopped before lock acquisition') from error
                until=min(deadline,time.monotonic()+(1<<attempt))
                while time.monotonic()<until:
                    if stopping():raise InterruptedError('SQLite retry stopped') from error
                    time.sleep(min(.1,max(0,until-time.monotonic())))
    finally:
        con.execute('PRAGMA busy_timeout='+str(original))
