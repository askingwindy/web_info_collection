"""Synthetic semantic reuse probes: no site, model service or human is contacted."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/quality-inspector'),str(REPO/'projects/quality-inspector/tests')]
from make_fixture import fixture
from quality_inspector import ai_worker, semantic, contract
from quality_inspector.reviews import intake
from webcollect.batch_core import BatchLedger, OutcomeUnknown, load_json


class SemanticReuseTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.sample=fixture(self.root/'first');self.dataset=self.sample.parent.parent
        self.ledger=BatchLedger(self.root/'ops.sqlite3',load_json(REPO/'projects/code/config/batch-synthetic.json'),initialize=True)
        self.calls=[]
        outer=self
        class Stub:
            def __init__(self,ledger):pass
            def call(self,job,purpose,text,schema,*,synthetic_response=None,**kwargs):
                outer.calls.append((purpose,deepcopy(schema),text))
                result=deepcopy(synthetic_response)
                for check in result.get('checks',{}).values():
                    check['status']='PASS';check['note']='Authored offline fixture only; no actual model review'
                return result
        self.stub=Stub
        self.addCleanup(patch.stopall)
        patch('urllib.request.build_opener',side_effect=AssertionError('No external service')).start()
        patch('socket.create_connection',side_effect=AssertionError('No network')).start()

    def prepare_run(self,name,dataset=None):
        prepared=ai_worker.prepare(self.ledger,dataset or self.dataset,self.root/name)
        with patch.object(ai_worker,'ModelGateway',self.stub):ai_worker.run(self.ledger,max_jobs=10)
        return load_json(prepared['queue_file'])

    def test_identical_scope_and_relocated_package_do_not_repeat_any_ai_check(self):
        first=self.prepare_run('qc1');self.assertEqual(len(self.calls),1)
        second=self.prepare_run('qc2');self.assertEqual(first['jobs'],second['jobs'])
        other=self.root/'relocated';shutil.copytree(self.dataset,other)
        before={p.relative_to(other).as_posix():p.read_bytes() for p in other.rglob('*') if p.is_file()}
        moved=self.prepare_run('qc3',other)
        self.assertEqual(len(self.calls),1)
        visual=self.ledger.get(moved['jobs'][0]['visual_job'])
        self.assertEqual(set(visual['result']['semantic_check_sources'].values()),{first['jobs'][0]['visual_job']})
        self.assertEqual(before,{p.relative_to(other).as_posix():p.read_bytes() for p in other.rglob('*') if p.is_file()})

    def test_one_rule_change_requests_only_that_check(self):
        first=self.prepare_run('qc1')
        with patch.dict(semantic.RULE_VERSIONS,{'privacy':'changed-explicit-privacy-rule'}):
            changed=self.prepare_run('qc2')
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.calls[-1][1]['properties']['checks']['required'],['privacy'])
        visual=self.ledger.get(changed['jobs'][0]['visual_job'])
        for name in ('visual_alignment','language','terminal_semantics'):
            self.assertEqual(visual['result']['semantic_check_sources'][name],first['jobs'][0]['visual_job'])

    def test_changed_evidence_and_different_sample_cannot_borrow_review(self):
        self.prepare_run('qc1')
        from PIL import Image
        path=self.sample/'images/step_001.png'
        with Image.open(path) as image:
            image=image.copy();image.putpixel((0,0),(17,29,31));image.save(path)
        self.prepare_run('qc2');self.assertEqual(len(self.calls),2)
        other=self.root/'other';shutil.copytree(self.dataset,other)
        target=other/'samples'/self.sample.name;value=load_json(target/'annotation.json')
        value['sample_id']='different_fixture_02';target=target.rename(target.with_name(value['sample_id']))
        (target/'annotation.json').write_text(json.dumps(value))
        self.prepare_run('qc3',other);self.assertEqual(len(self.calls),3)

    def test_unresolved_exact_attempt_does_not_retry_after_repackaging(self):
        outer=self
        class Unknown(self.stub):
            def call(self,*args,**kwargs):
                outer.calls.append('UNKNOWN');raise OutcomeUnknown('Authored uncertain protocol result')
        self.stub=Unknown
        first=self.prepare_run('qc1');self.assertEqual(len(self.calls),1)
        other=self.root/'relocated';shutil.copytree(self.dataset,other)
        second=self.prepare_run('qc2',other)
        self.assertEqual(len(self.calls),1)
        job=self.ledger.get(second['jobs'][0]['visual_job'])
        self.assertEqual(job['state'],'review_required')
        from quality_inspector.semantic_runtime import failure_jobs
        self.assertIn(first['jobs'][0]['visual_job'],failure_jobs(self.ledger,[job['id']]))
        self.assertIsNone(job['result'])

    def test_tampered_completed_result_is_not_reused_or_reissued(self):
        first=self.prepare_run('qc1');source=first['jobs'][0]['visual_job']
        value=self.ledger.get(source)['result'];value['checks']['privacy']['note']='altered source conclusion'
        with self.ledger.transaction() as con:
            con.execute('UPDATE jobs SET result=? WHERE id=?',(json.dumps(value),source))
        moved=self.root/'relocated';shutil.copytree(self.dataset,moved)
        second=self.prepare_run('qc2',moved)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.ledger.get(second['jobs'][0]['visual_job'])['state'],'review_required')

    def test_concurrent_alias_keeps_queued_without_a_second_dispatch(self):
        from quality_inspector.semantic_runtime import guard
        prepared=ai_worker.prepare(self.ledger,self.dataset,self.root/'qc1')
        queue=load_json(prepared['queue_file']);job=self.ledger.get(queue['jobs'][0]['visual_job'])
        with guard(self.ledger,job),patch.object(ai_worker,'ModelGateway',self.stub):
            result=ai_worker.run(self.ledger,max_jobs=10)
        self.assertEqual(len(self.calls),0);self.assertIn('already being inspected',result['stopped'])
        self.assertEqual(self.ledger.get(job['id'])['state'],'queued')
        with patch.object(ai_worker,'ModelGateway',self.stub):ai_worker.run(self.ledger,max_jobs=10)
        self.assertEqual(len(self.calls),1)

    def test_source_snapshot_changes_do_not_change_semantic_contract(self):
        value,digest=contract.fingerprint();changed=deepcopy(value)
        changed['implementation_sha256']['engine.py']='0'*64;changed['rules_version']='new-package-build'
        with patch.object(contract,'installed_contract',return_value=changed):
            snapshot,current=contract.fingerprint()
        self.assertEqual(current,digest);self.assertNotEqual(value['implementation_sha256'],snapshot['implementation_sha256'])

    def collection_checks(self,*,history=()):
        source=self.root/'pending.json'
        checks=[{'task_id':'fixture-task','task_version':'r1','task_sha256':'1'*64,
                 'status':'REVIEW_REQUIRED','reason':'CONTROLLED mapped business question',
                 'history_sample_ids':list(history)}]
        source.write_text(json.dumps({'schema_version':'webcollect-pending-quality-checks-1',
            'checks':checks,'requires_independent_QC':True,'QC_approval':False}))
        path=self.root/'collection-checks.json'
        path.write_text(json.dumps({'schema_version':'webcollect-qc-collection-checks-1',
            'source':{'path':str(source),'sha256':ai_worker.file_sha(source)},'checks':checks,
            'sample_bindings':[{'sample_id':self.sample.name,'task_id':'fixture-task',
                                'task_version':'r1','task_key':'fixture-key'}]}))
        return {'path':str(path.resolve()),'sha256':ai_worker.file_sha(path)}

    def test_pending_collection_checks_are_consumed_once_by_independent_difference(self):
        reference=self.collection_checks()
        prepared=ai_worker.prepare(self.ledger,self.dataset,self.root/'qc1',collection_checks=reference)
        with patch.object(ai_worker,'ModelGateway',self.stub):ai_worker.run(self.ledger,max_jobs=10)
        self.assertTrue(any('CONTROLLED mapped business question' in text for _,_,text in self.calls))
        queue=load_json(prepared['queue_file']);job=self.ledger.get(queue['jobs'][0]['difference_job'])
        self.assertEqual(job['result']['status'],'REVIEW_REQUIRED')
        self.assertEqual(sum(purpose.startswith('difference-collection-checks') for purpose,_,_ in self.calls),1)
        prepared=ai_worker.prepare(self.ledger,self.dataset,self.root/'qc2',collection_checks=reference)
        with patch.object(ai_worker,'ModelGateway',self.stub):ai_worker.run(self.ledger,max_jobs=10)
        self.assertEqual(sum(purpose.startswith('difference-collection-checks') for purpose,_,_ in self.calls),1)

    def test_unmapped_or_missing_comparison_evidence_cannot_turn_into_pass(self):
        reference=self.collection_checks(history=['missing-current-chain-sample'])
        prepared=ai_worker.prepare(self.ledger,self.dataset,self.root/'qc1',collection_checks=reference)
        with patch.object(ai_worker,'ModelGateway',self.stub):ai_worker.run(self.ledger,max_jobs=10)
        queue=load_json(prepared['queue_file']);job=self.ledger.get(queue['jobs'][0]['difference_job'])
        self.assertEqual(job['result']['status'],'REVIEW_REQUIRED')
        self.assertIn('missing-current-chain-sample',job['result']['note'])
        value=load_json(reference['path']);value['sample_bindings']=[]
        Path(reference['path']).write_text(json.dumps(value))
        reference['sha256']=ai_worker.file_sha(reference['path'])
        with self.assertRaisesRegex(ValueError,'no exact candidate task mapping'):
            ai_worker.prepare(self.ledger,self.dataset,self.root/'qc2',collection_checks=reference)

    def test_per_check_review_invalidation_preserves_original_and_other_decisions(self):
        from test_delivery import DeliveryContractTests
        case=DeliveryContractTests();case.setUp();self.addCleanup(case.tearDown)
        path=case.reviewed();before=path.read_bytes();value=load_json(path)
        samples=[{'sample_id':row['sample_id'],'sample_path':str(case.client/'samples'/row['sample_id'])} for row in value['records']]
        with patch.dict(semantic.RULE_VERSIONS,{'privacy':'changed-explicit-privacy-rule'}):
            accepted,errors,_=intake(path,samples,contract.fingerprint()[1])
        self.assertFalse(errors);record=next(iter(accepted.values()))
        self.assertEqual(record['checks']['privacy']['status'],'REVIEW_REQUIRED')
        self.assertTrue(all(record['checks'][name]['status']=='PASS' for name in semantic.RULE_VERSIONS if name!='privacy'))
        self.assertEqual(record['semantic_reuse']['invalidated_checks'][0]['check'],'privacy')
        self.assertEqual(path.read_bytes(),before)

    def test_unversioned_v2_needs_explicit_migration_even_with_matching_contract(self):
        from test_delivery import DeliveryContractTests
        from quality_inspector.reviews import migration_template
        case=DeliveryContractTests();case.setUp();self.addCleanup(case.tearDown)
        path=case.reviewed();value=load_json(path)
        for record in value['records']:record.pop('semantic_rule_ids')
        path.write_text(json.dumps(value));original=path.read_bytes()
        samples=[{'sample_id':row['sample_id'],'sample_path':str(case.client/'samples'/row['sample_id'])} for row in value['records']]
        current=contract.fingerprint()[1]
        accepted,errors,_=intake(path,samples,current)
        self.assertFalse(accepted);self.assertTrue(errors)
        migration=migration_template(path,samples,current)
        for row in migration['decisions']:
            row.update(decision='inherit_unchanged',reason='Explicit synthetic impact assessment only',
                authority_and_semantic_rule_assessment='Authored current-rule compatibility fixture; no actual approval',
                assessor={'kind':'human','name':'SYNTHETIC ASSESSOR FIXTURE ONLY'})
        assessment=self.root/'migration.json';assessment.write_text(json.dumps(migration))
        accepted,errors,migrated=intake(path,samples,current,assessment)
        self.assertFalse(errors);self.assertEqual(len(accepted),len(samples))
        self.assertTrue(migrated);self.assertEqual(path.read_bytes(),original)


if __name__=='__main__':unittest.main()
