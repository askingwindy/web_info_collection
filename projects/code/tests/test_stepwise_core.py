"""策略 3 stepwise 核心契约（离线）：策略路由与保存资格、决策协议与动作绑定、
原始记录/导出映射与 annotation 生成。全部离线；无真实 GLM 或生产库。
"""
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from webcollect import collection_strategy as cs
from webcollect.stepwise import finalize, observation, prompt
from webcollect.stepwise.records import Journal


def _png(width=40, height=30, color=(240, 240, 240)):
    buffer = io.BytesIO()
    Image.new('RGB', (width, height), color).save(buffer, format='PNG')
    return buffer.getvalue()


def _captured(state, png=None, number=0):
    return {'state': state, 'png': png or _png(), 'capture': {'attempts': [number]}}


def _state(url='https://example.org/tool', **extra):
    state = {'url': url, 'title': '面积计算器', 'screen_resolution': [1280, 720],
             'scroll': [0, 0], 'values': [], 'elements': [
                 {'element_id': 'nav1', 'parent_id': 'root', 'element_type': 'link',
                  'native_role': 'link', 'text': '首页', 'bbox': [10, 10, 60, 30],
                  'clickable': True, 'inputable': False, 'scrollable': False,
                  'visible': True, 'enabled': True, 'state': 'default'},
                 {'element_id': 'e1', 'parent_id': 'root', 'element_type': 'input',
                  'native_role': 'input', 'text': '长度', 'bbox': [100, 100, 260, 130],
                  'clickable': True, 'inputable': True, 'scrollable': False,
                  'visible': True, 'enabled': True, 'state': 'default'},
                 {'element_id': 'e2', 'parent_id': 'root', 'element_type': 'button',
                  'native_role': 'button', 'text': '计算', 'bbox': [100, 200, 160, 230],
                  'clickable': True, 'inputable': False, 'scrollable': False,
                  'visible': True, 'enabled': True, 'state': 'default'}],
             'visible_text': '面积计算器 长度 宽度 计算'}
    state.update(extra)
    return state


class StepwiseRoutingAndSaveGate(unittest.TestCase):
    """策略路由：stepwise 执行与封存；历史策略的保存资格继续按原标记解释。"""

    def test_stepwise_gate_dispatch_and_eligibility(self):
        # task_type 标签与 QC 权威清单一致，不另起业务枚举。
        from quality_inspector.format_checks import LABELS
        self.assertEqual(prompt.TASK_TYPE_LABELS, LABELS)
        # 指定模式系统提示替换任务选择段。
        self.assertIn('不能改变、缩小目标', prompt.specified_system_prompt())
        self.assertNotIn('本条没有指定任务', prompt.specified_system_prompt())

        def annotation(steps=6, status='success'):
            return {'completion_status': status, 'steps': [
                {'action': {'action_type': 'click'}} for _ in range(steps)]}

        judgement = {'instruction_specific': True, 'completed': True,
                     'judgement_supported': True, 'redundant_steps': [],
                     'mismatch_steps': [], 'reason': '任务具体且末帧支持结论'}

        def raw(effective=6, stop='complete_success', unknown=False, gaps=(),
                judge=None, strategy=True):
            payload = {'stop_reason': stop, 'unknown': unknown,
                       'effective_steps': effective, 'continuity_gaps': list(gaps),
                       'judgement': judge if judge is not None else judgement,
                       'completion_status': 'success', 'writeback': {}, 'trusted_prefix': None}
            if strategy:
                payload['collection_strategy'] = {'id': 'stepwise'}
            return payload

        # 统一入口按封存策略标记分流：stepwise 标记走本策略判定。
        decision = cs.save_eligibility(annotation(), raw())
        self.assertTrue(decision['delivery_eligible'])
        self.assertEqual(decision['delivery_policy'], 'completed-goal-delivery')
        self.assertEqual(decision['effective_steps'], 6)
        self.assertFalse(decision['QC_approval'])
        # 无标记记录仍走 closing_policy（策略1/2 原路径不受策略3默认值污染）。
        react_shaped = {'collection_ending': {'kind': 'HOST_PLAN_ENDPOINT',
            'safe_for_pending_sample': True, 'endpoint_evidence': {'image': {'path': 'x'},
            'source': 'host_plan_endpoint'}}, 'goal_evidence': {'checks': [{'status': 'VERIFIED'}]},
            'stop_reason': 'ready', 'unknown': False, 'trusted_prefix': None}
        legacy = cs.save_eligibility(annotation(), react_shaped)
        self.assertTrue(legacy['delivery_eligible'])
        # 反例：短流程、超过12步、判定不通过、连续性缺口、未知终态均不可保存。
        for payload in (raw(effective=4), raw(effective=13),
                        raw(judge={**judgement, 'completed': False}),
                        raw(gaps=['frame_gap_3']),
                        raw(unknown=True), raw(stop='no_effect')):
            self.assertFalse(finalize.save_eligibility(annotation(), payload)['delivery_eligible'],
                             payload)
        self.assertFalse(finalize.save_eligibility(annotation(status='failed'), raw())['delivery_eligible'])
        # 指定目标渲染：结构化目标如实渲染；不可交付目标被拒绝并保留原因。
        self.assertEqual(finalize.specified_instruction(
            {'kind': 'edit', 'entity': 'fields', 'parameters': {'长度': 12}}, '面积计算器'),
            '在「面积计算器」上完成edit/fields：长度为12')
        with self.assertRaisesRegex(ValueError, 'STEPWISE_GOAL_NOT_DELIVERABLE'):
            finalize.specified_instruction({'unrelated': 1}, 'app')


