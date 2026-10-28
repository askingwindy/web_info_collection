"""Independent local Chrome coverage for the exact observed Layui label shape."""
import hashlib
import json
import os
from pathlib import Path
import unittest

import test_s1_adjacent_label as baseline
from webcollect.browser import prepare_action

SNAPSHOT_PATH = Path(os.environ.get('WEBCOLLECT_SNAPSHOT_UNDER_TEST',
    str(Path(__file__).resolve().parents[1] / 'webcollect/snapshot.js')))
SNAPSHOT = SNAPSHOT_PATH.read_text()
KIND = 'rendered_adjacent_input_group_label'  # shared inference channel; exact Layui structure remains required
CSS = '''
body { margin:24px; font:14px/20px Arial,sans-serif; color:#333; }
.layui-form-item { position:relative; width:600px; height:38px; margin-bottom:15px; }
.layui-form-label { position:relative; float:left; display:block; padding:8px 15px;
  box-sizing:border-box; width:110px; height:38px; text-align:center; white-space:nowrap; border:1px solid #ddd; background:#fafafa; }
.layui-input-block { margin-left:110px; min-height:36px; }
input { box-sizing:border-box; display:block; height:38px; width:100%;
  padding-left:10px; border:1px solid #ddd; color:#333; font:inherit; background:white; }
'''
LABEL = '<label class="layui-form-label" id="label">开始日期</label>'
INPUT = '<input type="text" class="layui-input" id="target" value="2024-02-28" autocomplete="off">'


def group(label=LABEL, control=INPUT, before='', after='', wrapper_class='layui-input-block'):
    return f'<div class="layui-form-item">{before}{label}<div class="{wrapper_class}">{control}</div>{after}</div>'


class LayuiLabelEvidenceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = baseline.AdjacentLabelTests.asyncSetUp
    asyncTearDown = baseline.AdjacentLabelTests.asyncTearDown

    async def observe(self, html=None, case='case', extra_css=''):
        html = group() if html is None else html
        await self.page.set_content('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                                    f'<style>{CSS}{extra_css}</style><body>{html}</body></html>')
        before = await self.page.content()
        state = await self.page.evaluate(SNAPSHOT, {'selector': '#target'})
        self.assertEqual(await self.page.content(), before)
        self.assertEqual(self.requests, [])
        if folder := os.environ.get('WEBCOLLECT_LAYUI_LABEL_ARTIFACTS'):
            dest = Path(folder)/self._testMethodName/case; dest.mkdir(parents=True, exist_ok=True)
            (dest/'fixture.html').write_text(before)
            (dest/'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2))
            (dest/'observation.json').write_text(json.dumps({'observer_sha256': hashlib.sha256(SNAPSHOT.encode()).hexdigest(),
                'chrome_version': self.browser.version, 'dom_unchanged': True, 'network_requests': self.requests,
                'fixture_kind': 'controlled_local_html'}, ensure_ascii=False, indent=2))
            await self.page.screenshot(path=str(dest/'frame.png'))
        return state

    def accepted(self, state, expected='开始日期'):
        self.assertIn({'kind': KIND, 'text': expected}, state['target']['visible_label_evidence'])
        prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': expected}})

    def rejected(self, state, expected='开始日期'):
        self.assertFalse(any(r['kind'] == KIND for r in (state['target'] or {}).get('visible_label_evidence', [])))
        with self.assertRaises(ValueError):
            prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': expected}})

    async def test_real_shape_start_and_end_labels_support_click_and_type(self):
        state = await self.observe()
        self.accepted(state)
        args, _ = prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': '开始日期'}})
        await self.page.mouse.click(args['x'], args['y'])
        focused = await self.page.evaluate(SNAPSHOT, {'selector': '#target'})
        prepare_action(focused, {'action_type': 'type', 'arguments': {'text': '2024-03-01'}, 'evidence': {'target_label': '开始日期'}})
        self.accepted(await self.observe(group(label=LABEL.replace('开始日期', '结束日期')), 'end'), '结束日期')

    async def test_multiple_hidden_or_readonly_controls_reject(self):
        for case, extra in {'second_input':'<input value="2024-03-01">', 'hidden_input':'<input type="hidden">',
                            'readonly_input':'<input readonly>', 'textarea':'<textarea></textarea>',
                            'button':'<button>计算</button>', 'contenteditable':'<div contenteditable="false"></div>'}.items():
            with self.subTest(case=case):
                self.rejected(await self.observe(group(control=INPUT+extra), case))

    async def test_unrelated_or_ambiguous_structures_reject(self):
        cases = {
            'extra_label':group(after='<label class="layui-form-label">其他</label>'),
            'hidden_extra_label':group(after='<label hidden class="layui-form-label">其他</label>'),
            'group_own_text':group(before='另一个含义'),
            'block_own_text':group(control='另一个含义'+INPUT),
            'nested_control':group(control='<div>'+INPUT+'</div>'),
            'nested_label':group(label=LABEL.replace('开始日期', '<span>开始日期</span>')),
            'unmarked_label':group(label=LABEL.replace('layui-form-label', 'unrelated')),
            'wrong_label_tag':group(label=LABEL.replace('<label','<span').replace('</label>','</span>')),
            'wrong_block':group(wrapper_class='unrelated'),
            'wrong_for':group(label=LABEL.replace('id="label"', 'id="label" for="another"'))+'<input id="another">',
            'wrong_group':group().replace('layui-form-item','unrelated'),
            'nested_group':group(control='<div class="layui-form-item">'+INPUT+'</div>'),
            'outside':LABEL+'<div class="layui-form-item"><div class="layui-input-block">'+INPUT+'</div></div>',
        }
        for case, html in cases.items():
            with self.subTest(case=case):
                self.rejected(await self.observe(html, case))

    async def test_partial_glyph_or_nonopaque_text_never_proves_label(self):
        for case, css in {
            'hidden':'#label{visibility:hidden}', 'none':'#label{display:none}',
            'opacity_zero':'#label{opacity:0}', 'opacity_faint':'#label{opacity:0.1}',
            'ancestor_opacity':'.layui-form-item{opacity:0.5}', 'transparent':'#label{color:transparent}',
            'transparent_fill':'#label{-webkit-text-fill-color:transparent}', 'tiny':'#label{font-size:1px}',
            'clip_label':'#label{width:18px;overflow:hidden}', 'clip_parent':'.layui-form-item{width:60px;overflow:hidden}',
            'offscreen':'.layui-form-item{margin-left:-95px}', 'filter':'#label{filter:blur(3px)}',
            'pseudo':'#label::after{content:"结束日期"}', 'transform':'#label{text-transform:uppercase}',
        }.items():
            with self.subTest(case=case):
                self.rejected(await self.observe(case=case, extra_css=css))

    async def test_distant_or_different_row_labels_reject(self):
        for case, css in {'horizontal_gap':'.layui-input-block{margin-left:160px}',
                          'vertical_gap':'#label{top:50px}', 'overlap':'.layui-input-block{margin-left:105px}',
                          'stacked':'#label{float:none}.layui-input-block{margin-left:0}'}.items():
            with self.subTest(case=case):
                self.rejected(await self.observe(case=case, extra_css=css))

    async def test_occluded_label_or_target_area_reject(self):
        for case, left in (('label_covered', 54), ('target_covered', 275)):
            overlay=f'<div style="position:absolute;left:{left}px;top:25px;width:24px;height:35px;background:white;z-index:9">挡</div>'
            with self.subTest(case=case):
                self.rejected(await self.observe(group()+overlay, case))
        self.rejected(await self.observe(case='target_clipped', extra_css='.layui-input-block{width:220px;overflow:hidden}input{width:489px}'))

    async def test_noneditable_controls_do_not_gain_inferred_label(self):
        for case, control in {'readonly':INPUT.replace('id="target"','id="target" readonly'),
                              'disabled':INPUT.replace('id="target"','id="target" disabled'),
                              'range':INPUT.replace('type="text"','type="range"'),
                              'checkbox':INPUT.replace('type="text"','type="checkbox"')}.items():
            with self.subTest(case=case):
                self.rejected(await self.observe(group(control=control), case))

    async def test_aria_only_cannot_replace_missing_visible_label(self):
        html=group(label=LABEL.replace('开始日期',''), control=INPUT.replace('id="target"','id="target" aria-label="开始日期"'))
        self.rejected(await self.observe(html, 'aria_only'))


if __name__ == '__main__':
    unittest.main()
