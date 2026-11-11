"""React session protocol simulations. No browser, site, model or QC service.

Covers the A01-A15 engineering matrix from the 2026-10-31 agent redesign:
single-session ReAct loop, four host tools, goal rules, staged errors, raw
journal first, offline whole-trajectory derivation and the unified duplicate
verdicts. All pages/captures are synthetic fixtures.
"""
import asyncio
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import socket
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image
from test_planner_repair import SemanticFixture
from webcollect.batch_core import load_json, file_sha
from webcollect.react_session import (ReactSession, ReactStop, SYSTEM_PROMPT, GOAL_BUDGETS,
    build_url_task, validate_task, tool_definitions)
import webcollect.browser
import webcollect.collect


def make_png(token):
    stream = BytesIO()
    Image.new('RGB', (1280, 720), ((token >> 16) & 255, (token >> 8) & 255, token & 255)).save(stream, 'PNG')
    return stream.getvalue()


class ReactSurface:
    """Synthetic page: same trusted-capture shape as the agent-loop fixtures."""

    def __init__(self, state):
        self.state = deepcopy(state)
        self.state.update(document_identity={'url_without_fragment': self.state['url'],
                                             'performance_time_origin': 123},
                          scroll=[0, 0], screen_resolution=[1280, 720], target=None,
                          title='受控输入页面')
        self.state['visible_text'] = '受控输入页面\n数量\n单价\n这里查看当前输入内容与页面状态。'
        for i, row in enumerate(self.state['elements']):
            row.update(bbox=[10, 20 + i * 60, 210, 60 + i * 60], enabled=True, visible=True,
                       element_type='input' if i < 2 else 'text', state='default', parent_id='root',
                       native_role='input' if i < 2 else 'p', scrollable=False)
        for value in self.state['values']:
            value.update(selection_start=0, selection_end=0, input_type='text', value_visible=True)
        self.readable = True
        self.executed = []
        self.history = [self.state['url']]

    async def capture(self, page, selector=None, index=0, **kw):
        state = deepcopy(self.state)
        state['visible_text'] += '\n' + '\n'.join(e.get('text', '') for e in state['elements'])
        for value in state['values']:
            value['display_value'] = value['value']
        binding = next((b for b in state['capture_controls'] if b['selector'] == selector), None)
        if binding:
            eid = binding['element_id']
            row = next(e for e in state['elements'] if e['element_id'] == eid)
            value = next((v for v in state['values'] if v['element_id'] == eid), {})
            label = value.get('value') or '请输入数量'
            state['target'] = {'element_id': eid, 'coordinate': [30, row['bbox'][1] + 10],
                'hit_valid': True, 'focused': value.get('focused', False),
                'value': value.get('value'),
                'visible_label_evidence': [{'kind': 'visible_native_value' if value.get('value')
                                            else 'visible_placeholder', 'text': label}]}
        else:
            state['target'] = None
        token = int(hashlib.sha256(json.dumps({k: self.state.get(k) for k in
            ('url', 'values', 'scroll', 'document_identity')}, sort_keys=True, default=str).encode()).hexdigest()[:6], 16)
        png = make_png(token)
        from webcollect.browser import fingerprint
        attempt = {'dom_stable': True, 'before_fingerprint': fingerprint(state),
                   'after_fingerprint': fingerprint(state),
                   'started_ns': time.time_ns(), 'ended_ns': time.time_ns()}
        return {'state': state, 'png': png, 'capture': {'snapshot_source': 'browser_dom',
            'screenshot_sha256': hashlib.sha256(png).hexdigest(),
            'coordinate_space': 'screenshot_css_pixels', 'attempts': [attempt]}}

    def execute_action(self, action_type, arguments):
        self.executed.append((action_type, deepcopy(arguments)))
        values = self.state['values']
        if action_type == 'click':
            x, y = arguments['x'], arguments['y']
            target = None
            for value in values:
                row = next(e for e in self.state['elements'] if e['element_id'] == value['element_id'])
                box = row['bbox']
                target = value if box[0] <= x < box[2] and box[1] <= y < box[3] else target
            for value in values:
                value['focused'] = value is target
        elif action_type == 'hotkey':
            value = next(v for v in values if v['focused'])
            keys = arguments['keys']
            if keys == ['meta', 'a']:
                value.update(selection_start=0, selection_end=len(value['value']))
            elif keys == ['backspace']:
                value.update(value='', selection_start=0, selection_end=0)
        elif action_type == 'type':
            value = next(v for v in values if v['focused'])
            value['value'] = arguments['text']
            value.update(selection_start=len(arguments['text']), selection_end=len(arguments['text']))
        elif action_type == 'scroll':
            self.state['scroll'][1] += 480
        elif action_type == 'open_url':
            self.state['url'] = arguments['url']
            self.state['document_identity']['performance_time_origin'] += 1
            self.history.append(self.state['url'])
        elif action_type == 'back':
            if len(self.history) > 1:
                self.history.pop()
                self.state['url'] = self.history[-1]
                self.state['document_identity']['performance_time_origin'] += 1


class FakePage:
    def __init__(self, surface):
        self.surface = surface
        self.context = type('Ctx', (), {'pages': []})()
        self.context.pages = [self]

    @property
    def url(self):
        return self.surface.state['url']

    async def goto(self, url, **kw):
        self.surface.state['url'] = url

    async def wait_for_timeout(self, ms):
        pass

    async def wait_for_load_state(self, *a, **k):
        pass

    async def content(self):
        return '<html><body>' + self.surface.state['visible_text'] + '</body></html>'

    def on(self, event, cb):
        pass

    def set_default_timeout(self, ms):
        pass


