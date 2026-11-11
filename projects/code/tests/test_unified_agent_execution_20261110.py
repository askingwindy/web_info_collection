"""Focused unified protocol/evidence regressions; no live browser/model/ledger."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from webcollect.banded_plan import Controller, choice_schema, strip_v13_wire
from webcollect.batch_core import file_sha
from webcollect.numeric_result_evidence import process_result_text, substantive_result_text
from webcollect.wiki_reading import schema as wiki_schema


def test_wiki_recursive_schema_retains_conditional_fragments_without_items():
    wire=strip_v13_wire(wiki_schema(choice_schema(inherited=True,wire=True,max_steps=None),
                                   max_steps=None,evidence_ids=True),wiki=True)
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(wire)
    conditional={'properties':{'required_step_indices':{'maxItems':0}}}
    assert strip_v13_wire(conditional,wiki=True)==conditional


def test_first_path_prefers_five_eight_without_schema_upper_cap():
    wire=strip_v13_wire({'properties':{'goal':{},'steps':{'type':'array','maxItems':10}}},initial_complete=True)
    assert wire['properties']['steps']['minItems']==5
    assert 'maxItems' not in wire['properties']['steps']


def test_attempt_feedback_reads_sealed_event_and_rejects_drift():
    with TemporaryDirectory() as root:
        path=Path(root)/'event.json'
        path.write_text(json.dumps({'kind':'business-attempt','number':3,'outcome':'KNOWN_NO_EFFECT',
            'step':{'action':'click','control_id':'e_4'},'actual_dispatches_delta':1,
            'effective_steps_delta':0,'reason':'unchanged result'}))
        ref={'path':str(path),'sha256':file_sha(path)}
        session=SimpleNamespace(business_attempt_refs=[ref])
        fact=Controller()._attempt_facts(session)[0]
        assert fact['number']==3 and fact['dispatched'] and not fact['effective']
        assert fact['reason']=='unchanged result'
        path.write_text('{}')
        import pytest
        with pytest.raises(ValueError):Controller()._attempt_facts(session)


def test_pending_submit_offers_original_followup_without_repeating_submit():
    controller=Controller()
    controller.plan={'steps':[{'action':'click'},{'action':'scroll'},{'action':'wait'}]}
    controller.pending_effect={'position':0,'predicate':{'kind':'visible_text','text':'answer'}}
    option=controller.pending_followup_options()[0]
    assert option['choice']=='continue' and option['observe_after_pending']
    controller.plan['steps'][1]={'action':'click'}
    assert not controller.pending_followup_options()


def test_process_answer_requires_actual_steps_and_result_labels_are_not_answers():
    assert process_result_text('4x + 7 = 11 | Subtract 7: 4x = 4.0000 | Divide by 4: x = 1.0000','逐步求解过程')
    assert not process_result_text('方程求解器提供逐步过程','逐步求解过程')
    assert not substantive_result_text('利润率：',field='利润率计算结果')
    assert not substantive_result_text('2027',field='2027')
    assert substantive_result_text('利润率：40%',field='利润率计算结果')


# Use the actual ReactSession/controller and capture/dispatch evidence writer.
import unittest
from copy import deepcopy
from test_react_session import ReactHarness
import test_complete_goal_v6_20261110 as complete_goal_fixture
from webcollect.react_session import build_url_task
from webcollect.banded_plan import V13_VERSION
from webcollect.closing_policy import COMPLETE_VERSION


class UnifiedAgentExecutionSessionTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.task=build_url_task(url=self.page.url,task_version='unified-execution-fixture',
            ending_policy=COMPLETE_VERSION,plan_protocol=V13_VERSION)
        import os
        if os.environ.get('WEBCOLLECT_AGENT_FIXTURE_ROOT'):
            self.root=Path(os.environ['WEBCOLLECT_AGENT_FIXTURE_ROOT']);self.root.mkdir(parents=True,exist_ok=True)
        self.ids={'sample_id':'S000001_sample_000001'}

    async def test_known_no_effect_step_executes_original_followup(self):
        session,_=complete_goal_fixture.CompleteGoalV6SessionTests.recorded(self,5,trailing_wait=True)
        self.surface.state['elements'].append({'element_id':'noop-submit','text':'计算','native_role':'button',
            'element_type':'button','bbox':[10,200,210,240],'visible':True,'enabled':True,
            'clickable':True,'inputable':False,'parent_id':'root','scrollable':False,'state':'default'})
        self.surface.state['capture_controls'].append({'element_id':'noop-submit','selector':'#noop-submit',
            'tag':'button','input_type':'submit','form_selector':'#calculator'})
        choose=session.choose
        decisions=[]
        async def followup(prompt):
            if prompt.get('phase')=='first':
                response=await choose(prompt)
                response['arguments']['steps'][0]={'action':'click','target':{'text':'计算'},
                    'purpose':'提交本次输入','expected':{'kind':'visible_text','text':'结果等待后可见'},
                    'rationale':'原目标需要实际提交，然后继续滚动观察结果。',
                    'expected_result':'提交后结果将由后续观察核对。'}
                return response
            decisions.append(deepcopy(prompt))
            options=prompt.get('options',[])
            choice='continue' if any(o.get('observe_after_pending') for o in options) else 'stop'
            return {'choice':choice,'decision_summary':'继续原计划取结果' if choice=='continue' else '如实结束'}
        session.choose=followup
        await session.run()
        assert decisions and any(any(o.get('observe_after_pending') for o in p.get('options',[])) for p in decisions)
        assert len(session.trajectory)==4
        assert all(row['action']=='scroll' for row in session.trajectory)
        attempts=[json.loads(Path(ref['path']).read_text()) for ref in session.business_attempt_refs]
        assert attempts[0]['outcome']=='KNOWN_NO_EFFECT'
        assert attempts[0]['effective_steps_delta']==0
        assert any(row.get('effective_steps_delta')==1 for row in attempts[1:])

    async def test_result_application_maps_original_check_and_replays_into_annotation(self):
        from webcollect.react_session import ReactSession
        from webcollect.batch_core import object_sha256
        from webcollect.postprocess import process
        task=deepcopy(self.task)
        for part in (task['fragment'],task['workflow_proposal']['spec']):
            part['result_execution_policy']='webcollect-result-execution-1'
            part['result_completion_protocol']='webcollect-result-completion-1'
            part['numeric_result_evidence_policy']='webcollect-numeric-result-evidence-1'
        task['task_id']='react-'+object_sha256({'url':task['initial_url'],'spec':task['workflow_proposal']['spec']})[:24]
        state=self.surface.state
        state['elements'][0]['text']='数量'
        state['elements'][1]['text']='成本'
        for binding in state['capture_controls']:binding['form_selector']='#calculator'
        state['elements'].append({'element_id':'submit-result','text':'计算','native_role':'button',
            'element_type':'button','bbox':[10,200,210,240],'visible':True,'enabled':True,
            'clickable':True,'inputable':False,'parent_id':'root','scrollable':False,'state':'default'})
        state['capture_controls'].append({'element_id':'submit-result','selector':'#submit-result',
            'tag':'button','input_type':'submit','form_selector':'#calculator'})
        result=state['elements'][-2]
        result['text']='结果尚未生成'
        result['native_role']='status'
        result_binding=next(b for b in state['capture_controls'] if b['element_id']==result['element_id'])
        result_binding.update(selector='#actual-result',tag='p',form_selector='#calculator',result_region_selector='#actual-result')
        execute=self.surface.execute_action
        def calculate(action,args):
            execute(action,args)
            if action=='click' and args.get('y',0)>=200:
                result['text']='利润率：40%'
        self.surface.execute_action=calculate
        prompts=[]
        async def choose(prompt):
            prompts.append(deepcopy(prompt))
            if prompt.get('phase')=='first':
                steps=[
                    {'action':'click','target':{'text':'数量'},'expected':{'kind':'focused','text':'数量'}},
                    {'action':'hotkey','keys':['ctrl','a'],'expected':{'kind':'text_selected','text':state['values'][0]['value']}},
                    {'action':'type','target':{'text':'数量'},'value':'20','expected':{'kind':'value','text':'20'}},
                    {'action':'click','target':{'text':'成本'},'expected':{'kind':'focused','text':'成本'}},
                    {'action':'hotkey','keys':['ctrl','a'],'expected':{'kind':'text_selected','text':state['values'][1]['value']}},
                    {'action':'type','target':{'text':'成本'},'value':'60','expected':{'kind':'value','text':'60'}},
                    {'action':'click','target':{'text':'计算'},'expected':{'kind':'visible_text','text':'利润率：'}},
                    {'action':'scroll','direction':'down','expected':{'kind':'scroll_changed','text':'滚动后位置改变'}}]
                for step in steps:
                    step.update(purpose='完成输入并读取本次实际利润率',rationale='原目标要求本次输入的利润率，按已见页面操作并读取结果。',
                                expected_result='当前操作得到可见反馈，后续读取本次提交的利润率结果。')
                return {'name':'submit_plan','arguments':{'goal':'修改数量为20、成本为60，提交计算并阅读利润率结果',
                    'checks':[{'field':'利润率计算结果','page':'p0'}], 'steps':steps,
                    'finish_when':{'kind':'visible_text','text':'利润率：'}},
                    'tool_call_id':'result-first','assistant_message':{'role':'assistant','tool_calls':[]}}
            catalog=prompt.get('result_evidence_catalog',[])
            if any(o['choice']=='finish_result' for o in prompt.get('options',[])):
                source=next(row for row in catalog if row['quote']=='利润率：40%')
                return {'choice':'finish_result','result_answer':{'check_answers':[{'check_index':0,'evidence_ids':[source['evidence_id']]}]}}
            return {'choice':'continue'}
        ids={'sample_id':'S000001_sample_000001','site_id':'S000001','batch_id':'B20261110_001','attempt_id':'unified-result-offline'}
        evidence=self.root/'result-completion'/'evidence'/ids['sample_id']
        session=ReactSession(task,evidence/'raw',choose,self.page,steps_directory=evidence,attempt_id=ids['attempt_id'])
        await session.run()
        assert session.stop_reason=='ready', session.stop_summary
        assert len(session.trajectory)>=5
        assert session.goal_evidence['business_goal_status']=='VERIFIED'
        assert session.goal_evidence['result_completion']==session.result_completion
        manifest={'batch_id':ids['batch_id'],'sample_kind':'real','program_version':'CONTROLLED','rule_version':'1.0.0',
            'sites':[{'site_id':ids['site_id'],'uri':self.page.url,'site_category':task['site_category']}],'samples':[ids['sample_id']]}
        destination=self.root/'result-derived'/'samples'/ids['sample_id']
        processed=process(evidence,destination,ids,manifest)
        (self.root/'result-processing-outcome.json').write_text(json.dumps(processed,ensure_ascii=False,indent=2))
        assert processed.get('status')=='derived_saved', processed
        annotation=json.loads((destination/'annotation.json').read_text())
        assert annotation['completion_status']=='success'
        assert '40%' in annotation['final_result']
