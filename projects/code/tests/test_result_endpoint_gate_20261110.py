"""2026-11-10 result-endpoint gate: weak first-frame finish_when and UNVERIFIED
declared result checks must never export as success. Disposable fixtures only.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from webcollect.banded_plan import Controller
from webcollect.postprocess import terminal_outcome


def _controller(first_frame, checks, finish_kind='visible_text'):
    c = Controller()
    c.endpoint_established_at_first_frame = first_frame
    c.plan = {'finish_when': {'kind': finish_kind, 'text': '相当于人类'}}
    c.fact_progress = lambda s: {'checks': checks}
    return c


class WeakEndpointTests(unittest.TestCase):
    def test_first_frame_weak_predicate_with_unverified_result_blocks(self):
        c = _controller(True, [{'field': '本次计算的换算结果区', 'status': 'UNVERIFIED'}])
        s = SimpleNamespace(task={'fragment': {}})
        self.assertEqual(c.weak_endpoint_unverified(s),
                         [{'field': '本次计算的换算结果区', 'status': 'UNVERIFIED'}])

    def test_action_produced_endpoint_or_verified_checks_do_not_block(self):
        s = SimpleNamespace(task={'fragment': {}})
        self.assertEqual(_controller(False, [{'field': 'r', 'status': 'UNVERIFIED'}]).weak_endpoint_unverified(s), [])
        self.assertEqual(_controller(True, [{'field': 'r', 'status': 'VERIFIED'}]).weak_endpoint_unverified(s), [])

    def test_pending_auxiliary_checks_keep_non_blocking_semantics(self):
        c = _controller(True, [{'field': '辅助业务检查', 'status': 'PENDING'}])
        self.assertEqual(c.weak_endpoint_unverified(SimpleNamespace(task={'fragment': {}})), [])

    def test_contracted_goal_evidence_endpoint_is_exempt(self):
        c = _controller(True, [{'field': 'r', 'status': 'UNVERIFIED'}], finish_kind='goal_evidence')
        with patch('webcollect.banded_plan.contract_for', return_value={'kind': 'calculation'}):
            self.assertEqual(c.weak_endpoint_unverified(SimpleNamespace(task={'fragment': {}})), [])


def _outcome(checks, stop='ready'):
    task = {'fragment': {'ending_policy': 'webcollect-continuous-attempt-ending-4'}, 'instruction': '获得两种换算结果'}
    record = {'terminal': {'stop_reason': stop,
                           'goal_evidence': {'business_goal_status': 'PARTIAL', 'checks': checks}}}
    state = {'visible_text': '狗狗年龄计算器\n相当于人类', 'title': '狗狗年龄计算器', 'values': []}
    return terminal_outcome(task, record, state)


class TerminalOutcomeGateTests(unittest.TestCase):
    def test_unverified_declared_result_is_failed_not_success(self):
        status, description = _outcome([
            {'field': '年龄输入回显', 'status': 'VERIFIED', 'visible_text': '7'},
            {'field': '本次计算的换算结果区', 'status': 'UNVERIFIED'}])
        self.assertEqual(status, 'failed')
        self.assertIn('本次计算的换算结果区', description)

    def test_pending_does_not_block_and_verified_facts_lead_summary(self):
        status, description = _outcome([
            {'field': '人类等效年龄', 'status': 'VERIFIED', 'visible_text': '28 岁'},
            {'field': '辅助业务检查', 'status': 'PENDING'}])
        self.assertEqual(status, 'success')
        self.assertTrue(description.startswith('已核验目标事实：'))
        self.assertIn('人类等效年龄「28 岁」', description)

    def test_no_declared_checks_keeps_original_success(self):
        status, _ = _outcome([])
        self.assertEqual(status, 'success')


if __name__ == '__main__':
    unittest.main()
