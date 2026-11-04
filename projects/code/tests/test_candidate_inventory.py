"""Disposable, socket-blocked candidate producer/lease tests. No real IO."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from site_planner.site_pool import SitePool
from site_planner.candidate_pool import CandidatePool, CandidatePool as _Pool, VERSION, VERSION2, DDL as V1_DDL
from site_planner.candidate_discovery import produce, QueryPolicy
from producer_legacy_fixture import produce_entries
from site_planner.discovery_tools import reference
from webcollect.batch_core import load_json, save_json, OutcomeUnknown, BatchLedger


def mock_entry_http(test):
    return test.enterContext(patch('site_planner.entry_access.fetch_status',
                                   side_effect=lambda uri,*_: (200,uri)))


class Inventory(unittest.TestCase):
    def setUp(self):
        self.entry_http = mock_entry_http(self)
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        SitePool(self.root/'pool.db',initialize=True)
        self.pool=CandidatePool(self.root/'pool.db',install=True)
        self.proof=self.root/'source.json'; save_json(self.proof,{'CONTROLLED':'source only'})
        self.source={'origin':'codex_session','run_id':'offline','references':[reference(self.proof)]}
        self.network=patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden'))
        self.network.start(); self.addCleanup(self.network.stop)

    def candidate(self,n=0,**kw):
        return {'schema_version':VERSION,'entry_url':'https://example.org/','name':'受控离线站点',
            'parent_category':'图书文化','business_kind':'阅读','description':'搜索作品并查看详情',
            'target':{'kind':'search','entity':'book','parameters':{'query':str(n)}},**kw}

    def test_explicit_extension_no_old_page_conversion(self):
        other=self.root/'old.db'; pool=SitePool(other,initialize=True)
        pool.record({'schema_version':'webcollect-site-discovery-1','origin':'codex_session','run_id':'old',
            'event_id':'old','uri':'https://other.example/','name':'Old','category_hint':'图书文化','source_refs':[reference(self.proof)]})
        with self.assertRaises(Exception): CandidatePool(other)
        CandidatePool(other,install=True)
        self.assertEqual(CandidatePool(other).stats()['candidate_total'],0)
        self.assertEqual(pool.stats()['pages'],1)

    def test_metadata_rewrite_preserves_id_state_versions_and_claim_snapshot(self):
        cid=self.pool.put(self.candidate(),self.source)
        claim=self.pool.claim_next('w','request')
        revised=self.candidate(parent_category='在线工具',business_kind='检索',description='改写描述')
        self.assertEqual(self.pool.put(revised,{**self.source,'run_id':'again'}),cid)
        row=self.pool.rows()[0]
        self.assertEqual(row['state'],'consuming');self.assertEqual(row['version'],2)
        self.assertEqual(self.pool.get_claim(claim['claim_id'])['snapshot']['parent_category'],'图书文化')
        self.assertEqual(len(row['sources']),2)
        self.pool.finish(claim,state='failed',reason='No plan',stage='planning')
        self.pool.put(revised,self.source)
        self.assertEqual(self.pool.claim_next('new','next')['state'],'EMPTY')

    def test_multibusiness_category_same_url_parameter_identity_and_normalization(self):
        first=self.pool.put(self.candidate(),self.source)
        variant=self.candidate();variant['target']['parameters']['query']=' Ａ  B '
        second=self.pool.put(variant,self.source)
        variant['target']['parameters']['query']='A B'
        self.assertEqual(self.pool.put(variant,self.source),second)
        movie=self.candidate(parent_category='学习教育',business_kind='电影')
        movie['target']['entity']='movie'
        self.pool.put(movie,self.source);self.pool.put(self.candidate(1),self.source)
        self.assertEqual(len(self.pool.rows()),4)
        self.assertEqual(self.pool.pool.stats()['applications'],1)
        self.assertEqual(self.pool.claim_next('w','cat',categories=['学习教育'])['snapshot']['business_kind'],'电影')

    def test_atomic_concurrent_claim_idempotency_and_expiry_fencing(self):
        self.pool.put(self.candidate(),self.source)
        with ThreadPoolExecutor(max_workers=8) as ex:
            results=list(ex.map(lambda i:CandidatePool(self.pool.path).claim_next('w'+str(i),'r'+str(i)),range(8)))
        winner=next(c for c in results if c['state']=='consuming')
        self.assertEqual(sum(c['state']=='consuming' for c in results),1)
        self.assertEqual(self.pool.claim_next(winner['worker_id'],winner['request_id'])['token'],winner['token'])
        with self.assertRaises(ValueError): self.pool.claim_next('foreign',winner['request_id'])
        with self.pool.transaction() as con: con.execute('UPDATE candidate_claims SET expires=0')
        with self.assertRaises(ValueError): self.pool.finish(winner,state='failed',reason='stale',stage='planning')
        self.assertEqual(self.pool.claim_next('another','other')['state'],'EMPTY')
        self.assertEqual(self.pool.stats()['reconcile'],1)
        with self.assertRaises(ValueError): self.pool.heartbeat(winner)

    def test_empty_and_incremental_inventory_no_producer_dependency(self):
        self.assertEqual(self.pool.claim_next('w','empty')['state'],'EMPTY')
        cid=self.pool.put(self.candidate(),self.source)
        self.assertEqual(self.pool.claim_next('w','empty')['state'],'EMPTY')
        self.assertEqual(CandidatePool(self.pool.path).claim_next('w','one')['candidate_id'],cid)
        self.assertEqual(self.pool.stats()['candidate_total'],1)

    def test_case_sensitive_parameters_and_program_assigned_identity(self):
        first=self.candidate();first['target']['parameters']['query']='ID-Ab'
        second=deepcopy(first);second['target']['parameters']['query']='ID-ab'
        self.assertNotEqual(self.pool.put(first,self.source),self.pool.put(second,self.source))
        with self.assertRaises(ValueError):self.pool.put({**first,'candidate_id':'AI-ID'},self.source)

    def test_explicit_candidate_claim_does_not_take_another_target(self):
        first=self.pool.put(self.candidate(1),self.source);second=self.pool.put(self.candidate(2),self.source)
        claim=self.pool.claim_next('w','specific',candidate_id=second)
        self.assertEqual(claim['candidate_id'],second)
        with self.assertRaises(ValueError):self.pool.claim_next('w','specific',candidate_id=first)
        self.assertEqual(self.pool.claim_next('w','other',candidate_id=first)['candidate_id'],first)

    def test_generic_page_rejected_and_explicit_correction_preserves_original_budget(self):
        row=self.candidate();row['target']={'kind':'web_page','entity':row['entry_url'],'parameters':{}}
        with self.assertRaises(ValueError):self.pool.put(row,self.source)
        sources=[{'uri':row['entry_url'],'reference':reference(self.proof)}]
        response={'candidates':[{'source_index':0,**{k:v for k,v in row.items() if k not in ('schema_version','entry_url')}}]}
        args=dict(pool_path=self.pool.path,ledger_path=self.root/'p.db',sources=sources,target=1,max_batches=1,batch_size=1)
        with patch('site_planner.candidate_pool.validate_target'),patch('webcollect.model_gateway.ModelGateway.call',return_value=response):
            original=produce(self.config(),output=self.root/'p',**args)
        report=next((self.root/'p').glob('report-*.json'))
        valid=self.candidate();response['candidates']=[{'source_index':0,**{k:v for k,v in valid.items() if k not in ('schema_version','entry_url')}}]
        with patch('webcollect.model_gateway.ModelGateway.call',return_value=response):
            fixed=produce(self.config(),output=self.root/'correction',correction=reference(report),**args)
        self.assertEqual(fixed['listed_unique_candidates'],1)
        self.assertEqual(self.pool.stats()['failed'],1);self.assertEqual(self.pool.stats()['pending'],1)
        ledger=BatchLedger(self.root/'p.db',self.config())
        with ledger.connect() as con:
            self.assertEqual(dict(con.execute('SELECT kind,SUM(amount) FROM resources GROUP BY kind')),
                             {'discovery_candidates':1,'probe_pages':1})
            # Both work units reuse the same original source GET.
            self.assertEqual(con.execute('SELECT COUNT(*) FROM top_level_visits').fetchone()[0],1)
        self.assertEqual(self.entry_http.call_count,1)
        self.assertEqual(self.pool.stats()['consumption_attempts'],0)

    def test_flags_normalization_preserves_values_rejects_conflict_and_unknown_recovery(self):
        from site_planner.candidate_discovery import normalize_candidate,reconcile_response
        row={'target':{'kind':'regex','entity':'expression','parameters':{'pattern':'[0-9]+'},'flags':'global'}}
        value,rules=normalize_candidate(row)
        self.assertEqual(value['target']['parameters']['flags'],'global')
        self.assertEqual(row['target']['flags'],'global');self.assertTrue(rules)
        row['target']['parameters']['flags']='ignore-case'
        with self.assertRaises(ValueError):normalize_candidate(row)
        ledger=BatchLedger(self.root/'unknown.db',self.config(),initialize=True)
        jid=ledger.enqueue('ai-candidate-list-1',{'input':{}});job=ledger.claim('ai-candidate-list-1',job_id=jid)
        req=ledger.reserve_request(job,'fixture',0);ledger.settle_request(req['id'],state='unknown',error='CONTROLLED')
        with self.assertRaises(ValueError):reconcile_response(self.config(),pool_path=self.pool.path,ledger_path=ledger.path,
            output=self.root/'no-recovery',request_id=req['id'])

    def config(self):
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        cfg['run_id']='candidate-producer-offline'; cfg['budget']['max_discovery_candidates']=1000; return cfg

    def test_producer_1000_batches_replay_state_preservation_and_no_browser(self):
        queries=[f'受控来源{i}' for i in range(20)]
        def search(pool,run,model,query,root,**kw):
            return {'request_id':query,'results':[{'uri':'https://example.org/','title':'来源','content':query,'reference':reference(self.proof)}]}
        calls=[]
        def model(job,purpose,prompt,schema,**kw):
            data=json.loads(prompt); calls.append(data['batch'])
            return {'candidates':[{'source_index':0,**{k:v for k,v in self.candidate(data['batch']*50+i).items() if k not in ('schema_version','entry_url')}} for i in range(50)]}
        with patch('site_planner.candidate_discovery.glm_search',side_effect=search), \
             patch('webcollect.model_gateway.ModelGateway.call',side_effect=model), \
             patch('site_planner.discovery_tools.DiscoveryBrowser.__aenter__',side_effect=AssertionError('No discovery browser')), \
             patch('site_planner.site_pool.SitePool.assess',side_effect=AssertionError('No assessment')):
            args=dict(pool_path=self.pool.path,ledger_path=self.root/'producer.db',output=self.root/'producer',queries=queries,target=1000)
            result=produce(self.config(),**args)
            self.assertEqual(result['listed_unique_candidates'],1000,result)
            claim=self.pool.claim_next('consumer','early');self.pool.finish(claim,state='failed',stage='planning',reason='CONTROLLED')
            self.assertEqual(produce(self.config(),**args)['listed_unique_candidates'],1000)
        self.assertEqual(len(calls),20);self.assertEqual(self.pool.stats()['candidate_total'],1000)
        self.assertEqual(self.pool.stats()['failed'],1)
        self.assertEqual(self.pool.pool.stats()['applications'],1)

    def test_unknown_model_never_resends_and_partial_batch_survives(self):
        counter=[]
        def model(job,purpose,prompt,schema,**kw):
            n=json.loads(prompt)['batch'];counter.append(n)
            if n: raise OutcomeUnknown('CONTROLLED UNKNOWN')
            return {'candidates':[{'source_index':0,**{k:v for k,v in self.candidate().items() if k not in ('schema_version','entry_url')}}]}
        src=[{'uri':'https://example.org/','title':'known','content':'source','reference':reference(self.proof)}]
        with patch('site_planner.candidate_discovery.glm_search',return_value={'results':src}),patch('webcollect.model_gateway.ModelGateway.call',side_effect=model):
            args=dict(pool_path=self.pool.path,ledger_path=self.root/'producer.db',output=self.root/'producer',queries=['first','second'],target=2)
            first=produce(self.config(),**args);second=produce(self.config(),**args)
        self.assertEqual(counter,[0,1]);self.assertEqual(first['listed_unique_candidates'],1)
        self.assertEqual(second['listed_unique_candidates'],1);self.assertEqual(self.pool.stats()['candidate_total'],1)
        self.assertEqual(second['stopped']['type'],'OutcomeUnknown')

    def test_invented_source_index_rejected_no_deep_url_and_bounded_target(self):
        src=[{'uri':'https://example.org/','reference':reference(self.proof)}]
        row={k:v for k,v in self.candidate().items() if k not in ('schema_version','entry_url')}
        with patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[{'source_index':10,**row}]}):
            r=produce(self.config(),pool_path=self.pool.path,ledger_path=self.root/'p.db',output=self.root/'p',sources=src,target=1000,max_batches=1)
        self.assertEqual(r['listed_unique_candidates'],0);self.assertEqual(r['batches'],1);self.assertEqual(len(r['rejected']),1)

    def wire(self,n=0,**extra):
        row={k:v for k,v in self.candidate(n).items() if k not in ('schema_version','entry_url')}
        return {'source_index':0,**row,**extra}

    def test_legacy_producer_rejects_http_status_before_inventory_write(self):
        self.entry_http.side_effect = lambda uri,*_: (403,uri)
        args = self.strict_args('legacy-http')
        with patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[self.wire(1),self.wire(2)]}):
            report = produce(self.config(),**args)
            self.assertEqual(report['listed_unique_candidates'],0,report)
            self.assertEqual(report['deficit'],2)
            self.assertEqual(len(report['rejected']),2)
            self.assertTrue(all(load_json(r['entry_http']['path'])['http_status']==403 for r in report['rejected']))
            self.assertEqual(self.pool.claim_next('legacy-consumer','empty-legacy'),{'state':'EMPTY'})
            produce(self.config(),**args)
        self.assertEqual(self.entry_http.call_count,1)

    def strict_args(self,key):
        return dict(pool_path=self.pool.path,ledger_path=self.root/'strict.db',output=self.root/key,
            sources=[{'uri':'https://example.org/','title':'受控来源','content':'书籍检索','reference':reference(self.proof)}],
            target=2,batch_size=2,max_batches=1,batch_key=key,strict=True)

    def test_strict_independent_batches_share_budget_replay_and_preserve_original_rows(self):
        responses=[{'candidates':[self.wire(1),self.wire(2)]},{'candidates':[self.wire(3),self.wire(4)]}]
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=responses) as call:
            first=produce(self.config(),**self.strict_args('one'))
            second=produce(self.config(),**self.strict_args('two'))
            replay=produce(self.config(),**self.strict_args('one'))
        self.assertEqual(call.call_count,2)
        self.assertEqual([first['listed_unique_candidates'],second['listed_unique_candidates'],replay['listed_unique_candidates']],[2,2,2])
        self.assertTrue(first['strict_raw_output']);self.assertEqual(self.pool.stats()['candidate_total'],4)
        ledger=BatchLedger(self.root/'strict.db',self.config())
        with ledger.connect() as con:
            self.assertEqual(dict(con.execute('SELECT kind,SUM(amount) FROM resources GROUP BY kind')),
                             {'discovery_candidates':4,'probe_pages':1})
            # Both work units reuse the same original source GET.
            self.assertEqual(con.execute('SELECT COUNT(*) FROM top_level_visits').fetchone()[0],1)
        self.assertEqual(self.entry_http.call_count,1)
        for row in self.pool.rows():self.assertEqual(row['sources'][0]['normalization'],[])

    def test_strict_wrong_count_flat_flags_generic_and_duplicate_publish_nothing(self):
        flags=self.wire(1);flags['target']['flags']='g'
        generic=self.wire(2);generic['target']['kind']='web_page'
        whitespace=self.wire(2);whitespace['name']='   '
        cases=[{'candidates':[self.wire(1)]},{'candidates':[flags,self.wire(2)]},
               {'candidates':[self.wire(1),generic]},{'candidates':[self.wire(1),self.wire(1)]},
               {'candidates':[self.wire(1),whitespace]}]
        for n,response in enumerate(cases):
            with patch('webcollect.model_gateway.ModelGateway.call',return_value=response):
                result=produce(self.config(),**self.strict_args('bad'+str(n)))
            self.assertEqual(result['listed_unique_candidates'],0,result)
            self.assertIsNotNone(result['stopped'])
            self.assertEqual(self.pool.stats()['candidate_total'],0)

    def test_strict_source_guard_filters_stopped_application_before_model(self):
        from webcollect.site_failure_stop import SiteFailureStore
        cfg=self.config();cfg['site_failure_guard']=SiteFailureStore.initialize({'ledger':str(self.root/'stop.db'),
            'campaign_id':'CONTROLLED','formal_since':time.time()-1}).binding
        args=self.strict_args('guard');args['sources'].append({'uri':'https://held.example.org/','reference':reference(self.proof)})
        def guard(uri):
            if 'held.example' in uri:raise ValueError('CONTROLLED original whole-app hold')
        with patch('webcollect.site_failure_stop.SiteFailureStore.guard',side_effect=guard), \
             patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[self.wire(1),self.wire(2)]}) as call:
            result=produce(cfg,**args)
        self.assertEqual(result['listed_unique_candidates'],2)
        self.assertEqual(len(result['excluded_sources']),1)
        payload=json.loads(call.call_args.args[2]);self.assertEqual(len(payload['sources']),1)

    def test_strict_prior_unknown_search_cannot_be_resent_in_new_session(self):
        self.pool.pool.freeze_run('old',{})
        rid,_=self.pool.pool.reserve_tool('old','search','unresolved query',{'search_query':'unresolved query'},maximum=1)
        self.pool.pool.settle_tool(rid,'unknown',{'outcome_and_charge':'UNKNOWN'})
        args=self.strict_args('unknown-search');args.pop('sources');args['queries']=['unresolved query']
        with patch('site_planner.candidate_discovery.glm_search',side_effect=AssertionError('No resend')):
            result=produce(self.config(),**args)
        self.assertEqual(result['stopped']['type'],'OutcomeUnknown')
        with self.pool.pool.connect() as con:self.assertEqual(con.execute('SELECT state FROM tool_requests WHERE id=?',(rid,)).fetchone()[0],'unknown')

    def test_strict_extra_unresolved_application_excluded_even_without_stop_projection(self):
        args=self.strict_args('missing-projection');args['excluded_applications']=['https://example.org/other/']
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=AssertionError('No model for held app')):
            result=produce(self.config(),**args)
        self.assertEqual(result['listed_unique_candidates'],0)
        self.assertEqual(len(result['excluded_sources']),1)
        self.assertIn('unresolved model',result['excluded_sources'][0]['reason'])

    def test_strict_foreign_application_from_article_rejected_before_publication(self):
        row=self.wire(1);row['target']['entity']='linked.example.net单位转换'
        with patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[row,self.wire(2)]}):
            result=produce(self.config(),**self.strict_args('foreign-app'))
        self.assertEqual(self.pool.stats()['candidate_total'],0)
        self.assertIn('another host',result['stopped']['reason'])
        from site_planner.candidate_discovery import validate_source_binding
        row['target']['entity']='example.org长度转换';validate_source_binding(row,{'uri':'https://www.example.org/tool/'})
        row['target']['entity']='Node.js文档';validate_source_binding(row,{'uri':'https://nodejs.org/'})

    def test_tool_source_triage_preserves_content_discovery_and_direct_tools(self):
        from site_planner.candidate_discovery import reference_article_for_tool_query
        article={'uri':'https://example.org/81422.html','title':'单位换算工具大全','content':'作者\n公开作者\n介绍其他工具'}
        self.assertTrue(reference_article_for_tool_query('在线工具 单位换算',article))
        self.assertFalse(reference_article_for_tool_query('阅读单位换算知识文章',article))
        direct={'uri':'https://example.org/converter/','title':'单位换算器大全','content':'长度 面积 温度 输入值'}
        self.assertFalse(reference_article_for_tool_query('在线工具 单位换算',direct))

    def test_strict_unknown_blocks_new_work_but_preserves_completed_cache_reads(self):
        with patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[self.wire(1),self.wire(2)]}):
            first=produce(self.config(),**self.strict_args('cached'))
        ledger=BatchLedger(self.root/'strict.db',self.config())
        jid=ledger.enqueue('ai-candidate-list-2',{'CONTROLLED':'unresolved different batch'})
        job=ledger.claim('ai-candidate-list-2',job_id=jid);request=ledger.reserve_request(job,'uncertain',0)
        ledger.settle_request(request['id'],state='unknown',error='CONTROLLED');ledger.finish(job,'review_required')
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=AssertionError('No dispatch')):
            cached=produce(self.config(),**self.strict_args('cached'))
            blocked=produce(self.config(),**self.strict_args('new'))
        self.assertEqual(cached['candidate_ids'],first['candidate_ids'])
        self.assertEqual(blocked['stopped']['type'],'OutcomeUnknown')
        with ledger.connect() as con:self.assertEqual(con.execute('SELECT state FROM model_requests').fetchone()[0],'unknown')


class EntryInventory(unittest.TestCase):
    """candidate-producer-3 / webcollect-data-candidate-2 offline acceptance."""

    def setUp(self):
        self.entry_http = mock_entry_http(self)
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name).resolve()
        SitePool(self.root/'pool.db',initialize=True)
        self.pool=CandidatePool(self.root/'pool.db',install=True)
        self.proof=self.root/'source.json'; save_json(self.proof,{'CONTROLLED':'entry source only'})
        self.network=patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden'))
        self.network.start(); self.addCleanup(self.network.stop)
        self.environ=patch.dict(os.environ,{'SYNTH_FAKE_SEARCH_KEY':'controlled-offline'})
        self.environ.start(); self.addCleanup(self.environ.stop)

    def config(self,run='entry-producer-offline'):
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        cfg['run_id']=run; cfg['budget']['max_discovery_candidates']=1000
        cfg['model']['api_key_env']='SYNTH_FAKE_SEARCH_KEY'; return cfg

    def source(self,**kw):
        return {'origin':'glm_agent','run_id':'entry-offline','references':[reference(self.proof)],**kw}

    def candidate(self,n=0,**kw):
        return {'schema_version':VERSION,'entry_url':'https://example.org/','name':'受控离线站点',
            'parent_category':'图书文化','business_kind':'阅读','description':'搜索作品并查看详情',
            'target':{'kind':'search','entity':'book','parameters':{'query':str(n)}},**kw}

    def entry(self,url,goal=None,kind='entry'):
        return {'schema_version':VERSION2,'candidate_kind':kind,'entry_url':url,'requested_goal':goal}

    def hit(self,n,host='example.org',**kw):
        return {'uri':f'https://{host}/p{n}','title':kw.pop('title',f'来源{n}'),
                'content':kw.pop('content','内容'),'reference':reference(kw.pop('proof',self.proof))}

    def rows_for(self,cid):
        return next(r for r in self.pool.rows(protocols=(VERSION2,)) if r['candidate_id']==cid)

    def rejected_reasons(self):
        with self.pool.pool.connect() as con:
            return [json.loads(r[0])['reason'] for r in con.execute(
                "SELECT record FROM candidate_batch_rows WHERE result='REJECTED'")]

    def test_explicit_search_scope_counts_only_its_batch_and_deduplicates_original_input(self):
        from webcollect.batch_core import BudgetStop
        pool = self.pool.pool
        first, _ = pool.reserve_tool('shared','search','a',{},maximum=1,batch_scope='first')
        pool.settle_tool(first,'succeeded',{'value':'a'})
        pool.checkpoint('first','entry-batch/0/input',{'kind':'search','search_request_id':first})
        self.assertEqual(pool.reserve_tool('shared','search','a',{},maximum=1,batch_scope='first'),(first,{'value':'a'}))
        second, _ = pool.reserve_tool('shared','search','b',{},maximum=2,batch_scope='first')
        with self.assertRaises(BudgetStop):
            pool.reserve_tool('shared','search','c',{},maximum=2,batch_scope='first')
        third, _ = pool.reserve_tool('shared','search','c',{},maximum=1,batch_scope='second')
        self.assertEqual(len({first,second,third}),3)

    def test_v1_pool_refuses_v2_writes_until_install_and_install_rolls_back(self):
        other=self.root/'v1.db'; SitePool(other,initialize=True)
        con=sqlite3.connect(other)
        for sql in V1_DDL: con.execute(sql)
        con.execute("INSERT INTO candidate_meta VALUES(1,'candidate-pool-1')"); con.commit()
        v1=CandidatePool(other)
        with self.assertRaises(ValueError):
            v1.put(self.entry('https://example.org/'),self.source())
        con.execute('CREATE TABLE candidate_batch_rows(x)'); con.commit()
        with self.assertRaises(sqlite3.OperationalError): CandidatePool(other,install=True)
        con2=sqlite3.connect(other)
        self.assertEqual(con2.execute('SELECT version FROM candidate_meta').fetchone()[0],'candidate-pool-1')
        self.assertNotIn('sources',[r[1] for r in con2.execute('PRAGMA table_info(candidate_claims)')])
        con.execute('DROP TABLE candidate_batch_rows'); con.commit()
        upgraded=CandidatePool(other,install=True)
        cid=upgraded.put(self.entry('https://example.org/'),self.source())
        self.assertEqual(upgraded.rows(protocols=(VERSION2,))[0]['candidate_id'],cid)
        self.assertEqual(CandidatePool(other).claim_next('legacy','l1')['state'],'EMPTY')

    def test_entry_url_identity_rules(self):
        base='https://example.org/catalog'
        route=self.pool.put(self.entry(base+'#/search'),self.source())
        self.assertEqual(self.pool.put(self.entry(base+'?utm_source=share#/search'),self.source()),route)
        self.assertEqual(self.pool.put(self.entry(base+'#!/search'),self.source()),route)
        plain=self.pool.put(self.entry(base),self.source())
        self.assertNotEqual(plain,route)
        self.assertEqual(self.pool.put(self.entry(base+'#section-1'),self.source()),plain)
        query=self.pool.put(self.entry(base+'?q=a&q2=b'),self.source())
        self.assertEqual(self.pool.put(self.entry(base+'?q2=b&q=a'),self.source()),query)
        self.assertNotEqual(self.pool.put(self.entry(base+'?q=a'),self.source()),query)
        self.assertEqual(len(self.pool.rows(protocols=(VERSION2,))),4)
        self.assertEqual(self.pool.pool.stats()['applications'],1)
        self.assertEqual(self.rows_for(route)['candidate']['entry_url'],base+'#/search')

    def test_claim_protocol_isolation_snapshot_freeze_and_appended_sources(self):
        old=self.pool.put(self.candidate(),self.source())
        entry1=self.pool.put(self.entry('https://one.example.org/'),self.source())
        legacy=self.pool.claim_next('legacy','l1')
        self.assertEqual(legacy['candidate_id'],old)
        self.assertEqual(legacy['snapshot']['schema_version'],VERSION)
        self.assertEqual(self.pool.claim_next('legacy','l2',candidate_id=entry1)['state'],'EMPTY')
        claim=self.pool.claim_next('entry-worker','e1',protocols=(VERSION2,))
        self.assertEqual(claim['candidate_id'],entry1)
        self.assertEqual(claim['snapshot']['candidate_kind'],'entry')
        self.assertEqual(len(claim['sources']),1)
        self.pool.put(self.entry('https://one.example.org/'),self.source(category_hint='在线工具',
            suggested_goal={'kind':'unit_convert','entity':'temperature','parameters':{'value':'100'}}))
        self.assertEqual(len(self.pool.get_claim(claim['claim_id'])['sources']),1)
        row=self.rows_for(entry1)
        self.assertEqual(len(row['sources']),2); self.assertEqual(row['state'],'consuming')
        replay=self.pool.claim_next('entry-worker','e1',protocols=(VERSION2,))
        self.assertEqual((replay['claim_id'],replay['token']),(claim['claim_id'],claim['token']))
        with self.pool.transaction() as con: con.execute('UPDATE candidate_claims SET expires=0')
        with self.assertRaises(ValueError): self.pool.finish(claim,state='failed',reason='stale',stage='planning')
        # Any later claim sweeps the expired lease into reconcile before scanning.
        self.assertEqual(self.pool.claim_next('entry-worker','e3',protocols=(VERSION2,))['state'],'EMPTY')
        self.pool.put(self.entry('https://one.example.org/'),self.source())
        self.assertEqual(self.rows_for(entry1)['state'],'reconcile')
        self.assertEqual(self.pool.claim_next('entry-worker','e4',protocols=(VERSION2,))['state'],'EMPTY')

    def test_concurrent_entry_claims_single_winner(self):
        ids=[self.pool.put(self.entry(f'https://c{i}.example.org/'),self.source()) for i in range(2)]
        with ThreadPoolExecutor(max_workers=8) as ex:
            results=list(ex.map(lambda i:_Pool(self.pool.path).claim_next('w'+str(i),'r'+str(i),protocols=(VERSION2,)),range(8)))
        self.assertEqual(sorted(c['candidate_id'] for c in results if c['state']=='consuming'),sorted(ids))
        self.assertEqual(sum(c['state']=='EMPTY' for c in results),6)

    def test_targets_from_caller_coexist_and_dedup_by_frozen_goal(self):
        goal1={'kind':'unit_convert','entity':'temperature','parameters':{'value':'25','from':'C','to':'F'}}
        goal2={'kind':'unit_convert','entity':'temperature','parameters':{'value':'0','from':'C','to':'F'}}
        t1=self.pool.put(self.entry('https://convert.example.org/units',goal1,kind='target'),self.source())
        t2=self.pool.put(self.entry('https://convert.example.org/units',goal2,kind='target'),self.source())
        self.assertNotEqual(t1,t2)
        self.assertEqual(self.pool.put(self.entry('https://convert.example.org/other',goal1,kind='target'),self.source()),t1)
        with self.assertRaises(ValueError): self.pool.put(self.entry('https://x.example.org/',goal1),self.source())
        with self.assertRaises(ValueError): self.pool.put(self.entry('https://x.example.org/',kind='target'),self.source())
        row=self.rows_for(t1)
        self.assertEqual(row['candidate']['requested_goal'],goal1)
        self.assertEqual(row['candidate']['entry_url'],'https://convert.example.org/units')

    def test_mixed_batch_row_results_deficit_and_pool_growth(self):
        dup='https://dup.example.org/tool'
        preset=self.pool.put(self.entry(dup),self.source())
        hits=[self.hit(1,'new1.example.org'),self.hit(2,'new2.example.org'),
              {'uri':dup,'title':'重复','content':'内容','reference':reference(self.proof)},
              {'uri':'https://a.example.org/tutorial','title':'工具推荐','content':'介绍','reference':reference(self.proof)},
              self.hit(3,'new3.example.org')]
        rows=[{'source_index':0,'requested_goal':{'kind':'convert','entity':'usurp','parameters':{}},'user_requires':True},
              {'source_index':1,'category_hint':'不存在的类目','suggested_goal':'broken'},
              {'source_index':2,'category_hint':'在线工具'},
              {'source_index':3,'application':'b.com换算器'},
              {'source_index':99}]
        with patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':rows}) as call:
            report=produce_entries(self.config(),pool_path=self.pool.path,ledger_path=self.root/'p.db',
                output=self.root/'out',sources=hits,target=5,max_batches=1,batch_size=5)
        self.assertEqual(report['row_results'],{'NEW':2,'DUPLICATE':1,'REJECTED':2},report)
        self.assertEqual(report['listed_unique_candidates'],2)
        self.assertEqual(report['deficit'],3); self.assertEqual(report['status'],'PARTIAL')
        self.assertEqual(self.pool.stats()['by_protocol'][VERSION2],3)
        self.assertEqual(len(json.loads(call.call_args.args[2])['sources']),5)
        new1=self.rows_for(next(r['candidate_id'] for r in self.pool.rows(protocols=(VERSION2,))
                                if 'new1.example.org' in r['candidate']['entry_url']))
        self.assertIsNone(new1['candidate']['requested_goal'])
        self.assertTrue(new1['sources'][0]['suggestion_issues'])
        self.assertEqual(len(self.rows_for(preset)['sources']),2)
        self.assertTrue(any('another application host' in r for r in self.rejected_reasons()))

    def test_empty_over_limit_and_corrupted_envelope(self):
        with patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[]}):
            empty=produce_entries(self.config(),pool_path=self.pool.path,ledger_path=self.root/'p.db',
                output=self.root/'empty',sources=[self.hit(1,'e.example.org')],target=3,max_batches=1)
        self.assertEqual(empty['row_results'],{}); self.assertEqual(empty['listed_unique_candidates'],0)
        self.assertEqual(empty['status'],'PARTIAL'); self.assertIsNone(empty['stopped'])
        hits=[self.hit(1,'o1.example.org'),self.hit(2,'o2.example.org')]
        with patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[{'source_index':0},{'source_index':1}]}):
            over=produce_entries(self.config('entry-producer-over'),pool_path=self.pool.path,
                ledger_path=self.root/'p2.db',output=self.root/'over',sources=hits,target=1,max_batches=1,batch_size=5)
        self.assertEqual(over['row_results'],{'NEW':1,'OVER_LIMIT':1},over)
        self.assertEqual(over['listed_unique_candidates'],1); self.assertEqual(over['deficit'],0)
        with patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':'not-a-list'}):
            broken=produce_entries(self.config('entry-producer-broken'),pool_path=self.pool.path,
                ledger_path=self.root/'p3.db',output=self.root/'broken',sources=[self.hit(1,'b.example.org')],
                target=1,max_batches=1)
        self.assertIsNotNone(broken['stopped'],broken)
        self.assertEqual(broken['row_results'],{})
        self.assertEqual(load_json(self.root/'broken'/'batch-0000-response.json'),{'candidates':'not-a-list'})
        self.assertEqual(self.pool.stats()['by_protocol'][VERSION2],1)

    def fake_search(self,responder):
        class Response:
            def __init__(self,body): self.body=body
            def read(self,n=-1): return self.body
            def __enter__(self): return self
            def __exit__(self,*a): return False
        class Opener:
            def open(self,request,timeout=None):
                return Response(json.dumps({'search_result':responder(json.loads(request.data)),
                                            'usage':{'total_tokens':1}}).encode())
        return patch('urllib.request.build_opener',side_effect=lambda *a,**k:Opener())

    def test_query_policy_switch_stall_rule_and_cache_no_resend(self):
        self.pool.put(self.entry('https://dup.example.org/converter'),self.source())
        self.pool.put(self.entry('https://dup.example.org/library'),self.source())
        directions=[{'direction':'单位换算','category':'在线工具','queries':['单位换算 在线换算器','长度换算 公斤磅换算']},
                    {'direction':'公共图书馆','category':'图书文化','queries':['公共图书馆 馆藏检索']},
                    {'direction':'词典范例','category':'学习教育','queries':['词典 在线查词','成语 在线查询']}]
        def responder(payload):
            query=payload['search_query']
            link=('https://dup.example.org/converter' if '换算' in query else
                  'https://dup.example.org/library' if '图书馆' in query else
                  'https://fresh1.example.org/' if '词典' in query else 'https://fresh2.example.org/')
            return [{'link':link,'title':query,'content':'内容'}]
        searches=[]
        def wrapped(payload):
            searches.append(payload['search_query']); return responder(payload)
        calls=[]
        def model(job,purpose,prompt,schema,**kw):
            calls.append(json.loads(prompt)['batch']); return {'candidates':[{'source_index':0,'category_hint':'在线工具'}]}
        env=self.fake_search(wrapped)
        with env, patch('webcollect.model_gateway.ModelGateway.call',side_effect=model):
            first=produce_entries(self.config(),pool_path=self.pool.path,ledger_path=self.root/'p.db',
                output=self.root/'r1',directions=directions,target=5,max_batches=4,batch_size=5)
        self.assertEqual([d['query'] for d in first['query_decisions']],
            ['单位换算 在线换算器','公共图书馆 馆藏检索','词典 在线查词','长度换算 公斤磅换算'])
        self.assertEqual(first['listed_unique_candidates'],1,first)
        self.assertEqual(first['row_results'],{'DUPLICATE':3,'NEW':1})
        with env, patch('webcollect.model_gateway.ModelGateway.call',side_effect=model):
            second=produce_entries(self.config(),pool_path=self.pool.path,ledger_path=self.root/'p.db',
                output=self.root/'r2',directions=directions,target=5,max_batches=1,batch_size=5,batch_key='continue')
        decision=[d for d in second['query_decisions'] if d['scope'].endswith('/continue')][-1]
        self.assertEqual(decision['query'],'成语 在线查询')
        self.assertEqual(decision['reason']['switched_from_stalled'],['单位换算'],decision)
        self.assertEqual(second['listed_unique_candidates'],1)
        self.assertEqual(searches,['单位换算 在线换算器','公共图书馆 馆藏检索','词典 在线查词',
                                    '长度换算 公斤磅换算','成语 在线查询'])
        with env, patch('webcollect.model_gateway.ModelGateway.call',side_effect=model):
            replay=produce_entries(self.config(),pool_path=self.pool.path,ledger_path=self.root/'p.db',
                output=self.root/'r2',directions=directions,target=5,max_batches=1,batch_size=5,batch_key='continue')
        self.assertEqual(replay['listed_unique_candidates'],1)
        self.assertEqual(len(searches),5)
        self.assertEqual(len(calls),5)
        self.assertEqual(self.pool.stats()['by_protocol'][VERSION2],4)

    def test_query_policy_unit_rules_directly(self):
        policy=QueryPolicy([{'direction':'A','category':'UNKNOWN','queries':['a1','a2','a3']},
                            {'direction':'B','category':'UNKNOWN','queries':['b1','b2']}],
                           stall_threshold=2,per_direction_cap=3)
        state=policy.initial_state()
        self.assertEqual(policy.next_query(state)['query'],'a1')
        state={'queries':{'a1':{'query':'a1','direction':'A','new_entries':0,'article_hits':0,'raw_hits':1},
                          'a2':{'query':'a2','direction':'A','new_entries':0,'article_hits':0,'raw_hits':1}},
               'order':['a1','a2'],'blocked':{},'version':'producer-query-policy-1',
               'stall_threshold':2,'per_direction_cap':3}
        switch=policy.next_query(state)
        self.assertEqual(switch['query'],'b1')
        self.assertEqual(switch['reason']['switched_from_stalled'],['A'])
        state['queries']['b1']={'query':'b1','direction':'B','new_entries':1,'article_hits':0,'raw_hits':1}
        state['order'].append('b1')
        resume=policy.next_query(state)
        self.assertEqual(resume['query'],'b2')
        self.assertEqual(resume['reason']['completed_in_direction'],1)
        state['queries']['b2']={'query':'b2','direction':'B','new_entries':0,'article_hits':0,'raw_hits':1}
        state['order'].append('b2')
        # Only the stalled direction still has terms: the stall rule is a stop condition.
        self.assertIsNone(policy.next_query(state))

    def test_search_unknown_blocks_same_query_only_and_auth_hold_blocks_all(self):
        directions=[{'direction':'A','category':'UNKNOWN','queries':['未知词一','可用词']}]
        class Failing:
            def open(self,request,timeout=None): raise OSError('controlled transport failure')
        class Serving:
            def open(self,request,timeout=None):
                return io.BytesIO(json.dumps({'search_result':[{'link':'https://fresh.example.org/','title':'t','content':'c'}],
                                              'usage':{}}).encode())
        with patch('urllib.request.build_opener',side_effect=lambda *a,**k:Failing()), \
             patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[{'source_index':0}]}):
            unknown=produce_entries(self.config(),pool_path=self.pool.path,ledger_path=self.root/'p.db',
                output=self.root/'u1',directions=directions,target=5,max_batches=1)
        self.assertEqual(unknown['stopped']['type'],'OutcomeUnknown',unknown)
        with self.pool.pool.connect() as con:
            states=dict(con.execute("SELECT json_extract(payload,'$.search_query'),state FROM tool_requests WHERE kind='search'").fetchall())
        self.assertEqual(states['未知词一'],'unknown')
        with patch('urllib.request.build_opener',side_effect=lambda *a,**k:Serving()), \
             patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[{'source_index':0}]}):
            recovered=produce_entries(self.config(),pool_path=self.pool.path,ledger_path=self.root/'p.db',
                output=self.root/'u2',directions=directions,target=5,max_batches=1,batch_key='recover')
        self.assertIsNone(recovered['stopped'],recovered)
        self.assertEqual(recovered['listed_unique_candidates'],1)
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tool_requests WHERE kind='search' AND json_extract(payload,'$.search_query')='未知词一'").fetchone()[0],1)
        import urllib.error as urlerror
        class Unauthorized:
            def open(self,request,timeout=None):
                raise urlerror.HTTPError('https://api',401,'Unauthorized',None,io.BytesIO(b''))
        auth_directions=[{'direction':'A','category':'UNKNOWN','queries':['词一','词二']}]
        with patch('urllib.request.build_opener',side_effect=lambda *a,**k:Unauthorized()):
            auth=produce_entries(self.config('entry-producer-auth'),pool_path=self.pool.path,
                ledger_path=self.root/'p2.db',output=self.root/'auth',
                directions=auth_directions,target=5,max_batches=1)
        self.assertEqual(auth['stopped']['type'],'OutcomeUnknown',auth)
        with patch('urllib.request.build_opener',side_effect=lambda *a,**k:Unauthorized()):
            blocked=produce_entries(self.config('entry-producer-auth'),pool_path=self.pool.path,
                ledger_path=self.root/'p2.db',output=self.root/'auth-retry',
                directions=auth_directions,target=5,max_batches=1,batch_key='retry')
        self.assertEqual(blocked['stopped']['type'],'AuthorizationHold',blocked)
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tool_requests WHERE kind='search'").fetchone()[0],3)

    def test_site_hold_excludes_at_search_stage_and_holds_before_write(self):
        from webcollect.site_failure_stop import SiteFailureStore, SiteStopped
        cfg=self.config()
        cfg['site_failure_guard']=SiteFailureStore.initialize({'ledger':str(self.root/'stop.db'),
            'campaign_id':'CONTROLLED','formal_since':time.time()-1}).binding
        def guard(uri):
            if 'held.example' in uri: raise SiteStopped('CONTROLLED whole-app hold')
        sources=[{'uri':'https://held.example.org/tool','title':'h','content':'c','reference':reference(self.proof)},
                 self.hit(1,'ok.example.org')]
        with patch('webcollect.site_failure_stop.SiteFailureStore.guard',side_effect=guard), \
             patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[{'source_index':0}]}) as call:
            excluded=produce_entries(cfg,pool_path=self.pool.path,ledger_path=self.root/'p.db',
                output=self.root/'excluded',sources=sources,target=2,max_batches=1,batch_size=5)
        self.assertEqual(excluded['excluded_search_stage'],1,excluded)
        self.assertEqual(len(json.loads(call.call_args.args[2])['sources']),1)
        self.assertEqual(excluded['row_results'],{'NEW':1})
        with patch('webcollect.site_failure_stop.SiteFailureStore.guard',side_effect=[None,SiteStopped('controlled new hold')]), \
             patch('webcollect.model_gateway.ModelGateway.call',return_value={'candidates':[{'source_index':0}]}):
            held=produce_entries(cfg,pool_path=self.pool.path,ledger_path=self.root/'p.db',
                output=self.root/'held',sources=[self.hit(1,'late.example.org')],target=1,max_batches=1,batch_key='late')
        self.assertEqual(held['row_results'],{'HELD':1},held)
        self.assertEqual(self.pool.stats()['by_protocol'][VERSION2],1)

    def test_interrupt_recovery_three_points_and_digest_evidence_guards(self):
        hits=[self.hit(i,f'recover{i}.example.org') for i in range(3)]
        rows=[{'source_index':i} for i in range(3)]
        calls=[]
        def model(job,purpose,prompt,schema,**kw):
            calls.append(json.loads(prompt)['batch']); return {'candidates':rows}
        real_publish=_Pool.publish_row
        def exit_after_accounting(self_,header,candidate,source,**kw):
            raise RuntimeError('CONTROLLED exit after accounting')
        args=dict(pool_path=self.pool.path,ledger_path=self.root/'p.db',sources=hits,target=3,max_batches=1,batch_size=5)
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=model), \
             patch.object(_Pool,'publish_row',autospec=True,side_effect=exit_after_accounting):
            first=produce_entries(self.config('entry-producer-recover-a'),output=self.root/'a',**args)
        self.assertEqual(first['row_results'],{})
        ledger=BatchLedger(self.root/'p.db',self.config('entry-producer-recover-a'))
        with ledger.connect() as con:
            self.assertEqual(con.execute("SELECT SUM(amount) FROM resources WHERE kind='discovery_candidates'").fetchone()[0],3)
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=model):
            recovered=produce_entries(self.config('entry-producer-recover-a'),output=self.root/'a',**args)
        self.assertEqual(recovered['row_results'],{'NEW':3},recovered)
        self.assertEqual(len(calls),1)
        with ledger.connect() as con:
            self.assertEqual(con.execute("SELECT SUM(amount) FROM resources WHERE kind='discovery_candidates'").fetchone()[0],3)
        self.assertEqual(self.pool.stats()['by_protocol'][VERSION2],3)
        SitePool(self.root/'pool2.db',initialize=True); pool2=CandidatePool(self.root/'pool2.db',install=True)
        def exit_mid_rows(self_,header,candidate,source,**kw):
            if exit_mid_rows.n==0:
                exit_mid_rows.n=1; return real_publish(self_,header,candidate,source,**kw)
            raise RuntimeError('CONTROLLED exit mid rows')
        exit_mid_rows.n=0
        args2=dict(pool_path=pool2.path,ledger_path=self.root/'p2.db',sources=hits,target=3,max_batches=1,batch_size=5)
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=model), \
             patch.object(_Pool,'publish_row',autospec=True,side_effect=exit_mid_rows):
            partial=produce_entries(self.config('entry-producer-recover-b'),output=self.root/'b',**args2)
        self.assertEqual(partial['row_results'],{})
        self.assertIsNotNone(partial['stopped'])
        self.assertEqual(pool2.stats()['by_protocol'][VERSION2],1)
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=model):
            filled=produce_entries(self.config('entry-producer-recover-b'),output=self.root/'b',**args2)
        self.assertEqual(filled['row_results'],{'NEW':3})
        self.assertEqual(pool2.stats()['by_protocol'][VERSION2],3)
        self.assertEqual(len(calls),2)
        SitePool(self.root/'pool3.db',initialize=True); pool3=CandidatePool(self.root/'pool3.db',install=True)
        real_cp=SitePool.checkpoint
        def drop_commit(self_,run_id,key,value=None):
            if value is not None and key.endswith('/committed'):
                raise RuntimeError('CONTROLLED exit before commit record')
            return real_cp(self_,run_id,key,value)
        args3=dict(pool_path=pool3.path,ledger_path=self.root/'p3.db',sources=hits,target=3,max_batches=1,batch_size=5)
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=model),patch.object(SitePool,'checkpoint',drop_commit):
            uncommitted=produce_entries(self.config('entry-producer-recover-c'),output=self.root/'c',**args3)
        self.assertIsNotNone(uncommitted['stopped'])
        self.assertEqual(pool3.stats()['by_protocol'][VERSION2],3)
        with pool3.pool.connect(write=True) as con:
            con.execute("UPDATE candidate_batch_rows SET response_sha256='tampered'"); con.commit()
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=model):
            tampered=produce_entries(self.config('entry-producer-recover-c'),output=self.root/'c',**args3)
        self.assertIn('Original response row changed',tampered['stopped']['reason'])
        self.assertEqual(len(calls),3)

    def test_concurrent_duplicate_sources_add_once_and_evidence_tamper_stops(self):
        hits=[self.hit(1,'shared.example.org')]
        rows=[{'source_index':0},{'source_index':0}]
        def model(job,purpose,prompt,schema,**kw): return {'candidates':rows}
        args=dict(pool_path=self.pool.path,ledger_path=self.root/'p.db',sources=hits,target=2,max_batches=1,batch_size=5)
        reports=[]
        # The shared ledger exists before both writers start; concurrent first
        # creation is a BatchLedger race outside this producer's contract.
        BatchLedger(self.root/'p.db',self.config('entry-producer-concurrent'),initialize=True)
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=model):
            with ThreadPoolExecutor(max_workers=2) as ex:
                reports=list(ex.map(lambda i: produce_entries(self.config('entry-producer-concurrent'),
                    output=self.root/'cc',**args),range(2)))
        # Concurrent duplicate sources add exactly one inventory candidate;
        # each writer's own report may still count the shared NEW row.
        union={cid for r in reports for cid in r['candidate_ids']}
        self.assertEqual(len(union),1,reports)
        self.assertEqual(self.pool.stats()['by_protocol'][VERSION2],1)
        tamper=self.root/'tamper-proof.json'; save_json(tamper,{'v':1})
        real_publish=_Pool.publish_row
        def once(self_,header,candidate,source,**kw):
            if once.n==0:
                once.n=1; return real_publish(self_,header,candidate,source,**kw)
            raise RuntimeError('CONTROLLED exit mid rows')
        once.n=0
        hits2=[self.hit(2,'tamper.example.org',proof=tamper)]
        args2=dict(pool_path=self.pool.path,ledger_path=self.root/'p2.db',sources=hits2,target=1,max_batches=1,batch_size=5)
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=model), \
             patch.object(_Pool,'publish_row',autospec=True,side_effect=once):
            produce_entries(self.config('entry-producer-tamper'),output=self.root/'t1',**args2)
        tamper.write_text(json.dumps({'v':2},ensure_ascii=False))  # deliberate evidence tamper
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=model):
            stopped=produce_entries(self.config('entry-producer-tamper'),output=self.root/'t1',**args2)
        self.assertIsNotNone(stopped['stopped'])
        self.assertIn('SHA',stopped['stopped']['reason'])

    def test_thousand_unique_entries_without_full_pool_entity_reads(self):
        sources=[self.hit(0,f'bulk{i}.org') for i in range(1000)]
        def model(job,purpose,prompt,schema,**kw):
            return {'candidates':[{'source_index':i} for i in range(50)]}
        traces=[]
        real_connect=sqlite3.connect
        def traced(*a,**k):
            con=real_connect(*a,**k)
            con.set_trace_callback(lambda sql: traces.append(sql) if 'FROM data_candidates' in sql else None)
            return con
        with patch('sqlite3.connect',side_effect=traced), \
             patch.object(CandidatePool,'rows',side_effect=AssertionError('full pool candidate entity load forbidden')), \
             patch.object(SitePool,'rows',side_effect=AssertionError('full pool site entity load forbidden')), \
             patch('webcollect.model_gateway.ModelGateway.call',side_effect=model) as call:
            args=dict(pool_path=self.pool.path,ledger_path=self.root/'p.db',sources=sources,target=1000,
                      max_batches=20,batch_size=50)
            cfg=self.config('entry-producer-bulk'); cfg['budget']['max_probe_pages']=1000
            bulk=produce_entries(cfg,output=self.root/'bulk',**args)
            replay=produce_entries(cfg,output=self.root/'bulk',**args)
        self.assertEqual(bulk['listed_unique_candidates'],1000,bulk)
        self.assertEqual(replay['listed_unique_candidates'],1000)
        self.assertEqual(call.call_count,20)
        self.assertEqual(self.pool.stats()['candidate_total'],1000)
        self.assertEqual(self.pool.pool.stats()['applications'],1000)
        full_scans=[sql for sql in traces if sql.strip().upper().startswith('SELECT *') and 'WHERE' not in sql.upper()]
        self.assertEqual(full_scans,[],full_scans)

    def test_caller_goals_do_not_bypass_http_or_repeat_unknown_visits(self):
        cfg = self.config('offline-explicit-access')
        path = self.root/'goals-http.json'
        uris = ['https://forbidden.example.org/a','https://missing.example.net/b',
                'https://slow.example.edu/c','https://slow.example.edu/c']
        save_json(path,{'schema_version':'webcollect-caller-goals-1','goals':[
            {'uri':uri,'requested_goal':{'kind':'search','entity':'books','parameters':{'term':str(i)}}}
            for i,uri in enumerate(uris)]})
        def status(uri,*_):
            if uri==uris[2]: raise TimeoutError('controlled connection timeout')
            return (403 if uri==uris[0] else 404),uri
        self.entry_http.side_effect = status
        args = dict(pool_path=self.pool.path,ledger_path=self.root/'access.db',goals_path=path,
                    target=4,max_batches=1,output=self.root/'goal-output')
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=AssertionError('No model for caller goals')):
            report = produce_entries(cfg,**args)
            rows = self.pool.batch_rows(report['batch_scope'],-1)
            self.assertEqual(report['row_results'],{'REJECTED':2,'HELD':2},report)
            self.assertEqual(report['explicit_target_candidates'],0)
            self.assertEqual(report['listed_unique_candidates'],0)
            self.assertEqual(self.pool.claim_next('worker','empty',protocols=(VERSION2,)),{'state':'EMPTY'})
            first = [load_json(r['entry_http']['path']) for r in rows]
            self.assertEqual([r['http_status'] for r in first],[403,404,None,None])
            self.assertEqual(rows[2]['entry_http'],rows[3]['entry_http'])
            self.assertEqual(produce_entries(cfg,**args)['row_results'],report['row_results'])
            self.assertEqual(self.entry_http.call_count,3)
            visits=BatchLedger(args['ledger_path'],cfg).visits()
            self.assertEqual([v['state'] for v in visits],['failed','failed','unknown'])

    def test_caller_goals_publish_targets_without_model(self):
        goals=self.root/'goals.json'
        save_json(goals,{'schema_version':'webcollect-caller-goals-1','goals':[
            {'uri':'https://convert.example.org/units','requested_goal':{'kind':'unit_convert','entity':'temperature','parameters':{'value':'25','from':'C','to':'F'}}},
            {'uri':'https://convert.example.org/units','requested_goal':{'kind':'unit_convert','entity':'temperature','parameters':{'value':'0','from':'C','to':'F'}}}]})
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=AssertionError('No model for caller goals')):
            report=produce_entries(self.config('entry-producer-goals'),pool_path=self.pool.path,
                ledger_path=self.root/'p.db',output=self.root/'goals',goals_path=goals,target=2,max_batches=1)
        self.assertEqual(report['explicit_target_candidates'],2)
        self.assertEqual(self.entry_http.call_count,1)
        self.assertEqual(len(self.pool.batch_rows(report['batch_scope'],-1)),2)
        self.assertEqual(report['listed_unique_candidates'],2)
        self.assertEqual(report['status'],'TARGET_REACHED')
        rows=self.pool.rows(protocols=(VERSION2,))
        self.assertTrue(all(r['candidate']['candidate_kind']=='target' and r['candidate']['requested_goal'] for r in rows))
        source=rows[0]['sources'][0]
        self.assertEqual(source['goal_origin'],'caller')
        self.assertTrue(source['caller_input']['sha256'])

    def test_handoff_samples_cover_both_protocols_and_mismatch(self):
        from site_planner.candidate_handoff import build_samples
        samples=build_samples(self.root/'handoff.db',self.root/'handoff-out')
        self.assertEqual(len(samples['read']['legacy_caller_rows(protocols unset)']),1)
        self.assertEqual(len(samples['read']['entry_caller_rows(protocols=(webcollect-data-candidate-2,))']),3)
        self.assertEqual(samples['claim']['legacy_claim_of_old_candidate']['snapshot']['schema_version'],VERSION)
        snapshot=samples['claim']['entry_claim_expected_snapshot']
        self.assertEqual(snapshot['snapshot_body']['schema_version'],VERSION2)
        self.assertIsNone(snapshot['snapshot_body']['requested_goal'])
        self.assertEqual(len(snapshot['frozen_sources_at_claim']),1)
        self.assertTrue(samples['claim']['replay_same_request_returns_original']['same_token'])
        mismatch=samples['claim']['version_mismatch']
        self.assertEqual(mismatch['new_protocol_claimer_requesting_legacy_id'],{'state':'EMPTY'})
        self.assertEqual(mismatch['legacy_claimer_requesting_entry_id'],{'state':'EMPTY'})
        self.assertEqual(mismatch['unsupported_protocol_declaration']['error_type'],'ValueError')


class ConsumerPolling(unittest.IsolatedAsyncioTestCase):
    setUp = Inventory.setUp

    async def test_consumer_started_first_claims_new_row_with_a_new_request_id(self):
        from unittest.mock import AsyncMock, Mock
        from webcollect.candidate_consumer import run
        ledger = Mock()
        ledger.remaining_seconds.return_value = 30
        async def publish(_seconds):
            self.pool.put({'schema_version': VERSION2, 'candidate_kind': 'entry',
                           'entry_url': 'https://example.org/', 'requested_goal': None}, self.source)
        consumed = AsyncMock(return_value={'state': 'succeeded'})
        with (patch('webcollect.candidate_consumer.startup_check', return_value={}),
              patch('webcollect.candidate_consumer.asyncio.sleep', side_effect=publish) as slept,
              patch('webcollect.candidate_consumer.consume', consumed)):
            result = await run(self.pool, ledger, worker_id='worker', request_prefix='wait',
                               protocols=(VERSION2,), poll_seconds=2)
        slept.assert_awaited_once_with(2)
        self.assertEqual(result, [{'state': 'succeeded'}])
        self.assertEqual(self.pool.claim_next('worker', 'wait/0', protocols=(VERSION2,)), {'state': 'EMPTY'})
        self.assertEqual(consumed.await_args.args[1]['request_id'], 'wait/1')

    async def test_empty_idle_consumer_returns_and_explicit_poll_can_be_cancelled(self):
        from unittest.mock import Mock
        import asyncio
        from webcollect.candidate_consumer import run
        ledger = Mock()
        with patch('webcollect.candidate_consumer.startup_check', return_value={}):
            result = await run(self.pool, ledger, worker_id='worker', request_prefix='once')
            self.assertEqual(result, [{'state': 'EMPTY'}])
            with patch('webcollect.candidate_consumer.asyncio.sleep', side_effect=asyncio.CancelledError):
                with self.assertRaises(asyncio.CancelledError):
                    await run(self.pool, ledger, worker_id='worker', request_prefix='wait', poll_seconds=2)
            ledger.remaining_seconds.assert_not_called()
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM candidate_empty_requests').fetchone()[0], 2)
