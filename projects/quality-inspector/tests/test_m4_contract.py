"""M4 negative gates, synthetic observations only; never actual review signatures."""
import copy
import json
import unittest
from unittest.mock import patch

import test_delivery
from quality_inspector import contract
from quality_inspector.format_checks import prohibited_narrative
from quality_inspector.reviews import migration_template, record_hash


class M4ContractTests(unittest.TestCase):
    setUp=test_delivery.DeliveryContractTests.setUp
    tearDown=test_delivery.DeliveryContractTests.tearDown
    seal=test_delivery.DeliveryContractTests.seal
    report=test_delivery.DeliveryContractTests.report
    reviewed=test_delivery.DeliveryContractTests.reviewed
    mutate=test_delivery.DeliveryContractTests.mutate

    def rejected_review(self, operation):
        path=self.reviewed(); value=json.loads(path.read_text()); operation(value['records'][0]);path.write_text(json.dumps(value))
        report=self.report(reviews=path)
        self.assertEqual(report['review_import']['accepted_count'],0)
        self.assertFalse(report['release_ready'])
        self.assertTrue(report['review_import']['invalid_records'])
        return report

    def test_missing_frame_observations_rejected(self):
        self.rejected_review(lambda row:row.pop('step_observations'))

    def test_duplicate_frame_does_not_replace_missing_observation(self):
        self.rejected_review(lambda row:row['step_observations'].__setitem__(1,copy.deepcopy(row['step_observations'][0])))

    def test_duplicate_viewed_ids_rejected(self):
        self.rejected_review(lambda row:row['provenance']['frames_viewed'].__setitem__(1,1))

    def test_missing_one_of_five_checks_rejected(self):
        self.rejected_review(lambda row:row['checks'].pop('privacy'))

    def test_unknown_semantic_frame_reference_rejected(self):
        self.rejected_review(lambda row:row['checks']['language'].update(evidence_steps=[999]))

    def test_new_unbound_observation_reference_rejected(self):
        self.rejected_review(lambda row:row['step_observations'][0].update(evidence=[{'path':'images/unknown.png','sha256':'a'*64}]))

    def test_changed_observation_reference_hash_rejected(self):
        self.rejected_review(lambda row:row['step_observations'][0].update(evidence=[{'path':'images/step_001.png','sha256':'a'*64}]))

    def test_observation_cannot_cite_other_steps_bound_image(self):
        self.rejected_review(lambda row:row['step_observations'][0].update(evidence=[{'path':'images/step_002.png','sha256':row['evidence_sha256']['images/step_002.png']}]))

    def test_malformed_review_sample_id_is_rejected_without_crash(self):
        self.rejected_review(lambda row:row.update(sample_id={'invalid':'object'}))

    def test_pending_or_missing_review_never_releases(self):
        result=self.report()
        self.assertEqual(result['local_sample_status'],'REVIEW_REQUIRED')
        self.assertFalse(result['release_ready'])

    def legacy(self):
        path=self.reviewed(); value=json.loads(path.read_text());value['schema_version']='qc-review-1'
        value['records'][0]['baseline_sha256']='0'*64
        for check in value['records'][0]['checks'].values():check.pop('evidence_steps')
        path.write_text(json.dumps(value));return path,value

    def migration(self,path,complete=False):
        report=self.report();value=migration_template(path,report['samples'],report['baseline']['config_sha256'])
        if complete:
            for item in value['decisions']:
                item.update(decision='inherit_unchanged',reason='SYNTHETIC migration test, unchanged fixture bytes only.',
                            authority_and_semantic_rule_assessment='SYNTHETIC assessment only, not approval of real data.',
                            assessor={'kind':'ai','name':'SYNTHETIC IMPACT TEST ONLY'})
        destination=self.root/'migration.json';destination.write_text(json.dumps(value));return destination,value

    def test_migration_template_never_signs_eligibility_facts(self):
        path,_=self.legacy();migration,value=self.migration(path)
        self.assertTrue(value['decisions'][0]['eligibility']['annotation_unchanged'])
        self.assertEqual(value['decisions'][0]['decision'],'REVIEW_REQUIRED')
        report=self.report(reviews=path,review_migration=migration)
        self.assertEqual(report['review_import']['accepted_count'],0)

    def test_legacy_without_migration_not_silently_rebound(self):
        path,_=self.legacy();before=path.read_bytes();report=self.report(reviews=path)
        self.assertEqual(report['review_import']['accepted_count'],0);self.assertEqual(path.read_bytes(),before)

    def test_explicit_synthetic_migration_preserves_original_record_and_identity(self):
        path,value=self.legacy();before=path.read_bytes();migration,_=self.migration(path,True)
        report=self.report(reviews=path,review_migration=migration)
        self.assertEqual(report['review_import']['accepted_count'],1)
        self.assertEqual(path.read_bytes(),before)
        migrated=report['review_import']['migrated_records'][0]
        self.assertEqual(migrated['source_record_sha256'],record_hash(value['records'][0]))
        self.assertFalse(migrated['new_visual_review_claimed'])
        self.assertFalse(report['review_import']['identity_authenticated'])
        self.assertTrue(all(check['reviewer']['kind']=='ai' for check in report['samples'][0]['checks'] if check['rule_id'].startswith('REVIEW_')))

    def test_changed_annotation_cannot_inherit_even_completed_migration(self):
        path,_=self.legacy();migration,_=self.migration(path,True)
        self.mutate(lambda annotation:annotation.update(final_result='实际变更后的说明'))
        self.assertEqual(self.report(reviews=path,review_migration=migration)['review_import']['accepted_count'],0)

    def test_changed_source_review_cannot_reuse_migration(self):
        path,value=self.legacy();migration,_=self.migration(path,True)
        value['records'][0]['reviewer']['kind']='human';path.write_text(json.dumps(value))
        self.assertEqual(self.report(reviews=path,review_migration=migration)['review_import']['accepted_count'],0)

    def test_migrated_fail_is_not_changed_to_pass(self):
        path,value=self.legacy();value['records'][0]['checks']['language']['status']='FAIL';path.write_text(json.dumps(value))
        migration,_=self.migration(path,True);report=self.report(reviews=path,review_migration=migration)
        self.assertEqual(report['local_sample_status'],'FAIL')

    def test_malformed_migration_assessor_does_not_inherit(self):
        path,_=self.legacy();migration,value=self.migration(path,True)
        value['decisions'][0]['assessor']='not an identity object';migration.write_text(json.dumps(value))
        self.assertEqual(self.report(reviews=path,review_migration=migration)['review_import']['accepted_count'],0)

    def test_missing_readme_role_is_mechanically_pending(self):
        (self.client/'README.md').unlink();self.seal();result=self.report()
        check=next(row for row in result['dataset_checks'] if row['rule_id']=='DELIVERY_DOCUMENT_ROLES')
        self.assertEqual(check['status'],'REVIEW_REQUIRED');self.assertFalse(result['release_ready'])

    def test_alternative_readme_role_name_is_allowed(self):
        (self.client/'README.md').rename(self.client/'说明.md')
        (self.client/'document_roles.json').write_text(json.dumps({'document_roles':{'readme':'说明.md'}}))
        self.seal();result=self.report()
        self.assertEqual(next(row for row in result['dataset_checks'] if row['rule_id']=='DELIVERY_DOCUMENT_ROLES')['status'],'PASS')

    def population(self,excluded):
        count=len(excluded);value={'total_samples':count+1,'selected_count':1,'excluded_count':count,'excluded_samples':excluded}
        with (self.client/'来源与合规说明.md').open('a') as stream:stream.write('\n```json\n'+json.dumps(value)+'\n```\n')
        self.seal();result=self.report()
        self.assertEqual(next(row for row in result['dataset_checks'] if row['rule_id']=='DELIVERY_ACCOUNTING')['status'],'FAIL')

    def test_duplicate_excluded_ids_fail_even_with_correct_arithmetic(self):
        self.population([{'sample_id':'same','reason':'one'},{'sample_id':'same','reason':'two'}])

    def test_selected_and_excluded_intersection_fails(self):
        self.population([{'sample_id':next(self.client.glob('samples/*')).name,'reason':'cannot also be selected'}])

    def test_malformed_excluded_id_fails_without_crash(self):
        self.population([{'sample_id':{'bad':'object'},'reason':'invalid ID'}])

    def test_known_machine_prose_and_original_quoted_names(self):
        for text in ('点击 #result 显示结果。','目标元素 e123 已出现。','当前有控件20个。','使用选择器 .result 查看。'):
            self.assertTrue(prohibited_narrative(text),text)
        for text in ('点击「#result」页签。','查看「e123」文件。','查看2个结果。','页面显示Python技术词。'):
            self.assertFalse(prohibited_narrative(text),text)

    def test_empty_hotkey_member_is_rejected(self):
        def mutation(annotation):
            step=annotation['steps'][0];step['action'].update(action_type='hotkey',target_element_id='',target_text='回车键',coordinate=[],input_text='')
            step['action'].pop('target_bbox');step['tool_call'].update(tool_name='hotkey',arguments={'keys':['']})
        self.mutate(mutation);result=self.report()
        self.assertTrue(any(row['rule_id']=='C09' and row['status']=='FAIL' for row in result['samples'][0]['checks']))

    def test_absolute_open_url_without_new_scheme_whitelist(self):
        original=next(self.client.glob('samples/*/annotation.json')).read_text()
        for url,expected in (('',True),('not a url',True),('https://example.org/',False),('file:///tmp/demo.html',False),('about:blank',False)):
            with self.subTest(url=url):
                next(self.client.glob('samples/*/annotation.json')).write_text(original)
                def mutation(annotation):
                    step=annotation['steps'][0];step['action'].update(action_type='open_url',target_element_id='',target_text='',coordinate=[],input_text='')
                    step['action'].pop('target_bbox');step['tool_call'].update(tool_name='open_url',arguments={'url':url})
                self.mutate(mutation);result=self.report()
                self.assertEqual(any(row['rule_id']=='C09' and row['status']=='FAIL' for row in result['samples'][0]['checks']),expected)

    def test_installed_authorities_and_rule_changes_are_bound(self):
        value,before=contract.fingerprint()
        self.assertEqual({row['role'] for row in value['authority']['documents']},{'clarification','site_trajectory_scope','trajectory_supplement','qc_sampling','requirement','annex_a','annex_b'})
        changed=copy.deepcopy(value['authority']);changed['documents'][0]['sha256']='a'*64
        with patch.object(contract,'authority',return_value=changed):self.assertNotEqual(contract.fingerprint()[1],before)


if __name__=='__main__':unittest.main()
