"""Strict history integration and source-drift dispatch guards; no real network."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from webcollect.batch_core import BatchLedger, load_json, save_json
from webcollect.task_generation import (annotation_business_strategy, customer_history_decision,
    generation_source_identity, generate, execute, read_customer_history, semantic_signature)
from test_s0_task_generation import capability, catalog, config

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / 'verify_results/three-program-acceleration-20261026/history-r01/history-set-old220.json'


class HistoryBusinessIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.scope = read_customer_history(MANIFEST)

    def test_actual_frozen220_strict_tree_path_is_used(self):
        self.assertEqual(len(self.records), 220)
        self.assertEqual(self.scope['known_strategy_samples'], 42)
        self.assertEqual(self.scope['unknown_strategy_samples'], 178)
        lddgo = [r for r in self.records if r['origin'] == 'https://www.lddgo.net']
        self.assertEqual(len(lddgo), 22)
        self.assertTrue(all(r['strategy_id'] for r in lddgo))
        self.assertIn('target UI trees', self.scope['parsed_content'])

    def test_real_delegate_cannot_fallback_to_legacy_without_original_tree(self):
        row = next(r for r in self.records if r['strategy_id'] == 'body-mass-index-v1')
        path = Path(row['annotation_path']); a = load_json(path)
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(annotation_business_strategy(a, d))
        self.assertEqual(annotation_business_strategy(a, path.parent), 'body-mass-index-v1')

    def test_cross_origin_known_business_is_rejected(self):
        task = {'site_uri': 'https://completely-new-source.example/',
                'deterministic_strategy': {'id': 'body-mass-index-v1'}}
        result = customer_history_decision(task, self.records)
        self.assertEqual(result['status'], 'REJECTED')
        self.assertEqual(result['history_sample_ids'], ['S000002_sample_000044'])

    def test_global_semantics_does_not_count_site_or_parameter_variation(self):
        def task(uri, value):
            return {'site_uri': uri, 'deterministic_strategy': {'id': 'unit-conversion-v1'},
                    'operations': [{'action_type': 'type', 'input_text': value}]}
        self.assertEqual(semantic_signature(task('https://a.example', '2')),
                         semantic_signature(task('https://b.example', '27')))

    def test_date_business_can_clear_known_lddgo_history(self):
        task = {'site_uri': 'https://www.lddgo.net/index',
                'deterministic_strategy': {'id': 'date-difference-v1'}}
        self.assertIsNone(customer_history_decision(task, self.records))
        self.assertFalse(any(r['strategy_id'] == 'date-difference-v1' for r in self.records))

    def test_unknown_same_origin_still_holds(self):
        task = {'site_uri': 'https://www.lddgo.net/index',
                'deterministic_strategy': {'id': 'date-difference-v1'}}
        rows = copy.deepcopy(self.records)
        row = next(r for r in rows if r['origin'] == 'https://www.lddgo.net')
        row['strategy_id'] = None; row['semantic_signature'] = None
        result = customer_history_decision(task, rows)
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['history_sample_ids'], [row['sample_id']])

    def test_generation_sources_bind_classifier_and_adapters_by_actual_bytes(self):
        identity = generation_source_identity()
        self.assertTrue({'task_generation.py', 'history_business.py', 'date_strategy.py',
                         'bmi_strategy.py', 'planning.py', 'task_contract.py'} <= set(identity))
        for name, digest in identity.items():
            self.assertEqual(digest, hashlib.sha256((ROOT/'projects/code/webcollect'/name).read_bytes()).hexdigest())

    def controlled_generation(self, root):
        record = capability(root/'capability')
        cat = catalog(root/'catalog.json', [record])
        ledger = BatchLedger(root/'CONTROLLED-operations.sqlite3', config(), initialize=True)
        return ledger, cat

    def test_generated_plan_and_job_bind_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); ledger, cat = self.controlled_generation(root)
            result = generate(ledger, cat, root/'tasks')
            plan = load_json(result['plan_file'])
            self.assertEqual(plan['generation']['source_identity'], generation_source_identity())
            with ledger.connect() as con:
                payload = json.loads(con.execute("SELECT payload FROM jobs WHERE kind='task-generation'").fetchone()[0])
            self.assertEqual(payload['source_identity'], generation_source_identity())

    def test_generation_source_drift_does_not_publish_plan(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); ledger, cat = self.controlled_generation(root)
            before = generation_source_identity(); after = {**before, 'history_business.py': '0'*64}
            with patch('webcollect.task_generation.generation_source_identity', side_effect=[before, after]):
                with self.assertRaisesRegex(ValueError, 'implementation changed'):
                    generate(ledger, cat, root/'tasks')
            self.assertFalse((root/'tasks/plan.json').exists())

    def test_execute_rejects_missing_or_drifted_generator_before_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); ledger, cat = self.controlled_generation(root)
            result = generate(ledger, cat, root/'tasks'); original = load_json(result['plan_file'])
            real_cat = load_json(cat); real_cat['mode'] = 'real'; cat = root/'real-catalog.json'; save_json(cat, real_cat)
            for kind in ('missing', 'classifier', 'adapter'):
                with self.subTest(kind=kind):
                    plan = copy.deepcopy(original); plan['generation']['mode'] = 'real'
                    if kind == 'missing':
                        plan['generation'].pop('source_identity')
                    else:
                        key = 'history_business.py' if kind == 'classifier' else 'date_strategy.py'
                        plan['generation']['source_identity'][key] = 'f'*64
                    plan_path = root / (kind + '-plan.json'); save_json(plan_path, plan)
                    with (patch('webcollect.preflight.preflight_plan', new_callable=AsyncMock) as preflight,
                          patch('webcollect.collect_runtime.collect_m4', new_callable=AsyncMock) as collect):
                        with self.assertRaisesRegex(ValueError, 'implementation changed or was not bound'):
                            asyncio.run(execute(SimpleNamespace(config={'mode': 'real'}), plan_path, cat,
                                                root/'execution', root/'MUST_NOT_CREATE.sqlite3', root/'policy.json'))
                        preflight.assert_not_awaited(); collect.assert_not_awaited()
                    self.assertFalse((root/'MUST_NOT_CREATE.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
