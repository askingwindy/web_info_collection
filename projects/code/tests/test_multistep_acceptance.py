"""Target/result effects, narration and QC layers on disposable local evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from webcollect.collect import describe_change, visible_result_description
from webcollect.react_protocol import atomic_effect, SYSTEM, native_tools
from webcollect.react_context import project
from webcollect.qc_handoff import qc_layers
from webcollect.browser import stability_pair
from test_related_capture_stability import state, png


class MultistepChecks(unittest.TestCase):
    def test_first_frame_does_not_use_letter_ratio_as_language_eligibility(self):
        from webcollect.candidate_batch import first_frame_disposition
        self.assertIsNone(first_frame_disposition({'title':'中文测验','visible_text':'HTML 的全称是什么？Hyper Text Markup Language'}))
        self.assertEqual(first_frame_disposition({'title':'HTML 测验 | 菜鸟教程','visible_text':
            'HTML 的全称是什么？\nA\nHyper Text Markup Language\nB\nHyperlinks and Text Markup Language'}),
            ('abandon','english_quiz_answers'))
        self.assertIsNone(first_frame_disposition({'title':'工具页','visible_text':'This is an English input tool.'}))
        self.assertIsNone(first_frame_disposition({'title':'常见问题 | Vue.js',
            'visible_text':'文档 搜索 关于\nVue 的 TypeScript API 与 JavaScript TypeScript 支持',
            'elements':[{'element_type':'button','text':'搜索'}]}))
        self.assertIsNone(first_frame_disposition({'title':'中文知识测验','visible_text':
            '请回答下列关于网页结构的问题，选择正确选项并查看答案解析。HTML 标签可用于组织页面内容。'}))
        self.assertIsNone(first_frame_disposition({'title':'汉字查询','visible_text':'输入汉字查询读音、释义、部首及笔画。'}))

    def test_english_question_or_majority_english_answers_skip_independently(self):
        from webcollect.candidate_batch import first_frame_disposition
        chrome='中文导航和页面说明。'*100
        question=chrome+'\nWhat is the correct answer?\nA\n正确答案\nB\n错误答案'
        answers=chrome+'\n正确答案是什么？\nA\nCorrect answer\nB\nWrong answer'
        self.assertEqual(first_frame_disposition({'title':'知识测验','visible_text':question}),('abandon','english_quiz_question'))
        self.assertEqual(first_frame_disposition({'title':'知识测验','visible_text':answers}),('abandon','english_quiz_answers'))
        chinese=chrome+'\n网页内容使用什么语言组织？\nA\n超文本标记语言 HTML\nB\n层叠样式表 CSS'
        self.assertIsNone(first_frame_disposition({'title':'知识测验','visible_text':chinese}))
        self.assertIsNone(first_frame_disposition({'title':'查询工具','visible_text':answers}))

    def test_rerendered_selection_requires_unique_binding_and_target_ancestor(self):
        before={'url':'u','document_identity':{'origin':1},'values':[], 'visible_text':'选择甲\n选择乙',
                'elements':[dict(element_id='row',parent_id='root',native_role='div',text='',clickable=True,state='default'),
                            dict(element_id='text',parent_id='row',native_role='span',text='选择甲',clickable=True,state='default')],
                'capture_controls':[dict(element_id='row',selector='#choices > div:nth-of-type(1)',index=0,tag='div'),
                                    dict(element_id='text',selector='#choices > div:nth-of-type(1) > span',index=0,tag='span')]}
        after=deepcopy(before)
        after['elements'][0].update(element_id='new-row',state='selected')
        after['elements'][1].update(element_id='new-text',parent_id='new-row')
        after['capture_controls'][0]['element_id']='new-row';after['capture_controls'][1]['element_id']='new-text'
        self.assertTrue(atomic_effect(before,after,'click',{},'text')['verified'])
        for altered in ('selector','document','label','duplicate'):
            bad=deepcopy(after)
            if altered=='selector':bad['capture_controls'][1]['selector']='#elsewhere'
            if altered=='document':bad['document_identity']={'origin':2}
            if altered=='label':bad['elements'][1]['text']='选择乙'
            if altered=='duplicate':bad['capture_controls'].append({**bad['capture_controls'][1],'element_id':'new-row'})
            self.assertFalse(atomic_effect(before,bad,'click',{},'text')['verified'],altered)

    def test_sidebar_refresh_is_zero_but_target_result_and_new_dialog_count(self):
        def node(cid, parent, role, text):
            return dict(element_id=cid, parent_id=parent, native_role=role, text=text)
        before = dict(url='https://example.org/', values=[], visible_text='查询\n旧结果\n旧侧栏', elements=[
            node('main','root','main',''), node('button','main','button','查询'),
            node('result','main','p','旧结果'), node('aside','root','aside',''),
            node('news','aside','p','旧侧栏')])
        after = deepcopy(before);after['elements'][-1]['text']='新侧栏';after['visible_text']='查询\n旧结果\n新侧栏'
        self.assertFalse(atomic_effect(before, after, 'click', {}, 'button')['verified'])
        after['elements'][2]['text']='找到三项';after['visible_text']+='\n找到三项'
        self.assertTrue(atomic_effect(before, after, 'click', {}, 'button')['verified'])
        scoped=deepcopy(before)
        scoped['elements'].append(node('form','main','form',''))
        scoped['elements'][1]['parent_id']='form'
        unrelated=deepcopy(scoped);unrelated['elements'][2]['text']='别处更新';unrelated['visible_text']+='\n别处更新'
        self.assertFalse(atomic_effect(scoped,unrelated,'click',{},'button')['verified'])
        after = deepcopy(before);after['elements'] += [node('modal','root','dialog','详情'),node('body','modal','p','正文已显示')]
        after['visible_text']+='\n详情\n正文已显示'
        self.assertTrue(atomic_effect(before, after, 'click', {}, 'button')['verified'])

    def test_dialog_narrates_rendered_result_and_ordered_table_not_disappearance(self):
        b = dict(url='u',title='页面',scroll=[0,0],values=[],visible_text='时刻表',elements=[
            dict(element_id='button',parent_id='root',native_role='button',text='时刻表',inputable=False,state='default')])
        a = deepcopy(b);a['visible_text']='运营时刻表\n甲 → 乙\n05:00-22:40\n乙 → 甲\n05:00-23:00'
        a['elements']=[dict(element_id='modal',parent_id='root',native_role='dialog',text='运营时刻表')]
        for i,text in enumerate(a['visible_text'].splitlines()):
            a['elements'].append(dict(element_id=str(i),parent_id='modal',native_role='h2' if not i else 'td',text=text))
        result=describe_change(b,a,dict(action_type='click',arguments={},goal='打开时刻表'),b['elements'][0])
        self.assertIn('运营时刻表已展开',result)
        self.assertIn('「甲 → 乙」；「05:00-22:40」；「乙 → 甲」；「05:00-23:00」',result)
        self.assertIsNone(visible_result_description(b))

    def test_wire_carries_current_truth_and_specific_missing_probe_advice(self):
        source=dict(system=SYSTEM,tools=native_tools(['click']),requested_goal={'对象':'原对象','参数':10},
            working_goal='按原参数查询并核对结果',observation={'observation_id':'current','controls':{
                'a':{'actions':{'click':'INSUFFICIENT/MISSING_TARGET_PROBE'}},
                'b':{'actions':{'click':'PROVEN'}}}},last_tool_result={'summary':'缺探针','data':{
                'next_tool':{'name':'observe','arguments':{'focus_control_id':'a'}}}},_history=[])
        wire=project(source)
        self.assertEqual(wire['requested_goal'],source['requested_goal'])
        self.assertEqual(wire['observation'],source['observation'])
        self.assertIn('MISSING_TARGET_PROBE',wire['system'])
        self.assertIn('优先围绕当前正文与目录',wire['system'])
        self.assertEqual(wire['last_tool_result']['data']['next_tool']['name'],'observe')
        self.assertIn('焦点',wire['tools'][2]['function']['description'])

    def test_peripheral_video_repaint_is_not_a_target_or_outside_exception(self):
        first=state();first['capture_images']=[]
        first['capture_media']=[dict(kind='peripheral_video',bbox=[10,0,30,10],src='v',ready=True,
            eligible=True,actions_supported=False,proof=dict(schema_version='webcollect-peripheral-video-1',
            peripheral=True,controls=False,geometry_and_style_clear=True,hit_samples=[True]*9,
            protected_boxes=[[0,15,9,25]]))]
        self.assertTrue(stability_pair(first,deepcopy(first),png(),png(pixel=(15,5)))['accepted'])
        self.assertFalse(stability_pair(first,deepcopy(first),png(),png(pixel=(5,20)))['accepted'])
        first['capture_media'][0]['proof']['protected_boxes'].append([15,2,20,8])
        self.assertFalse(stability_pair(first,deepcopy(first),png(),png(pixel=(15,5)))['accepted'])

    def test_sample_pass_package_fail_and_unreviewed_are_independent(self):
        names=['VISUAL_ALIGNMENT','TERMINAL_SEMANTICS','LANGUAGE','PRIVACY','SUBSTANTIVE_DIFFERENCE']
        with tempfile.TemporaryDirectory() as d:
            sample=Path(d)/'sample.json';package=Path(d)/'package.json'
            report={'payload_sha256':'same','samples':[{'sample_id':'s','status':'PASS','checks':[
                {'rule_id':'REVIEW_'+n,'status':'PASS','reviewer':{'kind':'ai'}} for n in names]}]}
            sample.write_text(json.dumps(report));package.write_text(json.dumps({**report,'sample_count':1,
                'delivery_document_review':{'status':'FAIL','reason':'规模和分布'},'dataset_checks':[
                    {'rule_id':'DELIVERY_EXPECTED_SAMPLES','status':'FAIL','reason':'Expected 1000; inspected 1'}]}))
            layers=qc_layers(sample,package)
            self.assertEqual(layers['sample_ai']['pass'],1)
            self.assertEqual(layers['package_document_ai']['status'],'FAIL')
            self.assertEqual(layers['distribution']['status'],'FAIL')
            report['samples'][0]['checks']=[];sample.write_text(json.dumps(report))
            self.assertEqual(qc_layers(sample)['sample_ai']['actually_reviewed'],0)
            self.assertEqual(qc_layers(sample)['sample_ai']['samples'][0]['status'],'NOT_REVIEWED')
