"""Read-only selection, evidence-based reading and pair-scoped QC fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from webcollect.batch_core import load_json, save_json, file_sha, OutcomeUnknown
from webcollect.agent_feedback import reference
from webcollect.planning import object_sha256
from webcollect.candidate_cohort import inspect_rows, freeze, ReadOnlyLedger
from webcollect.reading_progress import project, control_return, ending, VERSION
from webcollect.task_instruction import generated_instruction
from quality_inspector.ai_worker import do_difference, snapshot, DIFFERENCE_PROTOCOL, compact_trajectory
from test_react_session import ReactHarness, decide, act_step
import test_react_native as native_fixture
from test_react_native import scroll, finish


class SelectionTests(unittest.TestCase):
    page='https://example.org/page/0'
    other='https://example.org/page/1'
    def setUp(self):
        from test_request_quarantine import RequestQuarantineTests
        RequestQuarantineTests.setUp(self)
        from site_planner.candidate_pool import CandidatePool
        from webcollect.batch_core import BatchLedger
        from site_planner.entry_access import POLICY
        self.pool=CandidatePool(self.scope['pool'])
        producer=BatchLedger(self.scope['producer_db'],load_json(self.scope['producer_config']),initialize=True)
        self.ids=[]
        for n in range(4):
            uri='https://example.org/page/'+str(n)
            receipt=self.root/f'get-{n}.json'
            jid=producer.enqueue('candidate-entry-http',{'uri':uri,'policy':POLICY})
            job=producer.claim('candidate-entry-http',job_id=jid)
            visit=producer.reserve_visit(job,uri,'candidate-entry-http',f'fixture{n}.example.org')
            producer.settle_visit(visit,state='succeeded',response_status=200,landed_uri=uri)
            save_json(receipt,{'method':'GET','result':'PASS','http_status':200,
                               'entry_uri':uri,'visit_id':visit['id'],'job_id':jid,'policy':POLICY,'landed_uri':uri})
            producer.finish(job,result=reference(receipt))
            body={'schema_version':'webcollect-data-candidate-2','candidate_kind':'entry',
                  'entry_url':uri,'requested_goal':None}
            source={'origin':'codex_session','run_id':'fixture','references':[reference(receipt)],
                    'entry_http':reference(receipt),'category_hint':'在线工具'}
            cid=self.pool.put(body,source);self.ids.append(cid)
            with self.pool.transaction() as con:
                con.execute('INSERT INTO candidate_batch_rows VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    ('row-'+str(n),'batch-'+str(n),0,'request-'+str(n),'1'*64,n,'NEW',None,cid,
                     json.dumps({'candidate_id':cid}),n+1))
        self.scope_path=self.root/'project/scope.json'

    def test_reproducible_read_only_and_worker_frozen_row(self):
        before=file_sha(self.pool.path);ledger_before=file_sha(self.ledger.path)
        a=freeze(self.scope_path,self.root/'a',count=3,seed='fixed')
        b=freeze(self.scope_path,self.root/'b',count=3,seed='fixed')
        first=load_json(a['cohort'])['selected'];second=load_json(b['cohort'])['selected']
        self.assertEqual(first,second)
        self.assertEqual(file_sha(self.pool.path),before);self.assertEqual(file_sha(self.ledger.path),ledger_before)
        from webcollect.candidate_consumer import _cohort_rows
        _,rows=_cohort_rows(a['cohort'],self.pool,self.scope['registry'],None)
        row=rows[0]
        claim=self.pool.claim_next('worker','request',candidate_id=row['candidate_id'],frozen_row=row,
            producer_batch=row['producer_batch'],protocols=('webcollect-data-candidate-2',))
        self.assertEqual(claim['candidate_id'],row['candidate_id'])
        self.assertEqual(self.pool.claim_next('other','new',candidate_id=row['candidate_id'],frozen_row=row,
            producer_batch=row['producer_batch'],protocols=('webcollect-data-candidate-2',))['state'],'ALREADY_CLAIMED')

    def test_original_claim_and_exact_list_rejection_never_top_up(self):
        cid=self.ids[0]
        self.pool.claim_next('worker','original',candidate_id=cid,protocols=('webcollect-data-candidate-2',))
        result=freeze(self.scope_path,self.root/'blocked',candidate_ids=[cid,self.ids[1]])
        self.assertFalse(result['selection_complete']);self.assertIsNone(result['cohort'])
        self.assertEqual(result['selected_count'],1)
        dry=freeze(self.scope_path,self.root/'dry',count=2,dry_run=True)
        self.assertTrue(dry['selection_complete']);self.assertIsNone(dry['cohort'])
        with self.assertRaises(FileExistsError):freeze(self.scope_path,self.root/'dry',count=2)

    def test_unfinished_formal_planning_job_and_changed_get_rejected(self):
        uri='https://example.org/page/0'
        self.ledger.enqueue('react-native-decision',{'site_uri':uri})
        _,rows,audit=inspect_rows(self.scope_path,candidate_ids=self.ids[:2])
        self.assertFalse(rows[0]['eligible']);self.assertIn('planning job',rows[0]['rejection']['reason'])
        self.assertTrue(rows[1]['eligible']);self.assertEqual(audit['layers']['dispatch_guard_pass'],1)
        (self.root/'get-1.json').write_text('{}')
        _,rows,_=inspect_rows(self.scope_path,candidate_ids=[self.ids[1]])
        self.assertFalse(rows[0]['eligible'])

    def test_source_change_after_freeze_blocks_claim_inside_original_transaction(self):
        result=freeze(self.scope_path,self.root/'fixed',candidate_ids=[self.ids[0]])
        row=load_json(result['cohort'])['selected'][0]
        with self.pool.transaction() as con:
            con.execute('INSERT INTO candidate_sources VALUES(?,?,?,?)',(row['candidate_id'],'later',
                json.dumps({'origin':'codex_session','references':[]}),99))
        with self.assertRaisesRegex(ValueError,'sources changed'):
            self.pool.claim_next('w','r',candidate_id=row['candidate_id'],frozen_row=row,
                producer_batch=row['producer_batch'],protocols=('webcollect-data-candidate-2',))
        with self.pool.pool.connect() as con:self.assertEqual(con.execute('SELECT count(*) FROM candidate_claims').fetchone()[0],0)

    def test_formal_interruption_without_synced_site_fact_is_already_excluded(self):
        from test_request_quarantine import RequestQuarantineTests
        import sqlite3
        task=RequestQuarantineTests.original_task(self)
        task['candidate_binding']['candidate_id']=self.ids[0]
        with sqlite3.connect(self.scope['registry']) as con:
            con.execute('UPDATE m4_tasks SET task_json=? WHERE task_key=?',(json.dumps(task),'old-key'))
        _,rows,_=inspect_rows(self.scope_path,candidate_ids=self.ids[:2])
        self.assertFalse(rows[0]['eligible']);self.assertIn('formal attempt',rows[0]['rejection']['reason'])
        self.assertTrue(rows[1]['eligible'])


class ReadingTests(unittest.TestCase):
    def test_seen_new_text_and_control_return_need_actual_bound_control(self):
        origin={'url':'https://example.org/','scroll':[0,0],'visible_text':'标题\nAndroid',
                'screen_resolution':[100,100],'elements':[{'element_id':'tab','text':'Android','visible':True,'bbox':[1,1,40,20]}]}
        middle={**origin,'scroll':[0,480],'visible_text':'新内容\n更新说明','elements':[]}
        current=deepcopy(origin)
        progress=project({'a':origin,'b':middle,'c':current},'c',[])
        self.assertEqual(progress['new_line_count'],0);self.assertTrue(progress['exact_view_seen_before'])
        progress=project({'a':origin,'b':middle},'b',[])
        self.assertEqual(progress['new_visible_quotes'],['新内容','更新说明'])
        operation={'action_type':'click','evidence':{'anchor_element_id':'tab','target_label':'Android'}}
        self.assertTrue(control_return(origin,middle,current,operation))
        self.assertFalse(control_return(origin,middle,current,{'action_type':'scroll'}))
        self.assertFalse(control_return(origin,origin,current,operation))
        self.assertFalse(control_return(origin,middle,current,{**operation,'evidence':{'anchor_element_id':'fake'}}))

    def test_five_is_not_completion_and_generated_task_quotes_preserve_source_quotes(self):
        proof=ending(5,{'visible_text':''})
        self.assertTrue(proof['minimum_reached']);self.assertFalse(proof['automatic_success'])
        self.assertFalse(proof['visible_terminal_material']);self.assertFalse(proof['finish_complete_counted'])
        self.assertEqual(generated_instruction('核对《须知》及「原文《法律》」'),'核对「须知」及「原文《法律》」')
        self.assertEqual(generated_instruction('「原文《须知》」与《须知》'),'「原文《须知》」与「须知」')


class ReadingSessionTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    recorded=native_fixture.NativeSessionTests.recorded
    def setUp(self):
        super().setUp()
        self.ids={'sample_id':'S000001_sample_000001'}

    async def test_five_effective_operations_and_finish_are_separate_in_normal_session(self):
        from webcollect.react_session import build_url_task
        self.task=build_url_task(url=self.page.url,task_version='five-current')
        session,evidence,script=self.recorded([scroll('核对当前正文及后续条目'),scroll(),scroll(),scroll(),scroll(),finish()])
        result=await session.run()
        self.assertEqual(result['effective_steps'],5);self.assertFalse(result['short_flow'])
        self.assertEqual(len(self.surface.executed),5)
        proof=script.prompts[-1]['ending_evidence']
        self.assertTrue(proof['minimum_reached']);self.assertFalse(proof['automatic_success'])
        self.assertEqual(script.prompts[-1]['progress']['effective_steps'],5)
        self.assertTrue(list((evidence/'raw').glob('*ending-evidence.json')))

    async def test_real_round_trip_keeps_both_actions_and_rejects_ready_finish(self):
        from webcollect.react_session import build_url_task
        self.task=build_url_task(url=self.page.url,task_version='loop-current')
        original=self.surface.execute_action
        def action(kind,args):
            original(kind,args)
            if kind=='scroll' and args['direction']=='up':self.surface.state['scroll'][1]-=960
        self.surface.execute_action=action
        up=decide(tool='act',arguments=lambda p:{'observation_id':p['observation']['observation_id'],
            'step':act_step('scroll',direction='up',goal='回到原位置',expected='原位置')})
        session,evidence,_=self.recorded([scroll('核对正文'),up,finish()])
        result=await session.run()
        self.assertEqual(result['stop_reason'],'blocked');self.assertIn('READING_ROUND_TRIP',result['stop_summary'])
        self.assertEqual(result['effective_steps'],2);self.assertEqual(len(self.surface.executed),2)
        self.assertEqual(len((evidence/'raw/trajectory.jsonl').read_text().splitlines()),2)


class PairTests(unittest.TestCase):
    def setUp(self):
        from test_difference_batch_calibration import DifferenceBatchTests
        self.fixture=DifferenceBatchTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.calls=[]
        outer=self
        class Gateway:
            def call(self,job,purpose,text,schema,**kwargs):
                prompt=json.loads(text);outer.calls.append((purpose,prompt,schema))
                return {'status':'PASS','note':'CONTROLLED bound pair response, no real review',
                        'evidence_steps':schema['properties']['evidence_steps']['items']['enum']}
        self.gateway=Gateway()

    def job(self,neighbors=True):
        payload=deepcopy(self.fixture.source['payload']);payload['difference_protocol']=DIFFERENCE_PROTOCOL
        ids=[r['sample_id'] for r in payload['neighbors']]
        if not neighbors:payload['neighbors']=[]
        pending=[{'history_sample_ids':ids,'reason':'CONTROLLED collection question'}]
        ref=self.fixture.root/'checks.json';save_json(ref,pending)
        payload.update(pending_collection_checks=pending,collection_checks=reference(ref),required_history_missing=[])
        return {'id':'test','payload':payload}

    def test_each_request_scopes_questions_to_supplied_neighbor_and_host_aggregates(self):
        job=self.job();ledger=self.fixture.ledger
        with patch.object(ledger,'heartbeat'):
            result=do_difference(ledger,self.gateway,job)
        self.assertEqual(result['status'],'PASS');self.assertEqual(len(result['pair_decisions']),3)
        self.assertEqual(result['required_history_missing'],[])
        for _,prompt,schema in self.calls:
            for check in prompt.get('pending_collection_checks',[]):
                self.assertEqual(check['history_sample_ids'],[prompt['neighbor_sample_id']])
            allowed=schema['properties']['evidence_steps']['items']['enum']
            if 'focal_frame_ids' in prompt:self.assertEqual(allowed,prompt['focal_frame_ids'])

    def test_terminal_confirmation_has_no_extra_image_and_missing_history_never_passes(self):
        job=self.job(neighbors=False)
        with patch.object(self.fixture.ledger,'heartbeat'):
            result=do_difference(self.fixture.ledger,self.gateway,job)
        self.assertEqual(result['status'],'REVIEW_REQUIRED');self.assertEqual(self.calls,[])
        context,_=compact_trajectory(job['payload']['candidate'])
        terminal=context['steps'][-1]['adjacent_image_evidence']
        self.assertIsNone(terminal['after_frame_id'])
        self.assertEqual(terminal['image_difference_applicability'],'NOT_APPLICABLE_TERMINAL_CONFIRMATION')
        job['payload'].update(pending_collection_checks=[],neighbors=[])
        result=do_difference(self.fixture.ledger,self.gateway,job)
        self.assertEqual(result['status'],'REVIEW_REQUIRED')
        self.assertEqual(result['comparison_applicability'],'NOT_APPLICABLE_EMPTY_SET')

    def test_unknown_does_not_send_another_pair_or_create_pass(self):
        job=self.job()
        with patch.object(self.fixture.ledger,'heartbeat'),patch.object(self.gateway,'call',side_effect=OutcomeUnknown('original unknown')) as call:
            with self.assertRaises(OutcomeUnknown):do_difference(self.fixture.ledger,self.gateway,job)
        self.assertEqual(call.call_count,1)


class DeliveryStageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from test_pipeline_offline_e2e import PipelineAcceptance
        self.case=PipelineAcceptance('test_joint_producer_cli_to_same_page_save_and_writeback')
        self.case.setUp();self.addCleanup(self.case.doCleanups)

    async def test_saved_evidence_survives_customer_export_rejection_with_explicit_stage_receipt(self):
        c=self.case
        with c.boundaries(),patch('webcollect.client_package.build_client_package',side_effect=ValueError('CONTROLLED export mismatch')):
            await c.produce();result=await c.consume_cli()
        self.assertEqual(result['state'],'succeeded')
        _,claim,_=c.assert_complete(result);execution=claim['binding']['execution_result']
        stages=execution['delivery_stages']
        self.assertEqual(stages['saved_count'],1);self.assertEqual(stages['customer_export'],'BLOCKED')
        self.assertEqual(stages['independent_AI_QC'],'NOT_RUN');self.assertIsNone(execution['qc_inputs'])
        self.assertTrue(Path(result['result']['save_receipt']['path']).is_file())
        self.assertEqual(load_json(execution['delivery_stage_receipt']['path']),stages)

    async def test_export_and_handoff_failures_are_independent_of_formal_save_and_ai(self):
        c=self.case
        with c.boundaries(),patch('webcollect.task_generation._prepare_qc_handoff',side_effect=ValueError('CONTROLLED history mismatch')):
            await c.produce();result=await c.consume_cli()
        self.assertEqual(result['state'],'succeeded')
        _,claim,_=c.assert_complete(result);execution=claim['binding']['execution_result'];stages=execution['delivery_stages']
        self.assertEqual(stages['saved_count'],1)
        self.assertEqual(stages['customer_export'],'EXPORTED_FORMAT_VALID')
        self.assertEqual(stages['qc_handoff'],'BLOCKED');self.assertEqual(execution['qc_status'],'handoff_blocked')
        self.assertFalse(execution['QC_approval']);self.assertTrue(Path(execution['candidate']).is_dir())
