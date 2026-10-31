"""Disposable agent protocol simulations. No browser, site, model or QC service."""
import asyncio
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import socket
import time
import sqlite3
import unittest
from unittest.mock import patch
from PIL import Image
from test_planner_repair import SemanticFixture
from webcollect.batch_core import save_json, load_json, file_sha, BatchLedger
from webcollect.agent_controller import (FragmentController, compile_goal, LIMITS, FRAGMENT_VERSION,
    ControllerStop, exclusive, model_chooser)
from webcollect.agent_observation import project, action_availability, PROVEN, INSUFFICIENT, UNAVAILABLE
from webcollect.planning import object_sha256
from webcollect.browser import fingerprint
import webcollect.collect  # Bind imports before per-test browser.capture mocks.


class Surface:
    def __init__(self, state):
        self.state = deepcopy(state)
        self.state.update(document_identity={'url_without_fragment':state['url'],'performance_time_origin':123},
                          scroll=[0,0], screen_resolution=[1280,720], target=None, title='受控输入页面')
        self.state['visible_text'] = '受控输入页面\n数量\n单价\n这里查看当前输入内容与页面状态。'
        for i, row in enumerate(self.state['elements']):
            row.update(bbox=[10,20+i*60,210,60+i*60], enabled=True, visible=True, element_type='input' if i<2 else 'text')
        for value in self.state['values']:
            value.update(selection_start=0,selection_end=0,input_type='text',value_visible=True)
        self.readable = True; self.executed = []

    async def capture(self, page, selector=None, index=0, **kw):
        state = deepcopy(self.state)
        state['visible_text'] += '\n' + '\n'.join(e.get('text','') for e in state['elements'])
        for value in state['values']: value['display_value'] = value['value']
        binding = next((b for b in state['capture_controls'] if b['selector']==selector), None)
        if binding:
            eid = binding['element_id']; row = next(e for e in state['elements'] if e['element_id']==eid)
            value = next((v for v in state['values'] if v['element_id']==eid), {})
            label = value.get('value') or '请输入数量'
            state['target'] = {'element_id':eid,'coordinate':[30,row['bbox'][1]+10], 'hit_valid':True,
                'focused':value.get('focused',False), 'value':value.get('value'),
                'visible_label_evidence':[{'kind':'visible_native_value' if value.get('value') else 'visible_placeholder',
                                           'text':label}] if self.readable else []}
        else: state['target'] = None
        if kw.get('assertions'):
            state['assertion_targets'] = [{'selector':a['selector'],'index':a.get('index',0),
                'visible':True,'value_visible':True,'target_text':'输入条件','display_value':a['value'],'value':next(v['value'] for v in state['values']
                    if v['element_id']==next(b['element_id'] for b in state['capture_controls'] if b['selector']==a['selector']))}
                for a in kw['assertions']]
        token = int(object_sha256({k:self.state.get(k) for k in ('url','values','scroll','document_identity')})[:6],16)
        stream=BytesIO();Image.new('RGB',(1280,720),(token>>16,(token>>8)&255,token&255)).save(stream,'PNG')
        png=stream.getvalue()
        return {'state':state,'png':png,'capture':{'snapshot_source':'browser_dom',
            'screenshot_sha256':hashlib.sha256(png).hexdigest(), 'coordinate_space':'screenshot_css_pixels',
            'attempts':[{'dom_stable':True,'before_fingerprint':fingerprint(state),'after_fingerprint':fingerprint(state),
                         'started_ns':time.time_ns(),'ended_ns':time.time_ns()}]}}

    def execute(self, op):
        from webcollect.browser import prepare_action
        self.executed.append(op['action_type'])
        cid=op.get('evidence',{}).get('anchor_element_id')
        value=next((v for v in self.state['values'] if v['element_id']==cid),None)
        action=op['action_type']
        if action=='click':
            for v in self.state['values']:v['focused']=v is value
        elif action=='hotkey':
            value=next(v for v in self.state['values'] if v['focused'])
            keys=op['arguments']['keys']
            if keys==['meta','a']:
                value.update(selection_start=0,selection_end=len(value['value']))
            elif keys==['backspace']:
                value.update(value='',selection_start=0,selection_end=0)
        elif action=='type':
            value['value']=op['arguments']['text'];value.update(selection_start=len(value['value']),selection_end=len(value['value']))
        elif action=='scroll': self.state['scroll'][1]+=480
        elif action=='open_url':
            self.state['url']=op['arguments']['url'];self.state['document_identity']['performance_time_origin']+=1

    @property
    def url(self): return self.state['url']
    def set_default_timeout(self,*args): pass
    def on(self,*args): pass
    async def goto(self,*args,**kw): pass
    async def wait_for_timeout(self,*args): pass
    async def evaluate(self,script,*args):
        return 123 if script=='performance.timeOrigin' else None
    async def close(self): pass


