"""V11 free reading-action composition and cross-page baseline (2026-11-09).

The prompt permits page-evidenced legal actions without a fixed mix, direction,
link type or independent purpose for each click. The cross-page baseline asks
its unchanged question and requires a related-page visit and return; it does
not make that route mandatory for general reading tasks. Scripted sessions
cover the mixed route, a generic pure-scroll route and the real r2 early-finish
breakpoint. No provider or browser runs; real GLM validation is separate.
"""
import json
import re
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from test_direct_reading_baseline_20261108 import (
    ARTICLE, RELATED, DirectHarness, SUBJECT)
from webcollect.action_stability import ACTION_SCOPED_VERSION
from webcollect.banded_plan import V10_VERSION, V11_VERSION, system_for
from webcollect.closing_policy import V2_VERSION as END_V2, VERSION as END_V3
from webcollect.goal_evidence import VERSION as EVIDENCE_VERSION
from webcollect.planning import object_sha256
from webcollect.react_session import ReactSession, build_url_task

REPO = Path(__file__).resolve().parents[3]
VARIANT_FILE = REPO / 'request/consumer-baselines/zh-wikipedia-direct-reading-cross-page.json'
ORIGINAL_FILE = REPO / 'request/consumer-baselines/zh-wikipedia-direct-reading.json'


def prompt_task(protocol, ending, contract, description='阅读月食'):
    task = build_url_task(url=ARTICLE, task_version='t', ending_policy=ending,
                          plan_protocol=protocol,
                          action_stability_protocol=ACTION_SCOPED_VERSION)
    spec = task['workflow_proposal']['spec']
    spec['goal'] = {'instruction': description,
                    'structured': {'kind': contract['kind'], 'description': description,
                                   'minimum_effective_steps': 5, 'preferred_band': 'long',
                                   'evidence_contract': contract}}
    task['task_id'] = 'react-' + object_sha256({'url': spec.get('entry_url'), 'spec': spec})[:24]
    return task


READING_CONTRACT = {'version': EVIDENCE_VERSION, 'kind': 'reading', 'subject': SUBJECT,
                    'aspects': ['月球', '地球']}


class MixPromptTests(unittest.TestCase):
    """Free composition applies to V11 reading, preserving other prompt paths."""

    def test_v11_reading_prompt_allows_free_composition_and_recovery(self):
        prompt = system_for(prompt_task(V11_VERSION, END_V3, READING_CONTRACT))
        self.assertIn('按冻结目标与当前页面证据自由组合allowed_actions中的合法动作', prompt)
        self.assertIn('滚动可向上或向下', prompt)
        self.assertIn('按失败事实和最新观察调整位置或改选目标', prompt)
        self.assertIn('可继续原任务仍需的合法剩余动作', prompt)
        self.assertIn('纯滚动也可作为合法阅读路径', prompt)
        self.assertIn('不强制跨页', prompt)
        self.assertNotIn('一至两次', prompt)
        self.assertNotIn('独立查阅目的', prompt)

    def test_v10_reading_prompt_keeps_previous_wording(self):
        prompt = system_for(prompt_task(V10_VERSION, END_V2, READING_CONTRACT))
        self.assertIn('长阅读由多段滚动自然组成', prompt)
        self.assertNotIn('一至两次有独立查阅目的的点击', prompt)
        self.assertNotIn('滚动段落与一至两次目的性点击', prompt)

    def test_v11_computation_prompt_untouched(self):
        contract = {'version': EVIDENCE_VERSION, 'kind': 'computation',
                    'subject': '税额', 'aspects': ['税额']}
        prompt = system_for(prompt_task(V11_VERSION, END_V3, contract, '计算税额'))
        self.assertNotIn('滚动段落与一至两次目的性点击', prompt)
        self.assertNotIn('一至两次有独立查阅目的的点击', prompt)

    def test_direct_article_protocol_prompt_untouched(self):
        from webcollect.direct_article import VERSION as DIRECT_VERSION
        contract = {'version': DIRECT_VERSION, 'kind': 'reading', 'entry_url': ARTICLE,
                    'titles': [SUBJECT]}
        prompt = system_for(prompt_task(V11_VERSION, END_V3, contract))
        self.assertIn('离开原词条后下一业务动作必须back', prompt)
        self.assertNotIn('滚动段落与一至两次目的性点击', prompt)
        self.assertNotIn('一至两次有独立查阅目的的点击', prompt)

    def test_direct_entry_prompt_allows_related_link_excursion(self):
        contract = {**READING_CONTRACT, 'direct_entry': True}
        prompt = system_for(prompt_task(V11_VERSION, END_V3, contract))
        self.assertIn('本任务入口已直接打开目标词条', prompt)
        self.assertIn('可点击当前帧可见的相关链接查阅关联词条', prompt)
        self.assertIn('引用仍只来自原词条', prompt)


