"""Named uncertain selections are retained, never retried or turned into empty choices."""
from pathlib import Path
import tempfile
import unittest
from webcollect.batch_core import BatchLedger,load_json,save_json,file_sha
from site_planner.discovery_agent import deferred_selections,is_deferred_selection,selection_job_id,SELECT_SCHEMA


class DiscoveryContinuation(unittest.TestCase):
    def test_only_named_transport_unknown_selection_is_deferred(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
            ledger=BatchLedger(root/'ledger.db',cfg,initialize=True);payload={'results':[{'index':1}]}
            jid=ledger.enqueue('ai-select-results',{'input':payload,'schema':SELECT_SCHEMA,'image_refs':[]})
            self.assertEqual(jid,selection_job_id(payload));job=ledger.claim('ai-select-results',job_id=jid)
            rid=ledger.reserve_request(job,'selection',0,{})['id'];ledger.settle_request(rid,state='unknown',error='URLError');ledger.finish(job,'review_required')
            decision=root/'decision.json';save_json(decision,{'action':'continue-independent-discovery-without-retrying-unknown','run_id':cfg['run_id'],'request_ids':[rid],'reason':'Keep original unresolved; only new independent inputs may proceed'})
            allowed=deferred_selections(ledger,{'path':str(decision),'sha256':file_sha(decision)},cfg['run_id'])
            self.assertEqual(is_deferred_selection(ledger,payload,allowed),[rid])
            self.assertEqual(is_deferred_selection(ledger,{'results':[]},allowed),[])
            self.assertEqual(ledger.get(jid)['state'],'review_required');self.assertEqual(ledger.summary()['model_requests'],1)
            with self.assertRaises(ValueError):deferred_selections(ledger,{'path':str(decision),'sha256':file_sha(decision)},'different-run')
