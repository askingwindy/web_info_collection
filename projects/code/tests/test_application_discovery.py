"""P1-P5 disposable new-policy integration and invariant regression checks."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import io
import multiprocessing
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import test_producer_tools as native
from application_discovery_fixtures import document, seed
from site_planner.application_discovery import Discovery, POLICY, classify_sites
from site_planner.candidate_discovery import produce_entries
from site_planner.candidate_pool import CandidatePool, VERSION2, candidate_dedup_key
from site_planner.discovery_tools import reference
from site_planner.entry_selection import confirmed_category
from webcollect.batch_core import BatchLedger, save_json
from webcollect.candidate_accounting import discovery_shares
from quality_inspector.application_capacity import admit


class SiteTables(unittest.TestCase):
    def setUp(self):
        self.f=native.ProducerToolTests('test_fresh_glm_session_selects_native_tools_without_a_flag')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.inv=self.f.inv;self.pool=self.inv.pool;self.root=self.inv.root
        self.sites=Discovery(self.pool,install=True)
        self.docs=self.root/"output";self.docs.mkdir(exist_ok=True)
        self.inv.proof=self.docs/"source.json";save_json(self.inv.proof,{"CONTROLLED":"source"})

    def source(self, path='/scientific/', host='www.muxtly.example.org', name='科学计算器'):
        return self.inv.hit(0,host,title=name,content=name+' 支持输入数值并查看结果') | {'uri':'https://'+host+path}

    def run_producer(self,sources,rows,key='main',**kwargs):
        self.f.response(rows)
        args=dict(pool_path=self.pool.path,ledger_path=self.root/'model.db',history_set=self.f.chain,
            output=self.root/'output'/key,sources=sources,batch_key=key,discovery_mode='mixed',target=10,
            max_batches=1,batch_size=10)
        args.update(kwargs)
        return produce_entries(self.f.cfg,**args)

    def row(self,i=0,home=1,category='在线工具',page='功能页'):
        return {'source_index':i,'page_type':page,'classification':{'parent_category':category,
            'function_source_index':home,'homepage_source_index':home,'function_quote':'本站提供中文在线计算与单位转换服务'}}

    def test_new_site_classifies_homepage_then_old_reader_confirms(self):
        entry=self.source(); home=document(self.docs,'https://www.muxtly.example.org/zh-CN/')
        report=self.run_producer([entry,{**home,'context_only':True}],[self.row()])
        self.assertEqual(report['row_results'],{'NEW':1},report)
        row=self.pool.rows(protocols=(VERSION2,))[0]
        self.assertEqual(set(row['candidate']),{'schema_version','candidate_kind','entry_url','requested_goal'})
        self.assertEqual(confirmed_category(row['sources']),'在线工具')
        site=self.sites.get(row['application_id'])
        self.assertEqual((site['homepage'],site['language'],site['category'],site['mining_state']),
                         (home['uri'],'zh','在线工具','complete'))
        replay=self.run_producer([entry,{**home,'context_only':True}],[self.row()])
        self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})

    def test_snippet_cannot_classify_and_unknown_never_gets_entry_GET(self):
        entry=self.source()
        with patch('site_planner.application_discovery.homepage_document',side_effect=ValueError('offline no homepage')):
            report=self.run_producer([entry],[self.row(home=0)])
        self.assertEqual(report['row_results'],{'REJECTED':1},report)
        self.assertEqual(self.inv.entry_http.call_count,0)
        self.assertEqual(self.pool.stats()['candidate_total'],0)

    def test_foreign_or_tampered_homepage_and_conflicting_proposals(self):
        entry=self.source();home=document(self.docs,'https://www.muxtly.example.org/')
        bad={**home,'content':'伪造全文'}
        result=self.run_producer([entry,{**bad,'context_only':True}],[self.row()],key='bad')
        self.assertEqual(result['listed_unique_candidates'],0)
        self.assertEqual(self.inv.entry_http.call_count,0)
        result=self.run_producer([entry,{**home,'context_only':True}],
                                 [self.row(),self.row(category='小游戏')],key='conflict')
        self.assertEqual(result['listed_unique_candidates'],0,result)
        self.assertEqual(self.inv.entry_http.call_count,0)

    def test_mixed_science_fraction_and_wiki_browsing_independent_keys(self):
        seed(self.pool,self.docs,'https://www.muxtly.example.org/')
        seed(self.pool,self.docs,'https://wiki.example.org/','百科与文档','本站提供中文百科知识与浏览目录')
        science=self.source();fraction=self.source('/fraction/',name='分数计算器')
        wiki=self.source('/wiki/甲条目',host='wiki.example.org',name='甲条目')
        def row(i,h):
            return {'source_index':i,'page_type':'内容详情' if i==2 else '功能页',
                'browsing_evidence' if i==2 else 'entry_function':{'name_quote':h['title'],'operation_quote':'支持输入数值并查看结果'}}
        result=self.run_producer([science,fraction,wiki],[row(i,h) for i,h in enumerate([science,fraction,wiki])])
        self.assertEqual(result['row_results'],{'NEW':3},result)
        old=self.run_producer([science,fraction,wiki],[],key='old')
        self.assertEqual(old['new_dispatches'],{'model':0,'GET':0,'search':0})

    def test_all_protocols_and_explicit_targets_require_table1(self):
        goals=self.root/'goals.json';goal={'kind':'calculate','entity':'fraction','parameters':{'value':2}}
        save_json(goals,{'schema_version':'webcollect-caller-goals-1','goals':[{'uri':self.source()['uri'],'requested_goal':goal}]})
        first=self.run_producer([],[],goals_path=goals,key='missing')
        self.assertEqual(first['row_results'],{'REJECTED':1})
        self.assertEqual(first['new_dispatches']['GET'],0)
        seed(self.pool,self.docs,self.source()['uri'])
        second=self.run_producer([],[],goals_path=goals,key='proven')
        self.assertEqual(second['row_results'],{'NEW':1},second)
        claim=self.pool.claim_next('worker','target',protocols=(VERSION2,))
        self.assertEqual(claim['snapshot']['requested_goal'],goal)
        self.assertEqual(confirmed_category(claim['sources']),'在线工具')

    def test_GET_403_404_521_failures_do_not_block_other_sources(self):
        hits=[]
        for i in range(4):
            hit=self.source('/tool'+str(i)+'/',host=f'h{i}.example.org');seed(self.pool,self.docs,hit['uri']);hits.append(hit)
        statuses=iter([403,404,521,200]);self.inv.entry_http.side_effect=lambda uri,*a:(next(statuses),uri)
        report=self.run_producer(hits,[{'source_index':i,'page_type':'功能页','entry_function':{
            'name_quote':h['title'],'operation_quote':'支持输入数值并查看结果'}} for i,h in enumerate(hits)])
        self.assertEqual(report['row_results'],{'REJECTED':3,'NEW':1},report)

    def test_scope_interruption_quarantine_unfinished_and_incremental(self):
        aid,_=seed(self.pool,self.docs,self.source()['uri'])
        items=[{'uri':'/a'},{'uri':'/b'}]
        refs=[reference(self.inv.proof)]
        sid=self.sites.freeze_scope(aid,'run',items,refs)
        self.sites.conclude(sid,items[0],{'result':'NEW','candidate_id':'a'})
        self.sites.conclude(sid,items[1],{'result':'HELD'})
        reopened=Discovery(CandidatePool(self.pool.path),install=True)
        self.assertEqual(reopened.remaining(sid),[items[1]])
        self.assertEqual(reopened.freeze_scope(aid,'run',items,refs),sid)
        self.assertEqual(reopened.get(aid)['mining_state'],'running')
        reopened.conclude(sid,items[1],{'result':'REJECTED','reason':'404'})
        self.assertEqual(reopened.get(aid)['mining_state'],'complete')
        next_sid=reopened.freeze_scope(aid,'incremental',[{'uri':'/c'}],refs)
        self.assertNotEqual(sid,next_sid);self.assertEqual(reopened.get(aid)['mining_state'],'running')
        reopened.freeze_scope(aid,'run',items,refs)
        self.assertEqual(reopened.get(aid)['scope_id'],next_sid)
        self.assertEqual(reopened.get(aid)['mining_state'],'running')
        empty=reopened.freeze_scope(aid,'empty',[],refs)
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute('SELECT state FROM application_scopes WHERE scope_id=?',(empty,)).fetchone()[0],'complete')
        self.assertEqual(reopened.get(aid)['mining_state'],'running')

    def test_duplicate_conflict_original_body_claim_sources_and_quarantine(self):
        aid,_=seed(self.pool,self.docs,self.source()['uri']);candidate=self.inv.entry(self.source()['uri'])
        cid=self.pool.put(candidate,self.inv.source())
        with self.pool.pool.connect() as con: body=con.execute('SELECT body FROM data_candidates WHERE candidate_id=?',(cid,)).fetchone()[0]
        good=self.sites.source(aid,candidate['entry_url'],self.inv.source())
        self.assertEqual(self.pool.put(candidate,good),cid)
        self.assertEqual(confirmed_category(self.inv.rows_for(cid)['sources']),'在线工具')
        claim=self.pool.claim_next('w','c',protocols=(VERSION2,))
        self.assertEqual(self.sites.quarantine(cid,reason='not eligible',evidence=good['references'])['result'],'SKIPPED')
        self.assertEqual(self.pool.get_claim(claim['claim_id'])['sources'],claim['sources'])
        other=self.inv.entry(self.source('/other/')['uri'])
        bad=deepcopy(good);bad['application_classification']['status']='CONFLICT';bad.pop('table_policy')
        conflict=self.pool.put(other,bad)
        with self.assertRaisesRegex(ValueError,'conflicting category'):self.pool.put(other,good)
        receipt=self.sites.quarantine(conflict,reason='original protocol conflict',evidence=good['references'])
        self.assertEqual(receipt['result'],'QUARANTINED')
        with self.assertRaises(ValueError):self.sites.quarantine(conflict,reason='cannot release',evidence=good['references'],release=True)
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute('SELECT body FROM data_candidates WHERE candidate_id=?',(cid,)).fetchone()[0],body)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM candidate_claims WHERE candidate_id=?',(conflict,)).fetchone()[0],0)

    def test_publication_transaction_fences_decision_change_and_competing_producers(self):
        aid,home=seed(self.pool,self.docs,self.source()['uri']);candidate=self.inv.entry(self.source()['uri'])
        source=self.sites.source(aid,candidate['entry_url'],self.inv.source())
        receipt=self.docs/'race-http.json';save_json(receipt,{'method':'GET','result':'PASS','http_status':200,'entry_uri':candidate['entry_url']})
        source['entry_http']=reference(receipt);source['references'].append(reference(receipt))
        def publish(i):
            h={'run_id':'race','batch':0,'raw_index':i,'request_id':'race','response_sha256':str(i),'row_id':str(i)}
            return CandidatePool(self.pool.path).publish_row(h,candidate,source,application_id=aid)
        with ThreadPoolExecutor(2) as ex:results=list(ex.map(publish,range(2)))
        self.assertEqual(sorted(r['result'] for r in results),['DUPLICATE','NEW'])
        decision=deepcopy(self.sites.get(aid)['decision']);decision['parent_category']='学习教育'
        self.sites.decide(aid,decision,home,expected=source['site_decision_id'])
        with self.assertRaisesRegex(ValueError,'changed'):publish(3)

    def test_schema_positional_old_inserts_migration_rollback_and_index_scale(self):
        with self.pool.pool.connect() as con:
            before=[(r['name'],r['sql']) for r in con.execute("SELECT name,sql FROM sqlite_master WHERE name IN ('applications','data_candidates')")]
        Discovery(self.pool,install=True)
        with self.pool.transaction() as con:
            con.executemany('INSERT INTO applications VALUES(?,?,?,?,?)',((f'h{n}',f'h{n}.example.org','history','UNKNOWN',1) for n in range(200000)))
            con.executemany('INSERT INTO data_candidates VALUES(?,?,?,?,?,?,?)',((f'c{n}',f'h{n}',f'k{n}',1,json.dumps(self.inv.entry(f'https://h{n}.example.org/')),1,'pending') for n in range(200000)))
            after=[(r['name'],r['sql']) for r in con.execute("SELECT name,sql FROM sqlite_master WHERE name IN ('applications','data_candidates')")]
            self.assertEqual(before,after)
            plans=[r['detail'] for sql,params in [
                ('SELECT * FROM applications WHERE host=?',('h199999.example.org',)),
                ('SELECT * FROM data_candidates WHERE dedup_key=?',('k199999',)),
                ('SELECT * FROM application_discovery WHERE application_id=?',('h199999',)),
                ('SELECT * FROM application_scope_items WHERE scope_id=? AND item_key=?',('x','y'))]
                for r in con.execute('EXPLAIN QUERY PLAN '+sql,params)]
        self.assertTrue(all('INDEX' in p for p in plans),plans)
        # Rollback keeps new tables and all old rows: only new publication stops.
        self.assertEqual(CandidatePool(self.pool.path).pool.application('https://h199999.example.org/')['id'],'h199999')

    def test_capacity_499_plus_two_replacement_and_pending(self):
        existing=[{'sample_id':str(n),'application_id':'app'} for n in range(499)]
        proposed=[{'sample_id':'new1','application_id':'app'},{'sample_id':'new2','application_id':'app'},existing[0]]
        report=admit(existing,proposed)
        self.assertEqual(report['accepted_sample_ids'],['new1'])
        self.assertEqual(report['over_capacity_sample_ids'],['new2'])
        self.assertEqual(report['counts'],{'app':500})
        self.assertEqual(report['already_effective_sample_ids'],['0'])
        # Re-read/restart and alternative copies have the same unique denominator.
        self.assertEqual(admit(existing+existing,[])['counts'],{'app':499})

    def test_request_allocation_multiple_mining_calls_zero_NEW_and_unsettled(self):
        def request(j,i,o):return {'id':j,'job_id':j,'state':'succeeded','error':None,'started':1,'usage':json.dumps({'input_tokens':i,'output_tokens':o})}
        requests=[request('one',5,3),request('two',3,1),request('zero',99,99)]
        pubs=[{'request_id':'one','candidate_id':c} for c in ('a','b')]+[{'request_id':'two','candidate_id':c} for c in ('a','b')]
        shares,attributed=discovery_shares(requests,pubs)
        self.assertEqual(shares['a']['allocated'],{'input_tokens':5,'output_tokens':3,'total_tokens':8})
        self.assertEqual(shares['b']['allocated'],{'input_tokens':3,'output_tokens':1,'total_tokens':4})
        self.assertEqual(attributed,{'one','two'})

    def test_real_homepage_fetch_code_multiline_document_and_original_recovery(self):
        from site_planner.application_discovery import homepage_document
        ledger=BatchLedger(self.root/'homepage-jobs.db',self.f.cfg,initialize=True)
        uri='https://www.muxtly.example.org/zh-CN/'
        @contextmanager
        def fetch(url,*args):
            response=io.BytesIO('<html lang="zh-CN"><h1>中文工具站</h1><p>本站提供中文在线计算与单位转换服务</p></html>'.encode())
            response.status=200;response.geturl=lambda:uri
            yield response
        with patch('site_planner.pipeline.open_public_get',side_effect=fetch) as get:
            first,ref=homepage_document(ledger,'homepage',uri,self.docs)
            replay,ref2=homepage_document(ledger,'homepage',uri,self.docs)
        self.assertEqual(get.call_count,1);self.assertEqual(ref,ref2)
        self.assertIn('\n',first['content']);self.assertEqual(first,replay)
        entry=self.source();home={**first,'reference':ref,'context_only':True}
        result=self.run_producer([entry,home],[self.row()])
        self.assertEqual(result['row_results'],{'NEW':1},result)

    def test_install_failure_rolls_back_additive_tables_and_preserves_old_writer(self):
        from site_planner.site_pool import SitePool
        path=self.root/'rollback.db';SitePool(path,initialize=True);pool=CandidatePool(path,install=True)
        cid=pool.put(self.inv.entry(self.source()['uri']),self.inv.source())
        original=pool.transaction
        class FailingConnection:
            def __init__(self,con):self.con=con
            def execute(self,sql,*args):
                if 'CREATE TABLE IF NOT EXISTS application_mining_requests' in sql:raise sqlite3.OperationalError('OFFLINE migration interruption')
                return self.con.execute(sql,*args)
        @contextmanager
        def failing():
            with original() as con:yield FailingConnection(con)
        with patch.object(pool,'transaction',side_effect=failing),self.assertRaises(sqlite3.OperationalError):Discovery(pool,install=True)
        with pool.pool.connect() as con:
            self.assertFalse(con.execute("SELECT 1 FROM sqlite_master WHERE name='application_discovery'").fetchone())
        self.assertEqual(pool.claim_next('old','after-rollback',protocols=(VERSION2,))['candidate_id'],cid)

    def test_homepage_declared_gb2312_keeps_raw_and_reads_chinese(self):
        from site_planner.application_discovery import homepage_document
        ledger=BatchLedger(self.root/'gbk-jobs.db',self.f.cfg,initialize=True);uri='https://gbk.example.org/'
        raw='<html><meta charset="gb2312"><h1>中文在线工具首页</h1><p>本站提供中文计算与换算服务</p></html>'.encode('gb18030')
        @contextmanager
        def fetch(url,*args):
            response=io.BytesIO(raw);response.status=200;response.geturl=lambda:uri;yield response
        with patch('site_planner.pipeline.open_public_get',side_effect=fetch):
            doc,ref=homepage_document(ledger,'gbk',uri,self.docs)
        self.assertTrue(doc['chinese']);self.assertEqual(doc['encoding'],'gb18030')
        self.assertIn('中文在线工具首页',doc['content'])
        self.assertEqual(Path(doc['raw_html']['path']).read_bytes(),raw)

    def test_known_tokens_still_balance_when_original_request_unsettled(self):
        requests=[{'id':'known','job_id':'job','state':'succeeded','error':None,'started':1,
                   'usage':json.dumps({'input_tokens':5,'output_tokens':3})},
                  {'id':'unknown','job_id':'job','state':'unknown','error':'timeout','started':2,'usage':None}]
        shares,attributed=discovery_shares(requests,[{'request_id':'job','candidate_id':c} for c in ('a','b')])
        self.assertIsNone(shares['a']['allocated']['total_tokens'])
        self.assertEqual(sum(r['known_allocated']['total_tokens'] for r in shares.values()),8)
        self.assertEqual(attributed,{'known','unknown'})

    def test_two_producer_processes_share_original_unique_key(self):
        aid,_=seed(self.pool,self.docs,self.source()['uri']);candidate=self.inv.entry(self.source()['uri'])
        source=self.sites.source(aid,candidate['entry_url'],self.inv.source())
        receipt=self.docs/'process-get.json';save_json(receipt,{'method':'GET','result':'PASS','http_status':200,'entry_uri':candidate['entry_url']})
        source['entry_http']=reference(receipt);source['references'].append(reference(receipt))
        context=multiprocessing.get_context('fork');queue=context.Queue();start=context.Event()
        def publish(i):
            start.wait(5)
            header={'run_id':'process-race','batch':0,'raw_index':i,'row_id':'process-'+str(i),'request_id':'shared','response_sha256':str(i)}
            try:queue.put(CandidatePool(self.pool.path).publish_row(header,candidate,source,application_id=aid))
            except Exception as error:queue.put({'error':repr(error)})
        workers=[context.Process(target=publish,args=(i,)) for i in range(2)]
        for worker in workers:worker.start()
        start.set();results=[queue.get(timeout=10) for worker in workers]
        for worker in workers:
            worker.join(5);self.assertEqual(worker.exitcode,0)
        self.assertEqual(sorted(r.get('result',r.get('error')) for r in results),['DUPLICATE','NEW'])
        self.assertEqual(len({r['candidate_id'] for r in results}),1)

    def test_new_search_priority_uses_effective_trajectory_coverage(self):
        aid,_=seed(self.pool,self.docs,self.source()['uri'])
        hit=self.source('/news/',host='news.example.org',name='公开新闻')
        seed(self.pool,self.docs,hit['uri'],'新闻资讯','本站提供中文新闻资讯和行业报道')
        # An explicitly synthetic effective-set projection, not a QC decision.
        with self.pool.transaction() as con:
            con.execute('INSERT INTO application_delivery_projection VALUES(?,?,?)',(aid,1,json.dumps(reference(self.inv.proof))))
        calls=[]
        def search(*args,**kwargs):
            calls.append(args[3]);return {'request_id':'OFFLINE-search','results':[{**hit,'index':0}]}
        directions=[{'direction':'tools','category':'在线工具','queries':['工具方向']},
                    {'direction':'news','category':'新闻资讯','queries':['新闻方向']}]
        with patch('site_planner.candidate_discovery.glm_search',side_effect=search):
            result=self.run_producer([], [{'source_index':0}],directions=directions,discovery_mode='expand',target=1)
        self.assertEqual(result['listed_unique_candidates'],1,result)
        self.assertEqual(calls,['新闻方向'])

    def test_new_policy_partial_publication_resumes_original_rows_without_IO(self):
        science=self.source();fraction=self.source('/fraction/',name='分数计算器')
        home=document(self.docs,'https://www.muxtly.example.org/zh-CN/')
        hits=[science,fraction,{**home,'context_only':True}];rows=[self.row(0,2),self.row(1,2)]
        publish=CandidatePool.publish_row;calls=[]
        def interrupt(pool,*args,**kwargs):
            calls.append(args[0]['raw_index'])
            if len(calls)==2:raise OSError('OFFLINE after first row publication')
            return publish(pool,*args,**kwargs)
        with patch.object(CandidatePool,'publish_row',interrupt):first=self.run_producer(hits,rows)
        self.assertEqual(first['listed_unique_candidates'],1,first)
        self.assertEqual(first['stopped']['type'],'OSError')
        before=self.inv.entry_http.call_count;requests=len(self.f.provider.opener.calls)
        replay=self.run_producer(hits,rows)
        self.assertEqual(replay['listed_unique_candidates'],2,replay)
        self.assertEqual(self.inv.entry_http.call_count,before)
        self.assertEqual(len(self.f.provider.opener.calls),requests)
        self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})

    def test_effective_capacity_500_skips_only_that_application_before_IO(self):
        capped=self.source('/new-function/');aid,_=seed(self.pool,self.docs,capped['uri'])
        healthy=self.source('/tool/',host='other.example.org');seed(self.pool,self.docs,healthy['uri'])
        with self.pool.transaction() as con:
            con.execute('INSERT INTO application_delivery_projection VALUES(?,?,?)',(aid,500,json.dumps(reference(self.inv.proof))))
        result=self.run_producer([capped,healthy],[{'source_index':0}],discovery_mode='expand',target=1)
        self.assertEqual(result['row_results'],{'NEW':1},result)
        self.assertEqual(result['excluded_sources'][0]['reason'],'application_effective_capacity_500')
        stopped=self.run_producer([capped],[],key='capacity-only',discovery_mode='expand',target=1)
        self.assertEqual(stopped['new_dispatches'],{'model':0,'GET':0,'search':0})

    def test_site_only_classifier_binds_original_quote_ids_and_reuses_decision(self):
        from site_planner.application_discovery import classify_homepage
        home=document(self.docs,'https://isolated.example.org/')
        aid=self.pool.pool.record({'schema_version':'webcollect-site-discovery-1','origin':'codex_session',
            'run_id':'offline','event_id':'site-only','uri':home['uri'],'name':'受控站点','category_hint':'UNKNOWN','source_refs':[home['reference']]})['application_id']
        self.sites.ensure(aid);ledger=BatchLedger(self.root/'site-only.db',self.f.cfg,initialize=True)
        envelope={'request_id':'OFFLINE-site-request','tool_call_id':'OFFLINE-site-call','arguments':{
            'parent_category':'在线工具','quote_ids':[0],'reason':'首页列出本站计算与转换服务'}}
        with patch('webcollect.model_gateway.ModelGateway'),patch('site_planner.discovery_agent.model_tool_decision',return_value=('OFFLINE-site-job',envelope)) as call:
            result=classify_homepage(self.pool,ledger,home,self.docs)
            replay=classify_homepage(self.pool,ledger,home,self.docs)
        self.assertEqual(call.call_count,1);self.assertEqual(result['decision_id'],replay['decision_id'])
        self.assertEqual(result['decision']['evidence'][0]['quote'],home['content'])
        self.assertEqual(result['decision']['mining_job_id'],'OFFLINE-site-job')

    def test_caller_entries_allocate_zero_selection_tokens(self):
        shares,attributed=discovery_shares([],[{'request_id':'caller-entries/receipt','candidate_id':'a'}])
        self.assertEqual(shares['a']['basis'],'caller_entry')
        self.assertEqual(shares['a']['allocated']['total_tokens'],0)
        self.assertEqual(attributed,set())


if __name__=='__main__':unittest.main()