class CrossPageObjectiveTests(unittest.TestCase):
    """The fixed variant file is a valid, materially different objective."""

    def test_variant_file_passes_objective_binding_rules(self):
        value = json.loads(VARIANT_FILE.read_text(encoding='utf-8'))
        self.assertEqual(value['schema_version'], 'webcollect-session-objective-1')
        self.assertEqual(value['entry_url'], json.loads(ORIGINAL_FILE.read_text(encoding='utf-8'))['entry_url'])
        objective = value['objective']
        # Mirrors session_objective.bind's objective constraints.
        self.assertTrue(objective.get('description'))
        minimum = objective.get('minimum_effective_steps')
        band = objective.get('preferred_band')
        self.assertTrue(type(minimum) is int and band in ('five', 'long')
                        and (minimum == 5 if band == 'five' else 5 <= minimum <= 8))
        self.assertIn(objective.get('evidence_policy'),
                      ('webcollect-action-scoped-evidence-1',))
        contract = objective['evidence_contract']
        self.assertEqual(contract['version'], EVIDENCE_VERSION)
        self.assertIs(contract['direct_entry'], True)
        # The contracted description still demands real downward reading.
        self.assertTrue(re.search(r'(?:往下|向下)(?:滚动)?阅读|(?:往下|向下)滚动|scroll\s+down',
                                  objective['description'], re.I))

    def test_variant_instruction_is_route4_distant_from_original(self):
        from quality_inspector.duplicates import analyze_inputs
        original = json.loads(ORIGINAL_FILE.read_text(encoding='utf-8'))['objective']['description']
        variant = json.loads(VARIANT_FILE.read_text(encoding='utf-8'))['objective']['description']
        from test_direct_reading_baseline_20261108 import FourRouteDedupTests
        helper = FourRouteDedupTests()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_a = helper._png(lambda x, y: (x * 4 % 256, y * 4 % 256, (x + y) % 256))
            last_a = helper._png(lambda x, y: ((x * 3 + y) % 256, (x ^ y) % 256, 255 - x * 2 % 256))
            first_b = helper._png(lambda x, y: (255 - x % 256, (x * y) % 256, y * 2 % 256))
            last_b = helper._png(lambda x, y: ((x + y) % 256, 255 - y % 256, x % 256))
            steps = [('scroll', '', '月食', 'step_001.png'), ('click', '日食', '月食', 'step_002.png')]
            a = helper._sample(root, 'S1_sample_000001', original, steps,
                               {'step_001.png': first_a, 'step_002.png': last_a})
            b = helper._sample(root, 'S1_sample_000002', variant, steps,
                               {'step_001.png': first_b, 'step_002.png': last_b})
            result = analyze_inputs([a, b])
            self.assertEqual(result['route4']['count'], 0)  # substantive task-text difference
            self.assertEqual(result['route1']['confirmed_pair_count'], 0)


