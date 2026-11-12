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
        raw = {'goal': '计算', 'requirements': [{'id': 'r1', 'kind': 'result', 'description': '观察计算结果', 'id2': '',
                                                 'evidence_route': {'source_type': 'page_result', 'observation_steps': [1]}}],
               'steps': [{'action': 'back', 'purpose': '返回', 'rationale': '查看前页', 'expected_result': '前页出现'}],
               'final_presentation_step': 1}
        before = deepcopy(raw)
        normalized, record = normalize_submit_plan(raw)
        validate(normalized, submit_plan_schema(['back']))
        self.assertEqual(raw, before)
        self.assertEqual(record['transforms'][0]['path'], 'requirements[0].id2')
        raw['requirements'][0]['id2'] = 'another-business-id'
        normalized, _ = normalize_submit_plan(raw)
        with self.assertRaises(ValidationError):
            validate(normalized, submit_plan_schema(['back']))

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
