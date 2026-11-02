"""A-C: real producer CLI/tool boundary, disposable stores, no external IO."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

import test_producer_tools as native
from producer_legacy_fixture import main, produce_entries
from site_planner.candidate_pool import CandidatePool, candidate_dedup_key
from site_planner import entry_selection as selection
from site_planner.site_pool import SitePool
from site_planner.discovery_tools import reference
from webcollect.batch_core import load_json,save_json,BatchLedger
from webcollect.candidate_consumer import _entry_hints
from webcollect.site_failure_stop import SiteFailureStore


class Optimization(unittest.TestCase):
    def setUp(self):
        self.f = native.ProducerToolTests('test_fresh_glm_session_selects_native_tools_without_a_flag')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.inv=self.f.inv;self.root=self.inv.root
        self.config=self.f.cfg
        self.sources=self.root/'sources.json';self.config_path=self.root/'config.json'
        save_json(self.config_path,self.config)

    def hit(self,n,host=None):
        host=host or f'new{n}.example.org'
        return self.inv.hit(n,host,title=host+' 主站',content=host+' 主营中文计算与转换服务')

    def row(self,index,host,category='在线工具',page_type='功能页'):
        return {'source_index':index,'page_type':page_type,'classification':{
            'parent_category':category,'identity_source_index':index,'identity_quote':host,
            'function_source_index':index,'function_quote':'主营中文计算与转换服务'}}

    def cli(self,sources,*,key='one',mode=None,target=5,size=10,batches=1,goals=None,feedback=None):
        # Immutable explicit input files; rewriting identical bytes is test setup only.
        path=self.root/('sources-'+key+'.json');save_json(path,sources)
        args=['produce-entries','--config',str(self.config_path),'--pool',str(self.inv.pool.path),
            '--ledger',str(self.root/'model.db'),'--history-set',str(self.f.chain),
            '--output',str(self.root/'output'/key),'--sources',str(path),
            '--batch-key',key,'--target',str(target),'--batch-size',str(size),'--max-batches',str(batches)]
        if mode: args += ['--discovery-mode',mode]
        if goals: args += ['--goals',str(goals)]
        if feedback: args += ['--feedback-scope',str(feedback)]
        with redirect_stdout(io.StringIO()) as stream:
            main(args)
        result=json.loads(stream.getvalue())
        self.export(key+'-'+str(len(self.f.provider.opener.calls))+'-'+str(result['new_candidates_this_invocation']), result)
        return result

    def export(self,name,value):
        destination=os.environ.get('WEBCOLLECT_PRODUCER_REPORT_DIR')
        if destination:
            root=Path(destination);root.mkdir(parents=True,exist_ok=True)
            filename=self._testMethodName+'-'+name+'.json'
            path=root/filename
            if path.exists():
                path=root/(self._testMethodName+'-'+name+'-replay.json')
            save_json(path,value)

    def test_A_complete_restart_and_old_only_new_batch_zero_dispatch(self):
        hits=[self.hit(n) for n in range(3)]
        self.f.response([{'source_index':0}])
        first=self.cli(hits,size=1,batches=5,target=8)
        self.assertEqual(first['listed_unique_candidates'],3,first)
        before=(len(self.f.provider.opener.calls),self.inv.entry_http.call_count)
        replay=self.cli(hits,size=1,batches=5,target=8)
        old=self.cli(hits,key='old',target=8)
        self.assertEqual(replay['listed_unique_candidates'],3)
        self.assertEqual(replay['new_dispatches'],{'search':0,'model':0,'GET':0})
        self.assertEqual(old['new_dispatches'],{'search':0,'model':0,'GET':0})
        self.assertEqual(old['excluded_search_stage'],3)
        self.assertEqual(before,(len(self.f.provider.opener.calls),self.inv.entry_http.call_count))

    def test_A_mixed_new_sites_extend_goals_tracking_and_routes(self):
        self.inv.pool.put(self.inv.entry('https://old.example.org/tool'),self.inv.source())
        self.f.response([{'source_index':0}])
        mixed=self.cli([self.hit(0,'old.example.org'),self.hit(1)],key='mixed')
        self.assertEqual(mixed['listed_unique_candidates'],1,mixed)
        first=self.cli([{'**':'ignored',**self.hit(1),'uri':'https://new1.example.org/p1?utm_source=share'},
                        {**self.hit(2,'new1.example.org'),'uri':'https://new1.example.org/p2#/convert'}],mode='expand',key='expand')
        self.assertEqual(first['listed_unique_candidates'],1,first)
        self.assertEqual(first['excluded_search_stage'],1)
        self.assertEqual(first['new_dispatches']['GET'],1)
        goals=self.root/'goals.json'
        def goal(n):return {'uri':'https://new1.example.org/p1','requested_goal':{'kind':'convert','entity':'temperature','parameters':{'value':n}}}
        save_json(goals,{'schema_version':'webcollect-caller-goals-1','goals':[goal(1),goal(2),goal(1)]})
        report=self.cli([],goals=goals,key='goals',mode='expand')
        self.assertEqual(report['listed_unique_candidates'],2,report)
        self.assertEqual(report['row_results'],{'NEW':2,'DUPLICATE':1})
        self.assertEqual(report['new_dispatches']['GET'],1)
        self.assertEqual(report['new_dispatches']['model'],0)

    def test_mixed_keeps_independent_controls_and_skips_language_and_content_variants(self):
        host='tool.example.org'
        self.inv.pool.put(self.inv.entry('https://'+host+'/zh-CN/first/'),self.inv.source())
        def link(path,title,content):
            return {**self.hit(0,host),'uri':'https://'+host+path,'title':title,'content':content}
        hits=[link('/en/first/?x=1','原工具','原工具页面'),
              link('/second/','退休计算器','输入年龄后计算余额'),
              link('/article/123','退休政策','解读退休年龄政策'),
              link('/alias/','退休计算器','输入年龄后计算余额')]
        function={'name_quote':'退休计算器','operation_quote':'输入年龄后计算余额'}
        self.f.response([{'source_index':0,'page_type':'功能页','entry_function':function},
                         {'source_index':1,'page_type':'内容详情','entry_function':function},
                         {'source_index':2,'page_type':'功能页','entry_function':function}])
        result=self.cli(hits,mode='mixed')
        self.assertEqual((result['excluded_search_stage'],result['row_results'],result['new_dispatches']['GET']),
                         (1,{'NEW':1,'REJECTED':2},1),result.get('stopped'))
        stored=next(r for r in self.inv.pool.rows(protocols=('webcollect-data-candidate-2',))
                    if r['candidate_id']==result['candidate_ids'][0])
        self.assertEqual(stored['sources'][0]['independent_function']['name_quote'],'退休计算器')

    def test_A_new_site_best_function_source_and_search_route_fragment(self):
        article=self.hit(0,'same.example.org');article.update(title='工具推荐教程合集',content='介绍与下载'*20)
        function=self.hit(1,'same.example.org');function.update(title='在线计算器',content='在线查询与单位转换')
        self.f.response([{'source_index':0}])
        first=self.cli([article,function])
        row=next(r for r in self.inv.pool.rows(protocols=('webcollect-data-candidate-2',)) if r['candidate_id'] in first['candidate_ids'])
        self.assertEqual(row['candidate']['entry_url'],function['uri'])
        raw=self.root/'raw-search.json';save_json(raw,{'search_result':[{'link':'https://route.example.org/app#/convert'}]})
        search={'request_id':'CONTROLLED-route','reference':reference(raw),
            'results':[dict(self.hit(2,'route.example.org'),uri='https://route.example.org/app',index=0,reference=reference(raw))]}
        args=dict(pool_path=self.inv.pool.path,ledger_path=self.root/'model.db',history_set=self.f.chain,
            output=self.root/'output'/'route',batch_key='route',queries=['中文转换'],target=1,max_batches=1)
        with patch('site_planner.candidate_discovery.glm_search',return_value=search):
            result=produce_entries(self.config,**args)
        route=next(r for r in self.inv.pool.rows(protocols=('webcollect-data-candidate-2',)) if r['candidate_id'] in result['candidate_ids'])
        self.assertTrue(route['candidate']['entry_url'].endswith('#/convert'))

    def test_A_indexed_hot_path_with_200000_history_keys(self):
        pool=self.inv.pool
        with pool.transaction() as con:
            con.executemany('INSERT INTO applications VALUES(?,?,?,?,?)',
                ((f'app-history-{n}',f'h{n}.example.org','合成历史','UNKNOWN',1) for n in range(200000)))
            con.executemany('INSERT INTO data_candidates VALUES(?,?,?,?,?,?,?)',
                ((f'history-{n}',f'app-history-{n}',f'history-key-{n}',1,json.dumps(self.inv.entry(f'https://h{n}.example.org/')),1,'pending') for n in range(200000)))
        queries=[];connect=sqlite3.connect
        def traced(*args,**kwargs):
            con=connect(*args,**kwargs)
            if str(pool.path) in str(args[0]):con.set_trace_callback(queries.append)
            return con
        self.f.response([{'source_index':0}])
        with patch.object(sqlite3,'connect',side_effect=traced):
            report=self.cli([self.hit(0,'h199999.example.org'),self.hit(1)],target=1)
        self.assertEqual(report['listed_unique_candidates'],1,report)
        self.assertFalse(any('SELECT id,host,name FROM applications' in q for q in queries))
        self.assertFalse(any('LEFT JOIN aliases' in q for q in queries))
        with pool.pool.connect() as con:
            baseline=[json.loads(r[0]) for r in con.execute('SELECT baseline FROM runs')]
            plans=[r['detail'] for r in con.execute('EXPLAIN QUERY PLAN SELECT id FROM applications WHERE host=?',('new.example.org',))]
            plans += [r['detail'] for r in con.execute('EXPLAIN QUERY PLAN SELECT candidate_id FROM data_candidates WHERE dedup_key=?',('x',))]
        self.assertTrue(all(b==[] for b in baseline));self.assertTrue(all('INDEX' in p for p in plans),plans)
        self.assertLess(sum('WHERE host=' in q for q in queries),30)
        self.export('scale',{'synthetic_history_keys':200000,'plans':plans,
            'host_point_queries':sum('WHERE host=' in q for q in queries),
            'total_SQL_statements':len(queries),'frozen_baselines':baseline})

    def test_B_status_receipts_timeout_resume_and_other_rows_continue(self):
        statuses=[204,403,404,521,None,200]
        hits=[self.hit(n) for n in range(6)]
        self.f.response([{'source_index':n} for n in range(6)])
        def fetch(uri,*args):
            n=int(uri.split('/p')[-1]);status=statuses[n]
            if status is None:raise TimeoutError('CONTROLLED dispatched timeout')
            return status,uri
        with patch('site_planner.entry_access.fetch_status',side_effect=fetch) as get:
            first=self.cli(hits,target=6)
            before=get.call_count
            replay=self.cli(hits,target=6)
        self.assertEqual(first['row_results'],{'NEW':2,'REJECTED':3,'HELD':1},first)
        self.assertEqual(before,6);self.assertEqual(get.call_count,6)
        self.assertEqual(replay['listed_unique_candidates'],2)
        self.assertEqual(replay['new_dispatches']['GET'],0)
        with BatchLedger(self.root/'model.db',self.config).connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM top_level_visits WHERE state='unknown'").fetchone()[0],1)
        receipts=[load_json(p) for p in (self.root/'output'/'one').glob('entry-http-*.json')]
        self.assertEqual(sorted(str(r['http_status']) for r in receipts),sorted(str(s) for s in statuses))

    def test_B_unknown_native_model_never_replaced(self):
        from urllib.error import URLError
        with patch.object(self.f.provider.opener,'open',side_effect=URLError('CONTROLLED dispatched model timeout')) as send:
            first=self.cli([self.hit(0)])
            before=send.call_count
            replay=self.cli([self.hit(0)])
        self.assertEqual(before,1);self.assertEqual(send.call_count,1)
        self.assertEqual(replay['listed_unique_candidates'],0)
        self.assertEqual(replay['stopped']['type'],'OutcomeUnknown')
        self.assertEqual(replay['new_dispatches'],{'search':0,'model':0,'GET':0})

    def test_B_partial_native_response_restart_uses_original_input(self):
        hits=[self.hit(0),self.hit(1)]
        self.f.response([{'source_index':0},{'source_index':1}])
        publish=CandidatePool.publish_row;count=[0]
        def interrupt(pool,*args,**kwargs):
            count[0]+=1
            if count[0]==2:raise OSError('CONTROLLED row interruption')
            return publish(pool,*args,**kwargs)
        with patch.object(CandidatePool,'publish_row',interrupt):first=self.cli(hits)
        self.assertEqual(first['stopped']['type'],'OSError')
        self.assertEqual(first['listed_unique_candidates'],1)
        self.assertEqual(first['new_candidates_this_invocation'],1)
        get_before=self.inv.entry_http.call_count
        second=self.cli(hits)
        self.assertEqual(second['listed_unique_candidates'],2,second)
        self.assertEqual(self.inv.entry_http.call_count,get_before)
        self.assertEqual(len(self.f.provider.opener.calls),1)
        self.assertEqual(second['new_dispatches'],{'search':0,'model':0,'GET':0})

    def test_B_original_hold_before_model_and_publication_race_single_NEW(self):
        guard=SiteFailureStore(self.config['site_failure_guard']);held=self.hit(0)
        for n in range(3):
            guard.record(held['uri'],'controlled-hold-'+str(n),stage='observation',state='failed',
                real_execution=True,reason='CONTROLLED network',evidence=[reference(self.inv.proof)],usage_refs=[])
        report=self.cli([held])
        self.assertEqual(report['listed_unique_candidates'],0)
        self.assertEqual(report['new_dispatches'],{'search':0,'model':0,'GET':0})
        candidate=self.inv.entry('https://race.example.org/')
        def publish(n):
            header={'run_id':'race','batch':0,'request_id':'same','raw_index':n,
                'response_sha256':str(n),'row_id':'race-'+str(n)}
            return self.inv.pool.publish_row(header,candidate,self.inv.source())
        with ThreadPoolExecutor(max_workers=2) as executor:out=list(executor.map(publish,range(2)))
        self.assertEqual(sorted(r['result'] for r in out),['DUPLICATE','NEW'])

    def test_C_normal_tool_category_page_roles_hint_missing_conflict_third_party(self):
        hits=[self.hit(0),self.hit(1),self.hit(2),self.hit(3,'same.example.org'),self.hit(4,'same.example.org'),self.hit(5,'article.example.org')]
        rows=[self.row(0,'new0.example.org'),{'source_index':1,'category_hint':'在线工具'},
              {'source_index':2},self.row(3,'same.example.org'),self.row(4,'same.example.org','新闻资讯','内容详情'),
              {**self.row(5,'article.example.org',page_type='第三方介绍或下载'),'application':'other.com'}]
        self.f.response(rows)
        report=self.cli(hits,mode='expand',target=10)
        self.assertEqual(report['listed_unique_candidates'],5,report)
        self.assertEqual(report['row_results'],{'NEW':5,'REJECTED':1})
        payload=json.loads(self.f.provider.opener.calls[0].data)
        context=json.loads(payload['messages'][1]['content'][0]['text'])
        self.assertEqual(context['version'],selection.TOOL_PROTOCOL)
        self.assertEqual(context['page_types'],list(selection.PAGE_TYPES))
        sources=[r['sources'][0] for r in self.inv.pool.rows(protocols=('webcollect-data-candidate-2',))]
        classes=[s['application_classification']['status'] for s in sources]
        self.assertEqual(Counter(classes),{'EVIDENCE_BOUND_AI':1,'UNKNOWN':2,'CONFLICT':2})
        for r in self.inv.pool.rows(protocols=('webcollect-data-candidate-2',)):
            hints=_entry_hints({'snapshot':r['candidate'],'sources':r['sources']})
            self.assertEqual(hints['category_proven'],r['sources'][0]['application_classification']['status']=='EVIDENCE_BOUND_AI')
        distribution=report['application_distribution']
        self.assertEqual(distribution['total'],4)
        self.assertEqual(distribution['counts']['UNKNOWN'],3)
        self.assertEqual(distribution['shares']['在线工具'],0.25)
        self.assertIn('NOT_EVALUATED',distribution['effective_sample_distribution'])

    def test_C_same_application_inherits_evidence_and_later_conflict_does_not_rewrite_claim(self):
        hits=[self.hit(0,'same.example.org'),self.hit(1,'same.example.org')]
        self.f.response([self.row(0,'same.example.org'),{'source_index':1,'page_type':'内容详情'}])
        self.cli(hits,mode='expand')
        inherited = next(r for r in self.inv.pool.rows(protocols=('webcollect-data-candidate-2',))
                         if r['candidate']['entry_url'] == hits[1]['uri'])
        self.assertEqual([e['uri'] for e in inherited['sources'][0]['application_classification']['evidence']],
                         [hits[1]['uri'], hits[0]['uri']])
        claim=self.inv.pool.claim_next('worker','one',protocols=('webcollect-data-candidate-2',))
        self.assertTrue(_entry_hints(claim)['category_proven'])
        frozen=json.dumps(claim['sources'],sort_keys=True)
        self.f.response([self.row(0,'same.example.org','新闻资讯')])
        self.cli([self.hit(2,'same.example.org')],mode='expand',key='conflict')
        self.assertEqual(json.dumps(self.inv.pool.get_claim(claim['claim_id'])['sources'],sort_keys=True),frozen)
        fresh=[r for r in self.inv.pool.rows(protocols=('webcollect-data-candidate-2',)) if r['candidate']['entry_url'].endswith('/p2')][0]
        self.assertEqual(fresh['sources'][0]['application_classification']['status'],'CONFLICT')

    def test_C_bad_quotation_foreign_evidence_and_third_party_content_remain_unknown(self):
        hits=[self.hit(0),self.hit(1)]
        a=self.row(0,'new0.example.org');a['classification']['function_source_index']=1
        b=self.row(1,'new1.example.org');b['classification']['function_quote']='invented'
        self.f.response([a,b])
        report=self.cli(hits)
        self.assertEqual(report['application_distribution']['counts']['UNKNOWN'],2)
        self.assertTrue(all(r['sources'][0]['category_hint']=='UNKNOWN' for r in self.inv.pool.rows(protocols=('webcollect-data-candidate-2',))))

    def test_C_url_owns_identity_and_glm_only_quotes_the_function(self):
        hit = self.inv.hit(0, 'www.calc.example.org', title='算术工坊', content='在线计算与单位转换')
        proposal = {'parent_category':'在线工具', 'function_source_index':0, 'function_quote':hit['content']}
        self.f.response([{'source_index':0, 'page_type':'功能页', 'classification':proposal}])
        report = self.cli([hit])
        self.assertEqual(report['new_dispatches'], {'model':1, 'GET':1, 'search':0})
        claim = self.inv.pool.claim_next('worker','one',protocols=('webcollect-data-candidate-2',))
        decision = claim['sources'][0]['application_classification']
        identity, function = decision['evidence']
        self.assertEqual((identity['hostname'], identity['quote'], identity['reference']),
                         ('www.calc.example.org', hit['uri'], hit['reference']))
        self.assertEqual((function['role'], function['quote'], decision['proposal']), ('function', hit['content'], proposal))
        self.assertEqual(_entry_hints(claim)['category'], '在线工具')
        self.assertTrue(_entry_hints(claim)['category_proven'])
        prompt = json.loads(self.f.provider.opener.calls[0].data)['messages'][0]['content']
        self.assertNotIn('identity_quote', prompt)
        self.assertIn('function_quote', prompt)

    def test_C_third_party_article_belongs_to_its_publisher(self):
        publisher, vendor = 'press.example.org', 'solver.example.org'
        about_tool = '求解方程并显示两个根'
        article = self.inv.hit(0, publisher, title='外站工具介绍', content=vendor+' '+about_tool)
        official = self.inv.hit(1, vendor, content=about_tool)
        second = {**self.inv.hit(2, publisher, content=about_tool), 'page_type':selection.THIRD_PARTY}
        page = self.inv.hit(3, publisher)
        def proposal(index, function_index, page_type):
            return {'source_index':index, 'page_type':page_type, 'classification':{
                'parent_category':'在线工具', 'identity_quote':vendor, 'identity_source_index':1,
                'function_source_index':function_index, 'function_quote':about_tool}}
        self.f.response([proposal(0, 0, selection.THIRD_PARTY), proposal(2, 2, '功能页'),
                         proposal(3, 0, '内容详情'), proposal(3, 1, '内容详情'),
                         {**proposal(0, 1, selection.THIRD_PARTY), 'application':vendor}])
        report = self.cli([article,official,second,page], mode='expand', target=6)
        self.assertEqual(report['row_results'], {'NEW':3, 'DUPLICATE':1, 'REJECTED':1})
        self.assertIsNone(self.inv.pool.pool.application(official['uri']))
        for row in self.inv.pool.rows(protocols=('webcollect-data-candidate-2',)):
            self.assertEqual(row['application_id'], self.inv.pool.pool.application(article['uri'])['id'])
            for source in row['sources']:
                decision = source['application_classification']
                self.assertEqual(decision['parent_category'], 'UNKNOWN')
                self.assertEqual([(e['role'],e['hostname']) for e in decision['evidence']], [('identity',publisher)])
                if row['candidate']['entry_url'] in (article['uri'],second['uri']):
                    self.assertEqual(source['page_type'], selection.THIRD_PARTY)

    def test_C_article_can_use_another_publisher_source_for_its_own_business(self):
        article = self.inv.hit(0, 'press.example.org', content='介绍外部计算软件')
        about = self.inv.hit(1, 'press.example.org', content='本报提供科技新闻和行业报道')
        self.f.response([{'source_index':0, 'page_type':selection.THIRD_PARTY, 'classification':{
            'parent_category':'新闻资讯','function_source_index':1,'function_quote':about['content']}}])
        self.cli([article,about], mode='expand')
        row, = self.inv.pool.rows(protocols=('webcollect-data-candidate-2',))
        decision = row['sources'][0]['application_classification']
        self.assertEqual(decision['parent_category'], '新闻资讯')
        self.assertEqual([e['uri'] for e in decision['evidence']], [article['uri'],about['uri']])

    def test_C_new_entry_cannot_inherit_a_third_party_articles_product_quote(self):
        host = 'press.example.org'
        article = self.inv.hit(0, host, title=host+' 外站软件介绍', content='推荐的外部工具支持单位转换')
        row = self.row(0, host, page_type=selection.THIRD_PARTY)
        row['classification']['function_quote'] = '外部工具支持单位转换'
        old = selection.classify_rows([row], [article], {}, identity_from_url=False)[0]
        self.assertEqual(old['parent_category'], '在线工具')
        self.inv.pool.put(self.inv.entry(article['uri']), self.inv.source(selection_version=selection.VERSION,
                          page_type=selection.THIRD_PARTY, application_classification=old))
        self.f.response([{'source_index':0,'page_type':'内容详情'}])
        report = self.cli([self.hit(1, host)], mode='expand')
        fresh = self.inv.rows_for(report['candidate_ids'][0])['sources'][0]['application_classification']
        self.assertEqual(fresh['status'], 'UNKNOWN')
        self.assertEqual(fresh['previous_judgments'], [old])

    def test_C_frozen_batch_keeps_original_prompt_and_quotation_rule(self):
        hit = self.inv.hit(0,'www.calc.example.org',title='算术工坊',content='在线计算与转换')
        original_freeze = SitePool.freeze_run
        def freeze_old_batch(pool, run_id, config, **kwargs):
            if 'selection_version' not in config:
                return original_freeze(pool, run_id, config, **kwargs)
            old = json.loads(json.dumps(config))
            del old['identity_rule']
            old['system'] = old['tools'][0]['function']['description'] = selection.LEGACY_SYSTEM
            original_freeze(pool, run_id, old, **kwargs)
            raise InterruptedError('frozen before classification')
        with patch.object(SitePool,'freeze_run',freeze_old_batch), self.assertRaises(InterruptedError):
            self.cli([hit])
        proposal = {'parent_category':'在线工具','identity_source_index':0,'identity_quote':'算术工坊',
                    'function_source_index':0,'function_quote':hit['content']}
        self.f.response([{'source_index':0,'page_type':'功能页','classification':proposal}])
        first = self.cli([hit])
        self.assertEqual(first['application_distribution']['counts'], {'UNKNOWN':1})
        self.assertEqual(self.cli([hit])['new_dispatches'], {'model':0,'GET':0,'search':0})
        body = json.loads(self.f.provider.opener.calls[0].data)
        self.assertEqual(body['messages'][0]['content'], selection.LEGACY_SYSTEM)
        self.assertEqual(body['tools'][0]['function']['description'], selection.LEGACY_SYSTEM)
        next_hit = {**hit, 'uri':hit['uri']+'/next'}
        second = self.cli([next_hit], key='next', mode='expand')
        old = self.inv.rows_for(first['candidate_ids'][0])
        new = self.inv.rows_for(second['candidate_ids'][0])
        self.assertEqual(old['sources'][0]['application_classification']['parent_category'], 'UNKNOWN')
        self.assertEqual(new['sources'][0]['application_classification']['parent_category'], '在线工具')

    def test_C_direction_deficit_order_is_frozen(self):
        self.f.response([self.row(0,'new0.example.org')]);self.cli([self.hit(0)])
        observed=[]
        def search(*args,**kwargs):
            observed.append(args[3]);return {'request_id':'CONTROLLED','results':[dict(self.hit(1),index=0)]}
        self.f.response([{'source_index':0}])
        args=dict(pool_path=self.inv.pool.path,ledger_path=self.root/'model.db',history_set=self.f.chain,
            output=self.root/'output'/'directions',batch_key='directions',target=1,max_batches=1,
            directions=[{'direction':'tools','category':'在线工具','queries':['工具']},
                        {'direction':'books','category':'图书文化','queries':['图书']}])
        with patch('site_planner.candidate_discovery.glm_search',side_effect=search):
            first=produce_entries(self.config,**args);second=produce_entries(self.config,**args)
        self.assertEqual(observed,['图书']);self.assertEqual(second['new_dispatches']['search'],0)

    def test_C_explicit_target_share_changes_real_query_priority(self):
        self.f.response([self.row(0,'new0.example.org')]);self.cli([self.hit(0)])
        observed=[]
        def search(*args,**kwargs):
            observed.append(args[3]);return {'request_id':'CONTROLLED-ratio','results':[dict(self.hit(1),index=0)]}
        self.f.response([{'source_index':0}])
        config={**self.config,'run_id':'ratio-producer'}
        with patch('site_planner.candidate_discovery.glm_search',side_effect=search):
            report=produce_entries(config,pool_path=self.inv.pool.path,ledger_path=self.root/'ratio.db',history_set=self.f.chain,
                output=self.root/'output'/'ratio',target=1,max_batches=1,
                directions=[{'direction':'books','category':'图书文化','queries':['图书'],'target_share':0.1},
                            {'direction':'tools','category':'在线工具','queries':['工具'],'target_share':0.9}])
        self.assertEqual(observed,['工具']);self.assertEqual(report['listed_unique_candidates'],1)

    def test_A_local_launcher_binds_mode_and_feedback(self):
        import runpy
        scope={'batch':self.config['run_id']+'/entry-batch/demo','pool':str(self.inv.pool.path),
            'producer_config':str(self.config_path),'producer_db':str(self.root/'model.db'),
            'history_set':str(self.f.chain),'discovery_mode':'expand','feedback_scope':str(self.root/'feedback.json')}
        path=self.root/'scope.json';save_json(path,scope)
        args=['start_candidates.py','--scope',str(path),'--dry-run','producer','--query','中文计算']
        with patch.object(sys,'argv',args),redirect_stdout(io.StringIO()) as stream:
            runpy.run_path(str(__import__('pathlib').Path(__file__).parents[1]/'scripts/start_candidates.py'),run_name='__main__')
        self.assertIn('--discovery-mode expand',stream.getvalue());self.assertIn('--feedback-scope',stream.getvalue())


from collections import Counter
if __name__=='__main__':unittest.main()
