"""Requirement regressions with disposable evidence and ledgers; no external IO."""
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from webcollect.batch_core import BatchLedger, file_sha, load_json, save_json
from webcollect.site_failure_stop import SiteFailureStore, SiteStopped
from webcollect.task_generation import generate
from test_s0_task_generation import config, catalog


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        proof = self.root / 'ownership.txt'; proof.write_text('CONTROLLED observed same application ownership')
        registry = self.root / 'applications.json'
        save_json(registry, {'schema_version': 'webcollect-application-aliases-1', 'applications': [{
            'canonical_uri': 'https://example.org/',
            'aliases': ['https://example.org/', 'https://m.example.org/'],
            'evidence': [{'path': str(proof), 'sha256': file_sha(proof)}]}]})
        self.binding = {'ledger': str(self.root / 'failures.sqlite3'), 'campaign_id': 'CONTROLLED',
            'formal_since': time.time() - 1,
            'application_registry': {'path': str(registry), 'sha256': file_sha(registry)}}
        self.stop = SiteFailureStore.initialize(self.binding)
        self.config = config('real'); self.config['site_failure_guard'] = self.binding
        self.clock = time.time()
        clock = patch('webcollect.batch_core.time.time', side_effect=lambda: self.clock)
        clock.start(); self.addCleanup(clock.stop)
        self.ledger = BatchLedger(self.root / 'batch.sqlite3', self.config, initialize=True)
        jid = self.ledger.enqueue('site-probe', {'CONTROLLED': True})
        self.job = self.ledger.claim('site-probe', job_id=jid)

    def visit(self, uri):
        self.clock += 2
        return self.ledger.reserve_visit(self.job, uri, 'probe-page:0', 'example.org')

    def test_evidenced_aliases_share_three_failures_and_reopen_cannot_reset(self):
        for uri in ('https://example.org/a', 'https://m.example.org/b', 'https://example.org/c'):
            self.ledger.settle_visit(self.visit(uri), state='failed', error=TimeoutError('CONTROLLED original timeout'))
        reopened = BatchLedger(self.ledger.path, self.config)
        with self.assertRaises(SiteStopped):
            reopened.reserve_visit(self.job, 'https://m.example.org/fourth', 'probe-page:0', 'example.org')
        self.assertEqual(len(self.ledger.visits()), 3)
        self.assertEqual(self.stop.status('https://m.example.org/')['failure_count'], 3)
        self.assertFalse(self.stop.status('https://other.example.org/')['dispatch_blocked'])

    def test_live_visit_is_not_unknown_and_settlement_is_idempotently_reconciled(self):
        visit = self.visit('https://example.org/a')
        self.ledger.sync_visit_failures()
        self.assertEqual(self.stop.status('https://example.org/')['unknown_execution_count'], 0)
        self.ledger.settle_visit(visit, state='failed', error=TimeoutError('CONTROLLED'))
        self.ledger.sync_visit_failures()
        self.assertEqual(self.stop.status('https://example.org/')['failure_count'], 1)

    def test_uncertain_visit_holds_alias_without_retry(self):
        self.ledger.settle_visit(self.visit('https://example.org/a'), state='unknown', error=InterruptedError('CONTROLLED'))
        with self.assertRaises(SiteStopped): self.visit('https://m.example.org/retry')
        self.assertEqual(self.stop.status('https://example.org/')['failure_count'], 0)
        self.assertEqual(len(self.ledger.visits()), 1)

    def test_changed_ownership_evidence_blocks_instead_of_silently_rekeying(self):
        (self.root / 'ownership.txt').write_text('different ownership')
        with self.assertRaises(ValueError): self.visit('https://example.org/a')

    def test_real_source_cannot_dispatch_without_the_original_stop_ledger(self):
        from webcollect.batch_core import BudgetStop
        unbound = config('real')
        ledger = BatchLedger(self.root/'unbound.sqlite3', unbound, initialize=True)
        job = ledger.claim('site-probe', job_id=ledger.enqueue('site-probe', {'CONTROLLED': 'unbound'}))
        with self.assertRaisesRegex(BudgetStop, 'no request sent'):
            ledger.reserve_visit(job, 'https://example.org/', 'probe-page:0', 'example.org')
        self.assertEqual(ledger.visits(), [])

    def test_collection_job_preflight_failure_counts_before_next_navigation(self):
        from webcollect.navigation import BatchNavigation
        self.ledger.finish(self.job)
        jid = self.ledger.enqueue('collection', {'CONTROLLED': 'preflight'})
        job = self.ledger.claim('collection', job_id=jid)
        navigation = BatchNavigation(self.ledger, job)
        for index in range(3):
            self.clock += 2
            task = {'task_id': 'task-' + str(index), 'site_uri': 'https://example.org/'}
            visit = self.ledger.reserve_visit(job, 'https://example.org/page-' + str(index),
                                             'preflight:' + task['task_id'], 'example.org')
            self.ledger.settle_visit(visit, state='succeeded')
            record = {'task_id': task['task_id'], 'summary': {'routing': 'REVIEW_REQUIRED'},
                      'error': {'kind': 'TimeoutError', 'message': 'CONTROLLED original rendering failure'}}
            path = self.root / ('preflight-' + str(index) + '.json'); save_json(path, record)
            reference = {'path': str(path), 'sha256': file_sha(path)}
            navigation.record_preflight_outcome(task, record, reference)
            navigation.record_preflight_outcome(task, record, reference)
        self.clock += 2
        with self.assertRaises(SiteStopped):
            self.ledger.reserve_visit(job, 'https://m.example.org/fourth', 'preflight:fourth', 'example.org')
        self.assertEqual(self.stop.status('https://example.org/')['failure_count'], 3)

    def test_collection_preflight_navigation_failure_is_not_skipped_as_formal_attempt(self):
        self.ledger.finish(self.job)
        jid = self.ledger.enqueue('collection', {'CONTROLLED': 'navigation'})
        job = self.ledger.claim('collection', job_id=jid)
        self.clock += 2
        visit = self.ledger.reserve_visit(job, 'https://example.org/', 'preflight:task', 'example.org')
        self.ledger.settle_visit(visit, state='failed', error=TimeoutError('CONTROLLED original goto failure'))
        self.assertEqual(self.stop.status('https://example.org/')['failure_count'], 1)

    def test_synthetic_navigation_cannot_enter_real_failure_denominator(self):
        synthetic = config('synthetic'); synthetic['site_failure_guard'] = self.binding
        ledger = BatchLedger(self.root / 'synthetic.sqlite3', synthetic, initialize=True)
        jid = ledger.enqueue('site-probe', {'CONTROLLED': True}); job = ledger.claim('site-probe', job_id=jid)
        visit = ledger.reserve_visit(job, 'https://example.org/', 'probe-page:0', 'example.org')
        ledger.settle_visit(visit, state='failed', error=TimeoutError('CONTROLLED synthetic failure'))
        self.assertEqual(self.stop.status('https://example.org/')['failure_count'], 0)

    def test_rendered_probe_failure_counts_but_pending_review_and_navigation_failure_do_not_double_count(self):
        visit = self.visit('https://example.org/a')
        self.ledger.settle_visit(visit, state='succeeded')
        pending = {'status': 'review_required', 'reason': 'Not reviewed'}
        self.ledger.record_probe_outcome(self.job, 'https://example.org/', pending, {})
        self.assertEqual(self.stop.status('https://example.org/')['failure_count'], 0)
        failure = {'status': 'rejected', 'reason': 'CONTROLLED rendered language failure'}
        path = self.root / 'rendered-failure.json'; save_json(path, failure)
        ref = {'path': str(path), 'sha256': file_sha(path)}
        self.ledger.record_probe_outcome(self.job, 'https://example.org/', failure, ref)
        self.ledger.record_probe_outcome(self.job, 'https://example.org/', failure, ref)
        self.assertEqual(self.stop.status('https://example.org/')['failure_count'], 1)
        self.ledger.settle_visit(self.visit('https://example.org/b'), state='failed', error=TimeoutError('CONTROLLED'))
        self.ledger.record_probe_outcome(self.job, 'https://example.org/', failure, ref)
        self.assertEqual(self.stop.status('https://example.org/')['failure_count'], 2)


