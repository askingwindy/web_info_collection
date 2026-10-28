"""Independent local popup timing fixtures; never actual collection data."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from playwright.async_api import async_playwright
from webcollect.collect import collect_one

START = 'https://popup-fixture.invalid/start'
ARTICLE = 'https://popup-fixture.invalid/article'


class PopupNavigation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(channel='chrome', headless=True)
        self.context = await self.browser.new_context(viewport={'width':1280,'height':720}, device_scale_factor=1)
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)

    async def asyncTearDown(self):
        await self.browser.close(); await self.runtime.stop(); self.temp.cleanup()

    def operation(self, selector, **execution):
        return {'action_type':'click', 'selector':selector, 'arguments':{},
                'goal':'核对实际可见页面的结果', 'rationale':'使用本地合成夹具验证真实弹窗时序',
                'expected':'显示对应页面结果', 'execution':{'settle_ms':0, **execution}}

    async def run_fixture(self, start, operations):
        async def route(request):
            if request.request.url == START:
                await request.fulfill(content_type='text/html; charset=utf-8', body='<meta charset="utf-8">'+start)
            elif request.request.url == ARTICLE:
                await asyncio.sleep(0.65)
                await request.fulfill(content_type='text/html; charset=utf-8', body='<meta charset="utf-8"><h1>延迟打开的真实新页面</h1><button id="confirm" onclick="document.getElementById(\'result\').textContent=\'核对成功\'">确认报道内容</button><p id="result">等待核对</p>')
            else:
                await request.abort()
        await self.context.route('https://popup-fixture.invalid/**', route)
        sid = 'S000001_sample_000001'; sample = self.root/'samples'/sid; evidence = self.root/'evidence'/sid
        task = {'initial_url':START, 'initial_settle_ms':0, 'stop_when_final':False,
                'operations':operations, 'final_assertions':[{'selector':'#result','contains':'核对成功'}],
                'final_result':'结果显示核对成功', 'completion_judgement':'末图可见核对成功',
                'instruction':'独立本地弹窗时序测试，不可作为实际交付数据',
                'task_type':['数据查看'], 'app_name':'本地弹窗夹具', 'task_id':'popup-unit-only'}
        annotation = await collect_one(self.context, task, sample, evidence, {'sample_id':sid})
        return annotation, evidence

    async def test_delayed_blank_anchor_waits_before_next_operation(self):
        html = '<h1>当前测试首页</h1><a id="open" target="_blank" href="/article" onclick="event.preventDefault();setTimeout(()=>window.open(this.href,\'_blank\'),350)">打开延迟报道</a><p>点击后新页面需要等待网络响应才能出现，禁止继续对原页面操作</p>'
        annotation, evidence = await self.run_fixture(html, [self.operation('#open'), self.operation('#confirm')])
        first = json.loads((evidence/'step_001.json').read_text()); second = json.loads((evidence/'step_002.json').read_text())
        self.assertEqual(first['opened_page_url'], ARTICLE)
        self.assertEqual(second['state']['url'], ARTICLE)
        self.assertEqual(annotation['steps'][1]['action']['target_text'], '确认报道内容')

    async def test_explicit_popup_wait_for_button_is_registered_before_click(self):
        html = '<h1>当前测试首页</h1><button id="open" onclick="setTimeout(()=>window.open(\'/article\',\'_blank\'),350)">打开延迟报道</button>'
        _, evidence = await self.run_fixture(html, [self.operation('#open', wait_popup=True), self.operation('#confirm')])
        self.assertEqual(json.loads((evidence/'step_001.json').read_text())['opened_page_url'], ARTICLE)

    async def test_same_page_click_does_not_wait_for_unrelated_popup(self):
        html = '<h1>当前测试首页</h1><a id="confirm" href="#same" onclick="document.getElementById(\'result\').textContent=\'核对成功\'">确认本页内容</a><p id="result">等待核对</p>'
        annotation, evidence = await asyncio.wait_for(self.run_fixture(html, [self.operation('#confirm')]), timeout=5)
        self.assertNotIn('opened_page_url', json.loads((evidence/'step_001.json').read_text()))
        self.assertEqual(annotation['steps'][-1]['action']['action_type'], 'complete')


if __name__ == '__main__':
    unittest.main(verbosity=2)