class CrossPageVariantSessionTests(DirectHarness):
    """Scripted mechanics retain source identity across the mixed route."""

    def variant_task(self):
        objective = json.loads(VARIANT_FILE.read_text(encoding='utf-8'))['objective']
        return self.direct_task(objective=objective)

    async def test_scroll_click_back_scroll_mix_verified_under_variant(self):
        self.surface.article_scroll_limit = 3  # room for the post-return segment
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读月食类型章节',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读成因段落',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '查阅日食词条核对形成条件对应关系', 'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'back', 'purpose': '返回月食词条并核验原页面身份',
             'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '续读满月与周期章节',
             'expected': {'kind': 'scroll_changed'}},
        ]
        session, evidence = self.scripted('mix-variant', lambda p: self.plan_with(p, steps),
                                          ['cite:e_p3', 'stop'], task=self.variant_task())
        result = await session.run()
        self.assertFalse(result['host_failure'], result)
        self.assertEqual(result['effective_steps'], 5)
        self.assertEqual([a for a, _ in self.surface.executed],
                         ['scroll', 'scroll', 'click', 'back', 'scroll'])
        objective = self.objective_of(evidence)
        self.assertEqual(objective['status'], 'VERIFIED')
        self.assertTrue(objective['direct_entry'])
        self.assertEqual(objective['search_inputs'], [])
        self.assertTrue(objective['required_downward_reading'])
        self.assertTrue(objective['downward_reading_satisfied'])
        # The citation still originates from the original 月食 article.
        selected = objective['selected_passage']
        self.assertIsNotNone(selected)
        self.assertIn('月球', selected['quote'])
        self.assertIn('地球', selected['quote'])

    async def test_pure_scroll_verifies_under_generic_reading_objective(self):
        """The generic original goal allows pure scrolling; a cross-page goal
        cannot be used to claim that pure scrolling completes its route."""
        self.surface.article_scroll_limit = 5
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': f'阅读第{i}段',
             'expected': {'kind': 'scroll_changed'}}
            for i in range(1, 6)
        ]
        session, evidence = self.scripted('mix-pure-scroll', lambda p: self.plan_with(p, steps),
                                          ['cite:e_p3', 'stop'], task=self.direct_task())
        result = await session.run()
        self.assertEqual(result['effective_steps'], 5)
        objective = self.objective_of(evidence)
        self.assertEqual(objective['status'], 'VERIFIED')


class UnprovedEffectFinishTests(DirectHarness):
    """Real-run r2 breakpoint (2026-11-09): after the model committed to a
    purposeful click/back continuation, its repositioning scroll's expected text
    was not established on the new frame. The host's mismatch shortcut finished
    the session on the spot because goal evidence was already VERIFIED — unlike
    endpoint_now it never consulted continue_reading — and the round-trip guard
    then rightly rejected the unresolved tail. The host must ask the model
    instead of finishing over a planned, purposeful remaining route."""

    def variant_task(self):
        objective = json.loads(VARIANT_FILE.read_text(encoding='utf-8'))['objective']
        return self.direct_task(objective=objective)

    def scripted_replan(self, name, steps, replan_steps, branches, task):
        preferences = list(branches)

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if len(self.prompts) == 1:
                return {'name': 'submit_plan', 'arguments': self.plan_with(prompt, steps),
                        'tool_call_id': 'provider-first',
                        'assistant_message': {'role': 'assistant', 'tool_calls': []},
                        'request_id': 'mock'}
            options = [o.get('choice') for o in prompt.get('options', []) if isinstance(o, dict)]
            for wanted in preferences:
                if wanted in options:
                    picked = {'attempt_id': prompt['attempt_id'],
                              'observation_id': prompt['observation']['observation_id'],
                              'choice': wanted}
                    if wanted == 'replan':
                        picked['plan'] = self.plan_with(prompt, replan_steps)
                    return picked
                if ':' in wanted and any(o.startswith(wanted.split(':')[0] + ':') for o in options):
                    return {'attempt_id': prompt['attempt_id'],
                            'observation_id': prompt['observation']['observation_id'],
                            'choice': next(o for o in options
                                           if o.startswith(wanted.split(':')[0] + ':'))}
            raise AssertionError('no scripted preference offered: ' + repr(options))

        evidence = self.root / name / 'evidence' / self.ids['sample_id']
        session = ReactSession(task, evidence / 'raw', choose, self.page,
                               steps_directory=evidence, attempt_id='offline-direct')
        return session, evidence

    async def test_unproved_prediction_does_not_finish_over_purposeful_remaining_plan(self):
        self.surface.article_scroll_limit = 4
        failing = {'action': 'scroll', 'direction': 'down', 'purpose': '继续向下阅读成因段落',
                   'expected': {'kind': 'visible_text', 'text': '本帧不存在的文字'}}
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读月食类型章节',
             'expected': {'kind': 'scroll_changed'}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '阅读成因段落',
             'expected': {'kind': 'scroll_changed'}},
            failing,
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '查阅日食词条核对形成条件对应关系',
             'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'back', 'purpose': '返回月食词条并核验原页面身份',
             'expected': {'kind': 'document_changed', 'text': SUBJECT}},
        ]
        replan_steps = [
            {'action': 'click', 'target': {'text': '日食'},
             'purpose': '查阅日食词条核对形成条件对应关系',
             'expected': {'kind': 'document_changed', 'text': '日食'}},
            {'action': 'back', 'purpose': '返回月食词条并核验原页面身份',
             'expected': {'kind': 'document_changed', 'text': SUBJECT}},
            {'action': 'scroll', 'direction': 'down', 'purpose': '续读满月与周期章节',
             'expected': {'kind': 'scroll_changed'}},
        ]
        session, evidence = self.scripted_replan(
            'mix-unproved-effect', steps, replan_steps, ['cite:e_p3', 'replan'],
            task=self.variant_task())
        result = await session.run()
        # Before the fix the host finished at 3 steps with '动作预期有差异'.
        self.assertFalse(result['host_failure'], result)
        # The original remaining reading is still legal after the minimum;
        # reaching five steps must not silently cancel it.
        self.assertEqual([a for a, _ in self.surface.executed],
                         ['scroll', 'scroll', 'scroll', 'click', 'back', 'scroll'])
        self.assertEqual(result['effective_steps'], 6)
        self.assertEqual(result['stop_reason'], 'ready')
        # The model was consulted about the unproved prediction (replan offer).
        branch_prompts = [p for p in self.prompts[1:]]
        self.assertTrue(any('replan' in [o.get('choice') for o in p.get('options', [])]
                            for p in branch_prompts))
        self.assertEqual(self.objective_of(evidence)['status'], 'VERIFIED')

    async def test_unproved_prediction_still_finishes_when_minimum_already_met(self):
        """The mismatch shortcut is preserved once the minimum route length is
        reached: continue_reading no longer applies, the verified goal lets the
        host close without spending another model request."""
        self.surface.article_scroll_limit = 5
        steps = [
            {'action': 'scroll', 'direction': 'down', 'purpose': f'阅读第{i}段',
             'expected': {'kind': 'scroll_changed'}}
            for i in range(1, 5)
        ]
        steps.append({'action': 'scroll', 'direction': 'down', 'purpose': '阅读收尾段落',
                      'expected': {'kind': 'visible_text', 'text': '本帧不存在的文字'}})
        session, evidence = self.scripted_replan(
            'mix-unproved-met-minimum', steps, [], ['cite:e_p3'], task=self.direct_task())
        result = await session.run()
        self.assertFalse(result['host_failure'], result)
        self.assertEqual(result['effective_steps'], 5)
        self.assertEqual(result['stop_reason'], 'ready')
        # Only the plan submission and the citation offer reached the model.
        self.assertEqual(len(self.prompts), 2)


