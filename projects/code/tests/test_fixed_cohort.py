"""Controlled fixed-cohort accounting; not real collection or model review."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from webcollect import fixed_cohort as cohort
from webcollect.batch_core import file_sha, load_json


class FixedCohortTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.capture = self.root / 'formal-capture'
        self.capture.mkdir()
        self.dataset = self.capture / 'dataset'
        self.dataset.mkdir()
        self.history = self.root / 'history'
        self.history.mkdir()
        self.write(self.history / 'HISTORICAL' / 'annotation.json', {'sample_id': 'HISTORICAL'})
        manifest = self.root / 'history-set.json'
        self.write(manifest, {'schema_version': 'qc-cumulative-set-1', 'packages': [
            {'path': str(self.history), 'package_files_sha256': cohort._files(self.history)}]})
        self.binding = self.root / 'CONTROLLED-bindings.json'
        self.write(self.binding, {'purpose': 'OFFLINE TEST ONLY; no real model or production approval'})
        regular = {'path': str(self.binding), 'sha256': file_sha(self.binding)}
        history = {'path': str(manifest), 'sha256': file_sha(manifest)}
        tasks = [{'task_id': f'T{site:02}-{task:02}', 'site_id': f'SITE-{site:02}',
                  'domain': 'example.invalid', 'uri': f'https://example.invalid/site/{site}',
                  'category': f'CONTROLLED-category-{site % 5}'}
                 for site in range(50) for task in range(20)]
        self.spec = {'cohort_id': 'CONTROLLED-fixed1000', 'campaign_id': 'CONTROLLED-original-campaign',
            'capture_run_id': 'CONTROLLED-formal-run', 'capture_root': str(self.capture),
            'target_count': 1000, 'site_count': 50, 'samples_per_site': 20,
            'counting_policy': 'Exact URI counts as a site; all fixtures are offline controls.',
            'tasks': tasks, 'development_exclusion': {'run_ids': ['CONTROLLED-development'],
                                                       'sample_ids': ['DEVELOPMENT-SAMPLE']},
            'bindings': {group: [deepcopy(history if group == 'history' else regular)]
                         for group in cohort.BINDING_GROUPS}}
        self.state = self.root / 'cohort-state.json'
        self.qc_path = self.root / 'CONTROLLED-qc.json'
        self.cumulative_path = self.root / 'CONTROLLED-cumulative-qc.json'
        self.output = self.root / 'final-report.json'

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def initialize(self):
        return cohort.freeze(self.spec, self.state)

    def sample(self, sid='FORMAL-1'):
        path = self.dataset / 'samples' / sid
        self.write(path / 'images/step_001.png', {'CONTROLLED': 'not an actual PNG'})
        self.write(path / 'ui_tree/step_001.json', {'CONTROLLED': 'not a real UI'})
        self.write(path / 'annotation.json', {'sample_id': sid, 'completion_status': 'success',
            'steps': [{'step_id': 1, 'image_path': 'images/step_001.png',
                       'ui_tree_path': 'ui_tree/step_001.json'}]})
        return path

    def attempt(self, status='SUCCEEDED', *, aid='A1', task='T00-00', sid='FORMAL-1'):
        value = {'attempt_id': aid, 'task_id': task, 'run_id': 'CONTROLLED-formal-run',
                 'status': status}
        if sid is not None:
            value['sample_id'] = sid
            value['sample_path'] = str(self.sample(sid))
        return value

    def qc(self, sid='FORMAL-1', *, semantic=True):
        path = self.dataset / 'samples' / sid
        if not (self.dataset / 'site-list.json').exists():
            self.mapping({sid: 'T00-00'})
        elif not (self.dataset / 'metadata.csv').exists():
            with (self.dataset / 'metadata.csv').open('w', newline='') as stream:
                writer = csv.writer(stream); writer.writerow(['sample_id', 'site_id', 'site_category'])
                writer.writerow([sid, 'SITE-00', 'CONTROLLED-category-0'])
        checks = [{'rule_id': rule, 'status': 'PASS'} for rule in cohort.REQUIRED_RULES]
        checks += [{'rule_id': 'DUPLICATE_SEQUENCE', 'status': 'PASS'},
                   {'rule_id': 'NEAR_DUPLICATES', 'route': 'route3', 'status': 'PASS'},
                   {'rule_id': 'NEAR_DUPLICATES', 'route': 'route4', 'status': 'PASS'}]
        if semantic:
            checks += [{'rule_id': 'REVIEW_' + name.upper(), 'status': 'PASS',
                        'reviewer': {'kind': 'ai', 'name': 'CONTROLLED-NOT-A-REAL-MODEL'},
                        'provenance': {'frames_viewed': [1]}}
                       for name in cohort.SEMANTIC]
        row = {'sample_id': sid, 'sample_path': str(path), 'status': 'PASS', 'checks': checks,
               'annotation_sha256': file_sha(path / 'annotation.json'),
               'evidence_sha256': {p: file_sha(path / p) for p in
                                   ('images/step_001.png', 'ui_tree/step_001.json')}}
        report = {'program': 'quality-inspector', 'scope': 'delivery', 'layout': 'customer-flat',
                  'status': 'PASS', 'dataset': str(self.dataset),
                  'sample_count': 1, 'samples': [row],
                  'inspection_stage': 'payload', 'release_ready': False,
                  'input_integrity': {'status': 'PASS', 'checked_before_and_after': True, 'errors': []},
                  'root_checksum': {'pass': True}, 'duplicates': self.empty_duplicates([sid]),
                  'dataset_checks': [{'rule_id': rule, 'status': 'PASS'} for rule in (
                      'C13', 'C14', 'DELIVERY_DOCUMENT_CONTENT', 'DELIVERY_DOCUMENT_CONTENT',
                      'DELIVERY_ATTACHMENT', 'DELIVERY_ATTACHMENT', 'DELIVERY_DOCUMENT_ROLES',
                      'DELIVERY_ACCOUNTING', 'DELIVERY_VIEWPORT_SPECS', 'DELIVERY_SHORT_FLOW_SHARE',
                      'DELIVERY_CATEGORY_SHARE', 'ROOT_CHECKSUM', 'DELIVERY_DOCUMENT_REVIEW')],
                  'input_files_sha256': cohort._files(self.dataset),
                  'test_boundary': 'Fabricated protocol result only; no actual QC judgment.'}
        self.write(self.qc_path, report)
        inputs = {str(self.history): cohort._files(self.history), str(self.dataset): cohort._files(self.dataset)}
        manifest = {'schema_version': 'qc-cumulative-set-1', 'packages': [
            {'path': path, 'package_files_sha256': files} for path, files in inputs.items()]}
        self.write(self.cumulative_path, {'schema_version': 'qc-cumulative-report-1',
            'mechanical_status': 'PASS', 'status': 'PASS', 'errors': [],
            'input_integrity_checked_before_and_after': True,
            'sample_count': 2, 'manifest': manifest, 'manifest_sha256': cohort.object_sha256(manifest),
            'input_files_sha256': inputs, 'duplicates': self.empty_duplicates(['HISTORICAL', sid])})
        return report

    def empty_duplicates(self, ids=()):
        result = {route: {count: 0, pairs: []} for route, count, pairs in (
            ('route1', 'confirmed_pair_count', 'pairs'), ('route2', 'count', 'confirmed_pairs'),
            ('route3', 'count', 'candidates'), ('route4', 'count', 'candidates'))}
        result.update(sample_count=len(ids), pair_comparisons=len(ids) * (len(ids) - 1) // 2,
                      rows=[{'sample_id': sid} for sid in ids])
        return result

    def mapping(self, assignments):
        tasks = {task['task_id']: task for task in self.spec['tasks']}
        sites = {}
        for sid, tid in assignments.items():
            task = tasks[tid]
            site = sites.setdefault(task['site_id'], {'site_id': task['site_id'], 'uri': task['uri'],
                'site_category': task['category'], 'sample_ids': []})
            site['sample_ids'].append(sid)
        self.write(self.dataset / 'site-list.json', {'schema_version': 'webcollect-site-list-1',
            'sites': list(sites.values()), 'samples': [
                {'sample_id': sid, 'site_id': tasks[tid]['site_id']} for sid, tid in assignments.items()]})
        with (self.dataset / 'metadata.csv').open('w', newline='') as stream:
            writer = csv.writer(stream); writer.writerow(['sample_id', 'site_id', 'site_category'])
            for sid, tid in assignments.items():
                task = tasks[tid]; writer.writerow([sid, task['site_id'], task['category']])

    def ready(self, *, semantic=True):
        self.initialize()
        cohort.record(self.state, self.attempt())
        self.qc(semantic=semantic)
        cohort.seal(self.state)

    def finish(self, **kwargs):
        return cohort.finalize(self.state, self.qc_path, self.output,
                                cumulative_report=self.cumulative_path, **kwargs)

    def test_freeze_requires_complete_50_by_20_assignment_and_unique_task_ids(self):
        for variant in ('count', 'duplicate', 'site', 'uri'):
            bad = deepcopy(self.spec)
            if variant == 'count': bad['tasks'].pop()
            elif variant == 'duplicate': bad['tasks'][1]['task_id'] = bad['tasks'][0]['task_id']
            elif variant == 'site': bad['tasks'][0]['site_id'] = 'NEW'
            else: bad['tasks'][0]['uri'] = 'https://other.invalid/task'
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                cohort.freeze(bad, self.state)
        self.assertFalse(self.state.exists())

    def test_frozen_membership_and_development_exclusion_cannot_be_reassigned(self):
        first = self.initialize()
        self.assertEqual(cohort.freeze(self.spec, self.state), first)
        for change in ('ownership', 'task'):
            bad = deepcopy(self.spec)
            if change == 'ownership': bad['development_exclusion']['sample_ids'] = []
            else: bad['tasks'][0]['task_id'] = 'REPLACEMENT'
            with self.assertRaisesRegex(ValueError, 'replace a fixed cohort'):
                cohort.freeze(bad, self.state)

    def test_development_run_sample_and_historical_ids_are_rejected(self):
        self.initialize()
        for mode in ('run', 'development', 'history'):
            value = self.attempt()
            if mode == 'run': value['run_id'] = 'CONTROLLED-development'
            elif mode == 'development': value['sample_id'] = 'DEVELOPMENT-SAMPLE'
            else: value['sample_id'] = 'HISTORICAL'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                cohort.record(self.state, value)
        self.assertEqual(cohort.verify(self.state)['attempt_count'], 0)

    def test_failure_is_preserved_retry_succeeds_and_idempotent_record_does_not_recount(self):
        self.initialize()
        failed = self.attempt('FAILED', aid='FAILED-FIRST', sid=None)
        cohort.record(self.state, failed)
        cohort.record(self.state, failed)
        value = self.attempt(aid='SUCCEEDED-SECOND')
        cohort.record(self.state, value)
        cohort.record(self.state, value)
        self.qc()
        cohort.seal(self.state)
        result = self.finish()
        self.assertEqual(result['capture_attempt_count'], 2)
        self.assertEqual(result['failed_capture_attempt_count'], 1)
        self.assertEqual(result['collected_count'], 1)
        self.assertEqual(result['primary_success_rate']['value'], .001)
        self.assertEqual(result['collected_sample_pass_rate']['value'], 1)
        self.assertEqual(result['collection_gap'], 999)
        self.assertFalse(result['formal_1000_collection_complete'])
        self.assertEqual(sum(result['cohort_status_counts'].values()), 1000)

    def test_success_is_not_recollected_and_failed_ids_are_never_reused(self):
        self.initialize()
        value = self.attempt()
        cohort.record(self.state, value)
        with self.assertRaisesRegex(ValueError, 'cannot be collected again'):
            cohort.record(self.state, self.attempt(aid='A2', sid='FORMAL-2'))
        with self.assertRaisesRegex(ValueError, 'ID cannot be reused'):
            cohort.record(self.state, self.attempt(aid='A3', task='T00-01'))

    def test_bounded_retry_and_immutable_attempt_payload(self):
        self.initialize()
        failed = self.attempt('FAILED', aid='F1', sid=None)
        cohort.record(self.state, failed)
        with self.assertRaisesRegex(ValueError, 'attempt is immutable'):
            cohort.record(self.state, {**failed, 'reason': 'changed historical reason'})
        cohort.record(self.state, {**failed, 'attempt_id': 'F2'})
        with self.assertRaisesRegex(ValueError, 'attempt limit'):
            cohort.record(self.state, {**failed, 'attempt_id': 'F3'})

    def test_all_tree_bytes_are_sealed_and_qc_never_writes_inside_capture(self):
        self.ready()
        self.write(self.capture / 'extra-log.json', {'event': 'added after seal'})
        self.assertEqual(cohort.verify(self.state)['status'], 'FAIL')
        result = self.finish()
        self.assertEqual(result['collected_sample_status_counts']['PASS'], 0)
        self.assertEqual(result['collected_sample_status_counts']['FAIL'], 1)
        self.assertTrue(any(issue['kind'] == 'SEALED_CAPTURE_CHANGED' for issue in result['issues']))

    def test_missing_semantic_review_cannot_become_pass(self):
        self.ready(semantic=False)
        before = cohort._files(self.capture)
        result = self.finish()
        self.assertEqual(result['collected_sample_status_counts']['REVIEW_REQUIRED'], 1)
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertEqual(cohort._files(self.capture), before)

    def test_synthetic_or_incomplete_semantic_provenance_is_not_approval(self):
        self.ready()
        value = load_json(self.qc_path)
        semantic = [c for c in value['samples'][0]['checks'] if c['rule_id'].startswith('REVIEW_')]
        semantic[0]['reviewer']['kind'] = 'synthetic'
        self.write(self.qc_path, value)
        result = self.finish()
        self.assertEqual(result['collected_sample_status_counts']['PASS'], 0)

    def test_missing_cumulative_history_cannot_become_pass(self):
        self.ready()
        result = cohort.finalize(self.state, self.qc_path, self.output)
        self.assertEqual(result['collected_sample_status_counts']['PASS'], 0)
        self.assertEqual(result['cumulative_status'], 'REVIEW_REQUIRED')

    def test_cumulative_omitted_history_and_duplicate_hits_fail(self):
        self.ready()
        report = load_json(self.cumulative_path)
        del report['input_files_sha256'][str(self.history)]
        self.write(self.cumulative_path, report)
        result = self.finish()
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['primary_success_rate']['numerator'], 0)

    def test_duplicate_or_extra_qc_ids_and_missing_population_cannot_pass(self):
        for variant in ('duplicate', 'extra', 'missing'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as td:
                # Separate state per evaluation; no same-round rescore is used.
                state = Path(td).resolve() / 'state.json'
                cohort.freeze(self.spec, state)
                cohort.record(state, self.attempt())
                value = self.qc()
                if variant == 'duplicate': value['samples'].append(deepcopy(value['samples'][0]))
                elif variant == 'extra':
                    value['samples'].append({**deepcopy(value['samples'][0]), 'sample_id': 'EXTRA'})
                else: value['samples'] = []
                value['sample_count'] = len(value['samples'])
                self.write(self.qc_path, value)
                cohort.seal(state)
                result = cohort.finalize(state, self.qc_path, Path(td).resolve() / 'out.json',
                                         cumulative_report=self.cumulative_path)
                self.assertNotEqual(result['status'], 'PASS')
                self.assertEqual(result['primary_success_rate']['numerator'], 0)

    def test_checker_exception_is_terminal_and_does_not_invent_judgments(self):
        self.initialize()
        cohort.record(self.state, self.attempt())
        cohort.seal(self.state)
        result = cohort.finalize(self.state, output=self.output, checker_error='Controlled checker crash')
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertEqual(result['limitations'][0]['kind'], 'CHECKER_EXCEPTION')
        self.assertEqual(cohort.verify(self.state)['phase'], 'FINALIZED')
        with self.assertRaisesRegex(ValueError, 'reject attempt'):
            cohort.record(self.state, self.attempt(aid='LATE', sid='REPLACEMENT'))

    def test_malformed_and_missing_checker_reports_are_preserved_as_limits(self):
        for missing in (False, True):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as td:
                state = Path(td).resolve() / 'state.json'
                cohort.freeze(self.spec, state)
                cohort.seal(state)
                qc = Path(td).resolve() / 'broken.json'
                if not missing: qc.write_text('{broken JSON')
                result = cohort.finalize(state, qc, Path(td).resolve() / 'report.json')
                self.assertEqual(result['primary_success_rate']['numerator'], 0)
                self.assertEqual(result['limitations'][0]['kind'], 'QC_REPORT_EXCEPTION')
                self.assertEqual(cohort.verify(state)['phase'], 'FINALIZED')

    def test_final_report_is_idempotent_and_same_round_rescoring_is_forbidden(self):
        self.ready()
        first = self.finish()
        original_state = self.state.read_bytes()
        original_output = self.output.read_bytes()
        self.assertEqual(self.finish(), first)
        self.assertEqual(self.state.read_bytes(), original_state)
        self.assertEqual(self.output.read_bytes(), original_output)
        with self.assertRaisesRegex(ValueError, 'rescoring is prohibited'):
            cohort.finalize(self.state, self.qc_path, self.root / 'new-score.json',
                            cumulative_report=self.cumulative_path)
        self.qc_path.write_text(self.qc_path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'rescoring is prohibited'):
            self.finish()
        self.assertEqual(cohort.verify(self.state)['status'], 'FAIL')

    def test_crash_after_score_freeze_resumes_without_recomputing_score(self):
        self.ready()
        with patch.object(cohort, 'save_json', side_effect=OSError('Controlled publication crash')):
            with self.assertRaises(OSError): self.finish()
        self.assertEqual(load_json(self.state)['phase'], 'FINALIZING')
        stored = load_json(self.state)['finalization']['report']
        with patch.object(cohort, '_summarize', side_effect=AssertionError('Must not rescore')):
            recovered = self.finish()
        self.assertEqual(recovered, stored)
        self.assertEqual(cohort.verify(self.state)['phase'], 'FINALIZED')

    def test_source_binding_mutation_prevents_collection_and_is_reported_after_seal(self):
        self.ready()
        self.binding.write_text('controlled changed source bytes')
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertTrue(any(issue['kind'] == 'FROZEN_BINDING_CHANGED' for issue in result['issues']))

    def test_state_qc_and_output_cannot_be_inside_capture(self):
        with self.assertRaisesRegex(ValueError, 'outside sealed capture'):
            cohort.freeze(self.spec, self.capture / 'state.json')
        self.ready()
        with self.assertRaisesRegex(ValueError, 'outside sealed capture'):
            cohort.finalize(self.state, self.qc_path, self.capture / 'report.json')
        with self.assertRaisesRegex(ValueError, 'outside sealed capture'):
            cohort.finalize(self.state, self.capture / 'qc.json', self.output)

    def test_state_or_report_cannot_modify_historical_delivery(self):
        with self.assertRaisesRegex(ValueError, 'outside sealed capture'):
            cohort.freeze(self.spec, self.history / 'state.json')
        self.ready()
        with self.assertRaisesRegex(ValueError, 'outside sealed capture'):
            cohort.finalize(self.state, self.qc_path, self.history / 'report.json')

    def test_failed_reserved_id_is_not_reused_on_another_task(self):
        self.initialize()
        failed = self.attempt('FAILED')
        cohort.record(self.state, failed)
        with self.assertRaisesRegex(ValueError, 'ID cannot be reused'):
            cohort.record(self.state, self.attempt(aid='NEW', task='T00-01'))

    def test_missing_actual_success_annotation_is_rejected(self):
        self.initialize()
        value = self.attempt()
        (Path(value['sample_path']) / 'annotation.json').unlink()
        with self.assertRaises(OSError):
            cohort.record(self.state, value)
        self.assertEqual(cohort.verify(self.state)['attempt_count'], 0)

    def test_source_change_before_collection_rejects_new_attempt(self):
        self.initialize()
        self.binding.write_text('CONTROLLED source mutation')
        with self.assertRaisesRegex(ValueError, 'changed during collection'):
            cohort.record(self.state, self.attempt())

    def test_seal_rejects_symbolic_capture_files(self):
        self.initialize()
        (self.capture / 'aliased-history').symlink_to(self.history, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'cannot contain symlinks'):
            cohort.seal(self.state)

    def test_capture_and_attempt_history_tampering_are_detected(self):
        self.initialize()
        cohort.record(self.state, self.attempt('FAILED', sid=None))
        state = load_json(self.state)
        state['attempts'][0]['attempt']['status'] = 'SUCCEEDED'
        # Even recomputing the outer state digest cannot erase event binding.
        cohort._state_write(self.state, state)
        with self.assertRaisesRegex(ValueError, 'attempt history integrity'):
            cohort.verify(self.state)

    def test_malformed_qc_checks_are_terminal_without_manufactured_pass(self):
        self.ready()
        value = load_json(self.qc_path)
        value['samples'][0]['checks'] = [None]
        value['dataset_checks'] = [None]
        self.write(self.qc_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertEqual(result['collected_sample_status_counts']['FAIL'], 1)
        self.assertEqual(cohort.verify(self.state)['phase'], 'FINALIZED')

    def test_global_checker_failure_and_cumulative_duplicate_are_not_overridden(self):
        self.ready()
        value = load_json(self.qc_path)
        value['status'] = 'FAIL'
        self.write(self.qc_path, value)
        cumulative = load_json(self.cumulative_path)
        cumulative['duplicates']['route4']['count'] = 1
        self.write(self.cumulative_path, cumulative)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(any(i['kind'] == 'CUMULATIVE_DUPLICATE' for i in result['issues']))

    def test_qc_report_mutation_during_summary_is_bound_and_fails(self):
        self.ready()
        original = cohort._sample_decision
        def changing(row, attempt):
            self.qc_path.write_text(self.qc_path.read_text() + '\n')
            return original(row, attempt)
        with patch.object(cohort, '_sample_decision', side_effect=changing):
            result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertTrue(any(i['kind'] == 'QC_EVIDENCE_CHANGED_DURING_REPORT' for i in result['issues']))
        self.assertEqual(load_json(self.state)['phase'], 'FINALIZED')

    def test_complete_controlled_population_reports_exactly_1000_not_an_estimate(self):
        state = self.initialize()
        # Bulk-build the controlled ledger fixture to isolate finalization from
        # record performance. These fabricated reports never execute real QC.
        template = self.qc()['samples'][0] if (self.dataset / 'samples/FORMAL-1').exists() else None
        rows = []
        previous = state['spec_sha256']
        for number, task in enumerate(self.spec['tasks'], 1):
            sid = f'CONTROLLED-{number:04}'
            sample = self.sample(sid)
            attempt = {'attempt_id': f'A-{number}', 'task_id': task['task_id'],
                'run_id': 'CONTROLLED-formal-run', 'status': 'SUCCEEDED',
                'sample_id': sid, 'sample_path': str(sample), 'cost_reference': 'UNKNOWN'}
            event = {'sequence': number, 'recorded_at_utc': cohort._now(),
                     'attempt': attempt, 'previous_sha256': previous}
            event['event_sha256'] = cohort.object_sha256(event)
            previous = event['event_sha256']
            state['attempts'].append(event)
            if template is None:
                template = self.qc(sid)['samples'][0]
            row = deepcopy(template)
            row.update(sample_id=sid, sample_path=str(sample),
                       annotation_sha256=file_sha(sample / 'annotation.json'),
                       evidence_sha256={p: file_sha(sample / p) for p in
                           ('images/step_001.png', 'ui_tree/step_001.json')})
            rows.append(row)
        cohort._state_write(self.state, state)
        self.mapping({event['attempt']['sample_id']: event['attempt']['task_id'] for event in state['attempts']})
        report = load_json(self.qc_path)
        report.update(samples=rows, sample_count=1000, input_files_sha256=cohort._files(self.dataset),
                      duplicates=self.empty_duplicates([row['sample_id'] for row in rows]))
        self.write(self.qc_path, report)
        cumulative = load_json(self.cumulative_path)
        cumulative['input_files_sha256'][str(self.dataset)] = cohort._files(self.dataset)
        cumulative['manifest'] = {'schema_version': 'qc-cumulative-set-1', 'packages': [
            {'path': path, 'package_files_sha256': files} for path, files in cumulative['input_files_sha256'].items()]}
        cumulative['manifest_sha256'] = cohort.object_sha256(cumulative['manifest'])
        cumulative['sample_count'] = 1001
        cumulative['duplicates'] = self.empty_duplicates(['HISTORICAL', *[row['sample_id'] for row in rows]])
        self.write(self.cumulative_path, cumulative)
        cohort.seal(self.state)
        result = self.finish()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['cohort_status_counts'], {'PASS': 1000, 'FAIL': 0, 'REVIEW_REQUIRED': 0})
        self.assertEqual(result['collection_gap'], 0)
        self.assertTrue(result['formal_1000_collection_complete'])
        self.assertEqual(result['primary_success_rate']['denominator'], 1000)
        self.assertEqual(result['primary_success_rate']['value'], 1)

    def test_audit_dataset_cannot_hide_unregistered_actual_sample_directory(self):
        self.initialize()
        cohort.record(self.state, self.attempt())
        self.sample('UNREGISTERED-ACTUAL-SAMPLE')
        self.qc()  # Complete file hashes include the hidden sample; rows omit it.
        cohort.seal(self.state)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertEqual(result['status'], 'FAIL')

    def test_audit_actual_annotation_identity_must_match_registered_success(self):
        self.initialize()
        value = self.attempt()
        cohort.record(self.state, value)
        annotation = Path(value['sample_path']) / 'annotation.json'
        original = load_json(annotation)
        original['sample_id'] = 'DIFFERENT-ACTUAL-ID'
        self.write(annotation, original)
        self.qc()  # Row falsely retains FORMAL-1 while binding the new bytes.
        cohort.seal(self.state)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)

    def test_audit_frozen_site_uri_cannot_be_reassigned_by_self_consistent_qc(self):
        self.initialize()
        cohort.record(self.state, self.attempt())
        self.write(self.dataset / 'site-list.json', {'schema_version': 'webcollect-site-list-1',
            'sites': [{'site_id': 'SITE-00', 'uri': 'https://example.invalid/WRONG-BUSINESS',
                       'site_category': 'CONTROLLED-category-0', 'sample_ids': ['FORMAL-1']}],
            'samples': [{'sample_id': 'FORMAL-1', 'site_id': 'SITE-00'}]})
        self.qc()
        cohort.seal(self.state)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)

    def test_audit_duplicate_candidate_lists_override_zero_counts(self):
        self.ready()
        value = load_json(self.cumulative_path)
        value['duplicates']['route4']['candidates'] = [{'sample_ids': ['FORMAL-1', 'HISTORICAL']}]
        self.write(self.cumulative_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertEqual(result['status'], 'FAIL')

    def test_audit_local_duplicate_report_cannot_disagree_with_sample_pass(self):
        self.ready()
        value = load_json(self.qc_path)
        value['duplicates'] = {'route3': {'count': 1, 'candidates': [{'sample_ids': ['FORMAL-1', 'OTHER']} ]}}
        self.write(self.qc_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)

    def test_audit_engine_contract_fail_alias_cannot_be_ignored(self):
        self.ready()
        value = load_json(self.qc_path)
        value['contract_status'] = 'FAIL'
        self.write(self.qc_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertEqual(result['status'], 'FAIL')

    def test_audit_checker_input_integrity_failure_cannot_be_ignored(self):
        self.ready()
        value = load_json(self.qc_path)
        value['input_integrity'] = {'status': 'FAIL', 'checked_before_and_after': True,
                                    'errors': ['Original bytes changed during actual checker execution']}
        self.write(self.qc_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)

    def test_audit_unexpected_summarizer_exception_is_terminal_not_repairable_rescore(self):
        self.ready()
        with patch.object(cohort, '_sample_decision', side_effect=RuntimeError('CONTROLLED unexpected checker shape')):
            result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertEqual(load_json(self.state)['phase'], 'FINALIZED')
        self.assertTrue(any(item['kind'] == 'CHECKER_SUMMARIZER_EXCEPTION' for item in result['limitations']))
        with self.assertRaisesRegex(ValueError, 'rescoring is prohibited'):
            cohort.finalize(self.state, output=self.root / 'new-score.json', checker_error='Edited after failure')

    def test_audit_observed_source_drift_cannot_be_erased_by_restoring_old_bytes(self):
        self.initialize()
        original = self.binding.read_bytes()
        self.binding.write_text('CONTROLLED source drift during formal collection')
        with self.assertRaises(ValueError):
            cohort.record(self.state, self.attempt())
        self.binding.write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'changed during collection'):
            cohort.record(self.state, self.attempt())
        cohort.seal(self.state)
        result = cohort.finalize(self.state, output=self.output, checker_error='Known frozen-source violation')
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertTrue(any(issue['kind'] == 'FROZEN_BINDING_CHANGED' and issue.get('observed_sha256')
                            for issue in result['issues']))

    def test_audit_preexisting_report_is_never_overwritten_or_rescored(self):
        self.ready()
        self.output.write_text('PREEXISTING DIFFERENT IMMUTABLE ARTIFACT')
        with self.assertRaisesRegex(ValueError, 'replace different artifact'):
            self.finish()
        self.assertEqual(self.output.read_text(), 'PREEXISTING DIFFERENT IMMUTABLE ARTIFACT')
        self.assertEqual(load_json(self.state)['phase'], 'FINALIZING')
        with self.assertRaisesRegex(ValueError, 'rescoring is prohibited'):
            cohort.finalize(self.state, self.qc_path, self.root / 'replacement.json',
                            cumulative_report=self.cumulative_path)

    def test_audit_cumulative_overall_fail_is_preserved(self):
        self.ready()
        value = load_json(self.cumulative_path)
        value['status'] = 'FAIL'
        self.write(self.cumulative_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertEqual(result['status'], 'FAIL')

    def test_audit_checker_fail_with_pending_samples_stays_overall_fail(self):
        self.ready(semantic=False)
        value = load_json(self.qc_path)
        value['status'] = 'FAIL'
        value['samples'][0]['status'] = 'REVIEW_REQUIRED'
        self.write(self.qc_path, value)
        result = self.finish()
        self.assertEqual(result['status'], 'FAIL')

    def test_audit_duplicate_search_must_cover_the_entire_bound_population(self):
        self.ready()
        value = load_json(self.cumulative_path)
        value['duplicates']['sample_count'] = 1  # It silently omitted history.
        value['duplicates']['rows'] = [{'sample_id': 'FORMAL-1'}]
        value['duplicates']['pair_comparisons'] = 0
        self.write(self.cumulative_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)

    def test_audit_post_finalize_history_mutation_is_reported_without_rescoring(self):
        self.ready()
        self.finish()
        self.write(self.history / 'HISTORICAL' / 'annotation.json', {'sample_id': 'MUTATED'})
        self.assertEqual(cohort.verify(self.state)['status'], 'FAIL')

    def test_audit_missing_text_narrative_rule_c12_cannot_hide_behind_five_reviews(self):
        self.ready()
        value = load_json(self.qc_path)
        value['samples'][0]['checks'] = [row for row in value['samples'][0]['checks'] if row['rule_id'] != 'C12']
        self.assertEqual(sum(row['rule_id'].startswith('REVIEW_') for row in value['samples'][0]['checks']), 5)
        self.write(self.qc_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertIn('MISSING_C12', result['samples'][0]['reasons'])

    def test_audit_missing_batch_c13_is_not_filled_by_sample_rules(self):
        self.ready()
        value = load_json(self.qc_path)
        value['dataset_checks'] = [row for row in value['dataset_checks'] if row['rule_id'] != 'C13']
        self.write(self.qc_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertTrue(any(issue['kind'] == 'MISSING_REQUIRED_BATCH_RULES' and 'C13' in issue['rules'] for issue in result['issues']))

    def test_audit_missing_batch_c14_is_not_filled_by_sample_rules(self):
        self.ready()
        value = load_json(self.qc_path)
        value['dataset_checks'] = [row for row in value['dataset_checks'] if row['rule_id'] != 'C14']
        self.write(self.qc_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertTrue(any(issue['kind'] == 'MISSING_REQUIRED_BATCH_RULES' and 'C14' in issue['rules'] for issue in result['issues']))

    def test_audit_generic_batch_pass_cannot_replace_actual_check_set(self):
        self.ready()
        value = load_json(self.qc_path)
        value['dataset_checks'] = [{'rule_id': 'GENERIC_ALL_GOOD', 'status': 'PASS'}]
        self.write(self.qc_path, value)
        result = self.finish()
        self.assertEqual(result['primary_success_rate']['numerator'], 0)
        self.assertNotEqual(result['status'], 'PASS')

    def test_audit_hard_interruption_freezes_inputs_before_summary_can_be_changed(self):
        self.ready()
        with patch.object(cohort, '_summarize', side_effect=KeyboardInterrupt('CONTROLLED process interruption')):
            with self.assertRaises(KeyboardInterrupt):
                self.finish()
        self.assertEqual(load_json(self.state)['phase'], 'EVALUATING')
        self.qc_path.write_text(self.qc_path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'rescoring is prohibited'):
            self.finish()
        self.assertEqual(cohort.verify(self.state)['status'], 'FAIL')

    def test_audit_hard_interruption_resumes_same_inputs_without_new_attempts(self):
        self.ready()
        with patch.object(cohort, '_summarize', side_effect=KeyboardInterrupt('CONTROLLED interruption')):
            with self.assertRaises(KeyboardInterrupt):
                self.finish()
        request = load_json(self.state)['finalization']['request']
        result = self.finish()
        self.assertEqual(load_json(self.state)['finalization']['request'], request)
        self.assertEqual(load_json(self.state)['phase'], 'FINALIZED')
        self.assertEqual(result['primary_success_rate']['numerator'], 1)
        self.assertEqual(result['capture_attempt_count'], 1)


if __name__ == '__main__':
    unittest.main()
