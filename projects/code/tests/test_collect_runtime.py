"""Controlled orchestration tests; no real websites or production registry."""
import tempfile
import unittest
import json
from pathlib import Path
from webcollect.production_quality import sha
from webcollect.collect_runtime import (CollectionFailure, classify_failure,
    quarantine_interrupted, sample_hashes, verify_committed_samples)


class RecoveryAdapterTests(unittest.TestCase):
    def test_only_explicit_transport_errors_are_retryable(self):
        self.assertEqual(classify_failure(ValueError('net::ERR_CONNECTION_RESET')), 'network')
        self.assertEqual(classify_failure(ValueError('Page.goto: Timeout 30000ms exceeded')), 'network')
        self.assertEqual(classify_failure(ValueError('Locator.wait_for: Timeout 30000ms exceeded')), 'semantic')
        self.assertEqual(classify_failure(TimeoutError()), 'semantic')
        self.assertEqual(classify_failure(CollectionFailure('same screenshot', 'duplicate')), 'duplicate')

    def test_planning_choice_rejections_are_model_not_site_failures(self):
        """M4_TARGET_LABEL_UNREADABLE is a plan defect: the task replans, the
        site keeps its failure margin (sync_formal skips 'model')."""
        from webcollect.browser import PlanLabelUnreadable, PlanViewportInfeasible
        error = PlanLabelUnreadable('M4_TARGET_LABEL_UNREADABLE: 目标文字未完整可读')
        self.assertEqual(classify_failure(error), 'model')
        self.assertEqual(classify_failure(PlanViewportInfeasible('目标未出现在当前视口')), 'collector')
        # The exact legacy message raised as a bare ValueError still maps to
        # semantic only when it is not the typed planning exception.
        self.assertEqual(classify_failure(ValueError('M4_TARGET_LABEL_UNREADABLE: x')), 'semantic')

    def test_committed_completion_is_verified_and_failed_partial_is_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('done', 'partial'):
                sample = root / 'samples' / name
                sample.mkdir(parents=True)
                (sample / 'annotation.json').write_text(name)
            receipt = root / 'evidence' / 'done' / 'saved_sample.json'
            receipt.parent.mkdir(parents=True)
            (receipt.parent / 'step_001.json').write_text('original capture fixture')
            receipt.write_text(json.dumps({'sample_id': 'done', 'attempt_id': 'attempt-1',
                'sample_files_sha256': sample_hashes(root / 'samples' / 'done'),
                'capture_files_sha256': sample_hashes(receipt.parent)}))
            attempts = [
                {'sample_id': 'done', 'attempt_id': 'attempt-1', 'status': 'collected_pending_review',
                 'evidence': [{'path': str(receipt.resolve()), 'sha256': sha(receipt)}]},
                {'sample_id': 'partial', 'status': 'rejected'}]
            verify_committed_samples(root, attempts)
            quarantine_interrupted(root, attempts)
            self.assertTrue((root / 'samples' / 'done' / 'annotation.json').is_file())
            self.assertTrue((root / 'rejected' / 'partial' / 'annotation.json').is_file())
            self.assertFalse((root / 'samples' / 'partial').exists())
            (root / 'samples' / 'done' / 'annotation.json').write_text('tampered')
            with self.assertRaisesRegex(ValueError, '停止续跑'):
                verify_committed_samples(root, attempts)

    def test_quarantine_will_not_overwrite_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'samples' / 'partial').mkdir(parents=True)
            (root / 'rejected' / 'partial').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, '拒绝覆盖'):
                quarantine_interrupted(root, [{'sample_id': 'partial', 'status': 'rejected'}])


class CollectorIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import time
        from unittest.mock import patch, AsyncMock, MagicMock
        from m4_runtime_fixtures import make_plan, make_registry
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        with patch('m4_runtime_fixtures.NOW', time.time()):
            self.plan, self.publication = make_plan(self.root / 'planning')
        self.registry = make_registry(self.root / 'registry.sqlite3')
        self.output = self.root / 'batches' / 'batch'
        self.plan_path = self.root / 'plan.json'
        self.publication_path = self.root / 'publication.json'
        self.policy_path = self.root / 'policy.json'
        for path, value in [(self.plan_path, self.plan), (self.publication_path, self.publication),
                            (self.policy_path, {'baseline_category_counts': {}})]:
            path.write_text(json.dumps(value))
        context = MagicMock()
        context.close = AsyncMock()
        browser = MagicMock(version='controlled-mock-browser')
        browser.new_context = AsyncMock(return_value=context)
        browser.close = AsyncMock()
        playwright = MagicMock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=playwright)
        manager.__aexit__ = AsyncMock(return_value=False)
        for target, value in [('playwright.async_api.async_playwright', MagicMock(return_value=manager)),
                              ('webcollect.collect_runtime.validate_sample', MagicMock(return_value={'structural_pass': True})),
                              ('webcollect.evidence.audit_capture', MagicMock(return_value={'capture_evidence_pass': True})),
                              ('webcollect.metadata.export_metadata', MagicMock(side_effect=
                                lambda batch, path: Path(path).write_text('synthetic metadata fixture\n')))]:
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.executed = []

    async def fake_collect(self, context, task, sample, evidence, ids):
        # Explicit synthetic bytes exercise persistence only, never visual/QC claims.
        self.executed.append(ids['sample_id'])
        (sample / 'images').mkdir(parents=True)
        evidence.mkdir(parents=True)
        (sample / 'images' / 'step_001.png').write_bytes(b'synthetic-not-delivery-' + ids['sample_id'].encode())
        (sample / 'annotation.json').write_text(json.dumps({'fixture_only': True}))

    async def run_collector(self, resume=False):
        from webcollect.collect_runtime import collect_m4
        return await collect_m4(self.plan_path, self.output, self.registry,
            publication_path=self.publication_path, policy_path=None if resume else self.policy_path,
            resume=resume)

    async def test_program_failure_pauses_before_second_allocation(self):
        from unittest.mock import patch
        import time
        from m4_runtime_fixtures import make_plan
        from webcollect.collect_runtime import runtime_scope
        from webcollect.runtime import RuntimeStore
        with patch('m4_runtime_fixtures.NOW', time.time()):
            plan, publication = make_plan(self.root / 'two-task-program', 2)
        self.plan_path.write_text(json.dumps(plan)); self.publication_path.write_text(json.dumps(publication))
        with patch('webcollect.collect.collect_one', self.fake_collect), patch(
                'webcollect.collect_runtime.validate_sample', return_value={'structural_pass':False,'issues':['controlled schema mismatch']}):
            result = await self.run_collector()
        snapshot = RuntimeStore(self.registry,runtime_scope(self.output)).snapshot()
        self.assertEqual(result['actual_attempts'],1); self.assertEqual(result['rejected'],1)
        self.assertEqual(snapshot['scope']['state'],'paused')
        self.assertEqual(len(snapshot['attempts']),1)
        self.assertEqual(sum(t['status']=='queued' for t in snapshot['tasks']),1)
        self.assertEqual(snapshot['attempts'][0]['failure_class'],'program')

    async def test_site_semantic_failure_does_not_pause_other_task(self):
        from unittest.mock import patch
        import time
        from m4_runtime_fixtures import make_plan
        from webcollect.collect_runtime import runtime_scope
        from webcollect.runtime import RuntimeStore
        with patch('m4_runtime_fixtures.NOW', time.time()):
            plan, publication = make_plan(self.root / 'two-task-semantic', 2)
        self.plan_path.write_text(json.dumps(plan)); self.publication_path.write_text(json.dumps(publication))
        async def fail(*args):
            await self.fake_collect(*args)
            raise ValueError('controlled site-specific target mismatch')
        with patch('webcollect.collect.collect_one', fail):result = await self.run_collector()
        snapshot = RuntimeStore(self.registry,runtime_scope(self.output)).snapshot()
        self.assertEqual(result['actual_attempts'],2)
        self.assertEqual(snapshot['scope']['state'],'active')
        self.assertTrue(all(a['failure_class']=='semantic' for a in snapshot['attempts']))

    async def test_resume_rebuilds_lost_manifest_without_executing_committed_success(self):
        from unittest.mock import patch
        with patch('webcollect.collect.collect_one', self.fake_collect):
            first = await self.run_collector()
            self.assertEqual(first['collected'], 1)
            manifest = self.output / 'manifest.json'
            body = json.loads(manifest.read_text())
            body.update(samples=[], attempts=[], batch_id=None, collection_status='in_progress')
            manifest.write_text(json.dumps(body))
            resumed = await self.run_collector(resume=True)
        self.assertEqual(len(self.executed), 1)
        self.assertEqual(resumed['actual_attempts'], 1)
        self.assertEqual(resumed['collected'], 1)
        self.assertEqual(resumed['qualified_samples'], 0)
        self.assertEqual(resumed['collection_status'], 'finished_pending_review')

    async def test_interrupted_started_attempt_is_preserved_without_automatic_reexecution(self):
        import sqlite3
        from unittest.mock import patch
        class ProcessStopped(BaseException):
            pass
        async def interrupted(*args):
            await self.fake_collect(*args)
            raise ProcessStopped('controlled interruption after partial files')
        with patch('webcollect.collect.collect_one', interrupted):
            with self.assertRaises(ProcessStopped):
                await self.run_collector()
        # Controlled fault injection into this test DB only, simulating elapsed lease.
        con = sqlite3.connect(self.registry)
        try:
            with con:
                con.execute('UPDATE m4_attempts SET lease_expires_at=0')
        finally:
            con.close()
        import time
        from webcollect.runtime import RuntimeStore
        manifest = json.loads((self.output / 'manifest.json').read_text())
        store = RuntimeStore(self.registry, manifest['runtime_scope_id'])
        store.recover_expired(now=time.time()-2)
        with patch('webcollect.collect.collect_one', self.fake_collect):
            resumed = await self.run_collector(resume=True)
        self.assertEqual(len(self.executed), 1)
        self.assertTrue((self.output / 'rejected' / self.executed[0] / 'annotation.json').is_file())
        self.assertEqual(resumed['actual_attempts'], 1)
        self.assertEqual(resumed['rejected'], 1)
        self.assertEqual(resumed['collected'], 0)
        self.assertEqual(resumed['qualified_samples'], 0)
        self.assertEqual(store.snapshot()['tasks'][0]['status'], 'needs_replan')

    async def test_semantic_failure_is_not_retried_on_resume(self):
        from unittest.mock import patch
        async def failed(*args):
            await self.fake_collect(*args)
            raise ValueError('任务尚未真正完成')
        with patch('webcollect.collect.collect_one', failed):
            result = await self.run_collector()
            resumed = await self.run_collector(resume=True)
        self.assertEqual(result['rejected'], 1)
        self.assertEqual(resumed['actual_attempts'], 1)
        self.assertEqual(len(self.executed), 1)

    async def test_tampered_committed_bytes_prevent_resume(self):
        from unittest.mock import patch
        with patch('webcollect.collect.collect_one', self.fake_collect):
            await self.run_collector()
            path = self.output / 'samples' / self.executed[0] / 'annotation.json'
            path.write_text('changed after commit')
            with self.assertRaisesRegex(ValueError, '停止续跑'):
                await self.run_collector(resume=True)
        self.assertEqual(len(self.executed), 1)

    async def test_tampered_capture_evidence_prevents_resume(self):
        from unittest.mock import patch
        with patch('webcollect.collect.collect_one', self.fake_collect):
            await self.run_collector()
            path = self.output / 'evidence' / self.executed[0] / 'capture_audit.json'
            path.write_text('changed original capture audit')
            with self.assertRaisesRegex(ValueError, '原始采集证据改变'):
                await self.run_collector(resume=True)
        self.assertEqual(len(self.executed), 1)

    async def test_same_output_second_runner_is_rejected_before_start(self):
        import fcntl
        from webcollect.collect_runtime import runtime_scope
        self.output.parent.mkdir(parents=True)
        lock_path = self.output.parent / ('.' + runtime_scope(self.output) + '.lock')
        with lock_path.open('a+') as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, '第二runner'):
                await self.run_collector()
        self.assertFalse(self.output.exists())

    async def test_missing_explicit_wave_policy_does_not_initialize_ledger(self):
        from webcollect.collect_runtime import collect_m4
        original = self.registry.read_bytes()
        with self.assertRaisesRegex(ValueError, '必须提供 --policy'):
            await collect_m4(self.plan_path, self.output, self.registry,
                             publication_path=self.publication_path)
        self.assertEqual(self.registry.read_bytes(), original)
        self.assertFalse(self.output.exists())

    async def test_resource_stop_precedes_claim_and_resume_preserves_budget_events(self):
        from unittest.mock import patch
        from webcollect.runtime import RuntimeStore
        from webcollect.collect_runtime import runtime_scope
        self.policy_path.write_text(json.dumps({'baseline_category_counts': {},
            'resource_root': str(self.output.parent), 'max_output_bytes': 1}))
        with patch('webcollect.collect.collect_one', self.fake_collect):
            stopped = await self.run_collector()
            self.assertEqual(stopped['actual_attempts'], 0)
            self.assertEqual(stopped['reserved_allocations'], 0)
            self.assertEqual(self.executed, [])
            store = RuntimeStore(self.registry, runtime_scope(self.output))
            before = store.snapshot()
            self.assertEqual(before['scope']['state'], 'paused')
            self.assertTrue(any(row['event_type']=='resource_checkpoint' and row['payload']['status']=='STOP'
                                for row in before['events']))
            store.update_policy({'max_output_bytes': 10000000}, 'Synthetic test explicit storage budget adjustment')
            store.set_scope_paused(False, 'Synthetic operator verified storage allowance')
            result = await self.run_collector(resume=True)
        self.assertEqual(result['collected'], 1)
        self.assertEqual(result['actual_attempts'], 1)
        self.assertTrue(all(event in store.snapshot()['events'] for event in before['events']))

    async def test_network_backoff_retries_within_the_same_invocation(self):
        from unittest.mock import patch
        async def transient(*args):
            await self.fake_collect(*args)
            if len(self.executed) < 3:
                raise ValueError('net::ERR_CONNECTION_RESET')
        with patch('webcollect.collect.collect_one', transient):
            result = await self.run_collector()
        self.assertEqual(result['actual_attempts'], 3)
        self.assertEqual(result['rejected'], 2)
        self.assertEqual(result['collected'], 1)
        self.assertEqual(len(set(self.executed)), 3)

    async def test_accounted_outer_navigation_timeout_is_retried_and_keeps_root_cause(self):
        import asyncio
        from unittest.mock import patch
        from webcollect.batch_core import BatchLedger, load_json
        from webcollect.navigation import BatchNavigation
        from webcollect.collect_runtime import runtime_scope
        from webcollect.runtime import RuntimeStore

        class SlowPage:
            url = 'about:blank'
            def on(self, *args): pass
            def remove_listener(self, *args): pass
            async def goto(self, uri, **kwargs):
                self.url = uri
                await asyncio.sleep(1)

        config = load_json(Path(__file__).resolve().parents[1] / 'config/batch-no-model.json')
        config['mode'] = 'synthetic'  # SlowPage is a simulation; no real dispatch permission.
        ledger = BatchLedger(self.root / 'navigation.sqlite3', config, initialize=True)
        job = ledger.claim('test', job_id=ledger.enqueue('test', {'case': self._testMethodName}))
        navigation = BatchNavigation(ledger, job)
        async def transient(*args):
            await self.fake_collect(*args)
            if len(self.executed) == 1:
                await navigation.goto(SlowPage(), 'https://example.org/task',
                                      purpose='collection:timeout-fixture', timeout_ms=10)
        with patch('webcollect.collect.collect_one', transient):
            result = await self.run_collector()
        attempts = RuntimeStore(self.registry, runtime_scope(self.output)).attempt_ledger()['attempts']
        self.assertEqual((result['actual_attempts'], result['rejected'], result['collected']), (2, 1, 1))
        self.assertEqual(attempts[0]['failure_class'], 'network')
        self.assertEqual(attempts[0]['root_cause'], 'navigation_timeout')
        self.assertEqual(attempts[1]['retry_of'], attempts[0]['attempt_id'])
        self.assertNotEqual(attempts[0]['sample_id'], attempts[1]['sample_id'])
        self.assertEqual(len(ledger.visits()), 1)
        self.assertEqual(ledger.visits()[0]['state'], 'failed')
        self.assertTrue((self.output / 'evidence' / attempts[0]['sample_id'] / 'failure.json').is_file())

    async def test_postcapture_audit_remains_covered_by_lease(self):
        import time
        from unittest.mock import patch
        self.policy_path.write_text(json.dumps({'baseline_category_counts': {}, 'lease_seconds': 1}))
        def slow_audit(*args):
            time.sleep(1.4)
            return {'capture_evidence_pass': True}
        with patch('webcollect.collect.collect_one', self.fake_collect), patch('webcollect.evidence.audit_capture', slow_audit):
            result = await self.run_collector()
        self.assertEqual(result['collected'], 1)
        self.assertEqual(result['rejected'], 0)

    async def test_bootstrap_restores_missing_manifest_only_before_first_attempt(self):
        from unittest.mock import patch
        from webcollect.runtime import RuntimeStore
        class StoppedBeforeAllocation(BaseException):
            pass
        with patch.object(RuntimeStore, 'claim_next', side_effect=StoppedBeforeAllocation()):
            with self.assertRaises(StoppedBeforeAllocation):
                await self.run_collector()
        manifest = self.output / 'manifest.json'
        manifest.unlink()  # Controlled test loss, never a production cleanup.
        with patch('webcollect.collect.collect_one', self.fake_collect):
            result = await self.run_collector(resume=True)
        self.assertEqual(result['actual_attempts'], 1)
        self.assertEqual(result['collected'], 1)
        manifest.unlink()
        with self.assertRaisesRegex(ValueError, '已有attempt'):
            await self.run_collector(resume=True)


class LeaseCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_lost_lease_cancels_inflight_browser_job(self):
        import asyncio
        from unittest.mock import MagicMock
        from webcollect.collect_runtime import _with_lease
        cancelled = []
        async def page_job():
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.append(True)
        store = MagicMock()
        store.heartbeat.side_effect = ValueError('lease fenced')
        with self.assertRaisesRegex(ValueError, 'lease fenced'):
            await _with_lease(page_job(), store,
                {'attempt_id': 'a', 'worker_id': 'w', 'lease_token': 't'}, 0.3)
        self.assertEqual(cancelled, [True])