class StepwiseExceptionClosure(unittest.TestCase):
    def test_session_exceptions_seal_raw_and_keep_failure_ownership(self):
        # 同一 run 边界对已知模型/网络/采集错误和未知程序错误均封存原件。
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from playwright.async_api import Error as BrowserError
        from webcollect.browser import EvidenceStale, SnapshotFault
        from webcollect.failure_policy import disposition
        from webcollect.model_gateway import ProviderFinishIncomplete, ProviderRejected
        from webcollect.stepwise.session import StepwiseSession
        from webcollect.stepwise import records
        errors = [(ValueError('bounded_plan_correction_failed: invalid'), 'model', 'protocol_error'),
                  (ValueError('consumer_protocol_no_progress'), 'model', 'protocol_error'),
                  (ProviderFinishIncomplete('refused', 'declined'), 'model', 'protocol_error'),
                  (ProviderRejected(400, 'request-400', {'message': 'bad request'}), 'model', 'error'),
                  (BrowserError('page.goto: net::ERR_CONNECTION_CLOSED'), 'network', 'error'),
                  (EvidenceStale('stale pixels'), 'collector', 'capture_stale'),
                  (SnapshotFault('UNSUPPORTED_GEOMETRY: rotated target'), 'collector', 'capture_stale'),
                  (BrowserError('UNSUPPORTED_GEOMETRY: rotated target'), 'collector', 'capture_stale'),
                  (SnapshotFault('invalid capture record'), 'program', 'capture_stale'),
                  (KeyError('missing fact'), 'program', 'error')]
        with tempfile.TemporaryDirectory() as temporary:
            for index, (error, failure_class, stop_reason) in enumerate(errors):
                evidence = Path(temporary) / str(index)
                task = {'task_id': 'task-error', 'site_uri': 'https://example.org/tool',
                        'initial_url': 'https://example.org/tool', 'fragment': {}}
                session = StepwiseSession(task, evidence, AsyncMock(),
                    SimpleNamespace(url=task['site_uri']), attempt_id='attempt-error', entry_ready=True)
                with patch.object(session, '_capture', new=AsyncMock(return_value=_captured(_state()))), \
                     patch.object(session, '_loop', new=AsyncMock(side_effect=error)):
                    result = asyncio.run(session.run())
                self.assertEqual(result['failure_class'], failure_class)
                self.assertEqual(result['stop_reason'], stop_reason)
                self.assertIn(type(error).__name__, result['stop_summary'])
                self.assertTrue(Path(result['raw_receipt']['path']).is_file())
                terminal = records.read_terminal(evidence)
                self.assertEqual(terminal['failure_class'], failure_class)
                self.assertFalse(terminal['unknown'])
                expected = 'page_program' if failure_class == 'program' else 'business'
                self.assertEqual(disposition(failure_class=failure_class)['disposition'], expected)


        # Errors after a recorded dispatch must retain its receipt and actual
        # execution fact; post-capture faults are never silently retried.
        from webcollect import browser
        for phase, error, failure_class in (
                ('dispatch', BrowserError('net::ERR_CONNECTION_CLOSED'), 'network'),
                ('dispatch', KeyError('execution defect'), 'program'),
                ('capture', EvidenceStale('after pixels stale'), 'collector'),
                ('capture', SnapshotFault('capture implementation defect'), 'program'),
                ('capture', SnapshotFault('UNSUPPORTED_GEOMETRY: target'), 'collector')):
            with tempfile.TemporaryDirectory() as temporary:
                task = {'task_id': 'dispatched', 'site_uri': 'https://example.org/tool',
                        'initial_url': 'https://example.org/tool', 'fragment': {}}
                session = StepwiseSession(task, temporary, AsyncMock(),
                    SimpleNamespace(url=task['site_uri']), attempt_id='dispatched', entry_ready=True)
                async def dispatch_once():
                    await session._dispatch(session.current,
                        {'action_type': 'back', 'arguments': {}, 'evidence': {'collection_strategy': 'stepwise'}},
                        None, {'action': 'back'})
                captures = [_captured(_state())]
                if phase == 'capture':
                    captures.append(error)
                with patch.object(session, '_capture', new=AsyncMock(side_effect=captures)), \
                     patch.object(session, '_loop', new=dispatch_once), \
                     patch.object(browser, 'execute', new=AsyncMock(side_effect=error if phase == 'dispatch' else None)):
                    result = asyncio.run(session.run())
                terminal = records.read_terminal(temporary)
                self.assertEqual(result['failure_class'], failure_class)
                self.assertEqual(terminal['actual_dispatches'], 1)
                self.assertEqual(len(terminal['steps']), 1)
                receipt = json.loads(Path(terminal['steps'][0]['step_file']).read_text())
                self.assertEqual(receipt['action_executed'], True if phase == 'capture' else None)
                self.assertIn(type(error).__name__, receipt['execution_error'])
                self.assertEqual(len(list(records.unverified_actions(result['raw_receipt']))), 1)


