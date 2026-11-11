"""Strategy-2 display logging: runlog records, gateway model-calls, session loop.

Isolated temp directories and the synthetic ReactHarness surface only. The
simulated model transport goes through the real screenshot_chooser /
ModelGateway parse, normalize, validate and settle chain. No live site, real
provider HTTP, production ledger, QC or customer export runs here.
"""
import asyncio
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import test_model_provider_protocols as provider_fixtures
from test_react_session import ReactHarness
from webcollect.batch_core import BatchLedger, OutcomeUnknown, load_json, object_sha256
from webcollect.model_gateway import ModelGateway
from webcollect.runlog import (SessionLog, for_claim, for_direct_run,
                               image_references, sanitize_debug)
from webcollect.plan_protocol import ENDING_POLICY as COMPLETE_VERSION
from webcollect.react_session import build_url_task, validate_task
from webcollect.collection_strategy import (STRATEGY_SCREENSHOT_PLAN,
    freeze as freeze_strategy)
from webcollect.screenshot_plan import submit_plan_tools
from webcollect.screenshot_session import ScreenshotPlanSession


def _rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]


class SessionLogUnitTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_stderr_runtime_line_and_jsonl_share_one_session_id(self):
        log = SessionLog(self.root, 'w1', 'claim-1', STRATEGY_SCREENSHOT_PLAN,
                         claim_id='claim-1', candidate_id='c1')
        log.attach(attemptId='a1', sessionId='must-not-change')
        stderr, stdout = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            log.info('claim', claimId='claim-1', candidateId='c1')
        line = stderr.getvalue().strip()
        self.assertEqual(stdout.getvalue(), '')
        self.assertIn('sessionId=claim-1', line)
        self.assertIn('event=claim', line)
        self.assertIn('attemptId=a1', line)
        self.assertIn('sampleId=null', line)
        rows = _rows(self.root / 'logs' / 'w1' / 'runtime.jsonl')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['event'], 'claim')
        self.assertEqual(rows[0]['sessionId'], 'claim-1')
        self.assertIsNone(rows[0]['sampleId'])
        self.assertEqual(rows[0]['attemptId'], 'a1')

    def test_model_calls_and_debug_are_separate_and_debug_is_gated(self):
        log = SessionLog(self.root, 'w1', 'claim-1', STRATEGY_SCREENSHOT_PLAN,
                         claim_id='claim-1', level='DEBUG')
        log.model_call(requestId='r1', state='succeeded', inputTokens=250)
        log.model_debug(requestId='r1', payload={
            'Authorization': 'Bearer offline-secret',
            'messages': [{'content': 'data:image/png;base64,' + 'A' * 32}],
            'nested': [{'api_key': 'offline-secret', 'reasoning_content': 'opaque'}],
        })
        calls = _rows(self.root / 'logs' / 'w1' / 'model-calls.jsonl')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['requestId'], 'r1')
        self.assertFalse((self.root / 'logs' / 'w1' / 'runtime.jsonl').exists())
        debug = _rows(self.root / 'logs' / 'w1' / 'model-debug.jsonl')
        self.assertEqual(len(debug), 1)
        self.assertEqual(debug[0]['payload']['Authorization'], '<omitted>')
        self.assertEqual(debug[0]['payload']['nested'][0]['api_key'], '<omitted>')
        self.assertEqual(debug[0]['payload']['nested'][0]['reasoning_content'], '<omitted>')
        self.assertTrue(debug[0]['payload']['messages'][0]['content'].startswith('<data-url-omitted:'))
        info = SessionLog(self.root, 'w2', 'claim-2', STRATEGY_SCREENSHOT_PLAN,
                          claim_id='claim-2', level='INFO')
        info.model_debug(requestId='r2', payload={'Authorization': 'x'})
        self.assertFalse((self.root / 'logs' / 'w2' / 'model-debug.jsonl').exists())

    def test_sanitize_debug_is_recursive_and_case_insensitive(self):
        value = {'headers': {'Cookie': 'session=1', 'api-key': 'k'},
                 'list': [{'Token': 't', 'Password': 'p'}]}
        clean = sanitize_debug(value)
        self.assertEqual(clean['headers']['Cookie'], '<omitted>')
        self.assertEqual(clean['headers']['api-key'], '<omitted>')
        self.assertEqual(clean['list'][0]['Token'], '<omitted>')
        self.assertEqual(clean['list'][0]['Password'], '<omitted>')

    def test_image_references_keep_files_not_base64(self):
        image = self.root / 'shot.png'
        Image.new('RGB', (8, 6), 'white').save(image)
        reference = image_references([image])[0]
        self.assertEqual(set(reference), {'path', 'sha256', 'bytes', 'width', 'height'})
        self.assertEqual((reference['width'], reference['height']), (8, 6))
        self.assertNotIn(str(image.read_bytes())[:50], json.dumps(reference))

    def test_write_failure_warns_once_and_never_raises(self):
        blocker = self.root / 'blocker'
        blocker.write_text('not a directory', encoding='utf-8')
        log = SessionLog(self.root, 'w1', 'claim-1', STRATEGY_SCREENSHOT_PLAN,
                         claim_id='claim-1', log_dir=blocker / 'sub')
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            log.info('claim', claimId='claim-1')
            log.info('failed', reason='still running')
            log.model_call(requestId='r1')
            log.model_call(requestId='r2')
        # One warning per destination file, never per record.
        self.assertEqual(stderr.getvalue().count('日志写入失败'), 2)
        self.assertFalse((blocker / 'sub').exists())

    def test_session_id_sources(self):
        claim = {'claim_id': 'CL-9', 'candidate_id': 'C-9'}
        self.assertEqual(for_claim(self.root, 'w1', claim).session_id, 'CL-9')
        first = for_direct_run(self.root).session_id
        second = for_direct_run(self.root).session_id
        self.assertNotEqual(first, second)
        self.assertTrue(first and second)


