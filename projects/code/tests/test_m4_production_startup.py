"""Regressions for the first real M4 round; no production data is mutated."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_task_instruction_contract import reading_plan
from webcollect.collect import validate_plan
from webcollect.preflight import preflight_plan
from webcollect.validate import SCHEMAS, StrictValidator


class PlannedTaskTypeTests(unittest.TestCase):
    def test_actual_illegal_tag_is_rejected_before_browser_work(self):
        plan = reading_plan('查阅「测试文献」并核对指定事实。')
        plan['tasks'][0]['task_type'] = ['信息检索', '数据查看']
        with self.assertRaisesRegex(ValueError, 'task_type.*合同枚举'):
            validate_plan(plan)

    def test_contract_array_constraints_apply_to_planning(self):
        for bad in ('数据查看', ['数据查看', '数据查看'],
                    ['数据查看', '搜索查询', '填写表单', '修改设置']):
            with self.subTest(value=bad):
                plan = reading_plan('查阅「测试文献」并核对指定事实。')
                plan['tasks'][0]['task_type'] = bad
                with self.assertRaisesRegex(ValueError, 'task_type'):
                    validate_plan(plan)
        plan['tasks'][0]['task_type'] = ['搜索查询', '数据查看']
        validate_plan(plan)


class PreflightTypeTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_type_never_launches_browser_or_creates_preflight_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = reading_plan('查阅「测试文献」并核对指定事实。')
            plan['tasks'][0]['task_type'] = ['信息检索']
            source = root / 'plan.json'
            source.write_text(json.dumps(plan, ensure_ascii=False))
            with patch('playwright.async_api.async_playwright') as browser:
                with self.assertRaisesRegex(ValueError, 'task_type'):
                    await preflight_plan(source, root / 'output')
                browser.assert_not_called()
            self.assertFalse((root / 'output').exists())


class RuntimeManifestVersionTests(unittest.TestCase):
    def setUp(self):
        self.validator = StrictValidator(json.loads(
            SCHEMAS.joinpath('manifest.schema.json').read_text(encoding='utf-8')))
        self.legacy = {'batch_id': 'B20261025_001', 'sample_kind': 'real',
            'program_version': 'controlled-fixture', 'rule_version': '1.0.0',
            'samples': ['S000001_sample_000001'],
            'sites': [{'site_id': 'S000001', 'uri': 'https://example.org/',
                       'site_category': '测试'}]}

    def test_legacy_manifest_remains_valid(self):
        self.assertFalse(list(self.validator.iter_errors(self.legacy)))

    def test_explicit_m4_manifest_accepts_its_actual_version(self):
        m4 = {**self.legacy, 'schema_version': 'webcollect-runtime-manifest-m4-1',
              'rule_version': 'm4-1'}
        self.assertFalse(list(self.validator.iter_errors(m4)))

    def test_cross_version_and_unknown_version_are_rejected(self):
        for value in ({**self.legacy, 'rule_version': 'm4-1'},
                      {**self.legacy, 'schema_version': 'webcollect-runtime-manifest-m4-1'},
                      {**self.legacy, 'rule_version': 'unknown'}):
            with self.subTest(value=value):
                self.assertTrue(list(self.validator.iter_errors(value)))
