"""Read-only text Range evidence must exclude actual overlays in local HTML."""
import os
from pathlib import Path
import unittest
from playwright.async_api import async_playwright

SNAPSHOT = Path(os.environ.get("WEBCOLLECT_SNAPSHOT_UNDER_TEST", str(Path(__file__).resolve().parents[1] / "webcollect/snapshot.js"))).read_text()


class TextOcclusion(unittest.IsolatedAsyncioTestCase):
    async def test_numeric_source_full_stops_do_not_create_truncated_sentences(self):
        line='位置东经118。 30分52秒，北纬31。29分35秒，墓葬海拔12。8米。'
        state=await self.observe('<p>'+line+'</p>')
        sentences=[s for b in state['text_blocks'] for s in b['complete_sentences']]
        self.assertIn(line,sentences)
        self.assertFalse(any(s.endswith(('118。','31。','12。')) for s in sentences))
        clipped=await self.observe('<p style="position:absolute;left:10px;top:440px;width:150px">'+line+'</p>')
        sentences=[s for b in clipped['text_blocks'] for s in b['complete_sentences']]
        self.assertNotIn(line,sentences,'A complete source sentence must also be fully painted inside the viewport')

    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(channel="chrome", headless=True)
        self.page = await self.browser.new_page(viewport={"width": 640, "height": 480})

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def observe(self, html, selector=None):
        await self.page.set_content('<!doctype html><meta charset="utf-8"><style>body{margin:0;font-size:20px}</style>' + html)
        before = await self.page.content()
        result = await self.page.evaluate(SNAPSHOT, {"selector": selector, "index": 0})
        self.assertEqual(await self.page.content(), before, "Observer must not mutate DOM or CSS")
        return result

    async def test_fixed_header_hides_first_line_but_not_next_line(self):
        state = await self.observe('<p style="position:absolute;left:20px;top:5px;margin:0;white-space:pre;line-height:32px">被标题栏遮住的上行\n未遮挡下行真实可见</p><header style="position:fixed;left:0;top:0;width:640px;height:35px;background:white;z-index:10">固定新闻标题</header>')
        self.assertNotIn("被标题栏遮住的上行", state["visible_text"])
        self.assertIn("未遮挡下行真实可见", state["visible_text"])
        self.assertIn("固定新闻标题", state["visible_text"])

    async def test_central_modal_excludes_covered_body_text(self):
        state = await self.observe('<p style="position:absolute;left:120px;top:140px">模态覆盖正文不可引用</p><p style="position:absolute;left:20px;top:330px">模态外正文真实可见</p><div style="position:fixed;left:80px;top:100px;width:440px;height:180px;background:white;z-index:10">登录推广遮罩</div>')
        self.assertNotIn("模态覆盖正文不可引用", state["visible_text"])
        self.assertIn("模态外正文真实可见", state["visible_text"])
        self.assertIn("登录推广遮罩", state["visible_text"])

    async def test_sibling_overlay_inside_same_parent_is_not_text_owner(self):
        state = await self.observe('<div style="position:absolute;left:20px;top:40px;width:550px;height:120px;line-height:30px">兄弟遮罩挡住的文字<span style="position:absolute;left:0;top:0;width:420px;height:32px;background:white;z-index:9">兄弟遮罩标题</span><span style="position:absolute;left:0;top:60px">容器下方可见文字</span></div>')
        self.assertNotIn("兄弟遮罩挡住的文字", state["visible_text"])
        self.assertIn("兄弟遮罩标题", state["visible_text"])
        self.assertIn("容器下方可见文字", state["visible_text"])

    async def test_nested_text_link_and_form_values_remain_visible(self):
        state = await self.observe('<p>普通<span>嵌套<strong>文字</strong></span>与<a id="link" href="#next">链接<span>文字</span></a></p><label for="query">查询词</label><input id="query" value="公开输入值"><textarea>中文多行值</textarea>', "#link")
        for text in ["普通", "嵌套", "文字", "链接", "查询词", "公开输入值", "中文多行值"]:
            self.assertIn(text, state["visible_text"])
        self.assertTrue(state["target"]["hit_valid"])

    async def test_unicode_codepoints_and_combining_marks_not_rewritten(self):
        state = await self.observe('<p>原样字符𠮷、学、e\u0301、中文</p>')
        self.assertIn("原样字符𠮷、学、e\u0301、中文", state["visible_text"])

    async def test_partly_covered_control_value_is_not_claimed_fully_visible(self):
        state = await self.observe('<input style="position:absolute;left:20px;top:20px;width:300px;height:40px" value="遮挡的输入值不能引用"><div style="position:absolute;left:20px;top:20px;width:90px;height:48px;background:white;z-index:9">遮罩</div><input style="position:absolute;left:20px;top:120px;width:300px;height:40px" value="未遮挡输入值保留">')
        self.assertNotIn("遮挡的输入值不能引用", state["visible_text"])
        self.assertIn("未遮挡输入值保留", state["visible_text"])

    async def test_fractional_inline_overflow_box_keeps_visible_final_punctuation(self):
        # Actual First范文 uses an intrinsic inline-block with hidden overflow.
        # Its fractional width rounds down in clientWidth although the complete
        # closing glyph is still painted (exact width depends on font fallback).
        state = await self.observe('<a id="lesson" href="#lesson" title="四季 教案（精选12篇）" style="display:inline-block;overflow:hidden;font:14px/28px Arial,SimSun">四季 教案（精选12篇）</a>', '#lesson')
        metrics = await self.page.locator('#lesson').evaluate('(n)=>({width:n.getBoundingClientRect().width,client:n.clientWidth})')
        self.assertGreater(metrics['width'], metrics['client'], 'Fixture must expose fractional clientWidth rounding')
        self.assertIn('四季 教案（精选12篇）', state['visible_text'])
        target = next(e for e in state['elements'] if e['element_id'] == state['target']['element_id'])
        self.assertEqual(target['text'], '四季 教案（精选12篇）')
        self.assertTrue(state['target']['hit_valid'])

    async def test_real_fractional_overflow_still_excludes_clipped_final_glyph(self):
        state = await self.observe('<div style="width:100.46875px;overflow:hidden"><a id="lesson" href="#lesson" style="display:inline-block;white-space:nowrap;font:14px/28px Arial,SimSun">四季 教案（精选12篇）</a></div>', '#lesson')
        self.assertNotIn('四季 教案（精选12篇）', state['visible_text'])
        self.assertNotIn('）', state['visible_text'])

    async def test_fractional_link_final_glyph_under_overlay_stays_excluded(self):
        state = await self.observe('<div style="position:absolute;left:20px;top:60px"><a id="lesson" href="#lesson" style="display:inline-block;overflow:hidden;font:14px/28px Arial,SimSun">四季 教案（精选12篇）</a><span style="position:absolute;right:0;top:0;width:15px;height:28px;background:white;z-index:10">挡</span></div>', '#lesson')
        self.assertNotIn('四季 教案（精选12篇）', state['visible_text'])
        self.assertNotIn('）', state['visible_text'])
        self.assertIn('挡', state['visible_text'])

    async def test_transparent_padded_inline_link_does_not_erase_following_text(self):
        state = await self.observe('<div style="padding:64px 0 0 24px;font:16px/20px Arial,sans-serif"><div style="position:relative;z-index:1;margin-bottom:16px"><a href="#one" style="padding:32px 0">准则 1</a></div><div style="font:24px/30px Arial,sans-serif">互联网是现代生活不可分割的一部分。</div></div>')
        self.assertIn('互联网是现代生活不可分割的一部分。', state['visible_text'])

    async def test_adjacent_fractional_inline_link_boundaries_keep_original_characters(self):
        state = await self.observe('<p style="margin-left:264.328125px;font:16px/26px sans-serif">末年，医圣<a href="#doctor">张仲景</a>在家乡<a href="#river">白河</a><br><a href="#region">新疆</a><a href="#city">吐鲁番</a><a href="#tomb">阿斯塔那</a></p>')
        for text in ['末年，医圣','在家乡','新疆','吐鲁番']:
            self.assertIn(text, state['visible_text'])

    async def test_font_cell_outside_tight_line_clip_keeps_complete_visible_ink(self):
        state = await self.observe('<div style="position:absolute;left:24px;top:100px;width:234px;height:42px;overflow:hidden;font:700 16px/21px sans-serif">在职党必学：体验营优先录取保姆级政策全解析</div>')
        self.assertIn('在职党必学：体验营优先录取保姆级政策全解析', state['visible_text'])

    async def test_actual_ink_clipped_by_overflow_is_still_excluded(self):
        state = await self.observe('<div style="position:absolute;left:24px;top:100px;width:234px;height:8px;overflow:hidden;font:700 16px/21px sans-serif">课程真正裁掉字形不可引用</div>')
        self.assertNotIn('课程真正裁掉字形不可引用', state['visible_text'])

    async def test_painted_padded_inline_is_not_treated_as_transparent(self):
        state = await self.observe('<div style="padding:64px 0 0 24px;font:16px/20px Arial,sans-serif"><div style="position:relative;z-index:1;margin-bottom:16px"><a href="#one" style="padding:32px 0;background:white">准则标题覆盖区</a></div><div style="font:24px/30px Arial,sans-serif">互联网被有背景链接遮挡。</div></div>')
        self.assertNotIn('互联网被有背景链接遮挡。', state['visible_text'])

    async def test_transparent_positioned_overlay_remains_conservatively_excluded(self):
        state = await self.observe('<p style="position:absolute;left:20px;top:80px">不推定透明定位遮罩下文字</p><span style="position:absolute;left:20px;top:80px;width:500px;height:60px;z-index:9"></span>')
        self.assertNotIn('不推定透明定位遮罩下文字', state['visible_text'])

    async def test_text_blocks_preserve_inline_reading_order_and_actual_edges(self):
        state = await self.observe('<p style="position:absolute;top:-24px;margin:0;line-height:32px">首行滚到视口之外<br>医圣<a href="#doctor">张仲景</a>在家乡<a href="#river">白河</a>。</p><p style="position:absolute;top:440px;margin:0;line-height:32px">完整首行句。<br>末行滚到视口之外</p><p style="position:absolute;top:200px;margin:0">深，雨洗<span>凝愁！</span></p>')
        blocks = state['text_blocks']
        clipped_start = next(b for b in blocks if '医圣' in b['visible_text'])
        self.assertEqual(clipped_start['visible_text'], '医圣张仲景在家乡白河。')
        self.assertFalse(clipped_start['starts_visible'])
        self.assertTrue(clipped_start['ends_visible'])
        clipped_end = next(b for b in blocks if '完整首行句' in b['visible_text'])
        self.assertTrue(clipped_end['starts_visible'])
        self.assertFalse(clipped_end['ends_visible'])
        complete = next(b for b in blocks if '凝愁' in b['visible_text'])
        self.assertEqual(complete['visible_text'], '深，雨洗凝愁！')
        self.assertTrue(complete['starts_visible'])
        self.assertTrue(complete['ends_visible'])

    async def test_text_blocks_do_not_include_hidden_inline_edges_or_modal_text(self):
        state = await self.observe('<p style="position:absolute;left:20px;top:20px"><span style="display:none">隐藏开头</span>真正可见的中间文字<span style="visibility:hidden">隐藏结尾</span></p><p style="position:absolute;left:100px;top:200px">被模态盖住的整个段落</p><div style="position:absolute;left:80px;top:190px;width:500px;height:100px;background:white;z-index:10">模态</div>')
        self.assertEqual(len(state['text_blocks']),1)
        block=state['text_blocks'][0]
        self.assertEqual(block['visible_text'],'真正可见的中间文字')
        self.assertFalse(block['starts_visible'])
        self.assertFalse(block['ends_visible'])

    async def test_noninteractive_images_keep_geometry_and_only_real_attribute_names(self):
        state = await self.observe('<img id="plain" width="300" height="160" src="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'300\' height=\'160\'%3E%3Crect width=\'300\' height=\'160\' fill=\'blue\'/%3E%3C/svg%3E"><img width="200" height="100" alt="真实替代属性不代表像素正文" src="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\'/%3E">')
        images=[e for e in state['elements'] if e['element_type']=='image']
        self.assertEqual(len(images),2)
        self.assertEqual(images[0]['text'],'')
        self.assertEqual(images[0]['native_role'],'img')
        self.assertEqual(images[0]['bbox'],[0,0,300,160])
        self.assertEqual(images[1]['text'],'真实替代属性不代表像素正文')
        self.assertNotIn('真实替代属性不代表像素正文',state['visible_text'])

    async def test_fully_covered_image_is_excluded_but_partly_visible_image_remains(self):
        state = await self.observe('<img style="position:absolute;left:20px;top:20px" width="200" height="100"><img style="position:absolute;left:20px;top:200px" width="200" height="100"><div style="position:absolute;left:0;top:0;width:260px;height:140px;background:white;z-index:10">完整遮挡</div><div style="position:absolute;left:20px;top:200px;width:70px;height:100px;background:white;z-index:10">部分</div>')
        images=[e for e in state['elements'] if e['element_type']=='image']
        self.assertEqual(len(images),1)
        self.assertEqual(images[0]['bbox'],[20,200,220,300])


if __name__ == "__main__":
    unittest.main()
