"""Producer timeout isolation at formal producer and shared-gateway boundaries."""
import unittest
from unittest.mock import patch

import test_model_provider_protocols as fixtures
from site_planner.discovery_agent import model_decision,model_tool_decision
from webcollect.batch_core import BatchLedger,OutcomeUnknown
from webcollect.model_gateway import ModelGateway


class ProducerTimeout(unittest.TestCase):
    def test_each_producer_protocol_keeps_one_original_unknown_without_resend(self):
        f=fixtures.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        f.setUp();self.addCleanup(f.doCleanups)
        f.opener.error=TimeoutError('controlled producer timeout')
        for index,kind in enumerate(('ai-search-plan','ai-application-site-classification-1','ai-grounded-entry-ids-1')):
            with self.subTest(kind=kind):
                ledger=BatchLedger(f.root/f'producer-{index}.sqlite3',f.config('glm'),initialize=True)
                payload={'scope':'same-frozen-work','offline':index}
                tools=[{'type':'function','function':{'name':'answer','parameters':fixtures.SCHEMA}}]
                def invoke(value=payload):
                    gateway=ModelGateway(ledger)
                    if index==0:return model_decision(ledger,gateway,kind,value,fixtures.SCHEMA)
                    return model_tool_decision(ledger,gateway,kind,value,tools,system='Only answer the frozen request')
                before=len(f.opener.calls)
                with patch('webcollect.model_gateway.time.sleep'):
                    with self.assertRaises(OutcomeUnknown):invoke()
                self.assertEqual(len(f.opener.calls),before+1)
                with ledger.connect() as con:rows=[dict(r) for r in con.execute('SELECT * FROM model_requests')]
                self.assertEqual(len(rows),1);original=rows[0]
                self.assertEqual(original['state'],'unknown');self.assertIsNone(original['usage']);self.assertIsNone(original['cost'])
                with self.assertRaises(OutcomeUnknown):invoke()
                if index:
                    # The tool host owns the cross-job global gate. Query planner
                    # category/source isolation is covered by test_category_new_sites.
                    with self.assertRaises(OutcomeUnknown):invoke({**payload,'different_job':True})
                self.assertEqual(len(f.opener.calls),before+1)
                with ledger.connect() as con:
                    self.assertEqual(dict(con.execute('SELECT * FROM model_requests').fetchone()),original)


if __name__=='__main__':unittest.main()
