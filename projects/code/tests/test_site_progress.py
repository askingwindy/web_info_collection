"""Controlled sidecar/identity tests; no browser, model or human review occurs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from webcollect.planning import canonical, object_sha256
from webcollect.runtime import SCHEMA
from webcollect.site_progress import SiteProgress
from webcollect.storage import allocate_in_transaction, ensure_registry_schema


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SiteProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = self.root / 'production.sqlite3'
        self.campaign = 'CONTROLLED-original-campaign'
        con = sqlite3.connect(self.registry)
        ensure_registry_schema(con)
        con.executescript(SCHEMA)
        con.execute('INSERT INTO m4_campaigns VALUES(?,?,?)', (self.campaign, '{}', 1))
        con.commit(); con.close()
        self.state = self.root / 'progress.json'
        self.progress = SiteProgress(self.registry, self.state)
        self.sites = [{'site_id': 'logical-one', 'app_name': '受控站点', 'target_count': 20,
                       'allowed_uris': ['https://example.invalid/one', 'https://example.invalid/two']}]
        self.progress.initialize(self.campaign, self.sites)
        self.tasks = {}
        # Most cases isolate progress bookkeeping from the separately exercised
        # inspector. Two hostile-input tests below explicitly restore the real
        # read-only final checker; no synthetic report is production evidence.
        self.recheck = patch('webcollect.site_progress._recheck_final_report',
                             return_value={'status': 'PASS', 'controlled_checker_stub': True})
        self.recheck.start()
        self.addCleanup(self.recheck.stop)

    def task(self, scope='scope1', task_id='task-one', version='1', uri='https://example.invalid/one'):
        task = {'task_id': task_id, 'task_version': version, 'site_uri': uri, 'site_category': '受控类目'}
        key = object_sha256([self.campaign, task_id, version])
        con = sqlite3.connect(self.registry)
        con.execute('INSERT OR IGNORE INTO m4_scopes VALUES(?,?,?,?)', (scope, self.campaign, 'active', 1))
        con.execute('INSERT INTO m4_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (key, scope, self.campaign, task_id, version, object_sha256(task), canonical(task),
                     '受控类目', 'example.invalid', 'queued', 1, 9999999999, 1, 1))
        con.commit(); con.close()
        self.tasks[key] = task
        return key

    def assignment(self, task_id='task-one', version='1', slot='slot-one'):
        return {'slot_id': slot, 'site_id': 'logical-one', 'task_id': task_id, 'task_version': version}

    def register(self, key=None, scope='scope1', version='1', task_id='task-one', slot='slot-one'):
        key = key or self.task(scope, task_id, version)
        self.progress.register_tasks(scope, [self.assignment(task_id, version, slot)], request_id='register-' + slot)
        return key

    def capture(self, key, *, status='collected_pending_review', started=1):
        con = sqlite3.connect(self.registry)
        con.execute('BEGIN IMMEDIATE')
        scope = con.execute('SELECT scope_id FROM m4_tasks WHERE task_key=?', (key,)).fetchone()[0]
        ids = allocate_in_transaction(con, self.tasks[key]['site_uri'], '受控类目', 'real', day='20261027')
        number = con.execute('SELECT COUNT(*) FROM m4_attempts').fetchone()[0] + 1
        aid = 'controlled-attempt-' + str(number)
        proof = self.root / (aid + '.json')
        proof.write_text('Controlled saved capture proof, not actual collection')
        evidence = [{'path': str(proof), 'sha256': sha(proof)}]
        con.execute('INSERT INTO m4_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (aid, scope, self.campaign, key, 'controlled-plan', 'request-' + str(number),
                     'controlled-worker', 'controlled-lease', 9999999999, ids['sample_id'], ids['site_id'],
                     ids['batch_id'], status, number, started, number + 1,
                     None, 'interrupted' if status == 'interrupted' else None,
                     'controlled failure' if status == 'interrupted' else None, canonical(evidence)))
        con.commit(); con.close()
        return ids['sample_id']

    def package(self, sample_id, *, name='package-one', sample_status='PASS', final=False,
                human=None, sampling='AI_PASS'):
        dataset = self.root / name
        sample = dataset / 'samples' / sample_id
        (sample / 'images').mkdir(parents=True)
        (sample / 'ui_tree').mkdir()
        steps = []
        for n in range(1, 7):
            image = f'images/step_{n:03}.png'; tree = f'ui_tree/step_{n:03}.json'
            (sample / image).write_text('CONTROLLED image fixture ' + str(n))
            (sample / tree).write_text(canonical({'controlled': n}))
            steps.append({'step_id': n, 'image_path': image, 'ui_tree_path': tree})
        (sample / 'annotation.json').write_text(canonical({'sample_id': sample_id, 'steps': steps}))
        files = {p.relative_to(dataset).as_posix(): sha(p) for p in sorted(dataset.rglob('*')) if p.is_file()}
        (dataset / 'SHA256SUMS').write_text(''.join(digest + '  ' + name + '\n' for name, digest in files.items()))
        files['SHA256SUMS'] = sha(dataset / 'SHA256SUMS')
        evidence = {p.relative_to(sample).as_posix(): sha(p) for p in sorted(sample.rglob('*'))
                    if p.is_file() and p.name != 'annotation.json'}
        row = {'sample_id': sample_id, 'sample_path': str(sample), 'status': sample_status,
               'annotation_sha256': sha(sample / 'annotation.json'), 'evidence_sha256': evidence,
               'semantic_sampling': {'status': sampling}}
        from quality_inspector.semantic import rule_ids
        report = {'program': 'quality-inspector', 'dataset': str(dataset), 'semantic_rule_ids':rule_ids(),
                  'inspection_stage': 'final' if final else 'payload', 'release_ready': final,
                  'delivery_status': 'PASS' if final else 'REVIEW_REQUIRED',
                  'input_files_sha256': dict(sorted(files.items())), 'root_checksum': {'pass': True},
                  'baseline': {'config_sha256': 'controlled-contract'}, 'samples': [row]}
        report_path = self.root / (name + '-qc.json')
        report_path.write_text(canonical(report))
        review_path = None
        if human:
            from quality_inspector.reviews import SEMANTIC
            record = {'sample_id': sample_id, 'annotation_sha256': row['annotation_sha256'], 'semantic_rule_ids':rule_ids(),
                      'evidence_sha256': evidence, 'baseline_sha256': 'controlled-contract',
                      'reviewer': {'kind': 'human', 'name': 'CONTROLLED fixture only'},
                      'provenance': {'description': 'Synthetic review fixture; no human inspection occurred',
                                     'frames_viewed': list(range(1, 7))},
                      'step_observations': [{'step_id': n, 'decision': 'ok', 'note': ''} for n in range(1, 7)],
                      'checks': {key: {'status': 'FAIL' if human == 'FAIL' and key == 'terminal_semantics' else 'PASS',
                                      'note': 'Controlled failure' if human == 'FAIL' else '',
                                      'evidence_steps': [6]} for key in SEMANTIC}}
            review_path = self.root / (name + '-human.json')
            review_path.write_text(canonical({'schema_version': 'qc-review-2', 'records': [record]}))
        return report_path, review_path

    def reject_original(self):
        key = self.register()
        sid = self.capture(key)
        report, human = self.package(sid, sample_status='FAIL', human='FAIL', sampling='REPLACE_REQUIRED')
        self.progress.import_qc(report, human_reviews=human, request_id='qc-original')
        return sid

    def test_targets_are_configurable_and_do_not_allocate_ids_or_budget(self):
        before = self.registry.read_bytes()
        result = self.progress.snapshot()
        self.assertEqual(result['remaining_gap'], 20)
        self.assertEqual(result['by_site']['logical-one']['planned'], 0)
        self.assertEqual(before, self.registry.read_bytes())
        other = SiteProgress(self.registry, self.root / 'another.json')
        result = other.initialize(self.campaign, [{**self.sites[0], 'target_count': 2000}])
        self.assertEqual(result['target_count'], 2000)

    def test_missing_original_campaign_or_registry_is_not_recreated(self):
        with self.assertRaisesRegex(ValueError, 'existing initialized'):
            SiteProgress(self.registry, self.root / 'missing.json').initialize('different', self.sites)
        absent = self.root / 'absent.sqlite3'
        with self.assertRaises(sqlite3.OperationalError):
            SiteProgress(absent, self.root / 'absent.json').initialize(self.campaign, self.sites)
        self.assertFalse(absent.exists())

    def test_task_registration_is_bound_and_idempotent(self):
        self.register()
        before = self.state.read_bytes()
        self.progress.register_tasks('scope1', [self.assignment()], request_id='register-slot-one')
        self.assertEqual(before, self.state.read_bytes())
        with self.assertRaisesRegex(ValueError, 'already bound'):
            self.progress.register_tasks('scope1', [self.assignment(slot='different')], request_id='different')

    def test_task_registration_rejects_cross_scope_uri_and_excess_positions(self):
        self.task(uri='https://elsewhere.invalid/')
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.progress.register_tasks('scope1', [self.assignment()], request_id='bad-uri')
        with self.assertRaisesRegex(ValueError, 'already exist'):
            self.progress.register_tasks('wrong-scope', [self.assignment()], request_id='bad-scope')

    def test_captured_success_is_pending_and_does_not_fill_final_gap(self):
        key = self.register(); self.capture(key)
        result = self.progress.sync()['by_site']['logical-one']
        self.assertEqual((result['attempted'], result['captured_pending'], result['remaining_gap']), (1, 1, 20))
        self.assertEqual(result['final_policy_accepted'], 0)

    def test_interrupted_attempt_and_retry_preserve_original_denominator(self):
        key = self.register(); self.capture(key, status='interrupted'); self.capture(key)
        result = self.progress.snapshot()['by_site']['logical-one']
        self.assertEqual((result['attempted'], result['failed_attempts'], result['captured_pending']), (2, 1, 1))

    def test_payload_sample_pass_is_not_final_policy_acceptance(self):
        key = self.register(); sid = self.capture(key)
        report, _ = self.package(sid)
        result = self.progress.import_qc(report, request_id='payload')['by_site']['logical-one']
        self.assertEqual(result['sample_pass'], 1)
        self.assertEqual((result['final_policy_accepted'], result['remaining_gap']), (0, 20))

    def test_final_sampling_admission_counts_without_inventing_ai_or_human_pass(self):
        key = self.register(); sid = self.capture(key)
        report, _ = self.package(sid, final=True, sampling='NOT_SELECTED')
        result = self.progress.import_qc(report, request_id='final')['by_site']['logical-one']
        self.assertEqual((result['not_selected'], result['final_policy_accepted'], result['remaining_gap']), (1, 1, 19))
        self.assertEqual(result['released'], 0)

    def test_import_is_idempotent_and_report_or_customer_drift_stops_progress(self):
        key = self.register(); sid = self.capture(key)
        report, _ = self.package(sid, final=True)
        self.progress.import_qc(report, request_id='final')
        before = self.state.read_bytes()
        self.progress.import_qc(report, request_id='final')
        self.assertEqual(before, self.state.read_bytes())
        image = self.root / 'package-one' / 'samples' / sid / 'images' / 'step_001.png'
        image.write_text('Controlled unexpected change')
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.progress.snapshot()

    def test_explicit_human_fail_creates_replacement_request_and_keeps_original(self):
        sid = self.reject_original()
        requests = self.progress.replacement_requests()
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['replaces_sample_id'], sid)
        self.assertTrue(requests[0]['mandatory_human_recheck'])
        self.assertEqual(self.progress.snapshot()['remaining_gap'], 20)

    def test_ai_failure_alone_does_not_fabricate_human_rejection(self):
        key = self.register(); sid = self.capture(key)
        report, _ = self.package(sid, sample_status='REVIEW_REQUIRED', sampling='HUMAN_REQUIRED')
        result = self.progress.import_qc(report, request_id='ai-fail')
        self.assertEqual(result['by_site']['logical-one']['human_pending'], 1)
        self.assertEqual(result['replacement_requests'], [])
        key2 = self.task('scope2', version='2')
        with self.assertRaisesRegex(ValueError, 'human-rejected'):
            self.progress.bind_replacement('slot-one', 'scope2', self.assignment(version='2'),
                                           replaces_sample_id=sid, request_id='replace')

    def test_stale_or_nonhuman_review_cannot_close_replacement(self):
        key = self.register(); sid = self.capture(key)
        report, human = self.package(sid, sample_status='FAIL', human='FAIL')
        value = json.loads(human.read_text()); value['records'][0]['reviewer']['kind'] = 'ai'
        human.write_text(canonical(value))
        with self.assertRaisesRegex(ValueError, 'explicit human'):
            self.progress.import_qc(report, human_reviews=human, request_id='bad-human')

    def test_replacement_needs_new_scope_and_human_recheck_and_does_not_double_count(self):
        original = self.reject_original()
        replacement_key = self.task('scope2', version='2')
        assignment = self.assignment(version='2')
        self.progress.bind_replacement('slot-one', 'scope2', assignment, replaces_sample_id=original, request_id='replace')
        before = self.state.read_bytes()
        self.progress.bind_replacement('slot-one', 'scope2', assignment, replaces_sample_id=original, request_id='replace')
        self.assertEqual(before, self.state.read_bytes())
        replacement = self.capture(replacement_key)
        self.assertNotEqual(original, replacement)
        report, human = self.package(replacement, name='replacement', final=True, human='PASS', sampling='HUMAN_PASS')
        with self.assertRaisesRegex(ValueError, 'explicit current human PASS'):
            self.progress.import_qc(report, request_id='missing-recheck')
        result = self.progress.import_qc(report, human_reviews=human, request_id='rechecked')['by_site']['logical-one']
        self.assertEqual((result['attempted'], result['final_policy_accepted'], result['remaining_gap']), (2, 1, 19))
        self.assertEqual(result['replacement_positions'], 1)
        self.assertEqual(len(json.loads(self.state.read_text())['events']), 4)

    def test_same_rejected_sample_cannot_be_relabelled_as_pass(self):
        sid = self.reject_original()
        report, human = self.package(sid, name='relabelled', final=True, human='PASS', sampling='HUMAN_PASS')
        with self.assertRaisesRegex(ValueError, 'new capture identity'):
            self.progress.import_qc(report, human_reviews=human, request_id='relabel')

    def test_attempt_limit_preserves_deficit(self):
        limited = SiteProgress(self.registry, self.root / 'limited.json')
        limited.initialize(self.campaign, self.sites, max_attempts_per_slot=1)
        self.progress = limited
        original = self.reject_original()
        self.task('scope2', version='2')
        with self.assertRaisesRegex(ValueError, 'attempt limit'):
            limited.bind_replacement('slot-one', 'scope2', self.assignment(version='2'),
                                     replaces_sample_id=original, request_id='replace')
        self.assertEqual(limited.replacement_requests()[0]['status'], 'ATTEMPT_LIMIT_REACHED')

    def test_task_drift_and_event_tampering_are_rejected(self):
        self.register()
        con = sqlite3.connect(self.registry)
        con.execute("UPDATE m4_tasks SET task_sha256='unexpected'")
        con.commit(); con.close()
        with self.assertRaisesRegex(ValueError, 'task bytes'):
            self.progress.snapshot()
        value = json.loads(self.state.read_text())
        value['events'][0]['payload']['bindings'][0]['site_id'] = 'different'
        self.state.write_text(canonical(value))
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.progress.snapshot()

    def test_handwritten_final_pass_without_checker_inputs_is_rejected(self):
        self.recheck.stop()
        key = self.register(); sid = self.capture(key)
        report, _ = self.package(sid, final=True)
        before = self.state.read_bytes()
        with self.assertRaisesRegex(ValueError, 'existing absolute'):
            self.progress.import_qc(report, request_id='forged-final')
        self.assertEqual(before, self.state.read_bytes())

    def test_handwritten_final_pass_with_real_profile_still_fails_actual_qc(self):
        self.recheck.stop()
        key = self.register(); sid = self.capture(key)
        report, _ = self.package(sid, final=True)
        from quality_inspector.profiles import DEFAULT_DELIVERY_PROFILE, load
        value = json.loads(report.read_text()); value['local_profile'] = load(DEFAULT_DELIVERY_PROFILE)
        report.write_text(canonical(value))
        before = self.state.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Claimed final PASS'):
            self.progress.import_qc(report, request_id='forged-final')
        self.assertEqual(before, self.state.read_bytes())

    def test_sample_path_relocation_and_duplicate_slot_cannot_bypass_binding(self):
        key = self.register(); sid = self.capture(key)
        report, _ = self.package(sid, final=True)
        value = json.loads(report.read_text())
        value['samples'][0]['sample_path'] = str(self.root / 'different-sample')
        report.write_text(canonical(value))
        with self.assertRaisesRegex(ValueError, 'actual client sample path'):
            self.progress.import_qc(report, request_id='moved')
        with self.assertRaisesRegex(ValueError, 'already bound'):
            self.progress.register_tasks('scope1', [self.assignment(slot='slot-copy')], request_id='double-count')
        self.assertEqual(self.progress.snapshot()['by_site']['logical-one']['planned'], 1)

    def test_interrupted_sidecar_write_preserves_last_committed_state(self):
        self.task()
        before = self.state.read_bytes()
        with patch('webcollect.site_progress.os.replace', side_effect=OSError('CONTROLLED interrupted write')):
            with self.assertRaisesRegex(OSError, 'interrupted write'):
                self.progress.register_tasks('scope1', [self.assignment()], request_id='register')
        self.assertEqual(before, self.state.read_bytes())
        self.assertEqual(self.progress.snapshot()['by_site']['logical-one']['planned'], 0)
        self.progress.register_tasks('scope1', [self.assignment()], request_id='register')
        self.assertEqual(self.progress.snapshot()['by_site']['logical-one']['planned'], 1)

    def test_concurrent_registration_preserves_both_events(self):
        from concurrent.futures import ThreadPoolExecutor
        self.task(task_id='one'); self.task(task_id='two', uri='https://example.invalid/two')
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(SiteProgress(self.registry, self.state).register_tasks, 'scope1',
                         [self.assignment(task_id=name, slot='slot-' + name)], request_id='register-' + name)
                       for name in ('one', 'two')]
            for future in futures:
                future.result()
        result = self.progress.snapshot()
        self.assertEqual(result['by_site']['logical-one']['planned'], 2)
        self.assertEqual(len(json.loads(self.state.read_text())['events']), 2)

    def test_multiple_uris_can_belong_to_one_logical_site(self):
        first = self.task(task_id='one'); second = self.task(task_id='two', uri='https://example.invalid/two')
        self.progress.register_tasks('scope1', [self.assignment(task_id=name, slot='slot-' + name)
                                               for name in ('one', 'two')], request_id='multi-uri')
        self.capture(first); self.capture(second)
        result = self.progress.snapshot()
        self.assertEqual(len(result['by_site']), 1)
        self.assertEqual(result['by_site']['logical-one']['attempted'], 2)


if __name__ == '__main__':
    unittest.main()
