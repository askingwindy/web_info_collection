"""Isolated native leases: healthy polls, due renewals and revocation across 20 processes."""
from contextlib import closing
import argparse
import json
import multiprocessing as mp
from pathlib import Path
import sqlite3
import tempfile
import time

from site_planner.site_pool import SitePool
from site_planner.candidate_pool import CandidatePool, CandidateLeaseLost
from webcollect.batch_core import BatchLedger, JobLeaseLost, file_sha
from webcollect.failure_policy import disposition

CONFIG = {
    'run_id': 'local-heartbeat', 'mode': 'synthetic', 'model': None,
    'budget': {'max_concurrent_jobs': 20, 'min_domain_interval_seconds': 1,
               'lease_seconds': 300, 'max_job_attempts': 1},
}
WORKERS = 20

def work(pool_path,ledger_path,claim,job,barrier):
    pool=CandidatePool(pool_path)
    ledger=BatchLedger(ledger_path,CONFIG,initialize=False)
    for due_check in (False,True,True):
        barrier.wait(timeout=45)
        for _ in range(3):
            pool.heartbeat(claim,only_if_due=due_check)
            ledger.heartbeat(job,only_if_due=due_check)
        barrier.wait(timeout=45)

def counter(path,sql):
    with closing(sqlite3.connect(path)) as c:
        r=c.execute(sql).fetchone()
        c.commit()
    return r[0] if r else None

def main(output):
    ctx = mp.get_context('spawn')
    start = time.monotonic()
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        pool_path = base / 'candidate-pool.sqlite3'
        ledger_path = base / 'consumer-jobs.sqlite3'
        SitePool(pool_path,initialize=True)
        pool=CandidatePool(pool_path,install=True)
        ledger=BatchLedger(ledger_path,CONFIG,initialize=True)
        counter(ledger_path,'PRAGMA journal_mode=DELETE')
        proof = base / 'source.json'
        proof.write_text('{"fixture":true}')
        claims = []
        jobs = []
        for i in range(WORKERS):
            cid=pool.put({'schema_version':'webcollect-data-candidate-2','candidate_kind':'entry',
                         'entry_url':f'https://example.org/page-{i}','requested_goal':None},
                        {'origin':'codex_session','run_id':'local-heartbeat','category_hint':'在线工具',
                         'references':[{'path':str(proof),'sha256':file_sha(proof)}]})
            claims.append(pool.claim_next('worker-'+str(i),'request-'+str(i),candidate_id=cid))
            job_id = ledger.enqueue('collection', {'fixture_page': i})
            jobs.append(ledger.claim('collection', job_id=job_id))
        for path,table,column in ((pool_path,'candidate_claims','expires'),(ledger_path,'jobs','lease')):
            with closing(sqlite3.connect(path)) as con:
                con.executescript(f'CREATE TABLE writes (id INTEGER); CREATE TRIGGER count_renew AFTER UPDATE OF {column} ON {table} BEGIN INSERT INTO writes VALUES(1); END;')
        barrier=ctx.Barrier(WORKERS+1)
        processes=[ctx.Process(target=work,args=(pool_path,ledger_path,c,j,barrier)) for c,j in zip(claims,jobs)]
        for proc in processes:
            proc.start()
        stages={}
        try:
            for stage in ('force_every_poll','healthy_periodic','due_periodic'):
                for path,table,column in ((pool_path,'candidate_claims','expires'),(ledger_path,'jobs','lease')):
                    if stage == 'due_periodic':
                        counter(path,f"UPDATE {table} SET {column}=unixepoch()+110")
                    counter(path,'DELETE FROM writes')
                barrier.wait(timeout=45)
                assert sum(p.is_alive() for p in processes)==WORKERS
                barrier.wait(timeout=45)
                stages[stage]=[counter(path,'select count(*) from writes') for path in (pool_path,ledger_path)]
            for proc in processes:
                proc.join(10)
            assert all(p.exitcode==0 for p in processes)
        finally:
            for proc in processes:
                if proc.is_alive():
                    proc.terminate()
                    proc.join(5)
        assert stages=={'force_every_poll':[60,60],'healthy_periodic':[0,0],'due_periodic':[20,20]},stages
        for callback,expected_error in ((lambda:pool.heartbeat({**claims[0],'token':'revoked'},only_if_due=True),CandidateLeaseLost),
                             (lambda:ledger.heartbeat({**jobs[0],'owner':'revoked'},only_if_due=True),JobLeaseLost)):
            try:
                callback()
            except expected_error as error:
                assert disposition(error)['disposition'] == 'interrupted'
            else:
                raise AssertionError('revoked writer not fenced')
        child_id=ledger.enqueue('stepwise-decision',{'parent_job_id':jobs[0]['id']})
        child=ledger.claim('stepwise-decision',job_id=child_id,parent_job=jobs[0])
        ledger.finish(jobs[0])
        try:
            ledger.heartbeat(child, only_if_due=True)
        except JobLeaseLost as error:
            assert 'parent' in str(error)
        else:
            raise AssertionError('revoked parent not fenced')
        assert counter(ledger_path,'select count(*) from model_requests')==0
        result={'concurrent_processes':WORKERS,'exit_zero':WORKERS,'polls_per_lease_per_phase':3,
                'db_order':['candidate_pool','model_jobs'],'candidate_journal':counter(pool_path,'pragma journal_mode'),
                'model_journal':counter(ledger_path,'pragma journal_mode'),'writes':stages,
                'revoked_claim_owner_and_revoked_job_owner_rejected':True,'revoked_parent_job_rejected':True,
                'model_requests':0,'elapsed_seconds':round(time.monotonic()-start,3)}
        with output.open('x') as f:
            json.dump(result, f, indent=2)
            f.write('\n')
        print(result)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output
    main(output)