class FailureDiagnosticsTests(unittest.TestCase):
    def test_mixed_catalog_publishes_valid_subset_and_retains_probe_failure_denominator(self):
        from m4_runtime_fixtures import make_plan, NOW
        from webcollect.planning import publish_plan, verify_publication
        with tempfile.TemporaryDirectory() as directory:
            plan, original = make_plan(Path(directory))
            failure = {'schema_version': 'webcollect-site-probe-failure-1', 'site_uri': 'https://failed.example/',
                       'reason': 'TimeoutError', 'error_message': 'CONTROLLED original timeout', 'visit_ids': ['original-visit']}
            receipt = publish_plan(plan, original['capability_catalog'] + [failure], now=NOW)
            self.assertEqual(receipt['capability_candidate_count'], 2)
            self.assertEqual(receipt['task_count'], 1)
            self.assertEqual(receipt['probe_failures'], [failure])
            verify_publication(plan, receipt, now=NOW)
            legacy = {key: value for key, value in failure.items() if key != 'schema_version'}
            receipt = publish_plan(plan, original['capability_catalog'] + [legacy], now=NOW)
            self.assertEqual(receipt['probe_failures'], [legacy])
            verify_publication(plan, receipt, now=NOW)

    def test_probe_timeout_is_not_reported_as_capability_schema_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            failure = {'schema_version': 'webcollect-site-probe-failure-1',
                'site_uri': 'https://example.org/', 'reason': 'TimeoutError',
                'error_message': 'CONTROLLED Page.goto timeout', 'visit_ids': ['CONTROLLED-visit'], 'evidence': []}
            ledger = BatchLedger(root / 'batch.sqlite3', config(), initialize=True)
            result = generate(ledger, catalog(root / 'catalog.json', [failure]), root / 'generated')
            self.assertEqual(result['catalog_candidates'], 1)
            self.assertEqual(result['rejected'][0]['reason'], 'TimeoutError')
            self.assertEqual(result['rejected'][0]['visit_ids'], ['CONTROLLED-visit'])
            self.assertEqual(result['generated_tasks'], 0)


