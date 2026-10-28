"""Budget, cache and crash tests; controlled synthetic results never count as AI."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest

from webcollect.batch_core import BatchLedger, BudgetStop, OutcomeUnknown, load_json, validate_config
from webcollect.model_gateway import ModelGateway

CONFIG = Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json'
SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'integer'}},
          'required': ['answer'], 'additionalProperties': False}


class BatchCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = load_json(CONFIG)
        self.root = Path(self.temp.name)

    def ledger(self, config=None):
        return BatchLedger(self.root/'ops.sqlite3', config or self.config, initialize=True)

    def job(self, ledger, identity='a'):
        jid = ledger.enqueue('test', {'fixture': identity})
        return ledger.claim('test', job_id=jid)

    def test_idempotent_jobs_frozen_budget_and_cache(self):
        ledger = self.ledger()
        job = self.job(ledger)
        self.assertEqual(job['id'], ledger.enqueue('test', {'fixture': 'a'}))
        gateway = ModelGateway(ledger)
        for _ in range(2):
            self.assertEqual(gateway.call(job, 'check-v1', 'JSON test', SCHEMA,
                synthetic_response={'answer': 42}), {'answer': 42})
        self.assertEqual(ledger.summary()['model_requests'], 1)
        ledger.finish(job, result={'answer': 42})
        self.assertIsNone(ledger.claim('test', job_id=job['id']))
        changed = deepcopy(self.config); changed['budget']['max_model_requests'] += 1
        with self.assertRaisesRegex(ValueError, 'frozen'):
            BatchLedger(ledger.path, changed, initialize=True)

    def test_limits_include_failed_requests_and_survive_restart(self):
        config = deepcopy(self.config); config['budget']['max_model_requests'] = 1
        ledger = self.ledger(config); job = self.job(ledger)
        gateway = ModelGateway(ledger)
        with self.assertRaises(BudgetStop):
            gateway.call(job, 'bad', 'JSON test', SCHEMA, synthetic_response={'answer': 'wrong'})
        self.assertEqual(ledger.summary()['model_requests'], 1)
        resumed = BatchLedger(ledger.path, config)
        with self.assertRaises(BudgetStop):
            resumed.reserve_request(job, 'other', 0)
        ledger.finish(job, 'review_required')

    def test_crash_after_reserve_preserves_unknown_charge(self):
        ledger = self.ledger(); job = self.job(ledger)
        rid = ledger.reserve_request(job, 'test', 0)['id']
        with ledger.transaction() as con:
            con.execute('UPDATE jobs SET lease=? WHERE id=?', (time.time()-1, job['id']))
        self.assertEqual(ledger.recover(), 1)
        self.assertEqual(ledger.get(job['id'])['state'], 'review_required')
        self.assertIsNone(ledger.claim('test'))
        with ledger.connect() as con:
            self.assertEqual(con.execute('SELECT state FROM model_requests WHERE id=?', (rid,)).fetchone()[0], 'unknown')
        self.assertEqual(ledger.summary()['model_cost_micros'], 'UNKNOWN')
        with self.assertRaisesRegex(ValueError, 'Lost/expired'):
            ledger.finish(job)

    def test_resource_and_request_caps_do_not_reset(self):
        config = deepcopy(self.config); config['budget']['max_probe_pages'] = 1
        ledger = self.ledger(config)
        ledger.consume('probe_pages', 'one')
        BatchLedger(ledger.path, config).consume('probe_pages', 'one')
        with self.assertRaises(BudgetStop):
            ledger.consume('probe_pages', 'two')
        self.assertEqual(ledger.summary()['resources'][0]['used'], 1)

    def test_changed_prompt_has_new_request_and_all_images_checked(self):
        ledger = self.ledger(); job = self.job(ledger); gateway = ModelGateway(ledger)
        for text in ('JSON v1', 'JSON v2'):
            gateway.call(job, 'review', text, SCHEMA, synthetic_response={'answer': 1})
        with self.assertRaises(ValueError):
            gateway.call(job, 'review', 'JSON', SCHEMA, images=[self.root/'absent.png'])
        self.assertEqual(ledger.summary()['model_requests'], 2)

    def test_invalid_real_configuration_fails_before_database_creation(self):
        config = deepcopy(self.config); config['mode'] = 'real'
        config['model']['provider'] = 'chat-completions'
        with self.assertRaises(ValueError):
            self.ledger(config)
        self.assertFalse((self.root/'ops.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
