"""Disposable native ReAct fixtures: no network, real gateway, or production data."""
import asyncio
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from test_react_session import ReactHarness, Script, decide, act_step
from webcollect.batch_core import load_json, file_sha, OutcomeUnknown
from webcollect.react_session import (ReactSession, build_url_task, validate_task, struct_goal,
                                     GOAL_BUDGETS, LEGACY_BUDGETS, REACT_VERSION, react_chooser)
from webcollect.react_protocol import VERSION, SYSTEM, native_tools, native_decision, atomic_effect
from webcollect.postprocess import session_record, effective_trajectory, process, terminal_outcome


def native(build, cid):
    def result(prompt):
        decision = build(prompt)
        args = {**decision['tool_call']['arguments'], 'goal_update': decision['goal_update'],
                'decision_summary': decision['decision_summary']}
        name = decision['tool_call']['name']
        return {'name': name, 'arguments': args, 'tool_call_id': cid,
                'assistant_message': {'role': 'assistant', 'content': None,
                    'reasoning_content': 'opaque-protocol-private',
                    'tool_calls': [{'id': cid, 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]},
                'user_message': {'role': 'user', 'content': [
                    {'type': 'text', 'text': 'actual sent current observation'},
                    {'type': 'image_url', 'image_url': {'url': prompt['observation']['image_ref']}}]}}
    return result


def finish(reason='ready', summary='当前连续片段结束'):
    return decide(tool='finish', arguments=lambda p: {
        'observation_id': p['observation']['observation_id'], 'stop_reason': reason,
        'summary': summary, 'evidence_refs': [p['observation']['observation_id']]})


def scroll(goal=None):
    return decide(goal=goal, tool='act', arguments=lambda p: {
        'observation_id': p['observation']['observation_id'],
        'step': act_step('scroll', direction='down', goal='查看下方内容', expected='视口下移')})


class NativeSessionTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.task = build_url_task(url=self.page.url, task_version='native-fixture')
        self.ids = {'sample_id': 'S000001_sample_000001', 'site_id': 'S000001',
                    'batch_id': 'B20261031_001', 'attempt_id': 'synthetic-attempt'}
        self.manifest = {'batch_id': 'B20261031_001', 'sample_kind': 'real', 'program_version': 't',
                         'rule_version': '1.0.0', 'sites': [{'site_id': 'S000001',
                          'uri': self.task['site_uri'], 'site_category': self.task['site_category']}],
                         'samples': [self.ids['sample_id']]}

    def recorded(self, builds, name='native'):
        evidence = self.root / name / 'evidence' / self.ids['sample_id']
        script = Script([native(build, f'tc{i}') for i, build in enumerate(builds)])
        return ReactSession(self.task, evidence / 'raw', script, self.page,
                            steps_directory=evidence), evidence, script

    async def test_native_tool_round_trip_filters_permissions_keeps_private_history(self):
        self.task = build_url_task(url=self.page.url, task_version='n', allowed_actions=['scroll'])
        session, evidence, script = self.recorded([scroll('查看页面下方内容'), finish()])
        result = await session.run()
        self.assertEqual(result['effective_steps'], 1)
        self.assertEqual(result['stop_reason'], 'ready')
        self.assertEqual(len(self.surface.executed), 1)
        prompt = script.prompts[1]
        self.assertEqual(prompt['system'], SYSTEM)
        self.assertEqual(prompt['observation']['page_actions'], ['scroll'])
        self.assertEqual([m['role'] for m in prompt['_history']], ['user', 'assistant', 'tool'])
        self.assertEqual(prompt['_history'][1]['reasoning_content'], 'opaque-protocol-private')
        self.assertEqual(prompt['_history'][2]['tool_call_id'], 'tc0')
        feedback = json.loads(prompt['_history'][2]['content'])
        self.assertEqual(feedback['data']['effective_steps_delta'], 1)
        self.assertIn('actual_change', prompt['trajectory'][-1])
        # Opaque protocol fields are confined to transport history, not ordinary journals.
        for path in (evidence / 'raw').glob('*.json'):
            self.assertNotIn('opaque-protocol-private', path.read_text())
        self.assertTrue(result['short_flow'])
        self.assertIn('实际完成1个', result['short_flow_reason'])

    async def test_entry_observation_reused_without_navigation_and_invalid_refreshed(self):
        captured = await self.surface.capture(self.page)
        entry = {'captured': captured, 'html': await self.page.content()}
        for invalid in (False, True):
            supplied = deepcopy(entry)
            if invalid:
                supplied['captured']['capture']['screenshot_sha256'] = 'bad'
            session, _, _ = self.recorded([finish('no_path')], name='entry-' + str(invalid))
            session.entry_observation = supplied
            session.preflight = preflight = unittest.mock.AsyncMock(return_value={})
            with patch.object(self.page, 'goto', side_effect=AssertionError('must reuse claimed Page')):
                await session.run()
            preflight.assert_awaited_once()
            first = session.observation_records[session.observations[0]]
            self.assertTrue(first['capture_verified'])
            self.assertIs(session.page, self.page)

    async def test_native_protocol_failures_never_dispatch(self):
        valid = native(scroll('查看页面下方内容'), 'tc0')
        def change(kind):
            def build(prompt):
                response = valid(prompt)
                if kind == 'content':
                    response['assistant_message'].pop('tool_calls')
                elif kind == 'many':
                    response['assistant_message']['tool_calls'] *= 2
                elif kind == 'wrong':
                    response['name'] = 'rogue'
                elif kind == 'flat':
                    response['arguments']['action'] = 'scroll'
                elif kind == 'empty-id':
                    response['tool_call_id'] = ''
                return response
            return build
        for kind in ('content', 'many', 'wrong', 'flat', 'empty-id'):
            session = self.session(Script([change(kind), native(finish('no_path'), 'tc1')]), name=kind)
            result = await session.run()
            self.assertEqual(result['effective_steps'], 0, kind)
            self.assertEqual(self.surface.executed, [], kind)
            self.assertFalse(result['unknown'], kind)

    async def test_cancellation_seals_dispatched_unknown_and_propagates(self):
        session, evidence, _ = self.recorded([scroll('查看页面下方内容')])
        async def cancel(*args, **kwargs):
            raise asyncio.CancelledError()
        with patch('webcollect.browser.execute', side_effect=cancel):
            with self.assertRaises(asyncio.CancelledError):
                await session.run()
        self.assertTrue((evidence / 'raw/raw-receipt.json').is_file())
        terminal = load_json(evidence / 'raw/terminal.json')
        self.assertTrue(terminal['unknown'])
        raw = load_json(evidence / 'step_001.json')
        self.assertTrue(raw['dispatched'])
        self.assertIsNone(raw['action_executed'])
        self.assertEqual(terminal['effective_steps'], 0)

    async def test_compound_atomic_count_and_automatic_short_flow_derivation(self):
        session, evidence, _ = self.recorded([
            decide(tool='observe', arguments={'focus_control_id': 'control-0'}),
            decide(goal='修改数量字段并查看结果', tool='act', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'],
                'step': act_step('set_value', control_id='control-0', value='20')}), finish()])
        result = await session.run()
        self.assertEqual(result['effective_steps'], 3, result)
        record = session_record(evidence / 'raw')
        self.assertEqual(len(effective_trajectory(record)), 3)
        # Program derives short_flow even if an untrusted label says otherwise.
        record['terminal'].update(short_flow=False, short_flow_reason=None)
        from webcollect.postprocess import derive
        delivery = self.root / 'sample' / self.ids['sample_id']
        derived = derive(self.task, record, delivery, self.ids, self.manifest)
        self.assertEqual(derived['status'], 'derived', derived)
        annotation = load_json(delivery / 'annotation.json')
        self.assertTrue(annotation['short_flow'])
        self.assertIn('实际完成3个', annotation['short_flow_reason'])
        self.assertEqual(annotation['completion_status'], 'success')
        self.assertNotIn('opaque-protocol-private', json.dumps(annotation))
        self.assertEqual(len(annotation['steps']), 4)
        self.assertIn('ctrl+a', [step['action']['input_text'] for step in annotation['steps']])
        with self.assertRaises(FileExistsError):
            derive(self.task, record, delivery, self.ids, self.manifest)

    async def test_five_actions_regular_and_zero_actions_raw_only(self):
        for count in (0, 4, 5, 11):
            session, evidence, _ = self.recorded(
                [scroll('查看页面下方内容' if i == 0 else None) for i in range(count)] + [finish()],
                name='length-' + str(count))
            result = await session.run()
            self.assertEqual(result['effective_steps'], count, result)
            record = session_record(evidence / 'raw')
            self.assertEqual(len(effective_trajectory(record)), count)
            derived = process(evidence, self.root / ('derived-' + str(count)) / self.ids['sample_id'],
                              self.ids, self.manifest)
            if count == 0:
                self.assertEqual(derived['status'], 'no_actions')
                self.assertFalse((self.root / 'derived-0').exists())
            else:
                self.assertEqual(derived['status'], 'derived_saved', derived)
                annotation = load_json(self.root / ('derived-' + str(count)) / self.ids['sample_id'] / 'annotation.json')
                self.assertEqual(annotation.get('short_flow', False), count < 5)

    async def test_native_recounts_unique_dispatch_rejects_gap_unknown_and_raw_mutation(self):
        session, evidence, _ = self.recorded([scroll('查看页面下方内容'), scroll(), finish()])
        await session.run()
        record = session_record(evidence / 'raw')
        duplicate = deepcopy(record)
        duplicate['trajectory'].append(deepcopy(duplicate['trajectory'][-1]))
        self.assertEqual(len(effective_trajectory(duplicate)), 2)
        gap = deepcopy(record)
        gap['trajectory'][1]['before_observation_id'] = gap['trajectory'][0]['before_observation_id']
        with self.assertRaises(ValueError):
            effective_trajectory(gap)
        raw_path = evidence / 'step_001.json'
        raw = load_json(raw_path)
        raw['action_executed'] = None
        raw_path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            effective_trajectory(record)
        image = evidence / 'raw/observation-001.png'
        image.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '封存原件'):
            session_record(evidence / 'raw')

    async def test_unknown_never_retried(self):
        calls = []
        async def unknown(prompt):
            calls.append(prompt)
            raise OutcomeUnknown('sent request unresolved')
        session = self.session(unknown)
        result = await session.run()
        self.assertEqual(len(calls), 1)
        self.assertTrue(result['unknown'])
        self.assertEqual(self.surface.executed, [])

    async def test_no_effect_is_dispatched_fact_and_waf_remains_failure(self):
        session, evidence, _ = self.recorded([scroll('查看页面下方内容')], name='no-effect')
        with patch('webcollect.browser.execute', new=unittest.mock.AsyncMock()):
            result = await session.run()
        self.assertEqual(result['effective_steps'], 0)
        self.assertEqual(result['actual_actions'], 1)
        self.assertIn('NO_EFFECTIVE_ACTION', result['stop_summary'])
        self.assertTrue(load_json(evidence / 'step_001.json')['dispatched'])
        self.assertEqual(process(evidence, self.root / 'no-effect-delivery', self.ids, self.manifest)['status'], 'no_actions')

        session, evidence, _ = self.recorded([scroll('查看页面下方内容'), finish()], name='waf')
        original = self._fake_execute
        async def blocked(*args, **kwargs):
            await original(*args, **kwargs)
            self.surface.state.update(title='访问被阻止', visible_text='您的访问被阻止，请联系站点管理员。')
        with patch('webcollect.browser.execute', side_effect=blocked):
            await session.run()
        result = process(evidence, self.root / 'waf-delivery', self.ids, self.manifest)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertFalse((self.root / 'waf-delivery').exists())

    async def test_roundtrip_cannot_be_removed_to_join_other_actions(self):
        up = decide(tool='act', arguments=lambda p: {
            'observation_id': p['observation']['observation_id'],
            'step': act_step('scroll', direction='up', goal='查看上方内容', expected='视口上移')})
        session, evidence, _ = self.recorded([scroll('查看页面内容'), up, scroll(), finish()], name='roundtrip')
        original = self._fake_execute
        async def scroll_both(page, action_type, arguments, execution):
            if action_type == 'scroll' and arguments['direction'] == 'up':
                self.surface.executed.append((action_type, deepcopy(arguments)))
                self.surface.state['scroll'][1] -= 480
            else:
                await original(page, action_type, arguments, execution)
        with patch('webcollect.browser.execute', side_effect=scroll_both):
            result = await session.run()
        self.assertEqual(result['actual_actions'], 3)
        record = session_record(evidence / 'raw')
        with self.assertRaisesRegex(ValueError, '无效往返'):
            effective_trajectory(record)

    async def test_completed_call_id_cannot_be_reused_to_dispatch_again(self):
        first = native(scroll('查看页面下方内容'), 'same-id')
        second = native(scroll(), 'same-id')
        script = Script([first, second, native(finish(), 'finish-id')])
        session = self.session(script)
        result = await session.run()
        self.assertEqual(result['effective_steps'], 1)
        self.assertEqual(len(self.surface.executed), 1)
        self.assertEqual([message['tool_call_id'] for message in session.history if message['role'] == 'tool'],
                         ['same-id', 'finish-id'])

    async def test_observed_navigation_enables_back_without_padding_policy(self):
        session, _, _ = self.recorded([finish()], name='navigate')
        await session._open_entry()
        session.working_goal = '查看词条内容后返回入口'
        destination = self.page.url.rstrip('/') + '/article'
        session.page_urls.append(destination)
        open_result = await session._tool_act({'observation_id': session.current['observation_id'],
            'step': act_step('open_url', page_id='p1', goal='查看词条', expected='显示词条页')})
        self.assertEqual(open_result['status'], 'ok', open_result)
        self.assertIn('back', session._compact(session.current)['page_actions'])
        back_result = await session._tool_act({'observation_id': session.current['observation_id'],
            'step': act_step('back', goal='返回入口', expected='显示入口页')})
        self.assertEqual(back_result['status'], 'ok', back_result)
        self.assertEqual(self.page.url, self.task['initial_url'])
        session.stop_reason, session.stop_summary = 'ready', '返回后结束'
        session._close()

    async def test_lower_frozen_decision_budget_and_legacy_budget(self):
        self.assertEqual((GOAL_BUDGETS['max_decisions'], GOAL_BUDGETS['max_model_calls']), (12, 24))
        self.task = build_url_task(url=self.page.url, task_version='low', budgets={'max_decisions': 1})
        session, evidence, script = self.recorded([scroll('查看页面下方内容'), finish()])
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'budget')
        self.assertEqual(len(script.prompts), 1)
        self.assertEqual(load_json(evidence / 'raw/terminal.json')['used']['max_decisions'], 1)
        old = build_url_task(url=self.page.url, task_version='old', decision_protocol=REACT_VERSION)
        self.assertEqual(old['fragment']['budgets'], LEGACY_BUDGETS)
        self.assertNotIn('decision_protocol', old['fragment'])
        validate_task(old)

    async def test_real_chooser_interface_synthetic_wire_history_and_settled_original_cache(self):
        from webcollect.batch_core import BatchLedger
        from webcollect.model_gateway import ModelGateway
        config = load_json(__import__('pathlib').Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json')
        ledger = BatchLedger(self.root / 'wire.sqlite3', config, initialize=True)
        choose = react_chooser(ledger, self.task, 'attempt-wire')
        builds = [scroll('查看页面下方内容'), finish()]
        calls = []
        original = ModelGateway.call_tool

        def controlled(gateway, job, purpose, text, tools, **kwargs):
            self.assertEqual(kwargs['system'], SYSTEM)
            self.assertEqual(kwargs['reasoning_effort'], 'max')
            self.assertEqual(kwargs['max_requests'], 24)
            self.assertEqual({tool['function']['name'] for tool in tools}, {'observe', 'inspect', 'act', 'finish'})
            payload = json.loads(text)
            self.assertNotIn('system', payload)
            self.assertNotIn('_history', payload)
            self.assertNotIn('tools', payload)
            index = len(calls)
            calls.append(deepcopy(kwargs))
            assistant = native(builds[index], 'wire-' + str(index))(payload)['assistant_message']
            return original(gateway, job, purpose, text, tools, synthetic_response=assistant, **kwargs)

        evidence = self.root / 'wire/evidence' / self.ids['sample_id']
        session = ReactSession(self.task, evidence / 'raw', choose, self.page, steps_directory=evidence)
        with patch.object(ModelGateway, 'call_tool', new=controlled):
            result = await session.run()
        self.assertEqual(result['effective_steps'], 1, result)
        self.assertEqual(len(calls), 2)
        self.assertEqual([m['role'] for m in calls[1]['history']], ['user', 'assistant', 'tool'])
        self.assertEqual(calls[1]['history'][1]['reasoning_content'], 'opaque-protocol-private')
        self.assertTrue(calls[1]['history'][0]['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertEqual(choose.requests_used(), 0)  # synthetic responses are not HTTP
        with ledger.connect() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM model_requests').fetchone()[0], 2)
        # Exact original prompt/cache replay does not claim or issue a new request.
        replay = session._prompt()
        replay['progress']['decisions_used'] = 0
        replay['_history'] = []
        # Build a separate explicit settled original identity and replay it.
        replay_chooser = react_chooser(ledger, self.task, 'attempt-replay')
        calls.clear()
        with patch.object(ModelGateway, 'call_tool', new=controlled):
            first = await replay_chooser(replay)
            second = await replay_chooser(replay)
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)

    async def test_one_short_sample_can_queue_independent_review_without_formal_release(self):
        from pathlib import Path
        from webcollect.batch_core import BatchLedger
        from quality_inspector.ai_worker import prepare
        from quality_inspector.delivery_scope import verify_delivery_scope
        session, evidence, _ = self.recorded([scroll('查看页面下方内容'), finish()], name='single-qc')
        await session.run()
        dataset = self.root / 'single-candidate'
        result = process(evidence, dataset / 'samples' / self.ids['sample_id'], self.ids, self.manifest)
        self.assertEqual(result['status'], 'derived_saved')
        config = load_json(Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json')
        ledger = BatchLedger(self.root / 'qc-only.sqlite3', config, initialize=True)
        queue = prepare(ledger, dataset, self.root / 'qc-output', sample_ids=[self.ids['sample_id']])
        self.assertEqual(queue['queued_samples'], 1, queue)
        self.assertEqual(queue['model_requests'], 0)
        prepared = load_json(queue['queue_file'])
        self.assertEqual(len(prepared['jobs']), 1)
        self.assertTrue(prepared['batch_errors'])  # missing formal package files stay explicit
        with self.assertRaisesRegex(ValueError, 'Explicit effective-set'):
            verify_delivery_scope(None, None, dataset=dataset)


class NativePureContractTests(unittest.TestCase):
    def test_v2_goals_only_frozen_goal_and_v1_identity_preserved(self):
        for kind, goal in [('entry', None), ('target', {'kind': '查询', 'entity': '图书', 'parameters': {'书名': '三国'}})]:
            candidate = {'schema_version': 'webcollect-data-candidate-2', 'candidate_kind': kind,
                         'requested_goal': goal, 'entry_url': 'https://example.org'}
            task = {'candidate_binding': {'candidate': candidate}}
            self.assertEqual(struct_goal(task), goal)
            if goal:
                struct_goal(task)['entity'] = 'changed'
                self.assertEqual(candidate['requested_goal']['entity'], '图书')
        v1 = {'schema_version': 'webcollect-data-candidate-1', 'description': '旧目标'}
        self.assertEqual(struct_goal({'candidate_binding': {'candidate': v1}}), v1)

    def test_atomic_effect_excludes_pixels_wait_complete_and_unrelated_values(self):
        state = {'url': 'u', 'scroll': [0, 0], 'visible_text': '中文', 'elements': [],
                 'values': [{'element_id': 'a', 'value': '1', 'focused': True},
                            {'element_id': 'b', 'value': '1'}]}
        after = deepcopy(state)
        after['values'][1]['value'] = '2'
        for action in ('type', 'wait', 'complete', 'observe', 'inspect'):
            self.assertFalse(atomic_effect(state, after, action, {}, 'a')['verified'])
        after = deepcopy(state)
        after['values'][0].update(selection_start=0, selection_end=1)
        self.assertTrue(atomic_effect(state, after, 'hotkey', {'keys': ['meta', 'a']}, 'a')['verified'])
        after = deepcopy(state)
        after['scroll'] = [0, -5]
        self.assertFalse(atomic_effect(state, after, 'scroll', {'direction': 'down'})['verified'])

    def test_waf_and_stopped_terminal_not_success_and_exception_requires_policy(self):
        task = build_url_task(url='https://example.org', task_version='v')
        record = {'terminal': {'stop_reason': 'ready', 'stop_summary': '模型声称完成'}}
        state = {'visible_text': '您的访问被阻止', 'elements': [], 'title': '访问被阻止'}
        status, description = terminal_outcome(task, record, state)
        self.assertEqual(status, 'failed')
        self.assertIn('访问被阻止', description)
        article = {'title':'帮助中心', 'visible_text':'常见问题\n这篇文章解释验证码和安全验证的使用。', 'elements':[]}
        self.assertEqual(terminal_outcome(task, record, article)[0], 'success')
        task['fragment']['allow_controlled_exception'] = True
        self.assertEqual(terminal_outcome(task, record, state)[0], 'controlled_exception')
        with self.assertRaises(ValueError):
            validate_task(task)  # flag cannot bypass frozen caller policy
        task = build_url_task(url='https://example.org', task_version='v', allow_controlled_exception=True)
        self.assertEqual(terminal_outcome(task, record, state)[0], 'controlled_exception')
        record['terminal']['unknown'] = True
        self.assertEqual(terminal_outcome(task, record, state)[0], 'failed')


if __name__ == '__main__':
    unittest.main()
