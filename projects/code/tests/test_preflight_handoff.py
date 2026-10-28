"""Risk advice must retain every task and cannot bypass integrity or QC."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image
from webcollect.preflight import (SOURCE_FILES, digest, object_digest, pixel_change,
    schedule_plan, validate_preflight_binding, _limits, inspect_page, preflight_plan)


class PreflightHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = {'tasks': [{'task_id': 'first', 'site_uri': 'https://example.org/a',
                                'instruction': '观察正文'},
                               {'task_id': 'second', 'site_uri': 'https://example.org/b',
                                'instruction': '观察工具'}], 'scope': 'fixture'}
        self.records = [{'task_id': task['task_id'], 'task_sha256': object_digest(task),
                         'summary': {'routing': route}}
                        for task, route in zip(self.plan['tasks'], ['REVIEW_REQUIRED', 'NORMAL_M1'])]

    def bound(self):
        import webcollect.preflight as module
        original = self.root / 'input-plan.json'
        original.write_text(json.dumps(self.plan))
        records = deepcopy(self.records)
        for index, record in enumerate(records):
            directory = self.root / f'task_{index+1:03d}'; directory.mkdir(exist_ok=True)
            record.update(error={'message': 'Synthetic partial-navigation fixture'},
                          evidence_directory=directory.name)
            (directory / 'navigation_failure.json').write_text(json.dumps(
                {k: v for k, v in record.items() if k != 'evidence_directory'}))
        from webcollect.preflight import _files
        report = {'schema_version': 'webcollect-preflight-report-1',
                  'records': records, 'input_plan_sha256': digest(original),
                  'fixed_task_denominator': 2, 'source_changed_during_run': [],
                  'source_files_sha256': {name: digest(Path(module.__file__).parent / name)
                                           for name in SOURCE_FILES},
                  'evidence_files_sha256': {p: s for p, s in _files(self.root).items()
                      if p not in ['report.json', 'scheduled-plan.json', 'manifest.json', 'SHA256SUMS']}}
        path = self.root / 'report.json'
        path.write_text(json.dumps(report))
        return schedule_plan(self.plan, records, path, digest(path))

    def test_priority_reorders_but_never_removes_difficult_task(self):
        scheduled = schedule_plan(self.plan, self.records, self.root / 'report.json', '0' * 64)
        self.assertEqual([task['task_id'] for task in scheduled['tasks']], ['second', 'first'])
        self.assertEqual({object_digest(t) for t in self.plan['tasks']},
                         {object_digest(t) for t in scheduled['tasks']})
        self.assertFalse(scheduled['media_preflight']['routing_is_QC_acceptance'])

    def test_fixed_comparison_keeps_original_order(self):
        scheduled = schedule_plan(self.plan, self.records, self.root / 'report.json', '0' * 64, True)
        self.assertEqual(scheduled['tasks'], self.plan['tasks'])

    def test_missing_duplicate_changed_and_unknown_records_rejected(self):
        variants = [self.records[:1], [self.records[0], self.records[0]]]
        changed = deepcopy(self.records); changed[0]['task_sha256'] = 'f' * 64
        unknown = deepcopy(self.records); unknown[0]['summary']['routing'] = 'PASS'
        for records in variants + [changed, unknown]:
            with self.subTest(records=records), self.assertRaises(ValueError):
                schedule_plan(self.plan, records, self.root / 'report.json', '0' * 64)

    def test_hash_bound_handoff_accepts_complete_unchanged_advice(self):
        validate_preflight_binding(self.bound())

    def test_dropped_or_changed_task_is_rejected_before_collection(self):
        for change in ['drop', 'change']:
            scheduled = self.bound()
            if change == 'drop': scheduled['tasks'].pop()
            else: scheduled['tasks'][0]['instruction'] = '偷换任务目标'
            with self.assertRaises(ValueError): validate_preflight_binding(scheduled)

    def test_modified_report_or_frame_invalidates_binding(self):
        scheduled = self.bound()
        (self.root / 'task_001/navigation_failure.json').write_bytes(b'changed evidence')
        with self.assertRaises(ValueError): validate_preflight_binding(scheduled)

    def test_empty_inventory_and_deleted_task_cannot_hide_missing_evidence(self):
        scheduled = self.bound(); path = self.root / 'report.json'
        report = json.loads(path.read_text()); report['evidence_files_sha256'] = {}
        (self.root / 'task_001/navigation_failure.json').unlink()
        path.write_text(json.dumps(report)); scheduled['media_preflight']['report_sha256'] = digest(path)
        with self.assertRaises(ValueError): validate_preflight_binding(scheduled)
        scheduled = self.bound()
        (self.root / 'report.json').write_text('{}')
        with self.assertRaises(ValueError): validate_preflight_binding(scheduled)

    def test_source_drift_invalidates_advice_even_if_report_rehashed(self):
        scheduled = self.bound(); path = self.root / 'report.json'
        report = json.loads(path.read_text()); report['source_files_sha256']['browser.py'] = '0' * 64
        path.write_text(json.dumps(report)); scheduled['media_preflight']['report_sha256'] = digest(path)
        with self.assertRaises(ValueError): validate_preflight_binding(scheduled)

    def test_accounting_source_drift_invalidates_complete_unchanged_handoff(self):
        scheduled = self.bound()
        report = json.loads((self.root / 'report.json').read_text())
        self.assertIn('batch_core.py', report['source_files_sha256'])
        validate_preflight_binding(scheduled)
        # Simulate changed current source bytes without modifying the shared checkout.
        def changed_digest(path):
            return '0' * 64 if Path(path).name == 'batch_core.py' else digest(path)
        with patch('webcollect.preflight.digest', side_effect=changed_digest):
            with self.assertRaisesRegex(ValueError, '预检运行源码已变化'):
                validate_preflight_binding(scheduled)

    def test_missing_accounting_source_in_old_handoff_requires_new_preflight(self):
        scheduled = self.bound(); path = self.root / 'report.json'
        report = json.loads(path.read_text())
        del report['source_files_sha256']['batch_core.py']
        path.write_text(json.dumps(report))
        scheduled['media_preflight']['report_sha256'] = digest(path)
        with self.assertRaisesRegex(ValueError, '预检运行源码已变化'):
            validate_preflight_binding(scheduled)

    def test_original_pixel_difference_is_not_an_ad_classifier(self):
        def png(image):
            buffer = BytesIO(); image.save(buffer, format='PNG'); return buffer.getvalue()
        first = Image.new('RGB', (10, 10), 'white'); last = first.copy(); last.putpixel((3, 4), (0, 0, 0))
        change = pixel_change(png(first), png(last))
        self.assertEqual(change['changed_pixels'], 1)
        self.assertEqual(change['bbox'], [3, 4, 4, 5])
        self.assertEqual(change['changed_fraction'], .01)
        self.assertNotIn('advertisement', change)
        with self.assertRaises(ValueError): pixel_change(png(first), png(Image.new('RGB', (12, 10))))

    def test_bounded_observation_budget(self):
        _limits(3, 400)
        for samples, interval in [(1, 400), (6, 400), (3, 99), (3, 2001), (True, 400)]:
            with self.assertRaises(ValueError): _limits(samples, interval)


class PreflightFailureEvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        buffer = BytesIO(); Image.new('RGB', (12, 8), 'white').save(buffer, format='PNG')
        self.png = buffer.getvalue()
        self.task = {'task_id': 'synthetic-failure', 'site_uri': 'https://example.org/a',
                     'initial_url': 'https://example.org/a', 'operations': [{'action_type': 'scroll'}]}

    async def test_after_observation_failure_keeps_original_PNG_and_partial_before_state(self):
        class Page: url = 'https://example.org/a'
        before = {'url': Page.url, 'visible_text': '真实前置观察'}
        with patch('webcollect.preflight.viewport_png', AsyncMock(return_value=(self.png, {'method': 'fixture'}))), \
             patch('webcollect.media_preflight.probe_media', AsyncMock(return_value={'media': []})), \
             patch('webcollect.media_preflight.summarize_preflight', return_value={'routing': 'NORMAL_M1'}), \
             patch('webcollect.preflight.assess_content', AsyncMock(return_value={'body': {}})), \
             patch('webcollect.preflight.observe', AsyncMock(side_effect=[before, TimeoutError('after failed')])):
            result = await inspect_page(Page(), self.task, self.root / 'task', samples=2)
        self.assertEqual(result['summary']['routing'], 'REVIEW_REQUIRED')
        self.assertEqual((self.root / 'task/initial.png').read_bytes(), self.png)
        self.assertEqual((self.root / 'task/probe_000.png').read_bytes(), self.png)
        partial = json.loads((self.root / 'task/probe_000.partial.json').read_text())
        self.assertEqual(partial['state_before'], before)
        self.assertTrue(partial['incomplete'])
        self.assertFalse(partial['accepted_as_formal_frame'])

    async def test_partial_navigation_retains_diagnostic_and_full_scheduled_denominator(self):
        class Page:
            url = 'https://example.org/a'
            goto = AsyncMock(side_effect=TimeoutError('partially loaded navigation'))
        page = Page()
        context = type('Context', (), {'new_page': AsyncMock(return_value=page), 'close': AsyncMock()})()
        browser = type('Browser', (), {'version': 'SYNTHETIC-NO-BROWSER',
            'new_context': AsyncMock(return_value=context), 'close': AsyncMock()})()
        driver = type('Driver', (), {'chromium': type('Chromium', (), {'launch': AsyncMock(return_value=browser)})()})()
        manager = type('Manager', (), {'__aenter__': AsyncMock(return_value=driver), '__aexit__': AsyncMock(return_value=False)})()
        plan = self.root / 'plan.json'; plan.write_text(json.dumps({'tasks': [self.task]}))
        output = self.root / 'preflight'
        with patch('playwright.async_api.async_playwright', return_value=manager), \
             patch('webcollect.collect.validate_plan'), \
             patch('webcollect.preflight.viewport_png', AsyncMock(return_value=(self.png, {'method': 'fixture'}))), \
             patch('webcollect.preflight.asyncio.sleep', AsyncMock()):
            result = await preflight_plan(plan, output, samples=2)
        self.assertEqual(result['probe_errors'], 1)
        self.assertEqual(result['task_count'], 1)
        self.assertEqual((output / 'task_001/navigation_failure_capture.png').read_bytes(), self.png)
        scheduled = json.loads((output / 'scheduled-plan.json').read_text())
        self.assertEqual(scheduled['tasks'], [self.task])
        validate_preflight_binding(scheduled)
        browser.close.assert_awaited_once(); context.close.assert_awaited_once()