def decide(*, goal=None, summary='继续当前目标', tool='observe', arguments=None):
    """Build a protocol decision against the prompt's current observation."""
    def build(prompt):
        return {'goal_update': ({'description': goal, 'reason': '基于当前实际观察',
                                 'basis_observation_id': prompt['observation']['observation_id']}
                                if goal else None),
                'decision_summary': summary,
                'tool_call': {'name': tool,
                              'arguments': (arguments(prompt) if callable(arguments) else arguments)}}
    return build


def act_step(action, *, control_id=None, value=None, keys=None, direction=None, page_id=None,
             goal='修改当前字段', expected='显示新的输入值'):
    step = {'action': action, 'goal': goal, 'expected': expected}
    for key, item in (('control_id', control_id), ('value', value), ('keys', keys),
                      ('direction', direction), ('page_id', page_id)):
        if item is not None:
            step[key] = item
    return step


class Script:
    def __init__(self, builds, after=None):
        self.builds = list(builds)
        self.after = after
        self.prompts = []
        self.n = 0

    async def __call__(self, prompt):
        self.prompts.append(deepcopy(prompt))
        self.n += 1
        if not self.builds:
            raise AssertionError('model asked for another decision beyond the script')
        build = self.builds.pop(0)
        decision = build(prompt)
        if self.after:
            self.after(self.n, prompt)
        # The current decision protocol is the native tool-call wire; synthetic
        # replies get a fresh call id like the real provider does.
        if isinstance(decision, dict) and 'tool_call' in decision and 'tool_call_id' not in decision:
            tool_call = decision['tool_call']
            extra = {k: v for k, v in tool_call['arguments'].items()
                     if k not in ('short_flow', 'short_flow_reason') and v is not None}
            tool_call = {**tool_call, 'arguments': extra}
            arguments = {**{'goal_update': decision.get('goal_update'),
                            'decision_summary': decision.get('decision_summary'),
                            'task_intent': {'status': 'UNKNOWN', 'task_types': [],
                                            'basis_observation_id': prompt['observation']['observation_id'],
                                            'visible_end_condition': '页面当前状态', 'basis': '当前观察'},
                            **({'evidence_refs': [prompt['observation']['observation_id']]}
                               if tool_call['name'] == 'finish' else {})},
                         **tool_call['arguments']}
            decision = {**decision, 'tool_call_id': 'call-%03d' % self.n,
                        'assistant_message': {'role': 'assistant',
                                              'tool_calls': [{'id': 'call-%03d' % self.n, 'type': 'function',
                                                              'function': {'name': tool_call['name'],
                                                                           'arguments': json.dumps(arguments, ensure_ascii=False)}}]},
                        'user_message': {'role': 'user', 'content': 'tool result'},
                        'name': tool_call['name'],
                        'arguments': arguments}
        return decision


