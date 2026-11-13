"""Offline contracts for observed model normalization and standalone health startup."""
from copy import deepcopy
from pathlib import Path
import tempfile
import sqlite3
from contextlib import contextmanager
import unittest
from unittest.mock import patch

from webcollect.candidate_consumer import run
from webcollect.screenshot_plan import normalize_submit_plan, submit_plan_schema
from jsonschema import validate, ValidationError


class ConsumerStartupCore(unittest.IsolatedAsyncioTestCase):
    def test_empty_requirement_metadata_is_losslessly_normalized(self):
        raw = {'goal': '计算', 'requirements': [{'id': 'r1', 'kind': 'input', 'description': '设置数量', 'id2': '',
                                                 'target': {'visible_label': '数量', 'role': 'input'}, 'expected_value': '10',
                                                 'evidence_route': {'source_type': 'input_state', 'observation_steps': [1]}}],
               'steps': [{'action': 'back', 'purpose': f'返回{index}', 'rationale': '查看前页',
                          'expected_result': '前页出现'} for index in range(5)],
               'final_presentation_step': 1}
        before = deepcopy(raw)
        normalized, record = normalize_submit_plan(raw)
        validate(normalized, submit_plan_schema(['back']))
        self.assertEqual(raw, before)
        self.assertIn('requirements[0].id2', [r['path'] for r in record['transforms']])
        self.assertEqual(normalized['requirements'][0]['target']['text'], '数量')
        self.assertNotIn('visible_label', normalized['requirements'][0]['target'])
        raw['requirements'][0]['id2'] = 'another-business-id'
        normalized, _ = normalize_submit_plan(raw)
        with self.assertRaises(ValidationError):
            validate(normalized, submit_plan_schema(['back']))
        # 普通首轮与宿主准入同一下限：不足五步的计划不能通过 wire schema；
        # unsuitable 分支不要求凑够五步。
        short = deepcopy(raw)
        short['requirements'][0].pop('id2')
        short['steps'] = short['steps'][:4]
        with self.assertRaises(ValidationError):
            validate(short, submit_plan_schema(['back']))
        validate({'unsuitable': {'reason': '自然不足五步'}}, submit_plan_schema(['back']))

    async def test_standalone_checks_scope_then_probes_once_and_stops_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            with patch('webcollect.candidate_consumer.startup_check', side_effect=lambda *a, **k: calls.append('scope') or {}), \
                 patch('webcollect.key_health.pool_available', return_value=False), \
                 patch('webcollect.key_health.probe_accounts', side_effect=lambda *a: calls.append('probe') or []) as probe:
                result = await run(None, object(), worker_id='worker', request_prefix='launch', limit=1, output=Path(directory))
            self.assertEqual(calls, ['scope', 'probe'])
            self.assertEqual(probe.call_args.args[1], 'candidate-run:launch')
            self.assertEqual(result['stop_reason'], 'key_pool_unavailable')
            self.assertEqual(result['processed'], 0)

    async def test_available_pool_and_campaign_workers_never_probe(self):
        from webcollect.consumer_campaign import stop_engineering_failure, stopped
        import json
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'campaign.json'
            state.write_text(json.dumps({'deliveries': [], 'dispatch_stopped': False}))
            stop_engineering_failure(state, {'error_type': 'OperationalError'})
            stop_engineering_failure(state, {'error_type': 'another'})
            self.assertTrue(stopped(state))
            saved = json.loads(state.read_text())
            self.assertEqual(saved['stop_reason'], 'ENGINEERING_FAILURE')
            self.assertEqual(saved['stop_details']['error_type'], 'OperationalError')
        with tempfile.TemporaryDirectory() as directory:
            with patch('webcollect.candidate_consumer.startup_check', return_value={}), \
                 patch('webcollect.key_health.pool_available', side_effect=[True, False]), \
                 patch('webcollect.key_health.probe_accounts') as probe:
                result = await run(None, object(), worker_id='worker', request_prefix='launch', limit=1, output=Path(directory))
                probe.assert_not_called()
                self.assertEqual(result['stop_reason'], 'key_pool_unavailable')
            with patch('webcollect.candidate_consumer.startup_check', return_value={}), \
                 patch('webcollect.key_health.pool_available', return_value=False), \
                 patch('webcollect.key_health.probe_accounts') as probe:
                result = await run(None, object(), worker_id='worker', request_prefix='launch', limit=1,
                                   campaign='campaign.json', output=Path(directory))
                probe.assert_not_called()
                self.assertEqual(result['stop_reason'], 'key_pool_unavailable')

    def test_unknown_probe_is_not_replayed_in_same_launch(self):
        from webcollect.key_health import probe_accounts
        class Ledger:
            real_glm = True
            config = {'model': {'provider': 'glm', 'endpoint': 'https://example.invalid', 'model': 'glm'}}
            def __init__(self):
                self.con = sqlite3.connect(':memory:')
            @contextmanager
            def transaction(self):
                with self.con:
                    yield self.con
        ledger = Ledger()
        try:
            with patch('webcollect.model_credentials.configured_credentials', return_value=[('account', 'test-secret')]):
                calls = []
                def transport(*args):
                    calls.append(args[-1])
                    return {'success': False}
                first = probe_accounts(ledger, 'launch', transport)
                self.assertEqual(first[0]['status'], 'unknown')
                self.assertEqual(probe_accounts(ledger, 'launch', transport), [])
                self.assertEqual(len(calls), 1)
                self.assertEqual(ledger.con.execute('SELECT state FROM consumer_key_probes').fetchone()[0], 'unknown')
        finally:
            ledger.con.close()
