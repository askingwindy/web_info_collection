"""Independent fixed expectations for scope/aggregation; synthetic fixtures only."""
import json,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
import test_engine as fixture_cases
from quality_inspector.engine import SEMANTIC
class ScopeRegression(unittest.TestCase):
 setUp=fixture_cases.IndependentQC.setUp
 tearDown=fixture_cases.IndependentQC.tearDown
 report=fixture_cases.IndependentQC.report
 review=fixture_cases.IndependentQC.review
 def complete_review(self):
  d=self.review();d['records'][0]['checks']={k:{'status':'PASS','note':'SYNTHETIC TEST ONLY independently defined expectation'} for k in SEMANTIC};p=self.root/'review.json';p.write_text(json.dumps(d));return p
 def checks(self,d):return {c['rule_id']:c for c in d['samples'][0]['checks']}
 def test_complete_review_resolves_U04_but_external_stays_unknown(self):
  d=self.report(reviews=self.complete_review());c=self.checks(d);self.assertEqual(c['U04']['status'],'PASS');self.assertEqual(c['U03']['status'],'PASS');self.assertEqual(d['customer_actual_acceptance'],'UNKNOWN');self.assertEqual(d['status'],'REVIEW_REQUIRED')
 def test_external_and_corpus_rules_emitted_once_at_dataset_scope(self):
  d=self.report();self.assertFalse({'U01','U02','U05'}&set(self.checks(d)));self.assertEqual({c['rule_id'] for c in d['dataset_checks']},{'U01','U02','U05'});self.assertTrue(all(c['scope'] in ['external','contract','corpus'] for c in d['dataset_checks']))
 def test_preparation_check_has_one_traceable_catalog_entry_without_visual_claim(self):
  d=self.report();self.assertIn('PREPARATION_INTEGRITY',self.checks(d))
  rows=[r for r in d['rules'] if r['id']=='PREPARATION_INTEGRITY'];self.assertEqual(len(rows),1)
  r=rows[0];self.assertEqual(r['certainty'],'new_production_evidence_contract')
  self.assertEqual(r['policy'],'content-preparation-v1');self.assertEqual(r['new_policy_missing_evidence_status'],'FAIL')
  self.assertEqual(r['legacy_status'],'NOT_APPLICABLE');self.assertEqual(r['legacy_compatibility_status'],'PASS')
  self.assertFalse(r['legacy_new_policy_verification_claimed']);self.assertTrue(r['not_visual_semantic_acceptance'])
  self.assertTrue(any('2026-10-23' in s for s in r['sources']));self.assertTrue(any('连续截图' in s for s in r['sources']))
  c=self.checks(d)['PREPARATION_INTEGRITY'];self.assertEqual(c['status'],'PASS')
  self.assertEqual(c['evidence']['status'],'NOT_APPLICABLE');self.assertTrue(c['not_visual_semantic_acceptance'])
 def test_partial_review_does_not_resolve_U04(self):
  p=self.root/'partial.json';p.write_text(json.dumps(self.review()));self.assertEqual(self.checks(self.report(reviews=p))['U04']['status'],'REVIEW_REQUIRED')
 def test_semantic_failure_propagates_to_U04(self):
  p=self.complete_review();d=json.loads(p.read_text());d['records'][0]['checks']['terminal_semantics']['status']='FAIL';p.write_text(json.dumps(d));self.assertEqual(self.checks(self.report(reviews=p))['U04']['status'],'FAIL')
 def test_capture_tree_tamper_cannot_be_approved_by_review(self):
  tree=self.p/'ui_tree/step_001.json';t=json.loads(tree.read_text());t['elements'][0]['text']='篡改实际证据';tree.write_text(json.dumps(t));d=self.report(reviews=self.complete_review());self.assertEqual(self.checks(d)['CAPTURE_INTEGRITY']['status'],'FAIL');self.assertEqual(self.checks(d)['U04']['status'],'FAIL')
 def test_malformed_review_fields_rejected_as_data_not_crash(self):
  for field,value in [('reviewer',None),('checks',[]),('provenance','wrong')]:
   d=self.review();d['records'][0][field]=value;p=self.root/'bad.json';p.write_text(json.dumps(d));r=self.report(reviews=p);self.assertEqual(r['status'],'FAIL');self.assertEqual(r['review_import']['accepted_count'],0)
 def test_missing_raw_tree_evidence_remains_review_required(self):
  raw=self.p.parent.parent/'evidence'/self.p.name/'step_001.json';d=json.loads(raw.read_text());del d['state'];raw.write_text(json.dumps(d));r=self.report(reviews=self.complete_review());self.assertEqual(self.checks(r)['CAPTURE_INTEGRITY']['status'],'REVIEW_REQUIRED');self.assertEqual(self.checks(r)['U04']['status'],'REVIEW_REQUIRED')
 def test_language_unknown_is_not_silently_passed(self):
  p=self.complete_review();d=json.loads(p.read_text());d['records'][0]['checks']['language']={'status':'REVIEW_REQUIRED','note':'client policy unavailable'};p.write_text(json.dumps(d));r=self.report(reviews=p);self.assertEqual(self.checks(r)['U03']['status'],'REVIEW_REQUIRED');self.assertEqual(self.checks(r)['U04']['status'],'PASS');self.assertEqual(r['status'],'REVIEW_REQUIRED')
 def test_observations_only_declared_paths(self):
  from quality_inspector.format_checks import observations_from_examples
  x=self.root/'refs';(x/'pinned').mkdir(parents=True);(x/'unlisted').mkdir();(x/'pinned/annotation.json').write_text('{"allowed":"value"}');(x/'unlisted/annotation.json').write_text('{"untrusted":123}')
  obs=observations_from_examples([x/'pinned/annotation.json']);self.assertIn('annotation/allowed',{o['path'] for o in obs});self.assertNotIn('annotation/untrusted',{o['path'] for o in obs})
