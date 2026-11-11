"""V12 wire/host boundary fixtures; included in the single integration run."""
from copy import deepcopy
import unittest
from jsonschema import Draft202012Validator, ValidationError
from webcollect.plan_protocol import PLAN_PROTOCOL
from webcollect.banded_plan import (bind_reply_scope,
    plan_schema,validate_plan,tools)
from webcollect.plan_protocol import WIKI_READING_COMPLETION as WIKI_VERSION
from webcollect.wiki_reading import FIELD,FINISH_WHEN,schema
from webcollect.model_gateway import strict_plan_content
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def step():
    return {'action':'scroll','direction':'down','purpose':'继续读取原目标的下一段正文',
            'expected':{'kind':'scroll_changed'}}


class PlanWireMinimum(unittest.TestCase):
    def prompt(self):
        return {'protocol':PLAN_PROTOCOL,'attempt_id':'a1',FIELD:WIKI_VERSION,
                'session_objective':{'description':'了解原条目的制作情况'},
                'observation':{'observation_id':'o1','rendered_dom':[]}}

    def wire(self,n=5):
        return {'checks':[{'field':'制作情况','page':'https://zh.wikipedia.org/wiki/Test',
                           'evidence_kind':'reading'}],'steps':[step() for _ in range(n)]}

    def host(self,n=5):
        return bind_reply_scope(self.wire(n),self.prompt())

    def test_generate_react_url_and_controller_first_prompt_are_connected(self):
        # Only candidate ledger validation is substituted; use the real task
        # generator, task validators, persisted plan and Controller projection.
        from webcollect.task_generation import _generate_react_url
        from webcollect.banded_plan import Controller
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ledger=SimpleNamespace(config={'mode':'synthetic'},path=root/'ledger.sqlite3',
                                   enqueue=lambda *args:'fixture-job')
            claim={'candidate_id':'candidate-fixture','claim_id':'claim-fixture','version':1,
                   'snapshot':{'schema_version':'webcollect-data-candidate-2',
                               'entry_url':'https://zh.wikipedia.org/wiki/Test'}}
            from webcollect.agent_controller import exclusive
            claim_ref=exclusive(root/'claim.json',claim)
            state_ref=exclusive(root/'first-state.json',{'elements':[],'capture_controls':[]})
            with patch('webcollect.candidate_contract.validate_task_binding'):
                result=_generate_react_url(ledger,root/'generation',url=claim['snapshot']['entry_url'],
                    react_candidate={'claim':claim,'claim_reference':claim_ref})
            task=result['generated_task_details'][0]
            self.assertEqual(task['fragment']['plan_protocol'],PLAN_PROTOCOL)
            self.assertEqual(task['fragment'][FIELD],WIKI_VERSION)
            controller=Controller()
            session=SimpleNamespace(task=task,plan_controller=controller,root=root,attempt_id='a1',
                current={'observation_id':'o1','url':task['initial_url'],'document_identity':{'nonce':'first'},
                         'evidence':{'image':{'path':str(root/'first.png')},'state':state_ref},'controls':{},'visible_text':''},
                requested_goal=None,trajectory=[],context={},actual_dispatches=0,
                used={'max_decisions':0},page_urls=[task['initial_url']],event=lambda *args,**kwargs:None)
            with patch('webcollect.inference_image.derive',return_value={'path':str(root/'inference.jpg')}), \
                 patch('webcollect.banded_plan.initial_projection',return_value=([],{})):
                prompt=controller.prompt(session)
            contract=prompt['tools'][0]['function']['parameters']
            wire={**self.wire(),'goal':'阅读当前词条的制作情况',
                  'steps':[{**step(),'rationale':'原目标需要继续阅读下一段正文',
                            'expected_result':'视口移动并显示下一段正文'} for _ in range(5)]}
            Draft202012Validator(contract).validate(wire)
            self.assertEqual(contract['properties']['steps']['minItems'],5)
            self.assertNotIn('必须填写本请求的attempt_id',prompt['system'])
            bound=bind_reply_scope(wire,prompt)
            self.assertEqual(bound['attempt_id'],'a1')
            validate_plan(bound,'a1','o1',task['fragment']['allowed_actions'],pending_checks=True,
                direct_completion=True,wiki=True,max_steps=10,ordinary_minimum=True,extended_actions=True)

    def test_qc_handoff_forwards_explicit_delivery_policy_and_preserves_legacy_call(self):
        from webcollect.task_generation import _prepare_qc_handoff
        from webcollect.closing_policy import COMPLETED_GOAL_DELIVERY
        sampling={'ai_percent':100,'human_percent':0,'seed':'fixture'}
        with patch('webcollect.qc_handoff.prepare_qc_inputs',return_value={'status':'frozen'}) as prepare:
            _prepare_qc_handoff('/candidate','/history','/qc',sampling,{'path':'checks'},
                                delivery_policy=COMPLETED_GOAL_DELIVERY)
            self.assertEqual(prepare.call_args.kwargs['delivery_policy'],COMPLETED_GOAL_DELIVERY)
            self.assertEqual(prepare.call_args.kwargs['collection_checks'],{'path':'checks'})
            prepare.reset_mock()
            _prepare_qc_handoff('/candidate','/history','/qc',sampling,{'path':'checks'})
            self.assertNotIn('delivery_policy',prepare.call_args.kwargs)

    def test_model_omits_host_fields_and_raw_stays_unchanged(self):
        wire=self.wire();raw=deepcopy(wire)
        bound=bind_reply_scope(wire,self.prompt())
        self.assertEqual(wire,raw)
        self.assertEqual(bound['attempt_id'],'a1')
        self.assertEqual(bound['observation_id'],'o1')
        self.assertEqual(bound['goal'],'了解原条目的制作情况')
        self.assertEqual(bound['finish_when'],FINISH_WHEN)
        self.assertEqual(bound['band'],'five')

    def test_explicit_conflicting_identity_goal_band_or_finish_rejected(self):
        for key,value in [('attempt_id','a2'),('observation_id','o2'),('goal','另一个问题'),
                          ('band','short'),('finish_when',{'kind':'visible_text','text':'完成'})]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                bind_reply_scope({**self.wire(),key:value},self.prompt())

    def test_initial_minimum_is_host_checked_but_one_remaining_step_is_allowed(self):
        for n in (1,4,11):
            with self.subTest(n=n),self.assertRaises((ValueError,ValidationError)):
                validate_plan(self.host(n),'a1','o1',['scroll'],pending_checks=True,
                              direct_completion=True,wiki=True,max_steps=10,ordinary_minimum=True)
        plan=validate_plan(self.host(5),'a1','o1',['scroll'],pending_checks=True,
                           direct_completion=True,wiki=True,max_steps=10,ordinary_minimum=True)
        remaining={**plan,'steps':[step()]}
        self.assertEqual(len(validate_plan(remaining,'a1','o1',['scroll'],remaining=1,
            pending_checks=True,direct_completion=True,wiki=True,max_steps=10,
            ordinary_minimum=True,replanning=True)['steps']),1)

    def test_old_short_plan_still_accepted(self):
        plan=self.host(3)
        self.assertEqual(len(validate_plan(plan,'a1','o1',['scroll'],pending_checks=True,
            direct_completion=True,wiki=True,max_steps=10)['steps']),3)

    def test_strict_content_and_native_schema_use_identical_optional_scope(self):
        declared=schema(tools(wire=True,pending_checks=True,max_steps=10),evidence_ids=True)
        contract=declared[0]['function']['parameters']
        contract['required']=[k for k in contract['required'] if k not in ('band','goal','replan_when')]
        wire=self.wire()
        Draft202012Validator(contract).validate(wire)
        self.assertEqual(strict_plan_content({'content':json.dumps(wire)}, {'submit_plan':contract}),wire)


if __name__=='__main__':unittest.main()
