"""P0 contracts using disposable evidence, local HTML and simulated providers only."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from webcollect.batch_core import BatchLedger, load_json, save_json, file_sha
from webcollect.workflow_normalization import VERSION, SCHEMA, normalize, prompt_for, assert_initial_state
from webcollect.workflow_proposal import compile_workflow, verify_task
from test_planner_repair import SemanticFixture


class P0Fixture(SemanticFixture):
    def proposal(self):
        self.case_number = getattr(self, 'case_number', 0) + 1
        self.fixture.root = self.root / f'case-{self.case_number}'
        self.fixture.root.mkdir()
        record, spec = self.semantic()
        anchor = record['capabilities'][0]['page_anchor']; state = load_json(anchor['state']['path'])
        # One necessary nonempty input, two changed choices, one satisfied precision.
        state['elements'] = [state['elements'][0], state['elements'][2]]
        state['capture_controls'] = [state['capture_controls'][0], state['capture_controls'][2]]
        state['values'] = [state['values'][0]]
        for n in range(3):
            eid = f'choice-{n}'
            state['elements'].append({'element_id':eid,'text':['来源单位','目标单位','精度'][n],
                'visible':True,'enabled':True,'clickable':True,'inputable':False,'bbox':[10,200+n*40,200,230+n*40]})
            state['capture_controls'].append({'element_id':eid,'selector':'#'+eid,'index':0,'tag':'select',
                'options':[{'value':'a','label':'初值','disabled':False},{'value':'b','label':'目标值','disabled':False}]})
            state['values'].append({'element_id':eid,'value':'a','focused':False,'readonly':False})
        Path(anchor['state']['path']).write_text(json.dumps(state)); anchor['state']['sha256']=file_sha(anchor['state']['path'])
        record['supported_actions'].append('select')
        spec.update(schema_version=VERSION, conditions=[{k:v for k,v in spec['steps'][0].items() if k!='action'}], steps=[])
        spec['conditions'] += [{'control_id':f'p0/choice-{n}','value':'b' if n<2 else 'a',
            'necessity':'设定业务要求的单位或精度','expected':'显示所需条件'} for n in range(3)]
        return record,spec

    def state(self, record, mutate):
        anchor=record['capabilities'][0]['page_anchor']; state=load_json(anchor['state']['path'])
        mutate(state);Path(anchor['state']['path']).write_text(json.dumps(state));anchor['state']['sha256']=file_sha(anchor['state']['path'])


class NormalizedPlans(P0Fixture,unittest.TestCase):
    def test_five_necessary_actions_satisfied_precision_and_frozen_report(self):
        record,spec=self.proposal();original=deepcopy(spec)
        task=compile_workflow(record,spec,'fixture');verify_task(task,record)
        self.assertEqual([o['action_type'] for o in task['operations']],['click','hotkey','type','select','select'])
        self.assertEqual([o['arguments']['option'] for o in task['operations'] if o['action_type']=='select'],['目标值']*2)
        self.assertEqual([o['postconditions'][0]['value'] for o in task['operations'] if o['action_type']=='select'],['b']*2)
        report=task['workflow_proposal']['normalization']
        self.assertEqual(report['effective_steps'],5)
        self.assertEqual(report['conditions'][-1]['status'],'ALREADY_SATISFIED')
        self.assertEqual(len(task['initial_preconditions']),4)
        self.assertEqual(spec,original)
        task['initial_preconditions'][-1]['value']='b'
        with self.assertRaises(ValueError):verify_task(task,record)

    def test_focus_empty_unknown_and_step_boundaries(self):
        for initial, focused, count in [('10',False,5),('10',True,4),('',False,4),('',True,3)]:
            record,spec=self.proposal()
            self.state(record,lambda s:s['values'][0].update(value=initial,focused=focused))
            _,report=normalize(record,spec)
            self.assertEqual(report['effective_steps'],count)
            self.assertEqual(any(i['code']=='INSUFFICIENT_EFFECTIVE_STEPS' for i in report['issues']),count<5)
        record,spec=self.proposal();self.state(record,lambda s:s['values'][0].pop('value'))
        with self.assertRaises(ValueError):compile_workflow(record,spec,'fixture')
        record,spec=self.proposal();spec['conditions'][1]['value']='invented'
        with self.assertRaises(ValueError):compile_workflow(record,spec,'fixture')
        record,spec=self.proposal()
        spec['conditions'] += [dict(spec['conditions'][0],control_id=f'p0/extra-{n}') for n in range(2)]
        def add_inputs(state):
            for n in range(2):
                eid=f'extra-{n}'
                state['elements'].append(dict(state['elements'][0],element_id=eid))
                state['capture_controls'].append(dict(state['capture_controls'][0],element_id=eid,selector='#'+eid))
                state['values'].append(dict(state['values'][0],element_id=eid))
        self.state(record,add_inputs)
        _,report=normalize(record,spec)
        self.assertEqual(report['effective_steps'],11)
        self.assertIn('TOO_MANY_EFFECTIVE_STEPS',{i['code'] for i in report['issues']})

    def test_all_known_issues_and_satisfied_info_are_returned_together(self):
        record,spec=self.proposal();record['supported_actions'].remove('select')
        spec['conditions'][0]['control_id']='unobserved'
        spec['final_requirements'][0]['control_id']='p0/choice-2'
        with self.assertRaises(ValueError) as caught:compile_workflow(record,spec,'fixture')
        codes={i['code'] for i in caught.exception.report['issues']}
        self.assertTrue({'ACTION_CONTRACT_MISMATCH','UNOBSERVED_TARGET','ALREADY_SATISFIED',
                         'INSUFFICIENT_EFFECTIVE_STEPS','MISSING_TERMINAL_EVIDENCE'}<=codes,codes)

    def test_prompt_has_initial_focus_options_cost_and_result_evidence(self):
        record,_=self.proposal();prompt=prompt_for(record)
        controls={r['control_id']:r for r in prompt['controls']}
        self.assertEqual(controls['p0/control-0']['action_cost']['change_value'],3)
        self.assertEqual(controls['p0/choice-0']['allowed_actions'],['click','select'])
        self.assertEqual(controls['p0/choice-0']['dom']['options'][1]['label'],'目标值')
        self.assertEqual(prompt['result_candidates'],['p0/control-2'])

    def test_contract_mismatch_stops_before_request_job_freeze_and_number(self):
        from webcollect.task_generation import generate
        from test_s0_task_generation import catalog
        record,_=self.proposal();record['supported_actions']=['scroll']
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'preflight',cfg,initialize=True)
        with patch('webcollect.model_gateway.ModelGateway',side_effect=AssertionError('No provider/credential access allowed')):
            result=generate(ledger,catalog(self.root/'catalog',[record]),self.root/'out',generator='workflow-model')
        self.assertEqual(result['generated_tasks'],0);self.assertEqual(result['sample_ids_allocated'],0)
        self.assertIsNone(result['plan_file']);self.assertEqual(ledger.summary()['model_requests'],0)
        with ledger.connect() as con:self.assertEqual(con.execute('select count(*) from jobs').fetchone()[0],0)
        self.assertGreater(len(result['rejected'][0]['diagnostics']['issues']),2)

    def test_readonly_disabled_unobserved_options_and_input_types_refuse_writes(self):
        for mutate in (lambda s:s['values'][0].update(readonly=True),
                       lambda s:s['elements'][0].update(enabled=False),
                       lambda s:s['capture_controls'][0].update(input_type='date'),
                       lambda s:s['capture_controls'][2]['options'][1].update(disabled=True),
                       lambda s:s['capture_controls'][2]['options'][1].update(label='初值')):
            record,spec=self.proposal();self.state(record,mutate)
            with self.assertRaises(ValueError):compile_workflow(record,spec,'fixture')

    def test_unknown_request_is_never_reissued_by_same_generation_resume(self):
        from webcollect.task_generation import generate
        from webcollect.batch_core import OutcomeUnknown
        from test_s0_task_generation import catalog
        record,_=self.proposal();cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'unknown',cfg,initialize=True);source=catalog(self.root/'catalog',[record])
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=OutcomeUnknown('Controlled unknown')) as call:
            for _ in range(2):
                result=generate(ledger,source,self.root/'out',generator='workflow-model')
                self.assertEqual(result['generated_tasks'],0)
                self.assertEqual(result['pending'][0]['state'],'review_required')
        self.assertEqual(call.call_count,1)

    def test_new_empty_response_reason_and_unknown_legacy_are_preserved_on_resume(self):
        from webcollect.task_generation import generate
        from test_s0_task_generation import catalog
        from jsonschema import Draft202012Validator
        self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors({'tasks':[],'empty_reasons':[]})))
        record,_=self.proposal();cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        for n,response in enumerate(({'tasks':[],'empty_reasons':[{'code':'NO_CANDIDATE_FOUND',
                'reason':'This observation did not yield a candidate','control_ids':['p0/control-0'],'step_indices':[]}]},{'tasks':[]})):
            ledger=BatchLedger(self.root/f'empty-{n}',cfg,initialize=True)
            source=catalog(self.root/f'catalog-{n}',[record])
            with patch('webcollect.model_gateway.ModelGateway.call',return_value=response) as call:
                first=generate(ledger,source,self.root/f'out-{n}',generator='workflow-model')
                again=generate(ledger,source,self.root/f'out-{n}',generator='workflow-model')
            self.assertEqual(call.call_count,1);self.assertEqual(first,again)
            self.assertEqual(first['empty_results'][0]['reasons'][0]['code'],'NO_CANDIDATE_FOUND' if n==0 else 'UNKNOWN')
            self.assertEqual(first['generated_tasks'],0)
        from webcollect.workflow_normalization import empty_reason_report
        result=empty_reason_report(record,{'empty_reasons':[{'code':'INSUFFICIENT_EFFECTIVE_STEPS',
            'reason':'Model claims too few actions without supplying a specification',
            'control_ids':['p0/control-0'],'step_indices':[]}]})
        self.assertEqual(result[0]['code'],'UNKNOWN')
        self.assertEqual(result[0]['reported_reason']['code'],'INSUFFICIENT_EFFECTIVE_STEPS')


class InitialAssertionTests(P0Fixture,unittest.IsolatedAsyncioTestCase):
    async def test_changed_frozen_initial_state_refuses_without_actions(self):
        record,spec=self.proposal();task=compile_workflow(record,spec,'fixture')
        page=MagicMock();page.evaluate=AsyncMock(return_value={'focus':True,'conditions':[True,True,True,False]})
        with self.assertRaisesRegex(ValueError,'initial precondition changed'):await assert_initial_state(page,task)
        page.evaluate.return_value={'focus':True,'conditions':[True]*4}
        self.assertEqual((await assert_initial_state(page,task))['status'],'PASS')

    async def test_collector_checks_before_any_preparation_or_execution(self):
        from test_single_execution_path import SingleCollectionTests
        from webcollect.collect import collect_one
        fixture=SingleCollectionTests();fixture._asyncioRunner=self._asyncioRunner
        await fixture.asyncSetUp();self.addCleanup(fixture.doCleanups)
        fixture.prepared();task=deepcopy(fixture.plan['tasks'][0])
        with patch('webcollect.workflow_normalization.assert_initial_state',AsyncMock(side_effect=ValueError('initial precondition changed'))) as guard, \
             patch('webcollect.collect.assess_content',AsyncMock(side_effect=AssertionError('No preparation'))) as preparation:
            with self.assertRaisesRegex(ValueError,'initial precondition changed'):
                await collect_one(fixture.context,task,self.root/'sample',self.root/'raw',{'sample_id':'CONTROLLED'})
        self.assertEqual(guard.await_count,1);self.assertEqual(preparation.await_count,0);self.assertEqual(fixture.actions,[])


class NativeNoForm(unittest.IsolatedAsyncioTestCase):
    async def test_observed_no_form_inventory_compiles_and_executes_native_select(self):
        import tempfile
        from playwright.async_api import async_playwright
        from webcollect.browser import capture,execute,prepare_action
        from site_planner.pipeline import inventory_support
        with tempfile.TemporaryDirectory() as tmp:
            async with async_playwright() as runtime:
                browser=await runtime.chromium.launch(channel='chrome',headless=True)
                context=await browser.new_context(viewport={'width':800,'height':600},service_workers='block')
                await context.route('**/*',lambda route:route.abort())
                page=await context.new_page()
                try:
                    await page.set_content('''<!doctype html><meta charset="utf-8"><style>body{font:18px Arial}input,select{width:150px;height:32px;display:block}</style>
                    <label>数量<input id="amount" value="10"></label>
                    <label>来源单位<select id="from"><option value="a">初值</option><option value="b">米</option></select></label>
                    <label>目标单位<select id="to"><option value="a">初值</option><option value="b">厘米</option></select></label>
                    <label>精度<select id="precision"><option value="a">整数</option><option value="b">小数</option></select></label>
                    <input readonly value="只读"><input disabled value="禁用"><p id="result">结果区域</p>
                    <script>document.querySelector('#to').onchange=()=>document.querySelector('#result').textContent='结果42';</script>''')
                    frame=await capture(page)
                    state=frame['state']; uri='https://example.org/'
                    state['url']=uri
                    inventory=dict(state,page_uri=uri,forms=[],widgets=[],title='受控无form工具')
                    _,forms,actions=inventory_support(uri,[inventory])
                    self.assertEqual(forms,[]);self.assertTrue({'click','type','hotkey','select'}<=set(actions))
                    root=Path(tmp);anchor={}
                    for key in ('image','state','capture'):
                        path=root/key
                        if key=='image':path.write_bytes(frame['png'])
                        else:save_json(path,state if key=='state' else frame['capture'])
                        anchor[key]={'path':str(path),'sha256':file_sha(path)}
                    cap={'capability_id':'native-fixture','version':'fixture','site_uri':uri,'site_category':'工具',
                         'mode':'synthetic','task_families':['navigation-reading'],'supported_actions':actions,
                         'capabilities':[dict(inventory,page_anchor=anchor)]}
                    bindings=state['capture_controls']
                    async def find_id(dom_id):
                        # Resolve by native value/tag and original geometric row.
                        box=await page.locator('#'+dom_id).bounding_box()
                        row=next(e for e in state['elements'] if e['bbox'][0]==box['x'] and e['bbox'][1]==box['y'] and
                                 e.get('element_type') in ('input','select','text','paragraph','p'))
                        return 'p0/'+row['element_id']
                    ids={key:await find_id(key) for key in ('amount','from','to','precision','result')}
                    condition=lambda key,value:{'control_id':ids[key],'value':value,'necessity':'设定业务必要条件','expected':'显示所需条件'}
                    spec={'schema_version':VERSION,'task_family':'navigation-reading',
                          'instruction':'在「受控无form工具」填写数量并选择来源单位和目标单位，核对换算结果。','task_type':['填写表单','数据查看'],
                          'conditions':[condition('amount','20'),condition('from','b'),condition('to','b'),condition('precision','a')],
                          'steps':[],'final_requirements':[{'control_id':ids['result'],'kind':'contains','expected':'结果42'}],
                          'final_result':'显示结果42','completion_judgement':'核对结果42。'}
                    task=compile_workflow(cap,spec,'fixture')
                    from webcollect.task_contract import validate_m4_task
                    validate_m4_task(task)
                    await assert_initial_state(page,task)
                    for op in task['operations']:
                        current=await capture(page,op.get('selector'),op.get('index',0))
                        args,_=prepare_action(current['state'],op)
                        await execute(page,op['action_type'],args,op.get('execution'))
                    self.assertEqual(await page.locator('#amount').input_value(),'20')
                    self.assertEqual(await page.locator('#to').input_value(),'b')
                    self.assertEqual(await page.locator('#precision').input_value(),'a')
                    self.assertEqual(await page.locator('#result').inner_text(),'结果42')
                finally:
                    await context.close();await browser.close()
