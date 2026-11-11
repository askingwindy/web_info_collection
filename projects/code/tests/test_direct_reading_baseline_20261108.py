"""Direct-entry reading baseline and action-scoped evidence (2026-11-08).

Covers the new round on the direct 月食 entry baseline:
1. The action-scoped evidence protocol (webcollect-action-scoped-evidence-1):
   target-level click/type/hotkey proofs and document-level scroll/back proofs
   accept unrelated overlay/announcement/SVG churn without any region
   classification, while target pixel change, identity drift, focus/value
   change, occlusion and hit failure still reject.
2. Direct-entry reading (goal-evidence-2 + direct_entry) path families as full
   offline sessions: TOC-anchor clicks, multi-segment scrolls, cross-page link
   visits with back, honest short flows, ≥5 steps vs VERIFIED separation, and
   the search-mixed counterexample that stays honestly UNVERIFIED.
3. Session-objective binding: evidence_policy stamps the frozen fragment and
   task identity; objectives without it keep the generator's protocol.
4. Four-route dedup unchanged: samples with different action sequences but a
   shared first frame still hit route1; identical sequences hit route2.
5. Real-Chromium local-HTML integration: focus/type/submit under an
   UNDECLARED churning popup still dispatch, and an occluded/mismatched target
   is still rejected. No provider, no external network.
"""
import base64
import hashlib
import json
import io
import socket
import time
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image, ImageDraw

from test_react_session import FakePage
from webcollect.batch_core import load_json, save_json
from webcollect.plan_protocol import PLAN_PROTOCOL as V11_VERSION, ENDING_POLICY as END_V3
from webcollect.banded_plan import system_for
from webcollect.goal_evidence import VERSION as EVIDENCE_VERSION, progress as evidence_progress
from webcollect.react_session import ReactSession, build_url_task
from webcollect.browser import stability_pair, fingerprint
from webcollect import dynamic_regions
from webcollect.action_stability import (ACTION_SCOPED_VERSION, action_scoped_scope, document_scope,
                                         post_action_document_scope)
from webcollect.planning import object_sha256

ARTICLE = 'https://local.test/wiki/%E6%9C%88%E9%A3%9F'
RELATED = 'https://local.test/wiki/%E6%97%A5%E9%A3%9F'
SUBJECT = '月食'
INTRO = '月食是一种可见的天文现象，本条目介绍其观察记录与成因脉络。'
MID = '历史记录显示该现象出现的周期与轨道位置相关，观测机构整理了系统资料。'
ASPECTS_BODY = '发生月食时，地球位于太阳与月球之间，月球进入地球的本影，因此只能出现在满月之夜。'
RELATED_BODY = '日食是月球运行到太阳与月球之间的现象，与月食位置关系相反。'
NOTICES = ('交流群甲欢迎大家加入。', '交流群乙请大家一同关注。', '频道丙已经正式上线。')
SUGGESTIONS = ('月食', '月食的过程', '月食观测')
Q_SELECTOR = 'html:1 > body:1 > header:1 > form:1 > input:1'
REGION_ATTRS = {'id': None, 'class': None, 'role': None, 'aria-label': None,
                'aria-roledescription': None, 'title': None}

DIRECT_OBJECTIVE = {
    'kind': 'reading',
    'description': ('从「月食」词条直接开始阅读，不经过站内检索。往下阅读正文，依据当前页面证据'
                    '自由组合滚动、目录或相关链接点击、返回等合法操作，用正文说明发生月食时'
                    '月球与地球的位置关系。'),
    'minimum_effective_steps': 5, 'preferred_band': 'long',
    'evidence_policy': ACTION_SCOPED_VERSION,
    'evidence_contract': {'version': EVIDENCE_VERSION, 'kind': 'reading', 'subject': SUBJECT,
                          'aspects': ['月球', '地球'], 'direct_entry': True}}


