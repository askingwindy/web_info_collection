"""Bounded connections and transaction-only registry reads."""
import sqlite3
from pathlib import Path

BUSY_SECONDS = 90


def connect(registry, *, readonly=True):
    path = Path(registry).resolve()
    con = sqlite3.connect(path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'),
                          uri=True, timeout=BUSY_SECONDS)
    con.row_factory = sqlite3.Row
    return con


def is_locked(error):
    """A busy/shared-lock SQLite error is a bounded wait outcome, not an engineering fault.

    Connections already wait BUSY_SECONDS; an error that still escapes is a
    transient conflict to settle and continue, never a reason to stop the batch.
    Message matching keeps the predicate true for wrapped or re-raised errors.
    """
    if not isinstance(error, sqlite3.OperationalError):
        return False
    if (getattr(error, 'sqlite_errorcode', 0) & 255) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return True
    message = str(error)
    return 'database is locked' in message or 'database table is locked' in message


def history_rows(registry, *, include_plans=False):
    """Copy a consistent SQL snapshot; decoding/hashing never holds a read lock."""
    con = connect(registry)
    try:
        con.execute('BEGIN')
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'm4_tasks' not in tables:
            raise ValueError('TASK_ADMISSION: original M4 history table missing')
        columns = {row[1] for row in con.execute('PRAGMA table_info(m4_tasks)')}
        fields = ','.join(key if key in columns else 'NULL AS ' + key
                          for key in ('scope_id', 'campaign_id'))
        tasks = [dict(row) for row in con.execute('SELECT ' + fields + ',task_json FROM m4_tasks')]
        plans = ([tuple(row) for row in con.execute('SELECT scope_id,plan_json FROM m4_plans WHERE scope_id IN (SELECT DISTINCT scope_id FROM m4_tasks)')]
                 if include_plans and 'm4_plans' in tables else [])
        con.commit()
        return tasks, plans
    finally:
        con.close()
