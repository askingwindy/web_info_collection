"""Disposable synthetic browser / mocked transport only. No real model/site/QC."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image
from webcollect.banded_plan import (VERSION, tools, validate_plan, bind_target, rendered_dom,
                                    proves, distribution)
from webcollect.closing_policy import VERSION as END
from webcollect.react_session import ReactSession, build_url_task, validate_task, react_chooser
from webcollect.batch_core import load_json, file_sha, OutcomeUnknown, SessionGLMCallLimit
from webcollect.inference_image import derive
from test_react_session import ReactHarness
import test_closing_policy_v2 as closing_fixture
import test_model_provider_protocols as provider_fixture


def plan_for(prompt,n=5):
    return {'attempt_id':prompt['attempt_id'],'observation_id':prompt['observation']['observation_id'],
            'band':'five' if n==5 else 'long' if n>=6 else 'short','short_reason':'当前页面自然短流程' if n<5 else '',
            'goal':'逐段核对当前页面相关信息','checks':[],'steps':[{'action':'scroll','direction':'down',
                'purpose':f'核对第{i+1}段独立信息','expected':{'kind':'scroll_changed','text':'滚动后位置改变'}} for i in range(n)],
            'finish_when':{'kind':'visible_text','text':'当前终点内容'},'replan_when':'新文档或目标缺失'}


class BandedSessionTests(ReactHarness,unittest.IsolatedAsyncioTestCase):
    derive=closing_fixture.EndingV2Tests.derive
    fail_local=closing_fixture.EndingV2Tests.fail_local
    def setUp(self):
        ReactHarness.setUp(self)
        self.task=build_url_task(url=self.page.url,task_version='plan',ending_policy=END,plan_protocol=VERSION)
        self.ids={'sample_id':'S000001_sample_000001','site_id':'S000001','batch_id':'B20261103_001','attempt_id':'offline-plan'}
        self.manifest={'batch_id':'B20261103_001','sample_kind':'real','program_version':'CONTROLLED',
            'rule_version':'1.0.0','sites':[{'site_id':'S000001','uri':self.page.url,'site_category':self.task['site_category']}],
            'samples':[self.ids['sample_id']]}

    def recorded(self,n=5,name='banded',bad=None,mark_endpoint=True):
        self.prompts=[]
        original=self.surface.execute_action
        def execute(kind,args):
            original(kind,args)
            if mark_endpoint and len(self.surface.executed)==n:self.surface.state['visible_text']+='\n当前终点内容'
        self.surface.execute_action=execute
        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if len(self.prompts)>1:raise AssertionError('Stable planned path must not call model again')
            plan=plan_for(prompt,n)
            if bad:bad(plan)
            return {'name':'submit_plan','arguments':plan,'tool_call_id':'provider-first',
                    'assistant_message':{'role':'assistant','tool_calls':[]},'request_id':'mock-provider'}
        evidence=self.root/name/'evidence'/self.ids['sample_id']
        return ReactSession(self.task,evidence/'raw',choose,self.page,steps_directory=evidence,attempt_id='offline-plan'),evidence

    async def test_first_plan_then_five_host_actions_finish_and_export_qc_input(self):
        s,e=self.recorded();r=await s.run()
        self.assertEqual(r['effective_steps'],5,r)
        self.assertEqual(len(self.prompts),1);self.assertEqual(s.history,[])
        self.assertEqual([t['function']['name'] for t in self.prompts[0]['tools']],['submit_plan'])
        self.assertTrue(self.prompts[0]['observation']['rendered_dom'])
        self.assertEqual(r['collection_ending']['finish_origin'],'host')
        self.assertEqual(r['collection_ending']['goal_completion'],'NOT_CLAIMED')
        destination,a=self.derive(e);self.assertEqual(len(a['steps']),6)
        self.assertTrue(list((e/'raw/inference').glob('*.jpg')))
        from quality_inspector.ai_worker import snapshot,verify_snapshot
        captured=snapshot(destination)
        self.assertIsNotNone(captured)
        verify_snapshot(captured)

    async def test_short_six_seven_eight_do_not_pad_or_make_closing_http(self):
        initial=deepcopy(self.surface.state);execute=self.surface.execute_action
        for n in (1,4,6,7,8):
            self.surface.state=deepcopy(initial);self.surface.executed=[];self.surface.execute_action=execute
            s,e=self.recorded(n,name='n'+str(n));r=await s.run()
            self.assertEqual(r['effective_steps'],n,r);self.assertEqual(len(self.prompts),1)
            self.assertEqual(r['short_flow'],n<5)
            self.derive(e,name='derived-'+str(n))

    async def test_stale_wrong_attempt_unknown_operation_rejected_without_dispatch(self):
        for key,value in [('observation_id','old'),('attempt_id','other')]:
            s,_=self.recorded(name=key,bad=lambda p:p.update({key:value}));r=await s.run()
            self.assertEqual(r['actual_actions'],0);self.assertTrue(r['host_failure'])
        s,_=self.recorded(name='op',bad=lambda p:p['steps'][0].update(action='eval'))
        self.assertEqual((await s.run())['actual_actions'],0)

    async def test_same_name_and_reload_rebind_and_does_not_reuse_old_handle(self):
        s,_=self.recorded();await s._observe()
        target={'text':'数量'}
        e=s.current['controls']['control-0']['element'];e['text']='部门'
        self.assertEqual(bind_target(s.current,{'text':'部门'}),['control-0'])
        s.current['controls']['control-1']['element']['text']='部门'
        self.assertEqual(len(bind_target(s.current,{'text':'部门'})),2)
        row=s.current['controls'].pop('control-0');row['element']['element_id']='e_35'
        s.current['controls']['e_35']=row
        self.assertIn('e_35',bind_target(s.current,{'text':'部门'}))
        self.assertNotIn('control-0',bind_target(s.current,{'text':'部门'}))

    async def test_plain_branch_refuses_stale_and_unknown_option(self):
        s,_=self.recorded();await s._observe();controller=s.plan_controller
        controller.plan=plan_for(controller.prompt(s));controller.submitted=True
        for field,value in [('observation_id','stale'),('attempt_id','foreign'),('choice','eval')]:
            async def choose(p):
                return {**{'attempt_id':s.attempt_id,'observation_id':s.current['observation_id'],'choice':'stop'},field:value}
            s.choose=choose
            with self.assertRaises(ValueError):await controller.request(s,[{'choice':'stop','meaning':'结束'}])
        self.assertEqual(s.actual_dispatches,0)

    async def test_unknown_is_not_sent_or_acted_again(self):
        s,_=self.recorded()
        def guard():raise OutcomeUnknown('original')
        s.choose.guard_unresolved=guard
        r=await s.run();self.assertEqual(r['actual_actions'],0);self.assertEqual(self.prompts,[])


class BandedWireTests(unittest.TestCase):
    def setUp(self):
        self.f=provider_fixture.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
    def test_actual_native_and_plain_payloads_jpeg_and_qc_png_boundary(self):
        f=self.f;ledger,job,g=f.gateway(f.config('glm',vision=True))
        asset=derive(f.image,f.root/'inference')
        f.opener.raw['choices']=[{'finish_reason':'tool_calls','message':{'tool_calls':[
            {'id':'provider-plan','type':'function','function':{'name':'submit_plan','arguments':json.dumps(plan_for(
                {'attempt_id':'a','observation':{'observation_id':'o'}}))}}]}}]
        response=g.call_tool(job,'plan','page',tools(),system='s',images=[asset['path']],inference=True,
                             attempt_id='a',max_requests=25)
        first=json.loads(f.opener.calls[-1].data)
        self.assertEqual(len(first['tools']),1);self.assertEqual(response['tool_call_id'],'provider-plan')
        self.assertTrue(first['messages'][-1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,'))
        f.opener.raw['choices']=[{'finish_reason':'stop','message':{'content':'{"attempt_id":"a","observation_id":"o","choice":"stop"}'}}]
        from webcollect.banded_plan import CHOICE
        g.call_message(job,'branch','current',CHOICE,system='s',images=[asset['path']],attempt_id='a',max_requests=25)
        later=json.loads(f.opener.calls[-1].data)
        self.assertNotIn('tools',later);self.assertNotIn('tool_choice',later)
        self.assertEqual([m['role'] for m in later['messages']],['system','user'])
        with self.assertRaisesRegex(ValueError,'must be PNG'):
            g.call(job,'qc','x',{'type':'object'},images=[asset['path']])
        self.assertEqual(len(f.opener.calls),2)
    def test_plain_invalid_has_no_format_retry_or_tool_forgery(self):
        f=self.f;ledger,job,g=f.gateway(f.config('glm'))
        f.opener.raw['choices']=[{'finish_reason':'stop','message':{'content':'```json\n{}\n```'}}]
        with self.assertRaises(ValueError):g.call_message(job,'bad','x',{'type':'object'},system='s',attempt_id='a',max_requests=25)
        self.assertEqual(len(f.opener.calls),1)
        with ledger.connect() as con:self.assertEqual(con.execute('SELECT state FROM model_requests').fetchone()[0],'invalid_response')
    def test_unknown_and_25_limit_share_original_ledger(self):
        f=self.f;ledger,job,g=f.gateway(f.config('glm'))
        import urllib.error
        f.opener.error=urllib.error.URLError(OSError('offline'))
        with self.assertRaises(OutcomeUnknown):g.call_message(job,'unknown','x',{'type':'object'},system='s',attempt_id='a',max_requests=25)
        with self.assertRaises(OutcomeUnknown):g.call_message(job,'different','x',{'type':'object'},system='s',attempt_id='a',max_requests=25)
        self.assertEqual(len(f.opener.calls),1)


class BandedPureTests(unittest.TestCase):
    def test_old_frozen_identity_and_extension_binding(self):
        old=build_url_task(url='https://example.org',task_version='old',ending_policy=END)
        self.assertNotIn('plan_protocol',old['fragment']);validate_task(old)
        new=build_url_task(url='https://example.org',task_version='new',ending_policy=END,plan_protocol=VERSION)
        self.assertNotEqual(old['task_id'],new['task_id'])
        new['fragment']['plan_protocol']='bad'
        with self.assertRaises(ValueError):validate_task(new)
    def test_unknown_accepted_denominator_and_distinct_stage_counts(self):
        d=distribution(planned=[{'effective_steps':5}],pending=[{'effective_steps':2}])
        self.assertEqual(d['accepted']['status'],'UNKNOWN');self.assertIsNone(d['accepted']['denominator'])
        self.assertEqual(d['planned']['counts']['five'],1);self.assertEqual(d['pending_review']['counts']['short'],1)


class BandedFormalEntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_formal_candidate_entry_actual_gateway_save_export_and_independent_qc_input(self):
        import io
        import test_pipeline_offline_e2e as joint
        fixture=joint.PipelineAcceptance('test_joint_producer_cli_to_same_page_save_and_writeback')
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        old_transport=fixture.transport
        execute=fixture.surface.execute_action
        def action(kind,args):
            execute(kind,args)
            if len(fixture.surface.executed)==1:
                fixture.surface.state['document_identity']['performance_time_origin']+=1
            if len(fixture.surface.executed)==5:
                fixture.surface.state['visible_text']+='\n当前终点内容'
        fixture.surface.execute_action=action
        captures=[]
        def transport(request,timeout):
            payload=json.loads(request.data)
            names={x['function']['name'] for x in payload.get('tools',[])}
            if names and names!={'submit_plan'}:return old_transport(request,timeout)
            captures.append(payload)
            prompt=json.loads(payload['messages'][-1]['content'][0]['text'])
            if names:
                self.assertEqual(prompt['bands']['assigned_band'],'five')
                self.assertEqual(prompt['bands']['accepted']['status'],'UNKNOWN')
                message={'tool_calls':[{'id':'provider-plan','type':'function',
                    'function':{'name':'submit_plan','arguments':json.dumps(plan_for(prompt))}}]}
            else:
                self.assertNotIn('tools',payload);self.assertNotIn('tool_choice',payload)
                self.assertNotIn('bands',prompt);self.assertNotIn('image_asset',prompt)
                self.assertTrue(prompt['observation']['rendered_dom'])
                self.assertEqual(prompt['plan_schema'],tools()[0]['function']['parameters'])
                self.assertEqual([m['role'] for m in payload['messages']],['system','user'])
                message={'content':json.dumps({'attempt_id':prompt['attempt_id'],
                    'observation_id':prompt['observation']['observation_id'],'choice':'continue'})}
            return io.BytesIO(json.dumps({'model':'offline-provider','usage':{'prompt_tokens':200,'completion_tokens':50,'prompt_tokens_details':{'cached_tokens':0}},
                'choices':[{'finish_reason':'tool_calls' if names else 'stop','message':message}]}).encode())
        fixture.transport=transport
        with fixture.boundaries(legacy_protocol=False):
            await fixture.produce()
            result=await fixture.consume_cli()
        self.assertEqual(result['state'],'succeeded',(result,[load_json(p) for p in fixture.output.rglob('failure.json')], [load_json(p) for p in fixture.output.rglob('terminal.json')]))
        self.assertEqual(result['QC'],'pending_review')
        self.assertEqual(len(captures),2)
        saved=Path(result['result']['save_receipt']['path']).parent
        marker=load_json(saved/'raw/terminal.json')['collection_ending']
        range_event=load_json(next((saved/'raw').glob('*range-finish.json')))['collection_ending']
        self.assertEqual(marker,range_event)
        self.assertEqual(marker['kind'],'HOST_PLAN_ENDPOINT')
        from quality_inspector.ai_worker import snapshot,verify_snapshot
        annotation=next(fixture.output.rglob('candidate/samples/*/annotation.json'))
        verify_snapshot(snapshot(annotation.parent))
        from webcollect.batch_core import BatchLedger
        from quality_inspector.ai_worker import prepare
        config=load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')
        qcledger=BatchLedger(fixture.root/'independent-qc.sqlite3',config,initialize=True)
        queued=prepare(qcledger,annotation.parents[2],fixture.root/'qc-out',sample_ids=[annotation.parent.name])
        self.assertEqual(queued['queued_samples'],1)
        self.assertEqual(queued['model_requests'],0)


class BandedBudgetTests(unittest.TestCase):
    def setUp(self):
        from test_request_quarantine import RequestQuarantineTests
        self.fixture=RequestQuarantineTests('test_unknown_document_get_keeps_original_and_another_page_can_be_read_after_restart')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
    def task_attempt(self,n):
        return {'task_id':'task-'+str(n)},{'attempt_id':'attempt-'+str(n),'scope_id':'batch-'+str(n//3),
                                         'campaign_id':'campaign-'+str(n//3),'task_key':'key-'+str(n)}
    def test_cross_batch_small_runs_and_restart_do_not_round_half_short_or_reset_planning(self):
        from webcollect.band_budget import reserve
        registry=self.fixture.scope['registry'];bands=[]
        for n in range(99):
            task,attempt=self.task_attempt(n);budget=reserve(registry,task,attempt)
            self.assertEqual(reserve(registry,task,attempt),budget)
            bands.append(budget['assigned_band'])
            self.assertEqual(budget['accepted']['status'],'UNKNOWN')
            self.assertIsNone(budget['accepted']['denominator'])
        self.assertEqual(bands.count('five'),80);self.assertEqual(bands.count('long'),19)
        self.assertNotIn('short',bands)
    def test_trusted_accepted_set_changes_deficit_but_not_prior_task_lock(self):
        from webcollect.band_budget import reserve,bind_accepted_set,_project
        from webcollect.agent_feedback import reference
        from webcollect.batch_core import save_json
        registry=self.fixture.scope['registry'];task,attempt=self.task_attempt(1)
        old=reserve(registry,task,attempt)
        members=[]
        for n in range(5):
            p=self.root/f'accepted-{n}.json';save_json(p,{'sample_id':str(n),'status':'accepted','effective_steps':5})
            members.append({'sample_id':str(n),'effective_steps':5,'acceptance_receipt':reference(p)})
        source=self.root/'accepted.json';save_json(source,{'schema_version':'webcollect-explicit-accepted-bands-1',
            'project':_project(registry),'deduplication':'COMPLETE','members':members})
        # Test quota arithmetic from a controlled trusted projection. The
        # production reader separately rejects this synthetic index as admission.
        trusted=distribution(reference(source))['accepted']
        with patch('webcollect.band_budget._accepted',return_value=trusted):
            bind_accepted_set(registry,reference(source))
            self.assertEqual(reserve(registry,task,attempt),old)
            new=reserve(registry,*self.task_attempt(2))
        self.assertEqual(new['accepted']['denominator'],5)
        self.assertEqual(new['assigned_band'],'long')
        with self.assertRaisesRegex(ValueError,'quality-inspector'):bind_accepted_set(registry,reference(source))
        data=load_json(source);data['members'].append(data['members'][0]);source=self.root/'duplicate-accepted.json';save_json(source,data)
        with self.assertRaises(ValueError):distribution(reference(source))


class BandedSafetyTests(ReactHarness,unittest.IsolatedAsyncioTestCase):
    setUp=BandedSessionTests.setUp
    recorded=BandedSessionTests.recorded
    derive=BandedSessionTests.derive
    async def test_contracted_seven_step_proposal_leaves_one_slot_for_the_visible_result(self):
        from webcollect.goal_evidence import VERSION as evidence_version
        from webcollect.react_session import ReactStop

        session, _ = self.recorded(7, name='contracted-seven')
        session.task['fragment']['session_objective'] = {'objective':{
            'kind':'calculation', 'description':'读出面积',
            'evidence_contract':{'version':evidence_version, 'kind':'calculation',
                'inputs':[{'label':'长','value':'12.5'}], 'result_label':'面积','unit':'平方英尺'}}}
        await session._observe()
        controller = session.plan_controller
        await controller.request(session)
        self.assertEqual(controller.check_page_urls['p0'], self.page.url)
        self.assertEqual(len(controller.frozen_plan['steps']), 7)
        self.assertEqual(controller.target_steps, 8)
        controller.position = 7
        session.trajectory = [{'effect_evidence':{'verified':True}} for _ in range(7)]
        async def choose_last(prompt):
            self.assertEqual(prompt['replan_contract']['remaining_effective_limit'], 1)
            self.assertIn('replan', {option['choice'] for option in prompt['options']})
            remaining = plan_for(prompt, 7)
            remaining['steps'] = [{'action':'click','target':{'text':'计算面积'},
                'purpose':'取得本次计算结果','expected':{'kind':'goal_evidence'}}]
            remaining['finish_when'] = {'kind':'goal_evidence'}
            return {'choice':'replan','plan':remaining}
        session.choose = choose_last
        with patch('webcollect.goal_evidence.progress', return_value={'status':'UNVERIFIED','kind':'calculation'}):
            await controller.round(session)
            self.assertEqual(controller.plan['steps'][0]['target']['text'], '计算面积')
            session.trajectory.append({'effect_evidence':{'verified':True}})
            with self.assertRaisesRegex(ReactStop, 'FROZEN_PLAN_ENDPOINT_UNPROVEN'):
                await controller.round(session)
        self.assertEqual(session.actual_dispatches, 0)

    async def test_plain_replan_remaining_four_allowed_five_rejected_after_one(self):
        for remaining,accepted in ((4,True),(5,False)):
            s,_=self.recorded(name='remaining-'+str(remaining));await s._observe()
            c=s.plan_controller;initial=c.prompt(s)
            c.plan=plan_for(initial);c.submitted=True;c.frozen_band='five';c.target_steps=5
            s.trajectory.append({'effect_evidence':{'verified':True}})
            revised=plan_for(initial);revised['steps']=revised['steps'][:remaining]
            async def choose(p):return {'attempt_id':s.attempt_id,'observation_id':s.current['observation_id'],'choice':'replan','plan':revised}
            s.choose=choose
            if accepted:await c.request(s,[{'choice':'replan'}]);self.assertEqual(len(c.plan['steps']),4)
            else:
                with self.assertRaisesRegex(ValueError,'REMAINING'):await c.request(s,[{'choice':'replan'}])
    async def test_long_proposal_can_ground_to_five_with_reason_before_dispatch(self):
        s,e=self.recorded(name='downgrade');s.context={'band_budget':{'assigned_band':'long'}}
        original=s.choose
        async def choose(p):
            response=await original(p);response['arguments']['band_reason']='当前页面仅有五项自然相关核对用途'
            return response
        s.choose=choose;r=await s.run()
        self.assertEqual(r['effective_steps'],5,r);self.assertEqual(s.plan_controller.frozen_band,'five')
        self.assertEqual(s.plan_controller.target_steps,5)
    async def test_fresh_finish_frame_must_still_prove_endpoint_and_range_event_matches(self):
        s,e=self.recorded(name='finish-changed');original=s._native_finish
        async def changed(arguments):
            self.surface.state['visible_text']=self.surface.state['visible_text'].replace('当前终点内容','终点消失')
            return await original(arguments)
        s._native_finish=changed
        # A blocked final re-observation must not create a normal finish record.
        r=await s.run();self.assertNotEqual(r.get('collection_ending',{}).get('kind'),'HOST_PLAN_ENDPOINT')
        self.assertFalse(list((e/'raw').glob('*host-plan-finish.json')))
    async def test_selected_after_frame_without_probe_is_a_state_fact_not_dispatch_permission(self):
        s,_=self.recorded();await s._observe();ob=s.current;c=ob['controls']['control-0']
        c['element'].update(text='部门',state='selected');c['readable_labels']=[];c['probe']=None
        self.assertTrue(proves({'kind':'selected','text':'部门'},ob))
        self.assertNotEqual(c['actions']['click']['status'],'PROVEN')


class BandedRegionsTests(unittest.TestCase):
    def test_region_owner_excludes_footer_and_keeps_blank_distinct_from_explicit_empty(self):
        from webcollect.banded_plan import region_evidence
        state={'screen_resolution':[1280,720],'elements':[
            {'element_id':'heading','text':'政策文件','visible':True,'bbox':[100,300,1100,340],'native_role':'h1'},
            {'element_id':'footer','text':'全国人大','visible':True,'bbox':[120,400,300,430],'native_role':'a'}],
            'capture_controls':[{'element_id':'heading','selector':'body > main > h1'},
                                {'element_id':'footer','selector':'body > footer > a'}]}
        blank=region_evidence(state,'政策文件');self.assertEqual(blank['status'],'NOT_YET_OBSERVED')
        self.assertEqual(blank['visible_rows'],[])
        state['elements'].append({'element_id':'row','text':'具体政策标题','visible':True,'bbox':[120,400,1000,430],'native_role':'a'})
        state['capture_controls'].append({'element_id':'row','selector':'body > main > ul > li > a'})
        self.assertEqual(len(region_evidence(state,'政策文件')['visible_rows']),1)
        state['elements'][-1].update(text='暂无数据',native_role='p')
        self.assertEqual(region_evidence(state,'政策文件')['status'],'EXPLICIT_EMPTY')
    def test_initial_dom_has_real_character_budget_and_omission_metadata(self):
        from webcollect.banded_plan import initial_projection
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';p.write_text(json.dumps({'elements':[{'element_id':str(i),'visible':True,'text':'信息'*100,
                'native_role':'a','parent_id':'root','bbox':[0,0,10,10]} for i in range(500)]}))
            obs={'evidence':{'state':{'path':str(p)}},'controls':{}}
            rows,coverage=initial_projection(obs)
            self.assertLessEqual(len(json.dumps(rows,ensure_ascii=False,separators=(',',':'))),6500)
            self.assertGreater(coverage['omitted'],0)


class BandedCapTests(unittest.TestCase):
    setUp=BandedWireTests.setUp
    def test_plain_mode_26th_request_is_rejected_by_same_session_ledger(self):
        import time
        f=self.f;cfg=f.config('glm');cfg['budget']['lease_seconds']=100000
        ledger,job,g=f.gateway(cfg);clock=[time.time()]
        def now():clock[0]+=2;return clock[0]
        with patch('webcollect.batch_core.time.time',side_effect=now):
            for n in range(25):
                g.call_message(job,'cap-'+str(n),'x',{'type':'object'},system='s',attempt_id='cap-session',max_requests=25)
            with self.assertRaises(SessionGLMCallLimit):
                g.call_message(job,'cap-26','x',{'type':'object'},system='s',attempt_id='cap-session',max_requests=25)
        self.assertEqual(len(f.opener.calls),25)
        with ledger.connect() as con:self.assertEqual(ledger.session_http_usage(con,'cap-session')['used'],25)


class BandedConcurrencyTests(unittest.TestCase):
    setUp=BandedBudgetTests.setUp
    task_attempt=BandedBudgetTests.task_attempt
    def test_four_different_and_same_tasks_reserve_without_losing_local_competition(self):
        from concurrent.futures import ThreadPoolExecutor
        from webcollect.band_budget import reserve
        from threading import Barrier
        for same in (False,True):
            barrier=Barrier(4)
            def reserve_one(n):
                barrier.wait();return reserve(self.fixture.scope['registry'],*self.task_attempt(500 if same else 200+n))
            with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(reserve_one,range(4)))
            self.assertEqual(len(results),4)
            if same:self.assertTrue(all(r==results[0] for r in results))
            else:self.assertEqual(len({r['reservation_ordinal'] for r in results}),4)


class BandedRecoveryTests(ReactHarness,unittest.IsolatedAsyncioTestCase):
    setUp=BandedSessionTests.setUp
    recorded=BandedSessionTests.recorded
    async def test_error_recovery_prefix_keeps_five_band_and_revision_has_only_four_remaining(self):
        self.surface.state['visible_text']='ERROR: ZERO SIZE OBJECT'
        s,_=self.recorded(name='error-prefix');s.context={'band_budget':{'assigned_band':'five'}}
        await s._observe();c=s.plan_controller;prompts=[]
        async def choose(p):
            prompts.append(deepcopy(p))
            plan=plan_for(p);plan['steps']=[{'action':'open_url','page_id':'p0','purpose':'恢复有据入口',
                'expected':{'kind':'url','text':s.page.url}}]
            return {'name':'submit_plan','tool_call_id':'error-provider','arguments':plan}
        s.choose=choose;await c.request(s)
        self.assertEqual(c.frozen_band,'five');self.assertEqual(c.target_steps,5)
        self.assertTrue(c.recovery_prefix)
        # A recovery prefix is counted from original execution, never from this plan.
        s.trajectory=[{'effect_evidence':{'verified':True}}]
        self.surface.state['visible_text']='已恢复的业务页面';await s._observe()
        async def revise(p):
            plan=plan_for(p);plan['steps']=plan['steps'][:4]
            return {'attempt_id':s.attempt_id,'observation_id':s.current['observation_id'],'choice':'replan','plan':plan}
        s.choose=revise;await c.request(s,[{'choice':'replan'}])
        self.assertEqual(len(c.plan['steps']),4);self.assertFalse(c.recovery_prefix)
    async def test_final_document_change_with_proved_endpoint_finishes_without_model_http(self):
        s,_=self.recorded(name='doc-end');execute=self.surface.execute_action
        def action(kind,args):
            execute(kind,args)
            if len(self.surface.executed)==5:self.surface.state['document_identity']['performance_time_origin']+=1
        self.surface.execute_action=action
        result=await s.run();self.assertEqual(result['effective_steps'],5,result)
        self.assertEqual(len(self.prompts),1);self.assertEqual(result['collection_ending']['kind'],'HOST_PLAN_ENDPOINT')


class BandedAtomicAccountingTests(unittest.TestCase):
    setUp=BandedWireTests.setUp
    def test_plain_protocol_uses_original_atomic_cap_and_account_guard(self):
        import time
        from webcollect.batch_core import BudgetStop
        f=self.f;cfg=f.config('glm');cfg['budget']['lease_seconds']=100000
        ledger,job,g=f.gateway(cfg);clock=[time.time()]
        def now():clock[0]+=2;return clock[0]
        material={'protocol':'banded-plain-json-1','http_dispatch':True,'dispatch_attempt_id':'plain-atomic',
                  'dispatch_max_requests':1,'account_id':'controlled-fixture-account'}
        with patch('webcollect.batch_core.time.time',side_effect=now):
            first=ledger.reserve_request(job,'one',0,material)
            with self.assertRaises(OutcomeUnknown):ledger.reserve_request(job,'two',0,material)
            ledger.settle_request(first['id'],state='succeeded',usage={'input_tokens':1,'output_tokens':1,'cached_input_tokens':0},response={'result':{}})
            with self.assertRaises(BudgetStop):ledger.reserve_request(job,'three',0,material)
        self.assertEqual(ledger.summary()['model_requests'],1)


class BandedTailTests(ReactHarness,unittest.IsolatedAsyncioTestCase):
    setUp=BandedSessionTests.setUp
    recorded=BandedSessionTests.recorded
    derive=BandedSessionTests.derive
    fail_local=BandedSessionTests.fail_local
    async def test_new_plan_fifth_known_no_effect_keeps_four_step_flagged_prefix(self):
        self.fail_local(5)
        s,e=self.recorded(name='new-known-tail',mark_endpoint=False);r=await s.run()
        self.assertEqual(r['effective_steps'],4,r)
        self.assertEqual(r['collection_ending']['kind'],'KNOWN_NO_EFFECT')
        self.assertEqual(len(self.prompts),1)
        _,annotation=self.derive(e)
        self.assertTrue(annotation['short_flow']);self.assertEqual(annotation['completion_status'],'controlled_exception')
    async def test_new_plan_fifth_unknown_keeps_original_raw_without_replaying(self):
        s,e=self.recorded(name='new-unknown-tail');execute=self.surface.execute_action
        def action(kind,args):
            if len(self.surface.executed)==4:
                self.surface.executed.append((kind,args));raise TimeoutError('CONTROLLED original external effect unknown')
            execute(kind,args)
        self.surface.execute_action=action
        r=await s.run();self.assertTrue(r['unknown']);self.assertEqual(r['actual_actions'],5)
        self.assertFalse(r['collection_ending']['safe_for_pending_sample']);self.assertEqual(len(self.prompts),1)
        self.assertFalse((e/'saved_sample.json').exists())


class BandedImageTests(unittest.TestCase):
    def test_original_fallback_and_crop_keep_bytes_pixels_mapping_and_reject_outside_crop(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'original.png'
            image=Image.new('RGBA',(1280,720),(10,20,30,128));image.save(source)
            full=derive(source,root/'derived',original=True)
            self.assertEqual(Path(full['path']).read_bytes(),source.read_bytes())
            roi=derive(source,root/'derived',crop=(10,20,30,40),original=True)
            with Image.open(roi['path']) as actual:self.assertEqual(actual.tobytes(),image.crop((10,20,30,40)).tobytes())
            self.assertEqual(roi['mapping'],{'origin':[10,20],'source_per_output_pixel':[1,1]})
            with self.assertRaises(ValueError):derive(source,root/'derived',crop=(1279,0,1281,10))


class BandedVisualBindingTests(ReactHarness,unittest.IsolatedAsyncioTestCase):
    setUp=BandedSessionTests.setUp
    recorded=BandedSessionTests.recorded
    async def test_plain_visual_result_binds_current_original_image_and_document_without_dispatch(self):
        s,e=self.recorded(name='visual-binding');await s._observe();c=s.plan_controller
        c.plan=plan_for(c.prompt(s));c.submitted=True;c.frozen_band='five';c.target_steps=5
        predicate={'kind':'list_present','text':'政策文件','region':'政策文件'}
        c.plan['finish_when']=predicate
        async def choose(p):return {'attempt_id':s.attempt_id,'observation_id':s.current['observation_id'],
            'choice':'visual_yes','visual_evidence':{'quotes':['受控测试结果行'],'visible_row_count':1}}
        s.choose=choose
        await c.request(s,c.visual_option(predicate))
        self.assertTrue(c.proved(predicate,s));self.assertEqual(s.actual_dispatches,0)
        proof=load_json(next(iter(c.visual_confirmations.values()))['path'])
        self.assertEqual(proof['image'],s.current['evidence']['image']);self.assertTrue(proof['decision_event'])
        s.current['document_identity']={'changed':'document'}
        self.assertFalse(c.proved(predicate,s))


class BandedAmbiguityExecutionTests(ReactHarness,unittest.IsolatedAsyncioTestCase):
    setUp=BandedSessionTests.setUp
    recorded=BandedSessionTests.recorded
    async def test_model_selected_same_name_node_executes_after_its_current_document_probe(self):
        for e in self.surface.state['elements'][:2]:e['text']='部门'
        s,e=self.recorded(name='same-name-execution');calls=[]
        async def choose(p):
            calls.append(deepcopy(p))
            if len(calls)==1:
                plan=plan_for(p,1);plan['steps']=[{'action':'click','target':{'text':'部门'},
                    'purpose':'选择同名输入中的第二项','expected':{'kind':'focused','text':'部门'}}]
                plan['finish_when']={'kind':'visible_text','text':'受控输入页面'}
                return {'name':'submit_plan','tool_call_id':'provider-ambiguous','arguments':plan}
            return {'attempt_id':s.attempt_id,'observation_id':s.current['observation_id'],'choice':'node:control-1'}
        s.choose=choose;r=await s.run()
        self.assertEqual(r['effective_steps'],1,r);self.assertEqual(len(calls),2)
        self.assertEqual(len(self.surface.executed),1)
        self.assertTrue(next(v for v in self.surface.state['values'] if v['element_id']=='control-1')['focused'])


class BandedAsyncResultTests(ReactHarness,unittest.IsolatedAsyncioTestCase):
    setUp=BandedSessionTests.setUp
    recorded=BandedSessionTests.recorded
    async def test_expected_async_result_waits_on_same_action_before_raw_after_is_finalized(self):
        s,e=self.recorded(name='async-original-action');choose=s.choose;capture=self.surface.capture;post=[0]
        async def response(p):
            r=await choose(p);r['arguments']['steps'][0]['expected']={'kind':'visible_text','text':'异步业务结果已出现'}
            return r
        async def delayed(*args,**kwargs):
            if len(self.surface.executed)==1:
                post[0]+=1
                if post[0]>=2 and '异步业务结果已出现' not in self.surface.state['visible_text']:
                    self.surface.state['visible_text']+='\n异步业务结果已出现'
            return await capture(*args,**kwargs)
        s.choose=response
        with patch('webcollect.browser.capture',side_effect=delayed):r=await s.run()
        self.assertEqual(r['effective_steps'],5,r);self.assertEqual(r['actual_actions'],5)
        self.assertEqual(len(self.prompts),1)
        after=s.observation_records[s.trajectory[0]['after_observation_id']]
        self.assertIn('异步业务结果已出现',load_json(after['evidence']['state']['path'])['visible_text'])
        waits=list((e/'raw').glob('*plan-result-wait.json'));self.assertEqual(len(waits),1)
        self.assertFalse(load_json(waits[0])['dispatched_again'])
