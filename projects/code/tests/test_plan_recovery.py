"""R09 bounded zero-send repair and shared action evidence deadline, offline only."""
import asyncio
from copy import deepcopy
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock,patch
import unittest
from webcollect import collect
from webcollect.agent_controller import compile_step,SelectionValueMismatch
from test_banded_plan import BandedSessionTests,plan_for

class Recovery(BandedSessionTests):
    async def test_numeric_expected_condition_keeps_raw_and_exports_chinese_narrative(self):
        s,e=self.recorded(n=6,bad=lambda p:[step['expected'].update(text='480') for step in p['steps']])
        result=await s.run();self.assertEqual(result['effective_steps'],6)
        self.assertTrue(all(row['expected']=='480' for row in s.trajectory))
        destination,annotation=self.derive(e)
        self.assertEqual(annotation['steps'][0]['action']['expected_result'],'预期状态：「480」')
        self.assertTrue(all(row['expected']=='480' for row in s.trajectory))
    async def test_rejected_host_finish_stops_instead_of_reobserving_forever(self):
        from webcollect.react_session import ReactStop
        s,_=self.recorded();await s._observe();c=s.plan_controller;c.plan=plan_for(c.prompt(s));s.state='recording'
        with patch.object(c,'fact_progress',return_value={}),patch.object(s,'_native_finish',AsyncMock(return_value={'status':'rejected','error':{'message':'empty final frame'}})) as finish:
            with self.assertRaisesRegex(ReactStop,'HOST_PLAN_FINISH_REJECTED'):await c.finish(s,'受控结束测试')
            self.assertEqual(finish.await_count,1)

    async def test_disproven_selection_returns_values_and_preserves_seven_steps(self):
        s,_=self.recorded(n=7);await s._observe();c=s.plan_controller
        cid=next(iter(s.current['controls']));control=s.current['controls'][cid]
        control['actions']['select']={'status':'PROVEN'}
        control['binding']['options']=[{'value':'a','label':'第一种','disabled':False},{'value':'b','label':'第二种','disabled':False}]
        control['value']['value']='a'
        label=control['element']['text'];s.task['fragment']['allowed_actions'].append('select')
        c.plan=plan_for(c.prompt(s),8);c.plan['steps']=[{'action':'select','target':{'text':label},'value':'missing','purpose':'核实单位','expected':{'kind':'selected','text':'missing'}}]
        c.frozen_plan=deepcopy(c.plan);c.submitted=True;c.position=0;c.frozen_band='long';c.target_steps=8;c.last_document=deepcopy(s.current['document_identity'])
        s.trajectory=[{} for _ in range(7)];s.actual_dispatches=7
        async def choose(prompt):
            fb=prompt['options'][0]['compile_feedback'];self.assertFalse(fb['action_dispatched']);self.assertEqual(fb['current_value']['value'],'a')
            self.assertEqual(fb['remaining_effective_limit'],1);self.assertEqual(len(fb['options']),2)
            self.assertTrue(prompt['observation']['rendered_dom'])
            return {'attempt_id':s.attempt_id,'observation_id':s.current['observation_id'],'choice':'replan','plan':{**c.plan,'steps':[{'action':'scroll','direction':'down','purpose':'查看结果区','expected':{'kind':'scroll_changed'}}]}}
        s.choose=choose
        with patch.object(s,'_tool_act',AsyncMock()) as act,patch.object(c,'fact_summary',return_value={}):
            await c.round(s)
        act.assert_not_called();self.assertEqual(s.actual_dispatches,7);self.assertEqual(len(s.trajectory),7)
        self.assertEqual(c.plan['steps'][0]['action'],'scroll');self.assertEqual(c.frozen_band,'long')
        c.plan['steps']=[deepcopy(c.frozen_plan['steps'][0])]
        with self.assertRaisesRegex(ValueError,'PRE_DISPATCH_REPLAN_LIMIT'):await c.round(s)

class EvidenceDeadline(unittest.IsolatedAsyncioTestCase):
    async def test_slow_frame_uses_caller_budget_and_verification_only_remaining(self):
        frame={'state':{},'png':b'x','capture':{}}
        async def slow(*a,**kw):
            self.assertGreater(kw['timeout'],.1);await asyncio.sleep(.04);return frame
        with TemporaryDirectory() as d,patch.object(collect,'capture',side_effect=slow),patch.object(collect,'verify_execution_state',AsyncMock()) as verify:
            result=await collect.capture_before_action(None,d,timeout=.2)
        self.assertTrue(result['action_refresh']['accepted']);self.assertLess(verify.call_args.kwargs['timeout'],.18)
    async def test_capture_and_verify_timeouts_preserve_stage_no_action(self):
        async def stall(*a,**kw):await asyncio.Future()
        for phase in ('capture','verify_execution_state'):
            with TemporaryDirectory() as d,patch.object(collect,'capture',side_effect=stall if phase=='capture' else AsyncMock(return_value={'state':{}})),patch.object(collect,'verify_execution_state',side_effect=stall),patch.object(collect,'execute',AsyncMock()) as execute:
                with self.assertRaises(TimeoutError) as caught:await collect.capture_before_action(None,d,timeout=.02)
                diag=caught.exception.action_refresh;self.assertEqual(diag['stage'],phase);self.assertEqual(diag['error_type'],'TimeoutError');self.assertFalse(diag['action_executed'])
                execute.assert_not_called()

def load_tests(loader,tests,pattern):
    suite=unittest.TestSuite()
    for cls in (Recovery,EvidenceDeadline):
        for name in cls.__dict__:
            if name.startswith('test_'):suite.addTest(cls(name))
    return suite
