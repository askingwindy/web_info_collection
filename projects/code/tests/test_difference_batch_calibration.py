"""All original frames, three separate decisions and bounded calibration only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from webcollect.batch_core import BatchLedger, OutcomeUnknown, load_json
from webcollect.model_gateway import ModelGateway
from webcollect.planning import object_sha256
from quality_inspector.ai_worker import snapshot
from quality_inspector.difference_batch import (JOB_KIND, RELATIONSHIPS, _request, _synthetic,
                                               do_comparison, prepare)


ROOT=Path(__file__).resolve().parents[3]


class DifferenceBatchTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.config=load_json(ROOT/'projects/code/config/batch-synthetic.json')
        self.config['model'].update(max_images=48,reserve_input_tokens=500000,
            supports_vision=True,image_tokens_per_image=16,request_overhead_tokens=128)
        self.ledger=BatchLedger(self.root/'CONTROLLED-ops.sqlite3',self.config,initialize=True)
        self.focal=self.trajectory('FOCAL',11)
        self.neighbors=[self.trajectory('NEIGHBOR_'+str(i),n) for i,n in enumerate((8,6,11))]
        self.source={'id':'CONTROLLED-original-difference-job','kind':'ai-difference','payload':{
            'candidate':snapshot(self.focal),'neighbors':[snapshot(p) for p in self.neighbors],
            'comparison_scope':'Explicit controlled snapshots, never a real production claim',
            'mode':'synthetic','model':deepcopy(self.config['model'])}}
        self.source['payload']['comparison_version']=object_sha256(self.source['payload']['neighbors'])

    def trajectory(self,sid,count):
        path=self.root/sid;(path/'images').mkdir(parents=True);(path/'ui_tree').mkdir()
        steps=[]
        for i in range(1,count+1):
            image=f'images/step_{i:03d}.png';tree=f'ui_tree/step_{i:03d}.json'
            # Identical PNG bytes deliberately prove that SHA equality never
            # removes a distinct original step from the merged request.
            Image.new('RGB',(64,48),'white').save(path/image)
            (path/tree).write_text(json.dumps({'image_path':image,'screen_resolution':[64,48],
                'elements':[{'element_id':'target','text':'实际控件测试'}]}))
            steps.append({'step_id':i,'image_path':image,'ui_tree_path':tree,
                'action':{'action_type':'complete' if i==count else 'click','target_element_id':'' if i==count else 'target'},
                'page_name':'合成对照页','step_result':'测试状态','user_goal':'必要目标',
                'next_step_rationale':'按观测执行','tool_result':{'status':'success','error':''}})
        (path/'annotation.json').write_text(json.dumps({'sample_id':sid,'task_instruction':'合成独立任务，非真实交付',
            'final_result':'测试终态','completion_judgement':'合成测试','completion_status':'success',
            'device_info':{'screen_resolution':[64,48]},'steps':steps},ensure_ascii=False))
        return path

    def job(self):
        result=prepare(self.ledger,self.source)
        return self.ledger.claim(JOB_KIND,job_id=result['job_id'])

    def response(self,job,statuses=('PASS','PASS','PASS')):
        result=_synthetic(job['payload']['material'])
        for item,status in zip(result['pair_decisions'],statuses):
            item['status']=status;item['relationship']=RELATIONSHIPS[status]
            item['note']={'PASS':'Controlled distinct business goals and action purposes.',
                          'FAIL':'Controlled same business with parameter-only variation.',
                          'REVIEW_REQUIRED':'Controlled evidence is insufficient to decide the relationship.'}[status]
        return result

    def test_58_to_36_keeps_all_identical_sha_originals_and_complete_index_mapping(self):
        job=self.job();material=job['payload']['material'];text,schema,images=_request(material)
        metrics=material['image_presentations']
        self.assertEqual(metrics['three_complete_pairs_without_chunk_repetition'],58)
        self.assertEqual(metrics['merged_complete_trajectories'],36)
        self.assertEqual(metrics['repeated_focal_presentations_removed'],22)
        self.assertEqual(len(images),36);self.assertEqual(len(set(images)),36)
        self.assertEqual(len({r['image_sha256'] for r in material['image_manifest']}),1)
        request=json.loads(text);mapping=request['image_index_mapping']
        self.assertEqual([r['image_index'] for r in mapping],list(range(1,37)))
        self.assertEqual([len(t['step_ids']) for t in request['trajectories']],[11,8,6,11])
        self.assertEqual(request['trajectories'][0]['image_indices'],list(range(1,12)))
        self.assertEqual(request['trajectories'][3]['image_indices'],list(range(26,37)))
        self.assertNotIn('frame_observations',schema['properties']) # no added long visual-QC output
        self.assertEqual(job['payload']['request_text_sha256'],hashlib.sha256(text.encode()).hexdigest())

    def test_one_gateway_request_three_pair_failures_preserved_and_no_formal_review_shape(self):
        job=self.job();result=do_comparison(self.ledger,ModelGateway(self.ledger),job,
            synthetic_response=self.response(job,('PASS','REVIEW_REQUIRED','FAIL')))
        self.assertEqual(self.ledger.summary()['model_requests'],1)
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual([p['status'] for p in result['pair_decisions']],['PASS','REVIEW_REQUIRED','FAIL'])
        self.assertEqual([p['relationship'] for p in result['pair_decisions']],
                         ['SUBSTANTIVELY_DISTINCT','UNCERTAIN','SAME_BUSINESS_OR_PARAMETER_ONLY'])
        self.assertTrue(result['experimental'] and result['calibration_only'])
        self.assertFalse(result['production_review_import_allowed'] or result['QC_approval'])
        self.assertEqual(result['sample_ids_allocated'],0)
        self.assertNotIn('records',result);self.assertNotIn('checks',result)

    def test_unknown_pair_cannot_become_overall_pass(self):
        job=self.job();result=do_comparison(self.ledger,ModelGateway(self.ledger),job,
            synthetic_response=self.response(job,('PASS','REVIEW_REQUIRED','PASS')))
        self.assertEqual(result['status'],'REVIEW_REQUIRED')

    def test_status_relationship_contradictions_are_rejected_without_text_reinterpretation(self):
        job=self.job();result=self.response(job)
        result['pair_decisions'][0]['relationship']='SAME_BUSINESS_OR_PARAMETER_ONLY'
        # The prose does not repair, override or reinterpret the invalid pair.
        result['pair_decisions'][0]['note']='This pair is substantively different.'
        with self.assertRaisesRegex(ValueError,'Bounded model attempts exhausted'):
            do_comparison(self.ledger,ModelGateway(self.ledger),job,synthetic_response=result)
        self.assertEqual(self.ledger.summary()['model_requests'],1)

    def test_legacy_calibration_version_is_rejected_before_dispatch(self):
        job=self.job();job['payload']['version']='three-neighbor-original-frame-calibration-1'
        with patch.object(ModelGateway,'call') as call,self.assertRaisesRegex(ValueError,'separate experimental'):
            do_comparison(self.ledger,ModelGateway(self.ledger),job)
        call.assert_not_called();self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_unknown_provider_outcome_propagates_without_retry_or_manufactured_result(self):
        job=self.job()
        with patch.object(ModelGateway,'call',side_effect=OutcomeUnknown('Controlled unknown outcome')) as call,\
                self.assertRaises(OutcomeUnknown):
            do_comparison(self.ledger,ModelGateway(self.ledger),job)
        self.assertEqual(call.call_count,1)
        self.assertEqual(self.ledger.get(job['id'])['state'],'running') # outer runner persists the failure

    def test_default_synthetic_response_is_pending_and_exact_cache_reuses_one_request(self):
        job=self.job();gateway=ModelGateway(self.ledger)
        first=do_comparison(self.ledger,gateway,job);second=do_comparison(self.ledger,gateway,job)
        self.assertEqual(first,second);self.assertEqual(first['status'],'REVIEW_REQUIRED')
        self.assertEqual(self.ledger.summary()['model_requests'],1)

    def test_image_or_complete_text_bound_blocks_before_enqueue_or_dispatch(self):
        for maximum,reserve in ((24,500000),(48,1000)):
            self.ledger.config['model'].update(max_images=maximum,reserve_input_tokens=reserve)
            with self.subTest(maximum=maximum),self.assertRaisesRegex(ValueError,'exceed'):
                prepare(self.ledger,self.source)
            self.assertEqual(self.ledger.summary()['model_requests'],0)
            self.assertEqual(self.ledger.summary()['jobs'],[])

    def test_missing_or_wrong_pair_identity_and_missing_coverage_fail_without_retry(self):
        for mode in ('wrong_identity','coverage'):
            with self.subTest(mode=mode):
                # Each independently owned fixture ledger retains its malformed
                # request; no retry or replacement of the original occurs.
                account=BatchLedger(self.root/(mode+'.sqlite3'),self.config,initialize=True)
                prepared=prepare(account,self.source);job=account.claim(JOB_KIND,job_id=prepared['job_id'])
                result=self.response(job)
                if mode=='wrong_identity':result['pair_decisions'][1]['neighbor_sample_id']='WRONG'
                else:result['pair_decisions'][1]['covered_neighbor_step_ids'].pop(2)
                with self.assertRaisesRegex(ValueError,'Bounded model attempts exhausted'):
                    do_comparison(account,ModelGateway(account),job,synthetic_response=result)
                self.assertEqual(account.summary()['model_requests'],1)

    def test_duplicate_neighbor_decision_is_rejected_even_if_each_item_has_valid_schema(self):
        job=self.job();result=self.response(job)
        result['pair_decisions'][2]=deepcopy(result['pair_decisions'][1])
        with self.assertRaisesRegex(ValueError,'Three distinct'):
            do_comparison(self.ledger,ModelGateway(self.ledger),job,synthetic_response=result)
        self.assertEqual(self.ledger.summary()['model_requests'],1)

    def test_changed_middle_frame_or_tree_blocks_before_gateway(self):
        job=self.job()
        (self.focal/'images/step_006.png').write_bytes(b'changed original')
        with patch.object(ModelGateway,'call') as call,self.assertRaisesRegex(ValueError,'Candidate bytes changed'):
            do_comparison(self.ledger,ModelGateway(self.ledger),job)
        call.assert_not_called();self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_changed_middle_tree_or_input_during_request_cannot_be_completed(self):
        job=self.job();result=self.response(job)
        def changed(*args,**kwargs):
            (self.neighbors[1]/'ui_tree/step_003.json').write_text('{"changed":true}')
            return result
        with patch.object(ModelGateway,'call',side_effect=changed),self.assertRaisesRegex(ValueError,'Candidate bytes changed'):
            do_comparison(self.ledger,ModelGateway(self.ledger),job)

    def test_requires_exactly_three_distinct_whole_trajectories_and_original_tree_binding(self):
        bad=deepcopy(self.source);bad['payload']['neighbors'].pop()
        with self.assertRaisesRegex(ValueError,'Exactly three'):prepare(self.ledger,bad)
        bad=deepcopy(self.source);bad['payload']['neighbors'][2]=bad['payload']['neighbors'][0]
        bad['payload']['comparison_version']=object_sha256(bad['payload']['neighbors'])
        with self.assertRaisesRegex(ValueError,'roots must be distinct'):prepare(self.ledger,bad)
        tree=self.neighbors[0]/'ui_tree/step_004.json';value=json.loads(tree.read_text());value['image_path']='images/step_002.png';tree.write_text(json.dumps(value))
        bad=deepcopy(self.source);bad['payload']['neighbors'][0]=snapshot(self.neighbors[0]);bad['payload']['comparison_version']=object_sha256(bad['payload']['neighbors'])
        with self.assertRaisesRegex(ValueError,'UI tree does not bind'):prepare(self.ledger,bad)
        self.assertEqual(self.ledger.summary()['model_requests'],0)


if __name__=='__main__':unittest.main()