class StepwiseDecisionProtocolAndBinding(unittest.TestCase):
    """扁平 next_action 协议、上下文裁剪次序与当前帧动作绑定。"""

    def test_schema_context_trim_and_action_binding(self):
        autonomous = prompt.next_action_schema(autonomous=True)
        self.assertIn('task_goal', autonomous['required'])
        specified = prompt.next_action_schema(autonomous=False)
        self.assertNotIn('task_goal', specified['properties'])
        self.assertFalse(specified['additionalProperties'])
        # 裁剪次序：页面结构 → 可见正文 → 较早历史 → 导航元素；任务与反馈保留。
        state = _state()
        state['visible_text'] = '正文' * 400
        state['text_blocks'] = [{'visible_text': '第%d章' % i + '内容' * 40} for i in range(30)]
        long_rows = [(i + 1, {'element_id': 'n%d' % i, 'element_type': 'link',
                              'text': '导' * 96 + str(i), 'bbox': [10, 10, 60, 30],
                              'visible': True, 'enabled': True, 'clickable': True,
                              'state': 'default'}) for i in range(60)]
        # 用放小的动态预算（monkeypatch 常量）确定性触发整条裁剪链。
        from unittest.mock import patch
        with patch.object(prompt, 'LIMIT_TOTAL_DYNAMIC', 3000):
            text, trimmed = prompt.build_decision_message(
                mode='specified', requested_goal_text='目标' * 400,
                task_goal=None, progress='进' * 200, rows=long_rows, state=state,
                history=['第%d步' % i + '结' * 55 for i in range(15)],
                feedback='拒' * 190, note='跨页笔记',
                site_tasks=['已采' + '任' * 56 + str(i) for i in range(10)])
        blocks = [item['block'] for item in trimmed]
        self.assertIn('structure', blocks)
        self.assertIn('visible_text', blocks)
        self.assertIn('任务与进度', text)
        self.assertIn('上一条反馈', text)
        # 不可裁内容（任务文本）本身超预算时结束并保留原因，不循环发送同一超大请求。
        with patch.object(prompt, 'LIMIT_TOTAL_DYNAMIC', 200):
            with self.assertRaisesRegex(ValueError, 'CONTEXT_OVER_BUDGET'):
                prompt.build_decision_message(
                    mode='specified', requested_goal_text='长' * 20000, task_goal=None,
                    progress='', rows=[], state={'visible_text': '', 'elements': []},
                    history=[], feedback='', note='', site_tasks=[])
        # 动作绑定：编号→元素中心坐标；越界编号、未聚焦输入、非法按键拒绝。
        rows = observation.actionable_rows(state)
        self.assertEqual([element['element_id'] for _, element in rows][:3], ['e1', 'e2', 'nav1'])
        operation, element = observation.bind_action(state, rows, {
            'action': 'click', 'element': 2,
            'page_name': '计算器', 'precondition': '可见「计算」按钮',
            'thought': '点击计算', 'user_goal': '开始计算',
            'expected_result': '出现结果', 'last_step_result': ''})
        self.assertEqual(operation['action_type'], 'click')
        self.assertEqual(operation['arguments'], {'x': 130, 'y': 215})
        self.assertEqual(operation['evidence']['element_id'], 'e2')
        with self.assertRaises(observation.ActionRejected):
            observation.bind_action(state, rows, {'action': 'click', 'element': 99})
        with self.assertRaisesRegex(observation.ActionRejected, 'FOCUSED'):
            observation.bind_action(state, rows, {'action': 'type', 'element': 1, 'text': '12.5'})
        with self.assertRaisesRegex(observation.ActionRejected, 'KEYS_NOT_ALLOWED'):
            observation.bind_action(state, rows, {'action': 'hotkey', 'keys': ['ctrl', 'pwn']})
        scroll_operation, _ = observation.bind_action(state, rows, {
            'action': 'scroll', 'direction': 'down'})
        self.assertEqual(scroll_operation['arguments'],
                         {'x': 640, 'y': 360, 'direction': 'down'})
        with self.assertRaisesRegex(observation.ActionRejected, 'UNEXPECTED_ACTION_FIELDS'):
            observation.bind_action(state, rows, {'action': 'back', 'text': '多余参数'})
        # select 原文只允许当前捕获的非禁用选项，拒绝必须发生在派发前。
        select_state = _state()
        select_state['elements'][2].update(element_type='select', native_role='select')
        select_state['capture_controls'] = [{'element_id': 'e2', 'tag': 'select',
            'options': [{'label': '厘米', 'value': 'cm', 'disabled': False},
                        {'label': '米', 'value': 'm', 'disabled': True}]}]
        select_rows = observation.actionable_rows(select_state)
        chosen, _ = observation.bind_action(select_state, select_rows,
                                            {'action': 'select', 'element': 2, 'option': '厘米'})
        self.assertEqual(chosen['arguments']['option'], '厘米')
        for option in ('千米', '米', ' 厘米', 'cm'):
            with self.assertRaisesRegex(observation.ActionRejected, 'SELECT_OPTION_NOT_PRESENT'):
                observation.bind_action(select_state, select_rows,
                                        {'action': 'select', 'element': 2, 'option': option})
        with self.assertRaisesRegex(observation.ActionRejected, 'SELECT_OPTION_REQUIRED'):
            observation.bind_action(select_state, select_rows, {'action': 'select', 'element': 2})
        # require_action（browser.validate_action_observation 的策略3校验器）复核同一事实。
        self.assertTrue(observation.require_action(state, operation))
        bad = {'action_type': 'click', 'arguments': {'x': 5, 'y': 5},
               'evidence': {'collection_strategy': 'stepwise', 'element_id': 'e2',
                            'element_bbox': [100, 200, 160, 230]}}
        with self.assertRaisesRegex(ValueError, 'POINTER_OUTSIDE'):
            observation.require_action(state, bad)
        # 效果判断：同文档同业务视图的无效果点击可省略；键入保守保留；改文档不可省略。
        omittable, reason = observation.action_omittable(state, state, 'click')
        self.assertTrue(omittable)
        self.assertEqual(reason, 'no_effect_confirmed')
        typed = _state(values=[{'element_id': 'e1', 'value': '12.5', 'value_visible': True,
                                'focused': True}])
        omittable, reason = observation.action_omittable(state, typed, 'type')
        self.assertFalse(omittable)
        moved = _state(scroll=[0, 480])
        omittable, _ = observation.action_omittable(state, moved, 'scroll')
        self.assertFalse(omittable)
        other = _state(url='https://example.org/other')
        self.assertFalse(observation.view_equal(state, other))
        # 范围与排除：同host放行、越界拒绝、登录/纯英文页拒绝。
        hosts = observation.allowed_hosts({'site_uri': 'https://example.org/tool',
                                           'initial_url': 'https://example.org/tool'})
        self.assertTrue(observation.destination_allowed('https://example.org/other', hosts))
        self.assertFalse(observation.destination_allowed('https://evil.example/page', hosts))
        self.assertIsNotNone(observation.exclusion_issues('https://example.org/login', state))
        english = _state()
        english['visible_text'] = 'This page contains English content only. ' * 20
        self.assertIsNotNone(observation.exclusion_issues('https://example.org/', english))


