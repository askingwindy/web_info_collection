"""Offline formal v7, evidence selection and actual multiprocess Table2 claims."""
from copy import deepcopy
import io
import json
import multiprocessing
import sqlite3
import time
import unittest
from unittest.mock import patch
from pathlib import Path

import test_grounded_producer as fixture
from site_planner import page_purpose_v5 as p
from site_planner.candidate_pool import CandidatePool
from site_planner.discovery_tools import reference
from webcollect.batch_core import BatchLedger,load_json,save_json,OutcomeUnknown
from webcollect.planning import object_sha256


def claim_worker(pool_path,barrier,queue,n):
    pool=CandidatePool(pool_path)
    barrier.wait(15)
    claim=pool.claim_next('w'+str(n),'request-'+str(n),protocols=('webcollect-data-candidate-2',))
    queue.put({'state':claim['state'],'candidate_id':claim.get('candidate_id')})


class Business(unittest.TestCase):
    def setUp(self):
        self.f=fixture.Grounded('test_formal_CLI_seed_expansion_rules_provenance_and_restart_zero_IO')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.ledger=BatchLedger(self.f.root/'model.db',self.f.f.cfg,initialize=True)
    def document(self,html,uri='https://tools.example.org/article'):
        raw=self.f.t.docs/(object_sha256([html,uri])+'.html');raw.write_text(html)
        body={'uri':uri,'raw_html':reference(raw),'encoding':'utf-8','content':'中文正文材料','site_evidence':'homepage','chinese':True}
        path=raw.with_suffix('.json');save_json(path,body)
        return {**body,'reference':reference(path)}
    def get(self,ledger,batch,uri,root):
        html=self.target_html.get(uri,'<main><h1>正文</h1><p>'+('具体条目的完整说明文字。'*10)+'</p></main>')
        doc=self.document(html,uri);body={k:v for k,v in doc.items() if k!='reference'}
        jid=ledger.enqueue('application-evidence-get',{'uri':uri,'policy':'offline-v7'})
        if ledger.get(jid)['state']=='done':
            ref=ledger.get(jid)['result'];return load_json(ref['path']),ref
        job=ledger.claim('application-evidence-get',job_id=jid);body['job_id']=jid
        path=self.f.t.docs/(jid+'.json');save_json(path,body);ref=reference(path);ledger.finish(job,result=ref)
        return body,ref
    def provider(self,request,timeout):
        body=json.loads(request.data);ctx=json.loads(body['messages'][1]['content'][0]['text']);self.inputs.append(ctx)
        entries=[]
        for row in ctx['rows']:
            menu=row['target_material'];islegal=row['target_title']=='免责声明' or any(u['text']=='免责声明' for u in menu.values())
            entries.append({'row':row['row'],'type':2 if menu else 4,'quotes':list(menu)[:12],
                'select':not islegal and bool(menu),'business':'support' if islegal else 'public_business' if menu else 'UNKNOWN',
                'business_quotes':list(menu)[:2] if menu else [],'reason':'依据原件选择正文，法律帮助不作主营入口'})
        args={'entries':entries,'inspect':self.inspect if ctx['turn']==0 else []}
        raw=deepcopy(self.f.f.provider.opener.raw)
        if self.plain:
            msg={'role':'assistant','content':json.dumps(args)};finish='stop'
        else:
            msg={'role':'assistant','tool_calls':[{'id':'selection','type':'function','function':{'name':'submit_page_purposes','arguments':json.dumps(args)}}]};finish='tool_calls'
        raw['choices']=[{'finish_reason':finish,'message':msg}]
        return io.BytesIO(json.dumps(raw).encode())
    def run_formal(self,html=None,plain=False,inspect=()):
        home=self.f.site(html=html or '<main><a href="/a">主营条目</a><a href="/legal">免责声明</a></main>')[1]
        self.target_html={'https://tools.example.org/legal':'<main><h1>免责声明</h1><p>'+('本网站法律声明正文。'*12)+'</p></main>'}
        self.inputs=[];self.inspect=list(inspect);self.plain=plain
        with patch.object(p,'homepage_document',side_effect=self.get),patch.object(self.f.f.provider.opener,'open',side_effect=self.provider):
            report=self.f.run_new(home,key='v7',target=2,sources=[{**home,'context_only':True}])
            replay=self.f.run_new(home,key='v7',target=2,sources=[{**home,'context_only':True}])
        return report,replay
    def test_has_sidebar_does_not_hide_main_and_inline_paragraph_joined(self):
        doc=self.document('<div class="VPContent has-sidebar"><div class="VPContentDoc has-aside has-sidebar"><main><h1>Vue中文文档</h1><p>'+('内联<span>文字</span>与<a href="/ref">引用</a>组成完整段落，'*8)+'</p></main></div></div>')
        after=p.material(doc)
        self.assertTrue(after['main_region_found'])
        self.assertTrue(p.supports('内容详情',after['units']))
        self.assertEqual(sum(u['tag']=='p' and u['kind']=='body' for u in after['units']),1)
    def test_compound_content_containers_preserved_but_css_utilities_not_main(self):
        for css in ['detail-content','cont-main-l','txt-content','mobile-news-content','right-content']:
            ev=p.material(self.document('<div class="'+css+'"><h1>正文</h1><p>'+('正文说明。'*15)+'</p></div>'))
            self.assertTrue(ev['main_region_found'],css)
        for html in ['<input class="border-main" name="search">','<button class="bg-main">搜索</button>',
                     '<div class="text-main"><input name="search"></div>']:
            self.assertFalse(p.material(self.document(html))['main_region_found'])

    def test_sidebar_footer_search_stay_excluded(self):
        doc=self.document('<aside><p>侧栏正文</p><input name="secret"></aside><footer><main><h1>看板</h1><input name="search"></main></footer><main><h1>正文</h1><p>'+('实际正文内容。'*12)+'</p></main>')
        units=p.material(doc)['units'];self.assertFalse(any('侧栏' in u['text'] or u['kind']=='control' for u in units))
        self.assertTrue(p.supports('内容详情',units))
    def test_mixed_catalog_not_forced_into_detail_or_three_inline_links(self):
        html='<main><p>主题介绍。</p><dl>'+''.join('<dt><a href="/x'+str(i)+'">模块'+str(i)+'</a></dt><dd>'+('模块介绍内容。'*20)+'</dd>' for i in range(3))+'</dl></main>'
        ev=p.material(self.document(html));self.assertTrue(p.supports('检索或列表',ev['units']));self.assertFalse(p.accepts('内容详情',ev['units'],ev))
        ev=p.material(self.document('<main><p>'+('文章正文。'*12)+'<a href="/a">引用甲</a><a href="/b">引用乙</a><a href="/c">引用丙</a></p></main>'))
        self.assertFalse(p.supports('检索或列表',ev['units']));self.assertTrue(p.accepts('内容详情',ev['units'],ev))
    def test_legal_cannot_be_selected_even_if_model_calls_it_public_business(self):
        ev=p.material(self.document('<title>免责声明 - 中文站</title><main><h1>免责声明</h1><p>'+('法律正文。'*15)+'</p></main>'))
        menu=p.numbered(ev['units'],5000)
        proposal={'select':True,'business':'public_business','business_quotes':list(menu)[:2]}
        self.assertFalse(p.business_supported(proposal,menu,ev))
    def test_formal_business_selection_filters_legal_and_restart_zero_io(self):
        report,replay=self.run_formal();self.assertEqual(report['listed_unique_candidates'],1,report)
        self.assertEqual(report['new_dispatches']['model'],1)
        self.assertEqual(self.inputs[0]['rows'][0]['site_context']['category'],'在线工具')
        self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})
        rows=self.f.pool.rows(protocols=('webcollect-data-candidate-2',));self.assertEqual(len(rows),1);self.assertEqual(rows[0]['candidate']['entry_url'],'https://tools.example.org/a')
        self.assertEqual(set(rows[0]['candidate']),{'schema_version','candidate_kind','entry_url','requested_goal'})
        rec=rows[0]['sources'][0]['purpose_evidence'];self.assertTrue(rec['selected']);self.assertEqual(rec['business'],'public_business')
    def test_no_new_evidence_inspect_sends_only_one_request(self):
        report,replay=self.run_formal(inspect=[0]);self.assertEqual(report['listed_unique_candidates'],1,report)
        self.assertEqual(len(self.inputs),1);self.assertFalse(self.inputs[0]['rows'][0]['can_inspect'])
        rec=self.f.pool.rows(protocols=('webcollect-data-candidate-2',))[0]['sources'][0]['purpose_evidence'];self.assertIn('NO_NEW_EVIDENCE',rec['inspect_result'])
    def test_real_extra_saved_material_allows_exactly_one_more_inspection(self):
        home=self.f.site(html='<main><a href="/a">正文条目</a></main>')[1]
        from site_planner.grounded_entries import extract_links
        self.target_html={'https://tools.example.org/a':'<main><h1>中文正文</h1>'+''.join('<p>'+str(i)+('段落原件文字。'*120)+'</p>' for i in range(8))+'</main>'}
        self.inputs=[];self.inspect=[0];self.plain=False
        with patch.object(p,'homepage_document',side_effect=self.get),patch.object(self.f.f.provider.opener,'open',side_effect=self.provider):
            rows,receipt=p.classify(self.ledger,extract_links(home,strict=True),'additional',self.f.root)
        self.assertEqual(len(rows),1);self.assertEqual(len(self.inputs),2)
        self.assertTrue(self.inputs[0]['rows'][0]['can_inspect'])
        self.assertGreater(len(self.inputs[1]['rows'][0]['target_material']),len(self.inputs[0]['rows'][0]['target_material']))
        with patch.object(p,'homepage_document',side_effect=self.get),patch.object(self.f.f.provider.opener,'open',side_effect=AssertionError('reuse richer original response')):
            repeated,reused=p.classify(self.ledger,extract_links(home,strict=True),'additional-again',self.f.root)
        self.assertEqual(reused['calls'],[])
        self.assertEqual(reused['records'][0]['model_calls'][0]['request_id'],receipt['calls'][-1]['request_id'])
    def test_formal_all_legal_returns_zero_and_replay_no_io(self):
        report,replay=self.run_formal(html='<main><a href="/legal">免责声明</a></main>')
        self.assertEqual(report['listed_unique_candidates'],0,report)
        self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})
        self.assertEqual(self.f.pool.stats()['candidate_total'],0)
    def test_query_planner_gets_search_role_not_page_submission_instructions(self):
        from site_planner import producer_query_plan as qp
        seen=[]
        def plan(ledger,gateway,purpose,payload,schema):
            seen.append(payload);return {'queries':['中文匿名表格公开演示']}
        state={'queries':{},'blocked':{}}
        with patch.object(qp,'model_decision',side_effect=plan):
            result=qp.next_query(self.f.pool.pool,self.ledger,'offline-new','unit',('企业后台与开源演示站',),state,[],self.f.t.docs,
                                 independent=True,public_business=True,purpose_grounded=True,purpose_protocol='entry-tools-7')
        self.assertIn('匿名',result['query']);self.assertNotIn('submit_page_purposes',seen[0]['instruction'])
        self.assertIn('三种',seen[0]['goal'])

    def test_paid_json_recovery_does_not_rewrite_original_status(self):
        report,replay=self.run_formal(plain=True);self.assertEqual(report['listed_unique_candidates'],1,report)
        with self.ledger.connect() as con:self.assertEqual(con.execute('SELECT state FROM model_requests').fetchone()[0],'invalid_response')
        self.assertEqual(replay['new_dispatches']['model'],0)
    def test_unknown_stays_unselected_without_business_proof_and_no_resend(self):
        home=self.f.site(html='<main><a href="/a">未判入口</a></main>')[1];from site_planner.grounded_entries import extract_links
        links=extract_links(home,strict=True);self.inputs=[];self.inspect=[];self.plain=False
        with patch.object(p,'homepage_document',side_effect=ValueError('缺原件')),patch.object(self.f.f.provider.opener,'open',side_effect=self.provider):
            rows,receipt=p.classify(self.ledger,links,'first',self.f.root)
        self.assertEqual(rows,[]);self.assertEqual(receipt['records'][0]['final_page_type'],'UNKNOWN')
        with patch.object(p,'homepage_document',side_effect=ValueError('缺原件')),patch.object(self.f.f.provider.opener,'open',side_effect=AssertionError('no repeat')):
            rows,reuse=p.classify(self.ledger,links,'second',self.f.root)
        self.assertEqual(reuse['calls'],[])
    def test_table2_primary_key_and_eight_processes_only_one_holder(self):
        report,_=self.run_formal();cid=report['candidate_ids'][0]
        self.assertEqual(self.f.pool.concurrency_contract()['primary_key'],'candidate_id')
        ctx=multiprocessing.get_context('fork');barrier=ctx.Barrier(8);queue=ctx.Queue()
        processes=[ctx.Process(target=claim_worker,args=(str(self.f.pool.path),barrier,queue,i)) for i in range(8)]
        for proc in processes:proc.start()
        for proc in processes:
            proc.join(20)
            if proc.is_alive():proc.kill();proc.join();self.fail('claim race timeout')
            self.assertEqual(proc.exitcode,0)
        results=[queue.get(timeout=5) for _ in processes]
        self.assertEqual(sum(r['state']=='consuming' for r in results),1,results)
        self.assertEqual({r['candidate_id'] for r in results if r['candidate_id']},{cid})
        with self.f.pool.pool.connect() as con:self.assertEqual(con.execute("SELECT COUNT(*) FROM candidate_claims WHERE state='consuming'").fetchone()[0],1)
    def test_missing_claim_index_fails_closed_without_auto_migration(self):
        with self.f.pool.transaction() as con:con.execute('DROP INDEX one_candidate_holder')
        with self.assertRaisesRegex(ValueError,'exclusive-claim'):CandidatePool(self.f.pool.path)
    def test_expired_claim_is_reconciled_not_reassigned(self):
        report,_=self.run_formal();cid=report['candidate_ids'][0]
        claim=self.f.pool.claim_next('old','old-request',candidate_id=cid,protocols=('webcollect-data-candidate-2',))
        with self.f.pool.transaction() as con:con.execute('UPDATE candidate_claims SET expires=0 WHERE claim_id=?',(claim['claim_id'],))
        other=self.f.pool.claim_next('new','new-request',candidate_id=cid,protocols=('webcollect-data-candidate-2',))
        self.assertEqual(other['state'],'EMPTY');self.assertEqual(self.f.pool.get_claim(claim['claim_id'])['state'],'reconcile')
        with self.assertRaises(ValueError):self.f.pool.stage(claim,'execute')

if __name__=='__main__':unittest.main()
