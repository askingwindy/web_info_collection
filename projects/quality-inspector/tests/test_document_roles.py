import unittest
import test_engine as fixture_cases
class DeliveryDocuments(unittest.TestCase):
 setUp=fixture_cases.IndependentQC.setUp
 tearDown=fixture_cases.IndependentQC.tearDown
 report=fixture_cases.IndependentQC.report
 def test_missing_synthesis_not_silently_reported_pass(self):
  (self.data/'docs/合成方式说明.md').unlink();d=self.report();self.assertEqual(d['status'],'FAIL');self.assertTrue(any(c['rule_id']=='C14' and c['status']=='FAIL' for c in d['samples'][0]['checks']))
 def test_empty_readme_rejected(self):
  (self.data/'README.md').write_text('');self.assertEqual(self.report()['status'],'FAIL')
 def test_alternative_document_name_with_mapping_is_supported(self):
  import json
  (self.data/'docs/合成方式说明.md').rename(self.data/'docs/custom-description.md');p=self.data/'document_roles.json';d=json.loads(p.read_text());d['document_roles']['synthesis']='docs/custom-description.md';p.write_text(json.dumps(d));r=self.report();self.assertEqual(next(c for c in r['samples'][0]['checks'] if c['rule_id']=='C14')['status'],'PASS')
 def test_undeclared_alternative_name_requires_review_not_guessed_fail(self):
  (self.data/'document_roles.json').unlink();(self.data/'docs/合成方式说明.md').rename(self.data/'docs/unknown.md');r=self.report();self.assertEqual(next(c for c in r['samples'][0]['checks'] if c['rule_id']=='C14')['status'],'REVIEW_REQUIRED')
