"""Controlled qualification rules; no network or external model calls."""
import unittest
from site_planner.qualification import CHECKS, qualification_status


class SiteQualificationRules(unittest.TestCase):
    def decision(self):
        return {'category': '在线工具', 'checks': {name: {'status': 'PASS', 'observation': '受控证据'} for name in CHECKS}}

    def test_ready_does_not_override_low_initial_language(self):
        self.assertEqual(qualification_status(self.decision(), [.69, .95]), 'rejected')

    def test_full_pass_requires_all_checks(self):
        decision = self.decision()
        self.assertEqual(qualification_status(decision, [.70]), 'ready')
        del decision['checks']['compliance']
        self.assertEqual(qualification_status(decision, [.95]), 'review_required')

    def test_navigation_and_access_failures_are_not_approved(self):
        for name in ('chinese_navigation_controls', 'access', 'category', 'compliance'):
            decision = self.decision(); decision['checks'][name]['status'] = 'FAIL'
            self.assertEqual(qualification_status(decision, [.95]), 'rejected')

    def test_unresolved_preflight_cannot_be_overridden_by_model(self):
        self.assertEqual(qualification_status(self.decision(), [.95], preflight_blocked=True), 'review_required')

    def test_missing_and_invalid_observation_fail_closed(self):
        for ratios in ([], [True], [-1], [1.1], ['.8']):
            with self.assertRaises(ValueError):
                qualification_status(self.decision(), ratios)


if __name__ == '__main__':
    unittest.main()
