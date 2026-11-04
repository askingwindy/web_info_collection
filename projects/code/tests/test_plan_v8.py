"""V8 scope, continuation and inherited remainder; disposable synthetic evidence."""
from copy import deepcopy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from jsonschema import Draft202012Validator
from webcollect.banded_plan import (VERSION, V7_VERSION, Controller, bind_target,
    choice_schema, initial_projection, validate_plan, system_for)
from webcollect.agent_controller import exclusive
from webcollect.session_objective import bind
from test_contracted_goal import ContractedGoal
from test_banded_plan import BandedSessionTests, plan_for
from test_consumer_page_policy import BoundarySessionTests


class Grounding(ContractedGoal):
    def test_extra_prose_only_relaxes_unique_proven_reference(self):
        ob=self.view('frame','form',[('q','input','站内搜索','',None)])
        ob['controls']['q']['actions']={'click':{'status':'PROVEN'}}
        target=dict(node='q',observation_id='frame',text='站内搜索',region='顶部搜索框',parent_text='猜测父文案')
        self.assertEqual(bind_target(ob,target),[])
        self.assertEqual(bind_target(ob,target,advisory=True),['q'])
        for extra in ({'region':'左栏菜单'},{'region':'右侧搜索框'},{'role':'button'},
                      {'href':'https://test.invalid/wrong'},{'observation_id':'stale'}):
            self.assertEqual(bind_target(ob,{**target,**extra},advisory=True),[])
        ob['controls']['same']=deepcopy(ob['controls']['q'])
        self.assertEqual(bind_target(ob,target,advisory=True),[])
        ob['controls'].pop('same')
        ob['controls']['q']['binding']['selector']='main > div.advert > input'
        self.assertEqual(bind_target(ob,target,advisory=True),[])
        ob['controls']['q']['binding']['selector']='main > input'
        ob['controls']['q']['actions']={'click':{'status':'UNVERIFIABLE'}}
        self.assertEqual(bind_target(ob,target,advisory=True),[])

    def test_minimum_is_an_integer_compatible_with_frozen_band(self):
        base=dict(schema_version='webcollect-session-objective-1',candidate_id='c',version=1,
            entry_url='https://test.invalid',requested_goal=None)
        claim=dict(candidate_id='c',version=1,snapshot=dict(entry_url=base['entry_url']))
        for i,(band,minimum,ok) in enumerate([('long',6,True),('long',5,True),('long',8,True),
                ('five',5,True),('five',6,False),('long',True,False),('long',9,False),('long',4,False)]):
            ref=exclusive(self.root/f'objective-{i}.json',{**base,'objective':dict(
                description='原任务',minimum_effective_steps=minimum,preferred_band=band)})
            if ok:self.assertEqual(bind(ref,claim)['objective']['minimum_effective_steps'],minimum)
            else:
                with self.assertRaises(ValueError):bind(ref,claim)

    def test_citation_survives_real_later_scroll_only_in_v8_same_document(self):
        self.test_reading_requires_result_lineage_new_passage_and_bound_model_selection()
        steps=[self.operation('o1','type','entry','typed','q','河流'),
               self.operation('submit','click','typed','results','send'),
               self.operation('o2','click','results','land','go'),
               self.operation('o3','scroll','land','new')]
        s=self.session('new',steps)
        s.answer_citation=exclusive(self.root/'selected.json',dict(kind='plan-branch',boundary=self.binding,
            response=dict(choice='cite:p',attempt_id='a',observation_id='new'),provider_reply={'choice':'cite:p'},
            options=[dict(choice='cite:p',passage=__import__('webcollect.goal_evidence',fromlist=['progress']).progress(s,'entry',self.reading)['passages'][0])]))
        later=self.view('later','article',[('p2','p','继续阅读河流动力学的后续正文，不包含原来所引句子。',None,None)],y=800)
        s.current=later;s.trajectory=steps+[self.operation('o4','scroll','new','later')]
        from webcollect.goal_evidence import progress
        s.task={'fragment':{'plan_protocol':VERSION}}
        proof=progress(s,'entry',self.reading)
        self.assertEqual(proof['status'],'VERIFIED')
        self.assertEqual(proof['selected_passage']['observation_id'],'new')
        s.task['fragment']['plan_protocol']=V7_VERSION
        self.assertEqual(progress(s,'entry',self.reading)['status'],'UNVERIFIED')
        s.task['fragment']['plan_protocol']=VERSION
        s.trajectory[-1]['action']='hotkey'
        self.assertEqual(progress(s,'entry',self.reading)['status'],'UNVERIFIED')
        s.trajectory[-1]['action']='scroll'
        s.current={**later,'document_identity':{'document':'other'}}
        self.assertEqual(progress(s,'entry',self.reading)['status'],'UNVERIFIED')


