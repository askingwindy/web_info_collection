"""Visible observation regressions; fixtures are not production or human review."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from webcollect.collect import describe_change, quoted_visible_content
from webcollect.task_contract import narrative_evidence, PLAN_SCHEMA
from test_m4_task_contract import m4_task


def frame(text='', title='后台标题', url='https://example.org/page'):
    return {'url':url, 'title':title, 'visible_text':text, 'elements':[], 'values':[],
            'text_blocks':[], 'scroll':[0,0], 'screen_resolution':[640,480]}


class NarrativeObservationBinding(unittest.TestCase):
    def test_navigation_quotes_painted_heading_and_fact_instead_of_browser_title(self):
        before=frame('书籍目录')
        after=frame('梦溪笔谈/卷三\n钧石之石，五权之名，石重百二十斤。',
                    '梦溪笔谈/卷三 - 网站后台标题', 'https://example.org/chapter')
        op={'action_type':'click','goal':'核对古代一石斤数',
            'postconditions':[{'visible_text':'石重百二十斤。'}]}
        result=describe_change(before,after,op,None)
        self.assertIn('梦溪笔谈/卷三',result)
        self.assertIn('石重百二十斤。',result)
        self.assertNotIn('网站后台标题',result)
        self.assertEqual(narrative_evidence(result,before,after,op)[0],result)

    def test_planned_or_hidden_postcondition_never_supplies_an_observation(self):
        before=frame('原页面')
        after=frame('当前确实显示的是一段普通介绍文字。')
        op={'action_type':'click','goal':'核对未出现的秘密',
            'postconditions':[{'visible_text':'尚未显示的秘密事实'}]}
        result=describe_change(before,after,op,None)
        self.assertNotIn('秘密事实',result)
        self.assertIn('普通介绍',result)

    def test_composed_visible_fragments_are_bound_separately(self):
        after=frame('第一段真实可见的介绍。\n编辑\n第二段真实可见的解释。')
        context='第一段真实可见的介绍。；第二段真实可见的解释。'
        result=quoted_visible_content(context,after)
        self.assertEqual(result.count('「'),2)
        self.assertEqual(narrative_evidence(result,frame(),after,{})[0],result)
        safe,evidence=narrative_evidence('可见「'+context+'」',frame(),after,{})
        self.assertIsNone(safe)
        self.assertEqual(evidence['machine_status'],'REVIEW_REQUIRED')

    def test_directory_scroll_uses_actual_link_not_repeated_glyph_or_search_chrome(self):
        before=frame('目录')
        after=frame('二 二 二 二\n搜索梦溪笔谈\n卷三')
        after['scroll']=[0,240]
        after['elements']=[{'element_id':'chapter3','element_type':'link','native_role':'a',
                            'text':'卷三','bbox':[10,20,70,40]}]
        op={'action_type':'scroll','arguments':{'direction':'down'},'goal':'向下查找目录中的卷三'}
        result=describe_change(before,after,op,None)
        self.assertIn('卷三',result)
        self.assertNotIn('搜索',result)
        self.assertNotIn('二 二',result)

    def test_unpainted_title_and_placeholder_are_not_exportable_fallbacks(self):
        with self.assertRaisesRegex(ValueError,'NARRATIVE_VISIBLE_EVIDENCE_MISSING'):
            describe_change(frame(),frame(title='未绘制标题',url='https://example.org/other'),
                            {'action_type':'click','goal':'进入目标'},None)
        safe,evidence=narrative_evidence('已执行本步动作并保存后续实际视口；具体可见变化待独立审核。',
                                         frame(),frame(),{})
        self.assertIsNone(safe)
        self.assertTrue(evidence['placeholder_result'])
        self.assertFalse(evidence['exportable'])

    def test_control_value_requires_explicit_complete_visibility(self):
        after=frame('输入结果')
        after['elements']=[{'element_id':'field','text':'结果','visible':True}]
        after['values']=[{'element_id':'field','display_value':'12345','value':'12345','value_visible':True}]
        result='结果显示「12345」'
        self.assertEqual(narrative_evidence(result,frame(),after,{})[0],result)
        for visible in (False,None):
            bad=copy.deepcopy(after);bad['values'][0]['value_visible']=visible
            self.assertIsNone(narrative_evidence(result,frame(),bad,{})[0])


class UnsupportedNarrativeCollection(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_quote_keeps_diagnostics_without_successful_annotation(self):
        from playwright.async_api import async_playwright
        from webcollect.collect import collect_one
        html='<meta charset="utf-8"><h1>五分钟</h1><p id="state">等待开始</p><button id="start" onclick="document.querySelector(\'#state\').textContent=\'已开始\'">开始</button><button id="pause" onclick="document.querySelector(\'#state\').textContent=\'已暂停\'">暂停</button>'
        task={**m4_task(),'_plan_schema_version':PLAN_SCHEMA,'initial_settle_ms':0,'content_preparation':False}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);sample=root/'sample';evidence=root/'evidence'
            async with async_playwright() as runtime:
                browser=await runtime.chromium.launch(channel='chrome',headless=True)
                context=await browser.new_context(viewport={'width':640,'height':480})
                try:
                    await context.route('https://example.org/**',lambda route:route.fulfill(content_type='text/html',body=html))
                    with patch('webcollect.collect.describe_change',return_value='当前可见「从未绘制的秘密」'):
                        with self.assertRaisesRegex(ValueError,'NARRATIVE_EVIDENCE_UNSUPPORTED'):
                            await collect_one(context,task,sample,evidence,{'sample_id':'fixture-only'})
                finally:
                    await browser.close()
            self.assertFalse((sample/'annotation.json').exists())
            diagnosis=json.loads((evidence/'step_001_narrative.json').read_text())
            self.assertEqual(diagnosis['unsupported_quotes'],['从未绘制的秘密'])
            self.assertFalse(diagnosis['exportable'])
            failure=json.loads((evidence/'task_contract.json').read_text())
            self.assertEqual(failure['machine_status'],'FAIL')
            self.assertTrue(failure['original_evidence_preserved'])
            self.assertTrue((evidence/'failure_after.json').is_file())


if __name__=='__main__':
    unittest.main()
