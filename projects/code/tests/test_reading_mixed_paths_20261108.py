"""Mixed reading path families and suggestion-overlay evidence (2026-11-08).

Covers the four results of this round on the general reading protocol:
1. The wwiki type-step breakpoint shape: a focused search combobox whose
   suggestion popup and rotating notice churn between two no-action captures
   must pass the shared dynamic-region comparison, while input value, focus or
   hit changes still reject the scoped typing proof.
2. Path families A1/A2/B (multi-segment reading, cross-page check then return
   reading, two-purpose cross-page checks) as full offline sessions with exact
   effective-step counts, honest goal evidence and save/derivation agreement.
3. Zero-effect counterexamples: found-but-unmoved scrolls, mechanical
   same-link repeats and wrong-result opens never become reading credit.
4. One real-Chromium local-HTML integration: real capture/verify across a live
   churning suggestion popup and rotating notice, plus real scroll/click/back
   with position, landing and identity assertions. No provider, no network.
"""
import base64
import hashlib
import json
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
from webcollect.banded_plan import system_for
from webcollect.plan_protocol import PLAN_PROTOCOL, ENDING_POLICY, ACTION_STABILITY_PROTOCOL
from webcollect.goal_evidence import VERSION as EVIDENCE_VERSION, result_links
from webcollect.react_session import ReactSession, build_url_task
from webcollect.browser import stability_pair, fingerprint
from webcollect import dynamic_regions

HOME = 'https://local.test/home'
RESULTS = 'https://local.test/search'
ARTICLE = 'https://local.test/wiki/%E6%9C%88%E9%A3%9F'
RELATED = 'https://local.test/wiki/%E6%97%A5%E9%A3%9F'
WRONG = 'https://local.test/wiki/wrong'
SUBJECT = '月食'
INTRO = '月食是一种可见的天文现象，本条目介绍其观察记录与成因脉络。'
MID = '历史记录显示该现象出现的周期与轨道位置相关，观测机构整理了系统资料。'
ASPECTS_BODY = '发生月食时，地球位于太阳与月球之间，月球进入地球的本影，因此只能出现在满月之夜。'
RELATED_BODY = '日食是月球运行到太阳与地球之间的现象，与月食位置关系相反。'
NOTICES = ('交流群甲欢迎大家加入。', '交流群乙请大家一同关注。', '频道丙已经正式上线。')
SUGGESTIONS = ('月食', '月食的过程', '月食观测')
Q_SELECTOR = 'html:1 > body:1 > main:1 > form:1 > input:1'
REGION_ATTRS = {'id': None, 'class': None, 'role': None, 'aria-label': None,
                'aria-roledescription': None, 'title': None}
SEARCH_OPEN = (
    {'action': 'click', 'target': {'text': '搜索', 'role': 'textbox'},
     'purpose': '聚焦站内搜索框', 'expected': {'kind': 'focused', 'text': '搜索'}},
    {'action': 'type', 'target': {'text': '搜索', 'role': 'textbox'}, 'value': SUBJECT,
     'purpose': '输入检索词', 'expected': {'kind': 'value', 'text': SUBJECT}},
    {'action': 'hotkey', 'keys': ['enter'], 'purpose': '用回车提交站内检索',
     'expected': {'kind': 'search_results', 'text': SUBJECT}},
)


