"""Exercise project-bound request isolation without network or browser access."""
import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import time
import unittest
from unittest.mock import patch

from site_planner.application_discovery import homepage_document
from webcollect.batch_core import BatchLedger, OutcomeUnknown, load_json
from webcollect.candidate_consumer import guard_candidate_dispatch, guard_request_scope
from webcollect.candidate_project import initialize
from webcollect.planning import object_sha256
from webcollect.runtime import RuntimeStore
from webcollect.site_failure_stop import SiteFailureStore, SiteStopped


class RequestQuarantineTests(unittest.TestCase):
    page = 'https://example.org/topics?id=1'
    other = 'https://example.org/topics?id=2'

    def setUp(self):
        from test_model_provider_protocols import ProviderProtocolTests
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        cfg = load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')
        cfg['budget'].update(max_concurrent_jobs=4,min_domain_interval_seconds=1)
        self.scope = load_json(initialize(self.root/'project','quarantine-test',{},
                                         ProviderProtocolTests().config('glm'),cfg))
        self.ledger = BatchLedger(self.scope['consumer_db'],load_json(self.scope['consumer_config']),initialize=True)
        self.binding = self.ledger.config['site_failure_guard']
        self.store = SiteFailureStore(self.binding)

    def test_unknown_document_get_keeps_original_and_another_page_can_be_read_after_restart(self):
        producer = BatchLedger(self.scope['producer_db'],load_json(self.scope['producer_config']),initialize=True)
        old = 'https://www.example.org/vue/tutorial'
        other = 'https://www.example.org/react/tutorial'
        with patch('site_planner.pipeline.open_public_get',side_effect=TimeoutError('no HTTP response')) as send:
            with self.assertRaises(TimeoutError):
                homepage_document(producer,'a',old,self.root)
            with self.assertRaises(OutcomeUnknown):
                homepage_document(producer,'b',old,self.root)
            self.assertEqual(send.call_count,1)
        before = producer.visits()
        self.assertEqual([(v['state'],v['target_uri']) for v in before],[('unknown',old)])
        fresh = BatchLedger(producer.path,producer.config)
        with self.assertRaisesRegex(SiteStopped,'entry_uri_hold'):
            self.store.guard('http://example.org/vue/tutorial/?utm_source=test#ref')
        self.assertEqual(self.store.guard(other)['whole_application_unknowns'],0)
        with patch('site_planner.pipeline.open_public_get') as send:
            response = send.return_value.__enter__.return_value
            response.status=200
            response.geturl.return_value=other
            response.read.return_value='<html lang="zh"><p>教程</p>'.encode()
            response.headers=None
            record,_=homepage_document(fresh,'b',other,self.root)
            self.assertEqual(record['http_status'],200)
            self.assertEqual(send.call_count,1)
        self.assertEqual(next(v for v in fresh.visits() if v['id']==before[0]['id']),before[0])

    def original_task(self):
        now=time.time()
        task={'task_id':'old-task','site_uri':self.page,'initial_url':self.page,
              'candidate_binding':{'candidate_id':'original-candidate','candidate':{'entry_url':self.page}}}
        with closing(sqlite3.connect(self.scope['registry'])) as con:
            con.execute('INSERT INTO m4_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        ('old-key','project-setup','quarantine-test','old-task','v1',object_sha256(task),
                         json.dumps(task),'在线工具','example.org','failed',0,now+100,now,now))
            con.execute('INSERT INTO m4_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        ('original-attempt','project-setup','quarantine-test','old-key','plan','original-request',
                         'worker','fixture',now,'fixture-1','site','batch','interrupted',now,now,now,None,
                         'interrupted','original effect unconfirmed','[]'))
            con.commit()
        return task

    def test_model_and_formal_unknown_follow_original_candidate_even_on_same_url(self):
        task=self.original_task()
        self.store.sync_formal(self.scope['registry'],'quarantine-test')
        alias=self.page.replace('://example.', '://www.example.')
        RuntimeStore._guard_site({'site_failure_guard':self.binding},{**task,'initial_url':alias,
                                                                    'candidate_binding':{'candidate_id':'independent-goal'}})
        with self.assertRaisesRegex(SiteStopped,'task_hold'):
            RuntimeStore._guard_site({'site_failure_guard':self.binding},task)
        # A read-only browser GET does not repeat the interrupted form action.
        self.store.guard(self.page)
        payload={'site_uri':alias,'task_id':task['task_id'],'attempt_id':'original-attempt'}
        jid=self.ledger.enqueue('react-native-decision',payload)
        job=self.ledger.claim('react-native-decision',job_id=jid)
        material={'protocol':'native-tool-1','http_dispatch':True,'dispatch_attempt_id':'original-attempt'}
        req=self.ledger.reserve_request(job,'round',0,material)
        for state in ('reserved','unknown'):
            if state=='unknown':
                self.ledger.settle_request(req['id'],state=state,error='TimeoutError')
                self.ledger.finish(job,'review_required',error='TimeoutError')
            ledger=BatchLedger(self.ledger.path,self.ledger.config)
            with self.assertRaises(OutcomeUnknown):
                guard_request_scope(ledger,self.other,candidate_id='original-candidate')
            self.assertEqual(guard_candidate_dispatch(ledger,self.page,candidate_id='independent-goal')[0]['id'],req['id'])
            self.assertEqual(guard_request_scope(ledger,self.other)[0]['state'],state)
            with self.assertRaises(OutcomeUnknown):
                guard_request_scope(ledger,self.page)
            with ledger.connect() as con:
                self.assertEqual(tuple(con.execute('SELECT id,state,usage FROM model_requests').fetchone()),(req['id'],state,None))
        # Renaming the job cannot dispatch another HTTP for the unresolved attempt.
        another=ledger.enqueue('react-native-decision',{**payload,'decision':2})
        replacement=ledger.claim('react-native-decision',job_id=another)
        with self.assertRaises(OutcomeUnknown):
            ledger.reserve_request(replacement,'another round',0,material)
        # A separate task and attempt on the same page can reserve their own request.
        independent=ledger.enqueue('react-native-decision',{**payload,'attempt_id':'new-attempt','task_id':'another-task'})
        new=ledger.claim('react-native-decision',job_id=independent)
        dispatched=ledger.reserve_request(new,'round',0,{**material,'dispatch_attempt_id':'new-attempt'})
        self.assertNotEqual(dispatched['id'],req['id'])

    def test_formal_react_reaches_chooser_for_other_candidate_and_keeps_original_in_history(self):
        from webcollect.agent_feedback import site_context
        from webcollect.collect_runtime import CollectionFailure, _react_collection
        task = self.original_task()
        old = self.ledger
        jid = old.enqueue('react-native-decision', {'site_uri':self.page, 'task_id':task['task_id'],
                                                   'attempt_id':'original-attempt'})
        job = old.claim('react-native-decision', job_id=jid)
        old.finish(job, 'review_required', error='unsettled original')
        ledger = BatchLedger(old.path,old.config)
        def context(candidate):
            return site_context(self.scope['registry'], self.page, model_ledger=ledger, candidate_id=candidate)
        independent = context('independent')
        self.assertEqual(independent['unresolved'],[])
        self.assertEqual([r['attempt_id'] for r in independent['executions']],['original-attempt'])
        for candidate in ('original-candidate', None):
            holds=context(candidate)['unresolved']
            self.assertEqual({r.get('attempt_id') or r['job_id'] for r in holds},{'original-attempt',jid})
        attempt={'attempt_id':'next-attempt','sample_id':'next-sample','site_id':'site','batch_id':'batch'}
        def run(candidate):
            current={**task,'candidate_binding':{'candidate_id':candidate}}
            return asyncio.run(_react_collection(None,current,attempt,None,None,None,None,ledger=ledger,
                    parent_job=None,registry=self.scope['registry'],manifest={},index=0))
        class ReachedChooser(Exception):
            pass
        with patch('webcollect.react_session.react_chooser', side_effect=ReachedChooser) as choose:
            with self.assertRaises(CollectionFailure):
                run('original-candidate')
            choose.assert_not_called()
            with self.assertRaises(ReachedChooser):
                run('independent')
            choose.assert_called_once()

    def test_unattributed_model_request_and_provider_authorization_still_block(self):
        job_id=self.ledger.enqueue('fragment-decision',{})
        job=self.ledger.claim('fragment-decision',job_id=job_id)
        request=self.ledger.reserve_request(job,'original',0,{})
        with self.assertRaises(OutcomeUnknown):
            guard_candidate_dispatch(self.ledger,self.other,candidate_id='independent')
        self.ledger.settle_request(request['id'],state='unknown',error='HTTPError:401')
        self.ledger.finish(job,'review_required',error='provider')
        with self.assertRaisesRegex(OutcomeUnknown,'authorization'):
            guard_request_scope(BatchLedger(self.ledger.path,self.ledger.config),'https://other.example.org/')

    def test_worker_keeps_original_claim_in_reconciliation_and_processes_next_page(self):
        from site_planner.candidate_pool import CandidatePool
        VERSION = 'webcollect-data-candidate-1'  # historical v1 body, kept only as fixture data
        from webcollect.agent_feedback import reference
        from webcollect.candidate_consumer import run
        pool = CandidatePool(self.scope['pool'])
        proof = self.root/'fixture.json'
        proof.write_text('{}')
        ids = []
        for n, uri in enumerate((self.page,self.other)):
            candidate={'schema_version':VERSION,'entry_url':uri,'name':'离线工具','parent_category':'在线工具',
                       'business_kind':'换算','description':'按输入换算数值',
                       'target':{'kind':'convert','entity':'quantity','parameters':{'value':n+1}}}
            ids.append(pool.put(candidate,{'origin':'codex_session','run_id':'offline','references':[reference(proof)]}))
        jid = self.ledger.enqueue('candidate-observation',{'site_uri':self.page})
        job = self.ledger.claim('candidate-observation',job_id=jid)
        visit = self.ledger.reserve_visit(job,self.page,'initial','example.org')
        self.ledger.settle_visit(visit,state='unknown',error=TimeoutError())
        processed = []
        async def consume(pool,claim,ledger,**kwargs):
            guard_candidate_dispatch(ledger,claim['snapshot']['entry_url'],candidate_id=claim['candidate_id'])
            processed.append(claim['candidate_id'])
            pool.finish(claim,state='failed',stage='planning',reason='fixture completed without a path')
            return {'state':'failed'}
        with patch('webcollect.candidate_consumer.startup_check',return_value={}), \
                patch('webcollect.candidate_consumer.consume',consume):
            result=asyncio.run(run(pool,self.ledger,worker_id='worker',request_prefix='isolated',limit=2))
        self.assertEqual([row['state'] for row in result],['reconcile','failed'])
        self.assertEqual(processed,[ids[1]])
        self.assertEqual([(v['id'],v['state']) for v in self.ledger.visits()],[(visit['id'],'unknown')])

    def test_business_query_keeps_parameter_order_and_http_fragment_is_local(self):
        from webcollect.request_quarantine import endpoint
        self.assertNotEqual(endpoint(self.page+'&id=2'),endpoint(self.other+'&id=1'))
        self.assertEqual(endpoint('https://www.example.org/工具/?id=1&utm_medium=foo#one'),
                         endpoint('http://example.org/%E5%B7%A5%E5%85%B7?id=1#two'))

    def test_two_concurrent_visits_same_endpoint_dispatch_once_independent_query_can_run(self):
        jobs=[]
        for i in range(3):
            jid=self.ledger.enqueue('candidate-observation',{'claim_id':str(i)})
            jobs.append(self.ledger.claim('candidate-observation',job_id=jid))
        barrier=Barrier(2)
        def reserve(arguments):
            job,url=arguments
            barrier.wait(timeout=5)
            try:
                return self.ledger.reserve_visit(job,url,'test','example.org')
            except OutcomeUnknown:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            visits=list(executor.map(reserve,[(jobs[0],self.page),(jobs[1],self.page+'&utm_source=box#tab')]))
        self.assertEqual(sum(v is not None for v in visits),1)
        first=next(v for v in visits if v)
        with self.assertRaises(OutcomeUnknown):
            guard_request_scope(self.ledger,self.page)
        guard_request_scope(self.ledger,self.other)
        with patch('webcollect.batch_core.time.time',return_value=time.time()+2):
            self.ledger.reserve_visit(jobs[2],self.other,'test','example.org')
        self.ledger.settle_visit(first,state='unknown',error=TimeoutError())
        with self.assertRaises(OutcomeUnknown):
            self.ledger.reserve_visit(jobs[0],self.page,'different purpose','example.org')
        self.assertEqual(Counter(v['state'] for v in self.ledger.visits()),{'unknown':1,'reserved_for_dispatch':1})
