"""Independent controlled pages; expected outcomes are hand-authored, not generated."""
import unittest
import hashlib
import json
from pathlib import Path
import tempfile
from playwright.async_api import async_playwright
from webcollect.content_preparation import assess_content, preparation_settings

PROSE = (
    "四季变化与校园观察活动。学生在春天观察枝叶，在夏天记录天气，在秋天比较果实，在冬天描述风景。"
    "教师引导学生把实际观察写成完整句子，并核对时间、地点和颜色，最后交流自己的发现和感受。"
)
ARTICLE = '<article><h1>校园四季观察课程</h1><p id="body">'+PROSE+'</p><p>'+PROSE+'</p></article>'
CSS = '<style>body{margin:0;font:20px/1.6 sans-serif}article{padding:20px}p{margin:16px 0}button{font-size:22px}</style>'
MODAL = '<div id="modal" role="dialog" style="position:fixed;left:10%;top:15%;width:80%;height:70%;background:white;z-index:20;border:1px solid">广告推广，扫码登录查看更多{close}</div>'


class Settings(unittest.TestCase):
    def test_default_is_bounded_auto(self):
        self.assertEqual(preparation_settings({}), {"mode":"auto","max_actions":6,"max_scrolls":4,"scroll_step_pixels":240,"close_hints":[]})

    def test_explicit_false_is_off(self):
        self.assertEqual(preparation_settings({"content_preparation":False})["mode"], "off")

    def test_invalid_or_unbounded_configuration_rejected(self):
        for value in [None, "article", {"mode":"force"}, {"max_actions":True}, {"max_scrolls":-1}, {"max_actions":21},
                      {"scroll_step_pixels":True},{"scroll_step_pixels":0},{"scroll_step_pixels":481}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                preparation_settings({"content_preparation":value})


class ContentPreparation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime=await async_playwright().start()
        self.browser=await self.runtime.chromium.launch(channel="chrome",headless=True)
        self.page=await self.browser.new_page(viewport={"width":800,"height":600})

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def check(self,html,mode="auto",operation=None,hints=None):
        await self.page.set_content('<!doctype html><meta charset="utf-8">'+CSS+html)
        before=await self.page.content()
        original=await self.page.evaluate('({scroll:[scrollX,scrollY],active:document.activeElement.tagName})')
        config={"mode":mode}
        if hints is not None:config["close_hints"]=hints
        result=await assess_content(self.page,{"content_preparation":config},operation)
        self.assertEqual(await self.page.content(),before,"Classifier must not mutate page")
        self.assertEqual(await self.page.evaluate('({scroll:[scrollX,scrollY],active:document.activeElement.tagName})'),original)
        self.assertTrue(result["DOM_was_not_modified"])
        return result

    def hint(self,root,selector="#icon"):
        p=Path(root)/"reviewed-control.json";p.write_text(json.dumps({"reviewed":"actual observed optional close icon","selector":selector}))
        return {"selector":selector,"evidence":{"path":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
                "description":"UNIT TEST ONLY independent evidence-bound icon case"}}

    async def test_bound_reviewed_image_close_hint_revalidated_inside_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            hint=self.hint(temp)
            r=await self.check(ARTICLE+MODAL.format(close='<img id="icon" src="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2230%22 height=%2230%22%3E%3Cpath d=%22M0,0 L30,30 M30,0 L0,30%22 stroke=%22black%22/%3E%3C/svg%3E" onclick="this.parentElement.remove()">'),hints=[hint])
            self.assertEqual(r["decision"]["action"],"close_overlay")
            self.assertEqual(r["decision"]["selector"],"#icon")
            self.assertEqual(r["obstruction"]["close"]["hint_evidence"]["sha256"],hint["evidence"]["sha256"])

    async def test_bound_hint_cannot_authorize_external_link_or_outside_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            hint=self.hint(temp)
            r=await self.check(ARTICLE+MODAL.format(close='<a id="icon" href="https://ad.example.invalid">×</a>'),hints=[hint])
            self.assertEqual(r["decision"]["action"],"blocked")
            r=await self.check(ARTICLE+MODAL.format(close='<span onclick="location.href=\'https://ad.example.invalid\'"><span id="icon" style="display:inline-block;width:30px;height:30px">×</span></span>'),hints=[hint])
            self.assertEqual(r["decision"]["action"],"blocked")
            r=await self.check('<button id="icon">关闭</button>'+ARTICLE+MODAL.format(close=''),hints=[hint])
            self.assertEqual(r["decision"]["action"],"blocked")

    async def test_missing_stale_or_unbound_close_hint_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            hint=self.hint(temp)
            for bad in [{"selector":"#icon"},{"selector":"#icon","evidence":{**hint["evidence"],"sha256":"0"*64}},
                        {"selector":"#icon","evidence":{**hint["evidence"],"path":str(Path(temp)/"missing.json")}}]:
                with self.subTest(hint=bad),self.assertRaises(ValueError):
                    preparation_settings({"content_preparation":{"close_hints":[bad]}})

    async def test_clean_article_ready_with_actual_excerpt(self):
        r=await self.check(ARTICLE)
        self.assertEqual(r["decision"]["action"],"ready")
        self.assertEqual(r["page_kind"],"article")
        self.assertTrue(r["body"]["visible"])
        self.assertIn("学生在春天观察枝叶",r["body"]["excerpt"])

    async def test_top_ad_banner_scrolls_in_small_explicit_increment(self):
        r=await self.check('<div style="height:900px;background:#ffc">广告推广横幅</div>'+ARTICLE)
        self.assertTrue(r["body"]["found"])
        self.assertFalse(r["body"]["visible"])
        self.assertEqual(r["decision"]["action"],"scroll_to_content")
        self.assertEqual(r["decision"]["direction"],"down")
        self.assertEqual(r["decision"]["distance"],240)
        self.assertEqual(await self.page.evaluate('scrollY'),0)

    async def test_modal_selects_actual_safe_close_without_executing_it(self):
        r=await self.check(ARTICLE+MODAL.format(close='<button id="close" type="button" onclick="this.parentElement.remove()">关闭</button>'))
        self.assertEqual(r["decision"]["action"],"close_overlay")
        self.assertEqual(r["decision"]["selector"],"#close")
        self.assertTrue(await self.page.locator("#modal").is_visible())
        self.assertFalse(r["body"]["visible"])

    async def test_unclosable_modal_blocks_even_with_article_underneath(self):
        r=await self.check(ARTICLE+MODAL.format(close='<button type="button">立即登录</button>'))
        self.assertEqual(r["decision"]["action"],"blocked")
        self.assertTrue(r["obstruction"]["present"])
        self.assertIsNone(r["obstruction"]["close"])

    async def test_fake_ad_close_link_is_not_clicked(self):
        r=await self.check(ARTICLE+MODAL.format(close='<a id="fake-close" href="https://ad.example.invalid/landing" target="_blank">关闭</a>'))
        self.assertEqual(r["decision"]["action"],"blocked")
        self.assertIsNone(r["obstruction"]["close"])
        self.assertTrue(r["obstruction"]["rejected_close_candidates"])

    async def test_consent_or_submit_button_not_a_close(self):
        for close in ['<button type="button">同意并关闭</button>',
                      '<form><button id="submit">关闭</button></form>',
                      '<button type="button" onclick="window.open(\'https://ad.example.invalid\')">关闭</button>']:
            with self.subTest(close=close):
                r=await self.check(ARTICLE+MODAL.format(close=close))
                self.assertEqual(r["decision"]["action"],"blocked")

    async def test_article_about_advertising_is_not_itself_rejected_as_an_ad(self):
        r=await self.check('<article><h1>广告行业治理报道</h1><p>广告行业治理正在推进。'+PROSE+'</p></article>',mode="article")
        self.assertTrue(r["body"]["visible"])
        self.assertEqual(r["decision"]["action"],"ready")

    async def test_unsemantic_long_sidebar_not_a_substitute_for_main_article(self):
        html='<div style="width:520px"><h1>校园四季观察课程</h1><div style="height:850px"></div><p>'+PROSE+'</p></div>'
        html+='<div style="position:absolute;left:610px;top:20px;width:170px"><p>'+PROSE+'</p></div>'
        r=await self.check(html,mode="article")
        self.assertTrue(r["body"]["found"])
        self.assertFalse(r["body"]["visible"])
        self.assertEqual(r["decision"]["action"],"scroll_to_content")
        self.assertEqual(r["body"]["excerpt"],"")

    async def test_main_heading_may_precede_nested_article(self):
        r=await self.check('<main><h1>校园四季观察课程</h1><article><p>'+PROSE+'</p></article></main>',mode="article")
        self.assertTrue(r["body"]["visible"])
        self.assertEqual(r["decision"]["action"],"ready")

    async def test_centered_heading_may_be_narrower_than_body_column(self):
        r=await self.check('<main><h1 style="width:300px;margin:auto">校园四季观察课程</h1><article><p>'+PROSE+'</p></article></main>',mode="article")
        self.assertTrue(r["body"]["visible"])
        self.assertEqual(r["decision"]["action"],"ready")

    async def test_short_paragraph_cut_at_viewport_bottom_is_not_ready(self):
        r=await self.check('<article><h1>校园四季观察课程</h1><p style="position:absolute;left:20px;top:520px;width:760px;margin:0">'+PROSE+'</p></article>',mode="article")
        self.assertFalse(r["body"]["visible"])
        self.assertFalse(r["body"]["full_paragraph_visible"])
        self.assertTrue(r["body"]["partial"])
        self.assertGreaterEqual(r["body"]["visible_character_count"],50)
        self.assertEqual(r["decision"]["action"],"scroll_to_content")

    async def test_tall_paragraph_uses_explicit_two_full_lines_partial_policy(self):
        r=await self.check('<article><h1>较长正文观察记录</h1><p>'+PROSE*12+'</p></article>',mode="article")
        self.assertEqual(r["decision"]["action"],"ready")
        self.assertTrue(r["body"]["visible"])
        self.assertTrue(r["body"]["partial"])
        self.assertTrue(r["body"]["long_block_policy_applied"])
        self.assertFalse(r["body"]["full_paragraph_visible"])
        self.assertGreaterEqual(r["body"]["complete_visible_lines"],2)

    async def test_single_text_numeric_field_calculate_button_and_output_is_tool(self):
        r=await self.check('<main><h1>长度换算工具</h1><input value="4.5"><button>转换</button><output>137.16 厘米</output><p>'+PROSE+'</p></main>')
        self.assertEqual(r["page_kind"],"tool")
        self.assertEqual(r["decision"]["action"],"not_applicable")

    async def test_single_search_box_with_news_body_is_not_calculation_tool(self):
        r=await self.check('<main><h1>校园观察新闻报道</h1><input type="search" value="2026"><button>搜索</button><p>'+PROSE+'</p></main>')
        self.assertEqual(r["page_kind"],"article")
        self.assertEqual(r["decision"]["action"],"ready")

    async def test_visible_dictionary_fields_are_preserved_without_prose(self):
        r=await self.check('<main><h1>學</h1><ul><li>总笔画：16画</li><li>部首：子，加13画</li><li>简化字：学</li></ul><div style="height:900px"></div><p>'+PROSE+'</p></main>')
        self.assertTrue(r["reference_content"]["found"])
        self.assertEqual(r["reference_content"]["kind"],"labeled_reference_fields")
        self.assertEqual(r["decision"]["action"],"not_applicable")

    async def test_actual_visible_reference_table_preserved(self):
        html='<main><h1>字形参考</h1><table><tr><th>参考字段名称</th><th>实际字段数值</th></tr><tr><td>总笔画与部首</td><td>十六画，子字部</td></tr></table><div style="height:900px"></div><p>'+PROSE+'</p></main>'
        r=await self.check(html)
        self.assertTrue(r["reference_content"]["found"])
        self.assertEqual(r["decision"]["action"],"not_applicable")

    async def test_reference_fields_and_unlandmarked_control_panel_are_not_prose(self):
        # Independent structure: a short dictionary heading with real reference
        # fields, beside a tall settings wrapper lacking p/aside/nav landmarks.
        # The lengthy display-control explanations are not article paragraphs.
        panel=('显示选项，可以选择文字大小、页面宽度以及界面颜色。'
               '这些选项用于调整当前画面的显示方式，请按个人阅读习惯选择。'
               '小字、标准字和大字属于字号；标准、宽属于宽度；自动、浅色和深色属于配色。')
        html='<main><h1>學</h1><div style="width:560px"><ul><li>总笔画：16画</li><li>部首：子，加13画</li><li>简化字：学</li></ul></div>'
        html+='<div id="panel" style="position:absolute;left:600px;top:70px;width:180px;height:3500px">'+panel
        html+='<label><input type="radio" name="size" style="display:none">小</label><label><input type="radio" name="size" style="display:none">标准</label>'
        html+='<label><input type="radio" name="width" style="display:none">宽</label></div></main>'
        r=await self.check(html)
        self.assertTrue(r["reference_content"]["found"])
        self.assertEqual(r["reference_content"]["kind"],"labeled_reference_fields")
        self.assertFalse(r["body"]["found"])
        self.assertEqual(r["body"]["paragraph_count"],0)
        self.assertEqual(r["body"]["excerpt"],"")
        self.assertEqual(r["decision"]["action"],"not_applicable")

    async def test_plain_div_prose_with_one_inline_control_remains_body(self):
        r=await self.check('<main><h1>校园四季观察课程</h1><div>'+PROSE+
                           '<button type="button">查看备注</button></div></main>',mode="article")
        self.assertTrue(r["body"]["found"])
        self.assertTrue(r["body"]["visible"])
        self.assertEqual(r["decision"]["action"],"ready")

    async def test_navigation_or_hidden_dictionary_fields_do_not_authorize_reference(self):
        fields='<ul><li>总笔画：16画</li><li>部首：子，加13画</li><li>简化字：学</li></ul>'
        for html in ['<main><h1>页面标题</h1><nav>'+fields+'</nav></main>',
                     '<main><h1>页面标题</h1><div style="display:none">'+fields+'</div></main>']:
            with self.subTest(html=html):
                r=await self.check(html)
                self.assertFalse(r["reference_content"]["found"])
                self.assertEqual(r["decision"]["action"],"blocked")

    async def test_overlay_priority_still_blocks_structured_reference(self):
        fields='<main><h1>字形参考</h1><ul><li>总笔画：16画</li><li>部首：子，加13画</li><li>简化字：学</li></ul></main>'
        r=await self.check(fields+MODAL.format(close=''))
        self.assertEqual(r["decision"]["action"],"blocked")

    async def test_prepared_reading_position_does_not_chase_body_again(self):
        r=await self.check('<div style="height:900px"></div>'+ARTICLE,
            operation={"action_type":"scroll","preserve_reading_position":True})
        self.assertEqual(r["decision"]["action"],"not_applicable")
        self.assertEqual(await self.page.evaluate('scrollY'),0)

    async def test_new_modal_still_closed_after_reading_position_prepared(self):
        r=await self.check(ARTICLE+MODAL.format(close='<button type="button" id="late-close">关闭</button>'),
            operation={"action_type":"scroll","preserve_reading_position":True})
        self.assertEqual(r["decision"]["action"],"close_overlay")
        self.assertEqual(r["decision"]["selector"],"#late-close")

    async def test_complete_never_inserts_a_preparation_action(self):
        for html in ['<div style="height:900px"></div>'+ARTICLE,
                     ARTICLE+MODAL.format(close='<button type="button">关闭</button>')]:
            with self.subTest(html=html):
                r=await self.check(html,operation={"action_type":"complete"})
                self.assertEqual(r["decision"]["action"],"not_applicable")

    async def test_tool_fields_not_scrolled_away(self):
        r=await self.check('<h1>长度换算</h1><input type="number" value="4.5"><select><option>英尺</option></select><button>换算</button><div style="height:900px"></div>'+ARTICLE)
        self.assertEqual(r["page_kind"],"tool")
        self.assertEqual(r["decision"]["action"],"not_applicable")
        self.assertEqual(await self.page.evaluate('scrollY'),0)

    async def test_listing_not_misclassified_as_body(self):
        links=''.join('<p><a href="#'+str(i)+'">课程目录与公开内容入口'+str(i)+'</a></p>' for i in range(8))
        r=await self.check('<h1>课程目录</h1>'+links)
        self.assertEqual(r["page_kind"],"listing")
        self.assertFalse(r["body"]["found"])
        self.assertEqual(r["decision"]["action"],"not_applicable")

    async def test_visible_next_navigation_target_preserved(self):
        r=await self.check('<a id="entry" href="#article">阅读课程正文</a><div style="height:900px"></div>'+ARTICLE,
                           operation={"action_type":"click","selector":"#entry"})
        self.assertEqual(r["decision"]["action"],"not_applicable")
        self.assertTrue(r["next_target"]["visible_hit"])

    async def test_heading_only_and_link_spam_are_not_prose(self):
        r=await self.check('<article><h1>只有标题没有正文</h1><p>'+''.join('<a href="#a">'+PROSE+'</a>' for _ in range(2))+'</p></article>',mode="article")
        self.assertFalse(r["body"]["found"])
        self.assertEqual(r["decision"]["action"],"blocked")

    async def test_hidden_paragraph_not_counted(self):
        r=await self.check('<article><h1>标题</h1><p style="display:none">'+PROSE+'</p></article>',mode="article")
        self.assertFalse(r["body"]["found"])
        self.assertEqual(r["decision"]["action"],"blocked")

    async def test_fixed_header_text_not_cited_as_body(self):
        r=await self.check('<header style="position:fixed;top:0;left:0;right:0;height:500px;background:white;z-index:30">固定导航</header>'+ARTICLE,mode="article")
        self.assertNotIn("学生在春天观察枝叶",r["body"]["excerpt"])
        self.assertFalse(r["body"]["visible"])
        self.assertEqual(r["decision"]["action"],"blocked")

    async def test_advertising_prose_not_treated_as_article(self):
        r=await self.check('<article><h1>推广信息</h1><p>广告推广。'+PROSE+'</p></article>',mode="article")
        self.assertFalse(r["body"]["found"])
        self.assertEqual(r["decision"]["action"],"blocked")

    async def test_explicit_off_returns_no_action_without_hiding_observation(self):
        r=await self.check(ARTICLE+MODAL.format(close='<button type="button">关闭</button>'),mode="off")
        self.assertTrue(r["obstruction"]["present"])
        self.assertEqual(r["decision"]["action"],"not_applicable")


if __name__=="__main__":
    unittest.main()
