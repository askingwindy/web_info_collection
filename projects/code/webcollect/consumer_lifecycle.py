"""Bounded local congestion waits; retry only a never-dispatched queued job."""
import asyncio
import time

from .batch_core import BudgetStop


def recoverable_congestion(error):
    return isinstance(error, BudgetStop) and str(error) in (
        'max_concurrent_jobs reached; queued work retained',
        'domain rate limit; queued work retained',
    )


async def claim_job(ledger, kind, *, job_id, wait_seconds=120, **kwargs):
    deadline = time.monotonic() + wait_seconds
    retries = 0
    while True:
        try:
            return ledger.claim(kind, job_id=job_id, **kwargs)
        except BudgetStop as error:
            if not recoverable_congestion(error):
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            delay = min(2 ** min(retries + 1, 4), 10, remaining)
            with ledger.transaction() as con:
                ledger.event(con, 'consumer_congestion_wait', {
                    'job_id': job_id, 'kind': kind, 'retry': retries + 1,
                    'delay_seconds': delay, 'reason': str(error)})
            retries += 1
            await asyncio.sleep(delay)
