"""Temporary authorization diagnostics; no provider or historical data access."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from webcollect.batch_core import BatchLedger,load_json,save_json,file_sha,OutcomeUnknown
from webcollect.model_gateway import ModelGateway
from webcollect import provider_recovery as recovery

class ProviderRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        cfg=load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')
        self.ledger=BatchLedger(self.root/'ledger.sqlite3',cfg,initialize=True)
        self.evidence=self.root/'update.json';save_json(self.evidence,{'CONTROLLED':'credential update assertion'})
        self.ref={'path':str(self.evidence),'sha256':file_sha(self.evidence)}
        jid=self.ledger.enqueue('original',{'CONTROLLED':True});job=self.ledger.claim('original',job_id=jid)
        self.request=self.ledger.reserve_request(job,'original unknown',0)
        self.ledger.settle_request(self.request['id'],state='unknown',error='HTTPError:401',
            response={'provider_error':{'http_status':401,'provider_code':'1000'}})
        self.ledger.finish(job,'review_required')

    def probe(self):
        jid=recovery.prepare(self.ledger,[self.ref]);return self.ledger.claim(recovery.KIND,job_id=jid)

    def test_recovery_preserves_unknown_and_old_replay_stays_blocked(self):
        with self.ledger.connect() as con:before=dict(con.execute('SELECT * FROM model_requests').fetchone())
        job=self.probe();gateway=ModelGateway(self.ledger)
        result=gateway.call(job,'auth-health',recovery.TEXT,recovery.SCHEMA,attempts=1,synthetic_response={'ok':True})
        self.ledger.finish(job,result=result);proof=recovery.complete(self.ledger,job['id'])
        self.assertEqual(proof,recovery.complete(self.ledger,job['id']))
        with self.ledger.connect() as con:
            self.assertFalse(recovery.holds(con));self.assertEqual(before,dict(con.execute('SELECT * FROM model_requests WHERE id=?',(self.request['id'],)).fetchone()))
        jid=self.ledger.enqueue('business',{'new':True});new=self.ledger.claim('business',job_id=jid)
        self.assertEqual(gateway.call(new,'new-input','new request',{'type':'object'},synthetic_response={}),{})
        old=deepcopy(new);old['id']=before['job_id']
        # The original uncertain identity is never changed to successful.
        with self.ledger.connect() as con:self.assertEqual(con.execute('SELECT state FROM model_requests WHERE id=?',(before['id'],)).fetchone()[0],'unknown')

    def test_wrong_probe_content_cannot_bypass_hold(self):
        job=self.probe()
        with self.assertRaises(OutcomeUnknown):ModelGateway(self.ledger).call(job,'fake','business task',{'type':'object'},synthetic_response={})
        self.assertEqual(self.ledger.summary()['model_requests'],1)
        with self.assertRaises(ValueError):recovery.complete(self.ledger,job['id'])

    def test_failed_diagnostic_is_not_repeated_or_accepted(self):
        job=self.probe();request=self.ledger.reserve_request(job,'fixed diagnostic',0,
            request_json={'text':recovery.TEXT,'schema':recovery.SCHEMA,'images':[]})
        self.ledger.settle_request(request['id'],state='unknown',error='HTTPError:401')
        with self.assertRaises(OutcomeUnknown):self.ledger.reserve_request(job,'fixed diagnostic',0)
        with self.assertRaises(ValueError):recovery.complete(self.ledger,job['id'])
        self.assertEqual(self.ledger.summary()['model_requests'],2)

    def test_changed_authorization_evidence_blocks_probe(self):
        job=self.probe();self.evidence.write_text('changed')
        with self.assertRaises(ValueError):ModelGateway(self.ledger).call(job,'auth-health',recovery.TEXT,recovery.SCHEMA,synthetic_response={'ok':True})
        self.assertEqual(self.ledger.summary()['model_requests'],1)
