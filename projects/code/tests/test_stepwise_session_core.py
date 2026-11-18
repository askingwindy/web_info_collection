"""Stepwise bounded completion and actual-request/effect accounting, fully offline."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from webcollect.batch_core import BudgetStop
from webcollect.stepwise.session import StepwiseSession, StepwiseStop, stepwise_caller


def capture(text='计算器 参数 结果', color='white'):
    png = io.BytesIO()
    Image.new('RGB', (40, 30), color).save(png, format='PNG')
    return {'png': png.getvalue(), 'capture': {}, 'state': {
        'url': 'https://example.org/tool', 'title': '计算器',
        'document_identity': 'doc', 'visible_text': text,
        'screen_resolution': [40, 30], 'elements': [], 'values': [], 'scroll': [0, 0]}}


def decision(**extra):
    return {'action': 'complete', 'status': 'success', 'task_goal': '查看参数并比较结果',
            'last_step_result': '结果已显示', 'page_name': '计算器',
            'precondition': '结果可见', 'thought': '确认结果', 'user_goal': '查看结果',
            'expected_result': '完成比较', **extra}


class StepwiseSessionCore(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_autonomous_completion_and_specified_goal(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
                'webcollect.stepwise.session.browser.verify_execution_state', new=AsyncMock()):
            def new(name, requested_goal=None):
                call = AsyncMock()
                call.requests_used = lambda: 0
                session = StepwiseSession({'task_id': name, 'site_uri': 'https://example.org/tool'},
                    Path(tmp) / name, call, object(), attempt_id=name, requested_goal=requested_goal)
                session.current = session.journal.add_frame(capture())
                session.effective = 3
                session.goal = '查看参数'
                return session

            extended = new('extended')
            self.assertFalse(await extended._handle_complete(extended.current, decision()))
            self.assertIsNone(extended.complete_decision)
            self.assertIsNone(extended.complete_completed_at)
            self.assertEqual(extended.complete_rejections[0]['effective_steps'], 3)
            self.assertIn('第 1 步起', extended.feedback)
            self.assertTrue((extended.root / 'complete-rejection-001.json').is_file())
            extended.effective = 5
            self.assertTrue(await extended._handle_complete(extended.current, decision()))
            self.assertEqual(extended.stop_reason, 'complete_success')

            bounded = new('bounded')
            self.assertFalse(await bounded._handle_complete(bounded.current, decision()))
            self.assertFalse(await bounded._handle_complete(bounded.current, decision()))
            with self.assertRaises(StepwiseStop) as stopped:
                await bounded._handle_complete(bounded.current, decision())
            self.assertEqual(stopped.exception.stop_reason, 'short_flow')
            self.assertEqual(len(bounded.complete_rejections), 2)
            self.assertIsNone(bounded.complete_decision)

            specified = new('specified', {'instruction': '查看原指定结果'})
            with self.assertRaises(StepwiseStop) as stopped:
                await specified._handle_complete(specified.current, decision())
            self.assertEqual(stopped.exception.stop_reason, 'short_flow')
            self.assertEqual(specified.complete_rejections, [])

            infeasible = new('infeasible')
            self.assertFalse(await infeasible._handle_complete(infeasible.current, decision(status='infeasible')))
            with self.assertRaises(StepwiseStop) as stopped:
                await infeasible._handle_complete(infeasible.current, decision(status='infeasible'))
            self.assertEqual(stopped.exception.stop_reason, 'complete_infeasible')
            malformed = decision()
            malformed.pop('status')
            self.assertIn('STATUS_REQUIRED', extended._validate_decision(malformed, False))
            self.assertIsNone(extended._validate_decision(decision(), False))

    async def test_actual_http_reserve_and_visible_effect_accounting(self):
        class Ledger:
            used = 33
            config = {'model': {'max_completion_tokens': 2048}}
            def connect(self): return contextlib.nullcontext(None)
            def session_http_usage(self, con, attempt): return {'used': self.used, 'unresolved': None}
            def enqueue(self, kind, payload): return 'job-' + str(self.used)
            def get(self, jid): return {'state': 'queued', 'attempts': 0}
            def claim(self, kind, **kwargs): return {'id': kwargs['job_id']}
            def finish(self, *args, **kwargs): pass

        ledger = Ledger()
        attempts = []
        class Gateway:
            def __init__(self, ledger, runlog=None): self.ledger = ledger
            def call_tool(self, *args, **kwargs):
                attempts.append(kwargs['attempts'])
                self.ledger.used += kwargs['attempts']
                return {'arguments': decision()}

        with patch('webcollect.model_gateway.ModelGateway', Gateway):
            call = stepwise_caller(ledger, {'task_id': 't', 'site_uri': 'https://example.org'}, 'a')
            kwargs = dict(system='', tools=[], user_text='', images=[], reasoning_effort='low',
                          dispatch_deadline=None, round_index=1, tool_name='next_action')
            await call(phase='decision', **kwargs)
            self.assertEqual((attempts, call.requests_used()), ([1], 34))
            with self.assertRaises(BudgetStop):
                await call(phase='decision', **kwargs)
            for phase in ('writeback', 'writeback', 'judgement'):
                await call(phase=phase, **kwargs)
            self.assertEqual((attempts, call.requests_used()), ([1, 2, 2, 2], 40))

        with tempfile.TemporaryDirectory() as tmp:
            def new(name, used=0):
                call = AsyncMock()
                call.requests_used = lambda: used
                session = StepwiseSession({'task_id': name, 'site_uri': 'https://example.org/tool'},
                    Path(tmp) / name, call, object(), attempt_id=name)
                session.current = session.journal.add_frame(capture())
                return session

            exhausted = new('exhausted', used=32)
            exhausted.effective = 3
            with self.assertRaises(StepwiseStop) as stopped:
                await exhausted._loop()
            self.assertEqual(stopped.exception.stop_reason, 'short_flow')
            exhausted.call.assert_not_awaited()
            operation = {'action_type': 'click', 'arguments': {'x': 1, 'y': 1},
                         'evidence': {'collection_strategy': 'stepwise'}}
            # Disallowed link schemes never reach browser dispatch.
            for scheme in ('mailto', 'tel', 'file', 'data'):
                forbidden = new('scheme-' + scheme)
                forbidden.call.return_value = {'arguments': decision(action='click', element=1)}
                forbidden._link_carrier = lambda frame, element, scheme=scheme: {'href': scheme + ':blocked'}
                forbidden._dispatch = AsyncMock()
                with patch('webcollect.stepwise.session.observation.bind_action', return_value=(operation, None)):
                    with self.assertRaises(StepwiseStop) as stopped:
                        await forbidden._loop()
                self.assertEqual(stopped.exception.stop_reason, 'repeat_reject')
                self.assertIn('NAVIGATION_SCHEME_NOT_PERMITTED', forbidden.feedback)
                forbidden._dispatch.assert_not_awaited()

            pending_navigation = {'navigation_expected': True, 'navigation_observed': False,
                                  'href': 'https://example.org/next'}
            delayed = new('delayed-navigation')
            delayed._execute_observed = AsyncMock(return_value=pending_navigation)
            delayed._capture = AsyncMock(return_value=capture())
            with self.assertRaises(StepwiseStop) as stopped:
                await delayed._dispatch(delayed.current, operation, None, decision(action='click'))
            self.assertEqual((stopped.exception.stop_reason, stopped.exception.failure_class),
                             ('navigation_unconfirmed', 'collector'))
            self.assertFalse(stopped.exception.unknown)
            self.assertEqual((delayed.dispatches, delayed.no_effect_run, delayed.dispatch_rows), (1, 0, []))
            self.assertTrue(delayed.failed_dispatches[0]['action_executed'])

            # A completed host return plus a failed screenshot is a capture fault,
            # while a timeout in the actual return dispatch remains unknown.
            for phase in ('capture', 'dispatch'):
                recovery = new('recovery-' + phase)
                rejected = recovery.journal.add_frame(capture('范围外页面', color='red'))
                recovery._capture = AsyncMock(side_effect=TimeoutError('slow screenshot'))
                execute = AsyncMock(side_effect=TimeoutError('uncertain back')) if phase == 'dispatch' else AsyncMock()
                with patch('webcollect.stepwise.session.browser.execute', new=execute):
                    with self.assertRaises(StepwiseStop) as stopped:
                        await recovery._restore_landing(recovery.current, rejected, recovery.page, 0, 'out_of_scope')
                raw = json.loads(Path(recovery.failed_dispatches[0]['step_file']).read_text())
                self.assertEqual(stopped.exception.stop_reason, 'capture_timeout' if phase == 'capture' else 'unknown_dispatch')
                self.assertEqual(stopped.exception.unknown, phase == 'dispatch')
                self.assertEqual(raw['action_executed'], True if phase == 'capture' else None)

            same_pixels = new('same-pixels')
            same_pixels._execute_observed = AsyncMock(return_value=None)
            same_pixels._capture = AsyncMock(return_value=capture('结果已变成新数值'))
            await same_pixels._dispatch(same_pixels.current, operation, None, decision(action='click'))
            self.assertEqual(same_pixels.effective, 0)
            self.assertFalse(same_pixels.dispatch_rows[0]['omittable'])
            self.assertIn('不计入有效步', same_pixels.feedback)
            same_pixels.effective = 5
            same_pixels.current = same_pixels.journal.frames[same_pixels.dispatch_rows[-1]['after_frame']]
            with patch('webcollect.stepwise.session.browser.verify_execution_state', new=AsyncMock()):
                with self.assertRaises(StepwiseStop) as stopped:
                    await same_pixels._handle_complete(same_pixels.current, decision())
            self.assertEqual(stopped.exception.stop_reason, 'unproven_effect')
            self.assertEqual(stopped.exception.failure_class, 'collector')

            no_effect = new('no-effect')
            no_effect._execute_observed = AsyncMock(return_value=None)
            no_effect._capture = AsyncMock(return_value=capture())
            await no_effect._dispatch(no_effect.current, operation, None, decision(action='click'))
            self.assertEqual((no_effect.effective, no_effect.no_effect_run), (0, 1))
            self.assertIn('1/3', no_effect.feedback)
            changed = new('tab-change')
            changed._execute_observed = AsyncMock(return_value=pending_navigation)
            changed._capture = AsyncMock(return_value=capture('标签二内容', color='blue'))
            await changed._dispatch(changed.current, operation, None, decision(action='click'))
            self.assertEqual(changed.effective, 1)
