"""Controlled protocol tests only: authored bytes/labels are not real calibration."""
from copy import deepcopy
import csv
import hashlib
import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from test_customer_layout import fixture, put
from quality_inspector import batch_decision as decision
from quality_inspector import engine
from quality_inspector.checksums import write_manifest
from quality_inspector.cumulative import build_set_manifest
from quality_inspector.profiles import DEFAULT_DELIVERY_PROFILE, package_files
from quality_inspector.reporting import review_template
from quality_inspector.reviews import SEMANTIC
from webcollect.batch_core import load_json
from webcollect.planning import object_sha256


def seal(root):
    metadata = root / 'metadata.csv'
    with metadata.open(newline='') as stream:
        reader = csv.DictReader(stream); names = reader.fieldnames; rows = list(reader)
    for row in rows:
        sample = root / 'samples' / row['sample_id']
        row['bytes'] = str(sum(path.stat().st_size for path in sample.rglob('*') if path.is_file()))
    with metadata.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=names); writer.writeheader(); writer.writerows(rows)
    (root / 'SHA256SUMS').unlink(missing_ok=True)
    write_manifest(root)


def batch(root, count=6, *, negative=False, balanced=False, seed=410):
    _, client, _ = fixture(root, count)
    rng = random.Random(seed)
    for index, sample in enumerate(sorted((client / 'samples').iterdir())):
        annotation = load_json(sample / 'annotation.json')
        annotation['task_instruction'] = ''.join(chr(0x4e00 + rng.randrange(2000)) for _ in range(45))
        annotation['_controlled_failure'] = negative and index == count - 1
        for step in annotation['steps']:
            step['page_name'] = '协议测试状态' + str(index)
            Image.frombytes('RGB', (100, 80), rng.randbytes(100 * 80 * 3)).save(sample / step['image_path'])
        put(sample / 'annotation.json', annotation)
    with (client / 'metadata.csv').open(newline='') as stream:
        reader = csv.DictReader(stream); names = reader.fieldnames; rows = list(reader)
    sites = []; assignments = []; categories = ['学习教育', '新闻资讯', '生活服务', '休闲娱乐', '实用工具']
    for index, row in enumerate(rows):
        annotation = load_json(client / 'samples' / row['sample_id'] / 'annotation.json')
        row['task_instruction'] = annotation['task_instruction']
        if balanced: row.update(site_id='SITE' + str(index), site_category=categories[index % len(categories)])
        assignments.append({'sample_id': row['sample_id'], 'site_id': row['site_id']})
        if balanced:
            sites.append({'site_id': row['site_id'], 'uri': 'https://example.org/tool/' + str(index),
                          'site_category': row['site_category'], 'sample_ids': [row['sample_id']]})
    if not balanced:
        sites = [{'site_id': 'SITE1', 'uri': 'https://example.org/tool', 'site_category': '学习教育',
                  'sample_ids': [row['sample_id'] for row in rows]}]
    with (client / 'metadata.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=names); writer.writeheader(); writer.writerows(rows)
    put(client / 'site-list.json', {'schema_version': 'webcollect-site-list-1', 'sites': sites, 'samples': assignments})
    (client / '合成方式说明.md').write_text('## test_agent\nagent unified_gui_v4\n## 动作映射\n按附件B动作参数。\n## 坐标\n截图像素整数。\n## 界面变化判定\n独立协议测试。\n## 文字字段生成方式\n合成测试，未使用模型，不表示真实采集。\n')
    (client / '来源与合规说明.md').write_text('## 采集方式\n独立离线夹具。\n## 访问频率策略\n不联网。\n## 账号与脱敏\n没有账号和真实个人信息。\n## 站点清单\n见site-list.json。\n')
    seal(client)
    return client


def reviews(dataset, path, ids=None, *, negative=False):
    report = engine.inspect(None, dataset, profile=DEFAULT_DELIVERY_PROFILE, inspection_stage='payload')
    value = review_template(report); value.pop('package_review', None)
    records = []
    for row in value['records']:
        if ids is not None and row['sample_id'] not in ids: continue
        annotation = load_json(Path(dataset) / 'samples' / row['sample_id'] / 'annotation.json')
        steps = [step['step_id'] for step in annotation['steps']]
        row['reviewer'] = {'kind': 'ai', 'name': 'CONTROLLED TEST AUTHOR; NOT A REAL REVIEW'}
        row['provenance'] = {'description': 'Independently authored protocol labels only; no production acceptance', 'frames_viewed': steps}
        row['step_observations'] = [{'step_id': step, 'note': 'CONTROLLED authored observation, not real pixels'} for step in steps]
        state = 'FAIL' if negative and annotation['_controlled_failure'] else 'PASS'
        row['checks'] = {name: {'status': state, 'note': 'CONTROLLED independent expected label', 'evidence_steps': steps} for name in SEMANTIC}
        records.append(row)
    value['records'] = records
    document = value['delivery_document_review']
    document['reviewer'] = {'kind': 'ai', 'name': 'CONTROLLED TEST AUTHOR'}
    document['provenance'] = {'description': 'Controlled documentary binding test only'}
    for result in document['checks'].values():
        result.update(status='PASS', note='Controlled actual fixture protocol expectation',
                      evidence=[{'path': 'README.md', 'sha256': document['payload_files_sha256']['README.md'],
                                 'detail': 'Controlled evidence fixture, no production document review'}])
    put(path, value)
    return path


def controlled_validator(context):
    """Deliberately artificial marker oracle, NEVER registered in production."""
    root = Path(context['sample_path']); annotation = context['annotation']
    evidence = [{'path': 'annotation.json', 'sha256': hashlib.sha256((root / 'annotation.json').read_bytes()).hexdigest(),
                 'detail': 'CONTROLLED marker only; not visual semantic evidence'}]
    for step in annotation['steps']:
        for name in ('image_path', 'ui_tree_path'):
            evidence.append({'path': step[name], 'sha256': hashlib.sha256((root / step[name]).read_bytes()).hexdigest(),
                             'detail': 'CONTROLLED immutable frame/tree reference only'})
    return {'scope': {'uri': context['uri'], 'task_family': context['task_family'],
                      'business_rule': 'CONTROLLED-TEST-ONLY', 'business_rule_version': '1'},
            'checks': {name: {'status': 'FAIL' if annotation.get('_controlled_failure') else 'PASS',
                              'reason': 'CONTROLLED marker evaluation only', 'evidence': evidence} for name in SEMANTIC}}


class BatchDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.dataset = batch(self.root / 'current')
        self.manifest = self.root / 'effective-set.json'; put(self.manifest, build_set_manifest([self.dataset]))

    def full_reviews(self):
        return reviews(self.dataset, self.root / 'reviews.json')

    def decide(self, **kwargs):
        return decision.decide(self.dataset, self.manifest, **kwargs)

    def register(self):
        registry = {'controlled': {'version': '1', 'evaluate': controlled_validator}}
        context = patch.dict(decision._VALIDATORS, registry, clear=True); context.start(); self.addCleanup(context.stop)

    def calibration(self, *, negative=True):
        self.register(); dataset = batch(self.root / 'calibration', 2, negative=negative, seed=990)
        source = reviews(dataset, self.root / 'calibration-reviews.json', negative=negative)
        path = self.root / 'calibration.json'
        decision.prepare_calibration(dataset, source, 'controlled', path)
        return path

    def plan(self, calibration=None):
        path = self.root / 'selection.json'
        decision.prepare_plan(self.dataset, self.manifest, path, calibration=calibration)
        return path

    def test_fully_reviewed_batch_has_internal_pass_without_waiving_distribution(self):
        before = package_files(self.dataset)
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('No network')):
            result = self.decide(reviews=self.full_reviews())
        self.assertEqual(result['internal_batch_decision'], 'PASS')
        self.assertEqual(result['delivery_distribution']['status'], 'FAIL')
        self.assertEqual(result['unchanged_delivery_status'], 'FAIL')
        self.assertFalse(result['release_ready']); self.assertEqual(before, package_files(self.dataset))
        self.assertEqual(result['candidate']['profile']['configuration']['targets']['expected_samples'], None)
        self.assertNotIn('DELIVERY_EXPECTED_SAMPLES', [c['rule_id'] for c in result['candidate_qc']['dataset_checks']])

    def test_unreviewed_real_protocol_is_hold_and_no_production_validators_exist(self):
        self.assertEqual(decision._VALIDATORS, {})
        result = self.decide()
        self.assertEqual(result['internal_batch_decision'], 'HOLD')
        self.assertEqual(result['review_status_counts'], {'REVIEW_REQUIRED': 6})
        self.assertTrue(all(not r['actual_ai_reviewed'] for r in result['rows']))

    def test_balanced_full_review_keeps_payload_not_release_ready(self):
        self.dataset = batch(self.root / 'balanced', 5, balanced=True)
        put(self.manifest, build_set_manifest([self.dataset]))
        result = self.decide(reviews=self.full_reviews())
        self.assertEqual(result['internal_batch_decision'], 'PASS')
        self.assertEqual(result['delivery_distribution']['status'], 'PASS')
        self.assertEqual(result['unchanged_delivery_status'], 'PASS')
        self.assertFalse(result['release_ready'])

    def test_partial_without_supported_detector_cannot_pass_random_plan(self):
        plan = self.plan(); self.assertEqual(len(load_json(plan)['rows']), 6)
        path = reviews(self.dataset, self.root / 'partial.json', {load_json(plan)['rows'][0]['sample_id']})
        result = self.decide(reviews=path, sampling_plan=plan)
        self.assertEqual(result['internal_batch_decision'], 'HOLD')
        self.assertTrue(all(r['selection']['risk_required'] for r in result['rows']))

    def test_calibrated_scoped_sampling_executes_detector_and_retains_unreviewed(self):
        calibration = self.calibration(); plan = self.plan(calibration)
        selected = {r['sample_id'] for r in load_json(plan)['rows'] if r['selected']}
        self.assertEqual(len(selected), 2)
        path = reviews(self.dataset, self.root / 'selected.json', selected)
        result = self.decide(reviews=path, sampling_plan=plan, calibration=calibration)
        self.assertEqual(result['internal_batch_decision'], 'PASS')
        self.assertEqual(result['review_status_counts'], {'PASS': 2, 'REVIEW_REQUIRED': 4})
        self.assertEqual(sum(r['actual_ai_reviewed'] for r in result['rows']), 2)
        self.assertEqual(sum(r['batch_evidence_basis'] == 'validated-machine-checks-and-sampling' for r in result['rows']), 4)
        self.assertFalse(result['release_ready'])

    def test_missing_random_selection_review_holds_even_when_machine_passes(self):
        calibration = self.calibration(); plan = self.plan(calibration)
        path = reviews(self.dataset, self.root / 'empty.json', set())
        self.assertEqual(self.decide(reviews=path, sampling_plan=plan, calibration=calibration)['internal_batch_decision'], 'HOLD')

    def test_positive_only_calibration_never_creates_support(self):
        calibration = self.calibration(negative=False); plan = self.plan(calibration)
        self.assertTrue(all(row['risk_required'] for row in load_json(plan)['rows']))
        result = self.decide(sampling_plan=plan, calibration=calibration)
        self.assertEqual(result['calibration']['supported'], {})
        self.assertEqual(result['internal_batch_decision'], 'HOLD')

    def test_false_pass_certificate_and_unregistered_validator_rejected(self):
        path = self.root / 'fake.json'; put(path, {'schema_version': 'qc-calibration-PASS', 'status': 'PASS'})
        with self.assertRaisesRegex(ValueError, 'certificates'):
            self.decide(calibration=path)
        put(path, {'schema_version': decision.CALIBRATION_VERSION, 'validator_id': 'self-certified'})
        with self.assertRaisesRegex(ValueError, 'No registered validator'):
            self.decide(calibration=path)

    def test_missed_calibration_defect_is_recomputed_and_rejected(self):
        calibration = self.calibration(); value = load_json(calibration)
        raw = load_json(value['reviews']['path']); raw['records'][-1]['checks']['privacy']['status'] = 'PASS'
        put(Path(value['reviews']['path']), raw)
        value['reviews']['sha256'] = hashlib.sha256(Path(value['reviews']['path']).read_bytes()).hexdigest()
        put(calibration, value)
        with self.assertRaisesRegex(ValueError, 'misclassified'):
            self.decide(calibration=calibration)

    def test_calibration_byte_and_implementation_changes_rejected(self):
        calibration = self.calibration(); value = load_json(calibration)
        source = Path(value['dataset']) / 'README.md'; source.write_text(source.read_text() + 'changed')
        with self.assertRaisesRegex(ValueError, 'Calibration bytes'):
            self.decide(calibration=calibration)
        source.write_text(source.read_text().removesuffix('changed'))
        with patch.object(decision, '_implementation', return_value={'different': 'code'}):
            with self.assertRaisesRegex(ValueError, 'Calibration bytes'):
                self.decide(calibration=calibration)

    def test_changed_exact_uri_is_new_scope_not_calibrated(self):
        calibration = self.calibration()
        source = self.dataset / 'site-list.json'; value = load_json(source); value['sites'][0]['uri'] += '/new-page'; put(source, value)
        seal(self.dataset); put(self.manifest, build_set_manifest([self.dataset]))
        plan = self.plan(calibration)
        self.assertTrue(all(r['risk_required'] for r in load_json(plan)['rows']))
        self.assertEqual(self.decide(sampling_plan=plan, calibration=calibration)['internal_batch_decision'], 'HOLD')

    def test_rehashed_selection_or_risk_tampering_rejected(self):
        calibration = self.calibration(); plan = self.plan(calibration)
        value = load_json(plan); value['rows'][0]['selected'] = not value['rows'][0]['selected']
        value.pop('plan_sha256'); value['plan_sha256'] = object_sha256(value); put(plan, value)
        with self.assertRaisesRegex(ValueError, 'recomputed'):
            self.decide(sampling_plan=plan, calibration=calibration)

    def test_sensitive_risk_always_requires_actual_review(self):
        calibration = self.calibration(); source = next(self.dataset.glob('samples/*/annotation.json'))
        value = load_json(source); value['risk_level'] = 'sensitive'; put(source, value)
        seal(self.dataset); put(self.manifest, build_set_manifest([self.dataset]))
        plan = self.plan(calibration); row = next(r for r in load_json(plan)['rows'] if r['sample_id'] == value['sample_id'])
        self.assertTrue(row['risk_required']); self.assertTrue(row['selected'])
        chosen = {r['sample_id'] for r in load_json(plan)['rows'] if r['selected']} - {value['sample_id']}
        path = reviews(self.dataset, self.root / 'missing-risk.json', chosen)
        self.assertEqual(self.decide(sampling_plan=plan, calibration=calibration, reviews=path)['internal_batch_decision'], 'HOLD')

    def test_mechanical_error_not_hidden_by_review(self):
        source = next(self.dataset.glob('samples/*/annotation.json')); value = load_json(source)
        value['steps'][0]['action']['coordinate'] = [9999, 9999]; put(source, value)
        seal(self.dataset); put(self.manifest, build_set_manifest([self.dataset]))
        result = self.decide(reviews=self.full_reviews())
        self.assertEqual(result['internal_batch_decision'], 'FAIL')
        self.assertIn('C08', next(r['rules'] for r in result['reasons'] if r['code'] == 'CANDIDATE_QUALITY_FAILED'))

    def test_missing_document_review_holds(self):
        path = self.full_reviews(); value = load_json(path); value.pop('delivery_document_review'); put(path, value)
        result = self.decide(reviews=path)
        self.assertEqual(result['internal_batch_decision'], 'HOLD')
        self.assertIn('BATCH_EVIDENCE_PENDING', [r['code'] for r in result['reasons']])

    def test_semantic_failure_cannot_be_overridden_by_machine(self):
        calibration = self.calibration(); plan = self.plan(calibration); path = self.full_reviews()
        value = load_json(path); value['records'][0]['checks']['privacy']['status'] = 'FAIL'; put(path, value)
        self.assertEqual(self.decide(reviews=path, sampling_plan=plan, calibration=calibration)['internal_batch_decision'], 'FAIL')

    def test_missing_or_changed_history_refuses_decision(self):
        put(self.manifest, {'schema_version': 'qc-cumulative-set-1', 'packages': []})
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            self.decide()
        put(self.manifest, build_set_manifest([self.dataset]))
        source = self.dataset / 'README.md'; source.write_text(source.read_text() + 'changed')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            self.decide()

    def test_category_waiver_and_output_inside_inputs_rejected(self):
        profile = self.root / 'weak.json'; value = load_json(DEFAULT_DELIVERY_PROFILE)
        value['targets']['category_share'] = 'report-only'; put(profile, value)
        with self.assertRaisesRegex(ValueError, 'cannot waive'):
            self.decide(profile=profile)
        with self.assertRaisesRegex(ValueError, 'outside'):
            decision.write_decision(self.dataset / 'bad.json', self.dataset, self.manifest)
        with self.assertRaisesRegex(ValueError, 'outside'):
            decision.write_decision(self.manifest, self.dataset, self.manifest)

    def test_incomplete_observations_are_not_actual_reviews(self):
        path = self.full_reviews(); value = load_json(path); value['records'][0]['step_observations'].pop(); put(path, value)
        result = self.decide(reviews=path)
        self.assertEqual(result['internal_batch_decision'], 'FAIL')
        self.assertFalse(result['rows'][0]['actual_ai_reviewed'])

    def test_report_preserves_unknown_cost_and_no_external_calls(self):
        output = self.root / 'report.json'
        result = decision.write_decision(output, self.dataset, self.manifest)
        self.assertEqual(result['actual_model_requests'], 0); self.assertEqual(result['actual_network_requests'], 0)
        self.assertEqual(result['usage_and_cost']['upstream_review_cost'], 'UNKNOWN')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            decision.write_decision(output, self.dataset, self.manifest)

    def test_history_image_reuse_blocks_only_candidate_involved_pairs(self):
        historical = batch(self.root / 'history', 1, seed=499)
        old = next((historical / 'samples').iterdir()); original = old.name; new_id = 'S900000_sample_000001'
        target = old.with_name(new_id); old.rename(target)
        annotation = load_json(target / 'annotation.json'); annotation['sample_id'] = new_id
        put(target / 'annotation.json', annotation)
        (historical / 'ground_truth' / (original + '.json')).rename(historical / 'ground_truth' / (new_id + '.json'))
        for name in ('metadata.csv', 'site-list.json'):
            path = historical / name; path.write_text(path.read_text().replace(original, new_id))
        current = next(self.dataset.glob('samples/*/images/step_001.png'))
        shutil.copyfile(current, target / 'images/step_001.png'); seal(historical)
        put(self.manifest, build_set_manifest([historical, self.dataset]))
        result = self.decide(reviews=self.full_reviews())
        self.assertEqual(result['internal_batch_decision'], 'FAIL')
        self.assertEqual(result['cumulative_duplicates']['history_sample_count'], 1)
        self.assertEqual(result['cumulative_duplicates']['candidate_pair_denominator'], 21)
        self.assertTrue(result['cumulative_duplicates']['candidate_involved_hits']['route1'])

    def test_stale_validator_evidence_cannot_be_self_declared_pass(self):
        self.register()
        original = decision._VALIDATORS['controlled']['evaluate']
        def stale(context):
            result = original(context)
            result['checks']['privacy']['evidence'] = [{'path': 'annotation.json', 'sha256': '0' * 64, 'detail': 'forged'}]
            return result
        with patch.dict(decision._VALIDATORS, {'controlled': {'version': '1', 'evaluate': stale}}):
            sample = engine.inspect(None, self.dataset, inspection_stage='payload')['samples'][0]
            with self.assertRaisesRegex(ValueError, 'missing/stale'):
                decision._evaluate('controlled', sample)

    def test_partial_detector_coverage_cannot_waive_other_four_checks(self):
        self.register()
        def terminal_only(context):
            result = controlled_validator(context)
            result['checks'] = {'terminal_semantics': result['checks']['terminal_semantics']}
            return result
        with patch.dict(decision._VALIDATORS, {'controlled': {'version': '1', 'evaluate': terminal_only}}):
            dataset = batch(self.root / 'terminal-calibration', 2, negative=True, seed=777)
            source = reviews(dataset, self.root / 'terminal-reviews.json', negative=True)
            calibration = self.root / 'terminal-calibration.json'
            decision.prepare_calibration(dataset, source, 'controlled', calibration)
            plan = self.plan(calibration)
            self.assertTrue(all(row['risk_required'] for row in load_json(plan)['rows']))
            self.assertEqual(self.decide(calibration=calibration, sampling_plan=plan)['internal_batch_decision'], 'HOLD')

    def test_populated_status_certificate_cannot_change_recomputed_support(self):
        calibration = self.calibration(negative=False); value = load_json(calibration)
        value.update(status='PASS', supported={'made-up': {'checks': SEMANTIC}}); put(calibration, value)
        result = self.decide(calibration=calibration)
        self.assertEqual(result['calibration']['supported'], {})
        self.assertEqual(result['internal_batch_decision'], 'HOLD')

    def test_validator_cannot_replace_all_frames_with_annotation_only(self):
        self.register()
        def incomplete(context):
            result = controlled_validator(context)
            result['checks']['visual_alignment']['evidence'] = result['checks']['visual_alignment']['evidence'][:1]
            return result
        with patch.dict(decision._VALIDATORS, {'controlled': {'version': '1', 'evaluate': incomplete}}):
            sample = engine.inspect(None, self.dataset, inspection_stage='payload')['samples'][0]
            with self.assertRaisesRegex(ValueError, 'original frame/tree'):
                decision._evaluate('controlled', sample)

    def test_current_validator_failure_blocks_even_if_review_claims_pass(self):
        calibration = self.calibration(); source = next(self.dataset.glob('samples/*/annotation.json'))
        value = load_json(source); value['_controlled_failure'] = True; put(source, value)
        seal(self.dataset); put(self.manifest, build_set_manifest([self.dataset]))
        result = self.decide(reviews=self.full_reviews(), calibration=calibration)
        self.assertEqual(result['internal_batch_decision'], 'FAIL')
        self.assertIn('REGISTERED_VALIDATOR_FAILED', [row['code'] for row in result['reasons']])


if __name__ == '__main__':
    unittest.main()
