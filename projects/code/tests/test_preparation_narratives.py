"""Independent counterexamples for actual A/B narrative defects."""
import unittest
from webcollect.collect import describe_change, observed_excerpt, completion_from_assertions

def state(text='',elements=None,values=None,scroll=0):
    return {'url':'https://fixture.invalid/','title':'本地独立测试','visible_text':text,
            'elements':elements or [],'values':values or [],'scroll':[0,scroll]}

class PreparationNarratives(unittest.TestCase):
    def test_clipped_course_names_are_explicit_fragments_before_open_parentheses(self):
        result=describe_change(state(),state('雅思精讲解题思路 · 1对1定制课强化基础/单\n新东方雅思进阶班：6-8人直播VIP小班（中学生',scroll=240),
            {'action_type':'scroll','arguments':{'direction':'down'},'goal':'核对雅思课程与师资'},None)
        self.assertIn('以「雅思精讲解题思路」开头的课程文字片段',result)
        self.assertIn('以「新东方雅思进阶班」开头的课程文字片段',result)
        self.assertNotIn('基础/单',result);self.assertNotIn('（中学生',result)

    def test_duplicate_clipped_subtitle_does_not_become_a_second_course(self):
        result=describe_change(state(),state('在职党必学：体验营优先录取保姆级政策全解析\n在职党必学：体验营优先录取保姆级政策全',scroll=240),
            {'action_type':'scroll','arguments':{'direction':'down'},'goal':'阅读考研课程'},None)
        self.assertEqual(result.count('在职党必学'),1)

    def test_terminal_judgement_uses_passed_observations_without_plan_navigation_claims(self):
        result=completion_from_assertions([{'expected':{'visible_text':'电话询问'},'actual':'电话询问：市民可致电查询','passed':True},
            {'expected':{'visible_text':'互联网'},'actual':'互联网：网站提供文字及声音版本','passed':True}])
        self.assertIn('电话询问',result);self.assertIn('互联网',result);self.assertNotIn('导航',result)
        with self.assertRaises(ValueError):completion_from_assertions([])
        with self.assertRaises(ValueError):completion_from_assertions([{'passed':False}])

    def test_news_scroll_prefers_new_prose_over_photo_credit_or_unchanged_prose(self):
        credit='观众在展览会上了解智能驾驶技术。记者 尹栋逊 摄'
        old='随着产业规划出台，行业发展正从技术验证转向规模商用。'
        new='今年有三十辆试验车辆正式上路，工程师在真实车流中核对复杂场景。'
        elements=[{'element_id':str(i),'native_role':'p','text':text} for i,text in enumerate([credit,old,new])]
        after=state('\n'.join([credit,old,new]),elements,scroll=240)
        after['text_blocks']=[{'element_id':str(i),'visible_text':text,'starts_visible':True,'ends_visible':True} for i,text in enumerate([credit,old,new])]
        result=describe_change(state(credit+'\n'+old),after,
             {'action_type':'scroll','arguments':{'direction':'down'},'goal':'阅读新进入视口的技术验证段落'},None)
        self.assertIn(new,result);self.assertNotIn('尹栋逊',result);self.assertNotIn(old,result)

    def test_short_inline_paragraph_suffix_is_not_a_separate_punctuation_fragment(self):
        text='不忍登高临远，望故乡渺邈\n(miǎo)\n，归思难收。叹年来踪迹，何事苦淹留。\n凝愁！'
        p={'native_role':'p','text':'不忍登高临远，望故乡渺邈 ，归思难收。叹年来踪迹，何事苦淹留。 凝愁！'}
        result=describe_change(state(),state(text,[p],scroll=240),
            {'action_type':'scroll','arguments':{'direction':'down'},'goal':'阅读词作译注'},None)
        self.assertIn('，归思难收。',result)
        self.assertNotIn('和「，',result)
        self.assertIn('(miǎo)',result)

    def test_unlabelled_counters_are_not_mistaken_for_tool_results(self):
        result=describe_change(state(),state('免费公开课\n18\n57\n已有1621人购买',scroll=240),
            {'action_type':'scroll','arguments':{'direction':'down'},'goal':'查看公开课程'},None)
        self.assertNotIn('「18」',result);self.assertNotIn('「57」',result)
        self.assertIn('公开课',result)

    def test_observed_closing_quote_stays_with_its_sentence(self):
        self.assertEqual(observed_excerpt('该词写道：“是处红衰翠减，苒苒物华休。”随后说明背景。'),
                         '该词写道：“是处红衰翠减，苒苒物华休。”')

    def test_course_title_is_not_concatenated_with_teacher_and_counter_fields(self):
        result=describe_change(state(),state('考研\n小白必看28考研入门宝典\n谭剑波\n18\n57',scroll=240),
            {'action_type':'scroll','arguments':{'direction':'down'},'goal':'阅读考研课程及教师信息'},None)
        self.assertIn('小白必看28考研入门宝典',result)
        self.assertNotIn('宝典谭剑波',result);self.assertNotIn('「18」',result)

    def test_main_image_is_described_without_inventing_its_subject_or_using_sidebar(self):
        heading={'native_role':'h1','text':'公开调查报道','bbox':[30,0,850,70]}
        picture={'native_role':'img','text':'','bbox':[30,160,850,700]}
        sidebar={'native_role':'p','text':'航拍长江源区重要支流与其他热点新闻推荐','bbox':[910,200,1080,280]}
        result=describe_change(state(),state(sidebar['text'],[heading,picture,sidebar],scroll=240),
            {'action_type':'scroll','arguments':{'direction':'down'},'goal':'查看报道的配图示例'},None)
        self.assertIn('主内容区的图片',result);self.assertNotIn('航拍',result)

    def test_partial_paragraph_discards_the_opening_fragment_using_recorded_boundaries(self):
        p={'element_id':'p','native_role':'p','text':'残句末尾。后面的完整句子说明该词写景与离情的关系。','bbox':[10,0,810,300]}
        after=state(p['text'],[p],scroll=240)
        after['text_blocks']=[{'element_id':'p','visible_text':p['text'],'starts_visible':False,'ends_visible':True}]
        result=describe_change(state(),after,{'action_type':'scroll','arguments':{'direction':'down'},'goal':'阅读赏析'},None)
        self.assertNotIn('残句末尾',result);self.assertIn('完整句子',result)

    def test_native_number_selection_unknown_is_not_claimed_as_verified(self):
        field={'element_id':'n','element_type':'input','text':'输入数值：','inputable':True,'state':'focused'}
        v={'element_id':'n','value':'1','display_value':'1','focused':True,'choice':False,
           'selection_start':None,'selection_end':None,'input_type':'number'}
        before=state('输入数值：\n1',[field],[v]);after=state('输入数值：\n1',[field],[dict(v)])
        result=describe_change(before,after,{'action_type':'hotkey','arguments':{'keys':['meta','a']}},None)
        self.assertIn('执行全选快捷键',result);self.assertIn('数值仍为「1」',result)
        self.assertIn('保持焦点',result);self.assertNotIn('已全部选中',result)

    def test_blurred_number_field_does_not_claim_retained_focus(self):
        field={'element_id':'n','element_type':'input','text':'输入数值：','inputable':True,'state':'default'}
        v={'element_id':'n','value':'1','display_value':'1','focused':False,'choice':False,
           'selection_start':None,'selection_end':None,'input_type':'number'}
        result=describe_change(state(),state('输入数值：\n1',[field],[v]),
                              {'action_type':'hotkey','arguments':{'keys':['meta','a']}},None)
        self.assertNotIn('保持焦点',result);self.assertNotIn('已全部选中',result)

if __name__=='__main__':unittest.main()
