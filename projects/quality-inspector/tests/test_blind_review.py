"""Blind workspace isolation uses synthetic fixtures, never human approvals."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from make_fixture import fixture
from quality_inspector.blind import prepare_data, write_workspace
from quality_inspector.reporting import review_data
from quality_inspector.__main__ import main


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BlindReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / 'source'
        self.sample = fixture(self.dataset)
        self.report = {
            'scope': 'delivery', 'dataset': str(self.dataset),
            'baseline': {'config_sha256': 'b' * 64},
            'status': 'AI_OUTCOME_SENTINEL',
            'review_import': {'records': 'AI_JUDGMENT_SENTINEL'},
            'rejection_history': 'REJECTION_HISTORY_SENTINEL',
            'samples': [{
                'sample_id': self.sample.name, 'sample_path': str(self.sample),
                'annotation_sha256': digest(self.sample / 'annotation.json'),
                'evidence_sha256': self.evidence(),
                'checks': [{'status': 'FAIL', 'reason': 'QC_FAILURE_SENTINEL'}],
                'reviewer': {'name': 'AI_REVIEWER_SENTINEL'},
            }],
            'acceptance_scopes': {'pilot': {'statistics': {'secret': 'HIDDEN_STATISTIC_SENTINEL'}}},
        }
        self.context = {'source_statement': '仅离线合成测试；不是真实采集。',
                        'input_statement': '测试输入为“测试”，不是个人资料。'}
        self.report_path = self.root / 'report.json'
        self.context_path = self.root / 'context.json'
        self.output = self.root / 'blind'
        self.receipt = self.root / 'operator' / 'receipt.json'
        self.write_inputs()

    def tearDown(self):
        self.tmp.cleanup()

    def evidence(self):
        return {p.relative_to(self.sample).as_posix(): digest(p)
                for dirname in ['images', 'ui_tree']
                for p in (self.sample / dirname).iterdir() if p.is_file()}

    def write_inputs(self):
        self.report_path.write_text(json.dumps(self.report, ensure_ascii=False))
        self.context_path.write_text(json.dumps(self.context, ensure_ascii=False))

    def create(self):
        return write_workspace(self.report_path, self.output, context_path=self.context_path,
                               receipt_path=self.receipt)

    def test_no_report_decisions_history_or_document_links_are_embedded(self):
        data = prepare_data(self.report, reviewer_name='hemiao', context=self.context)
        encoded = json.dumps(data, ensure_ascii=False)
        for marker in ['AI_OUTCOME', 'AI_JUDGMENT', 'REJECTION_HISTORY', 'QC_FAILURE',
                       'AI_REVIEWER', 'HIDDEN_STATISTIC']:
            self.assertNotIn(marker, encoded)
        self.assertNotIn('report', data)
        self.assertEqual(data['package_documents'], [])
        self.assertEqual(set(data['template']), {'schema_version', 'records'})
        self.assertEqual(data['template']['schema_version'], 'qc-review-2')
        for row in data['template']['records']:
            self.assertEqual(row['reviewer'], {'kind': '', 'name': ''})
            self.assertEqual(row['step_observations'], [])
            self.assertTrue(all(c['status'] == 'REVIEW_REQUIRED' and not c['note']
                                for c in row['checks'].values()))

    def test_real_evidence_copied_byte_exact_and_workspace_is_portable(self):
        before = {str(p): digest(p) for p in self.dataset.rglob('*') if p.is_file()}
        receipt = self.create()
        self.assertEqual(receipt['sample_count'], 1)
        self.assertEqual(receipt['frame_count'], 6)
        self.assertEqual(receipt['actual_human_reviews_created'], 0)
        self.assertEqual(len(receipt['copied_evidence_sha256']), 13)
        for relative, expected in receipt['copied_evidence_sha256'].items():
            self.assertEqual(digest(self.output / relative), expected)
        html = (self.output / 'review.html').read_text()
        self.assertIn('assets/fixture_client_01/images/step_001.png', html)
        self.assertNotIn(str(self.dataset), html)
        self.assertNotIn(str(self.report_path), html)
        self.assertNotIn('AI_JUDGMENT_SENTINEL', html)
        self.assertEqual({str(p): digest(p) for p in self.dataset.rglob('*') if p.is_file()}, before)
        self.assertEqual(set(p.name for p in self.output.iterdir()), {'assets', 'review.html', 'review-template.json'})

    def test_blind_namespace_is_separate_and_context_changes_identity(self):
        normal = review_data(self.report)['data_id']
        blind = prepare_data(self.report, reviewer_name='hemiao', context=self.context)['data_id']
        self.assertNotEqual(normal, blind)
        other = dict(self.context, input_statement='另一份真实输入声明')
        self.assertNotEqual(blind, prepare_data(self.report, reviewer_name='hemiao', context=other)['data_id'])

    def test_unknown_annotation_metadata_cannot_enter_workspace(self):
        path = self.sample / 'annotation.json'
        value = json.loads(path.read_text()); value['prior_AI_review'] = 'SECRET'
        path.write_text(json.dumps(value))
        self.report['samples'][0]['annotation_sha256'] = digest(path)
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, '白名单'):
            self.create()
        self.assertFalse(self.output.exists())

    def test_nested_tool_metadata_cannot_enter_workspace(self):
        path = self.sample / 'annotation.json'
        value = json.loads(path.read_text()); value['steps'][0]['tool_call']['arguments']['AI'] = 'SECRET'
        path.write_text(json.dumps(value))
        self.report['samples'][0]['annotation_sha256'] = digest(path)
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, '参数超出'):
            self.create()

    def test_tree_metadata_cannot_enter_workspace(self):
        path = self.sample / 'ui_tree/step_001.json'
        value = json.loads(path.read_text()); value['elements'][0]['old_review'] = 'SECRET'
        path.write_text(json.dumps(value))
        self.report['samples'][0]['evidence_sha256'] = self.evidence()
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, '白名单'):
            self.create()

    def test_extra_bound_file_cannot_enter_assets(self):
        extra = self.sample / 'private-review.json'; extra.write_text('SECRET')
        self.report['samples'][0]['evidence_sha256'][extra.name] = digest(extra)
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, '额外文件'):
            self.create()

    def test_changed_image_rejects_without_creating_a_workspace(self):
        (self.sample / 'images/step_001.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '绑定无效'):
            self.create()
        self.assertFalse(self.output.exists())

    def test_neutral_context_is_explicit_and_has_no_unknown_fields(self):
        self.context['previous_decisions'] = 'SECRET'; self.write_inputs()
        with self.assertRaisesRegex(ValueError, '中性事实'):
            self.create()

    def test_operator_receipt_cannot_be_exposed_inside_workspace(self):
        with self.assertRaisesRegex(ValueError, '独立'):
            write_workspace(self.report_path, self.output, context_path=self.context_path,
                            receipt_path=self.output / 'receipt.json')
        self.assertFalse(self.output.exists())

    def test_workspace_never_overwrites_source_or_existing_output(self):
        with self.assertRaisesRegex(ValueError, '受检包'):
            write_workspace(self.report_path, self.dataset / 'review', context_path=self.context_path,
                            receipt_path=self.receipt)
        self.create()
        with self.assertRaisesRegex(ValueError, '新路径'):
            self.create()

    def test_current_cli_creates_only_pending_blind_workspace(self):
        result = main(['review', '--report', str(self.report_path), '--output', str(self.output),
                       '--blind', '--context', str(self.context_path), '--receipt', str(self.receipt)])
        self.assertEqual(result, 0)
        template = json.loads((self.output / 'review-template.json').read_text())
        self.assertEqual(template['schema_version'], 'qc-review-2')
        self.assertTrue(all(c['status'] == 'REVIEW_REQUIRED' for r in template['records'] for c in r['checks'].values()))


if __name__ == '__main__':
    unittest.main()
