import os
import sys,json,tempfile,hashlib,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from make_fixture import fixture
from quality_inspector.engine import inspect,baseline_load,aggregate,evidence_files,review_intake,sha,compare_baseline_shape,capture_integrity
from quality_inspector.reporting import write_outputs
R=Path(os.environ.get('QC_TEST_REPO',str(Path(__file__).resolve().parents[3])))
class IndependentQC(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.p=fixture(self.root/'data');self.data=self.root/'data';c=json.loads((Path(__file__).parents[1]/'config/customer-samples.json').read_text());c['repository_root']=str(R)
  # The legacy profile intentionally pins the old authority bytes. Current
  # user requirements may evolve; do not weaken its product drift detection or
  # silently repin a historical profile just to make this fixture pass.
  legacy=Path(__file__).parent/'fixtures/legacy-clarification-20261026.md'
  for document in c['supplemental_documents']:
   if document['path']=='request/需求澄清记录.md':
    self.assertEqual(hashlib.sha256(legacy.read_bytes()).hexdigest(),document['sha256'])
    document['path']=str(legacy.resolve())
  self.config=self.root/'baseline.json';self.config.write_text(json.dumps(c,ensure_ascii=False));self.a=json.loads((self.p/'annotation.json').read_text())
 def tearDown(self):self.t.cleanup()
 def report(self,**kw):return inspect(self.config,self.data,**kw)
 def mutate(self): (self.p/'annotation.json').write_text(json.dumps(self.a,ensure_ascii=False))
 def test_aggregate_three_states(self):self.assertEqual(aggregate(['PASS']),'PASS');self.assertEqual(aggregate(['PASS','REVIEW_REQUIRED']),'REVIEW_REQUIRED');self.assertEqual(aggregate(['REVIEW_REQUIRED','FAIL']),'FAIL')
 def test_actual_original_samples_remain_known_limits(self):
  b=baseline_load(self.config);self.assertEqual(b['integrity'],'PASS');self.assertEqual(b['status'],'REVIEW_REQUIRED');self.assertEqual(len(b['samples']),2);self.assertTrue(all(s['original_format_result']['errors'][0]['rule_id']=='C03' for s in b['samples']))
 def test_literal_fixture_auto_format_pass_but_visual_not_assumed(self):
  d=self.report();self.assertEqual(d['status'],'REVIEW_REQUIRED');checks={c['rule_id']:c for c in d['samples'][0]['checks']};self.assertTrue(all(checks[f'C{i:02}']['status']=='PASS' for i in range(1,18)));self.assertEqual(checks['REVIEW_VISUAL_ALIGNMENT']['status'],'REVIEW_REQUIRED');self.assertEqual(d['customer_actual_acceptance'],'UNKNOWN')
 def test_baseline_observed_types_are_actually_compared_without_constant_values(self):
  d=compare_baseline_shape({'sample_id':'DIFFERENT BUT STRING','risk_level':42},self.p,[{'path':'annotation/sample_id','types':['string']},{'path':'annotation/risk_level','types':['string']}]);self.assertEqual(d['matched_paths_compared'],2);self.assertEqual(d['type_differences'][0]['field'],'annotation/risk_level');self.assertTrue(d['values_not_used_as_constants'])
 def test_reference_hash_change_fails_without_editing_reference(self):
  c=json.loads(self.config.read_text());k=next(iter(c['samples'][0]['files']));c['samples'][0]['files'][k]='0'*64;self.config.write_text(json.dumps(c));self.assertEqual(self.report()['status'],'FAIL')
 def test_missing_field_localized(self):
  del self.a['task_instruction'];self.mutate();d=self.report();self.assertEqual(d['status'],'FAIL');self.assertTrue(any(c['status']=='FAIL' and c['rule_id']=='C01' for c in d['samples'][0]['checks']))
 def test_missing_image_is_not_review_pass(self):
  (self.p/'images/step_002.png').unlink();d=self.report();self.assertEqual(d['status'],'FAIL');self.assertTrue(any(c['rule_id']=='C06' and c['status']=='FAIL' for c in d['samples'][0]['checks']))
 def test_same_size_image_tamper_detected_from_capture(self):
  from PIL import Image
  Image.new('RGB',(640,480),'black').save(self.p/'images/step_002.png');d=self.report();c=next(c for c in d['samples'][0]['checks'] if c['rule_id']=='CAPTURE_INTEGRITY');self.assertEqual(c['status'],'FAIL');self.assertEqual(c['evidence']['errors'][0]['step_id'],2)
 def test_capture_meta_select_all_matches_canonical_delivery_without_rewriting_raw(self):
  raw=self.p.parent.parent/'evidence'/self.p.name/'step_001.json';value=json.loads(raw.read_text());value['executed_action']={'tool_name':'hotkey','arguments':{'keys':['meta','a']}};raw.write_text(json.dumps(value));before=raw.read_bytes()
  self.a['device_info']['os_name']='macOS';self.a['steps'][0]['tool_call'].update(tool_name='hotkey',arguments={'keys':['ctrl','a']})
  result=capture_integrity(self.p,self.a);self.assertEqual(result['status'],'PASS',result);self.assertEqual(raw.read_bytes(),before)
 def test_capture_native_paste_matches_windows_delivery_only_for_macos(self):
  raw=self.p.parent.parent/'evidence'/self.p.name/'step_001.json';value=json.loads(raw.read_text());value['executed_action']={'tool_name':'hotkey','arguments':{'keys':['meta','v']}};raw.write_text(json.dumps(value));before=raw.read_bytes()
  self.a['device_info']['os_name']='macOS';self.a['steps'][0]['tool_call'].update(tool_name='hotkey',arguments={'keys':['ctrl','v']})
  self.assertEqual(capture_integrity(self.p,self.a)['status'],'PASS');self.assertEqual(raw.read_bytes(),before)
  self.a['device_info']['os_name']='Windows';self.assertEqual(capture_integrity(self.p,self.a)['status'],'FAIL')
 def test_capture_select_all_mapping_does_not_hide_other_changes(self):
  raw=self.p.parent.parent/'evidence'/self.p.name/'step_001.json';value=json.loads(raw.read_text());self.a['steps'][0]['tool_call'].update(tool_name='hotkey',arguments={'keys':['ctrl','a']})
  for executed in ({'tool_name':'hotkey','arguments':{'keys':['meta','c']}},{'tool_name':'hotkey','arguments':{'keys':['meta','a','a']}},{'tool_name':'hotkey','arguments':{'keys':['meta','a'],'extra':True}},{'tool_name':'click','arguments':{'keys':['meta','a']}},{'tool_name':'hotkey','arguments':{'keys':['meta','a']},'extra':True}):
   with self.subTest(executed=executed):
    value['executed_action']=executed;raw.write_text(json.dumps(value));result=capture_integrity(self.p,self.a);self.assertEqual(result['status'],'FAIL');self.assertTrue(any('Executed action' in row['reason'] for row in result['errors']))
 def test_no_final_assertions_does_not_assume_semantics(self):
  p=self.p.parent.parent/'evidence'/self.p.name/'step_006.json';a=json.loads(p.read_text());a['final_assertions']=[];p.write_text(json.dumps(a));d=self.report();self.assertEqual(next(c for c in d['samples'][0]['checks'] if c['rule_id']=='FINAL_MACHINE_EVIDENCE')['status'],'REVIEW_REQUIRED')
 def test_explicit_failed_final_assertion_is_FAIL(self):
  p=self.p.parent.parent/'evidence'/self.p.name/'step_006.json';a=json.loads(p.read_text());a['final_assertions']=[{'passed':False,'actual':'测试明确失败'}];p.write_text(json.dumps(a));d=self.report();self.assertEqual(next(c for c in d['samples'][0]['checks'] if c['rule_id']=='FINAL_MACHINE_EVIDENCE')['status'],'FAIL')
 def test_invalid_annotation_json_yields_FAIL_report(self):
  (self.p/'annotation.json').write_text('{broken');self.assertEqual(self.report()['status'],'FAIL')
 def test_empty_input_is_FAIL(self):
  empty=self.root/'empty';empty.mkdir();self.assertEqual(inspect(self.config,empty)['status'],'FAIL')
 def review(self):
  return {'schema_version':'qc-review-1','records':[{'sample_id':self.p.name,'baseline_sha256':sha(self.config),'annotation_sha256':sha(self.p/'annotation.json'),'evidence_sha256':evidence_files(self.p),'reviewer':{'kind':'ai','name':'UNIT TEST ONLY'},'provenance':{'description':'Synthetic fixture test, not actual customer/human review'},'checks':{'visual_alignment':{'status':'PASS','note':'TEST FIXTURE ONLY: verifies intake plumbing, not image truth'}}}]}
 def test_evidence_bound_AI_record_import(self):
  p=self.root/'review.json';p.write_text(json.dumps(self.review()));d=self.report(reviews=p);self.assertEqual(d['review_import']['accepted_count'],1);self.assertEqual(next(c for c in d['samples'][0]['checks'] if c['rule_id']=='REVIEW_VISUAL_ALIGNMENT')['status'],'PASS');self.assertEqual(next(c for c in d['samples'][0]['checks'] if c['rule_id']=='REVIEW_LANGUAGE')['status'],'REVIEW_REQUIRED')
 def test_stale_review_annotation_rejected(self):
  data=self.review();data['records'][0]['annotation_sha256']='0'*64;p=self.root/'review.json';p.write_text(json.dumps(data));d=self.report(reviews=p);self.assertEqual(d['review_import']['accepted_count'],0);self.assertEqual(d['status'],'FAIL')
 def test_incomplete_review_evidence_rejected(self):
  data=self.review();data['records'][0]['evidence_sha256']={};p=self.root/'review.json';p.write_text(json.dumps(data));d=self.report(reviews=p);self.assertEqual(d['review_import']['accepted_count'],0)
 def test_blank_reviewer_rejected(self):
  data=self.review();data['records'][0]['reviewer']={'kind':'human','name':''};p=self.root/'review.json';p.write_text(json.dumps(data));self.assertEqual(self.report(reviews=p)['review_import']['accepted_count'],0)
 def test_review_schema_errors_reported(self):
  p=self.root/'review.json';p.write_text('[]');self.assertTrue(self.report(reviews=p)['review_import']['invalid_records'])
 def test_export_interface_defaults_pending_and_has_evidence(self):
  out=self.root/'out';write_outputs(self.report(),out);s=(out/'review.html').read_text();self.assertIn('导出质检审核记录',s);self.assertIn('打开同步界面树',s);t=json.loads((out/'review-template.json').read_text());self.assertTrue(all(c['status']=='REVIEW_REQUIRED' for c in t['records'][0]['checks'].values()));self.assertTrue(t['records'][0]['evidence_sha256'])
if __name__=='__main__':unittest.main(verbosity=2)