class ControllerTests(BandedSessionTests):
    async def test_boundary_hash_matches_actual_initial_v8_tools_and_system(self):
        from webcollect.batch_core import load_json
        from webcollect.planning import object_sha256
        s,_=self.recorded();await s._observe()
        prompt=s.plan_controller.prompt(s);boundary=load_json(s.binding['path'])
        self.assertEqual(boundary['tool_schema_sha256'],object_sha256(prompt['tools']))
        self.assertEqual(boundary['system_prompt_sha256'],object_sha256(prompt['system']))

    async def test_focus_pinned_in_bounded_request_and_unmodified_reply_dispatches(self):
        s,_=self.recorded();await s._observe()
        cid=next(iter(s.current['controls']))
        s.preflight_search_focus={'node':cid,'label':s.current['controls'][cid]['element']['text']}
        s.task['fragment']['session_objective']={'objective':dict(evidence_contract={'kind':'reading'},minimum_effective_steps=6)}
        prompt=s.plan_controller.prompt(s)
        self.assertEqual(prompt['completion_policy']['minimum_effective_steps'],6)
        self.assertIn(cid,[r['node'] for r in prompt['observation']['rendered_dom']])
        self.assertLessEqual(prompt['observation']['dom_coverage']['serialized_chars'],6500)
        rows,coverage=initial_projection(s.current,limit=700,pinned=[cid])
        self.assertEqual(rows[0]['node'],cid)

    async def test_replan_one_remaining_inherits_long_without_short_reason_or_repeated_fields(self):
        s,_=self.recorded(n=7);await s._observe();c=s.plan_controller
        s.task['fragment']['session_objective']={'objective':dict(evidence_contract={'kind':'calculation'})}
        c.plan=plan_for(c.prompt(s),7);c.submitted=True;c.frozen_plan=deepcopy(c.plan)
        c.frozen_band='long';c.target_steps=8;c.last_document=deepcopy(s.current['document_identity'])
        s.trajectory=[{}]*7
        for partial in (False,True):
            p=plan_for({'attempt_id':s.attempt_id,'observation':{'observation_id':s.current['observation_id']}},1);p.pop('short_reason');p['band_reason']='只剩最后一项真实操作'
            if partial:p={'steps':p['steps']}
            raw={'choice':'replan','plan':p}
            async def choose(prompt):return deepcopy(raw)
            s.choose=choose
            with patch.object(c,'fact_summary',return_value={}):
                await c.request(s,[{'choice':'replan'}])
            self.assertEqual(c.plan['band'],'long');self.assertEqual(len(c.plan['steps']),1)
            self.assertEqual(raw['plan'],p)
        old=plan_for({'attempt_id':s.attempt_id,'observation':{'observation_id':s.current['observation_id']}},1)
        old.pop('short_reason')
        with self.assertRaisesRegex(ValueError,'SHORT_REQUIRES_REASON'):
            validate_plan(old,s.attempt_id,s.current['observation_id'],['scroll'],remaining=1)

    async def test_continuation_requires_preplanned_reading_scroll_below_explicit_minimum(self):
        s,_=self.recorded(n=6);await s._observe();c=s.plan_controller
        s.task['fragment']['session_objective']={'objective':dict(evidence_contract={'kind':'reading'},minimum_effective_steps=6)}
        c.plan=plan_for(c.prompt(s),6);c.position=4;s.trajectory=[{}]*4
        self.assertTrue(c.continue_reading(s))
        c.plan['steps'][4]['action']='hotkey';self.assertFalse(c.continue_reading(s))
        c.plan['steps'][4]['action']='scroll';s.trajectory=[{}]*6;self.assertFalse(c.continue_reading(s))
        s.trajectory=[{}]*4;s.task['fragment']['plan_protocol']=V7_VERSION;self.assertFalse(c.continue_reading(s))


class Schemas(unittest.TestCase):
    def test_partial_remaining_schema_is_versioned(self):
        p={'steps':[{'action':'scroll','direction':'down','purpose':'阅读后续正文','expected':{'kind':'scroll_changed'}}]}
        self.assertTrue(Draft202012Validator(choice_schema(True,inherited=True)).is_valid({'choice':'replan','plan':p}))
        self.assertFalse(Draft202012Validator(choice_schema(True)).is_valid({'choice':'replan','plan':p}))

    def test_pending_goal_checks_from_wire_are_not_observed_facts(self):
        from webcollect.banded_plan import tools,bind_reply_scope
        from webcollect.plan_evidence import facts
        prompt={'attempt_id':'a','observation':{'observation_id':'o','rendered_dom':[]}}
        raw=plan_for(prompt,6)
        raw['checks']=[{'field':'发生条件','purpose':'从真实正文核实位置关系'}]
        raw['finish_when']={'kind':'goal_evidence'}
        Draft202012Validator(tools(True,pending_checks=True)[0]['function']['parameters']).validate(raw)
        with self.assertRaises(Exception):
            Draft202012Validator(tools(True)[0]['function']['parameters']).validate(raw)
        plan=validate_plan(bind_reply_scope(raw,prompt),'a','o',['scroll'],grounded=True,pending_checks=True)
        session=SimpleNamespace(observation_records={},requested_goal='原目标',working_goal='查阅正文',trajectory=[])
        proof=facts(session,plan)
        self.assertEqual(proof['checks'][0]['status'],'PENDING')
        self.assertEqual(proof['verified'],0)


class BoundaryIntegrity(BoundarySessionTests):
    async def test_boundary_marker_cannot_switch_frozen_plan_version(self):
        from webcollect.postprocess import session_record
        from webcollect.closing_policy import validate_record
        s,e,_,_=await self.run_boundary('login')
        record=session_record(e/'raw');validate_record(record)
        record['terminal']['collection_ending']['plan_protocol']=V7_VERSION
        with self.assertRaisesRegex(ValueError,'Boundary return'):
            validate_record(record)


def load_tests(loader, tests, pattern):
    suite=unittest.TestSuite()
    for cls in (Grounding,ControllerTests,Schemas,BoundaryIntegrity):
        for name in cls.__dict__:
            if name.startswith('test_'):suite.addTest(cls(name))
    return suite
