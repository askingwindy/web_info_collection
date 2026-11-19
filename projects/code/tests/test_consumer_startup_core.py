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
    def test_fixed_pages_match_the_authorized_total_and_worker_limits(self):
        import json
        from collections import Counter
        from webcollect import site_workers
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows = [{'candidate_id': str(index), 'application_id': str(index % 3), 'order': index + 1} for index in range(150)]
            cohort = root / 'cohort.json'
            cohort.write_text(json.dumps({'selected': rows, 'denominator': 150, 'site_denominators': {'0': 50, '1': 50, '2': 50}}))
            scope = {key: str(root / key) for key in ('pool', 'consumer_config', 'consumer_db', 'registry', 'history_set', 'policy', 'output')}
            with patch.object(site_workers, 'load_scope', return_value=(root / 'scope.json', scope)):
                with self.assertRaisesRegex(ValueError, '100 unique'):
                    site_workers.fixed_consumer_plan('scope.json', cohort, root / 'wrong')
                plan = site_workers.fixed_consumer_plan('scope.json', cohort, root / 'run', expected_pages=150)
            self.assertEqual(plan['expected_pages'], 150)
            self.assertEqual([ident for worker in plan['workers'] for ident in worker['candidate_ids']], [row['candidate_id'] for row in rows])
            self.assertEqual([len(worker['candidate_ids']) for worker in plan['workers']], [8] * 10 + [7] * 10)
            for worker in plan['workers']:
                command = worker['command']
                shard = json.loads(Path(command[command.index('--cohort') + 1]).read_text())
                self.assertEqual(shard['denominator'], int(command[command.index('--limit') + 1]))
                self.assertEqual(shard['site_denominators'], dict(Counter(row['application_id'] for row in shard['selected'])))
                self.assertEqual(command[command.index('--collection-strategy') + 1], 'stepwise')

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
        # operation 的线协议先接纳四种可确定归一化形式，再由同一正规化器
        # 补齐/删除并留痕；执行编译器仍要求最终 expected_value。
        from webcollect.screenshot_templates.operation.plan import (
            FIRST_RULES, normalize_submit_plan as normalize_operation,
            submit_plan_schema as operation_schema)
        common = {'purpose': '必要业务操作', 'rationale': '依据当前控件',
                  'expected_result': '页面显示相应变化'}
        operation_raw = {
            'goal': '计算',
            'requirements': [{'id': 'r1', 'kind': 'content',
                'acceptance': {'mode': 'presence', 'subject': '计算结果', 'source_quote': '计算'},
                'target': {'text': '页面介绍不是目标'}, 'evidence_route': {'depends_on': []}}],
            'steps': [
                {**common, 'action': 'type', 'target': {'control': 'c1'}, 'value': '10'},
                {**common, 'action': 'select', 'target': {'control': 'c2'}, 'value': '千克'},
                *[{**common, 'action': 'back'} for _ in range(3)]]}
        operation_before = deepcopy(operation_raw)
        validate(operation_raw, operation_schema(['type', 'select', 'back']))
        operation_normalized, operation_record = normalize_operation(
            operation_raw, ['type', 'select', 'back'])
        validate(operation_normalized, operation_schema(['type', 'select', 'back']))
        self.assertEqual(operation_raw, operation_before)
        requirement = operation_normalized['requirements'][0]
        self.assertEqual(requirement['description'], '计算结果')
        self.assertNotIn('target', requirement)
        self.assertNotIn('evidence_route', requirement)
        self.assertEqual(operation_normalized['steps'][0]['expected_value'], '10')
        self.assertEqual(operation_normalized['steps'][1]['expected_value'], '千克')
        self.assertFalse(operation_record.get('missing'))
        self.assertIn('type不会自动聚焦', FIRST_RULES['step_fields'])
        self.assertIn('本轮提交goal的逐字连续原文', FIRST_RULES['requirements'])
        # 封存校验与在线执行使用同一宿主编译顺序：省略或由宿主字段清空的
        # evidence_route 不是 None 对象错误；显式 null 仍须拒绝。
        from webcollect.screenshot_templates.operation.plan import verify_first_evidence_routes
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sealed = deepcopy(operation_normalized)
            sealed['requirements'][0]['evidence_route'] = {'source_type': 'page_content'}
            (root / '0001-screenshot-plan.json').write_text(__import__('json').dumps(sealed))
            (root / 'boundary.json').write_text('{}')
            record = {'receipt': {'boundary': {'path': str(root / 'boundary.json')},
                'files_sha256': {'0001-screenshot-plan.json': 'offline-fixture'}}}
            replay = SimpleNamespace(observation_records={}, provided_observations=[], region_registries={})
            verify_first_evidence_routes(record, replay)
            sealed['requirements'][0]['evidence_route'] = None
            (root / '0001-screenshot-plan.json').write_text(__import__('json').dumps(sealed))
            with self.assertRaisesRegex(ValueError, "None is not of type 'object'"):
                verify_first_evidence_routes(record, replay)
        from webcollect.failure_policy import disposition
        from webcollect.candidate_navigation import NavigationRejected
        self.assertEqual(disposition(NavigationRejected('NAVIGATION_SOURCE_UNPROVEN: no exact permission'))['disposition'], 'business')
        self.assertEqual(disposition(ValueError('NAVIGATION_SOURCE_UNPROVEN'))['disposition'], 'page_program')
        from site_planner.candidate_pool import CandidatePool
        heartbeat_pool = object.__new__(CandidatePool)
        heartbeat_pool.transaction = MagicMock()
        heartbeat_pool.transaction.return_value.__enter__.return_value = MagicMock()
        heartbeat_pool._fence = MagicMock()
        heartbeat_pool.pool = MagicMock()
        heartbeat_pool.pool.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {'expires':__import__('time').time()+300}
        heartbeat_pool.heartbeat({'claim_id': 'offline-claim'})
        self.assertLessEqual(heartbeat_pool.transaction.call_args.kwargs['timeout'], 90)
        heartbeat_pool._fence.assert_called_once()

    async def test_standalone_checks_scope_then_probes_once_and_stops_unavailable(self):
        from webcollect.current_chain import CurrentChainError
        with tempfile.TemporaryDirectory() as directory:
            pool = MagicMock()
            with patch('webcollect.key_health.probe_accounts') as probe:
                blocked = await run(pool, SimpleNamespace(config={'model': {'max_images': 1}}),
                    worker_id='single-image', request_prefix='blocked', limit=1, output=Path(directory),
                    registry='unused', policy='unused', history_set='unused')
            self.assertEqual((blocked['stop_reason'], blocked['processed']), ('engineering_failure', 0))
            self.assertEqual(blocked['stop_details']['disposition'], 'global')
            self.assertIn('STEPWISE_FINAL_IMAGES_UNAVAILABLE', str(blocked['stop_details']))
            pool.claim_next.assert_not_called()
            probe.assert_not_called()
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
            # Original GET bytes remain checked; candidate audit hashes do not
            # block a stable business identity before claim/IO.
            import json
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
                preflight_cohort_sources(SimpleNamespace(path=database),
                    [{**fixed,'sources_sha256':'outdated-audit','entry_http':ref}],'registry')
                preflight_cohort_sources(SimpleNamespace(path=database),
                    [{'candidate_id':'fixed','entry_http':ref}],'registry')
                receipt.write_text('{"changed":true}')
                with self.assertRaises(CurrentChainError):
                    preflight_cohort_sources(SimpleNamespace(path=database),
                        [{'candidate_id':'fixed','entry_http':ref}],'registry')
            self._check_fixed_strategy_before_probes(Path(directory))
            self._check_cohort_audit_hashes(Path(directory))

    def _check_fixed_strategy_before_probes(self, root):
        import json
        from webcollect import site_workers, collection_startup
        from webcollect.collection_strategy import Strategy1Forbidden, Strategy2Frozen
        from webcollect.failure_policy import disposition
        command=['python','-m','webcollect.candidate_consumer','run']
        plan={'role':'consumer','fixed':True,'plan_id':'offline-fixed',
            'scope':'scope.json','cohort':'cohort.json','log_root':str(root/'launcher'),
            'workers':[{'worker_id':'w1','command':command}]}
        rejected=[({**plan,'collection_strategy':name},fault)
                  for name,fault in [('screenshot_plan',Strategy2Frozen),('react',Strategy1Forbidden)]]
        rejected.extend(({**plan,'workers':[{'worker_id':'w1','command':command+flag}]},fault)
            for flag,fault in [(['--collection-strategy','screenshot_plan'],Strategy2Frozen),
                               (['--collection-strategy=react'],Strategy1Forbidden)])
        with patch('webcollect.collection_startup.check') as preflight, \
             patch('webcollect.key_health.probe_accounts') as probe, \
             patch.object(site_workers.subprocess,'Popen') as process:
            for old_plan,fault in rejected:
                with self.assertRaises(fault) as caught:
                    site_workers.launch(old_plan)
                self.assertEqual(disposition(caught.exception)['disposition'],'global')
                self.assertFalse(Path(plan['log_root']).exists())
            preflight.assert_not_called();probe.assert_not_called();process.assert_not_called()
        with patch('webcollect.site_inventory.load_scope') as read_scope:
            with self.assertRaises(Strategy2Frozen) as caught:
                collection_startup.check('scope.json',plan={**plan,'collection_strategy':'screenshot_plan'})
            self.assertEqual(disposition(caught.exception)['disposition'],'global')
            read_scope.assert_not_called()
        cohort={'selected':[{'candidate_id':f'c{i}','application_id':'app'} for i in range(100)]}
        for marker,fault in [({'collection_strategy':'screenshot_plan'},Strategy2Frozen),
                             ({'collection_strategy':'react'},Strategy1Forbidden),({},Strategy2Frozen)]:
            with patch.object(site_workers,'load_scope',return_value=(Path('scope.json'),{})), \
                 patch('webcollect.batch_core.load_json',side_effect=[cohort,marker]), \
                 patch('webcollect.batch_core.save_json') as shard:
                with self.assertRaises(fault) as caught:
                    site_workers.fixed_consumer_plan('scope.json','cohort.json',root/'old-resume',
                        resume_from='previous.json')
                self.assertEqual(disposition(caught.exception)['disposition'],'global')
                self.assertFalse((root/'old-resume').exists());shard.assert_not_called()
        with patch.object(site_workers,'fixed_consumer_plan',return_value=rejected[0][0]), \
             patch('sys.stderr',new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as caught:
                site_workers.main(['fixed-consumer','--scope','scope.json','--cohort','cohort.json',
                    '--log-root',plan['log_root'],'--launch'])
            self.assertEqual(caught.exception.code,2)
        child=MagicMock();child.pid=12345;child.poll.return_value=0
        with patch('webcollect.collection_startup.check',return_value={'status':'PASS'}), \
             patch.object(site_workers,'load_scope',return_value=(Path('scope.json'),
                 {'consumer_db':'offline.sqlite3','consumer_config':'offline.json'})), \
             patch('webcollect.batch_core.load_json',return_value={}), \
             patch.object(site_workers,'BatchLedger'), \
             patch('webcollect.key_health.pool_available',return_value=True), \
             patch('webcollect.key_health.probe_accounts') as probe, \
             patch.object(site_workers.subprocess,'Popen',return_value=child) as process, \
             patch.object(site_workers,'automatic_report'):
            summary=site_workers.launch(plan)
        self.assertTrue(summary['succeeded']);probe.assert_not_called()
        persisted=json.loads((Path(plan['log_root'])/'plan.json').read_text())
        self.assertEqual(persisted['collection_strategy'],'stepwise')
        self.assertEqual(persisted['workers'][0]['command'][-2:],['--collection-strategy','stepwise'])
        self.assertEqual(process.call_args.args[0],persisted['workers'][0]['command'])

    def _check_cohort_audit_hashes(self, root):
        from webcollect.collection_startup import check
        config=root/'startup-config.json';config.write_text('{"model":{"max_images":3}}')
        cohort=root/'startup-cohort.json';cohort.write_text('{}')
        scope={key:str(config) for key in ('producer_config','consumer_config','policy','history_set')}
        scope.update(pool='pool',producer_db='producer',consumer_db='consumer',registry='registry',output=str(root))
        rows=[{'candidate_id':f'c{i}','version':1,'application_id':'app',
            'producer_batch':'batch','producer_row_id':f'r{i}','entry_http':{'path':'original','sha256':'receipt'},
            'producer_row_response_sha256':'old','body_sha256':'old','sources_sha256':'old'} for i in range(100)]
        current=[{**row,'eligible':True,'producer_row_response_sha256':'new',
            'body_sha256':'new','sources_sha256':'new'} for row in rows]
        connection=MagicMock();connection.execute.return_value.fetchone.return_value=(config.read_text(),)
        pool=MagicMock();poolcon=pool.pool.connect.return_value.__enter__.return_value
        poolcon.execute.return_value.fetchone.return_value={'version':1,'state':'pending'}
        poolcon.execute.return_value.fetchall.return_value=[]
        with patch('webcollect.site_inventory.load_scope',return_value=(config,scope)), \
             patch('webcollect.collection_startup.required_schema',return_value={}), \
             patch('webcollect.collection_startup.connect',return_value=connection), \
             patch('webcollect.current_chain.read_chain_scope'), \
             patch('webcollect.current_chain.assert_current_result_path'), \
             patch('webcollect.current_chain.check_project_guard'), \
             patch('site_planner.candidate_pool.CandidatePool',return_value=pool), \
             patch('webcollect.candidate_consumer._cohort_rows',return_value=('batch',rows)), \
             patch('webcollect.candidate_cohort.inspect_rows',return_value=(None,current,None)), \
             patch('webcollect.candidate_consumer.preflight_cohort_sources') as originals:
            result=check(config,cohort_path=cohort,minimum_free_bytes=0)
            self.assertEqual(result['status'],'PASS',result)
            originals.assert_called_once_with(pool,rows,scope['registry'])
            current[0]['entry_http']={'path':'different','sha256':'different'}
            result=check(config,cohort_path=cohort,minimum_free_bytes=0)
            self.assertIn('COHORT_EVIDENCE_MISMATCH',[e['code'] for e in result['errors']])
            connection.execute.return_value.fetchone.return_value=('{"model":{"max_images":1}}',)
            errors = {e['code'] for e in check(config, minimum_free_bytes=0)['errors']}
            self.assertTrue({'CONFIG_BINDING_MISMATCH', 'STEPWISE_FINAL_IMAGES_UNAVAILABLE'} <= errors)
            config.write_text('{"model":{"max_images":1}}')
            self.assertEqual(check(config, launch_role='producer', minimum_free_bytes=0)['status'], 'PASS')
            blocked = check(config, minimum_free_bytes=0)
            self.assertEqual([e['code'] for e in blocked['errors']], ['STEPWISE_FINAL_IMAGES_UNAVAILABLE'])
            self.assertEqual([blocked[k] for k in ('dispatches','browser_calls','account_probes','ledger_writes')], [0]*4)

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
