"""One-record orchestration contracts, disposable fixtures only; no real IO."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from site_planner.site_pool import SitePool
from webcollect import single_record
from webcollect.batch_core import BatchLedger, save_json, load_json
from webcollect.task_generation import generate
from test_s0_task_generation import capability, catalog, config


class SingleRecordTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.root=Path(tmp.name)

    def test_pool_candidate_has_one_exact_page_and_preserves_both_origins(self):
        pool=SitePool(self.root/'pool.sqlite3',initialize=True)
        proof=self.root/'proof.json';save_json(proof,{'fixture':True})
        for i,origin in enumerate(('glm_agent','codex_session')):
            pool.record({'schema_version':'webcollect-site-discovery-1','origin':origin,'run_id':'fixture',
                'event_id':str(i),'uri':'https://example.org/tool','name':'Fixture','category_hint':'在线工具',
                'source_refs':[single_record.ref(proof)]})
        a=single_record.candidate(pool.path,'https://example.org/tool',self.root/'candidate.json')
        self.assertEqual(a['fixed_candidate_count'],1);self.assertEqual(a['sample_ids_allocated'],0)
        sources=load_json(a['source_manifest'])['sources']
        self.assertEqual(len(sources[0]['discovery_provenance']),2)
        self.assertEqual(single_record.candidate(pool.path,'https://example.org/tool',self.root/'candidate.json'),a)
        with self.assertRaisesRegex(ValueError,'existing'):
            single_record.candidate(pool.path,'https://example.org/unknown',self.root/'unknown.json')
        proof.write_text('tampered')
        with self.assertRaisesRegex(ValueError,'SHA'):
            single_record.candidate(pool.path,'https://example.org/tool',self.root/'tampered.json')

    def test_generation_is_limited_before_registration_and_can_resume(self):
        records=[capability(self.root/'a',uri='https://example.org/shop'),
                 capability(self.root/'b',uri='https://example.org/speed',kind='speed')]
        source=catalog(self.root/'catalog.json',records)
        ledger=BatchLedger(self.root/'ops.sqlite3',config(),initialize=True)
        result=generate(ledger,source,self.root/'generation',max_tasks=1)
        self.assertEqual(result['generated_tasks'],1)
        plan=load_json(result['plan_file']);self.assertEqual(len(plan['tasks']),1)
        self.assertEqual(plan['generation']['max_tasks'],1)
        self.assertEqual(generate(ledger,source,self.root/'generation',max_tasks=1),result)
        with self.assertRaisesRegex(ValueError,'max_tasks'):
            generate(ledger,source,self.root/'invalid',max_tasks=False)

    def test_plan_passes_original_registry_and_history_to_existing_generator(self):
        cfg=self.root/'config.json';save_json(cfg,config())
        with patch('webcollect.current_chain.read_chain_history',return_value=([],{'registry':str(self.root/'registry.sqlite3')})), \
             patch.object(single_record,'identity'), \
             patch('webcollect.current_chain.assert_current_evidence'), \
             patch('webcollect.task_generation.generate',return_value={'generated_tasks':1}) as call:
            result=single_record.plan(cfg,self.root/'ops.sqlite3',self.root/'catalog.json',self.root/'chain.json',self.root/'out')
        self.assertEqual(result['generated_tasks'],1)
        self.assertEqual(call.call_args.kwargs['history_registry'],str(self.root/'registry.sqlite3'))
        self.assertEqual(call.call_args.kwargs['max_tasks'],1)

    def test_source_rejects_wrong_evidence_root_before_browser_or_model(self):
        scope={'manifest':{'path':str(self.root/'allowed/current-chain/manifest.json')},
               'current_result_roots':[str(self.root/'results')]}
        with patch('webcollect.current_chain.read_chain_history',return_value=([],scope)), \
             patch('site_planner.pipeline.probe',side_effect=AssertionError('No browser')):
            with self.assertRaisesRegex(ValueError,'inside the original'):
                asyncio.run(single_record.source('unused','https://example.org/', 'unused','unused',
                    self.root/'wrong-evidence',chain=self.root/'manifest.json'))
        self.assertFalse((self.root/'wrong-evidence').exists())

    def test_failed_capture_cannot_dispatch_independent_review(self):
        result=self.root/'failed.json';save_json(result,{'collection':{'collected':0},'candidate':None,'qc_status':'no_pending_candidate'})
        with patch('quality_inspector.delivery_pipeline.prepare',side_effect=AssertionError('No model/QC dispatch')):
            with self.assertRaisesRegex(ValueError,'saved real candidate'):
                single_record.qc(self.root/'config.json',self.root/'ledger.sqlite3',result,self.root/'profile.json',self.root/'qc')
        self.assertFalse((self.root/'qc').exists())

    def test_original_auth_unknown_blocks_source_before_browser_or_candidate(self):
        cfg=self.root/'model-config.json';value=load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')
        save_json(cfg,value);path=self.root/'source.sqlite3'
        ledger=BatchLedger(path,value,initialize=True)
        jid=ledger.enqueue('test',{'CONTROLLED':'auth failure'});job=ledger.claim('test',job_id=jid)
        request=ledger.reserve_request(job,'CONTROLLED',0)
        ledger.settle_request(request['id'],state='unknown',error='HTTPError:401')
        output=self.root/'allowed/new-source'
        scope={'manifest':{'path':str((self.root/'allowed/current-chain/manifest.json').resolve())},'current_result_roots':[]}
        with patch('webcollect.current_chain.read_chain_history',return_value=([],scope)), \
             patch.object(single_record,'candidate',side_effect=AssertionError('No new candidate dispatch')), \
             patch('site_planner.pipeline.probe',side_effect=AssertionError('No browser')):
            result=asyncio.run(single_record.source('unused','https://example.org/',cfg,path,output,chain='unused'))
        self.assertEqual(result['status'],'PROVIDER_AUTHORIZATION_HOLD')
        self.assertFalse(result['browser_dispatched'])
        self.assertEqual(result['original_request_ids'],[request['id']])
        self.assertEqual(ledger.summary()['model_requests'],1)

class NumericWorkflowTests(unittest.TestCase):
    def test_non_form_numeric_controls_bind_real_selectors_and_original_anchor(self):
        from copy import deepcopy
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);record=capability(root/'cap')
            record['task_families']=['navigation-reading']
            record['supported_actions']=['click','type','scroll','hotkey']
            page=record['capabilities'][0];page['forms']=[]
            page['controls']=[{'selector':'#x','tag':'input','type':'number','label':'长度',
                'value':'','visible':True,'enabled':True,'editable':True,'min':'0','max':''},
                {'selector':'#y','tag':'input','type':'number','label':'宽度','value':'','visible':True,'enabled':True,'editable':True,'min':'0','max':''},
                {'selector':'#go','tag':'button','type':'button','label':'计算','value':'','visible':True,'enabled':True,'editable':True}]
            state=root/'state.json';save_json(state,{'url':record['site_uri'],'visible_text':'受控长度和宽度计算界面','screen_resolution':[1280,720],'elements':[
                {'element_id':'x','text':'长度','visible':True,'enabled':True,'inputable':True,'clickable':True},
                {'element_id':'y','text':'宽度','visible':True,'enabled':True,'inputable':True,'clickable':True},
                {'element_id':'go','text':'计算','visible':True,'enabled':True,'clickable':True}]})
            from PIL import Image
            image=root/'image.png';Image.new('RGB',(1280,720),'white').save(image)
            capture=root/'capture.json';save_json(capture,{'screenshot_sha256':single_record.file_sha(image),'observer_sha256':'CONTROLLED'})
            page['page_anchor']={k:single_record.ref(p) for k,p in (('image',image),('state',state),('capture',capture))}
            source=catalog(root/'catalog.json',[record])
            identities=single_record.identity(source,root/'identities.json')
            self.assertEqual(identities['pages'][record['site_uri']]['task_page']['kind'],'function')
            import sqlite3
            from webcollect.production_identity import page_url
            registry=root/'original-registry.sqlite3'
            with sqlite3.connect(registry) as con:
                con.execute('CREATE TABLE m4_pilot_applications(application_key TEXT PRIMARY KEY,canonical_uri TEXT,name TEXT)')
                con.execute('INSERT INTO m4_pilot_applications VALUES(?,?,?)',
                    (page_url('https://example.org/'),'https://example.org/','Original whole application'))
            reused=single_record.identity(source,root/'second-function-identities.json',registry=registry)
            self.assertEqual(reused['pages'][record['site_uri']]['application']['name'],'Original whole application')
            self.assertEqual(reused['pages'][record['site_uri']]['task_page']['anchor'],page['page_anchor'])
            kwargs=dict(inputs=[('长度','6'),('宽度','7')],submit_label='计算',
                assertions=[{'selector':'#result','contains':'42'}],instruction='在受控页面输入长度6、宽度7，计算并核对结果42。')
            result=single_record.numeric_workflow(source,root/'workflow.json',**kwargs)
            self.assertEqual(len(result['tasks'][0]['operations']),5)
            self.assertEqual(result['tasks'][0]['operations'][0]['selector'],'#x')
            self.assertEqual(result['tasks'][0]['anchors'][0],page['page_anchor'])
            with self.assertRaisesRegex(ValueError,'Unique visible'):
                single_record.numeric_workflow(source,root/'invalid.json',**{**kwargs,'inputs':[('不存在','1'),('宽度','7')]})
            with self.assertRaisesRegex(ValueError,'observed result'):
                single_record.numeric_workflow(source,root/'invalid-result.json',**{**kwargs,'assertions':[{'selector':'#invented','contains':'42'}]})

class DOMInventoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_visible_non_form_controls_keep_selectors_values_and_editability(self):
        from playwright.async_api import async_playwright
        from site_planner.pipeline import INVENTORY_JS
        async with async_playwright() as p:
            browser=await p.chromium.launch(channel='chrome',headless=True)
            try:
                page=await browser.new_page(viewport={'width':1280,'height':720})
                await page.route('**/*',lambda route:route.abort())
                await page.set_content('<html lang="zh-CN"><meta charset="utf-8"><title>受控DOM库存</title><label for="a">长度</label><input id="a" type="number" value="2"><label for="b">宽度</label><input id="b" type="number"><button id="go">计算</button><label for="r">只读项</label><input id="r" readonly value="1"><input id="hidden" style="display:none"><div id="result">待计算</div></html>')
                inventory=await page.evaluate(INVENTORY_JS)
                self.assertEqual(inventory['forms'],[])
                controls={c['selector']:c for c in inventory['controls']}
                self.assertEqual(controls['#a']['label'],'长度')
                self.assertEqual(controls['#a']['value'],'2')
                self.assertFalse(controls['#r']['editable'])
                self.assertNotIn('#hidden',controls)
                self.assertEqual(controls['#go']['label'],'计算')
            finally: await browser.close()

class DocumentaryHandoffTests(unittest.TestCase):
    def test_qc_supplies_original_attempt_census_and_actual_review_evidence(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();capture=root/'capture';capture.mkdir();dataset=root/'candidate';dataset.mkdir()
            for p in (capture/'manifest.json',capture/'runtime-snapshot.json',root/'facts.json',root/'sampling.json',root/'effective.json',root/'profile.json',root/'actual-review.json'):
                save_json(p,{'CONTROLLED_fixture_only':True})
            execution=root/'execution.json';save_json(execution,{'collection':{'output':str(capture)},
                'candidate':str(dataset),'qc_status':'QC_NOT_RUN','qc_inputs':{'effective_set':str(root/'effective.json'),'sampling_plan':str(root/'sampling.json')}})
            cfg=root/'config.json';save_json(cfg,config())
            def prepare(*args,**kwargs):
                output=Path(args[4]);output.mkdir();save_json(output/'pipeline-receipt.json',{'CONTROLLED':True})
            with patch('quality_inspector.cumulative.inspect_set',return_value={'status':'PASS'}), \
                 patch('quality_inspector.delivery_pipeline.prepare',side_effect=prepare) as prep, \
                 patch('quality_inspector.delivery_pipeline.run',return_value={'payload_status':'PASS'}):
                result=single_record.qc(cfg,root/'ledger.sqlite3',execution,root/'profile.json',root/'qc',supporting_files=[root/'actual-review.json'],sample_reviews=root/'actual-review.json')
            self.assertEqual(result['payload_status'],'PASS')
            self.assertIn(capture/'manifest.json',prep.call_args.kwargs['supporting_files'])
            self.assertIn(root/'sampling.json',prep.call_args.kwargs['supporting_files'])
            self.assertIn(root/'actual-review.json',prep.call_args.kwargs['supporting_files'])
            self.assertEqual(prep.call_args.kwargs['sample_reviews'],root/'actual-review.json')