class ActionScopedFeedbackTests(unittest.TestCase):
    """Real-run r4 (2026-11-09): the model picked a visible link whose dispatch
    was legitimately rejected, but the single generic 'lacks visible loaded hit
    proof' message could not tell it whether to scroll, wait, or switch links.
    The rejection now names the failing sub-condition so the next planned step
    can fix the right thing. The checks themselves are unchanged."""

    @staticmethod
    def state():
        box = [100, 100, 200, 120]
        samples = [{'point': [x, y], 'ancestor': True}
                   for y in (101, 110, 119) for x in (101, 150, 199)]
        return {'elements': [{'element_id': 'e1', 'visible': True, 'enabled': True,
                              'bbox': list(box), 'clickable': True, 'native_role': 'a'}],
                'capture_controls': [{'element_id': 'e1', 'tag': 'a', 'href': 'x', 'selector': 's'}],
                'geometry_witnesses': [{'element_id': 'e1', 'bbox': list(box), 'samples': samples}],
                'screen_resolution': [1280, 720],
                'capture_readiness': {'document_ready': 'complete', 'fonts_ready': True,
                                      'images_ready': True},
                'values': [], 'target': None}

    def test_valid_target_passes(self):
        from webcollect.action_stability import action_scoped_projection
        basis = action_scoped_projection(self.state(), 'e1', 'click')
        self.assertIn('url', basis)

    def test_obstructed_hit_samples_name_the_remedy(self):
        from webcollect.action_stability import action_scoped_projection
        state = self.state()
        state['geometry_witnesses'][0]['samples'][0]['ancestor'] = False
        with self.assertRaises(ValueError) as caught:
            action_scoped_projection(state, 'e1', 'click')
        self.assertIn('hit samples partially obstructed', str(caught.exception))
        self.assertIn('pick another visible link', str(caught.exception))

    def test_outside_viewport_names_scrolling(self):
        from webcollect.action_stability import action_scoped_projection
        state = self.state()
        state['elements'][0]['bbox'] = [100, 700, 200, 760]
        state['geometry_witnesses'][0]['bbox'] = [100, 700, 200, 760]
        with self.assertRaises(ValueError) as caught:
            action_scoped_projection(state, 'e1', 'click')
        self.assertIn('outside current viewport', str(caught.exception))

    def test_unloaded_frame_and_hidden_target_are_distinct(self):
        from webcollect.action_stability import action_scoped_projection
        state = self.state()
        state['capture_readiness']['images_ready'] = False
        with self.assertRaises(ValueError) as caught:
            action_scoped_projection(state, 'e1', 'click')
        self.assertIn('not fully loaded', str(caught.exception))
        state = self.state()
        state['elements'][0]['visible'] = False
        with self.assertRaises(ValueError) as caught:
            action_scoped_projection(state, 'e1', 'click')
        self.assertIn('not visible/enabled', str(caught.exception))