def draw_direct(page, *, focused, scroll, overlay_tick, notice_tick, size=(1280, 720)):
    """Deterministic PNG; churn stays inside the suggestion/notice boxes."""
    image = Image.new('RGB', size, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([260, 10, 770, 55], outline=(0, 0, 0), width=2)  # header search box
    draw.rectangle([44, 90, 713, 121], fill=(250, 250, 210), outline=(200, 200, 160))
    draw.rectangle([50, 96, 50 + 20 * (notice_tick % 3 + 1), 115],
                   fill=(180, 40 + 30 * (notice_tick % 3), 40))
    if focused:
        for row in range(3):
            width = 60 + 30 * ((overlay_tick + row) % 3 + 1)
            draw.rectangle([270, 60 + row * 50, 270 + width, 100 + row * 50],
                           fill=(40 * (row + 1), 90 + 40 * ((overlay_tick + row) % 3), 150))
    if page in ('article', 'related'):
        rows = {'article': 3, 'related': 1}[page]
        for index in range(min(scroll + 1, rows)):
            draw.rectangle([100, 140 + index * 60, 100 + 90 * (index + 1), 180 + index * 60],
                           fill=(20, 100 + index * 40, 60))
    return image


class DirectSurface:
    """月食 article opened directly, with a header search box the objective
    forbids using, a declared rotating announcement and (when the search box is
    focused) an undeclared-churn suggestion popup for evidence-shape tests."""

    def __init__(self, entry='article'):
        assert entry == 'article'
        self.page = entry
        self.history = [ARTICLE]
        self.origins = {ARTICLE: 1000}
        self.page_scroll = {ARTICLE: 0}
        self.q_value = ''
        self.focused = None
        self.scroll = 0
        self.navigations = 0
        self.tick = 0
        self.executed = []
        self.fail_on = None       # (action_type, occurrence) -> raise after recording dispatch
        self.toc_text = '目录'
        self.fragment = ''        # same-document anchor navigation changes the URL
        self.mutate_toc_on_capture = None  # executed-count threshold that relabels the TOC link
        self.executed_count = {}
        self.state = self._render()

    def _overlay_rows(self):
        if self.focused != 'e_q':
            return []
        order = [(self.tick + i) % 3 for i in range(3)]
        return [{'element_id': f'e_s{i}', 'native_role': 'a', 'text': SUGGESTIONS[order[i]],
                 'parent_id': 'e_menu', 'clickable': True} for i in range(3)]

    def _elements(self):
        rows = [
            {'element_id': 'e_h', 'native_role': 'h1', 'text': SUBJECT, 'parent_id': 'root'},
            {'element_id': 'e_note', 'native_role': 'p', 'text': NOTICES[self.tick % 3],
             'parent_id': 'root'},
            {'element_id': 'e_q', 'native_role': 'input', 'text': '搜索', 'parent_id': 'root',
             'inputable': True, 'clickable': True},
            {'element_id': 'e_toc', 'native_role': 'a', 'text': self.toc_text, 'parent_id': 'root',
             'clickable': True},
            {'element_id': 'e_p1', 'native_role': 'p', 'text': INTRO, 'parent_id': 'root'},
        ]
        if self.page == 'article':
            if self.scroll >= 1:
                rows.append({'element_id': 'e_p2', 'native_role': 'p', 'text': MID, 'parent_id': 'root'})
            if self.scroll >= 2:
                rows.append({'element_id': 'e_p3', 'native_role': 'p', 'text': ASPECTS_BODY,
                             'parent_id': 'root'})
            rows.append({'element_id': 'e_rel', 'native_role': 'a', 'text': '日食',
                         'parent_id': 'root', 'clickable': True})
        else:
            rows.append({'element_id': 'e_p1b', 'native_role': 'p', 'text': RELATED_BODY,
                         'parent_id': 'root'})
        if self.focused == 'e_q':
            rows.append({'element_id': 'e_menu', 'native_role': 'listbox', 'text': '搜索结果',
                         'parent_id': 'root'})
            rows.extend(self._overlay_rows())
        return rows

    def _bindings(self):
        rows = [{'element_id': 'e_h', 'selector': 'html:1 > body:1 > main:1 > h1:1', 'tag': 'h1', 'href': None},
                {'element_id': 'e_note', 'selector': 'html:1 > body:1 > div:1 > p:1', 'tag': 'p', 'href': None},
                {'element_id': 'e_q', 'selector': Q_SELECTOR, 'tag': 'input', 'href': None,
                 'input_type': 'search', 'form_index': 0},
                {'element_id': 'e_toc', 'selector': 'html:1 > body:1 > main:1 > nav:1 > a:1',
                 'tag': 'a', 'href': ARTICLE + '#s2'},
                {'element_id': 'e_p1', 'selector': 'html:1 > body:1 > main:1 > p:1', 'tag': 'p', 'href': None}]
        if self.page == 'article':
            if self.scroll >= 1:
                rows.append({'element_id': 'e_p2', 'selector': 'html:1 > body:1 > main:1 > p:2',
                             'tag': 'p', 'href': None})
            if self.scroll >= 2:
                rows.append({'element_id': 'e_p3', 'selector': 'html:1 > body:1 > main:1 > p:3',
                             'tag': 'p', 'href': None})
            rows.append({'element_id': 'e_rel', 'selector': 'html:1 > body:1 > main:1 > a:1',
                         'tag': 'a', 'href': RELATED})
        else:
            rows.append({'element_id': 'e_p1b', 'selector': 'html:1 > body:1 > main:1 > p:1',
                         'tag': 'p', 'href': None})
        if self.focused == 'e_q':
            menu = 'html:1 > body:1 > header:1 > form:1 > div:1 > ul:1'
            rows.append({'element_id': 'e_menu', 'selector': menu, 'tag': 'ul', 'href': None})
            for i, row in enumerate(self._overlay_rows()):
                rows.append({'element_id': row['element_id'],
                             'selector': f'{menu} > li:{i + 1} > a:1', 'tag': 'a', 'href': ARTICLE})
        return rows

    def _contract(self):
        notice = {'schema_version': dynamic_regions.VERSION, 'category': 'announcement',
                  'tag': 'p', 'native_image_paint': None,
                  'attributes': {**REGION_ATTRS, 'id': 'siteNotice', 'class': 'site-notice'},
                  'selector': 'html:1 > body:1 > div:1 > p:1', 'element_id': 'e_note',
                  'bbox': [44, 90, 713, 121], 'raw_bbox': [44, 90, 713, 121],
                  'native_paint_bbox': [44, 90, 713, 121], 'clip_bbox': [0, 0, 1280, 720],
                  'member_ids': ['e_note'], 'member_selectors': ['html:1 > body:1 > div:1 > p:1'],
                  'eligible': True, 'reasons': [], 'external_text_overlaps': [],
                  'external_paint_overlaps': [], 'external_control_ids': [], 'target_inside': False}
        outside = '\n'.join(row.get('text') or '' for row in self._elements()
                            if row['element_id'] != 'e_note' and row['element_id'] != 'e_menu'
                            and not str(row['element_id']).startswith('e_s'))
        return {'schema_version': dynamic_regions.VERSION, 'regions': [notice],
                'visible_text_outside': outside, 'ancestor_text_outside': {}}

    def _url(self):
        base = ARTICLE if self.page == 'article' else RELATED
        return base + self.fragment if self.page == 'article' else base

    def _title(self):
        return SUBJECT if self.page == 'article' else '日食'

    def _render(self, *, probe=None):
        elements = []
        for i, row in enumerate(self._elements()):
            row = dict(row)
            top = 130 + i * 55
            row.update(bbox=[10, top, 640, top + 40], enabled=True, visible=True,
                       element_type='link' if row['native_role'] == 'a' else
                       ('input' if row.get('inputable') else 'text'),
                       state='default', scrollable=False,
                       clickable=row.get('clickable', False), inputable=row.get('inputable', False))
            elements.append(row)
        values = [{'element_id': 'e_q', 'value': self.q_value, 'focused': self.focused == 'e_q',
                   'selection_start': len(self.q_value), 'selection_end': len(self.q_value),
                   'input_type': 'search', 'value_visible': True, 'readonly': False,
                   'enabled': True}] if self.focused == 'e_q' else []
        witnesses = []
        for e in elements:
            box = e['bbox']
            samples = [{'point': [x, y], 'ancestor': True}
                       for y in (box[1] + 1, (box[1] + box[3]) / 2, box[3] - 1)
                       for x in (box[0] + 1, (box[0] + box[2]) / 2, box[2] - 1)]
            witnesses.append({'element_id': e['element_id'], 'bbox': box, 'samples': samples})
        base_url = ARTICLE if self.page == 'article' else RELATED
        state = {'url': self._url(), 'title': self._title(),
                 'document_identity': {'url_without_fragment': base_url,
                                       'performance_time_origin': self.origins[base_url]},
                 'scroll': [0, self.scroll * 480], 'screen_resolution': [1280, 720],
                 'device_pixel_ratio': 1, 'target': None,
                 'capture_readiness': {'schema_version': 'webcollect-capture-readiness-1',
                                       'document_ready': 'complete', 'fonts_ready': True,
                                       'images_ready': True},
                 'elements': elements, 'values': values, 'capture_controls': self._bindings(),
                 'geometry_witnesses': witnesses,
                 'dynamic_region_contract': self._contract(),
                 'visible_text': self._title() + '\n' + '\n'.join(
                     e['text'] for e in elements if e['text'])}
        if probe:
            binding = next((b for b in state['capture_controls'] if b['selector'] == probe), None)
            if binding:
                eid = binding['element_id']
                row = next(e for e in state['elements'] if e['element_id'] == eid)
                value = next((v for v in state['values'] if v['element_id'] == eid), {})
                label = value.get('value') or row['text']
                state['target'] = {'element_id': eid, 'coordinate': [30, row['bbox'][1] + 10],
                                   'bbox': row['bbox'], 'hit_valid': True,
                                   'focused': value.get('focused', False), 'value': value.get('value'),
                                   'readonly': False,
                                   'visible_label_evidence': [{'kind':
                                       'visible_native_value' if value.get('value') else 'rendered_target_text',
                                       'text': label}]}
        return state

    def png(self, state=None, *, probe=False):
        image = draw_direct(self.page, focused=self.focused == 'e_q', scroll=self.scroll,
                            overlay_tick=self.tick, notice_tick=self.tick)
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue()

    async def capture(self, page, selector=None, index=0, **kw):
        self.tick += 1  # every capture observes a new churn frame
        if (self.mutate_toc_on_capture is not None
                and len(self.executed) >= self.mutate_toc_on_capture):
            self.toc_text = '目录已重排'  # target identity drift after the frozen basis
        state = self._render(probe=selector)
        png = self.png(state, probe=selector is not None)
        stability = stability_pair(state, state, png, png)
        encoded = base64.b64encode(png).decode('ascii')
        attempt = {'attempt': 1, 'started_ns': time.time_ns(), 'ended_ns': time.time_ns(),
                   'dom_stable': stability['full_dom_stable'], 'rejected_reason': None,
                   'delay_before_ms': 0.0, 'next_retry_delay_ms': 0.0, 'mismatch_fields': [],
                   'before_fingerprint': fingerprint(state), 'after_fingerprint': fingerprint(state),
                   'snapshot_before': state, 'snapshot_after': state, 'snapshot_final': state,
                   'original_png_base64': encoded, 'comparison_png_base64': encoded,
                   'comparison_screenshot': 'synthetic', 'stability': stability,
                   'final_stability': stability}
        return {'state': state, 'png': png, 'capture': {'schema_version': 'webcollect-capture-2',
            'snapshot_source': 'browser_dom', 'screenshot_sha256': hashlib.sha256(png).hexdigest(),
            'natural_wait_requested_ms': 0, 'natural_wait_observed_ms': 0, 'natural_wait_budget_ms': 8000,
            'coordinate_space': 'screenshot_css_pixels', 'attempts': [attempt]}}

    def execute_action(self, action_type, arguments):
        self.executed.append((action_type, deepcopy(arguments)))
        self.executed_count[action_type] = self.executed_count.get(action_type, 0) + 1
        if self.fail_on and (action_type, self.executed_count[action_type]) == self.fail_on:
            raise RuntimeError('simulated post-dispatch infrastructure failure')
        if action_type == 'click':
            x, y = arguments['x'], arguments['y']
            hit = None
            for e in self._elements():
                row = next(r for r in self.state['elements'] if r['element_id'] == e['element_id'])
                if row['bbox'][0] <= x < row['bbox'][2] and row['bbox'][1] <= y < row['bbox'][3]:
                    hit = e
            if hit and hit['element_id'] == 'e_q':
                self.focused = 'e_q'
            elif hit and hit['element_id'] == 'e_toc' and self.page == 'article':
                if self.scroll < 1:
                    self.scroll = 1  # same-document anchor jump exposes the mid section
                self.fragment = '#s2'
            elif hit and hit['element_id'] == 'e_rel' and self.page == 'article':
                self.page_scroll[ARTICLE] = self.scroll
                self.page = 'related'; self.scroll = 0; self.fragment = ''
                self.history.append(RELATED); self.navigations += 1
                self.origins.setdefault(RELATED, 1000 + self.navigations)
                self.focused = None
        elif action_type == 'type':
            if self.focused == 'e_q':
                self.q_value = arguments['text']
        elif action_type == 'scroll':
            limit = {'article': getattr(self, 'article_scroll_limit', 2), 'related': 1}.get(self.page, 0)
            if self.scroll < limit:
                self.scroll += 1
        elif action_type == 'back':
            if len(self.history) > 1:
                self.history.pop()
                url = self.history[-1]
                self.page = 'article' if url == ARTICLE else 'related'
                self.navigations += 1
                self.origins.setdefault(url, 1000)  # back restores the same document
                self.scroll = self.page_scroll.get(url, 0)
                self.fragment = ''  # back restores the plain document URL
                self.focused = None
        self.state = self._render()


class DirectHarness(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        network = patch.object(socket.socket, 'connect', side_effect=AssertionError('external IO forbidden'))
        network.start()
        self.addCleanup(network.stop)
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.surface = DirectSurface()
        self.page = FakePage(self.surface)
        capture = patch('webcollect.browser.capture', side_effect=self.surface.capture)
        capture.start(); self.addCleanup(capture.stop)
        execute_patch = patch('webcollect.browser.execute', side_effect=self._fake_execute)
        execute_patch.start(); self.addCleanup(execute_patch.stop)
        verify_patch = patch('webcollect.browser.verify_execution_state', side_effect=self._fake_verify)
        verify_patch.start(); self.addCleanup(verify_patch.stop)
        before_patch = patch('webcollect.collect.capture_before_action', side_effect=self._fake_before)
        before_patch.start(); self.addCleanup(before_patch.stop)
        self.ids = {'sample_id': 'S000001_sample_000001', 'site_id': 'S000001',
                    'batch_id': 'B20261108_002', 'attempt_id': 'offline-direct'}
        self.manifest = {'batch_id': 'B20261108_002', 'sample_kind': 'real',
                         'program_version': 'CONTROLLED', 'rule_version': '1.0.0',
                         'sites': [{'site_id': 'S000001', 'uri': ARTICLE, 'site_category': 'reading'}],
                         'samples': [self.ids['sample_id']]}
        self.prompts = []

    async def _fake_execute(self, page, action_type, arguments, execution):
        self.surface.execute_action(action_type, arguments)

    async def _fake_verify(self, page, state, selector=None, index=0, **kw):
        return {'matched': True, 'state_fingerprint': fingerprint(state)}

    async def _fake_before(self, page, evidence, selector=None, index=0, **options):
        observation = await self.surface.capture(page, selector, index,
                                                 **({'action_scope': options['action_scope']}
                                                    if options.get('action_scope') else {}))
        observation['action_state_preflight'] = await self._fake_verify(
            page, observation['state'], selector, index)
        observation['action_refresh'] = {'timeout_seconds': 45, 'stage': 'complete', 'accepted': True,
                                         'attempts': [{'attempt': 1, 'capture_seconds': 0.05,
                                                       'verification_seconds': 0.05}],
                                         'action_executed': False, 'elapsed_seconds': 0.1}
        observation['action_deadline_monotonic'] = time.monotonic() + 45
        return observation

    def direct_task(self, *, objective=None, stability=ACTION_SCOPED_VERSION, url=ARTICLE):
        task = build_url_task(url=url, task_version='direct-reading', ending_policy=END_V3,
                              plan_protocol=V11_VERSION,
                              **({'action_stability_protocol': stability} if stability else {}))
        spec = task['workflow_proposal']['spec']
        spec['goal'] = {'instruction': (objective or DIRECT_OBJECTIVE)['description'],
                        'structured': deepcopy(objective or DIRECT_OBJECTIVE)}
        task['task_id'] = 'react-' + object_sha256({'url': spec.get('entry_url'), 'spec': spec})[:24]
        return task

    def scripted(self, name, plan, branches, task=None):
        preferences = list(branches)

        def pick(prompt):
            options = [o.get('choice') for o in prompt.get('options', []) if isinstance(o, dict)]
            citation = any(option.startswith('cite:') for option in options)
            remaining = prompt.get('remaining_plan') or []
            for wanted in preferences:
                if callable(wanted):
                    if not citation or not remaining:
                        continue
                    return wanted(prompt)
                if wanted in options:
                    return {'attempt_id': prompt['attempt_id'],
                            'observation_id': prompt['observation']['observation_id'],
                            'choice': wanted}
                if ':' in wanted and any(option.startswith(wanted.split(':')[0] + ':')
                                         for option in options):
                    return {'attempt_id': prompt['attempt_id'],
                            'observation_id': prompt['observation']['observation_id'],
                            'choice': next(option for option in options
                                           if option.startswith(wanted.split(':')[0] + ':'))}
            raise AssertionError('no scripted preference offered: ' + repr(options))

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if len(self.prompts) == 1:
                return {'name': 'submit_plan', 'arguments': plan(prompt), 'tool_call_id': 'provider-first',
                        'assistant_message': {'role': 'assistant', 'tool_calls': []}, 'request_id': 'mock'}
            return pick(prompt)

        evidence = self.root / name / 'evidence' / self.ids['sample_id']
        bound_task = task if task is not None else self.direct_task()
        session = ReactSession(bound_task, evidence / 'raw',
                               choose, self.page, steps_directory=evidence, attempt_id='offline-direct')
        return session, evidence

    def reply(self, choice, **extra):
        return lambda p: {'attempt_id': p['attempt_id'],
                          'observation_id': p['observation']['observation_id'],
                          'choice': choice, **extra}

    def plan_with(self, prompt, steps, *, band='long', goal=None):
        return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
                'band': band, 'band_reason': '直接词条自然阅读',
                'goal': goal or '从月食词条直接阅读，说明月球与地球的位置关系',
                'checks': [{'field': '月球与地球的位置关系'}], 'steps': [deepcopy(s) for s in steps],
                'finish_when': {'kind': 'goal_evidence'}, 'replan_when': '正文缺失或链接失效'}

    def objective_of(self, evidence):
        return load_json(evidence / 'raw' / 'terminal.json')['goal_evidence']['session_objective']


class ActionScopedEvidenceTests(DirectHarness):
    """Target/document scoped proofs: churn passes, target damage rejects."""

    def _states(self, *, focused=False, typed=''):
        surface = DirectSurface()
        surface.focused = 'e_q' if focused else None
        surface.q_value = typed
        return surface

    def test_click_scope_accepts_undeclared_overlay_churn(self):
        surface = self._states(focused=True, typed=SUBJECT)
        before = surface._render(probe=Q_SELECTOR)
        png_before = surface.png(before, probe=True)
        surface.tick += 1  # suggestion rows and notice churn with NO declared region for them
        after = surface._render(probe=Q_SELECTOR)
        png_after = surface.png(after, probe=True)
        scope = action_scoped_scope(before, 'e_q', 'click')
        proof = stability_pair(before, after, png_before, png_after, action_scope=scope)
        self.assertEqual(proof['schema_version'], ACTION_SCOPED_VERSION)
        self.assertTrue(proof['accepted'], proof)
        self.assertFalse(proof['full_dom_stable'])  # churn happened; it simply is not blocking

    def test_action_scoped_pair_routes_before_dynamic_regions(self):
        """The postprocess replay path: both states carry a dynamic-region
        contract, yet the action-scoped scope must never depend on region
        classification (the real r02 derivation-gap shape)."""
        from webcollect.action_stability import pair as scoped_pair
        from webcollect.dynamic_regions import enabled as dynamic_enabled
        surface = self._states()
        surface.scroll = 1
        first = surface._render()
        surface.tick += 2  # announcement text rotates inside its declared region
        second = surface._render()
        self.assertTrue(dynamic_enabled(first) and dynamic_enabled(second))
        scope = document_scope(first, 'scroll')
        proof = scoped_pair(first, second, surface.png(first), surface.png(second), deepcopy(scope))
        self.assertEqual(proof['schema_version'], ACTION_SCOPED_VERSION)
        self.assertTrue(proof['accepted'], proof)

    def test_click_scope_rejects_target_pixel_change_identity_and_occlusion(self):
        surface = self._states(focused=True, typed=SUBJECT)
        before = surface._render(probe=Q_SELECTOR)
        png_before = surface.png(before, probe=True)
        after = surface._render(probe=Q_SELECTOR)
        scope = action_scoped_scope(before, 'e_q', 'click')
        # 1. pixels changed INSIDE the guarded target box (e_q row 2)
        box = next(e['bbox'] for e in before['elements'] if e['element_id'] == 'e_q')
        image = Image.open(io.BytesIO(surface.png(after, probe=True))).convert('RGB')
        ImageDraw.Draw(image).rectangle([box[0] + 6, box[1] + 6, box[0] + 30, box[1] + 20],
                                        fill=(10, 10, 10))
        buffer = io.BytesIO(); image.save(buffer, format='PNG')
        proof = stability_pair(before, after, png_before, buffer.getvalue(), action_scope=deepcopy(scope))
        self.assertFalse(proof['accepted'], proof['pixel_change'])
        # 2. target identity moved
        moved = deepcopy(after)
        for e in moved['elements']:
            if e['element_id'] == 'e_q':
                e['bbox'] = [300, 300, 900, 340]
        self.assertFalse(stability_pair(before, moved, png_before, surface.png(after),
                                        action_scope=deepcopy(scope))['accepted'])
        # 3. occluded hit samples
        occluded = deepcopy(after)
        for w in occluded['geometry_witnesses']:
            if w['element_id'] == 'e_q':
                w['samples'][4]['ancestor'] = False
        with self.assertRaises(ValueError):
            action_scoped_scope(occluded, 'e_q', 'click')
        # 4. ambiguous target rows
        ambiguous = deepcopy(after)
        ambiguous['elements'].append(deepcopy(next(e for e in ambiguous['elements']
                                                   if e['element_id'] == 'e_q')))
        with self.assertRaises(ValueError):
            action_scoped_scope(ambiguous, 'e_q', 'click')

    def test_type_scope_requires_focus_and_value_stability(self):
        surface = self._states(focused=True, typed=SUBJECT)
        before = surface._render(probe=Q_SELECTOR)
        png_before = surface.png(before, probe=True)
        surface.tick += 1
        after = surface._render(probe=Q_SELECTOR)
        png_after = surface.png(after, probe=True)
        scope = action_scoped_scope(before, 'e_q', 'type')
        self.assertTrue(stability_pair(before, after, png_before, png_after,
                                       action_scope=deepcopy(scope))['accepted'])
        tampered = deepcopy(after)
        tampered['values'][0]['value'] = '月'
        self.assertFalse(stability_pair(before, tampered, png_before, png_after,
                                        action_scope=deepcopy(scope))['accepted'])
        tampered = deepcopy(after)
        tampered['values'][0]['focused'] = False
        self.assertFalse(stability_pair(before, tampered, png_before, png_after,
                                        action_scope=deepcopy(scope))['accepted'])
        unfocused = self._states()  # type scope on a non-focused input cannot even build
        with self.assertRaises(ValueError):
            action_scoped_scope(unfocused._render(), 'e_q', 'type')

    def test_document_scope_and_post_action_document_scope(self):
        surface = self._states()
        entry = surface._render()
        png_entry = surface.png(entry)
        surface.scroll = 1
        scrolled = surface._render()
        png_scrolled = surface.png(scrolled)
        scope = document_scope(entry, 'scroll')
        churn = stability_pair(entry, scrolled, png_entry, png_scrolled, action_scope=deepcopy(scope))
        self.assertFalse(churn['accepted'])  # pre-scroll position changed: not a stable dispatch basis
        stable = stability_pair(entry, entry, png_entry, png_entry, action_scope=deepcopy(scope))
        self.assertTrue(stable['accepted'])
        # A page-wide repaint (announcement/SVG churn) with the document settled passes.
        surface.tick += 2
        repainted = surface._render()
        churned_png = surface.png(repainted)
        scope2 = document_scope(entry, 'back')
        self.assertTrue(stability_pair(entry, repainted, png_entry, churned_png,
                                       action_scope=deepcopy(scope2))['accepted'])
        moved = deepcopy(repainted)
        moved['url'] = RELATED
        moved['document_identity'] = {'url_without_fragment': RELATED, 'performance_time_origin': 9}
        self.assertFalse(stability_pair(entry, moved, png_entry, churned_png,
                                        action_scope=deepcopy(scope2))['accepted'])
        # Post-action observation: a settled NEW document passes; mid-change rejects.
        post = post_action_document_scope(entry, {'operation_id': 'react-1'})
        self.assertTrue(stability_pair(scrolled, scrolled, png_scrolled, png_scrolled,
                                       action_scope=post)['accepted'])
        self.assertTrue(stability_pair(scrolled, repainted, png_scrolled, churned_png,
                                       action_scope=deepcopy(post))['accepted'])
        drifting = deepcopy(repainted)
        drifting['document_identity'] = {'url_without_fragment': RELATED, 'performance_time_origin': 9}
        self.assertFalse(stability_pair(scrolled, drifting, png_scrolled, churned_png,
                                        action_scope=deepcopy(post))['accepted'])
        receipt = stability_pair(scrolled, repainted, png_scrolled, churned_png, action_scope=post)
        self.assertTrue(receipt['observation_only'])
        self.assertFalse(receipt['dispatch_permission'])


class DirectReadingPathTests(DirectHarness):
    def derive(self,evidence,name='candidate'):
        destination=self.root/name/'samples'/self.ids['sample_id']
        from webcollect.postprocess import process
        result=process(evidence,destination,self.ids,self.manifest)
        if result['status']!='derived_saved' and result.get('record_ref'):
            self.fail(str(load_json(result['record_ref']['path'])))
        self.assertEqual(result['status'],'derived_saved',result)
        from webcollect.client_package import validate_client_sample
        from quality_inspector.format_checks import sample_check
        from webcollect.closing_policy import annotation_errors
        annotation=validate_client_sample(destination)
        check=sample_check(destination)
        self.assertTrue(check['confirmed_format_pass'],check['errors'])
        self.assertEqual(annotation_errors(annotation),[])
        return destination,annotation

    async def _run(self, name, steps, branches, *, band='long', task=None):
        session, evidence = self.scripted(name, lambda p: self.plan_with(p, steps, band=band),
                                          branches, task=task)
        result = await session.run()
        return result, evidence

    async def test_d1_toc_click_then_scrolls_cross_page_and_back(self):
        tail = [
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '跨页核对日食与月食的位置关系差异', 'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读关联页正文',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'back', 'purpose': '返回月食条目并核验原页面身份',
             'expected': {'kind': 'document_changed', 'text': SUBJECT}},
        ]

        def replan_tail(p):  # at a citation offer the cross-page tail is still required
            return {'attempt_id': p['attempt_id'],
                    'observation_id': p['observation']['observation_id'],
                    'choice': 'replan', 'plan': {'steps': deepcopy(tail)}}

        steps = [
            {'action': 'click', 'target': {'text': '目录'},
             'purpose': '同页目录定位到中段章节', 'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '继续向下阅读到成因段落',
             'expected': {'kind': 'scroll_changed'}},
        ] + tail
        result, evidence = await self._run('d1', steps, [replan_tail, 'cite:e_p3', 'stop'])
        self.assertFalse(result['host_failure'], result)
        self.assertEqual(result['effective_steps'], 5)
        self.assertEqual([a for a, _ in self.surface.executed],
                         ['click', 'scroll', 'click', 'scroll', 'back'])
        objective = self.objective_of(evidence)
        self.assertEqual(objective['status'], 'VERIFIED')
        self.assertTrue(objective['required_downward_reading'])
        self.assertTrue(objective['downward_reading_satisfied'])
        self.assertTrue(objective['direct_entry'])
        self.assertEqual(objective['opened_results'][0]['source'], 'direct_entry_article')
        self.assertEqual(objective['search_inputs'], [])
        destination, annotation = self.derive(evidence, name='derived-d1')
        self.assertEqual(annotation['steps'][-1]['tool_result']['return_value']['collection_ending']
                         ['verified_effective_steps'], 5)

    async def test_d2_cross_page_first_then_return_reading(self):
        steps = [
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '先跨页核对日食定义', 'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读关联页正文',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'back', 'purpose': '返回月食条目核验身份',
             'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '向下阅读月食正文前段',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '继续阅读成因段落',
             'expected': {'kind': 'scroll_changed'}},
        ]
        result, evidence = await self._run('d2', steps, ['cite:e_p3', 'stop'])
        self.assertEqual(result['effective_steps'], 5)
        objective = self.objective_of(evidence)
        self.assertEqual(objective['status'], 'VERIFIED')
        self.assertEqual(len(objective['downward_reading']), 2)

    async def test_d3_five_steps_without_citation_stay_unverified(self):
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读前段',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '跨页核对', 'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读关联页',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'back', 'purpose': '返回原条目', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '继续阅读成因段',
             'expected': {'kind': 'scroll_changed'}},
        ]
        result, evidence = await self._run('d3', steps, ['stop'])
        self.assertEqual(result['effective_steps'], 5)
        objective = self.objective_of(evidence)
        self.assertNotEqual(objective['status'], 'VERIFIED')  # ≥5 steps never replaces body evidence

    async def test_d4_short_flow_with_verified_goal_is_honestly_short(self):
        steps = [
            {'action': 'click', 'target': {'text': '目录'},
             'purpose': '目录定位', 'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读成因段',
             'expected': {'kind': 'scroll_changed'}},
        ]
        result, evidence = await self._run('d4', steps, ['cite:e_p3', 'stop'], band='short')
        self.assertEqual(result['effective_steps'], 2)
        self.assertTrue(result['short_flow'])
        objective = self.objective_of(evidence)
        self.assertEqual(objective['status'], 'VERIFIED')  # goal evidence and length stay separate

    async def test_d5_search_mixed_into_direct_baseline_stays_unverified(self):
        steps = [
            {'action': 'click', 'target': {'text': '搜索', 'role': 'textbox'},
             'purpose': '误用站内搜索', 'expected': {'kind': 'focused', 'text': '搜索'}},
            {'action': 'type', 'target': {'text': '搜索', 'role': 'textbox'}, 'value': SUBJECT,
             'purpose': '误输入检索词', 'expected': {'kind': 'value', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读前段',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读成因段',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '已到底，机械补步',
             'expected': {'kind': 'scroll_changed'}},
        ]
        result, evidence = await self._run('d5', steps, ['cite:e_p3', 'stop'])
        objective = self.objective_of(evidence)
        self.assertEqual(objective['search_inputs'][0]['query'], SUBJECT)
        self.assertEqual(objective['direct_entry_search_forbidden'], [SUBJECT])
        self.assertNotEqual(objective['status'], 'VERIFIED')

    async def test_d6_dispatched_without_postobservation_is_unknown_not_repeated(self):
        self.surface.fail_on = ('click', 1)
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读前段',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '跨页核对', 'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'back', 'purpose': '返回', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
        ]
        session, evidence = self.scripted('d6', lambda p: self.plan_with(p, steps), ['stop'])
        result = await session.run()
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        self.assertEqual(terminal['stop_reason'], 'blocked')
        # exactly one dispatched click, never re-sent after the unknown effect
        self.assertEqual([a for a, _ in self.surface.executed], ['scroll', 'click'])
        self.assertEqual(result['effective_steps'], 1)

    async def test_d7_target_identity_drift_is_zero_dispatch(self):
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读前段',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'click', 'target': {'text': '目录'},
             'purpose': '目录定位', 'expected': {'kind': 'scroll_changed'}},
        ]
        # After the first executed scroll every fresh capture relabels the TOC
        # link: the frozen target basis no longer matches the live target.
        self.surface.mutate_toc_on_capture = 1
        session, evidence = self.scripted('d7', lambda p: self.plan_with(p, steps), ['stop'])
        result = await session.run()
        self.assertNotIn('click', [a for a, _ in self.surface.executed])  # zero dispatch on drift
        self.assertEqual([a for a, _ in self.surface.executed], ['scroll'])

    async def test_d8_zero_effect_scroll_records_no_credit(self):
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读前段',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读成因段',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '已到底仍声称阅读',
             'expected': {'kind': 'scroll_changed'}},
        ]
        session, evidence = self.scripted('d8', lambda p: self.plan_with(p, steps), ['stop'])
        result = await session.run()
        self.assertEqual(result['effective_steps'], 2)  # the bottomed-out scroll earns no step
        objective = self.objective_of(evidence)
        self.assertEqual(len(objective['downward_reading']), 2)

    async def test_d10_citation_does_not_void_planned_cross_page_tail(self):
        """The real r01 breakpoint shape: citation lands mid-plan at 2 steps while
        the frozen plan still has click/back/scroll steps; the host must continue
        them to the minimum instead of closing the attempt early."""
        self.surface.article_scroll_limit = 3  # the real article has more segments
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读类型章节',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读成因段落',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '跨页核对相反位置关系', 'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'back', 'purpose': '返回原词条核验身份',
             'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '续读剩余章节',
             'expected': {'kind': 'scroll_changed'}},
        ]
        result, evidence = await self._run('d10', steps, ['cite:e_p3', 'stop'])
        self.assertFalse(result['host_failure'], result)
        self.assertEqual(result['effective_steps'], 5)
        self.assertEqual([a for a, _ in self.surface.executed],
                         ['scroll', 'scroll', 'click', 'back', 'scroll'])
        objective = self.objective_of(evidence)
        self.assertEqual(objective['status'], 'VERIFIED')

    async def test_d11_unrelated_image_churn_does_not_void_endpoint(self):
        """The second real r01 breakpoint: a decorative image row disappears in
        the final frame. The action-scoped ending keeps the endpoint safe."""
        from webcollect.action_stability import action_scoped_view_stable
        from webcollect.reading_progress import same_view
        surface = DirectSurface()
        surface.scroll = 2
        prefix = surface._render()
        image = {'element_id': 'e_img', 'native_role': 'img', 'text': '', 'parent_id': 'root',
                 'bbox': [700, 130, 900, 200], 'enabled': True, 'visible': True,
                 'element_type': 'image', 'state': 'default', 'scrollable': False,
                 'clickable': False, 'inputable': False}
        churned = deepcopy(prefix)
        churned['elements'].append(deepcopy(image))  # frame A carries the image
        churned['geometry_witnesses'].append({'element_id': 'e_img', 'bbox': image['bbox'],
                                              'samples': [{'point': [701, 131], 'ancestor': True}]})
        churned['capture_controls'].append({'element_id': 'e_img',
                                            'selector': 'html:1 > body:1 > main:1 > img:1',
                                            'index': 0, 'tag': 'img', 'href': None})
        self.assertFalse(same_view(churned, prefix))  # the old full-equality rule
        self.assertTrue(action_scoped_view_stable(churned, prefix))  # image churn tolerated
        moved = deepcopy(prefix)
        moved['scroll'] = [0, 999]
        self.assertFalse(action_scoped_view_stable(churned, moved))
        replaced = deepcopy(prefix)
        for e in replaced['elements']:
            if e['element_id'] == 'e_p3':
                e['text'] = '正文被替换的无关内容，不再是原来的阅读材料。'
        self.assertFalse(action_scoped_view_stable(churned, replaced))

    async def test_d9_non_article_entry_cannot_direct_verify(self):
        wrong_objective = deepcopy(DIRECT_OBJECTIVE)
        wrong_objective['evidence_contract'] = {
            'version': EVIDENCE_VERSION, 'kind': 'reading', 'subject': '日食',
            'aspects': ['月球', '地球'], 'direct_entry': True}
        task = self.direct_task(objective=wrong_objective)  # entry stays the 月食 article
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读',
             'expected': {'kind': 'scroll_changed'}},
        ]
        result, evidence = await self._run('d9', steps, ['stop'], task=task)
        objective = self.objective_of(evidence)
        self.assertEqual(objective['status'], 'UNVERIFIED')
        self.assertFalse(objective['opened_results'])


