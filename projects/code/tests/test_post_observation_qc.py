"""Scoped observation and unresolved-pair guards, disposable evidence only."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import io,json,unittest
from PIL import Image
from webcollect.action_stability import pair
from webcollect.batch_core import BatchLedger,load_json
from quality_inspector.ai_worker import unresolved_pair_inputs

class UnknownPair(unittest.TestCase):
    def test_full_vectors_block_new_ids_prose_and_chunking_but_not_other_neighbor(self):
        with TemporaryDirectory() as d:
            root=Path(d);cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
            ledger=BatchLedger(root/'local.db',cfg,initialize=True)
            for name in ('f1','f2','n1','n2','different'):(root/name).write_text(name)
            payload={'candidate':{'sample_id':'old','images':['f1','f2']},'neighbors':[{'sample_id':'old-neighbor','images':['n1','n2']}]}
            jid=ledger.enqueue('ai-difference',payload)
            with ledger.connect() as con:columns=[r[1] for r in con.execute('pragma table_info(model_requests)')]
            with ledger.transaction() as con:
                con.execute("INSERT INTO model_requests(id,job_id,purpose,state,started,request_json,attempt,reserved_tokens,reserved_cost) VALUES(?,?,?,'unknown',0,'{}',1,0,0)",('original',jid,'difference-0-part-0:original-binding'))
            def compact(value):return {'sample_id':value['sample_id']},[root/n for n in value['images']]
            with patch('quality_inspector.ai_worker.compact_trajectory',side_effect=compact):
                focal={**payload['candidate'],'sample_id':'new','annotation':'changed prose'}
                other={**payload['neighbors'][0],'sample_id':'renamed'}
                self.assertEqual(unresolved_pair_inputs(ledger,focal,other)[0]['request_id'],'original')
                self.assertEqual(unresolved_pair_inputs(ledger,focal,{**other,'images':['different']}),[])
            with ledger.connect() as con:self.assertEqual(con.execute('select state from model_requests').fetchone()[0],'unknown')