class GatewayRunlogTests(unittest.TestCase):
    """Model-call records for the real gateway settle chain, offline transport."""

    def setUp(self):
        self.fixture = provider_fixtures.NativeToolProtocolTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.fixture
        self.serial = 0

    def _gateway(self, level='INFO'):
        self.serial += 1
        cfg = self.f.config('glm', vision=True)
        cfg['budget']['min_model_interval_seconds'] = 0
        ledger = BatchLedger(self.f.root / f'runlog-{self.serial}.sqlite3', cfg,
                             initialize=True)
        job = ledger.claim('test', job_id=ledger.enqueue('test', {'offline': True}))
        runlog = SessionLog(self.f.root, 'w1', 'claim-1', STRATEGY_SCREENSHOT_PLAN,
                            level=level, claim_id='claim-1')
        gateway = ModelGateway(ledger, runlog=runlog)
        # Offline transport: freeze the credential so the non-core GLM account
        # selection in model_credentials never runs here.
        gateway._credential = 'CONTROLLED_UNUSED'
        gateway._session_id = 'claim-1'
        return ledger, job, gateway, runlog

    def _calls(self, runlog, worker='w1'):
        return _rows(self.f.root / 'logs' / worker / 'model-calls.jsonl')

    def _ledger_request_ids(self, ledger):
        with ledger.connect() as con:
            return [row[0] for row in con.execute('SELECT id FROM model_requests ORDER BY id')]

    def test_succeeded_request_logs_started_finished_and_usage(self):
        ledger, job, gateway, runlog = self._gateway()
        self.fixture.response(self.fixture.message())
        self.fixture.call(gateway, job, attempt_id='claim-1')
        rows = self._calls(runlog)
        started = [row for row in rows if row['event'] == 'request_started']
        finished = [row for row in rows if row['event'] == 'request_finished']
        self.assertEqual(len(started), 1)
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]['state'], 'succeeded')
        self.assertEqual(finished[0]['requestId'], started[0]['requestId'])
        self.assertIn(started[0]['requestId'], self._ledger_request_ids(ledger))
        self.assertEqual(finished[0]['sessionId'], 'claim-1')
        self.assertEqual(finished[0]['jobId'], job['id'])
        self.assertEqual(finished[0]['inputTokens'], 250)
        self.assertEqual(finished[0]['outputTokens'], 50)
        self.assertEqual(finished[0]['totalTokens'], 300)
        self.assertEqual(finished[0]['cachedInputTokens'], 100)
        self.assertIsNotNone(finished[0]['elapsedMs'])
        self.assertIsNotNone(finished[0]['startedAt'])
        self.assertIsNotNone(finished[0]['endedAt'])

    def test_missing_usage_is_null_not_zero(self):
        _, job, gateway, runlog = self._gateway()
        self.fixture.response(self.fixture.message())
        self.f.opener.raw.pop('usage')
        with self.assertRaises(OutcomeUnknown):
            self.fixture.call(gateway, job, attempt_id='claim-1')
        finished = [row for row in self._calls(runlog)
                    if row['event'] == 'request_finished']
        self.assertEqual(finished[0]['state'], 'unknown')
        for key in ('inputTokens', 'outputTokens', 'totalTokens', 'cachedInputTokens'):
            self.assertIsNone(finished[0][key], key)

    def test_exact_replay_is_one_cache_hit_without_new_request(self):
        _, job, gateway, runlog = self._gateway()
        self.fixture.response(self.fixture.message())
        first = self.fixture.call(gateway, job, attempt_id='claim-1', images=[self.f.image])
        replay = self.fixture.call(gateway, job, attempt_id='claim-1', images=[self.f.image])
        self.assertEqual(replay, first)
        rows = self._calls(runlog)
        hits = [row for row in rows if row['event'] == 'cache_hit']
        finished = [row for row in rows if row['event'] == 'request_finished']
        self.assertEqual(len(hits), 1)
        self.assertEqual(len(finished), 1)
        self.assertEqual(hits[0]['reusedRequestId'], finished[0]['requestId'])
        self.assertEqual(len(self.f.opener.calls), 1)

    def test_timeout_retry_gets_its_own_request_id_and_records(self):
        _, job, gateway, runlog = self._gateway()
        original = self.f.opener.open

        def send(request, timeout):
            if len(self.f.opener.calls) == 0:
                self.f.opener.calls.append(request)
                raise TimeoutError()
            return original(request, timeout)

        self.f.opener.open = send
        self.fixture.response(self.fixture.message())
        self.fixture.call(gateway, job, attempt_id='claim-1')
        rows = self._calls(runlog)
        retries = [row for row in rows if row['event'] == 'timeout_retry_scheduled']
        started = [row for row in rows if row['event'] == 'request_started']
        finished = [row for row in rows if row['event'] == 'request_finished']
        self.assertEqual([row['state'] for row in finished], ['unknown', 'succeeded'])
        self.assertEqual(len(started), 2)
        self.assertEqual(retries[0]['retryNumber'], 1)
        self.assertEqual(len({row['requestId'] for row in started}), 2)
        self.assertEqual(len(self.f.opener.calls), 2)

    def test_invalid_response_still_records_its_usage(self):
        _, job, gateway, runlog = self._gateway()
        self.fixture.response(self.fixture.message(arguments='{"answer":'))
        with self.assertRaises(ValueError):
            self.fixture.call(gateway, job, attempt_id='claim-1', attempts=2)
        finished = [row for row in self._calls(runlog)
                    if row['event'] == 'request_finished']
        self.assertTrue(finished)
        self.assertEqual({row['state'] for row in finished}, {'invalid_response'})
        self.assertEqual(finished[0]['inputTokens'], 250)

    def test_debug_level_records_sanitized_wire_in_and_out(self):
        _, job, gateway, runlog = self._gateway(level='DEBUG')
        self.fixture.response(self.fixture.message())
        self.fixture.call(gateway, job, attempt_id='claim-1', images=[self.f.image])
        debug = _rows(self.f.root / 'logs' / 'w1' / 'model-debug.jsonl')
        directions = {row['direction'] for row in debug}
        self.assertEqual(directions, {'request', 'response'})
        wire = [row for row in debug if row['direction'] == 'request'][0]
        self.assertIn('payload', wire)
        self.assertIn('images', wire)
        blob = json.dumps(debug)
        self.assertNotIn('offline-secret-never-export', blob)
        self.assertNotIn('opaque-offline-protocol-field', blob)
        self.assertNotIn('data:image/png;base64,', blob)
        self.assertTrue(any(entry['path'].endswith('.png') for entry in wire['images']))

    def test_no_runlog_keeps_gateway_quiet_and_unchanged(self):
        cfg = self.f.config('glm', vision=True)
        cfg['budget']['min_model_interval_seconds'] = 0
        ledger = BatchLedger(self.f.root / 'plain.sqlite3', cfg, initialize=True)
        job = ledger.claim('test', job_id=ledger.enqueue('test', {'offline': True}))
        gateway = ModelGateway(ledger)
        gateway._credential = 'CONTROLLED_UNUSED'
        gateway._session_id = 'claim-1'
        self.fixture.response(self.fixture.message())
        self.fixture.call(gateway, job, attempt_id='claim-1')
        self.assertFalse((self.f.root / 'logs').exists())
        self.assertEqual(ledger.summary()['usage_covered_requests'], 1)


