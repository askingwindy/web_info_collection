"""Synthetic normalization checks; no real collection or human decisions."""
import copy
import json
from pathlib import Path
import platform
import tempfile
import unittest

from webcollect.action_normalization import (
    is_select_all, normalize_delivery_arguments, normalize_delivery_step, canonical_windows_keys, display_windows_keys,
)


def shortcut_step(keys):
    return {
        'action': {'action_type': 'hotkey', 'target_element_id': '',
                   'target_text': 'Command+A', 'coordinate': [],
                   'input_text': '+'.join(keys)},
        'tool_call': {'tool_name': 'hotkey', 'arguments': {'keys': keys}},
        'next_step_rationale': '合成测试：选中输入框中的原内容',
    }


class WindowsKeyNormalizationTests(unittest.TestCase):
    def test_mac_common_shortcuts_publish_windows_names_without_changing_source(self):
        for keys, expected in ((['meta', 'a'], ['ctrl', 'a']), (['meta', 'c'], ['ctrl', 'c']),
                               (['meta', 'v'], ['ctrl', 'v']), (['cmd', 'x'], ['ctrl', 'x']),
                               (['Meta', 'Shift', 'V'], ['ctrl', 'shift', 'v']),
                               (['command', 'shift', 'z'], ['ctrl', 'shift', 'z']),
                               (['meta', '3'], ['ctrl', '3'])):
            with self.subTest(keys=keys):
                source = shortcut_step(keys); before = copy.deepcopy(source)
                result = normalize_delivery_step(source, 'macOS')
                self.assertEqual(result['tool_call']['arguments'], {'keys': expected})
                self.assertEqual(result['action']['input_text'], '+'.join(expected))
                self.assertEqual(result['action']['target_text'], display_windows_keys(expected))
                self.assertEqual(source, before)
                self.assertEqual(normalize_delivery_step(result, 'macOS'), result)

    def test_windows_native_meta_is_win_not_ctrl_and_plain_uppercase_is_preserved(self):
        self.assertEqual(canonical_windows_keys(['Meta', 'A'], 'Windows'), ['win', 'a'])
        self.assertEqual(canonical_windows_keys(['meta'], 'Windows'), ['win'])
        self.assertEqual(canonical_windows_keys(['A']), ['A'])
        self.assertEqual(canonical_windows_keys(['Shift', 'Control', 'V']), ['ctrl', 'shift', 'v'])

    def test_named_keys_and_display_are_canonical(self):
        for original, canonical, display in (('Return','enter','Enter'), ('Esc','escape','Esc'),
                ('TAB','tab','Tab'), ('HOME','home','Home'), ('PgDn','pagedown','PageDown'),
                ('Left','arrowleft','Left'), ('F12','f12','F12'), ('Del','delete','Delete')):
            with self.subTest(original=original):
                result = normalize_delivery_step(shortcut_step([original]))
                self.assertEqual(result['tool_call']['arguments']['keys'], [canonical])
                self.assertEqual(result['action']['target_text'], display)

    def test_ambiguous_native_shortcuts_and_invalid_chords_cannot_be_relabelled(self):
        cases = [(['meta','arrowleft'], 'macOS'), (['option','arrowleft'], 'macOS'),
                 (['meta','q'], 'macOS'), (['meta','a'], ''), (['command','a'], 'Windows'),
                 (['ctrl','meta','a'], 'macOS'), (['ctrl','ctrl','v'], 'Windows'),
                 (['a','meta'], 'macOS'), (['ctrl','c','v'], 'Windows'),
                 (['ctrl','shift'], 'Windows'), (['meta','shift','3'], 'macOS'),
                 (['unknown-key'], 'Windows')]
        for keys, os_name in cases:
            with self.subTest(keys=keys, os_name=os_name):
                with self.assertRaisesRegex(ValueError, 'WINDOWS_SHORTCUT_MAPPING_REQUIRED'):
                    normalize_delivery_step(shortcut_step(keys), os_name)

    def test_arguments_are_detached_and_extra_parameters_are_not_hidden(self):
        actual = {'keys': ['meta', 'v'], 'unexpected': {'value': [1]}}
        delivery = normalize_delivery_arguments('hotkey', actual, 'macOS')
        delivery['unexpected']['value'].append(2)
        self.assertEqual(actual, {'keys': ['meta', 'v'], 'unexpected': {'value': [1]}})
        self.assertIn('unexpected', delivery)

    def test_nonhotkey_actions_and_mismatched_names_are_not_silently_repaired(self):
        source = shortcut_step(['meta', 'v']); source['tool_call']['tool_name'] = 'type'
        self.assertEqual(normalize_delivery_step(source, 'macOS'), source)
        self.assertEqual(normalize_delivery_arguments('type', {'keys': ['meta', 'v']}),
                         {'keys': ['meta', 'v']})

    def test_invalid_keys_do_not_become_valid_chords(self):
        for keys in (None, 'meta+v', ['meta', None], ['meta', 1], [' meta', 'v'], []):
            with self.subTest(keys=keys):
                with self.assertRaisesRegex(ValueError, 'WINDOWS_SHORTCUT_MAPPING_REQUIRED'):
                    canonical_windows_keys(keys, 'macOS')


class CollectorNativeShortcutTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_copy_paste_and_named_keys_keep_raw_inputs_without_using_clipboard(self):
        from playwright.async_api import async_playwright
        from webcollect.collect import collect_one
        from webcollect.evidence import audit_capture
        modifier = 'meta' if platform.system() == 'Darwin' else 'ctrl'
        chords = [[modifier,'c'], [modifier,'v'], ['home'], ['arrowleft'], ['f2'], ['Return']]
        operations = [{'action_type':'hotkey', 'arguments':{'keys':keys},
            'goal':'合成测试记录快捷键事件', 'rationale':'验证原生按键与Windows交付名称',
            'expected':'页面显示已记录的按键'} for keys in chords]
        expected = '|'.join([modifier+'+c',modifier+'+v','Home','ArrowLeft','F2','Enter'])
        task = {'task_id':'SYNTHETIC_WINDOWS_KEYS_ONLY', 'instruction':'合成测试：记录键名',
            'task_type':['填写表单'], 'app_name':'合成键名验证',
            'initial_url':'https://example.org/windows-key-test', 'initial_settle_ms':0,
            'content_preparation':False, 'stop_when_final':False, 'operations':operations,
            'final_assertions':[{'selector':'#log','contains':expected}],
            'final_result':'页面显示全部按键事件', 'completion_judgement':'可见日志含全部预期按键'}
        html = '''<meta charset="utf-8"><h1>合成键名验证</h1>
        <p>此页面只用于受控工程验证，所有输入和按键日志都是合成测试内容。页面会阻止按键的默认行为，
        不读取或修改系统剪贴板，也不访问个人资料。验证目标是保留真实执行的原生按键，
        同时在交付记录中使用统一的中文说明和标准键名。下面的日志仅展示浏览器收到的按键事件，
        不表示已经执行复制或粘贴业务操作，更不能作为真实采集或人工审核通过的证据。</p>
        <input autofocus value="测试"><p id="log"></p>
        <script>const seen=[];document.addEventListener('keydown',event=>{event.preventDefault();
        if(['Control','Meta','Shift','Alt'].includes(event.key))return;
        seen.push((event.metaKey?'meta+':event.ctrlKey?'ctrl+':'')+event.key);
        document.getElementById('log').textContent=seen.join('|');});</script>'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); sid='SYNTHETIC_WINDOWS_KEYS_ONLY'
            async with async_playwright() as runtime:
                browser=await runtime.chromium.launch(channel='chrome',headless=True)
                context=await browser.new_context(viewport={'width':640,'height':480})
                try:
                    await context.route('https://example.org/**',lambda route:route.fulfill(content_type='text/html',body=html))
                    result=await collect_one(context,task,root/'samples'/sid,root/'evidence'/sid,{'sample_id':sid})
                finally:
                    await browser.close()
            self.assertEqual([step['action']['target_text'] for step in result['steps'][:-1]],
                             ['Ctrl+C','Ctrl+V','Home','Left','F2','Enter'])
            for index,keys in enumerate(chords,1):
                raw=json.loads((root/'evidence'/sid/f'step_{index:03}.json').read_text())
                self.assertEqual(raw['executed_action']['arguments']['keys'],keys)
            audit=audit_capture(root,sid)
            self.assertTrue(audit['capture_evidence_pass'],audit['issues'])

    async def test_collector_publishes_ctrl_but_executes_and_records_native_keys(self):
        from playwright.async_api import async_playwright
        from webcollect.collect import collect_one
        from webcollect.evidence import audit_capture

        native_keys = ['meta', 'a'] if platform.system() == 'Darwin' else ['ctrl', 'a']
        operation = {'action_type': 'hotkey', 'arguments': {'keys': native_keys},
                     'key_name': 'Command+A' if platform.system() == 'Darwin' else 'Ctrl+A',
                     'goal': '选中输入框的原内容', 'rationale': '替换现有文字前先全选',
                     'expected': '输入框原内容被选中'}
        task = {'task_id': 'SYNTHETIC_NORMALIZATION_ONLY', 'instruction': '将输入框文字替换为「新内容」',
                'task_type': ['信息处理'], 'app_name': '合成快捷键测试',
                'initial_url': 'https://example.org/normalization-only',
                'initial_settle_ms': 0, 'content_preparation': False, 'stop_when_final': False,
                'operations': [operation, {'action_type': 'type', 'selector': '#entry',
                    'arguments': {'text': '新内容'}, 'goal': '输入新内容',
                    'rationale': '原内容已选中，输入替换文字', 'expected': '输入框显示新内容'}],
                'final_assertions': [{'selector': '#entry', 'value': '新内容'}],
                'final_result': '输入框显示新内容', 'completion_judgement': '输入框文字完整显示为新内容'}
        before = copy.deepcopy(operation)
        html = ('<meta charset="utf-8"><h1>合成快捷键验证</h1><p>这里只验证全选键的交付映射与原始执行分离。</p>'
                '<label for="entry">输入内容</label><input autofocus id="entry" value="原内容">')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / 'samples/SYNTHETIC_ONLY'
            evidence = root / 'evidence/SYNTHETIC_ONLY'
            async with async_playwright() as runtime:
                browser = await runtime.chromium.launch(channel='chrome', headless=True)
                context = await browser.new_context(viewport={'width': 640, 'height': 480})
                try:
                    await context.route('https://example.org/**',
                        lambda route: route.fulfill(content_type='text/html', body=html))
                    result = await collect_one(context, task, sample, evidence,
                                               {'sample_id': 'SYNTHETIC_ONLY'})
                finally:
                    await browser.close()
            raw = json.loads((evidence / 'step_001.json').read_text())
            self.assertEqual(raw['executed_action']['arguments']['keys'], native_keys)
            self.assertEqual(raw['operation'], before)
            self.assertEqual(operation, before)
            first = result['steps'][0]
            self.assertEqual(first['tool_call']['arguments']['keys'], ['ctrl', 'a'])
            self.assertEqual(first['action']['input_text'], 'ctrl+a')
            self.assertEqual(first['action']['target_text'], 'Ctrl+A')
            self.assertEqual(result['completion_status'], 'success')
            audit = audit_capture(root, 'SYNTHETIC_ONLY')
            self.assertTrue(audit['capture_evidence_pass'], audit['issues'])
            raw['executed_action']['arguments']['keys'] = ['meta', 'c']
            (evidence / 'step_001.json').write_text(json.dumps(raw))
            self.assertFalse(audit_capture(root, 'SYNTHETIC_ONLY')['capture_evidence_pass'])


if __name__ == '__main__':
    unittest.main()
