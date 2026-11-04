"""First-plan shared contract and normal candidate entry; synthetic I/O only."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator
from webcollect.banded_plan import tools,choice_schema,validate_plan,bind_target,initial_projection
from test_banded_plan import BandedSessionTests,plan_for
from test_candidate_entry_engineering import EntryEngineering
from webcollect.batch_core import load_json

class ReferenceTests(BandedSessionTests):
    async def test_current_reference_survives_probe_but_not_document_change(self):
        s,_=self.recorded();await s._observe()
        cid=next(iter(s.current['controls']));text=s.current['controls'][cid]['element']['text']
        target={'text':text,'node':cid,'observation_id':s.current['observation_id']}
        self.assertEqual(bind_target(s.current,target,s.observation_records),[cid])
        old=deepcopy(s.current)
        await s._observe(cid)
        self.assertEqual(bind_target(s.current,target,{old['observation_id']:old}),[cid])
        s.current['document_identity']={'different':'document'}
        self.assertEqual(bind_target(s.current,target,{old['observation_id']:old}),[])

    async def test_expected_click_navigation_continues_next_actual_action_without_model(self):
        destination='https://example.org/next'
        self.surface.state['capture_controls'][0]['href']=destination
        execute=self.surface.execute_action
        def effect(kind,args):
            execute(kind,args)
            if len(self.surface.executed)==1:
                self.surface.state['url']=destination
                self.surface.state['document_identity']={'url_without_fragment':destination,'performance_time_origin':456}
            if len(self.surface.executed)==5:self.surface.state['visible_text']+='\n当前终点内容'
        self.surface.execute_action=effect
        s,_=self.recorded(mark_endpoint=False)
        async def choose(prompt):
            self.prompts.append(prompt)
            self.assertEqual(len(self.prompts),1)
            p=plan_for(prompt);cid=next(iter(s.current['controls']))
            p['steps'][0]={'action':'click','target':{'text':s.current['controls'][cid]['element']['text'],
                'node':cid,'observation_id':s.current['observation_id']},'purpose':'打开详情',
                'expected':{'kind':'url','text':destination}}
            return {'name':'submit_plan','arguments':p,'tool_call_id':'first'}
        s.choose=choose;r=await s.run()
        self.assertEqual(r['effective_steps'],5,r)
        self.assertEqual([a['action'] for a in s.trajectory],['click','scroll','scroll','scroll','scroll'])
        self.assertEqual(len(self.prompts),1)
        self.assertTrue(list(s.root.glob('*host-expected-navigation.json')))

    async def test_missing_target_exposes_current_candidates_and_explicit_stop(self):
        s,_=self.recorded();calls=[]
        async def choose(prompt):
            calls.append(prompt)
            if len(calls)==1:
                p=plan_for(prompt);p['steps'][0]={'action':'click','target':{'text':'不存在'},'purpose':'查找','expected':{'kind':'visible_text','text':'结果'}}
                return {'name':'submit_plan','arguments':p,'tool_call_id':'first'}
            self.assertIn('stop',[x['choice'] for x in prompt['options']])
            self.assertTrue(prompt['observation']['rendered_dom'])
            return {'attempt_id':prompt['attempt_id'],'observation_id':prompt['observation']['observation_id'],'choice':'stop'}
        s.choose=choose;r=await s.run();self.assertEqual(r['actual_actions'],0)
        self.assertEqual(len(calls),2)

class SharedContract(unittest.TestCase):
    def test_initial_replan_and_host_use_identical_action_endpoint_contract(self):
        p=plan_for({'attempt_id':'a','observation':{'observation_id':'o'}})
        schema=tools()[0]['function']['parameters']
        self.assertEqual(schema,choice_schema()['properties']['plan'])
        for bad in ('extra','endpoint','reference'):
            q=deepcopy(p)
            if bad=='extra':q['steps'][0]['page_id']='p0'
            if bad=='endpoint':q['finish_when']['kind']='scroll_changed'
            if bad=='reference':q['steps'][0]={'action':'click','target':{'text':'标题','node':'e1'},'purpose':'阅读','expected':{'kind':'visible_text','text':'正文'}}
            self.assertTrue(list(Draft202012Validator(schema).iter_errors(q)))
            with self.assertRaises(Exception):validate_plan(q,'a','o',['scroll','click'])

class NormalEntry(EntryEngineering):
    async def test_normal_python_entry_first_page_full_plan_atomic_actions_and_save(self):
        from webcollect.model_gateway import ModelGateway
        async def invoke():
            from webcollect.candidate_consumer import consume
            return await consume(self.pool,self.claim,self.ledger,output=self.output,registry=self.registry,
                                 policy=self.policy_path,history_set=self.chain)
        def call(gateway,job,purpose,prompt,tools,**kwargs):
            p=json.loads(prompt);self.prompts.append(p)
            self.assertEqual(len(self.prompts),1)
            self.assertEqual(p['phase'],'first');self.assertTrue(p['observation']['rendered_dom'])
            self.assertIsNone(p['requested_goal'])
            plan=plan_for(p)
            # A deterministic synthetic scroll reveals a genuinely new viewport
            # each time. Final endpoint is introduced only by the fifth action.
            return {'name':'submit_plan','arguments':plan,'tool_call_id':'controlled-first'}
        execute=self.surface.execute_action
        def effect(kind,args):
            execute(kind,args)
            if len(self.surface.executed)==5:self.surface.state['visible_text']+='\n当前终点内容'
        self.surface.execute_action=effect
        with self.io_boundaries(mock_gateway=False,legacy_protocol=False),patch.object(ModelGateway,'call_tool',call):
            r=await invoke()
        self.assertEqual(r['state'],'succeeded',r)
        self.assertEqual(len(self.gotos),1);self.assertEqual(len(self.contexts),1)
        self.assertEqual(len(self.prompts),1)
        terminal=load_json(next(self.output.rglob('terminal.json')))
        self.assertEqual(terminal['effective_steps'],5)
        self.assertTrue(list(self.output.rglob('saved_sample.json')))


def load_tests(loader, tests, pattern):
    suite=unittest.TestSuite()
    for cls in (ReferenceTests,SharedContract,NormalEntry):
        for name in cls.__dict__:
            if name.startswith('test_'):suite.addTest(cls(name))
    return suite
