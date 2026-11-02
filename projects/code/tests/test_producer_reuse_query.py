"""Project checks and category-only formal entry, all external I/O controlled."""
from concurrent.futures import ThreadPoolExecutor
import json
import socket
import unittest
from unittest.mock import patch

import test_grounded_producer as grounded_fixture
from site_planner import entry_access as access
from site_planner.candidate_discovery import produce_entries
from site_planner.discovery_tools import reference
from webcollect.batch_core import BatchLedger, OutcomeUnknown, save_json


class ProducerReuseQuery(unittest.TestCase):
    def setUp(self):
        self.f=grounded_fixture.Grounded('test_formal_CLI_seed_expansion_rules_provenance_and_restart_zero_IO')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root
        self.ledger=BatchLedger(self.root/'checks.db',self.f.f.cfg,initialize=True)
        self.addCleanup(patch.stopall)
        patch('socket.create_connection',side_effect=AssertionError('network forbidden')).start()

    def test_403_404_cross_batch_and_restart(self):
        for status in (403,404):
            uri='https://checks.example.org/'+str(status)
            with patch.object(access,'fetch_status',return_value=(status,uri)) as fetch:
                first=access.check_entry(self.ledger,'one',uri,self.root)
                second=access.check_entry(BatchLedger(self.ledger.path,self.ledger.config),'two',uri,self.root)
            self.assertEqual(first,second);self.assertEqual(fetch.call_count,1)
            self.assertEqual(first[0]['http_status'],status)

    def test_concurrent_batches_single_dispatch(self):
        import threading
        entered=threading.Event();release=threading.Event()
        uri='https://checks.example.org/concurrent'
        def fetch(*args):entered.set();release.wait(5);return 404,uri
        with patch.object(access,'fetch_status',side_effect=fetch) as get,ThreadPoolExecutor(2) as executor:
            first=executor.submit(access.check_entry,self.ledger,'one',uri,self.root)
            self.assertTrue(entered.wait(5))
            with self.assertRaises(OutcomeUnknown):access.check_entry(self.ledger,'two',uri,self.root)
            release.set();receipt=first.result()
            self.assertEqual(access.check_entry(self.ledger,'three',uri,self.root),receipt)
            self.assertEqual(get.call_count,1)

    def test_unknown_and_inflight_no_replacement(self):
        uri='https://checks.example.org/unknown'
        jid=access.shared_job(self.ledger,'one',uri)
        self.ledger.claim('candidate-entry-http',job_id=jid)
        with patch.object(access,'fetch_status',side_effect=AssertionError('must not send')):
            with self.assertRaises(OutcomeUnknown):access.check_entry(self.ledger,'two',uri,self.root)

    def test_recheck_requires_evidence_and_is_idempotent(self):
        uri='https://checks.example.org/recheck'
        with patch.object(access,'fetch_status',return_value=(404,uri)):
            original=access.check_entry(self.ledger,'one',uri,self.root)
        with self.assertRaises(ValueError):access.check_entry(self.ledger,'two',uri,self.root,recheck={'reason':'try again'})
        evidence=self.root/'changed.json';save_json(evidence,{'source':'first-party link corrected'})
        authorization={'condition':'source_or_access_changed','reason':'first party correction','references':[reference(evidence)]}
        with patch.object(access,'fetch_status',return_value=(200,uri)) as fetch:
            one=access.check_entry(self.ledger,'two',uri,self.root,recheck=authorization)
            two=access.check_entry(self.ledger,'three',uri,self.root,recheck=authorization)
        self.assertEqual(one,two);self.assertNotEqual(one[1],original[1]);self.assertEqual(fetch.call_count,1)

    def test_temporary_fault_elapsed_and_hash_routes_share_get(self):
        uri='https://checks.example.org/temporary?business=1'
        with patch.object(access,'fetch_status',return_value=(503,uri)) as fetch:
            first=access.check_entry(self.ledger,'one',uri+'#/a',self.root)
            self.assertEqual(access.check_entry(self.ledger,'two',uri+'#/b',self.root),first)
        self.assertEqual(fetch.call_count,1)
        evidence=self.root/'temporary.json';save_json(evidence,{'incident':'planned maintenance ended'})
        authorization={'condition':'temporary_fault_elapsed','not_before':10**20,'reason':'maintenance',
                       'references':[reference(evidence)]}
        with self.assertRaises(ValueError):access.check_entry(self.ledger,'two',uri,self.root,recheck=authorization)
        authorization['not_before']=0
        with patch.object(access,'fetch_status',return_value=(200,uri)) as fetch:
            receipt=access.check_entry(self.ledger,'two',uri,self.root,recheck=authorization)
        self.assertEqual(receipt[0]['result'],'PASS');self.assertEqual(fetch.call_count,1)

    def test_category_formal_entry_plan_classify_select_pool_and_restart(self):
        aid,home=self.f.site(confirmed=False)
        calls=[]
        def model(gateway,job,purpose,text,schema,**kwargs):
            payload=json.loads(text);calls.append(payload)
            request=gateway.ledger.reserve_request(job,purpose,1,{'fixture':True})
            value={'queries':['中文科学计算器 在线使用']}
            gateway.ledger.settle_request(request['id'],state='succeeded',response=value,
                usage={'input_tokens':1,'output_tokens':1,'cached_input_tokens':0})
            return value
        def provider_response(request,timeout):
            import io
            from copy import deepcopy
            payload=json.loads(request.data)
            if 'search_query' in payload:
                return io.BytesIO(json.dumps({'search_result':[{'link':home['uri'],'title':home['title'],'content':home['content']}]}).encode())
            context=json.loads(payload['messages'][1]['content'][0]['text'])
            args={'parent_category':'在线工具','quote_ids':[context['quote_choices'][0]['id']],'reason':'首页主营原文'}
            raw=deepcopy(self.f.f.provider.opener.raw)
            raw['choices']=[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                'tool_calls':[{'id':'offline-site','type':'function','function':{'name':'submit_site_classification','arguments':json.dumps(args)}}]}}]
            return io.BytesIO(json.dumps(raw).encode())
        patch.object(self.f.f.provider.opener,'open',side_effect=provider_response).start()
        args=dict(pool_path=self.f.pool.path,ledger_path=self.root/'model.db',history_set=self.f.f.chain,
            output=self.root/'output/category',batch_key='category',categories=['在线工具'],target=1,
            max_batches=1,max_searches=1,model_protocol='entry-tools-3')
        # Search transport is controlled; Table1 classification still uses the existing fake provider.
        from site_planner import grounded_entries as g
        with patch('webcollect.model_gateway.ModelGateway.call',new=model), patch('site_planner.application_discovery.homepage_document',return_value=(home,home['reference'])):
            report=produce_entries(self.f.f.cfg,**args)
            replay=produce_entries(self.f.f.cfg,**args)
        self.assertEqual(report['listed_unique_candidates'],1,report)
        self.assertEqual(report['supply_counts'],{'pending_lead_first_output':1})
        self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})
        self.assertEqual(len(calls),1);self.assertEqual(report['new_dispatches']['search'],1)
        self.assertEqual(report['search_usage'],[{'state':'succeeded','count':1}])
        self.assertEqual(calls[0]['categories'],['在线工具'])
