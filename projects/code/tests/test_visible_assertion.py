import unittest
from playwright.async_api import async_playwright
from webcollect.collect import assert_state
class VisibleAssertion(unittest.IsolatedAsyncioTestCase):
 async def test_visible_excerpt_allowed_but_hidden_or_offscreen_text_rejected(self):
  async with async_playwright() as p:
   b=await p.chromium.launch(channel='chrome',headless=True);page=await b.new_page(viewport={'width':640,'height':480});await page.set_content('<div style="height:1200px"><p>当前可见的目标段落</p><p style="display:none">隐藏词语不可作为证据</p><p style="position:absolute;top:1000px">视口外目标</p></div>')
   good=await assert_state(page,[{'visible_text':'当前可见的目标段落'}]);self.assertTrue(good[0]['passed'])
   for text in ['隐藏词语不可作为证据','视口外目标']:
    with self.assertRaises(ValueError):await assert_state(page,[{'visible_text':text}])
   await b.close()
