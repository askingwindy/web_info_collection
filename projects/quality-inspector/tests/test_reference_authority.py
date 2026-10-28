"""Authority regression: no sample ID exemptions and no production waiver."""
import json,unittest
from pathlib import Path
import test_engine as fixture_cases
from quality_inspector.engine import baseline_load
from quality_inspector.format_checks import sample_check,catalog
class ReferenceAuthority(unittest.TestCase):
 setUp=fixture_cases.IndependentQC.setUp
 tearDown=fixture_cases.IndependentQC.tearDown
 def test_customer_references_known_exception_not_missing_fields(self):
  b=baseline_load(self.config);self.assertEqual(b['reference_conventions_status'],'PASS')
  for s in b['samples']:
   self.assertEqual(s['reference_contract']['status'],'PASS');self.assertEqual(s['reference_contract']['semantic_acceptance'],'NOT_CLAIMED');self.assertEqual(s['reference_contract']['documented_exceptions'][0]['actual'],[]);self.assertFalse(s['reference_contract']['documented_exceptions'][0]['production_waiver']);self.assertTrue(s['deep_historical_diagnostic']['errors'])
 def test_arbitrary_production_id_empty_labels_still_FAIL(self):
  d=json.loads((self.p/'annotation.json').read_text());d['task_type']=[];(self.p/'annotation.json').write_text(json.dumps(d));self.assertFalse(sample_check(self.p)['confirmed_format_pass']);self.assertTrue(any(e['rule_id']=='C03' for e in sample_check(self.p)['errors']))
 def test_human_and_T6_are_not_rejected_by_internal_constants(self):
  d=json.loads((self.p/'annotation.json').read_text());d['trajectory_source'].update(source_type='human',data_type='T6');(self.p/'annotation.json').write_text(json.dumps(d));self.assertTrue(sample_check(self.p)['confirmed_format_pass'])
 def test_source_catalog_distinguishes_customer_from_internal(self):
  rows={r['id']:r for r in catalog()};self.assertEqual(rows['C03']['provenance']['authority'],'customer-original-archive');self.assertIn('not a customer requirement',rows['I01']['provenance']['authority']);self.assertEqual(rows['C04']['provenance']['source_enum'],['human','agent','human_agent_hybrid'])
