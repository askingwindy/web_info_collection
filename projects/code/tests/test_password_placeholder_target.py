"""Real HMAC empty-password shape, with only locally authored browser fixtures."""
import unittest
from playwright.async_api import async_playwright
from webcollect.browser import observe, prepare_action, execute
from webcollect.collect import assert_state

HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>
body{margin:40px;font:14px Arial,sans-serif;background:white;color:#343a40}
.input-group{display:flex;width:570px}.input-group-prepend,.input-group-append{display:flex}
.input-group-text{box-sizing:border-box;display:flex;align-items:center;width:70px;padding:6px 10px;background:#e9ecef}
#pwd{box-sizing:border-box;width:450px;height:35px;padding:6px 12px;border:1px solid #ced4da;background:#fff;color:#495057;font:14px/21px Arial,sans-serif}
#pwd::placeholder{color:#6c757d;opacity:1}button{height:35px;width:42px}#remote{position:absolute;top:200px;left:700px}
</style><div class="input-group"><div class="input-group-prepend"><span class="input-group-text"><i class="fas fa-key"></i> 密钥</span></div>
<input type="password" id="pwd" placeholder="请输入密钥" autocomplete="new-password">
<div class="input-group-append"><button type="button" title="显示/隐藏密钥"><i class="fas fa-eye"></i></button></div></div>
<span id="remote">请输入密钥</span></html>'''
LABEL = '请输入密钥'
# Reproduces the captured real Bootstrap footprint, including its append button
# overlapping the input's shared right border by 1 CSS px. The original PNG and
# computed styles are retained in hmac-password-real-diagnostic-r01.
REAL_CSS_HTML = HTML.replace('</style>', """
body{margin:0;font-family:-apple-system,"system-ui","Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif}
.input-group{position:absolute;left:58px;top:253.84375px;width:560px;height:36px}
.input-group-prepend{position:absolute;left:0;top:0;width:72px;height:36px}
.input-group-text{width:72px;height:36px;border:1px solid #ced4da}
#pwd{position:absolute;left:71px;top:0;width:448.25px;height:35px;font-family:inherit;overflow:clip}
#pwd::placeholder{color:#7c8791}
.input-group-append{position:absolute;left:518.25px;top:0;width:41.75px;height:36px}
button{box-sizing:border-box;width:41.75px;height:36px}
</style>""")


class PasswordPlaceholderTargetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(channel='chrome', headless=True)
        self.page = await self.browser.new_page(viewport={'width': 1280, 'height': 720})
        await self.page.set_content(HTML)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def test_real_three_branch_icon_group_empty_password_placeholder_is_readable_target(self):
        state = await observe(self.page, '#pwd', assertions=[{'selector': '#pwd', 'value': ''}])
        sources = state['target']['visible_label_evidence']
        self.assertIn({'kind': 'visible_placeholder', 'text': LABEL}, sources)
        self.assertFalse(any(row['kind'] == 'rendered_adjacent_input_group_label' for row in sources))
        args, _ = prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': LABEL}})
        self.assertFalse(next(v for v in state['values'] if v['element_id'] == state['target']['element_id'])['value_visible'])
        self.assertFalse(state['assertion_targets'][0]['value_visible'])
        with self.assertRaisesRegex(ValueError, '完整值未在实际视口中可见'):
            await assert_state(None, [{'selector': '#pwd', 'value': ''}], captured_state=state)
        await execute(self.page, 'click', args, {'settle_ms': 0})
        focused = await observe(self.page, '#pwd')
        typed, _ = prepare_action(focused, {'action_type': 'type', 'arguments': {'text': '公开示例密钥'},
                                           'evidence': {'target_label': LABEL}})
        self.assertEqual(typed['text'], '公开示例密钥')

    async def test_saved_real_css_shared_border_does_not_hide_full_placeholder_glyphs(self):
        await self.page.set_content(REAL_CSS_HTML)
        footprint = await self.page.locator('#pwd').evaluate("""n=>{const r=n.getBoundingClientRect(),x=r.right-1,y=(r.top+r.bottom)/2,h=document.elementFromPoint(x,y);return {input:r.toJSON(),shared_border_owner:h?.tagName,shared_border_is_target:h===n};}""")
        self.assertEqual(footprint['input']['width'], 448.25)
        self.assertFalse(footprint['shared_border_is_target'])
        self.assertEqual(footprint['shared_border_owner'], 'BUTTON')
        state = await observe(self.page, '#pwd')
        self.assertIn({'kind': 'visible_placeholder', 'text': LABEL}, state['target']['visible_label_evidence'])
        prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': LABEL}})
        await self.page.evaluate("document.body.insertAdjacentHTML('beforeend','<div style=\"position:absolute;left:150px;top:264px;width:12px;height:17px;background:white;z-index:10\"></div>')")
        covered = await observe(self.page, '#pwd')
        self.assertFalse(any(row['kind'] == 'visible_placeholder' for row in covered['target']['visible_label_evidence']))
        with self.assertRaisesRegex(ValueError, 'M4_TARGET_LABEL_UNREADABLE'):
            prepare_action(covered, {'action_type': 'click', 'evidence': {'target_label': LABEL}})

    async def test_ordinary_empty_placeholder_uses_the_same_full_glyph_readability_guard(self):
        for width in ('2px', '45px'):
            await self.page.set_content(HTML)
            await self.page.evaluate("width=>{const n=document.querySelector('#pwd');n.type='text';n.style.width=width;n.style.padding='0';n.style.border='0';document.querySelector('#remote').remove();}", width)
            state = await observe(self.page, '#pwd')
            with self.subTest(width=width):
                self.assertFalse(any(row['kind'] == 'visible_placeholder' for row in state['target']['visible_label_evidence']))
                value = next(v for v in state['values'] if v['element_id'] == state['target']['element_id'])
                self.assertFalse(value['value_visible'])
                self.assertNotIn(LABEL, state['visible_text'])
                with self.assertRaisesRegex(ValueError, 'M4_TARGET_LABEL_UNREADABLE'):
                    prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': LABEL}})
        await self.page.set_content(REAL_CSS_HTML)
        await self.page.evaluate("document.querySelector('#pwd').type='text'")
        valid = await observe(self.page, '#pwd')
        self.assertIn({'kind': 'visible_placeholder', 'text': LABEL}, valid['target']['visible_label_evidence'])
        # The target-label exception does not loosen the default value gate.
        self.assertFalse(next(v for v in valid['values'] if v['element_id'] == valid['target']['element_id'])['value_visible'])
        prepare_action(valid, {'action_type': 'click', 'evidence': {'target_label': LABEL}})

    async def test_global_password_placeholder_only_from_complete_visible_empty_glyphs(self):
        changes = {'valid-empty': None,
                   'nonempty': "document.querySelector('#pwd').value='公开示例密钥'",
                   'transparent': "document.styleSheets[0].insertRule('#pwd::placeholder{color:transparent}',document.styleSheets[0].cssRules.length)",
                   'covered': "document.body.insertAdjacentHTML('beforeend','<div style=\"position:absolute;left:150px;top:264px;width:12px;height:17px;background:white;z-index:10\"></div>')",
                   'clipped': "document.querySelector('#pwd').style.width='40px'"}
        for case, change in changes.items():
            await self.page.set_content(REAL_CSS_HTML)
            await self.page.locator('#remote').evaluate('(n)=>n.remove()')
            if change:
                await self.page.evaluate(change)
            state = await observe(self.page, '#pwd', assertions=[{'selector': '#pwd', 'value': ''}])
            with self.subTest(case=case):
                self.assertEqual(LABEL in state['visible_text'], case == 'valid-empty')
                self.assertNotIn('公开示例密钥', state['visible_text'])
                self.assertFalse(next(v for v in state['values'] if v['element_id'] == state['target']['element_id'])['value_visible'])
                self.assertFalse(state['assertion_targets'][0]['value_visible'])
        await self.page.set_content(REAL_CSS_HTML)
        await self.page.locator('#remote').evaluate('(n)=>n.remove()')
        before = await observe(self.page, '#pwd')
        args, target = prepare_action(before, {'action_type': 'click', 'evidence': {'target_label': LABEL}})
        await execute(self.page, 'click', args, {'settle_ms': 0})
        after = await observe(self.page, '#pwd')
        from webcollect.collect import describe_change
        from webcollect.task_contract import narrative_evidence
        operation = {'operation_id': 'key-focus', 'action_type': 'click', 'evidence': {'target_label': LABEL}}
        prose = describe_change(before, after, operation, target)
        safe, evidence = narrative_evidence(prose, before, after, operation)
        self.assertEqual(prose, '「请输入密钥」输入框获得焦点')
        self.assertEqual(safe, prose)
        self.assertEqual(evidence['machine_status'], 'PASS')
        self.assertEqual(evidence['quoted_evidence'], [{'quote': LABEL, 'source': 'after_visible_text'}])

    async def test_nonempty_masked_password_is_neither_readable_value_nor_placeholder(self):
        await self.page.locator('#pwd').fill('公开示例密钥')
        state = await observe(self.page, '#pwd', assertions=[{'selector': '#pwd', 'value': '公开示例密钥'}])
        self.assertFalse(any(row['kind'] in ('visible_placeholder', 'visible_native_value')
                             for row in state['target']['visible_label_evidence']))
        self.assertNotIn('公开示例密钥', state['visible_text'])
        self.assertFalse(next(v for v in state['values'] if v['element_id'] == state['target']['element_id'])['value_visible'])
        self.assertFalse(state['assertion_targets'][0]['value_visible'])
        with self.assertRaisesRegex(ValueError, 'M4_TARGET_LABEL_UNREADABLE'):
            prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': LABEL}})

    async def test_transparent_small_clipped_covered_and_noneditable_placeholders_reject(self):
        changes = {
            'transparent-placeholder': "document.styleSheets[0].insertRule('#pwd::placeholder{color:transparent}',document.styleSheets[0].cssRules.length)",
            'transparent-fill': "document.styleSheets[0].insertRule('#pwd::placeholder{-webkit-text-fill-color:transparent}',document.styleSheets[0].cssRules.length)",
            'zero-placeholder-opacity': "document.styleSheets[0].insertRule('#pwd::placeholder{opacity:0}',document.styleSheets[0].cssRules.length)",
            'transparent-input': "document.querySelector('#pwd').style.opacity='0'",
            'transparent-ancestor': "document.querySelector('.input-group').style.opacity='0'",
            'tiny-placeholder': "document.styleSheets[0].insertRule('#pwd::placeholder{font-size:1px}',document.styleSheets[0].cssRules.length)",
            'narrow-input': "document.querySelector('#pwd').style.width='45px'",
            'clipped-ancestor': "Object.assign(document.querySelector('.input-group').style,{width:'170px',overflow:'hidden'})",
            'covered-text': "document.body.insertAdjacentHTML('beforeend','<div style=\"position:absolute;left:130px;top:48px;width:12px;height:18px;background:white;z-index:10\"></div>')",
            'readonly': "document.querySelector('#pwd').readOnly=true",
            'disabled': "document.querySelector('#pwd').disabled=true",
            'invisible-color': "document.styleSheets[0].insertRule('#pwd::placeholder{color:white}',document.styleSheets[0].cssRules.length)",
            'indented-outside': "document.querySelector('#pwd').style.textIndent='1000px'",
            'aria-name-only': "document.querySelector('#pwd').placeholder='';document.querySelector('#pwd').setAttribute('aria-label','请输入密钥')",
            'hidden-labelledby': "document.querySelector('#pwd').placeholder='';document.querySelector('#pwd').setAttribute('aria-labelledby','remote');document.querySelector('#remote').style.display='none'",
        }
        for case, change in changes.items():
            await self.page.set_content(HTML)
            await self.page.evaluate(change)
            state = await observe(self.page, '#pwd')
            with self.subTest(case=case):
                self.assertFalse(any(row['kind'] == 'visible_placeholder' for row in (state.get('target') or {}).get('visible_label_evidence', [])))
                with self.assertRaises(ValueError):
                    prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': LABEL}})


if __name__ == '__main__':
    unittest.main()
