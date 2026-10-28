"""Native Chrome fallback reads actual pixels; no page/font edits or resizing."""
from io import BytesIO
import unittest
from unittest.mock import AsyncMock,patch
from PIL import Image,ImageChops
from playwright.async_api import async_playwright,TimeoutError
from webcollect.browser import capture


class FontCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_font_wait_fallback_preserves_css_pixels_and_page(self):
        async with async_playwright() as p:
            browser=await p.chromium.launch(channel='chrome',headless=True)
            try:
                for dpr in [1,2]:
                    context=await browser.new_context(viewport={'width':640,'height':480},device_scale_factor=dpr)
                    page=await context.new_page()
                    await page.set_content('<html lang="zh-CN"><meta charset="utf-8"><body style="margin:0"><div style="height:600px;background:#ddf">上文</div><p>真实浏览器当前视口文字</p><div style="height:600px;background:#fdd">下文</div></body></html>')
                    await page.evaluate('scrollTo(0,550)')
                    normal=await capture(page)
                    dom=await page.content()
                    with patch.object(page,'screenshot',AsyncMock(side_effect=TimeoutError('taking page screenshot; waiting for fonts to load...'))):
                        fallback=await capture(page)
                    self.assertEqual(fallback['state'],normal['state'])
                    self.assertEqual(await page.content(),dom)
                    self.assertEqual(fallback['capture']['screenshot']['method'],'chrome_rendered_viewport')
                    actual=Image.open(BytesIO(fallback['png'])).convert('RGB')
                    expected=Image.open(BytesIO(normal['png'])).convert('RGB')
                    self.assertEqual(actual.size,(640,480))
                    self.assertIsNone(ImageChops.difference(actual,expected).getbbox())
                    restored=await capture(page)
                    self.assertEqual(restored['state'],normal['state'])
                    self.assertIsNone(ImageChops.difference(Image.open(BytesIO(restored['png'])).convert('RGB'),expected).getbbox())
                    await context.close()
            finally:await browser.close()

    async def test_unrelated_screenshot_error_is_not_masked(self):
        from webcollect.browser import viewport_png
        page=AsyncMock();page.screenshot.side_effect=TimeoutError('Page closed')
        with self.assertRaises(TimeoutError):await viewport_png(page)
        page.context.new_cdp_session.assert_not_called()
