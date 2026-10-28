"""Synthetic human clicks exercise input semantics, never real review approval."""
import copy
import json
import unittest

import test_delivery
from quality_inspector.reviews import migration_template


class HumanStepConfirmationTests(unittest.TestCase):
    setUp = test_delivery.DeliveryContractTests.setUp
    tearDown = test_delivery.DeliveryContractTests.tearDown
    seal = test_delivery.DeliveryContractTests.seal
    report = test_delivery.DeliveryContractTests.report
    reviewed = test_delivery.DeliveryContractTests.reviewed

    def confirmation(self):
        path = self.reviewed()
        value = json.loads(path.read_text())
        row = value['records'][0]
        row['reviewer'] = {'kind': 'human', 'name': 'SYNTHETIC HUMAN CLICK TEST ONLY'}
        for observation in row['step_observations']:
            observation.update(decision='ok', note='')
        path.write_text(json.dumps(value))
        return path, value

    def assert_rejected(self, path):
        result = self.report(reviews=path)
        self.assertEqual(result['review_import']['accepted_count'], 0)
        self.assertTrue(result['review_import']['invalid_records'])
        self.assertFalse(result['release_ready'])
        return result

    def test_explicit_human_ok_is_imported_without_manufacturing_notes(self):
        path, value = self.confirmation()
        before = path.read_bytes()
        result = self.report(reviews=path)
        self.assertEqual(result['review_import']['accepted_count'], 1)
        self.assertEqual(result['review_import']['invalid_records'], [])
        self.assertEqual(result['local_sample_status'], 'PASS')
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(all(item['note'] == '' for item in value['records'][0]['step_observations']))
        self.assertFalse(result['review_import']['identity_authenticated'])
        self.assertFalse(result['review_import']['actual_reading_authenticated'])

    def test_issue_unclear_missing_or_unrecognized_decision_need_written_observation(self):
        for decision in ('issue', 'unclear', None, 'PASS'):
            with self.subTest(decision=decision):
                path, value = self.confirmation()
                observation = value['records'][0]['step_observations'][0]
                if decision is None:
                    observation.pop('decision')
                else:
                    observation['decision'] = decision
                path.write_text(json.dumps(value))
                self.assert_rejected(path)

    def test_ai_ok_still_requires_actual_written_observations(self):
        path, value = self.confirmation()
        value['records'][0]['reviewer']['kind'] = 'ai'
        path.write_text(json.dumps(value))
        result = self.assert_rejected(path)
        self.assertIn('nonempty note', str(result['review_import']['invalid_records']))

    def test_note_field_remains_a_string_even_for_explicit_human_ok(self):
        for bad in (None, [], 0):
            with self.subTest(note=bad):
                path, value = self.confirmation()
                value['records'][0]['step_observations'][0]['note'] = bad
                path.write_text(json.dumps(value))
                self.assert_rejected(path)

    def test_confirmation_cannot_replace_unviewed_missing_or_duplicate_step(self):
        mutations = (
            lambda row: row['provenance']['frames_viewed'].pop(),
            lambda row: row['step_observations'].pop(),
            lambda row: row['step_observations'].__setitem__(1, copy.deepcopy(row['step_observations'][0])),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                path, value = self.confirmation()
                mutation(value['records'][0])
                path.write_text(json.dumps(value))
                self.assert_rejected(path)

    def test_confirmation_keeps_annotation_and_evidence_hash_guards(self):
        for field in ('annotation_sha256', 'evidence_sha256'):
            with self.subTest(field=field):
                path, value = self.confirmation()
                row = value['records'][0]
                if field == 'annotation_sha256':
                    row[field] = '0' * 64
                else:
                    key = next(iter(row[field]))
                    row[field][key] = '0' * 64
                path.write_text(json.dumps(value))
                self.assert_rejected(path)

    def test_old_human_written_notes_without_decision_remain_accepted(self):
        path = self.reviewed()
        value = json.loads(path.read_text())
        value['records'][0]['reviewer']['kind'] = 'human'
        path.write_text(json.dumps(value))
        self.assertEqual(self.report(reviews=path)['review_import']['accepted_count'], 1)

    def test_human_pass_accepts_empty_reasons_without_manufacturing_text(self):
        path, value = self.confirmation()
        for check in value['records'][0]['checks'].values():
            check['note'] = ''
        path.write_text(json.dumps(value))
        before = path.read_bytes()
        result = self.report(reviews=path)
        self.assertEqual(result['review_import']['accepted_count'], 1)
        self.assertEqual(result['local_sample_status'], 'PASS')
        self.assertEqual(path.read_bytes(), before)

    def test_human_fail_and_ai_resolved_checks_still_require_reasons(self):
        for kind, status in (('human', 'FAIL'), ('ai', 'PASS'), ('ai', 'FAIL')):
            with self.subTest(kind=kind, status=status):
                path, value = self.confirmation()
                row = value['records'][0]
                row['reviewer']['kind'] = kind
                for observation in row['step_observations']:
                    observation['note'] = 'SYNTHETIC observed fixture step only'
                row['checks']['visual_alignment'].update(status=status, note='')
                path.write_text(json.dumps(value))
                result = self.assert_rejected(path)
                self.assertIn('actual evidence reasoning required visual_alignment',
                              str(result['review_import']['invalid_records']))

    def test_human_pass_reason_still_requires_string_type_and_step_references(self):
        for mutation in (
            lambda row: row['checks']['visual_alignment'].update(note=None),
            lambda row: row['checks']['visual_alignment'].update(note=[], evidence_steps=[]),
            lambda row: row['checks']['visual_alignment'].update(note='', evidence_steps=[]),
        ):
            with self.subTest(mutation=mutation):
                path, value = self.confirmation()
                mutation(value['records'][0])
                path.write_text(json.dumps(value))
                self.assert_rejected(path)

    def test_human_document_pass_may_omit_note_and_evidence_detail(self):
        path, value = self.confirmation()
        document = value['delivery_document_review']
        document['reviewer'] = {'kind': 'human', 'name': 'SYNTHETIC HUMAN DOCUMENT CLICK ONLY'}
        for check in document['checks'].values():
            check['note'] = ''
            for evidence in check['evidence']:
                evidence['detail'] = ''
        path.write_text(json.dumps(value))
        before = path.read_bytes()
        result = self.report(reviews=path)
        self.assertEqual(result['delivery_document_review']['status'], 'PASS')
        self.assertEqual(result['delivery_status'], 'PASS')
        self.assertEqual(path.read_bytes(), before)

    def test_human_document_pass_keeps_file_binding_and_fail_reason_guards(self):
        mutations = (
            lambda check: check.update(evidence=[]),
            lambda check: check['evidence'][0].update(sha256='0' * 64),
            lambda check: check['evidence'][0].update(detail=None),
            lambda check: check.update(note=None),
            lambda check: check.update(status='FAIL'),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                path, value = self.confirmation()
                document = value['delivery_document_review']
                document['reviewer']['kind'] = 'human'
                check = document['checks']['source_and_compliance']
                check['note'] = ''
                check['evidence'][0]['detail'] = ''
                mutation(check)
                path.write_text(json.dumps(value))
                result = self.report(reviews=path)
                self.assertEqual(result['delivery_document_review']['status'], 'FAIL')

    def test_normal_steps_do_not_resolve_pending_semantic_check(self):
        path, value = self.confirmation()
        value['records'][0]['checks']['terminal_semantics'].update(
            status='REVIEW_REQUIRED', note='', evidence_steps=[])
        path.write_text(json.dumps(value))
        result = self.report(reviews=path)
        self.assertEqual(result['review_import']['accepted_count'], 1)
        self.assertEqual(result['local_sample_status'], 'REVIEW_REQUIRED')
        self.assertFalse(result['release_ready'])

    def test_previous_baseline_requires_explicit_migration_and_stays_unchanged(self):
        path, value = self.confirmation()
        value['records'][0]['baseline_sha256'] = '0' * 64
        path.write_text(json.dumps(value))
        before = path.read_bytes()
        self.assert_rejected(path)
        report = self.report()
        assessment = migration_template(path, report['samples'], report['baseline']['config_sha256'])
        for decision in assessment['decisions']:
            decision.update(decision='inherit_unchanged', reason='SYNTHETIC unchanged human click fixture.',
                authority_and_semantic_rule_assessment='SYNTHETIC input-format-only migration fixture, not actual visual approval.',
                assessor={'kind': 'ai', 'name': 'SYNTHETIC MIGRATION TEST ONLY'})
        migration = self.root / 'migration.json'
        migration.write_text(json.dumps(assessment))
        result = self.report(reviews=path, review_migration=migration)
        self.assertEqual(result['review_import']['accepted_count'], 1)
        self.assertFalse(result['review_import']['migrated_records'][0]['new_visual_review_claimed'])
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
