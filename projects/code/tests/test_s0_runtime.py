"""S0 dependency separation. No external fetch/provider or production registry."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO/'projects/site-planner')]

from webcollect.batch_core import BatchLedger, BudgetStop, load_json, save_json, validate_config
from webcollect.model_gateway import ModelGateway
from site_planner.pipeline import discover, probe


class NoModelRuntimeTests(unittest.TestCase):
    def setUp(self):
        retained = os.environ.get('WEBCOLLECT_S0_RUNTIME_EVIDENCE')
        if retained:
            self.root = Path(retained)/self._testMethodName
            self.root.mkdir(parents=True, exist_ok=False)
        else:
            temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
            self.root = Path(temp.name)
        self.config = load_json(REPO/'projects/code/config/batch-no-model.json')

    def ledger(self, config=None):
        return BatchLedger(self.root/'operations.sqlite3', config or self.config, initialize=True)

    def test_real_config_needs_no_model_rates_currency_or_credentials(self):
        self.assertEqual(self.config['mode'], 'real')
        self.assertIsNone(self.config['model'])
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(validate_config(self.config, credentials=True), self.config)
            ledger = self.ledger()
            summary = ledger.export(self.root/'metering')
        self.assertFalse(summary['model_enabled'])
        self.assertEqual(summary['model_requests'], 0)
        self.assertEqual(summary['model_cost_micros'], 0)
        self.assertIsNone(summary['currency'])
        self.assertIsNone(summary['rate_version'])

    def test_no_model_gateway_and_reservation_fail_before_network(self):
        ledger = self.ledger()
        job = ledger.claim('test', job_id=ledger.enqueue('test', {'case':'disabled'}))
        with patch('urllib.request.build_opener', side_effect=AssertionError('network forbidden')):
            with self.assertRaisesRegex(ValueError, 'disabled'):
                ModelGateway(ledger)
            with self.assertRaisesRegex(ValueError, 'disabled'):
                ledger.reserve_request(job, 'not-authorized', 0)
        ledger.finish(job, 'review_required')
        self.assertEqual(ledger.summary()['model_requests'], 0)

    def test_invalid_runtime_limits_and_fake_model_cost_fields_rejected(self):
        for key, value in [('max_run_seconds',0), ('max_concurrent_jobs',0),
                           ('max_probe_pages',-1), ('max_job_attempts',0),
                           ('min_domain_interval_seconds',0), ('lease_seconds',4)]:
            config = deepcopy(self.config); config['budget'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config(config)
        config = deepcopy(self.config); config['budget']['max_model_cost_micros'] = 0
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_model_branch_still_requires_real_rates_and_credentials(self):
        config = load_json(REPO/'projects/code/config/batch-synthetic.json')
        config['mode'] = 'real'
        config['model'].update(provider='chat-completions', model='configured-test-model',
            endpoint='https://example.org/v1/chat/completions', api_key_env='WEBCOLLECT_TEST_API_KEY')
        config['budget']['min_model_interval_seconds'] = 1
        with self.assertRaises(ValueError):
            validate_config(config)
        config['model']['rates'].update(input=1, output=1)
        config['model']['reserve_cost_micros'] = 1
        config['budget']['max_model_cost_micros'] = 2
        self.assertEqual(validate_config(config), config)
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'credential'):
            validate_config(config, credentials=True, require_model=True)

    def test_resource_and_frozen_budget_resume(self):
        config = deepcopy(self.config); config['budget']['max_probe_pages'] = 1
        ledger = self.ledger(config)
        ledger.consume('probe_pages', 'original-page')
        resumed = BatchLedger(ledger.path, config)
        resumed.consume('probe_pages', 'original-page')
        with self.assertRaises(BudgetStop):
            resumed.consume('probe_pages', 'new-page')
        changed = deepcopy(config); changed['budget']['max_probe_pages'] = 2
        with self.assertRaisesRegex(ValueError, 'frozen'):
            BatchLedger(ledger.path, changed, initialize=True)
        self.assertEqual(resumed.summary()['resources'], [{'kind':'probe_pages','used':1}])

    def test_wall_limit_survives_resume(self):
        ledger = self.ledger()
        jid = ledger.enqueue('test', {'case':'time'})
        with ledger.transaction() as con:
            con.execute('UPDATE batch_meta SET started=? WHERE id=1',
                        (time.time()-self.config['budget']['max_run_seconds']-1,))
        resumed = BatchLedger(ledger.path, self.config)
        with self.assertRaisesRegex(BudgetStop, 'max_run_seconds'):
            resumed.claim('test', job_id=jid)
        self.assertEqual(resumed.get(jid)['attempts'], 0)

    def test_concurrency_domain_limits_and_retry_cap_survive_resume(self):
        config = deepcopy(self.config); config['budget']['min_domain_interval_seconds'] = 60
        ledger = self.ledger(config)
        first = ledger.enqueue('test', {'case':'first'})
        second = ledger.enqueue('test', {'case':'second'})
        job = ledger.claim('test', job_id=first, domain='example.org')
        with self.assertRaisesRegex(BudgetStop, 'max_concurrent_jobs'):
            ledger.claim('test', job_id=second, domain='other.org')
        ledger.finish(job, 'queued')
        resumed = BatchLedger(ledger.path, config)
        with self.assertRaisesRegex(BudgetStop, 'domain rate limit'):
            resumed.claim('test', job_id=second, domain='example.org')
        job = resumed.claim('test', job_id=first)
        self.assertEqual(resumed.get(first)['attempts'], 2)
        resumed.finish(job, 'queued')
        self.assertIsNone(BatchLedger(ledger.path, config).claim('test', job_id=first))
        self.assertEqual(resumed.get(first)['state'], 'review_required')
        self.assertEqual(resumed.get(first)['attempts'], 2)
        self.assertEqual(resumed.summary()['model_requests'], 0)

    def test_expired_non_model_lease_recovers_without_resetting_attempts(self):
        ledger = self.ledger()
        jid = ledger.enqueue('test', {'case':'crash'})
        ledger.claim('test', job_id=jid)
        with ledger.transaction() as con:
            con.execute('UPDATE jobs SET lease=? WHERE id=?', (time.time()-1, jid))
        resumed = BatchLedger(ledger.path, self.config)
        self.assertEqual(resumed.recover(), 1)
        self.assertEqual(resumed.get(jid)['attempts'], 1)
        self.assertIsNotNone(resumed.claim('test', job_id=jid))
        self.assertEqual(resumed.get(jid)['attempts'], 2)

    def test_seed_discovery_is_real_mode_offline_and_capped_reproducibly(self):
        config = deepcopy(self.config); config['budget']['max_discovery_candidates'] = 2
        ledger = self.ledger(config)
        sources = {'schema_version':'webcollect-site-sources-1','sources':[
            {'kind':'seed','category':'工具','max_candidates':1,
             'uris':['https://example.org/a','https://example.org/b']},
            {'kind':'seed','category':'资讯','uris':['https://example.com/c','https://example.com/d']},
            {'kind':'directory','category':'教育','uri':'https://example.net/'}]}
        save_json(self.root/'sources.json', sources)
        with patch('site_planner.pipeline.fetch_public', side_effect=AssertionError('external fetch forbidden')):
            result = discover(ledger, self.root/'sources.json', self.root/'supply')
            resumed = discover(BatchLedger(ledger.path, config), self.root/'sources.json', self.root/'supply')
        self.assertEqual(resumed, result)
        self.assertEqual(result['mode'], 'real')
        self.assertEqual(result['fixed_candidate_count'], 2)
        self.assertEqual([r['site_uri'] for r in result['records']], ['https://example.org/a','https://example.com/c'])
        self.assertEqual(result['discovery_link_occurrences'], 4)
        self.assertEqual(len(result['deferred_links']), 2)
        self.assertEqual(len(result['unprocessed_sources']), 1)
        self.assertEqual(result['unprocessed_sources'][0]['link_occurrences'], 'UNKNOWN')
        self.assertFalse(result['link_denominator_complete'])
        self.assertTrue((self.root/'supply/candidates.json').exists())
        self.assertEqual(ledger.summary()['model_requests'], 0)
        ledger.export(self.root/'metering')


class NoModelProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_rendered_fixture_probes_without_credentials_and_stays_pending(self):
        retained = os.environ.get('WEBCOLLECT_S0_RUNTIME_EVIDENCE')
        if retained:
            root = Path(retained)/self._testMethodName; root.mkdir(parents=True,exist_ok=False)
        else:
            temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); root = Path(temp.name)
        config = load_json(REPO/'projects/code/config/batch-no-model.json')
        ledger = BatchLedger(root/'operations.sqlite3', config, initialize=True)
        uri = 'https://example.org/controlled-fixture'
        html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>受控计算页面</title>
        <h1>受控合成工程页面</h1><p>此页面只用于验证无模型探测与证据保存，不是真实生产样本。</p>
        <p>请输入商品数量和价格，点击计算按钮查看结果。本页面提供中文标签和中文导航，所有内容均为受控工程测试。</p>
        <form aria-label="金额计算"><label>数量<input name="quantity" type="number"></label>
        <label>价格<input name="price" type="number"></label><button type="submit">计算</button></form>
        <output>等待计算结果</output></html>'''
        candidates = {'schema_version':'webcollect-site-candidates-1','mode':'real','records':[
            {'site_uri':uri,'site_category':'工具','source':[{'kind':'controlled-fixture-not-real-supply'}]}]}
        save_json(root/'candidates.json', candidates)
        save_json(root/'mode.json', {'scope':'controlled rendered fixture only', 'runtime_config_mode':'real',
            'real_sites_probed':0, 'model_requests':0, 'production_samples':0})
        with patch('site_planner.pipeline.ModelGateway',side_effect=AssertionError('model forbidden')):
            result = await probe(ledger,root/'candidates.json',root/'probe',fixture_pages={uri:html})
            resumed = await probe(ledger,root/'candidates.json',root/'probe',fixture_pages={uri:html})
        self.assertEqual(result['status_counts'], {'review_required':1})
        self.assertEqual(result['records'],resumed['records'])
        record = result['records'][0]
        self.assertEqual(record['screening']['review_source'], 'not_reviewed')
        self.assertTrue(record['evidence'])
        self.assertFalse(record['QC_approval'])
        self.assertEqual(ledger.summary()['model_requests'],0)
        ledger.export(root/'metering')


if __name__ == '__main__':
    unittest.main()