class ReactHarness(SemanticFixture):
    def setUp(self):
        super().setUp()
        self.network = patch.object(socket.socket, 'connect',
                                    side_effect=AssertionError('external IO forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        record, _ = self.semantic()
        state = load_json(record['capabilities'][0]['page_anchor']['state']['path'])
        self.surface = ReactSurface(state)
        self.page = FakePage(self.surface)
        self.task = build_url_task(url=self.surface.state['url'], task_version='fixture',
                                   )
        for name, target in (('webcollect.browser.capture', self.surface.capture),):
            p = patch(target if False else name, side_effect=target)
            p.start()
            self.addCleanup(p.stop)
        execute_patch = patch('webcollect.browser.execute', side_effect=self._fake_execute)
        execute_patch.start()
        self.addCleanup(execute_patch.stop)
        verify_patch = patch('webcollect.browser.verify_execution_state', side_effect=self._fake_verify)
        verify_patch.start()
        self.addCleanup(verify_patch.stop)
        before_patch = patch('webcollect.collect.capture_before_action', side_effect=self._fake_before)
        before_patch.start()
        self.addCleanup(before_patch.stop)

    async def _fake_execute(self, page, action_type, arguments, execution):
        self.surface.execute_action(action_type, arguments)

    async def _fake_verify(self, page, state, selector=None, index=0, **kw):
        return {'matched': True, 'state_fingerprint': hashlib.sha256(
            json.dumps({'url': state['url'], 'identity': state.get('document_identity')},
                       sort_keys=True, default=str).encode()).hexdigest()}

    async def _fake_before(self, page, evidence, selector=None, index=0, **kw):
        observation = await self.surface.capture(page, selector, index)
        if kw.get('include_html'):
            observation['html'] = await page.content()
        return observation

    def session(self, script, name='session', **kw):
        return ReactSession(self.task, self.root / name, script, self.page, **kw)


class ReactSessionTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    async def test_a01_url_only_goal_established_in_loop_and_act_gated(self):
        """URL-only: working_goal starts null; act before a goal is rejected;
        goal_update + act can land in the same round; requested_goal stays null."""
        script = Script([
            decide(tool='act', arguments=lambda p: {'observation_id': p['observation']['observation_id'],
                                                    'step': act_step('set_value', control_id='control-0', value='20')}),
            decide(goal='修改数量字段并查看输入状态', tool='observe', arguments={'focus_control_id': 'control-0'}),
            lambda p: {'goal_update': {'description': '修改数量字段并查看输入状态',
                                        'basis_observation_id': p['observation']['observation_id'],
                                        'reason': '页面提供数量与单价输入框'},
                       'decision_summary': '已建立目标，直接修改数量',
                       'tool_call': {'name': 'act', 'arguments': {
                           'observation_id': p['observation']['observation_id'],
                           'step': act_step('set_value', control_id='control-0', value='20')}}},
            decide(tool='finish', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'], 'stop_reason': 'ready',
                'summary': '已完成数量修改并查看状态', 'short_flow': False, 'short_flow_reason': None}),
            decide(tool='finish', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'], 'stop_reason': 'no_path',
                'summary': '如实结束', 'short_flow': False, 'short_flow_reason': None}),
        ])
        session = self.session(script)
        summary = await session.run()
        self.assertEqual(session.requested_goal, None)
        self.assertEqual(session.working_goal, '修改数量字段并查看输入状态')
        first_act = [load_json(e['path']) for e in session.events
                     if Path(e['path']).name.split('-', 1)[1].startswith('tool-result')][0]
        self.assertEqual(first_act['result']['status'], 'rejected')
        self.assertIn('工作目标', first_act['result']['summary'])
        # A 1-4 step ready claim is internal-only under the goal-completion rule;
        # the honest close then ends the session.
        self.assertIn(summary['stop_reason'], ('blocked', 'no_path'))
        self.assertEqual(summary['effective_steps'], 3)  # click + select-all + type

    async def test_a04_a12_tool_definitions_in_prompt_and_fabricated_result_rejected(self):
        script = Script([
            lambda p: {'goal_update': None, 'decision_summary': 'x',
                       'tool_call': {'name': 'inspect', 'arguments': {
                           'kind': 'html', 'observation_id': p['observation']['observation_id'],
                           'target_id': None, 'query': None, 'offset': 0, 'limit_chars': 200,
                           'fabricated_observation': {'observation_id': 'fake'}}}},
            lambda p: {'goal_update': None, 'decision_summary': 'x',
                       'tool_call': {'name': 'dream', 'arguments': {}}},
            decide(tool='finish', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'], 'stop_reason': 'no_path',
                'summary': '没有可行路径', 'short_flow': False, 'short_flow_reason': None}),
        ])
        session = self.session(script)
        summary = await session.run()
        prompt = script.prompts[0]
        tool_names = {t['function']['name'] for t in prompt['tools']}
        self.assertIn('observe', tool_names)
        self.assertEqual(tool_names, {'observe', 'inspect', 'act', 'finish'})
        self.assertIn('working_goal', prompt['system'])
        self.assertEqual(prompt['requested_goal'], None)
        events = [load_json(e['path']) for e in session.events]
        rejected = [e for e in events if e['kind'] == 'decision-rejected']
        self.assertEqual(len(rejected), 2)
        self.assertEqual(session.trajectory, [])
        self.assertEqual(summary['stop_reason'], 'no_path')

    async def test_a04_old_observation_cannot_act(self):
        script = Script([
            decide(tool='observe', arguments={'focus_control_id': 'control-0'}),
            lambda p: {'goal_update': {'description': '修改数量',
                                        'basis_observation_id': p['observation']['observation_id'],
                                        'reason': '输入框可用'},
                       'decision_summary': '用旧观察提交动作',
                       'tool_call': {'name': 'act', 'arguments': {
                           'observation_id': script_first_observation(p),
                           'step': act_step('set_value', control_id='control-0', value='20')}}},
            decide(tool='finish', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'], 'stop_reason': 'blocked',
                'summary': '绑定失效', 'short_flow': False, 'short_flow_reason': None}),
        ])
        session = self.session(script)
        summary = await session.run()
        results = [load_json(e['path'])['result'] for e in session.events if load_json(e['path'])['kind'] == 'tool-result']
        self.assertTrue(any(r['status'] == 'need_observation' and r['tool'] == 'act' for r in results))
        self.assertEqual(summary['effective_steps'], 0)
        self.assertEqual(self.surface.executed, [])

    async def test_a04_back_needs_no_page_id_and_requires_navigation(self):
        from webcollect.agent_controller import compile_step as controller_compile
        observation = None
        script = Script([
            decide(tool='observe', arguments={'focus_control_id': 'control-0'}),
            lambda p: {'goal_update': {'description': '跳转后返回',
                                        'basis_observation_id': p['observation']['observation_id'],
                                        'reason': '需要验证返回'},
                       'decision_summary': 'open_url 到观察页',
                       'tool_call': {'name': 'act', 'arguments': {
                           'observation_id': p['observation']['observation_id'],
                           'step': act_step('open_url', page_id='p0', goal='打开页面', expected='页面打开')}}},
            lambda p: {'goal_update': None, 'decision_summary': '返回上一页',
                       'tool_call': {'name': 'act', 'arguments': {
                           'observation_id': p['observation']['observation_id'],
                           'step': act_step('back', goal='返回上一页', expected='回到上一页面')}}},
            decide(tool='finish', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'], 'stop_reason': 'ready',
                'summary': '完成导航与返回', 'short_flow': True,
                'short_flow_reason': '受控页面只有导航路径，无法形成5个有效操作'}),
        ])
        session = self.session(script)
        summary = await session.run()
        # open_url to the same URL has no effect -> session stops honestly.
        self.assertIn(summary['stop_reason'], ('blocked', 'ready'))
        # Direct compile-level contract: back without page_id, no navigation -> INSUFFICIENT.
        state = load_json(session.observation_records[session.observations[0]]['evidence']['state']['path'])
        from webcollect.agent_observation import project
        observation = project(state, session.observation_records[session.observations[0]]['evidence'])
        with self.assertRaisesRegex(ValueError, 'INSUFFICIENT'):
            controller_compile(self.task, ['https://example.org/'], act_step('back'), observation, 0)
        controller_compile(self.task, ['https://example.org/', 'https://example.org/x'],
                           act_step('back'), observation, 1)
        with self.assertRaisesRegex(ValueError, 'page_id'):
            controller_compile(self.task, ['https://example.org/'],
                               act_step('back', page_id='p0'), observation, 1)

    async def test_a05_five_steps_finish_without_goal_proof_is_not_formal_sample(self):
        """Six and nine effective actions are not cut at 8/10, but length alone
        cannot create a formal sample without original-goal completion proof."""
        # 2026-10-31 user cap: a react run is bounded at ten model/tool rounds;
        # nine effective actions still proves no artificial stop at 8.
        for total, label in ((6, 'five'), (9, 'nine')):
            for value in self.surface.state['values']:
                value.update(value='10', focused=False, selection_start=0, selection_end=0)
            semantic = (total + 2) // 3  # each set_value = click + select-all + type
            builds = []
            counter = [0]
            which = ['control-0', 'control-1']
            for round_index in range(semantic):
                cid = which[round_index % 2]
                builds.append(decide(tool='observe', arguments={'focus_control_id': cid}))
                if round_index == 0:
                    def first_goal(prompt, cid=cid):
                        return {'goal_update': {'description': '依次修改两个输入字段',
                                'basis_observation_id': prompt['observation']['observation_id'],
                                'reason': '输入框可用'},
                            'decision_summary': '开始修改',
                            'tool_call': {'name': 'act', 'arguments': {
                                'observation_id': prompt['observation']['observation_id'],
                                'step': act_step('set_value', control_id=cid, value='20')}}}
                    builds.append(first_goal)
                    continue
                def next_act(prompt, cid=cid):
                    counter[0] += 1
                    return {'observation_id': prompt['observation']['observation_id'],
                            'step': act_step('set_value', control_id=cid,
                                             value=str(20 + counter[0]))}
                builds.append(decide(tool='act', arguments=next_act))
            builds.append(decide(tool='finish', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'], 'stop_reason': 'ready',
                'summary': '完成连续输入操作并查看状态', 'short_flow': False,
                'short_flow_reason': None}))
            script = Script(builds)
            name = f'session-{label}'
            evidence = self.root / name / 'evidence' / 'S000001_sample_000001'
            session = ReactSession(self.task, evidence / 'raw', script, self.page,
                                   steps_directory=evidence)
            summary = await session.run()
            self.assertEqual(summary['stop_reason'], 'ready', label)
            self.assertEqual(summary['effective_steps'], total, label)
            from webcollect.postprocess import process
            manifest = {'batch_id': 'B20261031_001', 'sample_kind': 'real', 'program_version': 't',
                        'rule_version': '1.0.0',
                        'sites': [{'site_id': 'S000001', 'uri': self.task['site_uri'],
                                   'site_category': self.task['site_category']}],
                        'samples': ['S000001_sample_000001']}
            derived = process(evidence, self.root / name / 'samples' / 'S000001_sample_000001',
                              {'sample_id': 'S000001_sample_000001', 'site_id': 'S000001', 'batch_id': 'B20261031_001',
                               'attempt_id': 'attempt-fixture'}, manifest)
            self.assertEqual(derived['status'], 'completion_unqualified', label + ' :: ' + str(derived)[:300])
            self.assertEqual(derived['effective_steps'], total, label)
            destination = self.root / name / 'samples' / 'S000001_sample_000001'
            self.assertFalse((destination / 'annotation.json').exists())
            self.assertFalse((evidence / 'saved_sample.json').exists())
            self.assertEqual(summary['strategy_result']['goal']['goal_status'], 'unconfirmed')

    async def test_a10_short_flow_rules(self):
        def finish_call(reason=None, short=False):
            return lambda p: {'observation_id': p['observation']['observation_id'],
                              'stop_reason': 'ready', 'summary': '短路径结束',
                              'short_flow': short, 'short_flow_reason': reason}
        # <5 with a ready claim: rejected; a 1-4 step trajectory is internal-only.
        script = Script([decide(goal='短路径', tool='observe', arguments={'focus_control_id': 'control-0'}),
                         lambda p: {'goal_update': {'description': '短路径',
                                                     'basis_observation_id': p['observation']['observation_id'],
                                                     'reason': '页面简单'},
                                    'decision_summary': '一次输入后结束',
                                    'tool_call': {'name': 'act', 'arguments': {
                                        'observation_id': p['observation']['observation_id'],
                                        'step': act_step('set_value', control_id='control-0', value='20')}}},
                         decide(tool='finish', arguments=finish_call()),
                         decide(tool='finish', arguments=lambda p: {
                             'observation_id': p['observation']['observation_id'],
                             'stop_reason': 'no_path', 'summary': '路径不足，如实结束',
                             'short_flow': False, 'short_flow_reason': None})])
        evidence = self.root / 'sf1' / 'evidence'
        session = ReactSession(self.task, evidence / 'raw', script, self.page,
                               steps_directory=evidence)
        summary = await session.run()
        # The 1-4 step ready finish was rejected (internal-only), then the model
        # closed honestly; the trajectory itself carries the rejection receipt.
        self.assertIn(summary['stop_reason'], ('blocked', 'no_path'))
        from webcollect.postprocess import process
        manifest = {'batch_id': 'B20261031_001', 'sample_kind': 'real', 'program_version': 't',
                    'rule_version': '1.0.0',
                    'sites': [{'site_id': 'S000001', 'uri': self.task['site_uri'],
                               'site_category': self.task['site_category']}], 'samples': ['S000001_sample_000001']}
        derived = process(evidence, self.root / 'sf1' / 'S000001_sample_000001',
                          {'sample_id': 'S000001_sample_000001', 'site_id': 'S000001', 'batch_id': 'B20261031_001',
                           'attempt_id': 'attempt-fixture'}, manifest)
        # A 1-4 step honest close stays internal: flagged/raw-only, no formal sample.
        self.assertIn(derived['status'], ('processing_failed', 'raw_only'))
        # Model-declared short_flow fields are ignored; the host derives both
        # the flag and optional reason from actual effective actions. Zero
        # actions are not a sample and therefore are not labelled short_flow.
        script2 = Script([decide(goal='短路径', tool='finish', arguments=finish_call(None, True)),
                          decide(tool='finish', arguments=lambda p: {
                              'observation_id': p['observation']['observation_id'],
                              'stop_reason': 'blocked', 'summary': '结束',
                              'short_flow': False, 'short_flow_reason': None})])
        session2 = ReactSession(self.task, self.root / 'sf2', script2, self.page)
        summary2 = await session2.run()
        results = [load_json(e['path'])['result'] for e in session2.events if load_json(e['path'])['kind'] == 'tool-result']
        finish_results = [r for r in results if r['tool'] == 'finish']
        # A zero-action ready claim is rejected under the goal-completion rule;
        # the honest blocked close then succeeds and keeps no short_flow label.
        self.assertEqual(len(finish_results), 2)
        self.assertEqual(finish_results[0]['status'], 'rejected')
        self.assertEqual(finish_results[1]['status'], 'ok')
        self.assertEqual(summary2['effective_steps'], 0)
        self.assertFalse(summary2['short_flow'])
        self.assertIsNone(summary2['short_flow_reason'])

    async def test_a07_pre_dispatch_stale_is_zero_dispatch(self):
        script = Script([
            decide(tool='observe', arguments={'focus_control_id': 'control-0'}),
            lambda p: {'goal_update': {'description': '修改数量',
                                        'basis_observation_id': p['observation']['observation_id'],
                                        'reason': '输入框可用'},
                       'decision_summary': '提交动作',
                       'tool_call': {'name': 'act', 'arguments': {
                           'observation_id': p['observation']['observation_id'],
                           'step': act_step('set_value', control_id='control-0', value='20')}}},
            decide(tool='finish', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'], 'stop_reason': 'blocked',
                'summary': '状态过期后结束', 'short_flow': True,
                'short_flow_reason': '页面状态在派发前变化，无法继续'}),
        ])
        # After the act decision returns, mutate the page before dispatch.
        def mutate(round_number, prompt):
            if round_number == 2:  # the act round: mutate before dispatch
                self.surface.state['scroll'] = [0, 120]
        script.after = mutate
        session = ReactSession(self.task, self.root / 'stale', script, self.page)
        summary = await session.run()
        results = [load_json(e['path'])['result'] for e in session.events if load_json(e['path'])['kind'] == 'tool-result']
        stale = [r for r in results if r['status'] == 'need_observation']
        self.assertTrue(stale)
        self.assertEqual(self.surface.executed, [])  # zero dispatch
        self.assertEqual(summary['effective_steps'], 0)

    async def test_a07_post_dispatch_unknown_kept_not_resent(self):
        execute_patch = patch('webcollect.browser.execute',
                              side_effect=RuntimeError('transport lost after dispatch'))
        execute_patch.start()
        self.addCleanup(execute_patch.stop)
        script = Script([
            decide(tool='observe', arguments={'focus_control_id': 'control-0'}),
            lambda p: {'goal_update': {'description': '修改数量',
                                        'basis_observation_id': p['observation']['observation_id'],
                                        'reason': '输入框可用'},
                       'decision_summary': '提交动作',
                       'tool_call': {'name': 'act', 'arguments': {
                           'observation_id': p['observation']['observation_id'],
                           'step': act_step('set_value', control_id='control-0', value='20')}}},
        ])
        session = ReactSession(self.task, self.root / 'unknown', script, self.page)
        summary = await session.run()
        self.assertTrue(summary['unknown'])
        self.assertEqual(summary['failure_class'], 'interrupted')
        # Exactly the two planned rounds reached the model; the post-dispatch
        # UNKNOWN round never re-asked the model for another decision.
        self.assertEqual(len(script.prompts), 2)

    async def test_a08_inspect_bounded_windows_and_context_images_not_attached(self):
        script = Script([
            lambda p: {'goal_update': None, 'decision_summary': '查询HTML片段',
                       'tool_call': {'name': 'inspect', 'arguments': {
                           'kind': 'html', 'observation_id': p['observation']['observation_id'],
                           'target_id': None, 'query': None, 'offset': 0, 'limit_chars': 50}}},
            lambda p: {'goal_update': None, 'decision_summary': '查询控件真实值',
                       'tool_call': {'name': 'inspect', 'arguments': {
                           'kind': 'control', 'observation_id': p['observation']['observation_id'],
                           'target_id': 'control-0', 'query': None, 'offset': 0, 'limit_chars': 2000}}},
            lambda p: {'goal_update': None, 'decision_summary': '查询历史',
                       'tool_call': {'name': 'inspect', 'arguments': {
                           'kind': 'history', 'observation_id': None, 'target_id': None,
                           'query': '修改', 'offset': 0, 'limit_chars': 500}}},
            decide(tool='finish', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'], 'stop_reason': 'no_path',
                'summary': '查询完成', 'short_flow': False, 'short_flow_reason': None}),
        ])
        site_context = {'actual_feedback': {'avoid': [
            {'operation': {'action_type': 'click'}, 'reason': '重复点击无变化'}] * 30}}
        session = ReactSession(self.task, self.root / 'inspect', script, self.page,
                               site_context=site_context)
        summary = await session.run()
        results = [load_json(e['path'])['result'] for e in session.events if load_json(e['path'])['kind'] == 'tool-result']
        html = next(r for r in results if r['data'].get('kind') == 'html')
        self.assertEqual(len(html['data']['content_text']), 50)
        self.assertTrue(html['data']['truncated'])
        self.assertIsNotNone(html['data']['next_offset'])
        control = next(r for r in results if r['data'].get('kind') == 'control')
        self.assertIn('"value"', control['data']['content_text'])
        # The default prompt carries bounded context: no feedback images field.
        self.assertNotIn('images', script.prompts[-1])
        self.assertEqual(len(script.prompts[-1]['recent_feedback']), 3)

    async def test_a11_common_start_frame_hint_is_not_fatal(self):
        conflicts = [{'sha256': 'deadbeef', 'other_sample_id': 'S_sample_000'}]
        def guard(ref):
            return conflicts
        script = Script([
            decide(goal='修改数量', tool='observe', arguments={'focus_control_id': 'control-0'}),
            lambda p: {'goal_update': {'description': '修改数量',
                                        'basis_observation_id': p['observation']['observation_id'],
                                        'reason': '输入框可用'},
                       'decision_summary': '提交动作',
                       'tool_call': {'name': 'act', 'arguments': {
                           'observation_id': p['observation']['observation_id'],
                           'step': act_step('set_value', control_id='control-0', value='20')}}},
            decide(tool='finish', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'], 'stop_reason': 'ready',
                'summary': '完成修改', 'short_flow': True, 'short_flow_reason': '受控页面路径有限'})])
        session = ReactSession(self.task, self.root / 'hint', script, self.page, frame_guard=guard)
        summary = await session.run()
        # The common start-frame hint stays non-fatal; the 1-4 step ready claim
        # is rejected by the goal-completion rule and the honest close follows.
        self.assertIn(summary['stop_reason'], ('blocked', 'no_path'))
        self.assertEqual(session.current.get('duplicate_hint'), conflicts)

    async def test_repeated_focus_is_rejected_and_action_reasons_reach_the_model(self):
        """Real-run v7 lesson: five identical focus probes burned the decision
        budget because the model never saw WHY a control stays INSUFFICIENT.
        One probe per control per document; reasons ride with every status.
        Real-run v9 lesson: agent observations carry the wider hard bound."""
        timeouts = []
        surface_capture = self.surface.capture
        async def recording(page, selector=None, index=0, **kw):
            timeouts.append(kw.get('timeout'))
            return await surface_capture(page, selector, index, **kw)
        with patch('webcollect.browser.capture', side_effect=recording):
            script = Script([
                decide(tool='observe', arguments={'focus_control_id': 'control-0'}),
                decide(tool='observe', arguments={'focus_control_id': 'control-0'}),
                decide(tool='finish', arguments=lambda p: {
                    'observation_id': p['observation']['observation_id'], 'stop_reason': 'no_path',
                    'summary': '重复定向观察被拒绝后结束', 'short_flow': True,
                    'short_flow_reason': '控件无渲染标签且重复探针被拒'})])
            session = self.session(script, name='focus-guard')
            summary = await session.run()
        from webcollect.react_session import REACT_OBSERVE_TIMEOUT_SECONDS
        self.assertEqual(summary['stop_reason'], 'no_path')
        self.assertTrue(timeouts and all(t == REACT_OBSERVE_TIMEOUT_SECONDS for t in timeouts), timeouts)
        records = [load_json(e['path']) for e in session.events]
        observe_results = [r['result'] for r in records
                           if r['kind'] == 'tool-result' and r['result']['tool'] == 'observe']
        self.assertEqual(observe_results[0]['status'], 'ok')
        self.assertEqual(observe_results[1]['status'], 'rejected')
        self.assertIn('重复定向观察', observe_results[1]['summary'])
        # The initial full-page observation has no probe: the model must see
        # the INSUFFICIENT reason, not a bare status string.
        first_actions = script.prompts[0]['observation']['controls']['control-0']['actions']
        self.assertTrue(all('/' in value for action, value in first_actions.items()
                            if not value.startswith('PROVEN')), first_actions)

    async def test_navigation_destroyed_context_gets_one_settled_retry(self):
        """Real-run v13 lesson: a click that navigates destroys the in-flight
        effect snapshot's evaluate context. The observation retries once on
        the settled page; the action itself is never re-executed."""
        calls = []
        surface_capture = self.surface.capture
        async def navigating(page, selector=None, index=0, **kw):
            calls.append(selector)
            # Call order to a successful act: initial observe, focused observe,
            # pre-dispatch refresh, effect observation. The navigation race
            # destroys exactly the effect snapshot's evaluate context.
            if len(calls) == 4:
                raise RuntimeError('Page.evaluate: Execution context was destroyed, '
                                   'most likely because of a navigation')
            return await surface_capture(page, selector, index, **kw)
        with patch('webcollect.browser.capture', side_effect=navigating):
            script = Script([
                decide(tool='observe', arguments={'focus_control_id': 'control-0'}),
                decide(goal='修改数量并结束', tool='act', arguments=lambda p: {
                    'observation_id': p['observation']['observation_id'],
                    'step': act_step('set_value', control_id='control-0', value='20')}),
                decide(tool='finish', arguments=lambda p: {
                    'observation_id': p['observation']['observation_id'], 'stop_reason': 'ready',
                    'summary': '完成修改', 'short_flow': False, 'short_flow_reason': None}),
                decide(tool='finish', arguments=lambda p: {
                    'observation_id': p['observation']['observation_id'], 'stop_reason': 'no_path',
                    'summary': '如实结束', 'short_flow': False, 'short_flow_reason': None})])
            session = self.session(script, name='nav-retry')
            summary = await session.run()
        # The 1-4 step ready claim is internal-only; the honest close then ends.
        self.assertIn(summary['stop_reason'], ('blocked', 'no_path'))
        self.assertEqual(summary['effective_steps'], 3)  # click + select-all + type
        self.assertGreaterEqual(len(calls), 5)  # failed effect capture plus retry
        # The navigation retry re-observed; it never re-dispatched the action.
        self.assertEqual([a for a, _ in self.surface.executed], ['click', 'hotkey', 'type'])

    async def test_a09_reprocessing_appends_without_browser(self):
        from webcollect.postprocess import process
        script = Script([
            decide(tool='observe', arguments={'focus_control_id': 'control-0'}),
            lambda p: {'goal_update': {'description': '修改数量',
                                        'basis_observation_id': p['observation']['observation_id'],
                                        'reason': '输入框可用'},
                       'decision_summary': '提交动作',
                       'tool_call': {'name': 'act', 'arguments': {
                           'observation_id': p['observation']['observation_id'],
                           'step': act_step('set_value', control_id='control-0', value='20')}}},
            decide(tool='observe', arguments={'focus_control_id': 'control-1'}),
            decide(tool='act', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'],
                'step': act_step('set_value', control_id='control-1', value='30')}),
            decide(tool='finish', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'], 'stop_reason': 'ready',
                'summary': '完成两处输入', 'short_flow': False, 'short_flow_reason': None})])
        evidence = self.root / 'rp' / 'evidence'
        session = ReactSession(self.task, evidence / 'raw', script, self.page,
                               steps_directory=evidence)
        await session.run()
        before = file_sha(evidence / 'raw' / 'boundary.json')
        manifest = {'batch_id': 'B20261031_001', 'sample_kind': 'real', 'program_version': 't',
                    'rule_version': '1.0.0',
                    'sites': [{'site_id': 'S000001', 'uri': self.task['site_uri'],
                               'site_category': self.task['site_category']}], 'samples': ['S000001_sample_000001']}
        ids = {'sample_id': 'S000001_sample_000001', 'site_id': 'S000001', 'batch_id': 'B20261031_001', 'attempt_id': 'a1'}
        validator_calls = []
        def failing(delivery_root):
            validator_calls.append(str(delivery_root))
            return ['fixture validator failure']
        destination = self.root / 'rp' / 'S000001_sample_000001'
        first = process(evidence, destination, ids, manifest, validators=(failing,))
        self.assertEqual(first['status'], 'completion_unqualified', first)
        self.assertEqual(first['browser_calls'], 0)
        self.assertEqual(first['model_calls'], 0)
        self.assertEqual(validator_calls, [])  # completion gate precedes formal validators
        self.assertEqual(before, file_sha(evidence / 'raw' / 'boundary.json'))
        # Reprocessing appends another honest negative derivation from the same
        # sealed raw; it never manufactures goal proof or invokes a browser.
        second = process(evidence, destination, ids, manifest, derivation=2)
        self.assertEqual(second['status'], 'completion_unqualified', second)
        self.assertEqual(second['derivation'], 2)
        self.assertEqual(second['browser_calls'], 0)
        self.assertEqual(second['model_calls'], 0)
        self.assertEqual(before, file_sha(evidence / 'raw' / 'boundary.json'))
        third = process(evidence, destination, ids, manifest, derivation=3)
        self.assertEqual(third['status'], 'completion_unqualified', third)
        self.assertEqual(third['derivation'], 3)
        rows = [json.loads(line) for line in (evidence / 'derivations.jsonl').read_text(encoding='utf-8').splitlines() if line]
        self.assertEqual([row['status'] for row in rows], ['completion_unqualified'] * 3)
        self.assertFalse((destination / 'annotation.json').exists())
        self.assertFalse((evidence / 'saved_sample.json').exists())

    async def test_a13_validate_task_rejects_tampering(self):
        broken = deepcopy(self.task)
        broken['fragment']['budgets']['max_actions'] = 999
        with self.assertRaises(ValueError):
            validate_task(broken)
        swapped = deepcopy(self.task)
        swapped['fragment']['allowed_actions'] = ['click', 'warp']
        with self.assertRaises(ValueError):
            validate_task(swapped)
        with self.assertRaises(ValueError):
            build_url_task(url='https://example.com/x', task_version='v', budgets={
                **GOAL_BUDGETS, 'max_actions': -1})


