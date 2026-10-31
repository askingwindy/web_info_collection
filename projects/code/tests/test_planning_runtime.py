"""Controlled persistence/concurrency failures; no network or production ledger."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from webcollect.planning import publish_plan, verify_publication, object_sha256
from webcollect.runtime import RuntimeStore, domain_key
from webcollect.storage import allocate
from m4_runtime_fixtures import NOW, evidence, make_plan, make_registry


class PlanningRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.registry = make_registry(self.root / 'registry.sqlite3')
        self.store = RuntimeStore(self.registry, 'batch-A')
        self.store.initialize(now=NOW)
        self.plan, self.publication = make_plan(self.root / 'planning', 3)

    def enqueue(self):
        return self.store.enqueue_plan(self.plan, self.publication, now=NOW)

    def claim(self, request='request-1', now=NOW, worker='worker', batch_id=None):
        return self.store.claim_next(worker, request_id=request, now=now, batch_id=batch_id)

    def start(self, row, now=NOW):
        return self.store.start_attempt(row['attempt_id'], row['worker_id'], row['lease_token'], now=now)

    def finish(self, row, outcome='rejected', now=NOW+1, failure_class='network', root_cause='timeout'):
        proof = evidence(self.root / (row['attempt_id'] + '.json'))
        return self.store.finish_attempt(row['attempt_id'], row['worker_id'], row['lease_token'], outcome,
                                        failure_class=failure_class if outcome == 'rejected' else None,
                                        root_cause=root_cause if outcome == 'rejected' else None,
                                        evidence=proof, now=now)

    def counts(self):
        con = sqlite3.connect(self.registry)
        try:
            return {name: con.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in ('sites', 'batches', 'allocations', 'm4_attempts')}
        finally:
            con.close()

    def qc_evidence(self, sample_ids, status='PASS', stage='final', release_ready=True):
        """Real binding-gate fixture, not a claim that QC ran or pixels passed."""
        from webcollect.client_package import sample_hashes, sha
        base = Path(tempfile.mkdtemp(prefix='controlled-qc-', dir=self.root))
        package = base / 'customer'
        rows = []
        for sample_id in sample_ids:
            sample = package / 'samples' / sample_id
            sample.mkdir(parents=True)
            (sample / 'annotation.json').write_text(json.dumps({'test_fixture_only': True, 'sample_id': sample_id}))
            (sample / 'controlled-evidence.txt').write_text('Synthetic test bytes; no browser or QC execution.')
            hashes = sample_hashes(sample)
            rows.append({'sample_id': sample_id, 'sample_path': str(sample), 'status': status,
                         'annotation_sha256': hashes.pop('annotation.json'), 'evidence_sha256': hashes})
        (package / 'SHA256SUMS').write_text(''.join(sha(path) + '  ' + path.relative_to(package).as_posix() + '\n'
            for path in sorted(package.rglob('*')) if path.is_file()))
        files = {path.relative_to(package).as_posix(): sha(path) for path in sorted(package.rglob('*')) if path.is_file()}
        from quality_inspector.semantic import rule_ids
        report = {'program': 'quality-inspector', 'test_fixture_only': True, 'qc_program_executed': False,
                  'semantic_rule_ids': rule_ids(),
                  'dataset': str(package), 'input_files_sha256': files, 'root_checksum': {'pass': True},
                  'samples': rows, 'inspection_stage': stage, 'delivery_status': status, 'release_ready': release_ready}
        return evidence(base / 'bound-report.json', json.dumps(report))

    def test_plan_registration_does_not_allocate_sample_ids(self):
        self.enqueue()
        self.assertEqual(self.counts(), {'sites': 0, 'batches': 0, 'allocations': 0, 'm4_attempts': 0})
        self.assertTrue(self.enqueue()['already_enqueued'])
        self.assertEqual(len(self.store.snapshot()['tasks']), 3)

    def test_legacy_allocate_keeps_mapping_and_sequence(self):
        first = allocate(self.registry, 'https://example.org/', '工具', 'real', day='20270115')
        self.enqueue()
        claimed = self.claim()
        self.assertEqual(claimed['site_id'], first['site_id'])
        self.assertTrue(claimed['sample_id'].endswith('000002'))
        with self.assertRaises(ValueError):
            allocate(self.registry, 'https://example.org/', '不同类目', 'real')
        self.assertEqual(self.counts()['allocations'], 2)

    def test_missing_registry_read_does_not_create_files(self):
        path = self.root / 'missing.sqlite3'
        with self.assertRaises(sqlite3.OperationalError):
            RuntimeStore(path, 'never').snapshot()
        self.assertFalse(path.exists())

    def test_snapshot_does_not_initialize_runtime_tables(self):
        path = make_registry(self.root / 'legacy.sqlite3')
        before = path.read_bytes()
        with self.assertRaises(sqlite3.OperationalError):
            RuntimeStore(path, 'never').snapshot()
        self.assertEqual(path.read_bytes(), before)

    def test_plan_binding_is_readonly_and_exposes_frozen_inputs(self):
        before = self.registry.read_bytes()
        empty = self.store.plan_binding()
        self.assertIsNone(empty['plan'])
        self.assertEqual(empty['attempt_count'], 0)
        self.assertEqual(self.registry.read_bytes(), before)
        self.enqueue()
        before = self.registry.read_bytes()
        binding = self.store.plan_binding()
        self.assertEqual(binding['plan'], self.plan)
        self.assertEqual(binding['publication'], self.publication)
        self.assertTrue(binding['bootstrap_recoverable'])
        self.assertEqual(self.registry.read_bytes(), before)
        legacy = make_registry(self.root / 'legacy-binding.sqlite3')
        before = legacy.read_bytes()
        with self.assertRaises(sqlite3.OperationalError):
            RuntimeStore(legacy, 'missing').plan_binding()
        self.assertEqual(legacy.read_bytes(), before)
        missing = self.root / 'missing-binding.sqlite3'
        with self.assertRaises(sqlite3.OperationalError):
            RuntimeStore(missing, 'missing').plan_binding()
        self.assertFalse(missing.exists())

    def test_bootstrap_recovery_only_appends_idempotent_event(self):
        self.enqueue()
        before = self.store.plan_binding()
        proof = evidence(self.root / 'bootstrap-recovery.json')
        result = self.store.record_bootstrap_recovery(self.plan, self.publication, proof,
                                                     'controlled manifest gap recovery', now=NOW+1)
        repeat = self.store.record_bootstrap_recovery(self.plan, self.publication, proof,
                                                     'controlled manifest gap recovery', now=NOW+2)
        self.assertFalse(result['already_recorded'])
        self.assertTrue(repeat['already_recorded'])
        self.assertEqual(result['event_id'], repeat['event_id'])
        self.assertEqual(before, self.store.plan_binding())
        self.assertEqual(self.counts()['allocations'], 0)
        events = [r for r in self.store.snapshot()['events'] if r['event_type'] == 'bootstrap_recovered']
        self.assertEqual(len(events), 1)
        altered = deepcopy(self.publication); altered['published_at'] += 1
        with self.assertRaisesRegex(ValueError, '不匹配'):
            self.store.record_bootstrap_recovery(self.plan, altered, proof, 'changed binding', now=NOW+3)

    def test_bootstrap_recovery_refuses_even_abandoned_unstarted_allocation(self):
        self.enqueue()
        proof = evidence(self.root / 'bootstrap-recovery.json')
        self.claim()
        self.assertFalse(self.store.plan_binding()['bootstrap_recoverable'])
        with self.assertRaisesRegex(ValueError, '预留编号'):
            self.store.record_bootstrap_recovery(self.plan, self.publication, proof, 'reserved gap', now=NOW+1)
        self.store.recover_expired(now=NOW+121)
        self.assertEqual(self.store.attempt_ledger()['actual_attempt_count'], 0)
        self.assertEqual(self.store.attempt_ledger()['reserved_attempts'][0]['status'], 'abandoned')
        with self.assertRaisesRegex(ValueError, '预留编号'):
            self.store.record_bootstrap_recovery(self.plan, self.publication, proof, 'abandoned gap', now=NOW+122)

    def test_expired_capability_rejected_before_queue_or_numbering(self):
        with self.assertRaisesRegex(ValueError, '过期'):
            self.store.enqueue_plan(self.plan, self.publication, now=NOW+10001)
        self.assertFalse(self.store.snapshot()['tasks'])
        self.assertEqual(self.counts()['allocations'], 0)

    def test_capability_drift_or_plan_tampering_rejects_publication(self):
        plan = deepcopy(self.plan); plan['tasks'][0]['task_family'] = 'unsupported'
        with self.assertRaises(ValueError):
            verify_publication(plan, self.publication, now=NOW)
        Path(self.publication['capabilities'][0]['evidence'][0]['path']).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'SHA'):
            self.enqueue()

    def test_preflight_cannot_be_skipped(self):
        with self.assertRaisesRegex(ValueError, '不能跳过'):
            publish_plan(self.plan, self.publication['capabilities'], require_preflight=False, now=NOW)

    def test_rejected_capability_candidates_remain_in_publication_denominator(self):
        rejected = deepcopy(self.publication['capabilities'][0])
        rejected.update(capability_id='rejected-site', site_uri='https://rejected.example.net/',
                        status='rejected', reason='Controlled unavailable site fixture')
        receipt = publish_plan(self.plan, self.publication['capabilities'] + [rejected], now=NOW)
        self.assertEqual(receipt['capability_candidate_count'], 2)
        self.assertEqual(len(receipt['capabilities']), 1)
        self.assertEqual(receipt['capability_catalog'][1]['status'], 'rejected')
        verify_publication(self.plan, receipt, now=NOW)

    def test_capability_expires_between_publication_and_claim(self):
        self.enqueue()
        self.assertIsNone(self.claim(now=NOW+10001))
        self.assertTrue(all(row['status'] == 'needs_replan' for row in self.store.snapshot()['tasks']))
        self.assertEqual(self.counts()['allocations'], 0)

    def test_atomic_failure_between_allocation_and_mapping_rolls_back(self):
        self.enqueue()
        def crash(point):
            if point == 'after_allocation_before_attempt':
                raise RuntimeError('controlled crash before commit')
        with self.assertRaisesRegex(RuntimeError, 'controlled crash'):
            self.store.claim_next('worker', request_id='crash', now=NOW, _fault=crash)
        self.assertEqual(self.counts(), {'sites': 0, 'batches': 0, 'allocations': 0, 'm4_attempts': 0})
        row = self.claim('crash')
        self.assertTrue(row['sample_id'].endswith('000001'))

    def test_response_loss_reuses_committed_request_without_second_allocation(self):
        self.enqueue()
        row = self.claim()
        replay = self.claim()
        self.assertEqual(row, replay)
        self.assertEqual(self.counts()['allocations'], 1)
        with self.assertRaises(ValueError):
            self.claim(worker='another-worker')

    def test_process_death_rolls_back_number_and_attempt_together(self):
        self.enqueue()
        code = ('import os,sys; from webcollect.runtime import RuntimeStore; '
                'store=RuntimeStore(sys.argv[1], "batch-A"); '
                'store.claim_next("worker",request_id="hard-crash",now=1800000000,'
                '_fault=lambda point: os._exit(23) if point=="after_allocation_before_attempt" else None)')
        result = subprocess.run([sys.executable, '-c', code, str(self.registry)], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(self.counts()['allocations'], 0)
        self.assertEqual(self.counts()['m4_attempts'], 0)
        self.assertIsNotNone(self.claim('hard-crash'))

    def test_process_death_after_commit_keeps_recoverable_mapping(self):
        self.enqueue()
        code = ('import os,sys; from webcollect.runtime import RuntimeStore; '
                'store=RuntimeStore(sys.argv[1], "batch-A"); '
                'store.claim_next("worker",request_id="committed",now=1800000000); os._exit(24)')
        result = subprocess.run([sys.executable, '-c', code, str(self.registry)], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 24, result.stderr)
        replay = self.claim('committed')
        self.assertEqual(replay['task_id'], 'task-0')
        self.assertEqual(self.counts()['allocations'], 1)
        self.assertEqual(self.counts()['m4_attempts'], 1)

    def test_concurrent_claims_respect_worker_and_domain_limits(self):
        self.enqueue()
        def reserve(index):
            return self.claim('r-'+str(index), worker='w-'+str(index))
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(reserve, range(8)))
        self.assertEqual(sum(row is not None for row in rows), 1)
        self.assertEqual(self.counts()['allocations'], 1)

    def test_concurrent_same_request_is_idempotent(self):
        self.enqueue()
        with ThreadPoolExecutor(max_workers=6) as pool:
            rows = list(pool.map(lambda _: self.claim(), range(6)))
        self.assertEqual(len({row['attempt_id'] for row in rows}), 1)
        self.assertEqual(self.counts()['allocations'], 1)

    def test_domain_limit_shared_across_scopes_with_multiple_workers(self):
        self.store.update_policy({'max_workers': 2}, 'controlled parallel workers', now=NOW)
        self.enqueue(); self.claim()
        other = RuntimeStore(self.registry, 'other')
        other.initialize(self.store.snapshot()['policy'], now=NOW)
        plan, receipt = make_plan(self.root / 'other-plan', 1, task_prefix='other', uri='https://sub.example.org/')
        other.enqueue_plan(plan, receipt, now=NOW)
        self.assertIsNone(other.claim_next('other-worker', request_id='other', now=NOW))
        self.assertEqual(self.counts()['allocations'], 1)

    def test_expired_unstarted_reservation_remains_numbered_not_real_attempt(self):
        self.enqueue(); first = self.claim()
        recovered = self.store.recover_expired(now=NOW+121)
        self.assertEqual(recovered[0]['status'], 'abandoned')
        ledger = self.store.attempt_ledger()
        self.assertEqual((ledger['actual_attempt_count'], ledger['reserved_allocation_count']), (0, 1))
        replacement = self.claim('replacement', now=NOW+122)
        self.assertNotEqual(replacement['sample_id'], first['sample_id'])
        self.assertEqual(replacement['retry_of'], first['attempt_id'])
        with self.assertRaises(ValueError):
            self.start(first, now=NOW+122)

    def test_started_crash_preserves_unknown_attempt_without_automatic_retry(self):
        self.enqueue(); first = self.claim(); self.start(first)
        self.store.recover_expired(now=NOW+121)
        ledger = self.store.attempt_ledger()
        self.assertEqual(ledger['actual_attempt_count'], 1)
        self.assertEqual(ledger['attempts'][0]['status'], 'interrupted')
        second = self.claim('second', now=NOW+122)
        self.assertNotEqual(first['task_id'], second['task_id'])
        self.assertIsNone(second['retry_of'])
        original = next(task for task in self.store.snapshot()['tasks'] if task['task_id'] == first['task_id'])
        self.assertEqual(original['status'], 'needs_replan')
        with self.assertRaises(ValueError):
            self.finish(first, now=NOW+122)

    def test_heartbeat_requires_current_lease_and_does_not_resurrect(self):
        self.enqueue(); row = self.claim(); self.start(row)
        expires = self.store.heartbeat(row['attempt_id'], 'worker', row['lease_token'], now=NOW+100)
        self.assertEqual(expires, NOW+220)
        self.assertFalse(self.store.recover_expired(now=NOW+121))
        with self.assertRaises(ValueError):
            self.store.heartbeat(row['attempt_id'], 'worker', row['lease_token'], now=NOW+221)

    def test_retry_cap_preserves_all_failed_attempts(self):
        self.enqueue()
        for i in range(3):
            row = self.claim(f'retry-{i}', now=NOW+i*10)
            self.start(row, now=NOW+i*10)
            self.finish(row, now=NOW+i*10+1)
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot['tasks'][0]['status'], 'needs_replan')
        self.assertEqual(len(snapshot['attempts']), 3)
        self.assertEqual(len({r['sample_id'] for r in snapshot['attempts']}), 3)
        self.assertEqual(snapshot['campaign_actual_attempt_count'], 3)

    def test_semantic_failure_releases_quota_without_blind_retry(self):
        self.enqueue(); row = self.claim(); self.start(row)
        self.finish(row, failure_class='semantic', root_cause='missing-action')
        task = self.store.snapshot()['tasks'][0]
        self.assertEqual((task['status'], task['quota_reserved']), ('needs_replan', 0))
        self.assertEqual(self.claim('next', now=NOW+3)['task_id'], 'task-1')

    def test_pending_review_budget_blocks_additional_capture(self):
        self.store.update_policy({'pending_review_cap': 1}, 'controlled pending budget', now=NOW)
        self.enqueue(); row = self.claim(); self.start(row)
        self.finish(row, outcome='collected_pending_review')
        self.assertIsNone(self.claim('next', now=NOW+3))
        proof = self.qc_evidence([row['sample_id']])
        self.store.record_review(row['sample_id'], 'pass', proof, 'controlled review fixture', now=NOW+4)
        self.assertIsNotNone(self.claim('next', now=NOW+5))

    def test_campaign_attempt_budget_shared_across_output_scopes(self):
        self.store.update_policy({'attempt_cap': 1}, 'controlled attempt cap', now=NOW)
        self.enqueue(); row = self.claim(); self.start(row)
        self.finish(row, failure_class='semantic')
        other = RuntimeStore(self.registry, 'batch-B')
        policy = self.store.snapshot()['policy']
        other.initialize(policy, now=NOW+2)
        plan, receipt = make_plan(self.root / 'second', 1, task_prefix='other', uri='https://another.net/')
        other.enqueue_plan(plan, receipt, now=NOW+2)
        self.assertIsNone(other.claim_next('worker-2', request_id='other', now=NOW+3))
        self.assertEqual(other.snapshot()['campaign_actual_attempt_count'], 1)
        with self.assertRaisesRegex(ValueError, '预算不同'):
            RuntimeStore(self.registry, 'batch-C').initialize(now=NOW+2)

    def test_cross_scope_same_task_version_is_rejected(self):
        self.enqueue()
        other = RuntimeStore(self.registry, 'other')
        other.initialize(now=NOW)
        with self.assertRaisesRegex(ValueError, '原scope'):
            other.enqueue_plan(self.plan, self.publication, now=NOW)
        self.assertFalse(other.snapshot()['tasks'])

    def test_concurrent_quota_reservations_are_atomic(self):
        self.store.update_policy({'category_limits': {'工具': 3}}, 'controlled quota', now=NOW)
        other = RuntimeStore(self.registry, 'other')
        other.initialize(self.store.snapshot()['policy'], now=NOW)
        plan, receipt = make_plan(self.root / 'other-plan', 3, task_prefix='other')
        def enqueue(item):
            try:
                return item[0].enqueue_plan(item[1], item[2], now=NOW)
            except ValueError as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(enqueue, [(self.store, self.plan, self.publication), (other, plan, receipt)]))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertEqual(len(self.store.snapshot()['tasks']) + len(other.snapshot()['tasks']), 3)
        self.assertEqual(self.counts()['allocations'], 0)

    def test_publication_is_idempotent_and_never_customer_acceptance(self):
        self.enqueue(); row = self.claim(); self.start(row)
        self.finish(row, outcome='collected_pending_review')
        proof = self.qc_evidence([row['sample_id']])
        self.store.record_review(row['sample_id'], 'pass', proof, 'controlled fixture', now=NOW+2)
        first = self.store.record_publication('release-1', [row['sample_id']], proof, now=NOW+3)
        second = self.store.record_publication('release-1', [row['sample_id']], proof, now=NOW+4)
        self.assertFalse(first['already_recorded']); self.assertTrue(second['already_recorded'])
        self.assertEqual(first['customer_acceptance'], 'UNKNOWN')
        self.assertEqual(sum(t['status'] == 'published' for t in self.store.snapshot()['tasks']), 1)

    def test_failed_retry_sample_cannot_be_published_via_successful_task(self):
        self.enqueue(); failed = self.claim(); self.start(failed); self.finish(failed)
        success = self.claim('retry', now=NOW+3); self.start(success, now=NOW+3)
        self.finish(success, outcome='collected_pending_review', now=NOW+4)
        proof = self.qc_evidence([success['sample_id']])
        self.store.record_review(success['sample_id'], 'pass', proof, 'controlled fixture', now=NOW+5)
        with self.assertRaises(ValueError):
            self.store.record_publication('bad-release', [failed['sample_id']], proof, now=NOW+6)

    def test_review_rejection_preserves_capture_outcome_and_raw_bytes(self):
        self.enqueue(); row = self.claim(); self.start(row)
        self.finish(row, outcome='collected_pending_review')
        raw = self.root / 'raw-batch' / 'samples' / row['sample_id'] / 'unchanged.json'
        evidence(raw, 'controlled raw capture bytes')
        proof = self.qc_evidence([row['sample_id']], status='FAIL', release_ready=False)
        original = raw.read_bytes()
        result = self.store.record_review(row['sample_id'], 'reject', proof,
                                         'controlled semantic rejection', now=NOW+2)
        self.assertTrue(result['raw_retained'])
        self.assertTrue(result['selection_only'])
        self.assertEqual(raw.read_bytes(), original)
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot['attempts'][0]['status'], 'collected_pending_review')
        task = next(t for t in snapshot['tasks'] if t['task_id'] == row['task_id'])
        self.assertEqual(task['status'], 'needs_replan')
        self.assertEqual(task['quota_reserved'], 0)
        with self.assertRaises(ValueError):
            self.store.record_publication('rejected-not-exported', [row['sample_id']], proof, now=NOW+3)

    def test_review_and_publication_reject_arbitrary_hashed_files(self):
        self.enqueue(); row = self.claim(); self.start(row)
        self.finish(row, outcome='collected_pending_review')
        proof = evidence(self.root / 'not-a-qc-report.json', '{"arbitrary": "hashed bytes"}')
        for decision in ('pass', 'reject'):
            with self.assertRaisesRegex(ValueError, 'quality-inspector'):
                self.store.record_review(row['sample_id'], decision, proof, 'unproven decision', now=NOW+2)
        with self.assertRaisesRegex(ValueError, 'quality-inspector'):
            self.store.record_publication('unproven-release', [row['sample_id']], proof, now=NOW+3)
        self.assertEqual(self.store.snapshot()['tasks'][0]['status'], 'collected_pending_review')

    def test_review_must_match_bound_sample_status_and_current_customer_bytes(self):
        self.enqueue(); row = self.claim(); self.start(row)
        self.finish(row, outcome='collected_pending_review')
        proof = self.qc_evidence([row['sample_id']], status='REVIEW_REQUIRED', release_ready=False)
        with self.assertRaisesRegex(ValueError, '实际状态一致'):
            self.store.record_review(row['sample_id'], 'pass', proof, 'pending is not pass', now=NOW+2)
        report = json.loads(Path(proof[0]['path']).read_text())
        sample = Path(report['samples'][0]['sample_path']) / 'annotation.json'
        sample.write_text('{"changed_after_QC": true}')
        with self.assertRaisesRegex(ValueError, 'hash binding'):
            self.store.record_review(row['sample_id'], 'reject', proof, 'changed bytes', now=NOW+3)

    def test_publication_requires_final_release_ready_qc(self):
        self.enqueue(); row = self.claim(); self.start(row)
        self.finish(row, outcome='collected_pending_review')
        proof = self.qc_evidence([row['sample_id']], stage='payload')
        self.store.record_review(row['sample_id'], 'pass', proof, 'controlled payload sample review', now=NOW+2)
        with self.assertRaisesRegex(ValueError, 'final阶段'):
            self.store.record_publication('payload-is-not-final', [row['sample_id']], proof, now=NOW+3)
        unfinished = self.qc_evidence([row['sample_id']], release_ready=False)
        with self.assertRaisesRegex(ValueError, 'release_ready'):
            self.store.record_publication('not-ready', [row['sample_id']], unfinished, now=NOW+3)

    def test_pause_stops_claims_and_preserves_queue(self):
        self.enqueue()
        self.store.set_scope_paused(True, 'controlled pause', now=NOW)
        self.assertIsNone(self.claim())
        self.store.set_scope_paused(False, 'controlled resume', now=NOW+1)
        self.assertIsNotNone(self.claim(now=NOW+1))

    def test_unstarted_cannot_count_as_real_failure(self):
        self.enqueue(); row = self.claim()
        with self.assertRaisesRegex(ValueError, '未开始'):
            self.finish(row)
        self.assertEqual(self.store.attempt_ledger()['actual_attempt_count'], 0)

    def test_completed_sample_not_reexecuted_after_reopen(self):
        self.enqueue(); row = self.claim(); self.start(row)
        self.finish(row, outcome='collected_pending_review')
        reopened = RuntimeStore(self.registry, 'batch-A')
        same = reopened.claim_next('worker', request_id='request-1', now=NOW+3)
        self.assertEqual(same['sample_id'], row['sample_id'])
        next_row = reopened.claim_next('worker', request_id='next', now=NOW+3)
        self.assertNotEqual(next_row['task_id'], row['task_id'])

    def test_subdomains_share_conservative_domain_budget(self):
        self.assertEqual(domain_key('https://a.example.com/'), domain_key('https://b.example.com/'))
        self.assertEqual(domain_key('https://127.0.0.1/'), '127.0.0.1')


if __name__ == '__main__':
    unittest.main()


class CampaignWideReapTests(PlanningRuntimeTests):
    def test_dead_scope_expired_attempt_is_reaped_campaign_wide_only(self):
        """Real-run v13/v14 fact: a crashed close-out leaves an expired running
        attempt in an abandoned scope. Scope-local recovery never touches it;
        only the campaign-wide reap clears the site-level unresolved block."""
        self.enqueue(); first = self.claim(); self.start(first)
        other = RuntimeStore(self.registry, 'other-batch')
        other.initialize(self.store.snapshot()['policy'], now=NOW)
        plan, receipt = make_plan(self.root / 'other-plan', 1, task_prefix='other',
                                  uri='https://sub.example.org/')
        other.enqueue_plan(plan, receipt, now=NOW)
        # The first attempt's lease has expired, so the other scope may claim.
        second = other.claim_next('other-worker', request_id='other-1', now=NOW + 130)
        self.assertIsNotNone(second)
        other.start_attempt(second['attempt_id'], 'other-worker', second['lease_token'], now=NOW + 130)
        # Scope-local recovery only reaps its own scope's expired attempt.
        self.store.recover_expired(now=NOW + 260)
        with sqlite3.connect(self.registry) as con:
            state = con.execute("SELECT status FROM m4_attempts WHERE attempt_id=?",
                                (second['attempt_id'],)).fetchone()[0]
        self.assertEqual(state, 'running')
        # Campaign-wide recovery reaches the dead scope's expired attempt.
        self.store.recover_expired(now=NOW + 261, campaign_wide=True)
        with sqlite3.connect(self.registry) as con:
            state = con.execute("SELECT status FROM m4_attempts WHERE attempt_id=?",
                                (second['attempt_id'],)).fetchone()[0]
        self.assertEqual(state, 'interrupted')
