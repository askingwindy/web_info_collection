"""Global fifth-check import protocol; authored humans are synthetic fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from test_customer_layout import fixture
from quality_inspector import global_difference as global_qc
from quality_inspector.reviews import sha, record_hash


class GlobalDifferenceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        _,self.client,_=fixture(self.root,count=2)
        self.samples=[{'sample_id':path.name,'sample_path':str(path.resolve())}
                      for path in sorted((self.client/'samples').iterdir())]
        for target in ('urllib.request.build_opener','socket.create_connection','quality_inspector.ai_worker.ModelGateway'):
            blocker=patch(target,side_effect=AssertionError('No model, human service or external network'))
            blocker.start();self.addCleanup(blocker.stop)

    def write_review(self,name='human',statuses=None,*,selected=None,record_scope=False):
        value=global_qc.review_template(self.samples)
        if selected is not None:value['records']=[row for row in value['records'] if row['sample_id'] in selected]
        header=value['global_difference_scope']
        for row in value['records']:
            root=Path(next(item['sample_path'] for item in self.samples if item['sample_id']==row['sample_id']))
            steps=[step['step_id'] for step in json.loads((root/'annotation.json').read_text())['steps']]
            row['reviewer']={'kind':'human','name':'SYNTHETIC HUMAN PROTOCOL AUTHOR; NOT ACTUAL HUMAN INSPECTION'}
            row['provenance']={'description':'Authored offline fixture for fifth-only import, not actual sign-off',
                               'frames_viewed':steps}
            row['step_observations']=[{'step_id':sid,'decision':'ok','note':'SYNTHETIC focal-frame observation'} for sid in steps]
            row['checks'][global_qc.CHECK]={'status':(statuses or {}).get(row['sample_id'],'PASS'),
                'note':'SYNTHETIC global population comparison only, no real inspection', 'evidence_steps':steps}
            if record_scope:row['global_difference_scope']=deepcopy(header)
        if record_scope:value.pop('global_difference_scope')
        path=self.root/(name+'.json');path.write_text(json.dumps(value,ensure_ascii=False))
        return value,{'path':str(path),'sha256':sha(path)}

    def save(self,reference,value):
        Path(reference['path']).write_text(json.dumps(value));return {**reference,'sha256':sha(reference['path'])}

    def test_template_is_unsigned_pending_and_no_reviews_never_qualify(self):
        value=global_qc.review_template(self.samples)
        self.assertEqual(value['global_difference_scope']['only_check_consumed'],global_qc.CHECK)
        self.assertEqual(len(value['comparison_population']),2)
        self.assertTrue(all(not row['reviewer']['kind'] for row in value['records']))
        self.assertTrue(all(check['status']=='REVIEW_REQUIRED' for row in value['records'] for check in row['checks'].values()))
        result=global_qc.resolve(self.samples)
        self.assertEqual(result['status'],'REVIEW_REQUIRED');self.assertEqual(result['qualified_sample_ids'],[])
        self.assertEqual(len(result['pending_sample_ids']),2)

    def test_explicit_zero_sampling_preserves_unknown_escalation_and_rejects_stale_sources(self):
        from quality_inspector.delivery_sampling import freeze
        from quality_inspector.semantic import rule_ids
        plan=self.root/'sampling.json'
        freeze(self.client,plan,ai_percent=0,human_percent=0,seed='SYNTHETIC explicit policy')
        plan_ref={'path':str(plan),'sha256':sha(plan)}
        rows,_=global_qc._population(self.samples)
        report={'program':'quality-inspector','semantic_rule_ids':rule_ids(),
                'samples':[{**row,'status':'PASS'} for row in rows],
                'semantic_sampling':{'rows':[{'sample_id':rows[0]['sample_id'],
                    'ai_status':'UNKNOWN','human_required':True,'human_random_selected':False}]}}
        path=self.root/'original-qc.json';path.write_text(json.dumps(report))
        ref={'path':str(path),'sha256':sha(path)}
        pending=global_qc.resolve(self.samples,sampling_plan=plan_ref,source_reports=[ref])
        self.assertEqual(pending['pending_sample_ids'],[rows[0]['sample_id']])
        self.assertEqual(pending['policy_admitted_sample_ids'],[rows[1]['sample_id']])
        template=global_qc.review_template(self.samples,sampling_plan=plan_ref,source_reports=[ref])
        self.assertEqual([row['sample_id'] for row in template['records']],[rows[0]['sample_id']])
        with self.assertRaisesRegex(ValueError,'original QC reports'):
            global_qc.resolve(self.samples,sampling_plan=plan_ref)
        report['samples'][0]['annotation_sha256']='0'*64
        path.write_text(json.dumps(report));ref['sha256']=sha(path)
        with self.assertRaisesRegex(ValueError,'sample bytes differ'):
            global_qc.resolve(self.samples,sampling_plan=plan_ref,source_reports=[ref])

    def test_human_scope_closes_all_fifths_and_ignores_new_visual_votes(self):
        value,reference=self.write_review()
        for row in value['records']:
            row['checks']['visual_alignment']={'status':'FAIL','note':'IGNORED new visual vote; original visual decision is retained',
                                             'evidence_steps':[1]}
        reference=self.save(reference,value);before=Path(reference['path']).read_bytes()
        original_files={str(path):path.read_bytes() for path in self.client.rglob('*') if path.is_file()}
        result=global_qc.resolve(self.samples,[reference])
        self.assertEqual(result['status'],'PASS');self.assertEqual(len(result['qualified_sample_ids']),2)
        self.assertFalse(result['visual_checks_imported']);self.assertEqual(result['model_requests_dispatched'],0)
        for decision,original in zip(result['decisions'],value['records']):
            self.assertEqual(decision['source_record_sha256'],record_hash(original))
            self.assertEqual(decision['status'],'PASS');self.assertNotIn('visual_alignment',decision)
        self.assertEqual(Path(reference['path']).read_bytes(),before)
        self.assertEqual(original_files,{str(path):path.read_bytes() for path in self.client.rglob('*') if path.is_file()})

    def test_fail_pending_and_missing_are_preserved_and_do_not_count(self):
        first,second=[row['sample_id'] for row in self.samples]
        _,reference=self.write_review(statuses={first:'FAIL',second:'REVIEW_REQUIRED'})
        result=global_qc.resolve(self.samples,[reference])
        self.assertEqual(result['status'],'FAIL');self.assertEqual(result['qualified_sample_ids'],[])
        self.assertEqual(result['failed_sample_ids'],[first]);self.assertEqual(result['pending_sample_ids'],[second])
        _,partial=self.write_review('partial',selected=[first])
        result=global_qc.resolve(self.samples,[partial])
        self.assertEqual(result['status'],'REVIEW_REQUIRED');self.assertEqual(result['qualified_sample_ids'],[first])

    def test_record_level_binding_and_split_reviewers_can_complete_the_scope(self):
        refs=[self.write_review('review-'+str(index),selected=[row['sample_id']],record_scope=True)[1]
              for index,row in enumerate(self.samples)]
        result=global_qc.resolve(self.samples,refs)
        self.assertEqual(result['status'],'PASS');self.assertEqual(len(result['qualified_sample_ids']),2)

    def test_missing_or_stale_population_and_rule_are_rejected(self):
        value,reference=self.write_review()
        for mutation in ('missing','population','rule'):
            with self.subTest(mutation=mutation):
                changed=deepcopy(value)
                if mutation=='missing':changed.pop('global_difference_scope')
                elif mutation=='population':changed['global_difference_scope']['population_sha256']='0'*64
                else:changed['global_difference_scope']['rule_id']='0'*64
                current=self.save(reference,changed)
                with self.assertRaises(ValueError):global_qc.resolve(self.samples,[current])
        reference=self.save(reference,value)
        with self.assertRaises(ValueError):global_qc.resolve(self.samples[:1],[reference])

    def test_wrong_coverage_identity_ai_without_trace_and_tamper_are_rejected(self):
        value,reference=self.write_review()
        variants=[]
        changed=deepcopy(value);changed['records'][0]['provenance']['frames_viewed']=[1];variants.append(changed)
        changed=deepcopy(value);changed['records'][0]['reviewer']['name']='';variants.append(changed)
        changed=deepcopy(value);changed['records'][0]['reviewer']['kind']='ai';variants.append(changed)
        changed=deepcopy(value);changed['records'][0]['annotation_sha256']='0'*64;variants.append(changed)
        changed=deepcopy(value);changed['records'][0]['evidence_sha256']={};variants.append(changed)
        for index,changed in enumerate(variants):
            with self.subTest(index=index):
                current=self.save(reference,changed)
                with self.assertRaises(ValueError):global_qc.resolve(self.samples,[current])
        current=self.save(reference,value)
        Path(current['path']).write_text('changed original file')
        with self.assertRaisesRegex(ValueError,'reference bytes changed'):global_qc.resolve(self.samples,[current])

    def test_relocation_is_reusable_but_different_sample_bytes_are_not(self):
        _,reference=self.write_review();before=global_qc.population_binding(self.samples)
        moved=self.root/'relocated';shutil.copytree(self.client,moved)
        rows=[{'sample_id':row['sample_id'],'sample_path':str(moved/'samples'/row['sample_id'])} for row in self.samples]
        self.assertEqual(global_qc.population_binding(rows),before)
        self.assertEqual(global_qc.resolve(rows,[reference])['status'],'PASS')
        path=moved/'samples'/rows[0]['sample_id']/'annotation.json'
        value=json.loads(path.read_text());value['final_result']='Changed synthetic evidence';path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):global_qc.resolve(rows,[reference])

    def test_conflicting_fifths_need_explicit_effective_selection(self):
        value,first=self.write_review('first')
        _,copy=self.write_review('same-copy')
        self.assertEqual(global_qc.resolve(self.samples,[first,copy])['status'],'PASS')
        _,other=self.write_review('different',statuses={self.samples[0]['sample_id']:'FAIL'})
        with self.assertRaisesRegex(ValueError,'Conflicting global decisions'):
            global_qc.resolve(self.samples,[first,other])
        # Explicitly selecting the later human source closes a pending vote;
        # neither earlier file is deleted or rewritten to do so.
        result=global_qc.resolve(self.samples,[other])
        self.assertEqual(result['status'],'FAIL');self.assertTrue(Path(first['path']).is_file())

    def test_internal_directory_and_file_symlinks_rejected_before_evidence_read(self):
        for variant in ('directory','file'):
            with self.subTest(variant=variant):
                _,client,_=fixture(self.root/('links-'+variant),count=1)
                sample=next((client/'samples').iterdir())
                if variant=='directory':
                    path=sample/'images';target=sample/'real-images';path.rename(target)
                    path.symlink_to(target.name,target_is_directory=True)
                else:
                    path=sample/'images/step_001.png';target=path.with_name('real-frame.png');path.rename(target)
                    path.symlink_to(target.name)
                rows=[{'sample_id':sample.name,'sample_path':str(sample)}]
                with patch.object(global_qc,'evidence_files',side_effect=AssertionError('No evidence read before child symlink rejection')):
                    with self.assertRaisesRegex(ValueError,'symlink'):
                        global_qc.population_binding(rows)


if __name__=='__main__':unittest.main()
