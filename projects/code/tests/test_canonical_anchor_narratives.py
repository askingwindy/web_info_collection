"""Offline regressions from the two archived Vue step-2 before/after records."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from webcollect.collect import describe_change
from webcollect.task_contract import narrative_evidence

CASES=json.loads((Path(__file__).parent/'fixtures/vue-canonical-anchor-raw-projection.json').read_text())['cases']


def describe(case):
    return describe_change(case['before'],case['after'],case['operation'],case['target_element'])


class CanonicalAnchorNarratives(unittest.TestCase):
    def assert_observed_page_change(self, case):
        result=describe(case)
        self.assertIn('页面已切换',result)
        self.assertNotIn('同一页面定位到',result)
        safe,evidence=narrative_evidence(result,case['before'],case['after'],case['operation'])
        self.assertEqual(safe,result)
        self.assertEqual(evidence['unsupported_quotes'],[])

    def assert_observed_section(self,case):
        result=describe(case)
        self.assertIn('同一页面定位到',result)
        self.assertIn(case['target_element']['text'],result)
        self.assertIn(case['expected_visible_quote'],result)
        self.assertNotIn('页面切换为',result)
        return result

    def test_archived_vue_spa_step2_reports_real_visible_section(self):
        self.assert_observed_section(CASES[0])

    def test_archived_vue_logic_reuse_step2_reports_real_visible_section(self):
        self.assert_observed_section(CASES[1])

    def test_identical_explicit_query_is_preserved_when_html_is_canonicalized(self):
        case=deepcopy(CASES[0])
        case['before']['url']+='?lang=zh'
        case['after']['url']=case['after']['url'].replace('.html#','.html?lang=zh#')
        self.assert_observed_section(case)

    def test_existing_exact_path_anchor_and_reverse_html_variant_still_use_prose(self):
        for mode in ['same_html_path','reverse_html_variant']:
            with self.subTest(mode=mode):
                case=deepcopy(CASES[0]);case['before']['url']+='.html'
                if mode=='reverse_html_variant':case['after']['url']=case['after']['url'].replace('.html#','#')
                self.assert_observed_section(case)

    def test_cross_origin_other_path_or_additional_extension_is_not_same_article(self):
        for before,after in [
            ('https://cn.vuejs.org/guide/extras/ways-of-using-vue','https://other.invalid/guide/extras/ways-of-using-vue.html#spa'),
            ('https://cn.vuejs.org/guide/extras/ways-of-using-vue','https://cn.vuejs.org/guide/extras/another-article.html#spa'),
            ('https://cn.vuejs.org/guide/extras/ways-of-using-vue.htm','https://cn.vuejs.org/guide/extras/ways-of-using-vue.htm.html#spa'),
            ('http://cn.vuejs.org/guide/extras/ways-of-using-vue','https://cn.vuejs.org/guide/extras/ways-of-using-vue.html#spa')]:
            with self.subTest(before=before,after=after):
                case=deepcopy(CASES[0]);case['before']['url']=before;case['after']['url']=after
                self.assert_observed_page_change(case)

    def test_changed_query_is_not_canonical_same_article(self):
        for old_query,new_query in [('', '?lang=en'),('?mode=one','?mode=two')]:
            with self.subTest(old=old_query,new=new_query):
                case=deepcopy(CASES[0]);case['before']['url']+=old_query
                case['after']['url']=case['after']['url'].replace('.html#','.html'+new_query+'#')
                self.assert_observed_page_change(case)

    def test_html_alias_requires_an_actual_fragment_only_anchor_click(self):
        for operation in [{'action_type':'click'}, {'action_type':'click','selector':'.toc a'},
                          {'action_type':'click','selector':'a[href="/guide/extras/ways-of-using-vue#single-page-application-spa"]'},
                          {'action_type':'click','selector':'a[href="#other-section"]'},
                          {'action_type':'hotkey','selector':'a[href="#single-page-application-spa"]'}]:
            with self.subTest(operation=operation):
                case=deepcopy(CASES[0]);case['operation']=operation
                self.assert_observed_page_change(case)

    def test_title_change_or_unchanged_fragment_is_not_section_navigation(self):
        for mode in ['different_title','no_new_fragment']:
            with self.subTest(mode=mode):
                case=deepcopy(CASES[0])
                if mode=='different_title':case['after']['title']='另一篇正文'
                else:case['after']['url']=case['after']['url'].split('#')[0]
                self.assert_observed_page_change(case)

    def test_directory_label_alone_does_not_invent_section_body(self):
        case=deepcopy(CASES[0]);label=case['target_element']['text']
        case['after']['visible_text']='本页目录\n'+label
        case['after']['elements']=[]
        result=describe(case)
        self.assertIn('可见目录项',result)
        self.assertNotIn('当前可见内容包括',result)
        self.assertNotIn(case['expected_visible_quote'],result)


if __name__=='__main__':unittest.main()
