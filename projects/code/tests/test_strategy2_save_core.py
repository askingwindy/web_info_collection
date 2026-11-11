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
