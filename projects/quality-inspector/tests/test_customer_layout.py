"""Customer output is the input; capture archives are optional bound evidence."""
import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from quality_inspector import engine
from quality_inspector.checksums import write_manifest
from quality_inspector.duplicates import analyze
from quality_inspector.external_evidence import load as load_evidence, evidence_hashes
from quality_inspector.format_checks import CSV_FIELDS, run as format_run, sample_check
from quality_inspector.layout import discover
from quality_inspector.reporting import review_data, write_outputs


REPO = Path(__file__).resolve().parents[3]
PROFILE = REPO / 'projects/quality-inspector/config/local-pilot-v1.json'


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(temporary, count=1):
    """Small valid source captures and a separately assembled customer package."""
    source = temporary / 'source' / 'B1'
    client = temporary / 'client'
    rows = []
    sidecar = {'schema_version': 'webcollect-client-evidence-1', 'samples': []}
    for number in range(count):
        sid = f'S{number:06}_sample_000001'
        sample = source / 'samples' / sid
        steps = []
        for step in range(1, 7):
            image = sample / 'images' / f'step_{step:03}.png'
            image.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (100, 80), (number, step * 20, 40)).save(image)
            element = dict(element_id='e1', parent_id='root', element_type='button',
                           native_role='button', text='按钮', bbox=[10, 10, 50, 40],
                           clickable=True, inputable=False, scrollable=False,
                           visible=True, enabled=True, state='default')
            tree = dict(image_path=f'images/step_{step:03}.png', screen_resolution=[100, 80], elements=[element])
            put(sample / 'ui_tree' / f'step_{step:03}.json', tree)
            action = dict(action_type='click' if step < 6 else 'complete', target_element_id='e1' if step < 6 else '',
                          target_text='按钮' if step < 6 else '', coordinate=[25, 25] if step < 6 else [], input_text='',
                          precondition='页面显示按钮', expected_result='页面显示完成结果')
            if step < 6:
                action['target_bbox'] = element['bbox']
            arguments = {'x': 25, 'y': 25} if step < 6 else {'status': 'success'}
            tool = dict(tool_name=action['action_type'], call_id=f'{sid}-{step}', arguments=arguments,
                        timestamp='2026-10-23T12:00:00+08:00', context='网页')
            record = dict(step_id=step, image_path=tree['image_path'], ui_tree_path=f'ui_tree/step_{step:03}.json',
                          page_name='测试网页', user_goal='查看公开内容', action=action, tool_call=tool,
                          tool_result=dict(status='success', return_value={'screen_changed': True} if step < 6 else {}, error=''),
                          next_step_rationale='当前按钮可见，继续查看', step_result='页面显示公开内容', exception_evidence=[])
            steps.append(record)
            put(source / 'evidence' / sid / f'step_{step:03}.json',
                dict(step_id=step, state=dict(tree, visible_text='公开内容', values=[], url='https://example.org/'),
                     capture={'screenshot_sha256': digest(image)},
                     executed_action={'tool_name': tool['tool_name'], 'arguments': arguments},
                     final_assertions=[{'passed': True}] if step == 6 else []))
        annotation = dict(sample_id=sid, task_instruction='连续查阅五项公开内容并核对结果', task_type=['数据查看'],
                          terminal_type='Web', device_info=dict(device_model='', os_name='macOS', os_version='', screen_resolution=[100, 80]),
                          app_info=dict(app_name='测试站点', app_version='', environment='真实网页', ui_language='zh'),
                          risk_level='normal', trajectory_source=dict(source_type='agent', data_type='test_agent', action_space='unified_gui_v4'),
                          steps=steps, final_state_image=steps[-1]['image_path'], final_result='页面显示完成结果',
                          completion_status='success', completion_judgement='最终页面可核对完成结果')
        put(sample / 'annotation.json', annotation)
        truth = [dict(step_id=step['step_id'], element_id=step['action']['target_element_id'],
                      text=step['action']['target_text'], bbox=step['action']['target_bbox']) for step in steps[:-1]]
        put(source / 'evidence' / sid / 'ground_truth.json', truth)
        shutil.copytree(sample, client / 'samples' / sid)
        put(client / 'ground_truth' / f'{sid}.json', truth)
        rows.append(dict(sample_id=sid, site_id='SITE1', site_category='学习教育', app_name='测试站点', task_type='["数据查看"]',
                         task_instruction=annotation['task_instruction'], steps='6', screen_resolution='[100, 80]', completion_status='success',
                         actions=json.dumps([s['action']['action_type'] for s in steps]),
                         bytes=str(sum(p.stat().st_size for p in sample.rglob('*') if p.is_file()))))
        sidecar['samples'].append(dict(sample_id=sid, source_sample_path=str(sample), source_batch_path=str(source),
                                       annotation_sha256=digest(sample / 'annotation.json'), evidence_sha256=evidence_hashes(sample),
                                       ground_truth_sha256=digest(client / 'ground_truth' / f'{sid}.json'),
                                       source_manifest_path=str(source / 'manifest.json')))
    put(source / 'manifest.json', dict(sites=[dict(site_id='SITE1', uri='https://example.org/', site_category='学习教育')],
                                      samples=[row['sample_id'] for row in rows]))
    for root in [source, client]:
        root.mkdir(parents=True, exist_ok=True)
        with (root / 'metadata.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader(); writer.writerows(rows)
        (root / 'qc_report.md').write_text('测试报告；客户验收未知。\n')
        (root / 'README.md').write_text('测试输入，不表示真实采集。\n')
        (root / '合成方式说明.md').write_text('## test_agent\nagent / unified_gui_v4\n')
        (root / '来源与合规说明.md').write_text('公开测试内容。\n')
        for name in ['附件A-字段说明.md', '附件B-动作空间与坐标系.md']:
            # Installed authority only; these synthetic fixtures never consult
            # repository request directories or isolated reference sample data.
            shutil.copyfile(Path(engine.__file__).parent / 'authority' / name, root / name)
        (root / '动作空间与系统提示.md').write_text('## test_agent\n使用统一动作空间。\n')
        write_manifest(root)
    put(client / 'site-list.json', dict(schema_version='webcollect-site-list-1', sites=[dict(site_id='SITE1', uri='https://example.org/', site_category='学习教育', sample_ids=[r['sample_id'] for r in rows])], samples=[dict(sample_id=r['sample_id'], site_id='SITE1') for r in rows]))
    (client / 'SHA256SUMS').unlink(); write_manifest(client)
    for record in sidecar['samples']:
        record['source_manifest_sha256'] = digest(source / 'manifest.json')
        directory = source / 'evidence' / record['sample_id']
        record['raw_evidence_files_sha256'] = {p.relative_to(source).as_posix(): digest(p) for p in directory.rglob('*') if p.is_file()}
    index = temporary / 'external-evidence.json'
    put(index, sidecar)
    return source, client, index


class CustomerLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        # Layout regressions bind only an explicit disposable reference scope.
        # Production authority and historical customer samples are not inputs.
        self.baseline = self.root / 'synthetic-reference.json'
        put(self.baseline, {'repository_root': str(REPO), 'samples': [],
            'supplemental_documents': [],
            'known_limits': ['Synthetic layout fixture; no historical sample is read.']})

    def tearDown(self):
        self.temporary.cleanup()

    def test_flat_18_is_discovered_by_format_and_duplicates(self):
        _, client, _ = fixture(self.root, 18)
        result = format_run(REPO, client)
        self.assertEqual(result['sample_count'], 18)
        self.assertEqual(result['confirmed_sample_format_pass'], 18)
        self.assertEqual(result['confirmed_batch_contract_fail'], 0)
        self.assertEqual(result['package_errors'], [])
        self.assertEqual(analyze(client)['pair_comparisons'], 153)

    def test_flat_without_raw_is_review_required_and_reviews_bind_client(self):
        _, client, _ = fixture(self.root)
        report = engine.inspect(self.baseline, client, profile=PROFILE)
        sample = report['samples'][0]
        checks = {check['rule_id']: check for check in sample['checks']}
        for name in ['CAPTURE_INTEGRITY', 'FINAL_MACHINE_EVIDENCE', 'PREPARATION_INTEGRITY', 'EXTERNAL_CAPTURE_BINDING']:
            self.assertEqual(checks[name]['status'], 'REVIEW_REQUIRED', name)
        self.assertTrue(Path(sample['sample_path']).is_relative_to(client.resolve()))
        self.assertEqual(sample['annotation_sha256'], digest(Path(sample['sample_path']) / 'annotation.json'))
        viewer = review_data(report)
        self.assertEqual(len(viewer['samples']), 1)
        self.assertTrue(viewer['samples'][0]['binding_valid'])
        self.assertTrue(any(d['relative_path'] == '附件B-动作空间与坐标系.md' for d in viewer['package_documents']))
        self.assertEqual(report['input_integrity']['status'], 'PASS')
        self.assertEqual(report['acceptance_scopes']['pilot']['statistics']['source_attribution']['status'], 'PASS')

    def test_complete_bound_external_evidence_is_used(self):
        source, client, index = fixture(self.root)
        report = engine.inspect(self.baseline, client, evidence=index)
        checks = {check['rule_id']: check for check in report['samples'][0]['checks']}
        for name in ['EXTERNAL_CAPTURE_BINDING', 'CAPTURE_INTEGRITY', 'FINAL_MACHINE_EVIDENCE']:
            self.assertEqual(checks[name]['status'], 'PASS', name)
        self.assertEqual(report['external_evidence']['status'], 'PASS')
        customer_annotation = Path(report['samples'][0]['sample_path']) / 'annotation.json'
        self.assertEqual(report['input_files_sha256'][customer_annotation.relative_to(client.resolve()).as_posix()], report['samples'][0]['annotation_sha256'])

    def test_bound_customer_report_writes_all_cli_outputs(self):
        _, client, index = fixture(self.root)
        report = engine.inspect(self.baseline, client, evidence=index, profile=PROFILE)
        before = {p.relative_to(client).as_posix(): digest(p)
                  for p in client.rglob('*') if p.is_file()}
        output = self.root / 'qc'
        write_outputs(report, output)
        for name in ['report.json', '报告.md', 'review.html', 'review-template.json']:
            self.assertTrue((output / name).is_file(), name)
        self.assertEqual(before, {p.relative_to(client).as_posix(): digest(p)
                                  for p in client.rglob('*') if p.is_file()})
        self.assertIn('[batch] PASS', (output / '报告.md').read_text())

    def test_customer_and_source_tampering_are_rejected(self):
        source, client, index = fixture(self.root)
        raw = next((source / 'evidence').glob('*/step_001.json'))
        raw.write_text(raw.read_text() + ' ')
        self.assertEqual(load_evidence(index, discover(client))['status'], 'FAIL')
        # Binding the modified archive explicitly is allowed only after its new hash is declared;
        # changing customer bytes must still fail independently of capture hashes.
        value = json.loads(index.read_text())
        value['samples'][0]['raw_evidence_files_sha256'][raw.relative_to(source).as_posix()] = digest(raw)
        put(index, value)
        self.assertEqual(load_evidence(index, discover(client))['status'], 'PASS')
        annotation = next(client.glob('samples/*/annotation.json'))
        data = json.loads(annotation.read_text()); data['final_result'] = '另一结果'; put(annotation, data)
        self.assertEqual(load_evidence(index, discover(client))['status'], 'FAIL')
        report = engine.inspect(self.baseline, client, evidence=index)
        checks = {check['rule_id']: check['status'] for check in report['samples'][0]['checks']}
        self.assertEqual(checks['EXTERNAL_CAPTURE_BINDING'], 'FAIL')
        self.assertEqual(checks['CAPTURE_INTEGRITY'], 'REVIEW_REQUIRED')

    def test_explicitly_unavailable_raw_never_bypasses_sample_binding(self):
        _, client, index = fixture(self.root)
        value = json.loads(index.read_text()); row = value['samples'][0]
        row.update(source_sample_path=str(next(client.glob('samples/*'))), source_batch_path=None,
                   source_manifest_path=None, source_manifest_sha256=None, raw_evidence_files_sha256={}, machine_evidence_status='UNAVAILABLE')
        put(index, value)
        self.assertEqual(load_evidence(index, discover(client))['status'], 'REVIEW_REQUIRED')
        row['annotation_sha256'] = '0' * 64; put(index, value)
        self.assertEqual(load_evidence(index, discover(client))['status'], 'FAIL')

    def test_legacy_batch_layout_remains_supported(self):
        source, _, _ = fixture(self.root)
        legacy = source.parent
        format_result = format_run(REPO, legacy)
        self.assertEqual(format_result['layout'], 'legacy-batches')
        self.assertEqual(format_result['confirmed_sample_format_pass'], 1)
        report = engine.inspect(self.baseline, legacy)
        checks = {check['rule_id']: check['status'] for check in report['samples'][0]['checks']}
        self.assertEqual(checks['CAPTURE_INTEGRITY'], 'PASS')
        self.assertEqual(checks['FINAL_MACHINE_EVIDENCE'], 'PASS')

    def test_extra_empty_directory_bad_layout_and_bad_annex_b_parameters_fail(self):
        _, client, _ = fixture(self.root)
        sample = next(client.glob('samples/*'))
        (sample / 'empty-extra').mkdir()
        self.assertTrue(any(e['rule_id'] == 'C05' for e in sample_check(sample)['errors']))
        (client / 'samples' / 'missing-annotation').mkdir()
        self.assertTrue(discover(client).errors)
        annotation = sample / 'annotation.json'; data = json.loads(annotation.read_text())
        data['steps'][0]['tool_call']['arguments']['selector'] = '#private'
        put(annotation, data)
        self.assertTrue(any(e['rule_id'] == 'C09' for e in sample_check(sample)['errors']))

    def test_flat_missing_annotation_is_a_failure_not_a_smaller_denominator(self):
        _, client, _ = fixture(self.root)
        (client / 'samples' / 'incomplete-sample').mkdir()
        report = engine.inspect(self.baseline, client)
        self.assertEqual(report['sample_count'], 2)
        self.assertEqual(report['status'], 'FAIL')
        self.assertTrue(report['format_layer_summary']['package_errors'])

    def test_system_prompt_chapter_and_original_annex_b_are_checked(self):
        _, client, _ = fixture(self.root)
        (client / '动作空间与系统提示.md').write_text('## unrelated\n不是同名章节。')
        result = format_run(REPO, client)
        self.assertTrue(any('data_type' in e['message'] for e in result['package_errors']))
        (client / '附件B-动作空间与坐标系.md').write_text('被改写的动作空间。')
        result = format_run(REPO, client)
        self.assertTrue(any('Annex B differs' in e['message'] for e in result['package_errors']))

    def test_site_list_mapping_conflict_is_not_accepted_from_valid_categories(self):
        _, client, _ = fixture(self.root)
        path = client / 'site-list.json'; data = json.loads(path.read_text())
        data['samples'][0]['site_id'] = 'SOME_OTHER_SITE'; put(path, data)
        report = engine.inspect(self.baseline, client, profile=PROFILE)
        attribution = report['acceptance_scopes']['pilot']['statistics']['source_attribution']
        self.assertEqual(attribution['status'], 'FAIL')
        self.assertTrue(any('mapping mismatch' in error for error in attribution['errors']))

    def test_missing_sidecar_and_tampered_manifest_never_grant_raw_access(self):
        source, client, index = fixture(self.root)
        missing = load_evidence(self.root / 'missing.json', discover(client))
        self.assertEqual(missing['status'], 'FAIL')
        manifest = source / 'manifest.json'; manifest.write_text(manifest.read_text() + ' ')
        report = engine.inspect(self.baseline, client, evidence=index)
        checks = {check['rule_id']: check['status'] for check in report['samples'][0]['checks']}
        self.assertEqual(checks['EXTERNAL_CAPTURE_BINDING'], 'FAIL')
        self.assertEqual(checks['FINAL_MACHINE_EVIDENCE'], 'REVIEW_REQUIRED')

    def test_hotkey_requires_key_name_and_web_final_state_image_is_required(self):
        _, client, _ = fixture(self.root)
        sample = next(client.glob('samples/*')); path = sample / 'annotation.json'; data = json.loads(path.read_text())
        data.pop('final_state_image'); put(path, data)
        self.assertTrue(any(e['rule_id']=='C10' and e['path']=='final_state_image' for e in sample_check(sample)['errors']))
        step = data['steps'][0]; step['action'].update(action_type='hotkey', target_element_id='', target_text='', input_text='enter', coordinate=[])
        step['action'].pop('target_bbox'); step['tool_call'].update(tool_name='hotkey', arguments={'keys': ['enter']}); put(path, data)
        self.assertTrue(any(e['rule_id'] == 'C09' and 'Hotkey must name' in e['message'] for e in sample_check(sample)['errors']))

    def test_input_change_during_check_cannot_keep_pass(self):
        _, client, _ = fixture(self.root)
        original = engine.analyze
        def change_input(*args, **kwargs):
            result = original(*args, **kwargs)
            (client / 'README.md').write_text('质检进行中被修改。')
            return result
        with patch.object(engine, 'analyze', change_input):
            report = engine.inspect(self.baseline, client)
        self.assertEqual(report['input_integrity']['status'], 'FAIL')
        self.assertEqual(report['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