class ObjectiveBindingTests(unittest.TestCase):
    """evidence_policy stamps frozen task identity; old objectives unchanged."""

    def _claim(self):
        return {'candidate_id': 'candidate-x', 'version': 1,
                'snapshot': {'entry_url': ARTICLE, 'requested_goal': None}}

    def _binding(self, objective):
        reference = {'path': 'objective.json', 'sha256': '0' * 64}
        with patch('webcollect.session_objective.load_json', return_value={
                'schema_version': 'webcollect-session-objective-1', 'candidate_id': 'candidate-x',
                'version': 1, 'entry_url': ARTICLE, 'requested_goal': None,
                'objective': objective}):
            with patch('webcollect.session_objective.verify_evidence'):
                from webcollect.session_objective import bind
                return bind(reference, self._claim())

    def test_evidence_policy_binds_fragment_and_identity(self):
        from webcollect.session_objective import apply
        binding = self._binding(deepcopy(DIRECT_OBJECTIVE))
        task = build_url_task(url=ARTICLE, task_version='t', ending_policy=END_V3,
                              plan_protocol=V11_VERSION,
                              action_stability_protocol=ACTION_SCOPED_VERSION)
        before_id = task['task_id']
        apply(task, binding)
        self.assertEqual(task['fragment']['action_stability_protocol'], ACTION_SCOPED_VERSION)
        self.assertEqual(task['workflow_proposal']['spec']['action_stability_protocol'],
                         ACTION_SCOPED_VERSION)
        self.assertNotEqual(task['task_id'], before_id)  # sealed into frozen identity

    def test_objective_without_policy_keeps_generator_protocol(self):
        from webcollect.session_objective import apply
        plain = deepcopy(DIRECT_OBJECTIVE)
        plain.pop('evidence_policy')
        binding = self._binding(plain)
        task = build_url_task(url=ARTICLE, task_version='t', ending_policy=END_V3,
                              plan_protocol=V11_VERSION,
                              action_stability_protocol=ACTION_SCOPED_VERSION)
        apply(task, binding)
        self.assertEqual(task['fragment']['action_stability_protocol'],
                         ACTION_SCOPED_VERSION)

    def test_unknown_policy_rejected_and_direct_entry_validated(self):
        from webcollect.session_objective import bind
        from webcollect.goal_evidence import validate_contract
        bad = deepcopy(DIRECT_OBJECTIVE)
        bad['evidence_policy'] = 'webcollect-anything-else'
        with self.assertRaises(ValueError):
            self._binding(bad)
        validate_contract(DIRECT_OBJECTIVE['evidence_contract'])
        legacy = {'version': 'webcollect-goal-evidence-1', 'kind': 'reading', 'subject': SUBJECT,
                  'aspects': ['月球', '地球'], 'direct_entry': True}
        with self.assertRaises(ValueError):
            validate_contract(legacy)
        self.assertIn('不经过站内检索', system_for(self._task_with_direct_contract()))

    def _task_with_direct_contract(self):
        task = build_url_task(url=ARTICLE, task_version='t', ending_policy=END_V3,
                              plan_protocol=V11_VERSION, action_stability_protocol=ACTION_SCOPED_VERSION)
        spec = task['workflow_proposal']['spec']
        spec['goal'] = {'instruction': DIRECT_OBJECTIVE['description'],
                        'structured': deepcopy(DIRECT_OBJECTIVE)}
        task['task_id'] = 'react-' + object_sha256({'url': ARTICLE, 'spec': spec})[:24]
        return task

    def test_direct_entry_prompt_and_no_forced_first_search_click(self):
        prompt = system_for(self._task_with_direct_contract())
        self.assertIn('本任务入口已直接打开目标词条', prompt)
        self.assertIn('首轮从已打开的目标词条正文直接规划自然阅读路径', prompt)
        self.assertIn('按冻结目标与当前页面证据自由组合', prompt)  # V11 free composition kept
        # The general (non-direct) reading prompt keeps the search-flow wording.
        general_task = build_url_task(url=ARTICLE, task_version='t', ending_policy=END_V3,
                                      plan_protocol=V11_VERSION,
                                      action_stability_protocol=ACTION_SCOPED_VERSION)
        spec = general_task['workflow_proposal']['spec']
        spec['goal'] = {'instruction': '检索月食并阅读', 'structured': {
            'kind': 'reading', 'description': '检索月食并往下阅读',
            'minimum_effective_steps': 5, 'preferred_band': 'long',
            'evidence_contract': {'version': EVIDENCE_VERSION, 'kind': 'reading', 'subject': SUBJECT,
                                  'aspects': ['月球', '地球']}}}
        general_task['task_id'] = 'react-' + object_sha256({'url': ARTICLE, 'spec': spec})[:24]
        self.assertIn('聚焦后的type只证明输入框值', system_for(general_task))


