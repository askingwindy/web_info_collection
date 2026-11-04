"""Fixed-fifty contracts using synthetic snapshots and fake browser surfaces only."""
from copy import deepcopy
from io import BytesIO
import json
import unittest
from PIL import Image, ImageDraw
from webcollect.browser import stability_pair, STABILITY_V5
from webcollect.candidate_navigation import delayed_landing
import test_related_capture_stability as related
import test_react_native as native_tests
from test_react_session import ReactHarness, act_step
from webcollect.react_session import build_url_task, ReactStop
from webcollect.postprocess import session_record, effective_trajectory


def frame(dx=0,dpr=1):
    box=[50+dx,10,60+dx,20]
    samples=[{'point':[x,y],'ancestor':True,'hit_tag':'img','hit_id':'side'}
             for x in (box[0]+.5,(box[0]+box[2])/2,box[2]-.5)
             for y in (10.5,15,19.5)]
    s={'screen_resolution':[100,70],'device_pixel_ratio':dpr,'visible_text':'操作 结果42',
       'document_identity':{'url':'https://example.org/','origin':1},'url':'https://example.org/',
       'capture_readiness':{'schema_version':'webcollect-capture-readiness-1','document_ready':'complete','images_ready':True,'fonts_ready':True},
       'target':{'element_id':'go','bbox':[0,40,25,60],'hit_valid':True,'text':'操作'},
       'elements':[{'element_id':'side','bbox':box,'text':'','element_type':'image','native_role':'img','visible':True}],
       'geometry_witnesses':[{'element_id':'side','bbox':box,'samples':samples}], 'capture_images':[]}
    im=Image.new('RGB',(100,70),'white');ImageDraw.Draw(im).rectangle([box[0],10,box[2]-1,19],fill='red')
    out=BytesIO();im.save(out,'PNG');return s,out.getvalue()


class GeometryTests(unittest.TestCase):
    def test_real_raster_translation_one_to_five_at_actual_dpr(self):
        for dpr in (1,2):
            for dx in (1,2,3,4,5):
                a,p=frame(dpr=dpr);b,q=frame(dx,dpr)
                proof=stability_pair(a,b,p,q)
                self.assertTrue(proof['accepted'],proof)
                self.assertEqual(proof['geometry_pixel_proof'][0]['translation_image'],[dx,0])
                self.assertEqual(proof['geometry_proof'][0]['physical_edge_offsets'][0],dx*dpr)
                self.assertFalse(stability_pair(a,b,p,q,rule_version=STABILITY_V5)['accepted'])

    def test_five_inclusive_greater_rejected_and_semantics_never_noise(self):
        a,p=frame();b,q=frame(5)
        for kind in ('six','fraction_over','occluded','hit_owner','target','text','pixels','identity','protected'):
            c=deepcopy(b);r=q
            if kind=='six':c,r=frame(6)
            if kind=='fraction_over':c['elements'][0]['bbox'][0]+=0.01
            if kind=='occluded':c['geometry_witnesses'][0]['samples'][0]['ancestor']=False
            if kind=='hit_owner':c['geometry_witnesses'][0]['samples'][0]['hit_id']='other'
            if kind=='target':c['target']['hit_valid']=False
            if kind=='text':c['visible_text']='操作 结果43'
            if kind=='pixels':
                im=Image.open(BytesIO(r));im.putpixel((56,15),(0,0,255));o=BytesIO();im.save(o,'PNG');r=o.getvalue()
            if kind=='identity':c['elements'][0]['element_id']='replacement'
            if kind=='protected':c['target']['bbox']=[53,10,58,20]
            self.assertFalse(stability_pair(a,c,p,r)['accepted'],kind)

    def test_failed_decorative_image_only_with_complete_irrelevance_proof(self):
        a=related.state();im=a['capture_images'][0];im.update(complete=True,natural_width=0,natural_height=0,eligible=False,exclusion_reasons=['image_not_loaded'])
        a['capture_readiness']['images_ready']=False
        self.assertTrue(stability_pair(a,a,related.png(),related.png())['accepted'])
        for kind in ('glyph','overlap','unknown','pending'):
            b=deepcopy(a);i=b['capture_images'][0]
            if kind=='glyph':i['exclusion_basis']['attributes']['alt']='口'
            if kind=='overlap':i['exclusion_basis']['protected_overlap']=True
            if kind=='unknown':i.pop('exclusion_basis')
            if kind=='pending':i['complete']=False
            self.assertFalse(stability_pair(b,b,related.png(),related.png())['accepted'],kind)


