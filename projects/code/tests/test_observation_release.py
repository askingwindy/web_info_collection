"""Observation-only release retains the old claim and permits formal re-claim."""
import unittest
from unittest.mock import patch
import test_candidate_inventory as inventory
from webcollect.batch_core import BatchLedger,load_json
from webcollect.candidate_consumer import release_observation

class ObservationRelease(unittest.TestCase):
    def test_only_verified_settled_observation_releases_and_new_claim_can_take_it(self):
        f=inventory.Inventory('test_explicit_extension_no_old_page_conversion');f.setUp();self.addCleanup(f.doCleanups)
        cid=f.pool.put(f.candidate(),f.source);claim=f.pool.claim_next('sample','sample-request')
        ledger=BatchLedger(f.root/'jobs.db',load_json(__import__('pathlib').Path(__file__).parents[1]/'config/batch-synthetic.json'),initialize=True)
        jid=ledger.enqueue('candidate-observation',{'claim_id':claim['claim_id']});job=ledger.claim('candidate-observation',job_id=jid)
        visit=ledger.reserve_visit(job,claim['snapshot']['entry_url'],'observation','example.org')
        f.pool.stage(claim,'observation',{'first_frame_only':True,'ledger':str(ledger.path)})
        with self.assertRaises(ValueError):release_observation(ledger,f.pool,claim)
        self.assertEqual(f.pool.get_claim(claim['claim_id'])['state'],'consuming')
        ledger.settle_visit(visit,state='succeeded',response_status=200,landed_uri=claim['snapshot']['entry_url']);ledger.finish(job,result={'receipt':'fixture'})
        with patch('webcollect.candidate_feedback._frame',return_value=(True,'public_page',[])):
            result=release_observation(ledger,f.pool,claim)
        self.assertEqual(result['candidate_state'],'pending')
        self.assertEqual(f.pool.get_claim(claim['claim_id'])['state'],'observed')
        formal=f.pool.claim_next('formal','formal-request',candidate_id=cid)
        self.assertEqual(formal['state'],'consuming');self.assertNotEqual(formal['claim_id'],claim['claim_id'])
