"""Strict local-profile acceptance with independent, explicitly synthetic inputs."""
import csv
import hashlib
import json
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1]))
from make_fixture import fixture
from quality_inspector.engine import inspect, SEMANTIC, evidence_files, sha
from quality_inspector.profiles import load, package_review_template
from quality_inspector.reporting import write_outputs

HERE = Path(__file__).parents[1]
REPO = Path(__file__).resolve().parents[3]


def manifests(root):
    for base in sorted(root.glob('batch*')) + [root]:
        entries = [f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(base).as_posix()}\n'
                   for p in sorted(base.rglob('*')) if p.is_file() and p != base / 'SHA256SUMS']
        (base / 'SHA256SUMS').write_text(''.join(entries))


class LocalProfiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.data = self.root / 'data'; self.data.mkdir()
        topics = ['查阅百科中的历史典籍与作者说明', '查询新闻报道的日期来源和航天正文',
                  '查看政务公开的部门职责和办事指南', '查看学习教育课程大纲和考试安排',
                  '查询交通线路的站点换乘和票价说明']
        self.samples = []
        for i, topic in enumerate(topics, 1):
            isolated = self.root / f'fixture{i}'; old = fixture(isolated)
            batch = self.data / f'batch{i}'; shutil.move(str(old.parent.parent), batch)
            old = batch / 'samples' / 'fixture_client_01'; sample = old.with_name(f'fixture_client_{i:02}')
            old.rename(sample); (batch / 'evidence' / 'fixture_client_01').rename(batch / 'evidence' / sample.name)
            a = json.loads((sample / 'annotation.json').read_text()); a['sample_id'] = sample.name
            a['task_instruction'] = topic + '。独立合成测试，不能用于实际交付。'
            for step in a['steps']:
                step['page_name'] = f'独立夹具第{i}页'
                path = sample / step['image_path']; rng = random.Random(100 * i + step['step_id'])
                Image.frombytes('RGB', (32, 24), rng.randbytes(32 * 24 * 3)).resize((640, 480)).save(path)
                raw = batch / 'evidence' / sample.name / f'step_{step["step_id"]:03}.json'
                value = json.loads(raw.read_text()); value['capture']['screenshot_sha256'] = sha(path)
                raw.write_text(json.dumps(value, ensure_ascii=False))
            (sample / 'annotation.json').write_text(json.dumps(a, ensure_ascii=False))
            with (batch / 'metadata.csv').open(newline='') as file:
                reader = csv.DictReader(file); columns = reader.fieldnames; row = next(reader)
            row.update(sample_id=sample.name, site_id=f'fixture-site-{i}', site_category=topic[:4],
                       task_instruction=a['task_instruction'], bytes=str(sum(p.stat().st_size for p in sample.rglob('*') if p.is_file())))
            with (batch / 'metadata.csv').open('w', newline='') as file:
                writer = csv.DictWriter(file, columns); writer.writeheader(); writer.writerow(row)
            (batch / 'manifest.json').write_text(json.dumps({'sample_kind': 'SYNTHETIC UNIT TEST ONLY', 'sites': [
                {'site_id': row['site_id'], 'uri': f'https://fixture{i}.invalid/', 'site_category': row['site_category']}]}))
            self.samples.append(sample)
        shutil.copytree(isolated / 'docs', self.data / 'docs')
        shutil.copyfile(isolated / 'README.md', self.data / 'README.md')
        shutil.copyfile(isolated / 'document_roles.json', self.data / 'document_roles.json')
        (self.data / 'docs/合成方式说明.md').write_text('# fixture-test-line\nunified_gui_v4\n独立合成测试，不是实际审核。')
        manifests(self.data)
        baseline = json.loads((HERE / 'config/customer-samples.json').read_text()); baseline['repository_root'] = str(REPO)
        # This suite exercises local profile aggregation using disposable
        # references, never the historical customer sample paths in the config.
        reference = self.root / 'synthetic-reference'
        shutil.copytree(self.samples[0], reference)
        baseline['samples'] = [{'path': str(reference), 'files': {
            p.relative_to(reference).as_posix(): sha(p) for p in reference.rglob('*') if p.is_file()}}]
        baseline['supplemental_documents'] = [row for row in baseline['supplemental_documents']
                                               if '/samples/' not in row['path']]
        # Keep the historical profile's original authority SHA; isolate this
        # legacy compatibility fixture from current requirement edits.
        legacy=Path(__file__).parent/'fixtures/legacy-clarification-20261026.md'
        for document in baseline['supplemental_documents']:
            if document['path']=='request/需求澄清记录.md':
                self.assertEqual(hashlib.sha256(legacy.read_bytes()).hexdigest(),document['sha256'])
                document['path']=str(legacy.resolve())
        self.baseline = self.root / 'baseline.json'; self.baseline.write_text(json.dumps(baseline, ensure_ascii=False))
        profile = json.loads((HERE / 'config/local-pilot-v1.json').read_text())
        profile['profile_id'] = 'SYNTHETIC-UNIT-TEST-ONLY'; profile['targets'].update(minimum_samples=5, minimum_sites=5)
        self.profile = self.root / 'profile.json'; self.profile.write_text(json.dumps(profile))

    def tearDown(self):
        self.temp.cleanup()

    def report(self, reviews=None):
        return inspect(self.baseline, self.data, reviews=reviews, profile=self.profile)

    def reviewed(self, package=True):
        r = self.report(); value = {'schema_version': 'qc-review-1', 'records': []}
        for sample in r['samples']:
            value['records'].append({'sample_id': sample['sample_id'], 'baseline_sha256': sha(self.baseline),
                'annotation_sha256': sample['annotation_sha256'], 'evidence_sha256': sample['evidence_sha256'],
                'reviewer': {'kind': 'ai', 'name': 'SYNTHETIC UNIT TEST ONLY'},
                'provenance': {'description': 'Tests intake and aggregation with independent synthetic fixtures; not an actual data review.'},
                'checks': {name: {'status': 'PASS', 'note': 'SYNTHETIC TEST expectation only; never a production sign-off.'} for name in SEMANTIC}})
        if package:
            value['package_review'] = package_review_template(r)
            value['package_review'].update(reviewer={'kind': 'ai', 'name': 'SYNTHETIC UNIT TEST ONLY'},
                provenance={'description': 'SYNTHETIC TEST document binding and aggregation, not real review.'},
                checks={name: {'status': 'PASS', 'note': 'Independent unit fixture only, never claims real document/category acceptance.'} for name in value['package_review']['checks']})
        path = self.root / 'reviews.json'; path.write_text(json.dumps(value, ensure_ascii=False)); return path

    def test_local_pass_requires_all_three_scopes_but_external_stays_unknown(self):
        r = self.report(self.reviewed())
        self.assertEqual(r['local_acceptance_status'], 'PASS')
        self.assertTrue(all(r['acceptance_scopes'][s]['status'] == 'PASS' for s in ['sample', 'batch', 'pilot']))
        self.assertEqual(r['acceptance_scopes']['corpus']['status'], 'UNKNOWN')
        self.assertEqual(r['customer_actual_acceptance'], 'UNKNOWN')
        self.assertEqual(r['status'], 'REVIEW_REQUIRED')

    def test_legacy_default_remains_compatible(self):
        r = inspect(self.baseline, self.data)
        self.assertNotIn('local_acceptance_status', r)
        self.assertEqual(r['status'], 'REVIEW_REQUIRED')

    def test_absent_document_review_remains_pending(self):
        r = self.report(self.reviewed(package=False))
        self.assertEqual(r['local_acceptance_status'], 'REVIEW_REQUIRED')
        self.assertEqual(r['acceptance_scopes']['sample']['status'], 'PASS')
        self.assertEqual(r['package_review']['status'], 'REVIEW_REQUIRED')

    def test_missing_sample_semantic_review_cannot_be_overridden_by_package_review(self):
        p = self.reviewed(); d = json.loads(p.read_text()); del d['records'][0]['checks']['language']; p.write_text(json.dumps(d))
        self.assertEqual(self.report(p)['local_acceptance_status'], 'REVIEW_REQUIRED')

    def test_explicit_semantic_failure_is_not_overridden(self):
        p = self.reviewed(); d = json.loads(p.read_text()); d['records'][0]['checks']['terminal_semantics']['status'] = 'FAIL'; p.write_text(json.dumps(d))
        self.assertEqual(self.report(p)['local_acceptance_status'], 'FAIL')

    def test_configured_near_hash_hit_is_fail_even_with_semantic_pass(self):
        p = self.samples[1] / 'annotation.json'; a = json.loads(p.read_text()); a['task_instruction'] = json.loads((self.samples[0] / 'annotation.json').read_text())['task_instruction']; p.write_text(json.dumps(a, ensure_ascii=False))
        r = self.report(self.reviewed())
        self.assertGreater(r['duplicates']['route4']['count'], 0)
        hits = [c for s in r['samples'] for c in s['local_checks'] if c['rule_id'] == 'NEAR_DUPLICATES' and c['status'] == 'FAIL']
        self.assertEqual(len(hits), 2)
        self.assertEqual(r['local_acceptance_status'], 'FAIL')

    def test_exact_shared_frame_cannot_be_exempted_by_review(self):
        shutil.copyfile(self.samples[0] / 'images/step_001.png', self.samples[1] / 'images/step_001.png')
        r = self.report(self.reviewed())
        self.assertEqual(r['duplicates']['route1']['confirmed_pair_count'], 1)
        self.assertTrue(any(c['rule_id'] == 'C17' and c['status'] == 'FAIL' for s in r['samples'] for c in s['local_checks']))
        self.assertEqual(r['local_acceptance_status'], 'FAIL')

    def test_package_review_stale_profile_fails(self):
        p = self.reviewed(); d = json.loads(p.read_text()); d['package_review']['profile_sha256'] = '0' * 64; p.write_text(json.dumps(d))
        self.assertEqual(self.report(p)['package_review']['status'], 'FAIL')

    def test_human_package_and_legacy_sample_pass_allow_empty_written_reasons(self):
        p = self.reviewed(); value = json.loads(p.read_text())
        for record in value['records'] + [value['package_review']]:
            record['reviewer'] = {'kind': 'human', 'name': 'SYNTHETIC HUMAN CLICK ONLY'}
            for check in record['checks'].values():
                check['note'] = ''
        p.write_text(json.dumps(value)); before = p.read_bytes()
        result = self.report(p)
        self.assertEqual(result['review_import']['accepted_count'], 5)
        self.assertEqual(result['package_review']['status'], 'PASS')
        self.assertEqual(result['local_acceptance_status'], 'PASS')
        self.assertEqual(p.read_bytes(), before)

    def test_package_human_fail_ai_pass_and_nonstring_notes_remain_rejected(self):
        for kind, status, note in (('human', 'FAIL', ''), ('ai', 'PASS', ''),
                                   ('ai', 'FAIL', ''), ('human', 'PASS', None)):
            with self.subTest(kind=kind, status=status, note=note):
                p = self.reviewed(); value = json.loads(p.read_text())
                value['package_review']['reviewer']['kind'] = kind
                value['package_review']['checks']['delivery_documentation'].update(
                    status=status, note=note)
                p.write_text(json.dumps(value))
                self.assertEqual(self.report(p)['package_review']['status'], 'FAIL')

    def test_package_review_stale_input_and_missing_note_fail(self):
        p = self.reviewed(); d = json.loads(p.read_text()); d['package_review']['package_files_sha256'] = {}; d['package_review']['checks']['delivery_documentation']['note'] = ''; p.write_text(json.dumps(d))
        self.assertEqual(self.report(p)['package_review']['status'], 'FAIL')

    def test_unreviewed_semantic_categories_cannot_pass_as_document_review(self):
        p = self.reviewed(); d = json.loads(p.read_text()); del d['package_review']['checks']['site_category_attribution']; p.write_text(json.dumps(d))
        self.assertEqual(self.report(p)['package_review']['status'], 'FAIL')

    def test_missing_source_attribution_is_pending_not_pass(self):
        (self.data / 'batch1/manifest.json').unlink()
        r = self.report(); checks = {c['rule_id']: c for c in r['acceptance_scopes']['pilot']['checks']}
        self.assertEqual(checks['PILOT_SOURCE_ATTRIBUTION']['status'], 'REVIEW_REQUIRED')

    def test_metadata_category_cannot_override_recorded_source(self):
        p = self.data / 'batch2/manifest.json'; d = json.loads(p.read_text()); d['sites'][0]['site_category'] = '与原始记录矛盾的分类'; p.write_text(json.dumps(d))
        r = self.report(); checks = {c['rule_id']: c for c in r['acceptance_scopes']['pilot']['checks']}
        self.assertEqual(checks['PILOT_SOURCE_ATTRIBUTION']['status'], 'FAIL')

    def test_duplicate_uri_cannot_inflate_site_count(self):
        p = self.data / 'batch2/manifest.json'; d = json.loads(p.read_text()); d['sites'][0]['uri'] = 'https://fixture1.invalid/'; p.write_text(json.dumps(d))
        r = self.report(); checks = {c['rule_id']: c for c in r['acceptance_scopes']['pilot']['checks']}
        self.assertEqual(checks['PILOT_SOURCE_ATTRIBUTION']['status'], 'FAIL')

    def test_declared_minimum_is_actual_gate(self):
        d = json.loads(self.profile.read_text()); d['targets']['minimum_samples'] = 6; self.profile.write_text(json.dumps(d))
        r = self.report(self.reviewed()); checks = {c['rule_id']: c for c in r['acceptance_scopes']['pilot']['checks']}
        self.assertEqual(checks['PILOT_MINIMUM_SAMPLES']['status'], 'FAIL')
        self.assertEqual(r['local_acceptance_status'], 'FAIL')

    def test_category_share_is_measured_from_all_actual_rows(self):
        path = self.data / 'batch2/metadata.csv'
        with path.open(newline='') as file:
            reader = csv.DictReader(file); columns = reader.fieldnames; row = next(reader)
        row['site_category'] = '查阅百科'
        with path.open('w', newline='') as file:
            writer = csv.DictWriter(file, columns); writer.writeheader(); writer.writerow(row)
        r = self.report(); checks = {c['rule_id']: c for c in r['acceptance_scopes']['pilot']['checks']}
        self.assertEqual(checks['PILOT_CATEGORY_SHARE']['status'], 'FAIL')
        self.assertEqual(checks['PILOT_CATEGORY_SHARE']['actual_maximum'], 0.4)

    def test_short_flow_share_is_not_waived_by_reviewer(self):
        path = self.samples[0] / 'annotation.json'; a = json.loads(path.read_text())
        a.update(short_flow=True, short_flow_reason='合成比例反例测试，不是实际数据')
        path.write_text(json.dumps(a, ensure_ascii=False))
        r = self.report(self.reviewed()); checks = {c['rule_id']: c for c in r['acceptance_scopes']['pilot']['checks']}
        self.assertEqual(checks['PILOT_SHORT_FLOW_SHARE']['status'], 'FAIL')
        self.assertEqual(checks['PILOT_SHORT_FLOW_SHARE']['actual'], 0.2)

    def test_invalid_metadata_or_resolution_remains_fail_report_not_crash(self):
        path = self.data / 'batch2/metadata.csv'; path.write_text('sample_id,site_id,site_category\nfixture_client_02\n')
        path = self.samples[0] / 'annotation.json'; a = json.loads(path.read_text())
        a['device_info']['screen_resolution'] = ['640', 480]; path.write_text(json.dumps(a, ensure_ascii=False))
        r = self.report(); self.assertEqual(r['local_acceptance_status'], 'FAIL')
        self.assertTrue(r['acceptance_scopes']['pilot']['statistics']['missing_facts'])

    def test_algorithm_or_distribution_weakening_is_rejected(self):
        original = json.loads(self.profile.read_text())
        for mutation in ['orientation', 'threshold', 'category']:
            d = json.loads(json.dumps(original))
            if mutation == 'orientation': d['duplicates']['dhash']['orientation'] = 'vertical'
            if mutation == 'threshold': d['duplicates']['simhash']['maximum_hamming'] = 0
            if mutation == 'category': d['targets']['max_category_share'] = 1
            self.profile.write_text(json.dumps(d))
            with self.assertRaises(ValueError): load(self.profile)

    def test_export_defaults_document_review_pending_and_keeps_both_statuses(self):
        out = self.root / 'out'; write_outputs(self.report(), out)
        template = json.loads((out / 'review-template.json').read_text())
        self.assertEqual(template['package_review']['checks']['delivery_documentation']['status'], 'REVIEW_REQUIRED')
        self.assertTrue(template['package_review']['package_files_sha256'])
        self.assertTrue((out / 'requirements-baseline.json').is_file())
        self.assertIn('客户实际验收：UNKNOWN', (out / '报告.md').read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
