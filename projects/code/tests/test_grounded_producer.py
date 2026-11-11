"""Formal entry tools v3 on disposable pools and controlled HTTP only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import threading
import time
import socket
import unittest
import urllib.request
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import test_application_discovery as tables
from site_planner import grounded_entries as g
from site_planner.application_discovery import Discovery
from site_planner.candidate_discovery import produce_entries, main, _publish_entry
from site_planner.candidate_pool import CandidatePool, VERSION2
from site_planner.discovery_tools import reference, glm_search, search_channel_hold
from site_planner.pipeline import request_uri, open_public_get
from site_planner.entry_access import fetch_status as _REAL_FETCH_STATUS
from webcollect.batch_core import BatchLedger, load_json, save_json, OutcomeUnknown
from webcollect.planning import object_sha256

_REAL_DNS = socket.getaddrinfo
_REAL_OPENER = urllib.request.build_opener


class Grounded(unittest.TestCase):
    def setUp(self):
        self.t=tables.SiteTables('test_new_site_classifies_homepage_then_old_reader_confirms');self.t.setUp();self.addCleanup(self.t.doCleanups)
        self.f=self.t.f;self.root=self.t.root;self.pool=self.t.pool

    def site(self,uri='https://tools.example.org/',html=None,category='在线工具',confirmed=True):
        html=html or '<html lang="zh"><h1>本站提供中文在线计算与单位转换服务</h1><a href="/calculator">科学计算器</a><a href="/index">目录索引</a><a href="/en/index.html">English</a><a href="/generic">更多</a></html>'
        raw=self.t.docs/('raw-'+object_sha256([uri,html])+'.html');raw.write_text(html)
        body={'uri':uri,'title':'中文首页','content':'本站提供中文在线计算与单位转换服务','chinese':True,'site_evidence':'homepage',
              'encoding':'utf-8','raw_html':reference(raw)}
        path=self.t.docs/('doc-'+object_sha256(body)+'.json');save_json(path,body);home={**body,'reference':reference(path)}
        aid=self.pool.pool.record({'schema_version':'webcollect-site-discovery-1','origin':'codex_session','run_id':'offline',
            'event_id':object_sha256(home),'uri':uri,'name':'受控站点','category_hint':'UNKNOWN','source_refs':[home['reference']]})['application_id']
        self.t.sites.ensure(aid)
        if confirmed:
            decision={'status':'EVIDENCE_BOUND_AI','parent_category':category,'references':[home['reference']],
                      'evidence':[{'role':'function','uri':uri,'quote':body['content'],'reference':home['reference']}]}
            self.t.sites.decide(aid,decision,home)
        return aid,home

    def run_new(self,home,key='new',target=4,**kwargs):
        args=dict(pool_path=self.pool.path,ledger_path=self.root/'model.db',history_set=self.f.chain,
                  output=self.root/'output'/key,sources=[home],batch_key=key,target=target,batch_size=10,max_batches=2)
        args.update(kwargs)
        return produce_entries(self.f.cfg,**args)

    def test_formal_CLI_seed_expansion_rules_provenance_and_restart_zero_IO(self):
        aid,home=self.site();config=self.root/'cfg.json';save_json(config,self.f.cfg)
        sources=self.root/'sources.json';save_json(sources,[home])
        command=['produce-entries','--config',str(config),'--pool',str(self.pool.path),'--ledger',str(self.root/'model.db'),
                 '--history-set',str(self.f.chain),'--output',str(self.root/'output/new'),'--sources',str(sources),
                 '--target','4','--batch-size','10','--max-batches','2']
        def invoke():
            stream=io.StringIO()
            with redirect_stdout(stream):main(command)
            return json.loads(stream.getvalue())
        first=invoke();second=invoke()
        self.assertEqual(first['listed_unique_candidates'],4,first)
        self.assertEqual(second['new_dispatches'],{'model':0,'GET':0,'search':0})
        self.assertEqual(second['new_candidates_this_invocation'],0)
        rows=self.pool.rows(protocols=(VERSION2,))
        self.assertFalse(any('/en/' in r['candidate']['entry_url'] for r in rows))
        self.assertEqual({r['sources'][0]['page_type'] for r in rows},{'功能页','检索或列表','UNKNOWN'})
        self.assertEqual(first['source_counts']['page_origin'],{'first_party_html':3,'caller_list':1})
        self.assertEqual(first['source_counts']['selection_method'],{'rule':3,'caller_list':1})
        for r in rows:
            self.assertEqual(set(r['candidate']),{'schema_version','candidate_kind','entry_url','requested_goal'})
            self.assertEqual(tables.confirmed_category(r['sources']),'在线工具')
        frozen=next((self.root/'output/new').glob('entry-links-*.json'))
        self.assertIn('rule',frozen.read_text())

    def test_two_stage_real_gateway_protocol_with_synthetic_provider(self):
        aid,home=self.site(confirmed=False)
        calls=[]
        def response(request,timeout):
            payload=json.loads(request.data);name=payload['tools'][0]['function']['name'];calls.append(name)
            context=json.loads(payload['messages'][1]['content'][0]['text'])
            if name=='submit_site_classification':args={'parent_category':'在线工具','quote_ids':[context['quote_choices'][0]['id']],'reason':'本站主营原文'}
            else:
                link=context['links'][0]
                args={'entries':[{'link_id':link['link_id'],'evidence_id':link['evidence_id'],'page_type':'功能页',
                                  'quote':link['anchor'],'operation_quotes':[link['anchor']],'reason':'原锚文本计算器'}]}
            raw=deepcopy(self.f.provider.opener.raw)
            raw['choices']=[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                'tool_calls':[{'id':'offline-'+name,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}]
            return io.BytesIO(json.dumps(raw).encode())
        with patch.object(self.f.provider.opener,'open',side_effect=response):
            report=self.run_new(home,target=1,entry_selection='model')
            replay=self.run_new(home,target=1,entry_selection='model')
        self.assertEqual(report['listed_unique_candidates'],1,report)
        self.assertEqual(calls,['submit_site_classification','submit_entry_links'])
        self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})
        self.assertEqual(self.t.sites.get(aid)['classification_state'],'confirmed')
        with self.pool.pool.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM application_mining_requests').fetchone()[0],1)
        from webcollect.candidate_accounting import discovery_shares,metering
        with BatchLedger(self.root/'model.db',self.f.cfg).connect() as con:
            requests=[dict(r) for r in con.execute('SELECT id,job_id,state,error,started,usage FROM model_requests')]
        with self.pool.pool.connect() as con:
            publications=[dict(r) for r in con.execute("SELECT request_id,candidate_id FROM candidate_batch_rows WHERE result='NEW'")]
            for r in con.execute('SELECT m.job_id,i.conclusion FROM application_mining_requests m JOIN application_scope_items i USING(scope_id)'):
                if r['conclusion']:
                    conclusion=json.loads(r['conclusion'])
                    if conclusion['result']=='NEW':publications.append({'request_id':r['job_id'],'candidate_id':conclusion['candidate_id']})
        shares,attributed=discovery_shares(requests,publications)
        self.assertEqual(sum(s['allocated']['total_tokens'] for s in shares.values()),metering(requests)['known_total_tokens'])
        self.assertEqual(attributed,{r['id'] for r in requests})

    def test_link_and_document_ids_and_quotes_cannot_cross_sites(self):
        _,a=self.site();_,b=self.site('https://wiki.example.org/',category='百科与文档')
        x=g.extract_links(a)[0];y=g.extract_links(b)[0];row=g.rule_decision(x)
        self.assertEqual(g.bind_decisions([row],[x])[0][0]['uri'],x['uri'])
        for bad in ({**row,'link_id':y['link_id']},{**row,'evidence_id':y['evidence_id']},
                    {**row,'evidence_id':'quote-0'},{**row,'quote':'不存在的原文'},
                    {**row,'operation_quotes':['伪造操作']}):
            with self.assertRaises(ValueError):g.bind_decisions([bad],[x])
        with self.assertRaises(Exception):g.bind_decisions([{**row,'uri':x['uri']}],[x])
        with self.assertRaises(ValueError):g.extract_links({**a,'raw_html':b['raw_html']})

    def test_HTML_base_and_hash_routes_keep_original_navigation_identity(self):
        _,home=self.site(html='<html lang="zh"><base href="/app/"><h1>中文工具</h1><a href="tool">计算器</a>'
                             '<a href="#/one">工具一</a><a href="#!/two">工具二</a><a href="#footer">底部</a></html>')
        links=g.extract_links(home)
        self.assertEqual([h['uri'] for h in links],['https://tools.example.org/app/tool',
            'https://tools.example.org/app/#/one','https://tools.example.org/app/#!/two'])

    def test_underrepresented_source_and_only_same_type_attributable_feedback(self):
        _,a=self.site();_,b=self.site('https://wiki.example.org/',category='百科与文档')
        links=g.extract_links(a)+g.extract_links(b)
        categories={'tools.example.org':'开发者站与 API 文档','wiki.example.org':'百科与文档'}
        counts={'counts':{'开发者站与 API 文档':72,'百科与文档':8},'page_types':{'功能页':50,'检索或列表':1}}
        feedback={'groups':[{'host':'wiki.example.org','page_type':'内容详情','deprioritized':True,'streak_candidate_ids':['a','b']}]}
        ranked=g.rank_links(links,categories,counts,feedback)
        self.assertEqual(ranked[0]['uri'],'https://wiki.example.org/index')
        self.assertFalse(ranked[0]['ranking_reason']['feedback']['deprioritized'])
        print(json.dumps({'frozen_source_ranking_comparison':{'old_first_two':[h['uri'] for h in links[:2]],
            'new_first_two':[h['uri'] for h in ranked[:2]],'category_supply':counts['counts']}},ensure_ascii=False))

    def test_site_quote_ID_from_another_document_cannot_classify(self):
        _,home=self.site(confirmed=False)
        raw=deepcopy(self.f.provider.opener.raw)
        raw['choices']=[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[
            {'id':'OFFLINE-wrong-site','type':'function','function':{'name':'submit_site_classification',
                'arguments':json.dumps({'parent_category':'在线工具','quote_ids':['siteq-another-document-0'],'reason':'错用其他首页编号'})}}]}}]
        self.f.provider.opener.raw=raw
        report=self.run_new(home,target=1)
        self.assertEqual(report['listed_unique_candidates'],0)
        self.assertEqual(self.t.inv.entry_http.call_count,0)
        self.assertTrue(report['site_failures'])

    def test_parallel_settled_landing_dedup_and_explicit_goals_and_hash_routes(self):
        aid,home=self.site();ledger=BatchLedger(self.root/'model.db',self.f.cfg,initialize=True)
        self.t.inv.entry_http.side_effect=lambda uri,*a:(200,'https://tools.example.org/landing')
        def publish(i):
            candidate={'schema_version':VERSION2,'candidate_kind':'entry','entry_url':home['uri']+'from'+str(i),'requested_goal':None}
            source={'origin':'codex_session','run_id':self.f.cfg['run_id'],'table_policy':g.POLICY,'references':[home['reference']]}
            header={'row_id':str(i),'run_id':'parallel','batch':0,'raw_index':i,'request_id':'caller-entries/race','response_sha256':str(i)}
            return _publish_entry(CandidatePool(self.pool.path),ledger,'parallel',self.t.docs,header,candidate,source,candidate,application_id=aid)
        with ThreadPoolExecutor(2) as ex:results=list(ex.map(publish,range(2)))
        self.assertEqual(sorted(r['result'] for r in results),['NEW','REJECTED'],results)
        # Same landed page with distinct explicit caller targets remains distinct.
        goals=self.t.docs/'goals.json';save_json(goals,{'schema_version':'webcollect-caller-goals-1','goals':[
            {'uri':home['uri'],'requested_goal':{'kind':'calculate','entity':'number','parameters':{'value':n}}} for n in (1,2)]})
        result=self.run_new(home,key='targets',target=2,sources=[],goals_path=goals)
        self.assertEqual(result['listed_unique_candidates'],2,result)
        self.assertNotEqual(g.landing_key({'entry_url':home['uri']+'#/a','candidate_kind':'entry'},aid,home['uri']),
                            g.landing_key({'entry_url':home['uri']+'#/b','candidate_kind':'entry'},aid,home['uri']))

    def test_original_search_UNKNOWNs_1113_hold_and_seed_expansion(self):
        _,home=self.site()
        session=self.f.cfg['run_id']
        for n,detail in enumerate(({'http_status':429},{'http_status':429,'provider_code':'1113'})):
            payload={'search_engine':'search_std','search_query':'original'+str(n),'search_intent':False,'count':10,'content_size':'medium'}
            rid,_=self.pool.pool.reserve_tool(session,'search','original'+str(n),payload)
            self.pool.pool.settle_tool(rid,'unknown',detail)
        before=self.f.provider.opener.open
        with patch('site_planner.grounded_entries.glm_search',side_effect=AssertionError('channel unavailable')):
            result=self.run_new(home,target=4,queries=['new query'])
        self.assertEqual(result['listed_unique_candidates'],4,result)
        self.assertEqual(result['new_dispatches']['search'],0)
        with self.pool.pool.connect() as con:self.assertEqual(con.execute("SELECT COUNT(*) FROM tool_requests WHERE state='unknown'").fetchone()[0],2)
        self.assertEqual(search_channel_hold(self.pool.pool,session)['provider_code'],'1113')
        with self.assertRaises(OutcomeUnknown):glm_search(self.pool.pool,session,self.f.cfg['model'],'another query',self.t.docs)

    def test_incomplete_scope_resumes_without_replacing_original_unknown_GET(self):
        _,home=self.site();self.t.inv.entry_http.side_effect=OSError('OFFLINE connection lost')
        first=self.run_new(home,target=4)
        before=self.t.inv.entry_http.call_count
        second=self.run_new(home,target=4)
        self.assertEqual(first['listed_unique_candidates'],0)
        self.assertEqual(second['listed_unique_candidates'],0)
        self.assertEqual(self.t.inv.entry_http.call_count,before)
        self.assertGreater(len(first['row_results']),0)

    def test_formal_entry_with_actual_controlled_HTTP_service_and_direction_search(self):
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path);self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
                self.wfile.write('<html lang="zh"><h1>本站提供中文在线计算与单位转换服务</h1><a href="/中文/%2F?q=中文&amp;x=%2F">科学计算器</a><a href="/list">目录索引</a></html>'.encode())
            def log_message(self,*a):pass
        self.t.inv.network.stop()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(thread.join);self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        uri=f'http://controlled.example.org:{server.server_port}/'
        raw=self.t.docs/'search.json';save_json(raw,{'search_result':[{'link':uri,'title':'受控中文站点','content':'本站中文工具'}]})
        # The formal direction path receives a frozen search response, then all
        # homepage/entry GET bytes pass through the real common transport.
        search={'request_id':'OFFLINE-search','results':[{'uri':uri,'title':'受控中文站点','content':'本站中文工具',
                'index':0,'reference':reference(raw)}],'reference':reference(raw)}
        def dns(host,port,*a,**kw):
            if host=='provider.invalid':return [('CONTROLLED_DNS',)]
            self.assertEqual(host,'controlled.example.org')
            return _REAL_DNS('127.0.0.1',port,*a,**kw)
        def response(request,timeout):
            payload=json.loads(request.data);context=json.loads(payload['messages'][1]['content'][0]['text'])
            raw=deepcopy(self.f.provider.opener.raw);args={'parent_category':'在线工具','quote_ids':[context['quote_choices'][0]['id']],'reason':'受控首页主营'}
            raw['choices']=[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[
                {'id':'OFFLINE-site','type':'function','function':{'name':'submit_site_classification','arguments':json.dumps(args)}}]}}]
            return io.BytesIO(json.dumps(raw).encode())
        config=self.root/'cfg.json';save_json(config,self.f.cfg)
        def real_status(url,timeout,metrics,mode,aliases,guard=None):
            # Same function body used by the product; saved before fixture patch.
            return _REAL_FETCH_STATUS(url,timeout,metrics,mode,aliases,guard)
        with patch('socket.getaddrinfo',side_effect=dns),patch('site_planner.pipeline.build_opener',side_effect=lambda *h:_REAL_OPENER(urllib.request.ProxyHandler({}),*h)), \
             patch('site_planner.entry_access.fetch_status',side_effect=real_status), \
             patch.object(self.f.provider.opener,'open',side_effect=response),patch('site_planner.grounded_entries.glm_search',return_value=search):
            out=io.StringIO()
            with redirect_stdout(out):main(['produce-entries','--config',str(config),'--pool',str(self.pool.path),
                '--ledger',str(self.root/'model.db'),'--history-set',str(self.f.chain),'--output',str(self.root/'output/local'),
                '--query','中文工具','--target','2','--max-batches','1','--max-searches','1'])
            report=json.loads(out.getvalue())
        self.assertEqual(report['listed_unique_candidates'],2,report)
        self.assertEqual(report['source_counts']['site_origin'],{'search':2})
        self.assertEqual(len(requests),3)
        self.assertTrue(any('/%E4%B8%AD%E6%96%87/%2F?q=' in r and 'x=%2F' in r for r in requests))


class Transport(unittest.TestCase):
    def test_unicode_raw_and_escaped_bytes_and_real_local_redirect_transport(self):
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','/done/%E4%B8%AD?x=%2F&x=2');self.end_headers()
                else:self.send_response(200);self.end_headers();self.wfile.write(b'ok')
            def log_message(self,*a):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            # Network access is confined to this explicitly created local server.
            for i in range(6):
                uri=base+'/中文'+str(i)+'/%2F?q=中文&x=%E4%B8%AD&x=%2F#/目录'
                metrics={}
                with open_public_get(uri,time.monotonic()+3,metrics,lambda url:None) as response:self.assertEqual(response.status,200)
                self.assertIn('/%2F?',requests[-1]);self.assertIn('x=%E4%B8%AD&x=%2F',requests[-1]);self.assertNotIn('%252F',requests[-1])
                self.assertEqual(request_uri(request_uri(uri)),request_uri(uri))
            metrics={}
            with open_public_get(base+'/redirect',time.monotonic()+3,metrics,lambda url:None) as response:self.assertEqual(response.status,200)
            self.assertEqual(requests[-1],'/done/%E4%B8%AD?x=%2F&x=2')
        finally:server.shutdown();server.server_close();thread.join()


class RowIsolation(Grounded):
    def test_bad_quote_keeps_other_rows_and_duplicate_ids_are_isolated(self):
        aid,home=self.site()
        links=g.extract_links(home)
        rows=[g.rule_decision(h) for h in links[:2]]
        bad=deepcopy(rows[1]);bad['operation_quotes']=['原件没有的一个字']
        good,errors=g.isolate_decisions([rows[0],bad],links)
        self.assertEqual((len(good),len(errors)),(1,1))
        self.assertEqual(errors[0]['original_row'],bad)
        self.assertEqual(len(g.isolate_decisions([rows[0],rows[0]],links)[0]),0)

    def test_new_id_tool_binds_quotes_and_empty_operations(self):
        aid,home=self.site()
        links=g.extract_links(home)[:1]
        env={'request_id':'paid','tool_call_id':'tool','arguments':{'entries':[{'row':0,'type':0,'quote':0}]}}
        with patch.object(g,'ModelGateway'),patch.object(g,'model_tool_decision',return_value=('job',env)):
            rows,receipt=g.id_selection(None,links,'scope')
        self.assertEqual(rows[0]['quote'],links[0]['anchor'])
        self.assertEqual(rows[0]['operation_quotes'],[])
        self.assertEqual(len(g.bind_decisions(rows,links)),1)

    def test_formal_v4_model_entry_and_restart(self):
        aid,home=self.site()
        env={'request_id':'paid','tool_call_id':'tool','arguments':{'entries':[{'row':0,'type':0,'quote':0}]}}
        with patch.object(g,'model_tool_decision',return_value=('job',env)) as dispatch:
            first=self.run_new(home,target=1,entry_selection='model')
            again=self.run_new(home,target=1,entry_selection='model')
        self.assertEqual(first['listed_unique_candidates'],1,first)
        self.assertEqual(dispatch.call_count,1)
        self.assertEqual(again['new_dispatches'],{'model':0,'GET':0,'search':0})

    def test_v4_batch_reuses_original_v3_session_binding(self):
        aid,home=self.site()
        first=self.run_new(home,target=1)
        second=self.run_new(home,target=2,batch_key='next')
        self.assertEqual(second['listed_unique_candidates'],2,second)
        with self.pool.pool.connect() as c:
            frozen=json.loads(c.execute('select config from runs where id=?',(self.f.cfg['run_id'],)).fetchone()[0])
        self.assertEqual(frozen['model_protocol'],'entry-tools')

    def test_archived_unadmitted_entry_is_held_before_directory_or_candidate_GET(self):
        aid,home=self.site()
        hold=self.root/'holds.json';save_json(hold,{'hosts':[],'entry_identities':[g.entry_identity('https://tools.example.org/index')]})
        source={**home,'dispatch_holds':{'reference':reference(hold)}}
        first=self.run_new(source,target=10)
        self.assertIsNone(first['stopped'],first)
        with self.pool.pool.connect() as c:
            held=c.execute("select count(*) from candidate_batch_rows where result='HELD'").fetchone()[0]
        self.assertEqual(held,1)
        self.assertFalse(any(r['candidate']['entry_url'].endswith('/index') for r in self.pool.rows()))

    def test_paid_invalid_id_response_keeps_legal_rows_without_retry(self):
        from site_planner.discovery_agent import SettledSelectionRejected
        aid,home=self.site();links=g.extract_links(home)[:2]
        raw=[{'row':0,'type':0,'quote':0},{'row':1,'type':99,'quote':0}]
        cause={'request_ids':['original-paid'],'tool_call_id':'original-tool'}
        with patch.object(g,'ModelGateway'),patch.object(g,'model_tool_decision',side_effect=SettledSelectionRejected('old-job',['original-paid'])) as call,patch.object(g,'settled_selection_rows',return_value=(raw,cause)):
            rows,receipt=g.id_selection(None,links,'scope')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['operation_quotes'],[])
        self.assertEqual(receipt['provider_arguments']['entries'],raw)
        self.assertEqual(len(receipt['mapping_errors']),1);self.assertEqual(call.call_count,1)

    def test_entry_id_chunk_reuses_original_tool_schema_across_optional_ops_change(self):
        aid,home=self.site();links=g.extract_links(home)[:1]
        env={'request_id':'paid','tool_call_id':'tool','arguments':{'entries':[{'row':0,'type':0,'quote':0}]}}
        with patch.object(g,'ModelGateway'),patch.object(g,'model_tool_decision',return_value=('job',env)):
            _,receipt=g.id_selection(None,links,'fixed-scope')
        ledger=BatchLedger(self.root/'frozen-tools.db',self.f.cfg,initialize=True)
        old_tools=[{'type':'function','function':{'name':'original_tool','parameters':{'required':['ops']}}}]
        original={'protocol':'native-tool-1','input':receipt['payload'],'tools':old_tools,'system':'original system','reasoning_effort':'low'}
        jid=ledger.enqueue('ai-grounded-entry-ids-1',original)
        job=ledger.claim('ai-grounded-entry-ids-1',job_id=jid);ledger.finish(job,result=env)
        with patch.object(g,'ModelGateway'),patch.object(g,'model_tool_decision',return_value=(jid,env)) as decide:
            rows,new_receipt=g.id_selection(ledger,links,'fixed-scope')
        self.assertEqual(decide.call_args.args[4],old_tools)
        self.assertEqual(decide.call_args.kwargs['system'],'original system')
        self.assertEqual(rows[0]['operation_quotes'],[])
        with ledger.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
