"""F1–F4 integration on disposable claims/Runtime and original IO fixtures."""
import asyncio
from copy import deepcopy
import time
import unittest
from unittest.mock import patch

import test_candidate_entry_engineering as entry
import test_react_native as native
from webcollect.batch_core import BudgetStop
from webcollect.candidate_consumer import consume
from webcollect.consumer_lifecycle import claim_job
from webcollect import browser
from webcollect.react_session import ReactSession
from test_react_session import make_png

ORIGINAL_CAPTURE = browser.capture


class MinfixIntegration(unittest.IsolatedAsyncioTestCase):
    def fixture(self):
        f = entry.EntryEngineering('test_entry_cli_to_original_save_and_same_page')
        f.setUp()
        self.addCleanup(f.doCleanups)
        return f

    async def test_queued_congestion_resumes_same_claim_and_formally_saves(self):
        f = self.fixture()
        blocker = f.ledger.claim('test-blocker', job_id=f.ledger.enqueue('test-blocker', {'fixture':True}))
        async def release():
            await asyncio.sleep(.02)
            f.ledger.finish(blocker)
        timer = asyncio.create_task(release())
        with f.io_boundaries():
            result = await consume(f.pool, f.claim, f.ledger, output=f.output,
                registry=f.registry, policy=f.policy_path, history_set=f.chain)
        await timer
        self.assertTrue(result['saved'], result)
        self.assertEqual(f.pool.get_claim(f.claim['claim_id'])['state'], 'succeeded')
        with f.ledger.connect() as con:
            self.assertGreater(con.execute("select count(*) from batch_events where event='consumer_congestion_wait'").fetchone()[0], 0)
            self.assertEqual(con.execute("select count(*) from jobs where state='running'").fetchone()[0], 0)
        self.assertEqual(len(f.gotos), 1)

    async def test_budget_and_unknown_are_not_congestion_retried(self):
        f = self.fixture()
        with patch.object(f.ledger, 'claim', side_effect=BudgetStop('model budget exhausted')) as call:
            with self.assertRaisesRegex(BudgetStop, 'budget exhausted'):
                await claim_job(f.ledger, 'collection', job_id='never-dispatched')
        self.assertEqual(call.call_count, 1)

    async def test_cancel_drains_runtime_job_and_claim_preserving_reserved_request(self):
        f = self.fixture()
        entered = asyncio.Event()
        request = {}
        async def waiting(session):
            with f.ledger.connect() as con:
                job = dict(con.execute("select * from jobs where kind='collection' and state='running'").fetchone())
            request.update(f.ledger.reserve_request(job, 'controlled-pending', 0, {}))
            entered.set()
            await asyncio.Event().wait()
        with f.io_boundaries(), patch.object(ReactSession, '_round', waiting):
            task = asyncio.create_task(consume(f.pool, f.claim, f.ledger, output=f.output,
                registry=f.registry, policy=f.policy_path, history_set=f.chain))
            await asyncio.wait_for(entered.wait(), 20)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(f.pool.get_claim(f.claim['claim_id'])['state'], 'reconcile')
        with f.ledger.connect() as con:
            self.assertEqual(con.execute("select count(*) from jobs where state='running'").fetchone()[0], 0)
            self.assertEqual(con.execute('select state from model_requests where id=?',(request['id'],)).fetchone()[0], 'reserved')
        import sqlite3
        with sqlite3.connect(f.registry) as con:
            self.assertEqual(con.execute("select count(*) from m4_attempts where status in ('reserved','running')").fetchone()[0], 0)
            self.assertEqual(con.execute('select failure_class from m4_attempts').fetchone()[0], 'interrupted')

    async def test_cancel_drains_runtime_job_and_claim_preserving_unknown_request(self):
        f = self.fixture()
        entered = asyncio.Event()
        request = {}
        async def waiting(session):
            with f.ledger.connect() as con:
                job = dict(con.execute("select * from jobs where kind='collection' and state='running'").fetchone())
            request.update(f.ledger.reserve_request(job, 'controlled-pending', 0, {}))
            with f.ledger.connect() as con:
                request['original_reserved_cost'] = con.execute('select reserved_cost from model_requests where id=?',(request['id'],)).fetchone()[0]
            f.ledger.settle_request(request['id'], state='unknown', error='CONTROLLED unresolved HTTP outcome')
            entered.set()
            await asyncio.Event().wait()
        with f.io_boundaries(), patch.object(ReactSession, '_round', waiting):
            task = asyncio.create_task(consume(f.pool, f.claim, f.ledger, output=f.output,
                registry=f.registry, policy=f.policy_path, history_set=f.chain))
            await asyncio.wait_for(entered.wait(), 20)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(f.pool.get_claim(f.claim['claim_id'])['state'], 'reconcile')
        with f.ledger.connect() as con:
            self.assertEqual(con.execute("select count(*) from jobs where state='running'").fetchone()[0], 0)
            self.assertEqual(con.execute('select state from model_requests where id=?',(request['id'],)).fetchone()[0], 'unknown')
            self.assertEqual(con.execute('select reserved_cost from model_requests where id=?',(request['id'],)).fetchone()[0], request['original_reserved_cost'])
        import sqlite3
        with sqlite3.connect(f.registry) as con:
            self.assertEqual(con.execute("select count(*) from m4_attempts where status in ('reserved','running')").fetchone()[0], 0)
            self.assertEqual(con.execute('select failure_class from m4_attempts').fetchone()[0], 'interrupted')

    async def test_hard_deadline_uses_same_cancel_closeout(self):
        f = self.fixture()
        async def waiting(session):
            await asyncio.Event().wait()
        with f.io_boundaries(), patch.object(ReactSession, '_round', waiting):
            with self.assertRaisesRegex(TimeoutError, 'hard_deadline'):
                await consume(f.pool, f.claim, f.ledger, output=f.output,
                    registry=f.registry, policy=f.policy_path, history_set=f.chain,
                    session_soft_seconds=.1, session_hard_seconds=2)
        self.assertEqual(f.pool.get_claim(f.claim['claim_id'])['state'], 'reconcile')
        with f.ledger.connect() as con:
            self.assertEqual(con.execute("select count(*) from jobs where state='running'").fetchone()[0], 0)

    async def test_soft_deadline_closes_at_verified_action_boundary(self):
        f = native.NativeSessionTests('test_native_tool_round_trip_filters_permissions_keeps_private_history')
        f.setUp(); self.addCleanup(f.doCleanups)
        session, evidence, script = f.recorded([native.scroll('阅读下方'), native.finish()])
        session.host_limits = {'soft_seconds':720, 'hard_seconds':900, 'started_monotonic':time.monotonic()}
        original = session._round
        async def one_round():
            await original()
            session.host_limits['started_monotonic'] = time.monotonic()-721
        session._round = one_round
        result = await session.run()
        self.assertEqual(result['effective_steps'], 1)
        self.assertEqual(result['stop_reason'], 'budget')
        self.assertFalse(result['unknown'])
        self.assertTrue((evidence/'raw/raw-receipt.json').exists())
        self.assertEqual(len(f.surface.executed), 1)
        self.assertEqual(len(script.prompts), 1)

    async def test_transient_capture_shares_attempt_budget_without_replaying_action(self):
        f = native.NativeSessionTests('test_native_tool_round_trip_filters_permissions_keeps_private_history')
        f.setUp(); self.addCleanup(f.doCleanups)
        state = deepcopy(f.surface.state)
        png = make_png(0)
        observations = [RuntimeError('Execution context was destroyed'), state, state]
        async def observe(*args, **kwargs):
            item = observations.pop(0)
            if isinstance(item, Exception): raise item
            return deepcopy(item)
        async def shot(*args, **kwargs): return png, {'method':'fixture'}
        with patch.object(browser, 'observe', side_effect=observe), patch.object(browser, 'viewport_png', side_effect=shot):
            result = await ORIGINAL_CAPTURE(f.page, retries=8, total_timeout=2)
        self.assertEqual(len(result['capture']['attempts']), 2)
        self.assertEqual(result['capture']['attempts'][0]['action_replayed'], False)
        self.assertEqual(f.surface.executed, [])
        with patch.object(browser, 'observe', side_effect=ValueError('UNSUPPORTED_GEOMETRY')) as call, patch.object(browser, 'viewport_png', side_effect=shot):
            with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_GEOMETRY'):
                await ORIGINAL_CAPTURE(f.page, retries=8, total_timeout=2)
        self.assertEqual(call.call_count, 1)
