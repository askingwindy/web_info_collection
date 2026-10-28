"""Offline review projection preserves real evidence and blank human decisions."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
from make_fixture import fixture
from quality_inspector.reporting import review_data, review_samples, review_template, render_review


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ReviewProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'data'
        self.sample = fixture(self.root)
        self.annotation = json.loads((self.sample / 'annotation.json').read_text())
        self.evidence = {path.relative_to(self.sample).as_posix(): digest(path)
                         for dirname in ['images', 'ui_tree']
                         for path in (self.sample / dirname).iterdir() if path.is_file()}
        self.report = {
            'baseline': {'config_sha256': 'b' * 64}, 'dataset': str(self.root),
            'samples': [{
                'sample_id': self.sample.name, 'sample_path': str(self.sample),
                'annotation_sha256': digest(self.sample / 'annotation.json'),
                'evidence_sha256': dict(self.evidence), 'steps': [],
            }],
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_real_task_full_actions_and_tree_target_are_projected(self):
        sample = review_samples(self.report)[0]
        self.assertEqual(sample['task_instruction'], self.annotation['task_instruction'])
        self.assertEqual(sample['final_result'], self.annotation['final_result'])
        self.assertEqual(sample['steps'][0]['tool_call'], self.annotation['steps'][0]['tool_call'])
        self.assertEqual(sample['steps'][0]['target']['text'], '输入框')
        self.assertEqual(sample['steps'][0]['target']['element_id'], 'inputA')
        self.assertTrue(Path(sample['steps'][0]['image_path']).is_absolute())
        self.assertTrue(sample['binding_valid'])
        self.assertEqual(sample['device_info']['screen_resolution'], [640, 480])

    def test_missing_tree_is_explicit_and_target_is_not_reconstructed(self):
        (self.sample / 'ui_tree/step_001.json').unlink()
        sample = review_samples(self.report)[0]
        self.assertFalse(sample['binding_valid'])
        self.assertFalse(sample['steps'][0]['binding_valid'])
        self.assertIsNone(sample['steps'][0]['target'])
        self.assertTrue(sample['steps'][0]['warnings'])

    def test_changed_annotation_and_image_cannot_reuse_report_binding(self):
        path = self.sample / 'annotation.json'
        annotation = json.loads(path.read_text())
        annotation['task_instruction'] = '文件发生变更后的测试任务'
        path.write_text(json.dumps(annotation))
        (self.sample / 'images/step_002.png').write_bytes(b'changed test bytes')
        sample = review_samples(self.report)[0]
        self.assertFalse(sample['binding_valid'])
        self.assertTrue(sample['warnings'])
        self.assertFalse(sample['steps'][1]['binding_valid'])

    def test_malformed_annotation_keeps_missing_task_explicit(self):
        (self.sample / 'annotation.json').write_text('[]')
        sample = review_samples(self.report)[0]
        self.assertIsNone(sample['annotation'])
        self.assertEqual(sample['task_instruction'], '')
        self.assertFalse(sample['binding_valid'])
        self.assertTrue(sample['warnings'])

    def test_evidence_path_cannot_escape_sample(self):
        annotation = copy.deepcopy(self.annotation)
        annotation['steps'][0]['image_path'] = '../../../../outside.png'
        path = self.sample / 'annotation.json'
        path.write_text(json.dumps(annotation))
        self.report['samples'][0]['annotation_sha256'] = digest(path)
        step = review_samples(self.report)[0]['steps'][0]
        self.assertIsNone(step['image_path'])
        self.assertFalse(step['binding_valid'])
        self.assertIn('超出', ''.join(step['warnings']))

    def test_default_single_reviewer_does_not_prefill_any_decision(self):
        data = review_data(self.report)
        self.assertEqual(data['reviewer'], {'kind': 'human', 'name': 'hemiao'})
        record = data['template']['records'][0]
        self.assertEqual(record['reviewer'], {'kind': '', 'name': ''})
        self.assertEqual(record['evidence_sha256'], self.evidence)
        self.assertTrue(all(check == {'status': 'REVIEW_REQUIRED', 'note': ''}
                            for check in record['checks'].values()))
        self.assertEqual(data['package_summary']['frame_count'], 6)
        self.assertEqual(data['package_summary']['effective_action_count'], 5)

    def test_draft_identity_changes_with_evidence_not_page_or_reviewer(self):
        data = review_data(self.report)
        other = copy.deepcopy(self.report)
        other['status'] = 'PASS'
        self.assertEqual(data['data_id'], review_data(other, reviewer_name='another config')['data_id'])
        other['samples'][0]['annotation_sha256'] = 'c' * 64
        self.assertNotEqual(data['data_id'], review_data(other)['data_id'])
        other = copy.deepcopy(self.report)
        other['samples'][0]['evidence_sha256']['images/step_001.png'] = 'd' * 64
        self.assertNotEqual(data['data_id'], review_data(other)['data_id'])

    def test_document_list_is_bound_and_detects_changed_documents(self):
        report = copy.deepcopy(self.report)
        report['local_profile'] = {'sha256': 'p' * 64}
        report['package_files_sha256'] = {path.relative_to(self.root).as_posix(): digest(path)
                                          for path in self.root.rglob('*') if path.is_file()}
        before = review_data(report)
        documents = before['package_documents']
        self.assertIn('README.md', [row['relative_path'] for row in documents])
        self.assertIn('batch/metadata.csv', [row['relative_path'] for row in documents])
        self.assertNotIn('batch/samples/fixture_client_01/annotation.json', [row['relative_path'] for row in documents])
        self.assertTrue(all(row['binding_valid'] for row in documents))
        (self.root / 'README.md').write_text('Changed test documentation')
        after = review_data(report)
        doc = next(row for row in after['package_documents'] if row['relative_path'] == 'README.md')
        self.assertFalse(doc['binding_valid'])
        template = review_template(report)
        self.assertEqual(template['package_review']['reviewer'], {'kind': '', 'name': ''})
        self.assertTrue(all(row['status'] == 'REVIEW_REQUIRED' for row in template['package_review']['checks'].values()))
        other = copy.deepcopy(report)
        other['package_files_sha256']['README.md'] = 'e' * 64
        self.assertNotEqual(before['data_id'], review_data(other)['data_id'])

    def test_inline_json_cannot_close_script_tag(self):
        annotation = copy.deepcopy(self.annotation)
        annotation['task_instruction'] = '</script><script>unexpected()</script>'
        path = self.sample / 'annotation.json'
        path.write_text(json.dumps(annotation))
        self.report['samples'][0]['annotation_sha256'] = digest(path)
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            if path.name == 'review.html':
                return '<script>const D=__DATA__;</script>'
            return original_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', new=read):
            html = render_review(self.report)
        self.assertEqual(html.count('</script>'), 1)
        self.assertNotIn('<script>unexpected()', html)
        self.assertIn('\\u003c/script>', html)


if __name__ == '__main__':
    unittest.main()
