"""Contract and evidence boundary tests for the production customer exporter."""
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from PIL import Image
from webcollect.__main__ import main
from webcollect.client_package import (CHECKS, ROOT_FILES, build_client_package, sample_hashes,
                                      sha, validate_client_layout, validate_client_sample)
from webcollect.scaffold import make_step

REPO = Path(__file__).resolve().parents[3]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def fixture(batch, sid='Web_fixture_001'):
    """Pure synthetic unit-test fixture; never submitted as collection evidence."""
    sample = batch / 'samples' / sid
    (sample / 'images').mkdir(parents=True); (sample / 'ui_tree').mkdir()
    specs = [('click', {'x': 15, 'y': 15}), ('type', {'text': '测试'}),
             ('hotkey', {'keys': ['enter']}), ('scroll', {'x': 32, 'y': 24, 'direction': 'down'}),
             ('back', {}), ('complete', {'status': 'success'})]
    steps = [make_step(n, name, args, n == 6) for n, (name, args) in enumerate(specs, 1)]
    truth = []
    for s in steps:
        if 'target_bbox' in s['action']:
            s['action']['target_bbox'] = [5, 5, 30, 20]
            truth.append(dict(step_id=s['step_id'], element_id='e_1', text='测试控件', bbox=[5, 5, 30, 20]))
        Image.new('RGB', (64, 48), 'white').save(sample / s['image_path'])
        write(sample / s['ui_tree_path'], dict(image_path=s['image_path'], screen_resolution=[64, 48], elements=[dict(element_id='e_1', parent_id='root', element_type='input', native_role='textbox', text='测试控件', bbox=[5, 5, 30, 20], clickable=True, inputable=True, scrollable=False, visible=True, enabled=True, state='default')]))
    annotation = dict(sample_id=sid, task_instruction='单元测试轨迹，不是实际采集', task_type=['填写表单'], terminal_type='Web', device_info=dict(device_model='', os_name='macOS', os_version='', screen_resolution=[64, 48]), app_info=dict(app_name='测试页面', app_version='', environment='单元测试', ui_language='zh'), risk_level='normal', trajectory_source=dict(source_type='human', data_type='customer_fixture_v1', action_space='unified_gui_v4'), steps=steps, final_state_image=steps[-1]['image_path'], final_result='测试最终状态', completion_status='success', completion_judgement='本图测试完成')
    write(sample / 'annotation.json', annotation)
    write(batch / 'evidence' / sid / 'ground_truth.json', truth)
    write(batch / 'evidence' / sid / 'step_001.json', {'unit_test_fixture': True})
    manifest_path = batch / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else dict(sample_kind='real', sites=[dict(site_id='site_fixture', uri='https://example.invalid/', site_category='测试')], samples=[], attempts=[])
    manifest['samples'].append(sid); manifest['attempts'].append(dict(sample_id=sid, site_id='site_fixture'))
    write(manifest_path, manifest)
    return sample


def review(sample, status='PASS'):
    hashes = sample_hashes(sample)
    return dict(sample_id=sample.name, baseline_sha256=sha(REPO / 'projects/quality-inspector/config/customer-samples.json'), annotation_sha256=hashes['annotation.json'], evidence_sha256={k: v for k, v in hashes.items() if k != 'annotation.json'}, reviewer=dict(kind='human', name='Unit test fixture'), provenance=dict(description='Synthetic unit-test review only', reviewed_at='2026-10-23T15:00:00Z'), checks={k: dict(status=status, note='Explicit unit-test judgment') for k in CHECKS})


class ClientPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.batch = self.root / 'source'; self.sample = fixture(self.batch)

    def export(self, **kwargs):
        return build_client_package(REPO, self.batch, self.root / 'client', **kwargs)

    def test_direct_batch_default_client_and_byte_preservation(self):
        before = sample_hashes(self.sample); result = self.export(); out = Path(result['output'])
        self.assertEqual(before, sample_hashes(out / 'samples' / self.sample.name))
        self.assertEqual(set(p.name for p in out.iterdir()), ROOT_FILES | {'samples', 'ground_truth'})
        self.assertEqual((out / '附件B-动作空间与坐标系.md').read_bytes(), (REPO / 'request/web操作采集需求/附件B-动作空间与坐标系.md').read_bytes())
        self.assertIn('## customer_fixture_v1', (out / '动作空间与系统提示.md').read_text())
        self.assertEqual(json.loads((out / 'samples' / self.sample.name / 'annotation.json').read_text())['trajectory_source']['source_type'], 'human')
        side = json.loads(Path(result['evidence_output']).read_text())
        self.assertIn('manifest.json', side['samples'][0]['source_files_sha256'])
        self.assertIn('evidence/Web_fixture_001/step_001.json', side['samples'][0]['raw_evidence_files_sha256'])
        self.assertEqual(result['independent_qc_status'], 'NOT_RUN')
        self.assertIn('NOT_RUN', (out / 'qc_report.md').read_text())
        readme = (out / 'README.md').read_text()
        self.assertIn('"site_count": 1', readme)
        self.assertIn('"frames": 6', readme)
        self.assertIn('"step_counts"', readme)
        self.assertIn('"categories"', readme)
        self.assertIn('"task_types"', readme)
        self.assertTrue(validate_client_layout(out)['structural_pass'])
        self.assertRaises(FileExistsError, self.export)

    def test_flat_reexport_keeps_nonproducer_id_source_and_unknown_machine_evidence(self):
        first = self.export(); result = build_client_package(REPO, Path(first['output']), self.root / 'second')
        self.assertEqual(sample_hashes(Path(first['output']) / 'samples' / self.sample.name), sample_hashes(Path(result['output']) / 'samples' / self.sample.name))
        side = json.loads(Path(result['evidence_output']).read_text())
        self.assertEqual(side['samples'][0]['machine_evidence_status'], 'UNAVAILABLE')
        self.assertIsNone(side['samples'][0]['source_manifest_path'])

    def test_web_complete_requires_final_state_image(self):
        path = self.sample / 'annotation.json'; annotation = json.loads(path.read_text())
        del annotation['final_state_image']; write(path, annotation)
        self.assertRaisesRegex(ValueError, 'final_state_image', self.export)

    def test_filter_is_opt_in_preserves_population_and_original_review_records(self):
        other = fixture(self.batch, 'Web_fixture_002'); approved = review(self.sample); rejected = review(other, 'FAIL')
        path = self.root / 'reviews.json'; write(path, dict(schema_version='qc-review-1', records=[approved, rejected], package_review={'old_package': True}))
        result = self.export(reviews=path, approved_only=True)
        side = json.loads(Path(result['evidence_output']).read_text())
        self.assertEqual(side['source_population'], dict(total_samples=2, selected_count=1, excluded_count=1))
        self.assertEqual(side['excluded_samples'][0]['review'], rejected)
        self.assertEqual(side['source_review_records'], [approved, rejected])
        selected = json.loads(Path(result['review_output']).read_text())
        self.assertEqual(selected, dict(schema_version='qc-review-1', records=[approved]))
        second = build_client_package(REPO, self.batch, self.root / 'all', reviews=path)
        self.assertEqual(second['samples'], 2)

    def test_stale_review_hash_or_baseline_rejected(self):
        for field in ('annotation_sha256', 'baseline_sha256'):
            with self.subTest(field=field):
                r = review(self.sample); r[field] = '0' * 64; path = self.root / (field + '.json'); write(path, dict(schema_version='qc-review-1', records=[r]))
                self.assertRaisesRegex(ValueError, 'binding mismatch', self.export, reviews=path, approved_only=True)
        r = review(self.sample); r['evidence_sha256']['images/step_001.png'] = '0' * 64
        path = self.root / 'stale-image.json'; write(path, dict(schema_version='qc-review-1', records=[r]))
        self.assertRaisesRegex(ValueError, 'binding mismatch', self.export, reviews=path, approved_only=True)

    def test_no_implicit_or_placeholder_human_approval(self):
        self.assertRaisesRegex(ValueError, 'requires --reviews', self.export, approved_only=True)
        for mutation in ('note', 'provenance', 'reviewer'):
            r = review(self.sample)
            if mutation == 'note': r['checks']['language']['note'] = ''
            elif mutation == 'provenance': r['provenance'] = {}
            else: r['reviewer']['kind'] = 'ai'
            path = self.root / (mutation + '.json'); write(path, dict(schema_version='qc-review-1', records=[r]))
            self.assertRaisesRegex(ValueError, 'No selected samples', self.export, reviews=path, approved_only=True)

    def test_missing_or_inconsistent_truth_is_never_invented(self):
        truth = self.batch / 'evidence' / self.sample.name / 'ground_truth.json'
        truth.unlink(); self.assertRaisesRegex(ValueError, 'Missing original capture ground truth', self.export)
        write(truth, []); self.assertRaisesRegex(ValueError, 'truth differs', self.export)
        self.assertFalse((self.root / 'client').exists())

    def test_missing_site_map_cannot_be_inferred(self):
        manifest = self.batch / 'manifest.json'; data = json.loads(manifest.read_text()); data['sites'] = []; write(manifest, data)
        self.assertRaisesRegex(ValueError, 'Missing explicit URI', self.export)

    def test_path_safety_and_duplicate_ids(self):
        self.assertRaises(ValueError, build_client_package, REPO, self.batch, self.batch / 'nested')
        self.assertRaises(ValueError, self.export, evidence_output=self.root / 'client' / 'index.json')
        self.assertRaises(ValueError, self.export, evidence_output=self.batch / 'index.json')
        multi = self.root / 'multi'; shutil.copytree(self.batch, multi / 'b1'); shutil.copytree(self.batch, multi / 'b2')
        self.assertRaisesRegex(ValueError, 'Duplicate sample', build_client_package, REPO, multi, self.root / 'dup')
        image = self.sample / 'images/step_001.png'; image.unlink(); image.symlink_to(self.sample / 'images/step_002.png')
        self.assertRaisesRegex(ValueError, 'symbolic', self.export)

    def test_nested_empty_asset_directory_rejected(self):
        (self.sample / 'images/extra').mkdir()
        self.assertRaisesRegex(ValueError, 'extra directories', self.export)

    def test_tree_image_and_integer_coordinate_contract(self):
        path = self.sample / 'ui_tree/step_001.json'; data = json.loads(path.read_text()); data['image_path'] = 'images/step_002.png'; write(path, data)
        self.assertRaisesRegex(ValueError, 'synchronization', self.export)

    def test_multibatch_and_cli_default(self):
        multi = self.root / 'multi'; shutil.move(str(self.batch), multi / 'first')
        fixture(multi / 'second', 'Web_fixture_002')
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = main(['package', '--source', str(multi), '--output', str(self.root / 'client')])
        self.assertEqual(code, 0); self.assertEqual(json.loads(stdout.getvalue())['samples'], 2)
        self.assertEqual(json.loads(stdout.getvalue())['layout'], 'client')

    def test_candidate_layout_remains_explicit(self):
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = main(['package', '--source', str(self.batch), '--output', str(self.root / 'legacy'), '--layout', 'candidate'])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / 'legacy/candidate_manifest.json').exists())
