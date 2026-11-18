"""Dispatch one frozen plan through the existing guarded execution entrypoint.

No automatic retry/lease reset. A dispatched or uncertain item requires original
ledger reconciliation; generation never runs this consumer implicitly.
"""
import argparse
import asyncio
from webcollect import workspace_json as json
from .batch_core import BatchLedger, file_sha, load_json


async def dispatch(ledger, job_id, catalog, output, registry, policy, *, site_pool=None):
    from .task_generation import execute
    original=ledger.get(job_id)
    if original['kind']!='frozen-plan':raise ValueError('Frozen plan queue item required')
    payload=original['payload']
    if file_sha(payload['plan'])!=payload['plan_sha256']:raise ValueError('Queued plan changed')
    if original['state']!='queued':
        return {'queue_state':original['state'],'dispatched':False,'original_result':original['result']}
    job=ledger.claim('frozen-plan',job_id=job_id)
    if not job:return {'dispatched':False,'queue_state':ledger.get(job_id)['state']}
    async def heartbeat():
        while True:
            await asyncio.sleep(max(1,ledger.config['budget']['lease_seconds']/3))
            ledger.heartbeat(job)
    keeper=asyncio.create_task(heartbeat())
    try:
        result=await execute(ledger,payload['plan'],catalog,output,registry,policy,site_pool=site_pool)
    except BaseException as error:
        ledger.finish(job,'review_required',error=type(error).__name__)
        raise
    finally:
        keeper.cancel()
        await asyncio.gather(keeper,return_exceptions=True)
    ledger.finish(job,result=result)
    return {'dispatched':True,'queue_state':'done','execution':result,'QC_approval':False}


async def dispatch_candidate(pool, ledger, *, worker_id, request_id, categories=None, application_id=None, **execution):
    """Pre-planning claim; the frozen-plan queue is deliberately not its lock."""
    from .candidate_consumer import consume
    claim = pool.claim_next(worker_id, request_id, categories=categories, application_id=application_id)
    if claim['state'] == 'EMPTY': return claim
    return await consume(pool, claim, ledger, **execution)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','ledger','catalog','output','registry','policy'):p.add_argument('--'+name,required=True)
    p.add_argument('--job-id',required=True);p.add_argument('--site-pool')
    a=p.parse_args(argv);ledger=BatchLedger(a.ledger,load_json(a.config))
    print(json.dumps(asyncio.run(dispatch(ledger,a.job_id,a.catalog,a.output,a.registry,a.policy,site_pool=a.site_pool)),ensure_ascii=False))


if __name__=='__main__':main()
