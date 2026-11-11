"""Independent category searches on the original pool, with controlled HTTP."""
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_grounded_producer as fixture
from site_planner.candidate_discovery import produce_entries
from site_planner.category_search import public_search
from site_planner.discovery_tools import glm_search, reference, search_channel_hold
from site_planner.producer_authority import disjoint_requests, grounded_timeout_scope
from webcollect.batch_core import OutcomeUnknown, save_json
from webcollect.planning import object_sha256


class NewSites(unittest.TestCase):
    def setUp(self):
        self.f = fixture.Grounded('test_formal_CLI_seed_expansion_rules_provenance_and_restart_zero_IO')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.pool = self.f.pool.pool
        self.run = self.f.f.cfg['run_id']
        self.output = self.f.t.docs
        self.old_query = '旧词'
        self.old, _ = self.pool.reserve_tool(self.run,'search',self.old_query,{'search_query':self.old_query,'count':10})
        self.pool.settle_tool(self.old,'unknown',{'http_status':429,'provider_code':'1113'})

    def test_probe_is_one_new_reservation_and_never_settles_original(self):
        model=self.f.f.cfg['model']
        with patch.object(self.f.f.provider.opener,'open',return_value=io.BytesIO(b'{"search_result":[]}')) as send:
            with self.assertRaises(ValueError):
                glm_search(self.pool,self.run,model,self.old_query,self.output,probe_of=self.old)
            result=glm_search(self.pool,self.run,model,'全新独立词',self.output,probe_of=self.old)
            self.assertEqual(result['probe_of'],self.old)
            self.assertIn('account_id',result)
            self.assertIsNone(search_channel_hold(self.pool,self.run))
            with self.assertRaises(ValueError):
                glm_search(self.pool,self.run,model,'第二探测',self.output,probe_of=self.old)
            self.assertEqual(send.call_count,1)
        with self.pool.connect() as con:
            self.assertEqual(con.execute('SELECT state FROM tool_requests WHERE id=?',(self.old,)).fetchone()[0],'unknown')

    def test_all_public_indexes_cooling_stops_before_paid_query_planning(self):
        from site_planner.category_search import PUBLIC_ENGINES
        for engine in PUBLIC_ENGINES:
            rid,_=self.pool.reserve_tool(self.run,'search','原失败-'+engine,{'search_query':'原失败-'+engine,'search_engine':engine,'count':10})
            self.pool.settle_tool(rid,'unknown',{'error_type':'controlled_original_failure'})
        with patch('webcollect.model_gateway.ModelGateway.call',side_effect=AssertionError('no paid planner when index availability is known')):
            result=produce_entries(self.f.f.cfg,pool_path=self.pool.path,ledger_path=self.f.root/'model.db',history_set=self.f.f.chain,
                output=self.f.root/'output'/'cooling',batch_key='cooling',categories=['在线工具'],discovery_mode='new-sites',
                target=1,max_batches=1,max_searches=1)
        self.assertEqual(result['new_dispatches'],{'model':0,'GET':0,'search':0})
        self.assertEqual(result['stopped']['type'],'OutcomeUnknown')
        self.assertIn('cooling down',result['stopped']['reason'])
        with self.pool.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tool_requests WHERE state='unknown'").fetchone()[0],4)

    def test_new_1113_is_the_barrier_for_a_later_explicit_independent_probe(self):
        from urllib.error import HTTPError
        model=self.f.f.cfg['model']
        err=HTTPError('https://provider.example',429,'opaque',{},io.BytesIO(b'{"error":{"code":"1113"}}'))
        with patch.object(self.f.f.provider.opener,'open',side_effect=err):
            with self.assertRaises(OutcomeUnknown):
                glm_search(self.pool,self.run,model,'第一次独立词',self.output,probe_of=self.old)
        current=search_channel_hold(self.pool,self.run)['request_id']
        self.assertNotEqual(current,self.old)
        self.assertEqual(self.pool.checkpoint(self.run,'search-account/'+current)['probe_of'],self.old)
        with patch.object(self.f.f.provider.opener,'open',return_value=io.BytesIO(b'{"search_result":[]}')) as send:
            result=glm_search(self.pool,self.run,model,'以后已恢复的新词',self.output,probe_of=current)
            self.assertEqual(send.call_count,1)
            self.assertEqual(result['probe_of'],current)
            self.assertIsNone(search_channel_hold(self.pool,self.run))
        with self.pool.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tool_requests WHERE state='unknown'").fetchone()[0],2)

    def test_public_demo_filter_requires_a_business_specific_destination(self):
        from site_planner.grounded_entries import demo_business_link
        for path,anchor,expected in [('/','微信公众平台',False),('/ruleCenter','规则中心',False),
                ('/cgi-bin/announce','群发功能开放公告',False),('/docs/form','表单文档',False),
                ('/#/dashboard','系统仪表盘',True),('/examples/table','表格示例',True)]:
            self.assertEqual(demo_business_link({'uri':'https://demo.example.org'+path,'anchor':anchor}),expected)

    def test_public_demo_read_requires_business_text_and_excludes_login_only(self):
        from site_planner.grounded_entries import public_demo_proof
        src='https://demo.example.org/examples/form'
        for index,html in enumerate(['<html><form><input type="password"></form></html>','<html><textarea></textarea></html>']):
            raw=self.output/f'raw-demo-{index}.html';raw.write_text(html)
            body={'uri':src,'raw_html':reference(raw),'encoding':'utf-8','content':'按钮表单示例\n'+('登录' if index==0 else '选择类型'),
                  'chinese':True,'site_evidence':'homepage'}
            path=self.output/f'demo-{index}.json';save_json(path,body)
            with patch('site_planner.application_discovery.homepage_document',return_value=(body,reference(path))):
                if index==0:
                    with self.assertRaises(ValueError):public_demo_proof(SimpleNamespace(config={}),self.run,{'uri':src},self.output,strict=False)
                else:self.assertEqual(public_demo_proof(SimpleNamespace(config={}),self.run,{'uri':src},self.output,strict=False)['html_elements'],{'textarea':1})

    def test_game_site_tool_links_do_not_count_as_game_supply(self):
        from site_planner.grounded_entries import game_business_priority
        def hit(path,anchor):return {'uri':'https://mix.example.org'+path,'anchor':anchor,'heading':'网页小游戏'}
        self.assertIsNone(game_business_priority(hit('/t/tax','个税计算器')))
        self.assertIsNone(game_business_priority(hit('/t/weather','天气')))
        self.assertEqual(game_business_priority(hit('/flash/435.html','隐藏物品')),0)
        self.assertEqual(game_business_priority(hit('/c/cards','纸牌游戏')),1)

    def test_duckduckgo_result_destination_not_transport_redirect(self):
        from site_planner.category_search import OrganicResults
        parser=OrganicResults('ddg-html')
        parser.feed('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdemo.example.org%2Fa">示例</a>')
        self.assertEqual(parser.rows,[{'link':'https://demo.example.org/a','title':'示例'}])

    def test_paid_probe_needs_explicit_paid_engine(self):
        with self.assertRaisesRegex(ValueError,'paid probe'):
            produce_entries(self.f.f.cfg,pool_path=self.pool.path,ledger_path=self.f.root/'model.db',
                history_set=self.f.f.chain,output=self.f.root/'output'/'no-probe',batch_key='no-bill',
                categories=['在线工具'],discovery_mode='new-sites',target=1,probe_search_hold=self.old)

    def test_public_results_are_bound_to_original_bytes_and_never_sent_twice(self):
        body=b'<h3>ad<a data-mdurl="https://ad.example.org/">ad</a></h3><h3 class="res-title"><a data-mdurl="https://test.example.org/a"><em>true</em> result</a></h3>'
        opener=SimpleNamespace(open=lambda *a,**kw:io.BytesIO(body))
        with patch('site_planner.category_search.build_opener',return_value=opener) as send:
            opts=dict(engine='360-public',maximum=1,batch_scope='one',count=4)
            first=public_search(self.pool,self.run,'另一个检索',self.output,**opts)
            self.assertEqual(first,public_search(self.pool,self.run,'另一个检索',self.output,**opts))
            self.assertEqual(send.call_count,1)
            self.assertEqual(Path(first['raw_response']['path']).read_bytes(),body)
            self.assertEqual([r['title'] for r in first['results']],['true result'])
            self.assertEqual(search_channel_hold(self.pool,self.run)['request_id'],self.old)

    def test_original_numbered_selection_needs_matching_prepared_excerpt_and_disjoint_new_host(self):
        run=self.run+'/entry-batch/old'
        cfg={'run_id':self.run}
        self.pool.freeze_run(run,{'batch_size':1,'config_sha256':object_sha256(cfg)})
        self.pool.checkpoint(run,'grounded-unit/0/prepared',{'links':[{'uri':'https://one.example.org/','anchor':'首页','heading':''}]})
        item={'state':'unknown','kind':'ai-grounded-entry-ids-1','job_id':'old-job','error':'TimeoutError',
              'job_state':'queued','attempts':1,'finished':2}
        payload={'scope':run+'/grounded-unit/0/0','links':[{'row':0,'quotes':{'0':'首页'}}]}
        row={**item,'payload':json.dumps({'input':payload})}
        bound=grounded_timeout_scope(self.pool,cfg,row)
        ledger=SimpleNamespace(producer_policy={'deferred':{'original':bound}},config=cfg)
        self.assertEqual(disjoint_requests(ledger,urls=['https://new.example.org/']),('original',))
        with self.assertRaises(OutcomeUnknown):disjoint_requests(ledger,urls=bound['source_urls'])
        with self.assertRaises(OutcomeUnknown):disjoint_requests(ledger,scope=run+'/category-query-plan')
        payload['links'][0]['quotes']['0']='不匹配'
        with self.assertRaises(ValueError):grounded_timeout_scope(self.pool,cfg,{**item,'payload':json.dumps({'input':payload})})

    def test_category_only_bypasses_held_search_through_real_adapter_and_excludes_known_and_off_category(self):
        _,known=self.f.site()
        urls=[known['uri'],'https://wrong.example.org/','https://fresh.example.org/']
        def home(_ledger,_batch,uri,_output):
            text='本网站提供免费计算器和长度转换'
            raw=self.output/(object_sha256(uri)+'.html')
            raw.write_text('<html lang="zh"><h1>'+text+'</h1><a href="/calc">科学计算器</a></html>')
            doc={'uri':uri,'title':'中文首页','content':text,'chinese':True,'site_evidence':'homepage',
                 'encoding':'utf-8','raw_html':reference(raw)}
            dest=self.output/(object_sha256(uri)+'.json');save_json(dest,doc)
            return doc,reference(dest)
        def classification(request,timeout):
            from copy import deepcopy
            ctx=json.loads(json.loads(request.data)['messages'][-1]['content'][0]['text'])
            cat='健康科普' if 'wrong.' in ctx['homepage_uri'] else '在线工具'
            args={'parent_category':cat,'quote_ids':[ctx['quote_choices'][0]['id']],'reason':'证据'}
            raw=deepcopy(self.f.f.provider.opener.raw)
            raw['choices']=[{'finish_reason':'tool_calls','message':{'tool_calls':[{'id':'offline','type':'function','function':
                          {'name':'submit_site_classification','arguments':json.dumps(args)}}]}}]
            return io.BytesIO(json.dumps(raw).encode())
        html=''.join('<h3 class="res-title"><a data-mdurl="'+u+'">标题</a></h3>' for u in urls).encode()
        args=dict(pool_path=self.pool.path,ledger_path=self.f.root/'model.db',history_set=self.f.f.chain,
                    output=self.f.root/'output'/'cat',batch_key='new',categories=['在线工具'],discovery_mode='new-sites',
                    target=1,max_batches=3,max_searches=1)
        with patch('site_planner.grounded_entries.search_channel_hold',return_value=None), \
             patch('site_planner.grounded_entries.glm_search',side_effect=AssertionError('public default cannot call paid API')), \
             patch('webcollect.model_gateway.ModelGateway.call',return_value={'queries':['公开中文计算工具']}) as planner, \
             patch('site_planner.category_search.build_opener',return_value=SimpleNamespace(open=lambda *a,**kw:io.BytesIO(html))), \
             patch.object(self.f.f.provider.opener,'open',side_effect=classification), \
             patch('site_planner.application_discovery.homepage_document',side_effect=home):
            result=produce_entries(self.f.f.cfg,**args)
            self.assertEqual(result['listed_unique_candidates'],1,result)
            self.assertEqual(result['supply_counts'],{'project_first_discovery_output':1})
            self.assertEqual(result['source_counts']['page_origin'],{'first_party_html':1})
            self.assertEqual({x['reason'] for x in result['site_failures']},{'previously_registered_application','outside_target_category'})
            self.assertEqual(produce_entries(self.f.f.cfg,**args)['new_dispatches'],{'search':0,'model':0,'GET':0})
            self.assertEqual(planner.call_count,1)
