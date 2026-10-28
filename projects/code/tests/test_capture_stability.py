"""Strict capture retries wait for natural stability, never edit dynamic pages."""
from io import BytesIO
import unittest
from unittest.mock import AsyncMock,patch

from PIL import Image
from playwright.async_api import async_playwright
from webcollect.browser import capture,fingerprint


def state(text):
    return {'screen_resolution':[16,12],'visible_text':text,'scroll':[0,0]}


def png():
    output=BytesIO()
    Image.new('RGB',(16,12),'white').save(output,format='PNG')
    return output.getvalue()


class CaptureBackoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_text_changes_only_accept_matching_pair(self):
        # Independent observations model three genuinely changing intervals,
        # followed by a stable final paragraph. Earlier pairs must be rejected.
        observations=[state('动画一'),state('动画二'),state('动画三'),state('动画四'),
                      state('动画五'),state('动画六'),state('正文自然稳定'),state('正文自然稳定')]
        image=png()
        with patch('webcollect.browser.observe',AsyncMock(side_effect=observations)) as observe, \
             patch('webcollect.browser.viewport_png',AsyncMock(return_value=(image,{'method':'test_viewport'}))) as viewport, \
             patch('webcollect.browser.asyncio.sleep',AsyncMock()) as sleep:
            result=await capture(object())
        self.assertEqual(result['state'],state('正文自然稳定'))
        self.assertEqual(result['png'],image)
        self.assertEqual((observe.await_count,viewport.await_count),(8,4))
        self.assertEqual([call.args[0] for call in sleep.await_args_list],[0.1,0.25,0.5])
        attempts=result['capture']['attempts']
        self.assertEqual([item['dom_stable'] for item in attempts],[False,False,False,True])
        self.assertEqual([item['mismatch_fields'] for item in attempts],
                         [['visible_text'],['visible_text'],['visible_text'],[]])
        self.assertEqual([item['delay_before_ms'] for item in attempts],[0,100,250,500])
        self.assertEqual([item['next_retry_delay_ms'] for item in attempts],[100,250,500,0])
        self.assertEqual(result['capture']['natural_wait_requested_ms'],850)
        self.assertEqual(attempts[-1]['before_fingerprint'],fingerprint(result['state']))
        self.assertEqual(attempts[-1]['before_fingerprint'],attempts[-1]['after_fingerprint'])

    async def test_continuous_text_changes_reject_after_default_eight_attempts(self):
        observations=[state(f'持续动画第{index}帧') for index in range(16)]
        with patch('webcollect.browser.observe',AsyncMock(side_effect=observations)) as observe, \
             patch('webcollect.browser.viewport_png',AsyncMock(return_value=(png(),{}))) as viewport, \
             patch('webcollect.browser.asyncio.sleep',AsyncMock()) as sleep:
            with self.assertRaisesRegex(ValueError,'拒绝保存') as caught:
                await capture(object())
        diagnostic=caught.exception.capture
        self.assertEqual((observe.await_count,viewport.await_count),(16,8))
        self.assertEqual(len(sleep.await_args_list),7)
        self.assertAlmostEqual(sum(call.args[0] for call in sleep.await_args_list),7.85)
        self.assertEqual(diagnostic['natural_wait_requested_ms'],7850)
        self.assertTrue(all(not item['dom_stable'] for item in diagnostic['attempts']))
        self.assertTrue(all(item['before_fingerprint']!=item['after_fingerprint'] for item in diagnostic['attempts']))
        self.assertEqual(diagnostic['attempts'][-1]['next_retry_delay_ms'],0)

    async def test_explicit_retry_count_and_larger_count_wait_budget(self):
        for retries,expected_wait in [(3,350),(20,8000)]:
            with self.subTest(retries=retries):
                observations=[state(str(index)) for index in range(retries*2)]
                with patch('webcollect.browser.observe',AsyncMock(side_effect=observations)) as observe, \
                     patch('webcollect.browser.viewport_png',AsyncMock(return_value=(png(),{}))) as viewport, \
                     patch('webcollect.browser.asyncio.sleep',AsyncMock()) as sleep:
                    with self.assertRaises(ValueError) as caught:
                        await capture(object(),retries=retries)
                self.assertEqual((observe.await_count,viewport.await_count),(retries*2,retries))
                self.assertEqual(len(caught.exception.capture['attempts']),retries)
                self.assertEqual(caught.exception.capture['natural_wait_requested_ms'],expected_wait)
                self.assertLessEqual(sum(call.args[0] for call in sleep.await_args_list),8.0)

    async def test_stable_page_needs_no_natural_wait(self):
        with patch('webcollect.browser.observe',AsyncMock(return_value=state('正文稳定'))), \
             patch('webcollect.browser.viewport_png',AsyncMock(return_value=(png(),{}))), \
             patch('webcollect.browser.asyncio.sleep',AsyncMock()) as sleep:
            result=await capture(object(),retries=3)
        sleep.assert_not_awaited()
        self.assertEqual(len(result['capture']['attempts']),1)
        self.assertEqual(result['capture']['natural_wait_requested_ms'],0)


class NativeCaptureStabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright=await async_playwright().start()
        self.browser=await self.playwright.chromium.launch(channel='chrome',headless=True)
        self.page=await self.browser.new_page(viewport={'width':640,'height':480})

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def test_short_native_animation_stabilizes_without_page_edits(self):
        await self.page.set_content('''<!doctype html><meta charset="utf-8">
            <p id="body">原始正文保持可见</p><p id="dynamic">动画准备</p>
            <script>
            window.animationStarted=performance.now();window.framesDrawn=0;
            function tick(){
                if(performance.now()-animationStarted<700){
                    document.getElementById('dynamic').textContent='自然动画帧'+(++framesDrawn);
                    requestAnimationFrame(tick);
                }else{
                    document.getElementById('dynamic').textContent='动画自然结束正文稳定';
                    window.animationEnded=true;
                }
            }requestAnimationFrame(tick);
            </script>''')
        result=await capture(self.page)
        self.assertTrue(await self.page.evaluate('window.animationEnded===true'))
        self.assertIn('动画自然结束正文稳定',result['state']['visible_text'])
        self.assertGreater(len(result['capture']['attempts']),1)
        self.assertTrue(result['capture']['attempts'][-1]['dom_stable'])
        self.assertTrue(any(not item['dom_stable'] for item in result['capture']['attempts'][:-1]))
        self.assertEqual(await self.page.evaluate('scrollY'),0)
        self.assertEqual(await self.page.locator('#body').inner_text(),'原始正文保持可见')
        self.assertEqual(await self.page.locator('#dynamic').get_attribute('style'),None)

    async def test_continuous_native_animation_remains_rejected(self):
        await self.page.set_content('''<!doctype html><meta charset="utf-8">
            <p id="dynamic">持续动画准备</p><script>
            window.framesDrawn=0;
            function tick(){
                document.getElementById('dynamic').textContent='持续自然动画帧'+(++framesDrawn);
                requestAnimationFrame(tick);
            }requestAnimationFrame(tick);
            </script>''')
        with self.assertRaisesRegex(ValueError,'拒绝保存') as caught:
            await capture(self.page,retries=3)
        self.assertEqual(len(caught.exception.capture['attempts']),3)
        self.assertTrue(all(not item['dom_stable'] for item in caught.exception.capture['attempts']))
        previous=await self.page.evaluate('framesDrawn')
        await self.page.wait_for_timeout(50)
        self.assertGreater(await self.page.evaluate('framesDrawn'),previous)
        self.assertEqual(await self.page.locator('#dynamic').get_attribute('style'),None)
        self.assertEqual(await self.page.evaluate('scrollY'),0)


if __name__=='__main__':unittest.main()
