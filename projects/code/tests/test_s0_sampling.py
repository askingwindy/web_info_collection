"""S0 sampling tests: controlled bytes and authored protocol fixtures, zero real AI."""
from copy import deepcopy
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/quality-inspector'),str(REPO/'projects/quality-inspector/tests')]
from PIL import Image
from make_fixture import fixture
from webcollect.batch_core import BatchLedger, load_json, save_json
from webcollect.planning import object_sha256
from quality_inspector.ai_worker import prepare as worker_prepare, run as worker_run
from quality_inspector.contract import fingerprint
from quality_inspector.cumulative import build_set_manifest
from quality_inspector.reviews import evidence_files, SEMANTIC
from quality_inspector.sampling import (DEFAULT_POLICY, calibrate, enqueue, expand,
    freeze_rows, prepare, report, verify_plan, coverage_map)


def controlled_reviews(dataset, path, statuses=None):
    """Protocol fixture only: authors pretend decisions, not actual pixel judgment."""
    from quality_inspector.format_checks import run
    from quality_inspector.semantic import rule_ids
    records=[]
    for sample in run(None,dataset)['samples']:
        root=Path(sample['sample_path']);a=load_json(root/'annotation.json');sid=a['sample_id']
        steps=[s['step_id'] for s in a['steps']]
        records.append({'sample_id':sid,'annotation_sha256':hashlib.sha256((root/'annotation.json').read_bytes()).hexdigest(),
            'semantic_rule_ids':rule_ids(),
            'evidence_sha256':evidence_files(root),'baseline_sha256':fingerprint()[1],
            'reviewer':{'kind':'ai','name':'CONTROLLED UNIT TEST AUTHOR, NOT ACTUAL AI'},
            'provenance':{'description':'CONTROLLED UNIT TEST authored protocol fixture, no AI judgment', 'frames_viewed':steps},
            'step_observations':[{'step_id':i,'note':'CONTROLLED TEST ONLY synthetic observation'} for i in steps],
            'checks':{name:{'status':(statuses or {}).get(sid,{}).get(name,'PASS'),
                'note':'CONTROLLED TEST ONLY, no actual model judgment','evidence_steps':steps} for name in SEMANTIC}})
    value={'schema_version':'qc-review-2','records':records}
    save_json(path,value);return value


