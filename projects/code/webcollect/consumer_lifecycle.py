"""Wait for local congestion without discarding never-dispatched work."""
import asyncio
import time

from .batch_core import BudgetStop, CONSUMER_KINDS


def recoverable_congestion(error):
    return isinstance(error, BudgetStop) and str(error) in (
        'max_concurrent_jobs reached; queued work retained',
        'domain rate limit; queued work retained',
    )


async def claim_job(ledger, kind, *, job_id, wait_seconds=None, **kwargs):
    if wait_seconds is None and kind not in CONSUMER_KINDS:
        wait_seconds = 120
    deadline = None if wait_seconds is None else time.monotonic() + wait_seconds
    retries = 0
    while True:
        try:
            return ledger.claim(kind, job_id=job_id, **kwargs)
        except BudgetStop as error:
            if not recoverable_congestion(error):
                raise
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise
            delay = min(2 ** min(retries + 1, 4), 10)
            if remaining is not None:
                delay = min(delay, remaining)
            with ledger.transaction() as con:
                ledger.event(con, 'consumer_congestion_wait', {
                    'job_id': job_id, 'kind': kind, 'retry': retries + 1,
                    'delay_seconds': delay, 'reason': str(error)})
            retries += 1
            await asyncio.sleep(delay)
