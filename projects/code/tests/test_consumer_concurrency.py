"""Consumer scheduler settings on temporary ledgers; no collection or model IO."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from webcollect.batch_core import BatchLedger, BudgetStop
from webcollect.consumer_ab import adjust_concurrency
from webcollect.consumer_roster import main as launch_roster
from webcollect.planning import object_sha256


class ConsumerConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = {'schema_version': 'webcollect-batch-config-1',
                       'run_id': 'isolated-consumer-concurrency', 'mode': 'synthetic',
                       'budget': {'max_concurrent_jobs': 1, 'min_domain_interval_seconds': 1,
                                  'lease_seconds': 300, 'max_job_attempts': 1}, 'model': None}
        self.config_path = self.root / 'config.json'
        self.config_path.write_text(json.dumps(self.config))
        self.ledger = BatchLedger(self.root / 'consumer.sqlite3', self.config, initialize=True)

    def job(self, index):
        jid = self.ledger.enqueue('collection', {'fixture': index})
        return self.ledger.claim('collection', job_id=jid)

    def change(self, target):
        return adjust_concurrency(self.ledger.path, self.config_path, target=target,
                                  authorization='isolated scheduler unit check')

    def test_live_instance_observes_changes_without_config_replacement(self):
        first = self.job(0)
        with self.assertRaises(BudgetStop):
            self.job(1)
        original = self.config_path.read_bytes()
        self.change(2)
        self.assertIsNotNone(self.job(1))
        self.change(None)
        self.assertIsNone(self.ledger.max_concurrent_jobs)
        self.assertEqual(len([self.job(i) for i in range(2, 12)]), 10)
        self.assertIsNone(BatchLedger(self.ledger.path, self.config).max_concurrent_jobs)
        self.assertEqual(self.config_path.read_bytes(), original)
        with self.ledger.connect() as con:
            self.assertEqual(json.loads(con.execute('SELECT config FROM batch_meta').fetchone()[0]), self.config)
        self.assertEqual(self.ledger.get(first['id'])['owner'], first['owner'])

    def test_unchanged_unlimited_setting_does_not_append_duplicate_event(self):
        self.assertTrue(self.change(None)['changed'])
        self.assertFalse(self.change(None)['changed'])
        with self.ledger.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM batch_events WHERE event='consumer_concurrency'").fetchone()[0], 1)

    def test_other_ledger_and_frozen_model_fields_remain_independent(self):
        producer = BatchLedger(self.root / 'producer.sqlite3', self.config, initialize=True)
        self.change(None)
        self.assertEqual(producer.max_concurrent_jobs, 1)
        jid = producer.enqueue('site-discovery-page', {'fixture': 1})
        producer.claim('site-discovery-page', job_id=jid)
        with self.assertRaises(BudgetStop):
            producer.claim('site-discovery-page', job_id=producer.enqueue('site-discovery-page', {'fixture': 2}))
        changed = deepcopy(self.config)
        changed['run_id'] = 'different-original-run'
        with self.assertRaisesRegex(ValueError, 'frozen'):
            BatchLedger(self.ledger.path, changed)

    def test_producer_markers_reject_consumer_settings_on_write_and_read(self):
        for event in ('producer_budget_unlimited', 'producer_concurrency'):
            with self.subTest(event=event):
                producer = BatchLedger(self.root / (event + '.sqlite3'), self.config, initialize=True)
                binding = {'ledger': str(producer.path), 'run_id': self.config['run_id'],
                           'config_sha256': object_sha256(self.config)}
                marker = {**binding, 'schema_version': 'webcollect-producer-concurrency-1',
                          'max_concurrent_jobs': 2}
                with producer.transaction() as con:
                    producer.event(con, event, marker)
                with self.assertRaisesRegex(ValueError, 'producer ledger'):
                    adjust_concurrency(producer.path, self.config_path, target=None, authorization='wrong role')
                with producer.transaction() as con:
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM batch_events WHERE event='consumer_concurrency'").fetchone()[0], 0)
                    # Even an already-loaded instance rejects a misplaced event.
                    producer.event(con, 'consumer_concurrency', {**binding,
                        'schema_version': 'webcollect-consumer-concurrency-1', 'max_concurrent_jobs': None})
                with self.assertRaisesRegex(ValueError, 'producer ledger'):
                    producer.max_concurrent_jobs

    def test_project_role_binding_rejects_unmarked_producer_ledger(self):
        from webcollect.current_chain import PROJECT_RULES
        config = deepcopy(self.config)
        guard = {'ledger': str(self.root / 'site-facts.sqlite3'), 'campaign_id': 'role-test',
                 'formal_since': 1, 'dispatch_rules': PROJECT_RULES}
        config['site_failure_guard'] = guard
        registry = self.root / 'production-registry.sqlite3'
        scope = {'chain_id': 'role-test', 'registry': str(registry),
                 'candidate_project': {'rules': PROJECT_RULES, 'site_ledger': guard['ledger']}}
        with sqlite3.connect(registry) as con:
            con.execute('CREATE TABLE current_chain_meta(id INTEGER PRIMARY KEY,binding_json TEXT)')
            con.execute('INSERT INTO current_chain_meta VALUES(1,?)', (json.dumps(scope),))
        config_path = self.root / 'guarded-config.json'
        config_path.write_text(json.dumps(config))
        producer = BatchLedger(self.root / 'producer-jobs.sqlite3', config, initialize=True)
        with self.assertRaisesRegex(ValueError, 'original role job ledger'):
            adjust_concurrency(producer.path, config_path, target=None, authorization='wrong role')
        consumer = BatchLedger(self.root / 'consumer-jobs.sqlite3', config, initialize=True)
        adjust_concurrency(consumer.path, config_path, target=None, authorization='bound consumer role')
        self.assertIsNone(consumer.max_concurrent_jobs)

    def test_missing_limit_is_not_an_unlimited_setting(self):
        with self.ledger.transaction() as con:
            self.ledger.event(con, 'consumer_concurrency', {
                'schema_version': 'webcollect-consumer-concurrency-1',
                'ledger': str(self.ledger.path), 'run_id': self.config['run_id'],
                'config_sha256': object_sha256(self.config)})
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.ledger.max_concurrent_jobs

    def test_roster_changes_settings_without_rewriting_config_or_policy(self):
        policy_path = self.root / 'policy.json'
        policy_path.write_text(json.dumps({'max_workers': 3, 'max_domain_workers': 3}))
        scope = {key: str(self.root / key) for key in ('pool', 'registry', 'output', 'history_set')}
        scope.update(consumer_db=str(self.ledger.path), consumer_config=str(self.config_path),
                     policy=str(policy_path), batch='isolated-batch')
        scope_path = self.root / 'scope.json'
        scope_path.write_text(json.dumps(scope))
        original = (self.config_path.read_bytes(), policy_path.read_bytes())
        runtime = Mock()
        runtime.set_consumer_concurrency.return_value = {'max_workers': None, 'max_domain_workers': None}
        process = Mock()
        process.wait.return_value = 0
        argv = ['consumer_roster', '--scope', str(scope_path), '--workers', '2',
                '--prefix', 'unit', '--output', str(self.root / 'launch'), '--limit', '2', '--launch']
        with patch('sys.argv', argv), patch('webcollect.runtime.RuntimeStore', return_value=runtime), \
                patch('webcollect.consumer_roster.subprocess.Popen', return_value=process) as popen:
            launch_roster()
        self.assertEqual(popen.call_count, 2)
        self.assertIsNone(self.ledger.max_concurrent_jobs)
        self.assertEqual(runtime.set_consumer_concurrency.call_args.kwargs['max_workers'], None)
        self.assertEqual(runtime.set_consumer_concurrency.call_args.kwargs['max_domain_workers'], None)
        self.assertEqual((self.config_path.read_bytes(), policy_path.read_bytes()), original)
        self.assertTrue(json.loads((self.root / 'launch/roster.json').read_text())['concurrency_settings_applied'])

    def test_prepared_roster_does_not_claim_settings_were_applied(self):
        policy_path = self.root / 'policy.json'
        policy_path.write_text(json.dumps({'max_workers': 3, 'max_domain_workers': 3}))
        scope = {key: str(self.root / key) for key in ('pool', 'registry', 'output', 'history_set')}
        scope.update(consumer_db=str(self.ledger.path), consumer_config=str(self.config_path),
                     policy=str(policy_path), batch='isolated-batch')
        scope_path = self.root / 'scope.json'
        scope_path.write_text(json.dumps(scope))
        argv = ['consumer_roster', '--scope', str(scope_path), '--workers', '2',
                '--prefix', 'unit', '--output', str(self.root / 'prepared'), '--limit', '2']
        with patch('sys.argv', argv), patch('webcollect.consumer_roster.subprocess.Popen') as popen:
            launch_roster()
        popen.assert_not_called()
        roster = json.loads((self.root / 'prepared/roster.json').read_text())
        self.assertFalse(roster['concurrency_settings_applied'])
        self.assertEqual(self.ledger.max_concurrent_jobs, 1)


if __name__ == '__main__':
    unittest.main()
