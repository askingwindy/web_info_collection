"""Admission receipts must also hold at the collector's direct task boundary."""
from copy import deepcopy
import unittest

import test_task_admission as admission_fixtures
from test_m4_task_contract import m4_task
from webcollect.task_contract import PLAN_SCHEMA, validate_m4_task
from webcollect.collect import validate_plan


class AdmissionContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = admission_fixtures.AdmissionTests(
            'test_unknown_task_can_be_admitted_only_with_bound_independent_complete_review')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_bound_task_remains_valid_with_only_collector_runtime_fields(self):
        task = self.fixture.admitted()
        self.assertIs(validate_m4_task(task), task)
        task.update(_plan_schema_version=PLAN_SCHEMA, require_public_origin=True)
        self.assertIs(validate_m4_task(task), task)

    def test_otherwise_valid_changed_input_cannot_reuse_admission(self):
        task = self.fixture.admitted()
        task['operations'][1]['arguments']['text'] = '999'
        with self.assertRaisesRegex(ValueError, 'proposal'):
            validate_m4_task(task)

    def test_declaring_receipt_fields_is_not_a_completed_review(self):
        task = deepcopy(self.fixture.task)
        task['task_admission'] = {'mode': 'real', 'QC_approval': False}
        with self.assertRaisesRegex(ValueError, 'malformed'):
            validate_m4_task(task)

    def test_unreviewed_task_cannot_opt_into_completion_view_scroll(self):
        task = m4_task()
        task['operations'][0]['completion_view'] = {'record': 'unreviewed'}
        with self.assertRaisesRegex(ValueError, 'independently reviewed'):
            validate_m4_task(task)

    def test_admission_cannot_downgrade_to_legacy_plan_validation(self):
        task = self.fixture.admitted()
        with self.assertRaisesRegex(ValueError, 'versioned M4'):
            validate_plan({'tasks': [task]})


if __name__ == '__main__':
    unittest.main()
