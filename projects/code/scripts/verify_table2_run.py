"""Focused offline regression for the Table2 fixed-run engineering boundaries."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from webcollect import collection_report, site_workers
from webcollect.batch_core import BudgetStop
from webcollect.failure_policy import RoundFailures, disposition, safe_retry
from webcollect.model_gateway import _qc_addresses
from webcollect.navigation import NavigationHTTPError, NavigationTimeoutError
from webcollect.production_quality import require_public_task_state


class Table2RunChecks(unittest.TestCase):
    def test_resume_retains_original_cohort_and_worker_ownership(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();scope_path=root/'scope.json';scope_path.write_text('{}')
            scope={k:str(root/k) for k in ('pool','consumer_config','consumer_db','registry','history_set','policy','output')}
            cohort=root/'cohort.json'
            cohort.write_text(json.dumps({'selected':[{'candidate_id':str(i),'application_id':'site'+str(i%3),'order':i+1} for i in range(100)],'denominator':100}))
            with patch.object(site_workers,'load_scope',return_value=(scope_path,scope)):
                first=site_workers.fixed_consumer_plan(scope_path,cohort,root/'first')
                (root/'first/summary.json').write_text(json.dumps({'workers':[{'returncode':0} for _ in range(20)]}))
                second=site_workers.fixed_consumer_plan(scope_path,cohort,root/'second',resume_from=root/'first/prepared-plan.json')
            self.assertEqual(second['cohort'],first['cohort'])
            self.assertEqual(second['prior_worker_ids'],[w['worker_id'] for w in first['workers']])
            self.assertEqual([w['candidate_ids'] for w in first['workers']],[w['candidate_ids'] for w in second['workers']])
            self.assertEqual(second['previous_run_roots'],[first['log_root']])

    def test_unrelated_owner_does_not_replay_closure_audit(self):
        from types import SimpleNamespace
        from webcollect.current_chain import PROJECT_RULES
        from webcollect.request_quarantine import job_conflicts
        ledger=SimpleNamespace(path=Path('/unused/jobs.sqlite3'),config={'site_failure_guard':{'dispatch_rules':PROJECT_RULES}})
        owner={'task_id':'old-task','candidate_id':'old','uri':'https://example.org/old','site_uri':'https://example.org'}
        with patch('webcollect.request_quarantine.attempt_owner',return_value=owner), \
             patch('webcollect.request_quarantine.accounted_closed_execution',side_effect=AssertionError('unrelated audit')):
            self.assertFalse(job_conflicts(ledger,'https://example.org/new','new',
                {'attempt_id':'old-attempt','task_id':'old-task'},running=False,candidate_only=True))

    def test_entry_rejections_do_not_stop_other_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            failures = RoundFailures(Path(folder)/'events.jsonl')
            for index in range(3):
                try:
                    raise NavigationHTTPError('https://example.org/'+str(index), 403)
                except NavigationHTTPError as error:
                    row = failures.record(str(index), disposition(error))
                    self.assertEqual(row['disposition'], 'business')
                    self.assertFalse(row['stop_dispatch'])
            self.assertEqual(disposition(NavigationTimeoutError('https://example.org', 'entry', 30))['reason_owner'], 'site')
            from playwright.async_api import Error as BrowserError
            for index in range(3):
                row=failures.record('geometry-'+str(index),disposition(BrowserError('Page.evaluate: Error: UNSUPPORTED_GEOMETRY: rotation')))
                self.assertEqual(row['disposition'],'business')
                self.assertEqual(row['code'],'UNSUPPORTED_GEOMETRY')
                self.assertFalse(row['stop_dispatch'])
            self.assertEqual(disposition(BrowserError('Page.evaluate: TypeError: broken host code'))['disposition'],'page_program')
            from webcollect.browser import EvidenceStale
            for index in range(3):
                row=failures.record('unstable-'+str(index),disposition(EvidenceStale('pixels changed')))
                self.assertEqual(row['failure_class'],'collector')
                self.assertEqual(row['disposition'],'business')
                self.assertFalse(row['stop_dispatch'])
            try:
                require_public_task_state({'url': 'https://example.org/login'})
            except ValueError as error:
                self.assertEqual(disposition(error)['disposition'], 'business')

    def test_dns_deadline_and_stop_terminate_resolver(self):
        import multiprocessing
        before = {p.pid for p in multiprocessing.active_children()}
        started = time.monotonic()
        with patch('webcollect.model_gateway.socket.getaddrinfo', side_effect=lambda *a, **k: time.sleep(5)):
            with self.assertRaises(TimeoutError):
                _qc_addresses('unused.invalid', 443, started+.05)
        self.assertLess(time.monotonic()-started, .7)
        with self.assertRaises(InterruptedError):
            _qc_addresses('unused.invalid', 443, time.monotonic()+5, lambda: True)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)
        with self.assertRaises(BudgetStop):
            safe_retry(lambda: time.sleep(.02), safe=True, deadline=time.monotonic()+.005)

    def test_legacy_serialization_does_not_copy_evidence(self):
        from webcollect.workspace_paths import _root, HistoricalAbsolute, encode
        from webcollect import workspace_json
        value={'path':HistoricalAbsolute('/legacy/a'), 'nested':[{'path':'/legacy/b'}]}
        token=_root.set(None)
        try:
            self.assertIs(encode(value),value)
            self.assertEqual(workspace_json.dumps(value,sort_keys=True),json.dumps(value,sort_keys=True))
        finally:_root.reset(token)

    def test_begin_wait_uses_its_budget_and_preserves_single_write(self):
        import sqlite3, threading
        from webcollect.sqlite_connection import begin_immediate
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'locks.sqlite3'
            owner=sqlite3.connect(path,check_same_thread=False)
            owner.execute('CREATE TABLE events(value TEXT)');owner.commit()
            owner.execute('BEGIN IMMEDIATE')
            def release():
                time.sleep(.35);owner.commit()
            thread=threading.Thread(target=release);thread.start()
            with sqlite3.connect(path,timeout=2) as con:
                begin_immediate(con,timeout=2)
                con.execute("INSERT INTO events VALUES('once')")
            thread.join();owner.close()
            with sqlite3.connect(path) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM events').fetchone()[0],1)

    def test_history_plan_validation_keeps_exact_membership(self):
        from webcollect import current_chain
        tasks=[{'scope_id':'a','campaign_id':'c','task_json':json.dumps({'task_id':'one'})},
               {'scope_id':'a','campaign_id':'c','task_json':json.dumps({'task_id':'two'})}]
        scope={'schema_version':current_chain.SCOPE_SCHEMA}
        plans=[('a',json.dumps({'generation':{'history_scope':scope},'tasks':[{'task_id':name}]}))
               for name in ('one','two')]
        with patch.object(current_chain,'assert_registry_scope'),patch.object(current_chain,'_chain_identity',return_value='same'), \
             patch('webcollect.registry_db.history_rows',return_value=(list(tasks),list(plans))):
            result=current_chain._registry_snapshot(scope,'/unused')
        self.assertEqual({r['task']['task_id'] for r in result['rows']},{'one','two'})
        with patch.object(current_chain,'assert_registry_scope'),patch.object(current_chain,'_chain_identity',return_value='same'), \
             patch('webcollect.registry_db.history_rows',return_value=(list(tasks),list(plans[:1]))):
            with self.assertRaises(current_chain.CurrentChainError):
                current_chain._registry_snapshot(scope,'/unused')

    def test_history_slot_excludes_concurrent_reads_and_obeys_stop(self):
        import os,threading
        from webcollect.registry_db import history_read_slot
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'WEBCOLLECT_SERIAL_HISTORY':'1'}):
            path=Path(folder)/'registry.sqlite3';entered=threading.Event()
            def read():
                with history_read_slot(path):entered.set()
            with history_read_slot(path):
                thread=threading.Thread(target=read);thread.start()
                self.assertFalse(entered.wait(.15))
            thread.join(2);self.assertTrue(entered.is_set())
            stop=Path(folder)/'stop';stop.touch()
            with patch.dict(os.environ,{'WEBCOLLECT_STOP_FILE':str(stop)}):
                with self.assertRaises(InterruptedError):
                    with history_read_slot(path):self.fail('stopped read entered')

    def test_new_claim_preserves_unrelated_expired_claim(self):
        from site_planner.site_pool import SitePool
        from site_planner.candidate_pool import CandidatePool
        from webcollect.agent_feedback import reference
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve(); path=root/'pool.sqlite3'
            SitePool(path, initialize=True);pool=CandidatePool(path, install=True)
            proof=root/'source.json';proof.write_text('{}')
            ids=[pool.put({'schema_version':'webcollect-data-candidate-2','candidate_kind':'entry',
                'entry_url':f'https://example.org/{i}','requested_goal':None},
                {'origin':'codex_session','run_id':'offline','references':[reference(proof)]}) for i in range(2)]
            old=pool.claim_next('old','old-request',candidate_id=ids[0])
            with pool.transaction() as con:
                con.execute('UPDATE candidate_claims SET expires=0 WHERE claim_id=?',(old['claim_id'],))
            before=pool.get_claim(old['claim_id'])
            pool.claim_next('new','new-request',candidate_id=ids[1])
            self.assertEqual(pool.get_claim(old['claim_id']),before)

    def test_unknown_with_response_counts_as_http(self):
        result=collection_report.request_summary([{'state':'unknown','request_json':'{}',
            'response':json.dumps({'provider_error':{'http_status':429},'http_timing':{'headers_ms':10}})}])
        self.assertEqual(result['dispatch'], {'dispatched':1})
        self.assertIsNone(result['input_tokens'])
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'requests.sqlite3'
            with sqlite3.connect(path) as con:
                con.execute('CREATE TABLE model_requests(id TEXT,job_id TEXT,state TEXT,started REAL,usage TEXT,response TEXT,request_json TEXT)')
                con.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?)',('original','job','unknown',1,None,'{}',
                    json.dumps({'provider':'glm','http_dispatch':False,'images':['large original remains in ledger']})))
            projected=collection_report.rows(path,'model_requests')
            self.assertNotIn('images',json.loads(projected[0]['request_json']))
            self.assertIs(json.loads(projected[0]['request_json'])['http_dispatch'],False)
            self.assertEqual(collection_report.request_summary(projected)['dispatch'],{'not_dispatched':1})

    def test_failed_claim_without_receipt_is_not_proven(self):
        selected=[{'candidate_id':str(i),'version':1,'application_id':'site'+str(i%3)} for i in range(100)]
        claims=[{**r,'claim_id':'c'+r['candidate_id'],'state':'failed','created':1,'updated':2,
                 'binding':'{}','snapshot':'{}','reason':'unproven'} for r in selected]
        scope={k:k for k in ('pool','registry','consumer_db','producer_db')}
        with tempfile.TemporaryDirectory() as folder, \
             patch('webcollect.site_inventory.load_scope',return_value=('scope',scope)), \
             patch.object(collection_report,'load_json',return_value={'selected':selected,'denominator':100}), \
             patch.object(collection_report,'rows',side_effect=lambda p,t: claims if t=='candidate_claims' else []), \
             patch.object(collection_report,'jsonl',return_value=[]), \
             patch.object(collection_report,'connect'), \
             patch('webcollect.candidate_consumer.verified_saved',return_value=None):
            report=collection_report.build('scope','cohort',folder)
        self.assertEqual(report['integrity'],'FAILED')
        self.assertFalse(any(r['task_terminal_proven'] for r in report['candidates']))
        self.assertIn('unsettled_claims',report['issues'])

    def test_startup_probe_interrupt_still_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            plan={'fixed':True,'scope':'unused','cohort':'unused','role':'consumer','plan_id':'offline',
                  'log_root':folder,'workers':[]}
            scope={'consumer_db':'unused','consumer_config':'unused'}
            with patch('webcollect.collection_startup.check',return_value={'status':'PASS'}), \
                 patch.object(site_workers,'load_scope',return_value=('scope',scope)), \
                 patch('webcollect.batch_core.load_json',return_value={}), \
                 patch.object(site_workers,'BatchLedger'), \
                 patch('webcollect.key_health.pool_available',return_value=False), \
                 patch('webcollect.key_health.probe_accounts',side_effect=KeyboardInterrupt):
                result=site_workers.launch(plan)
            self.assertTrue(result['interrupted'])
            self.assertTrue((Path(folder)/'summary.json').is_file())
            self.assertTrue((Path(folder)/'report-error.json').is_file())
            self.assertEqual(result['workers'],[])


if __name__=='__main__':
    unittest.main()
