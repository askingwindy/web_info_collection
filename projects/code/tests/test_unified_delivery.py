"""Final engineering delivery: original-byte batch merge, workflow expansion and native offline paint."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from webcollect.batch_core import load_json,save_json,file_sha


class BatchAssembly(unittest.TestCase):
    def test_explicit_sources_merge_original_bytes_and_refuse_duplicates(self):
        from test_client_package import fixture
        from webcollect.client_package import build_client_package
        from quality_inspector.profiles import package_files
        from webcollect.batch_qc import assemble
        repo=Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();sources=[]
            for i in range(2):
                raw=root/('raw'+str(i));fixture(raw,sid='Web_fixture_'+str(i+1).zfill(3))
                client=root/('client'+str(i));build_client_package(repo,raw,client);sources.append(client)
            before=[package_files(p) for p in sources]
            scope={'current_result_roots':[str(root)]}
            # Provenance enforcement is independently exercised with real fixture
            # ledgers in test_qc_handoff; this test isolates actual exporter bytes.
            with patch('webcollect.batch_qc.read_chain_history',return_value=([],scope)),patch('webcollect.qc_handoff._attempts',return_value=[]):
                with patch('webcollect.batch_qc.save_json',side_effect=OSError('fixture crash after package publication')):
                    with self.assertRaises(OSError):assemble(sources,root/'scope.json',root/'batch',max_batch_size=10)
                result=assemble(sources,root/'scope.json',root/'batch',max_batch_size=10)
                self.assertEqual(result,assemble(sources,root/'scope.json',root/'batch',max_batch_size=10))
                with self.assertRaises(ValueError):assemble([sources[0],sources[0]],None,root/'bad',max_batch_size=10)
            self.assertEqual(len(list((root/'batch/samples').iterdir())),2)
            self.assertEqual(before,[package_files(p) for p in sources])
            for source in sources:
                for sample in (source/'samples').iterdir():self.assertEqual(package_files(sample),package_files(root/'batch/samples'/sample.name))

    def test_affected_workflow_expands_successor_without_changing_parent(self):
        from test_delivery_sampling import DeliverySamplingTests
        from quality_inspector.delivery_sampling import freeze,verify
        from webcollect.batch_qc import expand_risk
        f=DeliverySamplingTests();f.setUp();self.addCleanup(f.doCleanups)
        plan=freeze(f.dataset,f.plan,ai_percent=20,human_percent=0,seed='frozen',risk_selected={})
        handoff=f.root/'handoff.json';save_json(handoff,{'dataset':str(f.dataset)})
        batch=f.root/'batch.json';save_json(batch,{'handoff':{'receipt':str(handoff),'sampling_plan':str(f.plan)},'status':'QC_NOT_RUN'})
        ids=[s['current']['sample_id'] for s in plan['slots']]
        report=f.root/'assessment.json';save_json(report,{'plan_sha256':plan['plan_sha256'],'rows':[{'sample_id':sid,'status':'HUMAN_REQUIRED' if i==0 else 'NOT_SELECTED'} for i,sid in enumerate(ids)]})
        original=file_sha(f.plan)
        value=expand_risk(batch,report,{sid:'same-flow' for sid in ids},f.root/'expansion')
        self.assertEqual(value['ai_selected'],2);self.assertEqual(file_sha(f.plan),original)
        self.assertTrue(all(s['ai_selected'] for s in verify(value['handoff']['sampling_plan'],f.dataset)['slots']))
        with self.assertRaises(ValueError):expand_risk(batch,report,{},f.root/'bad')


class NativePaint(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.p=await async_playwright().start();self.b=await self.p.chromium.launch(channel='chrome',headless=True)
        self.context=await self.b.new_context(viewport={'width':600,'height':300},service_workers='block')
        await self.context.route('**/*',lambda route:route.abort())
        self.page=await self.context.new_page()
        self.html='''<!doctype html><meta charset="utf-8"><style>*{box-shadow:none;text-shadow:none;outline:none}button,input{border:1px solid rgb(128,128,128);border-radius:0;background:white;position:absolute;width:160px;height:30px}#go{left:20px;top:160px}#other{left:250px;top:30px}#amount{left:20px;top:80px}</style><button id="go">执行操作</button><button id="other">普通边框</button><input id="amount" value="42"><p id="result">结果42</p>'''

    async def asyncTearDown(self):
        await self.context.close();await self.b.close();await self.p.stop()

    async def baseline(self):
        from webcollect.browser import capture
        await self.page.set_content(self.html)
        return await capture(self.page,'#go',retries=1,assertions=[{'selector':'#result','contains':'42'}])

    async def test_native_bound_border_noise_and_unproved_pixels(self):
        from webcollect.browser import stability_pair
        frame=await self.baseline();s=frame['state']
        self.assertTrue(s['paint_borders'],'fixture must supply an actual native border proof')
        edge=s['paint_borders'][0]['edges'][0];point=(edge[0]+20,edge[1])
        im=Image.open(BytesIO(frame['png'])).convert('RGBA');a=im.getpixel(point)
        im.putpixel(point,tuple(min(255,v+4) for v in a[:3])+(a[3],));stream=BytesIO();im.save(stream,format='PNG')
        self.assertTrue(stability_pair(s,s,frame['png'],stream.getvalue())['accepted'])
        self.assertFalse(stability_pair(s,s,frame['png'],stream.getvalue(),allow_border=False)['accepted'])

    async def test_real_text_value_focus_state_position_occlusion_changes_reject(self):
        from webcollect.browser import observe,viewport_png,stability_pair
        mutations=["document.querySelector('#result').textContent='结果43'", "document.querySelector('#amount').value='43'", "document.querySelector('#amount').focus()", "document.querySelector('#other').disabled=true", "document.querySelector('#go').style.left='21px'", "document.body.insertAdjacentHTML('beforeend','<div style=\"position:absolute;left:20px;top:160px;width:160px;height:30px;background:red\"></div>')"]
        for js in mutations:
            frame=await self.baseline();await self.page.evaluate(js)
            state=await observe(self.page,'#go',assertions=[{'selector':'#result','contains':'42'}]);png,_=await viewport_png(self.page)
            self.assertFalse(stability_pair(frame['state'],state,frame['png'],png)['accepted'],js)

class SavedIndexRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_committed_save_then_index_failure_resumes_without_replaying(self):
        from test_single_execution_path import SingleCollectionTests
        from webcollect.current_chain import read_chain_history
        from webcollect.runtime import RuntimeStore
        from webcollect.collect_runtime import runtime_scope
        f=SingleCollectionTests();f._asyncioRunner=self._asyncioRunner;await f.asyncSetUp();self.addCleanup(f.doCleanups)
        f.prepared(True)
        with patch('webcollect.current_chain.append_current_result',side_effect=OSError('fixture index unavailable')):
            with self.assertRaises(OSError):await f.collect()
        self.assertEqual(f.actions,['scroll']*5)
        saved=RuntimeStore(f.registry,runtime_scope(f.output/'capture')).attempt_ledger()['attempts']
        self.assertEqual(saved[0]['status'],'collected_pending_review')
        before=[file_sha(p) for p in sorted((f.output/'capture/evidence').rglob('*')) if p.is_file()]
        await f.collect(resume=True)
        self.assertEqual(f.actions,['scroll']*5)
        self.assertEqual(len(read_chain_history(f.chain_manifest)[0]),1)
        self.assertEqual(before,[file_sha(p) for p in sorted((f.output/'capture/evidence').rglob('*')) if p.is_file()])

class ExplicitReassessment(unittest.TestCase):
    def test_review_alone_keeps_stop_explicit_decision_applies_without_resetting_history(self):
        from webcollect.site_failure_stop import SiteFailureStore
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();binding={'ledger':str(root/'stop.db'),'campaign_id':'fixture','formal_since':1}
            s=SiteFailureStore.initialize(binding);e=root/'evidence';e.write_text('original fixture')
            ref={'path':str(e),'sha256':file_sha(e)}
            for i in range(3):s.record('https://example.org',str(i),stage='probe',state='failed',reason='original',real_execution=True,evidence=[ref],usage_refs=[])
            s.append_reassessment('0',responsibility='model',reason='provider error',evidence=[ref])
            self.assertTrue(s.status('https://example.org')['dispatch_blocked'])
            auth=root/'authorization.json';save_json(auth,{'action':'apply_evidenced_failure_reassessments','application_key':'//example.org/','campaign_id':'fixture','execution_ids':['0'],'user_instruction':'Explicit fixture decision after evidence review'})
            current=s.apply_reassessments('https://example.org',{'path':str(auth),'sha256':file_sha(auth)})
            self.assertEqual(current['failure_count'],3);self.assertEqual(current['effective_site_failure_count'],2)
            self.assertFalse(current['dispatch_blocked']);self.assertTrue(current['historical_stopped'])
            s.record('https://example.org/new','new-real-failure',stage='formal',state='failed',reason='actual site failure',real_execution=True,evidence=[ref],usage_refs=[])
            self.assertTrue(s.status('https://example.org')['dispatch_blocked'])
            auth.write_text('{}')
            with self.assertRaises(ValueError):s.guard('https://example.org')
