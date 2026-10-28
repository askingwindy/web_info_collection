"""Identity admission regression on controlled local inventories; no real I/O."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from webcollect.batch_core import BatchLedger, load_json
from webcollect.task_generation import (check_live_m4_history, compile_form,
    deterministic_specs, generate, register_task, semantic_signature,
    task_signature, validated_business_identity)
from test_s0_task_generation import capability, catalog, config


class BusinessIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def record(self, kind):
        record = capability(self.root / kind, kind=kind)
        # Deliberately use the same executor, URI and selector/action structure.
        # Labels, the actual business goal and the result meaning differ.
        for n, field in enumerate(record['capabilities'][0]['forms'][0]['fields']):
            field['selector'] = '#control-' + str(n)
        return record

    def task(self, kind='shopping'):
        record = self.record(kind)
        return compile_form(record, deterministic_specs(record)['tasks'][0])

    def ledger(self):
        return BatchLedger(self.root / 'CONTROLLED-operations.sqlite3', config(), initialize=True)

    def test_same_executor_and_structure_admit_distinct_registered_businesses(self):
        shopping, speed = self.task(), self.task('speed')
        self.assertEqual(shopping['execution_capability'], speed['execution_capability'])
        self.assertEqual(task_signature(shopping), task_signature(speed))
        self.assertNotEqual(semantic_signature(shopping), semantic_signature(speed))
        ledger = self.ledger()
        register_task(ledger, shopping, 'shopping-job')
        register_task(ledger, speed, 'speed-job')
        with ledger.connect() as connection:
            rows = list(connection.execute('SELECT signature,task_json FROM generated_task_index'))
        self.assertEqual(len(rows), 3)  # retained coarse structure and two business keys
        structural = next(row for row in rows if row['signature'] == task_signature(shopping))
        self.assertEqual(json.loads(structural['task_json']), shopping)

    def test_generation_retains_two_same_structure_distinct_businesses_and_resumes(self):
        ledger = self.ledger()
        path = catalog(self.root / 'catalog.json', [self.record('shopping'), self.record('speed')])
        result = generate(ledger, path, self.root / 'tasks')
        resumed = generate(ledger, path, self.root / 'tasks')
        self.assertEqual(result['generated_tasks'], 2)
        self.assertEqual(result['rejected'], [])
        self.assertEqual(result, resumed)
        self.assertEqual(len(load_json(result['plan_file'])['tasks']), 2)
        self.assertEqual(ledger.summary()['model_requests'], 0)

    def test_changed_execution_id_cannot_become_new_business(self):
        task = self.task()
        baseline = semantic_signature(task)
        task['deterministic_strategy']['id'] = 'shared-execution-strategy'
        self.assertEqual(semantic_signature(task), baseline)

    def test_parameters_route_and_selector_substitution_do_not_create_novelty(self):
        task = self.task()
        altered = deepcopy(task)
        altered['site_uri'] = altered['initial_url'] = 'https://new.example/copied?quantity=8'
        altered['operations'][1]['arguments']['text'] = '8'
        for op in altered['operations']:
            if 'selector' in op:
                op['selector'] += '-copy'
        self.assertEqual(semantic_signature(task), semantic_signature(altered))
        ledger = self.ledger()
        register_task(ledger, task, 'first-job')
        with self.assertRaisesRegex(ValueError, 'parameter/selector substitutions rejected'):
            register_task(ledger, altered, 'parameter-variant')

    def test_unknown_business_claim_does_not_fallback_to_execution_or_legacy_id(self):
        task = self.task()
        task['business_identity']['business_id'] = 'handwritten-unobserved-business'
        self.assertIsNone(validated_business_identity(task))
        self.assertIsNone(semantic_signature(task))
        with self.assertRaisesRegex(ValueError, 'review required'):
            register_task(self.ledger(), task, 'unknown')

    def test_other_registered_business_claim_requires_actual_matching_controls(self):
        task, speed = self.task(), self.task('speed')
        task['business_identity'] = speed['business_identity']
        task['capability_id'] = speed['capability_id']
        task['capability_version'] = speed['capability_version']
        self.assertIsNone(semantic_signature(task))

    def test_necessary_operation_role_cannot_be_changed(self):
        task = self.task()
        task['operations'][1]['evidence']['target_label'] = '未知输入'
        self.assertIsNone(semantic_signature(task))

    def test_padded_action_does_not_support_identity(self):
        task = self.task()
        task['operations'].insert(-1, {'action_type': 'scroll', 'operation_id': 'padding'})
        self.assertIsNone(semantic_signature(task))

    def test_missing_final_evidence_does_not_support_identity(self):
        task = self.task()
        task['final_assertions'] = []
        self.assertIsNone(semantic_signature(task))

    def test_changed_business_goal_state_or_terminal_meaning_is_not_new_business(self):
        for key, value in [('business_goal', '另一个目标'), ('state_path', ['invented-result']),
                           ('completion_criterion', {'result_role': '未知', 'unit': '小时'})]:
            task = self.task()
            task['business_identity']['definition'][key] = value
            with self.subTest(key=key):
                self.assertIsNone(semantic_signature(task))

    def test_observation_binding_must_match_exact_capability_version(self):
        for key in ('capability_id', 'capability_version'):
            task = self.task()
            task['business_identity']['observation_binding'][key] = 'other-observation'
            with self.subTest(key=key):
                self.assertIsNone(semantic_signature(task))

    def test_malformed_operations_or_terminal_cannot_supply_identity(self):
        for change in ('operations-object', 'operations-nondict', 'terminal-object', 'terminal-no-oracle'):
            task = self.task()
            if change == 'operations-object':
                task['operations'] = {'bad': 'claim'}
            elif change == 'operations-nondict':
                task['operations'] = ['unobserved']
            elif change == 'terminal-object':
                task['final_assertions'] = {'text': 'claimed-result'}
            else:
                task['final_assertions'][0]['numbers'] = {'minimum': 42}
            with self.subTest(change=change):
                self.assertIsNone(semantic_signature(task))

    def test_execution_capability_version_cannot_be_forged(self):
        task = self.task()
        task['execution_capability']['version'] = 'unchecked-new-executor'
        self.assertIsNone(semantic_signature(task))

    def test_unknown_legacy_structure_collision_still_rejects(self):
        task = self.task()
        unknown = deepcopy(task)
        unknown.pop('business_identity')
        unknown.pop('execution_capability')
        unknown['deterministic_strategy'] = {'id': 'legacy-unknown'}
        ledger = self.ledger()
        register_task(ledger, unknown, 'legacy')
        with self.assertRaisesRegex(ValueError, 'form/action structure already generated'):
            register_task(ledger, task, 'new')

    def test_live_history_keeps_same_business_rejection_but_admits_distinct_business(self):
        shopping, speed = self.task(), self.task('speed')
        registry = self.root / 'CONTROLLED-m4-history.sqlite3'
        with sqlite3.connect(registry) as connection:
            connection.execute('CREATE TABLE m4_tasks(scope_id TEXT,task_json TEXT)')
            connection.execute('INSERT INTO m4_tasks VALUES(?,?)', ('old-scope', json.dumps(shopping)))
        check_live_m4_history({'tasks': [speed]}, registry, self.root / 'capture')
        with self.assertRaisesRegex(ValueError, 'same business/structure'):
            check_live_m4_history({'tasks': [shopping]}, registry, self.root / 'capture')
        old = deepcopy(shopping)
        old.pop('business_identity')
        old.pop('execution_capability')
        with sqlite3.connect(registry) as connection:
            connection.execute('UPDATE m4_tasks SET task_json=?', (json.dumps(old),))
        # Legacy evidence does not retroactively gain a complete new identity.
        with self.assertRaisesRegex(ValueError, 'same business/structure'):
            check_live_m4_history({'tasks': [speed]}, registry, self.root / 'capture')


if __name__ == '__main__':
    unittest.main()
