"""V2 boundary/exception tests use disposable evidence and fake browser IO."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_react_native as native_fixture
from test_react_session import ReactHarness, act_step, decide
from test_react_native import scroll,finish
from webcollect.react_session import build_url_task
from webcollect.closing_policy import V2_VERSION as VERSION,annotation_errors
from webcollect.postprocess import session_record,effective_trajectory,process
from webcollect.batch_core import load_json,file_sha,BatchLedger


class EndingV2Tests(ReactHarness,unittest.IsolatedAsyncioTestCase):
    recorded=native_fixture.NativeSessionTests.recorded

    def setUp(self):
        super().setUp()
        self.task=build_url_task(url=self.page.url,task_version='V2-fixture',ending_policy=VERSION)
        self.ids={'sample_id':'S000001_sample_000001','site_id':'S000001',
                  'batch_id':'B20261103_001','attempt_id':'controlled-v2'}
        self.manifest={'batch_id':'B20261103_001','sample_kind':'real','program_version':'CONTROLLED',
                       'rule_version':'1.0.0','sites':[{'site_id':'S000001','uri':self.page.url,'site_category':self.task['site_category']}],
                       'samples':[self.ids['sample_id']]}

    def builds(self,n):return [scroll('核对连续正文')]+[scroll() for _ in range(n-1)]

    def fail_local(self,n):
        original=self.surface.execute_action
        def execute(kind,args):
            if len(self.surface.executed)==n-1:
                self.surface.executed.append((kind,deepcopy(args))) # real dispatch, known local no movement
            else:original(kind,args)
        self.surface.execute_action=execute

    def derive(self,evidence,name='candidate'):
        destination=self.root/name/'samples'/self.ids['sample_id']
        result=process(evidence,destination,self.ids,self.manifest)
        if result['status']!='derived_saved' and result.get('record_ref'):
            self.fail(str(load_json(result['record_ref']['path'])))
        self.assertEqual(result['status'],'derived_saved',result)
        from webcollect.client_package import validate_client_sample
        from quality_inspector.format_checks import sample_check
        annotation=validate_client_sample(destination)
        check=sample_check(destination)
        self.assertTrue(check['confirmed_format_pass'],check['errors'])
        self.assertEqual(annotation_errors(annotation),[])
        return destination,annotation

    async def test_eighth_attempt_closes_without_a_ninth_or_fake_goal_success(self):
        session,evidence,script=self.recorded(self.builds(9))
        result=await session.run();mark=result['collection_ending']
        self.assertEqual((mark['business_attempts'],mark['actual_atomic_dispatches'],mark['verified_effective_steps']),(8,8,8))
        self.assertEqual(len(script.prompts),8);self.assertEqual(len(script.builds),1)
        self.assertEqual(mark['kind'],'EIGHT_ATTEMPT_LIMIT');self.assertEqual(mark['finish_count'],1)
        _,a=self.derive(evidence)
        self.assertEqual(a['completion_status'],'controlled_exception');self.assertNotIn('short_flow',a)
        self.assertEqual(a['steps'][-1]['tool_result']['return_value']['collection_ending']['goal_completion'],'NOT_CLAIMED')

    async def test_fifth_known_local_failure_saves_short_prefix_with_original_tail(self):
        self.fail_local(5)
        session,evidence,script=self.recorded(self.builds(6))
        result=await session.run();mark=result['collection_ending']
        self.assertEqual((mark['business_attempts'],mark['actual_atomic_dispatches'],mark['verified_effective_steps'],mark['unverified_tail_dispatches']),(5,5,4,1))
        self.assertEqual(mark['kind'],'KNOWN_NO_EFFECT');self.assertFalse(mark['external_effect_unknown'])
        raw_tail=Path(mark['last_attempt']['raw_steps'][-1]['path']);tail_hash=file_sha(raw_tail)
        _,a=self.derive(evidence)
        self.assertTrue(a['short_flow']);self.assertIn('4 个有效业务操作',a['short_flow_reason'])
        self.assertEqual(a['completion_status'],'controlled_exception');self.assertEqual(len(a['steps']),5)
        self.assertEqual(file_sha(raw_tail),tail_hash)
        self.assertFalse(load_json(raw_tail).get('postconditions_checked',False))
        self.assertEqual(load_json(evidence/'step_005.json')['operation']['action_type'],'complete')
        self.assertEqual(len(script.prompts),5)

    async def test_eighth_known_failure_has_seven_effective_steps(self):
        self.fail_local(8)
        session,evidence,_=self.recorded(self.builds(8))
        result=await session.run();self.assertEqual(result['collection_ending']['verified_effective_steps'],7)
        _,a=self.derive(evidence);self.assertNotIn('short_flow',a)
        self.assertEqual(a['completion_status'],'controlled_exception')

    async def test_fifth_and_eighth_zero_dispatch_attempts_are_not_actual_actions(self):
        initial=deepcopy(self.surface.state)
        for n in (5,8):
            self.surface.state=deepcopy(initial);self.surface.executed=[]
            missing=decide(tool='act',arguments=lambda p:{'observation_id':p['observation']['observation_id'],
                'step':act_step('click',control_id='control-0')})
            session,evidence,script=self.recorded(self.builds(n-1)+[missing,finish()],name='zero-'+str(n))
            result=await session.run();mark=result['collection_ending']
            self.assertEqual((mark['business_attempts'],mark['actual_atomic_dispatches'],mark['verified_effective_steps']),(n,n-1,n-1))
            self.assertEqual(mark['kind'],'NOT_DISPATCHED');self.assertEqual(mark['zero_dispatch_attempts'],1)
            self.assertEqual(len(script.prompts),n)
            _,a=self.derive(evidence,name='zero-candidate-'+str(n));self.assertEqual(a.get('short_flow',False),n==5)

    async def test_predispatch_error_is_zero_dispatch_even_with_an_intent(self):
        original=self._fake_verify
        async def verify(*args,**kwargs):
            if len(self.surface.executed)==4:raise ValueError('CONTROLLED before dispatch failure')
            return await original(*args,**kwargs)
        with patch('webcollect.browser.verify_execution_state',side_effect=verify):
            session,evidence,_=self.recorded(self.builds(5));result=await session.run()
        mark=result['collection_ending'];self.assertEqual(mark['actual_atomic_dispatches'],4)
        self.assertFalse(mark['external_effect_unknown'])
        self.derive(evidence)

    async def test_fifth_and_eighth_dispatched_unknown_are_raw_only_and_never_replayed(self):
        original=self.surface.execute_action;initial=deepcopy(self.surface.state)
        for n in (5,8):
            self.surface.state=deepcopy(initial);self.surface.executed=[]
            def execute(kind,args):
                if len(self.surface.executed)==n-1:
                    self.surface.executed.append((kind,args));raise TimeoutError('CONTROLLED external effect unknown')
                original(kind,args)
            self.surface.execute_action=execute
            session,evidence,script=self.recorded(self.builds(n+1),name='unknown-'+str(n));result=await session.run()
            self.assertTrue(result['unknown']);self.assertTrue(result['collection_ending']['raw_only_pending'])
            self.assertEqual(len(script.prompts),n);self.assertEqual(len(self.surface.executed),n)
            self.assertEqual(load_json(evidence/'raw/terminal.json')['state'],'closed_pending_reconciliation')
            self.assertTrue((evidence/'raw/raw-receipt.json').is_file())
            with self.assertRaisesRegex(ValueError,'UNKNOWN'):session_record(evidence/'raw')
            self.assertFalse((evidence/'saved_sample.json').exists())

    async def test_missing_post_action_capture_retains_unknown_and_raw(self):
        original=self.surface.capture
        async def capture(*args,**kwargs):
            if len(self.surface.executed)>=5:raise ValueError('CONTROLLED no trusted terminal capture')
            return await original(*args,**kwargs)
        with patch('webcollect.browser.capture',side_effect=capture):
            session,evidence,script=self.recorded(self.builds(6));result=await session.run()
        self.assertTrue(result['collection_ending']['raw_only_pending'])
        self.assertTrue(result['unknown']);self.assertEqual(len(script.prompts),5)
        self.assertFalse((evidence/'saved_sample.json').exists())

    async def test_natural_success_and_short_flow_keep_agent_finish_separate(self):
        for n in (3,5):
            session,evidence,script=self.recorded(self.builds(n)+[finish()],name='success-'+str(n))
            result=await session.run();mark=result['collection_ending']
            self.assertEqual(mark['business_attempts'],n);self.assertEqual(mark['finish_origin'],'agent')
            self.assertFalse(mark['flagged']);self.assertEqual(mark['finish_count'],1)
            _,a=self.derive(evidence,name='success-candidate-'+str(n))
            self.assertEqual(a['completion_status'],'success');self.assertEqual(a.get('short_flow',False),n<5)

    async def test_stale_proposal_and_observe_do_not_count_as_business_attempts(self):
        stale=decide(goal='核对当前正文',tool='act',arguments={'observation_id':'obsolete',
            'step':act_step('scroll',direction='down',goal='查看正文',expected='视口下移')})
        session,evidence,_=self.recorded([stale,scroll(),finish()])
        result=await session.run();mark=result['collection_ending']
        self.assertEqual(mark['business_attempts'],1);self.assertEqual(mark['actual_atomic_dispatches'],1)
        self.derive(evidence)

    async def test_old_protocol_uses_original_behavior_beyond_eight(self):
        self.task=build_url_task(url=self.page.url,task_version='V1-frozen')
        session,evidence,_=self.recorded(self.builds(9)+[finish()]);result=await session.run()
        self.assertNotIn('collection_ending',result);self.assertEqual(result['effective_steps'],9)

    async def test_tampered_tail_counts_cannot_enter_formal_derivation(self):
        self.fail_local(5);session,evidence,_=self.recorded(self.builds(5));await session.run()
        record=session_record(evidence/'raw');record['terminal']['collection_ending']['actual_atomic_dispatches']=4
        with self.assertRaisesRegex(ValueError,'accounting'):effective_trajectory(record)

    async def test_qc_sees_flag_and_only_terminal_semantics_rule_changes(self):
        self.fail_local(5);session,evidence,_=self.recorded(self.builds(5));await session.run()
        destination,a=self.derive(evidence)
        from quality_inspector.ai_worker import compact_trajectory,snapshot,prepare
        from quality_inspector.semantic import RULE_VERSIONS
        material,images=compact_trajectory(snapshot(destination))
        self.assertTrue(material['collection_ending']['flagged'])
        self.assertEqual(material['whole_trajectory_length']['effective_steps'],4)
        self.assertEqual(len(images),5)
        config=load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'qc-offline.sqlite3',config,initialize=True)
        queued=prepare(ledger,destination.parent.parent,self.root/'qc-prepared')
        self.assertEqual(queued['queued_samples'],1);self.assertEqual(queued['model_requests'],0)
        self.assertIn('five-eight',RULE_VERSIONS['terminal_semantics'])
        self.assertEqual(RULE_VERSIONS['language'],'page-control-language-consistency-and-chinese-narratives-2')

    async def test_compound_business_attempt_and_atomic_dispatches_are_distinct(self):
        probe=decide(tool='observe',arguments={'focus_control_id':'control-0'})
        act=decide(goal='修改当前数量',tool='act',arguments=lambda p:{'observation_id':p['observation']['observation_id'],
            'step':act_step('set_value',control_id='control-0',value='20')})
        session,evidence,_=self.recorded([probe,act,finish()]);result=await session.run()
        mark=result['collection_ending'];self.assertEqual(mark['business_attempts'],mark['actual_atomic_dispatches'])
        self.assertGreater(mark['actual_atomic_dispatches'],1)
        self.assertEqual(mark['actual_atomic_dispatches'],mark['verified_effective_steps'])
        self.derive(evidence)

    async def test_eighth_primitive_stops_inside_compound_before_ninth_type(self):
        probe=decide(tool='observe',arguments={'focus_control_id':'control-0'})
        change=decide(goal='修改当前数量',tool='act',arguments=lambda p:{'observation_id':p['observation']['observation_id'],
            'step':act_step('set_value',control_id='control-0',value='20')})
        session,evidence,script=self.recorded(self.builds(6)+[probe,change,finish()])
        result=await session.run();mark=result['collection_ending']
        self.assertEqual((mark['business_attempts'],mark['actual_atomic_dispatches'],mark['verified_effective_steps']),(8,8,8))
        self.assertFalse(any(kind=='type' for kind,_ in self.surface.executed))
        self.assertEqual(self.surface.state['values'][0]['value'],'10')
        self.assertEqual(len(script.builds),1)
        self.derive(evidence)


class NormalEntryV2Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from test_pipeline_offline_e2e import PipelineAcceptance
        self.case=PipelineAcceptance('test_joint_producer_cli_to_same_page_save_and_writeback')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.case.decisions=[scroll('核对连续正文')]+[scroll() for _ in range(4)]
        # This harness verifies the already frozen V2 four-tool entry. New
        # conditional-plan entry coverage lives in test_banded_plan separately.
        from webcollect.react_session import build_url_task
        def frozen_v2(**kwargs):
            kwargs.pop('plan_protocol',None)
            return build_url_task(**kwargs)
        protocol=patch('webcollect.react_session.build_url_task',side_effect=frozen_v2)
        protocol.start();self.addCleanup(protocol.stop)


    async def test_formal_save_export_and_handoff_keep_flagged_short_prefix(self):
        c=self.case; original=c.surface.execute_action
        def execute(kind,args):
            if len(c.surface.executed)==4:c.surface.executed.append((kind,args))
            else:original(kind,args)
        c.surface.execute_action=execute
        policy=c.root/'v2-qc-policy.json'
        policy.write_text(json.dumps({'ai_percent':100,'human_percent':0,'seed':'CONTROLLED-V2'}))
        with c.boundaries():
            await c.produce()
            result=(await __import__('asyncio').to_thread(c.invoke,__import__('webcollect.candidate_consumer',fromlist=['main']).main,
                c.cli_args('v2-flag','v2-worker')+['--qc-policy',str(policy)]))[0]
        self.assertEqual(result['state'],'succeeded',result)
        row,claim,task=c.assert_complete(result)
        self.assertEqual(task['fragment']['ending_policy'],VERSION)
        execution=claim['binding']['execution_result']
        self.assertEqual(execution['delivery_stages']['customer_export'],'EXPORTED_FORMAT_VALID')
        self.assertEqual(execution['delivery_stages']['qc_handoff'],'PREPARED')
        sample=Path(execution['candidate'])/'samples'/result['result']['sample_id']
        a=load_json(sample/'annotation.json')
        self.assertEqual(a['completion_status'],'controlled_exception');self.assertTrue(a['short_flow'])
        self.assertEqual(a['steps'][-1]['tool_result']['return_value']['collection_ending']['actual_atomic_dispatches'],5)
        self.assertEqual(row['result']['qc_state'],'pending_review')
        self.assertFalse(execution['QC_approval'])

    async def test_unknown_final_operation_preserves_original_attempt_pending_without_export(self):
        c=self.case;original=c.surface.execute_action
        def execute(kind,args):
            if len(c.surface.executed)==4:
                c.surface.executed.append((kind,args));raise TimeoutError('CONTROLLED unknown external effect')
            original(kind,args)
        c.surface.execute_action=execute
        with c.boundaries():
            await c.produce();result=await c.consume_cli('v2-unknown')
        self.assertIn(result['state'],('reconcile','failed'),result)
        pending=list(c.output.rglob('raw-ending-pending.json'))
        self.assertEqual(len(pending),1)
        receipt=load_json(pending[0]);self.assertTrue(receipt['requires_reconciliation'])
        self.assertFalse(receipt['normal_sample_saved']);self.assertEqual(receipt['QC_status'],'NOT_RUN')
        self.assertTrue(receipt['collection_ending']['external_effect_unknown'])
        self.assertEqual(len(c.surface.executed),5)
        self.assertFalse(list(c.output.rglob('saved_sample.json')))
