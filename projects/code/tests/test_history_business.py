"""Real frozen-history identity checks plus controlled evidence corruptions."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from webcollect.history_business import annotation_business_strategy, classification_evidence

ROOT = Path(__file__).resolve().parents[3]
HANDOFF = ROOT / 'verify_results/production-day-20261027/history-business-r01/analysis-handoff.json'


class HistoryBusinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = json.loads(HANDOFF.read_text())
        cls.histories = {h['sample_id']: h for h in cls.handoff['tool_histories']}

    def fixture(self, sid='S000020_sample_000009'):
        h = self.histories[sid]; path = Path(h['annotation'])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), h['annotation_sha256'])
        return json.loads(path.read_text()), path.parent

    def test_all_42_observed_tool_histories_have_evidence_identity(self):
        for sid in self.histories:
            with self.subTest(sid=sid):
                a, root = self.fixture(sid)
                self.assertIsNotNone(classification_evidence(a, root))

    def test_unobserved_178_remain_unknown(self):
        unknown = [h for h in self.handoff['all_history_inputs'] if h['sample_id'] not in self.histories]
        self.assertEqual(len(unknown), 178)
        for h in unknown:
            path = Path(h['annotation'])
            self.assertIsNone(annotation_business_strategy(json.loads(path.read_text()), path.parent))

    def test_all_actions_must_succeed_not_just_matching_subset(self):
        a, root = self.fixture()
        a['steps'][0]['tool_result']['status'] = 'error'
        self.assertIsNone(annotation_business_strategy(a, root))

    def test_tool_action_mismatch_is_unknown(self):
        a, root = self.fixture()
        a['steps'][1]['tool_call']['tool_name'] = 'click'
        self.assertIsNone(annotation_business_strategy(a, root))

    def test_missing_or_extra_action_is_unknown(self):
        for mode in ('missing', 'extra'):
            a, root = self.fixture()
            if mode == 'missing':
                a['steps'].pop(0)
            else:
                a['steps'].insert(0, copy.deepcopy(a['steps'][0]))
            for i, s in enumerate(a['steps'], 1):
                s['step_id'] = i
            self.assertIsNone(annotation_business_strategy(a, root))

    def test_incomplete_and_failed_completion_are_unknown(self):
        for change in ('no_complete', 'failed_status'):
            a, root = self.fixture()
            if change == 'no_complete':
                a['steps'].pop()
            else:
                a['completion_status'] = 'failed'
            self.assertIsNone(annotation_business_strategy(a, root))

    def test_prose_does_not_determine_business(self):
        a, root = self.fixture()
        a['task_instruction'] = '日期差计算 BMI 秒表 ASCII艺术字'
        a['final_result'] = '日期偏移成功'
        self.assertEqual(annotation_business_strategy(a, root), 'logarithm-v1')
        for step in a['steps']:
            step['page_name'] = '网页「日期差计算器」'
        self.assertIsNone(annotation_business_strategy(a, root))

    def test_role_changed_even_with_same_label_is_unknown(self):
        a, root = self.fixture()
        a['steps'][0]['action']['target_control_type'] = 'button'
        self.assertIsNone(annotation_business_strategy(a, root))

    def test_target_identity_topology_changed_is_unknown(self):
        a, root = self.fixture()
        for s in a['steps'][2:4]:
            s['action']['target_element_id'] = a['steps'][0]['action']['target_element_id']
        self.assertIsNone(annotation_business_strategy(a, root))

    def test_parameter_variant_has_same_identity(self):
        a, root = self.fixture()
        for s in a['steps']:
            if s['action']['action_type'] == 'type':
                s['action']['input_text'] = '64'
                s['tool_call']['arguments']['text'] = '64'
        self.assertEqual(annotation_business_strategy(a, root), 'logarithm-v1')

    def test_empty_input_and_unbound_tool_text_are_unknown(self):
        for text in ('', 'different-from-tool'):
            a, root = self.fixture()
            a['steps'][1]['action']['input_text'] = text
            self.assertIsNone(annotation_business_strategy(a, root))

    def test_tree_proof_required(self):
        a, root = self.fixture()
        self.assertIsNone(annotation_business_strategy(a))
        a['steps'][0]['ui_tree_path'] = '../outside.json'
        self.assertIsNone(annotation_business_strategy(a, root))

    def test_anonymous_formula_context_cannot_be_relabelled(self):
        a, source = self.fixture()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for s in a['steps']:
                if not s['action'].get('target_element_id'):
                    continue
                p = root / s['ui_tree_path']; p.parent.mkdir(exist_ok=True)
                tree = json.loads((source / s['ui_tree_path']).read_text())
                for e in tree['elements']:
                    if e.get('text') == 'log':
                        e['text'] = 'date'
                p.write_text(json.dumps(tree))
            self.assertIsNone(annotation_business_strategy(a, root))

    def test_tree_bbox_or_editability_mismatch_is_unknown(self):
        for mode in ('bbox', 'inputable'):
            a, source = self.fixture()
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                for s in a['steps']:
                    if not s['action'].get('target_element_id'):
                        continue
                    p = root / s['ui_tree_path']; p.parent.mkdir(exist_ok=True)
                    tree = json.loads((source / s['ui_tree_path']).read_text())
                    if s['action']['action_type'] == 'type':
                        e = next(e for e in tree['elements'] if e['element_id'] == s['action']['target_element_id'])
                        e[mode] = [0, 0, 1, 1] if mode == 'bbox' else False
                    p.write_text(json.dumps(tree))
                self.assertIsNone(annotation_business_strategy(a, root))

    def test_cross_site_unit_and_radix_variants_share_business_id(self):
        for pair, expected in ((('S000002_sample_000043', 'S000020_sample_000037'), 'unit-conversion-v1'),
                               (('S000002_sample_000034', 'S000020_sample_000028'), 'radix-conversion-v1')):
            values = [annotation_business_strategy(*self.fixture(sid)) for sid in pair]
            self.assertEqual(values, [expected, expected])

    def test_ascii_lookup_is_not_art_and_time_unit_is_not_date_difference(self):
        for sid, expected in (('S000002_sample_000037', 'ascii-code-lookup-v1'),
                              ('S000002_sample_000049', 'unit-conversion-v1'),
                              ('S000002_sample_000054', 'timestamp-conversion-v1')):
            self.assertEqual(annotation_business_strategy(*self.fixture(sid)), expected)


if __name__ == '__main__':
    unittest.main()