class ReleaseRequirements(unittest.TestCase):
    def test_formal_member_has_10000_target_and_requires_the_bound_corpus_version(self):
        from quality_inspector.profiles import load, DEFAULT_DELIVERY_PROFILE, verify_member_release
        with tempfile.TemporaryDirectory() as directory:
            profile = load_json(DEFAULT_DELIVERY_PROFILE)
            profile['release'] = {'kind': 'formal-package', 'version': 'CONTROLLED-v1'}
            profile['targets']['expected_samples'] = 10000
            path = Path(directory) / 'member.json'; save_json(path, profile)
            loaded = load(path)
            report = {'local_profile': loaded, 'sample_count': 10000}
            scope = {'release': {'kind': 'formal', 'version': 'CONTROLLED-v1'},
                     'effective_sample_count': 200000, 'package_roots': list(range(20))}
            self.assertEqual(verify_member_release(report, scope), profile['release'])
            for bad in ({**scope, 'effective_sample_count': 199999},
                        {**scope, 'package_roots': list(range(19))},
                        {**scope, 'release': {'kind': 'formal', 'version': 'CONTROLLED-v2'}}):
                with self.assertRaises(ValueError): verify_member_release(report, bad)
            experiment = deepcopy(report)
            experiment['local_profile']['configuration']['release']['kind'] = 'experiment'
            with self.assertRaises(ValueError): verify_member_release(experiment, scope)

    def test_formal_package_counts_duplicates_and_versions_are_checked_separately(self):
        from quality_inspector.profiles import release_errors
        formal = {'release': {'kind': 'formal', 'version': 'CONTROLLED'}}
        packages = [{'sample_count': 10000} for _ in range(20)]
        self.assertEqual(release_errors(formal, packages, {}, 200000), [])
        for counts, total, versions in ((packages[:-1], 190000, {}),
                                        ([{'sample_count': 9999}] + packages[1:], 199999, {}),
                                        (packages, 200000, {'identical_copies': ['CONTROLLED-copy']}),
                                        (packages, 200000, {'superseded': ['CONTROLLED-old']})):
            self.assertTrue(release_errors(formal, counts, versions, total))
        self.assertEqual(release_errors({'release': {'kind': 'experiment', 'version': 'CONTROLLED'}},
                                        [{'sample_count': 1}], {}, 1), [])

    def test_experiment_profile_cannot_claim_formal_quantity_or_missing_version(self):
        from quality_inspector.profiles import load, DEFAULT_DELIVERY_PROFILE
        from webcollect.batch_core import load_json
        with tempfile.TemporaryDirectory() as directory:
            profile = load_json(DEFAULT_DELIVERY_PROFILE)
            profile['release'] = {'kind': 'formal', 'version': 'CONTROLLED'}
            profile['targets']['expected_samples'] = 1
            path = Path(directory) / 'formal.json'; save_json(path, profile)
            with self.assertRaises(ValueError): load(path)
