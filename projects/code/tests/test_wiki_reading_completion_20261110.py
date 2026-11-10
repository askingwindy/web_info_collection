"""Ordinary Wiki protocol regression fixtures; no live browser/model calls."""
import asyncio
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from jsonschema import Draft202012Validator, ValidationError
from webcollect.agent_controller import exclusive
from webcollect.banded_plan import Controller, plan_schema
from webcollect.plan_evidence import bind_check_pages, page_matches
from webcollect.wiki_reading import VERSION, FIELD, enabled, progress, schema, configure

URL='https://zh.wikipedia.org/wiki/我为喜剧狂_(第1季)'
P1='第一季在纽约拍摄，主角与同事共同制作喜剧节目，故事呈现电视制作过程中的冲突。'
P2='该季随后在电视台播出，评论主要讨论人物互动以及编剧采用的叙事和喜剧风格。'


class WikiReadingCompletion(unittest.TestCase):
    def fixture(self,root,*,check=None,other_url=None,heading_only=False,section='制作',show_second=True):
        check=check or {'field':'了解第一季如何制作','page':'p0','evidence_kind':'reading'}
        plan={'goal':'了解第一季如何制作','observation_id':'start','checks':[check],
              'steps':[{'action':'scroll','direction':'down','purpose':'阅读制作正文','expected':{'kind':'scroll_changed'}}]}
        task={'initial_url':URL,'fragment':{FIELD:VERSION,'plan_execution_policy':'webcollect-plan-execution-1'}}
        observations={}
        html=f'<html><body><main><h1>第一季</h1><h2>{section}</h2><p>{P1}</p><p>{P2}</p></main></body></html>'
        for oid,quote,index in [('start',P1,1),('last',P2 if show_second else P1,2 if show_second else 1)]:
            state={'url':other_url or URL,'document_identity':{'nonce':'article'},'scroll':[0,0 if oid=='start' else 400],
                'elements':[{'element_id':'main','native_role':'main','visible':True,'text':'','bbox':[0,0,800,600]},
                    {'element_id':'paragraph'+str(index),'native_role':'h2' if heading_only else 'p','visible':True,
                     'text':quote,'parent_id':'main','bbox':[20,50,700,250]}],
                'capture_controls':[{'element_id':'paragraph'+str(index),'selector':f'html:nth-of-type(1) > body:nth-of-type(1) > main:nth-of-type(1) > p:nth-of-type({index})'}]}
            observations[oid]={'url':state['url'],'capture_verified':True,'html':html,
                               'evidence':{'state':exclusive(root/(oid+'.json'),state)}}
        binding=bind_check_pages(plan,[{'page_id':'p0','url':URL}])
        row={'operation_id':'op1','action':'scroll','before_observation_id':'start','after_observation_id':'last','target':None}
        session=SimpleNamespace(task=task,plan_controller=SimpleNamespace(frozen_plan=plan,frozen_page_binding=binding),
            observation_records=observations,trajectory=[row],current=observations['last'],unknown=False,
            binding={'attempt':'fixture'},attempt_id='fixture',reading_completion=None)
        answer={'answer':'根据真实制作正文作答','check_answers':[{'check_index':0,'answer':'制作过程说明',
            'passages':[{'observation_id':'start','node':'paragraph1','quote':P1}]}]}
        return session,answer

    def finish(self,root,session,answer):
        reply={'attempt_id':session.attempt_id,'observation_id':'last','choice':'finish_reading','reading_answer':answer}
        session.reading_completion=exclusive(root/'completion.json',{'kind':'plan-branch','boundary':session.binding,
            'response':reply,'provider_reply':deepcopy(reply),'options':[{'choice':'finish_reading'}]})
        return progress(session,'start')

    def test_parenthesized_bound_url_before_embedded_regex(self):
        self.assertTrue(page_matches(URL,{'url':URL}))
        self.assertFalse(page_matches(URL,{'url':URL.replace('第1季','第2季')}))
        self.assertFalse(page_matches(URL,{'url':URL.rstrip(')')}))

    def test_previous_saved_body_can_complete_without_current_reappearance(self):
        with TemporaryDirectory() as d:
            s,a=self.fixture(Path(d));result=self.finish(Path(d),s,a)
            self.assertEqual(result['status'],'VERIFIED')
            self.assertIsNone(result['selected_passage'])
            self.assertEqual(result['completion']['answer']['check_answers'][0]['passages'][0]['observation_id'],'start')
            self.assertEqual(result['completion']['semantic_judgment'],'MODEL_REPORTED_REQUIRES_INDEPENDENT_QC')

    def test_wrong_source_rejected(self):
        with TemporaryDirectory() as d:
            s,a=self.fixture(Path(d),other_url='https://zh.wikipedia.org/wiki/另一个词条')
            with self.assertRaisesRegex(ValueError,'WRONG_SOURCE'):self.finish(Path(d),s,a)

    def test_wrong_section_rejected(self):
        with TemporaryDirectory() as d:
            s,a=self.fixture(Path(d),check={'field':'了解制作','page':'p0','section':'制作','evidence_kind':'reading'},section='评价')
            with self.assertRaisesRegex(ValueError,'WRONG_SECTION'):self.finish(Path(d),s,a)

    def test_section_coverage_requires_all_body_not_one_paragraph(self):
        check={'field':'通读制作整节','page':'p0','section':'制作','scope':'section','evidence_kind':'reading'}
        with TemporaryDirectory() as d:
            s,a=self.fixture(Path(d),check=check,show_second=False)
            with self.assertRaisesRegex(ValueError,'SECTION_BODY_NOT_FULLY_READ'):self.finish(Path(d),s,a)
        with TemporaryDirectory() as d:
            s,a=self.fixture(Path(d),check=check)
            self.assertEqual(self.finish(Path(d),s,a)['status'],'VERIFIED')

    def test_heading_missing_check_empty_answer_and_unknown_rejected(self):
        for case in ('heading','missing','empty'):
            with self.subTest(case=case),TemporaryDirectory() as d:
                s,a=self.fixture(Path(d),heading_only=case=='heading')
                if case=='missing':s.plan_controller.frozen_plan['checks'].append({'field':'另一个原事项','evidence_kind':'reading'})
                if case=='empty':a['answer']=''
                with self.assertRaises(ValueError):self.finish(Path(d),s,a)

    def test_unknown_progress_preserves_proven_prefix_without_completion_or_stitching(self):
        with TemporaryDirectory() as d:
            s,a=self.fixture(Path(d));s.unknown=True
            result=self.finish(Path(d),s,a)
            self.assertEqual(result['status'],'UNVERIFIED')
            self.assertIsNone(result['completion'])
            self.assertEqual(result['blocked_reason'],'WIKI_READING_UNRESOLVED_UNKNOWN')
            self.assertTrue(result['new_visible_body'])
            # A later apparently verified row must not bridge an unknown operation.
            s.trajectory=[{'operation_id':'unknown','unknown':True},*s.trajectory]
            result=progress(s,'start')
            self.assertEqual(result['new_visible_body'],[])
            self.assertIsNone(result['completion'])

    def test_section_fields_only_new_schema_and_no_implicit_old_opt_in(self):
        check={'field':'通读制作','section':'制作','scope':'section','evidence_kind':'reading'}
        Draft202012Validator(schema(plan_schema(pending_checks=True))['properties']['checks']['items']).validate(check)
        from webcollect.direct_completion import schema as old_schema
        with self.assertRaises(ValidationError):
            Draft202012Validator(old_schema(plan_schema(pending_checks=True))['properties']['checks']['items']).validate(check)
        task={'initial_url':URL,'workflow_proposal':{'spec':{}},'fragment':{'plan_protocol':'webcollect-banded-conditional-plan-11'}}
        self.assertFalse(enabled(task));configure(task);self.assertTrue(enabled(task))
        older=deepcopy(task);older['fragment'].pop(FIELD);older['fragment']['plan_protocol']='webcollect-banded-conditional-plan-10'
        configure(older);self.assertFalse(enabled(older))

    def test_every_safe_stop_branch_offers_finish_even_at_ten_and_unknown_never_reissues(self):
        from webcollect.react_session import ReactStop, DecisionRequestError
        calls=[];controller=Controller();controller.submitted=True
        session=SimpleNamespace(task={'fragment':{FIELD:VERSION}},plan_controller=controller,
            unknown=False,trajectory=[{}]*10,used={'max_decisions':0},context={})
        session._left=lambda key:100
        session._check_request_budget=lambda:None
        session._consume=lambda key:session.used.__setitem__(key,session.used.get(key,0)+1)
        session._strip_prompt=lambda value:value
        session.event=lambda *args,**kwargs:None
        session._phase=lambda *args,**kwargs:nullcontext()
        def prompt(s,options):return {'options':options}
        async def choose(p):calls.append(p);raise DecisionRequestError('settled fixture failure')
        session.choose=choose;controller.prompt=prompt
        from unittest.mock import patch
        with patch('webcollect.banded_plan.remaining_step_allowance',return_value=0):
            with self.assertRaises(ReactStop):asyncio.run(controller.request(session,[{'choice':'stop'}]))
        self.assertEqual(len(calls),1)
        self.assertIn('finish_reading',[o['choice'] for o in calls[0]['options']])
        session.unknown=True
        with self.assertRaises(ReactStop):asyncio.run(controller.request(session,[{'choice':'stop'}]))
        self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
