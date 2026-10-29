"""Source planning regression fixtures; no real websites or provider calls."""
from copy import deepcopy
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch,AsyncMock
from webcollect.batch_core import BatchLedger,load_json,save_json,file_sha


class SemanticFixture:
    def setUp(self):
        from test_requirement_workflows import WorkflowRequirements
        self.fixture=WorkflowRequirements();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root

    def semantic(self):
        record,old=self.fixture.proposal('在线工具');state=load_json(old['anchors'][0]['state']['path'])
        for i,row in enumerate(state['elements']):row.update(inputable=i<2,clickable=i<2)
        state['capture_controls']=[{'element_id':f'control-{i}','selector':f'#control-{i}','index':0,'tag':'input' if i<2 else 'p'} for i in range(3)]
        state['values']=[{'element_id':f'control-{i}','value':'10','focused':False,'readonly':False} for i in range(2)]
        path=Path(old['anchors'][0]['state']['path']);path.write_text(json.dumps(state));old['anchors'][0]['state']['sha256']=file_sha(path)
        record['capabilities'][0]['page_anchor']=old['anchors'][0]
        from webcollect.semantic_workflow import VERSION
        spec={'schema_version':VERSION,'task_family':'navigation-reading','instruction':'在「受控离线页面」输入两个必要的查询数值并核对计算结果。',
            'task_type':['填写表单','数据查看'],'steps':[{'control_id':f'p0/control-{i}','action':'set_value','value':str(20+i),'necessity':'填写必要查询数值','expected':'显示新值'} for i in range(2)],
            'final_requirements':[{'control_id':'p0/control-2','kind':'contains','expected':'结果42'}],
            'final_result':'显示结果42','completion_judgement':'核对结果数值42。'}
        return record,spec



class SemanticPlans(SemanticFixture,unittest.TestCase):
    def test_compile_complete_six_actions_and_verify_frozen(self):
        from webcollect.workflow_proposal import compile_workflow,verify_task
        record,spec=self.semantic();task=compile_workflow(record,spec,'fixture');verify_task(task,record)
        self.assertEqual([op['action_type'] for op in task['operations']],['click','hotkey','type']*2)
        task['operations'][0]['selector']='#invented'
        with self.assertRaises(ValueError):verify_task(task,record)

    def test_unobserved_unchanged_echo_unrelated_repeated_and_short_rejected(self):
        from webcollect.workflow_proposal import compile_workflow
        record,spec=self.semantic()
        for mutate in (lambda s:s['steps'][0].update(control_id='unknown'),lambda s:s['steps'][0].update(value='10'),
                       lambda s:s['final_requirements'][0].update(control_id='p0/control-0'),
                       lambda s:s['steps'][0].update(action='click'),
                       lambda s:s['steps'].append(s['steps'][0]),lambda s:s['steps'].pop()):
            bad=deepcopy(spec);mutate(bad)
            with self.assertRaises(ValueError):compile_workflow(record,bad,'fixture')
        from webcollect.task_generation import proposal_signature
        other=deepcopy(spec);other['steps'][0]['value']='99'
        self.assertEqual(proposal_signature(compile_workflow(record,spec,'fixture')),proposal_signature(compile_workflow(record,other,'fixture')))


