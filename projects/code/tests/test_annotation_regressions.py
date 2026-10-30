"""Regression cases for observed annotation defects; no websites or signatures."""
import unittest
import json
from pathlib import Path
from webcollect.collect import describe_change
import webcollect.collect as module


def state(elements=(), values=(), visible=''):
    return {'title':'测试页面','url':'https://example.invalid/','scroll':[0,0],
            'elements':list(elements),'values':list(values),'visible_text':visible}

def element(eid='e1', text='搜索框', kind='input', editable=True):
    return {'element_id':eid,'text':text,'element_type':kind,'inputable':editable,'state':'default'}

def value(eid='e1', text='', focused=False, choice=False, input_type='search'):
    return {'element_id':eid,'value':text,'display_value':text,'focused':focused,'choice':choice,
            'input_type':input_type,'selection_start':0,'selection_end':len(text),'value_visible':True}

class AnnotationRegressions(unittest.TestCase):
    def test_invisible_native_value_cannot_supply_change_text(self):
        e=element();v=value(text='屏外完整结果');v['value_visible']=False
        # A hidden input value is not a fallback when the frame has no painted
        # narrative evidence. Preserve the original empty-frame case as a
        # rejection, then test exclusion with independently visible prose.
        with self.assertRaisesRegex(ValueError,'NARRATIVE_VISIBLE_EVIDENCE_MISSING'):
            describe_change(state([e],[value()]),state([e],[v]),{'action_type':'type'},e)
        visible='当前页面展示输入说明，结果尚未进入可见区域。'
        result=describe_change(state([e],[value()]),state([e],[v],visible),{'action_type':'type'},e)
        self.assertNotIn('屏外完整结果',result)
        self.assertIn(visible,result)

    def test_complete_sentence_evidence_skips_clipped_punctuation_noise(self):
        e={'element_id':'p','native_role':'p','text':'。二 ， ，—— 七千公里，而泰雅人与排湾人只隔着一道山脊。完整且可见的后续正文足够说明当前页面变化。','bbox':[0,0,500,100]}
        after=state([e],visible=e['text']);after['scroll']=[0,480]
        after['text_blocks']=[{'element_id':'p','visible_text':e['text'],'starts_visible':False,'ends_visible':True,
                              'complete_sentences':['完整且可见的后续正文足够说明当前页面变化。']}]
        result=describe_change(state(),after,{'action_type':'scroll','arguments':{'direction':'down'}},None)
        self.assertIn('完整且可见的后续正文',result);self.assertNotIn('二 ，',result)
    def test_focus_replacement_and_choice_flag_are_not_empty_selection(self):
        e=element(); before=state([e],[value()]);after=state([element('e2')],[value('e2',focused=True,choice=True)])
        result=describe_change(before,after,{'action_type':'click'},e)
        self.assertIn('获得焦点',result); self.assertNotIn('已选择',result)
    def test_editable_combobox_typing_is_input_not_choice(self):
        e=element();result=describe_change(state([e],[value(choice=True)]),state([e],[value(text='出师表',choice=True,focused=True)]),{'action_type':'type'},e)
        self.assertIn('显示「出师表」',result);self.assertNotIn('已选择',result)
    def test_new_button_empty_value_does_not_override_visible_result(self):
        e=element(text='请输入金额');b=element('b','复制','button',False)
        result=describe_change(state([e],[value()]),state([e,b],[value(text='100'),value('b',input_type='submit')],'阿拉伯数字:\n¥100\n复制\n中文大写:\n壹佰元整'),{'action_type':'click'},b)
        self.assertIn('壹佰元整',result);self.assertNotIn('复制」显示',result)
    def test_scroll_uses_visible_prose_not_accessible_title(self):
        e=element('w','w:岳阳楼记','link',False);after=state([e],[], '先天下之忧而忧');after['scroll']=[0,400]
        result=describe_change(state(),after,{'action_type':'scroll','arguments':{'direction':'down'}},None)
        self.assertIn('先天下之忧而忧',result);self.assertNotIn('w:',result)
    def test_clear_real_input_is_preserved(self):
        e=element();result=describe_change(state([e],[value(text='旧值')]),state([e],[value()]),{'action_type':'hotkey'},None)
        self.assertIn('已清空',result)
    def test_readonly_choice_is_still_selection(self):
        e=element(editable=False);result=describe_change(state([e],[value(text='二进制数据',choice=True)]),state([e],[value(text='概率数据',choice=True)]),{'action_type':'click'},e)
        self.assertIn('已选择「概率数据」',result)
    def test_removed_popup_button_is_not_described_as_still_present(self):
        e=element('popup','知道了','button',False)
        result=describe_change(state([e]),state(),{'action_type':'click'},e)
        self.assertIn('已不在当前视口',result);self.assertNotIn('仍显示',result)
    def test_typing_does_not_append_unrelated_advertising(self):
        e=element(text='中文数字');result=describe_change(state([e],[value()]),state([e],[value(text='一')],'报名外语课程'),{'action_type':'type'},e)
        self.assertIn('显示「一」',result);self.assertNotIn('报名外语',result)
    def test_accessible_calendar_names_are_not_visible_labels(self):
        e=element(text='Month',editable=False)
        result=describe_change(state(),state([e],[value(text='十月')],'十月\n2026'),{'action_type':'click'},None)
        self.assertIn('可访问名称',result);self.assertIn('十月',result)
    def test_scroll_with_new_short_labels_retains_parameter_context(self):
        a=state(visible='输入内容\n结果精度');b=state(visible='输入内容\n结果精度\n打开\n计算');b['scroll']=[0,250]
        result=describe_change(a,b,{'action_type':'scroll','arguments':{'direction':'down'}},None)
        self.assertIn('打开',result);self.assertNotIn('当前页面为',result)
    def test_scroll_table_rows_are_visible_evidence(self):
        a=state(visible='熵值分布表格');b=state(visible='熵值分布表格\n概率 1\n概率 2');b['scroll']=[0,200]
        result=describe_change(a,b,{'action_type':'scroll','arguments':{'direction':'down'}},None)
        self.assertIn('概率 1',result);self.assertIn('概率 2',result)
    def test_scroll_explains_observed_goal_phrase_in_context(self):
        a=state();b=state(visible='所赖君子安贫\n老当益壮\n宁移白首之心');b['scroll']=[0,400]
        result=describe_change(a,b,{'action_type':'scroll','arguments':{'direction':'down'},'goal':'定位包含老当益壮的正文段落'},None)
        self.assertIn('目标文字「老当益壮」',result);self.assertIn('宁移白首之心',result)
    def test_scroll_does_not_claim_unobserved_goal_phrase(self):
        a=state();b=state(visible='页面尚在文章开头');b['scroll']=[0,400]
        result=describe_change(a,b,{'action_type':'scroll','arguments':{'direction':'down'},'goal':'定位包含老当益壮的正文段落'},None)
        self.assertNotIn('老当益壮',result)
    def test_vue_task_templates_have_specific_final_evidence(self):
        plan=json.loads((Path(module.__file__).parents[1]/'plans/M2-reading-navigation.json').read_text())
        tasks={t['task_id']:t for t in plan['tasks']}
        for name,term in [('vue-ways-of-using-vue','单页'),('vue-composition-api-faq','取舍')]:
            with self.subTest(task=name):
                t=tasks[name];self.assertIn(term,t['final_result']);self.assertNotIn('最后一个说明段落或小节',t['final_result'])

if __name__=='__main__':unittest.main(verbosity=2)


class ValueVisibilityDisplayProof(unittest.TestCase):
    def _target(self, **overrides):
        target = {'selector': '#from', 'index': 0, 'visible': True, 'value': '(2021)',
                  'value_visible': False, 'display_value': '(2021)', 'target_text': '显示页面开始于：'}
        target.update(overrides); return target

    def test_matching_display_passes_despite_inconclusive_flag(self):
        import asyncio
        from webcollect.collect import assert_state
        state = {'assertion_targets': [self._target()]}
        row = asyncio.run(assert_state(None, [{'selector': '#from', 'index': 0, 'value': '(2021)'}],
                                       captured_state=state))
        self.assertTrue(row[0]['passed'])

    def test_mismatched_display_still_rejects(self):
        import asyncio
        from webcollect.collect import assert_state
        state = {'assertion_targets': [self._target(display_value='(2020)')]}
        with self.assertRaisesRegex(ValueError, '未在实际视口中可见'):
            asyncio.run(assert_state(None, [{'selector': '#from', 'index': 0, 'value': '(2021)'}],
                                     captured_state=state))
