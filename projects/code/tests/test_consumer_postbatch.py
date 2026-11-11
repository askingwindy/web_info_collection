"""Post-batch disposable fixtures: no sites, provider or production evidence."""
import json
import asyncio
from copy import deepcopy
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch
from test_react_session import ReactHarness, Script, decide, act_step
import test_react_native as native_tests
from test_react_native import native, finish
from webcollect.react_session import build_url_task, ReactSession
from webcollect.react_protocol import REFERENCE_PROTOCOL
from webcollect.batch_core import load_json, file_sha, save_json
from webcollect.postprocess import session_record, completion_evidence, terminal_outcome


def short_finish():
    return decide(tool='finish', arguments=lambda p: {
        'observation_id':p['request_observation_ref'], 'evidence_refs':[p['request_observation_ref']],
        'stop_reason':'ready', 'summary':'已做阶段为空；当前原图仍为输入页；未完成输入与计算'})

class RequestReferenceTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.task=build_url_task(url=self.page.url, task_version='postbatch')
        self.ids={'sample_id':'S000001_sample_000001'}
    recorded=native_tests.NativeSessionTests.recorded

    async def test_normal_native_short_reference_is_bound_in_logs(self):
        session,evidence,script=self.recorded([short_finish()])
        session.attempt_id='attempt-A'
        result=await session.run()
        self.assertEqual(result['stop_reason'],'ready')
        prompt=script.prompts[0];alias=prompt['request_observation_ref']
        self.assertLess(len(alias),32)
        declaration=load_json(next((evidence/'raw').glob('*request-observation-reference.json')))
        basis=load_json(next((evidence/'raw').glob('*finish-basis.json')))
        self.assertEqual(declaration['attempt_id'],'attempt-A')
        self.assertEqual(basis['request_reference']['reference'],alias)
        self.assertEqual(basis['observation_id'],prompt['observation']['observation_id'])
        self.assertEqual(basis['evidence_refs'],[prompt['observation']['observation_id']])
        self.assertEqual(basis['submitted_references']['observation_id'],alias)
        self.assertEqual(self.surface.executed,[])
        self.assertIsNone(session.active_reference)

    async def test_prior_round_and_foreign_short_references_rejected_via_tools(self):
        old=[]
        def remember(p):
            old.append(p['request_observation_ref'])
            return {'focus_control_id':'control-0'}
        stale=decide(tool='finish', arguments=lambda p:{'observation_id':old[0],
            'evidence_refs':[old[0]],'summary':'不得接受旧轮引用','stop_reason':'ready'})
        session,_,script=self.recorded([decide(tool='observe',arguments=remember),stale,short_finish()])
        result=await session.run()
        self.assertEqual(result['stop_reason'],'ready')
        self.assertEqual(script.prompts[2]['last_tool_result']['status'],'rejected')
        # Another session's current alias cannot belong to this attempt.
        foreign=old[0]
        session,_,script=self.recorded([decide(tool='finish',arguments={
            'observation_id':foreign,'evidence_refs':[foreign],'summary':'异会话引用','stop_reason':'ready'}),short_finish()],name='foreign')
        session.attempt_id='attempt-B';await session.run()
        self.assertEqual(script.prompts[1]['last_tool_result']['status'],'rejected')

    async def test_wrong_attempt_mapping_is_rejected_via_native_finish(self):
        session=None
        def incorrect(p):
            session.active_reference['attempt_id']='other-attempt'
            return {'observation_id':p['request_observation_ref'], 'evidence_refs':[p['request_observation_ref']],
                    'summary':'错误attempt绑定','stop_reason':'ready'}
        session,_,script=self.recorded([decide(tool='finish',arguments=incorrect),short_finish()])
        session.attempt_id='original-attempt';await session.run()
        self.assertEqual(script.prompts[1]['last_tool_result']['status'],'rejected')

    async def test_old_observation_full_id_rejected_and_frozen_old_contract_works(self):
        old=[]
        def remember(p):
            old.append(p['observation']['observation_id']);return {'focus_control_id':'control-0'}
        session,_,script=self.recorded([decide(tool='observe',arguments=remember),decide(tool='finish',arguments=lambda p:{
            'observation_id':old[0],'evidence_refs':[old[0]],'summary':'旧观察','stop_reason':'ready'}),finish()])
        await session.run();self.assertEqual(script.prompts[2]['last_tool_result']['status'],'rejected')

    async def test_budget_focus_and_visible_result_keep_distinct_proven_effects(self):
        for visible in (False,True):
            self.surface.state['values'][0]['focused']=False
            self.task=build_url_task(url=self.page.url,task_version=str(visible),budgets={'max_decisions':2})
            original=self.surface.execute_action
            def action(kind,args):
                original(kind,args)
                if visible:
                    self.surface.state['visible_text']+='\n计算结果：总价为20元'
                    self.surface.state['elements'].append({'element_id':'result','parent_id':'control-0',
                        'text':'计算结果：总价为20元','native_role':'status','bbox':[10,400,200,430]})
            self.surface.execute_action=action
            session,evidence,script=self.recorded([
                decide(tool='observe',arguments={'focus_control_id':'control-0'}),
                decide(goal='输入并核对结果',tool='act',arguments=lambda p:{'observation_id':p['observation']['observation_id'],
                    'step':act_step('click',control_id='control-0')})],name='result'+str(visible))
            result=await session.run();self.surface.execute_action=original
            self.assertEqual(result['stop_reason'],'budget')
            self.assertEqual(result['effective_steps'],1)
            effect=session.last_tool_result['data']['effects'][0]
            self.assertEqual(effect['kind'],'VISIBLE_CONTENT_CHANGED' if visible else 'FOCUS_ONLY')
            self.assertEqual(effect['business_completion'],'NOT_CLAIMED')
            record=session_record(evidence/'raw');proof=completion_evidence(record)
            self.assertEqual(proof['business_completion'],'NOT_CLAIMED')
            self.assertEqual(proof['actual_effects'][0]['kind'],effect['kind'])
            final=load_json(record['observations'][record['terminal']['final_observation_id']]['state_path'])
            status,text=terminal_outcome(self.task,record,final)
            self.assertEqual(status,'success') # legitimate continuous fragment, no business claim
            self.assertEqual('计算结果：总价为20元' in text,visible)

    async def test_dispatched_unknown_tool_history_does_not_reuse_prior_observe_result(self):
        from webcollect.browser import EvidenceStale
        session,_,_=self.recorded([
            decide(tool='observe',arguments={'focus_control_id':'control-0'}),
            decide(goal='核对控件',tool='act',arguments=lambda p:{'observation_id':p['observation']['observation_id'],
                'step':act_step('click',control_id='control-0')})])
        original=self.surface.capture
        async def capture(*args,**kwargs):
            if self.surface.executed:raise EvidenceStale('synthetic after dispatch')
            return await original(*args,**kwargs)
        with patch('webcollect.browser.capture',side_effect=capture):
            result=await session.run()
        self.assertTrue(result['unknown']);self.assertEqual(result['actual_actions'],1)
        history=json.loads(session.history[-1]['content'])
        self.assertEqual(history['status'],'stopped')
        self.assertEqual(history['data']['actual_actions_delta'],1)
        self.assertEqual(history['data']['effect_status'],'UNKNOWN')


