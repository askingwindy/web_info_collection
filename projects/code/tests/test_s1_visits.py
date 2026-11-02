"""S1 active visit accounting; only bounded localhost HTTP/Chrome fixtures."""
import asyncio
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/site-planner')]
from webcollect.batch_core import BatchLedger, BudgetStop, VisitRateWait, load_json, save_json, file_sha
from site_planner.pipeline import discover, probe, fetch_public
from webcollect.site_failure_stop import SiteStopped

HTML='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>测试工具</title>
<style>body{font:24px sans-serif;margin:28px;line-height:1.7}input,button{font:24px sans-serif}</style>
<h1>访问计量受控工程页面</h1><p>这是本地合成页面，仅验证顶层访问计量、失败证据和恢复行为。请填写测试数量及测试单价，所有输入都是工程测试内容，不属于真实生产样本。</p>
<form aria-label="购物金额计算"><label for="a">数量</label><input id="a" type="number"><label for="b">单价</label><input id="b" type="number"><button type="submit">计算合计</button></form><div id="result">请填写数量和单价</div><a href="/broken">打开第二代表页</a></html>'''

class VisitAccountingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        retained=os.environ.get('WEBCOLLECT_S1_VISIT_EVIDENCE')
        if retained:
            self.root=Path(retained)/self._testMethodName;self.root.mkdir(parents=True,exist_ok=False)
        else:
            tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.cfg=load_json(REPO/'projects/code/config/batch-no-model.json')
        from webcollect.site_failure_stop import SiteFailureStore
        self.cfg['site_failure_guard'] = SiteFailureStore.initialize({
            'ledger': str(self.root/'site-stop.sqlite3'), 'campaign_id': 'CONTROLLED-visits',
            'formal_since': time.time()-1}).binding
        self.cfg['budget'].update(max_top_level_visits=8,min_domain_interval_seconds=1)
        self.ledger=BatchLedger(self.root/'ops.sqlite3',self.cfg,initialize=True)
        self.requests=[]
        requests=self.requests
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append({'path':self.path,'at':time.time()})
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','/directory');self.end_headers();return
                if self.path in ('/broken','/failure'):
                    self.send_response(404);self.end_headers();self.wfile.write(b'not found');return
                body=HTML if self.path=='/home' else '<html><meta charset="utf-8"><a href="/home">受控页面</a></html>'
                body=body.encode();self.send_response(200);self.send_header('Content-Type','text/html;charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        from webcollect.collect import verify_public_url
        def allow(url,allowed_hosts=None):
            if urlsplit(url).netloc==urlsplit(self.base).netloc:return '127.0.0.1'
            return verify_public_url(url,allowed_hosts)
        self.guard=patch('site_planner.pipeline.verify_public_url',side_effect=allow);self.guard.start();self.addCleanup(self.guard.stop)
        self.guard2=patch('webcollect.collect.verify_public_url',side_effect=allow);self.guard2.start();self.addCleanup(self.guard2.stop)

    def tearDown(self):
        self.ledger.export(self.root/'metering')
        save_json(self.root/'fixture-requests.json',self.requests)

    def job(self):
        return self.ledger.claim('fixture',job_id=self.ledger.enqueue('fixture',{'case':self._testMethodName}))

    def test_retries_count_every_dispatch_and_resource_is_not_reset(self):
        job=self.job();self.ledger.consume('probe_pages','same-page')
        for i in range(100):
            domain=f'fixture-{i}.example'
            visit=self.ledger.reserve_visit(job,f'https://{domain}/repeated','same',domain)
            self.ledger.settle_visit(visit,state='failed',error=TimeoutError('controlled failure'))
        resumed=BatchLedger(self.ledger.path,self.cfg);resumed.consume('probe_pages','same-page')
        visit = resumed.reserve_visit(job,'https://example.org/repeated','same','example.org')
        resumed.settle_visit(visit,state='succeeded',response_status=200)
        self.assertEqual(resumed.summary()['top_level_visits_attempted'],101)
        self.assertEqual(resumed.summary()['resources'],[{'kind':'probe_pages','used':1}])
        self.ledger.finish(job)

    def test_each_dispatch_rate_timeout_remaining_and_wall_limit(self):
        job=self.job();visit=self.ledger.reserve_visit(job,'https://example.org/a','a','example.org')
        self.ledger.settle_visit(visit,state='succeeded',response_status=200)
        with self.assertRaises(VisitRateWait):self.ledger.reserve_visit(job,'https://example.org/b','b','example.org')
        with self.ledger.transaction() as con:
            con.execute('DELETE FROM domain_dispatch')
            con.execute('UPDATE batch_meta SET started=?',(time.time()-self.cfg['budget']['max_run_seconds']+0.3,))
        visit=self.ledger.reserve_visit(job,'https://example.org/b','b','example.org')
        self.assertEqual(visit['timeout_seconds'],20)
        self.ledger.settle_visit(visit,state='failed',error=TimeoutError())
        with self.ledger.transaction() as con:con.execute('UPDATE batch_meta SET started=?',(time.time()-self.cfg['budget']['max_run_seconds']-1,))
        visit=self.ledger.reserve_visit(job,'https://other.example/a','a','other.example',timeout_seconds=7)
        self.assertEqual(visit['timeout_seconds'],7)
        self.ledger.settle_visit(visit,state='succeeded',response_status=200)
        self.ledger.finish(job)

    def test_legacy_unknown_history_never_reports_zero_or_resets_resources(self):
        self.ledger.consume('probe_pages','old-page')
        with self.ledger.transaction() as con:
            con.execute('DROP TABLE top_level_visits');con.execute('DROP TABLE visit_accounting_meta')
        self.assertEqual(self.ledger.summary()['top_level_visits_attempted'],'UNKNOWN')
        job=self.job()
        with self.assertRaisesRegex(BudgetStop,'history UNKNOWN'):
            self.ledger.reserve_visit(job,'https://example.org','legacy','example.org')
        self.assertEqual(self.ledger.summary()['resources'],[{'kind':'probe_pages','used':1}])
        self.ledger.finish(job)

    def test_sources_failures_redirects_cache_and_domain_frequency(self):
        sources={'schema_version':'webcollect-site-sources-1','sources':[
            {'kind':'directory','uri':self.base+'/redirect','category':'测试','max_candidates':1},
            {'kind':'directory','uri':self.base+'/failure','category':'测试','max_candidates':1}]}
        save_json(self.root/'sources.json',sources)
        result=discover(self.ledger,self.root/'sources.json',self.root/'supply')
        self.assertEqual(result['fixed_candidate_count'],1)
        self.assertEqual(result['source_errors'][0]['response_status'],404)
        visits=self.ledger.visits();self.assertEqual(len(visits),2)
        self.assertGreaterEqual(visits[1]['dispatched_at']-visits[0]['dispatched_at'],0.99)
        self.assertEqual(visits[0]['metrics']['redirect_request_events'],1)
        self.assertEqual([v['response_status'] for v in visits],[200,404])
        self.assertEqual(len(self.requests),3)
        resumed=discover(BatchLedger(self.ledger.path,self.cfg),self.root/'sources.json',self.root/'supply')
        self.assertEqual(resumed,result);self.assertEqual(len(self.ledger.visits()),2)

    def test_source_crash_resume_holds_unknown_visit_without_repeating_fetch(self):
        save_json(self.root/'sources.json',{'schema_version':'webcollect-site-sources-1','sources':[
            {'kind':'directory','uri':self.base+'/directory','category':'测试','max_candidates':1}]})
        def crash_after_fetch(*args,**kwargs):
            fetch_public(*args,**kwargs)
            raise SystemExit('controlled process loss after HTTP, before output')
        with patch('site_planner.pipeline.fetch_public',side_effect=crash_after_fetch):
            with self.assertRaises(SystemExit):discover(self.ledger,self.root/'sources.json',self.root/'supply')
        with self.ledger.transaction() as con:con.execute("UPDATE jobs SET lease=? WHERE state='running'",(time.time()-1,))
        resumed=BatchLedger(self.ledger.path,self.cfg)
        with self.assertRaises(SiteStopped): discover(resumed,self.root/'sources.json',self.root/'supply')
        self.assertEqual(len(self.requests),1)
        self.assertEqual([v['state'] for v in resumed.visits()],['unknown'])
        self.assertEqual(resumed.summary()['resources'],[{'kind':'probe_pages','used':1}])

    async def test_explicit_second_candidate_failure_preserves_first_and_cached_retry_no_extra_first_visit(self):
        save_json(self.root/'candidates.json',{'schema_version':'webcollect-site-candidates-1','mode':'real','records':[
            {'site_uri':self.base+path,'site_category':'测试','source':[{'kind':'controlled-local-http'}]}
            for path in ('/home','/broken')]})
        result=await probe(self.ledger,self.root/'candidates.json',self.root/'probe')
        self.assertEqual(len(result['records']),2)
        record=result['records'][0]
        self.assertEqual(len(record['representative_pages']),1)
        self.assertTrue(record['rendered']);self.assertTrue(record['accessible'])
        self.assertEqual([v['response_status'] for v in self.ledger.visits()],[200,404])
        first_images={p['path']:p['sha256'] for p in record['evidence'] if p['path'].endswith('.png')}
        self.assertGreaterEqual(len(first_images),2) # Includes any diagnostic diff PNG, originals remain complete.
        # The successful first candidate is complete and immutable; only the
        # failed explicitly requested candidate is made eligible for retry.
        with self.ledger.transaction() as con:
            con.execute("UPDATE jobs SET state='queued' WHERE kind='site-probe' AND state='review_required'")
        again=await probe(BatchLedger(self.ledger.path,self.cfg),self.root/'candidates.json',self.root/'probe')
        self.assertEqual(len(self.ledger.visits()),3)
        self.assertEqual([v['purpose'] for v in self.ledger.visits()],['probe-page:0']*3)
        self.assertEqual([v['response_status'] for v in self.ledger.visits()],[200,404,404])
        self.assertEqual([r['path'] for r in self.requests].count('/home'),1)
        self.assertEqual([r['path'] for r in self.requests].count('/broken'),2)
        self.assertEqual(again['records'][0],record)
        self.assertTrue(all(file_sha(p)==h for p,h in first_images.items()))
        failures=list((self.root/'probe').rglob('visit-failure.json'))
        self.assertEqual(len(failures),2)
        self.assertEqual(again['records'][1]['status'],'review_required')
        visits=self.ledger.visits();self.assertTrue(all(b['dispatched_at']-a['dispatched_at']>=0.99 for a,b in zip(visits,visits[1:])))

    async def test_old_visit_cap_allows_all_listed_candidates(self):
        self.cfg=deepcopy(self.cfg);self.cfg['budget']['max_top_level_visits']=1
        self.ledger=BatchLedger(self.root/'limited-ops.sqlite3',self.cfg,initialize=True)
        save_json(self.root/'candidates.json',{'schema_version':'webcollect-site-candidates-1','mode':'real','records':[
            {'site_uri':self.base+path,'site_category':'测试','source':[{'kind':'controlled-local-http'}]}
            for path in ('/home','/broken')]})
        result=await probe(self.ledger,self.root/'candidates.json',self.root/'probe')
        self.assertIsNone(result['stopped'])
        self.assertEqual(len(result['records'][0]['representative_pages']),1)
        self.assertTrue(result['records'][0]['rendered'])
        self.assertEqual(self.ledger.summary()['top_level_visits_attempted'],2)
        self.assertTrue(any(r['path']=='/broken' for r in self.requests))

    async def test_unlisted_same_host_link_does_not_expand_candidate_scope(self):
        save_json(self.root/'candidates.json',{'schema_version':'webcollect-site-candidates-1','mode':'real','records':[
            {'site_uri':self.base+'/home','site_category':'测试','source':[{'kind':'controlled-local-http'}]}]})
        result=await probe(self.ledger,self.root/'candidates.json',self.root/'probe')
        self.assertIsNone(result['stopped'])
        self.assertEqual([v['response_status'] for v in self.ledger.visits()],[200])
        self.assertFalse(any(r['path']=='/broken' for r in self.requests))
        self.assertEqual(result['records'][0]['capability_scope'],
                         {'kind':'exact-candidate-page','page_uris':[self.base+'/home'],'sitewide':False})

if __name__=='__main__':unittest.main()
