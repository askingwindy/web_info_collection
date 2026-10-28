"""Recent real history identities and controlled corruptions; no network/model."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from webcollect.batch_core import BatchLedger, load_json
from webcollect.history_business import annotation_business_strategy, classification_evidence
from webcollect.task_generation import (customer_history_decision, generate,
    generation_source_identity, read_customer_history)

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'verify_results/production-day-20261027'
OLD220 = ROOT / 'verify_results/three-program-acceleration-20261026/history-r01/history-set-old220.json'
CURRENT223 = BASE / 'qr-effective-set-r01.json'
FIXTURES = {
    'loan': (ROOT / 'results/m4-1000-20261025/day20261027-loan-r01/candidate-narrative-r01/samples/S000027_sample_000001',
             'mortgage-equal-payment-v1', 'c4c9f155c510f324c3b908d79067d49344b81ae02dc121004a65c90133762234'),
    'wifi': (ROOT / 'results/m4-1000-20261025/day20261027-qr-r01/candidate/samples/S000029_sample_000001',
             'wifi-qr-generation-v1', '4877b6711ce5c3912e4e2da85af16449f224286c6d18e3ef8e982ece3d6ae60b'),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RecentHistoryIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.old_scope = read_customer_history(OLD220)
        cls.current, cls.current_scope = read_customer_history(CURRENT223)

    def fixture(self, name):
        root, expected, checksum = FIXTURES[name]
        self.assertEqual(digest(root / 'annotation.json'), checksum)
        return load_json(root / 'annotation.json'), root, expected

    def copied(self, name):
        annotation, source, expected = self.fixture(name)
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / 'copy'
        shutil.copytree(source / 'ui_tree', root / 'ui_tree')
        return annotation, root, expected

    def tree(self, root, step, change):
        path = root / step['ui_tree_path']; value = load_json(path)
        change(value, step)
        path.write_text(json.dumps(value, ensure_ascii=False))

    def test_real_complete_loan_and_wifi_have_strict_identity_and_every_tree_binding(self):
        for name in FIXTURES:
            a, root, expected = self.fixture(name)
            result = classification_evidence(a, root)
            self.assertEqual(result['strategy_id'], expected)
            self.assertEqual(result['verified_target_tree_files'], [s['ui_tree_path'] for s in a['steps']])
            self.assertIn('not a quality', result['scope'])

    def test_old220_remains_42_known_and_178_unknown(self):
        self.assertEqual(len(self.old), 220)
        self.assertEqual(self.old_scope['known_strategy_samples'], 42)
        self.assertEqual(self.old_scope['unknown_strategy_samples'], 178)

    def test_real223_adds_two_known_without_relabelling_other_history(self):
        self.assertEqual(len(self.current), 223)
        self.assertEqual(self.current_scope['known_strategy_samples'], 44)
        self.assertEqual(self.current_scope['unknown_strategy_samples'], 179)
        old = {r['sample_id']: r['strategy_id'] for r in self.old}
        self.assertEqual({r['sample_id']: r['strategy_id'] for r in self.current if r['sample_id'] in old}, old)
        for name in FIXTURES:
            root, expected, _ = FIXTURES[name]
            row = next(r for r in self.current if r['sample_id'] == root.name)
            self.assertEqual(row['strategy_id'], expected)

    def test_same_business_rejected_globally_with_parameter_path_and_origin_variants(self):
        for _, strategy, _ in FIXTURES.values():
            task = {'site_uri': 'https://a-new-origin.example/other?amount=99',
                    'deterministic_strategy': {'id': strategy},
                    'operations': [{'action_type': 'type', 'input_text': '999'}]}
            self.assertEqual(customer_history_decision(task, self.current)['status'], 'REJECTED')

    def test_placeholder_clears_only_identified_same_origin_history(self):
        task = {'site_uri': 'https://www.jyshare.com/front-end/9355/',
                'deterministic_strategy': {'id': 'placeholder-image-generation-v1'}}
        self.assertIsNone(customer_history_decision(task, self.current))
        rows = deepcopy(self.current)
        row = next(r for r in rows if r['strategy_id'] == 'wifi-qr-generation-v1')
        row['strategy_id'] = row['semantic_signature'] = None
        decision = customer_history_decision(task, rows)
        self.assertEqual(decision['status'], 'REVIEW_REQUIRED')
        self.assertEqual(decision['history_sample_ids'], [row['sample_id']])

    def test_current223_can_generate_placeholder_offline_with_new_source_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); config = load_json(BASE / 'placeholder-production-r02/config.json')
            # This positive admission scenario has no newer M4 tasks. Production
            # may already contain the business and must continue rejecting it.
            registry = root / 'CONTROLLED-history-registry.sqlite3'
            with sqlite3.connect(registry) as con:
                con.execute('CREATE TABLE m4_tasks (scope_id TEXT, task_json TEXT NOT NULL)')
            before = digest(registry)
            config['run_id'] = 'CONTROLLED-recent-history-admission-no-dispatch'
            ledger = BatchLedger(root / 'CONTROLLED-operations.sqlite3', config, initialize=True)
            result = generate(ledger, BASE / 'placeholder-capability-reviewed-r01/catalog-reviewed.json',
                root / 'generated', history_registry=registry, history_set=CURRENT223)
            self.assertEqual(result['generated_tasks'], 1)
            plan = load_json(result['plan_file'])
            self.assertEqual(plan['generation']['history_scope']['customer_samples'], 223)
            self.assertEqual(plan['generation']['source_identity'], generation_source_identity())
            self.assertEqual(plan['tasks'][0]['deterministic_strategy']['id'], 'placeholder-image-generation-v1')
            self.assertEqual(ledger.summary()['model_requests'], 0)
            self.assertEqual(digest(registry), before)

    def test_ids_prose_and_input_parameters_do_not_determine_identity(self):
        for name in FIXTURES:
            a, root, expected = self.fixture(name)
            a.update(sample_id='unrelated-id', task_instruction='unrelated prose', final_result='unrelated result',
                     completion_judgement='unrelated judgment')
            for step in a['steps']:
                if step['action']['action_type'] == 'type':
                    step['action']['input_text'] = '参数变化'
                    step['tool_call']['arguments']['text'] = '参数变化'
            self.assertEqual(annotation_business_strategy(a, root), expected)

    def test_missing_extra_or_reordered_actions_remain_unknown(self):
        for name in FIXTURES:
            for change in ('missing', 'extra', 'reordered'):
                a, root, _ = self.fixture(name)
                if change == 'missing': a['steps'].pop(1)
                elif change == 'extra': a['steps'].insert(1, deepcopy(a['steps'][0]))
                else: a['steps'][0], a['steps'][1] = a['steps'][1], a['steps'][0]
                for i, step in enumerate(a['steps'], 1): step['step_id'] = i
                self.assertIsNone(annotation_business_strategy(a, root), (name, change))

    def test_failure_exception_incomplete_and_failed_complete_remain_unknown(self):
        for name in FIXTURES:
            for change in ('error', 'exception', 'incomplete', 'complete_args', 'tool_action'):
                a, root, _ = self.fixture(name)
                if change == 'error': a['steps'][0]['tool_result']['status'] = 'error'
                elif change == 'exception': a['steps'][0]['exception_evidence'] = {'recorded': True}
                elif change == 'incomplete': a['completion_status'] = 'failed'
                elif change == 'complete_args': a['steps'][-1]['tool_call']['arguments']['status'] = 'failed'
                else: a['steps'][0]['tool_call']['tool_name'] = 'type'
                self.assertIsNone(annotation_business_strategy(a, root), (name, change))

    def test_page_title_application_and_actual_tool_context_must_match(self):
        for name in FIXTURES:
            for change in ('page', 'app', 'tool'):
                a, root, _ = self.fixture(name)
                if change == 'page': a['steps'][0]['page_name'] = '网页「其他工具」'
                elif change == 'app': a['app_info']['app_name'] = '其他工具'
                else: a['steps'][0]['tool_call']['context'] = 'Web / 其他工具'
                self.assertIsNone(annotation_business_strategy(a, root), (name, change))

    def test_heading_is_required_unique_and_bound_even_in_terminal_frame(self):
        for name in FIXTURES:
            for mode in ('missing', 'duplicate', 'different'):
                a, root, _ = self.copied(name)
                def change(tree, step):
                    title = '房贷计算器' if name == 'loan' else '在线二维码生成器'
                    heading = next(e for e in tree['elements'] if e.get('text') == title)
                    if mode == 'missing': tree['elements'].remove(heading)
                    elif mode == 'duplicate':
                        other = deepcopy(heading); other['element_id'] += '-duplicate'; tree['elements'].append(other)
                    else: heading['text'] = '其他工具'
                self.tree(root, a['steps'][-1], change)
                self.assertIsNone(annotation_business_strategy(a, root), (name, mode))

    def test_targets_require_original_native_roles_and_exact_tree_bbox(self):
        for name in FIXTURES:
            for mode in ('native_role', 'bbox', 'visible', 'enabled', 'inputable'):
                a, root, _ = self.copied(name)
                step = next(s for s in a['steps'] if s['action']['action_type'] == 'type')
                def change(tree, current):
                    e = next(e for e in tree['elements'] if e['element_id'] == current['action']['target_element_id'])
                    e[mode] = {'native_role': 'textarea', 'bbox': [0, 0, 1, 1],
                               'visible': False, 'enabled': False, 'inputable': False}[mode]
                self.tree(root, step, change)
                self.assertIsNone(annotation_business_strategy(a, root), (name, mode))

    def test_same_label_duplicate_control_is_ambiguous(self):
        for name in FIXTURES:
            a, root, _ = self.copied(name)
            step = next(s for s in a['steps'] if s['action']['action_type'] == 'type')
            def change(tree, current):
                e = deepcopy(next(e for e in tree['elements'] if e['element_id'] == current['action']['target_element_id']))
                e['element_id'] += '-another'; tree['elements'].append(e)
            self.tree(root, step, change)
            self.assertIsNone(annotation_business_strategy(a, root))

    def test_control_parent_topology_cannot_be_rewritten(self):
        for name in FIXTURES:
            a, root, _ = self.copied(name)
            step = a['steps'][0]
            def change(tree, current):
                e = next(e for e in tree['elements'] if e['element_id'] == current['action']['target_element_id'])
                e['parent_id'] = 'root' if name == 'wifi' else 'missing-parent'
            self.tree(root, step, change)
            self.assertIsNone(annotation_business_strategy(a, root))

    def test_two_input_roles_cannot_share_target_identity(self):
        for name in FIXTURES:
            a, root, _ = self.fixture(name)
            first = next(s['action']['target_element_id'] for s in a['steps'] if s['action']['action_type'] == 'type')
            other = [s for s in a['steps'] if s['action']['action_type'] == 'type'][-1]
            other['action']['target_element_id'] = first
            self.assertIsNone(annotation_business_strategy(a, root))

    def test_wrong_shortcut_and_click_coordinates_are_not_successful_evidence(self):
        a, root, _ = self.fixture('loan')
        a['steps'][1]['tool_call']['arguments']['keys'] = ['ctrl', 'x']
        self.assertIsNone(annotation_business_strategy(a, root))
        for name in FIXTURES:
            for mode in ('call', 'outside'):
                a, root, _ = self.fixture(name); step = a['steps'][0]
                if mode == 'call': step['tool_call']['arguments']['x'] = 0
                else:
                    step['action']['coordinate'] = [0, 0]
                    step['tool_call']['arguments'] = {'x': 0, 'y': 0}
                self.assertIsNone(annotation_business_strategy(a, root), (name, mode))

    def test_every_frame_tree_must_bind_image_and_geometry(self):
        for name in FIXTURES:
            for mode in ('image_path', 'screen_resolution', 'missing'):
                a, root, _ = self.copied(name); step = a['steps'][-1]
                if mode == 'missing': (root / step['ui_tree_path']).unlink()
                else:
                    self.tree(root, step, lambda tree, _: tree.update({mode: 'another.png' if mode == 'image_path' else [1, 1]}))
                self.assertIsNone(annotation_business_strategy(a, root), (name, mode))

    def test_missing_original_tree_or_escaping_path_cannot_be_replaced_by_prose(self):
        for name in FIXTURES:
            a, root, _ = self.fixture(name)
            self.assertIsNone(annotation_business_strategy(a))
            a['steps'][-1]['ui_tree_path'] = '../outside.json'
            self.assertIsNone(annotation_business_strategy(a, root))

    def test_text_url_qr_with_wifi_payload_is_not_wifi_form_business(self):
        a, root, _ = self.fixture('wifi')
        a['steps'][0]['action']['target_text'] = '文本 / 网址'
        a['task_instruction'] = a['final_result'] = 'WIFI:T:WPA;S:example;P:test;;'
        self.assertIsNone(annotation_business_strategy(a, root))


if __name__ == '__main__':
    unittest.main()
