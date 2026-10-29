"""Complete documentary evidence and rejection before expenditure, offline only."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from webcollect.batch_core import BatchLedger, file_sha, load_json
from webcollect.model_gateway import ModelGateway
from quality_inspector.ai_worker import (DOCUMENT_PROMPT_VERSION, PROMPT_VERSION, POLICY_VERSION, _document_request,
                                        MAX_DOCUMENT_INPUT_BYTES, do_documents, documents_job, load_text, report)
from quality_inspector.contract import fingerprint
from quality_inspector.profiles import DELIVERY_DOCUMENT_CHECKS, package_files


REPO=Path(__file__).resolve().parents[3]


class DocumentMaterialsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.dataset=self.root/'candidate';self.dataset.mkdir()
        self.write('README.md','SYNTHETIC complete documentary fixture, not a delivery.')
        self.write('metadata.csv','sample_id,site_id,site_category\nA,S,测试\n')
        self.write('site-list.json',json.dumps({'sites':[{'site_id':'S','uri':'https://fixture.invalid/',
                    'site_category':'测试','sample_ids':['A']}]}))
        self.write('samples/A/annotation.json',json.dumps({'sample_id':'A','task_instruction':'真实内容测试标记'}))
        self.write('ground_truth/A.json',json.dumps({'sample_id':'A','truth':'真实标注测试标记'}))
        self.write('samples/A/ui_tree/step_001.json',json.dumps({'elements':['UI_TREE_BODY_NOT_DOCUMENT_TEXT']}))
        self.write('samples/A/images/step_001.png','ORIGINAL_IMAGE_FIXTURE_BYTES_NOT_IN_PROMPT')
        self.write('qc_report.md','Current payload export; final QC NOT_RUN, not approval.')
        self.write('SHA256SUMS','Current checksum text, not an approval citation.')
        self.config=load_json(REPO/'projects/code/config/batch-synthetic.json')
        self.ledger=BatchLedger(self.root/'ops.sqlite3',self.config,initialize=True)

    def write(self,relative,text):
        path=self.dataset/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);return path

    def report(self):
        return {'baseline':{'config_sha256':'a'*64},'local_profile':{'sha256':'b'*64},
                'payload_files_sha256':{k:v for k,v in package_files(self.dataset).items()
                                        if k not in ('qc_report.md','SHA256SUMS')},
                'dataset_checks':[{'rule_id':'DELIVERY_CATEGORY_SHARE','status':'FAIL','actual':1.0}]}

    def prepare(self,*,supporting=(),report=None,**kwargs):
        formats={'package_errors':[],'samples':[{'sample_id':'A','confirmed_format_pass':True,
                  'errors':[],'total_steps':6,'effective_steps':5}]}
        with patch('quality_inspector.engine.inspect',return_value=report or self.report()),\
                patch('quality_inspector.ai_worker.format_run',return_value=formats):
            return documents_job(self.ledger,self.dataset,REPO/'projects/quality-inspector/quality_inspector/delivery.json',
                                 self.root/'preparation',supporting_files=supporting,**kwargs)

    def test_verified_review_coverage_requires_paired_original_inputs_and_binds_hashes(self):
        reviews=self.root/'actual-reviews.json';reviews.write_text('{"fixture":"review"}')
        plan=self.root/'sampling.json';plan.write_text('{"fixture":"policy"}')
        with self.assertRaisesRegex(ValueError,'supplied together'):
            self.prepare(sample_reviews=reviews)
        evaluated=self.report()
        evaluated.update(semantic_sampling={'actual_ai_reviewed':1,'actual_human_reviewed':0,
            'ai_pending_count':0,'human_pending_count':0,'policy':{'ai_percent':100,'human_percent':0}},
            samples=[{'sample_id':'A','status':'PASS','checks':[{'rule_id':'REVIEW_PRIVACY','status':'PASS'}]}])
        jid=self.prepare(report=evaluated,sample_reviews=reviews,delivery_sampling_plan=plan)
        job=self.ledger.claim('ai-documents',job_id=jid)
        context=job['payload']['supplementary_evidence']['verified_sample_review_state']
        self.assertEqual(context['semantic_sampling'],evaluated['semantic_sampling'])
        self.assertEqual(context['sample_reviews']['sha256'],file_sha(reviews))
        self.assertEqual(context['sampling_plan']['sha256'],file_sha(plan))
        gateway=self.Gateway(self.decision())
        plan.write_text('{"fixture":"tampered policy"}')
        with self.assertRaisesRegex(ValueError,'Supporting documentary evidence changed'):
            do_documents(self.ledger,gateway,job)
        self.assertFalse(gateway.calls)

    def test_inspector_rejects_unbound_review_before_document_job_or_expenditure(self):
        reviews=self.root/'bad-reviews.json';reviews.write_text('{}')
        plan=self.root/'bad-plan.json';plan.write_text('{}')
        with patch('quality_inspector.engine.inspect',side_effect=ValueError('Invalid frozen sampling plan')) as inspector:
            with self.assertRaisesRegex(ValueError,'Invalid frozen'):
                documents_job(self.ledger,self.dataset,'unused',self.root/'out',
                              sample_reviews=reviews,delivery_sampling_plan=plan)
        self.assertEqual(inspector.call_args.kwargs['reviews'],reviews)
        self.assertEqual(inspector.call_args.kwargs['delivery_sampling_plan'],plan)
        self.assertFalse(self.ledger.summary()['jobs'])

    def job(self,**kwargs):
        return self.ledger.claim('ai-documents',job_id=self.prepare(**kwargs))

    def decision(self,status='REVIEW_REQUIRED'):
        return {'checks':{name:{'status':status,'note':'Specific controlled evidence; not actual AI approval.',
                'evidence':[{'path':'site-list.json','sha256':file_sha(self.dataset/'site-list.json'),
                             'detail':'Actual fixture mapping and distribution.'}]} for name in DELIVERY_DOCUMENT_CHECKS}}

    def queue(self):
        path=self.root/'queue.json'
        path.write_text(json.dumps({'dataset':str(self.dataset),'candidate_package_sha256':package_files(self.dataset),
            'contract_sha256':fingerprint()[1],'jobs':[],'sample_count':1,'mechanically_blocked':[],
            'prompt_version':PROMPT_VERSION,'policy_version':POLICY_VERSION}))
        return path

    class Gateway:
        def __init__(self,result):self.result=result;self.calls=[]
        def call(self,job,purpose,text,schema,**kwargs):
            self.calls.append((job,purpose,json.loads(text),schema,kwargs))
            Draft202012Validator(schema).validate(self.result)
            return deepcopy(self.result)

    def test_full_documentary_json_inventory_and_unknown_support_before_one_request(self):
        job=self.job();value=job['payload'];gateway=self.Gateway(self.decision())
        outcome=do_documents(self.ledger,gateway,job)
        self.assertEqual(value['prompt_version'],DOCUMENT_PROMPT_VERSION)
        self.assertEqual(len(gateway.calls),1)
        request=gateway.calls[0][2];context=request['supplementary_evidence']
        for name in ('site-list.json','samples/A/annotation.json','ground_truth/A.json'):
            self.assertEqual(request['documents'][name],(self.dataset/name).read_text())
        self.assertNotIn('UI_TREE_BODY_NOT_DOCUMENT_TEXT',json.dumps(request))
        inventory={r['path']:r for r in context['delivered_file_inventory']}
        self.assertIn('samples/A/ui_tree/step_001.json',inventory)
        self.assertFalse(inventory['samples/A/ui_tree/step_001.json']['content_supplied'])
        self.assertEqual(context['source_attempt_census_status'],'UNKNOWN')
        self.assertEqual(context['supporting_evidence_status'],'NOT_SUPPLIED')
        self.assertEqual(context['review_boundaries']['human_review_status'],'UNKNOWN')
        self.assertEqual(gateway.calls[0][4]['attempts'],1)
        self.assertTrue(all(c['status']=='REVIEW_REQUIRED' for c in outcome['checks'].values()))
        self.assertEqual(self.ledger.summary()['model_requests'],0) # recording gateway, never dispatches

    def test_explicit_supporting_census_keeps_failed_attempts_and_exact_hashes(self):
        manifest=self.root/'actual-manifest.json'
        manifest.write_text(json.dumps({'schema_version':'webcollect-runtime-manifest-m4-1',
            'batch_id':'CONTROLLED','sample_kind':'real','attempts':[{'status':'rejected'},{'status':'collected_pending_review'}],
            'samples':['A'],'collection_status':'finished_pending_review','producer_index_status':'PASS'}))
        facts=self.root/'facts.json';facts.write_text('{"schema_version":"webcollect-production-facts-1","selection":{"total_samples":2,"selected_count":1,"excluded_count":1}}')
        revision=self.root/'revision.json';revision.write_text('{"schema_version":"webcollect-narrative-provenance-1","capture_binding":"NOT_A_CAPTURE_BINDING"}')
        job=self.job(supporting=[manifest,facts,revision]);context=job['payload']['supplementary_evidence']
        self.assertEqual(len(context['supporting_run_files_outside_customer_payload']),3)
        census=context['source_attempt_censuses'][0]
        self.assertEqual(census['observed_attempt_entries'],2)
        self.assertEqual(census['attempt_statuses'],['rejected','collected_pending_review'])
        self.assertEqual(census['source_sha256'],file_sha(manifest))
        self.assertEqual(context['supporting_run_files_outside_customer_payload'][2]['content'],revision.read_text())
        gateway=self.Gateway(self.decision('FAIL'));result=do_documents(self.ledger,gateway,job)
        self.assertTrue(all(c['status']=='FAIL' for c in result['checks'].values()))
        self.assertIn({'rule_id':'DELIVERY_CATEGORY_SHARE','status':'FAIL','actual':1.0},
                      gateway.calls[0][2]['supplementary_evidence']['mechanical_payload_results']['dataset_checks'])

    def test_reference_pair_def_is_shared_and_cannot_cite_report_or_mix_hash(self):
        job=self.job();text,schema=_document_request(job['payload'])
        Draft202012Validator.check_schema(schema)
        self.assertIn('payload_reference',schema['$defs'])
        for check in schema['properties']['checks']['properties'].values():
            self.assertEqual(check['properties']['evidence']['items'],{'$ref':'#/$defs/payload_reference'})
        self.assertEqual(len(schema['$defs']['payload_reference']['oneOf']),len(job['payload']['payload_files_sha256']))
        for path,checksum in [('qc_report.md',file_sha(self.dataset/'qc_report.md')),
                              ('SHA256SUMS',file_sha(self.dataset/'SHA256SUMS')),
                              ('site-list.json',file_sha(self.dataset/'README.md'))]:
            bad=self.decision();bad['checks'][DELIVERY_DOCUMENT_CHECKS[0]]['evidence'][0].update(path=path,sha256=checksum)
            with self.subTest(path=path),self.assertRaises(ValidationError):Draft202012Validator(schema).validate(bad)
        Draft202012Validator(schema).validate(self.decision())

    def test_oversize_full_input_blocks_before_job_or_model_reservation(self):
        self.ledger.config['model']['reserve_input_tokens']=1000
        with self.assertRaisesRegex(ValueError,'Complete documentary materials exceed'):
            self.prepare()
        self.assertEqual(self.ledger.summary()['jobs'],[])
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_changed_export_artifact_or_supporting_file_blocks_before_gateway(self):
        supporting=self.root/'facts.json';supporting.write_text('{"actual":"one"}')
        job=self.job(supporting=[supporting]);gateway=self.Gateway(self.decision())
        supporting.write_text('{"actual":"changed"}')
        with self.assertRaisesRegex(ValueError,'Supporting documentary evidence changed'):
            do_documents(self.ledger,gateway,job)
        self.assertFalse(gateway.calls)
        supporting.write_text('{"actual":"one"}')
        self.write('qc_report.md','Changed stub')
        with self.assertRaisesRegex(ValueError,'corroborating export artifacts changed'):
            do_documents(self.ledger,gateway,job)
        self.assertFalse(gateway.calls)

    def test_material_change_versions_job_and_no_old_input_is_executed(self):
        first=self.prepare();self.write('site-list.json','{"sites":[],"version":2}')
        second=self.prepare();self.assertNotEqual(first,second)
        old=self.ledger.claim('ai-documents',job_id=first);gateway=self.Gateway(self.decision())
        with self.assertRaisesRegex(ValueError,'Document payload changed'):do_documents(self.ledger,gateway,old)
        old['payload']['prompt_version']='independent-all-frame-review-1'
        with self.assertRaisesRegex(ValueError,'Legacy documentary input'):do_documents(self.ledger,gateway,old)
        self.assertFalse(gateway.calls)

    def test_single_document_byte_limit_and_in_package_support_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside the customer payload'):
            self.prepare(supporting=[self.dataset/'site-list.json'])
        self.write('oversize.json',json.dumps({'value':'X'*MAX_DOCUMENT_INPUT_BYTES}))
        with self.assertRaisesRegex(ValueError,'4 MiB input-file safety limit'):self.prepare()
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_320820_byte_document_enters_complete_document_job_without_truncation(self):
        prefix='真实路径尺寸回归夹具：保留完整资料，不代表模型审批。\n'
        material=prefix+'A'*(320820-len(prefix.encode()))
        path=self.write('合成方式说明.md',material)
        self.assertEqual(path.stat().st_size,320820)
        self.ledger.config['model']['reserve_input_tokens']=1000000
        jid=self.prepare();payload=self.ledger.get(jid)['payload']
        self.assertEqual(payload['documents']['合成方式说明.md'],material)
        text,_=_document_request(payload)
        self.assertEqual(json.loads(text)['documents']['合成方式说明.md'],material)
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_file_safety_boundary_reads_whole_accepted_file_and_rejects_extra_byte(self):
        path=self.write('boundary.md','A'*MAX_DOCUMENT_INPUT_BYTES)
        self.assertEqual(len(load_text(path)),MAX_DOCUMENT_INPUT_BYTES)
        with path.open('ab') as stream:stream.write(b'B')
        with self.assertRaisesRegex(ValueError,'4 MiB input-file safety limit'):load_text(path)

    def test_full_accepted_file_still_blocks_model_budget_before_job_or_network(self):
        self.write('合成方式说明.md','A'*320820)
        self.ledger.config['model']['reserve_input_tokens']=100000
        with patch('urllib.request.build_opener',side_effect=AssertionError('No external request allowed')) as network:
            with self.assertRaisesRegex(ValueError,'Complete documentary materials exceed'):
                self.prepare()
        network.assert_not_called()
        self.assertEqual(self.ledger.summary()['jobs'],[])
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_mid_request_payload_drift_is_not_signed_as_completed_review(self):
        job=self.job();parent=self
        class ChangingGateway(self.Gateway):
            def call(inner,*args,**kwargs):
                result=super().call(*args,**kwargs)
                parent.write('metadata.csv','changed after dispatch')
                return result
        gateway=ChangingGateway(self.decision('PASS'))
        with self.assertRaisesRegex(ValueError,'Document payload changed'):
            do_documents(self.ledger,gateway,job)
        self.assertEqual(len(gateway.calls),1)

    def test_single_synthetic_gateway_request_and_exact_result_cache_reuse(self):
        job=self.job();gateway=ModelGateway(self.ledger)
        first=do_documents(self.ledger,gateway,job)
        second=do_documents(self.ledger,gateway,job)
        self.assertEqual(first,second)
        self.assertEqual(self.ledger.summary()['model_requests'],1)
        self.assertEqual(first['reviewer']['kind'],'synthetic')
        self.assertTrue(all(c['status']=='REVIEW_REQUIRED' for c in first['checks'].values()))

    def test_report_rejects_completed_legacy_or_wrong_kind_document_job(self):
        queue=self.queue()
        for kind,payload in [('ai-documents',{'dataset':str(self.dataset),'prompt_version':'independent-all-frame-review-1'}),
                             ('ai-visual',{'dataset':str(self.dataset)})]:
            jid=self.ledger.enqueue(kind,payload);job=self.ledger.claim(kind,job_id=jid)
            self.ledger.finish(job,result={'legacy':'a readable historical result, not v2 evidence'})
            output=self.root/('reject-'+kind)
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'Legacy documentary|wrong kind'):
                report(self.ledger,queue,output,document_job=jid)
            self.assertFalse(output.exists())
            self.assertEqual(self.ledger.get(jid)['result']['legacy'],'a readable historical result, not v2 evidence')

    def test_report_exports_current_v2_but_rejects_stale_supporting_proof(self):
        supporting=self.root/'facts.json';supporting.write_text('{"actual":"one"}')
        job=self.job(supporting=[supporting]);result=do_documents(self.ledger,ModelGateway(self.ledger),job)
        self.ledger.finish(job,result=result);queue=self.queue()
        first=report(self.ledger,queue,self.root/'current-report',document_job=job['id'])
        exported=load_json(first['review_file'])
        self.assertEqual(exported['delivery_document_review'],result)
        self.assertEqual(first['actual_ai_reviewed'],0)
        supporting.write_text('{"actual":"changed"}')
        with self.assertRaisesRegex(ValueError,'Supporting documentary evidence changed'):
            report(self.ledger,queue,self.root/'stale-report',document_job=job['id'])
        self.assertFalse((self.root/'stale-report').exists())

    def test_report_rejects_result_binding_or_provenance_tampering(self):
        job=self.job();result=do_documents(self.ledger,ModelGateway(self.ledger),job)
        self.ledger.finish(job,result=result);stored=self.ledger.get(job['id']);queue=self.queue()
        for key in ('payload_files_sha256','provenance'):
            changed=deepcopy(stored);changed['result'][key]={}
            output=self.root/('bad-result-'+key)
            with self.subTest(key=key),patch.object(self.ledger,'get',return_value=changed),\
                    self.assertRaisesRegex(ValueError,'payload binding|material provenance'):
                report(self.ledger,queue,output,document_job=job['id'])
            self.assertFalse(output.exists())
        self.assertEqual(self.ledger.get(job['id'])['result'],result)


if __name__=='__main__':unittest.main()
