"""Offline fixtures only: shared health/binding and independent site target semantics."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from webcollect.batch_core import BatchLedger, file_sha
from webcollect import consumer_campaign as campaign
from webcollect import key_health, model_credentials
import test_model_provider_protocols as protocol


class ConsumerHealthCampaignTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.token = self.root / 'tokens.yaml'
        self.keys = ['offline-key-one', 'offline-key-two']
        self.token.write_text('glm:\n  - offline-key-one\n  - offline-key-two\n')
        self.config = protocol.ProviderProtocolTests.config(self, 'glm', vision=True)
        self.config['model']['api_key_file'] = str(self.token)
        self.ledger = BatchLedger(self.root / 'ledger.sqlite3', self.config, initialize=True)

    def test_health_shared_1113_recovery_and_unknown_separate(self):
        account = model_credentials.account_id(self.keys[0])
        key_health.record_result(self.ledger, account, code='1113')
        other = BatchLedger(self.ledger.path, self.config)
        with other.transaction() as con:
            self.assertIn(account, key_health.unavailable_accounts(other, con))
        key_health.record_result(other, account)  # network UNKNOWN cannot restore balance
        with other.transaction() as con:
            self.assertIn(account, key_health.unavailable_accounts(other, con))
        key_health.record_result(other, account, success=True, probe_id='explicit-new-probe')
        with other.transaction() as con:
            self.assertNotIn(account, key_health.unavailable_accounts(other, con, historical={account}))
        unknown = model_credentials.account_id(self.keys[1])
        key_health.record_result(other, unknown)
        with other.transaction() as con:
            self.assertIn(unknown, key_health.unavailable_accounts(other, con))
        key_health.record_result(other, unknown, success=True, probe_id='known-good')
        key_health.record_result(other, unknown)
        with other.transaction() as con:
            self.assertNotIn(unknown, key_health.unavailable_accounts(other, con))
        key_health.record_result(other, unknown, code='1302', retry_after=60)
        with other.transaction() as con:
            self.assertIn(unknown, key_health.unavailable_accounts(other, con))
        key_health.record_result(other, unknown, code='1302', retry_after=-1)
        with other.transaction() as con:
            self.assertNotIn(unknown, key_health.unavailable_accounts(other, con))
        self.assertEqual(key_health.health_status('1302'), 'rate_limited')
        self.assertEqual(key_health.health_status('1305'), 'model_limited')

    def test_new_session_random_old_binding_and_empty_pool(self):
        self.assertFalse(key_health.pool_available(self.ledger))
        for key in self.keys:
            key_health.record_result(self.ledger, model_credentials.account_id(key), success=True, probe_id='fixture-probe')
        with patch('webcollect.model_credentials.secrets.choice', side_effect=lambda keys: keys[-1]) as choose:
            selected = self.ledger.bind_model_session('new-session', consumer=True)
            self.assertEqual(selected, self.keys[1])
            self.assertEqual(choose.call_count, 1)
        account = model_credentials.account_id(selected)
        key_health.record_result(self.ledger, account, code='1113')
        # Existing bindings remain original even when account becomes unavailable.
        self.assertEqual(self.ledger.bind_model_session('new-session', consumer=True), selected)
        self.assertEqual(self.ledger.bind_model_session('another-session', consumer=True), self.keys[0])
        key_health.record_result(self.ledger, model_credentials.account_id(self.keys[0]), code='1113')
        self.assertFalse(key_health.pool_available(self.ledger))
        with self.assertRaises(ValueError):
            self.ledger.bind_model_session('no-account', consumer=True)

    def test_unknown_session_recovers_original_account_without_replay(self):
        original = model_credentials.account_id(self.keys[0])
        with self.ledger.transaction() as con:
            con.execute("INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started,request_json) VALUES(?,?,?,?,?,?,?,?,?)",
                        ('unknown-original', 'old-session', 'plan', 0, 'unknown', 0, 0, 1,
                         json.dumps({'account_id':original, 'dispatch_attempt_id':'old-session'})))
        key_health.record_result(self.ledger, original, code='1113')
        self.assertEqual(self.ledger.bind_model_session('old-session', consumer=True), self.keys[0])
        with self.ledger.connect() as con:
            row = con.execute("SELECT state,request_json FROM model_requests WHERE id='unknown-original'").fetchone()
        self.assertEqual(row['state'], 'unknown')
        self.assertEqual(json.loads(row['request_json'])['account_id'], original)

    def test_coordinator_probes_once_separate_accounting_no_secret(self):
        calls = []
        def transport(model, secret, request_id):
            calls.append(request_id)
            return {'success': True, 'usage': {'prompt_tokens': 3, 'completion_tokens': 1}}
        key_health.probe_accounts(self.ledger, 'launch-one', transport)
        key_health.probe_accounts(self.ledger, 'launch-one', transport)
        self.assertEqual(len(calls), 2)
        with self.ledger.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0], 0)
            rows = list(con.execute('SELECT * FROM consumer_key_probes'))
            self.assertEqual(len(rows), 2)
            material = json.dumps([tuple(row) for row in rows])
            self.assertNotIn(self.keys[0], material)
            self.assertNotIn(self.keys[1], material)

    def site_state(self):
        return {'schema_version':campaign.SITE_CAMPAIGN_VERSION,
                'counting_policy':campaign.ORDINARY_COUNTING, 'site_targets':{'a':5, 'b':5},
                'dispatch_stopped':False, 'deliveries':[]}

    def test_site_target_closes_only_own_site_and_preserves_overage(self):
        state = self.site_state()
        state['deliveries'] = [{'application_id':'a', 'ordinary_target_eligible':True} for _ in range(7)]
        path = self.root / 'campaign.json'
        campaign.write_state(path, state)
        self.assertTrue(campaign.stopped(path, 'a'))
        self.assertFalse(campaign.stopped(path, 'b'))
        self.assertFalse(campaign.target_reached(state))
        self.assertIsNone(campaign.claim_if_open(path, lambda: 'wrong-claim', 'a'))
        self.assertEqual(campaign.claim_if_open(path, lambda: 'b-claim', 'b'), 'b-claim')
        state['deliveries'] += [{'application_id':'b', 'ordinary_target_eligible':True} for _ in range(5)]
        self.assertTrue(campaign.target_reached(state))
        self.assertEqual(campaign.target_count(state), 12)
        self.assertEqual(len(state['deliveries']), 12)
        old = {'schema_version':campaign.CAMPAIGN_VERSION, 'target':10,
               'counting_policy':campaign.ORDINARY_COUNTING, 'deliveries':state['deliveries']}
        self.assertTrue(campaign.target_reached(old))

    def saved(self, count, *, short=False, status='success'):
        sample = self.root / ('sample-' + str(count)); sample.mkdir()
        annotation = sample / 'annotation.json'
        annotation.write_text(json.dumps({'completion_status':status, 'short_flow':short,
            'steps':[{'action':{'action_type':'click'}} for _ in range(count)]}))
        receipt = self.root / ('receipt-' + str(count) + '.json')
        receipt.write_text(json.dumps({'sample_files_sha256':{'annotation.json':file_sha(annotation)},
                                      'raw_execution':{}}))
        return {'result_location':str(sample), 'save_receipt':{'path':str(receipt)}}

    def test_short_completion_and_range_policy_are_distinct(self):
        short = campaign.ordinary_completion(self.saved(3, short=True))
        self.assertTrue(short['original_goal_completed'])
        self.assertFalse(short['ordinary_target_eligible'])
        ordinary = campaign.ordinary_completion(self.saved(5))
        self.assertTrue(ordinary['ordinary_target_eligible'])
        incomplete = self.saved(6, status='controlled_exception')
        self.assertFalse(campaign.ordinary_completion(incomplete)['ordinary_target_eligible'])
        self.assertTrue(campaign.valid_range_completion(incomplete)['valid_range_target_eligible'])


if __name__ == '__main__':
    unittest.main()