def multi_fixture(root, count=4):
    source=fixture(root);batch=source.parents[1];rng=random.Random(719)
    base=load_json(source/'annotation.json');rows=[]
    for index in range(count):
        sample=source if index==0 else source.parent/f'fixture_client_{index+1:02}'
        if index:shutil.copytree(source,sample)
        a=deepcopy(base);a['sample_id']=sample.name
        # Random-looking authored states only exercise duplicate proxies; no real-site quality claim.
        a['task_instruction']='合成协议夹具不可交付：'+''.join(chr(0x4e00+rng.randrange(2000)) for _ in range(45))
        for step in a['steps']:
            step['page_name']=f'合成状态族{index}页面'
            image=Image.frombytes('RGB',(640,480),rng.randbytes(640*480*3));image.save(sample/step['image_path'])
        (sample/'annotation.json').write_text(json.dumps(a,ensure_ascii=False))
        rows.append([sample.name,'fixture','测试',a['app_info']['app_name'],json.dumps(a['task_type'],ensure_ascii=False),
            a['task_instruction'],6,json.dumps([640,480]),'success',json.dumps([s['action']['action_type'] for s in a['steps']]),
            sum(p.stat().st_size for p in sample.rglob('*') if p.is_file())])
    with (batch/'metadata.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['sample_id','site_id','site_category','app_name','task_type','task_instruction','steps','screen_resolution','completion_status','actions','bytes']);writer.writerows(rows)
    (batch/'SHA256SUMS').unlink()
    (batch/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(batch).as_posix()}\n' for p in sorted(batch.rglob('*')) if p.is_file()))
    return batch


class SamplingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.dataset=multi_fixture(self.root/'fixture')
        self.config=load_json(REPO/'projects/code/config/batch-synthetic.json')
        self.config['mode']='real';self.config['model']=None;self.config['budget']['max_job_attempts']=2
        for key in ('max_model_requests','max_reserved_tokens','max_model_cost_micros','currency','min_model_interval_seconds'):
            self.config['budget'].pop(key,None)
        self.manifest=self.root/'effective-set.json';save_json(self.manifest,build_set_manifest([self.dataset]))
        self.ledger=BatchLedger(self.root/'ops.sqlite3',self.config,initialize=True)

    def plan(self,**kwargs):
        return prepare(self.ledger,self.dataset,self.root/'qc',effective_set=self.manifest,**kwargs)

    def test_no_model_full_mechanical_freeze_and_pending_report(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No network')):
            result=self.plan();plan=load_json(result['plan_file'])
            summary=report(result['plan_file'],self.root/'report.json')
            self.assertEqual(self.ledger.summary()['model_requests'],0)
            self.assertEqual(plan['original_denominator'],4)
            self.assertEqual(result['risk_required'],4)
            self.assertEqual(result['selected_samples'],4)
            self.assertEqual(summary['not_ai_reviewed'],4)
            self.assertEqual(summary['required_evidence_pending'],4)
            self.assertFalse(summary['release_ready'])
            self.assertEqual(self.plan(),result) # same frozen identity, no duplicate preparation
            with self.assertRaisesRegex(ValueError,'Model branch disabled'):
                enqueue(self.ledger,result['plan_file'],self.root/'worker')

    def test_seed_reproducibility_risks_and_nonselected_semantics(self):
        reviews=self.root/'calibration-reviews.json';controlled_reviews(self.dataset,reviews)
        calibration=self.root/'calibration.json';calibrate(self.dataset,reviews,calibration)
        result=self.plan(calibration=calibration);plan=load_json(result['plan_file'])
        self.assertEqual(result['risk_required'],0)
        self.assertEqual(result['selected_samples'],1)
        again=freeze_rows(deepcopy(plan['rows']),plan['policy'])
        self.assertEqual([r['sample_id'] for r in again if r['selected']], [r['sample_id'] for r in plan['rows'] if r['selected']])
        summary=report(result['plan_file'],self.root/'unreviewed.json')
        self.assertEqual(summary['actual_ai_reviewed'],0)
        self.assertEqual(summary['not_ai_reviewed'],4)
        self.assertTrue(all(r['ai_status']=='NOT_REVIEWED' for r in summary['rows']))
        self.assertFalse(summary['release_ready'])
        # Explicit byte-derived risk cannot be erased by a random miss.
        rows=deepcopy(plan['rows']);unselected=next(r for r in rows if not r['selected']);unselected['risk_reasons']=['recorded-exception']
        chosen=freeze_rows(rows,plan['policy'])
        self.assertTrue(next(r for r in chosen if r['sample_id']==unselected['sample_id'])['selected'])

    def test_expansion_bound_reviews_persists_stop_and_invalidates_old_queue(self):
        reviews=self.root/'calibration-reviews.json';controlled_reviews(self.dataset,reviews)
        calibration=self.root/'calibration.json';calibrate(self.dataset,reviews,calibration)
        result=self.plan(calibration=calibration);plan=load_json(result['plan_file'])
        selected=next(r['sample_id'] for r in plan['rows'] if r['selected'])
        synthetic_config=load_json(REPO/'projects/code/config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'synthetic-worker.sqlite3',synthetic_config,initialize=True)
        queued=enqueue(ledger,result['plan_file'],self.root/'worker')
        self.assertEqual(queued['queued_samples'],1)
        issues=self.root/'issues.json';controlled_reviews(self.dataset,issues,{selected:{'privacy':'FAIL'}})
        expanded=self.root/'expanded.json';outcome=expand(result['plan_file'],issues,expanded)
        self.assertTrue(outcome['stop']);self.assertEqual(len(outcome['expanded_samples']),4)
        with self.assertRaisesRegex(ValueError,'superseded'):verify_plan(load_json(result['plan_file']))
        with self.assertRaisesRegex(ValueError,'stop condition'):enqueue(ledger,expanded,self.root/'stopped')
        # Already queued old jobs are rejected before synthetic/model gateway dispatch.
        worker_run(ledger)
        self.assertEqual(ledger.summary()['model_requests'],0)
        summary=report(expanded,self.root/'stopped-report.json',reviews=issues)
        self.assertTrue(summary['production_stop']);self.assertFalse(summary['sampling_complete'])
        self.assertFalse(summary['release_ready'])

    def test_missing_frame_invalid_reviews_and_synthetic_reviews_cannot_release(self):
        result=self.plan();reviews=self.root/'partial-reviews.json';value=controlled_reviews(self.dataset,reviews)
        reviews.unlink();value['records'][0]['step_observations'].pop();save_json(reviews,value)
        summary=report(result['plan_file'],self.root/'partial-summary.json',reviews=reviews)
        self.assertTrue(summary['invalid_records']);self.assertFalse(summary['release_ready'])
        bad=self.root/'synthetic.json';save_json(bad,{'schema_version':'webcollect-synthetic-review-test-1','records':value['records']})
        summary=report(result['plan_file'],self.root/'synthetic-summary.json',reviews=bad)
        self.assertEqual(summary['actual_ai_reviewed'],0);self.assertFalse(summary['release_ready'])
        with self.assertRaisesRegex(ValueError,'Invalid issue review'):expand(result['plan_file'],bad,self.root/'bad-expanded.json')

    def test_expansion_publish_failure_holds_old_plan_before_successor(self):
        result=self.plan();plan=load_json(result['plan_file'])
        selected=next(r['sample_id'] for r in plan['rows'] if r['selected'])
        issues=self.root/'issues.json';controlled_reviews(self.dataset,issues,{selected:{'privacy':'FAIL'}})
        successor=self.root/'interrupted-successor.json'
        def interrupted_publish(path,value):
            if Path(path)==successor:raise OSError('CONTROLLED crash after persistent hold before successor publish')
            return save_json(path,value)
        with patch('quality_inspector.sampling.save_json',side_effect=interrupted_publish):
            with self.assertRaisesRegex(OSError,'CONTROLLED crash'):expand(result['plan_file'],issues,successor)
        self.assertFalse(successor.exists())
        marker=load_json(Path(plan['state_directory'])/(plan['plan_sha256']+'.superseded.json'))
        self.assertTrue(marker['stop'])
        self.assertEqual(marker['successor_plan']['plan_sha256'],marker['successor_sha256'])
        with self.assertRaisesRegex(ValueError,'superseded'):enqueue(self.ledger,result['plan_file'],self.root/'blocked-dispatch')
        self.assertEqual(self.ledger.summary()['model_requests'],0)
        resumed=expand(result['plan_file'],issues,successor)
        self.assertTrue(resumed['resumed_from_persistent_hold'])
        self.assertEqual(load_json(successor),marker['successor_plan'])
        self.assertTrue(expand(result['plan_file'],issues,successor)['resumed_from_persistent_hold'])
        with self.assertRaisesRegex(ValueError,'different successor/review'):
            expand(result['plan_file'],issues,self.root/'unauthorized-different-successor.json')
        self.assertTrue((Path(plan['state_directory'])/(plan['plan_sha256']+'.superseded.json')).exists())

    def test_candidate_profile_and_implementation_changes_invalidate_plan(self):
        result=self.plan();plan=load_json(result['plan_file'])
        with patch('quality_inspector.sampling.implementation',return_value={'changed':'code'}):
            with self.assertRaisesRegex(ValueError,'implementation changed'):verify_plan(plan)
        alternate=self.root/'profile.json';alternate.write_text('{}')
        with self.assertRaisesRegex(ValueError,'profile differs'):report(result['plan_file'],self.root/'wrong-profile.json',profile=alternate)
        sample=Path(plan['rows'][0]['sample_path'])/'annotation.json';sample.write_text(sample.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'Candidate set changed'):verify_plan(plan)

    def test_calibration_code_change_is_mandatory_risk_and_missing_bytes_stop(self):
        reviews=self.root/'calibration-reviews.json';controlled_reviews(self.dataset,reviews)
        calibration=self.root/'calibration.json';calibrate(self.dataset,reviews,calibration)
        from quality_inspector.sampling import producer_implementation
        changed={**producer_implementation(),'collect.py':'CONTROLLED changed code fingerprint'}
        with patch('quality_inspector.sampling.producer_implementation',return_value=changed):
            result=self.plan(calibration=calibration);plan=load_json(result['plan_file'])
            self.assertTrue(all('relevant-code-changed-since-calibration' in r['risk_reasons'] for r in plan['rows']))
            self.assertEqual(result['selected_samples'],4)
        sample=Path(plan['rows'][0]['sample_path']);(sample/'images/step_002.png').unlink()
        # The old manifest is deliberately stale: fail closed, retain all four candidate attempts.
        with self.assertRaises((ValueError,OSError)):
            prepare(self.ledger,self.dataset,self.root/'missing-bytes',effective_set=self.manifest)
        failures=list((self.root/'missing-bytes').glob('preparation-failure-*.json'))
        self.assertEqual(len(failures),1)
        self.assertEqual(load_json(failures[0])['original_denominator'],4)
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_protected_calibration_and_effective_outputs_and_full_compatibility(self):
        result=self.plan()
        with self.assertRaisesRegex(ValueError,'outside candidates'):report(result['plan_file'],self.dataset/'bad-report.json')
        synthetic_config=load_json(REPO/'projects/code/config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'full-worker.sqlite3',synthetic_config,initialize=True)
        full=worker_prepare(ledger,self.dataset,self.root/'full-worker')
        self.assertEqual(full['queued_samples'],4)
        coverage=coverage_map();ids={r['requirement'] for r in coverage['rules']}
        self.assertTrue({f'需求书§7.{i}' for i in range(1,18)} <= ids)
        self.assertTrue(set(SEMANTIC)<=ids)


class PersistentSamplingEvidence(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('WEBCOLLECT_S0_QC_EVIDENCE'),'explicit persistent evidence directory only')
    def test_write_replayable_cli_inputs(self):
        root=Path(os.environ['WEBCOLLECT_S0_QC_EVIDENCE']).resolve();root.mkdir(parents=True,exist_ok=False)
        dataset=multi_fixture(root/'controlled-fixture');manifest=root/'effective-set.json';save_json(manifest,build_set_manifest([dataset]))
        config=load_json(REPO/'projects/code/config/batch-synthetic.json');config['mode']='real';config['model']=None;config['budget']['max_job_attempts']=2
        for key in ('max_model_requests','max_reserved_tokens','max_model_cost_micros','currency','min_model_interval_seconds'):config['budget'].pop(key,None)
        config['run_id']='s0-qc-controlled-no-model';save_json(root/'config.json',config)
        ledger=BatchLedger(root/'ops.sqlite3',config,initialize=True)
        result=prepare(ledger,dataset,root/'prepared',effective_set=manifest)
        summary=report(result['plan_file'],root/'pending-report.json')
        save_json(root/'verification.json',{'status':'PASS','input':str(dataset),'config':str(root/'config.json'),
            'ledger':str(root/'ops.sqlite3'),'effective_set':str(manifest),'plan':result['plan_file'],
            'original_denominator':result['original_denominator'],'selected_samples':result['selected_samples'],
            'actual_external_model_requests':0,'actual_external_model_fee':0,'real_sites_probed':0,'real_samples_collected':0,
            'mode':'real-no-model configuration on clearly marked SYNTHETIC fixture bytes',
            'sampling_report_release_ready':summary['release_ready'],'production_registry_modified':False,
            'active_human_review_modified':False,'controlled_authored_review_records_not_used_as_actual_ai':True})


if __name__=='__main__':unittest.main()