class StepwiseRecordsAndAnnotation(unittest.TestCase):
    """原始记录封存、导出真实动作映射与 annotation 生成（含引文核对）。"""

    def test_journal_seal_export_entries_and_delivery_annotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / 'evidence' / 'S000001'
            evidence.mkdir(parents=True)
            journal = Journal(evidence)
            task = {'task_id': 't1', 'site_uri': 'https://example.org/tool',
                    'app_name': '面积计算器', 'task_version': 'react-url'}
            journal.write_boundary(task, mode='autonomous', requested_goal=None, site_tasks=[])
            frame_one = journal.add_frame(_captured(_state()))
            frame_two = journal.add_frame(_captured(_state(scroll=[0, 300])))
            frame_three = journal.add_frame(_captured(_state(
                values=[{'element_id': 'e1', 'value': '12.5', 'value_visible': True,
                         'focused': False}])))
            element = frame_one['state']['elements'][2]
            operation = {'action_type': 'click',
                         'arguments': {'x': 130, 'y': 215},
                         'evidence': {'collection_strategy': 'stepwise',
                                      'element_id': 'e2', 'element_bbox': [100, 200, 160, 230]}}
            seq, dispatch, dispatch_ref = journal.begin_dispatch(
                frame_id=frame_one['frame_id'], operation=operation, element=element)
            journal.finish_step(seq=seq, dispatch_ref=dispatch_ref, operation=operation,
                                element=element, dispatched=True, action_executed=True,
                                execution_error=None, before_frame=frame_one['frame_id'],
                                after_frame=frame_two['frame_id'], effect='view_changed',
                                effective=True, omittable=False, omit_reason=None,
                                postconditions_checked=True, delivery_index=1,
                                after_state=frame_two['state'])
            # 无效果 wait：确认可安全省略，移出交付但原记录保留。
            wait_operation = {'action_type': 'wait', 'arguments': {},
                              'evidence': {'collection_strategy': 'stepwise'}}
            seq_two, dispatch_two, dispatch_ref_two = journal.begin_dispatch(
                frame_id=frame_two['frame_id'], operation=wait_operation, element=None)
            journal.finish_step(seq=seq_two, dispatch_ref=dispatch_ref_two,
                                operation=wait_operation, element=None, dispatched=True,
                                action_executed=True, execution_error=None,
                                before_frame=frame_two['frame_id'],
                                after_frame=frame_three['frame_id'], effect='no_effect',
                                effective=False, omittable=True, omit_reason='no_effect_confirmed',
                                postconditions_checked=True,
                                after_state=frame_three['state'])
            self.assertTrue((evidence / 'stepwise' / 'omitted-002.json').is_file())
            delivered = [{'dispatch_seq': 1, 'step_file': 'step_001.json',
                          'dispatch_file': 'dispatch-001.json',
                          'frame_id': frame_one['frame_id'],
                          'after_frame': frame_two['frame_id'],
                          'operation': operation, 'element': element,
                          'decision': {'page_name': '网页「面积计算器」',
                                       'precondition': '可见「计算」按钮',
                                       'thought': '点击「计算」查看结果',
                                       'user_goal': '开始计算',
                                       'expected_result': '出现面积结果',
                                       'last_step_result': '结果区显示「面积」'},
                          'dispatched_at': dispatch['dispatched_at'],
                          'effective': True, 'omittable': False,
                          'step_result': '结果区显示「面积」', 'result_round': 2}]
            journal.write_delivery_map(
                [{'step_id': 1, 'dispatch_file': 'dispatch-001.json',
                  'step_file': 'step_001.json', 'frame_id': frame_one['frame_id'],
                  'after_frame': frame_two['frame_id'], 'result_round': 2}],
                {'frame_id': frame_three['frame_id'],
                 'decision': {'action': 'complete', 'status': 'success',
                              'page_name': '网页「面积计算器」',
                              'precondition': '结果区显示「面积」',
                              'thought': '结果已出现，结束任务',
                              'user_goal': '确认「面积」结果',
                              'expected_result': '结束任务',
                              'last_step_result': '结果区显示「面积」'},
                 'completed_at': '2026-11-18T00:00:00+00:00'},
                [{'dispatch_seq': 2, 'reason': 'no_effect_confirmed'}])
            terminal_ref = journal.write_terminal({'schema_version': 'stepwise-terminal-1',
                'strategy': {'id': 'stepwise'}, 'stop_reason': 'complete_success',
                'unknown': False, 'effective_steps': 1, 'actual_dispatches': 2,
                'steps': [{'step_file': 'step_001.json', 'dispatched': True,
                           'after_frame': frame_two['frame_id'], 'ended_at': 'x',
                           'effective': True, 'omittable': False},
                          {'step_file': 'step_002.json', 'dispatched': True,
                           'after_frame': frame_three['frame_id'], 'ended_at': 'x',
                           'effective': False, 'omittable': True}]})
            receipt = journal.seal(terminal_ref)
            self.assertTrue((evidence / 'step_001.json').is_file())
            self.assertTrue((evidence / 'stepwise' / 'raw-receipt.json').is_file())
            # 导出映射：交付步骤绑定真实派发原件（哈希一致）。
            record = {'batch': Path(tmp), 'sample_id': 'S000001',
                      'data': {'trajectory_source': {'data_type': 'stepwise'}}}
            from webcollect.stepwise import records as stepwise_records
            entries = stepwise_records.execution_entries(record)
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(entry['tool_name'], 'click')
            self.assertEqual(entry['arguments'], {'x': 130, 'y': 215})
            dispatch_file = json.loads(Path(entry['dispatch_ref']['path']).read_text())
            self.assertEqual(dispatch_file['operation']['action_type'], 'click')
            step_file = json.loads(Path(entry['raw_step_ref']['path']).read_text())
            self.assertEqual(step_file['controller_dispatch']['sha256'], entry['dispatch_ref']['sha256'])
            # annotation 生成：交付用干净原图；末步 complete 省略 screen_changed。
            from webcollect.stepwise.annotation import build_delivery
            sample = Path(tmp) / 'samples' / 'S000001'
            complete_row = {'frame_id': frame_three['frame_id'],
                            'decision': {'page_name': '网页「面积计算器」',
                                         'precondition': '结果区显示「面积」',
                                         'thought': '结果已出现，结束任务',
                                         'user_goal': '确认「面积」结果',
                                         'expected_result': '结束任务'},
                            'completed_at': '2026-11-18T00:00:00+00:00'}
            writeback = {'task_type': ['数据查看'], 'model_instruction': '在「面积计算器」输入并查看结果',
                         'final_result': '结果区显示「面积」数值',
                         'completion_judgement': '末帧可见「面积」结果'}
            frame_one['state']['elements'][0]['geometry_proof'] = {'raw_only': True}
            annotation, frame_texts = build_delivery(
                sample, journal, task, delivered=delivered, complete_row=complete_row,
                omitted=[{'dispatch_seq': 2, 'reason': 'no_effect_confirmed'}],
                instruction_text=writeback['model_instruction'], writeback=writeback,
                judgement={'completed': True})
            self.assertEqual(annotation['trajectory_source'],
                             {'source_type': 'agent', 'data_type': 'stepwise',
                              'action_space': 'unified_gui_v4'})
            self.assertEqual(len(annotation['steps']), 2)
            self.assertNotIn('screen_changed', annotation['steps'][-1]['tool_result']['return_value'])
            self.assertEqual(annotation['steps'][0]['action']['target_text'], '计算')
            from webcollect.stepwise.annotation import UI_ELEMENT_FIELDS
            tree = json.loads((sample / 'ui_tree' / 'step_001.json').read_text())
            self.assertNotIn('geometry_proof', tree['elements'][0])
            self.assertIn('geometry_proof', frame_one['state']['elements'][0])
            self.assertTrue(all(set(item) <= set(UI_ELEMENT_FIELDS) for item in tree['elements']))

            ground_truth = json.loads((evidence / 'ground_truth.json').read_text())
            self.assertEqual(ground_truth[0]['element_id'], 'e2')
            # 引文核对：字段所属帧命中；末帧缺失引文如实报出。
            self.assertEqual(finalize.citations_check(annotation, frame_texts), [])
            broken = json.loads(json.dumps(annotation))
            broken['final_result'] = '末帧可见「不存在的数值」'
            problems = finalize.citations_check(broken, frame_texts)
            self.assertTrue(any('final_result' in item for item in problems))
            # 守卫读取：已结算且后帧齐全时不报未决动作。
            self.assertEqual(list(stepwise_records.unverified_actions(receipt)), [])


if __name__ == '__main__':
    unittest.main()