class LegacyEffectMetadataTests(unittest.TestCase):
    def test_missing_legacy_effect_proof_never_invents_input_change(self):
        from webcollect.react_protocol import effect_feedback
        value=effect_feedback({'operation_id':'old','before_observation_id':'a','after_observation_id':'b','effective':True})
        self.assertEqual(value['kind'],'NOT_ESTABLISHED')
        self.assertEqual(value['effect_status'],'UNKNOWN')


class CollectionReportContextTests(unittest.TestCase):
    def setUp(self):
        from test_delivery import DeliveryContractTests
        self.fixture=DeliveryContractTests('test_delivery_needs_no_reference_samples_or_capture_archives')
        self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        f=self.fixture;self.root=f.root.resolve();self.registry=self.root/'state/registry.db'
        from webcollect.current_chain import initialize_chain
        self.pool=self.root/'state/pool.db';self.pool.parent.mkdir(exist_ok=True)
        with sqlite3.connect(self.pool) as c:c.execute('CREATE TABLE application_delivery_projection(application_id TEXT,count INTEGER,reference TEXT)')
        self.scope=initialize_chain(self.root/'chain/manifest.json',self.registry,chain_id='fixture-project',current_result_roots=[self.root/'current'],
            candidate_project={'rules':'candidate-project-2','pool':str(self.pool),'site_ledger':str(self.root/'state/sites.db')})
        self.package=self.root/'current/package';shutil.copytree(f.client,self.package)
        from quality_inspector.cumulative import inspect_set,build_set_manifest
        self.report=inspect_set(build_set_manifest([self.package]),f.profile,verify_exhaustive=True)
        self.assertEqual(self.report['mechanical_status'],'PASS',self.report['errors'])
        member=self.report['version_comparison']['effective_samples'][0];sid=member['sample_id'];annotation=Path(member['sample_path'])/'annotation.json'
        with sqlite3.connect(self.registry) as c:
            c.execute('''INSERT INTO m4_attempts(attempt_id,scope_id,campaign_id,task_key,plan_sha256,request_id,
                worker_id,lease_token,lease_expires_at,sample_id,site_id,batch_id,status,created_at,evidence_json)
                VALUES('fixture','s','c','task','p','r','w','l',0,?,'site','batch','collected_pending_review',0,'[]')''',(sid,))
            c.execute('INSERT INTO current_chain_results VALUES(?,?,?,?,?,0)',(sid,str(annotation),file_sha(annotation),'https://fixture.example/','task'))
        self.path=self.root/'report.json';self.revision=0
    def write(self):
        self.revision+=1;self.path=self.root/f'report-{self.revision}.json'
        save_json(self.path,self.report);return {'path':str(self.path),'sha256':file_sha(self.path)}
    def context(self,ref):
        from webcollect.agent_feedback import site_context
        return site_context(self.registry,'https://fixture.example/',collection_report=ref)['collection_facts']
    def test_actual_cumulative_report_via_official_context_known_and_prompt(self):
        ref=self.write()
        with sqlite3.connect(self.pool) as c:c.execute('INSERT INTO application_delivery_projection VALUES(?,?,?)',('fixture-app',1,json.dumps(ref)))
        from webcollect.agent_feedback import site_context
        actual_context=site_context(self.registry,'https://fixture.example/')
        facts=actual_context['collection_facts']
        fixture=RequestReferenceTests('test_normal_native_short_reference_is_bound_in_logs')
        fixture._callCleanup=unittest.TestCase._callCleanup.__get__(fixture);fixture.setUp()
        try:
            session,_,script=fixture.recorded([short_finish()]);session.context=actual_context
            asyncio.run(session.run())
            self.assertEqual(script.prompts[0]['collection_facts'],facts)
        finally:fixture.doCleanups()
        self.assertEqual(facts['short_flow']['status'],'KNOWN')
        self.assertEqual(facts['short_flow']['denominator'],1)
        self.assertEqual(facts['near_duplicate_unique_samples']['numerator'],0)
        self.assertEqual(facts['near_duplicate_unique_samples']['denominator'],1)
        self.assertEqual(facts['short_flow']['scope']['chain_id'],'fixture-project')
    def test_missing_changed_members_and_cross_project_unknown(self):
        ref=self.write();self.path.write_text(self.path.read_text()+'\n')
        self.assertEqual(self.context(ref)['short_flow']['status'],'UNKNOWN')
        self.write();annotation=next(self.package.glob('samples/*/annotation.json'));annotation.write_text('{}')
        self.assertEqual(self.context(self.write())['short_flow']['status'],'UNKNOWN')
    def test_missing_short_flow_count_only_invalidates_its_metric(self):
        self.report['statistics'].pop('short_flow_count')
        facts=self.context(self.write())
        self.assertEqual(facts['short_flow']['status'],'UNKNOWN')
        self.assertEqual(facts['near_duplicate_unique_samples']['status'],'KNOWN')

    def test_duplicate_incomplete_only_invalidates_its_metric(self):
        self.report['duplicates']['summary']['analysis_status']='PENDING'
        facts=self.context(self.write())
        self.assertEqual(facts['short_flow']['status'],'KNOWN')
        self.assertEqual(facts['near_duplicate_unique_samples']['status'],'UNKNOWN')
    def test_zero_denominator_and_cross_project_context(self):
        other=self.root/'other.db'
        from webcollect.current_chain import initialize_chain
        initialize_chain(self.root/'other/manifest.json',other,chain_id='other',current_result_roots=[self.root/'other/results'])
        from webcollect.agent_feedback import site_context
        facts=site_context(other,'https://fixture.example/',collection_report=self.write())['collection_facts']
        self.assertEqual(facts['short_flow']['status'],'UNKNOWN')
        shutil.rmtree(self.package/'samples')
        from quality_inspector.cumulative import inspect_set,build_set_manifest
        self.report=inspect_set(build_set_manifest([self.package]),self.fixture.profile)
        facts=self.context(self.write());self.assertEqual(facts['short_flow']['status'],'UNKNOWN')
        self.assertIn('分母为零',facts['short_flow']['reason'])
