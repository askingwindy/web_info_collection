"""D-E: read-only original-claim/job/frame joins and actual next-batch selection."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import sqlite3
import unittest
from unittest.mock import patch

import test_producer_optimization as producer
from webcollect.batch_core import BatchLedger,save_json,load_json
from webcollect.browser import fingerprint
from webcollect.candidate_feedback import summarize_scope,main,fold_groups
from site_planner.discovery_tools import reference
from site_planner import entry_selection as selection


class Feedback(unittest.TestCase):
    def setUp(self):
        self.p=producer.Optimization('test_A_complete_restart_and_old_only_new_batch_zero_dispatch')
        self.p.setUp();self.addCleanup(self.p.doCleanups)
        self.inv=self.p.inv;self.root=self.p.root;self.pool=self.inv.pool
        self.ledger=BatchLedger(self.root/'consumer.db',self.p.config,initialize=True)
        self.registry=self.root/'runtime.db'
        with sqlite3.connect(self.registry) as con:
            con.executescript('''CREATE TABLE m4_tasks(task_key TEXT,scope_id TEXT,task_json TEXT);
                CREATE TABLE m4_attempts(attempt_id TEXT,task_key TEXT,status TEXT);
                CREATE TABLE m4_events(event_id INTEGER PRIMARY KEY,scope_id TEXT,event_type TEXT,at REAL,payload_json TEXT);''')
        self.scope={'pool':str(self.pool.path),'batch':'feedback-batch','consumer_db':str(self.ledger.path),'registry':str(self.registry)}
        self.n=0

    def candidate(self,host='bad.example.org',page_type='功能页',outcome='http521',*,pause=None,category_unknown=False):
        from PIL import Image
        n=self.n;self.n+=1;uri=f'https://{host}/p{n}'
        producer_receipt=self.root/('producer-'+str(n)+'.json')
        save_json(producer_receipt,{'entry_uri':uri,'http_status':200,'result':'PASS'})
        source=self.inv.source(selection_version=selection.VERSION,page_type=page_type,entry_http=reference(producer_receipt),
            application_classification={'version':selection.VERSION,'parent_category':'UNKNOWN','status':'UNKNOWN'})
        header={'row_id':str(n),'run_id':'feedback-batch','batch':0,'raw_index':n,
                'request_id':'fixture','response_sha256':str(n)}
        cid=self.pool.publish_row(header,self.inv.entry(uri),source)['candidate_id']
        if outcome=='unclaimed':return cid
        claim=self.pool.claim_next('worker-'+str(n),'claim/'+str(n),candidate_id=cid,protocols=('webcollect-data-candidate-2',))
        output=self.root/('observation-'+str(n));output.mkdir()
        self.pool.stage(claim,'observation',{'output':str(output),'ledger':str(self.ledger.path)})
        jid=self.ledger.enqueue('candidate-observation',{'claim_id':claim['claim_id'],'site_uri':uri})
        job=self.ledger.claim('candidate-observation',job_id=jid)
        at=100+n*10
        if outcome not in ('not_dispatched',):
            status=521 if outcome=='http521' else None if outcome=='unknown' else 200
            visit_state='failed' if status==521 else 'unknown' if outcome=='unknown' else 'succeeded'
            with self.ledger.transaction() as con:
                con.execute('INSERT INTO top_level_visits VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    ('visit-'+str(n),jid,'candidate-entry:'+claim['claim_id'],1,uri,host,at,at+1,visit_state,status,uri,None,None,'{}'))
        if outcome in ('success','soft404','tampered','missing','login','captcha'):
            title={'soft404':'页面不存在','login':'请先登录','captcha':'请输入验证码'}.get(outcome,'中文计算器')
            state={'url':uri,'title':title,'elements':[]}
            stream=io.BytesIO();Image.new('RGB',(2,2),'white').save(stream,format='PNG');png=stream.getvalue()
            (output/'first.png').write_bytes(png);save_json(output/'first-state.json',state)
            capture={'snapshot_source':'browser_dom','coordinate_space':'screenshot_css_pixels',
                'screenshot_sha256':hashlib.sha256(png).hexdigest(),'attempts':[{'dom_stable':True,
                'before_fingerprint':fingerprint(state),'after_fingerprint':fingerprint(state)}]}
            save_json(output/'first-capture.json',capture)
            refs={'image':reference(output/'first.png'),'state':reference(output/'first-state.json'),'capture':reference(output/'first-capture.json')}
            self.ledger.finish(job,result=refs)
            with self.ledger.transaction() as con:con.execute('UPDATE jobs SET updated=? WHERE id=?',(at+2,jid))
            if outcome=='tampered':(output/'first.png').write_bytes(b'CONTROLLED tamper')
            if outcome=='missing':(output/'first-capture.json').unlink()
        else:
            if outcome=='stale':save_json(output/'first-observation-failure.json',{'job_id':jid,'error_type':'EvidenceStale','reason':'CONTROLLED unsynchronized'})
            self.ledger.finish(job,'review_required',error='EvidenceStale' if outcome=='stale' else 'CONTROLLED no frame')
        reason='Entry category UNKNOWN; no formal quota' if category_unknown else 'CONTROLLED final claim failure does not decide first frame'
        self.pool.finish(claim,state='failed',stage='planning',reason=reason)
        if pause:
            runtime_output=str((output/'execution/capture').resolve())
            scope_id='output-'+hashlib.sha256(runtime_output.encode()).hexdigest()
            with sqlite3.connect(self.registry) as con:
                con.execute('INSERT INTO m4_events VALUES(?,?,?,?,?)',(n+1,scope_id,'resource_checkpoint',at+3 if pause=='after' else at-1,
                    json.dumps({'reasons':['campaign_worker_time_limit']})))
        return cid

    def test_D_job_bound_frame_validation_pauses_and_coverage(self):
        self.candidate(outcome='success',pause='after',category_unknown=True)
        self.candidate(outcome='http521');self.candidate(outcome='stale')
        self.candidate(outcome='unknown');self.candidate(outcome='missing');self.candidate(outcome='tampered')
        self.candidate(outcome='not_dispatched',pause='before');self.candidate(outcome='unclaimed')
        report=summarize_scope(self.scope)
        self.assertEqual(report['net_new'],8)
        self.assertEqual(report['trusted_first_frames'],1)
        self.assertEqual(report['determinate'],4) # success,521,stale,tampered; absent proof stays unevaluated.
        self.assertEqual(report['time_pauses'],{'after_frame':1,'before_frame':1})
        self.assertEqual(report['category_unknown'],{'after_frame':1})
        self.assertEqual(report['formal_attempts'],0);self.assertEqual(report['saved'],0)
        failed=next(r for r in report['outcomes'] if r['reason']=='browser_http_521')
        self.assertEqual((failed['producer_http_status'],failed['browser_http_status']),(200,521))
        self.assertEqual(report,summarize_scope(self.scope))
        duplicate=summarize_scope({'scopes':[self.scope,self.scope]})
        for key in ('net_new','trusted_first_frames','determinate','time_pauses'):self.assertEqual(duplicate[key],report[key])

    def test_D_two_distinct_same_group_failures_change_actual_CLI_selection_and_freeze(self):
        ids=[self.candidate() for _ in range(2)]
        scope=self.root/'feedback-scope.json';save_json(scope,self.scope)
        report=summarize_scope(self.scope)
        self.p.export('feedback-before-selection',report)
        group=report['groups'][0]
        self.assertTrue(group['deprioritized']);self.assertEqual(group['streak_candidate_ids'],ids)
        hits=[{**self.p.hit(100,'bad.example.org'),'page_type':'功能页'},
              {**self.p.hit(2,'normal.example.org'),'page_type':'功能页'}]
        self.p.f.response([{'source_index':0,'page_type':'功能页'}])
        first=self.p.cli(hits,mode='expand',feedback=scope,target=1)
        rows=[r for r in self.pool.rows(protocols=('webcollect-data-candidate-2',)) if r['candidate_id'] in first['candidate_ids']]
        self.assertEqual(rows[0]['candidate']['entry_url'],hits[1]['uri'])
        payload=json.loads(self.p.f.provider.opener.calls[0].data)
        context=json.loads(payload['messages'][1]['content'][0]['text'])
        self.assertEqual(context['sources'][0]['uri'],hits[1]['uri'])
        self.assertEqual(context['sources'][1]['ranking_reason']['candidate_ids'],ids)
        self.candidate(outcome='success') # A later success changes future feedback, not frozen work.
        replay=self.p.cli(hits,mode='expand',feedback=scope,target=1)
        self.assertEqual(replay['candidate_ids'],first['candidate_ids'])
        self.assertEqual(replay['new_dispatches'],{'search':0,'model':0,'GET':0})

    def test_D_single_failure_separate_host_type_collector_time_and_unknown_are_neutral(self):
        self.candidate(host='one.example.org');self.candidate(host='two.example.org')
        self.candidate(host='types.example.org',page_type='功能页');self.candidate(host='types.example.org',page_type='内容详情')
        for n in range(2):
            self.candidate(host='time.example.org',outcome='success',pause='after')
            self.candidate(host='unknown.example.org',outcome='unknown')
            self.candidate(host='collector.example.org',outcome='stale')
            self.candidate(host='before.example.org',outcome='not_dispatched',pause='before')
        report=summarize_scope(self.scope)
        self.assertTrue(all(not g['deprioritized'] for g in report['groups']))
        self.assertEqual(report['time_pauses'],{'after_frame':2,'before_frame':2})
        self.assertTrue(all(g['success_rate'] is None for g in report['groups'] if g['host'] in ('unknown.example.org','before.example.org')))

    def test_D_soft_error_availability_is_separate_from_verified_capture(self):
        for outcome in ('soft404','login','captcha'):self.candidate(host=outcome+'.example.org',outcome=outcome)
        report=summarize_scope(self.scope)
        self.assertTrue(all(r['frame_verified'] for r in report['outcomes']))
        self.assertTrue(all(r['attributable'] for r in report['outcomes']))
        self.assertEqual(set(report['reasons']),{'soft_404','login_wall','captcha'})
        self.assertEqual(report['trusted_first_frames'],3)
        self.assertEqual(report['usable_first_frames'],0)

    def test_D_success_interrupts_consecutive_failures_and_reports_are_readonly(self):
        self.candidate();self.candidate(outcome='success');self.candidate()
        scope_path=self.root/'scope.json';save_json(scope_path,self.scope)
        sources=[self.pool.path,self.ledger.path,self.registry]
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        with redirect_stdout(io.StringIO()):main(['--scope',str(scope_path),'--output',str(self.root/'report.json')])
        report=load_json(self.root/'report.json')
        self.assertFalse(report['groups'][0]['deprioritized'])
        self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
        with self.assertRaises(ValueError):main(['--scope',str(scope_path),'--output',str(self.root/'report.json')])

    def test_D_duplicate_claim_and_worker_ledgers_fold_first_visit_once(self):
        cid=self.candidate(outcome='success')
        with self.pool.transaction() as con:
            claim=dict(con.execute('SELECT * FROM candidate_claims WHERE candidate_id=?',(cid,)).fetchone())
            claim.update(token='later-token',claim_id='later-claim',request_id='later-request',worker_id='later-worker',created=200,updated=200)
            cols=list(claim)
            con.execute('INSERT INTO candidate_claims('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',[claim[c] for c in cols])
        second=BatchLedger(self.root/'worker2.db',self.p.config,initialize=True)
        jid=second.enqueue('candidate-observation',{'claim_id':'later-claim','site_uri':'https://bad.example.org/p0'})
        job=second.claim('candidate-observation',job_id=jid)
        with second.transaction() as con:
            con.execute('INSERT INTO top_level_visits VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('later',jid,'candidate-entry:later-claim',1,'https://bad.example.org/p0','bad.example.org',200,201,'failed',521,'https://bad.example.org/p0',None,None,'{}'))
        second.finish(job,'review_required',error='CONTROLLED later failure')
        report=summarize_scope({**self.scope,'consumer_dbs':[str(second.path),str(self.ledger.path)]})
        self.assertEqual(report['net_new'],1);self.assertEqual(report['trusted_first_frames'],1)
        self.assertEqual(report['determinate'],1);self.assertEqual(report['outcomes'][0]['visit_id'],'visit-0')


if __name__=='__main__':unittest.main()
