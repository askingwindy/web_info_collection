"""Producer v5 disposable evidence, ranking and formal-entry regression."""
import io
import json
from copy import deepcopy
from unittest.mock import patch

import test_grounded_producer as fixture
from site_planner import grounded_entries as g
from site_planner.application_discovery import classify_homepage
from site_planner.producer_evidence import numbered_homepage, homepage_material, diverse_order, business_signature, consumer_feedback
from site_planner.discovery_tools import reference
from webcollect.batch_core import BatchLedger, save_json


class Evidence(fixture.unittest.TestCase):
    def setUp(self):
        self.f=fixture.Grounded('test_formal_CLI_seed_expansion_rules_provenance_and_restart_zero_IO')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.ledger=BatchLedger(self.f.root/'model.db',self.f.f.cfg,initialize=True)

    def test_numbered_material_preserves_original_union_without_body_duplication(self):
        doc={'content':'主营中文工具\n'+'目录入口\n'*800+'第一方业务补充\n','uri':'https://example.org/','reference':{}}
        menu=numbered_homepage(doc,['主营中文工具','第一方业务补充'])
        self.assertEqual(list(menu.values()).count('主营中文工具'),1)
        self.assertIn('第一方业务补充',menu.values())
        self.assertTrue(all(q in doc['content'] for q in menu.values()))
        self.assertLess(len(json.dumps(menu,ensure_ascii=False)),len(doc['content'][:4000]))

    def test_classifier_v4_only_numbered_material_and_exact_host_binding(self):
        aid,home=self.f.site(confirmed=False);seen=[]
        def response(request,timeout):
            body=json.loads(request.data);ctx=json.loads(body['messages'][1]['content'][0]['text']);seen.append(ctx)
            self.assertNotIn('text',ctx);self.assertNotIn('quote_choices',ctx)
            self.assertIn('[q0]',ctx['homepage_material']);q={'id':'q0'}
            raw=deepcopy(self.f.f.provider.opener.raw)
            raw['choices']=[{'finish_reason':'tool_calls','message':{'tool_calls':[{'id':'classified','type':'function',
                'function':{'name':'submit_site_classification','arguments':json.dumps({'parent_category':'在线工具','quote_ids':[q['id']],'reason':'主营工具'})}}]}}]
            return io.BytesIO(json.dumps(raw).encode())
        ledger=self.ledger
        with patch.object(self.f.f.provider.opener,'open',side_effect=response):
            result=classify_homepage(self.f.pool,ledger,home,self.f.t.docs,protocol='producer-site-classification-4')
        self.assertEqual(result['classification_state'],'confirmed')
        self.assertEqual(seen[0]['homepage_material'],'[q0]'+home['content'])

    def test_classifier_unknown_retains_receipt_without_table1_guess(self):
        aid,home=self.f.site(confirmed=False)
        result={'arguments':{'parent_category':'UNKNOWN','quote_ids':[],'reason':'缺证'},'request_id':'r','tool_call_id':'t'}
        with patch('site_planner.discovery_agent.model_tool_decision',return_value=('offline',result)):
            with self.assertRaisesRegex(ValueError,'UNKNOWN'):
                classify_homepage(self.f.pool,self.ledger,home,self.f.t.docs,protocol='producer-site-classification-4')
        self.assertTrue((self.f.t.docs/'site-classification-offline.json').is_file())
        self.assertNotEqual(self.f.t.sites.get(aid)['classification_state'],'confirmed')

    def test_classifier_rejects_unbound_number(self):
        _,home=self.f.site(confirmed=False)
        result={'arguments':{'parent_category':'在线工具','quote_ids':['q999'],'reason':'缺证'},'request_id':'r','tool_call_id':'t'}
        with patch('site_planner.discovery_agent.model_tool_decision',return_value=('offline',result)):
            with self.assertRaisesRegex(ValueError,'outside original'):
                classify_homepage(self.f.pool,self.ledger,home,self.f.t.docs,protocol='producer-site-classification-4')

    def test_unknown_gets_fifth_slot_and_same_template_keeps_all_identities(self):
        links=[{'uri':f'https://example.org/book/{i}.html','anchor':'图书详情','page_type':'内容详情','ranking_reason':{'deprioritized':False}} for i in range(8)]
        links += [{'uri':'https://example.org/form','anchor':'表单示例','page_type':'功能页','ranking_reason':{'deprioritized':False}},
                  {'uri':'https://example.org/mystery','anchor':'未判入口','page_type':'UNKNOWN','ranking_reason':{'deprioritized':False}}]
        result=diverse_order(links)
        self.assertIn('UNKNOWN',[h['page_type'] for h in result[:5]])
        self.assertIn('https://example.org/form',[h['uri'] for h in result[:2]])
        self.assertEqual(len(result),len(links));self.assertEqual(business_signature(links[0]),business_signature(links[1]))

    def test_v5_formal_publish_restart_reuses_original_no_io(self):
        _,home=self.f.site()
        opts=dict(key='v5',target=2,model_protocol='entry-tools-5')
        first=self.f.run_new(home,**opts);replay=self.f.run_new(home,**opts)
        self.assertEqual(first['listed_unique_candidates'],2,first)
        self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})
        self.assertEqual(replay['candidate_ids'],first['candidate_ids'])
        self.assertEqual(consumer_feedback(self.f.pool)['consumer_signals'],[])

    def test_model_v5_bound_rows_keep_unknown_and_compact_template_hints(self):
        _,home=self.f.site();links=g.extract_links(home)
        def answer(ledger,gateway,purpose,payload,tools,**kwargs):
            self.assertEqual(payload['version'],'entry-tools-5')
            self.assertIsInstance(payload['business_hints'][0]['template'],int)
            self.assertIn('Hi8',kwargs['system']);self.assertIn('京东',kwargs['system'])
            return 'job',{'request_id':'request','tool_call_id':'tool','arguments':{'entries':[{'row':0,'type':4,'quote':0}]}}
        with patch.object(g,'model_tool_decision',side_effect=answer):
            rows,receipt=g.id_selection(self.ledger,links,'offline',protocol='entry-tools-5')
        self.assertEqual(rows[0]['page_type'],'UNKNOWN');self.assertEqual(rows[0]['quote'],links[0]['anchor'])
        self.assertEqual(len(g.bind_decisions(rows,links)),1)

    def test_original_consumer_versions_saved_and_engine_faults_are_separate(self):
        _,home=self.f.site();report=self.f.run_new(home,key='feedback',target=4)
        ids=report['candidate_ids'];pool=self.f.pool
        for i,cid in enumerate(ids):
            claim=pool.claim_next('w'+str(i),'r'+str(i),candidate_id=cid,protocols=('webcollect-data-candidate-2',))
            reason=['source_scene_mismatch','EvidenceStale: capture failed','HTTP 403 browser error',None][i]
            pool.finish(claim,state='failed',stage='saved' if i==3 else 'observation',reason=reason or 'saved fixture')
            if i==3:
                dest=self.f.t.docs/'saved.json';save_json(dest,{'sample_id':'sample'})
                with pool.transaction() as con:
                    con.execute('INSERT INTO candidate_results VALUES(?,?,?,?,?,?,?)',
                        (cid,claim['claim_id'],'sample',json.dumps({'save_receipt':reference(dest)}),'pending_review',None,1))
        # One binding has the wrong version and must never influence selection.
        with pool.transaction() as con:
            con.execute('UPDATE candidate_claims SET version=99 WHERE candidate_id=?',(ids[2],))
        result=consumer_feedback(pool)
        signals={r['candidate_id']:r for r in result['consumer_signals']}
        self.assertEqual(signals[ids[0]]['signal'],'source_mismatch')
        self.assertEqual(signals[ids[1]]['signal'],'neutral')
        self.assertNotIn(ids[2],signals)
        self.assertEqual(signals[ids[3]]['signal'],'saved_pending_review')
        self.assertEqual(signals[ids[3]]['version'],1);self.assertFalse(result['saved_is_qc_pass'])


if __name__=='__main__':fixture.unittest.main()
