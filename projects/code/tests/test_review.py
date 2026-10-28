"""Synthetic record fixtures only; no real sample receives a human decision."""
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from webcollect.review import sha, verify_review, main


class ReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.sample = self.root / 'batch/samples/S000001_sample_000001'
        self.sample.mkdir(parents=True)
        (self.sample / 'annotation.json').write_text('{"fixture":true}')
        (self.sample / 'image.png').write_bytes(b'not-a-real-sample-image')
        bundle = self.root / 'review'
        copy = bundle / 'assets' / self.sample.name
        shutil.copytree(self.sample, copy)
        hashes = {p.name: sha(p) for p in self.sample.iterdir()}
        row = {'sample_id': self.sample.name, 'batch_id': 'B20261022_001',
               'batch_path': str(self.root / 'batch'), 'asset_path': 'assets/' + self.sample.name,
               'annotation': {'steps': [{'step_id': 1}, {'step_id': 2}]},
               'annotation_sha256': hashes['annotation.json'], 'source_file_sha256': hashes}
        self.index = bundle / 'index.json'
        self.index.write_text(json.dumps({'samples': [row]}))
        self.index_sha = sha(self.index)
        self.record = {'review_type': 'human_authored', 'reviewer': '测试夹具（非人工验收）',
                       'reviewed_at': '2026-10-22T10:00:00+08:00', 'delivery_ready': False,
                       'records': [{k: row[k] for k in ['sample_id', 'batch_id', 'annotation_sha256', 'source_file_sha256']}]}
        self.record['records'][0].update(decision='pass', visited_steps=[1, 2], alignment=True,
                                         semantics=True, language=True, notes='仅单元测试')
        self.record_path = self.root / 'synthetic-record.json'

    def verify(self):
        self.record_path.write_text(json.dumps(self.record))
        return verify_review(self.record_path, self.index, self.index_sha)

    def test_complete_pending_and_rejected_records_do_not_approve_delivery(self):
        result = self.verify()
        self.assertTrue(result['all_samples_pass'])
        self.assertFalse(result['delivery_ready'])
        entry = self.record['records'][0]
        entry['decision'] = 'pending'
        self.assertFalse(self.verify()['all_samples_reviewed'])
        entry.update(decision='reject', notes='测试退回问题')
        result = self.verify()
        self.assertTrue(result['record_integrity_pass'])
        self.assertTrue(result['all_samples_reviewed'])
        self.assertFalse(result['all_samples_pass'])

    def test_duplicate_missing_and_unknown_samples_are_rejected(self):
        baseline = copy.deepcopy(self.record)
        for mode in ['duplicate', 'missing', 'unknown']:
            with self.subTest(mode=mode):
                self.record = copy.deepcopy(baseline)
                if mode == 'duplicate': self.record['records'] *= 2
                if mode == 'missing': self.record['records'] = []
                if mode == 'unknown': self.record['records'][0]['sample_id'] = 'S999999_sample_999999'
                self.assertFalse(self.verify()['record_integrity_pass'])

    def test_wrong_types_incomplete_pass_and_hash_binding_are_rejected(self):
        baseline = copy.deepcopy(self.record)
        for field, value in [('decision', []), ('visited_steps', [True, 2]), ('visited_steps', [1]),
                             ('visited_steps', [1, 1]), ('alignment', 'true'), ('notes', None),
                             ('annotation_sha256', 'changed'), ('source_file_sha256', {})]:
            with self.subTest(field=field, value=value):
                self.record = copy.deepcopy(baseline)
                self.record['records'][0][field] = value
                self.assertFalse(self.verify()['record_integrity_pass'])
        for field, value in [('reviewer', ''), ('records', False), ('reviewed_at', False),
                             ('reviewed_at', '2026-10-22'), ('delivery_ready', True)]:
            with self.subTest(field=field):
                self.record = copy.deepcopy(baseline); self.record[field] = value
                self.assertFalse(self.verify()['record_integrity_pass'])

    def test_changed_missing_extra_and_escaping_files_are_rejected(self):
        file = self.sample / 'image.png'
        file.write_bytes(b'changed')
        self.assertIn('file_changed', {i['code'] for i in self.verify()['issues']})
        file.unlink()
        self.assertIn('file_unavailable', {i['code'] for i in self.verify()['issues']})
        outside = self.root / 'outside.png'; outside.write_bytes(b'not-a-real-sample-image')
        file.symlink_to(outside)
        self.assertIn('file_unavailable', {i['code'] for i in self.verify()['issues']})
        file.unlink(); file.write_bytes(outside.read_bytes())
        (self.sample / 'extra.txt').write_text('unexpected')
        self.assertIn('file_inventory', {i['code'] for i in self.verify()['issues']})

    def test_changed_review_copy_is_rejected(self):
        (self.index.parent / 'assets' / self.sample.name / 'image.png').write_bytes(b'changed')
        self.assertFalse(self.verify()['record_integrity_pass'])

    def test_cli_exit_codes_overwrite_and_trusted_index(self):
        self.verify()
        def invoke(output, digest=None):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return main([str(self.record_path), '--index', str(self.index),
                             '--expected-index-sha256', digest or self.index_sha, '--report', str(output)])
        self.assertEqual(invoke(self.root / 'pass.json'), 0)
        self.assertEqual(invoke(self.root / 'pass.json'), 2)
        self.assertEqual(invoke(self.root / 'bad-index.json', 'bad'), 2)
        self.assertEqual(invoke(self.sample / 'report.json'), 2)
        self.record['records'][0]['decision'] = 'pending'; self.verify()
        self.assertEqual(invoke(self.root / 'pending.json'), 1)
        self.record_path.write_text('{broken')
        self.assertEqual(invoke(self.root / 'malformed.json'), 1)
        self.record_path.write_text('[]')
        self.assertEqual(invoke(self.root / 'wrong-type.json'), 1)
