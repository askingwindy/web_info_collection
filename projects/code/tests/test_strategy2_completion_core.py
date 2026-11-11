"""Seven offline completion, progress and plan-narrative contracts; no browser or provider IO."""
from copy import deepcopy

import test_strategy2_runlog_20261111 as substrate
from webcollect.batch_core import load_json
from webcollect.screenshot_plan import (
    NO_PROGRESS_STALL_LIMIT, READY_ENDING, _replay_session, narrative_grounding_gaps,
    verify_completion, normalize_decision,
)
from webcollect.screenshot_session import ScreenshotPlanSession


class CompletionCoreTests(substrate.SessionHarness):
    # SessionHarness has no test methods; importing its module as an alias avoids
    # collecting the existing runlog TestCase classes a second time.
    def setUp(self):
        super().setUp()
        self.task = substrate.build_url_task(
            url=self.page.url, task_version='completion-core',
            ending_policy=substrate.COMPLETE_VERSION)
        substrate.freeze_strategy(self.task, substrate.STRATEGY_SCREENSHOT_PLAN)
        self.task['task_id'] = 'react-' + substrate.object_sha256(
            {'url': self.task['initial_url'], 'spec': self.task['workflow_proposal']['spec']})[:24]
        substrate.validate_task(self.task)
        self.texts = ['这篇文章记载人物原名为陈树人，并介绍其早年经历。',
                      '这篇文章记载人物出生于广东，并介绍当地历史背景。']
        for index, text in enumerate(self.texts):
            self.surface.state['elements'].append({
                'element_id': f'body-{index}', 'text': text, 'native_role': 'p',
                'element_type': 'text', 'bbox': [10, 300 + index * 70, 1000, 350 + index * 70],
                'visible': True, 'enabled': True, 'inputable': False, 'clickable': False,
                'parent_id': 'root', 'scrollable': False, 'state': 'default'})

    async def _session(self, choose, requirements=None):
        root = self.root / 'evidence' / 'S000001_sample_000201'
        session = ScreenshotPlanSession(self.task, root / 'raw', choose, self.page,
            steps_directory=root, attempt_id='completion-core-attempt')
        await session._open_entry()
        session.frozen_goal = session._fixed_goal() or '阅读文章并回答原名及出生地'
        session.requirements = requirements or [
            {'id': 'r1', 'kind': 'content', 'description': '阅读文章并回答人物原名'},
            {'id': 'r2', 'kind': 'content', 'description': '阅读文章并回答人物出生地'}]
        session.plan = {'steps': [{'action': 'wait', 'duration_ms': 1}]}
        session.plan_event = session.event('screenshot-plan', phase='first',
            goal=session.frozen_goal, requirements=deepcopy(session.requirements),
            steps=deepcopy(session.plan['steps']))
        return session

    def _answer(self, oid, index):
        return {'requirement_id': f'r{index + 1}', 'observed_result': self.texts[index],
                'evidence': [{'observation': oid, 'quote': self.texts[index]}]}

    async def test_incremental_answers_are_sealed_together_and_replay(self):
        prompts = []

        async def choose(prompt):
            index = len(prompts)
            prompts.append(deepcopy(prompt))
            return {'arguments': {'decision': 'complete', 'reason': '补充当前缺项',
                'answers': [self._answer(prompt['current_observation'], index)]}}

        session = await self._session(choose)
        session.plan['steps'][0]['target'] = {'control': 'control-0', '_source': {'host': 'private'}}
        self.assertNotIn('_source', session._branch_prompt('plan_end')['remaining_plan'][0]['target'])
        wire = {'decision': 'revise', 'reason': '沿用剩余目标', 'remaining_plan': [{
            'action': 'drag', 'target': {'control': 'control-0', '_source': {'forged': True}},
            'end_target': {'control': 'control-1', '_source': {'forged': True}},
            'purpose': '移动项目', 'rationale': '当前目标可见', 'expected_result': '项目位置改变'}]}
        normalized, normalization = normalize_decision(wire, ['revise'])
        self.assertNotIn('_source', normalized['remaining_plan'][0]['target'])
        self.assertNotIn('_source', normalized['remaining_plan'][0]['end_target'])
        self.assertIn('_source', wire['remaining_plan'][0]['target'])
        self.assertEqual(sum(t['transform'] == 'host_binding_field_removed'
                             for t in normalization['transforms']), 2)
        await session._checkpoint('plan_end')
        self.assertEqual(session.collection_ending['kind'], READY_ENDING)
        self.assertEqual(prompts[1]['missing_requirements'], ['r2'])
        self.assertEqual(prompts[1]['confirmed_progress'][0]['requirement_id'], 'r1')
        event = load_json(session.goal_evidence['screenshot_completion']['path'])
        self.assertEqual({a['requirement_id'] for a in event['application']['answers']}, {'r1', 'r2'})
        receipt_ref = session._close()
        record = {**session.record(), 'receipt': load_json(receipt_ref['path']),
                  'terminal': load_json(session.root / 'terminal.json'),
                  'boundary': load_json(session.binding['path'])}
        replay, requirements = _replay_session(record)
        checks, gaps = verify_completion(replay, event['application'], requirements)
        self.assertEqual(gaps, [])
        self.assertEqual(checks, event['checks'])

    async def test_later_same_form_input_and_submission_invalidate_old_result(self):
        async def choose(prompt):
            return {'arguments': {'decision': 'continue', 'reason': '记录当前观察'}}

        requirement = [{'id': 'r1', 'kind': 'result', 'description': '查看本次输入对应的利润率计算结果'}]
        session = await self._session(choose, requirement)
        for binding in self.surface.state['capture_controls']:
            binding['form_selector'] = '#calculator'
        self.surface.state['elements'].append({
            'element_id': 'submit', 'text': '计算', 'native_role': 'button',
            'element_type': 'button', 'bbox': [10, 450, 210, 490], 'visible': True,
            'enabled': True, 'clickable': True, 'inputable': False, 'parent_id': 'root'})
        self.surface.state['capture_controls'].append({'element_id': 'submit',
            'selector': '#submit', 'tag': 'button', 'input_type': 'submit',
            'form_selector': '#calculator'})
        await session._observe()
        before = session.current['observation_id']
        self.surface.state['values'][0]['value'] = '20'
        await session._observe()
        entered = session.current['observation_id']
        session.trajectory.append({'operation_id': 'input', 'action': 'type',
            'arguments': {'text': '20'}, 'target': {'control_id': 'control-0'},
            'before_observation_id': before, 'after_observation_id': entered, 'effective': True})
        self.surface.state['elements'].append({
            'element_id': 'result', 'text': '利润率：40%', 'native_role': 'status',
            'element_type': 'text', 'bbox': [10, 510, 800, 560], 'visible': True,
            'enabled': True, 'inputable': False, 'clickable': False, 'parent_id': 'root'})
        self.surface.state['capture_controls'].append({'element_id': 'result',
            'selector': '#result', 'tag': 'p', 'form_selector': '#calculator',
            'result_region_selector': '#result'})
        await session._observe()
        result = session.current['observation_id']
        session.trajectory.append({'operation_id': 'submit', 'action': 'click',
            'arguments': {}, 'target': {'control_id': 'submit'},
            'before_observation_id': entered, 'after_observation_id': result, 'effective': True})
        await session._decide(session._branch_prompt('result'))
        application = {'answers': [{'requirement_id': 'r1', 'observed_result': '利润率：40%',
            'evidence': [{'observation': result, 'quote': '利润率：40%'}]}]}
        # A region reference allows a short actual result without weakening the
        # minimum length of free-form quote anchors.
        region = next(r for r in session.region_registries[result] if '利润率' in r['quote'])
        application['answers'][0]['evidence'] = [{'observation': result, 'region': region['region_id']}]
        checks, gaps = verify_completion(session, application, requirement)
        self.assertEqual(gaps, [])
        self.assertEqual(len(checks), 1)
        from webcollect.screenshot_execution import bind_plan_targets
        input_requirement = {'id': 'i1', 'kind': 'input', 'description': '数量为20',
                             'target': {'control': 'control-0'}, 'expected_value': '20'}
        bind_plan_targets({'requirements': [input_requirement]}, session.observation_records[result])
        input_application = {'answers': [{'requirement_id': 'i1', 'observed_result': '20',
                             'evidence': [{'observation': result, 'control': 'control-0'}]}]}
        input_checks, input_gaps = verify_completion(session, input_application, [input_requirement])
        self.assertEqual(input_gaps, [])
        self.assertEqual(input_checks[0]['evidence'][0]['actual'], '20')
        # Removing a value after calculation is an edit, even though its action is hotkey.
        for action, cid, arguments in [('hotkey', 'control-0', {'keys': ['backspace']}), ('click', 'submit', {})]:
            self.surface.state['values'][0]['value'] = ''
            await session._observe()
            later = session.current['observation_id']
            row = {'operation_id': 'later-' + action, 'action': action, 'arguments': arguments,
                   'target': {'control_id': cid}, 'before_observation_id': result,
                   'after_observation_id': later, 'effective': True}
            session.trajectory.append(row)
            checks, gaps = verify_completion(session, application, requirement)
            self.assertEqual(checks, [])
            self.assertIn('RESULT_EVIDENCE_SUPERSEDED', {gap['kind'] for gap in gaps})
            session.trajectory.pop()

    async def test_valid_complete_wins_at_stall_threshold(self):
        async def choose(prompt):
            return {'arguments': {'decision': 'complete', 'reason': '可见事实已完整',
                'answers': [self._answer(prompt['current_observation'], 0)]}}

        session = await self._session(choose, [{'id': 'r1', 'kind': 'content', 'description': '阅读文章并回答人物原名'}])
        session._stall_marker = session._progress_marker()
        session._stall_count = NO_PROGRESS_STALL_LIMIT
        await session._checkpoint('plan_end')
        self.assertEqual(session.collection_ending['kind'], READY_ENDING)
        self.assertEqual(session.goal_evidence['business_goal_status'], 'VERIFIED')

    async def test_no_effect_dispatch_and_cursor_changes_cannot_clear_stall(self):
        calls = 0

        async def choose(prompt):
            nonlocal calls
            calls += 1
            return {'arguments': {'decision': 'revise', 'reason': f'重新表述尾部{calls}',
                'remaining_plan': [{'action': 'wait', 'duration_ms': 1,
                    'purpose': f'等候结果{calls}', 'rationale': '页面暂时没有结果',
                    'expected_result': '页面出现结果'}]}}

        session = await self._session(choose)
        session._stall_marker = session._progress_marker()
        session._stall_count = NO_PROGRESS_STALL_LIMIT - 1
        session.actual_dispatches += 1  # Dispatched without an established effect.
        session.position = 1          # Cursor bookkeeping is not business progress.
        await session._checkpoint('action_not_established')
        self.assertEqual(session.collection_ending['kind'], 'NO_PROGRESS_END')
        self.assertEqual(session.trajectory, [])
        self.assertEqual(calls, 1)
        # Same business wrapper, no native form: focus and newly observed fields
        # cannot substitute for a real related edit after the preceding submit.
        from webcollect.screenshot_effect import business_scope
        state = deepcopy(self.surface.state)
        for binding in state['capture_controls']:
            binding['selector'] = 'html > body > main > div:nth-of-type(1) > ' + binding['selector']
        self.assertIsNotNone(business_scope(state, 'control-0'))
        self.surface.state = state
        await session._observe()
        state = load_json(session.current['evidence']['state']['path'])
        step = {'action': 'hotkey', 'keys': ['enter']}
        identity = session._action_identity(step, ['control-0'], state)
        basis, _ = session._submission_basis(state, ['control-0'])
        session.dispatch_identities[identity] = {'dispatched': True, 'basis': basis}
        conflict, _ = session._repeat_guard(step, ['control-0'], state, '换一种说法')
        self.assertIsNotNone(conflict)
        before = session.current['observation_id']
        self.surface.state['values'][0]['value'] = '6'
        await session._observe()
        session.trajectory.append({'operation_id': 'correction', 'action': 'type', 'effective': True,
            'target': {'control_id': 'control-0'}, 'before_observation_id': before,
            'after_observation_id': session.current['observation_id']})
        corrected = load_json(session.current['evidence']['state']['path'])
        conflict, _ = session._repeat_guard(step, ['control-0'], corrected, None)
        self.assertIsNone(conflict)

    def test_rationale_quotes_must_exist_in_the_current_frame(self):
        frame = '搜索结果\n金额 100 元\n下一页'
        steps = [{'action': 'type', 'value': '陈树人', 'target': {'text': '搜索'},
                  'rationale': '当前帧可见「金额 100 元」，先输入「陈树人」'},
                 {'action': 'click', 'target': {'text': '下一页'},
                  'rationale': '点击后进入「人物生平」页面'}]
        gaps = narrative_grounding_gaps(steps, frame)
        self.assertEqual([gap['kind'] for gap in gaps], ['RATIONALE_QUOTE_NOT_IN_FRAME'])
        self.assertEqual((gaps[0]['step_index'], gaps[0]['quote']), (1, '人物生平'))
        # The inherited goal and this step's own declared input are plan content,
        # not a claim about the page, and rendered line breaks are not a
        # difference in the quoted text.
        self.assertEqual(narrative_grounding_gaps(steps, frame, '查证「人物生平」'), [])
        self.assertEqual(narrative_grounding_gaps([{'rationale': '当前帧可见「金额100元」'}], frame), [])

    async def test_paraphrased_observed_result_reports_a_verbatim_gap(self):
        async def choose(prompt):
            return {'arguments': {'decision': 'continue', 'reason': '记录当前观察'}}

        requirement = [{'id': 'r1', 'kind': 'content', 'description': '阅读文章并回答人物原名'}]
        session = await self._session(choose, requirement)
        await session._decide(session._branch_prompt('result'))
        oid = session.current['observation_id']

        def answers(observed):
            return {'answers': [{'requirement_id': 'r1', 'observed_result': observed,
                                 'evidence': [{'observation': oid, 'quote': self.texts[0]}]}]}

        checks, gaps = verify_completion(session, answers('人物的原名是陈树人'), requirement)
        self.assertEqual(checks, [])
        self.assertEqual([gap['kind'] for gap in gaps], ['OBSERVED_RESULT_NOT_VERBATIM'])
        self.assertEqual(gaps[0]['quote'], self.texts[0])
        checks, gaps = verify_completion(session, answers(self.texts[0]), requirement)
        self.assertEqual(gaps, [])
        self.assertEqual(len(checks), 1)

    async def test_cited_control_from_an_earlier_frame_removes_continue(self):
        async def choose(prompt):
            return {'arguments': {'decision': 'revise', 'reason': '按当前帧重新绑定尾部'}}

        session = await self._session(choose)
        step = {'action': 'click', 'target': {'control': 'control-0',
                                              '_source': {'document_identity': 'doc-before'}}}
        session.plan['steps'] = [step]
        session.position = 0
        prompt = session._branch_prompt('navigation_checkpoint')
        self.assertNotIn('continue', prompt['choices'])
        self.assertIn('已变化的页面', prompt['next_checkpoint']['continue_unavailable'])
        decision_enum = prompt['tools'][0]['function']['parameters']['properties']['decision']['enum']
        self.assertNotIn('continue', decision_enum)
        step['target']['_source']['document_identity'] = session.current['document_identity']
        self.assertIn('continue', session._branch_prompt('navigation_checkpoint')['choices'])