class ChooserRunlogTests(unittest.IsolatedAsyncioTestCase):
    """Simulated provider transport through the real screenshot_chooser chain."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.opener = provider_fixtures.StubOpener()
        env = patch.dict('os.environ', {'WEBCOLLECT_OFFLINE_TEST_KEY': 'offline-secret-never-export'})
        dns = patch('webcollect.model_gateway.socket.getaddrinfo',
                    return_value=[('CONTROLLED_DNS',)])
        http = patch('urllib.request.build_opener', return_value=self.opener)
        for mock in (env, dns, http):
            mock.start()
            self.addCleanup(mock.stop)
        self.image = self.root / 'first.png'
        Image.new('RGB', (8, 8), 'white').save(self.image)
        self.task = build_url_task(url='https://example.org/', task_version='runlog-fixture',
                                    ending_policy=COMPLETE_VERSION)
        freeze_strategy(self.task, STRATEGY_SCREENSHOT_PLAN)
        self.task['task_id'] = 'react-' + object_sha256(
            {'url': self.task['initial_url'], 'spec': self.task['workflow_proposal']['spec']})[:24]
        validate_task(self.task)

    async def test_chooser_parses_native_submit_plan_and_logs_model_calls(self):
        from webcollect.screenshot_plan import screenshot_chooser
        config = load_json(provider_fixtures.CONFIG)
        config['mode'] = 'real'
        config['budget'].update(currency='OFFLINE_TEST_UNITS', max_model_cost_micros=1_000_000,
                                min_model_interval_seconds=0)
        config['model']['rates'].update(input=1, output=1, version='OFFLINE_TEST',
                                        source='OFFLINE_TEST')
        config['model'].update(provider='glm', model='glm-5.3-flash',
                               endpoint='https://provider.invalid/chat/completions',
                               api_key_env='WEBCOLLECT_OFFLINE_TEST_KEY', reserve_cost_micros=100_000,
                               supports_vision=True, image_tokens_per_image=1200,
                               request_overhead_tokens=128)
        ledger = BatchLedger(self.root / 'chooser.sqlite3', config, initialize=True)
        runlog = SessionLog(self.root, 'w1', 'claim-1', STRATEGY_SCREENSHOT_PLAN,
                            level='DEBUG', claim_id='claim-1')
        plan = {'goal': '阅读正文并回答原名',
                'requirements': [{'id': 'r1', 'description': '阅读正文并回答原名'}],
                'steps': [{'action': 'scroll', 'direction': 'down', 'purpose': f'阅读第{i}段',
                           'rationale': '逐段滚动阅读正文以找到答案',
                           'expected_result': '看到下一段正文'} for i in range(5)]}
        self.opener.raw['choices'] = [{'finish_reason': 'tool_calls', 'message': {
            'content': '', 'reasoning_content': 'opaque-offline-protocol-field',
            'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {
                'name': 'submit_plan', 'arguments': json.dumps(plan, ensure_ascii=False)}}]}}]
        prompt = {'phase': 'first', 'system': 'trusted', 'tools': submit_plan_tools(
            self.task['fragment']['allowed_actions']), '_images': [self.image],
            'progress': {'decisions_used': 0}}
        # Offline transport: freeze the credential so the non-core GLM account
        # selection in model_credentials never runs here.
        with patch('webcollect.batch_core.BatchLedger.bind_model_session',
                   return_value='CONTROLLED_UNUSED'):
            choose = screenshot_chooser(ledger, self.task, 'claim-1', runlog=runlog)
            response = await choose(prompt)
        self.assertEqual(response['name'], 'submit_plan')
        self.assertEqual(len(response['arguments']['steps']), 5)
        calls = _rows(self.root / 'logs' / 'w1' / 'model-calls.jsonl')
        started = [row for row in calls if row['event'] == 'request_started']
        finished = [row for row in calls if row['event'] == 'request_finished']
        self.assertEqual(len(started), 1)
        self.assertEqual(finished[0]['state'], 'succeeded')
        self.assertEqual(finished[0]['sessionId'], 'claim-1')
        self.assertTrue(finished[0]['stage'].startswith(STRATEGY_SCREENSHOT_PLAN))
        debug = _rows(self.root / 'logs' / 'w1' / 'model-debug.jsonl')
        blob = json.dumps(debug)
        self.assertNotIn('opaque-offline-protocol-field', blob)
        self.assertNotIn('offline-secret-never-export', blob)
        self.assertNotIn('data:image/png;base64,', blob)


class ScreenshotSessionRunlogTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    """Session-loop runtime events and unchanged business results."""

    def setUp(self):
        super().setUp()
        self.task = build_url_task(url=self.page.url, task_version='s2-runlog',
                                    ending_policy=COMPLETE_VERSION)
        freeze_strategy(self.task, STRATEGY_SCREENSHOT_PLAN)
        self.task['task_id'] = 'react-' + object_sha256(
            {'url': self.task['initial_url'], 'spec': self.task['workflow_proposal']['spec']})[:24]
        validate_task(self.task)
        self.attempt_id = 's2-runlog-attempt'
        state = self.surface.state
        state['elements'][0]['text'] = '数量'
        state['elements'][1]['text'] = '成本'
        for binding in state['capture_controls']:
            binding['form_selector'] = '#calculator'
        state['elements'].append({'element_id': 'submit-result', 'text': '计算',
            'native_role': 'button', 'element_type': 'button', 'bbox': [10, 200, 210, 240],
            'visible': True, 'enabled': True, 'clickable': True, 'inputable': False,
            'parent_id': 'root', 'scrollable': False, 'state': 'default'})
        state['capture_controls'].append({'element_id': 'submit-result',
            'selector': '#submit-result', 'tag': 'button', 'input_type': 'submit',
            'form_selector': '#calculator'})
        state['elements'].append({'element_id': 'visible-result', 'text': '利润率：40%',
            'native_role': 'status', 'element_type': 'p', 'bbox': [10, 260, 800, 320],
            'visible': True, 'enabled': True, 'clickable': False, 'inputable': False,
            'parent_id': 'root', 'scrollable': False, 'state': 'default'})
        state['capture_controls'].append({'element_id': 'visible-result',
            'selector': '#actual-result', 'tag': 'p', 'form_selector': '#calculator',
            'result_region_selector': '#actual-result'})

    def _steps(self):
        return [
            {'action': 'click', 'target': {'text': '数量'}, 'purpose': '聚焦数量输入框',
             'rationale': '需要先在数量输入框输入新值', 'expected_result': '数量输入框获得焦点'},
            {'action': 'hotkey', 'keys': ['ctrl', 'a'], 'target': {'text': '数量'},
             'purpose': '全选原值', 'rationale': '全选后才能替换旧值',
             'expected_result': '旧值被完整选中'},
            {'action': 'type', 'target': {'text': '数量'}, 'value': '20',
             'purpose': '输入数量20', 'rationale': '本次计算使用数量20',
             'expected_result': '数量显示为20', 'expected_value': '20'},
            {'action': 'click', 'target': {'text': '成本'}, 'purpose': '聚焦成本输入框',
             'rationale': '成本同样需要输入本次值', 'expected_result': '成本输入框获得焦点'},
            {'action': 'type', 'target': {'text': '成本'}, 'value': '60',
             'purpose': '输入成本60', 'rationale': '本次计算使用成本60',
             'expected_result': '成本显示为60'},
            {'action': 'click', 'target': {'text': '计算'}, 'purpose': '提交计算',
             'rationale': '提交后页面才会计算本次利润率',
             'expected_result': '结果区显示本次利润率'},
        ]

    def _plan(self):
        return {'goal': '修改数量为20并查看本次利润率结果',
                'requirements': [
                    {'id': 'r1', 'description': '查看本次输入对应的利润率计算结果'}],
                'steps': self._steps()}

    def _session(self, name, choose, runlog=None):
        evidence = self.root / name / 'evidence' / 'S000001_sample_000201'
        kwargs = {'steps_directory': evidence, 'attempt_id': self.attempt_id}
        if runlog is not None:
            kwargs['runlog'] = runlog
        return ScreenshotPlanSession(self.task, evidence / 'raw', choose, self.page,
                                     **kwargs), evidence

    def _choose(self, prompts):
        async def choose(prompt):
            prompts.append(deepcopy(prompt))
            if prompt.get('phase') == 'first':
                return {'name': 'submit_plan', 'arguments': self._plan(),
                        'tool_call_id': 'first', 'assistant_message': {'role': 'assistant'},
                        'request_id': 'mock'}
            regions = prompt.get('regions') or []
            region = next((r for r in regions if '利润率' in r.get('quote', '')), None)
            if region is None:
                return {'name': 'plan_decision', 'arguments': {
                    'decision': 'continue', 'reason': '继续查看结果'},
                    'tool_call_id': 'continue', 'request_id': 'mock'}
            return {'name': 'plan_decision', 'arguments': {
                'decision': 'complete', 'reason': '本次提交的利润率结果已经可见',
                'answers': [{'requirement_id': 'r1', 'observed_result': '利润率：40%',
                             'evidence': [{'observation': prompt['current_observation'],
                                           'region': region['region_id']}]}]},
                'tool_call_id': 'complete', 'request_id': 'mock'}
        return choose

    async def test_runtime_log_covers_lifecycle_and_never_emits_success(self):
        prompts = []
        runlog = SessionLog(self.root, 'w1', 'claim-1', STRATEGY_SCREENSHOT_PLAN,
                            claim_id='claim-1', attempt_id=self.attempt_id)
        session, _ = self._session('logged', self._choose(prompts), runlog=runlog)
        summary = await session.run()
        rows = _rows(self.root / 'logs' / 'w1' / 'runtime.jsonl')
        events = [row['event'] for row in rows]
        for expected in ('plan_accepted', 'checkpoint', 'action_started',
                         'action_finished', 'goal_verified', 'session_end'):
            self.assertIn(expected, events)
        self.assertNotIn('success', events)
        self.assertEqual({row['sessionId'] for row in rows}, {'claim-1'})
        self.assertEqual(summary['stop_reason'], 'ready')
        self.assertEqual(summary['strategy_end_reason'], 'goal_completed')
        self.assertTrue(summary['effective_steps'] >= 5)

    async def test_runlog_does_not_change_the_business_result(self):
        # Both runs must start from the same page surface: the first session's
        # typing changes input values, so restore the captured initial state.
        initial_values = deepcopy(self.surface.state['values'])
        initial_result = self.surface.state['elements'][-1]['text']
        quiet, _ = self._session('quiet', self._choose([]))
        without = await quiet.run()
        self.surface.state['values'] = deepcopy(initial_values)
        self.surface.state['elements'][-1]['text'] = initial_result
        loud_log = SessionLog(self.root, 'w2', 'claim-2', STRATEGY_SCREENSHOT_PLAN,
                              claim_id='claim-2', attempt_id=self.attempt_id)
        loud, _ = self._session('loud', self._choose([]), runlog=loud_log)
        with_log = await loud.run()
        for key in ('stop_reason', 'strategy_end_reason', 'goal_status',
                    'effective_steps', 'actual_actions', 'host_failure', 'unknown'):
            self.assertEqual(without[key], with_log[key], key)

    async def test_cancelled_session_logs_cancellation_and_keeps_raw(self):
        runlog = SessionLog(self.root, 'w1', 'claim-1', STRATEGY_SCREENSHOT_PLAN,
                            claim_id='claim-1', attempt_id=self.attempt_id)

        async def choose(prompt):
            if prompt.get('phase') == 'first':
                return {'name': 'submit_plan', 'arguments': self._plan(),
                        'tool_call_id': 'first', 'assistant_message': {'role': 'assistant'},
                        'request_id': 'mock'}
            await asyncio.sleep(30)
            raise AssertionError('unreachable')

        session, evidence = self._session('cancelled', choose, runlog=runlog)
        task = asyncio.ensure_future(session.run())
        await asyncio.sleep(0.05)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        rows = _rows(self.root / 'logs' / 'w1' / 'runtime.jsonl')
        events = [row['event'] for row in rows]
        self.assertIn('cancelled', events)
        self.assertTrue((evidence / 'raw').exists())

    async def test_unknown_decision_is_logged_as_unknown_not_resend(self):
        from webcollect.batch_core import OutcomeUnknown

        async def choose(prompt):
            if prompt.get('phase') == 'first':
                raise OutcomeUnknown('provider outcome/charge UNKNOWN; request retained: r9')
            raise AssertionError('unreachable')

        runlog = SessionLog(self.root, 'w1', 'claim-1', STRATEGY_SCREENSHOT_PLAN,
                            claim_id='claim-1', attempt_id=self.attempt_id)
        session, _ = self._session('unknown', choose, runlog=runlog)
        summary = await session.run()
        rows = _rows(self.root / 'logs' / 'w1' / 'runtime.jsonl')
        self.assertIn('session_end', [row['event'] for row in rows])
        self.assertTrue(summary['unknown'])
        self.assertEqual(summary['failure_class'], 'interrupted')

    async def test_concurrent_sessions_do_not_cross_logs(self):
        runlog_a = SessionLog(self.root, 'wa', 'claim-a', STRATEGY_SCREENSHOT_PLAN,
                              claim_id='claim-a', attempt_id=self.attempt_id)
        runlog_b = SessionLog(self.root, 'wb', 'claim-b', STRATEGY_SCREENSHOT_PLAN,
                              claim_id='claim-b', attempt_id=self.attempt_id)
        session_a, _ = self._session('parallel-a', self._choose([]), runlog=runlog_a)
        session_b, _ = self._session('parallel-b', self._choose([]), runlog=runlog_b)
        await asyncio.gather(session_a.run(), session_b.run())
        for worker, session_id in (('wa', 'claim-a'), ('wb', 'claim-b')):
            rows = _rows(self.root / 'logs' / worker / 'runtime.jsonl')
            self.assertTrue(rows)
            self.assertEqual({row['sessionId'] for row in rows}, {session_id})


if __name__ == '__main__':
    unittest.main()