class FourRouteDedupTests(unittest.TestCase):
    """Strict four-route predicates unchanged: shared first frame is route1."""

    def _sample(self, root, sample_id, instruction, steps, images):
        folder = root / sample_id
        (folder / 'images').mkdir(parents=True)
        (folder / 'ui_tree').mkdir(parents=True)
        for name, png in images.items():
            (folder / 'images' / name).write_bytes(png)
            (folder / 'ui_tree' / name).with_suffix('.json').write_text('{}')
        rows = []
        for index, (action_type, target_text, page, image) in enumerate(steps, start=1):
            rows.append({'step_id': index,
                         'action': {'action_type': action_type, 'target_text': target_text},
                         'page_name': page, 'image_path': f'images/{image}',
                         'ui_tree_path': f'ui_tree/{image}'})
            (folder / 'ui_tree' / image).with_suffix('.json').write_text('{}')
        save_json(folder / 'annotation.json',
                  {'sample_id': sample_id, 'task_instruction': instruction, 'steps': rows,
                   'final_result': instruction})
        return folder / 'annotation.json'

    @staticmethod
    def _png(pattern, size=(64, 64)):
        """Distinct high-frequency images: solid colours hash identically."""
        image = Image.new('RGB', size, (0, 0, 0))
        draw = ImageDraw.Draw(image)
        for index in range(size[0]):
            for y in range(size[1]):
                draw.point((index, y), fill=pattern(index, y))
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue()

    def test_different_actions_but_shared_first_frame_hits_route1(self):
        from quality_inspector.duplicates import analyze_inputs
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self._png(lambda x, y: (x * 4 % 256, y * 4 % 256, (x + y) % 256))
            last_a = self._png(lambda x, y: ((x * 3 + y) % 256, (x ^ y) % 256, 255 - x * 2 % 256))
            last_b = self._png(lambda x, y: (255 - (x + y) % 256, (y * 5) % 256, (x * y) % 256))
            a = self._sample(root, 'S1_sample_000001', '从月食词条直接阅读并说明月球与地球的位置关系',
                             [('scroll', '', '月食', 'step_001.png'),
                              ('click', '日食', '月食', 'step_002.png')],
                             {'step_001.png': first, 'step_002.png': last_a})
            b = self._sample(root, 'S1_sample_000002', '直接打开月食词条向下阅读核对成因段落',
                             [('click', '目录', '月食', 'step_001.png'),
                              ('back', '', '月食', 'step_002.png')],
                             {'step_001.png': first, 'step_002.png': last_b})
            result = analyze_inputs([a, b])
            self.assertEqual(result['route1']['confirmed_pair_count'], 1)
            self.assertEqual(result['route2']['count'], 0)  # action sequences differ
            self.assertEqual(result['route3']['count'], 0)
            self.assertEqual(result['route4']['count'], 0)

    def test_identical_action_sequence_hits_route2_regardless_of_images(self):
        from quality_inspector.duplicates import analyze_inputs
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            steps = [('scroll', '', '月食', 'step_001.png'), ('click', '日食', '月食', 'step_002.png')]
            a = self._sample(root, 'S2_sample_000001', '阅读月食词条前段并跨页核对日食定义', steps,
                             {'step_001.png': self._png(lambda x, y: (x * 4 % 256, y * 4 % 256, 0)),
                              'step_002.png': self._png(lambda x, y: ((x * 3 + y) % 256, 0, 0))})
            b = self._sample(root, 'S2_sample_000002', '阅读月食词条前段并跨页核对日食定义', steps,
                             {'step_001.png': self._png(lambda x, y: (0, (x + y) % 256, x % 256)),
                              'step_002.png': self._png(lambda x, y: (0, 0, (x ^ y) % 256))})
            result = analyze_inputs([a, b])
            self.assertEqual(result['route2']['count'], 1)


