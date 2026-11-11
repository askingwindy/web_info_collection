"""V13 main-content witness, no history/real network; V12 keeps its old meaning."""
import unittest
from unittest.mock import patch
from copy import deepcopy
import test_producer_business_value as fixtures
from site_planner import producer_business_content as value
from site_planner import producer_business_content as old, producer_observation as observed
from webcollect.batch_core import load_json,OutcomeUnknown


class BusinessContent(unittest.TestCase):
    setUp = fixtures.BusinessValue.setUp
    original = fixtures.BusinessValue.original
    provider = fixtures.BusinessValue.provider
    def prepared(self, html):
        link=self.original(html=html);ev=value.evidence_for(self.pool,self.ledger,link)
        _,_,visible=value.prepare(link,ev,self.ledger.config.get('model'))
        return ev,visible
    def decision(self, visible):
        return {'business':'public_business','business_quote_ids':visible['content_evidence_ids'][:2],
                'reason':'仅凭当前主区实际业务内容'}
    def run_decision(self,link,scope='first'):
        with patch.object(self.f.f.b.f.f.provider.opener,'open',side_effect=self.provider):
            return value.classify(self.ledger,[link],scope,self.root,pool=self.pool)

    def test_title_date_editorial_copyright_shell_does_not_prove_business(self):
        ev,visible=self.prepared('<main><h1>中医疾病条目</h1><span>时间：2015-04-03</span>'
            '<span>来源：</span><span>作者：</span><p>(责任编辑:系统管理员)</p>'
            '<div>凡注明本网站专稿的文字内容如需转载应注明来源，否则保留版权追责权利。</div></main>')
        self.assertEqual(value.content_ids(ev),[])
        for ids in ([next(q for q,u in ev['menu'].items() if u['kind']=='heading')],list(ev['menu'])):
            proposal={'business':'public_business','business_quote_ids':ids[:6],'reason':'标题属于站点主营'}
            self.assertFalse(value.assess(proposal,ev)['selected'])
        self.assertTrue(old.assess({'business':'public_business','business_quote_ids':[next(iter(ev['menu']))],
            'reason':'旧V12只引标题仍按原义解释'},ev)['selected'])

    def test_shell_has_zero_model_dispatch_and_no_reopen(self):
        link=self.original(html='<main><h1>业务标题</h1><p>日期：2026-11-04</p><p>Copyright 2026</p></main>')
        with patch.object(value,'model_tool_decision',side_effect=AssertionError('no empty business material')):
            rows,receipt=value.classify(self.ledger,[link],'shell',self.root,pool=self.pool)
        self.assertEqual(rows,[]);self.assertEqual(receipt['calls'],[])
        self.assertEqual(receipt['records'][0]['selection_reason'],'no_citable_main_content')

    def test_short_real_body_remains_valid_without_length_gate(self):
        ev,visible=self.prepared('<main><h1>参观安排</h1><p>周一闭馆。</p></main>')
        proposal=self.decision(visible)
        self.assertTrue(value.assess(proposal,ev)['selected'])
        self.assertEqual(ev['menu'][proposal['business_quote_ids'][0]]['text'],'周一闭馆。')

    def test_title_only_citation_does_not_borrow_uncited_body(self):
        ev,visible=self.prepared('<main><h1>参观安排</h1><p>周一闭馆。</p></main>')
        heading=next(q for q,u in ev['menu'].items() if u['kind']=='heading')
        result=value.assess({'business':'public_business','business_quote_ids':[heading],'reason':'有正文但未引用'},ev)
        self.assertFalse(result['selected']);self.assertEqual(result['selection_reason'],'business_content_not_proven')

    def test_real_list_items_are_permitted_not_rejected_by_reference_disagreement(self):
        for html in ('<main><h1>专家名单</h1><ul><li><a href="/person/1">张三</a></li>'
                     '<li><a href="/person/2">李四</a></li></ul></main>',
                     '<main><h1>成果展示</h1><ul><li><a href="/1">第二十九届比赛成果...</a></li></ul></main>'):
            ev,visible=self.prepared(html)
            self.assertTrue(value.content_ids(ev))
            self.assertTrue(value.assess(self.decision(visible),ev)['selected'])

    def test_real_content_cards_need_no_ul_li_or_long_summary(self):
        ev,visible=self.prepared('<main><h1>家庭教育服务</h1>'
            '<div><a href="/activities/nov">11月家长学校活动</a></div>'
            '<div><a href="/guide/parent">家长配套服务指引</a></div></main>')
        links=[q for q,u in ev['menu'].items() if u['kind']=='link']
        self.assertTrue(links)
        self.assertTrue(value.assess({'business':'public_business','business_quote_ids':links,
            'reason':'真实活动与指南条目链接'},ev)['selected'])

    def test_actual_tool_controls_remain_permitted_without_narrative(self):
        ev,visible=self.prepared('<main><h1>面积计算器</h1><input placeholder="长度"><input placeholder="宽度">'
            '<button>计算</button><output>0</output></main>')
        self.assertTrue(any(ev['menu'][q]['kind']=='control' for q in value.content_ids(ev)))
        self.assertTrue(value.assess(self.decision(visible),ev)['selected'])

    def test_only_navigation_or_date_or_copyright_citations_stay_unproven(self):
        ev,visible=self.prepared('<main><h1>业务标题</h1><p>首页 &gt; 新闻资讯</p>'
            '<a href="/about">关于我们</a><p>2015-04-03</p><p>Produced By 某发布系统</p></main>')
        self.assertEqual(value.content_ids(ev),[])

    def test_real_body_is_not_removed_merely_for_mentioning_copyright(self):
        ev,visible=self.prepared('<main><h1>版权课程</h1><p>本课介绍版权中的署名权。</p></main>')
        self.assertTrue(value.assess(self.decision(visible),ev)['selected'])

    def test_metadata_and_omission_disclosure_do_not_imply_missing_main_body(self):
        ev,visible=self.prepared('<header>主站新闻</header><nav><a href="/">首页</a></nav>'
            '<main><h1>公告</h1><p>周一闭馆。</p></main><footer>版权声明</footer>')
        self.assertEqual(visible['omitted_main_units'],0)
        self.assertIn('excluded_non_main_units',visible)
        self.assertEqual(visible['content_evidence_ids'],value.content_ids(ev))

    def test_unowned_copyright_heading_does_not_reject_real_main_body(self):
        ev,visible=self.prepared('<main><h1>参观安排</h1><p>周一闭馆。</p></main>'
            '<div><h2>版权声明</h2><p>本站保留版权。</p></div>')
        proposal=self.decision(visible)
        self.assertTrue(any(u['kind']=='heading' and u['text']=='版权声明' and not u.get('region') for u in ev['units']))
        self.assertFalse(old.assess(proposal,ev)['selected'])
        self.assertTrue(value.assess(proposal,ev)['selected'])

    def test_legal_main_heading_is_still_rejected_with_real_text(self):
        ev,visible=self.prepared('<main><h1>隐私政策</h1><p>本站收集访问日志并保留三十天。</p></main>')
        self.assertFalse(value.assess(self.decision(visible),ev)['selected'])

    def test_bad_reference_fields_are_not_repaired_from_reason_or_truncated(self):
        ev,visible=self.prepared('<main><h1>介绍</h1>'+''.join('<p>真实业务说明'+str(i)+'。</p>' for i in range(8))+'</main>')
        proposal={'business':'public_business','business_quote_ids':value.content_ids(ev)[:7],'reason':'这些真实正文不能自动截去第七引文'}
        self.assertEqual(len(proposal['business_quote_ids']),7)
        self.assertFalse(value.assess(proposal,ev)['selected'])
        self.assertEqual(value.assess(None,ev)['selection_reason'],'invalid_business_decision')

    def test_v12_paid_cache_remains_v12_and_new_cache_is_distinct(self):
        link=self.original()
        # V12 original uses its own paid response and cache, unchanged by V13.
        old_case=fixtures.BusinessValue('test_business_evidence_without_task_or_purpose_is_admitted')
        old_case.setUp();self.addCleanup(old_case.doCleanups)
        old_link=old_case.original()
        _,receipt=old_case.run_decision(old_link)
        before=old_case.pool.pool.checkpoint(old.CACHE,receipt['records'][0]['binding'])
        self.assertNotEqual(old.CACHE,value.CACHE);self.assertNotEqual(old.VERSION,value.VERSION)
        self.assertIsNone(old_case.pool.pool.checkpoint(value.CACHE,receipt['records'][0]['binding']))
        self.assertEqual(old_case.pool.pool.checkpoint(old.CACHE,receipt['records'][0]['binding']),before)

    def test_new_unknown_is_not_resent_under_another_chunk(self):
        link=self.original()
        with patch.object(self.f.f.b.f.f.provider.opener,'open',side_effect=TimeoutError('offline unknown')) as send, \
             patch('webcollect.model_gateway.time.sleep'):
            with self.assertRaises(OutcomeUnknown):value.classify(self.ledger,[link],'one',self.root,pool=self.pool)
            with self.assertRaises(OutcomeUnknown):value.classify(self.ledger,[link],'another',self.root,pool=self.pool)
        self.assertEqual(send.call_count,1)

    def test_formal_v13_same_observation_four_field_candidate_and_cached_replay(self):
        home=self.f.f.home
        from site_planner import page_consumption
        def screen(pool,ledger,links,root):
            for link in links:self.original(link['uri'])
            return page_consumption.screen(pool,ledger,links,root)
        sources=[{**home,'context_only':True,'excluded_entry_identities':['https://tools.example.org/old']}]
        with patch.object(observed,'screen',side_effect=screen), \
             patch('site_planner.candidate_discovery.check_entry',side_effect=AssertionError('no extra GET')), \
             patch('site_planner.entry_access.check_entry',side_effect=AssertionError('no landing GET')), \
             patch.object(self.f.f.b.f.f.provider.opener,'open',side_effect=self.provider):
            report=self.f.f.b.f.run_new(home,key='v13',target=1,sources=sources,batch_size=1)
            replay=self.f.f.b.f.run_new(home,key='v13',target=1,sources=sources,batch_size=1)
        self.assertEqual(report['listed_unique_candidates'],1,report)
        self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})
        row=self.pool.rows(protocols=('webcollect-data-candidate-2',))[0]
        self.assertEqual(set(row['candidate']),{'schema_version','candidate_kind','entry_url','requested_goal'})
        self.assertIsNone(row['candidate']['requested_goal'])
        source=row['sources'][0]
        self.assertEqual(source['purpose_evidence']['version'],value.VERSION)
        self.assertEqual(source['business_qualification'],'MAIN_CONTENT_WITNESS_NOT_EXECUTED')
        self.assertEqual(load_json(source['entry_http']['path'])['policy'],'producer-entry-observed-get-2')


if __name__=='__main__':unittest.main()