def draw_page(page, *, focused, scroll, overlay_tick, notice_tick, size=(1280, 720)):
    """Deterministic PNG that changes only inside the suggestion/notice boxes."""
    image = Image.new('RGB', size, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([260, 10, 770, 55], outline=(0, 0, 0), width=2)  # search box
    draw.rectangle([44, 90, 713, 121], fill=(250, 250, 210), outline=(200, 200, 160))
    draw.rectangle([50, 96, 50 + 20 * (notice_tick % 3 + 1), 115],
                   fill=(180, 40 + 30 * (notice_tick % 3), 40))
    if focused:
        for row in range(3):  # suggestion rows whose widths follow the tick
            width = 60 + 30 * ((overlay_tick + row) % 3 + 1)
            draw.rectangle([270, 60 + row * 50, 270 + width, 100 + row * 50],
                           fill=(40 * (row + 1), 90 + 40 * ((overlay_tick + row) % 3), 150))
    if page in ('article', 'related'):
        rows = {'article': 3, 'related': 1}[page]
        for index in range(min(scroll + 1, rows)):
            draw.rectangle([100, 140 + index * 60, 100 + 90 * (index + 1), 180 + index * 60],
                           fill=(20, 100 + index * 40, 60))
    elif page == 'results':
        draw.rectangle([100, 140, 400, 170], fill=(10, 10, 140))
        draw.rectangle([100, 190, 330, 220], fill=(140, 10, 10))
    return image


class PathSurface:
    """Search site with a churning combobox suggestion popup and rotating notice."""

    def __init__(self, entry='home'):
        self.page = entry
        self.history = [self._url_for(entry)]
        self.origins = {self._url_for(entry): 1000}
        self.q_value = ''
        self.focused = None
        self.scroll = 0
        self.navigations = 0
        self.tick = 0
        self.executed = []
        self.state = self._render()

    @staticmethod
    def _url_for(page):
        return {'home': HOME, 'results': RESULTS, 'article': ARTICLE,
                'related': RELATED, 'umbra': 'https://local.test/wiki/%E6%9C%AC%E5%BD%B1',
                'wrong': WRONG}[page]

    # ---- page models -------------------------------------------------
    def _overlay_rows(self):
        if self.page != 'home' or self.focused != 'e_q':
            return []
        order = [(self.tick + i) % 3 for i in range(3)]
        return [{'element_id': f'e_s{i}', 'native_role': 'a', 'text': SUGGESTIONS[order[i]],
                 'parent_id': 'e_menu', 'clickable': True} for i in range(3)]

    def _elements(self):
        if self.page == 'home':
            rows = [
                {'element_id': 'e_main', 'native_role': 'main', 'text': '', 'parent_id': 'root'},
                {'element_id': 'e_form', 'native_role': 'form', 'text': '', 'parent_id': 'e_main'},
                {'element_id': 'e_q', 'native_role': 'input',
                 'text': '搜索', 'parent_id': 'e_form', 'inputable': True, 'clickable': True},
                {'element_id': 'e_btn', 'native_role': 'button', 'text': '搜索',
                 'parent_id': 'e_form', 'clickable': True},
                {'element_id': 'e_note', 'native_role': 'p', 'text': NOTICES[self.tick % 3],
                 'parent_id': 'e_main'},
                {'element_id': 'e_intro', 'native_role': 'p', 'text': '输入关键词开始站内检索。',
                 'parent_id': 'e_main'},
            ]
            if self.focused == 'e_q':
                rows.append({'element_id': 'e_menu', 'native_role': 'listbox', 'text': '搜索结果',
                             'parent_id': 'e_form'})
                rows.extend(self._overlay_rows())
            return rows
        if self.page == 'results':
            return [
                {'element_id': 'e_note2', 'native_role': 'p', 'text': '站内检索结果如下。', 'parent_id': 'root'},
                {'element_id': 'e_l1', 'native_role': 'a', 'text': '基本现象词条',
                 'parent_id': 'root', 'clickable': True},
                {'element_id': 'e_l2', 'native_role': 'a', 'text': SUBJECT,
                 'parent_id': 'root', 'clickable': True},
            ]
        body = {'article': (INTRO, MID, ASPECTS_BODY), 'related': (RELATED_BODY,),
                'umbra': ('本影是影子中完全得不到光源直射的部分。',),
                'wrong': ('本页不含目标位置关系。',)}[self.page]
        heading = {'article': SUBJECT, 'related': '日食', 'umbra': '本影',
                   'wrong': '月食的基本现象'}[self.page]
        rows = [{'element_id': 'e_h', 'native_role': 'h1', 'text': heading, 'parent_id': 'root'},
                {'element_id': 'e_p1', 'native_role': 'p', 'text': body[0], 'parent_id': 'root'}]
        if self.page == 'article':
            if self.scroll >= 1:
                rows.append({'element_id': 'e_p2', 'native_role': 'p', 'text': MID, 'parent_id': 'root'})
            if self.scroll >= 2:
                rows.append({'element_id': 'e_p3', 'native_role': 'p', 'text': ASPECTS_BODY, 'parent_id': 'root'})
            rows.extend([
                {'element_id': 'e_rel', 'native_role': 'a', 'text': '日食', 'parent_id': 'root',
                 'clickable': True},
                {'element_id': 'e_umbra', 'native_role': 'a', 'text': '本影', 'parent_id': 'root',
                 'clickable': True}])
        return rows

    def _bindings(self):
        if self.page == 'home':
            rows = [{'element_id': 'e_main', 'selector': 'html:1 > body:1 > main:1', 'tag': 'main', 'href': None},
                    {'element_id': 'e_note', 'selector': 'html:1 > body:1 > main:1 > p:1', 'tag': 'p', 'href': None},
                    {'element_id': 'e_intro', 'selector': 'html:1 > body:1 > main:1 > p:2', 'tag': 'p', 'href': None},
                    {'element_id': 'e_form', 'selector': 'html:1 > body:1 > main:1 > form:1', 'tag': 'form',
                     'href': None, 'form_index': 0},
                    {'element_id': 'e_q', 'selector': Q_SELECTOR, 'tag': 'input', 'href': None,
                     'input_type': 'search', 'form_index': 0},
                    {'element_id': 'e_btn', 'selector': 'html:1 > body:1 > main:1 > form:1 > button:1',
                     'tag': 'button', 'href': None, 'form_index': 0}]
            if self.focused == 'e_q':
                menu = 'html:1 > body:1 > main:1 > form:1 > div:1 > ul:1'
                rows.append({'element_id': 'e_menu', 'selector': menu, 'tag': 'ul', 'href': None})
                for i, row in enumerate(self._overlay_rows()):
                    rows.append({'element_id': row['element_id'],
                                 'selector': f'{menu} > li:{i + 1} > a:1', 'tag': 'a', 'href': RESULTS})
            return rows
        if self.page == 'results':
            return [{'element_id': 'e_note2', 'selector': 'html:1 > body:1 > main:1 > p:1', 'tag': 'p', 'href': None},
                    {'element_id': 'e_l1', 'selector': 'html:1 > body:1 > main:1 > a:1', 'tag': 'a', 'href': WRONG},
                    {'element_id': 'e_l2', 'selector': 'html:1 > body:1 > main:1 > a:2', 'tag': 'a', 'href': ARTICLE}]
        rows = [{'element_id': 'e_h', 'selector': 'html:1 > body:1 > main:1 > h1:1', 'tag': 'h1', 'href': None},
                {'element_id': 'e_p1', 'selector': 'html:1 > body:1 > main:1 > p:1', 'tag': 'p', 'href': None}]
        if self.page == 'article':
            if self.scroll >= 1:
                rows.append({'element_id': 'e_p2', 'selector': 'html:1 > body:1 > main:1 > p:2', 'tag': 'p', 'href': None})
            if self.scroll >= 2:
                rows.append({'element_id': 'e_p3', 'selector': 'html:1 > body:1 > main:1 > p:3', 'tag': 'p', 'href': None})
            rows += [{'element_id': 'e_rel', 'selector': 'html:1 > body:1 > main:1 > a:1',
                      'tag': 'a', 'href': RELATED},
                     {'element_id': 'e_umbra', 'selector': 'html:1 > body:1 > main:1 > a:2',
                      'tag': 'a', 'href': 'https://local.test/wiki/%E6%9C%AC%E5%BD%B1'}]
        else:
            rows = [{'element_id': 'e_h', 'selector': 'html:1 > body:1 > main:1 > h1:1', 'tag': 'h1', 'href': None},
                    {'element_id': 'e_p1', 'selector': 'html:1 > body:1 > main:1 > p:1', 'tag': 'p', 'href': None}]
        return rows

    def _contract(self):
        notice = {'schema_version': dynamic_regions.VERSION, 'category': 'announcement',
                  'tag': 'p', 'native_image_paint': None,
                  'attributes': {**REGION_ATTRS, 'id': 'siteNotice', 'class': 'site-notice'},
                  'selector': 'html:1 > body:1 > main:1 > p:1', 'element_id': 'e_note',
                  'bbox': [44, 90, 713, 121], 'raw_bbox': [44, 90, 713, 121],
                  'native_paint_bbox': [44, 90, 713, 121], 'clip_bbox': [0, 0, 1280, 720],
                  'member_ids': ['e_note'], 'member_selectors': ['html:1 > body:1 > main:1 > p:1'],
                  'eligible': True, 'reasons': [], 'external_text_overlaps': [],
                  'external_paint_overlaps': [], 'external_control_ids': [], 'target_inside': False}
        regions = [notice]
        if self.page == 'home' and self.focused == 'e_q':
            members = ['e_menu'] + [row['element_id'] for row in self._overlay_rows()]
            menu = 'html:1 > body:1 > main:1 > form:1 > div:1 > ul:1'
            regions.append({'schema_version': dynamic_regions.VERSION,
                            'category': dynamic_regions.SUGGESTION_CATEGORY, 'tag': 'ul',
                            'native_image_paint': None,
                            'attributes': {**REGION_ATTRS, 'id': 'v-0', 'class': 'cdx-menu__listbox',
                                           'role': 'listbox', 'aria-label': '搜索结果'},
                            'selector': menu, 'element_id': 'e_menu',
                            'bbox': [266, 56, 713, 210], 'raw_bbox': [266, 56, 713, 210],
                            'native_paint_bbox': [266, 56, 713, 210], 'clip_bbox': [0, 0, 1280, 720],
                            'member_ids': members,
                            'member_selectors': [menu] + [f'{menu} > li:{i + 1} > a:1'
                                                          for i in range(len(members) - 1)],
                            'eligible': True, 'reasons': [], 'external_text_overlaps': [],
                            'external_paint_overlaps': [], 'external_control_ids': [],
                            'target_inside': False,
                            'suggestion_binding': {
                                'schema_version': dynamic_regions.SUGGESTION_VERSION,
                                'combobox_selector': Q_SELECTOR, 'input_type': 'search',
                                'link': 'aria_owns'}})
        outside = '\n'.join(row.get('text') or '' for row in self._elements()
                            if row['element_id'] not in {'e_note', 'e_menu'} and
                            not str(row['element_id']).startswith('e_s'))
        return {'schema_version': dynamic_regions.VERSION, 'regions': regions,
                'visible_text_outside': outside, 'ancestor_text_outside': {}}

    def _url(self):
        return self._url_for(self.page) if self.page != 'wrong' else WRONG

    def _title(self):
        return {'home': '站内检索', 'results': '检索结果', 'article': SUBJECT,
                'related': '日食', 'umbra': '本影', 'wrong': '月食的基本现象'}[self.page]

    def _render(self, *, probe=None):
        elements = []
        for i, row in enumerate(self._elements()):
            row = dict(row)
            top = 20 + i * 45 if self.page == 'home' else 130 + i * 60
            row.update(bbox=[10, top, 640, top + 40], enabled=True, visible=True,
                       element_type='link' if row['native_role'] == 'a' else
                       ('input' if row.get('inputable') else 'text'),
                       state='default', scrollable=False,
                       clickable=row.get('clickable', False), inputable=row.get('inputable', False))
            elements.append(row)
        values = [] if self.page != 'home' else [{
            'element_id': 'e_q', 'value': self.q_value, 'focused': self.focused == 'e_q',
            'selection_start': len(self.q_value), 'selection_end': len(self.q_value),
            'input_type': 'search', 'value_visible': True, 'readonly': False, 'enabled': True,
        }]
        witnesses = []
        for e in elements:
            box = e['bbox']
            samples = [{'point': [x, y], 'ancestor': True}
                       for y in (box[1] + 1, (box[1] + box[3]) / 2, box[3] - 1)
                       for x in (box[0] + 1, (box[0] + box[2]) / 2, box[2] - 1)]
            witnesses.append({'element_id': e['element_id'], 'bbox': box, 'samples': samples})
        state = {'url': self._url(), 'title': self._title(),
                 'document_identity': {'url_without_fragment': self._url(),
                                       'performance_time_origin': self.origins[self._url()]},
                 'scroll': [0, self.scroll * 480 if self.page != 'home' else 0],
                 'screen_resolution': [1280, 720], 'device_pixel_ratio': 1, 'target': None,
                 'capture_readiness': {'schema_version': 'webcollect-capture-readiness-1',
                                       'document_ready': 'complete', 'fonts_ready': True, 'images_ready': True},
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
                label = value.get('value') or '搜索'
                state['target'] = {'element_id': eid, 'coordinate': [30, row['bbox'][1] + 10],
                                   'bbox': row['bbox'], 'hit_valid': True,
                                   'focused': value.get('focused', False), 'value': value.get('value'),
                                   'readonly': False,
                                   'visible_label_evidence': [{'kind':
                                       'visible_native_value' if value.get('value') else 'visible_placeholder',
                                       'text': label}]}
        return state

    def png(self, state=None, *, probe=False):
        # Probe captures render identical pixels to plain captures, like the
        # real viewport: the probe is DOM truth, never a painted marker.
        import io
        image = draw_page(self.page, focused=self.focused == 'e_q',
                          scroll=self.scroll, overlay_tick=self.tick, notice_tick=self.tick)
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue()

    # ---- surface protocol -------------------------------------------
    async def capture(self, page, selector=None, index=0, **kw):
        self.tick += 1  # every capture observes a new churn frame, like the live site
        state = self._render(probe=selector)
        for value in state['values']:
            value['display_value'] = value['value']
        png = self.png(state, probe=selector is not None)
        from webcollect.browser import CAPTURE_VERSION
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
        return {'state': state, 'png': png, 'capture': {'schema_version': CAPTURE_VERSION,
            'snapshot_source': 'browser_dom', 'screenshot_sha256': hashlib.sha256(png).hexdigest(),
            'natural_wait_requested_ms': 0, 'natural_wait_observed_ms': 0, 'natural_wait_budget_ms': 8000,
            'coordinate_space': 'screenshot_css_pixels', 'attempts': [attempt]}}

    def _navigate(self, page):
        self.page_scroll = getattr(self, 'page_scroll', {})
        self.page_scroll[self._url()] = self.scroll
        if page == 'back-target':
            url = self.history[-1]
            self.page = {v: k for k, v in
                         {'home': HOME, 'results': RESULTS, 'article': ARTICLE,
                          'related': RELATED,
                          'umbra': 'https://local.test/wiki/%E6%9C%AC%E5%BD%B1'}.items()}.get(url, 'wrong')
        else:
            url = self._url_for(page)
            self.history.append(url)
            self.page = page
        self.navigations += 1
        self.origins.setdefault(url, 1000 + self.navigations)  # back restores the same document
        self.scroll = self.page_scroll.get(url, 0) if page == 'back-target' else 0
        self.focused = None

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
                self._navigate('article')  # exact-term submit lands directly on the article
            elif hit and self.page == 'results' and hit.get('native_role') == 'a':
                self._navigate('wrong' if hit['element_id'] == 'e_l1' else 'article')
            elif hit and self.page == 'article' and hit['element_id'] in ('e_rel', 'e_umbra'):
                self._navigate('related' if hit['element_id'] == 'e_rel' else 'umbra')
        elif action_type == 'type':
            if self.focused == 'e_q':
                self.q_value = arguments['text']
        elif action_type == 'hotkey':
            keys = [str(k).lower() for k in arguments['keys']]
            if keys == ['enter'] and self.focused == 'e_q' and self.q_value == SUBJECT:
                self._navigate('results')
        elif action_type == 'scroll':
            limit = {'article': 2, 'related': 1}.get(self.page, 0)
            if self.scroll < limit:
                self.scroll += 1
        elif action_type == 'back':
            if len(self.history) > 1:
                self.history.pop()
                self._navigate('back-target')
        self.state = self._render()


def focus_combobox(surface):
    """Click the synthetic search input at its rendered centre."""
    state = surface._render()
    row = next(e for e in state['elements'] if e['element_id'] == 'e_q')
    surface.execute_action('click', {'x': (row['bbox'][0] + row['bbox'][2]) // 2,
                                     'y': (row['bbox'][1] + row['bbox'][3]) // 2})


class PathHarness(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        network = patch.object(socket.socket, 'connect', side_effect=AssertionError('external IO forbidden'))
        network.start()
        self.addCleanup(network.stop)
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.surface = PathSurface()
        self.page = FakePage(self.surface)
        capture = patch('webcollect.browser.capture', side_effect=self.surface.capture)
        capture.start()
        self.addCleanup(capture.stop)
        execute_patch = patch('webcollect.browser.execute', side_effect=self._fake_execute)
        execute_patch.start()
        self.addCleanup(execute_patch.stop)
        verify_patch = patch('webcollect.browser.verify_execution_state', side_effect=self._fake_verify)
        verify_patch.start()
        self.addCleanup(verify_patch.stop)
        before_patch = patch('webcollect.collect.capture_before_action', side_effect=self._fake_before)
        before_patch.start()
        self.addCleanup(before_patch.stop)
        self.ids = {'sample_id': 'S000001_sample_000001', 'site_id': 'S000001',
                    'batch_id': 'B20261108_001', 'attempt_id': 'offline-mixed'}
        self.manifest = {'batch_id': 'B20261108_001', 'sample_kind': 'real',
                         'program_version': 'CONTROLLED', 'rule_version': '1.0.0',
                         'sites': [{'site_id': 'S000001', 'uri': HOME, 'site_category': 'reading'}],
                         'samples': [self.ids['sample_id']]}
        self.prompts = []

    async def _fake_execute(self, page, action_type, arguments, execution):
        self.surface.execute_action(action_type, arguments)

    async def _fake_verify(self, page, state, selector=None, index=0, **kw):
        return {'matched': True, 'state_fingerprint': fingerprint(state)}

    async def _fake_before(self, page, evidence, selector=None, index=0, **options):
        """capture_before_action shape over the synthetic surface: capture, then
        the (patched) pre-dispatch verification, with the same receipt fields."""
        observation = await self.surface.capture(page, selector, index,
                                                 **{'action_scope': options['action_scope']}
                                                 if options.get('action_scope') else {})
        observation['action_state_preflight'] = await self._fake_verify(
            page, observation['state'], selector, index)
        observation['action_refresh'] = {'timeout_seconds': 45, 'stage': 'complete', 'accepted': True,
                                         'attempts': [{'attempt': 1, 'capture_seconds': 0.05,
                                                       'verification_seconds': 0.05}],
                                         'action_executed': False, 'elapsed_seconds': 0.1}
        observation['action_deadline_monotonic'] = time.monotonic() + 45
        return observation

    OBJECTIVE = {
        'kind': 'reading',
        'description': '从站内入口检索月食，打开条目并往下阅读，用正文说明月球与地球的位置关系。',
        'minimum_effective_steps': 5, 'preferred_band': 'long',
        'evidence_contract': {'version': EVIDENCE_VERSION, 'kind': 'reading',
                              'subject': SUBJECT, 'aspects': ['月球', '地球']}}

    def reading_task(self, *, url=HOME, stability=True):
        from webcollect.planning import object_sha256
        task = build_url_task(url=url, task_version='reading', ending_policy=ENDING_POLICY,
                              plan_protocol=PLAN_PROTOCOL,
                              **({'action_stability_protocol': ACTION_STABILITY_PROTOCOL} if stability else {}))
        spec = task['workflow_proposal']['spec']
        spec['goal'] = {'instruction': self.OBJECTIVE['description'],
                        'structured': deepcopy(self.OBJECTIVE)}
        task['task_id'] = 'react-' + object_sha256({'url': spec.get('entry_url'), 'spec': spec})[:24]
        return task

    def scripted(self, name, plan, branches, task=None, *, entry='home'):
        """branches: either a preference list (first offered option wins, with
        'cite:e_p3' preferred over plain continue) or per-prompt callables."""
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
                if any(option.startswith(wanted.split(':')[0] + ':') and ':' in wanted
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

        if entry != 'home':
            self.surface.__init__(entry)
        evidence = self.root / name / 'evidence' / self.ids['sample_id']
        bound_task = task if task is not None else self.reading_task(
            url={'home': HOME, 'article': ARTICLE}[entry])
        session = ReactSession(bound_task, evidence / 'raw',
                               choose, self.page, steps_directory=evidence, attempt_id='offline-mixed')
        return session, evidence

    def reply(self, choice, **extra):
        return lambda p: {'attempt_id': p['attempt_id'],
                          'observation_id': p['observation']['observation_id'],
                          'choice': choice, **extra}

    def plan_with(self, prompt, steps, *, band='long', goal=None):
        def with_narratives(step):
            step = deepcopy(step)
            step.setdefault('rationale', '原目标需要该动作推进当前阅读链路')
            step.setdefault('expected_result', '页面按该动作产生可见业务变化')
            return step
        return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
                'band': band, 'band_reason': '自然多段阅读链路',
                'goal': goal or '站内检索月食，跨页核对后继续阅读，说明月球与地球的位置关系',
                'checks': [{'field': '月球与地球的位置关系'}], 'steps': [with_narratives(s) for s in steps],
                'finish_when': {'kind': 'goal_evidence'}, 'replan_when': '检索无结果或正文缺失'}


class SuggestionOverlayEvidenceTests(PathHarness):
    """The wwiki type-step breakpoint shape, reproduced frame by frame."""

    def _churn_pair(self):
        surface = PathSurface()
        focus_combobox(surface)
        before = surface._render(probe=Q_SELECTOR)
        png_before = surface.png(before, probe=True)
        surface.tick += 1  # overlay reordered + notice rotated between captures
        after = surface._render(probe=Q_SELECTOR)
        png_after = surface.png(after, probe=True)
        return before, after, png_before, png_after

    def test_churning_overlay_and_notice_pass_shared_comparison(self):
        before, after, png_before, png_after = self._churn_pair()
        proof = stability_pair(before, after, png_before, png_after)
        self.assertTrue(proof['accepted'], proof.get('scope_error') or proof['pixel_change'])
        self.assertTrue(proof['related_dom_stable'])
        self.assertEqual(proof['pixel_change']['outside_dynamic_pixels'], 0)
        suggestion = [r for r in dynamic_regions.regions(before)
                      if r['category'] == dynamic_regions.SUGGESTION_CATEGORY]
        self.assertEqual(len(suggestion), 1)
        announcement = [r for r in dynamic_regions.regions(before) if r['category'] == 'announcement']
        self.assertEqual(len(announcement), 1)

    async def test_suggestion_links_are_not_search_results(self):
        from webcollect.agent_observation import project
        surface = PathSurface()
        focus_combobox(surface)  # overlay open with subject rows
        captured = await surface.capture(None, Q_SELECTOR)
        evidence_state = self.root / 'link-state.json'
        evidence_png = self.root / 'link.png'
        evidence_capture = self.root / 'link.capture.json'
        save_json(evidence_state, captured['state'])
        save_json(evidence_capture, captured['capture'])
        evidence_png.write_bytes(captured['png'])
        digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
        observation = project(captured['state'], {
            'image': {'path': str(evidence_png), 'sha256': digest(evidence_png)},
            'state': {'path': str(evidence_state), 'sha256': digest(evidence_state)},
            'capture': {'path': str(evidence_capture), 'sha256': digest(evidence_capture)}})
        self.assertTrue(observation['capture_verified'])
        self.assertTrue(any('月食' in (c['element'].get('text') or '')
                            for c in observation['controls'].values()))
        links = result_links(observation, observation, SUBJECT)
        self.assertEqual(links, {})  # suggestion rows never impersonate results

    def test_forged_or_unbound_suggestion_rows_stay_rejected(self):
        surface = PathSurface()
        focus_combobox(surface)
        state = surface._render()
        unbound = deepcopy(state)
        unbound['dynamic_region_contract']['regions'][1].pop('suggestion_binding')
        self.assertEqual([r for r in dynamic_regions.regions(unbound)
                          if r['category'] == dynamic_regions.SUGGESTION_CATEGORY], [])
        forged = deepcopy(state)
        forged['dynamic_region_contract']['regions'][1]['suggestion_binding'] = {
            'schema_version': dynamic_regions.SUGGESTION_VERSION,
            'combobox_selector': 'html:1 > body:1 > main:1 > form:9 > input:1',
            'input_type': 'search', 'link': 'aria_owns'}
        self.assertEqual([r for r in dynamic_regions.regions(forged)
                          if r['category'] == dynamic_regions.SUGGESTION_CATEGORY], [])
        idle = PathSurface()._render()  # not focused: no overlay contract at all
        self.assertEqual([r for r in dynamic_regions.regions(idle)
                          if r['category'] == dynamic_regions.SUGGESTION_CATEGORY], [])


class DownwardReadingMappingTests(PathHarness):
    """The contracted objective itself requires its downward reading."""

    def _classic_plan(self, prompt, *, scrolls=1):
        steps = [
            {'action': 'click', 'target': {'text': '搜索', 'role': 'textbox'},
             'purpose': '聚焦站内搜索框', 'expected': {'kind': 'focused', 'text': '搜索'}},
            {'action': 'type', 'target': {'text': '搜索', 'role': 'textbox'}, 'value': SUBJECT,
             'purpose': '输入检索词', 'expected': {'kind': 'value', 'text': SUBJECT}},
            {'action': 'click', 'target': {'text': '搜索', 'role': 'button'},
             'purpose': '提交站内检索', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
        ] + [{'action': 'scroll', 'direction': 'down', 'purpose': '向下阅读正文',
              'expected': {'kind': 'scroll_changed'}} for _ in range(scrolls)]
        for step in steps:
            step.setdefault('rationale', '原目标需要该动作推进检索与阅读')
            step.setdefault('expected_result', '页面按该动作产生可见业务变化')
        return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
                'band': 'long' if scrolls else 'five', 'band_reason': '检索直达并向下阅读',
                'goal': '站内检索月食并向下阅读正文，说明月球与地球的位置关系',
                'checks': [{'field': '月球与地球的位置关系'}], 'steps': steps,
                'finish_when': {'kind': 'goal_evidence'}, 'replan_when': '检索无结果或正文缺失'}

    async def test_objective_without_stability_protocol_still_requires_downward_reading(self):
        # The raw-drive wwiki shape: no action_stability_protocol bound. Before
        # the fix this mapping silently reported required_downward_reading=false.
        session, evidence = self.scripted(
            'mapping', lambda p: self._classic_plan(p, scrolls=2),
            ['cite:e_p3', 'continue', 'stop'],
            task=self.reading_task(stability=False))
        result = await session.run()
        self.assertEqual(result['effective_steps'], 5)
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        objective = terminal['goal_evidence']['session_objective']
        self.assertTrue(objective['required_downward_reading'])
        self.assertTrue(objective['downward_reading'])
        self.assertEqual(objective['status'], 'VERIFIED')

    async def test_reading_required_without_any_downward_scroll(self):
        session, evidence = self.scripted(
            'required', lambda p: self._classic_plan(p, scrolls=0),
            ['continue', 'stop'],
            task=self.reading_task(stability=False))
        result = await session.run()
        self.assertEqual(result['effective_steps'], 3)
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        objective = terminal['goal_evidence']['session_objective']
        self.assertTrue(objective['required_downward_reading'])
        self.assertFalse(objective['downward_reading'])
        self.assertNotEqual(objective['status'], 'VERIFIED')


class PathFamilyTests(PathHarness):
    def derive(self, evidence, name='candidate'):
        destination = self.root / name / 'samples' / self.ids['sample_id']
        from webcollect.postprocess import process
        result = process(evidence, destination, self.ids, self.manifest)
        if result['status'] != 'derived_saved' and result.get('record_ref'):
            self.fail(str(load_json(result['record_ref']['path'])))
        self.assertEqual(result['status'], 'derived_saved', result)
        from webcollect.client_package import validate_client_sample
        from quality_inspector.format_checks import sample_check
        from webcollect.closing_policy import annotation_errors
        annotation = validate_client_sample(destination)
        check = sample_check(destination)
        self.assertTrue(check['confirmed_format_pass'], check['errors'])
        self.assertEqual(annotation_errors(annotation), [])
        return destination, annotation

    async def _run(self, name, steps, branches, *, entry='home', band='long'):
        session, evidence = self.scripted(name, lambda p: self.plan_with(p, steps, band=band),
                                          branches, entry=entry)
        result = await session.run()
        return result, evidence

    async def test_a1_cross_page_reading_then_return(self):
        tail = [
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '点击相关链接核对日食定义', 'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '新页面阅读与目标相关的正文',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'back', 'purpose': '返回月食条目并核验原页面身份',
             'expected': {'kind': 'document_changed', 'text': SUBJECT}},
        ]
        steps = [
            {'action': 'click', 'target': {'text': '搜索', 'role': 'textbox'},
             'purpose': '聚焦站内搜索框', 'expected': {'kind': 'focused', 'text': '搜索'}},
            {'action': 'type', 'target': {'text': '搜索', 'role': 'textbox'}, 'value': SUBJECT,
             'purpose': '输入检索词', 'expected': {'kind': 'value', 'text': SUBJECT}},
            {'action': 'click', 'target': {'text': '搜索', 'role': 'button'},
             'purpose': '提交站内检索直达条目', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '老页面滚动到正文区域A',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '老页面滚动到新的正文区域B',
             'expected': {'kind': 'scroll_changed'}},
        ] + tail
        def replan_tail(p):  # at a citation offer the cross-page tail is still required
            return {'attempt_id': p['attempt_id'],
                    'observation_id': p['observation']['observation_id'],
                    'choice': 'replan', 'plan': {'steps': deepcopy(tail)}}
        result, evidence = await self._run('a1', steps, [replan_tail, 'cite:e_p3', 'continue', 'stop'])
        self.assertFalse(result['host_failure'], result)
        self.assertEqual(result['effective_steps'], 8)
        self.assertEqual([a for a, _ in self.surface.executed],
                         ['click', 'type', 'click', 'scroll', 'scroll', 'click', 'scroll', 'back'])
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        objective = terminal['goal_evidence']['session_objective']
        # The back-return restored the read position, so the final frame shows
        # the aspects passage: both reading segments plus the final citation.
        self.assertEqual(objective['status'], 'VERIFIED')
        self.assertEqual(len(objective['downward_reading']), 2)  # both article segments
        destination, annotation = self.derive(evidence, name='derived-a1')
        self.assertEqual(annotation['steps'][-1]['tool_result']['return_value']['collection_ending']
                         ['verified_effective_steps'], 8)

    async def test_a2_return_then_continue_reading_new_segment(self):
        steps = list(SEARCH_OPEN) + [
            {'action': 'click', 'target': {'source': 'search_results', 'text': SUBJECT},
             'purpose': '打开月食条目', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '老页面滚动到正文区域A',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '跨页核对后返回', 'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'back', 'purpose': '返回月食条目并核验原页面身份',
             'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '老页面继续滚动到新的正文区域C',
             'expected': {'kind': 'scroll_changed'}},
        ]
        result, evidence = await self._run('a2', steps, ['cite:e_p3', 'continue', 'stop'])
        self.assertFalse(result['host_failure'], result)
        self.assertEqual(result['effective_steps'], 8)
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        objective = terminal['goal_evidence']['session_objective']
        self.assertEqual(objective['status'], 'VERIFIED')
        bodies = [entry['visible_new_body'][0]['quote'] for entry in objective['downward_reading']]
        self.assertEqual(bodies, [MID, ASPECTS_BODY])  # two distinct reading segments
        destination, annotation = self.derive(evidence, name='derived-a2')
        self.assertEqual(annotation['steps'][-1]['tool_result']['return_value']['collection_ending']
                         ['verified_effective_steps'], 8)

    async def test_b_two_purpose_cross_page_checks(self):
        steps = [
            {'action': 'click', 'target': {'text': '搜索', 'role': 'textbox'},
             'purpose': '聚焦站内搜索框', 'expected': {'kind': 'focused', 'text': '搜索'}},
            {'action': 'type', 'target': {'text': '搜索', 'role': 'textbox'}, 'value': SUBJECT,
             'purpose': '输入检索词', 'expected': {'kind': 'value', 'text': SUBJECT}},
            {'action': 'click', 'target': {'text': '搜索', 'role': 'button'},
             'purpose': '提交站内检索直达条目', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '第一次跨页查阅：核对日食定义', 'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'back', 'purpose': '返回月食条目', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '滚动阅读月食正文前段',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'click', 'target': {'text': '本影'},
             'purpose': '第二次跨页查阅：核对本影概念', 'expected': {'kind': 'document_changed', 'text': '本影'}},
            {'action': 'back', 'purpose': '再次返回月食条目',
             'expected': {'kind': 'document_changed', 'text': SUBJECT}},
        ]
        result, evidence = await self._run('b', steps, ['continue', 'stop'])
        self.assertEqual(result['effective_steps'], 8)
        self.assertEqual(result['collection_ending']['kind'], 'AGENT_STOP')
        self.assertEqual(result['collection_ending']['verified_effective_steps'], 8)
        # The direct submit opened the target article as a verified result.
        pages = [entry['text'] for entry in
                 load_json(evidence / 'raw' / 'terminal.json')['goal_evidence']['session_objective']['opened_results']]
        self.assertIn(SUBJECT, pages)

    async def test_exactly_five_step_general_path_with_related_scroll(self):
        # Article entry, general protocol: the A1 shape itself is exactly five
        # effective steps, and the related-page scroll is allowed only here.
        tail = [
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '点击相关链接核对', 'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '新页面阅读相关正文',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'back', 'purpose': '返回原条目核验身份',
             'expected': {'kind': 'document_changed', 'text': SUBJECT}},
        ]
        def replan_tail(p):  # at a citation offer the cross-page tail is still required
            return {'attempt_id': p['attempt_id'],
                    'observation_id': p['observation']['observation_id'],
                    'choice': 'replan', 'plan': {'steps': deepcopy(tail)}}
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': '滚动到正文区域A',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '滚动到新的正文区域B',
             'expected': {'kind': 'scroll_changed'}},
        ] + tail
        result, evidence = await self._run('five', steps, [replan_tail, 'continue', 'stop'],
                                           entry='article', band='five')
        self.assertEqual(result['effective_steps'], 5)
        self.assertFalse(result['short_flow'])
        self.assertEqual(result['collection_ending']['kind'], 'AGENT_STOP')
        self.assertEqual(result['collection_ending']['verified_effective_steps'], 5)
        self.assertEqual([a for a, _ in self.surface.executed],
                         ['scroll', 'scroll', 'click', 'scroll', 'back'])

    async def test_direct_article_prompt_still_forbids_search_and_requires_back(self):
        from webcollect.direct_article import VERSION as DIRECT_VERSION
        from webcollect.planning import object_sha256
        task = self.reading_task()
        spec = task['workflow_proposal']['spec']
        spec['goal']['structured']['evidence_contract'] = {
            'version': DIRECT_VERSION, 'kind': 'reading', 'entry_url': ARTICLE, 'titles': [SUBJECT]}
        task['task_id'] = 'react-' + object_sha256({'url': spec.get('entry_url'), 'spec': spec})[:24]
        prompt = system_for(task)
        self.assertIn('不使用站内检索', prompt)
        self.assertIn('离开原词条后下一业务动作必须back', prompt)
        # The general-protocol prompt keeps the new type/submit and path-family semantics.
        general = system_for(self.reading_task())
        self.assertIn('聚焦后的type只证明输入框值', general)
        self.assertIn('不强制跨页', general)


class ZeroEffectCounterexampleTests(PathHarness):
    async def test_found_scroll_without_movement_is_zero_effective(self):
        steps = list(SEARCH_OPEN) + [
            {'action': 'click', 'target': {'text': '基本现象词条'},
             'purpose': '打开无滚动空间的结果页', 'expected': {'kind': 'document_changed', 'text': '基本现象词条'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '声称found的滚动',
             'expected': {'kind': 'scroll_changed'}},
        ]
        session, evidence = self.scripted('nomove', lambda p: self.plan_with(p, steps),
                                          ['continue', 'stop'])
        result = await session.run()
        # The scroll dispatched but the position never moved: 0 effective steps
        # for it, and the sample honestly records the known no-effect tail.
        self.assertEqual(result['effective_steps'], 4)
        self.assertEqual(result['collection_ending']['kind'], 'KNOWN_NO_EFFECT')
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        self.assertFalse(terminal['goal_evidence']['session_objective']['downward_reading'])

    async def test_mechanical_same_link_repeat_gains_no_new_reading_credit(self):
        steps = [
            {'action': 'click', 'target': {'text': '搜索', 'role': 'textbox'},
             'purpose': '聚焦站内搜索框', 'expected': {'kind': 'focused', 'text': '搜索'}},
            {'action': 'type', 'target': {'text': '搜索', 'role': 'textbox'}, 'value': SUBJECT,
             'purpose': '输入检索词', 'expected': {'kind': 'value', 'text': SUBJECT}},
            {'action': 'click', 'target': {'text': '搜索', 'role': 'button'},
             'purpose': '提交站内检索直达条目', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读正文',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'click', 'target': {'text': '日食'}, 'purpose': '重复查阅同一链接',
             'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'back', 'purpose': '返回', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'click', 'target': {'text': '日食'}, 'purpose': '再次机械重复同一链接',
             'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'back', 'purpose': '返回', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
        ]
        session, evidence = self.scripted('repeat', lambda p: self.plan_with(p, steps),
                                          ['continue', 'stop'])
        result = await session.run()
        # The repeat actions are real and count as steps; reading credit stays
        # tied to the actually read segments, never to repeat visits.
        self.assertEqual(result['effective_steps'], 8)
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        objective = terminal['goal_evidence']['session_objective']
        self.assertEqual(len(objective['downward_reading']), 1)

    async def test_wrong_result_open_does_not_verify(self):
        steps = list(SEARCH_OPEN) + [
            {'action': 'click', 'target': {'text': '月食的基本现象'},
             'purpose': '打开错误词条', 'expected': {'kind': 'document_changed', 'text': '基本现象词条'}},
            {'action': 'back', 'purpose': '返回', 'expected': {'kind': 'document_changed', 'text': SUBJECT}},
        ]
        session, evidence = self.scripted('wrongback', lambda p: self.plan_with(p, steps),
                                          ['continue', 'stop'])
        result = await session.run()
        terminal = load_json(evidence / 'raw' / 'terminal.json')
        objective = terminal['goal_evidence']['session_objective']
        self.assertNotEqual(objective['status'], 'VERIFIED')
        self.assertFalse(objective['opened_results'])


INDEX_HTML = '''<!doctype html><meta charset="utf-8"><title>站内检索</title><style>
body{margin:0;font:16px Arial;background:white;color:black}
#head{position:absolute;left:260px;top:10px;width:505px}
#q{width:440px;height:42px;font:16px Arial}
#btn{margin-left:8px;height:42px}
#menu{position:absolute;left:265px;top:56px;width:448px;background:#fff;border:1px solid #a2a9b1;display:none}
#menu.open{display:block}
#menu li{list-style:none;padding:8px 10px;border-bottom:1px solid #eaecf0;cursor:pointer}
#siteNotice{position:absolute;left:44px;top:90px;width:660px;height:30px;background:#fef6e7;border:1px solid #eadcbc}
main{position:absolute;left:60px;top:140px;max-width:1100px}
a{color:#36c}
</style><div id="head"><form id="f" onsubmit="return go()"><input id="q" type="search" role="combobox"
aria-owns="lb" aria-expanded="false" aria-autocomplete="list" placeholder="搜索维基百科" autocomplete="off">
<button id="btn" type="button" onclick="go()">搜索</button></form></div>
<div id="menu"><ul id="lb" role="listbox" aria-label="搜索结果"></ul></div>
<div id="siteNotice">本地公告甲</div>
<main><p>本地受控检索入口。</p></main>
<script>
const ITEMS=['月食','月食的过程','月食观测','月食的历史','月食记录'];
let tick=0,churn=0;
const q=document.getElementById('q'),menu=document.getElementById('menu'),
lb=document.getElementById('lb'),notice=document.getElementById('siteNotice');
function render(){lb.innerHTML='';for(let i=0;i<3;i++){const li=document.createElement('li');
li.setAttribute('role','option');const a=document.createElement('a');
a.href='/wiki/'+encodeURIComponent(ITEMS[(tick+i)%ITEMS.length]);
a.textContent=ITEMS[(tick+i)%ITEMS.length];li.appendChild(a);lb.appendChild(li);}}
q.addEventListener('focus',()=>{menu.classList.add('open');q.setAttribute('aria-expanded','true');
const iv=setInterval(()=>{if(churn++>=200){clearInterval(iv);return;}tick++;render();},400);});
function go(){location.href='/search?q='+encodeURIComponent(q.value||'月食');return false;}
const NOTICES=['交流群甲欢迎大家加入。','交流群乙请大家一同关注。','频道丙已经正式上线。'];
setInterval(()=>{notice.textContent=NOTICES[Math.floor(Date.now()/900)%3];},900);
</script>'''

SEARCH_HTML = '''<!doctype html><meta charset="utf-8"><title>检索结果</title><style>
body{margin:0;font:16px Arial}main{position:absolute;left:60px;top:40px}a{color:#36c}
</style><main><h1>检索结果</h1><p><a id="r1" href="/wiki/%E6%9C%88%E9%A3%9F">月食</a></p></main>'''

ARTICLE_HTML = '''<!doctype html><meta charset="utf-8"><title>月食</title><style>
body{margin:0;font:16px Arial}main{margin-left:60px}section{height:480px;border-bottom:1px solid #ddd}a{color:#36c}
</style><main><h1>月食</h1>
<section id="s1"><p>月食是当地球位于太阳与月球之间、月球进入地球阴影时出现的现象。</p></section>
<section id="s2"><p>月食发生时，太阳、地球与月球几乎排成同一条直线。</p></section>
<section id="s3"><p>发生月食时，地球位于太阳与月球之间，月球进入地球的本影，因此只能出现在满月之夜。</p>
<p>相关条目：<a id="rel" href="/wiki/%E6%97%A5%E9%A3%9F">日食</a></p></section>
<section id="s4"><p>观测记录与历史记载。</p></section></main>'''

RELATED_HTML = '''<!doctype html><meta charset="utf-8"><title>日食</title><style>
body{margin:0;font:16px Arial}main{margin-left:60px}section{height:480px}a{color:#36c}
</style><main><h1>日食</h1><section><p>日食是月球运行到太阳与地球之间的现象，与月食位置关系相反。</p></section>
<section><p>更多日食细节。</p></section></main>'''


def route_local(url):
    from urllib.parse import unquote
    path = url.split('local.test', 1)[-1].split('?')[0]
    if path.startswith('/wiki/'):
        return RELATED_HTML if unquote(path[6:]) == '日食' else ARTICLE_HTML
    if path.startswith('/search'):
        return SEARCH_HTML
    return INDEX_HTML


class RealChromiumLocalSite(unittest.IsolatedAsyncioTestCase):
    """Real browser, local route: the exact pre-dispatch evidence chain."""

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

    async def test_type_step_pre_dispatch_evidence_survives_churning_overlay(self):
        from webcollect import browser
        from webcollect.collect import capture_before_action
        from webcollect.action_stability import action_scoped_scope
        from webcollect.dynamic_regions import regions as allowed_regions
        await self.page.goto('https://local.test/home', wait_until='domcontentloaded')
        await self.page.wait_for_timeout(400)
        box = await self.page.locator('#q').bounding_box()
        await self.page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        await self.page.wait_for_timeout(1200)  # overlay open; churn interval keeps running
        probe = await browser.observe(self.page, self.INPUT_SELECTOR)
        categories = [r['category'] for r in probe['dynamic_region_contract']['regions']
                      if r.get('eligible') is True]
        self.assertIn('search_suggestions', categories, probe['dynamic_region_contract']['regions'])
        self.assertIn('announcement', categories)
        scope = action_scoped_scope(probe, probe['target']['element_id'], 'type')
        with TemporaryDirectory() as tmp:
            observation = await capture_before_action(self.page, Path(tmp), self.INPUT_SELECTOR,
                                                      timeout=30, action_scope=scope)
        self.assertTrue(observation['action_state_preflight']['matched'])
        self.assertEqual(observation['action_refresh']['stage'], 'complete')

    async def test_real_scroll_click_back_with_identity_and_new_body(self):
        from webcollect import browser
        await self.page.goto('https://local.test/wiki/%E6%9C%88%E9%A3%9F', wait_until='domcontentloaded')
        await self.page.wait_for_timeout(300)
        entry = await browser.observe(self.page)
        await browser.execute(self.page, 'scroll', {'direction': 'down', 'x': 640, 'y': 360}, {})
        first = await browser.observe(self.page)
        self.assertGreater(first['scroll'][1], entry['scroll'][1])
        self.assertTrue(any('几乎排成同一条直线' in (e.get('text') or '')
                            for e in first['elements'] if e.get('visible')))
        await browser.execute(self.page, 'scroll', {'direction': 'down', 'x': 640, 'y': 360}, {})
        second = await browser.observe(self.page)
        self.assertGreater(second['scroll'][1], first['scroll'][1])
        self.assertTrue(any('地球位于太阳与月球之间' in (e.get('text') or '')
                            for e in second['elements'] if e.get('visible')))
        link = next(e for e in second['elements']
                    if e.get('text') == '日食' and e.get('clickable') and e.get('visible'))
        await browser.execute(self.page, 'click',
                              {'x': (link['bbox'][0] + link['bbox'][2]) / 2,
                               'y': (link['bbox'][1] + link['bbox'][3]) / 2},
                              {'wait_navigation': True})
        related = await browser.observe(self.page)
        self.assertIn('日食', related['title'])
        self.assertNotEqual(related['document_identity'], entry['document_identity'])
        self.assertTrue(any('位置关系相反' in (e.get('text') or '')
                            for e in related['elements'] if e.get('visible')))
        await browser.execute(self.page, 'back', {}, {'wait_navigation': True})
        returned = await browser.observe(self.page)
        # A real back may create a fresh document (new time origin) and may or
        # may not restore the scroll offset; identity is the restored URL,
        # title and the article's own visible body, not the origin counter.
        self.assertEqual(returned['url'], entry['url'])
        self.assertEqual(returned['title'], entry['title'])
        phrases = ('月食是当地球位于太阳与月球之间', '几乎排成同一条直线', '因此只能出现在满月之夜')
        self.assertTrue(any(phrase in (e.get('text') or '')
                            for e in returned['elements'] if e.get('visible')
                            for phrase in phrases))


if __name__ == '__main__':
    unittest.main()