CHURN_HTML = '''<!doctype html><meta charset="utf-8"><title>月食</title><style>
body{margin:0;font:16px Arial;background:white;color:black}
#head{position:absolute;left:260px;top:10px;width:505px}
#q{width:440px;height:42px;font:16px Arial}
#churn{position:absolute;left:265px;top:56px;width:448px;height:150px;border:1px solid #a2a9b1}
#spin{position:absolute;left:44px;top:90px;width:300px;height:28px;background:#eaf3ff}
main{position:absolute;left:60px;top:220px}a{color:#36c}
</style><div id="head"><form id="f" onsubmit="return go()"><input id="q" type="search"
placeholder="搜索" autocomplete="off"></form></div>
<div id="churn"></div><div id="spin">占位</div>
<main><h1>月食</h1><p id="p1">月食是当地球位于太阳与月球之间、月球进入地球阴影时出现的现象。</p>
<p id="p2" style="margin-top:1200px">发生月食时，地球位于太阳与月球之间，月球进入地球的本影，因此只能出现在满月之夜。</p>
<p>相关条目：<a id="rel" href="/wiki/%E6%97%A5%E9%A3%9F">日食</a></p></main>
<script>
let tick=0;const churn=document.getElementById('churn'),spin=document.getElementById('spin');
const WORDS=['月食','月食的过程','月食观测','月食的历史','月食记录'];
setInterval(()=>{tick++;let html='';for(let i=0;i<4;i++){html+='<div>'+WORDS[(tick+i)%WORDS.length]+'</div>';}
churn.innerHTML=html;spin.textContent='轮换'+(tick%3);},350);
function go(){location.href='/search?q='+encodeURIComponent(document.getElementById('q').value);return false;}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter'){go();}});
</script>'''

