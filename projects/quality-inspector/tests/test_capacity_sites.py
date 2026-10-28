"""Capacity-based website counts; independent controlled delivery fixtures."""
import json
import unittest

import test_delivery
from quality_inspector.profiles import load
from quality_inspector.cumulative import build_set_manifest, inspect_set


class CapacitySiteTests(unittest.TestCase):
    setUp = test_delivery.DeliveryContractTests.setUp
    tearDown = test_delivery.DeliveryContractTests.tearDown
    seal = test_delivery.DeliveryContractTests.seal

    def check(self):
        return inspect_set(build_set_manifest([self.client]), self.profile)

    def test_null_site_count_keeps_actual_count_and_passes_mechanical_scope_only(self):
        value = json.loads(self.profile.read_text()); value['targets']['expected_sites'] = None
        self.profile.write_text(json.dumps(value))
        self.assertIsNone(load(self.profile)['configuration']['targets']['expected_sites'])
        result = self.check()
        self.assertEqual(result['site_count'], 1)
        self.assertEqual(result['mechanical_status'], 'PASS')
        self.assertFalse(result['release_ready'])
        self.assertEqual(result['semantic_review_status'], 'NOT_EVALUATED')

    def test_nonnull_count_still_enforces_exact_actual_sites(self):
        value = json.loads(self.profile.read_text())
        for count, expected in ((1, 'PASS'), (2, 'FAIL')):
            value['targets']['expected_sites'] = count
            self.profile.write_text(json.dumps(value))
            result = self.check()
            self.assertEqual(result['mechanical_status'], expected)
            self.assertEqual(any('Expected 2 sites' in row['reason'] for row in result['errors']), count == 2)

    def test_invalid_nonnull_values_are_rejected(self):
        value = json.loads(self.profile.read_text())
        for invalid in (0, -1, True, False, 1.0, '1', [], {}):
            with self.subTest(invalid=invalid):
                value['targets']['expected_sites'] = invalid
                self.profile.write_text(json.dumps(value))
                with self.assertRaises(ValueError): load(self.profile)

    def test_null_does_not_waive_samples_or_category_share(self):
        value = json.loads(self.profile.read_text())
        value['targets'].update(expected_sites=None, expected_samples=2, category_share='enforced')
        self.profile.write_text(json.dumps(value))
        result = self.check()
        self.assertEqual(result['mechanical_status'], 'FAIL')
        reasons = [row['reason'] for row in result['errors']]
        self.assertTrue(any('Expected 2 samples' in reason for reason in reasons))
        self.assertTrue(any('category share' in reason for reason in reasons))


if __name__ == '__main__': unittest.main()
