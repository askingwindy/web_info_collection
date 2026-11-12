"""Three offline core contracts for strategy 2; no model or real browser."""
import asyncio
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from webcollect.batch_core import file_sha
from webcollect.screenshot_effect import atomic_effect, step_expectation, input_changes
from webcollect.screenshot_execution import (bind_plan_targets, bind_target, compile_step,
                                             resolve_control, react_step)
from webcollect.screenshot_native_observation import action_availability
from webcollect.screenshot_observation import (body_element_ids, controls_projection, crop_visual,
                                               interaction_affordances, prepare_visuals,
                                               verify_visuals)


def control(cid='input1', selector='#amount'):
    return {'element': {'element_id': cid, 'native_role': 'input', 'text': '',
                        'visible': True, 'enabled': True, 'inputable': True,
                        'clickable': True, 'bbox': [20, 30, 120, 55]},
            'binding': {'element_id': cid, 'selector': selector, 'index': 0, 'tag': 'input'},
            'readable_labels': [{'kind': 'rendered_associated_label', 'text': '金额'}],
            'value': {'element_id': cid, 'value': '', 'value_visible': True, 'readonly': False, 'input_type': 'text'},
            'actions': {}}


def observation():
    return {'observation_id': 'observation-current', 'document_identity': 'doc-current',
            'viewport': [200, 100], 'controls': {'input1': control(),
                                               'hidden': control('hidden', '#hidden')}}


def node(element_id, role, text, parent, *, clickable=True, top=0):
    return {'element_id': element_id, 'native_role': role, 'element_type': 'link', 'text': text,
            'parent_id': parent, 'visible': True, 'enabled': True, 'clickable': clickable,
            'inputable': False, 'scrollable': False, 'state': 'default',
            'bbox': [10, top, 120, top + 20]}


def reading_observation(root):
    """One long-reading frame: article links, navigation links, passive wrappers.

    The navigation sits inside `main`, so only the nearest role can decide it.
    """
    tree = [node('root', 'body', '', None, clickable=False),
            node('main-1', 'main', '', 'root', clickable=False),
            node('nav-1', 'nav', '', 'main-1', clickable=False, top=20),
            node('link-body', 'a', '月球', 'main-1', top=40),
            node('wrapper-1', 'div', '容器', 'main-1', clickable=False, top=60),
            node('link-chrome', 'a', '登录', 'nav-1', top=80)]
    state = {'url': 'https://example.test/article', 'elements': tree,
             'visible_text': '月球 容器 登录', 'screen_resolution': [200, 100]}
    path = root / 'state.json'
    path.write_text(json.dumps(state), encoding='utf-8')
    controls = {row['element_id']: {'element': row, 'readable_labels': [], 'value': {}, 'actions': {},
                                    'binding': {'element_id': row['element_id'], 'tag': row['native_role'],
                                                'selector': f'#{row["element_id"]}'}}
                for row in tree if row['native_role'] in ('a', 'div')}
    return state, {'observation_id': 'observation-reading', 'document_identity': 'doc-reading',
                   'viewport': [200, 100], 'controls': controls,
                   'evidence': {'state': {'path': str(path), 'sha256': file_sha(path)}}}


def png(width, height):
    stream = BytesIO()
    Image.new('RGB', (width, height), 'white').save(stream, format='PNG')
    return stream.getvalue()


class VisualPage:
    """Only native read APIs used by overview capture; actions are absent."""
    def __init__(self, state):
        self.state = deepcopy(state)
        self.full_page_requests = 0

    async def evaluate(self, script, options=None):
        if script.startswith('() => [Math.max'):
            return [200, 4000]
        return deepcopy(self.state)

    async def screenshot(self, **kwargs):
        if kwargs.get('full_page') is not True:
            raise AssertionError('Overview must request real full-page pixels')
        self.full_page_requests += 1
        return png(200, 4000)


