"""Offline strategy-2 prose and qualified-derivation storage boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from webcollect import postprocess
from webcollect.narration_normalization import normalize_annotation
from webcollect.plan_protocol import ENDING_POLICY, REACT_PROTOCOL


class Strategy2SaveCore(unittest.TestCase):
    def test_narration_simplifies_prose_preserving_ui_quotes_and_actual_input(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / 'observation.json'
            state_path.write_text(json.dumps({'title': '測試頁面', 'elements': [
                {'element_id': 'input', 'text': '搜尋欄'}]}, ensure_ascii=False))
            original_state = state_path.read_bytes()
            record = {'observations': {'o1': {'state_path': str(state_path)}},
                      'trajectory': [{'target': {'label': '搜尋欄'},
                                      'arguments': {'text': '臺灣資料'}}],
                      'terminal': {'goal_evidence': {'checks': [
                          {'evidence': [{'quote': '已找到臺灣資料'}]}]}}}
            annotation = {'task_instruction': '請在「搜尋欄」查詢「臺灣資料」。',
                          'final_result': '已確認「已找到臺灣資料」。',
                          'completion_judgement': '頁面證據顯示「已找到臺灣資料」。',
                          'steps': [{'user_goal': '查詢資料',
                                     'next_step_rationale': '目前可見「搜尋欄」，因此輸入資料。',
                                     'step_result': '結果顯示「已找到臺灣資料」。',
                                     'action': {'precondition': '目前可見「搜尋欄」。',
                                                'expected_result': '預期顯示查詢結果。',
                                                'target_text': '搜尋欄', 'input_text': '臺灣資料'},
                                     'tool_call': {'arguments': {'text': '臺灣資料'}}}]}
            original = deepcopy(annotation)
            normalize_annotation(annotation, record)
            self.assertEqual(annotation['task_instruction'], '请在「搜尋欄」查询「臺灣資料」。')
            self.assertEqual(annotation['completion_judgement'], '页面证据显示「已找到臺灣資料」。')
            self.assertEqual(annotation['steps'][0]['action']['expected_result'], '预期显示查询结果。')
            self.assertEqual(annotation['steps'][0]['action']['input_text'], '臺灣資料')
            self.assertEqual(annotation['steps'][0]['action']['target_text'], '搜尋欄')
            self.assertEqual(annotation['steps'][0]['tool_call'], original['steps'][0]['tool_call'])
            self.assertEqual(state_path.read_bytes(), original_state)
            from webcollect.annotation_corrections import step_narratives
            from webcollect.collect import describe_change
            before = {'title': '测试', 'url': 'https://example.test/', 'visible_text': '厚度',
                'scroll': [0, 0], 'elements': [{'element_id': 'input', 'text': '厚度',
                    'element_type': 'input', 'inputable': True, 'visible': True, 'state': 'focused'}],
                'values': [{'element_id': 'input', 'value': '4', 'display_value': '4',
                    'value_visible': False, 'focused': True, 'selection_start': None, 'selection_end': None}]}
            row = {'action': 'hotkey', 'arguments': {'keys': ['ctrl', 'a']},
                'target': {'control_id': 'input'}, 'semantic_goal': '当前厚度为4，全部选中后改为6'}
            prose = step_narratives(row, before, before['elements'][0], current_facts=True)
            self.assertNotIn('4', prose['next_step_rationale'])
            self.assertNotIn('4', prose['user_goal'])
            selected = deepcopy(before)
            selected['values'][0]['all_text_selected'] = True
            typed = step_narratives({'action': 'type', 'arguments': {'text': '6'},
                'target': {'control_id': 'input'}}, selected, before['elements'][0], current_facts=True)
            self.assertIn('已获得焦点', typed['next_step_rationale'])
            self.assertIn('已全选', typed['next_step_rationale'])
            self.assertIn('值变为「6」', typed['expected_result'])
            clicked = step_narratives({'action': 'click', 'semantic_goal': '展开control e_26 summary',
                'target': {'control_id': 'help'}}, {'visible_text': '运作原理', 'values': [],
                'elements': [{'element_id': 'help', 'text': '运作原理'}]},
                {'element_id': 'help', 'text': '运作原理', 'native_role': 'summary'}, current_facts=True)
            self.assertIn('运作原理', clicked['next_step_rationale'])
            self.assertNotIn('e_26', clicked['next_step_rationale'])
            clicked = step_narratives({'action': 'click', 'semantic_goal': '展开「运作原理」以阅读说明',
                'target': {'control_id': 'help'}}, {'visible_text': '运作原理', 'values': [],
                'elements': [{'element_id': 'help', 'text': '运作原理'}]},
                {'element_id': 'help', 'text': '运作原理', 'native_role': 'summary'}, current_facts=True)
            self.assertEqual(clicked['user_goal'], '展开「运作原理」以阅读说明')
            self.assertEqual(postprocess.terminal_fallback_timestamp({'terminal': {'completed_at': '2026-11-12T01:00:00+08:00'}}),
                             '2026-11-12T01:00:00+08:00')
            self.assertEqual(postprocess.terminal_fallback_timestamp({'terminal': {}}), '')
            # A result region contains every newly rendered answer, including
            # the fourth row; an unrelated navigation refresh is excluded.
            from webcollect.collect import action_content_changes
            old = {'visible_text': '计算', 'elements': [
                {'element_id': 'go', 'text': '计算', 'native_role': 'button', 'parent_id': 'root',
                 'element_type': 'button', 'inputable': False, 'state': 'default'}]}
            leaves = [{'element_id': 'r' + str(i), 'text': text, 'native_role': 'span',
                       'element_type': 'text', 'parent_id': 'result'}
                      for i, text in enumerate(['体积', '72.00 cu ft', '2.67 cu yd', '120 (80lb bags)'])]
            new = {'visible_text': '体积\n72.00 cu ft\n2.67 cu yd\n120 (80lb bags)\n侧栏99',
                   'elements': old['elements'] + [
                       {'element_id': 'result', 'text': '', 'native_role': 'status', 'parent_id': 'root'},
                       {'element_id': 'nav', 'text': '', 'native_role': 'navigation', 'parent_id': 'root'},
                       {'element_id': 'ad', 'text': '侧栏99', 'native_role': 'span',
                        'element_type': 'text', 'parent_id': 'nav'}] + leaves}
            self.assertEqual(action_content_changes(old, new, old['elements'][0]),
                             ['体积', '72.00 cu ft', '2.67 cu yd', '120 (80lb bags)'])
            long_text = '长度乘宽度再乘厚度，厚度先除以12换为英尺；体积除以27换为立方码，再除以0.6核算袋数。'
            long_after = deepcopy(new)
            long_after.update(title='测试', url='https://example.test/', scroll=[0, 0], values=[])
            long_after['elements'].append({'element_id': 'formula', 'text': long_text,
                'native_role': 'p', 'element_type': 'text', 'parent_id': 'result'})
            long_after['visible_text'] += '\n' + long_text
            long_before = {**old, 'title': '测试', 'url': 'https://example.test/', 'scroll': [0, 0], 'values': []}
            result = describe_change(long_before, long_after, {'action_type': 'click',
                'arguments': {}, 'goal': '查看公式'}, old['elements'][0])
            self.assertIn(long_text, result)
            from webcollect.task_contract import narrative_evidence
            self.assertEqual(narrative_evidence(result, long_before, long_after, {})[0], result)
            for goal in ['点击计算', '展开运作原理']:
                title = goal[2:]
                word = step_narratives({'action': 'click', 'semantic_goal': goal},
                    {'visible_text': title, 'elements': [], 'values': []},
                    {'text': title, 'native_role': 'summary' if goal.startswith('展开') else 'button'}, current_facts=True)
                self.assertEqual(word['user_goal'].count(title), 1)
                self.assertNotIn('以' + goal, word['user_goal'])

    def test_qualified_derivation_destination_failure_retains_eligibility_and_evidence(self):
        # Supply the already verified execution boundary; exercise real goal
        # narrative, completion gate, destination guard and failure journaling.
        # Atomic execution validation has its own independent core coverage.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / 'evidence'
            raw = evidence / 'raw'
            raw.mkdir(parents=True)
            state_path = raw / 'observation.json'
            quote = '页面已经显示本次查询的完整结果。'
            state_path.write_text(json.dumps({'title': '查询结果', 'url': 'https://example.test/',
                'visible_text': quote, 'elements': [], 'values': []}, ensure_ascii=False))
            # Derived arithmetic conclusions are labelled as calculation, while
            # each source quote retains its real observation/frame basis.
            derived = {'terminal': {'goal_evidence': {'business_goal_status': 'VERIFIED', 'checks': [
                {'field': '比例核对', 'status': 'VERIFIED',
                 'completion_mapping': 'cited_arithmetic_cross_check',
                 'observed_visible_text': '两份合计为24',
                 'calculations': [{'expression': '12 * 2', 'computed_value': 24, 'unit': '份'}],
                 'evidence': [{'observation_id': 'o1', 'quote': quote}]}]}},
                'observations': {'o1': {'state_path': str(state_path)}}, 'trajectory': []}
            narrative = postprocess.planned_terminal_narrative(derived, {'visible_text': quote}, 'o1')
            self.assertIn('计算核验通过', narrative['final_result'])
            self.assertEqual(narrative['completion_judgement'].count('12 * 2 = 24'), 1)
            self.assertNotIn('比例核对', narrative['final_result'])
            self.assertIn('推导核对', narrative['completion_judgement'])
            self.assertIn(quote, narrative['completion_judgement'])
            input_state_path = raw / 'input.json'
            input_state = {'visible_text': '原形状', 'elements': [
                {'element_id': 'shape', 'text': '原形状', 'visible': True}],
                'values': [{'element_id': 'shape', 'value': 'slab',
                            'display_value': '板', 'value_visible': True}]}
            input_state_path.write_text(json.dumps(input_state, ensure_ascii=False))
            input_check = {'requirement_id': 'shape-check', 'status': 'VERIFIED',
                'completion_mapping': 'bound_input_state', 'evidence': [
                    {'observation_id': 'input', 'node': 'shape', 'input_field': 'value', 'actual': 'slab'}]}
            input_record = {'observations': {'input': {'state_path': str(input_state_path)}},
                'trajectory': [], 'terminal': {'goal_evidence': {'business_goal_status': 'VERIFIED',
                    'checks': [input_check], 'final_visible_evidence': [
                        {'kind': 'input', 'node': 'shape', 'requirement_id': 'shape-check',
                         'observation_id': 'final', 'value_visible': True, 'display_value': '平板'}]}}}
            input_final = {'visible_text': '新形状', 'elements': [{'element_id': 'shape', 'text': '新形状'}]}
            input_narrative = postprocess.planned_terminal_narrative(input_record, input_final, 'final')
            self.assertIn('新形状：值为「平板」', input_narrative['final_result'])
            self.assertNotIn('slab', input_narrative['final_result'])
            self.assertNotIn('值为「板」', input_narrative['completion_judgement'])
            input_record['terminal']['goal_evidence']['final_visible_evidence'] = []
            historical = postprocess.planned_terminal_narrative(input_record, input_final, 'final')
            self.assertIn('原引用观察', historical['completion_judgement'])
            self.assertIn('值为「板」', historical['final_result'])
            self.assertNotIn('末帧仍可见', historical['completion_judgement'])
            input_state['values'][0].pop('display_value')
            input_state_path.write_text(json.dumps(input_state, ensure_ascii=False))
            missing_display = postprocess.planned_terminal_narrative(input_record, input_final, 'final')
            self.assertNotIn('slab', missing_display['final_result'])
            original_state = state_path.read_bytes()
            delivery = root / 'delivery'
            delivery.write_bytes(b'existing destination must remain untouched')
            task = {'instruction': '查询并确认结果', 'fragment': {
                'collection_strategy': {'id': 'screenshot_plan'},
                'decision_protocol': REACT_PROTOCOL, 'ending_policy': ENDING_POLICY}}
            rows = [{'operation_id': f'op-{i}', 'action': 'click',
                     'before_observation_id': 'o1', 'after_observation_id': 'o1'} for i in range(5)]
            record = {'task': task, 'trajectory': rows,
                      'observations': {'o1': {'state_path': str(state_path)}},
                      'terminal': {'stop_reason': 'ready', 'unknown': False,
                          'final_observation_id': 'o1',
                          'goal_evidence': {'business_goal_status': 'VERIFIED', 'checks': [
                              {'field': '查询结果', 'status': 'VERIFIED',
                               'evidence': [{'observation_id': 'o1', 'quote': quote}]}]},
                          'collection_ending': {'kind': 'AGENT_COMPLETE_VERIFIED',
                              'safe_for_pending_sample': True, 'flagged': False,
                              'endpoint_evidence': {'source': 'host_screenshot_completion',
                                  'completion': {'path': 'already-verified-completion'},
                                  'image': {'path': 'already-verified-image'}}}}}

            class VerifiedExecution:
                def record(self, unused_root):
                    return deepcopy(record)

            with patch.object(postprocess, 'effective_trajectory', return_value=rows):
                result = postprocess.process(evidence, delivery, {'sample_id': 'sample'}, {},
                                             _verified=VerifiedExecution())
            self.assertEqual(result['status'], 'processing_failed')
            self.assertEqual(result['error_type'], 'FileExistsError')
            self.assertEqual(result['save_eligibility'], 'eligible')
            journal = json.loads((evidence / 'derivations.jsonl').read_text())
            self.assertEqual(journal['save_eligibility'], 'eligible')
            failure = json.loads((evidence / 'derived-failed-01.json').read_text())
            self.assertEqual(failure['save_eligibility'], 'eligible')
            self.assertFalse((evidence / 'saved_sample.json').exists())
            self.assertEqual(state_path.read_bytes(), original_state)
            self.assertEqual(delivery.read_bytes(), b'existing destination must remain untouched')
