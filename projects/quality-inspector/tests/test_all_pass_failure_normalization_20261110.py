"""2026-11-10: an all-PASS review with an extra empty "no failure"
failure_assessment is normalized away; any non-PASS verdict keeps the strict
failure-locality rule. Pure in-memory validation, no provider IO.
"""
import unittest

from quality_inspector.ai_worker import validate_review


def _reply(check_status, failure):
    value = {'step_observations': [{'step_id': 1, 'note': '已逐帧查看'}],
             'checks': {'visual_alignment': {'status': check_status, 'note': '判断说明',
                                             'evidence_steps': [1]}}}
    if failure is not None:
        value['failure_assessment'] = failure
    return value


class AllPassFailureNormalizationTests(unittest.TestCase):
    def test_all_pass_with_empty_no_failure_field_is_normalized(self):
        value = _reply('PASS', {'scope': 'LOCAL', 'reason': '无失败', 'evidence_steps': []})
        validate_review(value, [1])
        self.assertNotIn('failure_assessment', value)

    def test_all_pass_without_field_unchanged(self):
        validate_review(_reply('PASS', None), [1])

    def test_non_pass_verdict_still_requires_failure_frames(self):
        value = _reply('REVIEW_REQUIRED', {'scope': 'UNKNOWN', 'reason': '无失败', 'evidence_steps': []})
        with self.assertRaisesRegex(ValueError, 'Failure locality'):
            validate_review(value, [1])

    def test_real_failure_with_bound_frames_still_accepted(self):
        value = _reply('FAIL', {'scope': 'LOCAL', 'reason': '末帧无结果', 'evidence_steps': [1]})
        validate_review(value, [1])
        self.assertIn('failure_assessment', value)


if __name__ == '__main__':
    unittest.main()