RELATED_CHURN_HTML = '''<!doctype html><meta charset="utf-8"><title>日食</title><style>
body{margin:0;font:16px Arial}main{position:absolute;left:60px;top:40px}a{color:#36c}
</style><main><h1>日食</h1><p>日食是月球运行到太阳与地球之间的现象，与月食位置关系相反。</p></main>'''

SEARCH_LANDING = '''<!doctype html><meta charset="utf-8"><title>检索结果</title><style>
body{margin:0;font:16px Arial}main{position:absolute;left:60px;top:40px}
</style><main><h1>检索结果</h1><p>月食相关结果。</p></main>'''


def route_local(url):
    from urllib.parse import unquote
    path = url.split('local.test', 1)[-1].split('?')[0]
    if path.startswith('/wiki/'):
        return RELATED_CHURN_HTML if unquote(path[6:]) == '日食' else CHURN_HTML
    if path.startswith('/search'):
        return SEARCH_LANDING
    return CHURN_HTML


class RealChromiumActionScopedTests(unittest.IsolatedAsyncioTestCase):
    """Real browser, local route: the new evidence chain under live churn."""

    INPUT_SELECTOR = ('html:nth-of-type(1) > body:nth-of-type(1) > div:nth-of-type(1) > '
                      'form:nth-of-type(1) > input:nth-of-type(1)')

    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(channel='chrome', headless=True)
        self.context = await self.browser.new_context(viewport={'width': 1280, 'height': 720},
                                                      device_scale_factor=1)

        async def handle(route):
            await route.fulfill(status=200, content_type='text/html; charset=utf-8',
                                body=route_local(route.request.url))
        await self.context.route('**/*', handle)
        self.page = await self.context.new_page()

    async def asyncTearDown(self):
        await self.context.close()
        await self.browser.close()
        await self.pw.stop()

    async def test_focus_type_submit_under_undeclared_churn(self):
        from webcollect import browser
        from webcollect.collect import capture_before_action
        from webcollect.action_stability import action_scoped_scope
        from webcollect.dynamic_regions import regions as allowed_regions
        await self.page.goto('https://local.test/wiki/%E6%9C%88%E9%A3%9F', wait_until='domcontentloaded')
        await self.page.wait_for_timeout(400)
        probe = await browser.observe(self.page, self.INPUT_SELECTOR)
        # The churn boxes carry no announcement/suggestion classification: the
        # old full-page rule would keep failing on them.
        self.assertEqual([r['category'] for r in allowed_regions(probe) if r.get('eligible') is True], [])
        click_scope = action_scoped_scope(probe, probe['target']['element_id'], 'click')
        with TemporaryDirectory() as tmp:
            observation = await capture_before_action(self.page, Path(tmp), self.INPUT_SELECTOR,
                                                      timeout=30, action_scope=click_scope)
        self.assertTrue(observation['action_state_preflight']['matched'])
        self.assertEqual(observation['action_refresh']['stage'], 'complete')
        box = await self.page.locator('#q').bounding_box()
        await self.page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        await self.page.wait_for_timeout(1200)  # churn keeps running under focus
        focused = await browser.observe(self.page, self.INPUT_SELECTOR)
        type_scope = action_scoped_scope(focused, focused['target']['element_id'], 'type')
        with TemporaryDirectory() as tmp:
            observation = await capture_before_action(self.page, Path(tmp), self.INPUT_SELECTOR,
                                                      timeout=30, action_scope=type_scope)
        self.assertTrue(observation['action_state_preflight']['matched'])
        await self.page.keyboard.type('月食', delay=30)
        await self.page.wait_for_timeout(800)
        typed = await browser.observe(self.page, self.INPUT_SELECTOR)
        submit_scope = action_scoped_scope(typed, typed['target']['element_id'], 'hotkey')
        with TemporaryDirectory() as tmp:
            observation = await capture_before_action(self.page, Path(tmp), self.INPUT_SELECTOR,
                                                      timeout=30, action_scope=submit_scope)
        self.assertTrue(observation['action_state_preflight']['matched'])
        await self.page.keyboard.press('Enter')
        await self.page.wait_for_load_state('domcontentloaded')
        landed = await browser.observe(self.page)
        self.assertIn('/search', landed['url'])
        from webcollect.action_stability import post_action_document_scope
        from webcollect.browser import viewport_png
        post = post_action_document_scope(typed, {'operation_id': 'real-1'})
        later = await browser.observe(self.page)
        png_first, _ = await viewport_png(self.page)
        png_second, _ = await viewport_png(self.page)
        proof = stability_pair(landed, later, png_first, png_second, action_scope=post)
        self.assertTrue(proof['accepted'])

    async def test_occluded_and_mismatched_targets_reject(self):
        from webcollect import browser
        from webcollect.action_stability import action_scoped_scope
        from webcollect.browser import viewport_png
        await self.page.goto('https://local.test/wiki/%E6%9C%88%E9%A3%9F', wait_until='domcontentloaded')
        await self.page.wait_for_timeout(300)
        await self.page.evaluate(
            'document.body.insertAdjacentHTML("beforeend",'
            '"<div id=\'cover\' style=\'position:absolute;left:250px;top:0px;width:520px;'
            'height:70px;background:rgba(0,0,0,0.9);z-index:9\'></div>")')
        await self.page.wait_for_timeout(300)
        probe = await browser.observe(self.page, self.INPUT_SELECTOR)
        node = next((b['element_id'] for b in probe['capture_controls']
                     if b.get('selector') == self.INPUT_SELECTOR), None)
        covered = next((e for e in probe['elements'] if e.get('element_id') == node), None)
        # An occluded target is invisible or gone from the synchronized tree;
        # either way no scoped proof can be built for it.
        self.assertTrue(covered is None or covered.get('visible') is not True)
        if covered is not None:
            with self.assertRaises(ValueError):
                action_scoped_scope(probe, node, 'click')
        # A scope frozen on the article does not survive a navigation: the
        # document basis differs, so the pair proof rejects it.
        await self.page.evaluate('document.getElementById("cover").remove()')
        await self.page.wait_for_timeout(200)
        entry = await browser.observe(self.page, self.INPUT_SELECTOR)
        scope = action_scoped_scope(entry, entry['target']['element_id'], 'click')
        png_entry, _ = await viewport_png(self.page)
        await self.page.evaluate('location.href="/wiki/%E6%97%A5%E9%A3%9F"')
        await self.page.wait_for_load_state('domcontentloaded')
        await self.page.wait_for_timeout(300)
        related = await browser.observe(self.page)
        png_related, _ = await viewport_png(self.page)
        proof = stability_pair(entry, related, png_entry, png_related, action_scope=scope)
        self.assertFalse(proof['accepted'])

    async def test_real_direct_article_scroll_click_back_with_action_scoped_document_proofs(self):
        from webcollect import browser
        from webcollect.action_stability import document_scope
        from webcollect.browser import viewport_png
        await self.page.goto('https://local.test/wiki/%E6%9C%88%E9%A3%9F', wait_until='domcontentloaded')
        await self.page.wait_for_timeout(300)
        entry = await browser.observe(self.page)
        scroll_scope = document_scope(entry, 'scroll')
        png_entry, _ = await viewport_png(self.page)
        await browser.execute(self.page, 'scroll', {'direction': 'down', 'x': 640, 'y': 360}, {})
        await self.page.wait_for_timeout(400)
        first = await browser.observe(self.page)
        self.assertGreater(first['scroll'][1], entry['scroll'][1])
        await browser.execute(self.page, 'scroll', {'direction': 'down', 'x': 640, 'y': 360}, {})
        await self.page.wait_for_timeout(400)
        scrolled = await browser.observe(self.page)
        png_scrolled, _ = await viewport_png(self.page)
        pre = stability_pair(entry, entry, png_entry, png_entry, action_scope=deepcopy(scroll_scope))
        self.assertTrue(pre['accepted'])
        moved = stability_pair(entry, scrolled, png_entry, png_scrolled, action_scope=deepcopy(scroll_scope))
        self.assertFalse(moved['accepted'])  # pre-dispatch basis must hold the recorded position
        self.assertTrue(any('地球位于太阳与月球之间' in (e.get('text') or '')
                            for e in scrolled['elements'] if e.get('visible')))
        link = next(e for e in scrolled['elements']
                    if e.get('text') == '日食' and e.get('clickable') and e.get('visible'))
        await browser.execute(self.page, 'click',
                              {'x': (link['bbox'][0] + link['bbox'][2]) / 2,
                               'y': (link['bbox'][1] + link['bbox'][3]) / 2},
                              {'wait_navigation': True})
        related = await browser.observe(self.page)
        self.assertEqual(related['title'], '日食')
        await browser.execute(self.page, 'back', {}, {'wait_navigation': True})
        returned = await browser.observe(self.page)
        self.assertEqual(returned['url'], entry['url'])
        self.assertEqual(returned['title'], entry['title'])


if __name__ == '__main__':
    unittest.main()
