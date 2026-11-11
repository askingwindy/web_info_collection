"""New-run fact binding and shared replan budget, without production data."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from webcollect.banded_plan import plan_schema
from webcollect.plan_evidence import page_matches, region_matches, facts, unverified_required_checks

POLICY='goal-completion-ending'  # single current ending policy

class FiveTenFactsTests(unittest.TestCase):
    def test_wiki_namespace_title_edit_and_redirect_are_observation_bound(self):
        state={'url':'https://zh.wikipedia.org/wiki/Wikipedia:%E5%85%B8%E8%8C%83%E6%9D%A1%E7%9B%AE','elements':[]}
        self.assertTrue(page_matches('Wikipedia:典范条目',state))
        state={'url':'https://zh.wikipedia.org/wiki/天津历史','elements':[{'visible':True,'native_role':'h1','text':'天津历史 编辑'}]}
        self.assertTrue(page_matches('天津历史',state))
        state={'url':'https://zh.wikipedia.org/wiki/三岔河口','elements':[]}
        nav=[{'actual_visible_target':'三会海口','landed_url':state['url']}]
        self.assertFalse(page_matches('三会海口',state))
        self.assertTrue(page_matches('三会海口',state,nav))
        self.assertFalse(page_matches('别的河口',state,nav))

    def test_calculator_result_requires_semantic_container(self):
        state={'url':'https://www.muxtly.com/calc','elements':[{'element_id':'v','visible':True,'native_role':'h1','text':'🇩🇪 德国增值税计算器 2026'},
               {'element_id':'intro','visible':True,'native_role':'p','text':'应纳税额和税后收入介绍'}],
               'capture_controls':[{'element_id':'intro','selector':'html > body > main > p'}]}
        self.assertTrue(page_matches('德国增值税计算器',state))
        self.assertFalse(region_matches(state,'intro','结果区',business_aliases=True))
        state['elements'].append({'element_id':'result','visible':True,'native_role':'output','text':'税后收入 1200'})
        state['elements'][1]['parent_id']='result'
        self.assertTrue(region_matches(state,'intro','结果区',business_aliases=True))

    def test_list_heading_is_not_page_identity(self):
        state={'url':'https://a.test/list','title':'目录','elements':[{'visible':True,'native_role':'h3','text':'天津历史'}]}
        self.assertFalse(page_matches('天津历史',state))

    def test_facts_keep_original_checks_and_attach_action_references(self):
        with TemporaryDirectory() as td:
            path=Path(td)/'state.json'
            state={'url':'https://zh.wikipedia.org/wiki/天津历史','document_identity':'d',
                   'elements':[{'element_id':'e','visible':True,'native_role':'p','text':'明代筑城'}],
                   'capture_controls':[{'element_id':'e','selector':'main > p'}]}
            path.write_text(json.dumps(state))
            obs={'capture_verified':True,'evidence':{'state':{'path':str(path)},'image':{'path':'image.png'}}}
            row={'action':'scroll','operation_id':'op1','before_observation_id':'a','after_observation_id':'b'}
            session=SimpleNamespace(task={'fragment':{'ending_policy':POLICY}},trajectory=[row],observation_records={'b':obs},requested_goal='阅读',working_goal='阅读')
            check={'field':'史实','page':'天津历史','region':'正文','visible_text':'明代筑城'}
            result=facts(session,{'checks':[check,{'field':'辅助'}]})
            self.assertEqual(result['checks'][0]['status'],'VERIFIED')
            self.assertEqual(result['checks'][0]['evidence'][0]['action_refs'][0]['operation_id'],'op1')
            self.assertEqual(result['checks'][1]['status'],'PENDING')
            self.assertEqual(unverified_required_checks(result),[])
            self.assertNotIn('status',check)