class ImagePages(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from test_unified_delivery import NativePaint
        self.fixture=NativePaint();await self.fixture.asyncSetUp()
        self.page=self.fixture.page;self.html=self.fixture.html
    async def asyncTearDown(self):
        await self.fixture.asyncTearDown()

    async def test_images_and_paint_scopes(self):
        import base64,io
        from PIL import Image
        from webcollect.browser import capture,observe
        stream=io.BytesIO();Image.new('RGB',(30,30),'red').save(stream,'PNG');uri='data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()
        for attrs in ('alt="普通图片"','alt="" aria-hidden="true" role="presentation" style="pointer-events:none"'):
            await self.page.set_content(self.html+f'<img id="image" {attrs} src="{uri}" width="30" height="30">')
            frame=await capture(self.page,'#go');self.assertEqual(len(frame['state']['capture_images']),1)
        for overlay in ('<span style="position:absolute;left:1px;top:1px">遮挡文字</span>',
                        '<button style="position:absolute;left:1px;top:1px">控件</button>',
                        '<div style="position:absolute;left:1px;top:1px;width:10px;height:10px;background:red;pointer-events:none"></div>'):
            await self.page.set_content(self.html+f'<img style="position:absolute;left:0;top:0;pointer-events:none" alt="" aria-hidden="true" role="presentation" src="{uri}">'+overlay)
            state=await observe(self.page,'#go');self.assertFalse(state['capture_images'][0]['eligible'])
        await self.page.set_content(self.html+'<img src="https://blocked.invalid/image.png" width="30" height="30">')
        state=await observe(self.page,'#go');self.assertFalse(state['capture_readiness']['images_ready'])
        self.assertIn('image_not_loaded',state['capture_images'][0]['exclusion_reasons'])

    async def test_capture_script_fault_has_current_diagnostic(self):
        from webcollect.browser import capture,SnapshotFault
        await self.page.set_content(self.html)
        with patch('webcollect.browser.observe',side_effect=RuntimeError('ReferenceError: observer broken')):
            with self.assertRaises(SnapshotFault) as caught:await capture(self.page)
        self.assertIn('diagnostic_png_base64',caught.exception.capture)
        self.assertFalse(caught.exception.capture['accepted_as_formal_frame'])


class BatchContracts(unittest.TestCase):
    def test_all_batch_sizes_reject_missing_duplicate_and_wrong_image(self):
        from site_planner.discovery_batch import validate_coverage,policy,DEFAULT
        for count in range(1,5):
            policy({**DEFAULT,'page_batch_size':count})
            items=[{'page_id':str(i),'image_id':'image'+str(i)} for i in range(count)]
            good={'items':[dict(row,decision={}) for row in items]}
            self.assertEqual(len(validate_coverage('assessment',items,good)),count)
            for rows in (good['items'][:-1],good['items']+good['items'][:1],[{**good['items'][0],'image_id':'wrong'}]+good['items'][1:]):
                with self.assertRaises(ValueError):validate_coverage('assessment',items,{'items':rows})
        with self.assertRaises(ValueError):validate_coverage('selection',[{'query_id':'q','results':[{'index':0}]}],{'items':[{'query_id':'q','decision':{'indices':[1]}}]})

    def test_success_and_unknown_never_reissued(self):
        from site_planner.discovery_batch import decide
        from test_s0_task_generation import config
        from unittest.mock import MagicMock
        from webcollect.batch_core import OutcomeUnknown
        with tempfile.TemporaryDirectory() as tmp:
            ledger=BatchLedger(Path(tmp)/'ledger',load_json(Path(__file__).parents[1]/'config/batch-synthetic.json'),initialize=True);gateway=MagicMock()
            items=[{'query_id':'q','results':[{'index':0}]}]
            gateway.call.return_value={'items':[{'query_id':'q','decision':{'indices':[0],'reason':'actual'}}]}
            self.assertEqual(decide(ledger,gateway,'selection',items,100),decide(ledger,gateway,'selection',items,100));self.assertEqual(gateway.call.call_count,1)
            other=[{'query_id':'q2','results':[]}];gateway.call.side_effect=OutcomeUnknown('unknown')
            for _ in range(2):
                with self.assertRaises(OutcomeUnknown):decide(ledger,gateway,'selection',other,100)
            self.assertEqual(gateway.call.call_count,2)

class SourceReuse(SemanticFixture,unittest.TestCase):
    def test_one_original_review_reused_and_changes_invalidate(self):
        from site_planner.source_review import review,qualify,validate,ACCESS
        from site_planner.qualification import CHECKS
        from webcollect.model_gateway import ModelGateway
        from webcollect.planning import object_sha256
        record,spec=self.semantic();anchor=record['capabilities'][0]['page_anchor'];image=Path(anchor['image']['path'])
        record['representative_pages']=[{'page_id':'p0','evidence_images':[{'image_id':'i0',**anchor['image']}],
            'chinese_ratio':1.0,'routing':'PASS','error':None}]
        record['evidence']=list(anchor.values())
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'source-ledger',cfg,initialize=True);gateway=ModelGateway(ledger)
        jid=ledger.enqueue('site-probe',{});job=ledger.claim('site-probe',job_id=jid)
        result={'screen':{'status':'ready','reason':'原图完整中文公开','page_observations':[{'page_id':'p0','image_ids':['i0'],'observation':'原图全部检查'}]},
            'qualification':{'category':'在线工具','category_reason':'可用工具','reason':'检查完整',
                'checks':{k:{'status':'PASS','observation':'原图可见依据'} for k in CHECKS}}}
        original=gateway.call
        def call(*args,**kwargs):return original(*args,**kwargs,synthetic_response=result)
        with patch.object(gateway,'call',side_effect=call):record['screening']=review(gateway,job,record['representative_pages'],record['capabilities'],[image])
        ledger.finish(job,result=record)
        a=qualify(record,ledger,self.root/'review',ACCESS);validate(a)
        b=qualify(record,ledger,self.root/'review',ACCESS)
        self.assertEqual(a,b);self.assertEqual(ledger.summary()['model_requests'],1)
        for mutate in (lambda r:r['screening']['unified_review'].update(rules_sha256='0'*64),
                       lambda r:r['representative_pages'].append(r['representative_pages'][0]),
                       lambda r:r['screening']['unified_review'].update(model_sha256='0'*64)):
            bad=deepcopy(record);mutate(bad)
            with self.assertRaises(ValueError):qualify(bad,ledger,self.root/'bad',ACCESS)
        image.write_bytes(b'changed')
        with self.assertRaises(ValueError):validate(a)