class AgentLoop(SemanticFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.network = patch.object(socket.socket,'connect',side_effect=AssertionError('external IO forbidden'))
        self.network.start();self.addCleanup(self.network.stop)
        self.cap, _ = self.semantic()
        self.spec={'schema_version':FRAGMENT_VERSION,'task_family':'navigation-reading',
            'instruction':'在「受控离线页面」修改数量和单价，并查看当前输入状态。',
            'task_type':['填写表单','数据查看'],'page_id':'p0','end_description':'查看本段输入状态，未提交业务。',
            'allowed_actions':['set_value','click','type','hotkey'], 'budgets':dict(LIMITS)}
        self.task=compile_goal(self.cap,self.spec,'fixture')
        self.surface=Surface(load_json(self.cap['capabilities'][0]['page_anchor']['state']['path']))
        self.patch=patch('webcollect.browser.capture',side_effect=self.surface.capture)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.prompts=[];self.raw=[]

    async def chooser(self,prompt):
        self.prompts.append(deepcopy(prompt));n=prompt['used']['max_actions']
        cid='control-0' if n<3 else 'control-1'
        base={'kind':'plan','observation_id':prompt['observation']['observation_id'],'reason':'继续当前输入片段',
              'control_id':'','steps':[]}
        if n>=6:return {**base,'kind':'finish'}
        c=prompt['observation']['controls'][cid]
        if c['actions']['set_value']['status']!=PROVEN:
            return {**base,'kind':'observe','control_id':cid}
        return {**base,'steps':[{'action':'set_value','control_id':cid,'value':'20' if n<3 else '30',
                               'goal':'修改当前字段','expected':'显示填写值'}]}

    def controller(self, choose=None, name='controller', **kw):
        return FragmentController(self.task,self.root/name,choose or self.chooser,**kw)

    async def step(self, controller):
        op=await controller.next(self.surface)
        if op['action_type']=='complete':return op
        from webcollect.browser import prepare_action
        prepare_action(controller.captured['state'],op)
        ref=controller.before_dispatch(op,controller.captured['state'],controller.current['evidence']['image'])
        self.surface.execute(op)
        raw={'operation':op,'state':deepcopy(controller.captured['state']), 'capture':controller.captured['capture'],
             'controller_dispatch':ref,'ended_at':'2026-10-30T00:00:00+08:00'}
        reference=exclusive(self.root/f'raw-{len(self.raw)}.json',raw)
        self.raw.append(raw);controller.result(reference)
        return op

    async def test_success_six_actual_actions_original_decisions_and_terminal(self):
        from webcollect.agent_audit import terminal_proof
        c=self.controller()
        while (await self.step(c))['action_type']!='complete': pass
        self.assertEqual(self.surface.executed,['click','hotkey','type']*2)
        result=terminal_proof(self.task,self.raw,{'screenshot_sha256':'fixture-ending'})
        self.assertEqual(result['effective_steps'],6);self.assertEqual(result['semantic_status'],'REVIEW_REQUIRED')
        self.assertEqual(c.state,'finished');self.assertEqual(c.used['max_actions'],6)
        self.assertTrue(any(p['observation']['controls']['control-0']['readable_labels'] for p in self.prompts))
        with self.assertRaises(FileExistsError):self.controller()
        self.raw[0]['operation']['goal']='tampered'
        with self.assertRaises(ValueError):terminal_proof(self.task,self.raw,{'screenshot_sha256':'ending'})

    async def test_inventory_text_is_not_readable_evidence_and_supplement_recovers(self):
        c=self.controller();obs=await c.observe(self.surface)
        self.assertTrue(obs['controls']['control-0']['element']['text'])
        self.assertEqual(obs['controls']['control-0']['actions']['click']['status'],INSUFFICIENT)
        self.assertIn('control-0',obs['supplemental_observation']['control_ids'])
        obs=await c.observe(self.surface,'control-0')
        self.assertEqual(obs['controls']['control-0']['actions']['click']['status'],PROVEN)
        self.surface.readable=False;obs=await c.observe(self.surface,'control-0')
        self.assertEqual(obs['controls']['control-0']['actions']['click']['reason'],'MISSING_READABLE_LABEL_EVIDENCE')

    async def test_scroll_old_target_disappears_and_navigation_invalidates_ids(self):
        c=self.controller();await c.observe(self.surface);before=await c.observe(self.surface,'control-0')
        op=c.compile_step({'action':'set_value','control_id':'control-0','value':'42','goal':'填写','expected':'显示'},before)
        self.assertEqual(len(op),3)
        self.surface.state['scroll'][1]=480;self.surface.state['elements'][0]['bbox']=[0,-60,100,-20]
        after=await c.observe(self.surface,'control-0')
        self.assertEqual(after['controls']['control-0']['actions']['click']['status'],UNAVAILABLE)
        with self.assertRaises(ValueError):c.compile_step({'action':'set_value','control_id':'control-0','value':'42','goal':'填写','expected':'显示'},after)
        self.surface.state['document_identity']['performance_time_origin']+=1
        from webcollect.agent_observation import require_action
        actual={'action_type':'click','selector':'#control-0','evidence':{'observation_protocol':before['schema_version'],
            'state_sha256':before['state_sha256'],'anchor_element_id':'control-0'}}
        with self.assertRaisesRegex(ValueError,'STALE'):require_action(self.surface.state,actual)

    async def test_input_placeholder_changes_and_current_value_label_is_refreshed(self):
        self.surface.state['values'][0]['value']=''
        c=self.controller();await c.observe(self.surface)
        before=await c.observe(self.surface,'control-0')
        self.assertEqual(before['controls']['control-0']['readable_labels'][0]['text'],'请输入数量')
        self.surface.state['values'][0]['value']='更新内容'
        after=await c.observe(self.surface,'control-0')
        self.assertEqual(after['controls']['control-0']['readable_labels'][0]['text'],'更新内容')
        self.assertNotEqual(before['observation_id'],after['observation_id'])

    async def test_compiled_expansion_cost_enforced_before_dispatch(self):
        c=self.controller();await c.observe(self.surface);obs=await c.observe(self.surface,'control-0')
        step={'action':'set_value','control_id':'control-0','value':'20','goal':'填写','expected':'显示'}
        self.assertEqual(len(c.compile_step(step,obs)),3)
        self.surface.state['values'][0].update(value='',focused=True)
        obs=await c.observe(self.surface,'control-0');self.assertEqual(len(c.compile_step(step,obs)),1)
        c.used['max_actions']=7
        self.surface.state['values'][0].update(value='10',focused=False)
        # Chooser attempts a 3-action replacement with one action remaining.
        async def bad(p):return {'kind':'plan','observation_id':p['observation']['observation_id'],
            'reason':'controlled too large','control_id':'','steps':[step]}
        c.choose=bad;c.last_control='control-0'
        with self.assertRaises(ControllerStop):await c.next(self.surface)
        self.assertEqual(c.used['max_actions'],7)
        self.assertTrue(any('remaining' in f['reason'] for f in c.feedback))

    async def test_budget_exhaustion_and_no_path_are_terminal_without_padding(self):
        self.task['fragment']['budgets']['max_model_calls']=1
        self.task['workflow_proposal']['spec']['budgets']['max_model_calls']=1
        c=self.controller()
        with self.assertRaisesRegex(ControllerStop,'BUDGET_EXHAUSTED'):await c.next(self.surface)
        self.assertEqual(c.used['max_actions'],0)
        async def no_path(p):return {'kind':'no_path','observation_id':p['observation']['observation_id'],
            'reason':'原始空结果：当前未观察到可执行控件','control_id':'','steps':[]}
        c=self.controller(no_path,name='no-path')
        with self.assertRaisesRegex(ControllerStop,'原始空结果'):await c.next(self.surface)
        self.assertEqual(c.state,'NO_FEASIBLE_PATH')

    async def test_unknown_blocks_restart_and_cannot_resend(self):
        calls=[]
        async def unknown(p):calls.append(p);raise TimeoutError('UNKNOWN')
        c=self.controller(unknown)
        with self.assertRaisesRegex(ControllerStop,'UNRESOLVED'):await c.next(self.surface)
        before={p.name:file_sha(p) for p in c.root.iterdir()}
        with self.assertRaises(ControllerStop):await c.next(self.surface)
        self.assertEqual(len(calls),1)
        self.assertEqual(before,{p.name:file_sha(p) for p in c.root.iterdir()})
        with self.assertRaises(FileExistsError):self.controller(unknown)

    async def test_execution_failure_keeps_original_attempt_no_splicing(self):
        c=self.controller();op=await c.next(self.surface)
        ref=c.before_dispatch(op,c.captured['state'],c.current['evidence']['image'])
        raw=exclusive(self.root/'failed-raw.json',{'operation':op,'state':c.captured['state'],'execution_error':'实际点击失败'})
        with self.assertRaisesRegex(ControllerStop,'EXECUTION_FAILED'):c.result(raw,error='实际点击失败')
        self.assertEqual(c.state,'EXECUTION_FAILED');self.assertTrue(Path(ref['path']).exists())
        with self.assertRaises(ControllerStop):await c.next(self.surface)

    async def test_first_and_intermediate_duplicate_frames_stop_early(self):
        c=self.controller(frame_guard=lambda ref:[{'sample_id':'original','image':ref}])
        with self.assertRaisesRegex(ControllerStop,'DUPLICATE'):await c.next(self.surface)
        self.assertEqual(c.used['max_actions'],0)
        def middle(ref):return [{'sample_id':'middle-original'}] if len(self.surface.executed)>=3 else []
        c=self.controller(name='middle',frame_guard=middle)
        for _ in range(3):await self.step(c)
        with self.assertRaisesRegex(ControllerStop,'DUPLICATE'):await c.next(self.surface)
        self.assertEqual(c.used['max_actions'],3)

    async def test_same_failure_context_changes_selection_and_is_not_path_only(self):
        from webcollect.agent_feedback import site_context, save_attempt_feedback
        from webcollect.runtime import SCHEMA
        from test_p0_production import seed_captures
        sid='CONTROLLED-feedback';registry=self.root/'production-fixture.db'
        rawdir=self.root/'capture/evidence'/sid;rawdir.mkdir(parents=True)
        frame=await self.surface.capture(None,'#control-0');sample=self.root/'capture/rejected'/sid/'images';sample.mkdir(parents=True)
        (sample/'step_001.png').write_bytes(frame['png'])
        op={'action_type':'click','selector':'#control-0','goal':'填写当前数量','arguments':{},'evidence':{}}
        save_json(rawdir/'step_001.json',{'step_id':1,'state':frame['state'],'capture':frame['capture'],
            'operation':op,'target_element':frame['state']['elements'][0],'execution_error':'当前目标点击失败'})
        attempt={'attempt_id':'attempt-'+sid,'task_id':sid,'sample_id':sid}
        ref=save_attempt_feedback(rawdir,attempt,'rejected','当前目标点击失败')
        seed_captures(registry,[sid],prefix=0,evidence={sid:[ref]})
        with sqlite3.connect(registry) as con:
            con.execute("UPDATE m4_attempts SET status='rejected',failure_class='model',root_cause='controlled-click-failed'")
        context=site_context(registry,self.cap['site_uri'])
        self.assertEqual(context['executions'][0]['feedback']['steps'][0]['execution_error'],'当前目标点击失败')
        self.assertTrue(context['images']);self.assertTrue(context['avoid'][0]['state']['values'])
        c=self.controller(site_context=context);await c.observe(self.surface);obs=await c.observe(self.surface,'control-0')
        c.queue_identity={k:deepcopy(obs[k]) for k in ('url','document_identity','scroll')}
        with self.assertRaisesRegex(ValueError,'Known same-state execution failure'):
            c.operation({'action':'click','control_id':'control-0','goal':'填写','expected':'显示'},obs['controls']['control-0'])
        seen=[]
        async def next_round(prompt):
            seen.append(prompt['site_context'])
            return {'kind':'no_path','observation_id':prompt['observation']['observation_id'],
                    'reason':'依据原失败现场选择停止','control_id':'','steps':[]}
        c.choose=next_round
        with self.assertRaises(ControllerStop): await c.next(self.surface)
        self.assertEqual(seen[0]['executions'][0]['feedback']['steps'][0]['execution_error'],'当前目标点击失败')

    async def test_rejected_step_images_are_materialized_from_preserved_originals(self):
        """Real-run v9/v10/v11 lesson: a react rejection declared packaged step
        images that no later bind materialized, and the next run's site context
        failed closed on the dangling absolute paths. The receipt itself must
        leave only resolvable references behind."""
        from webcollect.agent_feedback import site_context, save_attempt_feedback
        from test_p0_production import seed_captures
        from webcollect.batch_core import file_sha
        sid='CONTROLLED-materialize';registry=self.root/'production-fixture.db'
        rawdir=self.root/'capture/evidence'/sid;rawdir.mkdir(parents=True)
        (rawdir/'raw').mkdir()
        frame=await self.surface.capture(None,'#control-0')
        (rawdir/'raw'/'dispatch-frame-001.png').write_bytes(frame['png'])
        op={'action_type':'click','selector':'#control-0','goal':'填写当前数量','arguments':{},'evidence':{}}
        save_json(rawdir/'step_001.json',{'step_id':1,'state':frame['state'],'capture':frame['capture'],
            'operation':op,'target_element':frame['state']['elements'][0],'execution_error':'受控失败'})
        attempt={'attempt_id':'attempt-'+sid,'task_id':sid,'sample_id':sid}
        ref=save_attempt_feedback(rawdir,attempt,'rejected','受控失败')
        declared=json.loads(Path(ref['path']).read_text())['steps'][0]['image']
        packaged=Path(declared['path'])
        self.assertTrue(packaged.is_file(),'declared step image must exist right after the receipt')
        self.assertEqual(file_sha(packaged),declared['sha256'])
        seed_captures(registry,[sid],prefix=0,evidence={sid:[ref]})
        with sqlite3.connect(registry) as con:
            con.execute("UPDATE m4_attempts SET status='rejected',failure_class='collector',root_cause='controlled'")
        context=site_context(registry,self.cap['site_uri'])
        self.assertTrue(context['executions'][0]['feedback']['steps'][0]['execution_error']=='受控失败')

    async def test_old_frozen_fragment_roundtrip_keeps_all_original_bytes(self):
        from webcollect.fragment_workflow import compile_fragment, VERSION
        from webcollect.workflow_proposal import verify_task
        spec={'schema_version':VERSION,'task_family':'navigation-reading','instruction':self.spec['instruction'],
            'task_type':['填写表单'],'steps':[{'action':'set_value','control_id':'p0/control-0','value':v,
                'goal':'修改字段','expected':'显示值'} for v in ('20','','30')], 'end_description':'查看当前值。'}
        original={r['path']:file_sha(r['path']) for r in self.task['workflow_proposal']['evidence']}
        task=compile_fragment(self.cap,spec,'old-frozen');before=deepcopy(task);verify_task(task,self.cap)
        self.assertEqual(before,task);self.assertEqual(original,{p:file_sha(p) for p in original})


    async def test_shared_collector_saves_dynamic_sample_and_audits_original_decisions(self):
        from webcollect.collect import collect_one
        from webcollect.evidence import audit_capture
        from webcollect.task_contract import PLAN_SCHEMA
        from unittest.mock import AsyncMock
        surface=self.surface
        class Context:
            pages=[surface]
            async def new_page(self):return surface
        task=deepcopy(self.task);task['_plan_schema_version']=PLAN_SCHEMA;task['initial_settle_ms']=0
        batch=self.root/'shared';sample=batch/'samples'/'S999999_sample_000001';raw=batch/'evidence'/sample.name
        def factory(bound,directory):return FragmentController(bound,directory,self.chooser)
        async def actual(page,action,args,execution=None):
            if action!='complete':
                # Execute the exact pending primitive already accepted by the controller.
                controller_op=sorted((raw/'controller').glob('*-dispatch-intent.json'))[-1]
                surface.execute(load_json(controller_op)['operation'])
        async def final(page,evidence,*args,**kw):
            result=await surface.capture(page,*args,**kw);result['terminal_refresh']={'accepted':True};return result
        async def observed(page,*args,**kw):return (await surface.capture(page,*args,**kw))['state']
        async def preflight(page,state,*args,**kw):return {'matched':True,'state_fingerprint':object_sha256(state)}
        with patch('webcollect.collect.assess_content',new=AsyncMock(side_effect=lambda *a,**kw:{
                'page_url':surface.url,'decision':{'action':'ready','reason':'受控页面就绪'}})), \
             patch('webcollect.collect.execute',side_effect=actual), \
             patch('webcollect.collect.capture',side_effect=surface.capture), \
             patch('webcollect.collect.observe',side_effect=observed), \
             patch('webcollect.collect.verify_execution_state',side_effect=preflight), \
             patch('webcollect.collect.capture_complete',side_effect=final):
            result=await collect_one(Context(),task,sample,raw,{'sample_id':sample.name},controller_factory=factory)
        self.assertEqual(len(result['steps']),7)
        self.assertEqual(load_json(raw/'task_contract.json')['effective_steps'],6)
        report=audit_capture(batch,sample.name)
        self.assertTrue(report['capture_evidence_pass'],report)


    async def test_generation_new_protocol_keeps_original_empty_reasons_and_proposals(self):
        from webcollect.task_generation import generate
        from test_s0_task_generation import catalog
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'generation.db',cfg,initialize=True)
        source=catalog(self.root/'catalog.json',[self.cap])
        response={'tasks':[self.spec],'empty_reasons':[]}
        with patch('webcollect.model_gateway.ModelGateway.call',return_value=response):
            result=generate(ledger,source,self.root/'generated',generator='agent-model')
        self.assertEqual(result['generated_tasks'],1,result)
        self.assertEqual(result['model_responses'][0]['response']['tasks'][0],self.spec)
        self.assertEqual(result['generated_task_details'][0]['operations'],[])
        from webcollect.workflow_proposal import verify_task
        verify_task(result['generated_task_details'][0],self.cap)
        # Independent next ledger is only a disposable fixture for an empty response.
        other=BatchLedger(self.root/'empty.db',cfg,initialize=True)
        reason={'category':'MISSING_OBSERVATION','reason':'原图未证明字段标签可读','control_ids':['control-0']}
        with patch('webcollect.model_gateway.ModelGateway.call',return_value={'tasks':[],'empty_reasons':[reason]}):
            empty=generate(other,source,self.root/'empty',generator='agent-model')
        self.assertEqual(empty['empty_results'][0]['reasons'][0]['original_reason'],reason)

    async def test_original_model_ledger_unknown_blocks_following_site_round(self):
        from webcollect.agent_feedback import site_context
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'model-original.db',cfg,initialize=True)
        choose=model_chooser(ledger,self.task,'original-attempt')
        prompt={'observation':{'evidence':{'image':self.cap['capabilities'][0]['page_anchor']['image']}},
                'used':{'max_decisions':1}}
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=TimeoutError('UNKNOWN')) as call:
            with self.assertRaises(TimeoutError):await choose(prompt)
            with self.assertRaises(ValueError):await choose(prompt)
        self.assertEqual(call.call_count,1)
        context=site_context(None,self.cap['site_uri'],model_ledger=ledger)
        self.assertEqual(context['unresolved'][0]['category'],'UNRESOLVED_REQUEST')

    async def test_noop_scroll_cannot_pad_and_capture_tamper_cannot_prove_label(self):
        from webcollect.agent_observation import project
        c=self.controller();await c.observe(self.surface)
        before=await c.observe(self.surface,'control-0')
        evidence=deepcopy(before['evidence'])
        receipt=load_json(evidence['capture']['path']);receipt['screenshot_sha256']='0'*64
        ref=exclusive(self.root/'bad-capture.json',receipt);evidence['capture']=ref
        obs=project(c.captured['state'],evidence)
        self.assertFalse(obs['capture_verified'])
        self.assertEqual(obs['controls']['control-0']['actions']['click']['status'],INSUFFICIENT)
        c.pending_effect=(deepcopy(self.surface.state),{'action_type':'scroll'})
        c.effect_png=object_sha256(c.captured['png'].hex())
        with self.assertRaisesRegex(ControllerStop,'NO_EFFECTIVE_ACTION'):await c.observe(self.surface)


