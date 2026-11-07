"""2026-11-07 reading first-frame binding fixes; synthetic IO only.

Reproduces the wwiki A/B failure shapes against synthetic pages:
- A: a prose string used as target.node in the first plan;
- B: ARIA role words (textbox) + unproved region prose + wrong parent_text on a
  semantic target, repeated across zero-action replans.
Covers the fixes: role vocabulary equivalence, advisory semantic rebinding,
stale/prose node stripping, actionable binding diagnosis, the bounded
same-miss stop, the V11 hint simplification, and a full search->article->
scroll->cite reading chain that saves and derives.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from test_react_session import ReactHarness, FakePage, make_png
from test_banded_plan import plan_for
from test_closing_policy_v2 import EndingV2Tests
from webcollect.batch_core import load_json
from webcollect.banded_plan import (
    V10_VERSION, V11_VERSION, bind_reply_scope, bind_target, binding_diagnosis,
    roles_equivalent, REPEATED_BINDING_MISS_LIMIT,
)
from webcollect.closing_policy import V2_VERSION as END_V2, VERSION as END_V3, annotation_errors
from webcollect.goal_evidence import VERSION as EVIDENCE_VERSION
from webcollect.react_session import ReactSession, build_url_task

HOME = 'https://reading.example.org/'
RESULTS = 'https://reading.example.org/search?q=%E6%9C%88%E9%A3%9F'
WRONG = 'https://reading.example.org/wiki/yueshi-xianxiang'
ARTICLE = 'https://reading.example.org/wiki/%E6%9C%88%E9%A3%9F'
SUBJECT = '月食'
INTRO = '月食是一种可见的天文现象，本条目介绍其观察记录与成因脉络。'
MID = '历史记录显示该现象出现的周期与轨道位置相关，观测机构整理了系统资料。'
ASPECTS_BODY = '发生月食时，月球整体进入地球的本影区，此时月球位于地球背向太阳的一侧。'


class ReadingSurface:
    """Synthetic on-site search -> article site with the same capture shape."""

    def __init__(self):
        self.page = 'home'
        self.history = [HOME]
        self.q_value = ''
        self.focused = None
        self.scroll = 0
        self.navigations = 0
        self.executed = []
        self.readable = True
        self.state = self._render()

    # ---- page models -------------------------------------------------
    def _elements(self):
        if self.page == 'home':
            return [
                {'element_id': 'e_form', 'native_role': 'form', 'text': '', 'parent_id': 'root'},
                {'element_id': 'e_q', 'native_role': 'input', 'text': '搜索', 'parent_id': 'e_form',
                 'inputable': True, 'clickable': True},
                {'element_id': 'e_btn', 'native_role': 'button', 'text': '搜索', 'parent_id': 'e_form',
                 'clickable': True},
                {'element_id': 'e_intro', 'native_role': 'p', 'text': '输入关键词开始站内检索。', 'parent_id': 'root'},
            ]
        if self.page == 'results':
            return [
                {'element_id': 'e_note', 'native_role': 'p', 'text': '站内检索结果如下。', 'parent_id': 'root'},
                {'element_id': 'e_l1', 'native_role': 'a', 'text': '月食的基本现象', 'parent_id': 'root',
                 'clickable': True},
                {'element_id': 'e_l2', 'native_role': 'a', 'text': SUBJECT, 'parent_id': 'root',
                 'clickable': True},
            ]
        if self.page == 'wrong':
            return [
                {'element_id': 'e_h', 'native_role': 'h1', 'text': '月食的基本现象', 'parent_id': 'root'},
                {'element_id': 'e_p', 'native_role': 'p', 'text': '本页介绍该现象的一般描述，不含目标位置关系。',
                 'parent_id': 'root'},
            ]
        rows = [
            {'element_id': 'e_h', 'native_role': 'h1', 'text': SUBJECT, 'parent_id': 'root'},
            {'element_id': 'e_p1', 'native_role': 'p', 'text': INTRO, 'parent_id': 'root'},
        ]
        if self.scroll >= 1:
            rows.append({'element_id': 'e_p2', 'native_role': 'p', 'text': MID, 'parent_id': 'root'})
        if self.scroll >= 2:
            rows.append({'element_id': 'e_p3', 'native_role': 'p', 'text': ASPECTS_BODY, 'parent_id': 'root'})
        return rows

    def _bindings(self):
        if self.page == 'home':
            return [
                {'element_id': 'e_form', 'selector': 'main:1 > form:1', 'tag': 'form', 'href': None, 'form_index': 0},
                {'element_id': 'e_q', 'selector': 'main:1 > form:1 > input:1', 'tag': 'input', 'href': None,
                 'input_type': 'search', 'form_index': 0},
                {'element_id': 'e_btn', 'selector': 'main:1 > form:1 > button:1', 'tag': 'button', 'href': None, 'form_index': 0},
                {'element_id': 'e_intro', 'selector': 'main:1 > p:1', 'tag': 'p', 'href': None},
            ]
        if self.page == 'results':
            return [
                {'element_id': 'e_note', 'selector': 'main:1 > p:1', 'tag': 'p', 'href': None},
                {'element_id': 'e_l1', 'selector': 'main:1 > a:1', 'tag': 'a', 'href': WRONG},
                {'element_id': 'e_l2', 'selector': 'main:1 > a:2', 'tag': 'a', 'href': ARTICLE},
            ]
        if self.page == 'wrong':
            return [
                {'element_id': 'e_h', 'selector': 'main:1 > h1:1', 'tag': 'h1', 'href': None},
                {'element_id': 'e_p', 'selector': 'main:1 > p:1', 'tag': 'p', 'href': None},
            ]
        rows = [
            {'element_id': 'e_h', 'selector': 'main:1 > h1:1', 'tag': 'h1', 'href': None},
            {'element_id': 'e_p1', 'selector': 'main:1 > p:1', 'tag': 'p', 'href': None},
        ]
        if self.scroll >= 1:
            rows.append({'element_id': 'e_p2', 'selector': 'main:1 > p:2', 'tag': 'p', 'href': None})
        if self.scroll >= 2:
            rows.append({'element_id': 'e_p3', 'selector': 'main:1 > p:3', 'tag': 'p', 'href': None})
        return rows

    def _url(self):
        return {'home': HOME, 'results': RESULTS, 'wrong': WRONG, 'article': ARTICLE}[self.page]

    def _title(self):
        return {'home': '站内检索', 'results': '检索结果', 'wrong': '月食的基本现象', 'article': SUBJECT}[self.page]

    def _render(self):
        elements = [{
            'element_id': 'e_main', 'native_role': 'main', 'text': '', 'parent_id': 'root',
            'clickable': False, 'inputable': False,
            'bbox': [0, 0, 900, 720], 'enabled': True, 'visible': True,
            'element_type': 'text', 'state': 'default', 'scrollable': False,
        }]
        for i, row in enumerate(self._elements()):
            row = dict(row)
            row.update(bbox=[10, 20 + i * 60, 640, 60 + i * 60], enabled=True, visible=True,
                       element_type='link' if row['native_role'] == 'a' else
                       ('input' if row.get('inputable') else 'text'),
                       state='default', scrollable=False,
                       clickable=row.get('clickable', False), inputable=row.get('inputable', False))
            elements.append(row)
        values = [] if self.page != 'home' else [{
            'element_id': 'e_q', 'value': self.q_value, 'focused': self.focused == 'e_q',
            'selection_start': 0, 'selection_end': 0, 'input_type': 'search', 'value_visible': True,
            'readonly': False, 'enabled': True,
        }]
        bindings = [{'element_id': 'e_main', 'selector': 'main:1', 'tag': 'main', 'href': None}] + self._bindings()
        witnesses = [{'element_id': e['element_id'],
                      'samples': [{'point': [i % 3, i // 3]} for i in range(9)]}
                     for e in elements]
        for w in witnesses:
            w['samples'][4] = {'point': [1, 1], 'ancestor': {'selector': 'main:1'}}
        return {'url': self._url(), 'title': self._title(),
                'document_identity': {'url_without_fragment': self._url(),
                                      'performance_time_origin': 1000 + self.navigations},
                'scroll': [0, self.scroll], 'screen_resolution': [1280, 720], 'target': None,
                'capture_readiness': {'schema_version': 'webcollect-capture-readiness-1',
                                      'document_ready': 'complete', 'fonts_ready': True, 'images_ready': True},
                'elements': elements, 'values': values,
                'capture_controls': bindings, 'geometry_witnesses': witnesses,
                'visible_text': self._title() + '\n' + '\n'.join(e['text'] for e in elements if e['text'])}

    # ---- surface protocol -------------------------------------------
    async def capture(self, page, selector=None, index=0, **kw):
        self.state = self._render()
        state = deepcopy(self.state)
        for value in state['values']:
            value['display_value'] = value['value']
        binding = next((b for b in state['capture_controls'] if b['selector'] == selector), None)
        if binding:
            eid = binding['element_id']
            row = next(e for e in state['elements'] if e['element_id'] == eid)
            value = next((v for v in state['values'] if v['element_id'] == eid), {})
            label = value.get('value') or '搜索'
            state['target'] = {'element_id': eid, 'coordinate': [30, row['bbox'][1] + 10],
                               'bbox': row['bbox'], 'hit_valid': True, 'focused': value.get('focused', False),
                               'value': value.get('value'), 'readonly': False,
                               'visible_label_evidence': [{'kind':
                                   'visible_native_value' if value.get('value') else 'visible_placeholder',
                                   'text': label}]}
        import base64, hashlib, time
        from webcollect.browser import CAPTURE_VERSION, fingerprint, stability_pair
        token = int(hashlib.sha256(json.dumps({k: self.state.get(k) for k in
            ('url', 'values', 'scroll', 'document_identity')}, sort_keys=True, default=str).encode()).hexdigest()[:6], 16)
        png = make_png(token)
        stability = stability_pair(state, state, png, png)
        if not stability['accepted']:
            raise AssertionError('synthetic v2 stability proof rejected: ' + str(stability))
        encoded = base64.b64encode(png).decode('ascii')
        started = time.time_ns()
        attempt = {'attempt': 1, 'started_ns': started, 'ended_ns': time.time_ns(),
                   'dom_stable': stability['full_dom_stable'], 'rejected_reason': None,
                   'delay_before_ms': 0.0, 'next_retry_delay_ms': 0.0, 'mismatch_fields': [],
                   'before_fingerprint': fingerprint(state), 'after_fingerprint': fingerprint(state),
                   'snapshot_before': state, 'snapshot_after': state, 'snapshot_final': state,
                   'original_png_base64': encoded, 'comparison_png_base64': encoded,
                   'comparison_screenshot': 'synthetic', 'stability': stability,
                   'final_stability': stability}
        return {'state': state, 'png': png, 'capture': {'schema_version': CAPTURE_VERSION,
            'snapshot_source': 'browser_dom', 'screenshot_sha256': hashlib.sha256(png).hexdigest(),
            'natural_wait_requested_ms': 0, 'natural_wait_observed_ms': 0, 'natural_wait_budget_ms': 8000,
            'coordinate_space': 'screenshot_css_pixels', 'attempts': [attempt]}}

    def _navigate(self, page):
        if page == 'back-target':
            self.page = self._page_for_url(self.history[-1])
        else:
            self.history.append({'home': HOME, 'results': RESULTS,
                                 'wrong': WRONG, 'article': ARTICLE}[page])
            self.page = page
        self.navigations += 1
        self.scroll = 0
        self.focused = None

    @staticmethod
    def _page_for_url(url):
        return {HOME: 'home', RESULTS: 'results', WRONG: 'wrong', ARTICLE: 'article'}.get(url, 'home')

    def execute_action(self, action_type, arguments):
        self.executed.append((action_type, deepcopy(arguments)))
        if action_type == 'click':
            x, y = arguments['x'], arguments['y']
            hit = None
            for e in self._elements():
                row = next(r for r in self.state['elements'] if r['element_id'] == e['element_id'])
                if row['bbox'][0] <= x < row['bbox'][2] and row['bbox'][1] <= y < row['bbox'][3]:
                    hit = e
            if hit and hit['element_id'] == 'e_q':
                self.focused = 'e_q'
            elif hit and hit['element_id'] == 'e_btn' and self.q_value == SUBJECT:
                # Exact-term submit lands directly on the article page.
                self._navigate('article')
            elif hit and hit.get('native_role') == 'a' and self.page == 'results':
                self._navigate('wrong' if hit['element_id'] == 'e_l1' else 'article')
        elif action_type == 'type':
            if self.focused == 'e_q':
                self.q_value = arguments['text']
        elif action_type == 'hotkey':
            keys = [str(k).lower() for k in arguments['keys']]
            if keys == ['enter'] and self.focused == 'e_q' and self.q_value == SUBJECT:
                self._navigate('results')
        elif action_type == 'scroll':
            if self.page == 'article' and self.scroll < 2:
                self.scroll += 1
        elif action_type == 'back':
            if len(self.history) > 1:
                self.history.pop()
                self._navigate('back-target')
        self.state = self._render()


class ReadingHarness(ReactHarness):
    def setUp(self):
        ReactHarness.setUp(self)
        self.surface = ReadingSurface()
        self.page = FakePage(self.surface)
        capture = patch('webcollect.browser.capture', side_effect=self.surface.capture)
        capture.start()
        self.addCleanup(capture.stop)
        self.ids = {'sample_id': 'S000001_sample_000001', 'site_id': 'S000001',
                    'batch_id': 'B20261107_002', 'attempt_id': 'offline-reading'}
        self.manifest = {'batch_id': 'B20261107_002', 'sample_kind': 'real',
                         'program_version': 'CONTROLLED', 'rule_version': '1.0.0',
                         'sites': [{'site_id': 'S000001', 'uri': HOME, 'site_category': 'reading'}],
                         'samples': [self.ids['sample_id']]}

    OBJECTIVE = {
        'kind': 'reading',
        'description': '从站内入口检索月食，打开条目并向下阅读，用正文说明月球与地球的位置关系。',
        'minimum_effective_steps': 5, 'preferred_band': 'five',
        'evidence_contract': {'version': EVIDENCE_VERSION, 'kind': 'reading',
                              'subject': SUBJECT, 'aspects': ['月球', '地球']}}

    def reading_task(self, plan_protocol=V11_VERSION, ending_policy=END_V3):
        """Seal the reading objective into the frozen spec (struct_goal path), so
        contract_for resolves it for prompts, runtime evidence and the offline
        derivation replay alike, without a candidate claim binding."""
        from webcollect.planning import object_sha256
        task = build_url_task(url=HOME, task_version='reading', ending_policy=ending_policy,
                              plan_protocol=plan_protocol,
                              action_stability_protocol='webcollect-post-action-observation-stability-4')
        spec = task['workflow_proposal']['spec']
        spec['goal'] = {'instruction': self.OBJECTIVE['description'],
                        'structured': deepcopy(self.OBJECTIVE)}
        task['task_id'] = 'react-' + object_sha256({'url': spec.get('entry_url'), 'spec': spec})[:24]
        return task


class RoleVocabularyTests(unittest.TestCase):
    def test_aria_names_match_native_tags_and_wrong_kinds_do_not(self):
        self.assertTrue(roles_equivalent('textbox', 'input'))
        self.assertTrue(roles_equivalent('searchbox', 'input'))
        self.assertTrue(roles_equivalent('link', 'a'))
        self.assertTrue(roles_equivalent('button', 'button'))
        self.assertTrue(roles_equivalent('input', 'input'))
        self.assertFalse(roles_equivalent('button', 'input'))
        self.assertFalse(roles_equivalent('textbox', 'button'))
        self.assertTrue(roles_equivalent(None, 'input'))

    def test_bind_reply_scope_strips_prose_node_for_modern_and_raises_for_old(self):
        modern = {'attempt_id': 'a', 'observation': {'observation_id': 'o',
                   'rendered_dom': [{'node': 'e_1', 'text': 'x'}], '_node_scope': ['e_1']},
                  'protocol': V11_VERSION}
        arguments = {'attempt_id': 'a', 'observation_id': 'o',
                     'steps': [{'target': {'node': '页头站内搜索框', 'text': 'x'}}]}
        bound = bind_reply_scope(deepcopy(arguments), modern)
        self.assertEqual(bound['steps'][0]['target'], {'text': 'x'})
        self.assertEqual(bind_reply_scope(deepcopy(arguments), {**modern, 'protocol': V10_VERSION}),
                         bound)
        old = {**modern, 'protocol': 'webcollect-banded-conditional-plan-7'}
        with self.assertRaises(ValueError):
            bind_reply_scope(deepcopy(arguments), old)
        # A node-less target with no text cannot fall back to semantics: reject.
        with self.assertRaises(ValueError):
            bind_reply_scope({'attempt_id': 'a', 'observation_id': 'o',
                              'steps': [{'target': {'node': 'gone'}}]}, modern)


class SemanticRebindTests(ReadingHarness, unittest.IsolatedAsyncioTestCase):
    async def test_wwiki_shape_semantic_target_rebinds_only_with_advisory(self):
        session = ReactSession(self.reading_task(), self.root / 'rebind' / 'raw', None, self.page)
        await session._observe()
        target = {'text': '搜索', 'role': 'textbox', 'region': '页首', 'parent_text': '搜索'}
        self.assertEqual(bind_target(session.current, target, advisory=True), ['e_q'])
        # Historical strict matching keeps rejecting the over-specified form.
        self.assertEqual(bind_target(session.current, target, advisory=False), [])
        # Role equivalence alone (no prose extras) binds in strict mode too.
        self.assertEqual(bind_target(session.current, {'text': '搜索', 'role': 'textbox'}), ['e_q'])

    async def test_directional_region_stays_hard_and_ambiguity_stays_model_choice(self):
        session = ReactSession(self.reading_task(), self.root / 'hard' / 'raw', None, self.page)
        await session._observe()
        self.assertEqual(bind_target(session.current,
            {'text': '搜索', 'role': 'textbox', 'region': '左栏'}, advisory=True), [])
        session.current['controls']['e_btn']['element']['text'] = '搜索维基百科'
        session.current['controls']['e_q']['element']['text'] = '搜索维基百科'
        self.assertEqual(len(bind_target(session.current,
            {'text': '搜索维基百科', 'role': 'textbox', 'region': '页首'}, advisory=True)), 1)

    async def test_binding_diagnosis_names_the_vocabulary_mismatch(self):
        session = ReactSession(self.reading_task(), self.root / 'diag' / 'raw', None, self.page)
        await session._observe()
        result = binding_diagnosis(session.current,
                                   {'text': '搜索', 'role': 'textbox', 'region': '页首', 'parent_text': '搜索'})
        self.assertEqual([c['node'] for c in result['candidates']], ['e_q', 'e_btn'])
        self.assertTrue(any('region' in issue for issue in result['issues']))
        self.assertTrue(any('parent_text' in issue for issue in result['issues']))
        absent = binding_diagnosis(session.current, {'text': '不存在的目标'})
        self.assertTrue(any('当前帧没有可见标签' in issue for issue in absent['issues']))


class ReadingChainTests(ReadingHarness, unittest.IsolatedAsyncioTestCase):
    derive = EndingV2Tests.derive

    def scripted(self, name, plan, branches, task=None):
        self.prompts = []
        replies = list(branches)

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if len(self.prompts) == 1:
                return {'name': 'submit_plan', 'arguments': plan(prompt), 'tool_call_id': 'provider-first',
                        'assistant_message': {'role': 'assistant', 'tool_calls': []}, 'request_id': 'mock'}
            if not replies:
                raise AssertionError('unexpected extra model request')
            reply = replies.pop(0)
            return reply(prompt) if callable(reply) else deepcopy(reply)

        evidence = self.root / name / 'evidence' / self.ids['sample_id']
        session = ReactSession(self.reading_task() if task is None else task, evidence / 'raw',
                               choose, self.page, steps_directory=evidence, attempt_id='offline-reading')
        return session, evidence

    @staticmethod
    def reading_plan(prompt, *, first_target):
        return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
                'band': 'five', 'band_reason': '站内检索进入条目并向下阅读的自然五步链路',
                'goal': '站内检索月食并向下阅读正文，说明月球与地球的位置关系',
                'checks': [{'field': '月球与地球的位置关系'}],
                'steps': [
                    {'action': 'click', 'target': first_target,
                     'purpose': '聚焦站内搜索框', 'expected': {'kind': 'focused', 'text': '搜索'}},
                    {'action': 'type', 'target': {'text': '搜索', 'role': 'textbox'},
                     'value': SUBJECT, 'purpose': '输入检索词',
                     'expected': {'kind': 'value', 'text': SUBJECT}},
                    {'action': 'click', 'target': {'text': '搜索', 'role': 'button'},
                     'purpose': '提交站内检索', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
                    {'action': 'scroll', 'direction': 'down', 'purpose': '向下阅读正文前段',
                     'expected': {'kind': 'scroll_changed'}},
                    {'action': 'scroll', 'direction': 'down', 'purpose': '继续向下读到位置关系正文',
                     'expected': {'kind': 'scroll_changed'}},
                ],
                'finish_when': {'kind': 'goal_evidence'}, 'replan_when': '检索无结果或正文缺失'}

    async def test_search_open_scroll_cite_chain_saves_five_effective_steps(self):
        wwiki_b_shape = {'text': '搜索', 'role': 'textbox', 'region': '页首', 'parent_text': '搜索'}
        # wwiki-A shape: a prose node plus role/region prose; after the node is
        # stripped, the remaining text+role must still bind uniquely.
        wwiki_a_shape = {'node': '页头站内搜索框', 'text': '搜索', 'role': 'textbox', 'region': '页首'}
        for label, target in (('vocabulary', wwiki_b_shape), ('prose-node', wwiki_a_shape)):
            with self.subTest(target=label):
                self.surface.__init__()
                session, evidence = self.scripted(
                    label, lambda p, t=target: self.reading_plan(p, first_target=t),
                    [lambda p: {'attempt_id': p['attempt_id'],
                                'observation_id': p['observation']['observation_id'],
                                'choice': 'continue'},
                     lambda p: {'attempt_id': p['attempt_id'],
                                'observation_id': p['observation']['observation_id'],
                                'choice': 'cite:e_p3'}])
                result = await session.run()
                self.assertFalse(result['host_failure'], result)
                self.assertFalse(result['unknown'])
                self.assertEqual(result['stop_reason'], 'ready')
                self.assertEqual((result['effective_steps'], result['actual_actions']), (5, 5), result)
                self.assertFalse(result['short_flow'])
                self.assertEqual(result['collection_ending']['kind'], 'HOST_PLAN_ENDPOINT')
                self.assertEqual(len(self.prompts), 3)
                self.assertEqual([a for a, _ in self.surface.executed][:5],
                                 ['click', 'type', 'click', 'scroll', 'scroll'])
                terminal = load_json(evidence / 'raw' / 'terminal.json')
                objective = terminal['goal_evidence']['session_objective']
                self.assertEqual(objective['status'], 'VERIFIED')
                self.assertTrue(objective['downward_reading'])
                self.assertEqual(objective['search_inputs'][0]['query'], SUBJECT)
                self.assertTrue(objective['opened_results'])
                self.assertIn('月球', objective['selected_passage']['quote'])
                destination, annotation = self.derive(evidence, name='derived-' + label)
                # short_flow is only written when true; a normal sample omits it.
                self.assertNotIn('short_flow', annotation)
                self.assertEqual(len(annotation['steps']), 6)
                saved = annotation['steps'][-1]['tool_result']['return_value']['collection_ending']
                self.assertEqual(saved['verified_effective_steps'], 5)

    async def test_bottom_scroll_without_effect_is_not_an_effective_step(self):
        def plan(prompt):
            base = self.reading_plan(prompt, first_target={'text': '搜索', 'role': 'textbox'})
            base['band'] = 'long'
            base['band_reason'] = '含到底无效滚动的自然阅读链路'
            base['steps'] = base['steps'] + [
                {'action': 'scroll', 'direction': 'down', 'purpose': '已到底仍继续滚动凑步',
                 'expected': {'kind': 'scroll_changed'}}]
            return base

        def pad_scroll_replan(prompt):
            return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
                    'choice': 'replan', 'plan': {'steps': [
                        {'action': 'scroll', 'direction': 'down', 'purpose': '正文已读完仍试图再滚凑步',
                         'expected': {'kind': 'scroll_changed'}}]}}

        session, evidence = self.scripted(
            'bottom', plan,
            [lambda p: {'attempt_id': p['attempt_id'], 'observation_id': p['observation']['observation_id'],
                        'choice': 'continue'},
             # Offered the citation, the model instead insists on one more scroll.
             pad_scroll_replan,
             lambda p: {'attempt_id': p['attempt_id'], 'observation_id': p['observation']['observation_id'],
                        'choice': 'cite:e_p3'}])
        result = await session.run()
        # The sixth scroll dispatched at the article bottom with no position
        # change: an honest no-effect action never becomes an effective step,
        # and its unverified tail flags the sample instead of upgrading it.
        self.assertEqual(result['effective_steps'], 5)
        self.assertEqual(len(self.surface.executed), 6)
        self.assertFalse(result['short_flow'])
        self.assertEqual(result['stop_reason'], 'blocked')
        self.assertEqual(result['collection_ending']['kind'], 'KNOWN_NO_EFFECT')


class BoundedMissStopTests(ReadingHarness, unittest.IsolatedAsyncioTestCase):
    def scripted(self, name, task):
        self.prompts = []
        missing = {'text': '不存在的目标', 'role': 'textbox'}

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if len(self.prompts) == 1:
                return {'name': 'submit_plan', 'tool_call_id': 'provider-first',
                        'assistant_message': {'role': 'assistant', 'tool_calls': []}, 'request_id': 'mock',
                        'arguments': {'attempt_id': prompt['attempt_id'],
                                      'observation_id': prompt['observation']['observation_id'],
                                      'band': 'short', 'short_reason': '自然短流程',
                                      'goal': '找不到目标', 'checks': [],
                                      'steps': [{'action': 'click', 'target': missing,
                                                 'purpose': '点击不存在的目标',
                                                 'expected': {'kind': 'focused', 'text': 'x'}}],
                                      'finish_when': {'kind': 'visible_text', 'text': '终点'},
                                      'replan_when': 'x'}}
            return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
                    'choice': 'replan', 'plan': {'steps': [
                        {'action': 'click', 'target': missing, 'purpose': '再次提交同一目标',
                         'expected': {'kind': 'focused', 'text': 'x'}}]}}

        evidence = self.root / name / 'evidence' / self.ids['sample_id']
        session = ReactSession(task, evidence / 'raw', choose, self.page,
                               steps_directory=evidence, attempt_id='offline-reading')
        return session

    async def test_repeated_same_miss_stops_bounded_with_diagnosis_feedback(self):
        for protocol, ending in ((V11_VERSION, END_V3), (V10_VERSION, END_V2)):
            with self.subTest(protocol=protocol):
                self.surface.__init__()
                session = self.scripted(f'stop-{protocol[-2:]}', self.reading_task(protocol, ending))
                result = await session.run()
                self.assertEqual(result['stop_reason'], 'budget')
                self.assertIn('有界停止', result['stop_summary'])
                self.assertEqual(result['actual_actions'], 0)
                self.assertEqual(len(self.prompts), REPEATED_BINDING_MISS_LIMIT)
                feedback = self.prompts[1]['binding_feedback']
                self.assertIn('diagnosis', feedback)
                self.assertTrue(any('当前帧没有可见标签' in issue for issue in
                                    feedback['diagnosis']['issues']))
                # The bounded stop is a host receipt, not a model-visible field.
                self.assertNotIn('remaining_effective_limit', feedback)

    async def test_v10_branch_bytes_keep_remaining_field_and_v11_drops_it(self):
        for protocol, ending, keeps in ((V10_VERSION, END_V2, True), (V11_VERSION, END_V3, False)):
            with self.subTest(protocol=protocol):
                self.surface.__init__()
                task = self.reading_task(protocol, ending)
                session = ReactSession(task, self.root / f'bytes-{protocol[-2:]}' / 'raw', None, self.page)
                await session._observe()
                controller = session.plan_controller
                initial = controller.prompt(session)
                controller.plan = plan_for(initial, 5)
                controller.submitted = True
                controller.frozen_band = 'five'
                branch = controller.prompt(session)
                contract = branch['replan_contract']
                self.assertEqual(contract['attempt_limit'], 8)
                if keeps:
                    self.assertIn('remaining_effective_limit', contract)
                    self.assertIn('只剩1步', contract['budget_instruction'])
                    self.assertNotIn('role须与rendered_dom行的role原值一致',
                                     branch['target_references']['usage'])
                    self.assertIn('只剩1步', json.dumps(branch, ensure_ascii=False))
                else:
                    self.assertNotIn('remaining_effective_limit', contract)
                    self.assertNotIn('只剩1步', json.dumps(branch, ensure_ascii=False))
                    self.assertIn('role须与rendered_dom行的role原值一致',
                                  branch['target_references']['usage'])


class MixedActionTests(ReadingHarness, unittest.IsolatedAsyncioTestCase):
    """Task D: the planner composes the full allowed action space (type, hotkey
    submit, click open, back return, scroll reading) in one legal trajectory."""

    derive = EndingV2Tests.derive

    def mixed_plan(self, prompt):
        return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
                'band': 'long', 'band_reason': '检索、错开、返回、打开与阅读的自然多阶段链路',
                'goal': '站内检索月食，途经关联页返回后打开条目并向下阅读位置关系正文',
                'checks': [{'field': '月球与地球的位置关系'}],
                'steps': [
                    {'action': 'click', 'target': {'text': '搜索', 'role': 'textbox'},
                     'purpose': '聚焦站内搜索框', 'expected': {'kind': 'focused', 'text': '搜索'}},
                    {'action': 'type', 'target': {'text': '搜索', 'role': 'textbox'}, 'value': SUBJECT,
                     'purpose': '输入检索词', 'expected': {'kind': 'value', 'text': SUBJECT}},
                    {'action': 'hotkey', 'keys': ['enter'],
                     'purpose': '用回车提交站内检索', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
                    {'action': 'click', 'target': {'text': '月食的基本现象'},
                     'purpose': '打开检索结果中的关联词条核对',
                     'expected': {'kind': 'document_changed', 'text': '月食的基本现象'}},
                    {'action': 'back', 'purpose': '从关联页返回检索结果',
                     'expected': {'kind': 'document_changed', 'text': SUBJECT}},
                    {'action': 'click', 'target': {'text': SUBJECT},
                     'purpose': '打开月食条目', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
                    {'action': 'scroll', 'direction': 'down', 'purpose': '向下阅读条目前段',
                     'expected': {'kind': 'scroll_changed'}},
                    {'action': 'scroll', 'direction': 'down', 'purpose': '继续向下读到位置关系正文',
                     'expected': {'kind': 'scroll_changed'}},
                ],
                'finish_when': {'kind': 'goal_evidence'}, 'replan_when': '检索无结果或正文缺失'}

    async def test_type_hotkey_click_back_scroll_compose_one_long_sample(self):
        self.prompts = []
        cite_offered = iter(())  # placeholder; chooser below decides per options

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if len(self.prompts) == 1:
                return {'name': 'submit_plan', 'arguments': self.mixed_plan(prompt),
                        'tool_call_id': 'provider-first', 'assistant_message': {'role': 'assistant', 'tool_calls': []},
                        'request_id': 'mock'}
            options = {option['choice'] for option in prompt.get('options', [])}
            cites = [choice for choice in options if choice.startswith('cite:')]
            if cites:
                return {'attempt_id': prompt['attempt_id'],
                        'observation_id': prompt['observation']['observation_id'],
                        'choice': sorted(cites)[-1]}
            return {'attempt_id': prompt['attempt_id'],
                    'observation_id': prompt['observation']['observation_id'],
                    'choice': 'continue'}

        evidence = self.root / 'mixed' / 'evidence' / self.ids['sample_id']
        session = ReactSession(self.reading_task(), evidence / 'raw', choose, self.page,
                               steps_directory=evidence, attempt_id='offline-reading')
        result = await session.run()
        self.assertFalse(result['host_failure'], result)
        self.assertEqual((result['effective_steps'], result['actual_actions']), (8, 8), result)
        self.assertEqual([action for action, _ in self.surface.executed],
                         ['click', 'type', 'hotkey', 'click', 'back', 'click', 'scroll', 'scroll'])
        self.assertFalse(result['short_flow'])
        self.assertEqual(result['collection_ending']['kind'], 'HOST_PLAN_ENDPOINT')
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        objective = terminal['goal_evidence']['session_objective']
        self.assertEqual(objective['status'], 'VERIFIED')
        self.assertEqual(len(objective['downward_reading']), 2)
        destination, annotation = self.derive(evidence, name='derived-mixed')
        saved = annotation['steps'][-1]['tool_result']['return_value']['collection_ending']
        self.assertEqual((saved['verified_effective_steps'], saved['attempt_band']), (8, 'long'))
        self.assertNotIn('short_flow', annotation)


if __name__ == '__main__':
    unittest.main()
