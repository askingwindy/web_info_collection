"""Isolated runtime/history failure injection; no production ledger or models."""
import asyncio
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from webcollect.collect_runtime import _with_lease
from webcollect.current_chain import SCOPE_SCHEMA, history_scope_extends
from webcollect.task_generation import bind_formal_history
from webcollect.agent_feedback import (_verify_feedback_evidence,
    _verified_feedback_versions)


class LeaseCoverageTests(unittest.IsolatedAsyncioTestCase):
    async def test_threaded_preparation_and_closeout_keep_reserved_lease_alive(self):
        class Store:
            status = 'reserved'
            expiry = time.monotonic() + .18
            seen = []
            def heartbeat(self, *args):
                if time.monotonic() >= self.expiry:
                    raise ValueError('expired owner')
                self.seen.append(self.status)
                self.expiry = time.monotonic() + .18
        store = Store()
        attempt = dict(attempt_id='a', worker_id='w', lease_token='t')
        async def prepare():
            await asyncio.to_thread(time.sleep, .35)
            store.status = 'running'
        await _with_lease(prepare(), store, attempt, .18)
        async def execute_and_closeout():
            await asyncio.to_thread(time.sleep, .35)
            return 'saved_pending_review'
        result = await _with_lease(execute_and_closeout(), store, attempt, .18)
        self.assertEqual(result, 'saved_pending_review')
        self.assertIn('reserved', store.seen)
        self.assertIn('running', store.seen)

    async def test_committed_owner_heartbeat_does_not_cancel_thread_return_closeout(self):
        from webcollect.runtime import OwnedAttemptClosed
        class Store:
            closed = False
            def heartbeat(self, *args):
                if self.closed:
                    raise OwnedAttemptClosed('same owner committed')
        store = Store()
        closed_out = asyncio.Event()
        async def execute():
            store.closed = True
            # Inject the finish-thread-return window, then local close-out.
            await asyncio.sleep(.15)
            closed_out.set()
            return 'pending_review'
        result = await _with_lease(execute(), store,
            dict(attempt_id='a', worker_id='w', lease_token='t'), .18)
        self.assertEqual(result, 'pending_review')
        self.assertTrue(closed_out.is_set())

    async def test_lost_lease_cancels_execution(self):
        class Store:
            def heartbeat(self, *args):
                raise ValueError('expired owner')
        cancelled = asyncio.Event()
        async def execute():
            try:
                await asyncio.sleep(5)
            finally:
                cancelled.set()
        with self.assertRaisesRegex(ValueError, 'expired owner'):
            await _with_lease(execute(), Store(),
                dict(attempt_id='a', worker_id='w', lease_token='t'), .18)
        self.assertTrue(cancelled.is_set())


class RuntimeFencingTests(unittest.TestCase):
    def test_expired_reserved_owner_cannot_renew_or_start(self):
        import json
        import sqlite3
        from webcollect.runtime import RuntimeStore
        from webcollect.storage import ensure_registry_schema
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory)/'registry.sqlite3'
            with sqlite3.connect(registry) as con:
                ensure_registry_schema(con)
            store = RuntimeStore(registry, 'isolated')
            store.initialize({'campaign_id':'isolated', 'lease_seconds':120}, now=1000)
            task = {'task_id':'t','task_version':'1','site_uri':'https://example.org/', 'site_category':'工具'}
            with sqlite3.connect(registry) as con:
                con.execute('INSERT INTO m4_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    ('t','isolated','isolated','t','1','hash',json.dumps(task),'工具',
                     'example.org','queued',1,5000,1000,1000))
                con.execute('INSERT INTO m4_plan_tasks VALUES(?,?,?,?)', ('isolated','plan','t',0))
            attempt = store.claim_next('worker', request_id='claim', now=1000)
            owned = (attempt['attempt_id'], 'worker', attempt['lease_token'])
            store.heartbeat(*owned, now=1100)
            with self.assertRaisesRegex(ValueError, '过期'):
                store.heartbeat(*owned, now=1220)
            with self.assertRaisesRegex(ValueError, '过期'):
                store.start_attempt(*owned, now=1220)
            from webcollect.runtime import OwnedAttemptClosed
            with sqlite3.connect(registry) as con:
                con.execute("UPDATE m4_attempts SET status='rejected',finished_at=1200 WHERE attempt_id=?", (owned[0],))
            with self.assertRaises(OwnedAttemptClosed):
                store.heartbeat(*owned, now=1300)
            with self.assertRaises(ValueError) as wrong_owner:
                store.heartbeat(owned[0], 'other-worker', owned[2], now=1300)
            self.assertNotIsInstance(wrong_owner.exception, OwnedAttemptClosed)
            with sqlite3.connect(registry) as con:
                con.execute("UPDATE m4_attempts SET status='interrupted',root_cause='lease_expired' WHERE attempt_id=?", (owned[0],))
            with self.assertRaises(ValueError) as recovered:
                store.heartbeat(*owned, now=1300)
            self.assertNotIsInstance(recovered.exception, OwnedAttemptClosed)