class LocalControllerBrowser(unittest.IsolatedAsyncioTestCase):
    async def test_intercepted_html_native_actions_shared_collection_and_audit(self):
        """Every browser request is fulfilled from disposable HTML; no server/site/model."""
        import tempfile
        from urllib.parse import urlsplit
        from playwright.async_api import async_playwright
        from webcollect.browser import capture
        from webcollect.collect import collect_one
        from webcollect.evidence import audit_capture
        html='''<!doctype html><meta charset="utf-8"><title>受控输入页面</title>
        <style>body{font:20px Arial;background:white}input{width:200px;height:40px}</style>
        <h1>受控输入页面</h1><label>数量<input value="10"></label>
        <label>单价<input value="10"></label>
        <p>当前只查看两个条件的输入状态，可以在中途结束本段，不提交完整业务。这里是受控离线页面。</p>'''
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            async with async_playwright() as runtime:
                browser=await runtime.chromium.launch(channel='chrome',headless=True,args=['--disable-background-networking'])
                context=await browser.new_context(viewport={'width':1280,'height':720},locale='zh-CN',service_workers='block')
                await context.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html',body=html))
                try:
                    page=await context.new_page();await page.goto('https://controlled.invalid/')
                    original=await capture(page);anchor={}
                    for kind in ('image','state','capture'):
                        path=root/kind
                        if kind=='image':path.write_bytes(original['png'])
                        else:save_json(path,original[kind])
                        anchor[kind]={'path':str(path),'sha256':file_sha(path)}
                    await page.close()
                    cap={'capability_id':'local-control','version':'fixture','mode':'synthetic',
                        'site_uri':original['state']['url'],'site_category':'工具','task_families':['navigation-reading'],
                        'supported_actions':['click','type','hotkey','scroll'],
                        'capabilities':[{'page_uri':original['state']['url'],'title':'受控输入页面','page_anchor':anchor}]}
                    spec={'schema_version':FRAGMENT_VERSION,'task_family':'navigation-reading',
                        'instruction':'在「受控输入页面」修改数量和单价，并查看当前输入状态。',
                        'task_type':['填写表单'],'page_id':'p0','end_description':'查看本段的输入状态。',
                        'allowed_actions':['set_value','click','hotkey','type'],'budgets':dict(LIMITS)}
                    task=compile_goal(cap,spec,'fixture');task['_plan_schema_version']='webcollect-plan-m4-1'
                    async def choose(prompt):
                        count=prompt['used']['max_actions']
                        base={'kind':'finish','observation_id':prompt['observation']['observation_id'],
                            'reason':'查看当前状态','steps':[],'control_id':''}
                        if count>=6:return base
                        fields=[(cid,c) for cid,c in prompt['observation']['controls'].items() if c['binding']['tag']=='input']
                        cid,c=fields[0 if count<3 else 1]
                        if c['actions']['set_value']['status']!=PROVEN:
                            return {**base,'kind':'observe','control_id':cid}
                        return {**base,'kind':'plan','steps':[{'action':'set_value','control_id':cid,
                            'value':'20' if count<3 else '30','goal':'修改当前条件','expected':'显示输入值'}]}
                    def factory(bound,directory):return FragmentController(bound,directory,choose)
                    batch=root/'batch';sid='S999999_sample_000001'
                    with patch('webcollect.collect.verify_public_url',side_effect=lambda url,allowed_hosts=None:urlsplit(url).hostname):
                        result=await collect_one(context,task,batch/'samples'/sid,batch/'evidence'/sid,
                            {'sample_id':sid},controller_factory=factory)
                    self.assertEqual([r['tool_call']['tool_name'] for r in result['steps']],['click','hotkey','type']*2+['complete'])
                    self.assertTrue(audit_capture(batch,sid)['capture_evidence_pass'])
                    self.assertEqual(load_json(batch/'evidence'/sid/'task_contract.json')['semantic_status'],'REVIEW_REQUIRED')
                finally:
                    import os, shutil
                    export = os.environ.get('WEBCOLLECT_TEST_EVIDENCE')
                    if export: shutil.copytree(root,Path(export)/'native-controller',dirs_exist_ok=False)
                    await context.close();await browser.close()


