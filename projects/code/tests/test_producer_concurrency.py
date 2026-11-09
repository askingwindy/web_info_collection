"""Original-ledger producer concurrency decisions use disposable projects only."""
import json
from pathlib import Path
import tempfile
import unittest

from site_planner.producer_authority import authorize_concurrency
from webcollect.batch_core import BatchLedger, BudgetStop, load_json
from webcollect.candidate_project import initialize


class ProducerConcurrency(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        config = load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')
        config['budget']['max_concurrent_jobs'] = 1
        self.scope_path = initialize(self.root/'project', 'concurrency', {'max_worker_seconds':15}, config, config)
        self.scope = load_json(self.scope_path)
        self.config = load_json(self.scope['producer_config'])
        self.ledger = BatchLedger(self.scope['producer_db'], self.config, initialize=True)

    def test_two_slots_keep_original_config_unknown_and_consumer_limit(self):
        config_bytes = Path(self.scope['producer_config']).read_bytes()
        manifest_bytes = Path(self.scope['history_set']).read_bytes()
        jid = self.ledger.enqueue('original-unknown', {})
        with self.ledger.transaction() as con:
            con.execute("INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started) "
                        "VALUES('original',?,'probe',0,'unknown',10,20,1)", (jid,))
            original_request = tuple(con.execute("SELECT * FROM model_requests WHERE id='original'").fetchone())
            frozen = con.execute('SELECT config FROM batch_meta').fetchone()[0]
        decision = authorize_concurrency(self.scope_path, 2, 'test operator starts the new producer')
        self.assertEqual(authorize_concurrency(self.scope_path, 2, decision['reason']), decision)
        ledger = BatchLedger(self.scope['producer_db'], self.config)
        self.assertEqual((ledger.config['budget']['max_concurrent_jobs'], ledger.max_concurrent_jobs), (1, 2))
        first = ledger.claim('model', job_id=ledger.enqueue('model', {}))
        second = ledger.claim('browser', job_id=ledger.enqueue('browser', {}))
        self.assertTrue(first and second)
        with self.assertRaises(BudgetStop):
            ledger.claim('third', job_id=ledger.enqueue('third', {}))
        with ledger.connect() as con:
            self.assertEqual(con.execute('SELECT config FROM batch_meta').fetchone()[0], frozen)
            self.assertEqual(tuple(con.execute("SELECT * FROM model_requests WHERE id='original'").fetchone()), original_request)
            self.assertEqual(con.execute("SELECT count(*) FROM batch_events WHERE event='producer_concurrency'").fetchone()[0], 1)
        self.assertEqual(Path(self.scope['producer_config']).read_bytes(), config_bytes)
        self.assertEqual(Path(self.scope['history_set']).read_bytes(), manifest_bytes)
        consumer = BatchLedger(self.scope['consumer_db'], load_json(self.scope['consumer_config']), initialize=True)
        self.assertEqual(consumer.max_concurrent_jobs, 1)
        changed = json.loads(json.dumps(self.config)); changed['budget']['max_concurrent_jobs'] = 2
        with self.assertRaisesRegex(ValueError, 'configuration is frozen'):
            BatchLedger(self.scope['producer_db'], changed)

    def test_live_job_must_finish_before_decision(self):
        self.ledger.claim('browser', job_id=self.ledger.enqueue('browser', {}))
        with self.assertRaisesRegex(ValueError, 'active job'):
            authorize_concurrency(self.scope_path, 2, 'test')
        with self.ledger.connect() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM batch_events WHERE event='producer_concurrency'").fetchone()[0], 0)

    def test_foreign_binding_is_rejected(self):
        decision = authorize_concurrency(self.scope_path, 2, 'test')
        decision['ledger'] = str(self.root/'foreign.sqlite3')
        with self.ledger.transaction() as con:
            self.ledger.event(con, 'producer_concurrency', decision)
        with self.assertRaisesRegex(ValueError, 'concurrency decision'):
            BatchLedger(self.scope['producer_db'], self.config)


if __name__ == '__main__':
    unittest.main()