class ClosedVisit(unittest.TestCase):
    def test_only_zero_model_closed_observer_fault_resolves_visit_unknown(self):
        from webcollect.site_failure_stop import SiteFailureStore,execution_id
        from webcollect.planning import object_sha256
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
            binding={'ledger':str(root/'stop'),'campaign_id':'fixture','formal_since':1}
            store=SiteFailureStore.initialize(binding);cfg['site_failure_guard']=binding
            ledger=BatchLedger(root/'ledger',cfg,initialize=True);jid=ledger.enqueue('site-probe',{});job=ledger.claim('site-probe',job_id=jid)
            visit=ledger.reserve_visit(job,'https://example.org/','probe','example.org',timeout_seconds=1)
            error=RuntimeError('ReferenceError: observer fault')
            ledger.settle_visit(visit,state='failed',response_status=200,error=error,metrics={'responsibility':'unknown'})
            identity=execution_id('visit',ledger.path,visit['id'])
            store.record('https://example.org',identity,stage='probe',state='unknown',reason='Observer attribution unknown',real_execution=True,
                evidence=[{'visit_fact':visit}],usage_refs=[{'ledger':str(ledger.path),'visit_id':visit['id']}])
            diag=root/'diagnostic';save_json(diag,{'visit_id':visit['id'],'error_message':str(error)})
            ref=lambda p:{'path':str(p),'sha256':file_sha(p)}
            store.append_reassessment(identity,responsibility='collector',reason='Observer exception verified',evidence=[ref(diag)])
            proof={'diagnostic':ref(diag),'ledger':str(ledger.path),'visit_id':visit['id'],'visit_sha256':object_sha256(ledger.visits()[0])}
            decision={'action':'apply_evidenced_failure_reassessments','application_key':store.status('https://example.org')['application_key'],
                'campaign_id':'fixture','execution_ids':[identity],'user_instruction':'Explicit fixture authorization','visit_proofs':{identity:proof}}
            self.assertTrue(store.status('https://example.org')['dispatch_blocked'])
            auth=root/'authorization';save_json(auth,decision);state=store.apply_reassessments('https://example.org',ref(auth))
            self.assertFalse(state['dispatch_blocked']);self.assertEqual(state['unknown_execution_count'],1)
            # A new model UNKNOWN in that job cannot be resolved with a visit decision.
            rid=ledger.reserve_request(job,'model',0,{})['id'];ledger.settle_request(rid,state='unknown',error='URLError')
            with self.assertRaises(ValueError):store.apply_reassessments('https://example.org',ref(auth))