class DelayedTests(unittest.TestCase):
    def test_exact_href_and_all_counterexamples(self):
        op={'operation_id':'op1','action_type':'click','evidence':{'anchor_element_id':'link'}}
        a={'url':'https://example.org/','capture_controls':[{'element_id':'link','href':'https://example.org/doc','target':''}]}
        b={'url':'https://example.org/doc'}
        for same,other,tabs,url,target in ((True,True,True,b['url'],''),(False,True,True,b['url'],''),
                (True,False,True,b['url'],''),(True,True,False,b['url'],''),(True,True,True,'https://example.org/auto',''),
                (True,True,True,b['url'],'_blank')):
            a['capture_controls'][0]['target']=target
            proof=delayed_landing(op,a,a,{'url':url},same_tab=same,no_other_action=other,no_new_tab=tabs)
            self.assertEqual(bool(proof),same and other and tabs and url==b['url'] and not target)


class ToolTests(ReactHarness,unittest.IsolatedAsyncioTestCase):
    recorded=native_tests.NativeSessionTests.recorded
    def setUp(self):
        super().setUp();self.task=build_url_task(url=self.page.url,task_version='fifty-fixture')
        self.ids={'sample_id':'S000001_sample_000001','site_id':'S000001','batch_id':'B20261103_001','attempt_id':'fake-attempt'}
    async def test_search_exact_visible_text_role_and_plain_text_correction(self):
        session,_,_=self.recorded([]);await session._observe()
        controls=session.current['controls'];cid=next(iter(controls));controls[cid]['element']['text']='R';controls[cid]['element']['native_role']='a'
        r=await session._tool_inspect({'kind':'search','observation_id':session.current['observation_id'],'query':'R','match':'exact','role':'a'})
        self.assertEqual(r['status'],'ok');self.assertEqual(json.loads(r['data']['content_text'])[0]['control_id'],cid)
        self.assertEqual(controls[cid]['actions'],session.current['controls'][cid]['actions'])
        r=await session._tool_inspect({'kind':'search','observation_id':session.current['observation_id'],'query':'"text_hint": "R"'})
        self.assertEqual(r['status'],'rejected');self.assertIn('普通可见文字',r['summary'])
    async def test_delayed_landing_formal_session_and_contiguous_postprocess(self):
        link=self.surface.state['capture_controls'][0];link['href']='https://example.org/doc';link['target']=''
        session,evidence,_=self.recorded([]);await session._observe();await session._observe(link['element_id']);session.working_goal='核对文档'
        r=await session._tool_act({'observation_id':session.current['observation_id'],'step':act_step('click',control_id=link['element_id'])})
        self.assertEqual(r['status'],'ok');self.surface.state['url']=link['href'];self.surface.state['document_identity']={'url_without_fragment':link['href'],'performance_time_origin':456}
        r=await session._observe();self.assertEqual(r['status'],'ok');self.assertEqual(len(session.delayed_navigations),1)
        await session._tool_act({'observation_id':session.current['observation_id'],'step':act_step('scroll',direction='down')})
        session.state='finished';session.stop_reason='ready';session.stop_summary='已查看文档';session._close()
        record=session_record(evidence/'raw');self.assertEqual(len(effective_trajectory(record)),2)
        record['terminal']['delayed_navigations'][0]['no_other_action']=False
        with self.assertRaisesRegex(ValueError,'缺口'):effective_trajectory(record)


