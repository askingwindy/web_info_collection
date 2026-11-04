"""Pure mocked completion windows; no browser, model, or real trajectory IO."""
from contextlib import ExitStack
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from webcollect import collect
from webcollect.browser import fingerprint, EvidenceStale

STALE = '截图后页面状态发生变化，拒绝用陈旧坐标或终态执行：elements'
URI = 'https://example.org/CONTROLLED-completion'
CONDITIONS = [{'visible_text': '最终完成'}]


def frame(number=0, assertions=CONDITIONS):
    state = {'url': URI, 'title': '合成完成验证', 'screen_resolution': [1280, 720],
        'device_pixel_ratio': 1, 'scroll': {'x': 0, 'y': 0}, 'values': [], 'target': None,
        'visible_text': '合成测试，最终完成。全部内容均为离线夹具。', 'text_blocks': [], 'embedded_frames': [],
        'elements': [{'element_id': 'CONTROLLED-header', 'text': '合成顶栏', 'element_type': 'text',
                      'bbox': [number, 0, number + 100, 20]}],
        'assertion_targets': [None for _ in assertions or []]}
    png = ('CONTROLLED-PNG-' + str(number)).encode()
    return {'state': state, 'png': png, 'capture': {'screenshot_sha256': hashlib.sha256(png).hexdigest(),
        'attempts': [{'dom_stable': True, 'before_fingerprint': fingerprint(state), 'after_fingerprint': fingerprint(state)}]}}


class CompleteRefreshTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    async def test_late_once_then_stable_recaptures_full_frame_and_all_assertions(self):
        first, second = frame(0), frame(75)
        with patch.object(collect, 'capture', AsyncMock(side_effect=[first, second])) as capture, \
                patch.object(collect, 'verify_execution_state', AsyncMock(side_effect=[EvidenceStale(STALE),
                    {'matched': True, 'state_fingerprint': fingerprint(second['state'])}])) as verify, \
                patch.object(collect.asyncio, 'sleep', AsyncMock()) as wait, \
                patch.object(collect, 'execute', AsyncMock()) as execute:
            result = await collect.capture_complete(object(), self.root, assertions=CONDITIONS)
        self.assertEqual(result['png'], second['png'])
        self.assertEqual(capture.await_count, 2)
        self.assertEqual(verify.await_count, 2)
        self.assertEqual([c.args[0] for c in wait.await_args_list], [1, .25, 1])
        execute.assert_not_called()
        timing = result['terminal_refresh']
        self.assertEqual([a['status'] for a in timing['attempts']], ['stale_rejected', 'accepted'])
        self.assertTrue(all(a['assertions'][0]['passed'] for a in timing['attempts']))
        self.assertEqual(timing['natural_wait_requested_ms'], 2250)
        self.assertGreaterEqual(timing['natural_wait_observed_ms'], 0)
        self.assertGreaterEqual(timing['elapsed_seconds'], 0)
        rejected = json.loads((self.root / 'terminal_candidates/candidate_001.json').read_text())
        self.assertTrue(rejected['diagnostic_only'])
        self.assertFalse(rejected['accepted_as_formal_frame'])
        self.assertEqual(rejected['state'], first['state'])
        self.assertEqual((self.root / 'terminal_candidates/candidate_001.png').read_bytes(), first['png'])

    async def test_persistent_change_rejects_original_error_after_three_candidates(self):
        errors = [EvidenceStale(STALE) for _ in range(3)]
        with patch.object(collect, 'capture', AsyncMock(side_effect=[frame(i) for i in range(3)])) as capture, \
                patch.object(collect, 'verify_execution_state', AsyncMock(side_effect=errors)), \
                patch.object(collect.asyncio, 'sleep', AsyncMock()), \
                patch.object(collect, 'execute', AsyncMock()) as execute:
            with self.assertRaises(ValueError) as caught:
                await collect.capture_complete(object(), self.root, assertions=CONDITIONS)
        self.assertIs(caught.exception, errors[-1])
        self.assertEqual(capture.await_count, 3)
        self.assertFalse(caught.exception.terminal_refresh['accepted'])
        self.assertEqual(caught.exception.terminal_refresh['natural_wait_requested_ms'], 3500)
        self.assertEqual(len(list((self.root / 'terminal_candidates').glob('*.png'))), 3)
        execute.assert_not_called()

    async def test_failed_assertion_is_not_retried_or_waived(self):
        wrong = frame(); wrong['state']['visible_text'] = '合成缺少必要终态'
        with patch.object(collect, 'capture', AsyncMock(return_value=wrong)) as capture, \
                patch.object(collect, 'verify_execution_state', AsyncMock()) as verify, \
                patch.object(collect.asyncio, 'sleep', AsyncMock()) as wait:
            with self.assertRaisesRegex(ValueError, '目标文字未在实际视口'):
                await collect.capture_complete(object(), self.root, assertions=CONDITIONS)
        self.assertEqual(capture.await_count, 1); verify.assert_not_called(); wait.assert_not_called()

    async def test_unrelated_guard_failure_is_not_retried(self):
        with patch.object(collect, 'capture', AsyncMock(return_value=frame())) as capture, \
                patch.object(collect, 'verify_execution_state', AsyncMock(side_effect=ValueError('CONTROLLED different failure'))), \
                patch.object(collect.asyncio, 'sleep', AsyncMock()):
            with self.assertRaisesRegex(ValueError, 'CONTROLLED different failure'):
                await collect.capture_complete(object(), self.root, assertions=CONDITIONS)
        self.assertEqual(capture.await_count, 1)

    async def test_overall_deadline_rejects_a_stalled_capture_without_publication(self):
        original_wait_for = asyncio.wait_for
        async def stalled(*args, **kwargs):
            await asyncio.Future()
        async def short_deadline(coroutine, timeout):
            self.assertEqual(timeout, 12)
            return await original_wait_for(coroutine, timeout=.001)
        with patch.object(collect, 'capture', AsyncMock(side_effect=stalled)), \
                patch.object(collect.asyncio, 'wait_for', side_effect=short_deadline), \
                patch.object(collect, 'verify_execution_state', AsyncMock()) as verify:
            with self.assertRaises(TimeoutError) as caught:
                await collect.capture_complete(object(), self.root, assertions=CONDITIONS)
        self.assertFalse(caught.exception.terminal_refresh['accepted'])
        self.assertEqual(caught.exception.terminal_refresh['timeout_seconds'], 12)
        self.assertFalse(list(self.root.rglob('*.png')))
        verify.assert_not_called()

    async def collector(self, persistent):
        directory, evidence = self.root / 'sample', self.root / 'evidence'
        page = MagicMock(url=URI); page.goto = AsyncMock(); page.evaluate = AsyncMock(return_value=1)
        page.wait_for_timeout = AsyncMock(); page.close = AsyncMock()
        context = MagicMock(pages=[page]); context.new_page = AsyncMock(return_value=page)
        task = {'task_id': 'CONTROLLED-completion', 'task_version': 'CONTROLLED-1',
            'instruction': '合成五次必要操作后核对终态。', 'task_type': ['填写表单'],
            'site_uri': URI, 'initial_url': URI, 'app_name': '合成完成验证', 'initial_settle_ms': 0,
            'stop_when_final': False, 'content_preparation': False,
            'operations': [{'action_type': 'hotkey', 'arguments': {'keys': ['Tab']},
                'goal': '合成操作', 'rationale': '离线协议测试', 'expected': '显示合成状态'} for _ in range(5)],
            'final_assertions': CONDITIONS, 'final_result': '计划完成', 'completion_judgement': '计划核对'}
        task['operations'][-1]['postconditions'] = CONDITIONS
        original = deepcopy(task); final_checks = 0; final_captures = 0

        async def capture(*args, assertions=None, **kwargs):
            nonlocal final_captures
            if assertions:
                final_captures += 1
            return frame(final_captures, assertions=assertions)

        async def verify(page, state, *args, assertions=None, **kwargs):
            nonlocal final_checks
            if assertions:
                final_checks += 1
                if persistent or final_checks <= 2:
                    # Both the rejected candidate and accepted preflight occur
                    # before publication of terminal or previous-step bindings.
                    self.assertFalse((directory / 'images/step_006.png').exists())
                    self.assertFalse((directory / 'ui_tree/step_006.json').exists())
                    self.assertFalse((evidence / 'step_005_postconditions.json').exists())
                    self.assertFalse((evidence / 'step_005_narrative.json').exists())
                if persistent or final_checks == 1:
                    raise EvidenceStale(STALE)
            return {'matched': True, 'state_fingerprint': fingerprint(state)}

        with ExitStack() as stack:
            for name, value in {
                'capture': AsyncMock(side_effect=capture), 'verify_execution_state': AsyncMock(side_effect=verify),
                'observe': AsyncMock(return_value=frame()['state']),
                'execute': AsyncMock(), 'assess_content': AsyncMock(return_value={'page_url': URI,
                    'decision': {'action': 'ready', 'reason': 'CONTROLLED unobstructed'}}),
                'describe_change': MagicMock(return_value='合成后续状态已确认')}.items():
                stack.enter_context(patch.object(collect, name, value))
            wait = stack.enter_context(patch.object(collect.asyncio, 'sleep', AsyncMock()))
            stack.enter_context(patch('webcollect.task_contract.is_m4_task', return_value=True))
            stack.enter_context(patch('webcollect.task_contract.validate_m4_task'))
            stack.enter_context(patch('webcollect.task_contract.narrative_evidence',
                return_value=('合成后续状态已确认', {'machine_status': 'PASS'})))
            stack.enter_context(patch('webcollect.task_contract.terminal_evidence',
                return_value={'machine_status': 'PASS', 'semantic_status': 'REVIEW_REQUIRED'}))
            if persistent:
                with self.assertRaisesRegex(ValueError, '截图后页面状态发生变化'):
                    await collect.collect_one(context, task, directory, evidence, {'sample_id': 'CONTROLLED-only'})
                self.assertFalse((directory / 'annotation.json').exists())
                self.assertFalse((directory / 'images/step_006.png').exists())
                self.assertFalse((evidence / 'step_005_postconditions.json').exists())
                self.assertFalse((evidence / 'step_005_narrative.json').exists())
                self.assertEqual([c.args[1] for c in collect.execute.await_args_list], ['hotkey'] * 5)
                self.assertTrue((evidence / 'terminal_refresh_failure.json').is_file())
            else:
                result = await collect.collect_one(context, task, directory, evidence, {'sample_id': 'CONTROLLED-only'})
                self.assertEqual([c.args[1] for c in collect.execute.await_args_list], ['hotkey'] * 5 + ['complete'])
                self.assertEqual(final_checks, 3)  # Original post-publication preflight remains.
                raw = json.loads((evidence / 'step_006.json').read_text())
                self.assertEqual(len(raw['terminal_refresh']['attempts']), 2)
                self.assertTrue(raw['state_preflight']['matched'])
                self.assertTrue((evidence / 'step_005_postconditions.json').is_file())
                self.assertTrue((evidence / 'step_005_narrative.json').is_file())
                self.assertEqual(len(result['steps']), 6)
            self.assertEqual(task, original)

    async def test_collector_defers_all_terminal_bindings_and_never_replays_actions(self):
        await self.collector(False)

    async def test_collector_persistent_change_publishes_no_partial_terminal_bindings(self):
        await self.collector(True)


if __name__ == '__main__': unittest.main()
