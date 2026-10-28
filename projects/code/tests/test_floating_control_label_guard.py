"""Reproduce a real three-row layout and floating back-to-top obstruction.

All HTML is controlled local evidence; network is denied. The real failure is
preserved separately. A readable label does not exempt an occluded input box.
"""
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
LABEL_KIND = 'rendered_adjacent_input_group_label'
CSS = '''
body { margin:20px; font:14px/20px Arial,sans-serif; color:#111; min-height:1500px; }
main { padding-top:360px; }
.layui-form-item { position:relative; display:flex; width:1239px; height:38px; margin-bottom:15px; }
.layui-form-label { position:relative; float:left; display:block; padding:8px 15px;
  box-sizing:border-box; width:210px; height:38px; text-align:center; white-space:nowrap;
  border:1px solid #ddd; background:#fafafa; }
.layui-input-block { flex:1; min-width:0; margin-left:-1px; min-height:36px; }
input { box-sizing:border-box; display:block; height:38px; width:100%; padding-left:10px;
  border:1px solid #ddd; color:#111; font:inherit; background:white; }
.floating-control { position:fixed; right:15px; top:509px; width:50px; height:50px;
  z-index:99; background:#999; color:white; text-align:center; line-height:50px; }
'''


def rows(overlay=True, extra=''):
    content = ''.join(f'<div class="layui-form-item"><label class="layui-form-label" id="label-{name}">{label}</label>'
                      f'<div class="layui-input-block"><input type="number" id="{name}" value="{value}"></div></div>'
                      for name, label, value in (('count', '生成数量', 10), ('minimum', '随机数最小值', 0),
                                                 ('maximum', '随机数最大值', 100)))
    return '<main>' + content + '</main>' + ('<div class="floating-control">↑</div>' if overlay else '') + extra


class FloatingControlLabelGuard(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await baseline.AdjacentLabelTests.asyncSetUp(self)
        await self.page.set_viewport_size({'width': 1280, 'height': 720})

    asyncTearDown = baseline.AdjacentLabelTests.asyncTearDown

    async def load(self, content=None, css=''):
        await self.page.set_content('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                                    f'<style>{CSS}{css}</style><body>{rows() if content is None else content}</body></html>')

    async def state(self, selector, case):
        before = await self.page.content()
        state = await self.page.evaluate(SNAPSHOT, {'selector': selector})
        self.assertEqual(await self.page.content(), before)
        self.assertEqual(self.requests, [])
        if base := os.environ.get('WEBCOLLECT_FLOATING_LABEL_ARTIFACTS'):
            output = Path(base) / self._testMethodName / case
            output.mkdir(parents=True, exist_ok=False)
            (output / 'fixture.html').write_text(before)
            (output / 'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2))
            (output / 'observation.json').write_text(json.dumps({
                'observer_sha256': hashlib.sha256(SNAPSHOT.encode()).hexdigest(),
                'chrome_version': self.browser.version, 'dom_unchanged': True,
                'network_requests': self.requests, 'fixture_kind': 'controlled_local_three_row_layout'},
                ensure_ascii=False, indent=2))
            await self.page.screenshot(path=str(output / 'frame.png'))
        return state

    def accepted(self, state, text):
        self.assertIn({'kind': LABEL_KIND, 'text': text}, state['target']['visible_label_evidence'])
        prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': text}})

    def rejected(self, state, text):
        self.assertFalse(any(row['kind'] == LABEL_KIND for row in state['target']['visible_label_evidence']))
        with self.assertRaisesRegex(ValueError, 'M4_TARGET_LABEL_UNREADABLE'):
            prepare_action(state, {'action_type': 'click', 'evidence': {'target_label': text}})

    async def test_same_three_rows_reproduce_last_row_only_rejection(self):
        await self.load()
        self.accepted(await self.state('#count', 'first-row'), '生成数量')
        self.accepted(await self.state('#minimum', 'second-row'), '随机数最小值')
        state = await self.state('#maximum', 'third-row-occluded')
        self.assertEqual(state['target']['bbox'], [229, 486, 1259, 524])
        self.assertTrue(state['target']['hit_valid'])
        self.assertEqual(state['target']['text'], '随机数最大值')
        self.rejected(state, '随机数最大值')

    async def test_same_three_rows_without_obstruction_all_pass(self):
        await self.load(rows(overlay=False))
        for name, text in (('count', '生成数量'), ('minimum', '随机数最小值'), ('maximum', '随机数最大值')):
            self.accepted(await self.state('#' + name, name), text)

    async def test_necessary_scroll_exposes_the_entire_input_and_label(self):
        await self.load()
        self.rejected(await self.state('#maximum', 'before-scroll'), '随机数最大值')
        await self.page.mouse.wheel(0, 220)
        await self.page.wait_for_timeout(100)
        state = await self.state('#maximum', 'after-scroll')
        self.assertLess(state['target']['bbox'][3], 509)
        self.accepted(state, '随机数最大值')

    async def test_label_obstruction_does_not_gain_evidence(self):
        overlay = '<div style="position:absolute;left:83px;top:499px;width:50px;height:18px;background:white;z-index:99">挡</div>'
        await self.load(rows(overlay=False, extra=overlay))
        self.rejected(await self.state('#maximum', 'label-occluded'), '随机数最大值')

    async def test_clipped_label_or_target_does_not_gain_evidence(self):
        for name, css in (('label-clipped', '#label-maximum{width:50px;overflow:hidden}'),
                          ('target-clipped', '.layui-input-block{flex:0 0 600px;width:600px;overflow:hidden}input{width:1030px}')):
            with self.subTest(case=name):
                await self.load(rows(overlay=False), css)
                self.rejected(await self.state('#maximum', name), '随机数最大值')

    async def test_duplicate_group_label_does_not_gain_evidence(self):
        html = rows(overlay=False).replace('<label class="layui-form-label" id="label-maximum">',
            '<label class="layui-form-label">另一个含义</label><label class="layui-form-label" id="label-maximum">')
        await self.load(html)
        self.rejected(await self.state('#maximum', 'duplicate-label'), '随机数最大值')


if __name__ == '__main__':
    unittest.main()
