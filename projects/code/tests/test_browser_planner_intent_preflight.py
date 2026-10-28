"""Frozen intent failures must stop before a job, output, browser or model exists.

All observer dependencies are mocks. No real browser, external model, production
registry or historical intent/trace is used or modified by these tests.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from webcollect import browser_planner as planner


def intent():
    return {'schema_version': 'webcollect-observed-workflow-intent-1', 'mode': 'real',
            'site_uri': 'https://www.example.com/tool', 'site_category': '在线工具',
            'app_name': '测试工具', 'instruction': '在「测试工具」填写「数量」为3，点击「计算」并核对结果。',
            'task_type': ['填写表单', '数据查看'], 'initial_url': 'https://www.example.com/tool',
            'created_at': 1793150000.25}


class IntentValueChecks(unittest.TestCase):
    def test_finite_numeric_timestamp_is_accepted_without_modification(self):
        for value in (0, 1, 1.5, 1793150000.25):
            with self.subTest(value=value):
                row = intent(); row['created_at'] = value; original = deepcopy(row)
                planner.validate_observation_intent(row)
                self.assertEqual(row, original)
                self.assertIs(type(row['created_at']), type(value))

    def test_non_numeric_nonfinite_and_bool_timestamp_are_rejected(self):
        for value in (None, '', '1793150000.25', '2026-10-28T03:00:00Z', True, False,
                      float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=repr(value)):
                row = intent(); row['created_at'] = value
                with self.assertRaisesRegex(ValueError, 'finite numeric created_at'):
                    planner.validate_observation_intent(row)

    def test_required_text_fields_reject_missing_empty_whitespace_and_wrong_type(self):
        for field in ('site_uri', 'site_category', 'app_name', 'instruction', 'initial_url'):
            for value in (None, '', '   ', True, 1):
                with self.subTest(field=field, value=value):
                    row = intent(); row[field] = value
                    with self.assertRaisesRegex(ValueError, field): planner.validate_observation_intent(row)

    def test_task_type_uses_existing_annotation_contract(self):
        for value in (None, [], '填写表单', ['参数配置'], ['not-a-customer-enum'],
                      ['填写表单', '填写表单'], ['填写表单', '数据查看', '修改设置', '搜索查询']):
            with self.subTest(value=value):
                row = intent(); row['task_type'] = value
                with self.assertRaisesRegex(ValueError, 'customer enumeration'):
                    planner.validate_observation_intent(row)


class IntentPreflightSideEffects(unittest.IsolatedAsyncioTestCase):
    async def check_rejected(self, row, *, capability=None, ledger_mode='real',
                             capability_error=None, max_actions=12):
        capability = deepcopy(capability) if capability is not None else {
            'site_qualification': {'access': {'kind': 'public'}},
            'capabilities': [{'page_uri': 'https://www.example.com/tool'}]}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); path = base / 'intent.json'; cap_path = base / 'capability.json'
            path.write_text(json.dumps(row, ensure_ascii=False)); cap_path.write_text(json.dumps(capability))
            original = path.read_bytes(); output = base / 'must-not-be-created'
            ledger = MagicMock(); ledger.config = {'mode': ledger_mode}
            with patch.object(planner, 'validate_capability', side_effect=capability_error) as qualification, \
                 patch.object(planner, 'ModelGateway') as model, \
                 patch.object(planner, 'BatchNavigation') as navigation, \
                 patch('playwright.async_api.async_playwright') as browser:
                with self.assertRaises((ValueError, KeyError)):
                    await planner.observe_task(ledger, path, cap_path, output, max_actions=max_actions)
                ledger.enqueue.assert_not_called()       # NO_LEDGER_ENQUEUE
                ledger.claim.assert_not_called()
                self.assertFalse(output.exists())        # NO_OUTPUT_DIR
                browser.assert_not_called()              # NO_BROWSER
                model.assert_not_called()                # NO_MODEL
                navigation.assert_not_called()
                self.assertEqual(path.read_bytes(), original)

    async def test_missing_timestamp_has_no_side_effects(self):
        row = intent(); row.pop('created_at')
        await self.check_rejected(row)

    async def test_created_at_utc_only_is_not_automatically_repaired(self):
        row = intent(); row.pop('created_at'); row['created_at_utc'] = '2026-10-28T03:00:00Z'
        await self.check_rejected(row)

    async def test_invalid_task_type_has_no_side_effects(self):
        row = intent(); row['task_type'] = ['参数配置', '数据查看']
        await self.check_rejected(row)

    async def test_invalid_numeric_timestamp_variants_have_no_side_effects(self):
        for value in (None, True, '2026-10-28T03:00:00Z', float('nan'), float('inf')):
            with self.subTest(value=repr(value)):
                row = intent(); row['created_at'] = value
                await self.check_rejected(row)

    async def test_bad_schema_and_mode_have_no_side_effects(self):
        for field, value in (('schema_version', ''), ('schema_version', 'old-schema'),
                             ('mode', ''), ('mode', 'synthetic')):
            with self.subTest(field=field, value=value):
                row = intent(); row[field] = value
                await self.check_rejected(row)

    async def test_missing_required_fields_have_no_side_effects(self):
        for field in ('site_uri', 'site_category', 'app_name', 'instruction'):
            with self.subTest(field=field):
                row = intent(); row.pop(field)
                await self.check_rejected(row)

    async def test_private_initial_url_remains_blocked_before_dispatch(self):
        row = intent(); row['initial_url'] = 'http://127.0.0.1/tool'
        await self.check_rejected(row)

    async def test_private_declared_site_uri_is_blocked_before_dispatch(self):
        row = intent(); row['site_uri'] = 'http://192.168.1.2/tool'
        await self.check_rejected(row)

    async def test_qualification_failure_remains_before_dispatch(self):
        await self.check_rejected(intent(), capability_error=ValueError('original qualification failed'))

    async def test_nonpublic_account_context_remains_before_dispatch(self):
        cap = {'site_qualification': {'access': {'kind': 'test'}},
               'capabilities': [{'page_uri': 'https://www.example.com/tool'}]}
        await self.check_rejected(intent(), capability=cap)

    async def test_page_outside_qualified_scope_remains_before_dispatch(self):
        row = intent(); row['initial_url'] = 'https://www.example.com/other'
        await self.check_rejected(row)

    async def test_ledger_mode_and_action_bound_remain_before_dispatch(self):
        await self.check_rejected(intent(), ledger_mode='synthetic')
        await self.check_rejected(intent(), max_actions=4)

    async def test_valid_numeric_intent_reaches_mocked_enqueue_after_all_prechecks(self):
        class PassedPreflight(Exception): pass
        row = intent(); cap = {'site_qualification': {'access': {'kind': 'public'}},
                               'capabilities': [{'page_uri': row['initial_url']}]}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); path = base / 'intent.json'; cap_path = base / 'capability.json'
            path.write_text(json.dumps(row, ensure_ascii=False)); cap_path.write_text(json.dumps(cap))
            original = path.read_bytes(); output = base / 'valid-preflight-output'
            ledger = MagicMock(); ledger.config = {'mode': 'real'}
            ledger.enqueue.side_effect = PassedPreflight
            with patch.object(planner, 'validate_capability') as qualification, \
                 patch.object(planner, 'ModelGateway') as model, \
                 patch('playwright.async_api.async_playwright') as browser:
                with self.assertRaises(PassedPreflight):
                    await planner.observe_task(ledger, path, cap_path, output)
                qualification.assert_called_once_with(cap)
                ledger.enqueue.assert_called_once()
                self.assertTrue(output.is_dir())
                browser.assert_not_called(); model.assert_not_called()
                self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
