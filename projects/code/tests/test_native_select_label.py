"""Native selected text must be original, visible and fully corroborated.

Only temporary protocol fixtures and local HTML are used; no external site,
model, production registry or existing evidence is modified.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from webcollect.batch_core import load_json, save_json
from webcollect.browser import capture, prepare_action, execute
from webcollect.browser_planner import operation_from_decision
from webcollect.observed_workflow import compile_task, original_control_label
from webcollect.task_admission import reference
import test_observed_workflow as workflow_fixture


class OriginalSelectedText(unittest.TestCase):
    def setUp(self):
        self.fixture = workflow_fixture.ObservedWorkflowTests('runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)

    def select_trace(self, *, value_visible=True):
        trace = load_json(self.fixture.trace_ref['path'])
        transition = trace['transitions'][3]
        transition['operation'].update(action_type='select', arguments={'option': '七厘米'},
                                       evidence={'target_label': '请选择'})
        def native_select(state):
            element = state['elements'][1]
            element.update(element_type='select', native_role='select', inputable=False, text='')
            value = next(row for row in state['values'] if row['element_id'] == element['element_id'])
            value.update(choice=True, input_type='select-one', value_visible=value_visible,
                         display_value='七厘米' if value['value'] else '请选择')
            if (state.get('target') or {}).get('element_id') == element['element_id']:
                state['target'].update(text='', visible_label_evidence=[
                    {'kind': 'visible_selected_option', 'text': value['display_value']}])
        for frame in (transition['before'], transition['after'], trace['transitions'][2]['after'],
                      trace['transitions'][4]['before'], trace['transitions'][4]['after']):
            self.fixture.rewrite_frame(frame, native_select)
        for row in trace['transitions'][2:]:
            self.fixture.rewrite_receipt(row)
        path = self.fixture.root / ('selected-visible-' + str(value_visible) + '.json')
        save_json(path, trace)
        return reference(path), load_json(transition['before']['state']['path'])

    def test_original_workflow_compiles_blank_select_from_current_selected_text(self):
        trace, state = self.select_trace()
        task = compile_task(self.fixture.cap, trace)
        self.assertEqual(task['operations'][3]['evidence'], {'target_label': '请选择'})
        self.assertNotEqual(task['operations'][3]['evidence']['target_label'], task['operations'][3]['arguments']['option'])

    def test_original_workflow_rejects_hidden_display_even_with_forged_label_evidence(self):
        trace, _ = self.select_trace(value_visible=False)
        with self.assertRaisesRegex(ValueError, 'original control name must be readable'):
            compile_task(self.fixture.cap, trace)

    def test_select_label_requires_all_original_visibility_bindings(self):
        _, state = self.select_trace(); original = deepcopy(state)
        mutations = (
            lambda s: s['target'].update(hit_valid=False),
            lambda s: s['target'].update(enabled=False),
            lambda s: s['target'].update(element_id='different-control'),
            lambda s: s['target'].update(visible_label_evidence=[{'kind': 'aria_label', 'text': '请选择'}]),
            lambda s: s['target'].update(visible_label_evidence=[{'kind': 'visible_selected_option', 'text': '隐藏选项'}]),
            lambda s: s['values'][1].update(choice=False),
            lambda s: s['values'][1].update(value_visible=False),
            lambda s: s['values'][1].update(input_type='text'),
            lambda s: s['elements'][1].update(visible=False),
            lambda s: s['elements'][1].update(enabled=False),
            lambda s: s['elements'][1].update(native_role='combobox'),
            lambda s: s['elements'][1].update(element_type='input'),
        )
        for index, mutate in enumerate(mutations):
            candidate = deepcopy(original); mutate(candidate)
            with self.subTest(index=index):
                self.assertIsNone(original_control_label(candidate, candidate['elements'][1], 'select'))
        self.assertEqual(state, original)

    def test_visible_option_cannot_name_a_different_action_or_control(self):
        _, state = self.select_trace()
        self.assertIsNone(original_control_label(state, state['elements'][1], 'type'))
        self.assertIsNone(original_control_label(state, state['elements'][1], 'click'))


class NativeSelectLocalBrowser(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(channel='chrome', headless=True)
        self.context = await self.browser.new_context(viewport={'width': 640, 'height': 480})
        self.page = await self.context.new_page()

    async def asyncTearDown(self):
        await self.context.close(); await self.browser.close(); await self.runtime.stop()

    async def surface(self, *, css='', overlay=''):
        await self.page.set_content('''<!doctype html><meta charset="utf-8"><style>
            body{margin:0;background:white;color:black}select{position:absolute;left:40px;top:40px;
            width:240px;height:34px;font:16px Arial;color:black;background:white;opacity:1}
            ''' + css + '''</style><select id="choice"><option value="">请选择</option>
            <option value="seven">七厘米</option><option value="unseen">隐藏选项不能充当当前标签</option></select>''' + overlay)
        frame = await capture(self.page)
        element = next(row for row in frame['state']['elements'] if row.get('element_type') == 'select')
        return frame['state'], element

    def decision(self, element):
        return {'action_type': 'select', 'target_element_id': element['element_id'], 'arguments': {'option': '七厘米'},
                'goal': '选择「七厘米」作为宽度', 'rationale': '任务要求按该宽度计算', 'expected': '选择框显示「七厘米」'}

    async def test_original_tree_names_visible_selected_option_and_executes_native_select(self):
        state, element = await self.surface()
        self.assertEqual(element['text'], '请选择')
        original = deepcopy(state)
        operation = await operation_from_decision(self.page, state, self.decision(element))
        self.assertEqual(operation['evidence'], {'target_label': '请选择'})
        self.assertEqual(state, original)
        before = await capture(self.page, operation['selector'])
        args, _ = prepare_action(before['state'], operation)
        await execute(self.page, operation['action_type'], args)
        self.assertEqual(await self.page.locator('#choice').input_value(), 'seven')

    async def test_transparent_select_text_is_not_named_from_dom_option(self):
        state, element = await self.surface(css='select{color:transparent}')
        with self.assertRaisesRegex(ValueError, 'original label'):
            await operation_from_decision(self.page, state, self.decision(element))

    async def test_partially_occluded_control_is_rejected_with_center_still_exposed(self):
        overlay = '<div style="position:absolute;left:40px;top:40px;width:12px;height:34px;background:white;z-index:9"></div>'
        state, element = await self.surface(overlay=overlay)
        with self.assertRaisesRegex(ValueError, 'original label'):
            await operation_from_decision(self.page, state, self.decision(element))

    async def test_truncated_selected_text_is_rejected(self):
        state, element = await self.surface(css='select{width:40px}')
        with self.assertRaisesRegex(ValueError, 'original label'):
            await operation_from_decision(self.page, state, self.decision(element))

    async def test_disabled_select_remains_rejected(self):
        await self.surface(); await self.page.locator('#choice').evaluate('(node)=>node.disabled=true')
        state = (await capture(self.page))['state']
        element = next(row for row in state['elements'] if row.get('element_type') == 'select')
        with self.assertRaisesRegex(ValueError, 'enabled state'):
            await operation_from_decision(self.page, state, self.decision(element))

    async def test_changed_selection_after_original_png_is_not_silently_rebound(self):
        state, element = await self.surface()
        await self.page.locator('#choice').evaluate('(node)=>node.selectedIndex=1')
        with self.assertRaisesRegex(ValueError, 'changed after the original'):
            await operation_from_decision(self.page, state, self.decision(element))


if __name__ == '__main__':
    unittest.main()