def script_first_observation(prompt):
    return 'obs-not-current'


class CompileStepContract(unittest.TestCase):
    def test_back_contract(self):
        from webcollect.agent_controller import compile_step
        from webcollect.react_session import build_url_task
        task = build_url_task(url='https://example.com/', task_version='t')
        empty = {'controls': {}}
        with self.assertRaises(ValueError):
            compile_step(task, ['https://example.com/'], {'action': 'back', 'goal': 'g', 'expected': 'e',
                                                          'page_id': 'p0'}, empty, 1)
        compile_step(task, ['https://example.com/'], {'action': 'back', 'goal': 'g', 'expected': 'e'},
                     empty, 1)


class PromptBoundTests(unittest.TestCase):
    def test_a08_site_context_images_capped_in_model_chooser(self):
        from webcollect.agent_feedback import PLANNING_IMAGES_LIMIT
        self.assertLessEqual(PLANNING_IMAGES_LIMIT, 4)


class QCWholeTrajectoryTests(unittest.TestCase):
    def test_a10_compact_trajectory_carries_whole_length_metadata(self):
        from quality_inspector.ai_worker import compact_trajectory
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'S000001_sample_000001'
            (root / 'images').mkdir(parents=True)
            (root / 'ui_tree').mkdir(parents=True)
            steps = []
            for i in range(6):
                png = make_png(1000 + i)
                (root / f'images/step_{i+1:03}.png').write_bytes(png)
                tree = {'image_path': f'images/step_{i+1:03}.png', 'screen_resolution': [1280, 720],
                        'elements': []}
                (root / f'ui_tree/step_{i+1:03}.json').write_text(json.dumps(tree))
                steps.append({'step_id': i + 1, 'image_path': f'images/step_{i+1:03}.png',
                    'ui_tree_path': f'ui_tree/step_{i+1:03}.json', 'page_name': '网页「测试」',
                    'user_goal': '目标' if i < 5 else '确认最终页面',
                    'next_step_rationale': '说明', 'step_result': '结果说明',
                    'tool_result': {'status': 'success', 'return_value': {}, 'error': ''},
                    'action': {'action_type': 'click' if i < 5 else 'complete',
                               'target_element_id': '', 'target_text': '', 'coordinate': [],
                               'input_text': '', 'precondition': '前置', 'expected_result': '预期'}})
            annotation = {'sample_id': 'S000001_sample_000001', 'task_instruction': '在页面执行操作',
                'final_result': '完成', 'completion_judgement': '完成',
                'short_flow': True, 'short_flow_reason': '页面只有三个有效操作',
                'steps': steps}
            (root / 'annotation.json').write_text(json.dumps(annotation, ensure_ascii=False))
            from quality_inspector.ai_worker import snapshot as ai_snapshot
            context, images = compact_trajectory(ai_snapshot(root))
            self.assertEqual(context['whole_trajectory_length']['effective_steps'], 5)
            self.assertTrue(context['whole_trajectory_length']['short_flow'])
            self.assertEqual(context['whole_trajectory_length']['short_flow_reason'],
                             '页面只有三个有效操作')
            self.assertEqual(len(images), 6)


