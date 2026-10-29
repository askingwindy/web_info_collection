"""Disposable SQLite/evidence fixtures; no real browser, provider, or production IO."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from site_planner.site_pool import SitePool
from webcollect.batch_core import file_sha, load_json, save_json
from webcollect.runtime import RuntimeStore
from webcollect.site_pool_reader import read_site_pool
from webcollect.site_pool_sync import apply_qc, guard_plan, page_state, pool_for_catalog
from webcollect.single_record import candidate
from m4_runtime_fixtures import NOW, evidence, make_plan, make_registry


def ref(path):
    return {'path': str(Path(path).resolve()), 'sha256': file_sha(path)}


def discover(pool, root, uri, event):
    return pool.record({'schema_version': 'webcollect-site-discovery-1', 'origin': 'codex_session',
        'run_id': 'CONTROLLED-offline', 'event_id': event, 'uri': uri,
        'name': '临时离线夹具', 'category_hint': '在线工具', 'source_refs': evidence(root / (event + '.txt'))})


class PoolLifecycleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.pool = SitePool(self.root / 'pool.sqlite3', initialize=True)
        self.uri = 'https://example.org/tool'
        discover(self.pool, self.root, self.uri, 'first')
        discover(self.pool, self.root, 'https://example.org/other', 'other')
        self.registry = make_registry(self.root / 'registry.sqlite3')
        self.store = RuntimeStore(self.registry, 'scope-a')
        self.store.initialize(now=NOW)
        self.store.bind_site_pool(self.pool.path)
        self.plan, self.publication = make_plan(self.root / 'planning', uri=self.uri)

    def enqueue(self):
        self.store.enqueue_plan(self.plan, self.publication, now=NOW)

    def captured(self):
        self.enqueue()
        row = self.store.claim_next('worker', request_id='first', now=NOW)
        self.store.start_attempt(row['attempt_id'], row['worker_id'], row['lease_token'], now=NOW)
        self.store.finish_attempt(row['attempt_id'], row['worker_id'], row['lease_token'],
            'collected_pending_review', evidence=evidence(self.root / 'saved.txt'), now=NOW + 1)
        return row

    def report(self, row, status='PASS'):
        from test_planning_runtime import PlanningRuntimeTests
        proof = PlanningRuntimeTests.qc_evidence(self, [row['sample_id']], status=status, stage='payload', release_ready=False)
        report = load_json(proof[0]['path']); report['status'] = status
        path = Path(proof[0]['path']).with_name('scoped-report.json')
        save_json(path, report)
        return ref(path)

    def state(self):
        return page_state(self.pool, self.uri)

    def test_collection_progress_is_automatic_and_other_function_stays_available(self):
        self.assertEqual(self.state()['status'], 'not_started')
        row = self.captured()
        self.assertEqual(self.state()['status'], 'collected_pending_review')
        self.assertFalse(self.state()['dispatch_allowed'])
        self.assertTrue(page_state(self.pool, 'https://example.org/other')['dispatch_allowed'])
        available = read_site_pool(self.pool.path)['records']
        self.assertEqual([r['uri'] for r in available], ['https://example.org/other'])
        self.assertEqual(len(read_site_pool(self.pool.path, include_unavailable=True)['records']), 2)
        with self.assertRaisesRegex(ValueError, 'active or completed'):
            candidate(self.pool.path, self.uri, self.root / 'blocked.json')
        self.assertEqual(self.store.snapshot()['attempts'][0]['sample_id'], row['sample_id'])

    def test_qc_pending_then_pass_is_automatic_idempotent_and_keeps_raw_outcome(self):
        row = self.captured()
        pending = self.report(row, 'REVIEW_REQUIRED')
        self.store.record_qc_report(pending)
        self.assertEqual(self.state()['status'], 'collected_pending_review')
        approved = self.report(row)
        self.store.record_qc_report(approved)
        self.assertEqual(self.state()['status'], 'reviewed_pass')
        before = self.store.snapshot()
        self.store.record_qc_report(approved)
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(before['attempts'][0]['status'], 'collected_pending_review')
        self.assertEqual(before['tasks'][0]['status'], 'reviewed_pass')
        self.assertEqual(len(self.state()['tasks'][0]['attempts']), 1)

    def test_qc_failure_preserves_evidence_and_does_not_complete_whole_site(self):
        row = self.captured(); report = self.report(row, 'FAIL')
        self.store.record_qc_report(report)
        self.assertEqual(self.state()['status'], 'qc_failed')
        self.assertEqual(self.store.snapshot()['tasks'][0]['status'], 'needs_replan')
        self.assertEqual(self.store.snapshot()['attempts'][0]['status'], 'collected_pending_review')
        self.assertTrue((self.root / 'saved.txt').exists())
        self.assertTrue(page_state(self.pool, 'https://example.org/other')['dispatch_allowed'])
        other = self.report(row, 'PASS')
        with self.assertRaisesRegex(ValueError, 'cannot be overwritten'):
            self.store.record_qc_report(other)

    def test_capture_failure_and_retry_preserve_both_attempts(self):
        self.enqueue()
        row = self.store.claim_next('worker', request_id='fail', now=NOW)
        self.store.start_attempt(row['attempt_id'], row['worker_id'], row['lease_token'], now=NOW)
        self.store.finish_attempt(row['attempt_id'], row['worker_id'], row['lease_token'], 'rejected',
            failure_class='network', root_cause='CONTROLLED timeout', now=NOW + 1)
        self.assertEqual(self.state()['status'], 'failed')
        next_row = self.store.claim_next('worker', request_id='retry', now=NOW + 3)
        self.assertNotEqual(next_row['sample_id'], row['sample_id'])
        self.assertEqual(len(self.state()['tasks'][0]['attempts']), 2)
        self.assertEqual(self.state()['tasks'][0]['attempts'][0]['root_cause'], 'CONTROLLED timeout')

    def test_duplicate_page_across_registry_blocks_before_number_allocation(self):
        self.captured()
        registry = make_registry(self.root / 'second.sqlite3')
        other = RuntimeStore(registry, 'second')
        other.initialize(now=NOW); other.bind_site_pool(self.pool.path)
        plan, publication = make_plan(self.root / 'different-plan', uri=self.uri + '?word=changed', task_prefix='new-id')
        other.enqueue_plan(plan, publication, now=NOW)
        self.assertEqual(other.site_pool_binding()['pending'], 1)
        with self.assertRaisesRegex(ValueError, 'active or completed'):
            other.claim_next('other', request_id='never-dispatch', now=NOW)
        self.assertEqual(other.snapshot()['attempts'], [])

    def test_same_logical_task_on_another_page_cannot_bypass_completion(self):
        row = self.captured(); self.store.record_qc_report(self.report(row))
        plan, _ = make_plan(self.root / 'other-plan', uri='https://example.org/other')
        with self.assertRaisesRegex(ValueError, 'logical task'):
            guard_plan(self.pool.path, self.registry, 'different-scope', plan)

    def test_two_competing_registries_have_at_most_one_page_owner(self):
        entries = []
        for n in range(2):
            registry = make_registry(self.root / ('competitor-' + str(n) + '.sqlite3'))
            store = RuntimeStore(registry, 'competitor')
            store.initialize(now=NOW); store.bind_site_pool(self.pool.path)
            plan, pub = make_plan(self.root / ('plan-' + str(n)), uri=self.uri, task_prefix='task-' + str(n))
            entries.append((store, plan, pub))
        def enqueue_and_claim(entry):
            store, plan, pub = entry
            store.enqueue_plan(plan, pub, now=NOW)
            try:
                return store.claim_next('worker', request_id='claim', now=NOW) is not None
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as executor:
            accepted = list(executor.map(enqueue_and_claim, entries))
        self.assertEqual(sum(accepted), 1)
        self.assertEqual(sum(len(store.snapshot()['attempts']) for store, _, _ in entries), 1)

    def test_interrupted_writeback_repairs_without_new_attempt_or_request(self):
        self.enqueue()
        row = self.store.claim_next('worker', request_id='first', now=NOW)
        self.store.start_attempt(row['attempt_id'], row['worker_id'], row['lease_token'], now=NOW)
        with patch('webcollect.site_pool_sync.sync', side_effect=OSError('CONTROLLED pool unavailable')):
            self.store.finish_attempt(row['attempt_id'], row['worker_id'], row['lease_token'],
                'collected_pending_review', evidence=evidence(self.root / 'saved.txt'), now=NOW + 1)
            self.assertEqual(self.store.site_pool_binding()['pending'], 1)
            self.assertTrue(self.state()['sync_pending'])
            with self.assertRaises(OSError):
                self.store.claim_next('worker', request_id='must-not-replay', now=NOW + 3)
        before = self.store.attempt_ledger()
        self.store.bind_site_pool(self.pool.path)  # Resume repairs the same frozen binding.
        self.assertEqual(self.state()['status'], 'collected_pending_review')
        self.assertFalse(self.store.site_pool_binding()['pending'])
        self.assertEqual(self.store.attempt_ledger(), before)

    def test_pool_binding_cannot_be_replaced_or_missing_source_silently_recreated(self):
        other = SitePool(self.root / 'other-pool.sqlite3', initialize=True)
        with self.assertRaisesRegex(ValueError, 'Cannot replace'):
            self.store.bind_site_pool(other.path)
        self.captured()
        self.registry.rename(self.root / 'preserved.sqlite3')
        self.assertFalse(self.state()['dispatch_allowed'])
        self.assertFalse(self.registry.exists())

    def test_catalog_binding_requires_exact_original_catalog(self):
        path = self.root / 'qualified.json'; save_json(path, {'CONTROLLED': True})
        save_json(self.root / 'site-pool-binding.json', {'schema_version': 'webcollect-site-pool-binding-1',
            'pool': str(self.pool.path), 'catalog': ref(path)})
        self.assertEqual(pool_for_catalog(path), str(self.pool.path))
        path.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'binding changed'):
            pool_for_catalog(path)

    def test_tampered_report_or_arbitrary_pass_does_not_write_success(self):
        row = self.captured(); approved = self.report(row)
        Path(approved['path']).write_text('tampered')
        with self.assertRaises(ValueError):
            self.store.record_qc_report(approved)
        fake = self.root / 'fake.json'; save_json(fake, {'status': 'PASS'})
        with self.assertRaises(ValueError):
            self.store.record_qc_report(ref(fake))
        self.assertEqual(self.state()['status'], 'collected_pending_review')

    def test_tracked_application_merge_cannot_hide_completed_page(self):
        self.captured()
        target = discover(self.pool, self.root, 'https://other.org/tool', 'merge-target')
        app = self.pool.application(self.uri)
        with self.assertRaisesRegex(ValueError, 'collection reconciliation'):
            self.pool.merge(app['id'], target['application_id'], evidence(self.root / 'merge.txt'))


class CollectionWritebackIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_original_collector_qc_handoff_and_independent_report_writeback(self):
        # The existing collect_one fixture mocks browser IO and forbids the model gateway.
        from test_single_execution_path import SingleCollectionTests
        from webcollect.collect_runtime import collect_m4, runtime_scope
        from webcollect.client_package import build_client_package
        from webcollect.production_facts import derive
        from webcollect.qc_handoff import prepare_qc_inputs
        from webcollect.validate import validate_sample
        from quality_inspector import engine
        from quality_inspector.profiles import DEFAULT_DELIVERY_PROFILE, package_files
        from quality_inspector.reporting import review_template
        case = SingleCollectionTests('test_identity_bound_plan_uses_same_collector_without_admission_or_rehearsal')
        await case.asyncSetUp(); self.addCleanup(case.doCleanups)
        case.prepared(True)
        pool = SitePool(case.root / 'shared.sqlite3', initialize=True)
        discover(pool, case.root, 'https://example.org/', 'integration')
        discover(pool, case.root, 'https://example.org/other', 'other')
        capture = case.output / 'capture'
        with patch('webcollect.collect_runtime.validate_sample', side_effect=validate_sample), \
             patch('webcollect.metadata.export_metadata', side_effect=case.real_metadata):
            result = await collect_m4(case.plan_path, capture, case.registry, publication_path=case.publication_path,
                policy_path=case.policy_path, site_pool=pool.path)
        self.assertEqual(result['collected'], 1)
        self.assertEqual(page_state(pool, 'https://example.org/')['status'], 'collected_pending_review')
        store = RuntimeStore(case.registry, runtime_scope(capture))
        before = package_files(capture)
        facts = case.output / 'facts.json'; save_json(facts, derive(capture))
        dataset = case.output / 'candidate'
        build_client_package(Path(__file__).resolve().parents[3], capture, dataset, facts=facts)
        handoff = prepare_qc_inputs(dataset, case.chain_manifest, case.output / 'qc-inputs',
            ai_percent=100, human_percent=0, seed='CONTROLLED-writeback')
        profile = load_json(DEFAULT_DELIVERY_PROFILE)
        profile.update(profile_id='CONTROLLED-WRITEBACK-ONLY', authority='Disposable synthetic protocol test only')
        profile['targets'].update(expected_samples=1, category_share='report-only')
        profile_path = case.output / 'profile.json'; save_json(profile_path, profile)
        pending = engine.inspect(None, dataset, profile=profile_path, inspection_stage='payload')
        pending_path = case.output / 'pending-report.json'; save_json(pending_path, pending)
        apply_qc(pending_path, ref(handoff['receipt']))
        self.assertEqual(page_state(pool, 'https://example.org/')['status'], 'collected_pending_review')
        reviews = review_template(pending); reviews.pop('package_review', None)
        for record in reviews['records']:
            steps = [s['step_id'] for s in load_json(dataset / 'samples' / record['sample_id'] / 'annotation.json')['steps']]
            record['reviewer'] = {'kind': 'ai', 'name': 'CONTROLLED synthetic protocol only'}
            record['provenance'] = {'description': 'Authored offline expectations, no actual model or human review', 'frames_viewed': steps}
            record['step_observations'] = [{'step_id': s, 'note': 'CONTROLLED fixture only'} for s in steps]
            record['checks'] = {name: {'status': 'PASS', 'note': 'CONTROLLED fixture only', 'evidence_steps': steps} for name in engine.SEMANTIC}
        document = reviews['delivery_document_review']
        document['reviewer'] = {'kind': 'ai', 'name': 'CONTROLLED document fixture only'}
        document['provenance'] = {'description': 'Authored offline expectation only'}
        for check in document['checks'].values():
            check.update(status='PASS', note='CONTROLLED document expectation only', evidence=[{
                'path': 'README.md', 'sha256': document['payload_files_sha256']['README.md'], 'detail': 'Temporary fixture bytes'}])
        review_path = case.output / 'reviews.json'; save_json(review_path, reviews)
        passed = engine.inspect(None, dataset, profile=profile_path, reviews=review_path, inspection_stage='payload')
        self.assertEqual(passed['status'], 'PASS')
        report = case.output / 'passed-report.json'; save_json(report, passed)
        handoff_ref = ref(handoff['receipt'])
        apply_qc(report, handoff_ref)
        self.assertEqual(store.snapshot()['tasks'][0]['status'], 'reviewed_pass')
        self.assertEqual(page_state(pool, 'https://example.org/')['status'], 'reviewed_pass')
        self.assertTrue(page_state(pool, 'https://example.org/other')['dispatch_allowed'])
        events = store.snapshot()['events']
        apply_qc(report, handoff_ref)
        self.assertEqual(store.snapshot()['events'], events)
        self.assertEqual(package_files(capture), before)
        self.assertEqual(case.actions, ['scroll'] * 5)
        Path(handoff['receipt']).write_text('tampered handoff')
        with self.assertRaises(ValueError):
            apply_qc(report, handoff_ref)


class PipelineWritebackTriggerTests(unittest.TestCase):
    def setUp(self):
        from test_delivery_pipeline import DeliveryPipelineTests
        case = DeliveryPipelineTests('test_prepare_binds_jobs_to_plan_and_dispatches_no_model_requests')
        case.setUp(); self.addCleanup(case.doCleanups)
        self.case = case

    def test_pipeline_verifies_original_handoff_and_automatically_writes_back_report(self):
        from quality_inspector import delivery_pipeline as pipeline
        case = self.case
        ledger = case.real_ledger_fixture()
        handoff = case.root / 'mock-original-handoff.json'
        save_json(handoff, {'CONTROLLED': 'trigger boundary only; original capture validation tested separately'})
        with patch('webcollect.site_pool_sync.validate_handoff') as validate:
            prepared = pipeline.prepare(ledger, case.dataset, case.plan, case.effective, case.root / 'writeback-prepared',
                profile=case.fixture.profile, cross_package_report=case.cross_report, mode='real', production_handoff=ref(handoff))
            with patch.object(pipeline.ai_worker, 'ModelGateway', case.PassingProtocolGateway), \
                 patch('webcollect.site_pool_sync.apply_qc') as writeback:
                state = pipeline.run(prepared['receipt'], case.root / 'writeback-run', max_jobs=10)
            writeback.assert_called_once_with((case.root / 'writeback-run/payload-qc/report.json').resolve(), ref(handoff))
            self.assertTrue(validate.called)
            self.assertEqual(state['mode'], 'real')  # Mock protocol only; no network/provider call.
        with patch('webcollect.site_pool_sync.validate_handoff', side_effect=ValueError('CONTROLLED bad original')), \
             patch.object(pipeline.ai_worker, 'ModelGateway', side_effect=AssertionError('No model before handoff validation')):
            with self.assertRaisesRegex(ValueError, 'bad original'):
                pipeline.run(prepared['receipt'], case.root / 'must-not-run', max_jobs=10)

    def test_controlled_pipeline_cannot_bind_a_production_writeback(self):
        from quality_inspector import delivery_pipeline as pipeline
        with self.assertRaisesRegex(ValueError, 'Controlled QC cannot update'):
            self.case.prepare(production_handoff={'path': 'unused', 'sha256': 'unused'})
        self.assertEqual(self.case.ledger.summary()['model_requests'], 0)