class ReturnIdentityDeliveryTests(DirectHarness):
    """One mixed/derive chain plus counterfactual source checks; no network."""
    async def test_new_return_identity_preserves_citation_remaining_reading_and_natural_expectation(self):
        from types import SimpleNamespace
        from test_closing_policy_v2 import EndingV2Tests
        from webcollect.agent_controller import exclusive
        from webcollect.batch_core import load_json
        from webcollect.goal_evidence import reading_evidence, contract_for
        from webcollect.postprocess import delivery_expectation, session_record
        self.surface.article_scroll_limit = 4
        original_elements = self.surface._elements
        original_bindings = self.surface._bindings
        original_execute = self.surface.execute_action
        original_render = self.surface._render
        original_capture = self.surface.capture
        returned = False
        def elements():
            rows = original_elements()
            if self.surface.page == 'article':
                for i in (3, 4):
                    if self.surface.scroll >= i:
                        rows.append({'element_id':f'e_more{i}','native_role':'p','parent_id':'root',
                            'text':f'第{i}节正文说明月球运行周期与地球阴影的变化，继续核对满月期间的观测条件。'})
                if returned:
                    rows = [row for row in rows if row['element_id'] != 'e_h']
            return rows
        def bindings():
            rows = original_bindings()
            if self.surface.page == 'article':
                for i in (3, 4):
                    if self.surface.scroll >= i:
                        rows.append({'element_id':f'e_more{i}','selector':f'html:1 > body:1 > main:1 > p:{i+1}',
                                     'tag':'p','href':None})
            return rows
        def execute(action, arguments):
            nonlocal returned
            original_execute(action, arguments)
            if action == 'back' and self.surface.page == 'article':
                returned = True
                self.surface.origins[ARTICLE] = 9000 + self.surface.navigations
                self.surface.state = self.surface._render()
        def render(**kwargs):
            value = original_render(**kwargs)
            if self.surface.page == 'related':
                value['capture_readiness'].update(document_ready='interactive',images_ready=False)
            return value
        async def capture(*args, **kwargs):
            observation = await original_capture(*args, **kwargs)
            scope = kwargs.get('action_scope')
            if scope:
                from webcollect.browser import stability_pair
                proof = stability_pair(observation['state'], observation['state'],
                                       observation['png'], observation['png'], action_scope=scope)
                self.assertTrue(proof['accepted'], proof)
                observation['action_scope'] = scope
                for attempt in observation['capture']['attempts']:
                    attempt.update(stability=proof, final_stability=proof)
            return observation
        self.surface.capture = capture
        self.surface._render = render
        self.surface._elements = elements
        self.surface._bindings = bindings
        self.surface.execute_action = execute
        steps = [
            {'action':'scroll','direction':'down','purpose':'阅读月食类型章节','expected':{'kind':'scroll_changed'}},
            {'action':'scroll','direction':'down','purpose':'阅读地月位置关系段落','expected':{'kind':'scroll_changed'}},
            {'action':'scroll','direction':'down','purpose':'续读满月观测条件','expected':{'kind':'scroll_changed'}},
            {'action':'click','target':{'text':'日食'},'purpose':'查阅相关词条核对位置关系',
             'expected':{'kind':'url','text':RELATED}},
            {'action':'back','purpose':'返回月食正文继续核对','expected':{'kind':'document_changed','text':SUBJECT}},
            {'action':'scroll','direction':'down','purpose':'返回后续读原任务尚需的周期说明',
             'expected':{'kind':'scroll_changed'}},
        ]
        session,evidence = self.scripted('return-new-identity',lambda p:self.plan_with(p,steps),
                                        ['cite:e_p3','stop'],task=self.direct_task())
        result = await session.run()
        self.assertFalse(result['host_failure'],result)
        self.assertEqual(result['effective_steps'],6)
        self.assertEqual(result['stop_reason'],'ready')
        objective = self.objective_of(evidence)
        self.assertEqual(objective['status'],'VERIFIED')
        selected = objective['selected_passage']
        original_ob = session.observation_records[selected['observation_id']]
        self.assertNotEqual(original_ob['document_identity'],session.current['document_identity'])
        self.assertFalse(any(e.get('native_role')=='h1' for e in load_json(
            session.current['evidence']['state']['path'])['elements']))
        # Retained citation points at its actual old observation, never a newly
        # signed version of the returned document's passage.
        self.assertEqual(load_json(original_ob['evidence']['state']['path'])['url'],ARTICLE)
        _,annotation = EndingV2Tests.derive(self,evidence,name='return-new-identity-derived')
        expected = annotation['steps'][3]['action']['expected_result']
        self.assertEqual(expected,'预期打开「日食」页面')
        self.assertNotIn('%',expected)
        saved_record = session_record(evidence/'raw')
        self.assertEqual(saved_record['trajectory'][3]['expected'],RELATED)
        back = saved_record['trajectory'][4]
        before_back = load_json(saved_record['observations'][back['before_observation_id']]['evidence']['state']['path'])
        self.assertEqual(before_back['capture_readiness']['document_ready'],'interactive')
        self.assertFalse(before_back['capture_readiness']['images_ready'])
        from webcollect.action_stability import BACK_OBSERVED_VERSION
        capture = load_json(back['raw_step']['path'])['capture']
        self.assertEqual(capture['attempts'][-1]['stability']['action_scope']['readiness_policy'],BACK_OBSERVED_VERSION)
        self.assertEqual(delivery_expectation(RELATED,'click',None,None),'预期打开所选页面')
        self.assertEqual(annotation['completion_judgement'],'末帧完成判定依据：'+annotation['final_result'])

        # Counterfactuals are new fixture files; the sealed session is untouched.
        source_id = session.plan_controller.frozen_plan['observation_id']
        contract = contract_for(session.task)
        for mode in ('different-url','wrong-body'):
            observations = deepcopy(session.observation_records)
            for oid,ob in observations.items():
                if ob['document_identity'] != session.current['document_identity']:
                    continue
                value = load_json(ob['evidence']['state']['path'])
                if mode == 'different-url':
                    value['url'] = 'https://another.test/wiki/同名月食'
                    value['document_identity'] = {**value['document_identity'],'url_without_fragment':value['url']}
                    ob['url'] = value['url'];ob['document_identity'] = value['document_identity']
                else:
                    for element in value['elements']:
                        if element.get('native_role') == 'p':
                            element['text'] = '另一篇内容只介绍独立的天气观测记录，没有这次原词条曾经显示的正文。'
                ob['evidence']['state'] = exclusive(self.root/(mode+'-'+oid+'.json'),value)
            changed = SimpleNamespace(**{k:getattr(session,k) for k in
                ('trajectory','attempt_id','binding','task','answer_citation','requested_goal')})
            changed.observation_records = observations
            changed.current = observations[session.current['observation_id']]
            self.assertNotEqual(reading_evidence(changed,observations[source_id],contract)['status'],'VERIFIED',mode)
        branch = load_json(session.answer_citation['path'])
        foreign = next(ob for ob in session.observation_records.values() if ob['url']==RELATED)
        branch['response']['observation_id'] = foreign['observation_id']
        changed = SimpleNamespace(**{k:getattr(session,k) for k in
            ('trajectory','attempt_id','binding','task','requested_goal','current','observation_records')})
        changed.answer_citation = exclusive(self.root/'foreign-citation.json',branch)
        self.assertNotEqual(reading_evidence(changed,session.observation_records[source_id],contract)['status'],'VERIFIED')


if __name__ == '__main__':
    unittest.main()
