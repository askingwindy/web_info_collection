"""Stable body IDs and frozen lookup sources; integration runner executes these."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import test_wiki_reading_completion_20261110 as wiki_fixtures
from test_wiki_reading_completion_20261110 import URL, P1
from webcollect.agent_controller import exclusive
from webcollect.wiki_reading import (FIELD, VERSION, LEGACY_VERSION, progress,
    resolve_source, evidence_payload, bind_plan_wire, FINISH_WHEN)
from webcollect.direct_completion import bind_answer
from webcollect.plan_evidence import bind_check_pages


class StableReadingEvidence(unittest.TestCase):
    def fixture(self,root):
        return wiki_fixtures.WikiReadingCompletion().fixture(root)

    def test_id_survives_extension_and_binds_original_metadata(self):
        with TemporaryDirectory() as d:
            s,_=self.fixture(Path(d));facts=progress(s,'start');p=facts['new_visible_body'][0]
            answer={'check_answers':[{'check_index':0,'answer':'原问题答案','evidence_ids':[p['evidence_id']]}]}
            bound=bind_answer(answer,s.plan_controller.frozen_plan,facts['new_visible_body'],s.trajectory)
            self.assertEqual(bound['check_answers'][0]['passages'][0]['quote'],P1)
            self.assertEqual(bound['check_answers'][0]['passages'][0]['url'],URL)
            s.trajectory.append({**s.trajectory[0],'operation_id':'op2'})
            self.assertEqual(progress(s,'start')['new_visible_body'][0],p)
            other=deepcopy(s);other.attempt_id='another-session'
            self.assertNotEqual(progress(other,'start')['new_visible_body'][0]['evidence_id'],p['evidence_id'])
            with self.assertRaisesRegex(ValueError,'UNKNOWN_EVIDENCE_ID'):
                bind_answer(answer,s.plan_controller.frozen_plan,progress(other,'start')['new_visible_body'],s.trajectory)

    def test_unknown_tail_never_contributes_ids_or_completion(self):
        with TemporaryDirectory() as d:
            s,_=self.fixture(Path(d));original=progress(s,'start')['new_visible_body']
            s.trajectory.extend([{'unknown':True},s.trajectory[0]])
            facts=progress(s,'start')
            self.assertEqual(facts['new_visible_body'],original)
            self.assertIsNone(facts['completion'])
            self.assertEqual(facts['blocked_reason'],'WIKI_READING_UNRESOLVED_UNKNOWN')

    def test_wrong_section_not_offered_as_candidates(self):
        with TemporaryDirectory() as d:
            s,_=self.fixture(Path(d));s.plan_controller.frozen_plan['checks'][0]['section']='不存在章节'
            s.plan_controller.frozen_page_binding=bind_check_pages(s.plan_controller.frozen_plan,[{'page_id':'p0','url':URL}])
            payload=evidence_payload(s)
            self.assertEqual(payload['reading_check_progress'][0]['available_evidence_ids'],[])
            self.assertIn('WRONG_SECTION',payload['reading_check_progress'][0]['missing'])

    def test_unbound_cross_page_requires_unique_original_lookup(self):
        with TemporaryDirectory() as d:
            s,_=self.fixture(Path(d));plan=s.plan_controller.frozen_plan
            plan['checks']=[{'field':'点入的相关条目正文首段要点','evidence_kind':'reading'}]
            plan['steps']=[{'action':'click','purpose':'进入相关条目正文','target':{'text':'相关词条'},'expected':{'kind':'document_changed'}}]
            binding=bind_check_pages(plan,[])
            with self.assertRaisesRegex(ValueError,'SOURCE_UNBOUND'):resolve_source(s,plan,0,binding)
            before=deepcopy(s.observation_records['start'])
            state=__import__('json').loads(Path(before['evidence']['state']['path']).read_text())
            state['elements'].append({'element_id':'link','text':'相关词条','visible':True})
            state['capture_controls'].append({'element_id':'link','href':'https://zh.wikipedia.org/wiki/重定向词条'})
            before['evidence']['state']=exclusive(Path(d)/'click-before.json',state)
            s.observation_records['lookup-before']=before
            landed=deepcopy(state);landed['url']='https://zh.wikipedia.org/wiki/真实落地词条'
            after={'url':landed['url'],'capture_verified':True,'evidence':{'state':exclusive(Path(d)/'landing.json',landed)}}
            s.observation_records['lookup-after']=after
            s.trajectory.append({'operation_id':'lookup','action':'click','before_observation_id':'lookup-before',
                'after_observation_id':'lookup-after','target':{'control_id':'link'}})
            self.assertEqual(resolve_source(s,plan,0,binding),landed['url'])
            s.observation_records['unrelated']={'url':'https://zh.wikipedia.org/wiki/其他条目'}
            self.assertEqual(resolve_source(s,plan,0,binding),landed['url'])
            s.trajectory.append({**s.trajectory[-1],'operation_id':'ambiguous-second-click'})
            with self.assertRaisesRegex(ValueError,'SOURCE_UNBOUND'):resolve_source(s,plan,0,binding)

    def test_legacy_has_no_ids_and_wire_placeholder_is_bound(self):
        with TemporaryDirectory() as d:
            s,_=self.fixture(Path(d));s.task['fragment'][FIELD]=LEGACY_VERSION
            self.assertNotIn('evidence_id',progress(s,'start')['new_visible_body'][0])
            original={'goal':'原目标'}
            self.assertEqual(bind_plan_wire(original,{FIELD:VERSION})['finish_when'],FINISH_WHEN)
            self.assertEqual(original,{'goal':'原目标'})
            with self.assertRaisesRegex(ValueError,'CONFLICT'):
                bind_plan_wire({'finish_when':{'kind':'url'}},{FIELD:VERSION})


if __name__=='__main__':unittest.main()