class AgentLedgerBindings(SemanticFixture, unittest.TestCase):
    def test_model_ledger_binding_rejects_new_alias_or_changed_config(self):
        from webcollect.agent_controller import verify_ledger_binding
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'original-model.db',cfg,initialize=True)
        plan={'tasks':[{'fragment':{'schema_version':FRAGMENT_VERSION}}],
              'generation':{'controller_ledger':{'path':str(ledger.path),'config_sha256':object_sha256(cfg)}}}
        verify_ledger_binding(plan,ledger)
        other=BatchLedger(self.root/'new-alias.db',cfg,initialize=True)
        with self.assertRaises(ValueError):verify_ledger_binding(plan,other)
        with self.assertRaises(ValueError):verify_ledger_binding(plan,None)
        # Legacy plans don't acquire a new model dependency.
        verify_ledger_binding({'tasks':[{'operations':[]}]},None)

    def test_qc_context_auto_reads_original_review_and_rejects_unbound_report(self):
        from test_p0_production import seed_captures
        from webcollect.agent_feedback import site_context
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        sid='CONTROLLED-qc';registry=self.root/'registry.db';seed_captures(registry,[sid],prefix=0)
        report=self.root/'qc.json';save_json(report,{'fixture':'AUTHORED QC PROTOCOL INPUT, NOT AN ACTUAL REVIEW'})
        ref={'path':str(report),'sha256':file_sha(report)}
        with sqlite3.connect(registry) as con:
            con.execute('INSERT INTO m4_reviews VALUES(?,?,?,?,?)',(sid,'reject',json.dumps([ref]),'目标不清晰',0))
        with self.assertRaises(ValueError):site_context(registry,'https://example.org/')
        dataset=self.root/'dataset';(dataset/'samples').mkdir(parents=True)
        authored={'dataset':str(dataset),'issues':[{'step_id':3,'target':'输入字段','reason':'字被遮挡',
                                                  'duplicate_of':'CONTROLLED-other/step_002.png'}]}
        with patch('webcollect.runtime._bound_quality_report',return_value=(authored,ref)) as gate:
            context=site_context(registry,'https://example.org/')
        gate.assert_called_once_with([ref])
        self.assertEqual(context['quality'][0]['report']['issues'][0]['step_id'],3)
        self.assertNotIn('QC_approval',context)


    def test_legacy_unscoped_request_is_retained_as_unresolved(self):
        from webcollect.agent_feedback import site_context
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'legacy-model.db',cfg,initialize=True)
        original=ledger.enqueue('task-generation',{'capability_sha256':'legacy-unscoped'})
        context=site_context(None,'https://example.org/',model_ledger=ledger)
        self.assertEqual(context['unresolved'][0]['job_id'],original)
        self.assertEqual(ledger.get(original)['state'],'queued')

    def test_precommit_feedback_does_not_overwrite_rejected_outcome(self):
        from webcollect.agent_feedback import save_attempt_feedback
        evidence=self.root/'raw';evidence.mkdir()
        attempt={'attempt_id':'CONTROLLED-attempt','sample_id':'CONTROLLED-sample','task_id':'CONTROLLED-task'}
        provisional=save_attempt_feedback(evidence,attempt,'collected_pending_review')
        final=save_attempt_feedback(evidence,attempt,'rejected','commit duplicate conflict')
        self.assertNotEqual(provisional['path'],final['path'])
        self.assertEqual(load_json(provisional['path'])['outcome'],'collected_pending_review')
        self.assertEqual(load_json(final['path'])['error'],'commit duplicate conflict')
        self.assertEqual(file_sha(provisional['path']),provisional['sha256'])


    def test_direct_next_context_automatically_reads_model_and_compiler_feedback(self):
        from webcollect.agent_feedback import site_context
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'planning-original.db',cfg,initialize=True)
        jid=ledger.enqueue('task-generation',{'site_uri':'https://example.org/','capability_sha256':'fixture-source'})
        job=ledger.claim('task-generation',job_id=jid)
        original={'specs':{'tasks':[{'steps':[{'control_id':'field','action':'set_value','value':'42'}]}]}}
        ledger.finish(job,result=original)
        with ledger.transaction() as con:
            ledger.event(con,'phase_output',{'job_id':jid,'status':'rejected','identity':'fixture-spec',
                                            'reason':'INSUFFICIENT: readable label missing'})
        feedback=site_context(None,'https://example.org/',model_ledger=ledger)
        self.assertEqual(feedback['generation'][0]['model_response'],original)
        self.assertEqual(feedback['generation'][0]['compilation'][0]['reason'],'INSUFFICIENT: readable label missing')
