"""Stepwise bounded completion and actual-request/effect accounting, fully offline."""
import asyncio
import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from webcollect.action_stability import post_action_document_scope
from webcollect.batch_core import BudgetStop
from webcollect.stepwise.session import StepwiseSession, StepwiseStop, stepwise_caller


def capture(text='计算器 参数 结果', color='white', source_url='https://example.org/tool'):
    png = io.BytesIO()
    Image.new('RGB', (40, 30), color).save(png, format='PNG')
    proof = {'stability': {'action_scope': post_action_document_scope({'url': source_url})}}
    return {'png': png.getvalue(), 'capture': {'attempts': [proof]}, 'state': {
        'url': 'https://example.org/tool', 'title': '计算器',
        'document_identity': 'doc', 'visible_text': text,
        'screen_resolution': [40, 30], 'elements': [], 'values': [], 'scroll': [0, 0]}}


def decision(**extra):
    return {'action': 'complete', 'status': 'success', 'task_goal': '查看参数并比较结果',
            'last_step_result': '结果已显示', 'page_name': '计算器',
            'precondition': '结果可见', 'thought': '确认结果', 'user_goal': '查看结果',
            'expected_result': '完成比较', **extra}


class StepwiseSessionCore(unittest.IsolatedAsyncioTestCase):
    async def test_redirected_capture_and_interrupted_rejection_streak(self):
        source_url = 'https://example.org/before-redirect'
        data = capture(source_url=source_url)
        def answer(action, **fields):
            args = decision(action=action)
            del args['status']
            return {'arguments': {**args, **fields}}
        bad = answer('type', text='50', task_goal='无效提议', note='无效笔记', last_step_result='驳回轮的结果')
        call = AsyncMock(side_effect=[bad, bad, answer('wait'), bad, bad, answer('complete', status='success')])
        call.requests_used = lambda: 0
        with tempfile.TemporaryDirectory() as folder:
            session = StepwiseSession({'site_uri': 'https://example.org/tool'}, folder, call, object(), attempt_id='a')
            session.current = session.journal.add_frame(data)
            session.effective = 5
            session._execute_observed = AsyncMock(return_value=None)
            session._capture = AsyncMock(return_value=data)
            with patch('webcollect.stepwise.session.browser.verify_execution_state', new=AsyncMock()) as verify:
                await session._loop()
            self.assertEqual(session.stop_reason, 'complete_success')
            self.assertEqual(session.dispatches, 1)
            self.assertEqual([c.kwargs['action_scope']['source_url'] for c in verify.await_args_list],
                             [source_url, source_url])
            rejects = [json.loads(p.read_text()) for p in sorted(session.root.glob('decision-rejection-*.json'))]
            self.assertEqual([r['consecutive'] for r in rejects], [1, 2, 1, 2])
            self.assertTrue(all(r['reason'].startswith('TYPE_ELEMENT_REQUIRED') for r in rejects))
            decisions = [json.loads(p.read_text()) for p in sorted(session.root.glob('decision-[0-9]*.json'))]
            self.assertEqual([r['accepted'] for r in decisions], [False, False, True, False, False, True])
            self.assertTrue(all(r['task_goal_before'] == r['task_goal_after'] and r['note_before'] == r['note_after']
                                for r in decisions if not r['accepted']))
            self.assertEqual(decisions[0]['arguments']['task_goal'], '无效提议')
            self.assertEqual(decisions[-1]['frame_page_name'], '网页「计算器」')
            self.assertEqual(session.initial_goal, '查看参数并比较结果')
            self.assertEqual(session.dispatch_rows[-1]['step_result'], '结果已显示')
            self.assertEqual(session.dispatch_rows[-1]['result_round'], 6)
            self.assertIn('实际观察：结果已显示', session.history[-1])
            varying = AsyncMock(side_effect=[answer('wait', precondition='显示「虚构%s」' % word)
                                             for word in ('甲','乙','丙')])
            varying.requests_used = lambda: 0
            blocked = StepwiseSession(session.task, Path(folder)/'citations', varying, object(), attempt_id='b')
            blocked.current = blocked.journal.add_frame(data)
            with self.assertRaises(StepwiseStop) as stopped:
                await blocked._loop()
            self.assertEqual((stopped.exception.stop_reason, blocked.dispatches), ('repeat_reject', 0))
            self.assertEqual([json.loads(p.read_text())['consecutive']
                              for p in sorted(blocked.root.glob('decision-rejection-*.json'))], [1,2,3])

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
            bounded.effective += 1
            self.assertFalse(await bounded._handle_complete(bounded.current, decision()))
            with self.assertRaises(StepwiseStop) as stopped:
                await bounded._handle_complete(bounded.current, decision())
            self.assertEqual(stopped.exception.stop_reason, 'short_flow')
            self.assertEqual(len(bounded.complete_rejections), 2)
            self.assertIsNone(bounded.complete_decision)

            finished_early = new('finished_early')
            self.assertFalse(await finished_early._handle_complete(finished_early.current, decision()))
            with self.assertRaises(StepwiseStop) as stopped:
                await finished_early._handle_complete(finished_early.current, decision())
            self.assertEqual((stopped.exception.stop_reason, len(finished_early.complete_rejections)), ('short_flow', 1))

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
            extended.decision_round = 3
            empty = decision(last_step_result='')
            self.assertIsNone(extended._validate_decision(empty, False, pending_result=False))
            self.assertTrue(extended._validate_decision(empty, False, pending_result=True).startswith('LAST_STEP_RESULT_REQUIRED'))
            self.assertIsNone(extended._validate_decision(decision(last_step_result='本帧显示数量50'), False, pending_result=True))

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

        entering, release, settled = threading.Event(), threading.Event(), threading.Event()
        receipts = []
        class DelayedGateway(Gateway):
            def call_tool(self, *args, **kwargs):
                entering.set()
                if not release.wait(5):
                    raise TimeoutError('fixture did not release the dispatched request')
                self.stopped = self.stop_pending_dispatch()
                return {'request_id':'original', 'cancelled_before_return':self.stopped}
        def finish(job, *, result):
            receipts.append((job['id'],result))
            settled.set()
        ledger.used = 0
        ledger.finish = finish
        with patch('webcollect.model_gateway.ModelGateway', DelayedGateway):
            owned = stepwise_caller(ledger, {'task_id':'t','site_uri':'https://example.org'}, 'interrupted')
            in_flight = asyncio.create_task(owned(phase='decision', **kwargs))
            try:
                self.assertTrue(await asyncio.to_thread(entering.wait, 3))
                in_flight.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await in_flight
            finally:
                release.set()
            self.assertTrue(await asyncio.to_thread(settled.wait, 3))
            self.assertEqual(receipts, [('job-0',{'request_id':'original','cancelled_before_return':True})])

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
