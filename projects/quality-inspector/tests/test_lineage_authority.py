import unittest
import test_engine as fixture_cases
class LineageAuthority(unittest.TestCase):
 setUp=fixture_cases.IndependentQC.setUp
 tearDown=fixture_cases.IndependentQC.tearDown
 report=fixture_cases.IndependentQC.report
 def test_documented_lineage_requires_no_external_registry(self):
  (self.data/'docs/合成方式说明.md').write_text('# fixture-test-line\n动作空间：unified_gui_v4；合成测试说明不是实际签核。');d=self.report();c=next(c for c in d['dataset_checks'] if c['rule_id']=='U02');self.assertEqual(c['status'],'PASS');self.assertEqual(c['scope'],'contract');self.assertEqual(d['customer_actual_acceptance'],'UNKNOWN')
 def test_missing_mapping_remains_review(self):
  d=self.report();self.assertEqual(next(c for c in d['dataset_checks'] if c['rule_id']=='U02')['status'],'REVIEW_REQUIRED')
