"""Actual hash/error fixtures and strict decisions; zero real model/site calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from PIL import Image
from test_s0_sampling import multi_fixture, controlled_reviews
from quality_inspector.duplicates import (analyze_inputs, dhash, distance, indexed_routes,
    simhash, summarize)
from quality_inspector.delivery_sampling import freeze, evaluate
from quality_inspector.engine import inspect


class FourRouteResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = multi_fixture(self.root / 'CONTROLLED-fixture', count=2)
        self.paths = sorted(self.dataset.glob('samples/*/annotation.json'))
        self.assertEqual(len(self.paths), 2)

    def annotations(self):
        return [json.loads(path.read_text()) for path in self.paths]

    def save(self, index, value):
        self.paths[index].write_text(json.dumps(value, ensure_ascii=False))

    def result(self):
        return analyze_inputs(self.paths, verify_exhaustive=True)

    def gradient(self, path, offset=0, reverse=False, size=(9, 8)):
        # Already 9x8, so the golden dHash has no resampling ambiguity.
        width, height = size
        values = [int((width-1-x if reverse else x)*160/(width-1)) + offset
                  for y in range(height) for x in range(width)]
        image = Image.new('L', size); image.putdata(values); image.save(path)

    def force_route(self, route):
        annotations = self.annotations()
        if route == 'route1':
            shutil.copyfile(self.paths[0].parent / annotations[0]['steps'][2]['image_path'],
                            self.paths[1].parent / annotations[1]['steps'][2]['image_path'])
        elif route == 'route2':
            for first, second in zip(annotations[0]['steps'], annotations[1]['steps']):
                second['action']['action_type'] = first['action']['action_type']
                second['action']['target_text'] = first['action']['target_text']
                second['page_name'] = first['page_name']
            self.save(1, annotations[1])
        elif route == 'route3':
            # Four distinct PNG byte streams, all monotonic horizontal gradients.
            # Each endpoint therefore has dHash zero without any exact SHA reuse.
            for index, annotation in enumerate(annotations):
                for endpoint, step in enumerate((annotation['steps'][0], annotation['steps'][-1])):
                    self.gradient(self.paths[index].parent / step['image_path'], 10*index + endpoint,
                                  size=tuple(annotation['device_info']['screen_resolution']))
        elif route == 'route4':
            annotations[1]['task_instruction'] = annotations[0]['task_instruction']; self.save(1, annotations[1])

    def test_dhash_golden_bit_order_and_hamming_threshold(self):
        up, down = self.root / 'up.png', self.root / 'down.png'
        self.gradient(up); self.gradient(down, reverse=True)
        self.assertEqual(dhash(up), 0)
        self.assertEqual(dhash(down), 2**64 - 1)
        image = Image.new('L', (9, 8)); image.putpixel((0, 0), 255)
        one = self.root / 'first-bit.png'; image.save(one)
        self.assertEqual(dhash(one), 1 << 63)
        rows = [dict(sequence=[i], first_dhash=value, last_dhash=last, instruction_simhash=i << 30)
                for i, value, last in ((0, 0, 0), (1, 15, 15), (2, 31, 15), (3, 15, 31))]
        routes, _ = indexed_routes(rows)
        self.assertIn((0, 1), routes['route3'])
        self.assertNotIn((0, 2), routes['route3'])
        self.assertNotIn((0, 3), routes['route3'])
        self.assertEqual(distance(0, 15), 4)

    def test_simhash_golden_tokens_lowercase_tf_and_tie(self):
        word = lambda value: int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], 'big')
        self.assertEqual(simhash('中'), word('中'))
        self.assertEqual(simhash('ABAB abab'), word('abab'))
        self.assertEqual(simhash('中文 A1'), word('中文') & word('a1'))
        # 中文 appears twice; its weight dominates the one 文中 token.
        self.assertEqual(simhash('中文中文'), word('中文'))
        rows = [dict(sequence=[i], first_dhash=i*1111, last_dhash=i*3333, instruction_simhash=value)
                for i, value in enumerate((0, 7, 15))]
        routes, _ = indexed_routes(rows)
        self.assertIn((0, 1), routes['route4'])
        self.assertNotIn((0, 2), routes['route4'])

    def test_different_actual_samples_have_measured_zero_and_no_pending_pairs(self):
        result = self.result(); summary = result['summary']
        self.assertEqual(summary['current_union_pair_count'], 0)
        self.assertEqual(summary['near_duplicate_sample_rate'], 0)
        self.assertEqual(summary['unadjudicated_pair_count'], 0)
        self.assertEqual(summary['strict_zero_hit_gate'], 'PASS')
        self.assertEqual(result['search']['exhaustive_verification']['status'], 'PASS')

    def test_each_actual_route_hit_is_resolved_duplicate_without_semantic_exemption(self):
        for route in ('route1', 'route2', 'route3', 'route4'):
            with self.subTest(route=route):
                # Independent fresh temporary fixture for each single route.
                dataset = multi_fixture(self.root / route, count=2)
                previous = self.paths; self.paths = sorted(dataset.glob('samples/*/annotation.json'))
                try:
                    self.force_route(route); result = self.result(); summary = result['summary']
                    self.assertEqual(summary['current_union_pair_count'], 1)
                    self.assertEqual(summary['near_duplicate_sample_rate'], 1)
                    self.assertEqual(summary['near_duplicate_pair_rate'], 1)
                    self.assertEqual(summary['unadjudicated_pair_count'], 0)
                    self.assertEqual(summary['strict_zero_hit_gate'], 'FAIL')
                    self.assertIn(route, summary['pair_adjudications'][0]['matched_routes'])
                    self.assertFalse(summary['pair_adjudications'][0]['semantic_exemption_allowed'])
                finally:
                    self.paths = previous

    def test_one_pair_matching_all_routes_is_union_counted_once(self):
        annotations = self.annotations()
        for first, second in zip(annotations[0]['steps'], annotations[1]['steps']):
            second['page_name'] = first['page_name']
            second['action'] = deepcopy(first['action'])
            shutil.copyfile(self.paths[0].parent / first['image_path'], self.paths[1].parent / second['image_path'])
        annotations[1]['task_instruction'] = annotations[0]['task_instruction']; self.save(1, annotations[1])
        result = self.result(); summary = result['summary']
        self.assertEqual(summary['route_pair_counts'], {route: 1 for route in ('route1', 'route2', 'route3', 'route4')})
        self.assertEqual(summary['all_inspected_union_pair_count'], 1)
        self.assertEqual(len(summary['pair_adjudications'][0]['matched_routes']), 4)

    def test_current_rate_never_uses_224_history_samples_as_denominator(self):
        current = {'new-a', 'new-b'}; history = ['history-' + str(i) for i in range(224)]
        rows = [{'sample_id': sid} for sid in sorted(current) + history]
        pairs = [{'sample_ids': ['new-a', history[0]]}, {'sample_ids': [history[1], history[2]]}]
        value = {'rows': rows, 'route1': {'confirmed_pair_count': 0, 'pairs': []},
                 'route2': {'count': 0, 'confirmed_pairs': []}, 'route3': {'count': 2, 'candidates': pairs},
                 'route4': {'count': 1, 'candidates': pairs[:1]}}
        summary = summarize(value, current)
        self.assertEqual(summary['current_sample_count'], 2)
        self.assertEqual(summary['history_sample_count'], 224)
        self.assertEqual(summary['current_union_pair_count'], 1)
        self.assertEqual(summary['historical_only_union_pair_count'], 1)
        self.assertEqual(summary['near_duplicate_sample_rate'], .5)
        self.assertEqual(summary['near_duplicate_pair_rate'], 1/449)
        self.assertEqual(summary['affected_current_sample_ids'], ['new-a'])
        self.assertFalse(summary['sample_rate_within_requested_limit'])
        value['route3']['candidates'] = pairs[1:]; value['route3']['count'] = 1
        value['route4']['candidates'] = []; value['route4']['count'] = 0
        historical_only = summarize(value, current)
        self.assertEqual(historical_only['near_duplicate_sample_rate'], 0)
        self.assertEqual(historical_only['strict_zero_hit_gate'], 'PASS')
        self.assertEqual(historical_only['historical_only_union_pair_count'], 1)

    def test_all_ai_semantic_passes_cannot_override_actual_dhash_hit(self):
        self.force_route('route3')
        plan = self.root / 'sampling.json'; freeze(self.dataset, plan, ai_percent=100, human_percent=0, seed='CONTROLLED')
        reviews = self.root / 'CONTROLLED-ai-pass.json'; controlled_reviews(self.dataset, reviews)
        sampling, _ = evaluate(plan, self.dataset, ai_reviews=[reviews])
        self.assertEqual(sampling['status'], 'PASS')
        report = inspect(None, self.dataset, inspection_stage='payload', delivery_sampling_plan=plan, reviews=reviews)
        for sample in report['samples']:
            self.assertEqual(next(check for check in sample['checks'] if check['rule_id']=='REVIEW_SUBSTANTIVE_DIFFERENCE')['status'], 'PASS')
            self.assertEqual(next(check for check in sample['checks'] if check['rule_id']=='NEAR_DUPLICATES' and check['route']=='route3')['status'], 'FAIL')
            self.assertEqual(sample['status'], 'FAIL')
        self.assertFalse(report['release_ready'])

    def test_actual_unreadable_png_has_unknown_counts_and_cannot_release(self):
        annotation = self.annotations()[0]
        (self.paths[0].parent / annotation['steps'][0]['image_path']).write_bytes(b'CONTROLLED invalid PNG')
        report = inspect(None, self.dataset, inspection_stage='payload')
        duplicate = report['duplicates']; summary = duplicate['summary']
        self.assertIn('error', duplicate)
        self.assertIsNone(duplicate['route1']['confirmed_pair_count'])
        self.assertIsNone(duplicate['route3']['count'])
        self.assertIsNone(summary['unadjudicated_pair_count'])
        self.assertIsNone(summary['near_duplicate_sample_rate'])
        self.assertEqual(summary['analysis_status'], 'FAILED')
        self.assertEqual(summary['strict_zero_hit_gate'], 'PENDING')
        self.assertFalse(report['release_ready'])


if __name__ == '__main__':
    unittest.main()