class LocalRenderedGeometry(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=related.NativeRelatedCapture.asyncSetUp
    asyncTearDown=related.NativeRelatedCapture.asyncTearDown
    data=related.NativeRelatedCapture.data
    async def test_real_dom_three_and_five_pixel_translation_and_occlusion(self):
        from webcollect import browser
        await self.page.set_content('<style>body{margin:0}#side{position:absolute;left:300px;top:70px;width:40px;height:30px}button{position:absolute;left:10px;top:140px}</style>'
            '<button id="go">核对结果</button><p>结果42</p><img id="side" alt="" src="'+self.red+'">')
        await self.page.locator('img').evaluate('(n)=>n.decode()')
        for dx in (3,5):
            await self.page.locator('#side').evaluate("n=>n.style.left='300px'")
            a=await browser.observe(self.page,'#go');p=await self.page.screenshot(scale='css')
            await self.page.locator('#side').evaluate('(n,dx)=>n.style.left=(300+dx)+"px"',dx)
            b=await browser.observe(self.page,'#go');q=await self.page.screenshot(scale='css')
            proof=browser.stability_pair(a,b,p,q)
            self.assertTrue(proof['accepted'],proof)
            self.assertTrue(proof['geometry_pixel_proof'])
            await self.page.evaluate("()=>{const x=document.createElement('div');x.id='cover';x.style='position:absolute;left:10px;top:140px;width:90px;height:30px;background:black;z-index:999';document.body.append(x)}")
            c=await browser.observe(self.page,'#go');r=await self.page.screenshot(scale='css')
            self.assertFalse(browser.stability_pair(a,c,p,r)['accepted'])
            await self.page.locator('#cover').evaluate('n=>n.remove()')


class MultibatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_formal_run_uses_each_frozen_original_batch_without_replacement(self):
        from unittest.mock import Mock,AsyncMock,patch
        from webcollect.candidate_consumer import run
        rows=[{'order':1,'candidate_id':'a','producer_batch':'old-one'},
              {'order':2,'candidate_id':'b','producer_batch':'old-two'}]
        pool=Mock();pool.claim_next.side_effect=[{'state':'EMPTY'}, {'state':'consuming','claim_id':'c2','candidate_id':'b'}]
        with patch('webcollect.candidate_consumer._cohort_rows',return_value=('scope',rows)), \
             patch('webcollect.candidate_consumer.startup_check',return_value={}), \
             patch('webcollect.candidate_consumer.guard_request_scope'), \
             patch('webcollect.candidate_consumer.consume',new=AsyncMock(return_value={'state':'succeeded'})), \
             patch('webcollect.candidate_batch.record_outcome'):
            result=await run(pool,Mock(),worker_id='one',request_prefix='fixed',cohort='fixture',registry='original')
        self.assertEqual([c.kwargs['producer_batch'] for c in pool.claim_next.call_args_list],['old-one','old-two'])
        self.assertEqual([c.kwargs['candidate_id'] for c in pool.claim_next.call_args_list],['a','b'])
        self.assertEqual(result['skipped'],[{'candidate_id':'a','reason':'EMPTY'}])
        self.assertEqual(result['denominator'],2);self.assertEqual(pool.claim_next.call_count,2)


class ActualTypesTests(unittest.TestCase):
    def test_actual_query_filter_form_settings_reading_and_opaque_interactions(self):
        from unittest.mock import patch
        from webcollect.trajectory_types import classify
        def evaluate(action,label,before,after,fields=(),role='button',arguments=None):
            before={'url':'https://example.org/','values':[],'visible_text':'初始内容','elements':[],**before}
            after={**before,**after}
            before['elements']=[{'element_id':'c','native_role':role,'text':label}]
            record={'task':{'site_category':'小游戏','candidate_binding':{}},'terminal':{'final_observation_id':'b','planning_intents':[{'task_types':['购买流程']}]},
              'observations':{'a':{'state_path':'a'},'b':{'state_path':'b'}},'trajectory':[{'action':action,'operation_id':'op','before_observation_id':'a','after_observation_id':'b',
              'target':{'control_id':'c','label':label},'effect_evidence':{'fields':list(fields)},'arguments':arguments or {}}]}
            with patch('webcollect.batch_core.load_json',side_effect=lambda p:{'a':before,'b':after}[p]):return classify(record)
        r=evaluate('type','数量',{'values':[{'element_id':'c','value':''}]},{'values':[{'element_id':'c','value':'7'}]},['target.value'])
        self.assertEqual(r['task_type'],['填写表单']);self.assertNotIn('搜索查询',r['task_type'])
        r=evaluate('click','搜索',{}, {'visible_text':'搜索结果：Python文档'},['visible_content'])
        self.assertEqual(r['task_type'],['搜索查询']);self.assertIn('search_query',r['interaction_types'])
        r=evaluate('click','搜索',{}, {},['target.focused']);self.assertNotIn('搜索查询',r['task_type'])
        r=evaluate('select','价格排序',{}, {'visible_text':'价格从低到高：10、20、30'},['visible_content'])
        self.assertEqual(r['task_type'],['筛选排序'])
        r=evaluate('select','数量',{}, {'values':[{'element_id':'c','value':'7'}]},['target.value']);self.assertNotIn('筛选排序',r['task_type'])
        r=evaluate('select','主题',{'values':[{'element_id':'c','value':'浅色'}]}, {'values':[{'element_id':'c','value':'深色'}]},['target.value'])
        self.assertEqual(r['task_type'],['修改设置'])
        r=evaluate('click','主题设置',{}, {},['target.focused','target.owner.state'])
        self.assertNotIn('修改设置',r['task_type'])
        for title in ('2048游戏规则','商城图书试读'):
            r=evaluate('scroll','',{'scroll':[0,0]}, {'scroll':[0,500],'title':title,'visible_text':'已滚动到规则或书摘正文'},['scroll'])
            self.assertEqual(r['task_type'],['数据查看']);self.assertEqual(r['interaction_types'],['directed_reading']);self.assertNotIn('购买流程',r['task_type'])
        r=evaluate('click','',{}, {'visible_text':'得分10'},['visible_content'],role='canvas')
        self.assertEqual(r['status'],'REVIEW_REQUIRED');self.assertEqual(r['interaction_types'],['opaque_surface_interaction'])
        r=evaluate('click','加入购物车',{}, {'visible_text':'购物车增加1件'},['visible_content']);self.assertEqual(r['task_type'],['购买流程'])
        r=evaluate('click','查看书摘',{}, {'url':'https://example.org/excerpt','visible_text':'正文片段'},['url']);self.assertEqual(r['task_type'],['数据查看'])
