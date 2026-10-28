"""One local Chromium session: native Color4 normalization and paint guards.

All pages are authored fixtures; networking is aborted. No real task, model,
original sample, or credential is used. The source observer stays read-only.
"""
import hashlib
import json
import os
from pathlib import Path
import unittest

from playwright.async_api import async_playwright
from webcollect.browser import SNAPSHOT_JS, capture, prepare_action
from webcollect.collect import chinese_ratio

LAB = 'lab(7.78673 1.82345 -15.0537)'
TEAL = 'lab(44.4134 -33.1436 -4.22149)'
OKLAB = 'oklab(0.436997 -0.0771984 -0.0111369 / 0.7)'


def fixture(css='', extra=''):
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>
    html{color-scheme:light;background:white}body{margin:24px;font:16px/24px sans-serif;
    color:''' + LAB + ''';background:white}main{width:720px;background:white;padding:12px}
    h1{font-size:24px;line-height:32px}label{position:relative;display:block;width:460px;
    padding:8px;background:transparent}input{display:block;width:420px;height:36px;box-sizing:border-box;
    font:16px sans-serif;color:inherit;-webkit-text-fill-color:currentColor;background:transparent;
    border:1px solid #aaa;padding:4px}button{color:rgb(251,251,251);-webkit-text-fill-color:currentColor;
    background:''' + TEAL + ''';border:0;border-radius:4px;padding:8px 16px;font:16px/24px sans-serif}
    ''' + css + '''</style><body><main><h1>代谢年龄计算器</h1>
    <p>此页面仅是离线颜色与可见证据测试，不是实际健康结果。</p>
    <label for="height">身高（cm）<input id="height" type="number" value="175"></label>
    <label for="weight">体重（kg）<input id="weight" type="number" value="70"></label>
    <label for="age">年龄（岁）<input id="age" type="number" value="30"></label>
    <button id="calculate" type="button">计算参考值</button></main>''' + extra + '</body></html>'


class CSSColor4PaintTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_colors_and_all_negative_paint_guards_in_one_browser_session(self):
        outcomes = []
        requests = []
        if base := os.environ.get('WEBCOLLECT_COLOR4_ARTIFACTS'):
            Path(base).mkdir(parents=True, exist_ok=False)
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch(channel='chrome', headless=True)
            context = await browser.new_context(viewport={'width':1280, 'height':720},
                device_scale_factor=1, locale='zh-CN', color_scheme='light')
            try:
                page = await context.new_page()
                await page.route('**/*', lambda route: route.abort())
                page.on('request', lambda request: requests.append(request.url))
                cases = [
                    ('actual-lab-input', '', '', '#height', '身高（cm）', True, True),
                    ('actual-lab-background-button', '', '', '#calculate', '计算参考值', True, None),
                    ('actual-oklab-alpha-input', 'body{color:' + OKLAB + '}', '', '#height', '身高（cm）', True, True),
                    ('oklab-opaque-input', 'body{color:oklab(.2 .02 -.02)}', '', '#height', '身高（cm）', True, True),
                    ('lab-same-white', 'body{color:lab(100 0 0)}', '', '#height', '身高（cm）', False, False),
                    ('lab-transparent', 'body{color:lab(0 0 0 / 0)}', '', '#height', '身高（cm）', False, False),
                    ('oklab-low-alpha', 'body{color:oklab(.2 0 0 / .01)}', '', '#height', '身高（cm）', False, False),
                    ('lab-quantization-boundary', 'body{color:lab(61.5 0 0)}', '', '#height', '身高（cm）', False, False),
                    ('lab-clear-margin', 'body{color:lab(50 0 0)}', '', '#height', '身高（cm）', True, True),
                    ('same-color-button', 'button{color:' + TEAL + ';background:' + TEAL + '}', '', '#calculate', '计算参考值', False, None),
                    ('unknown-gradient', 'label{background-image:linear-gradient(white,white)}', '', '#height', '身高（cm）', False, False),
                    ('occluded', '', '<div style="position:fixed;inset:0;z-index:999;background:white"></div>', '#height', '身高（cm）', False, False),
                    ('opaque-pseudo-still-rejected', 'main::after{content:"";position:absolute;inset:0;background:' + LAB + ';pointer-events:none;z-index:999}', '', '#height', '身高（cm）', False, False),
                    ('tiny-alpha-pseudo-still-paints', 'main::after{content:"";background:lab(0 0 0 / .000001)}', '', '#height', '身高（cm）', False, False),
                    ('zero-alpha-pseudo-paints-nothing', 'main::after{content:"";background:lab(0 0 0 / 0)}', '', '#height', '身高（cm）', True, True),
                    ('filter-still-rejected', 'main{filter:brightness(1)}', '', '#height', '身高（cm）', False, False),
                ]
                for name, css, extra, selector, label, accepted, value_visible in cases:
                    with self.subTest(case=name):
                        await page.set_content(fixture(css, extra))
                        before = await page.content()
                        # Test the observer's read-only contract directly.
                        # Playwright screenshot caret hiding can itself leave
                        # an empty style attribute on native input controls.
                        await page.evaluate(SNAPSHOT_JS, {'selector':selector})
                        self.assertEqual(await page.content(), before)
                        observed = await capture(page, selector)
                        state = observed['state']
                        self.assertTrue(all(a['dom_stable'] for a in observed['capture']['attempts']))
                        if accepted:
                            self.assertEqual(state['target']['text'], label)
                            self.assertTrue(state['target']['visible_label_evidence'])
                            prepare_action(state, {'action_type':'click', 'evidence':{'target_label':label}})
                            self.assertIn('代谢年龄计算器', state['visible_text'])
                            self.assertGreaterEqual(chinese_ratio(state['visible_text']), .7)
                        else:
                            with self.assertRaises(ValueError):
                                prepare_action(state, {'action_type':'click', 'evidence':{'target_label':label}})
                        if value_visible is not None:
                            value = next((row for row in state['values'] if row['element_id'] == state['target']['element_id']), None)
                            self.assertEqual(bool(value and value['value_visible']), value_visible)
                        outcomes.append({'case':name, 'accepted':accepted, 'value_visible':value_visible,
                            'screenshot_sha256':observed['capture']['screenshot_sha256'],
                            'observer_sha256':observed['capture']['observer_sha256'], 'observer_dom_unchanged':True})
                        if base := os.environ.get('WEBCOLLECT_COLOR4_ARTIFACTS'):
                            folder = Path(base) / name; folder.mkdir(parents=True, exist_ok=False)
                            (folder / 'fixture.html').write_text(before)
                            (folder / 'frame.png').write_bytes(observed['png'])
                            (folder / 'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2))
                            (folder / 'capture.json').write_text(json.dumps(observed['capture'], ensure_ascii=False, indent=2))
                # Exercise the actual source helper against invalid strings and
                # known endpoints. CSS would otherwise discard an invalid style
                # declaration before getComputedStyle, hiding a parser fallback.
                helpers = SNAPSHOT_JS[SNAPSHOT_JS.index('  const frameworkColorCache='):
                                      SNAPSHOT_JS.index('  const frameworkLabelPaint =')]
                values = await page.evaluate('''() => {''' + helpers + '''
                    const inputs=['lab(0 0 0 / .12345)','oklab(1 0 0 / 25%)','lab(0 0 0 / .000001)',
                        'lab(bad 0 0)','color(unknown 1 0 0)','lab(0 0 0 / invalid)',
                        'linear-gradient(black,white)','not-a-color'];
                    return inputs.map(input=>{const color=frameworkColor(input);
                        return {input,rgba:color&&[...color],bounds:color?.bounds||null};});}''')
                self.assertEqual(values[0]['rgba'][:3], [0,0,0])
                self.assertEqual(values[0]['rgba'][3], .12345)
                self.assertEqual(values[1]['rgba'][3], .25)
                self.assertEqual(values[2]['rgba'][3], .000001)
                self.assertTrue(all(row['rgba'] is None for row in values[3:]))
                self.assertTrue(all(row['bounds'][3] == [row['rgba'][3], row['rgba'][3]] for row in values[:3]))
                self.assertEqual(requests, [])
                if base := os.environ.get('WEBCOLLECT_COLOR4_ARTIFACTS'):
                    (Path(base) / 'summary.json').write_text(json.dumps({'controlled_fixture_only':True,
                        'browser_launches':1, 'external_requests':requests, 'task_actions':0, 'model_requests':0,
                        'snapshot_sha256':hashlib.sha256(SNAPSHOT_JS.encode()).hexdigest(),
                        'cases':outcomes, 'native_parser_cases':values}, ensure_ascii=False, indent=2))
            finally:
                await context.close(); await browser.close()


if __name__ == '__main__': unittest.main()
