"""用真实 SQLite 事务验证准备阶段的中断收口及导航证据分类。"""
import asyncio
import argparse
import json
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from webcollect import collect_runtime
from webcollect.plan_protocol import ENDING_POLICY
from webcollect.runtime import RuntimeStore, SCHEMA, DEFAULT_POLICY
from webcollect.failure_policy import disposition
from webcollect.navigation import capture_http_chain, validate_http_chain
from webcollect.candidate_navigation import NavigationRejected

def seed(folder,token='owner'):
    db=folder/'registry.sqlite3'
    now=time.time()
    task={'task_id':'t','fragment':{'ending_policy':ENDING_POLICY}}
    with closing(sqlite3.connect(db)) as con:
        con.executescript(SCHEMA)
        con.execute('insert into m4_campaigns values(?,?,?)',('c',json.dumps({**DEFAULT_POLICY,'campaign_id':'c'}),now))
        con.execute('insert into m4_scopes values(?,?,?,?)',('s','c','active',now))
        con.execute('insert into m4_tasks values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('t','s','c','t','1','fixture',json.dumps(task),'test','example.org','reserved',1,now+500,now,now))
        con.execute('insert into m4_attempts values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('a','s','c','t','p','r','worker',token,now+300,'sample','site','batch','reserved',now,None,None,None,None,None,'[]'))
        con.commit()
    return RuntimeStore(db,'s'), {'attempt_id':'a','worker_id':'worker','task_id':'t','sample_id':'sample','lease_token':'owner'}

async def case(folder,name):
    folder.mkdir()
    store,attempt=seed(folder,'another' if name=='lost_fence' else 'owner')
    reached = threading.Event()
    release = threading.Event()
    start = store.start_attempt
    def pause():
        reached.set()
        assert release.wait(8)
    def sync(*_):
        if name == 'cancel_before_start':
            pause()
        return {'policy':{}}
    def starting(*args):
        result=start(*args)
        if name == 'cancel_during_start':
            pause()
        return result
    def bind(result):
        assert result['status']=='running'
        if name=='busy_bind':
            # An independent writer really holds the registry during this binding.
            with closing(sqlite3.connect(store.registry)) as holder, closing(sqlite3.connect(store.registry,timeout=0.02)) as contender:
                holder.execute('BEGIN IMMEDIATE')
                contender.execute('BEGIN IMMEDIATE')
        if name == 'cancel_during_bind':
            pause()
    with patch.object(collect_runtime,'sync_manifest',sync), patch.object(store,'start_attempt',starting):
        worker=asyncio.create_task(collect_runtime._prepare_owned_attempt(store,folder,{},attempt,300,bind))
        if name.startswith('cancel_'):
            assert await asyncio.to_thread(reached.wait,8)
            worker.cancel()
            await asyncio.sleep(0)
            release.set()
        try:
            await worker
        except (asyncio.CancelledError,sqlite3.OperationalError,ValueError) as error:
            err=type(error).__name__
        else:
            raise AssertionError('Unexpected success')
    with closing(sqlite3.connect(store.registry)) as con:
        status,started,finished,kind,cause,refs=con.execute('select status,started_at,finished_at,failure_class,root_cause,evidence_json from m4_attempts').fetchone()
        task_status,quota=con.execute('select status,quota_reserved from m4_tasks').fetchone()
    f=json.loads((folder/'evidence/sample/failure.json').read_text())
    if name=='lost_fence':
        assert (status,kind,finished,task_status,quota)==('reserved',None,None,'reserved',1)
        assert (folder/'evidence/sample/preparation-closeout-error.json').is_file()
    else:
        assert kind==('transient' if name=='busy_bind' else 'interrupted') and cause==f['root_cause']
        assert status==('abandoned' if name=='cancel_before_start' else 'rejected')
        assert (started is None)==(name=='cancel_before_start') and finished is not None
        assert task_status=='needs_replan' and quota==0
        assert Path(json.loads(refs)[0]['path']).read_bytes()==(folder/'evidence/sample/failure.json').read_bytes()
    return dict(fault=err,status=status,started=started is not None,task_status=task_status,ledger_failure_class=kind,receipt_stage=f['stage'])

async def navigation():
    source='https://example.org/entry'
    other='https://example.org/other'
    class Req:
        url = source
        redirected_from = None
        method = 'GET'
        post_data = None
        headers = {}

        def is_navigation_request(self):
            return True
    response=type('Response',(),{'request':Req(),'headers':{},'status':200})()
    valid=await capture_http_chain(response,source,source)
    try:
        await capture_http_chain(response, source, other)
    except NavigationRejected as error:
        assert disposition(error)['disposition']=='business' and error.capture['last_document_response']==source
    else:
        raise AssertionError('Unproven endpoint accepted')
    try:
        validate_http_chain({**valid, 'landed_url': other}, source, other)
    except ValueError as error:
        assert type(error) is ValueError and disposition(error)['disposition'] == 'page_program'
    else:
        raise AssertionError('Unproven endpoint accepted')
    return {'same_endpoint_accepted':True,'unproven_live_landing':'business','tampered_saved_chain':'rejected'}

async def main(output):
    with tempfile.TemporaryDirectory() as tmp:
        results={n:await case(Path(tmp)/n,n) for n in ('cancel_before_start','cancel_during_start','cancel_during_bind','busy_bind','lost_fence')}
    results['navigation']=await navigation()
    with output.open('x') as f:
        json.dump(results, f, indent=2)
        f.write('\n')
    print(results)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output
    asyncio.run(main(output))
