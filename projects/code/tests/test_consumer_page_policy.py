"""Disposable fixture tests, no production history, browser or model network."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from webcollect import consumer_page_policy as policy
from webcollect.candidate_batch import first_frame_disposition
from webcollect.batch_core import load_json
from webcollect.react_session import ReactSession,build_url_task
from webcollect.banded_plan import VERSION,V6_VERSION
from webcollect.closing_policy import VERSION as END
from test_react_session import ReactHarness
import test_banded_plan as banded
import test_candidate_entry_engineering as entry

class PagePolicyTests(unittest.TestCase):
    def test_image_geometry_rejects_full_viewport_not_normal_or_hidden_hero(self):
        image={'element_id':'image','element_type':'image','visible':True,'bbox':[-5,0,1300,720]}
        state={'screen_resolution':[1280,720],'elements':[image]}
        self.assertEqual(first_frame_disposition(state),('abandon','first_frame_image_fills_viewport'))
        for b in ([0,0,1280,300],[0,900,1280,1620]):
            image['bbox']=b;self.assertIsNone(policy.full_image(state))
        image['bbox']=[0,0,1280,720];image['visible']=False
        self.assertIsNone(policy.full_image(state))
        state['elements']=[{**image,'visible':True,'bbox':[0,0,640,720]}]*3
        self.assertIsNone(policy.full_image(state)) # duplicates cannot add area

    def test_public_login_download_buttons_are_not_a_boundary(self):
        state={'url':'https://example.org/article','title':'公开资料','elements':[
            {'element_id':'nav','visible':True,'text':'登录 下载','clickable':True}]}
        self.assertIsNone(policy.boundary(state))
        self.assertEqual(policy.boundary({**state,'url':'https://example.org/account/login'})['kind'],'login')
        self.assertEqual(policy.boundary({**state,'title':'文件下载'})['kind'],'download')
        state['elements'] += [{'element_id':'d','parent_id':'root','native_role':'dialog','visible':True,'text':'下载文件'},
            {'element_id':'c','parent_id':'d','visible':True,'clickable':True,'text':'取消'}]
        self.assertEqual(policy.boundary(state)['kind'],'download')
        self.assertTrue(policy.allowed_exit(state,'click','c'))
        self.assertFalse(policy.allowed_exit(state,'type','c'))
        self.assertFalse(policy.allowed_exit(state,'click','nav'))
        self.assertIsNone(policy.returned_pair(state,state,state,{'action':'click'},{'action':'back'}))

    def test_only_terminal_semantics_cache_is_invalidated(self):
        from quality_inspector.semantic import rule_ids,invalidate_record,digest
        ids=rule_ids();old=deepcopy(ids)
        old['terminal_semantics']=digest({'semantic_rule':'terminal_semantics','version':'truthful-legal-fragment-and-flagged-five-eight-ending-3'})
        record={'semantic_rule_ids':old,'checks':{k:{'status':'PASS'} for k in old}}
        updated=invalidate_record(record)
        self.assertEqual([v['check'] for v in updated['semantic_reuse']['invalidated_checks']],['terminal_semantics'])
        self.assertEqual(record['checks']['terminal_semantics']['status'],'PASS')
        self.assertEqual(len(updated['semantic_reuse']['reused_checks']),4)

class ConsumerOwnershipTests(unittest.IsolatedAsyncioTestCase):
    def test_table2_only_page_requires_its_exact_original_claim_and_leaves_table1_intact(self):
        from webcollect.site_pool_sync import _page, page_state
        f=self.fixture()
        with f.pool.pool.connect(write=True) as con:
            con.execute('UPDATE pages SET uri=? WHERE uri=?',(f.uri+'other-path',f.uri))
            con.commit()
        before=self.site_snapshot(f)
        locator={k:f.claim[k] for k in ('candidate_id','claim_id','version')}
        with self.assertRaisesRegex(ValueError,'already exist'):
            page_state(f.pool.pool,f.uri)
        self.assertEqual(_page(f.pool.pool,f.uri,locator)[0],f.cid)
        self.assertTrue(page_state(f.pool.pool,f.uri,candidate=locator)['dispatch_allowed'])
        for uri,binding in ((f.uri, {**locator,'version':999}), (f.uri, {**locator,'claim_id':'wrong'}),
                            (f.uri+'another',locator)):
            with self.assertRaisesRegex(ValueError,'original claimed entry'):
                _page(f.pool.pool,uri,binding)
        self.assertEqual(self.site_snapshot(f),before)

    def fixture(self):
        f=entry.EntryEngineering('test_entry_cli_to_original_save_and_same_page')
        f.setUp();self.addCleanup(f.doCleanups);return f
    def site_snapshot(self,f):
        with f.pool.pool.connect() as con:
            return {t:[tuple(r) for r in con.execute('SELECT * FROM '+t+' ORDER BY rowid')]
                    for t in ('applications','aliases','pages','discoveries','assessments','capabilities')}
    async def test_image_first_frame_blocks_repeat_without_planning_or_table1_write(self):
        f=self.fixture()
        # Another page under the same application remains independently eligible.
        other=f.pool.put({**f.v2,'entry_url':f.uri+'?other=1'},f.source)
        f.surface.state['elements']=[{'element_id':'photo','parent_id':'root','element_type':'image','native_role':'img',
            'visible':True,'enabled':True,'clickable':False,'inputable':False,'text':'','bbox':[0,0,1280,720]}]
        f.surface.state['values']=[];f.surface.state['capture_controls']=[]
        before=self.site_snapshot(f)
        with patch('site_planner.site_pool.SitePool.record',side_effect=AssertionError('Consumer must not mutate Table1')):
            result=(await f.invoke_cli())[0]
        self.assertEqual(result['reason'],'first_frame_image_fills_viewport',result)
        self.assertEqual(f.prompts,[])
        self.assertEqual(before,self.site_snapshot(f))
        c=f.pool.get_claim(f.claim['claim_id'])
        self.assertEqual(c['state'],'failed')
        with f.pool.pool.connect() as con:d=f.pool.disposition(con,f.cid)
        self.assertEqual(d['disposition'],'abandon');self.assertTrue(d['evidence'])
        self.assertNotEqual(f.pool.claim_next('w','repeat',candidate_id=f.cid,protocols=('webcollect-data-candidate-2',))['state'],'consuming')
        self.assertEqual(f.pool.claim_next('w','other',candidate_id=other,protocols=('webcollect-data-candidate-2',))['state'],'consuming')

    async def test_successful_consumer_keeps_all_table1_fields_and_provenance(self):
        f=self.fixture();before=self.site_snapshot(f)
        with patch('site_planner.site_pool.SitePool.record',side_effect=AssertionError('Consumer must not mutate Table1')):
            result=(await f.invoke_cli())[0]
        self.assertEqual(result['state'],'succeeded',result)
        self.assertEqual(before,self.site_snapshot(f))

    async def test_new_landing_path_does_not_require_creating_a_table1_page(self):
        f=self.fixture();before=self.site_snapshot(f);capture=f.capture
        async def redirected(*args,**kwargs):
            if not f.surface.executed:
                from urllib.parse import urlsplit,urlunsplit
                u=urlsplit(f.uri)
                f.surface.state['url']=urlunsplit((u.scheme,u.netloc,'/redirected-public','', ''))
            return await capture(*args,**kwargs)
        f.capture=redirected
        with patch('site_planner.site_pool.SitePool.record',side_effect=AssertionError('Consumer must not mutate Table1')):
            result=(await f.invoke_cli())[0]
        self.assertEqual(result['state'],'succeeded',result)
        self.assertEqual(before,self.site_snapshot(f))

class BoundarySessionTests(ReactHarness,unittest.IsolatedAsyncioTestCase):
    derive=banded.BandedSessionTests.derive
    def setUp(self):
        banded.BandedSessionTests.setUp(self)
    async def run_boundary(self,kind,modal=False,old=False,no_exit=False):
        self.task=build_url_task(url=self.page.url,task_version=kind+str(modal),ending_policy=END,
            plan_protocol=V6_VERSION if old else VERSION,
            allowed_actions=[a for a in self.task['fragment']['allowed_actions'] if a!='back'] if no_exit else None)
        self.surface.state['values']=[]
        self.surface.state['elements']=self.surface.state['elements'][:1]
        e=self.surface.state['elements'][0]
        e.update(element_type='link',native_role='a',inputable=False,clickable=True,text='查看资料',bbox=[10,20,210,60])
        self.surface.state['capture_controls']=self.surface.state['capture_controls'][:1]
        self.surface.state['capture_controls'][0].update(tag='a',href=self.page.url+'/login')
        origin=deepcopy(self.surface.state);n=0
        def execute(action,args):
            nonlocal n
            self.surface.executed.append((action,deepcopy(args)));n+=1
            if n==1:
                self.surface.state['title']='用户登录' if kind=='login' else '文件下载'
                self.surface.state['visible_text']='请登录后使用' if kind=='login' else '下载文件确认'
                if not modal:
                    self.surface.state['url']=origin['url']+'/login'
                    self.surface.state['document_identity']['performance_time_origin']+=1
                    self.surface.state['elements']=[];self.surface.state['capture_controls']=[]
                else:
                    self.surface.state['elements'][0].update(text='取消',element_type='button',native_role='button')
            else:
                self.surface.state=deepcopy(origin)
        self.surface.execute_action=execute
        prompts=[]
        async def choose(p):
            prompts.append(p)
            if len(prompts)>1:raise AssertionError('Boundary must exit before another planning request')
            plan=banded.plan_for(p,5)
            plan['steps'][0]={'action':'click','target':{'text':'查看资料'},'purpose':'查看资料入口',
                              'expected':{'kind':'visible_text','text':'资料正文'}}
            return {'name':'submit_plan','arguments':plan,'tool_call_id':'p1'}
        evidence=self.root/(kind+str(modal)+str(old))/'evidence'/self.ids['sample_id']
        s=ReactSession(self.task,evidence/'raw',choose,self.page,steps_directory=evidence,attempt_id='offline-plan')
        result=await s.run()
        return s,evidence,result,prompts
    async def test_login_navigation_real_click_back_two_effective_actions_sealed(self):
        s,e,r,p=await self.run_boundary('login')
        self.assertEqual(r['effective_steps'],2,r)
        self.assertEqual([v[0] for v in self.surface.executed],['click','back'])
        self.assertTrue(r['short_flow']);self.assertFalse(r['unknown'])
        self.assertEqual(r['collection_ending']['kind'],'HOST_BOUNDARY_RETURN')
        self.assertEqual(r['collection_ending']['goal_completion'],'NOT_CLAIMED')
        _,annotation=self.derive(e)
        self.assertTrue(annotation['short_flow'])
        self.assertEqual(len(annotation['steps']),3)
        self.assertEqual(len(p),1)
    async def test_download_dialog_real_click_cancel_is_not_invalid_round_trip(self):
        s,e,r,p=await self.run_boundary('download',modal=True)
        self.assertEqual(r['effective_steps'],2,r)
        self.assertEqual([v[0] for v in self.surface.executed],['click','click'])
        _,annotation=self.derive(e)
        self.assertNotIn('上传下载',annotation['task_type'])
        self.assertIn('问题排查',annotation['task_type'])
        self.assertEqual(len(p),1)
    async def test_sealed_boundary_marker_tampering_is_rejected(self):
        s,e,r,p=await self.run_boundary('login')
        from webcollect.postprocess import session_record
        from webcollect.closing_policy import validate_record
        record=session_record(e/'raw');validate_record(record)
        record['terminal']['collection_ending']['boundary_return_evidence']['kind']='download'
        with self.assertRaisesRegex(ValueError,'Boundary return'):validate_record(record)
    async def test_no_proven_exit_preserves_one_action_without_making_up_second(self):
        s,e,r,p=await self.run_boundary('login',no_exit=True)
        self.assertEqual(r['actual_actions'],1)
        self.assertEqual(r['effective_steps'],1)
        self.assertIn('BOUNDARY_WITHOUT_PROVEN_EXIT',r['stop_summary'])
    async def test_host_rejects_login_typing_before_any_dispatch(self):
        self.task=build_url_task(url=self.page.url,task_version='denied',ending_policy=END,plan_protocol=VERSION)
        self.surface.state['title']='用户登录'
        async def never(p):raise AssertionError('No model request needed')
        s=ReactSession(self.task,self.root/'denied',never,self.page,attempt_id='denied')
        await s._observe();s.working_goal='返回公开内容'
        result=await s._perform_act({'observation_id':s.current['observation_id'],
            'step':{'action':'type','control_id':'control-0','value':'credentials','goal':'登录','expected':'登录'}})
        self.assertEqual(result['status'],'rejected')
        self.assertEqual(self.surface.executed,[])
    async def test_v6_task_does_not_enable_automatic_boundary_return(self):
        s,e,r,p=await self.run_boundary('login',old=True)
        self.assertEqual(r['actual_actions'],1)
        self.assertNotEqual((r.get('collection_ending') or {}).get('kind'),'HOST_BOUNDARY_RETURN')