class DiscoveryIntegration(unittest.TestCase):
    def test_batch_sizes_preserve_coverage_and_interrupted_pool_write_recovers(self):
        import asyncio
        from unittest.mock import MagicMock
        from PIL import Image
        from site_planner import discovery_batch as batch
        from site_planner.site_pool import SitePool
        from site_planner.discovery_tools import reference
        for size in (1,2,4):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);pool=SitePool(root/'pool',initialize=True)
                cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json');calls=[]
                gateway=MagicMock()
                def respond(job,purpose,text,schema,**kwargs):
                    body=json.loads(text);calls.append(purpose)
                    if 'search-plan' in purpose:return {'queries':['第一组工具','第二组工具']}
                    rows=[]
                    for item in body['items']:
                        if purpose=='ai-batch-selection':rows.append({'query_id':item['query_id'],'decision':{'indices':[0,1],'reason':'符合约束'}})
                        else:
                            decision={'status':'PROMISING','category':'在线工具','reason':'原图中文公开','task_hint':'填写两个必要值并选择类型核对结果',
                                'unknowns':[],'follow_url':'','application_name':item['page_id'],'identity_confirmed':True,'public_chinese':True,'page_kind':'TARGET_APPLICATION'}
                            rows.append({'page_id':item['page_id'],'image_id':item['image_id'],'decision':decision})
                    return {'items':rows}
                gateway.call.side_effect=respond
                proof=root/'search.json';save_json(proof,{'fixture':True})
                def search(p,run,model,query,output,**kwargs):
                    prefix='a' if query=='第一组工具' else 'b'
                    return {'request_id':prefix,'results':[{'index':i,'uri':f'https://{prefix}{i}.example.org/','title':'受控工具','content':'中文功能','reference':reference(proof)} for i in (0,1)]}
                class Browser:
                    def __init__(self,*args):pass
                    async def __aenter__(self):return self
                    async def __aexit__(self,*args):pass
                    async def read(self,uri):
                        name=uri.split('//')[1].split('.')[0];image=root/(name+'.png');obs=root/(name+'.json')
                        if not image.exists():Image.new('RGB',(8,8),'white').save(image);save_json(obs,{'text':'公开中文必要计算','controls':[],'links':[]})
                        return {'readable':True,'same_application_host':True,'http_status':200,'navigation_error':None,'observation':reference(obs),'image':reference(image)}
                p={**batch.DEFAULT,'selection_batch_size':size,'page_batch_size':size,'output_limits':{'plan':100,'selection':200,'assessment':500}}
                args=dict(pool_path=pool.path,ledger_path=root/'ledger',output=root/'out',categories=['在线工具'],target=4,per_category=4,max_rounds=1,interaction_policy=p)
                # distinct whole hosts, not related subdomains
                original_search=search
                def distinct_search(*args,**kwargs):
                    result=original_search(*args,**kwargs)
                    for hit in result['results']:hit['uri']=hit['uri'].replace('.example.org','.org')
                    return result
                original=SitePool.assess;interrupted=[False]
                def fail_once(p,*args,**kwargs):
                    original(p,*args,**kwargs)
                    if not interrupted[0]:interrupted[0]=True;raise KeyboardInterrupt()
                with patch.object(batch,'ModelGateway',return_value=gateway),patch.object(batch,'DiscoveryBrowser',Browser),patch.object(batch,'glm_search',distinct_search):
                    with patch.object(SitePool,'assess',fail_once):
                        with self.assertRaises(KeyboardInterrupt):asyncio.run(batch.discover(cfg,**args))
                    result=asyncio.run(batch.discover(cfg,**args));count=len(calls)
                    self.assertEqual(result['status'],'TARGET_REACHED',result)
                    self.assertEqual(result['statistics']['task_opportunity_promising'],4)
                    self.assertEqual(asyncio.run(batch.discover(cfg,**args)),result)
                    self.assertEqual(len(calls),count)
                    self.assertEqual(calls.count('ai-batch-assessment'),(4+size-1)//size)