class HistoryAppendTests(unittest.TestCase):
    def setUp(self):
        self.scope = dict(schema_version=SCOPE_SCHEMA, manifest={'path':'/isolated/manifest.json', 'sha256':'fixed'},
            chain_id='fixture', registry='/isolated/registry.sqlite3', current_result_roots=['/isolated'],
            candidate_project={'schema_version':'candidate-project-2'}, current_results_refs=[{'path':'/isolated/a','sha256':'a'}],
            research_results_refs=[], customer_samples=1, research_samples=0,
            known_strategy_samples=1, unknown_strategy_samples=0)

    def test_concurrent_peer_append_keeps_callers_original_snapshot(self):
        actual = deepcopy(self.scope)
        actual['current_results_refs'].append({'path':'/isolated/b','sha256':'b'})
        actual.update(customer_samples=2, known_strategy_samples=2)
        with patch('webcollect.current_chain.read_chain_history', return_value=([], actual)):
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(bind_formal_history, [self.scope, deepcopy(self.scope)]))
        self.assertEqual(results, [self.scope, self.scope])

    def test_bound_reference_mutation_removal_and_manifest_change_fail(self):
        for change in ('mutate', 'remove', 'manifest'):
            actual = deepcopy(self.scope)
            if change == 'mutate': actual['current_results_refs'][0]['sha256'] = 'changed'
            if change == 'remove': actual['current_results_refs'] = []
            if change == 'manifest': actual['manifest']['sha256'] = 'changed'
            with self.subTest(change=change):
                self.assertFalse(history_scope_extends(self.scope, actual))
                with patch('webcollect.current_chain.read_chain_history', return_value=([], actual)):
                    with self.assertRaisesRegex(ValueError, 'population changed'):
                        bind_formal_history(self.scope)

    def test_legacy_frozen_chain_still_requires_exact_population(self):
        bound = deepcopy(self.scope); bound.pop('candidate_project')
        actual = deepcopy(bound); actual['current_results_refs'].append({'path':'b','sha256':'b'})
        self.assertFalse(history_scope_extends(bound, actual))


class FeedbackVersionTests(unittest.TestCase):
    def test_cache_reuses_only_unchanged_verified_bytes_and_detects_tamper(self):
        _verified_feedback_versions.cache_clear()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'original.json'; path.write_bytes(b'original')
            refs = [{'path':str(path), 'sha256':hashlib.sha256(b'original').hexdigest()}]
            _verify_feedback_evidence(refs)
            _verify_feedback_evidence(refs)
            self.assertEqual(_verified_feedback_versions.cache_info().hits, 1)
            path.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'SHA'):
                _verify_feedback_evidence(refs)
            path.unlink(); path.symlink_to(Path(directory)/'missing')
            with self.assertRaises(ValueError):
                _verify_feedback_evidence(refs)


if __name__ == '__main__':
    unittest.main()
