"""Controlled runner integration only; no real model, site or human decisions."""
import contextlib
import csv
from copy import deepcopy
import io
import json
import os
import shutil
from pathlib import Path
import sys
import time
import urllib.error
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/quality-inspector'),str(REPO/'projects/quality-inspector/tests')]
from webcollect.batch_core import BatchLedger,ModelRateWait
from quality_inspector.cumulative import build_set_manifest
from delivery_scope_fixture import freeze_scope
from quality_inspector import delivery_sampling,delivery_pipeline as pipeline


class DeliveryPipelineTests(unittest.TestCase):
    def setUp(self):
        from test_delivery import DeliveryContractTests
        self.fixture=DeliveryContractTests('test_delivery_needs_no_reference_samples_or_capture_archives')
        self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.root=self.fixture.root;self.dataset=self.fixture.client
        prompt=self.dataset/'动作空间与系统提示.md';prompt.write_text('\n'+prompt.read_text());self.fixture.seal()
        self.plan=self.root/'plan.json'
        delivery_sampling.freeze(self.dataset,self.plan,ai_percent=100,human_percent=0,seed='CONTROLLED-runner')
        self.effective,self.cross_report=freeze_scope(self.root/'scope',[self.dataset])
        self.config=json.loads((REPO/'projects/code/config/batch-synthetic.json').read_text())
        self.config['run_id']='CONTROLLED-pipeline-integration-no-real-model'
        self.config['model']['reserve_input_tokens']=500000
        self.config['budget']['max_reserved_tokens']=5000000
        self.ledger=BatchLedger(self.root/'operations.sqlite3',self.config,initialize=True)

    def prepare(self,**kwargs):
        return pipeline.prepare(self.ledger,self.dataset,self.plan,self.effective,self.root/'prepared',
                                profile=self.fixture.profile,cross_package_report=self.cross_report,mode='controlled',**kwargs)

    def real_ledger_fixture(self):
        config=deepcopy(self.config);config['mode']='real'
        config['run_id']='CONTROLLED-MOCK-GLM-PROTOCOL-NO-REAL-SERVICE'
        config['budget'].update(currency='CNY',max_model_cost_micros=1000000,min_model_interval_seconds=1)
        config['model'].update(provider='glm',model='glm-5.3-flash',endpoint='https://controlled.invalid/chat',
            api_key_env='CONTROLLED_PIPELINE_KEY',supports_vision=True,image_tokens_per_image=100,
            request_overhead_tokens=1000,reserve_cost_micros=1,
            rates={'version':'CONTROLLED-TEST-ONLY','source':'Authored offline protocol rates; not actual prices',
                   'input':1,'cached_input':0,'output':1})
        return BatchLedger(self.root/'CONTROLLED-real-protocol.sqlite3',config,initialize=True)

    class PassingProtocolGateway:
        """Authored protocol fixture, not an actual GLM/pixel judgement."""
        def __init__(self,ledger):self.ledger=ledger
        def transform(self,job,result):return result
        def call(self,job,purpose,text,schema,*,images=(),synthetic_response=None,**kwargs):
            from jsonschema import Draft202012Validator
            result=deepcopy(synthetic_response)
            for check in result['checks'].values():
                check.update(status='PASS',note='CONTROLLED MOCK PROTOCOL ONLY; NOT ACTUAL MODEL APPROVAL')
            result=self.transform(job,result)
            Draft202012Validator(schema).validate(result)
            while True:
                try:
                    ref=self.ledger.reserve_request(job,purpose+':CONTROLLED',0,request_json={
                        'CONTROLLED_TEST_ONLY':True,'text':text,'schema':schema,
                        'images':[{'path':str(path),'sha256':pipeline._sha(path)} for path in images]})
                    break
                except ModelRateWait as error:time.sleep(error.seconds)
            self.ledger.settle_request(ref['id'],state='succeeded',usage={
                'input_tokens':100,'output_tokens':20,'cached_input_tokens':0,'source':'CONTROLLED_MOCK_NO_NETWORK'},
                response={'CONTROLLED_TEST_ONLY':True,'result':result,'provider_response':{
                    'model':'glm-5.3-flash','choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}],
                    'usage':{'prompt_tokens':100,'completion_tokens':20,'prompt_tokens_details':{'cached_tokens':0}},
                    'CONTROLLED_MOCK_NO_NETWORK':True}})
            return result

    def run_mock_real(self):
        ledger=self.real_ledger_fixture()
        prepared=pipeline.prepare(ledger,self.dataset,self.plan,self.effective,self.root/'real-prepared',
                                  profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real')
        with patch.object(pipeline.ai_worker,'ModelGateway',self.PassingProtocolGateway):
            state=pipeline.run(prepared['receipt'],self.root/'real-run',max_jobs=10)
        return ledger,prepared,state

    def test_prepare_binds_jobs_to_plan_and_dispatches_no_model_requests(self):
        result=self.prepare();receipt=pipeline.verify(result['receipt'],self.ledger)
        self.assertEqual(result['bound_jobs'],3)
        self.assertEqual(result['ai_selected_samples'],1)
        self.assertEqual(self.ledger.summary()['model_requests'],0)
        for jid in receipt['jobs']:
            job=self.ledger.get(jid)
            self.assertEqual(job['payload']['delivery_pipeline_binding']['plan_sha256'],receipt['plan_sha256'])
            self.assertEqual(job['payload']['delivery_pipeline_binding'],receipt['binding'])
        self.assertFalse(receipt['release_ready'])

    def test_document_coverage_revalidates_real_review_protocol_and_reuses_original_sample_jobs(self):
        ledger,prepared,state=self.run_mock_real()
        original=pipeline.verify(prepared['receipt'],ledger)
        exported=pipeline.ai_worker.report(ledger,original['queue']['path'],self.root/'sample-only')
        reviews=exported['review_file']
        second=pipeline.prepare(ledger,self.dataset,self.plan,self.effective,self.root/'verified-doc-prepared',
            profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real',sample_reviews=reviews)
        revised=pipeline.verify(second['receipt'],ledger)
        context=ledger.get(revised['document_job'])['payload']['supplementary_evidence']['verified_sample_review_state']
        self.assertEqual(context['semantic_sampling']['actual_ai_reviewed'],1)
        self.assertEqual(context['semantic_sampling']['actual_human_reviewed'],0)
        self.assertEqual(context['semantic_sampling']['human_pending_count'],1)
        self.assertEqual(context['samples'][0]['status'],'REVIEW_REQUIRED')
        self.assertEqual({jid for jid in original['jobs'] if original['jobs'][jid]['kind']!='ai-documents'},
                         {jid for jid in revised['jobs'] if revised['jobs'][jid]['kind']!='ai-documents'})
        before=ledger.summary()['model_requests']
        with patch.object(pipeline.ai_worker,'ModelGateway',self.PassingProtocolGateway):
            resolved=pipeline.run(second['receipt'],self.root/'verified-doc-run',max_jobs=10)
        self.assertEqual(ledger.summary()['model_requests'],before+1)
        self.assertEqual(resolved['payload_status'],'REVIEW_REQUIRED') # documents cannot settle missing pair evidence
        self.assertEqual(resolved['actual_human_reviewed'],0)

    def test_document_coverage_preserves_pending_selected_sample_review(self):
        reviews=self.fixture.reviewed();value=json.loads(reviews.read_text())
        value.pop('delivery_document_review',None)
        value['records'][0]['checks']['privacy']['status']='REVIEW_REQUIRED'
        reviews.write_text(json.dumps(value))
        prepared=self.prepare(sample_reviews=reviews)
        receipt=pipeline.verify(prepared['receipt'],self.ledger)
        context=self.ledger.get(receipt['document_job'])['payload']['supplementary_evidence']['verified_sample_review_state']
        self.assertNotEqual(context['samples'][0]['status'],'PASS')
        self.assertGreater(context['semantic_sampling']['human_pending_count'],0)
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_run_uses_only_bound_jobs_and_controlled_reviews_never_claim_real_ai_pass(self):
        result=self.prepare()
        unrelated=self.ledger.enqueue('ai-visual',{'CONTROLLED-unbound':'must not execute'})
        with patch('urllib.request.build_opener',side_effect=AssertionError('No network in controlled integration')):
            status=pipeline.run(result['receipt'],self.root/'run',max_jobs=10)
        self.assertEqual(self.ledger.get(unrelated)['state'],'queued')
        self.assertEqual(status['job_states'],{'done':3})
        self.assertEqual(status['actual_ai_reviewed'],0)
        self.assertEqual(status['actual_human_reviewed'],0)
        self.assertEqual(status['ai_pending_count'],1)
        self.assertFalse(status['release_ready'])
        report=json.loads(Path(status['report']['path']).read_text())
        self.assertEqual(report['semantic_sampling']['rows'][0]['status'],'AI_REQUIRED')
        raw=json.loads(Path(status['review_file']['path']).read_text())
        self.assertEqual(raw['schema_version'],'webcollect-synthetic-review-test-1')
        self.assertTrue((self.root/'run/human-queue.json').is_file())
        self.assertTrue((self.root/'run/replacement-requests.json').is_file())
        with self.assertRaisesRegex(ValueError,'Controlled pipelines'):
            pipeline.finalize(result['receipt'],self.root/'run/status.json',self.root/'final')

    def test_unstarted_status_and_replay_do_not_dispatch_or_repeat_completed_jobs(self):
        result=self.prepare()
        before=pipeline.status(result['receipt'],self.root/'before')
        self.assertEqual(before['ai_pending_count'],1)
        self.assertEqual(self.ledger.summary()['model_requests'],0)
        pipeline.run(result['receipt'],self.root/'run',max_jobs=10)
        used=self.ledger.summary()['model_requests']
        again=pipeline.run(result['receipt'],self.root/'again',max_jobs=10)
        self.assertEqual(self.ledger.summary()['model_requests'],used)
        self.assertEqual(again['job_states'],{'done':3})

    def test_changed_plan_sample_or_job_payload_stops_before_dispatch(self):
        result=self.prepare();receipt=pipeline.verify(result['receipt'])
        jid=next(iter(receipt['jobs']))
        with self.ledger.transaction() as con:
            job=self.ledger.get(jid);payload=deepcopy(job['payload']);payload['unexpected']='changed'
            con.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(payload),jid))
        with self.assertRaisesRegex(ValueError,'job identity/payload changed'):
            pipeline.run(result['receipt'],self.root/'run')
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_bad_output_or_mode_is_rejected_before_model_work(self):
        with self.assertRaisesRegex(ValueError,'glm-5.3-flash'):
            pipeline.prepare(self.ledger,self.dataset,self.plan,self.effective,self.root/'bad',
                             profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real')
        self.assertFalse((self.root/'bad').exists())
        result=self.prepare();(self.root/'existing').mkdir()
        with self.assertRaisesRegex(ValueError,'new output path'):
            pipeline.run(result['receipt'],self.root/'existing')
        with self.assertRaisesRegex(ValueError,'outside inspected'):
            pipeline.run(result['receipt'],self.dataset/'new-qc-output')
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_actual_human_records_are_required_and_cannot_invent_selected_ai_work(self):
        result=self.prepare()
        with self.assertRaisesRegex(ValueError,'Actual human review'):
            pipeline.import_human(result['receipt'],[],self.root/'empty-human')
        human=self.fixture.reviewed();value=json.loads(human.read_text());value.pop('delivery_document_review',None)
        for row in value['records']:
            row['reviewer']={'kind':'human','name':'CONTROLLED TEST AUTHOR; NOT REAL HUMAN APPROVAL'}
            row['checks']['terminal_semantics']['status']='FAIL'
        human.write_text(json.dumps(value))
        status=pipeline.import_human(result['receipt'],[human],self.root/'human-result')
        self.assertEqual(status['replacement_required_count'],1)
        requests=json.loads((self.root/'human-result/replacement-requests.json').read_text())
        self.assertEqual(requests['count'],1)
        self.assertTrue(requests['original_failures_retained'])
        self.assertEqual(self.ledger.summary()['model_requests'],0)
        # The runner exports unchanged imported records, never new decisions.
        imported=json.loads((self.root/'human-result/current-human-reviews.json').read_text())
        self.assertEqual(imported['records'],value['records'])
        self.assertEqual(imported['actual_human_reviews_created'],0)

    def test_receipt_or_implementation_drift_is_rejected(self):
        result=self.prepare();path=Path(result['receipt']);saved=path.read_text()
        value=json.loads(saved);value['ai_selected_sample_ids']=[];path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'receipt was changed'):pipeline.verify(path)
        path.write_text(saved)
        actual=pipeline._implementation()
        with patch.object(pipeline,'_implementation',return_value={**actual,'CONTROLLED-source-drift':'0'*64}):
            pipeline.verify(path)  # unrelated source changes are engineering diagnostics only
        with patch.object(pipeline,'PIPELINE_RULES_VERSION','changed-explicit-pipeline-rules'):
            with self.assertRaisesRegex(ValueError,'rules changed'):pipeline.verify(path)
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_cli_prepare_status_are_explicit_and_offline(self):
        config=self.root/'config.json';config.write_text(json.dumps(self.config))
        args=['prepare','--config',str(config),'--ledger',str(self.ledger.path),
              '--input',str(self.dataset),'--plan',str(self.plan),'--effective-set',str(self.effective),'--cross-package-report',str(self.cross_report),
              '--profile',str(self.fixture.profile),'--output',str(self.root/'cli-prepared'),'--mode','controlled','--document-review-mode','ai']
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(pipeline.main(args),0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pipeline.main(['status','--receipt',str(self.root/'cli-prepared/pipeline-receipt.json'),
                                           '--output',str(self.root/'cli-status')]),0)
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_empty_comparison_blocks_archive_until_explicit_controlled_human_resolution(self):
        ledger=self.real_ledger_fixture()
        prepared=pipeline.prepare(ledger,self.dataset,self.plan,self.effective,self.root/'mock-prepared',
                                  profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real')
        with patch.object(pipeline.ai_worker,'ModelGateway',self.PassingProtocolGateway),\
                patch('urllib.request.build_opener',side_effect=AssertionError('No actual service')):
            state=pipeline.run(prepared['receipt'],self.root/'mock-run',max_jobs=10)
        self.assertEqual(state['payload_status'],'REVIEW_REQUIRED')
        self.assertEqual(state['human_pending_count'],1)
        self.assertEqual(state['pipeline_model_usage']['model_requests'],2)
        archive=self.root/'CONTROLLED-TEST-NOT-PRODUCTION.zip'
        with self.assertRaisesRegex(ValueError,'remain unresolved'):
            pipeline.finalize(prepared['receipt'],self.root/'mock-run/status.json',self.root/'blocked-final',archive=archive)
        self.assertFalse(archive.exists())
        # Authored disposable human protocol fixture, never a real review or a
        # host-generated PASS for an absent comparison set.
        human=self.fixture.reviewed();value=json.loads(human.read_text());value.pop('delivery_document_review',None)
        for row in value['records']:row['reviewer']={'kind':'human','name':'CONTROLLED HUMAN PROTOCOL ONLY'}
        human.write_text(json.dumps(value))
        resolved=pipeline.import_human(prepared['receipt'],[human],self.root/'mock-human-resolution')
        self.assertEqual(resolved['payload_status'],'PASS')
        final=pipeline.finalize(prepared['receipt'],self.root/'mock-human-resolution/status.json',self.root/'mock-final',archive=archive)
        self.assertEqual(final['delivery_status'],'PASS')
        self.assertTrue(final['release_ready'])
        self.assertTrue(archive.is_file())
        self.assertEqual(final['customer_acceptance'],'UNKNOWN')

    def test_zero_sample_ai_and_explicit_human_documents_dispatch_nothing(self):
        plan=self.root/'zero-ai-plan.json'
        delivery_sampling.freeze(self.dataset,plan,ai_percent=0,human_percent=0,seed='CONTROLLED-zero-AI')
        ledger=self.real_ledger_fixture()
        prepared=pipeline.prepare(ledger,self.dataset,plan,self.effective,self.root/'human-doc-prepared',
            profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real',document_review_mode='human')
        with patch.object(pipeline.ai_worker,'ModelGateway',side_effect=AssertionError('No AI at zero sample rate with human documents')):
            state=pipeline.run(prepared['receipt'],self.root/'human-doc-pending',max_jobs=10)
        self.assertEqual(state['actual_ai_reviewed'],0);self.assertEqual(state['human_document_pending_count'],1)
        self.assertEqual(state['pipeline_model_usage']['model_requests'],0)
        reviews=json.loads(self.fixture.reviewed().read_text());reviews['records']=[]
        reviews['delivery_document_review']['reviewer']={'kind':'human','name':'CONTROLLED HUMAN PROTOCOL FIXTURE ONLY'}
        path=self.root/'authored-human-document.json';path.write_text(json.dumps(reviews))
        original=path.read_bytes()
        with patch.object(pipeline.ai_worker,'ModelGateway',side_effect=AssertionError('Import/final/package must not dispatch AI')):
            resolved=pipeline.import_human(prepared['receipt'],[path],self.root/'human-doc-resolved')
            self.assertEqual(resolved['payload_status'],'PASS')
            final=pipeline.finalize(prepared['receipt'],self.root/'human-doc-resolved/status.json',
                self.root/'human-doc-final',archive=self.root/'CONTROLLED-human-route.zip')
        self.assertTrue(final['release_ready']);self.assertEqual(ledger.summary()['model_requests'],0)
        self.assertEqual(path.read_bytes(),original)
        report=json.loads(Path(resolved['report']['path']).read_text())
        self.assertEqual(report['semantic_sampling']['rows'][0]['status'],'NOT_SELECTED')
        self.assertFalse(report['semantic_sampling']['rows'][0]['semantic_review_claimed'])

    def test_relocated_package_reuses_sample_and_documentary_results(self):
        ledger,prepared,state=self.run_mock_real();count=ledger.summary()['model_requests']
        moved=self.root/'relocated-client';shutil.copytree(self.dataset,moved)
        plan=self.root/'relocated-plan.json'
        delivery_sampling.freeze(moved,plan,ai_percent=100,human_percent=0,seed='CONTROLLED-runner')
        effective,cross=freeze_scope(self.root/'relocated-scope',[moved])
        second=pipeline.prepare(ledger,moved,plan,effective,self.root/'relocated-prepared',
            profile=self.fixture.profile,cross_package_report=cross,mode='real')
        with patch.object(pipeline.ai_worker,'ModelGateway',self.PassingProtocolGateway):
            result=pipeline.run(second['receipt'],self.root/'relocated-run',max_jobs=10)
        self.assertEqual(result['payload_status'],'REVIEW_REQUIRED');self.assertEqual(ledger.summary()['model_requests'],count)
        self.assertEqual(result['pipeline_model_usage']['model_requests'],0)

    def test_worker_revalidates_frozen_scope_without_repeating_global_pair_checks(self):
        from quality_inspector import delivery_scope
        ledger=self.real_ledger_fixture()
        with patch.object(delivery_scope,'inspect_set',wraps=delivery_scope.inspect_set) as checks:
            prepared=pipeline.prepare(ledger,self.dataset,self.plan,self.effective,self.root/'count-prepared',
                profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real')
            self.assertEqual(checks.call_count,1)
            with patch.object(pipeline.ai_worker,'ModelGateway',self.PassingProtocolGateway):
                state=pipeline.run(prepared['receipt'],self.root/'count-run',max_jobs=10)
            self.assertEqual(state['payload_status'],'REVIEW_REQUIRED');self.assertEqual(checks.call_count,1)
            pipeline.status(prepared['receipt'],self.root/'count-status')
            self.assertEqual(checks.call_count,1)
        value=json.loads(self.cross_report.read_text());value['cross_package_status']='FAIL'
        self.cross_report.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'Bound pipeline input file changed'):
            pipeline.verify(prepared['receipt'])

    def test_unknown_glm_network_result_routes_bound_request_to_human_without_auto_retry(self):
        ledger=self.real_ledger_fixture()
        prepared=pipeline.prepare(ledger,self.dataset,self.plan,self.effective,self.root/'failed-prepared',
                                  profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real')
        class NoNetwork:
            def open(self,*args,**kwargs):raise urllib.error.URLError('CONTROLLED UNKNOWN OUTCOME; NO NETWORK')
        with patch.dict(os.environ,{'CONTROLLED_PIPELINE_KEY':'CONTROLLED-NONCREDENTIAL'}),\
                patch('webcollect.model_gateway.socket.getaddrinfo',return_value=[('fixture',)]), \
                patch('urllib.request.build_opener',return_value=NoNetwork()):
            state=pipeline.run(prepared['receipt'],self.root/'failed-run',max_jobs=10)
        self.assertEqual(state['human_pending_count'],1)
        self.assertEqual(state['ai_pending_count'],0)
        self.assertEqual(state['actual_ai_reviewed'],0)
        self.assertEqual(state['pipeline_model_usage']['model_requests'],2)  # visual + documentary; neither retried
        self.assertEqual(state['pipeline_model_usage']['request_states'],{'unknown':2})
        self.assertFalse(state['pipeline_model_usage']['usage_coverage_complete'])
        self.assertEqual(state['pipeline_model_usage']['input_tokens'],'UNKNOWN')
        self.assertTrue(state['ai_failure_sources'])
        report=json.loads(Path(state['report']['path']).read_text())
        self.assertEqual(report['semantic_sampling']['rows'][0]['ai_status'],'CALL_FAILED')
        with self.assertRaisesRegex(ValueError,'remain unresolved'):
            pipeline.finalize(prepared['receipt'],self.root/'failed-run/status.json',self.root/'refused-final')
        moved=self.root/'unknown-relocated';shutil.copytree(self.dataset,moved)
        plan=self.root/'unknown-relocated-plan.json'
        delivery_sampling.freeze(moved,plan,ai_percent=100,human_percent=0,seed='CONTROLLED-runner')
        effective,cross=freeze_scope(self.root/'unknown-relocated-scope',[moved])
        again=pipeline.prepare(ledger,moved,plan,effective,self.root/'unknown-relocated-prepared',
            profile=self.fixture.profile,cross_package_report=cross,mode='real')
        with patch.object(self.PassingProtocolGateway,'call',side_effect=AssertionError('No repeated UNKNOWN request')) as calls,\
                patch.object(pipeline.ai_worker,'ModelGateway',self.PassingProtocolGateway):
            repeated=pipeline.run(again['receipt'],self.root/'unknown-relocated-run',max_jobs=10)
        self.assertEqual(calls.call_count,0);self.assertEqual(ledger.summary()['model_requests'],2)
        self.assertEqual(repeated['human_pending_count'],1);self.assertEqual(repeated['ai_pending_count'],0)
        self.assertEqual(repeated['actual_ai_reviewed'],0);self.assertTrue(repeated['ai_failure_sources'])

    def test_human_rejection_replacement_is_bound_and_cannot_escape_reinspection(self):
        from quality_inspector.checksums import write_manifest
        ledger=self.real_ledger_fixture()
        prepared=pipeline.prepare(ledger,self.dataset,self.plan,self.effective,self.root/'first-prepared',
                                  profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real')
        with patch.object(pipeline.ai_worker,'ModelGateway',self.PassingProtocolGateway):
            pipeline.run(prepared['receipt'],self.root/'first-run',max_jobs=10)
        human=self.fixture.reviewed();raw=json.loads(human.read_text());raw.pop('delivery_document_review',None)
        old_id=raw['records'][0]['sample_id']
        raw['records'][0]['reviewer']={'kind':'human','name':'CONTROLLED TEST AUTHOR, NOT ACTUAL HUMAN'}
        raw['records'][0]['checks']['terminal_semantics']['status']='FAIL'
        human.write_text(json.dumps(raw))
        rejected=pipeline.import_human(prepared['receipt'],[human],self.root/'rejected')
        self.assertEqual(rejected['replacement_required_count'],1)
        original_bytes=(self.dataset/'samples'/old_id/'annotation.json').read_bytes()
        new_dataset=self.root/'replacement-client';shutil.copytree(self.dataset,new_dataset)
        old=new_dataset/'samples'/old_id;new=old.with_name('CONTROLLED_replacement_001');old.rename(new)
        annotation=json.loads((new/'annotation.json').read_text());annotation['sample_id']=new.name
        (new/'annotation.json').write_text(json.dumps(annotation))
        (new_dataset/'ground_truth'/f'{old_id}.json').rename(new_dataset/'ground_truth'/f'{new.name}.json')
        site=json.loads((new_dataset/'site-list.json').read_text())
        for row in site['sites']:row['sample_ids']=[new.name if sid==old_id else sid for sid in row['sample_ids']]
        for row in site['samples']:
            if row['sample_id']==old_id:row['sample_id']=new.name
        (new_dataset/'site-list.json').write_text(json.dumps(site))
        with (new_dataset/'metadata.csv').open(newline='') as stream:
            reader=csv.DictReader(stream);columns=reader.fieldnames;rows=list(reader)
        rows[0]['sample_id']=new.name;rows[0]['bytes']=str(sum(p.stat().st_size for p in new.rglob('*') if p.is_file()))
        with (new_dataset/'metadata.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows(rows)
        (new_dataset/'SHA256SUMS').unlink();write_manifest(new_dataset)
        new_plan=self.root/'replacement-plan.json'
        delivery_sampling.replace(self.plan,old_id,new,human,new_plan,reason='CONTROLLED fixture failure; replacement protocol only')
        new_set,new_cross=freeze_scope(self.root/'replacement-scope',[new_dataset])
        replacement=pipeline.prepare(ledger,new_dataset,new_plan,new_set,self.root/'replacement-prepared',
                                     profile=self.fixture.profile,cross_package_report=new_cross,mode='real')
        with patch.object(pipeline.ai_worker,'ModelGateway',self.PassingProtocolGateway):
            checked=pipeline.run(replacement['receipt'],self.root/'replacement-run',max_jobs=10)
        self.assertEqual(checked['human_pending_count'],1)
        self.assertEqual(checked['actual_ai_reviewed'],1)
        self.assertNotEqual(checked['payload_status'],'PASS')
        # Import may retain old rejection records, but only the unchanged actual
        # decision for the current replacement is exported for current intake.
        new_raw=deepcopy(raw);record=deepcopy(raw['records'][0]);record['sample_id']=new.name
        record['annotation_sha256']=pipeline._sha(new/'annotation.json')
        record['evidence_sha256']=delivery_sampling.evidence_files(new)
        for check in record['checks'].values():check['status']='PASS'
        new_raw['records'].append(record)
        new_human=self.root/'actual-CONTROLLED-human-export.json';new_human.write_text(json.dumps(new_raw))
        resolved=pipeline.import_human(replacement['receipt'],[new_human],self.root/'replacement-resolved')
        self.assertEqual(resolved['payload_status'],'PASS')
        self.assertEqual(resolved['human_pending_count'],0)
        self.assertEqual(resolved['replacement_required_count'],0)
        self.assertEqual((self.dataset/'samples'/old_id/'annotation.json').read_bytes(),original_bytes)
        self.assertEqual(json.loads(human.read_text())['records'][0]['checks']['terminal_semantics']['status'],'FAIL')

    def test_imported_human_fail_is_sticky_when_status_omits_parameter_or_uses_old_status(self):
        ledger,prepared,state=self.run_mock_real()
        self.assertEqual(state['payload_status'],'REVIEW_REQUIRED')
        human=self.fixture.reviewed();raw=json.loads(human.read_text());raw.pop('delivery_document_review',None)
        raw['records'][0]['reviewer']={'kind':'human','name':'CONTROLLED STICKY REJECTION FIXTURE'}
        initial_human=self.root/'initial-human-pass.json';initial_human.write_text(json.dumps(raw))
        pipeline.import_human(prepared['receipt'],[initial_human],self.root/'initial-human-approved')
        raw['records'][0]['checks']['privacy']['status']='FAIL';human.write_text(json.dumps(raw))
        rejected=pipeline.import_human(prepared['receipt'],[human],self.root/'human-rejected')
        self.assertEqual(rejected['replacement_required_count'],1)
        again=pipeline.status(prepared['receipt'],self.root/'omitted-human')
        self.assertEqual(again['replacement_required_count'],1)
        self.assertNotEqual(again['payload_status'],'PASS')
        with self.assertRaisesRegex(ValueError,'Human inspection history changed'):
            pipeline.finalize(prepared['receipt'],self.root/'real-run/status.json',self.root/'stale-final',archive=self.root/'forbidden.zip')
        self.assertFalse((self.root/'forbidden.zip').exists())
        old_status_path=self.root/'real-run/status.json';old_status=json.loads(old_status_path.read_text())
        old_status['human_history_sha256']=again['human_history_sha256']
        old_status_path.write_text(json.dumps(old_status))
        with self.assertRaisesRegex(ValueError,'not issued'):
            pipeline.finalize(prepared['receipt'],old_status_path,self.root/'forged-final',archive=self.root/'forged.zip')
        self.assertFalse((self.root/'forged.zip').exists())
        raw['records'][0]['checks']['privacy']['status']='PASS'
        conflicting=self.root/'changed-vote.json';conflicting.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,'new capture identity'):
            pipeline.import_human(prepared['receipt'],[conflicting],self.root/'overwritten-human')

    def test_progress_rejection_precedes_archive_publication(self):
        _,prepared,state=self.run_mock_real()
        human=self.fixture.reviewed();value=json.loads(human.read_text());value.pop('delivery_document_review',None)
        for row in value['records']:row['reviewer']={'kind':'human','name':'CONTROLLED HUMAN PROGRESS FIXTURE ONLY'}
        human.write_text(json.dumps(value))
        pipeline.import_human(prepared['receipt'],[human],self.root/'progress-human')
        class RejectProgress:
            def import_qc(self,*args,**kwargs):raise ValueError('CONTROLLED progress admission rejection')
        archive=self.root/'must-not-exist.zip'
        with self.assertRaisesRegex(ValueError,'progress admission rejection'):
            pipeline.finalize(prepared['receipt'],self.root/'progress-human/status.json',self.root/'denied-final',
                              archive=archive,progress=RejectProgress(),request_id='CONTROLLED-reject')
        self.assertFalse(archive.exists())

    def test_cli_cannot_initialize_model_ledger_inside_historical_package(self):
        # A separately frozen historical package is protected before any SQLite
        # constructor is allowed to create a file in it.
        historical=self.root/'historical';shutil.copytree(self.dataset,historical)
        effective=self.root/'with-history.json'
        delivery_sampling.write(effective,build_set_manifest([self.dataset,historical]))
        config=self.root/'config.json';config.write_text(json.dumps(self.config))
        ledger=historical/'must-not-be-created.sqlite3'
        with contextlib.redirect_stdout(io.StringIO()):
            result=pipeline.main(['prepare','--config',str(config),'--ledger',str(ledger),'--initialize-ledger',
                '--input',str(self.dataset),'--plan',str(self.plan),'--effective-set',str(effective),'--cross-package-report',str(self.cross_report),
                '--profile',str(self.fixture.profile),'--output',str(self.root/'bad-history'),'--mode','controlled','--document-review-mode','ai'])
        self.assertEqual(result,2);self.assertFalse(ledger.exists())

    def test_documentary_ai_issue_can_be_resolved_by_actual_bound_human_record(self):
        ledger=self.real_ledger_fixture()
        prepared=pipeline.prepare(ledger,self.dataset,self.plan,self.effective,self.root/'doc-prepared',
                                  profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real')
        class DocumentFailGateway(self.PassingProtocolGateway):
            def transform(self,job,result):
                if job['kind']=='ai-documents':
                    result=deepcopy(result)
                    next(iter(result['checks'].values()))['status']='FAIL'
                return result
        with patch.object(pipeline.ai_worker,'ModelGateway',DocumentFailGateway):
            failed=pipeline.run(prepared['receipt'],self.root/'doc-failed',max_jobs=10)
        self.assertEqual(failed['human_document_pending_count'],1)
        self.assertNotEqual(failed['payload_status'],'PASS')
        human=self.fixture.reviewed();value=json.loads(human.read_text());value['records']=[]
        value['delivery_document_review']['reviewer']={'kind':'human','name':'CONTROLLED DOCUMENT HUMAN FIXTURE'}
        human.write_text(json.dumps(value))
        resolved=pipeline.import_human(prepared['receipt'],[human],self.root/'doc-human')
        self.assertEqual(resolved['payload_status'],'REVIEW_REQUIRED')
        self.assertEqual(resolved['human_pending_count'],1) # documentary decision does not decide the sample's missing comparison
        self.assertEqual(resolved['document_review_status'],'HUMAN_PASS')
        replay=pipeline.status(prepared['receipt'],self.root/'doc-replay')
        self.assertEqual(replay['document_review_status'],'HUMAN_PASS')
        original=json.loads(Path(resolved['worker_review_file']['path']).read_text())
        self.assertTrue(any(row['status']=='FAIL' for row in original['delivery_document_review']['checks'].values()))

    def test_schema_success_followed_by_real_worker_validation_failure_routes_to_human(self):
        ledger=self.real_ledger_fixture()
        prepared=pipeline.prepare(ledger,self.dataset,self.plan,self.effective,self.root/'post-prepare',
                                  profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real')
        class WhitespaceGateway(self.PassingProtocolGateway):
            def transform(self,job,result):
                if job['kind']=='ai-visual':next(iter(result['checks'].values()))['note']=' '
                return result
        with patch.object(pipeline.ai_worker,'ModelGateway',WhitespaceGateway):
            status=pipeline.run(prepared['receipt'],self.root/'post-run',max_jobs=10)
        self.assertEqual(status['human_pending_count'],1)
        self.assertEqual(status['pipeline_model_usage']['request_states'],{'succeeded':2})
        report=json.loads(Path(status['report']['path']).read_text())
        row=report['semantic_sampling']['rows'][0]
        self.assertEqual(row['status'],'HUMAN_REQUIRED')
        self.assertEqual(row['ai_status'],'CALL_POST_VALIDATION_FAILED')
        receipt=json.loads(Path(status['ai_failure_sources'][0]['path']).read_text())
        self.assertEqual(receipt['rows'][0]['request_state'],'succeeded')
        self.assertIn('validate_review',receipt['rows'][0]['worker_validation_failure']['validator'])
        self.assertTrue(receipt['rows'][0]['worker_validation_failure']['original_response_sha256'])

    def test_hand_changed_job_error_does_not_forge_a_reproduced_validation_failure(self):
        ledger,prepared,_=self.run_mock_real()
        receipt=pipeline.verify(prepared['receipt'],ledger)
        jid=next(jid for jid,item in receipt['jobs'].items() if item['kind']=='ai-visual')
        with ledger.transaction() as con:
            con.execute("UPDATE jobs SET state='review_required',error='ValueError' WHERE id=?",(jid,))
        state=pipeline.status(prepared['receipt'],self.root/'fake-job-error')
        self.assertEqual(state['human_pending_count'],0)
        self.assertEqual(state['ai_pending_count'],1)
        self.assertFalse(state['ai_failure_sources'])

    def test_recovered_unknown_model_request_routes_to_human_with_lease_event_proof(self):
        ledger=self.real_ledger_fixture()
        prepared=pipeline.prepare(ledger,self.dataset,self.plan,self.effective,self.root/'expired-prepared',
                                  profile=self.fixture.profile,cross_package_report=self.cross_report,mode='real')
        receipt=pipeline.verify(prepared['receipt'],ledger)
        jid=next(jid for jid,item in receipt['jobs'].items() if item['kind']=='ai-visual')
        job=ledger.claim('ai-visual',job_id=jid)
        request=ledger.reserve_request(job,'CONTROLLED interrupted transport',0,request_json={'CONTROLLED_NO_NETWORK':True})
        with ledger.transaction() as con:con.execute('UPDATE jobs SET lease=? WHERE id=?',(time.time()-1,jid))
        ledger.recover()
        state=pipeline.status(prepared['receipt'],self.root/'expired-status')
        self.assertEqual(state['human_pending_count'],1)
        self.assertEqual(state['pipeline_model_usage']['request_states'],{'unknown':1})
        proof=json.loads(Path(state['ai_failure_sources'][0]['path']).read_text())
        self.assertEqual(proof['rows'][0]['request_id'],request['id'])
        self.assertEqual(proof['rows'][0]['recovery_event']['event'],'lease_expired')
        with ledger.connect() as con:
            saved=con.execute('SELECT state,finished,cost FROM model_requests WHERE id=?',(request['id'],)).fetchone()
        self.assertEqual(saved['state'],'unknown');self.assertIsNone(saved['finished']);self.assertIsNone(saved['cost'])


if __name__=='__main__':unittest.main()
