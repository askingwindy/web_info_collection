"""v6 formal producer, original bytes, provider ledger and protocol isolation."""
from copy import deepcopy
import io
import json
from unittest.mock import patch
import unittest

import test_grounded_producer as fixture
from site_planner import page_purpose as p
from site_planner import grounded_entries as g
from site_planner.producer_evidence import business_signature
from webcollect.batch_core import BatchLedger,OutcomeUnknown,save_json
from site_planner.discovery_tools import reference

class Purpose(unittest.TestCase):
    def setUp(self):
        self.f=fixture.Grounded('test_formal_CLI_seed_expansion_rules_provenance_and_restart_zero_IO')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.ledger=BatchLedger(self.f.root/'model.db',self.f.f.cfg,initialize=True)
    def document(self,html):
        return self.f.site(html=html)[1]
    def ev(self,html):return p.material(self.document(html))
    def test_footer_controls_and_marketing_cannot_prove_public_demo(self):
        for html in ['<main><h1>AI硬件专区</h1><p>案例可视化效率</p></main><footer><h2>云服务健康看板</h2><input name="search"><table></table></footer>',
                     '<main><h1>产品营销介绍</h1><p>智能数据查询、分析与可视化反馈的工作流系统</p><button>购买</button></main>']:
            with self.assertRaises(ValueError):p.demo_proof(self.document(html))
    def test_controls_need_same_main_owner(self):
        html='<main><h1>订单管理表格</h1><table></table><select name="status"></select></main>'
        result=p.demo_proof(self.document(html));self.assertEqual(result['acceptance'],'STATIC_PREREQUISITE_ONLY')
        self.assertFalse(result['anonymous_controls_proven'])
    def test_generic_punctuation_and_type_specific_support(self):
        for t in ['更多>>','详情>>',' 查看详情 » ','Read more...']:self.assertTrue(p.generic(t))
        ev=self.ev('<main><h1>什么是购物奖励</h1><p>'+('购物奖励说明文本。'*12)+'</p></main>')
        self.assertTrue(p.supports('内容详情',ev['units']));self.assertFalse(p.supports('功能页',ev['units']))
    def test_shqip_region_and_hreflang_excluded_not_path_guess(self):
        doc=self.document('<html><main><a href="/sq/">普通业务</a></main><div class="language-menu"><a href="/sq/lang">Shqip</a><a href="/zh/">中文</a></div><a hreflang="fr" href="/fr/">Français</a></html>')
        links=g.extract_links(doc,strict=True);reasons={h['anchor']:g.language_or_login(h) for h in links}
        self.assertIsNone(reasons['普通业务']);self.assertIsNone(reasons['中文'])
        self.assertEqual(reasons['Shqip'],'non_chinese_language_switch');self.assertEqual(reasons['Français'],'non_chinese_language_switch')
    def test_old_frozen_language_filter_does_not_adopt_v6_menu_policy(self):
        link={'uri':'https://tools.example.org/fr/','anchor':'Français','hreflang':'fr'}
        self.assertIsNone(g.language_or_login(link))
        self.assertEqual(g.language_or_login({**link,'language_context':False}),'non_chinese_language_switch')

    def test_hex_jd_template_three_identities_and_real_differences(self):
        urls=['https://e.jd.com/nrjs/24c6738b82f0d8e1.html','https://e.jd.com/nrjs/a4127c6348b1a27e.html','https://e.jd.com/nrjs/cc64e8129ab42178.html']
        self.assertEqual(len(set(urls)),3);self.assertEqual(len({business_signature({'uri':u},version='2') for u in urls}),1)
        self.assertNotEqual(business_signature({'uri':'https://e.jd.com/search'},version='2'),business_signature({'uri':'https://e.jd.com/product'},version='2'))
    def answer(self,request,timeout):
        body=json.loads(request.data);ctx=json.loads(body['messages'][1]['content'][0]['text'])
        self.assertEqual(body['tools'][0]['function']['name'],'submit_page_purposes')
        schema=body['tools'][0]['function']['parameters']
        self.assertIn('enum',schema['properties']['entries']['items']['properties']['quotes']['items'])
        self.assertIn('row和type',body['messages'][0]['content'])
        entries=[]
        for row in ctx['rows']:
            menu=row['target_material'];known=bool(menu)
            entries.append({'row':row['row'],'type':2 if known else 4,'quotes':list(menu),'reason':'正文实体' if known else '无目标主区证据'})
        raw=deepcopy(self.f.f.provider.opener.raw)
        raw['choices']=[{'finish_reason':'tool_calls','message':{'tool_calls':[{'id':'purpose','type':'function','function':{'name':'submit_page_purposes','arguments':json.dumps({'entries':entries,'inspect':[]})}}]}}]
        return io.BytesIO(json.dumps(raw).encode())
    def test_formal_produce_entries_v6_real_gateway_fallback_save_and_restart(self):
        home=self.document('<html><main><h1>本站中文工具</h1><a href="/a">甲页面</a><a href="/b">乙页面</a></main></html>')
        def get(ledger,batch,uri,root):
            target=self.f.site(uri=uri,html='<main><h1>条目甲</h1><p>'+('这是具体实体正文的长段落。'*8)+'</p></main>',confirmed=False)[1]
            jid=ledger.enqueue('application-evidence-get',{'uri':uri,'policy':'test'})
            job=ledger.claim('application-evidence-get',job_id=jid)
            body={k:v for k,v in target.items() if k!='reference'};body['job_id']=jid
            path=self.f.root/(jid+'.json');save_json(path,body);ref=reference(path)
            ledger.finish(job,result=ref)
            return body,ref
        with patch.object(p,'homepage_document',side_effect=get),patch.object(self.f.f.provider.opener,'open',side_effect=self.answer):
            report=self.f.run_new(home,key='v6',target=2,model_protocol='entry-tools-6')
            replay=self.f.run_new(home,key='v6',target=2,model_protocol='entry-tools-6')
        self.assertEqual(report['listed_unique_candidates'],2,report);self.assertEqual(report['new_dispatches']['model'],1)
        self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})
        for row in self.f.pool.rows(protocols=('webcollect-data-candidate-2',)):
            self.assertEqual(set(row['candidate']),{'schema_version','candidate_kind','entry_url','requested_goal'})
            src=row['sources'][0];self.assertEqual(src['selection_method'],'model_fallback')
            self.assertEqual(src['purpose_evidence']['final_page_type'],'内容详情')
            claim=self.f.pool.claim_next('offline-w1','claim-'+row['candidate_id'],candidate_id=row['candidate_id'],protocols=('webcollect-data-candidate-2',))
            self.assertEqual(claim['snapshot'],row['candidate'])
            self.assertEqual(self.f.pool.claim_next('offline-w2','other-'+row['candidate_id'],candidate_id=row['candidate_id'],protocols=('webcollect-data-candidate-2',))['state'],'EMPTY')
            self.f.pool.finish(claim,state='failed',stage='offline_fixture',reason='temporary fixture checks original result writeback contract')
    def test_formal_preflight_reads_original_job_even_without_visit(self):
        home=self.document('<main><a href="/a">甲页面</a><a href="/b">乙页面</a></main>')
        jid=self.ledger.enqueue('candidate-entry-http',{'uri':'https://tools.example.org/a','policy':'producer-entry-http-get-1'})
        job=self.ledger.claim('candidate-entry-http',job_id=jid)
        self.ledger.finish(job,'review_required',error='SiteStopped')
        with patch.object(p,'homepage_document',side_effect=ValueError('缺目标原件')) as get,patch.object(self.f.f.provider.opener,'open',side_effect=self.answer):
            report=self.f.run_new(home,key='preflight',target=1,model_protocol='entry-tools-6')
        self.assertEqual(report['listed_unique_candidates'],1,report)
        self.assertTrue(all(call.args[2]!='https://tools.example.org/a' for call in get.call_args_list))
        self.assertEqual(self.ledger.get(jid)['state'],'review_required')

    def test_missing_evidence_model_still_called_and_preserves_unknown(self):
        home=self.document('<main><a href="/a">甲页面</a></main>');links=g.extract_links(home)
        with patch.object(p,'homepage_document',side_effect=ValueError('缺目标原件')),patch.object(self.f.f.provider.opener,'open',side_effect=self.answer):
            rows,receipt=p.classify(self.ledger,links,'offline',self.f.root)
        self.assertEqual(len(receipt['calls']),1);self.assertEqual(rows[0]['page_type'],'UNKNOWN')
    def test_foreign_or_missing_model_evidence_cannot_fill_known_type(self):
        home=self.document('<main><a href="/a">更多&gt;&gt;</a></main>');links=g.extract_links(home)
        env={'request_id':'r','tool_call_id':'t','arguments':{'entries':[{'row':0,'type':0,'quotes':['q999'],'reason':'不受支持'}],'inspect':[]}}
        with patch.object(p,'homepage_document',side_effect=ValueError('目标缺证')),patch.object(p,'model_tool_decision',return_value=('j',env)):
            rows,receipt=p.classify(self.ledger,links,'offline',self.f.root)
        self.assertEqual(rows[0]['page_type'],'UNKNOWN');self.assertIn('不足',receipt['records'][0]['reason'])

    def test_paid_plain_json_ids_recovered_without_new_request(self):
        home=self.document('<main><a href="/a">甲页面</a><a href="/b">乙页面</a></main>')
        def plain(request,timeout):
            raw=json.loads(self.answer(request,timeout).getvalue())
            message=raw['choices'][0]['message'];message['content']=message.pop('tool_calls')[0]['function']['arguments']
            raw['choices'][0]['finish_reason']='stop'
            return io.BytesIO(json.dumps(raw).encode())
        with patch.object(p,'homepage_document',side_effect=ValueError('缺目标原件')),patch.object(self.f.f.provider.opener,'open',side_effect=plain):
            report=self.f.run_new(home,key='paid-json',target=2,model_protocol='entry-tools-6')
            replay=self.f.run_new(home,key='paid-json',target=2,model_protocol='entry-tools-6')
        self.assertEqual(report['listed_unique_candidates'],2,report)
        self.assertEqual(report['new_dispatches']['model'],1)
        self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})
        for row in self.f.pool.rows(protocols=('webcollect-data-candidate-2',)):
            src=row['sources'][0]
            self.assertEqual(src['purpose_evidence']['final_page_type'],'UNKNOWN')
            self.assertEqual(src['purpose_evidence']['model_calls'][0]['response_mode'],'settled_original_reply')

    def test_same_original_evidence_reuses_model_across_scope_without_resend(self):
        home=self.document('<main><a href="/a">甲页面</a></main>');links=g.extract_links(home)
        with patch.object(p,'homepage_document',side_effect=ValueError('缺目标原件')),patch.object(self.f.f.provider.opener,'open',side_effect=self.answer):
            rows,receipt=p.classify(self.ledger,links,'first',self.f.root)
        with patch.object(p,'homepage_document',side_effect=ValueError('缺目标原件')),patch.object(self.f.f.provider.opener,'open',side_effect=AssertionError('no replacement')):
            again,reuse=p.classify(self.ledger,links,'second',self.f.root)
        self.assertEqual(reuse['calls'],[])
        self.assertTrue(reuse['records'][0]['model_calls'][0]['reused'])
        self.assertEqual(rows[0]['page_type'],again[0]['page_type'])

    def test_unknown_paid_request_never_resent(self):
        home=self.document('<main><a href="/a">甲页面</a></main>');links=g.extract_links(home)
        with patch.object(p,'homepage_document',side_effect=ValueError('缺目标原件')),patch.object(self.f.f.provider.opener,'open',side_effect=TimeoutError('timeout')):
            with self.assertRaises(OutcomeUnknown):p.classify(self.ledger,links,'offline',self.f.root)
        with patch.object(p,'homepage_document',side_effect=ValueError('缺目标原件')),patch.object(self.f.f.provider.opener,'open',side_effect=AssertionError('no resend')):
            with self.assertRaises(OutcomeUnknown):p.classify(self.ledger,links,'offline',self.f.root)

if __name__=='__main__':unittest.main()