class DuplicatePolicyTests(unittest.TestCase):
    def test_a11_rate_verdicts_consistent(self):
        from quality_inspector.duplicates import summarize
        def result(rows, pairs):
            return {'rows': [{'sample_id': s} for s in rows],
                'route1': {'groups': [], 'pairs': [], 'confirmed_pair_count': 0},
                'route2': {'confirmed_pairs': [], 'count': 0},
                'route3': {'candidates': pairs, 'count': len(pairs)},
                'route4': {'candidates': [], 'count': 0}}
        empty = summarize(result([], []), [])
        self.assertEqual(empty['analysis_status'], 'PENDING')
        self.assertIsNone(empty['sample_rate_within_requested_limit'])
        below = summarize(result(['a', 'b'], []), ['a', 'b'])
        self.assertTrue(below['sample_rate_within_requested_limit'])
        above = summarize(result(['a', 'b'], [{'sample_ids': ['a', 'b']}]), ['a', 'b'])
        self.assertFalse(above['sample_rate_within_requested_limit'])
        # Historical samples never dilute the denominator.
        mixed = summarize(result(['a', 'h1', 'h2'], [{'sample_ids': ['a', 'h1']}]), ['a'])
        self.assertEqual(mixed['current_sample_count'], 1)
        self.assertFalse(mixed['sample_rate_within_requested_limit'])