class Strategy2VisualCore(unittest.TestCase):
    def test_plan_target_provenance_rebind_and_wrong_object_refusal(self):
        from webcollect.screenshot_plan import first_plan_admission, normalize_submit_plan
        route_plan = {'goal': '读取结果并根据页面依据核对',
            'requirements': [
                {'id': 'result', 'kind': 'result', 'description': '读取业务结果',
                 'evidence_route': {'source_type': 'page_result', 'observation_steps': [3]}},
                {'id': 'check', 'kind': 'content', 'description': '核对结果',
                 'evidence_route': {'source_type': 'derived_check', 'observation_steps': [4], 'depends_on': ['result']}}],
            'final_presentation_step': 5,
            'steps': [{'action': 'scroll', 'direction': 'down', 'purpose': '读取必要依据',
                       'rationale': '计划前提：需要读取目标依据', 'expected_result': '必要依据进入视口'} for _ in range(5)]}
        normalized, _ = normalize_submit_plan(route_plan)
        self.assertEqual(normalized, route_plan)
        self.assertTrue(first_plan_admission(normalized)[0])
        invalid_route = deepcopy(route_plan)
        invalid_route['requirements'][1]['evidence_route']['observation_steps'] = [6]
        self.assertEqual(first_plan_admission(invalid_route)[1]['kind'], 'EVIDENCE_ROUTE_INVALID')
        invalid_route['requirements'][1]['evidence_route']['observation_steps'] = [4]
        invalid_route['requirements'][1]['evidence_route']['depends_on'] = ['unknown']
        self.assertFalse(first_plan_admission(invalid_route)[0])
        invalid_route = deepcopy(route_plan)
        invalid_route['requirements'][0].pop('evidence_route')
        self.assertEqual(first_plan_admission(invalid_route)[1]['kind'], 'PLAN_FIELDS_INVALID')
        original = observation()
        original['provided_control_ids'] = ['input1']
        rows = controls_projection(original, ['click', 'type'])
        numeric = {'steps': [{'action': 'click', 'target': {'control': str(rows[0]['number'])}}]}
        bind_plan_targets(numeric, original)
        self.assertEqual(numeric['steps'][0]['target']['control'], rows[0]['control'])
        self.assertEqual(numeric['steps'][0]['target']['_source']['mark_number'], 1)
        conflict = deepcopy(original)
        conflict['controls']['1'] = control('1')
        conflict['provided_control_ids'].append('1')
        with self.assertRaisesRegex(ValueError, 'CONTROL_NUMBER_CONFLICT'):
            bind_plan_targets({'steps': [{'target': {'control': '1'}}]}, conflict)
        with self.assertRaisesRegex(ValueError, 'CONTROL_TARGET_CONFLICT'):
            bind_plan_targets({'steps': [{'target': {'control': '1', 'text': '错误金额'}}]}, original)
        original['provided_control_ids'] = ['input1']
        plan = {'steps': [{'action': 'click', 'target': {'control': 'input1'}}]}
        bind_plan_targets(plan, original)
        target = plan['steps'][0]['target']
        self.assertEqual(resolve_control(original, target), ['input1'])
        with self.assertRaisesRegex(ValueError, 'CONTROL_NOT_PROVIDED'):
            bind_plan_targets({'steps': [{'target': {'control': 'hidden'}}]}, original)
        drifted = deepcopy(original)
        drifted['controls']['input1']['binding']['selector'] = '#other'
        self.assertEqual(resolve_control(drifted, target), [])
        rerendered = deepcopy(original)
        rerendered['controls'] = {'new-input': control('new-input')}
        self.assertEqual(resolve_control(rerendered, target), ['new-input'])
        rerendered['controls']['duplicate'] = control('duplicate')
        self.assertEqual(resolve_control(rerendered, target), [])
        rerendered['document_identity'] = 'new-document'
        self.assertEqual(resolve_control(rerendered, target), [])

        with tempfile.TemporaryDirectory() as temporary:
            state, reading = reading_observation(Path(temporary))
            body_ids = body_element_ids(state)
            self.assertEqual({'link-body', 'wrapper-1'}, body_ids & {'link-body', 'wrapper-1', 'link-chrome'})
            rows = controls_projection(reading, ['click', 'scroll'], body_ids=body_ids)
            # The passive wrapper is never dispatchable and the article link must
            # outrank the navigation link, or a long page projects only chrome.
            self.assertEqual([row['control'] for row in rows], ['link-body', 'link-chrome'])
            self.assertEqual([row['number'] for row in rows], [1, 2])
            affordances = interaction_affordances(rows, body_ids)
            self.assertEqual(affordances['kinds'], ['body_link', 'chrome_link'])
            self.assertEqual(affordances['groups'][0]['examples'], ['月球'])
            self.assertEqual(controls_projection(reading, ['click', 'scroll'], limit=1)[0]['control'],
                             'link-body')
            # A region-only scroll target legally declares no text; absence is no
            # constraint, and used to raise KeyError instead of binding.
            self.assertEqual(bind_target(reading, {'role': 'a'}), ['link-body', 'link-chrome'])

    def test_visual_overview_crop_preserves_original_and_bound_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            obs = observation()
            obs['controls'].pop('hidden')
            state = {'url': 'https://example.test/form', 'document_identity': obs['document_identity'],
                     'scroll': [0, 0], 'elements': [obs['controls']['input1']['element']],
                     'values': [], 'visible_text': '金额'}
            original = root / 'original.png'
            original.write_bytes(png(200, 100))
            state_path = root / 'original.json'
            state_path.write_text(json.dumps(state), encoding='utf-8')
            obs['evidence'] = {'image': {'path': str(original), 'sha256': file_sha(original)},
                               'state': {'path': str(state_path), 'sha256': file_sha(state_path)}}
            original_bytes = original.read_bytes()
            controls_projection(obs, ['click', 'type'])
            page = VisualPage(state)
            visuals = asyncio.run(prepare_visuals(obs, root, page, first=True))
            overview, viewport = visuals
            self.assertEqual(page.full_page_requests, 1)
            self.assertEqual(viewport['control_mapping'][0]['control'], 'input1')
            self.assertNotEqual(Path(viewport['path']).read_bytes(), original_bytes)
            self.assertLess(overview['scale'], 1)
            crop = crop_visual(obs, root, [0, 100, 180, 300], image_ref=overview['ref'])
            self.assertEqual(crop_visual(obs, root, [0, 100, 180, 300], image_ref=overview['ref']), crop)
            # The same sealed source metadata is sufficient when the overview
            # itself is omitted to keep the actual model request within its cap.
            self.assertEqual(verify_visuals(obs, [viewport, crop]), [viewport['path'], crop['path']])
            self.assertEqual(original.read_bytes(), original_bytes)
            forged = deepcopy(crop)
            forged['parent_visual']['before_state']['sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                verify_visuals(obs, [viewport, forged])
            with self.assertRaisesRegex(ValueError, 'NOT_PROVIDED'):
                crop_visual(obs, root, [0, 0, 20, 20], image_ref='unseen-image')

    def test_atomic_input_focus_select_value_and_observed_effect_chain(self):
        c = control()
        state = {'screen_resolution': [200, 100], 'document_identity': 'doc-current',
                 'url': 'https://example.test/form', 'scroll': [0, 0],
                 'elements': [c['element']], 'values': [c['value']], 'visible_text': ''}
        probe = {'element_id': 'input1', 'focused': False, 'hit_valid': True,
                 'bbox': c['element']['bbox'], 'coordinate': [50, 40],
                 'visible_label_evidence': c['readable_labels']}
        c['probe'] = probe
        c['actions']['type'] = action_availability(state, c['element'], c['binding'], c['value'], probe, 'type')
        obs = {'controls': {'input1': c}}
        task = {'fragment': {'allowed_actions': ['type', 'select', 'hotkey']}}
        step = {'action': 'type', 'control_id': 'input1', 'value': '42', 'expected_value': '42', 'goal': '输入金额', 'expected': '金额为42'}
        with self.assertRaisesRegex(ValueError, 'TYPE_REQUIRES_CURRENT_FOCUS'):
            compile_step(task, [], step, obs)
        probe['focused'] = True
        c['actions']['type'] = action_availability(state, c['element'], c['binding'], c['value'], probe, 'type')
        rows = compile_step(task, [], step, obs)
        self.assertEqual([row['action'] for row in rows], ['type'])
        # A real click's ordinary observation proves focus without retaining
        # a targeted probe; keys still get a fresh probe before dispatch.
        focused = deepcopy(c)
        focused['probe'] = None
        focused['value'].update(focused=True, input_type='number', value='17')
        focused['element']['state'] = 'focused'
        focused_obs = {'controls': {'input1': focused}}
        select_all = {'action': 'hotkey', 'control_id': 'input1', 'keys': ['ctrl', 'a'],
                      'goal': '全选原数值', 'expected': '原数值已全选'}
        self.assertEqual(compile_step(task, [], select_all, focused_obs)[0]['keys'], ['ctrl', 'a'])
        with self.assertRaisesRegex(ValueError, 'HOTKEY_REQUIRES_CURRENT_TARGET_FOCUS'):
            compile_step(task, [], {**select_all, 'control_id': None}, focused_obs)
        focused['value']['focused'] = False
        focused['element']['state'] = ''
        with self.assertRaisesRegex(ValueError, 'HOTKEY_REQUIRES_CURRENT_TARGET_FOCUS'):
            compile_step(task, [], select_all, focused_obs)
        # Replacement uses the observed selection, not a preceding double click.
        c['value'].update(value='17', focused=True, selection_start=2, selection_end=2)
        with self.assertRaisesRegex(ValueError, 'TYPE_INSERTION_EXPECTATION_MISMATCH'):
            compile_step(task, [], step, obs)
        self.assertEqual(compile_step(task, [], {**step, 'expected_value': '1742'}, obs)[0]['value'], '42')
        c['value'].update(input_type='number', selection_start=None, selection_end=None,
                          all_text_selected=False)
        with self.assertRaisesRegex(ValueError, 'TYPE_REPLACEMENT_REQUIRES_OBSERVED_SELECTION_OR_EMPTY_VALUE'):
            compile_step(task, [], step, obs)
        # A browser lacking numeric selection evidence stays unknown; after-value
        # verification remains mandatory instead of an impossible selection gate.
        c['value'].pop('all_text_selected')
        self.assertEqual(compile_step(task, [], step, obs)[0]['value'], '42')
        # The later real targeted observation confirms numeric full selection.
        c['value'].update(input_type='number', value='17', focused=True, all_text_selected=True)
        numeric_rows = compile_step(task, [], step, obs)
        self.assertEqual([row['action'] for row in numeric_rows], ['type'])
        self.assertEqual(numeric_rows[0]['replace_selected_number'], '17')
        after = deepcopy(state)
        after['values'][0]['value'] = rows[0]['value']
        self.assertTrue(atomic_effect(state, after, 'type', {'text': rows[0]['value']}, 'input1')['verified'])
        self.assertFalse(atomic_effect(after, after, 'type', {'text': '42'}, 'input1')['verified'])
        compiled = react_step({**step, 'purpose': '输入金额', 'expected_result': '金额为42',
                               'rationale': '输入框可见'}, ['input1'], lambda _: [])
        self.assertEqual(compiled['expected_value'], '42')
        wrong = deepcopy(after); wrong['values'][0]['value'] = '1742'
        self.assertTrue(atomic_effect(state, wrong, 'type', {'text': '42'}, 'input1')['verified'])
        self.assertFalse(step_expectation(compiled, wrong, 'input1')['matched'])
        cleared = deepcopy(state); cleared['values'][0].update(value='', selection_start=0, selection_end=0)
        self.assertTrue(atomic_effect(state, cleared, 'hotkey', {'keys': ['backspace']}, 'input1')['verified'])
        self.assertEqual(input_changes(state, cleared, 'input1')[0]['after'], '')
        self.assertFalse(atomic_effect(cleared, cleared, 'hotkey', {'keys': ['backspace']}, 'input1')['verified'])
        projection_control = deepcopy(c); projection_control['value'] = cleared['values'][0]
        projection_control['value'].update(focused=True, value_visible=True)
        projected = controls_projection({'controls': {'input1': projection_control}, 'viewport': [200, 100]}, ['type'])[0]
        self.assertEqual(projected['value'], '')
        self.assertTrue(projected['focused'])
        projection_control['value'].update(value='hidden', value_visible=False)
        projected = controls_projection({'controls': {'input1': projection_control}, 'viewport': [200, 100]}, ['type'])[0]
        self.assertNotIn('value', projected)

        choice = control('choice', '#unit')
        choice['binding'].update(tag='select', options=[{'value': 'cm', 'label': '厘米'},
                                                     {'value': 'm', 'label': '米'}])
        choice['value']['value'] = 'cm'
        choice['actions']['select'] = {'status': 'PROVEN'}
        obs['controls']['choice'] = choice
        select = {'action': 'select', 'control_id': 'choice', 'value': 'm', 'expected_value': 'm', 'goal': '切换单位', 'expected': '米'}
        self.assertEqual(compile_step(task, [], select, obs)[0]['option'], '米')
        with self.assertRaisesRegex(ValueError, 'SELECT_OPTION_NOT_PROVEN'):
            compile_step(task, [], {**select, 'value': '米'}, obs)
        choice['binding']['options'][1]['disabled'] = True
        with self.assertRaisesRegex(ValueError, 'SELECT_OPTION_NOT_PROVEN'):
            compile_step(task, [], select, obs)
