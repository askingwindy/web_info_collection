"""Read-only regressions from actual captured states and independent counterexamples."""
import json
import unittest
from pathlib import Path
from webcollect.collect import describe_change, observed_excerpt
from test_annotation_regressions import state

FIXTURE = json.loads((Path(__file__).resolve().parent/'fixtures/narrative-context-real.json').read_text())


class NarrativeContext(unittest.TestCase):
    def actual(self, sid, step):
        case = FIXTURE['cases'][sid+':'+str(step)]
        before = FIXTURE['captures'][case['before_capture']]['state']
        after = FIXTURE['captures'][case['after_capture']]['state']
        return describe_change(before, after, case['operation'], case['target_element'])

    def test_actual_shiji_lunyu_keeps_author_and_classification(self):
        text = self.actual('S000010_sample_000001', 2)
        for phrase in ['史记', '司马迁', '史部正史类', '论语', '经部四书类']:
            self.assertIn(phrase, text)

    def test_actual_zhuangzi_xianwen_prose_precedes_trivial_counters(self):
        text = self.actual('S000010_sample_000001', 3)
        for phrase in ['庄子', '后学', '子部道家类', '增广贤文', '明代', '启蒙']:
            self.assertIn(phrase, text)

    def test_actual_zizhitongjian_preserves_informative_numeric_fact(self):
        text = self.actual('S000010_sample_000001', 4)
        for phrase in ['资治通鉴', '司马光', '史部编年类', '294卷']:
            self.assertIn(phrase, text)

    def test_actual_sunzi_and_huangdi_keep_distinct_visible_entities(self):
        text = self.actual('S000010_sample_000001', 5)
        for phrase in ['孙子兵法', '孙武', '子部兵家类', '黄帝内经', '子部医家类', '灵枢', '素问']:
            self.assertIn(phrase, text)

    def test_actual_hash_name_navigation_quotes_visible_body(self):
        text = self.actual('S000011_sample_000001', 1)
        self.assertIn('名称', text); self.assertIn('扁食', text); self.assertIn('角子', text)
        self.assertNotIn('页面切换为', text)

    def test_actual_hash_rumor_retains_rumor_qualifier(self):
        text = self.actual('S000011_sample_000001', 2)
        for phrase in ['传言', '有传言称', '张仲景']:
            self.assertIn(phrase, text)
        self.assertIn('称之为',text)
        self.assertNotIn('食物，」',text)

    def test_actual_hash_history_provides_visible_record_context(self):
        text = self.actual('S000011_sample_000001', 3)
        self.assertIn('历史', text); self.assertIn('南北朝', text)
        self.assertNotIn('页面切换为', text)

    def test_actual_hash_preparation_mentions_flour_not_just_page_title(self):
        text = self.actual('S000011_sample_000001', 4)
        for phrase in ['制法', '面团', '小麦粉']:
            self.assertIn(phrase, text)

    def test_actual_hash_variants_mentions_visible_food(self):
        text = self.actual('S000011_sample_000001', 5)
        self.assertIn('变体及类似食品', text); self.assertIn('水晶虾饺', text)
        self.assertNotIn('页面切换为', text)
        self.assertNotIn('Dumpling粤菜水晶虾饺',text)
        self.assertIn('广式点心',text)

    def test_long_observed_sentence_is_not_cut_at_length_or_comma(self):
        sentence='这是一段实际可见的长句，'*25+'直到这里才完整结束。'
        self.assertEqual(observed_excerpt(sentence+'下一句也可见。'),sentence)

    def test_block_without_sentence_punctuation_is_kept_whole(self):
        text='实际可见的完整语义块，'*25
        self.assertEqual(observed_excerpt(text),text)

    def test_unnamed_removed_control_uses_truthful_generic_description(self):
        control={'element_id':'close','text':'','element_type':'icon','inputable':False,'state':'default'}
        result=describe_change(state([control]),state(),{'action_type':'click','goal':'关闭登录推广'},control)
        self.assertEqual(result,'目标控件已不在当前视口')
        self.assertNotIn('「」',result)
        self.assertNotIn('登录推广已关闭',result)

    def test_unseen_goal_and_expected_are_not_observed_facts(self):
        before = state(visible='目录'); after = state(visible='当前仅显示可见的普通正文介绍。')
        after['scroll'] = [0, 300]
        text = describe_change(before, after, {'action_type':'scroll', 'arguments':{'direction':'down'},
            'goal':'定位未出现的秘密书名和外星作者', 'expected':'秘密书名由外星作者编纂，共9999卷'}, None)
        for unseen in ['秘密书名', '外星作者', '9999']:
            self.assertNotIn(unseen, text)

    def test_hash_menu_label_without_body_does_not_claim_section_reached(self):
        before = state(visible='目录\n传言\n历史'); after = state(visible='目录\n传言\n历史')
        after['url'] += '#history'
        target = {'element_id':'h', 'text':'历史', 'element_type':'link', 'inputable':False, 'state':'default'}
        text = describe_change(before, after, {'action_type':'click', 'goal':'阅读历史'}, target)
        self.assertNotIn('定位到', text); self.assertNotIn('章节正文', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
