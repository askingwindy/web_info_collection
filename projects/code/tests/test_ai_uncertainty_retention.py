"""Offline safety regressions: consolidation never weakens observed evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / 'projects/quality-inspector'),
                str(REPO / 'projects/quality-inspector/tests')]
from make_fixture import fixture
from quality_inspector.ai_worker import (do_difference, do_visual, segments,
                                         snapshot, synthetic_review, prepare, report, run)
from webcollect.batch_core import BatchLedger, load_json


class RecordingGateway:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, job, purpose, text, schema, *, images=(), **kwargs):
        self.calls.append({'purpose': purpose, 'text': json.loads(text),
                           'images': list(images)})
        return deepcopy(self.responses[purpose])


class Ledger:
    config = {'model': {'max_images': 6}}

    def heartbeat(self, job):
        pass


class UncertaintyRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.root = root
        self.focal = fixture(root / 'focal')
        self.neighbor = fixture(root / 'neighbor')
        self.steps = list(range(1, 7))
        annotation = self.neighbor / 'annotation.json'
        value = json.loads(annotation.read_text())
        value['sample_id'] = 'CONTROLLED_neighbor'
        annotation.write_text(json.dumps(value, ensure_ascii=False))
        self.job = {'payload': {'candidate': snapshot(self.focal),
                               'neighbors': [snapshot(self.neighbor)],
                               'comparison_version': 'CONTROLLED-only'}}

    def decision(self, status='PASS', note='Controlled distinct business flow'):
        return {'status': status, 'note': note, 'evidence_steps': self.steps}

    def difference(self, statuses=('PASS', 'PASS', 'PASS'), whole='PASS'):
        responses = {f'difference-0-part-{i}': self.decision(status)
                     for i, status in enumerate(statuses)}
        responses['difference-0-whole'] = self.decision(whole)
        gateway = RecordingGateway(responses)
        return do_difference(Ledger(), gateway, self.job), gateway

    def test_long_pair_unknown_segment_survives_whole_pass(self):
        result, _ = self.difference(('PASS', 'REVIEW_REQUIRED', 'PASS'))
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')

    def test_parameter_only_failure_survives_whole_pass(self):
        responses = {f'difference-0-part-{i}': self.decision()
                     for i in range(3)}
        responses['difference-0-part-1'] = self.decision(
            'FAIL', 'Controlled same business with keyword/parameter-only changes')
        responses['difference-0-whole'] = self.decision()
        result = do_difference(Ledger(), RecordingGateway(responses), self.job)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('parameter-only', result['note'])

    def test_whole_failure_has_priority_over_segment_uncertainty(self):
        result, _ = self.difference(('PASS', 'REVIEW_REQUIRED', 'PASS'), 'FAIL')
        self.assertEqual(result['status'], 'FAIL')

    def test_whole_uncertainty_survives_all_part_passes(self):
        result, _ = self.difference(whole='REVIEW_REQUIRED')
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')

    def test_distinct_positive_pair_passes_with_every_original_frame(self):
        result, gateway = self.difference()
        self.assertEqual(result['status'], 'PASS')
        actual = {str(path.resolve()) for call in gateway.calls for path in call['images']}
        expected = {str(path.resolve()) for root in (self.focal, self.neighbor)
                    for path in (root / 'images').glob('*.png')}
        self.assertEqual(actual, expected)
        self.assertEqual(len(gateway.calls), 4)

    def test_blank_duplicate_or_unbound_whole_evidence_cannot_pass(self):
        for bad in ({'note': '  '}, {'evidence_steps': []},
                    {'evidence_steps': [1, 1]}, {'evidence_steps': [99]}):
            with self.subTest(bad=bad):
                responses = {f'difference-0-part-{i}': self.decision()
                             for i in range(3)}
                responses['difference-0-whole'] = {**self.decision(), **bad}
                with self.assertRaises(ValueError):
                    do_difference(Ledger(), RecordingGateway(responses), self.job)

    def test_blank_or_repeated_segment_evidence_cannot_pass(self):
        for bad in ({'note': '  '}, {'evidence_steps': [1, 1]}):
            with self.subTest(bad=bad):
                responses = {f'difference-0-part-{i}': self.decision()
                             for i in range(3)}
                responses['difference-0-part-1'].update(bad)
                responses['difference-0-whole'] = self.decision()
                with self.assertRaises(ValueError):
                    do_difference(Ledger(), RecordingGateway(responses), self.job)

    def test_visual_whole_failure_is_not_downgraded_by_segment_uncertainty(self):
        ledger = Ledger()
        ledger.config = {'model': {'max_images': 3}}
        groups = segments(self.steps, 3)
        responses = {f'visual-part-{i}': synthetic_review(group)
                     for i, group in enumerate(groups)}
        for response in responses.values():
            response['checks']['visual_alignment']['status'] = 'PASS'
        responses['visual-part-1']['checks']['visual_alignment']['status'] = 'REVIEW_REQUIRED'
        responses['visual-whole-continuity'] = synthetic_review(self.steps)
        responses['visual-whole-continuity']['checks']['visual_alignment']['status'] = 'FAIL'
        result = do_visual(ledger, RecordingGateway(responses), self.job)
        self.assertEqual(result['checks']['visual_alignment']['status'], 'FAIL')

    def test_legacy_worker_jobs_remain_pending_without_dispatch(self):
        config = load_json(REPO / 'projects/code/config/batch-synthetic.json')
        ledger = BatchLedger(self.root / 'ops.sqlite3', config, initialize=True)
        ledger.enqueue('ai-difference', {**self.job['payload'],
                       'policy_version': 'batch-review-worker-1',
                       'prompt_version': 'independent-all-frame-review-1'})
        result = run(ledger)
        self.assertEqual(result['outcomes'][0]['state'], 'review_required')
        self.assertEqual(result['cost']['model_requests'], 0)


if __name__ == '__main__':
    unittest.main()
