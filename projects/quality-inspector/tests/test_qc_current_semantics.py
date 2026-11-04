"""Current contract compatibility using disposable images/actions only."""
import csv
import json
from pathlib import Path
import random
import shutil
import tempfile
import unittest

from PIL import Image
from test_customer_layout import fixture, put
from quality_inspector.checksums import write_manifest
from quality_inspector.cumulative import build_set_manifest, inspect_set
from quality_inspector.format_checks import sample_check
from quality_inspector.profiles import DEFAULT_DELIVERY_PROFILE


class CurrentSemanticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_same_site_different_goals_and_technical_words_are_not_automatic_rejection(self):
        _, client, _ = fixture(self.root, 2)
        goals = ['查阅「Vue API」的参数和类型说明，记录当前文档中的使用方法。',
                 '查看课程安排中的考试日期、报名条件与学分要求，核对公告信息。']
        for index, sample in enumerate(sorted((client / 'samples').iterdir())):
            annotation = json.loads((sample / 'annotation.json').read_text())
            annotation['task_instruction'] = goals[index]
            for step in annotation['steps']:
                step['page_name'] = '技术文档' if index == 0 else '课程公告'
                rng = random.Random(index * 100 + step['step_id'])
                Image.frombytes('RGB', (100, 80), rng.randbytes(100 * 80 * 3)).save(sample / step['image_path'])
            put(sample / 'annotation.json', annotation)
            checked = sample_check(sample)
            self.assertTrue(checked['confirmed_format_pass'], checked['errors'])
            self.assertIn('U03', checked['unknown_rule_ids'])  # Original-image language review is still required.
        with (client / 'metadata.csv').open(newline='') as stream:
            reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
        for row, goal in zip(rows, goals):
            row['task_instruction'] = goal
            row['bytes'] = str(sum(p.stat().st_size for p in (client / 'samples' / row['sample_id']).rglob('*') if p.is_file()))
        with (client / 'metadata.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
        (client / 'SHA256SUMS').unlink(); write_manifest(client)
        profile = json.loads(DEFAULT_DELIVERY_PROFILE.read_text())
        profile['authority'] = 'Explicit disposable two-sample same-site fixture; never a production waiver'
        profile['targets'].update(expected_samples=2, category_share='report-only')
        path = self.root / 'profile.json'; put(path, profile)
        result = inspect_set(build_set_manifest([client]), path)
        self.assertEqual(result['mechanical_status'], 'PASS', result['errors'])
        self.assertEqual(result['site_count'], 1); self.assertEqual(result['sample_count'], 2)
        self.assertEqual(result['semantic_review_status'], 'NOT_EVALUATED')
        samples = sorted((client / 'samples').iterdir())
        shutil.copyfile(samples[0] / 'images/step_001.png', samples[1] / 'images/step_001.png')
        (client / 'SHA256SUMS').unlink(); write_manifest(client)
        rejected = inspect_set(build_set_manifest([client]), path)
        self.assertEqual(rejected['mechanical_status'], 'FAIL')
        self.assertGreater(rejected['duplicates']['route1']['confirmed_pair_count'], 0)

    def test_wait_and_complete_do_not_pad_five_and_short_flow_needs_reason(self):
        _, client, _ = fixture(self.root)
        sample = next((client / 'samples').iterdir())
        self.assertEqual(sample_check(sample)['effective_steps'], 5)
        annotation = json.loads((sample / 'annotation.json').read_text()); step = annotation['steps'][0]
        step['action'].update(action_type='wait', target_element_id='', target_text='', coordinate=[])
        step['action'].pop('target_bbox'); step['tool_call'].update(tool_name='wait', arguments={})
        put(sample / 'annotation.json', annotation)
        checked = sample_check(sample)
        self.assertEqual(checked['total_steps'], 6); self.assertEqual(checked['effective_steps'], 4)
        self.assertTrue(any(row['rule_id'] == 'C11' for row in checked['errors']))
        annotation.update(short_flow=True, short_flow_reason='合成测试中的短片段结束，保留当前页面状态。')
        put(sample / 'annotation.json', annotation)
        self.assertTrue(sample_check(sample)['confirmed_format_pass'])
        annotation['short_flow_reason'] = ''; put(sample / 'annotation.json', annotation)
        self.assertTrue(any(row['rule_id'] == 'C11' for row in sample_check(sample)['errors']))