if __name__ == '__main__':
    unittest.main()


class EnvelopeToleranceTests(unittest.TestCase):
    def test_prose_wrapped_json_is_extracted_and_broken_json_is_not(self):
        from webcollect.model_gateway import parse_content
        good = '好的，以下是决策：\n{"goal_update": null, "decision_summary": "继续", "tool_call": {"name": "observe", "arguments": {"focus_control_id": null}}}'
        value, normalized = parse_content(good, 'glm')
        self.assertTrue(normalized)
        self.assertEqual(value['tool_call']['name'], 'observe')
        fenced, normalized2 = parse_content('```json\n{"a": 1}\n```', 'glm')
        self.assertEqual((fenced, normalized2), ({'a': 1}, True))
        strict, normalized3 = parse_content('{"a": 1}', 'glm')
        self.assertEqual((strict, normalized3), ({'a': 1}, False))
        with self.assertRaises(ValueError):
            parse_content('决策如下 {"a": 1} 但未结束', 'glm')
        with self.assertRaises(ValueError):
            parse_content('{"a": 1', 'glm')


class CliDynamicPlanResumeTests(unittest.TestCase):
    """Real-run v12 lesson: a paused/killed react runtime could only be
    continued through task_generation's one-attempt wrapper; the collect CLI
    had no way to supply the plan's original model ledger."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config_path = self.root / 'ledger-config.json'
        shutil.copy(Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json',
                    self.config_path)

    def test_builder_binds_original_ledger_and_rejects_altered_config(self):
        from webcollect.batch_core import BatchLedger
        from webcollect.collect import dynamic_controller_ledger
        from webcollect.planning import object_sha256
        config = load_json(self.config_path)
        ledger_path = self.root / 'original-ledger.sqlite3'
        ledger = BatchLedger(ledger_path, config, initialize=True)
        plan = {'schema_version': 'webcollect-plan-m4-1',
                'tasks': [build_url_task(url='https://example.org/entry', task_version='t')],
                'generation': {'controller_ledger': {
                    'path': str(ledger.path), 'config_sha256': object_sha256(ledger.config)}}}
        plan_path = self.root / 'plan.json'
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
        bound = dynamic_controller_ledger(plan_path, self.config_path)
        self.assertEqual(Path(bound.path), ledger_path.resolve())
        altered_path = self.root / 'altered-config.json'
        altered = deepcopy(config)
        altered['budget']['max_probe_pages'] = altered['budget']['max_probe_pages'] + 1
        altered_path.write_text(json.dumps(altered), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'original model ledger|configuration is frozen'):
            dynamic_controller_ledger(plan_path, altered_path)
        unbound = deepcopy(plan)
        del unbound['generation']['controller_ledger']
        unbound_path = self.root / 'unbound-plan.json'
        unbound_path.write_text(json.dumps(unbound), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '未绑定'):
            dynamic_controller_ledger(unbound_path, self.config_path)


class ReactCloseEventTests(unittest.TestCase):
    def test_close_event_uses_store_transaction_api(self):
        from test_p0_production import seed_captures
        from webcollect.collect_runtime import react_close_event
        from webcollect.runtime import RuntimeStore
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        registry = Path(temp.name) / 'registry.db'
        seed_captures(registry, ['CONTROLLED-react-x'], prefix=0)
        store = RuntimeStore(registry, 'CONTROLLED-scope')
        attempt = {'task_key': 'key-CONTROLLED-react-x', 'attempt_id': 'attempt-x'}
        react_close_event(store, attempt, 'react_raw_saved', 1793000000.0, {'probe': True})
        import sqlite3
        with sqlite3.connect(registry) as con:
            row = con.execute("SELECT event_type, at, payload_json FROM m4_events WHERE event_type='react_raw_saved'").fetchone()
        self.assertEqual(row[0], 'react_raw_saved')
        # The v15 real-run lesson: a swapped argument order bound a dict into
        # the timestamp slot; the receipt must carry the numeric event time.
        self.assertEqual(row[1], 1793000000.0)
        self.assertEqual(json.loads(row[2]), {'probe': True})
