"""2026-11-07 direct-article full offline session and rule counterexamples.

Walks the constrained keyword-click/back/scroll protocol end to end against a
synthetic article: original-body scroll reading -> body keyword click -> cross
page landing -> immediate back with identity verification -> continued reading
-> citation -> verified save with independent replay, plus the four rule
counterexamples (same-page TOC, away-page scroll, wrong return, no-effect
repeat). No browser, site, model or QC service.
"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from test_react_session import ReactHarness, FakePage, make_png
from test_closing_policy_v2 import EndingV2Tests
from webcollect.batch_core import load_json
from webcollect.banded_plan import V11_VERSION
from webcollect.closing_policy import VERSION as END_V3
from webcollect.direct_article import VERSION as DIRECT_VERSION, transition, body
from webcollect.direct_completion import VERSION as COMPLETION_VERSION
from webcollect.react_session import ReactSession, build_url_task

ARTICLE = 'https://direct.example.org/wiki/lunar-eclipse'
RELATED = 'https://direct.example.org/wiki/orbit-basics'
TITLE = '月食的轨道与几何'
P1 = '月食发生需要月球、地球与太阳排成近似直线，本词条分章节整理成因与过程。'
P2 = '本影与半影的区别决定了月全食与月偏食的形态，历史记录常据此分类。'
P3 = '食甚时刻，月球整体位于地球本影之内，即月球处在地球背向太阳的一侧。'


class DirectArticleSurface:
    """The article is already open; keyword link leaves, back returns."""

    def __init__(self):
        self.page = 'article'
        self.history = [ARTICLE]
        self.scroll = 0
        self.navigations = 0
        self.executed = []
        self.readable = True
        self.state = self._render()

    def _rows(self):
        if self.page == 'related':
            return [
                {'element_id': 'e_h', 'native_role': 'h1', 'text': '轨道基础', 'parent_id': 'e_main'},
                {'element_id': 'e_p', 'native_role': 'p', 'text': '这是关联词条的正文，不属于原词条，不能当作原词条引用。', 'parent_id': 'e_main'},
            ]
        rows = [
            {'element_id': 'e_h', 'native_role': 'h1', 'text': TITLE, 'parent_id': 'e_main'},
            {'element_id': 'e_p1', 'native_role': 'p', 'text': P1, 'parent_id': 'e_main'},
            {'element_id': 'e_toc', 'native_role': 'a', 'text': '章节导航', 'parent_id': 'e_main', 'clickable': True},
            {'element_id': 'e_kw', 'native_role': 'a', 'text': '轨道关系', 'parent_id': 'e_main', 'clickable': True},
        ]
        if self.scroll >= 1:
            rows.append({'element_id': 'e_p2', 'native_role': 'p', 'text': P2, 'parent_id': 'e_main'})
        if self.scroll >= 2:
            rows.append({'element_id': 'e_p3', 'native_role': 'p', 'text': P3, 'parent_id': 'e_main'})
        return rows

    def _bindings(self):
        if self.page == 'related':
            return [
                {'element_id': 'e_main', 'selector': 'main:1', 'tag': 'main', 'href': None},
                {'element_id': 'e_h', 'selector': 'main:1 > h1:1', 'tag': 'h1', 'href': None},
                {'element_id': 'e_p', 'selector': 'main:1 > p:1', 'tag': 'p', 'href': None},
            ]
        rows = [
            {'element_id': 'e_main', 'selector': 'main:1', 'tag': 'main', 'href': None},
            {'element_id': 'e_h', 'selector': 'main:1 > h1:1', 'tag': 'h1', 'href': None},
            {'element_id': 'e_p1', 'selector': 'main:1 > p:1', 'tag': 'p', 'href': None},
            {'element_id': 'e_toc', 'selector': 'main:1 > a:1', 'tag': 'a', 'href': ARTICLE + '#sec2'},
            {'element_id': 'e_kw', 'selector': 'main:1 > a:2', 'tag': 'a', 'href': RELATED},
        ]
        if self.scroll >= 1:
            rows.append({'element_id': 'e_p2', 'selector': 'main:1 > p:2', 'tag': 'p', 'href': None})
        if self.scroll >= 2:
            rows.append({'element_id': 'e_p3', 'selector': 'main:1 > p:3', 'tag': 'p', 'href': None})
        return rows

    def _url(self):
        return RELATED if self.page == 'related' else ARTICLE

    def _title(self):
        return '轨道基础' if self.page == 'related' else TITLE

    def _render(self):
        elements = [{
            'element_id': 'e_main', 'native_role': 'main', 'text': '', 'parent_id': 'root',
            'clickable': False, 'inputable': False, 'bbox': [0, 0, 900, 720],
            'enabled': True, 'visible': True, 'element_type': 'text', 'state': 'default',
            'scrollable': False,
        }]
        for i, row in enumerate(self._rows()):
            row = dict(row)
            row.update(bbox=[10, 20 + i * 60, 640, 60 + i * 60], enabled=True, visible=True,
                       element_type='link' if row['native_role'] == 'a' else 'text',
                       state='default', scrollable=False,
                       clickable=row.get('clickable', False), inputable=False)
            elements.append(row)
        witnesses = [{'element_id': e['element_id'],
                      'samples': [{'point': [i % 3, i // 3]} for i in range(9)]} for e in elements]
        for witness in witnesses:
            witness['samples'][4] = {'point': [1, 1], 'ancestor': {'selector': 'main:1'}}
        return {'url': self._url(), 'title': self._title(),
                'document_identity': {'url_without_fragment': self._url(),
                                      'performance_time_origin': 1000 + self.navigations},
                'scroll': [0, self.scroll], 'screen_resolution': [1280, 720], 'target': None,
                'capture_readiness': {'schema_version': 'webcollect-capture-readiness-1',
                                      'document_ready': 'complete', 'fonts_ready': True, 'images_ready': True},
                'elements': elements, 'values': [], 'capture_controls': self._bindings(),
                'geometry_witnesses': witnesses,
                'visible_text': self._title() + '\n' + '\n'.join(e['text'] for e in elements if e['text'])}

    async def capture(self, page, selector=None, index=0, **kw):
        self.state = self._render()
        state = deepcopy(self.state)
        binding = next((b for b in state['capture_controls'] if b['selector'] == selector), None)
        if binding:
            row = next(e for e in state['elements'] if e['element_id'] == binding['element_id'])
            state['target'] = {'element_id': binding['element_id'], 'coordinate': [30, row['bbox'][1] + 10],
                               'bbox': row['bbox'], 'hit_valid': True, 'focused': False, 'value': None,
                               'visible_label_evidence': [{'kind': 'visible_label', 'text': row['text']}]}
        import base64, hashlib, time
        from webcollect.browser import CAPTURE_VERSION, fingerprint, stability_pair
        token = int(hashlib.sha256(json.dumps({k: self.state.get(k) for k in
            ('url', 'scroll', 'document_identity')}, sort_keys=True, default=str).encode()).hexdigest()[:6], 16)
        png = make_png(token)
        stability = stability_pair(state, state, png, png)
        if not stability['accepted']:
            raise AssertionError('synthetic v2 stability proof rejected: ' + str(stability))
        encoded = base64.b64encode(png).decode('ascii')
        attempt = {'attempt': 1, 'started_ns': time.time_ns(), 'ended_ns': time.time_ns(),
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

    def execute_action(self, action_type, arguments):
        self.executed.append((action_type, deepcopy(arguments)))
        if action_type == 'click':
            x, y = arguments['x'], arguments['y']
            hit = None
            for e in self._rows():
                row = next(r for r in self.state['elements'] if r['element_id'] == e['element_id'])
                if row['bbox'][0] <= x < row['bbox'][2] and row['bbox'][1] <= y < row['bbox'][3]:
                    hit = e
            if not hit:
                return
            if hit['element_id'] == 'e_toc':
                self.scroll = 2  # Same-page anchor jumps to the later section.
            elif hit['element_id'] == 'e_kw' and self.page == 'article':
                self.history.append(RELATED)
                self.page = 'related'
                self.navigations += 1
                self.scroll = 0
        elif action_type == 'scroll':
            if self.page == 'article' and self.scroll < 2:
                self.scroll += 1
        elif action_type == 'back':
            if len(self.history) > 1:
                self.history.pop()
                self.page = 'article'
                self.navigations += 1
                self.scroll = 0
        self.state = self._render()


class DirectArticleHarness(ReactHarness):
    def setUp(self):
        ReactHarness.setUp(self)
        self.surface = DirectArticleSurface()
        self.page = FakePage(self.surface)
        capture = patch('webcollect.browser.capture', side_effect=self.surface.capture)
        capture.start()
        self.addCleanup(capture.stop)
        self.ids = {'sample_id': 'S000001_sample_000001', 'site_id': 'S000001',
                    'batch_id': 'B20261107_003', 'attempt_id': 'offline-direct'}
        self.manifest = {'batch_id': 'B20261107_003', 'sample_kind': 'real',
                         'program_version': 'CONTROLLED', 'rule_version': '1.0.0',
                         'sites': [{'site_id': 'S000001', 'uri': ARTICLE, 'site_category': 'reading'}],
                         'samples': [self.ids['sample_id']]}

    def direct_task(self):
        from webcollect.planning import object_sha256
        task = build_url_task(url=ARTICLE, task_version='direct', ending_policy=END_V3,
                              plan_protocol=V11_VERSION)
        spec = task['workflow_proposal']['spec']
        spec['goal'] = {'instruction': '在已打开的月食词条内定位并阅读轨道关系正文',
                        'structured': {'kind': 'reading', 'preferred_band': 'five',
                            'minimum_effective_steps': 5,
                            'description': '在已打开的月食词条内定位并阅读轨道关系正文',
                            'evidence_contract': {'version': DIRECT_VERSION, 'kind': 'reading',
                                                  'entry_url': ARTICLE, 'titles': [TITLE]}}}
        spec['direct_completion_protocol'] = COMPLETION_VERSION
        task['fragment']['direct_completion_protocol'] = COMPLETION_VERSION
        task['task_id'] = 'react-' + object_sha256({'url': spec.get('entry_url'), 'spec': spec})[:24]
        return task

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
        session = ReactSession(self.direct_task() if task is None else task, evidence / 'raw',
                               choose, self.page, steps_directory=evidence, attempt_id='offline-direct')
        return session, evidence


class DirectArticleSessionTests(DirectArticleHarness, unittest.IsolatedAsyncioTestCase):
    derive = EndingV2Tests.derive

    @staticmethod
    def reading_plan(prompt):
        return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
                'band': 'five', 'band_reason': '原词条定位、跨页核对与返回续读的自然五步',
                'goal': '在已打开的月食词条内定位并阅读轨道关系正文',
                'checks': [{'field': '食甚时月球与地球的位置关系', 'evidence_kind': 'reading'}],
                'steps': [
                    {'action': 'scroll', 'direction': 'down', 'purpose': '向下阅读原词条前段',
                     'expected': {'kind': 'scroll_changed'}},
                    {'action': 'click', 'target': {'text': '轨道关系'},
                     'purpose': '打开正文关键词关联词条核对', 'expected': {'kind': 'document_changed', 'text': '轨道基础'}},
                    {'action': 'back', 'purpose': '立即返回原词条',
                     'expected': {'kind': 'document_changed', 'text': TITLE}},
                    {'action': 'scroll', 'direction': 'down', 'purpose': '返回后继续向下阅读',
                     'expected': {'kind': 'scroll_changed'}},
                    {'action': 'scroll', 'direction': 'down', 'purpose': '读到位置关系正文',
                     'expected': {'kind': 'scroll_changed'}},
                ],
                'finish_when': {'kind': 'goal_evidence'}, 'replan_when': '原词条缺失或无法返回'}

    def branch(self, choice):
        return lambda p: {'attempt_id': p['attempt_id'], 'observation_id': p['observation']['observation_id'],
                          'choice': choice}

    def finish_reading(self, prompt):
        return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
                'choice': 'finish_reading', 'reading_answer': {
                    'answer': '食甚时月球整体位于地球本影之内，即月球处在地球背向太阳的一侧。',
                    'check_answers': [{'check_index': 0,
                                       'answer': '月球位于地球背向太阳的一侧（地球本影内）。',
                                       'passages': [P3]}]}}

    async def test_scroll_keyword_back_continue_cite_saves_and_replays(self):
        # The keyword click and the return land through host-expected navigation
        # (no model round); passage rounds appear after each reading scroll.
        session, evidence = self.scripted(
            'direct-chain', self.reading_plan,
            [self.branch('continue_plan'), self.branch('continue_plan'), self.finish_reading])
        result = await session.run()
        self.assertFalse(result['host_failure'], result)
        self.assertEqual((result['effective_steps'], result['actual_actions']), (5, 5), result)
        self.assertFalse(result['short_flow'])
        self.assertEqual([action for action, _ in self.surface.executed],
                         ['scroll', 'click', 'back', 'scroll', 'scroll'])
        self.assertEqual(result['collection_ending']['kind'], 'HOST_PLAN_ENDPOINT')
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        objective = terminal['goal_evidence']['session_objective']
        self.assertEqual(objective['status'], 'VERIFIED')
        self.assertEqual(objective['article_entry']['heading'], TITLE)
        self.assertFalse(objective['return_required'])
        self.assertIn('月球', objective['selected_passage']['quote'])
        # Save-time derivation replays the direct trace independently.
        destination, annotation = self.derive(evidence, name='derived-direct')
        saved = annotation['steps'][-1]['tool_result']['return_value']['collection_ending']
        self.assertEqual((saved['verified_effective_steps'], saved['attempt_band']), (5, 'five'))
        self.assertNotIn('short_flow', annotation)

    async def test_away_page_scroll_plan_is_rejected_and_never_dispatched(self):
        """Rule 2 counterexample: a scroll after a body link that leaves the
        article is deterministically rejected at plan submission with an
        explicit back requirement; nothing violating is ever dispatched."""
        violating = [
            {'action': 'click', 'target': {'text': '轨道关系'},
             'purpose': '打开关联词条', 'expected': {'kind': 'document_changed', 'text': '轨道基础'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '在关联页继续滚动',
             'expected': {'kind': 'scroll_changed'}},
        ]
        corrected = violating[:1] + [
            {'action': 'back', 'purpose': '立即返回原词条',
             'expected': {'kind': 'document_changed', 'text': TITLE}}]

        self.prompts = []

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if prompt.get('phase') == 'first':
                steps = corrected if prompt.get('initial_plan_feedback') else violating
                submitted = self.reading_plan(prompt)
                submitted['steps'] = [deepcopy(step) for step in steps]
                submitted['band'] = 'short'
                submitted['short_reason'] = '自然短流程'
                submitted['checks'] = [{'field': '关联页违规滚动不产生原词条阅读', 'evidence_kind': 'reading'}]
                return {'name': 'submit_plan', 'arguments': submitted, 'tool_call_id': 'provider-first',
                        'assistant_message': {'role': 'assistant', 'tool_calls': []}, 'request_id': 'mock'}
            return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
                    'choice': 'stop'}

        evidence = self.root / 'away-scroll' / 'evidence' / self.ids['sample_id']
        session = ReactSession(self.direct_task(), evidence / 'raw', choose, self.page,
                               steps_directory=evidence, attempt_id='offline-direct')
        result = await session.run()
        feedback = self.prompts[1].get('initial_plan_feedback') or {}
        self.assertTrue(any('must be back' in str(issue.get('detail', ''))
                            for issue in feedback.get('errors', [])), feedback)
        # Only the corrected click+back pair ever dispatched; the violating
        # scroll never executed and the session honestly stopped unverified.
        self.assertEqual([action for action, _ in self.surface.executed], ['click', 'back'])
        self.assertIn('如实结束', result['stop_summary'])
        self.assertNotEqual(result['collection_ending']['kind'], 'HOST_PLAN_ENDPOINT')
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        self.assertNotEqual(terminal['goal_evidence']['session_objective']['status'], 'VERIFIED')


class DirectArticleRuleCounterexamples(DirectArticleHarness, unittest.TestCase):
    """Unit-level rule counterexamples on the same synthetic article facts."""

    def setUp(self):
        DirectArticleHarness.setUp(self)

    def state(self, **kw):
        surface = DirectArticleSurface()
        for key, value in kw.items():
            setattr(surface, key, value)
        return surface._render()

    def test_same_page_toc_is_location_not_cross_document(self):
        before = self.state(scroll=0)
        after = self.state(scroll=2)
        self.assertEqual(transition(self.direct_task_obj(), before, after, 'click', {}, 'e_toc'),
                         (None, False))
        away = self.state(page='related')
        pending, returned = transition(self.direct_task_obj(), self.state(scroll=2), away,
                                       'click', {}, 'e_kw')
        self.assertTrue(pending)
        self.assertFalse(returned)

    def test_wrong_return_identity_is_rejected(self):
        task = self.direct_task_obj()
        pending = {'url': ARTICLE, 'title': TITLE, 'body': body(self.state(scroll=2)),
                   'document_identity': self.state()['document_identity']}
        returned = self.state(scroll=2)
        returned['document_identity'] = {'url_without_fragment': ARTICLE, 'performance_time_origin': 2000}
        self.assertEqual(transition(task, self.state(page='related'), returned, 'back', {}, pending=pending),
                         (None, True))
        for mode in ('url', 'title', 'body'):
            wrong = deepcopy(returned)
            if mode == 'url':
                wrong['url'] = ARTICLE + '?from=elsewhere'
            if mode == 'title':
                wrong['title'] = '另一个词条'
            if mode == 'body':
                # A landing that lost the original article body is unverified
                # even at the same URL and title.
                wrong['elements'] = [e for e in wrong['elements']
                                     if e['element_id'] not in ('e_p1', 'e_p2', 'e_p3')]
            with self.assertRaises(ValueError, msg=mode):
                transition(task, self.state(page='related'), wrong, 'back', {}, pending=pending)

    def test_repeat_scroll_without_new_body_extends_no_reading(self):
        from webcollect.direct_article import trace
        from webcollect.agent_controller import exclusive
        root = self.root / 'trace'
        observations = {}

        def ob(name, surface_state):
            state_ref = exclusive(root / (name + '.state.json'), surface_state)
            image = root / (name + '.png')
            image.write_bytes(b'')
            capture = root / (name + '.capture.json')
            capture.write_text('{}')
            from webcollect.batch_core import file_sha
            observations[name] = {'observation_id': name, 'capture_verified': True,
                                  'url': surface_state['url'], 'document_identity': surface_state['document_identity'],
                                  'evidence': {'state': state_ref,
                                               'image': {'path': str(image), 'sha256': file_sha(image)},
                                               'capture': {'path': str(capture), 'sha256': file_sha(capture)}}}
            return observations[name]

        ob('start', self.state(scroll=0))
        ob('first', self.state(scroll=1))
        bottom = ob('bottom', self.state(scroll=2))
        still = ob('still', self.state(scroll=2))
        steps = [
            {'action': 'scroll', 'arguments': {'direction': 'down'}, 'operation_id': 'r1',
             'before_observation_id': 'start', 'after_observation_id': 'first'},
            {'action': 'scroll', 'arguments': {'direction': 'down'}, 'operation_id': 'r2',
             'before_observation_id': 'first', 'after_observation_id': 'bottom'},
            {'action': 'scroll', 'arguments': {'direction': 'down'}, 'operation_id': 'r3',
             'before_observation_id': 'bottom', 'after_observation_id': 'still'},
        ]
        task = self.direct_task_obj()
        from types import SimpleNamespace
        result = trace(task, self.state(), steps, observations)
        quotes = [row['quote'] for row in result['new_body']]
        self.assertIn(P2, quotes)
        self.assertIn(P3, quotes)
        # The third scroll moved nothing: no new reading row for it.
        self.assertEqual(len([q for q in quotes if q == P3]), 1)

    def direct_task_obj(self):
        return self.direct_task()


if __name__ == '__main__':
    unittest.main()
