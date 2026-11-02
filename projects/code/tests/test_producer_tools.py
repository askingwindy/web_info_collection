"""Native lightweight producer with disposable SQLite and fake HTTP only."""
import json
import time
import unittest
from unittest.mock import patch

import test_candidate_inventory as inventory
import test_model_provider_protocols as providers
from site_planner.candidate_discovery import ENTRY_TOOL_PROTOCOL
from producer_legacy_fixture import produce_entries
from site_planner.candidate_pool import VERSION2
from site_planner.discovery_tools import reference
from webcollect.batch_core import BatchLedger, load_json
from webcollect.current_chain import initialize_chain
from webcollect.site_failure_stop import SiteFailureStore


class ProducerToolTests(unittest.TestCase):
    def setUp(self):
        self.inv = inventory.EntryInventory('test_mixed_batch_row_results_deficit_and_pool_growth')
        self.inv.setUp()
        self.addCleanup(self.inv.doCleanups)
        self.provider = providers.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        self.provider.setUp()
        self.addCleanup(self.provider.doCleanups)
        self.cfg = self.provider.config('glm', vision=True)
        self.cfg['model']['model'] = 'glm-5.3-flash'
        self.cfg['run_id'] = 'producer-tool-offline'
        root = self.inv.root.resolve()
        self.chain = root/'chain'/'manifest.json'
        initialize_chain(self.chain,root/'registry.sqlite3',chain_id='offline-producer',current_result_roots=[root/'output'])
        self.cfg['site_failure_guard'] = SiteFailureStore.initialize({'ledger':str(root/'site-stop.sqlite3'),
            'campaign_id':'offline-producer','formal_since':time.time()-1}).binding

    def response(self, rows, **kwargs):
        call = {'id':'provider-tool-id-7', 'type':'function',
                'function': {'name':'submit_candidates', 'arguments':json.dumps({'candidates':rows})}}
        call.update(kwargs)
        self.provider.opener.raw['choices'] = [{'finish_reason':'tool_calls', 'message':{
            'role':'assistant', 'content':None, 'reasoning_content':'opaque-not-for-report', 'tool_calls':[call]}}]

    def run_producer(self, sources, **kwargs):
        f = self.inv
        return produce_entries(self.cfg, history_set=self.chain, pool_path=f.pool.path, ledger_path=f.root/'model.db',
            output=f.root/'output', sources=sources, target=5, max_batches=1, batch_size=5,
            model_protocol=ENTRY_TOOL_PROTOCOL, **kwargs)

    def test_mixed_rows_bind_ids_source_and_actual_host_tool_result_without_ack_completion(self):
        f = self.inv
        duplicate = f.pool.put(f.entry('https://duplicate.example.org/'), f.source())
        hits = [f.hit(1, 'new1.example.org'), f.hit(2, 'new2.example.org'),
                {'uri':'https://duplicate.example.org/', 'title':'重复', 'content':'内容', 'reference':reference(f.proof)},
                f.hit(4, 'a.example.org'), f.hit(5)]
        self.response([{'source_index':0}, {'source_index':1,'suggested_goal':'invalid'},
                       {'source_index':2}, {'source_index':3,'application':'b.com'}, 'bad-row'])
        with patch('site_planner.candidate_discovery.glm_search', side_effect=AssertionError('explicit sources need no search')):
            report = self.run_producer(hits)
            replay = self.run_producer(hits)
        self.assertEqual(report['row_results'], {'NEW':2,'DUPLICATE':1,'REJECTED':2}, report)
        self.assertEqual(replay['listed_unique_candidates'], 2)
        self.assertEqual(report['deficit'], 3)
        self.assertEqual(len(self.provider.opener.calls), 1)
        payload = json.loads(self.provider.opener.calls[0].data)
        self.assertEqual(payload['tool_choice'], 'auto')
        self.assertEqual(payload['reasoning_effort'], 'low')
        self.assertEqual(payload['thinking'], {'type':'enabled','clear_thinking':False})
        self.assertEqual(len(payload['messages']), 2)
        context = json.loads(payload['messages'][1]['content'][0]['text'])
        self.assertIn('UNKNOWN', context['category_choices'])
        self.assertIn('在线工具', context['category_choices'])
        self.assertNotIn('instruction', context)
        self.assertLess(len(json.dumps(context,ensure_ascii=False).encode()), 2000)
        call = load_json(f.root/'output/batch-0000-tool-call.json')
        receipt = load_json(f.root/'output/batch-0000-tool-result.json')
        self.assertEqual(receipt['role'], 'tool')
        self.assertEqual(receipt['tool_call_id'], 'provider-tool-id-7')
        result = json.loads(receipt['content'])
        self.assertEqual(len(result['rows']), 5)
        self.assertEqual(result['model_request_id'], call['model_request_id'])
        for row in f.pool.rows(protocols=(VERSION2,)):
            source = row['sources'][-1]
            self.assertEqual(source['tool_call_id'], call['tool_call_id'])
            self.assertEqual(source['model_job_id'], call['model_job_id'])
            self.assertEqual(source['model_request_id'], call['model_request_id'])
            self.assertNotEqual(source['model_job_id'], source['model_request_id'])
            self.assertIn('explicit_source_index', source)
        self.assertEqual(len(f.rows_for(duplicate)['sources']), 2)
        self.assertNotIn('opaque-not-for-report', json.dumps(report))
        for artifact in (f.root/'output').glob('*.json'):
            self.assertNotIn('opaque-not-for-report', artifact.read_text())
        with BatchLedger(f.root/'model.db', self.cfg).connect() as con:
            rows = list(con.execute('SELECT id,state,usage FROM model_requests'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['state'], 'succeeded')
        self.assertIsNotNone(rows[0]['usage'])
        # The tool ID evidence participates in ordinary source hash verification.
        (f.root/'output/batch-0000-tool-call.json').write_text('{}')
        with self.assertRaises(ValueError):
            f.pool.rows(protocols=(VERSION2,))

    def test_wrong_tool_never_publishes_and_original_run_cannot_switch_protocol(self):
        f = self.inv
        hits = [f.hit(1)]
        self.response([{'source_index':0}])
        self.provider.opener.raw['choices'][0]['message']['tool_calls'][0]['function']['name'] = 'unregistered'
        report = self.run_producer(hits)
        self.assertEqual(report['listed_unique_candidates'], 0)
        self.assertEqual(f.pool.stats()['candidate_total'], 0)
        self.assertEqual(len(self.provider.opener.calls), 1)
        # Frozen failed model jobs are not replaced on resume.
        self.run_producer(hits)
        self.assertEqual(len(self.provider.opener.calls), 1)
        with self.assertRaises(ValueError):
            produce_entries(self.cfg, history_set=self.chain, pool_path=f.pool.path, ledger_path=f.root/'model.db',
                output=f.root/'output', sources=hits, target=5, max_batches=1, batch_size=5,
                model_protocol='entry-content-1')

    def test_fresh_glm_session_selects_native_tools_without_a_flag(self):
        f = self.inv
        self.response([{'source_index': 0}])
        report = produce_entries(self.cfg, history_set=self.chain, pool_path=f.pool.path, ledger_path=f.root/'model.db',
            output=f.root/'output', sources=[f.hit(1)], target=1, max_batches=1)
        self.assertEqual(report['listed_unique_candidates'], 1)
        self.assertEqual(json.loads(self.provider.opener.calls[0].data)['tool_choice'], 'auto')
        self.assertTrue((f.root/'output/batch-0000-tool-result.json').is_file())

    def test_unflagged_resume_preserves_frozen_content_session_without_http(self):
        f = self.inv
        self.provider.opener.raw['choices'] = [{'finish_reason': 'stop', 'message': {
            'content': json.dumps({'candidates': [{'source_index': 0}]})}}]
        args = dict(history_set=self.chain,pool_path=f.pool.path, ledger_path=f.root/'model.db', output=f.root/'output',
                    sources=[f.hit(1)], target=1, max_batches=1)
        first = produce_entries(self.cfg, model_protocol='entry-content-1', **args)
        resumed = produce_entries(self.cfg, **args)
        self.assertEqual((first['listed_unique_candidates'], resumed['listed_unique_candidates']), (1, 1))
        self.assertEqual(len(self.provider.opener.calls), 1)
        self.assertNotIn('tools', json.loads(self.provider.opener.calls[0].data))

    def test_source_search_request_and_model_request_are_distinct(self):
        f = self.inv
        self.response([{'source_index':0}])
        def search(*args, **kwargs):
            # Original provider search identity is independent of the model job.
            return {'request_id':'original-search-request', 'results':[dict(f.hit(1),index=9)]}
        with patch('site_planner.candidate_discovery.glm_search', side_effect=search):
            report = self.run_producer([], queries=['中文检索'])
        self.assertEqual(report['listed_unique_candidates'], 1, report)
        source = f.pool.rows(protocols=(VERSION2,))[0]['sources'][0]
        self.assertEqual(source['search_request_id'], 'original-search-request')
        self.assertEqual(source['raw_hit_index'], 9)
        self.assertEqual(source['source_index'], 0)
        self.assertNotEqual(source['search_request_id'], source['model_request_id'])

    def test_partial_native_publication_resumes_original_tool_call_with_zero_new_http(self):
        from site_planner.candidate_pool import CandidatePool
        f = self.inv
        self.response([{'source_index':0},{'source_index':1}])
        hits = [f.hit(1,'first.example.org'),f.hit(2,'second.example.org')]
        publish = CandidatePool.publish_row
        counter = [0]
        def stop_second(pool, *args, **kwargs):
            counter[0] += 1
            if counter[0] == 2:
                raise OSError('controlled interruption after one committed row')
            return publish(pool, *args, **kwargs)
        with patch.object(CandidatePool,'publish_row',stop_second):
            interrupted = self.run_producer(hits)
        self.assertEqual(interrupted['stopped']['type'],'OSError')
        self.assertEqual(f.pool.stats()['candidate_total'],1)
        with patch('webcollect.model_gateway.socket.getaddrinfo',side_effect=AssertionError('resume must use original tool response')):
            resumed = self.run_producer(hits)
        self.assertEqual(resumed['listed_unique_candidates'],2,resumed)
        self.assertEqual(resumed['row_results'],{'NEW':2})
        self.assertEqual(f.pool.stats()['candidate_total'],2)
        self.assertEqual(len(self.provider.opener.calls),1)
        receipt = load_json(f.root/'output/batch-0000-tool-result.json')
        self.assertEqual(receipt['tool_call_id'],'provider-tool-id-7')
        self.assertEqual(len(json.loads(receipt['content'])['rows']),2)


if __name__ == '__main__':
    unittest.main()
