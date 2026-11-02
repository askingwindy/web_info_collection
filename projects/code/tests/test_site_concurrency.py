"""Controlled concurrency/recovery tests, never real sites or delivery evidence."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from m4_runtime_fixtures import evidence, make_plan, make_registry
from webcollect.collect_runtime import collect_m4, runtime_scope
from webcollect.production_quality import ConcurrentExactImageIndex, sha
from webcollect.runtime import ImageCommitConflict, RuntimeStore
from webcollect.site_scheduler import run_schedule, validate_schedule


class RuntimeAtomicCommitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.registry = make_registry(self.root / 'registry.sqlite3')
        self.policy = {'baseline_category_counts': {}, 'max_workers': 2, 'max_domain_workers': 1}
        self.stores = []
        self.attempts = []
        for i, domain in enumerate(('example.org', 'example.net')):
            plan, publication = make_plan(self.root / ('plan-' + str(i)), uri='https://' + domain + '/', task_prefix='site-' + str(i))
            store = RuntimeStore(self.registry, 'scope-' + str(i))
            store.initialize(self.policy)
            store.enqueue_plan(plan, publication, now=1800000000)
            attempt = store.claim_next('worker-' + str(i), request_id='request-' + str(i), now=1800000000)
            store.start_attempt(attempt['attempt_id'], attempt['worker_id'], attempt['lease_token'], now=1800000000)
            self.stores.append(store)
            self.attempts.append(attempt)

    def image(self, attempt, content):
        path = self.root / attempt['scope_id'] / 'samples' / attempt['sample_id'] / 'images' / 'step_001.png'
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
        return {str(path): sha(path)}

    def test_same_digest_race_commits_exactly_one_success(self):
        images = [self.image(attempt, b'controlled-identical-image') for attempt in self.attempts]
        refs = [evidence(self.root / ('saved-' + str(i))) for i in range(2)]
        barrier = threading.Barrier(2)
        def commit(i):
            row = self.attempts[i]
            barrier.wait()
            try:
                self.stores[i].finish_attempt(row['attempt_id'], row['worker_id'], row['lease_token'],
                    'collected_pending_review', evidence=refs[i], exact_images=images[i], now=1800000001)
                return 'success'
            except ImageCommitConflict:
                return 'duplicate'
        with ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(commit, range(2)))
        self.assertEqual(sorted(outcomes), ['duplicate', 'success'])
        self.assertEqual(len(self.stores[0].exact_image_claims()), 1)
        statuses = [store.snapshot()['attempts'][0]['status'] for store in self.stores]
        self.assertEqual(statuses.count('collected_pending_review'), 1)
        self.assertEqual(statuses.count('running'), 1)

    def test_changed_image_rejected_before_success_and_claim(self):
        row = self.attempts[0]
        images = self.image(row, b'original')
        Path(next(iter(images))).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, '不一致'):
            self.stores[0].finish_attempt(row['attempt_id'], row['worker_id'], row['lease_token'],
                'collected_pending_review', evidence=evidence(self.root / 'receipt'), exact_images=images, now=1800000001)
        self.assertEqual(self.stores[0].exact_image_claims(), [])
        self.assertEqual(self.stores[0].snapshot()['attempts'][0]['status'], 'running')

    def test_snapshot_ignores_inflight_and_detects_accepted_tampering(self):
        first, second = self.attempts
        first_images = self.image(first, b'first')
        self.image(second, b'inflight-may-be-partial')
        index = ConcurrentExactImageIndex([self.root / first['scope_id'], self.root / second['scope_id']], self.stores[0])
        self.assertEqual(index.verify_snapshot()['image_count'], 0)
        self.stores[0].finish_attempt(first['attempt_id'], first['worker_id'], first['lease_token'],
            'collected_pending_review', evidence=evidence(self.root / 'receipt'), exact_images=first_images, now=1800000001)
        self.assertEqual(index.verify_snapshot()['image_count'], 1)
        Path(next(iter(first_images))).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '未登记变化'):
            index.verify_snapshot()


class ConcurrentSitesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self, *, cleanup_owner=None):
        # A nested fixture is not run by unittest and has no asyncio runner.
        # Its resources must belong to the currently running case, otherwise
        # nested.doCleanups() silently records runner errors without stopping
        # the global patches.
        add_cleanup = (cleanup_owner or self).addCleanup
        self.temp = tempfile.TemporaryDirectory()
        add_cleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.registry = make_registry(self.root / 'registry.sqlite3')
        self.policy = {'baseline_category_counts': {}, 'max_workers': 2, 'max_domain_workers': 1}
        self.policy_path = self.root / 'policy.json'
        self.policy_path.write_text(json.dumps(self.policy))
        self.config = {'schema_version': 'webcollect-site-schedule-1', 'registry': str(self.registry),
                       'max_parallel_sites': 2, 'max_schedule_seconds': 20, 'sites': []}
        for i, domain in enumerate(('example.org', 'example.net')):
            with patch('m4_runtime_fixtures.NOW', time.time()):
                plan, publication = make_plan(self.root / ('planning-' + str(i)), uri='https://' + domain + '/', task_prefix='site-' + str(i))
            plan_path, pub_path = self.root / ('plan-' + str(i) + '.json'), self.root / ('pub-' + str(i) + '.json')
            plan_path.write_text(json.dumps(plan)); pub_path.write_text(json.dumps(publication))
            self.config['sites'].append({'site_key': 'site-' + str(i), 'batches': [{
                'plan': str(plan_path), 'publication': str(pub_path), 'policy': str(self.policy_path),
                'output': str(self.root / 'batches' / ('site-' + str(i)))}]})
        context = MagicMock()
        context.close = AsyncMock()
        browser = MagicMock(version='controlled-concurrent-browser')
        browser.new_context = AsyncMock(side_effect=lambda **kwargs: self.new_context())
        browser.close = AsyncMock()
        playwright = MagicMock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=playwright)
        manager.__aexit__ = AsyncMock(return_value=False)
        self.contexts = []
        for target, value in [('playwright.async_api.async_playwright', MagicMock(return_value=manager)),
                              ('webcollect.collect_runtime.validate_sample', MagicMock(return_value={'structural_pass': True})),
                              ('webcollect.evidence.audit_capture', MagicMock(return_value={'capture_evidence_pass': True})),
                              ('webcollect.metadata.export_metadata', MagicMock(side_effect=lambda batch, path: Path(path).write_text('CONTROLLED metadata\n')))]:
            patcher = patch(target, value)
            patcher.start(); add_cleanup(patcher.stop)

    def new_context(self):
        context = MagicMock()
        context.close = AsyncMock()
        self.contexts.append(context)
        return context

    async def capture(self, context, task, sample, raw, ids, *, same=False):
        (sample / 'images').mkdir(parents=True)
        raw.mkdir(parents=True)
        (sample / 'images' / 'step_001.png').write_bytes(b'CONTROLLED-' + (b'same' if same else ids['sample_id'].encode()))
        (sample / 'annotation.json').write_text('{"controlled_fixture_only":true}')

    async def test_two_domains_overlap_with_distinct_contexts_and_shared_numbering(self):
        active, peak = 0, 0
        both = asyncio.Event()
        async def capture(*args):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                both.set()
            await asyncio.wait_for(both.wait(), 5)
            await self.capture(*args)
            active -= 1
        with patch('webcollect.collect.collect_one', capture):
            result = await run_schedule(self.config, self.root / 'schedule')
        self.assertEqual(peak, 2)
        self.assertEqual(result['peak_active_sites'], 2)
        self.assertEqual(result['status'], 'COLLECTED_PENDING_REVIEW')
        self.assertEqual(result['qualified_samples'], 0)
        self.assertEqual(len({id(context) for context in self.contexts}), 2)
        ids = []
        for site in self.config['sites']:
            store = RuntimeStore(self.registry, runtime_scope(site['batches'][0]['output']))
            ids += [row['sample_id'] for row in store.snapshot()['attempts']]
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(len(store.exact_image_claims()), 2)
        async def should_not_repeat(*args):
            self.fail('A committed capture must not execute again during resume')
        with patch('webcollect.collect.collect_one', should_not_repeat):
            resumed = await run_schedule(self.config, self.root / 'schedule', resume=True)
        self.assertEqual(resumed['status'], 'COLLECTED_PENDING_REVIEW')
        self.assertEqual(sum(len(RuntimeStore(self.registry, runtime_scope(site['batches'][0]['output'])).snapshot()['attempts'])
                             for site in self.config['sites']), 2)

    async def test_actual_collectors_cannot_both_commit_identical_image(self):
        count = 0
        both = asyncio.Event()
        async def capture(*args):
            nonlocal count
            count += 1
            if count == 2:
                both.set()
            await asyncio.wait_for(both.wait(), 5)
            await self.capture(*args, same=True)
        with patch('webcollect.collect.collect_one', capture):
            result = await run_schedule(self.config, self.root / 'schedule')
        outcomes = [row['result'] for row in result['batch_results']]
        self.assertEqual(sum(row['collected'] for row in outcomes), 1)
        self.assertEqual(sum(row['rejected'] for row in outcomes), 1)
        self.assertEqual(result['status'], 'PAUSED')
        self.assertEqual(result['qualified_samples'], 0)

    async def test_setting_one_site_serializes_execution(self):
        self.config['max_parallel_sites'] = 1
        self.policy['max_workers'] = 1
        self.policy_path.write_text(json.dumps(self.policy))
        active, peak = 0, 0
        async def fake(*args, **kwargs):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            await asyncio.sleep(.02)
            active -= 1
            return {'collection_status': 'finished_pending_review', 'collected': 1}
        result = await run_schedule(self.config, self.root / 'schedule', collector=fake)
        self.assertEqual(peak, 1)
        self.assertEqual(result['peak_active_sites'], 1)

    async def test_policy_conflict_is_rejected_before_dispatch(self):
        self.policy_path.write_text(json.dumps({'baseline_category_counts': {}, 'max_workers': 1}))
        called = AsyncMock()
        with self.assertRaisesRegex(ValueError, 'max_parallel_sites must equal'):
            await run_schedule(self.config, self.root / 'schedule', collector=called)
        called.assert_not_called()

    async def test_shared_limit_cannot_exceed_local_site_setting(self):
        self.config['max_parallel_sites'] = 1
        with self.assertRaisesRegex(ValueError, 'max_parallel_sites must equal'):
            validate_schedule(self.config)

    async def test_bound_resume_rejects_concurrency_source_drift(self):
        async def fake(*args, **kwargs):
            return {'collection_status': 'finished_pending_review', 'collected': 1}
        with patch('webcollect.site_scheduler.source_identity', return_value={'controlled-scheduler': 'before'}):
            await run_schedule(self.config, self.root / 'schedule', collector=fake)
        with patch('webcollect.site_scheduler.source_identity', return_value={'controlled-scheduler': 'after'}):
            with self.assertRaisesRegex(ValueError, 'binding changed'):
                await run_schedule(self.config, self.root / 'schedule', resume=True, collector=fake)

    async def test_schedule_evidence_cannot_pollute_capture_output(self):
        capture = Path(self.config['sites'][0]['batches'][0]['output'])
        with self.assertRaisesRegex(ValueError, 'separate directories'):
            await run_schedule(self.config, capture / 'schedule-evidence', collector=AsyncMock())
        self.assertFalse(capture.exists())

    async def test_one_logical_site_batches_remain_serial_with_domain_capacity_two(self):
        self.policy['max_domain_workers'] = 2
        self.policy_path.write_text(json.dumps(self.policy))
        self.config['sites'] = self.config['sites'][:1]
        other = json.loads(json.dumps(self.config['sites'][0]['batches'][0]))
        other['output'] = str(self.root / 'batches' / 'same-site-next-uri')
        self.config['sites'][0]['batches'].append(other)
        order = []
        active = 0
        async def fake(plan, output, registry, **kwargs):
            nonlocal active
            active += 1
            self.assertEqual(active, 1)
            order.append(Path(output).name)
            await asyncio.sleep(.01)
            active -= 1
            return {'collection_status': 'finished_pending_review', 'collected': 1}
        result = await run_schedule(self.config, self.root / 'schedule', collector=fake)
        self.assertEqual(order, ['site-0', 'same-site-next-uri'])
        self.assertEqual(result['status'], 'COLLECTED_PENDING_REVIEW')

    async def test_same_domain_sites_cannot_bypass_shared_domain_limit(self):
        path = Path(self.config['sites'][1]['batches'][0]['plan'])
        plan = json.loads(path.read_text())
        for task in plan['tasks']:
            task['site_uri'] = 'https://other.example.org/different-uri'
        path.write_text(json.dumps(plan))
        active, peak = 0, 0
        async def fake(*args, **kwargs):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            await asyncio.sleep(.02)
            active -= 1
            return {'collection_status': 'finished_pending_review', 'collected': 1}
        result = await run_schedule(self.config, self.root / 'schedule', collector=fake)
        self.assertEqual(peak, 1)
        self.assertEqual(result['peak_active_sites'], 1)

    async def test_pending_work_does_not_block_another_site_dispatch(self):
        calls = 0
        self.config['max_parallel_sites'] = 1
        self.policy['max_workers'] = 1
        self.policy['pending_review_cap'] = 1
        self.policy_path.write_text(json.dumps(self.policy))
        async def fake(*args, **kwargs):
            nonlocal calls
            calls += 1
            return {'collection_status': 'finished_pending_review', 'collected': 1}
        result = await run_schedule(self.config, self.root / 'schedule', collector=fake)
        self.assertEqual(calls, len(self.config['sites']))
        self.assertEqual(result['status'], 'COLLECTED_PENDING_REVIEW')

    async def test_cancellation_has_no_success_and_bound_resume_keeps_one_count(self):
        entered = asyncio.Event()
        async def blocked(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        work = asyncio.create_task(run_schedule(self.config, self.root / 'schedule', collector=blocked))
        await entered.wait()
        work.cancel()
        result = await work
        self.assertTrue(result['interrupted'])
        self.assertEqual(result['status'], 'PAUSED')
        self.assertEqual(result['qualified_samples'], 0)
        async def recovered(*args, **kwargs):
            self.assertTrue(kwargs['resume'])
            return {'collection_status': 'finished_pending_review', 'collected': 1}
        resumed = await run_schedule(self.config, self.root / 'schedule', resume=True, collector=recovered)
        self.assertEqual(len(resumed['batch_results']), 2)
        self.assertEqual(resumed['status'], 'COLLECTED_PENDING_REVIEW')
        changed = json.loads(json.dumps(self.config)); changed['max_schedule_seconds'] = 21
        with self.assertRaisesRegex(ValueError, 'binding changed'):
            await run_schedule(changed, self.root / 'schedule', resume=True, collector=recovered)

    async def test_actual_cancel_preserves_partial_and_resume_holds_interruption(self):
        self.config['sites'] = self.config['sites'][:1]
        self.config['max_parallel_sites'] = 1
        self.policy['max_workers'] = 1
        self.policy_path.write_text(json.dumps(self.policy))
        entered = asyncio.Event()
        async def partial(*args):
            await self.capture(*args)
            entered.set()
            await asyncio.Event().wait()
        with patch('webcollect.collect.collect_one', partial):
            work = asyncio.create_task(run_schedule(self.config, self.root / 'schedule'))
            await asyncio.wait_for(entered.wait(), 5)
            work.cancel()
            result = await work
        self.assertTrue(result['interrupted'])
        output = Path(self.config['sites'][0]['batches'][0]['output'])
        store = RuntimeStore(self.registry, runtime_scope(output))
        original = store.snapshot()['attempts'][0]
        self.assertEqual(original['status'], 'rejected')
        self.assertEqual(original['failure_class'], 'interrupted')
        self.assertTrue((output / 'rejected' / original['sample_id'] / 'annotation.json').is_file())
        self.assertEqual(store.exact_image_claims(), [])
        with patch('webcollect.collect.collect_one', self.capture):
            resumed = await run_schedule(self.config, self.root / 'schedule', resume=True)
        self.assertEqual(resumed['status'], 'PAUSED',resumed)
        self.assertEqual([r['sample_id'] for r in store.snapshot()['attempts']],[original['sample_id']])
        self.assertEqual(store.snapshot()['tasks'][0]['status'],'needs_replan')
        self.assertTrue((output/'rejected'/original['sample_id']/'annotation.json').is_file())

    async def test_two_scheduler_instances_share_the_global_site_limit(self):
        for i, domain in enumerate(('example.com', 'example.edu'), start=2):
            with patch('m4_runtime_fixtures.NOW', time.time()):
                plan, publication = make_plan(self.root / ('planning-' + str(i)), uri='https://' + domain + '/', task_prefix='site-' + str(i))
            plan_path, pub_path = self.root / ('plan-' + str(i) + '.json'), self.root / ('pub-' + str(i) + '.json')
            plan_path.write_text(json.dumps(plan)); pub_path.write_text(json.dumps(publication))
            self.config['sites'].append({'site_key': 'site-' + str(i), 'batches': [{
                'plan': str(plan_path), 'publication': str(pub_path), 'policy': str(self.policy_path),
                'output': str(self.root / 'batches' / ('site-' + str(i)))}]})
        first = json.loads(json.dumps(self.config)); first['sites'] = first['sites'][:2]
        second = json.loads(json.dumps(self.config)); second['sites'] = second['sites'][2:]
        active, peak = 0, 0
        async def capture(*args):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            await asyncio.sleep(.1)
            await self.capture(*args)
            active -= 1
        with patch('webcollect.collect.collect_one', capture):
            results = await asyncio.gather(run_schedule(first, self.root / 'schedule-first'),
                                           run_schedule(second, self.root / 'schedule-second'))
        self.assertEqual(peak, 2)
        self.assertTrue(all(row['status'] == 'COLLECTED_PENDING_REVIEW' for row in results), results)
        self.assertEqual(sum(row['result']['collected'] for run in results for row in run['batch_results']), 4)


if __name__ == '__main__':
    unittest.main()
