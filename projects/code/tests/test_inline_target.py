"""Click actual visible text, not whitespace inside a wrapped link's union box."""
import unittest
from playwright.async_api import async_playwright
from webcollect.browser import capture,prepare_action,execute


class InlineTargetTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrapped_link_client_rectangle_is_real_click_target(self):
        async with async_playwright() as p:
            browser=await p.chromium.launch(channel='chrome',headless=True)
            try:
                page=await browser.new_page(viewport={'width':640,'height':480})
                await page.set_content('<html lang="zh-CN"><meta charset="utf-8"><div style="line-height:100px;font-size:32px"><a id="wrapped" href="#done">第一行<br>第二行</a></div></html>')
                gap=await page.locator('#wrapped').evaluate('(n)=>{const r=n.getBoundingClientRect();const h=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);return !h||!(h===n||n.contains(h));}')
                self.assertTrue(gap,'fixture must expose center-of-union whitespace')
                observed=await capture(page,'#wrapped')
                args,_=prepare_action(observed['state'],{'action_type':'click'})
                self.assertTrue(observed['state']['target']['hit_valid'])
                await execute(page,'click',args,{'settle_ms':0})
                # Mouse dispatch does not await an asynchronous fragment
                # navigation commit. Observe the result before asserting it.
                await page.wait_for_url('**#done',timeout=2000)
                self.assertTrue(page.url.endswith('#done'))
                await page.evaluate("document.body.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;background:white\">遮挡</div>')")
                covered=await capture(page,'#wrapped')
                with self.assertRaises(ValueError):prepare_action(covered['state'],{'action_type':'click'})
            finally:await browser.close()
