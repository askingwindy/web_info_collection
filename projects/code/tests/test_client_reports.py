"""Output/QC/finalization binding tests using explicitly synthetic fixture data."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_client_package import fixture
from webcollect.client_package import build_client_package, sample_hashes, sha
from webcollect.client_reports import finalize_client_package

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'projects/quality-inspector'))
from quality_inspector.engine import inspect
from quality_inspector.checksums import verify_manifest


class BoundClientReports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'capture'
        fixture(self.source)
        self.client = self.root / 'client'
        exported = build_client_package(REPO, self.source, self.client)
        # Tests the actual flat-customer inspection route; this fixture has no
        # complete semantic/raw evidence and is never counted as a real sample.
        self.report = inspect(REPO / 'projects/quality-inspector/config/customer-samples.json',
                              self.client, evidence=Path(exported['evidence_output']),
                              profile=REPO / 'projects/quality-inspector/config/local-pilot-v1.json')
        self.report_path = self.root / 'qc.json'
        self.save_report()

    def save_report(self):
        self.report_path.write_text(json.dumps(self.report, ensure_ascii=False))

    def finalize(self):
        return finalize_client_package(REPO, self.client, self.report_path, self.root / 'final')

    def test_actual_customer_input_then_bound_report_then_new_customer_output(self):
        mapping = [c for c in self.report['dataset_checks'] if c['rule_id'] == 'U02' and c['status'] == 'PASS']
        self.assertEqual(len(mapping), 1)
        self.assertFalse(mapping[0]['unmapped_samples'])
        source_bytes = {p.relative_to(self.client).as_posix(): sha(p)
                        for p in self.client.rglob('*') if p.is_file()}
        # A synthetic mocked PASS tests file binding only, never real visual acceptance.
        self.report.update(delivery_status='PASS', inspection_stage='payload', synthetic_unit_fixture=True)
        self.save_report()
        result = self.finalize()
        output = Path(result['output'])
        self.assertEqual(self.report['dataset'], str(self.client.resolve()))
        self.assertEqual(sample_hashes(self.client / 'samples/Web_fixture_001'),
                         sample_hashes(output / 'samples/Web_fixture_001'))
        self.assertTrue(verify_manifest(output)['pass'])
        self.assertEqual(source_bytes, {p.relative_to(self.client).as_posix(): sha(p)
                                       for p in self.client.rglob('*') if p.is_file()})
        summary = (output / 'qc_report.md').read_text()
        self.assertIn(sha(self.report_path), summary)
        self.assertIn('REVIEW_REQUIRED', summary)
        self.assertIn('UNKNOWN', summary)
        self.assertNotIn(str(self.root), summary)
        self.assertEqual(result['new_package_qc_status'], 'NOT_RUN')
        self.assertRaises(FileExistsError, self.finalize)

    def test_pending_or_legacy_engineering_report_cannot_publish(self):
        self.assertRaisesRegex(ValueError, 'PASS delivery', self.finalize)
        for status in ('FAIL','REVIEW_REQUIRED'):
            self.report.update(delivery_status=status,inspection_stage='payload');self.save_report()
            self.assertRaisesRegex(ValueError, 'PASS delivery', self.finalize)

    def test_summary_preserves_actual_ai_identity_and_document_decisions(self):
        from webcollect.client_reports import _render_summary
        import re
        # Synthetic review facts exercise rendering, never approve a real sample.
        report = json.loads(json.dumps(self.report))
        report['scope'] = 'delivery'
        report['delivery_document_review'] = {'status':'PASS',
            'reviewer':{'kind':'ai','name':'Synthetic document reviewer'},
            'checks':{'synthetic_check':{'status':'PASS','note':'Synthetic fixture only'}}}
        for sample in report['samples']:
            sample['local_checks'] = [check for check in sample.get('local_checks',sample.get('checks',[]))
                                      if not check['rule_id'].startswith('REVIEW_')]
            for name in ['VISUAL_ALIGNMENT','TERMINAL_SEMANTICS','LANGUAGE','PRIVACY','SUBSTANTIVE_DIFFERENCE']:
                sample['local_checks'].append({'rule_id':'REVIEW_'+name,'status':'PASS',
                    'reviewer':{'kind':'ai','name':'Synthetic image reviewer'}})
        text = _render_summary(self.client,self.report_path,report,
            {p.relative_to(self.client).as_posix():sha(p) for p in self.client.rglob('*') if p.is_file()})
        summary = json.loads(re.findall(r'```json\n(.*?)\n```',text,re.S)[0])
        self.assertEqual(summary['review_coverage']['reviewer_sources'],
            [{'kind':'ai','name':'Synthetic image reviewer','samples':len(report['samples'])}])
        self.assertEqual(summary['delivery_document_review'],report['delivery_document_review'])
        self.assertEqual(summary['review_coverage']['human_complete_samples'],0)

    def test_stale_document_hash_cannot_be_attached_to_new_output(self):
        with (self.client / 'README.md').open('a') as stream:
            stream.write('\nChanged after QC\n')
        self.assertRaisesRegex(ValueError, 'hash binding|checksum manifest', self.finalize)
        self.assertFalse((self.root / 'final').exists())

    def test_other_dataset_or_shadow_sample_report_is_rejected(self):
        self.report['dataset'] = str(self.root / 'other')
        self.save_report()
        self.assertRaisesRegex(ValueError, 'dataset differs', self.finalize)
        self.report['dataset'] = str(self.client)
        self.report['samples'][0]['sample_path'] = str(self.source / 'samples/Web_fixture_001')
        self.save_report()
        self.assertRaisesRegex(ValueError, 'actual client sample', self.finalize)

    def test_partial_input_file_map_and_unverified_manifest_are_rejected(self):
        self.report.pop('input_files_sha256', None)
        self.report['package_files_sha256'].pop('README.md')
        self.save_report()
        self.assertRaisesRegex(ValueError, 'hash binding', self.finalize)
        self.report['package_files_sha256']['README.md'] = sha(self.client / 'README.md')
        self.report['root_checksum']['pass'] = False
        self.save_report()
        self.assertRaisesRegex(ValueError, 'SHA256SUMS', self.finalize)


if __name__ == '__main__':
    unittest.main(verbosity=2)
