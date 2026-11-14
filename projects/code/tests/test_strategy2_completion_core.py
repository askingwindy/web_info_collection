"""Seven offline completion, progress and plan-narrative contracts; no browser or provider IO."""
from copy import deepcopy

import test_strategy2_runlog_20261111 as substrate
from webcollect.batch_core import load_json
from webcollect.screenshot_plan import (
    NO_PROGRESS_STALL_LIMIT, READY_ENDING, _replay_session, narrative_grounding_gaps,
    verify_completion, verify_final_presentation, verify_first_evidence_routes, normalize_decision,
)
from webcollect.screenshot_session import ScreenshotPlanSession


class CompletionCoreTests(substrate.SessionHarness):
    # SessionHarness has no test methods; importing its module as an alias avoids
    # collecting the existing runlog TestCase classes a second time.
    def setUp(self):
        super().setUp()
        self.surface.state['capture_readiness'] = {'document_ready': 'complete', 'fonts_ready': True, 'images_ready': True}
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

    async def _session(self, choose, requirements=None, name='S000001_sample_000201'):
        root = self.root / 'evidence' / name
        session = ScreenshotPlanSession(self.task, root / 'raw', choose, self.page,
            steps_directory=root, attempt_id='completion-core-attempt')
        await session._open_entry()
        session.frozen_goal = session._fixed_goal() or '阅读文章并回答原名及出生地'
        session.requirements = requirements or [
            {'id': 'r1', 'kind': 'content', 'description': '阅读文章并回答人物原名'},
            {'id': 'r2', 'kind': 'content', 'description': '阅读文章并回答人物出生地'}]
        for row in session.requirements:
            row.setdefault('evidence_route', {'source_type': {'input': 'input_state', 'result': 'page_result', 'content': 'page_content'}[row['kind']], 'observation_steps': [1]})
        session.plan = {'steps': [{'action': 'wait', 'duration_ms': 1}]}
        from webcollect.screenshot_execution import bind_plan_targets
        session._controls()
        bind_plan_targets({'requirements': session.requirements}, session.current)
        session.plan_event = session.event('screenshot-plan', phase='first',
            goal=session.frozen_goal, requirements=deepcopy(session.requirements),
            steps=deepcopy(session.plan['steps']), final_presentation_step=1)
        return session

    def _answer(self, oid, index):
        return {'requirement_id': f'r{index + 1}', 'observed_result': self.texts[index],
                'evidence': [{'observation': oid, 'quote': self.texts[index]}]}

    async def test_incremental_answers_are_sealed_together_and_replay(self):
        prompts = []

        async def choose(prompt):
            index = len(prompts)
            prompts.append(deepcopy(prompt))
            if index == 2:
                self.assertNotIn('checkpoint_feedback', prompt, repr(prompt.get('checkpoint_feedback')))
                return {'arguments': {'decision': 'complete', 'reason': '原目标事项已逐帧核验', 'answers': []}}
            decision = {'decision': 'continue' if index == 0 else 'revise', 'reason': '保存当前帧证据',
                        'answers': [self._answer(prompt['current_observation'], index)]}
            if index == 1:
                decision['remaining_plan'] = [
                    {'action': 'scroll', 'direction': 'up', 'amount': 300,
                     'purpose': '返回人物资料展示区域', 'rationale': '原名尚不在当前画面',
                     'expected_result': '接近已阅读的人物资料区域'},
                    {'action': 'scroll', 'direction': 'up', 'amount': 300,
                     'purpose': '共同展示人物原名及出生地', 'rationale': '最后画面需要同时显示两项原目标证据',
                     'expected_result': '人物原名和出生地同时进入视口'}]
            return {'arguments': decision}

        self.surface.state['elements'][-1]['visible'] = False
        requirements = [
            {'id': 'r1', 'kind': 'content', 'description': '阅读文章并回答人物原名'},
            {'id': 'r2', 'kind': 'content', 'description': '阅读文章并回答人物出生地'},
            {'id': 'i1', 'kind': 'input', 'description': '保留数量10',
             'target': {'control': 'control-0'}, 'expected_value': '10'}]
        session = await self._session(choose, requirements)
        captured_input = session.current['observation_id']
        for key in ('elements', 'values', 'capture_controls'):
            self.surface.state[key] = [row for row in self.surface.state[key] if row['element_id'] != 'control-0']
        await session._observe()
        self.assertNotIn(captured_input, session.provided_observations)
        session.plan['steps'][0]['target'] = {'control': 'control-0', '_source': {'host': 'private'}}
        self.assertNotIn('_source', session._branch_prompt('plan_end')['pending_steps'][0]['target'])
        # The synthetic private-field projection probe is not a real step binding.
        # Remove it before exercising continue; an unbound _source has no document
        # identity and correctly makes the production checkpoint reject continue.
        session.plan['steps'][0].pop('target')
        self.assertIn('continue', session._branch_prompt('content_visible')['choices'])
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
        await session._checkpoint('content_visible')
        self.assertEqual(set(session.verified_answers), {'r1', 'i1'})
        self.surface.state['elements'][-2]['visible'] = False
        self.surface.state['elements'][-1]['visible'] = True
        self.surface.state['scroll'][1] = 960
        await session._observe()
        await session._checkpoint('content_visible')
        self.assertEqual(set(session.verified_answers), {'r1', 'r2', 'i1'})
        # The accepted revise (prompts[1]) replaced the plan tail. A requirement
        # still unmet at a later revise re-anchors its route to the new tail;
        # verified ones stay untouched, and the sealed first plan keeps its
        # original observation steps (SSD 3.1).
        self.assertEqual(session.route_map, [None, None])
        r2_answer = session.verified_answers.pop('r2')
        session._reanchor_routes()
        self.assertEqual(session.route_overrides, {'r2': [1, 2]})
        session.verified_answers['r2'] = r2_answer
        session.route_overrides = {}
        goal_prompt = session._branch_prompt('result')
        self.assertNotIn('continue', goal_prompt['choices'])
        self.assertIn('goal_ready', goal_prompt['next_checkpoint'])
        self.assertNotEqual(prompts[0]['current_observation'], prompts[1]['current_observation'])
        # The accepted goal-ready presentation segment runs both necessary
        # scrolls continuously. Only the second scroll reveals both answers.
        original_execute = self.surface.execute_action
        presentation_scrolls = 0

        def reveal_final_reading_frame(action, arguments):
            nonlocal presentation_scrolls
            previous_scroll = self.surface.state['scroll'][1]
            original_execute(action, arguments)
            if action == 'scroll':
                self.surface.state['scroll'][1] = previous_scroll - 300
                presentation_scrolls += 1
                if presentation_scrolls == 2:
                    self.surface.state['elements'][-2]['visible'] = True
                    self.surface.state['elements'][-1]['visible'] = True

        self.surface.execute_action = reveal_final_reading_frame
        session.working_goal = session.frozen_goal  # normal first-plan admission fact
        self.assertTrue(session._presentation_step_pending)
        await session._execute_round()
        self.assertEqual((presentation_scrolls, session.position, len(prompts)), (1, 1, 2))
        self.assertTrue(session._presentation_step_pending)
        self.assertEqual({gap['requirement_id'] for gap in verify_final_presentation(
            session, list(session.verified_checks.values()), session.requirements)[1]}, {'r1'})
        await session._execute_round()
        self.assertEqual((presentation_scrolls, session.position, len(prompts)), (2, 2, 3))
        self.assertEqual(prompts[-1]['call_purpose'], 'completion')
        self.assertEqual(sum(not prompt['missing_requirements'] for prompt in prompts), 1)
        self.assertEqual(session.collection_ending['kind'], READY_ENDING)
        self.assertEqual(prompts[1]['missing_requirements'], ['r2'])
        confirmed = next(row for row in prompts[1]['confirmed_progress'] if row['requirement_id'] == 'i1')
        self.assertEqual(confirmed['source'], 'host_verified_capture')
        self.assertFalse(confirmed['model_has_seen'], repr((captured_input, confirmed, session.host_input_proofs)))
        self.assertNotIn(captured_input, session.provided_observations)
        self.assertEqual(session.verified_answers['i1']['evidence'][0]['observation'], captured_input)
        event = load_json(session.goal_evidence['screenshot_completion']['path'])
        self.assertEqual({a['requirement_id'] for a in event['application']['answers']}, {'r1', 'r2', 'i1'})
        receipt_ref = session._close()
        record = {**session.record(), 'receipt': load_json(receipt_ref['path']),
                  'terminal': load_json(session.root / 'terminal.json'),
                  'boundary': load_json(session.binding['path'])}
        replay, requirements = _replay_session(record)
        verify_first_evidence_routes(record, replay)
        checks, gaps = verify_completion(replay, event['application'], requirements)
        self.assertEqual(gaps, [])
        self.assertEqual(checks, event['checks'])
        self.assertTrue(replay.host_input_proofs)
        self.assertNotIn(captured_input, replay.provided_observations)
        saved_proofs, replay.host_input_proofs = replay.host_input_proofs, []
        _, missing_proof_gaps = verify_completion(replay, event['application'], requirements)
        self.assertIn('INPUT_STATE_NOT_VERIFIED', {gap['kind'] for gap in missing_proof_gaps})
        replay.host_input_proofs = saved_proofs
        visible, gaps = verify_final_presentation(replay, checks, requirements)
        self.assertEqual(gaps, [])
        self.assertEqual({row['requirement_id'] for row in visible}, {'r1', 'r2'})
        self.assertEqual(session.goal_evidence['final_visible_evidence'], visible)
        self.assertEqual(record['terminal']['final_observation_id'], event['final_observation_id'])
        self.assertNotEqual(event['final_observation_id'], prompts[-1]['current_observation'])
        self.assertNotIn(event['final_observation_id'], replay.provided_observations)
        self.assertEqual(event['completed_at'], record['terminal']['completed_at'])
        self.assertEqual(session.first_route_status, 'deviated')
        self.assertNotIn('identity', str(prompts[1]['known_business_state']))
        self.assertNotIn('selector', str(prompts[1]['historical_evidence']))
        # Already verified reading text is retained once in confirmed_progress,
        # rather than duplicated as an additional historical region block.
        reading = next(row for row in prompts[1]['confirmed_progress'] if row['requirement_id'] == 'r1')
        self.assertEqual(reading['observed_result'], self.texts[0])
        self.assertEqual(reading['evidence'][0]['observation'], prompts[0]['current_observation'])
        self.assertTrue(reading['model_has_seen'])
        self.assertTrue(all(row['evidence_only'] for row in prompts[1]['historical_evidence']))

        # A frozen checked input presents its visible boolean state, not the
        # unrelated HTML value="on" string.
        from webcollect.screenshot_effect import input_facts
        self.surface.state['elements'][0].update(native_role='checkbox', inputable=True, visible=True)
        self.surface.state['values'][0].update(checked=True, input_type='checkbox', value_visible=False)
        await session._observe()
        current_state = load_json(session.current['evidence']['state']['path'])
        cid = self.surface.state['values'][0]['element_id']
        fact = input_facts(current_state)[cid]
        checked_requirement = [{'id': 'checked', 'kind': 'input', 'description': '保留选中状态', 'expected_checked': True}]
        checked_checks = [{'requirement_id': 'checked', 'status': 'VERIFIED',
            'evidence': [{'node': cid, 'source': fact['identity'], 'input_field': 'checked', 'actual': True}]}]
        session.final_requirement_ids = ['checked']
        shown, gaps = verify_final_presentation(session, checked_checks, checked_requirement)
        self.assertEqual(gaps, [])
        self.assertTrue(shown[0]['checked_visible'])
        self.assertNotIn('value_visible', shown[0])
        from webcollect.postprocess import planned_terminal_narrative
        checked_checks[0]['completion_mapping'] = 'bound_input_state'
        checked_checks[0]['evidence'][0]['observation_id'] = session.current['observation_id']
        checked_record = {'observations': {session.current['observation_id']: {
            'state_path': session.current['evidence']['state']['path']}}, 'trajectory': [],
            'terminal': {'goal_evidence': {'business_goal_status': 'VERIFIED',
                'checks': checked_checks, 'final_visible_evidence': shown}}}
        narrative = planned_terminal_narrative(checked_record, current_state, session.current['observation_id'])
        self.assertIn('末帧仍可见输入状态：已勾选', narrative['completion_judgement'])
        self.assertNotIn('完成时当前页面可见「已勾选」', narrative['completion_judgement'])
        checked_checks[0]['evidence'][0]['actual'] = False
        self.assertTrue(verify_final_presentation(session, checked_checks, checked_requirement)[1])

    async def test_later_same_form_input_and_submission_invalidate_old_result(self):
        sent_prompts = []

        async def choose(prompt):
            sent_prompts.append(deepcopy(prompt))
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
            'element_id': 'result', 'text': '40% 60% 80%', 'native_role': 'status',
            'element_type': 'text', 'bbox': [10, 510, 800, 560], 'visible': True,
            'enabled': True, 'inputable': False, 'clickable': False, 'parent_id': 'root'})
        formula = '本工具核算方法：输入数量先除以0.5，得到利润率百分数。'
        self.surface.state['elements'].append({
            'element_id': 'formula', 'text': formula, 'native_role': 'p',
            'element_type': 'text', 'bbox': [10, 600, 900, 650], 'visible': True,
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
        self.assertTrue(any(row['observation'] == result
                            for row in session._candidate_results()))

        # A result frame already supplied to the model is still the visual
        # evidence after a scroll removes that result from the current viewport.
        # Text-only candidates cannot replace reattaching this historical image.
        result_element = next(row for row in self.surface.state['elements']
                              if row['element_id'] == 'result')
        result_element['visible'] = False
        await session._observe()
        scrolled = session.current['observation_id']
        scroll_row = {'operation_id': 'scroll-result-away', 'action': 'scroll',
                      'arguments': {'direction': 'down'}, 'effective': True,
                      'before_observation_id': result, 'after_observation_id': scrolled}
        session.position = 3
        session.route_map = [1, 2, 3]
        session.route_frames = {3: result}
        # Capturing a previously read result leaving the viewport does not
        # itself request a new decision. It remains available for the next batch.
        self.assertIsNone(session._progress_checkpoint_reason(scroll_row))
        session.route_overrides = {'r1': [3]}
        self.assertIn(result, session.provided_observations)
        choose.max_images = 2
        visual = await session._key_evidence_visual()
        self.assertIsNotNone(visual)
        self.assertEqual(visual['observation_id'], result)
        self.assertEqual(visual['requirement_id'], 'r1')
        # Host input observations must not interrupt an accepted route before
        # its real result-producing submission. Identical paragraph captures do
        # not create an additional evidence-image batch either.
        saved_plan, saved_requirements = session.plan, session.requirements
        saved_frames, saved_map, saved_position = session.route_frames, session.route_map, session.position
        session.plan = {'steps': [{'action': 'click'}] * 4}
        session.position, session.route_map = 2, [1, 2, 3, 4]
        session.route_frames = {1: before, 2: entered}
        from webcollect.screenshot_observation import region_registry
        for oid in (before, entered):
            session.region_registries[oid] = region_registry(load_json(session.observation_records[oid]['evidence']['state']['path']))
        session.requirements = [
            {'id': 'pending-input', 'kind': 'input', 'target': {'control': 'control-0'},
             'expected_value': '999', 'description': '数量输入为999',
             'evidence_route': {'source_type': 'input_state', 'observation_steps': [1, 2]}},
            {'id': 'same-paragraph', 'kind': 'content', 'description': '阅读「人物原名」',
             'evidence_route': {'source_type': 'page_content', 'observation_steps': [1, 2]}},
            {'id': 'future-result', 'kind': 'result', 'description': '查看利润率结果',
             'evidence_route': {'source_type': 'page_result', 'observation_steps': [4]}}]
        self.assertIsNone(session._progress_checkpoint_reason(None))
        session.plan, session.requirements = saved_plan, saved_requirements
        session.route_frames, session.route_map, session.position = saved_frames, saved_map, saved_position
        result_element['visible'] = True
        self.surface.state['visible_text'] = self.surface.state['visible_text'].replace('40% 60% 80%', '')
        self.surface.state['visible_text'] += '\n利润率：\n40%\n总利息：\n60%\n总还款：\n80%'
        await session._observe()
        session.route_overrides = {}
        application = {'answers': [{'requirement_id': 'r1', 'observed_result': '40% 60% 80%',
            'evidence': [{'observation': result, 'quote': '40% 60% 80%'}]}]}
        # A region reference allows a short actual result without weakening the
        # minimum length of free-form quote anchors.
        region = next(r for r in session.region_registries[result] if '40%' in r['quote'])
        application['answers'][0]['evidence'] = [{'observation': result, 'region': region['region_id']}]
        checks, gaps = verify_completion(session, application, requirement)
        self.assertEqual(gaps, [])
        self.assertEqual(len(checks), 1)
        # Sibling values are concatenated in the semantic result node while
        # their labels remain interleaved in the page's full visible text.
        final_visible, final_gaps = verify_final_presentation(session, checks, requirement)
        self.assertEqual(final_gaps, [])
        self.assertEqual(final_visible[0]['quote'], '40% 60% 80%')
        result_element['visible'] = False
        await session._observe()
        _, final_gaps = verify_final_presentation(session, checks, requirement)
        self.assertEqual([row['kind'] for row in final_gaps], ['FINAL_RESULT_NOT_VISIBLE'])
        result_element['visible'] = True
        await session._observe()
        from webcollect.screenshot_execution import bind_plan_targets
        input_requirement = {'id': 'i1', 'kind': 'input', 'description': '数量为20',
                             'target': {'control': 'control-0'}, 'expected_value': '20'}
        bind_plan_targets({'requirements': [input_requirement]}, session.observation_records[result])
        input_application = {'answers': [{'requirement_id': 'i1', 'observed_result': '20',
                             'evidence': [{'observation': result, 'control': 'control-0'}]}]}
        input_checks, input_gaps = verify_completion(session, input_application, [input_requirement])
        self.assertEqual(input_gaps, [])
        self.assertEqual(input_checks[0]['evidence'][0]['actual'], '20')
        # A frozen, captured default may be submitted without a redundant edit.
        saved_rows, saved_requirements = session.trajectory, session.requirements
        session.trajectory = [row for row in session.trajectory if row['operation_id'] != 'input']
        session.requirements = [input_requirement, *requirement]
        default_checks, default_gaps = verify_completion(session, application, requirement)
        self.assertEqual(default_gaps, [])
        self.assertEqual(default_checks[0]['evidence'][0]['result_execution_binding']['submission']['input_refs'][0]['input_origin'], 'frozen_visible_state')
        session.requirements = [{**input_requirement, 'expected_value': '999'}, *requirement]
        _, default_gaps = verify_completion(session, application, requirement)
        self.assertIn('RESULT_INPUT_REQUIRED', {gap['kind'] for gap in default_gaps})
        session.trajectory, session.requirements = saved_rows, saved_requirements
        calculation_requirement = {'id': 'cross-check', 'kind': 'content', 'description': '核对利润率数值'}
        calculation_answer = {'requirement_id': 'cross-check', 'observed_result': '用实际输入按页面公式核算为40%，与本次结果一致',
            'evidence': [{'observation': result, 'quote': formula}],
            'calculations': [{'expression': '20 / 0.5', 'source_requirement_ids': ['i1'],
                             'result_requirement_id': 'r1', 'unit': '%'}]}
        combined = {'answers': input_application['answers'] + application['answers'] + [calculation_answer]}
        checks, gaps = verify_completion(session, combined, [input_requirement, *requirement, calculation_requirement])
        self.assertEqual(gaps, [])
        self.assertEqual(checks[-1]['calculations'][0]['computed_value'], 40)
        self.assertNotIn('expected_value', checks[-1]['calculations'][0])
        invalid = deepcopy(combined)
        invalid['answers'][-1]['calculations'][0]['expression'] = '20 / 0.6'
        _, gaps = verify_completion(session, invalid, [input_requirement, *requirement, calculation_requirement])
        self.assertIn('UNCITED_OPERAND', {gap['kind'] for gap in gaps})
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
            self.assertFalse(any(item['observation'] == result
                                 for item in session._candidate_results()))
            historical = [{**requirement[0], 'evidence_scope': 'historical'}]
            historical_checks, historical_gaps = verify_completion(session, application, historical)
            self.assertEqual(historical_gaps, [])
            self.assertEqual(len(historical_checks), 1)
            session.trajectory.pop()

        # An executed-route key frame the model never saw is attached as one
        # historical supplement (SSD 3.3): verifiable, evidence-only, and it
        # never rebinds current dispatch targets. The image limit keeps the
        # current viewport mandatory.
        session.route_map = [1, 2, 3]
        session.route_frames = {2: entered, 3: result}
        session.position = 2
        session.requirements.append({'id': 'r2', 'kind': 'content',
            'description': '阅读页面的公式说明', 'evidence_route': {
                'source_type': 'page_content', 'observation_steps': [2]}})
        choose.max_images = 2
        visual = await session._key_evidence_visual()
        self.assertIsNotNone(visual)
        self.assertEqual(visual['observation_id'], entered)
        choose.max_images = 1
        limited_prompt = session._branch_prompt('history_capacity')
        await session._decide(limited_prompt)
        limited_prompt = sent_prompts[-1]
        self.assertEqual(limited_prompt['history_supplement_unavailable']['kind'], 'IMAGE_LIMIT')
        self.assertEqual(len(limited_prompt['_images']), 1)
        choose.max_images = 2
        prompt = session._branch_prompt('result')
        self.assertTrue(any('40%' in row['text'] for row in prompt['candidate_results']))
        await session._decide(prompt)
        prompt = sent_prompts[-1]
        self.assertEqual(prompt['screenshots'][0], session.current['observation_id'])
        self.assertIn(entered, prompt['screenshots'])
        self.assertIn(entered, session.provided_observations)
        historical = next(row for row in prompt['visual_evidence'] if row['observation_id'] == entered)
        from webcollect.screenshot_observation import verify_visuals
        self.assertEqual(verify_visuals(session.observation_records[entered], [historical]),
                         [historical['path']])
        # Controls in the request all belong to the current frame; the historical
        # observation is referenceable as evidence, never as a dispatch target.
        self.assertTrue(all(row['control'] in session.current['controls'] for row in prompt['controls']))
        observation_enum = prompt['tools'][0]['function']['parameters']['properties']['answers'][
            'items']['properties']['evidence']['items']['properties']['observation']['enum']
        self.assertIn(entered, observation_enum)
        self.assertEqual(session._bind_target({'target': {'control': 'submit', '_source': {
            'observation_id': entered, 'document_identity': 'another-document',
            'control_id': 'submit', 'binding': {}, 'text': '计算', 'role': 'button', 'labels': []}}}), [])

        # The same causal contract applies to visible text values, not textarea
        # placeholder text. Exercise the existing invalidation contract on this
        # carrier as well as the numeric status above.
        from webcollect.result_execution import result_execution_binding, visible_result_texts
        self.surface.state['values'][0]['value'] = 'hello world'
        self.surface.state['elements'].append({'element_id': 'converted', 'text': '结果将在这里显示',
            'native_role': 'textarea', 'element_type': 'input', 'bbox': [20, 300, 700, 360],
            'visible': True, 'enabled': True, 'inputable': True, 'clickable': True, 'parent_id': 'root'})
        self.surface.state['capture_controls'].append({'element_id': 'converted', 'selector': '#converted',
            'tag': 'textarea', 'index': 0, 'form_selector': '#calculator'})
        self.surface.state['values'].append({'element_id': 'converted', 'value': '旧输出',
            'display_value': '旧输出', 'value_visible': True})
        await session._observe()
        text_before = session.current['observation_id']
        self.surface.state['values'][0]['value'] = 'new text'
        self.surface.state['values'][-1].update(value='NEW TEXT', display_value='NEW TEXT')
        await session._observe()
        text_after = session.current['observation_id']
        session.trajectory.append({'operation_id': 'text-input', 'action': 'type', 'arguments': {'text': 'new text'},
            'target': {'control_id': 'control-0'}, 'before_observation_id': text_before,
            'after_observation_id': text_after, 'effective': True})
        input_req = {'id': 'text-input', 'kind': 'input', 'description': '转换指定文本',
            'target': {'control': 'control-0'}, 'expected_value': 'new text'}
        text_req = {'id': 'text-result', 'kind': 'result', 'description': '查看转换后的文本',
            'result_kind': 'input_conversion', 'target': {'control': 'converted'},
            'evidence_route': {'source_type': 'page_result', 'depends_on': ['text-input'], 'observation_steps': [1]}}
        session._controls()
        bind_plan_targets({'requirements': [input_req, text_req]}, session.current)
        session.requirements = [input_req, text_req]
        session.provided_observations.add(text_after)
        text_answer = {'answers': [{'requirement_id': 'text-result', 'observed_result': 'NEW TEXT',
            'evidence': [{'observation': text_after, 'control': 'converted'}]}]}
        converted = next(n for n in self.surface.state['elements'] if n['element_id'] == 'converted')
        state = load_json(session.current['evidence']['state']['path'])
        self.assertEqual(visible_result_texts(state, converted), ['NEW TEXT'])
        self.assertEqual(result_execution_binding(session, text_after, state, converted)['mechanism'], 'edit')
        self.assertTrue(any(r['requirement_id'] == 'text-result' for r in session._valid_result_rows(text_after)))
        text_checks, text_gaps = verify_completion(session, text_answer, [text_req])
        self.assertEqual(text_gaps, [])
        self.assertEqual(verify_final_presentation(session, text_checks, [text_req])[1], [])
        # Frozen dependency mismatch cannot accept a different stage's output.
        session.requirements[0]['expected_value'] = 'other stage'
        self.assertEqual(verify_completion(session, text_answer, [text_req])[0], [])
        session.requirements[0]['expected_value'] = 'new text'
        hidden = deepcopy(state)
        hidden['values'][-1]['value_visible'] = False
        self.assertEqual(visible_result_texts(hidden, converted), [])
        self.assertIsNone(result_execution_binding(session, text_after, hidden, converted))
        # A visible copied input and an unchanged old output are not conversions.
        self.surface.state['values'][-1].update(value='new text', display_value='new text')
        await session._observe()
        echo = session.current['observation_id']
        session.trajectory[-1]['after_observation_id'] = echo
        echo_state = load_json(session.current['evidence']['state']['path'])
        self.assertIsNone(result_execution_binding(session, echo, echo_state, converted))
        self.surface.state['values'][-1].update(value='NEW TEXT', display_value='NEW TEXT')
        await session._observe()
        button_result = session.current['observation_id']
        session.trajectory.append({'operation_id': 'text-convert-submit', 'action': 'click', 'arguments': {},
            'target': {'control_id': 'submit'}, 'before_observation_id': echo,
            'after_observation_id': button_result, 'effective': True})
        session.provided_observations.add(button_result)
        state = load_json(session.current['evidence']['state']['path'])
        self.assertEqual(result_execution_binding(session, button_result, state, converted)['mechanism'], 'submit')
        # Default result obligations use the same visible value and causality;
        # they do not require guessing a distinct automatic-conversion kind.
        default_text_req = {**text_req, 'result_kind': 'calculation'}
        default_text_req.pop('target')
        text_answer['answers'][0]['evidence'][0]['observation'] = button_result
        checks, gaps = verify_completion(session, text_answer, [default_text_req])
        self.assertEqual(gaps, [])
        self.assertEqual(verify_final_presentation(session, checks, [default_text_req])[1], [])

        # A matching element ID/text is insufficient when the output binding
        # has changed. Current relevant errors also invalidate stale output;
        # errors in an independent form do not.
        output_binding = self.surface.state['capture_controls'][-1]
        output_binding['selector'] = '#unrelated-output'
        await session._observe()
        current_state = load_json(session.current['evidence']['state']['path'])
        self.assertIsNone(result_execution_binding(session, session.current['observation_id'], current_state, converted))
        output_binding['selector'] = '#converted'
        self.surface.state['capture_controls'][0]['validation_message'] = '输入错误'
        await session._observe()
        current_state = load_json(session.current['evidence']['state']['path'])
        self.assertIsNone(result_execution_binding(session, session.current['observation_id'], current_state, converted))
        self.surface.state['capture_controls'][0].pop('validation_message')
        self.surface.state['elements'].append({'element_id': 'unrelated-error', 'text': '输入错误',
            'native_role': 'input', 'visible': True, 'bbox': [10, 600, 100, 630]})
        self.surface.state['capture_controls'].append({'element_id': 'unrelated-error', 'tag': 'input',
            'selector': '#other-error', 'form_selector': '#other', 'validation_message': '输入错误'})
        await session._observe()
        current_state = load_json(session.current['evidence']['state']['path'])
        self.assertIsNotNone(result_execution_binding(session, session.current['observation_id'], current_state, converted))

        # Enter may submit and normalize its input in one real dispatch. The
        # submit obligation is fulfilled even though an edit is also observed.
        enter_before = session.current['observation_id']
        self.surface.state['values'][0]['value'] = 'New text'
        self.surface.state['values'][-1].update(value='ENTER RESULT', display_value='ENTER RESULT')
        await session._observe()
        enter_after = session.current['observation_id']
        session.trajectory.append({'operation_id': 'enter-submit', 'action': 'hotkey', 'arguments': {'keys': ['enter']},
            'target': {'control_id': 'control-0'}, 'before_observation_id': enter_before,
            'after_observation_id': enter_after, 'effective': True})
        session.working_goal = '输入文本后按下Enter提交转换'
        current_state = load_json(session.current['evidence']['state']['path'])
        self.assertEqual(result_execution_binding(session, enter_after, current_state, converted)['mechanism'], 'submit')
        from webcollect.screenshot_plan import explicit_submission_required
        self.assertTrue(explicit_submission_required(session))
        session.working_goal = '查看点击率计算结果'
        self.assertFalse(explicit_submission_required(session))
        session.working_goal = '点击目录，阅读计算方法'
        self.assertFalse(explicit_submission_required(session))

    async def test_valid_complete_wins_at_stall_threshold(self):
        async def choose(prompt):
            return {'arguments': {'decision': 'complete', 'reason': '可见事实已完整',
                'answers': [self._answer(prompt['current_observation'], 0)]}}

        session = await self._session(choose, [{'id': 'r1', 'kind': 'content', 'description': '阅读文章并回答人物原名'}])
        session._stall_marker = session._stall_progress_marker()
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
        # The accepted first plan already received this frame. Its first text
        # read is part of the baseline, before simulating a no-effect dispatch.
        session.provided_observations.add(session.current['observation_id'])
        session._stall_marker = session._stall_progress_marker()
        before_refresh = session._stall_marker
        self.surface.state['elements'].append({**self.surface.state['elements'][-1],
            'element_id': 'live-advertisement', 'text': '广告倒计时变化，不是任务证据'})
        await session._observe()
        self.assertEqual(before_refresh, session._stall_progress_marker())
        session._stall_seen_markers.add(session._stall_marker)
        session._stall_count = NO_PROGRESS_STALL_LIMIT - 1
        session.actual_dispatches += 1  # Dispatched without an established effect.
        session.position = 1          # Cursor bookkeeping is not business progress.
        await session._checkpoint('action_not_established')
        self.assertEqual(session.collection_ending['kind'], 'NO_PROGRESS_END')
        self.assertEqual(session.trajectory, [])
        self.assertEqual(calls, 0)  # Already stalled facts close before provider IO.
        # A business-attempt-shaped rejection is not a dispatch. Continue must
        # preserve this pending step, and repeated identical questions close
        # before issuing another provider request.
        no_dispatch_calls = 0
        refusal_prompts = []

        async def continue_pending(prompt):
            nonlocal no_dispatch_calls
            no_dispatch_calls += 1
            refusal_prompts.append(deepcopy(prompt))
            self.assertIn('pending_steps', prompt)
            self.assertNotIn('remaining_plan', prompt)
            return {'arguments': {'decision': 'continue', 'reason': '保留当前未派发动作'}}

        undispatched = await self._session(continue_pending, name='S000001_sample_000206')
        undispatched.provided_observations.add(undispatched.current['observation_id'])

        async def reject_before_dispatch(arguments):
            return {'status': 'rejected', 'summary': 'NOT_DISPATCHED: synthetic permission refusal',
                    'error': {'code': 'SYNTHETIC_PERMISSION'}, 'data': {'control_id': 'control-0'}}

        undispatched._tool_act = reject_before_dispatch
        self.assertFalse(undispatched._checkpoint_needed(
            {'action': 'scroll'}, [], {'status': 'ok'}, {'outcome': 'VERIFIED'}))
        await undispatched._execute_round()
        self.assertEqual((undispatched.position, undispatched.actual_dispatches), (0, 0))
        self.assertEqual(undispatched.trajectory, [])
        self.assertEqual(no_dispatch_calls, 1)
        refusal = refusal_prompts[-1]['checkpoint_feedback']
        self.assertEqual(refusal['message'], 'NOT_DISPATCHED: synthetic permission refusal')
        self.assertEqual(refusal['code'], 'SYNTHETIC_PERMISSION')
        self.assertEqual(refusal['data'], {'control_id': 'control-0'})
        self.assertFalse(refusal['business_attempt_created'])
        self.assertFalse(refusal_prompts[-1]['latest_attempt_is_current_step'])
        self.assertEqual(refusal_prompts[-1]['call_purpose'], 'route_deviation')
        await undispatched._checkpoint('step_execution_refused', feedback=refusal)
        self.assertEqual(no_dispatch_calls, 1)
        self.assertEqual(undispatched.collection_ending['kind'], 'NO_PROGRESS_END')

        # A completed wait is a real route operation despite having no GUI
        # dispatch and contributing zero effective business steps.
        waited = await self._session(continue_pending, name='S000001_sample_000207')
        waited.plan['steps'] = [{'action': 'wait', 'duration_ms': 1},
                               {'action': 'wait', 'duration_ms': 1}]

        async def completed_wait(arguments):
            return {'status': 'ok', 'data': {'wait_executed': True,
                    'actual_actions_delta': 0, 'effective_steps_delta': 0}}

        waited._tool_act = completed_wait
        await waited._execute_round()
        self.assertEqual((waited.position, waited.actual_dispatches), (1, 0))
        self.assertEqual(waited.trajectory, [])

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

        # 完成缺项投影纳入停滞核算：缺项减少是真实展示进展；同缺项的重复
        # complete 仍在第二次有界结束（SSD 2026-11-12 收口计划 B.2）。
        fresh = await self._session(choose, name='S000001_sample_000202')
        fresh.provided_observations.add(fresh.current['observation_id'])
        fresh._completion_gap_projection = (('FINAL_RESULT_NOT_VISIBLE', 'r1'),
                                            ('FINAL_RESULT_NOT_VISIBLE', 'r2'))
        fresh._stall_check({'decision': 'complete'}, None)
        fresh._completion_gap_projection = (('FINAL_RESULT_NOT_VISIBLE', 'r2'),)
        fresh._stall_check({'decision': 'complete'}, None)
        self.assertIsNone(getattr(fresh, 'collection_ending', None))
        fresh._stall_check({'decision': 'complete'}, None)
        self.assertEqual(fresh.collection_ending['kind'], 'NO_PROGRESS_END')

        # 必要定位许可：展示定位只允许确定不改变已核验事实的首步；编辑、提交、
        # 焦点按键与离开文档的导航不放行；点击只按明确展示控件事实判定。
        self.surface.state['elements'].append({
            'element_id': 'submit', 'text': '计算', 'native_role': 'button',
            'element_type': 'button', 'bbox': [10, 450, 210, 490], 'visible': True,
            'enabled': True, 'clickable': True, 'inputable': False, 'parent_id': 'root'})
        self.surface.state['capture_controls'].append({'element_id': 'submit',
            'selector': '#submit', 'tag': 'button', 'input_type': 'submit',
            'form_selector': '#calculator'})
        positioned = await self._session(choose, name='S000001_sample_000203')
        # 生产顺序：revise 接受前已 _bind_targets_feedback，target 带 _source。
        from webcollect.screenshot_execution import bind_plan_targets
        click_input = [{'action': 'click', 'target': {'control': 'control-0'}}]
        retype = [{'action': 'type', 'target': {'control': 'control-0'}, 'value': '6'}]
        submit_click = [{'action': 'click', 'target': {'control': 'submit'}}]
        for bound in (click_input, retype, submit_click):
            bind_plan_targets({'steps': bound}, positioned.current)
        self.assertTrue(positioned._presentation_repair_permitted(
            [{'action': 'scroll', 'direction': 'up'}]))
        self.assertTrue(positioned._presentation_repair_permitted(
            [{'action': 'wait', 'duration_ms': 1}]))
        self.assertFalse(positioned._presentation_repair_permitted(click_input))
        self.assertFalse(positioned._presentation_repair_permitted(
            [{'action': 'hotkey', 'keys': ['home']}]))
        self.assertFalse(positioned._presentation_repair_permitted(retype))
        self.assertFalse(positioned._presentation_repair_permitted(submit_click))
        self.assertFalse(positioned._presentation_repair_permitted(
            [{'action': 'hotkey', 'keys': ['enter']}]))
        self.assertFalse(positioned._presentation_repair_permitted(
            [{'action': 'hotkey', 'keys': ['ctrl', 'a'], 'target': {'control': 'control-0'}}]))
        self.assertFalse(positioned._presentation_repair_permitted(
            [{'action': 'open_url', 'page_id': 'p2'}]))
        self.assertFalse(positioned._presentation_repair_permitted([]))

        # Only an exact, visible HTML-dialog close button can finish a pure
        # reading presentation repair; account actions remain forbidden.
        self.surface.state['elements'].extend([
            {'element_id': 'reading-dialog', 'native_role': 'dialog', 'text': '条目详情',
             'bbox': [100, 100, 900, 700], 'visible': True, 'parent_id': 'root'},
            {'element_id': 'dialog-close', 'native_role': 'button', 'text': '关闭',
             'element_type': 'button', 'bbox': [800, 120, 860, 160], 'visible': True,
             'enabled': True, 'clickable': True, 'inputable': False,
             'parent_id': 'reading-dialog'}])
        self.surface.state['capture_controls'].append({'element_id': 'dialog-close',
            'selector': '#dialog-close', 'tag': 'button', 'input_type': 'button'})
        await positioned._observe()
        close = [{'action': 'click', 'target': {'control': 'dialog-close'}}]
        positioned._controls()
        bind_plan_targets({'steps': close}, positioned.current)
        self.assertTrue(positioned._presentation_repair_permitted(close))
        close_element = positioned.current['controls']['dialog-close']['element']
        close_element['text'] = '关闭账户'
        self.assertFalse(positioned._presentation_repair_permitted(close))
        close_element['text'] = '关闭'
        close_element['parent_id'] = 'root'
        self.assertFalse(positioned._presentation_repair_permitted(close))

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
        self.assertEqual(narrative_grounding_gaps([{'rationale': '看到「搜索结果…下一页」'}], frame), [])
        self.assertEqual(narrative_grounding_gaps([{'rationale': '看到「搜索结果…不存在」'}], frame)[0]['missing_fragment'], '不存在')
        # Selected native display text is visible evidence; raw option values,
        # unselected options and concatenated labels are not visible quotes.
        from types import SimpleNamespace
        from webcollect.result_execution import visible_control_texts
        state={'visible_text':'正文','elements':[{'element_id':'choice','native_role':'select','visible':True}],
            'capture_controls':[{'element_id':'choice','tag':'select','options':[{'value':'0','label':'精准'},{'value':'1','label':'拆分'}]}],
            'values':[{'element_id':'choice','value':'0','display_value':'精准','value_visible':True}]}
        path=self.root/'selected-display.json';path.write_text(__import__('json').dumps(state))
        fake=SimpleNamespace(current={'evidence':{'state':{'path':str(path)}}})
        visible=ScreenshotPlanSession._frame_text(fake)
        self.assertIn('精准',visible);self.assertNotIn('拆分',visible)
        self.assertEqual(visible_control_texts(state,state['elements'][0]),['精准'])
        self.assertEqual(narrative_grounding_gaps([{'rationale':'当前选中「精准」'}],visible),[])
        self.assertEqual(narrative_grounding_gaps([{'rationale':'当前显示「精准/拆分」'}],visible)[0]['quote'],'精准/拆分')
        state['values'][0]['value_visible']=False
        self.assertEqual(visible_control_texts(state,state['elements'][0]),[])

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
        region = next(r for r in session.region_registries[oid] if r['quote'] == self.texts[0])
        combined = answers(self.texts[0])
        combined['answers'][0]['evidence'][0].update(region=region['region_id'], quote='拼接标签 ' + self.texts[0])
        _, gaps = verify_completion(session, combined, requirement)
        self.assertEqual(gaps[0]['kind'], 'EVIDENCE_QUOTE_NOT_IN_REGION')
        self.assertIn(self.texts[0], gaps[0]['available_quotes'])

        # Inline links split element text; the clipped paragraph still proves
        # the full sentence, while hidden sentence suffixes remain inadmissible.
        body = next(row for row in self.surface.state['elements'] if row['element_id'] == 'body-0')
        body['text'] = '这篇文章记载人物原名为'
        self.surface.state['visible_text'] += '\n' + self.texts[0]
        self.surface.state['text_blocks'] = [{'element_id': 'body-0',
            'visible_text': self.texts[0], 'complete_sentences': [self.texts[0], self.texts[0] + '隐藏尾句']}]
        await session._observe()
        await session._decide(session._branch_prompt('inline_reading'))
        oid = session.current['observation_id']
        checks, gaps = verify_completion(session, answers(self.texts[0]), requirement)
        self.assertEqual(gaps, [])
        visible, gaps = verify_final_presentation(session, checks, requirement)
        self.assertEqual(gaps, [])
        self.assertEqual(visible[0]['quote'], self.texts[0])
        _, gaps = verify_completion(session, answers(self.texts[0] + '隐藏尾句'), requirement)
        self.assertIn('OBSERVED_RESULT_NOT_VERBATIM', [row['kind'] for row in gaps])
        reading = [{**requirement[0], 'description': '阅读并核对人物资料数量'}]
        _, gaps = verify_completion(session, answers(self.texts[0]), reading)
        self.assertEqual(gaps, [])
        derived = [{**reading[0], 'evidence_route': {'source_type': 'derived_check'}}]
        _, gaps = verify_completion(session, answers(self.texts[0]), derived)
        self.assertIn('CALCULATION_REQUIRED', [row['kind'] for row in gaps])
        # An explicit independent-derivation obligation still demands arithmetic;
        # mere “计算并核对” wording is page-output confirmation (SSD 3.5).
        _, gaps = verify_completion(session, answers(self.texts[0]), [
            {**reading[0], 'description': '根据数量验算并核对换算过程'}])
        self.assertIn('CALCULATION_REQUIRED', [row['kind'] for row in gaps])
        _, gaps = verify_completion(session, answers(self.texts[0]), [
            {**reading[0], 'description': '根据数量计算并核对体积'}])
        self.assertEqual(gaps, [])

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

        # 首屏只拒绝确定的首步重复输入；标题/局部引文不能证明滚动多余
        # 或正文目标完成。计划接受与完成核验分别断言，不派发业务动作。
        async def first_plan(plan, name):
            root = self.root / 'evidence' / name
            plan = deepcopy(plan)

            async def submit(prompt):
                return {'arguments': deepcopy(plan)}

            fresh = ScreenshotPlanSession(self.task, root / 'raw', submit, self.page,
                                          steps_directory=root, attempt_id=name.lower())
            await fresh._open_entry()
            for requirement in plan.get('requirements', []):
                for anchor in requirement.get('evidence_route', {}).get('existing_evidence', []):
                    if anchor.get('observation') == '首帧':
                        anchor['observation'] = fresh.current['observation_id']
            # A single-image request cannot send an overview. It must never
            # perform its optional second live observation before the model.
            from unittest.mock import AsyncMock, patch
            submit.max_images = 1
            with patch('webcollect.browser.observe', new_callable=AsyncMock,
                       side_effect=AssertionError('single-image overview must not observe')) as optional:
                await fresh._first_plan_round()
            optional.assert_not_awaited()
            return fresh

        redundant_plan = {
            'goal': '修改成本为20并查看利润率',
            'final_presentation_step': 5,
            'requirements': [{'id': 'r1', 'kind': 'result', 'description': '查看本次利润率结果',
                              'evidence_route': {'source_type': 'page_result', 'observation_steps': [5]}}],
            'steps': [
                {'action': 'type', 'target': {'control': 'control-0'}, 'value': '10',
                 'expected_value': '10', 'purpose': '重复输入数量框已有值',
                 'rationale': '数量框当前已显示该值', 'expected_result': '数量仍为原值'},
                {'action': 'scroll', 'direction': 'down', 'purpose': '滚动查看「数量」与「成本」',
                 'rationale': '核对输入区当前状态',
                 'expected_result': '「这里查看当前输入内容与页面状态。」进入视口'},
                {'action': 'click', 'target': {'control': 'control-1'}, 'purpose': '聚焦成本输入框',
                 'rationale': '成本需要输入新值', 'expected_result': '成本输入框获得焦点'},
                {'action': 'hotkey', 'keys': ['ctrl', 'a'], 'target': {'control': 'control-1'},
                 'purpose': '全选成本原值', 'rationale': '替换前需要全选', 'expected_result': '原值被选中'},
                {'action': 'type', 'target': {'control': 'control-1'}, 'value': '20',
                 'expected_value': '20', 'purpose': '输入成本20',
                 'rationale': '本次计算使用成本20', 'expected_result': '成本显示为20'}]}
        rejected = await first_plan(redundant_plan, 'S000001_sample_000204')
        self.assertEqual(rejected.initial_feedback['kind'], 'FIRST_FRAME_REDUNDANT_STEPS')
        self.assertEqual([row['step_index'] for row in rejected.initial_feedback['redundant']], [0])
        self.assertEqual(rejected.initial_feedback['effective_business'], 4)
        self.assertIsNone(rejected.plan)
        self.assertIsNone(getattr(rejected, 'collection_ending', None))

        anchored_plan = {
            'goal': '确认数量默认值并阅读页面说明',
            'final_presentation_step': 2,
            'requirements': [
                {'id': 'i1', 'kind': 'input', 'description': '数量保持默认10',
                 'target': {'control': 'control-0'}, 'expected_value': '10',
                 'evidence_route': {'source_type': 'input_state', 'observation_steps': [1]}},
                {'id': 'c1', 'kind': 'content', 'description': '阅读页面状态说明',
                 'evidence_route': {'source_type': 'page_content',
                                    'existing_evidence': [{'observation': '首帧',
                                        'quote': '这里查看当前输入内容与页面状态。'}]}}],
            'steps': [
                {'action': 'click', 'target': {'control': 'control-0'}, 'purpose': '聚焦数量输入框',
                 'rationale': '确认默认值需要聚焦', 'expected_result': '数量输入框获得焦点'},
                {'action': 'click', 'target': {'control': 'control-1'}, 'purpose': '聚焦成本输入框',
                 'rationale': '核对另一输入', 'expected_result': '成本输入框获得焦点'},
                {'action': 'hotkey', 'keys': ['ctrl', 'a'], 'target': {'control': 'control-1'},
                 'purpose': '全选成本', 'rationale': '准备核对', 'expected_result': '成本原值被选中'},
                {'action': 'type', 'target': {'control': 'control-1'}, 'value': '10',
                 'expected_value': '10', 'purpose': '成本保持原值',
                 'rationale': '成本当前已是该值', 'expected_result': '成本仍为原值'},
                {'action': 'scroll', 'direction': 'down', 'purpose': '滚动阅读页面说明',
                 'rationale': '说明在页面下方', 'expected_result': '说明文字进入视口'}]}
        anchored = await first_plan(anchored_plan, 'S000001_sample_000205')
        self.assertIsNone(anchored.initial_feedback)
        self.assertIsNotNone(anchored.plan)
        self.assertEqual(len(anchored.plan['steps']), 5)
        self.assertEqual(anchored.verified_checks, {})
        self.assertFalse(anchored._goal_ready())
        self.assertEqual(anchored.actual_dispatches, 0)
