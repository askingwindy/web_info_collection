"""Real Chrome/local fixtures; never production samples or human approval."""
import json
from pathlib import Path
import tempfile
import unittest

from playwright.async_api import async_playwright
from webcollect.browser import capture, prepare_action
from webcollect.collect import collect_one
from webcollect.task_contract import PLAN_SCHEMA
from test_m4_task_contract import m4_task


class M4BrowserContract(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime=await async_playwright().start()
        self.browser=await self.runtime.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':640,'height':480})
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)

    async def asyncTearDown(self):
        await self.browser.close();await self.runtime.stop();self.temp.cleanup()

    async def test_five_pixel_option_sliver_is_rejected_despite_hit_test(self):
        page=await self.context.new_page()
        await page.set_content('<style>body{margin:0}#clip{position:absolute;top:50px;left:30px;height:5px;width:180px;overflow:hidden}button{width:160px;height:40px;font:20px sans-serif}</style><div id="clip"><button id="target">厘米</button></div>')
        state=(await capture(page,'#target'))['state']
        self.assertTrue(state['target']['hit_valid'])
        self.assertEqual(state['target']['bbox'][3]-state['target']['bbox'][1],5)
        with self.assertRaisesRegex(ValueError,'M4_TARGET_LABEL_UNREADABLE'):
            prepare_action(state,{'action_type':'click','evidence':{'target_label':'厘米'}})

    async def test_one_pixel_border_clip_does_not_reject_fully_readable_label(self):
        page=await self.context.new_page()
        await page.set_content('<style>body{margin:0}#clip{position:absolute;top:40px;left:30px;width:199px;height:59px;overflow:hidden}button{width:200px;height:60px;font:20px sans-serif}</style><div id="clip"><button id="target">核对结果</button></div>')
        state=(await capture(page,'#target'))['state']
        args,element=prepare_action(state,{'action_type':'click','evidence':{'target_label':'核对结果'}})
        self.assertTrue(element['clickable']);self.assertIn('x',args)

    async def test_aria_only_name_does_not_become_visible_label_but_real_input_label_works(self):
        page=await self.context.new_page()
        await page.set_content('<button id="icon" aria-label="关闭" style="width:50px;height:40px">×</button><label for="input">测试输入</label><input id="input">')
        state=(await capture(page,'#icon'))['state']
        self.assertEqual(state['target']['text'],'关闭')
        with self.assertRaisesRegex(ValueError,'UNREADABLE'):
            prepare_action(state,{'action_type':'click','evidence':{'target_label':'关闭'}})
        state=(await capture(page,'#input'))['state']
        prepare_action(state,{'action_type':'click','evidence':{'target_label':'测试输入'}})

    async def test_required_start_pause_execute_when_literal_final_text_already_exists(self):
        html='<meta charset="utf-8"><h1>五分钟</h1><p id="state">等待开始</p><button id="start" onclick="document.querySelector(\'#state\').textContent=\'已开始\'">开始</button><button id="pause" onclick="document.querySelector(\'#state\').textContent=\'已暂停\'">暂停</button>'
        await self.context.route('https://example.org/**',lambda route:route.fulfill(content_type='text/html',body=html))
        task={**m4_task(),'_plan_schema_version':PLAN_SCHEMA,'initial_settle_ms':0,'content_preparation':False}
        sample=self.root/'sample';evidence=self.root/'evidence'
        annotation=await collect_one(self.context,task,sample,evidence,{'sample_id':'fixture-only'})
        self.assertEqual([s['action']['action_type'] for s in annotation['steps']],['click','click','complete'])
        contract=json.loads((evidence/'task_contract.json').read_text())
        self.assertEqual(contract['executed_operation_ids'],['pause','start'])
        self.assertEqual(contract['machine_status'],'PASS');self.assertEqual(contract['semantic_status'],'REVIEW_REQUIRED')
        self.assertEqual(len(contract['review_binding']['evidence_sha256']),6)
        start=json.loads((evidence/'step_001.json').read_text())
        self.assertNotIn('postconditions_saved_frame',start)
        later=json.loads((evidence/'step_001_postconditions.json').read_text())
        self.assertEqual(later['binding']['image_path'],'images/step_002.png')
        self.assertTrue(later['assertions'][0]['passed'])
        import hashlib
        self.assertEqual(later['source_raw_sha256'],hashlib.sha256((evidence/'step_001.json').read_bytes()).hexdigest())
        narrative=json.loads((evidence/'step_001_narrative.json').read_text())
        self.assertNotIn('narrative_evidence',start)
        self.assertEqual(narrative['source_raw_sha256'],later['source_raw_sha256'])
        self.assertEqual(narrative['after_frame']['image_path'],'images/step_002.png')


if __name__=='__main__':unittest.main()
