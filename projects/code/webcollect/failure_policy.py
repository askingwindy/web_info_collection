"""Disposition alongside original failure_class; no external request retries here."""
import asyncio
import fcntl
from webcollect import workspace_json as json
from pathlib import Path
import sqlite3
import time
import traceback


class GlobalFailure(ValueError):
    pass


class PreDispatchDNSFailure(GlobalFailure):
    pass


def feature(error):
    """Original exception and throw site, excluding wrappers and variable messages."""
    while error.__cause__ is not None:
        error = error.__cause__
    frames = traceback.extract_tb(error.__traceback__)
    frame = frames[-1] if frames else None
    return ':'.join((type(error).__module__ + '.' + type(error).__name__,
                     Path(frame.filename).name if frame else 'unknown',
                     frame.name if frame else 'unknown', str(frame.lineno if frame else 0)))


def disposition(error=None, *, failure_class=None, reason=None, phase=None):
    from .candidate_navigation import NavigationRejected
    from .collection_strategy import Strategy1Forbidden
    from .current_chain import CurrentChainError
    from .batch_core import OutcomeUnknown
    from .registry_db import is_locked
    original = failure_class or getattr(error, 'failure_class', None)
    if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, InterruptedError)) or original == 'interrupted':
        kind = 'interrupted'
    elif isinstance(error, OutcomeUnknown) or original == 'unknown':
        kind = 'unknown'
    elif original == 'configuration':
        kind = 'global'
    elif original == 'duplicate':
        kind = 'duplicate'
    elif isinstance(error, PreDispatchDNSFailure):
        kind = 'global'
    elif isinstance(error, (GlobalFailure, Strategy1Forbidden, CurrentChainError, PermissionError, FileNotFoundError)) or phase in ('startup_preflight','before_claim_preflight'):
        kind = 'global'
    elif is_locked(error) if error is not None else original == 'transient':
        kind = 'global' if phase in ('startup_preflight', 'before_claim_preflight') else 'page_program'
    elif isinstance(error,(KeyError,TypeError,NameError,AttributeError,sqlite3.Error)):
        kind = 'page_program'
    elif isinstance(error, NavigationRejected) or original in ('model', 'collector', 'semantic', 'unsupported', 'network', 'privacy', 'interface'):
        kind = 'business'
    elif original == 'program' or isinstance(error, (KeyError, TypeError, NameError, AttributeError, sqlite3.Error)):
        kind = 'page_program'
    elif error is not None:
        kind = 'page_program'
    else:
        kind = 'unclassified'
    owner=('program' if kind in ('global','page_program') else
           'model' if original=='model' or isinstance(error,OutcomeUnknown) else
           'site' if original in ('network','unsupported') else
           'business' if kind in ('business','duplicate') else 'unknown')
    if isinstance(error,PreDispatchDNSFailure):owner='model'
    return {'disposition': kind, 'reason_owner':owner, 'failure_class': original,
            'code':getattr(error,'code',None), 'retry_count':getattr(error,'retry_count',0),
            'reason': str(error) if error is not None else reason,
            'error_feature': feature(error) if error is not None else None,
            'transient': bool(is_locked(error)) if error is not None else original == 'transient',
            'shared_dependency_exhausted': isinstance(error, PreDispatchDNSFailure)}


class RoundFailures:
    """One round event file, guarded across local workers; replay rebuilds counts."""
    def __init__(self, path):
        self.path = Path(path)

    def record(self, claim_id, detail):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a+', encoding='utf-8') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            rows = [json.loads(line) for line in stream if line.strip()]
            if detail['disposition'] not in ('transient','page_program'):
                existing=next((row for row in rows if row.get('claim_id')==claim_id and row.get('disposition')==detail['disposition'] and row.get('error_feature')==detail.get('error_feature')),None)
                if existing:return existing
            same = [row for row in rows if row.get('error_feature') == detail.get('error_feature')
                    and row.get('disposition') == 'page_program']
            existing = next((r for r in same if r['claim_id'] == claim_id), None)
            if existing:
                return existing
            claims = {r['claim_id'] for r in same}
            count = len(claims | {claim_id}) if detail['disposition'] == 'page_program' else None
            row = {'reason_owner':'unknown','retry_count':0,**detail, 'claim_id': claim_id, 'at': time.time(), 'occurrence': count,
                   'stop_dispatch': detail['disposition'] == 'global' or count is not None and count >= 3}
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            return row

    def stopped(self):
        if not self.path.exists():
            return False
        with self.path.open() as stream:
            fcntl.flock(stream, fcntl.LOCK_SH)
            return any(json.loads(line).get('stop_dispatch') for line in stream if line.strip())


def safe_retry(operation, *, safe, deadline, stopped=lambda: False, retryable=None, sleep=time.sleep):
    """One owner, initial call plus three retries; only rolled-back/undispatched IO."""
    if not safe:
        raise ValueError('Retry requires proof of no dispatch or rolled back local transaction')
    from .registry_db import is_locked
    retryable = retryable or is_locked
    for attempt in range(4):
        if stopped():
            from .batch_core import UserStopped
            raise UserStopped('用户停止：预检尚未派发外部请求')
        if time.monotonic() >= deadline:
            from .batch_core import BudgetStop
            raise BudgetStop('pre_dispatch_deadline: no external request')
        try:
            result = operation()
            if stopped():
                from .batch_core import UserStopped
                raise UserStopped('用户停止：预检完成后不派发外部请求')
            if time.monotonic() >= deadline:
                from .batch_core import BudgetStop
                raise BudgetStop('pre_dispatch_deadline: no external request')
            return result
        except Exception as error:
            error.retry_count=attempt
            if attempt == 3 or not retryable(error):
                raise
            retry_event(error,attempt+1,operation='pre_dispatch_dns')
            until = min(deadline, time.monotonic() + (1 << attempt))
            while time.monotonic() < until:
                if stopped():
                    from .batch_core import UserStopped
                    raise UserStopped('用户停止：不再重试预检或派发HTTP') from error
                sleep(min(.1, max(0, until - time.monotonic())))


from contextvars import ContextVar
current_claim = ContextVar('failure_current_claim',default=None)


def retry_event(error, attempt, *, operation):
    """Display-only retry fact; never changes an original request or result."""
    import os
    path=os.environ.get('WEBCOLLECT_ROUND_EVENTS')
    if not path:return
    detail=disposition(error,failure_class='transient')
    detail.update(disposition='transient',operation=operation,retry_count=attempt,
                  error_feature=feature(error),reason_owner='program' if isinstance(error,sqlite3.Error) else 'model')
    RoundFailures(path).record(current_claim.get() or 'pre_dispatch',detail)
