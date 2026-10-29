"""Disposable, no-network fixtures for unified optimization contracts."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from PIL import Image
from webcollect.browser import stability_pair, EvidenceStale
from site_planner.pipeline import validate_screen_coverage
from quality_inspector.delivery_sampling import _selection, count
from webcollect.batch_core import BatchLedger
from test_s0_task_generation import config


def state():
    return {'screen_resolution':[200,100],'target':{'bbox':[150,70,190,95]},'elements':[],
      'visible_text':'数值42','values':{'amount':'42'},'focus':None,
      'capture_readiness':{'schema_version':'webcollect-capture-readiness-1','document_ready':'interactive','fonts_ready':True,'images_ready':True},
      'paint_borders':[{'bbox':[10,10,110,40],'edges':[[10,10,110,11],[10,39,110,40],[10,10,11,40],[109,10,110,40]],'tag':'button','colors':['rgb(128,128,128)']*4}]}


def png(point=None,color=(140,140,140)):
    im=Image.new('RGB',(200,100),(128,128,128))
    if point:im.putpixel(point,color)
    b=BytesIO();im.save(b,'PNG');return b.getvalue()


class StabilityContracts(unittest.TestCase):
    def test_forward_readiness_only_and_legacy_preserved(self):
        a=state();b=deepcopy(a);b['capture_readiness']['document_ready']='complete'
        self.assertTrue(stability_pair(a,b,png(),png())['accepted'])
        self.assertFalse(stability_pair(b,a,png(),png())['accepted'])
        self.assertFalse(stability_pair(a,b,png(),png(),rule_version='webcollect-related-stability-1')['accepted'])
        for key,value in [('fonts_ready',False),('images_ready',False),('document_ready','loading')]:
            c=deepcopy(b);c['capture_readiness'][key]=value
            self.assertFalse(stability_pair(a,c,png(),png())['accepted'])

    def test_local_edge_noise_after_refresh_only(self):
        a=state()
        self.assertTrue(stability_pair(a,a,png(),png((50,10)))['accepted'])
        self.assertFalse(stability_pair(a,a,png(),png((50,10)),allow_border=False)['accepted'])
        self.assertFalse(stability_pair(a,a,png(),png((50,11)))['accepted'])
        self.assertFalse(stability_pair(a,a,png(),png((50,10),(200,200,200)))['accepted'])
        self.assertFalse(stability_pair(a,a,png(),png((50,10),(140,128,128)))['accepted'])

    def test_char_number_focus_control_target_occlusion_protected(self):
        for key,value in [('visible_text','数值43'),('values',{'amount':'43'}),('focus','button'),
            ('target',{'bbox':[151,70,191,95]}),('elements',[{'checked':True}]),('occlusion',True)]:
            b=deepcopy(state());b[key]=value
            self.assertFalse(stability_pair(state(),b,png(),png((50,10)))['accepted'])
        self.assertFalse(stability_pair(state(),state(),png(),png((155,75)))['accepted'])


class ScreenContracts(unittest.TestCase):
    def test_page_and_image_exact_coverage(self):
        for groups in [[['a']],[['a','b']],[['a','b'],['c','d']]]:
            pages=[{'page_id':str(i),'evidence_images':[{'image_id':x} for x in group]} for i,group in enumerate(groups)]
            rows=[{'page_id':str(i),'image_ids':group,'observation':'原图已检查'} for i,group in enumerate(groups)]
            self.assertTrue(validate_screen_coverage(pages,{'reason':'依据','page_observations':rows}))
            for bad in [rows[:-1],rows+rows[:1],[{**rows[0],'image_ids':['unknown']}]+rows[1:]]:
                with self.assertRaises(ValueError):validate_screen_coverage(pages,{'reason':'依据','page_observations':bad})


class SamplingContracts(unittest.TestCase):
    def test_ceil_site_layers_and_risk_union(self):
        slots=[{'slot_id':str(i),'site_id':str(i//2)} for i in range(6)]
        policy={'stratify':'site','seed':'frozen','ai_percent':20,'risk_selected':{'0':['new workflow'],'1':['recovery']}}
        random=_selection(slots,policy,'ai',random_only=True);actual=_selection(slots,policy,'ai')
        self.assertEqual(count(1,20),1);self.assertEqual(len(random),3)
        self.assertEqual(actual,random|{'0','1'})
        with self.assertRaises(ValueError):_selection(slots,{**policy,'risk_selected':{'missing':['risk']}},'ai')


class RefreshContracts(unittest.IsolatedAsyncioTestCase):
    async def test_action_refresh_never_dispatches_and_keeps_rejection(self):
        from webcollect.collect import capture_before_action
        candidate={'state':{},'png':png(),'capture':{}}
        with tempfile.TemporaryDirectory() as temp, patch('webcollect.collect.capture',AsyncMock(return_value=candidate)), \
             patch('webcollect.collect.verify_execution_state',AsyncMock(side_effect=[EvidenceStale('changed'),{}])), \
             patch('webcollect.collect.execute',AsyncMock(side_effect=AssertionError('no dispatch'))):
            self.assertEqual(await capture_before_action(None,temp),candidate)
            self.assertEqual(len(list(Path(temp).rglob('*.png'))),1)

    async def test_queue_dispatch_is_once_and_changed_plan_rejected(self):
        from webcollect.plan_queue import dispatch
        from webcollect.batch_core import save_json,file_sha
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);plan=root/'plan.json';save_json(plan,{'tasks':[]})
            ledger=BatchLedger(root/'ledger.db',config(),initialize=True)
            jid=ledger.enqueue('frozen-plan',{'plan':str(plan),'plan_sha256':file_sha(plan)})
            with patch('webcollect.task_generation.execute',AsyncMock(return_value={'status':'pending'})) as execute:
                self.assertTrue((await dispatch(ledger,jid,None,None,None,None))['dispatched'])
                self.assertFalse((await dispatch(ledger,jid,None,None,None,None))['dispatched'])
                self.assertEqual(execute.await_count,1)


class PlanningContracts(unittest.TestCase):
    def test_model_planning_supplies_images_and_rejects_changed_anchors(self):
        from webcollect.workflow_planning import propose
        from webcollect.batch_core import save_json,file_sha
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'fixture';path.write_text('local')
            refs={}
            for key in ('image','state','capture'):
                item=Path(temp)/key;item.write_text('{"capture_controls":[{"element_id":"one","selector":"#one"}]}' if key=='state' else key)
                refs[key]={'path':str(item),'sha256':file_sha(item)}
            cap={'capabilities':[{'page_anchor':refs}]}
            gateway=MagicMock();gateway.ledger.path=Path(temp)/'ledger.db';gateway.call.return_value={'tasks':[]}
            self.assertEqual(propose(gateway,{'id':'controlled'},cap),{'tasks':[]})
            self.assertEqual(gateway.call.call_args.kwargs['images'],[refs['image']['path']])
            gateway.call.return_value={'tasks':[{'anchors':[]}]}
            with self.assertRaises(ValueError):propose(gateway,{'id':'controlled'},cap)


if __name__=='__main__':unittest.main()

class IntegratedPlanning(unittest.TestCase):
    def test_model_workflow_compiles_freezes_and_reuses_same_queue(self):
        from test_requirement_workflows import WorkflowRequirements
        from test_s0_task_generation import catalog
        from webcollect.task_generation import generate
        from webcollect.batch_core import save_json,file_sha,load_json
        fixture=WorkflowRequirements();fixture.setUp();self.addCleanup(fixture.doCleanups)
        record,spec=fixture.proposal('工具')
        record['capabilities'][0]['page_anchor']=spec['anchors'][0]
        state_path=Path(spec['anchors'][0]['state']['path'])
        observed=load_json(state_path)
        observed['capture_controls']=[{'element_id':'control-'+str(i),'selector':'#control-'+str(i),'index':0} for i in range(3)]
        state_path.write_text(__import__('json').dumps(observed))
        spec['anchors'][0]['state']['sha256']=file_sha(state_path)
        source=catalog(fixture.root/'model-catalog.json',[record])
        ledger=BatchLedger(fixture.root/'model-ledger.db',load_json(Path(__file__).parents[1]/'config/batch-synthetic.json'),initialize=True)
        with patch('webcollect.model_gateway.ModelGateway.call',return_value={'tasks':[spec]}) as call:
            first=generate(ledger,source,fixture.root/'generated',generator='workflow-model')
            second=generate(ledger,source,fixture.root/'generated',generator='workflow-model')
        self.assertEqual(first['generated_tasks'],1,first)
        self.assertEqual(first['queue_job_id'],second['queue_job_id'])
        self.assertEqual(call.call_count,1)
        self.assertEqual(ledger.get(first['queue_job_id'])['state'],'queued')
        bad=deepcopy(spec);bad['operations'][0]['selector']='#fictional'
        from webcollect.workflow_proposal import compile_workflow
        with self.assertRaises(ValueError):compile_workflow(record,bad,'fixture')


class ReassessmentContracts(unittest.TestCase):
    def test_append_only_review_does_not_unlock_original_stop(self):
        from webcollect.site_failure_stop import SiteFailureStore
        from webcollect.batch_core import file_sha
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);store=SiteFailureStore.initialize({'ledger':str(root/'stop.db'),'campaign_id':'fixture','formal_since':1})
            proof=root/'proof';proof.write_text('fixture')
            ref={'path':str(proof),'sha256':file_sha(proof)}
            for n in range(3):store.record('https://example.org',str(n),stage='probe',state='failed',reason='original',real_execution=True,evidence=[ref],usage_refs=[])
            a=store.append_reassessment('0',responsibility='interface',reason='model success, local mapping failed',evidence=[ref])
            self.assertEqual(a,store.append_reassessment('0',responsibility='interface',reason='model success, local mapping failed',evidence=[ref]))
            status=store.status('https://example.org')
            self.assertEqual(status['failure_count'],3);self.assertEqual(status['reassessed_site_failure_count'],2)
            self.assertTrue(status['dispatch_blocked']);self.assertEqual(status['reassessment_count'],1)
            proof.write_text('changed')
            with self.assertRaises(ValueError):store.status('https://example.org')


class FrozenRiskContracts(unittest.TestCase):
    def test_risk_selection_is_frozen_and_membership_change_refused(self):
        from test_delivery_sampling import DeliverySamplingTests
        from quality_inspector.delivery_sampling import freeze,verify
        fixture=DeliverySamplingTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        ids=sorted(p.name for p in (fixture.dataset/'samples').iterdir())
        plan=freeze(fixture.dataset,fixture.plan,ai_percent=20,human_percent=0,seed='fixture',stratify='site',risk_selected={ids[-1]:['new flow']})
        self.assertTrue(next(s for s in plan['slots'] if s['slot_id']==ids[-1])['ai_selected'])
        self.assertEqual(verify(fixture.plan,fixture.dataset),plan)
        (fixture.dataset/'samples'/ids[0]/'extra.txt').write_text('changed')
        with self.assertRaises(ValueError):verify(fixture.plan,fixture.dataset)

class BatchPreparationContracts(unittest.TestCase):
    def test_mechanics_precede_freeze_and_queue_preserves_actual_batch(self):
        from test_qc_handoff import QCHandoffTests
        from webcollect.batch_qc import prepare,queue_reviews
        from webcollect.batch_core import load_json
        fixture=QCHandoffTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        events=[]
        with patch('quality_inspector.cumulative.inspect_set',side_effect=lambda *a,**kw: events.append('mechanical') or {'mechanical_status':'PASS'}):
            result=prepare(fixture.candidate,fixture.history,fixture.root/'batch',max_batch_size=10,
                ai_percent=20,human_percent=0,seed='fixture',risk_selected={fixture.sample_id:['new workflow']})
        self.assertEqual(events,['mechanical']);self.assertEqual(result['denominator'],1)
        self.assertEqual(result['ai_selected'],1);self.assertEqual(result['status'],'QC_NOT_RUN')
        with patch('quality_inspector.delivery_pipeline.prepare',return_value={'queued':True}) as queue:
            queue_reviews(None,fixture.root/'batch'/'batch-receipt.json',fixture.root/'reviews')
        self.assertEqual(queue.call_count,1)
        with patch('quality_inspector.cumulative.inspect_set',return_value={'mechanical_status':'FAIL'}), \
             patch('webcollect.qc_handoff.prepare_qc_inputs',side_effect=AssertionError('must not freeze')):
            blocked=prepare(fixture.candidate,fixture.history,fixture.root/'blocked',max_batch_size=10,
                ai_percent=20,human_percent=0,seed='fixture',risk_selected={})
        self.assertEqual(blocked['status'],'MECHANICALLY_BLOCKED')

    def test_expired_queue_dispatch_is_held_without_replay(self):
        from webcollect.batch_core import save_json,file_sha
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'plan';save_json(path,{})
            cfg=config();cfg['budget']['max_concurrent_jobs']=1
            ledger=BatchLedger(root/'queue.db',cfg,initialize=True)
            jid=ledger.enqueue('frozen-plan',{'plan':str(path),'plan_sha256':file_sha(path)})
            job=ledger.claim('frozen-plan',job_id=jid)
            nested=ledger.enqueue('collection',{})
            self.assertIsNotNone(ledger.claim('collection',job_id=nested))
            with ledger.transaction() as con:con.execute('UPDATE jobs SET lease=0 WHERE id=?',(jid,))
            ledger.recover()
            self.assertEqual(ledger.get(jid)['state'],'review_required')

class SourceResponsibilityContracts(unittest.TestCase):
    def test_collector_visit_failure_stays_in_original_ledger_without_site_charge(self):
        from webcollect.site_failure_stop import SiteFailureStore
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cfg=config('real')
            binding={'ledger':str(root/'stop.db'),'campaign_id':'controlled','formal_since':1}
            store=SiteFailureStore.initialize(binding);cfg['site_failure_guard']=binding
            ledger=BatchLedger(root/'source.db',cfg,initialize=True)
            jid=ledger.enqueue('site-probe',{});job=ledger.claim('site-probe',job_id=jid)
            visit=ledger.reserve_visit(job,'https://example.org/','source','example.org',timeout_seconds=1)
            ledger.settle_visit(visit,state='failed',response_status=200,error=EvidenceStale('synthetic'))
            self.assertEqual(len(ledger.visits()),1);self.assertEqual(ledger.visits()[0]['state'],'failed')
            self.assertEqual(store.status('https://example.org')['failure_count'],0)

    def test_cached_probe_does_not_resolve_credentials_and_hold_precedes_gateway(self):
        from site_planner.pipeline import probe_gateway
        from webcollect.batch_core import load_json,OutcomeUnknown
        with tempfile.TemporaryDirectory() as temp:
            cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
            ledger=BatchLedger(Path(temp)/'source.db',cfg,initialize=True)
            with patch('site_planner.pipeline.ModelGateway',side_effect=AssertionError('cached branch needs no dependency')):
                self.assertIsNone(probe_gateway(ledger,{'records':[]},temp))
            with patch('webcollect.provider_recovery.holds',return_value={'original':'UNKNOWN'}), \
                 patch('site_planner.pipeline.ModelGateway',side_effect=AssertionError('hold must precede dependency')):
                with self.assertRaises(OutcomeUnknown):probe_gateway(ledger,{'records':[{'site_uri':'https://example.org'}]},temp)
