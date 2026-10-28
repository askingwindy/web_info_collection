"""Synthetic source-to-export normalization; never a real review decision."""
import json
from pathlib import Path
import tempfile
import unittest

from test_client_package import REPO, fixture, review, write
from webcollect.client_package import build_client_package, sample_hashes, validate_client_sample


class HotkeyNormalizationExport(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'source'
        self.sample = fixture(self.source)
        path = self.sample / 'annotation.json'
        annotation = json.loads(path.read_text())
        step = annotation['steps'][2]
        step['action'].update(input_text='meta+a', target_text='Command+A')
        step['tool_call']['arguments'] = {'keys': ['meta', 'a']}
        write(path, annotation)

    def export(self, output='client', **kwargs):
        return build_client_package(REPO, self.source, self.root / output, **kwargs)

    def test_new_version_normalizes_only_annotation_and_preserves_source_evidence(self):
        before = sample_hashes(self.sample)
        result = self.export()
        sample = Path(result['output']) / 'samples' / self.sample.name
        data = validate_client_sample(sample)
        step = data['steps'][2]
        self.assertEqual(step['tool_call']['arguments'], {'keys': ['ctrl', 'a']})
        self.assertEqual(step['action']['input_text'], 'ctrl+a')
        self.assertEqual(step['action']['target_text'], 'Ctrl+A')
        self.assertEqual(sample_hashes(self.sample), before)
        after = sample_hashes(sample)
        self.assertNotEqual(before['annotation.json'], after['annotation.json'])
        self.assertEqual({k: v for k, v in before.items() if k != 'annotation.json'},
                         {k: v for k, v in after.items() if k != 'annotation.json'})
        provenance = json.loads(Path(result['evidence_output']).read_text())
        self.assertEqual(provenance['schema_version'], 'webcollect-action-normalization-provenance-1')
        self.assertFalse(provenance['capture_binding'])
        self.assertTrue(provenance['requires_fresh_export_review'])
        row = provenance['samples'][0]
        self.assertEqual(row['source_annotation_sha256'], before['annotation.json'])
        self.assertEqual(row['export_annotation_sha256'], after['annotation.json'])
        self.assertNotIn('annotation_sha256', row)
        self.assertEqual(row['action_normalization_changes'][0]['step_id'], 3)
        self.assertEqual(row['action_normalization_changes'][0]['before']['tool_call']['arguments'],
                         {'keys': ['meta', 'a']})

    def test_legacy_source_is_readable_but_new_delivery_requires_canonical_ctrl_a(self):
        with self.assertRaisesRegex(ValueError, 'Windows keyboard delivery'):
            validate_client_sample(self.sample)
        validate_client_sample(self.sample, allow_legacy_hotkeys=True)
        result = self.export()
        second = build_client_package(REPO, result['output'], self.root / 'second')
        self.assertEqual(sample_hashes(Path(result['output']) / 'samples' / self.sample.name),
                         sample_hashes(Path(second['output']) / 'samples' / self.sample.name))

    def test_normalization_cannot_resign_old_review_records(self):
        path = self.root / 'review.json'
        write(path, {'schema_version': 'qc-review-1', 'records': [review(self.sample)]})
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Normalized annotations require fresh QC reviews'):
            self.export(reviews=path)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / 'client').exists())

    def test_paste_and_named_keys_use_the_same_versioned_export_path(self):
        for index, (keys, old_label, expected, label) in enumerate((
                (['meta','v'], 'Command+V', ['ctrl','v'], 'Ctrl+V'),
                (['meta','c'], 'Command+C', ['ctrl','c'], 'Ctrl+C'),
                (['Home'], 'HOME', ['home'], 'Home'),
                (['Return'], '回车键', ['enter'], 'Enter'))):
            with self.subTest(keys=keys):
                path = self.sample / 'annotation.json'
                annotation = json.loads(path.read_text()); step = annotation['steps'][2]
                step['action'].update(input_text='+'.join(keys), target_text=old_label)
                step['tool_call']['arguments'] = {'keys': keys}
                write(path, annotation); before = sample_hashes(self.sample)
                result = self.export(output='case'+str(index))
                data = validate_client_sample(Path(result['output'])/'samples'/self.sample.name)
                actual = data['steps'][2]
                self.assertEqual(actual['tool_call']['arguments']['keys'], expected)
                self.assertEqual(actual['action']['input_text'], '+'.join(expected))
                self.assertEqual(actual['action']['target_text'], label)
                self.assertEqual(sample_hashes(self.sample), before)


if __name__ == '__main__':
    unittest.main()
