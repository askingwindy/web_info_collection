"""Delivery contract probes use independently written synthetic fixtures only."""
import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_customer_layout import fixture, put
from quality_inspector import engine
from quality_inspector.__main__ import main
from quality_inspector.checksums import write_manifest
from quality_inspector.profiles import DEFAULT_DELIVERY_PROFILE, load
from quality_inspector.reporting import review_template, write_outputs


class DeliveryContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source,self.client,_=fixture(self.root)
        # The contract fixture is literal; no producer/schema helper authors it.
        (self.client/'合成方式说明.md').write_text('## test_agent\nagent unified_gui_v4\n## 动作映射\n按附件B动作参数。\n## 坐标\n截图像素整数。\n## 界面变化判定\n比较相邻截图与实际输入结果。\n## 文字字段生成方式\n独立测试人工字面夹具，未使用模型，无模型提示词。\n')
        (self.client/'来源与合规说明.md').write_text('## 采集方式\n独立离线测试夹具。\n## 访问频率策略\n不联网。\n## 账号与脱敏\n无账号或真实个人信息。\n## 站点清单\n见site-list.json。\n')
        self.profile=self.root/'delivery-profile.json'
        value=json.loads(DEFAULT_DELIVERY_PROFILE.read_text())
        value['profile_id']='SYNTHETIC-DELIVERY-TEST';value['authority']='Synthetic test with an explicit one-case category exception; never a production waiver.'
        value['targets'].update(expected_samples=1,category_share='report-only')
        put(self.profile,value);self.seal()

    def tearDown(self):self.temp.cleanup()

    def seal(self):
        manifest=self.client/'SHA256SUMS'
        if manifest.exists():manifest.unlink()
        write_manifest(self.client)

    def report(self,**kwargs):return engine.inspect(None,self.client,profile=self.profile,inspection_stage='payload',**kwargs)

    def reviewed(self):
        value=review_template(self.report());value.pop('package_review',None)
        for row in value['records']:
            row['reviewer']={'kind':'ai','name':'SYNTHETIC TEST ONLY'}
            steps=[step['step_id'] for step in json.loads((self.client/'samples'/row['sample_id']/'annotation.json').read_text())['steps']]
            row['provenance']={'description':'Tests binding and aggregation only; not actual production visual acceptance.','frames_viewed':steps}
            row['step_observations']=[{'step_id':step,'note':'Explicit synthetic observation for fixture step '+str(step)} for step in steps]
            row['checks']={name:{'status':'PASS','note':'Synthetic fixture expectation only.','evidence_steps':steps} for name in engine.SEMANTIC}
        document=value['delivery_document_review']
        document['reviewer']={'kind':'ai','name':'SYNTHETIC DOCUMENT TEST ONLY'}
        document['provenance']={'description':'Explicit synthetic fixture for binding and gate tests; no real production document approval.'}
        for result in document['checks'].values():
            result.update(status='PASS',note='Synthetic independently defined document expectation only.',
                evidence=[{'path':'README.md','sha256':document['payload_files_sha256']['README.md'],
                           'detail':'Synthetic fixture evidence only, not a claim of reading a real customer package.'}])
        path=self.root/'reviews.json';put(path,value);return path

    def mutate(self,operation):
        annotation=next(self.client.glob('samples/*/annotation.json'));value=json.loads(annotation.read_text());operation(value);put(annotation,value);self.seal()

    def test_delivery_needs_no_reference_samples_or_capture_archives(self):
        reviews=self.reviewed();shutil.rmtree(self.source.parent)
        with patch.object(engine,'baseline_load',side_effect=AssertionError('No reference reads allowed')):
            result=self.report(reviews=reviews)
        self.assertEqual(result['delivery_status'],'PASS')
        self.assertEqual(result['external_evidence']['status'],'NOT_REQUIRED_FOR_DELIVERY')
        self.assertNotIn('CAPTURE_INTEGRITY',{c['rule_id'] for c in result['samples'][0]['checks']})
        self.assertEqual(result['acceptance_scopes']['pilot']['status'],'NOT_APPLICABLE')

    def test_missing_optional_engineering_inputs_do_not_change_contract(self):
        reviews=self.reviewed();before=self.report(reviews=reviews)
        after=engine.inspect(self.root/'missing-baseline.json',self.client,profile=self.profile,reviews=reviews,evidence=self.root/'missing-capture.json',inspection_stage='payload')
        self.assertEqual(before['delivery_status'],after['delivery_status'])
        self.assertEqual(after['engineering_audit']['baseline']['status'],'FAIL')
        self.assertEqual(after['engineering_audit']['capture']['status'],'FAIL')

    def test_legacy_relocation_requires_the_exact_pinned_bytes(self):
        reference=self.root/'authority';moved=reference/'request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md'
        moved.parent.mkdir(parents=True);moved.write_text('独立搬迁测试原文\n')
        configuration={'repository_root':str(reference),'samples':[],
            'supplemental_documents':[{'path':'request/需求书-Web浏览器自动化操作轨迹数据集.md','sha256':engine.sha(moved)}],'known_limits':[]}
        path=self.root/'legacy.json';put(path,configuration)
        result=engine.baseline_load(path)
        self.assertEqual(result['integrity'],'PASS');self.assertEqual(result['authority_relocations'][0]['resolved_path'],str(moved.resolve()))
        moved.write_text('发生真实改动，不能当成相同的搬迁原件\n')
        self.assertEqual(engine.baseline_load(path)['integrity'],'FAIL')
        moved.unlink();other=reference/'elsewhere/需求书-Web浏览器自动化操作轨迹数据集.md';other.parent.mkdir();other.write_text('独立搬迁测试原文\n')
        self.assertEqual(engine.baseline_load(path)['integrity'],'FAIL')

    def test_default_cli_accepts_only_input_and_output_arguments(self):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            result=main(['check','--input',str(self.client),'--output',str(self.root/'cli')])
        self.assertIn(result,(1,2))  # one category and absent actual semantic review
        report=json.loads((self.root/'cli/report.json').read_text())
        self.assertEqual(report['scope'],'delivery');self.assertEqual(report['engineering_audit']['baseline']['status'],'NOT_REQUESTED')

    def test_profile_exception_is_batch_specific_and_default_category_still_fails(self):
        result=self.report(reviews=self.reviewed())
        self.assertEqual(result['delivery_status'],'PASS')
        self.assertEqual(result['statistics']['category_share_policy'],'report-only')
        generic=engine.inspect(None,self.client,reviews=self.reviewed())
        self.assertTrue(any(c['rule_id']=='DELIVERY_CATEGORY_SHARE' and c['status']=='FAIL' for c in generic['dataset_checks']))
        approved=load(Path(__file__).parents[1]/'config/delivery-approved18-20261024.json')
        self.assertEqual(approved['configuration']['targets']['expected_samples'],18)
        self.assertEqual(approved['configuration']['targets']['category_share'],'report-only')

    def test_exact_sample_count_is_enforced_without_a_pilot_minimum(self):
        value=json.loads(self.profile.read_text());value['targets']['expected_samples']=18;put(self.profile,value)
        result=self.report()
        self.assertTrue(any(c['rule_id']=='DELIVERY_EXPECTED_SAMPLES' and c['status']=='FAIL' for c in result['dataset_checks']))
        self.assertFalse(any('PILOT_MINIMUM' in c['rule_id'] for c in result['dataset_checks']))

    def test_real200_profile_enforces_ten_sites_and_keeps_category_limit(self):
        configured=load(Path(__file__).parents[1]/'config/delivery-200-10sites-20261024.json')['configuration']
        self.assertEqual(configured['scope'],'delivery')
        self.assertEqual(configured['targets']['expected_samples'],200)
        self.assertEqual(configured['targets']['expected_sites'],10)
        self.assertEqual(configured['targets']['category_share'],'enforced')
        self.assertEqual(configured['targets']['max_category_share'],0.2)
        value=json.loads(self.profile.read_text());value['targets']['expected_sites']=10;put(self.profile,value)
        result=self.report(reviews=self.reviewed())
        self.assertTrue(any(c['rule_id']=='DELIVERY_EXPECTED_SITES' and c['status']=='FAIL' for c in result['dataset_checks']))
        self.assertEqual(result['delivery_scope']['expected_sites'],10)
        value['targets']['expected_sites']=1;put(self.profile,value)
        self.assertEqual(self.report(reviews=self.reviewed())['delivery_status'],'PASS')

    def test_expected_site_target_cannot_be_zero_boolean_or_fractional(self):
        original=json.loads(self.profile.read_text())
        for target in (0,-1,True,1.5):
            with self.subTest(target=target):
                value=json.loads(json.dumps(original));value['targets']['expected_sites']=target;put(self.profile,value)
                with self.assertRaises(ValueError):load(self.profile)

    def test_new_report_rule_sources_reference_the_current_requirement_path(self):
        report=self.report()
        sources=[value for row in report['rules'] for value in row.get('sources',[])]
        self.assertTrue(any('request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md' in value for value in sources))
        self.assertFalse(any('request/需求书-Web浏览器自动化操作轨迹数据集.md' in value for value in sources))
        traceability=json.loads((Path(__file__).parents[1]/'config/requirements-baseline-v1.json').read_text())
        self.assertEqual(traceability['source_documents'][0]['path'],'request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md')

    def test_semantics_stay_pending_without_actual_review_and_ai_stays_ai(self):
        result=self.report();self.assertEqual(result['samples'][0]['status'],'REVIEW_REQUIRED')
        accepted=self.report(reviews=self.reviewed())
        checks=[c for c in accepted['samples'][0]['checks'] if c['rule_id'].startswith('REVIEW_')]
        self.assertTrue(all(c['reviewer']['kind']=='ai' for c in checks))
        self.assertEqual(accepted['customer_actual_acceptance'],'UNKNOWN')

    def test_missing_or_empty_final_image_is_rejected(self):
        for value in (None,''):
            with self.subTest(value=value):
                self.mutate(lambda a: a.pop('final_state_image',None) if value is None else a.update(final_state_image=value))
                result=self.report(reviews=self.reviewed())
                self.assertTrue(any(c['rule_id']=='C10' and c['status']=='FAIL' for c in result['samples'][0]['checks']))

    def test_failure_states_missing_complete_and_generic_terminal_goal_are_rejected(self):
        original=next(self.client.glob('samples/*/annotation.json')).read_text()
        probes=[lambda a:a.update(completion_status='failed'),
                lambda a:a['steps'][0]['tool_result'].update(status='error'),
                lambda a:a['steps'][-1]['tool_call']['arguments'].update(status='infeasible'),
                lambda a:a['steps'][-1].update(user_goal='确认最终页面符合任务要求'),
                lambda a:(a['steps'][-1]['action'].update(action_type='wait'),a['steps'][-1]['tool_call'].update(tool_name='wait',arguments={}))]
        for number,probe in enumerate(probes):
            with self.subTest(probe=number):
                next(self.client.glob('samples/*/annotation.json')).write_text(original);self.mutate(probe)
                result=self.report(reviews=self.reviewed())
                self.assertTrue(any(c['rule_id']=='C10' and c['status']=='FAIL' for c in result['samples'][0]['checks']))

    def test_document_placeholders_fail_even_with_sample_semantics_pass(self):
        (self.client/'来源与合规说明.md').write_text('采集方式、访问频率策略、账号与脱敏、站点清单：UNKNOWN。');self.seal()
        result=self.report(reviews=self.reviewed())
        self.assertEqual(result['local_sample_status_counts'],{'PASS':1})
        self.assertEqual(result['delivery_status'],'FAIL')
        self.assertTrue(any(c['rule_id']=='DELIVERY_DOCUMENT_CONTENT' and c['status']=='FAIL' for c in result['dataset_checks']))

    def test_selection_population_is_read_from_delivered_documents(self):
        population={'total_samples':3,'selected_count':1,'excluded_count':2,'excluded_samples':[{'sample_id':'excluded1','reason':'failed actual review'},{'sample_id':'excluded2','reason':'pending actual review'}]}
        with (self.client/'来源与合规说明.md').open('a') as stream:stream.write('\n```json\n'+json.dumps(population)+'\n```\n')
        self.seal();result=self.report(reviews=self.reviewed())
        self.assertEqual(result['statistics']['source_population'],population)
        self.assertEqual(result['delivery_status'],'PASS')

    def test_report_contains_finalize_bindings_and_writes_without_touching_input(self):
        result=self.report(reviews=self.reviewed());before=result['input_files_sha256']
        write_outputs(result,self.root/'report')
        self.assertEqual(before,engine._inspect_delivery(self.client,load(self.profile))['input_files_sha256'])
        self.assertTrue(all(key in result for key in ('program','dataset','input_files_sha256','samples','duplicates','root_checksum','delivery_status')))
        self.assertEqual(result['samples'][0]['annotation_sha256'],result['input_files_sha256']['samples/'+result['samples'][0]['sample_id']+'/annotation.json'])

    def final_summary(self):
        reviews=self.reviewed();result=self.report(reviews=reviews)
        self.assertEqual(result['delivery_status'],'PASS')
        summary={'payload_sha256':result['payload_sha256'],'payload_files_sha256':result['payload_files_sha256'],
                 'distribution':{key:result['statistics'][key] for key in ('sample_count','site_count','categories','task_types','step_counts')},
                 'review_coverage':{'human_complete_samples':0,'ai_complete_samples':1,'pending_or_missing_samples':0,'samples_in_this_output':1,
                                    'reviewer_sources':[{'kind':'ai','name':'SYNTHETIC TEST ONLY','samples':1}]},
                 'delivery_document_review':result['delivery_document_review'],
                 'four_route_duplicates':{'pair_comparisons':0,'route1':0,'route2':0,'route3':0,'route4':0,
                     'resolution':{key:value for key,value in result['duplicates']['summary'].items()
                                   if key not in ('pair_adjudications','current_sample_ids','affected_current_sample_ids')}},
                 'original_source_population':{'status':'NOT_DECLARED'},'delivery_scope':result['delivery_scope']}
        rows='\n'.join(f'| {number} | 独立测试要求 | PASS | 测试绑定 |' for number in range(1,18))
        (self.client/'qc_report.md').write_text('# 合成测试自检报告\n'+rows+'\n```json\n'+json.dumps(summary,ensure_ascii=False)+'\n```\n')
        self.seal();return reviews,summary

    def test_final_stage_requires_full_bound_qc_summary_and_payload_is_not_release_ready(self):
        payload=self.report(reviews=self.reviewed());self.assertFalse(payload['release_ready'])
        initial=engine.inspect(None,self.client,profile=self.profile,reviews=self.reviewed())
        self.assertEqual(initial['inspection_stage'],'final');self.assertFalse(initial['release_ready'])
        self.assertTrue(any(c['rule_id']=='DELIVERY_QC_REPORT' and c['status']=='FAIL' for c in initial['dataset_checks']))
        reviews,_=self.final_summary()
        final=engine.inspect(None,self.client,profile=self.profile,reviews=reviews)
        self.assertEqual(final['delivery_status'],'PASS');self.assertTrue(final['release_ready'])

    def test_qc_summary_cannot_claim_human_review_for_ai_decisions(self):
        reviews,_=self.final_summary()
        path=self.client/'qc_report.md';value=path.read_text().replace('"human_complete_samples": 0','"human_complete_samples": 1');path.write_text(value);self.seal()
        final=engine.inspect(None,self.client,profile=self.profile,reviews=reviews)
        self.assertEqual(final['delivery_status'],'FAIL')
        self.assertTrue(any('human_complete_samples' in c['reason'] for c in final['dataset_checks'] if c['rule_id']=='DELIVERY_QC_REPORT'))

    def test_final_summary_cannot_change_duplicate_rates_pending_count_or_current_denominator(self):
        reviews,summary=self.final_summary();path=self.client/'qc_report.md'
        prefix=path.read_text().split('```json',1)[0]
        for key,value in (('near_duplicate_sample_rate',0.5),('unadjudicated_pair_count',1),('current_sample_count',225)):
            changed=copy.deepcopy(summary);changed['four_route_duplicates']['resolution'][key]=value
            path.write_text(prefix+'```json\n'+json.dumps(changed,ensure_ascii=False)+'\n```\n');self.seal()
            with self.subTest(key=key):
                final=engine.inspect(None,self.client,profile=self.profile,reviews=reviews)
                self.assertEqual(final['delivery_status'],'FAIL')
                self.assertTrue(any('union/rates/unadjudicated' in check['reason']
                                    for check in final['dataset_checks'] if check['rule_id']=='DELIVERY_QC_REPORT'))

    def test_qc_summary_cannot_survive_a_resealed_payload_change(self):
        reviews,_=self.final_summary()
        with (self.client/'README.md').open('a') as stream:stream.write('更改后的说明\n')
        self.seal();final=engine.inspect(None,self.client,profile=self.profile,reviews=reviews)
        self.assertEqual(final['root_checksum']['pass'],True)
        self.assertEqual(final['delivery_status'],'FAIL')
        self.assertTrue(any('payload_sha256' in c['reason'] for c in final['dataset_checks'] if c['rule_id']=='DELIVERY_QC_REPORT'))

    def test_delivery_document_template_is_pending_and_binds_all_payload(self):
        report=self.report();record=review_template(report)['delivery_document_review']
        self.assertEqual(record['payload_files_sha256'],report['payload_files_sha256'])
        self.assertNotIn('qc_report.md',record['payload_files_sha256'])
        self.assertNotIn('SHA256SUMS',record['payload_files_sha256'])
        self.assertIn('metadata.csv',record['payload_files_sha256'])
        self.assertTrue(all(row=={'status':'REVIEW_REQUIRED','note':'','evidence':[]} for row in record['checks'].values()))

    def test_sample_pass_without_actual_document_review_cannot_release(self):
        path=self.reviewed();value=json.loads(path.read_text());del value['delivery_document_review'];put(path,value)
        result=self.report(reviews=path)
        self.assertEqual(result['sample_status_counts'],{'PASS':1})
        self.assertEqual(result['delivery_document_review']['status'],'REVIEW_REQUIRED')
        self.assertEqual(result['delivery_status'],'REVIEW_REQUIRED');self.assertFalse(result['release_ready'])
        value['package_review']={'status':'PASS'};put(path,value)
        self.assertEqual(self.report(reviews=path)['delivery_document_review']['status'],'REVIEW_REQUIRED')

    def test_document_binding_cannot_drop_or_change_any_required_fingerprint(self):
        path=self.reviewed();original=json.loads(path.read_text())
        mutations=[lambda d:d.update(schema_version='other'),lambda d:d.update(baseline_sha256='0'*64),
                   lambda d:d.update(profile_sha256='0'*64),lambda d:d['payload_files_sha256'].pop('metadata.csv'),
                   lambda d:d['payload_files_sha256'].update({'README.md':'0'*64})]
        for mutate in mutations:
            value=copy.deepcopy(original);mutate(value['delivery_document_review']);put(path,value)
            with self.subTest(value=value['delivery_document_review']['schema_version']):
                self.assertEqual(self.report(reviews=path)['delivery_document_review']['status'],'FAIL')

    def test_document_review_needs_identity_provenance_and_all_five_checks(self):
        path=self.reviewed();original=json.loads(path.read_text())
        mutations=[lambda d:d.update(reviewer={'kind':'ai','name':''}),lambda d:d.update(reviewer={'kind':'robot','name':'test'}),
                   lambda d:d.update(provenance={'description':''}),lambda d:d['checks'].pop('source_and_compliance'),
                   lambda d:d.update(checks=[])]
        for number,mutate in enumerate(mutations):
            value=copy.deepcopy(original);mutate(value['delivery_document_review']);put(path,value)
            with self.subTest(probe=number):self.assertEqual(self.report(reviews=path)['delivery_document_review']['status'],'FAIL')

    def test_document_pass_needs_specific_note_and_actual_file_evidence(self):
        path=self.reviewed();original=json.loads(path.read_text())
        mutations=[lambda c:c.update(note=''),lambda c:c.update(evidence=[]),
                   lambda c:c['evidence'][0].update(detail=''),lambda c:c['evidence'][0].update(sha256='0'*64),
                   lambda c:c['evidence'][0].update(path='../README.md'),lambda c:c['evidence'][0].update(path='/README.md'),
                   lambda c:c['evidence'][0].update(path='qc_report.md'),lambda c:c['evidence'][0].update(path='SHA256SUMS'),
                   lambda c:c['evidence'][0].update(path='./README.md'),lambda c:c.update(evidence=['README.md'])]
        for number,mutate in enumerate(mutations):
            value=copy.deepcopy(original);mutate(value['delivery_document_review']['checks']['source_and_compliance']);put(path,value)
            with self.subTest(probe=number):self.assertEqual(self.report(reviews=path)['delivery_document_review']['status'],'FAIL')

    def test_document_failure_or_pending_aggregates_without_changing_sample_decisions(self):
        path=self.reviewed();original=json.loads(path.read_text())
        for status in ('FAIL','REVIEW_REQUIRED'):
            value=copy.deepcopy(original);value['delivery_document_review']['checks']['source_and_compliance']['status']=status;put(path,value)
            result=self.report(reviews=path)
            self.assertEqual(result['sample_status_counts'],{'PASS':1})
            self.assertEqual(result['delivery_status'],status)
            self.assertEqual(result['acceptance_scopes']['batch']['status'],status)
            self.assertEqual(result['package_review']['status'],status)
            self.assertTrue(any(c['rule_id']=='DELIVERY_DOCUMENT_REVIEW' and c['status']==status for c in result['dataset_checks']))

    def test_resealed_metadata_change_invalidates_actual_document_review(self):
        path=self.reviewed();metadata=self.client/'metadata.csv';metadata.write_text(metadata.read_text()+'\n');self.seal()
        result=self.report(reviews=path)
        self.assertEqual(result['sample_status_counts'],{'PASS':1})
        self.assertTrue(result['root_checksum']['pass'])
        self.assertEqual(result['delivery_document_review']['status'],'FAIL')
        self.assertIn('missing/stale/different payload_files_sha256',result['delivery_document_review']['errors'])

    def test_same_actual_document_record_survives_final_report_and_checksum_only(self):
        path,_=self.final_summary();before=path.read_bytes()
        final=engine.inspect(None,self.client,profile=self.profile,reviews=path)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(final['delivery_document_review']['status'],'PASS')
        self.assertEqual(final['delivery_status'],'PASS');self.assertTrue(final['release_ready'])
        self.assertEqual(final['delivery_document_review']['reviewer']['kind'],'ai')

    def test_payload_document_record_is_portable_to_isolated_customer_directory(self):
        path=self.reviewed();isolated=self.root/'isolated/client';shutil.copytree(self.client,isolated)
        result=engine.inspect(None,isolated,profile=self.profile,reviews=path,inspection_stage='payload')
        self.assertEqual(result['delivery_document_review']['status'],'PASS')
        self.assertEqual(result['delivery_status'],'PASS')

    def test_final_summary_cannot_invent_a_different_actual_reviewer(self):
        path,_=self.final_summary();report=self.client/'qc_report.md'
        report.write_text(report.read_text().replace('"name": "SYNTHETIC TEST ONLY"','"name": "invented reviewer"'));self.seal()
        result=engine.inspect(None,self.client,profile=self.profile,reviews=path)
        self.assertEqual(result['delivery_document_review']['status'],'PASS')
        self.assertEqual(result['delivery_status'],'FAIL')
        self.assertTrue(any('reviewer_sources' in c['reason'] for c in result['dataset_checks'] if c['rule_id']=='DELIVERY_QC_REPORT'))

    def test_final_summary_must_preserve_actual_documentary_conclusion_and_evidence(self):
        path,original=self.final_summary();report=self.client/'qc_report.md';prefix=report.read_text().split('```json')[0]
        mutations=[lambda d:d['checks']['source_and_compliance'].update(status='FAIL'),
                   lambda d:d['checks']['source_and_compliance'].update(note='invented new reading'),
                   lambda d:d['reviewer'].update(name='invented document reviewer'),
                   lambda d:d['checks']['source_and_compliance']['evidence'][0].update(sha256='0'*64)]
        for number,mutate in enumerate(mutations):
            summary=copy.deepcopy(original);mutate(summary['delivery_document_review'])
            report.write_text(prefix+'```json\n'+json.dumps(summary,ensure_ascii=False)+'\n```\n');self.seal()
            result=engine.inspect(None,self.client,profile=self.profile,reviews=path)
            with self.subTest(probe=number):
                self.assertEqual(result['delivery_document_review']['status'],'PASS')
                self.assertEqual(result['delivery_status'],'FAIL')
                self.assertTrue(any('delivery_document_review' in c['reason'] for c in result['dataset_checks'] if c['rule_id']=='DELIVERY_QC_REPORT'))


if __name__=='__main__':unittest.main()
