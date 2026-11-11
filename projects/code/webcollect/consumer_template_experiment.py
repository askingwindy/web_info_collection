"""Explicit frozen-cohort entry for the bounded template comparison.

No scope/config/ledger is created or replaced. Only the passed original eight
Table2 rows can be claimed. A source snapshot is verified before dispatch.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import time

from .batch_core import BatchLedger, load_json, file_sha
from .consumer_templates import enabled, GOAL_RULE
from .planning import verify_evidence


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)
        stream.write('\n')


async def capture(cohort_path, directory, worker):
    from . import candidate_consumer
    from site_planner.candidate_pool import CandidatePool
    cohort=load_json(cohort_path)
    if cohort.get('goal_rule') != GOAL_RULE:
        raise ValueError('Explicit frozen template contract required')
    rows=cohort['selected']
    if len(rows)!=8 or cohort['denominator']!=8 or len({r['candidate_id'] for r in rows})!=8:
        raise ValueError('Exactly eight original candidate IDs required')
    if sorted((r['family'],r['arm']) for r in rows) != sorted(
            [(f,a) for f in ('calculator','encyclopedia') for a in ('template','react') for _ in range(2)]):
        raise ValueError('Two per family and arm required')
    for key in ('scope','manifest','source_freeze','offline','before'):
        verify_evidence([cohort[key]])
    proof=load_json(cohort['offline']['path'])
    if proof['status']!='PASS': raise ValueError('Offline verification did not pass')
    frozen=load_json(cohort['source_freeze']['path'])
    root=Path(__file__).resolve().parents[3]
    for name,digest in frozen.items():
        if file_sha(root/name)!=digest: raise ValueError('Frozen source changed: '+name)
    scope=load_json(cohort['scope']['path'])
    ledger=BatchLedger(scope['consumer_db'],load_json(scope['consumer_config']))
    pool=CandidatePool(scope['pool'])
    target=Path(scope['output'])/worker
    if target.exists() or (directory/'capture-started.json').exists():
        raise ValueError('This experiment already dispatched; inspect original evidence without replay')
    before=load_json(cohort['before']['path'])
    for key in ('consumer_config','policy','qc_policy'):
        verify_evidence([before[key]])
    with pool.pool.connect() as con:
        for row in rows:
            existing=con.execute('SELECT state,version,body FROM data_candidates WHERE candidate_id=?',(row['candidate_id'],)).fetchone()
            if (not existing or existing['state']!='pending' or existing['version']!=row['version']
                    or json.loads(existing['body'])!=row['body']
                    or con.execute('SELECT 1 FROM candidate_claims WHERE candidate_id=?',(row['candidate_id'],)).fetchone()):
                raise ValueError('Frozen original no longer never-claimed/pending: '+row['candidate_id'])
    started=time.time()
    def event(phase, **data):
        record={'phase':phase,'at':datetime.now(timezone.utc).isoformat(),**data}
        with (directory/'timeline.jsonl').open('a') as stream:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
        print(json.dumps(record,ensure_ascii=False),flush=True)
    async def wait_slot(claim=None):
        waiting=time.time();logged=False
        while True:
            with ledger.connect() as con:
                busy=con.execute("SELECT id,kind FROM jobs WHERE state='running' AND kind!='frozen-plan'").fetchall()
            if not busy:break
            if not logged:event('waiting_original_shared_slot',jobs=[dict(j) for j in busy]);logged=True
            if claim is not None:
                pool.heartbeat(claim)
            await asyncio.sleep(5)
        return time.time()-waiting
    # Wait before claiming, including the spaces between this cohort's rows.
    # The original ledger still arbitrates the actual claim transaction.
    waiting=await wait_slot()
    write_new(directory/'capture-started.json',{'worker':worker,'cohort':str(cohort_path),
        'output':str(target),'at':datetime.now(timezone.utc).isoformat(),'initial_wait_seconds':waiting})
    original_consume=candidate_consumer.consume
    completed=[]
    async def consume(*args,**kwargs):
        nonlocal waiting
        claim=args[1];waiting+=await wait_slot(claim);t=time.time()
        event('candidate_started',candidate_id=claim['candidate_id'],claim_id=claim['claim_id'])
        try:
            result=await original_consume(*args,**kwargs)
            completed.append({'candidate_id':claim['candidate_id'],'claim_id':claim['claim_id'],
                              'started':t,'finished':time.time(),'natural_seconds':time.time()-t,'result':result})
            event('candidate_finished',**completed[-1])
            (directory/'progress.json').write_text(json.dumps({'status':'CAPTURING','denominator':8,
                'completed':len(completed),'wait_seconds':waiting,'rows':completed},ensure_ascii=False,indent=2))
            return result
        except BaseException as exc:
            event('candidate_exception',candidate_id=claim['candidate_id'],type=type(exc).__name__,reason=str(exc))
            raise
    candidate_consumer.consume=consume
    try:
        with enabled(rows):
            result=await candidate_consumer.run(pool,ledger,worker_id=worker,request_prefix=worker,
                cohort=cohort_path,output=target,registry=scope['registry'],policy=scope['policy'],
                history_set=scope['history_set'],qc_policy=scope['qc_policy'])
        write_new(directory/'official-run-result.json',result)
        event('capture_returned',processed=result['processed'],stop_reason=result['stop_reason'],
              natural_seconds=time.time()-started,wait_seconds=waiting)
    finally:candidate_consumer.consume=original_consume
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort',required=True,type=Path);p.add_argument('--directory',required=True,type=Path)
    p.add_argument('--worker',required=True)
    a=p.parse_args(argv)
    with (a.directory/'runner.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        asyncio.run(capture(a.cohort.resolve(),a.directory.resolve(),a.worker))


if __name__=='__main__':main()
