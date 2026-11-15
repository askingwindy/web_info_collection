"""Offline contracts for observed model normalization and standalone health startup."""
from copy import deepcopy
from pathlib import Path
import tempfile
import sqlite3
import io
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from webcollect.candidate_consumer import run
from webcollect.screenshot_plan import normalize_submit_plan, submit_plan_schema
from jsonschema import validate, ValidationError


class ConsumerStartupCore(unittest.IsolatedAsyncioTestCase):
    def test_empty_requirement_metadata_is_losslessly_normalized(self):
        raw = {'goal': '计算', 'requirements': [{'id': 'r1', 'kind': 'input', 'description': '设置数量', 'id2': '',
                                                 'evidence_scope': 'current',
                                                 'acceptance': {'mode': 'presence', 'subject': '数量', 'source_quote': '计算'},
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
        from webcollect.current_chain import CurrentChainError
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
            # A deterministic frozen-input fault precedes even account probes,
            # and leaves both fixed candidates unclaimed for a corrected input.
            pool = MagicMock()
            rows = [{'candidate_id': 'first'}, {'candidate_id': 'second'}]
            calls.clear()
            def reject_sources(*args):
                calls.append('sources')
                raise CurrentChainError('out-of-chain source', context={'json_location': '$.nested'})
            with patch('webcollect.candidate_consumer._cohort_rows', return_value=('batch', rows)), \
                 patch('webcollect.candidate_consumer.startup_check', side_effect=lambda *a, **k: calls.append('scope') or {}), \
                 patch('webcollect.candidate_consumer.preflight_cohort_sources', side_effect=reject_sources), \
                 patch('webcollect.key_health.pool_available') as available, \
                 patch('webcollect.key_health.probe_accounts') as probe, \
                 patch('webcollect.candidate_consumer.consume', new_callable=AsyncMock) as consume:
                result = await run(pool, object(), worker_id='frozen', request_prefix='fixed',
                    cohort='cohort.json', registry='registry.sqlite3', output=Path(directory))
            self.assertEqual(calls, ['scope', 'sources'])
            available.assert_not_called()
            probe.assert_not_called()
            pool.claim_next.assert_not_called()
            consume.assert_not_awaited()
            self.assertEqual((result['processed'], result['unexamined']), (0, 2))
            self.assertEqual(result['stop_reason'], 'engineering_failure')
            self.assertEqual(result['stop_details']['evidence_context'], {'json_location': '$.nested'})
            # Frozen source hashes imply the same original GET reference that
            # claim_next consumes. Missing input must fail before claim/IO.
            import json
            from types import SimpleNamespace
            from webcollect.batch_core import file_sha
            from webcollect.planning import object_sha256
            from webcollect.candidate_consumer import preflight_cohort_sources
            receipt=Path(directory)/'original-get.json';receipt.write_text('{}')
            ref={'path':str(receipt),'sha256':file_sha(receipt)}
            sources=[{'entry_http':ref,'references':[ref]}]
            database=Path(directory)/'frozen-pool.sqlite3'
            with sqlite3.connect(database) as con:
                con.execute('CREATE TABLE candidate_sources(candidate_id TEXT,created REAL,source_key TEXT,source TEXT)')
                con.execute('INSERT INTO candidate_sources VALUES(?,?,?,?)',('fixed',1,'source',json.dumps(sources[0])))
            fixed={'candidate_id':'fixed','sources_sha256':object_sha256(sources)}
            with patch('webcollect.candidate_consumer.preflight_candidate_sources') as closure:
                with self.assertRaisesRegex(CurrentChainError,'entry_http'):
                    preflight_cohort_sources(SimpleNamespace(path=database),[fixed],'registry')
                closure.assert_not_called()
                preflight_cohort_sources(SimpleNamespace(path=database),[{**fixed,'entry_http':ref}],'registry')
                closure.assert_called_once()

    async def test_available_pool_and_campaign_workers_never_probe(self):
        from webcollect.consumer_campaign import stop_engineering_failure, stopped
        from webcollect.current_chain import CurrentChainError
        import json
        with tempfile.TemporaryDirectory() as directory:
            with patch('webcollect.candidate_consumer.startup_check', return_value={}), \
                 patch('webcollect.key_health.pool_available', side_effect=[True, False]), \
                 patch('webcollect.key_health.probe_accounts') as probe:
                result = await run(None, object(), worker_id='worker', request_prefix='launch', limit=1, output=Path(directory))
                probe.assert_not_called()
                self.assertEqual(result['stop_reason'], 'key_pool_unavailable')

            # Unexpected programming faults during claim are engineering
            # failures, never a sequence of candidate business skips.
            broken_campaign=Path(directory)/'claim-input-campaign.json'
            broken_campaign.write_text(json.dumps({'deliveries':[],'dispatch_stopped':False}))
            pool=MagicMock();pool.claim_next.side_effect=KeyError('entry_http')
            rows=[{'candidate_id':'fixed1','producer_batch':'batch'},{'candidate_id':'fixed2','producer_batch':'batch'}]
            with patch('webcollect.candidate_consumer._cohort_rows',return_value=('batch',rows)), \
                 patch('webcollect.candidate_consumer.preflight_cohort_sources'), \
                 patch('webcollect.candidate_consumer.startup_check',return_value={}), \
                 patch('webcollect.key_health.pool_available',return_value=True), \
                 patch('webcollect.key_health.probe_accounts') as probe, \
                 patch('webcollect.candidate_consumer.consume',new_callable=AsyncMock) as consume:
                result=await run(pool,object(),worker_id='fixed',request_prefix='fixed',cohort='cohort.json',
                    campaign=broken_campaign,registry='registry',output=Path(directory))
            self.assertEqual(result['stop_reason'],'engineering_failure')
            self.assertEqual(result['stop_details']['error_type'],'KeyError')
            self.assertEqual(result['processed'],0)
            pool.claim_next.assert_called_once();consume.assert_not_awaited();probe.assert_not_called()
            self.assertEqual(json.loads(broken_campaign.read_text())['stop_reason'],'ENGINEERING_FAILURE')
            # Continuous, non-cohort workers stop on a chain contract error.
            # Preserve an already unresolved claim; stopping is not reconciliation.
            state = Path(directory) / 'campaign.json'
            state.write_text(json.dumps({'deliveries': [], 'dispatch_stopped': False}))
            claim = {'claim_id': 'owned', 'candidate_id': 'first', 'state': 'consuming', 'stage': 'claimed'}
            pool = MagicMock()
            pool.claim_next.return_value = claim
            pool.get_claim.return_value = {**claim, 'state': 'reconcile', 'stage': 'execution'}
            with patch('webcollect.candidate_consumer.startup_check', return_value={}), \
                 patch('webcollect.key_health.pool_available', return_value=True), \
                 patch('webcollect.key_health.probe_accounts') as probe, \
                 patch('webcollect.candidate_consumer.consume', new_callable=AsyncMock,
                       side_effect=CurrentChainError('frozen source changed')) as consume, \
                 patch('webcollect.runlog.for_claim'), \
                 patch('webcollect.consumer_campaign.deliver', return_value={'state': 'queued'}), \
                 patch('webcollect.candidate_batch.record_outcome'):
                result = await run(pool, object(), worker_id='continuous', request_prefix='continuous',
                                   campaign=state, output=Path(directory))
            probe.assert_not_called()
            pool.claim_next.assert_called_once()
            consume.assert_awaited_once()
            pool.finish.assert_not_called()
            self.assertEqual(result['processed'], 1)
            self.assertEqual(result['stop_reason'], 'engineering_failure')
            self.assertTrue(stopped(state))
            stop_engineering_failure(state, {'error_type': 'later_error'})
            saved = json.loads(state.read_text())
            self.assertEqual(saved['stop_reason'], 'ENGINEERING_FAILURE')
            self.assertEqual(saved['stop_details']['error_type'], 'CurrentChainError')
            # A registry busy read that escaped consume is transient: the claim
            # settles reconcile and the same worker keeps claiming; the batch
            # is not stopped and no engineering failure is recorded.
            state = Path(directory) / 'transient-campaign.json'
            state.write_text(json.dumps({'deliveries': [], 'dispatch_stopped': False}))
            claim = {'claim_id': 'busy', 'candidate_id': 'page', 'state': 'consuming', 'stage': 'claimed'}
            pool = MagicMock()
            pool.claim_next.side_effect = [claim, {'state': 'EMPTY'}]
            pool.get_claim.side_effect = [{**claim, 'state': 'consuming'},
                                          {**claim, 'state': 'reconcile', 'stage': 'claimed'}]
            with patch('webcollect.candidate_consumer.startup_check', return_value={}), \
                 patch('webcollect.key_health.pool_available', return_value=True), \
                 patch('webcollect.key_health.probe_accounts') as probe, \
                 patch('webcollect.candidate_consumer.consume', new_callable=AsyncMock,
                       side_effect=sqlite3.OperationalError('database is locked')) as consume, \
                 patch('webcollect.runlog.for_claim'), \
                 patch('webcollect.consumer_campaign.deliver', return_value={'state': 'queued'}), \
                 patch('webcollect.candidate_batch.record_outcome'):
                result = await run(pool, object(), worker_id='busy', request_prefix='busy',
                                   campaign=state, output=Path(directory), limit=2, stop_when_empty=True)
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 1)
            self.assertEqual(pool.claim_next.call_count, 2)
            pool.finish.assert_called_once()
            self.assertEqual(pool.finish.call_args.kwargs.get('state'), 'reconcile')
            self.assertEqual(result[0]['failure_class'], 'transient')
            self.assertNotIn('engineering_failure', result[0])
            self.assertFalse(stopped(state))
            self.assertNotIn('stop_reason', json.loads(state.read_text()))
            with patch('webcollect.candidate_consumer.startup_check', return_value={}), \
                 patch('webcollect.key_health.pool_available', return_value=False), \
                 patch('webcollect.key_health.probe_accounts') as probe:
                result = await run(None, object(), worker_id='worker', request_prefix='launch', limit=1,
                                   campaign='campaign.json', output=Path(directory))
                probe.assert_not_called()
                self.assertEqual(result['stop_reason'], 'key_pool_unavailable')

            # 站点目标按"正式保存的不同页面"计数（deliver 登记的 saved_pages），
            # 与交付导出数（exported_count）分开；三次保存时翻转到达。
            from webcollect.consumer_campaign import deliver, exported_count, site_reached, target_count
            save_state = {'deliveries': [{'application_id': 'appA', 'ordinary_target_eligible': True}] * 5,
                          'saved_pages': [], 'site_targets': {'appA': 3}, 'dispatch_stopped': False}
            self.assertEqual(target_count(save_state, 'appA'), 0)
            self.assertEqual(exported_count(save_state, 'appA'), 5)  # exports alone never reach the target
            self.assertFalse(site_reached(save_state, 'appA'))
            save_state['saved_pages'] = [{'candidate_id': 'c1', 'application_id': 'appA'},
                                         {'candidate_id': 'c2', 'application_id': 'appA'},
                                         {'candidate_id': 'c2', 'application_id': 'appA'},
                                         {'candidate_id': 'c9', 'application_id': 'appB'}]
            self.assertEqual(target_count(save_state, 'appA'), 2)
            self.assertFalse(site_reached(save_state, 'appA'))
            save_state['saved_pages'].append({'candidate_id': 'c3', 'application_id': 'appA'})
            self.assertTrue(site_reached(save_state, 'appA'))
            self.assertFalse(site_reached(save_state, 'appB'))

            class MiniCandidateDB:
                from contextlib import contextmanager
                def __init__(self, path):
                    self.path = Path(path)
                @contextmanager
                def connect(self, write=False, timeout=90):
                    connection = sqlite3.connect(self.path)
                    try:
                        yield connection
                    finally:
                        connection.close()

            mini = Path(directory) / 'mini-pool.sqlite3'
            with sqlite3.connect(mini) as con:
                con.execute('CREATE TABLE data_candidates(candidate_id TEXT PRIMARY KEY, application_id TEXT)')
                con.execute("INSERT INTO data_candidates VALUES('c1','appA')")
            mini_pool = SimpleNamespace(pool=MiniCandidateDB(mini), get_claim=lambda cid: {'claim_id': cid})
            campaign_state = Path(directory) / 'saved-campaign.json'
            campaign_state.write_text(json.dumps({'deliveries': [], 'dispatch_stopped': False,
                                                  'site_targets': {'appA': 1}}))
            receipt = {'sample_id': 's1', 'template_name': 'operation'}
            stderr = io.StringIO()
            import contextlib
            with patch('webcollect.candidate_consumer.verified_saved', return_value=receipt), \
                 contextlib.redirect_stderr(stderr):
                self.assertEqual(deliver(campaign_state, mini_pool, {'claim_id': 'CL1', 'candidate_id': 'c1'}),
                                 {'state': 'queued', 'claim_id': 'CL1'})
                deliver(campaign_state, mini_pool, {'claim_id': 'CL1', 'candidate_id': 'c1'})
            written = json.loads(campaign_state.read_text())
            # dedup by candidate_id: one saved_pages row, one target line, export queued once
            self.assertEqual(written['saved_pages'], [{'candidate_id': 'c1', 'claim_id': 'CL1',
                'application_id': 'appA', 'sample_id': 's1', 'template_name': 'operation'}])
            self.assertEqual(written['site_target_log'], {'appA': True})
            self.assertIn('appA', written['site_target_at'])
            self.assertEqual(len(written['pending_deliveries']), 1)
            self.assertEqual(stderr.getvalue().count('site_target_reached applicationId=appA'), 1)
            self.assertTrue(site_reached(written, 'appA'))

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
