"""Independent native-action traces; these local fixtures are never delivery."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from playwright.async_api import async_playwright
from webcollect.collect import collect_one
from webcollect.evidence import audit_capture

URL='https://preparation-chain.invalid/page'
PROSE='这是真实正文。文章介绍公共知识的阅读方式，并说明如何按照标题与段落核对内容。每个操作必须保留实际画面和前后变化，不能用预期推断页面结果。'
ARTICLE='<article><h1>公共知识正文</h1><p>'+PROSE+'</p><p>'+PROSE+'</p></article>'
CONFIRM='<button id="confirm" onclick="document.querySelector(\'#result\').textContent=\'核对完成\'">确认正文内容</button><p id="result">等待核对</p>'

class PreparationCollection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.p=await async_playwright().start()
        self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':1280,'height':720},device_scale_factor=1)
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)

    async def asyncTearDown(self):
        await self.browser.close();await self.p.stop();self.temp.cleanup()

    async def run_case(self,html,operations=None,settings=None):
        await self.context.route('https://preparation-chain.invalid/**',
            lambda route:route.fulfill(content_type='text/html; charset=utf-8',body='<meta charset="utf-8"><style>body{font:20px sans-serif}p{line-height:1.7}</style>'+html))
        operations=operations or [{'action_type':'click','selector':'#confirm','arguments':{},
             'goal':'确认正文已完成核对','rationale':'根据实际可见正文确认结果',
             'expected':'页面显示核对完成','execution':{'settle_ms':50}}]
        task={'initial_url':URL,'initial_settle_ms':0,'stop_when_final':False,
              'operations':operations,'content_preparation':settings or {'mode':'auto'},
              'final_assertions':[{'visible_text':'核对完成'}],
              'final_result':'页面显示核对完成','completion_judgement':'末图确有核对完成',
              'instruction':'本地准备链条测试，不可作为真实交付','task_type':['数据查看'],
              'app_name':'本地准备测试','task_id':'unit-preparation-chain'}
        sid='S000001_sample_000001';s=self.root/'samples'/sid;e=self.root/'evidence'/sid
        a=await collect_one(self.context,task,s,e,{'sample_id':sid})
        return a,s,e

    def modal(self,button=None):
        button=button or '<button id="close" onclick="this.parentElement.remove()">关闭广告</button>'
        return '<div role="dialog" aria-modal="true" style="position:fixed;inset:30px;background:white;z-index:9999"><h2>课程推广广告</h2><p>这是可选推广，请先关闭推广再阅读公开正文。</p>'+button+'</div>'

    async def test_inserted_close_is_first_real_action_with_same_landing_frame(self):
        a,s,e=await self.run_case(ARTICLE+CONFIRM+self.modal())
        self.assertEqual([x['action']['action_type'] for x in a['steps']],['click','click','complete'])
        raws=[json.loads((e/f'step_{i:03}.json').read_text()) for i in [1,2,3]]
        self.assertEqual([x['operation_origin'] for x in raws],['preparation','planned','planned'])
        self.assertEqual([x['planned_operation_index'] for x in raws],[None,0,1])
        initial=json.loads((e/'initial_capture.json').read_text())
        self.assertEqual(initial['state'],raws[0]['state'])
        self.assertEqual((e/'initial_capture.png').read_bytes(),(s/'images/step_001.png').read_bytes())
        decisions=json.loads((e/'preparation_decisions.json').read_text())['decisions']
        self.assertEqual(decisions[0]['action_step_id'],1)
        self.assertEqual(decisions[0]['after_step_id'],2)
        self.assertEqual(decisions[0]['after_image_sha256'],hashlib.sha256((s/'images/step_002.png').read_bytes()).hexdigest())
        self.assertTrue(audit_capture(self.root,a['sample_id'])['capture_evidence_pass'])

    async def test_planned_real_close_is_not_executed_twice(self):
        close={'action_type':'click','selector':'#close','arguments':{},
               'goal':'关闭推广','rationale':'先正常关闭可选推广','expected':'推广关闭',
               'execution':{'settle_ms':50}}
        confirm={'action_type':'click','selector':'#confirm','arguments':{},
                 'goal':'确认正文','rationale':'正文可见后确认','expected':'核对完成',
                 'execution':{'settle_ms':50}}
        a,s,e=await self.run_case(ARTICLE+CONFIRM+self.modal(),[close,confirm])
        self.assertEqual(len(a['steps']),3)
        first=json.loads((e/'step_001.json').read_text())
        self.assertEqual(first['operation_origin'],'planned')
        self.assertEqual(first['planned_operation_index'],0)
        self.assertEqual(json.loads((e/'preparation_decisions.json').read_text())['decisions'][0]['performed_by_planned_close'],True)

    async def test_tool_input_and_viewport_are_preserved(self):
        a,s,e=await self.run_case('<h1>公开工具</h1><label>输入数据<input value="测试数值"></label>'+CONFIRM+ARTICLE)
        self.assertEqual(len(a['steps']),2)
        self.assertEqual(json.loads((e/'step_001.json').read_text())['state']['scroll'],[0,0])
        self.assertEqual(json.loads((e/'capture_summary.json').read_text())['preparation_actions'],0)
        self.assertTrue(audit_capture(self.root,a['sample_id'])['capture_evidence_pass'])

    async def test_first_existing_scroll_is_reused_without_moving_the_task_endpoint(self):
        scroll={'action_type':'scroll','arguments':{'direction':'down'},
                'goal':'向下阅读正文开头','rationale':'正文位于横幅之后，先阅读正文开头',
                'expected':'正文开头完整可见','execution':{'distance':240,'settle_ms':100}}
        confirm={'action_type':'click','selector':'#confirm','arguments':{},
                 'goal':'确认正文','rationale':'正文可见后确认','expected':'核对完成',
                 'execution':{'settle_ms':50}}
        a,s,e=await self.run_case('<style>#confirm{position:fixed;bottom:60px;right:10px}#result{position:fixed;bottom:5px;right:10px}</style><div style="height:600px">中文推广横幅，正文位于横幅之后。</div>'+ARTICLE+CONFIRM,
            [scroll,confirm],{'mode':'article'})
        self.assertEqual(len(a['steps']),3)
        raw=json.loads((e/'step_001.json').read_text())
        self.assertEqual(raw['operation_origin'],'planned')
        self.assertEqual(raw['planned_operation_index'],0)
        self.assertTrue(raw['planned_scroll_preflight']['matched'])
        decisions=json.loads((e/'preparation_decisions.json').read_text())['decisions']
        self.assertTrue(decisions[0]['performed_by_planned_scroll'])
        self.assertEqual(json.loads((e/'capture_summary.json').read_text())['preparation_actions'],0)
        self.assertTrue(audit_capture(self.root,a['sample_id'])['capture_evidence_pass'])

    async def test_unclosable_overlay_is_rejected_without_hidden_action(self):
        with patch('webcollect.collect.execute') as execute:
            with self.assertRaisesRegex(ValueError,'页面准备被阻断'):
                await self.run_case(ARTICLE+CONFIRM+self.modal('<p>没有正常关闭入口，请勿点击页面广告</p>'))
            execute.assert_not_called()
        e=self.root/'evidence/S000001_sample_000001'
        self.assertTrue((e/'initial_capture.png').is_file())
        self.assertEqual(json.loads((e/'preparation_decisions.json').read_text())['decisions'][0]['kind'],'blocked')

    async def test_language_gate_retains_actual_initial_frame_before_rejection(self):
        english='<article><h1>Untranslated public article</h1><p>'+('This is an English article with an unrelated commercial banner. '*12)+'</p></article>'+CONFIRM
        with patch('webcollect.collect.execute') as execute:
            with self.assertRaisesRegex(ValueError,'中文字符比例'):
                await self.run_case(english)
            execute.assert_not_called()
        e=self.root/'evidence/S000001_sample_000001'
        self.assertTrue((e/'initial_capture.png').is_file())
        failure=json.loads((e/'eligibility_failure.json').read_text())
        self.assertLess(failure['actual'],0.70)
        self.assertEqual(failure['screenshot_sha256'],hashlib.sha256((e/'initial_capture.png').read_bytes()).hexdigest())

    async def test_unchanged_close_is_bounded_and_rejected(self):
        with self.assertRaisesRegex(ValueError,'停止重复点击'):
            await self.run_case(ARTICLE+CONFIRM+self.modal('<button id="close">关闭广告</button>'))
        e=self.root/'evidence/S000001_sample_000001'
        self.assertTrue((e/'step_001.json').is_file())
        self.assertFalse((e/'step_002.json').exists())
        decisions=json.loads((e/'preparation_decisions.json').read_text())['decisions']
        self.assertEqual(decisions[0]['after_step_id'],2)
        self.assertIn('停止重复点击',decisions[1]['blocked_reason'])

    async def test_zero_action_budget_does_not_click_then_discard_evidence(self):
        with patch('webcollect.collect.execute') as execute:
            with self.assertRaisesRegex(ValueError,'动作达到上限'):
                await self.run_case(ARTICLE+CONFIRM+self.modal(),settings={'mode':'auto','max_actions':0})
            execute.assert_not_called()
        self.assertTrue((self.root/'evidence/S000001_sample_000001/initial_capture.png').is_file())

if __name__=='__main__':unittest.main()
