"""End-to-end synthetic v2 selection/revision/finalization; no real review claims."""
import json
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
import unittest
from PIL import Image

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'projects/quality-inspector'))
sys.path.insert(0, str(REPO / 'projects/quality-inspector/tests'))
from test_customer_layout import fixture, put
from quality_inspector import engine
from quality_inspector.reporting import review_template
from quality_inspector.profiles import DEFAULT_DELIVERY_PROFILE
from webcollect.client_package import build_client_package, sample_hashes, sha
from webcollect.client_reports import finalize_client_package


class V2SelectionFlowTests(unittest.TestCase):
    def setUp(self):
        evidence = os.environ.get('WEBCOLLECT_GATE_EVIDENCE')
        if evidence:
            self.root = Path(evidence).resolve() / self._testMethodName
            self.root.mkdir(parents=True, exist_ok=False)
        else:
            self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
            self.root = Path(self.temp.name)
        _, seed, _ = fixture(self.root / 'literal-fixture', count=3)
        topics = ['查阅山地河川地貌并核对岩层分类与海拔分布',
                  '比较古典诗歌声韵结构及作者生平作品年代',
                  '计算长方体容器的容量并换算不同体积单位']
        for index, sample in enumerate(sorted((seed / 'samples').iterdir())):
            annotation = json.loads((sample / 'annotation.json').read_text())
            annotation['task_instruction'] = topics[index]
            for step in annotation['steps']:
                step['page_name'] = ['地理知识', '古典文学', '容量换算'][index]
                rng = random.Random(1000 * index + step['step_id'])
                Image.frombytes('RGB', (100, 80), bytes(rng.randrange(256) for _ in range(24000))).save(sample / step['image_path'])
            put(sample / 'annotation.json', annotation)
        self.facts = self.write_facts('facts-all.json', 3)
        self.candidate = self.root / 'candidate'
        build_client_package(REPO, seed, self.candidate, facts=self.facts)
        self.profile = self.write_profile('profile-all.json', 3)
        self.initial = engine.inspect(None, self.candidate, profile=self.profile, inspection_stage='payload')
        self.reviews = self.make_reviews(self.initial, 'reviews-initial.json')
        self.ids = [row['sample_id'] for row in self.initial['samples']]
        value = json.loads(self.reviews.read_text())
        value['records'][1]['checks']['terminal_semantics'].update(status='FAIL', note='SYNTHETIC: second attempt terminal expectation failed.')
        put(self.reviews, value)
        self.report = engine.inspect(None, self.candidate, profile=self.profile, inspection_stage='payload', reviews=self.reviews)
        self.report_path = self.root / 'qc-initial.json'; put(self.report_path, self.report)

    def write_facts(self, name, selected):
        path = self.root / name
        fields = {key: '纯离线工程夹具，无真实网站、真人审核、账号或生产审批。' for key in
                  ('collection_method', 'frequency_policy', 'accounts_and_privacy', 'change_detection', 'narrative_generation')}
        fields['narrative_generation'] += '本夹具未使用模型，无模型提示词。'
        put(path, {'schema_version': 'webcollect-production-facts-1', **fields,
            'selection': {'total_samples': 3, 'selected_count': selected, 'excluded_count': 3-selected,
                          'scope': 'SYNTHETIC TEST ONLY: first, failed and replacement fixtures',
                          'excluded_samples': [{'sample_id': 'S000001_sample_000001', 'reason': 'SYNTHETIC terminal failure'}] if selected==2 else []}})
        return path

    def write_profile(self, name, count):
        path = self.root / name
        value = json.loads(DEFAULT_DELIVERY_PROFILE.read_text())
        value.update(profile_id='SYNTHETIC-SELECTION-TEST', authority='Offline fixture; category exception is only for this test, never production.')
        value['targets'].update(expected_samples=count, category_share='report-only')
        put(path, value); return path

    def make_reviews(self, report, name, records=None):
        value = review_template(report); value.pop('package_review', None)
        if records is not None:
            value['records'] = records
        else:
            for row in value['records']:
                steps = [step['step_id'] for step in json.loads((Path(report['dataset']) / 'samples' / row['sample_id'] / 'annotation.json').read_text())['steps']]
                row['reviewer'] = {'kind': 'human', 'name': 'SYNTHETIC TEST PERSON - NOT A REAL REVIEW'}
                row['provenance'] = {'description': 'Explicit synthetic binding/selection fixture, no actual human image review.',
                    'reviewed_at': '2026-10-25T00:00:00Z', 'frames_viewed': steps}
                row['step_observations'] = [{'step_id': step, 'note': 'Synthetic expected observation ' + str(step)} for step in steps]
                row['checks'] = {name: {'status': 'PASS', 'note': 'SYNTHETIC assertion only.', 'evidence_steps': steps} for name in engine.SEMANTIC}
        document = value['delivery_document_review']
        document['reviewer'] = {'kind': 'ai', 'name': 'SYNTHETIC DOCUMENT FIXTURE'}
        document['provenance'] = {'description': 'Pure test expectations, not real document review.'}
        for check in document['checks'].values():
            check.update(status='PASS', note='Explicit synthetic expectation.', evidence=[{'path': 'README.md',
                'sha256': document['payload_files_sha256']['README.md'], 'detail': 'Test fixture only.'}])
        path = self.root / name; put(path, value); return path

    def test_mixed_pass_fail_replacement_and_same_id_revision_end_to_end(self):
        self.assertEqual(self.report['sample_status_counts'], {'PASS': 2, 'FAIL': 1},
                         [(row['sample_id'], [c for c in row['checks'] if c['status']!='PASS']) for row in self.report['samples']])
        original_hashes = {sid: sample_hashes(self.candidate / 'samples' / sid) for sid in self.ids}
        original_review_sha = sha(self.reviews)
        selected_facts = self.write_facts('facts-selected.json', 2)
        result = build_client_package(REPO, self.candidate, self.root / 'selected', reviews=self.reviews,
            approved_only=True, selection_report=self.report_path, facts=selected_facts)
        self.assertEqual(result['source_population'], {'total_samples': 3, 'selected_count': 2, 'excluded_count': 1})
        selected = Path(result['output']); sidecar = json.loads(Path(result['evidence_output']).read_text())
        self.assertEqual(sidecar['excluded_samples'][0]['sample_id'], self.ids[1])
        selected_reviews = json.loads(Path(result['review_output']).read_text())
        originals = json.loads(self.reviews.read_text())['records']
        self.assertEqual(selected_reviews, {'schema_version': 'qc-review-2', 'records': [originals[0], originals[2]]})
        self.assertEqual(sha(self.reviews), original_review_sha)
        self.assertEqual(original_hashes, {sid: sample_hashes(self.candidate / 'samples' / sid) for sid in self.ids})
        profile2 = self.write_profile('profile-selected.json', 2)
        pending = engine.inspect(None, selected, profile=profile2, inspection_stage='payload')
        fresh = self.make_reviews(pending, 'selected-fresh-document-review.json', selected_reviews['records'])
        payload = engine.inspect(None, selected, profile=profile2, inspection_stage='payload', reviews=fresh)
        put(self.root / 'selected-payload.json', payload)
        self.assertEqual(payload['delivery_status'], 'PASS')
        final = self.root / 'final'
        finalize_client_package(REPO, selected, self.root / 'selected-payload.json', final)
        final_report = engine.inspect(None, final, profile=profile2, inspection_stage='final', reviews=fresh)
        put(self.root / 'final-qc.json', final_report)
        self.assertEqual(final_report['delivery_status'], 'PASS')
        # Same ID prose revision must precede a new real decision/selection.
        sample = self.candidate / 'samples' / self.ids[0]
        old = json.loads((sample / 'annotation.json').read_text())
        revision = self.root / 'revision.json'
        put(revision, {'schema_version': 'webcollect-narrative-revisions-1',
            'author': 'SYNTHETIC TEST FIXTURE', 'prompt': 'Synthetic controlled revision; not a model production instruction.',
            'samples': [{'sample_id': self.ids[0], 'annotation_sha256': sha(sample/'annotation.json'),
                'evidence_sha256': {k:v for k,v in original_hashes[self.ids[0]].items() if k!='annotation.json'},
                'edits': [{'path': 'task_instruction', 'before': old['task_instruction'],
                    'after': '查阅山地岩层分类、河流形成过程和高山地区海拔分布',
                    'evidence': ['images/step_006.png']}]}]})
        revised = self.root / 'revised-candidate'
        build_client_package(REPO, self.candidate, revised, facts=self.facts, revisions=revision)
        stale = engine.inspect(None, revised, profile=self.profile, inspection_stage='payload', reviews=self.reviews)
        put(self.root / 'stale-review-rejected.json', stale)
        self.assertTrue(any(row.get('sample_id')==self.ids[0] for row in stale['review_import']['invalid_records']))
        new_reviews = self.make_reviews(engine.inspect(None, revised, profile=self.profile, inspection_stage='payload'), 'revised-reviews.json')
        value = json.loads(new_reviews.read_text()); value['records'][1] = originals[1]; put(new_reviews,value)
        new_report = engine.inspect(None, revised, profile=self.profile, inspection_stage='payload', reviews=new_reviews)
        put(self.root/'revised-qc.json',new_report)
        reselected = build_client_package(REPO, revised, self.root/'reselected', reviews=new_reviews,
            approved_only=True, selection_report=self.root/'revised-qc.json', facts=selected_facts)
        self.assertEqual(reselected['samples'],2)
        self.assertEqual(original_hashes,{sid:sample_hashes(self.candidate/'samples'/sid) for sid in self.ids})

    def test_invalid_v2_coverage_stale_report_or_unbound_selection_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, 'selection-report'):
            build_client_package(REPO,self.candidate,self.root/'missing-report',reviews=self.reviews,approved_only=True)
        broken = json.loads(self.reviews.read_text()); broken['records'][0]['provenance']['frames_viewed'].pop()
        path = self.root/'missing-frame.json';put(path,broken)
        with self.assertRaisesRegex(ValueError,'frames_viewed'):
            build_client_package(REPO,self.candidate,self.root/'missing-frame-output',reviews=path,
                                 approved_only=True,selection_report=self.report_path)
        changed = json.loads(self.reviews.read_text());changed['records'][1]['checks']['terminal_semantics'].update(status='PASS',note='SYNTHETIC changed decision not in inspected report')
        path = self.root/'uninspected-change.json';put(path,changed)
        with self.assertRaisesRegex(ValueError,'does not contain'):
            build_client_package(REPO,self.candidate,self.root/'uninspected-output',reviews=path,
                                 approved_only=True,selection_report=self.report_path)
        report = json.loads(self.report_path.read_text());report['baseline']['config_sha256']='0'*64
        path = self.root/'stale-report.json';put(path,report)
        with self.assertRaisesRegex(ValueError,'stale/different contract'):
            build_client_package(REPO,self.candidate,self.root/'stale-output',reviews=self.reviews,
                                 approved_only=True,selection_report=path)

    def test_runtime_final_decision_follows_revision_and_retains_initial_failures(self):
        from m4_runtime_fixtures import make_plan, make_registry, evidence, NOW
        from webcollect.runtime import RuntimeStore
        plan, publication = make_plan(self.root/'decision-planning', count=3)
        store = RuntimeStore(make_registry(self.root/'decision-ledger.sqlite3'), 'synthetic-decision-scope')
        store.initialize({}, now=NOW);store.enqueue_plan(plan,publication,now=NOW)
        actual_ids=[];batch=None
        for number in range(3):
            at=NOW+number*3
            attempt=store.claim_next('synthetic-worker',request_id=str(number),batch_id=batch,now=at)
            batch=attempt['batch_id'];actual_ids.append(attempt['sample_id'])
            store.start_attempt(attempt['attempt_id'],'synthetic-worker',attempt['lease_token'],now=at)
            store.finish_attempt(attempt['attempt_id'],'synthetic-worker',attempt['lease_token'],
                'collected_pending_review',evidence=evidence(self.root/f'synthetic-save-{number}.txt'),now=at+1)
        seed=self.root/'decision-seed';shutil.copytree(self.candidate,seed)
        mapping=dict(zip(self.ids,actual_ids))
        for old in self.ids:
            (seed/'samples'/old).rename(seed/'samples'/('temp-'+old))
            (seed/'ground_truth'/(old+'.json')).rename(seed/'ground_truth'/('temp-'+old+'.json'))
        for old,new in mapping.items():
            (seed/'samples'/('temp-'+old)).rename(seed/'samples'/new)
            (seed/'ground_truth'/('temp-'+old+'.json')).rename(seed/'ground_truth'/(new+'.json'))
            path=seed/'samples'/new/'annotation.json';data=json.loads(path.read_text());data['sample_id']=new;put(path,data)
        site=json.loads((seed/'site-list.json').read_text())
        for row in site['samples']:row['sample_id']=mapping[row['sample_id']]
        for row in site['sites']:row['sample_ids']=[mapping[s] for s in row['sample_ids']]
        put(seed/'site-list.json',site)
        original=self.root/'decision-original';build_client_package(REPO,seed,original,facts=self.facts)
        review=self.make_reviews(engine.inspect(None,original,profile=self.profile,inspection_stage='payload'),'decision-initial-reviews.json')
        value=json.loads(review.read_text())
        value['records'][0]['checks']['language'].update(status='FAIL',note='SYNTHETIC initial prose defect before revision.')
        value['records'][1]['checks']['terminal_semantics'].update(status='FAIL',note='SYNTHETIC replacement required.')
        put(review,value);initial_sha=sha(review)
        initial=engine.inspect(None,original,profile=self.profile,inspection_stage='payload',reviews=review)
        initial_report=self.root/'decision-initial-qc.json';put(initial_report,initial)
        self.assertFalse(any(event['event_type']=='review_recorded' for event in store.snapshot()['events']))
        sample=original/'samples'/actual_ids[0];old=json.loads((sample/'annotation.json').read_text())
        revision=self.root/'decision-revision.json'
        put(revision,{'schema_version':'webcollect-narrative-revisions-1','author':'SYNTHETIC FIXTURE',
            'prompt':'Synthetic repair after initial failure; no actual human judgment.',
            'samples':[{'sample_id':actual_ids[0],'annotation_sha256':sha(sample/'annotation.json'),
                'evidence_sha256':{k:v for k,v in sample_hashes(sample).items() if k!='annotation.json'},
                'edits':[{'path':'task_instruction','before':old['task_instruction'],
                    'after':'查证高山岩层种类、地貌与河流源头的具体特征','evidence':['images/step_006.png']}]}]})
        revised=self.root/'decision-revised';build_client_package(REPO,original,revised,facts=self.facts,revisions=revision)
        final_reviews=self.make_reviews(engine.inspect(None,revised,profile=self.profile,inspection_stage='payload'),'decision-final-reviews.json')
        value2=json.loads(final_reviews.read_text());value2['records'][1]=value['records'][1];put(final_reviews,value2)
        report=engine.inspect(None,revised,profile=self.profile,inspection_stage='payload',reviews=final_reviews)
        report_path=self.root/'decision-final-qc.json';put(report_path,report)
        self.assertEqual(report['sample_status_counts'],{'PASS':2,'FAIL':1})
        bound=[{'path':str(report_path),'sha256':sha(report_path)}]
        for index,sid in enumerate(actual_ids):
            store.record_review(sid,'reject' if index==1 else 'pass',bound,'Synthetic final decision after revision',now=NOW+20)
        with self.assertRaisesRegex(ValueError,'不可覆盖'):
            store.record_review(actual_ids[0],'reject',[{'path':str(initial_report),'sha256':sha(initial_report)}],
                                'Synthetic old initial rejection cannot replace final choice',now=NOW+21)
        self.assertEqual(sha(review),initial_sha)
        snapshot=store.snapshot();put(self.root/'decision-runtime-snapshot.json',snapshot)
        self.assertEqual(len([row for row in snapshot['events'] if row['event_type']=='review_recorded']),3)
        self.assertTrue(all(row['status']=='collected_pending_review' for row in snapshot['attempts']))
        self.assertEqual(store.attempt_ledger()['actual_attempt_count'],3)


if __name__ == '__main__': unittest.main(verbosity=2)
