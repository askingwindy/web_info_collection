"""Strategy-2 display logging: runlog records, gateway model-calls, session loop.

Isolated temp directories and the synthetic ReactHarness surface only. The
simulated model transport goes through the real screenshot_chooser /
ModelGateway parse, normalize, validate and settle chain. No live site, real
provider HTTP, production ledger, QC or customer export runs here.
"""
import asyncio
from copy import deepcopy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

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


CONFIG = Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json'
_TOOLS_SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'integer'}},
                 'required': ['answer'], 'additionalProperties': False}


class StubOpener:
    def __init__(self):
        self.calls = []
        self.error = None
        self.raw = {'id': 'offline-provider-response', 'model': 'offline-model-version',
                    'usage': {'prompt_tokens': 250, 'completion_tokens': 50,
                              'prompt_tokens_details': {'cached_tokens': 100}},
                    'choices': [{'finish_reason': 'stop', 'message': {'content': '{"answer":42}'}}]}

    def open(self, request, timeout):
        self.calls.append(request)
        if self.error:
            raise self.error
        return io.BytesIO(json.dumps(self.raw).encode())


class _GatewayHarness(unittest.TestCase):
    """Offline native-tool transport: stub HTTP, controlled DNS/env, no real key."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.opener = StubOpener()
        for mock in (patch.dict('os.environ', {'WEBCOLLECT_OFFLINE_TEST_KEY': 'offline-secret-never-export'}),
                     patch('webcollect.model_gateway.socket.getaddrinfo', return_value=[('CONTROLLED_DNS',)]),
                     patch('urllib.request.build_opener', return_value=self.opener)):
            mock.start()
            self.addCleanup(mock.stop)
        self.image = self.root / 'original.png'
        Image.new('RGB', (8, 8), 'white').save(self.image)
        self.serial = 0
        self.tools = [{'type': 'function', 'function': {'name': 'act', 'parameters': _TOOLS_SCHEMA}}]

    def config(self, provider='glm', *, vision=False):
        value = load_json(CONFIG)
        value['mode'] = 'real'
        value['budget'].update(currency='OFFLINE_TEST_UNITS', max_model_cost_micros=1_000_000,
                               min_model_interval_seconds=1)
        value['model'].update(provider=provider, model='explicit-offline-model',
                              endpoint='https://provider.invalid/chat/completions',
                              api_key_env='WEBCOLLECT_OFFLINE_TEST_KEY', reserve_cost_micros=100_000,
                              supports_vision=vision, image_tokens_per_image=1200 if vision else 0,
                              request_overhead_tokens=128)
        value['model']['rates'] = {'version': 'OFFLINE-TEST-NOT-PRICES', 'source': 'Mock protocol only',
                                   'input': 1_000_000, 'cached_input': 500_000, 'output': 2_000_000}
        return value

    def gateway(self, config):
        self.serial += 1
        ledger = BatchLedger(self.root / f'ops-{self.serial}.sqlite3', config, initialize=True)
        job = ledger.claim('test', job_id=ledger.enqueue('test', {'offline': True}))
        return ledger, job, ModelGateway(ledger)

    def message(self, cid='tc1', name='act', arguments='{"answer":7}'):
        return {'role': 'assistant', 'content': None, 'reasoning_content': 'opaque-offline-protocol-field',
                'tool_calls': [{'id': cid, 'type': 'function',
                                'function': {'name': name, 'arguments': arguments}}]}

    def response(self, message):
        self.opener.raw['choices'] = [{'finish_reason': 'tool_calls', 'message': message}]

    def call(self, gateway, job, **kw):
        return gateway.call_tool(job, 'tools', 'current observation', self.tools,
                                 system='trusted policy', reasoning_effort='low', **kw)


def _make_png(token):
    stream = io.BytesIO()
    Image.new('RGB', (1280, 720), ((token >> 16) & 255, (token >> 8) & 255, token & 255)).save(stream, 'PNG')
    return stream.getvalue()


class OfflineSurface:
    """Synthetic page: same trusted-capture shape the agent loop consumes."""

    def __init__(self, state):
        self.state = deepcopy(state)
        self.state.update(document_identity={'url_without_fragment': self.state['url'],
                                             'performance_time_origin': 123},
                          scroll=[0, 0], screen_resolution=[1280, 720], target=None,
                          title='受控输入页面')
        self.state['visible_text'] = '受控输入页面\n数量\n成本\n这里查看当前输入内容与页面状态。'
        for i, row in enumerate(self.state['elements']):
            row.update(bbox=[10, 20 + i * 60, 210, 60 + i * 60], enabled=True, visible=True,
                       element_type='input' if row.get('inputable') else 'text', state='default',
                       parent_id='root', native_role='input' if row.get('inputable') else 'p',
                       scrollable=False)
        for value in self.state['values']:
            value.update(selection_start=0, selection_end=0, input_type='text', value_visible=True)
        self.readable = True
        self.executed = []
        self.history = [self.state['url']]

    async def capture(self, page, selector=None, index=0, **kw):
        state = deepcopy(self.state)
        state['visible_text'] += '\n' + '\n'.join(e.get('text', '') for e in state['elements'])
        for value in state['values']:
            value['display_value'] = value['value']
        # Synthetic capture keeps the current production evidence shape.
        # These are fixture witnesses, never browser/production receipts.
        state['capture_readiness'] = {'document_ready': 'complete', 'fonts_ready': True, 'images_ready': True}
        state['geometry_witnesses'] = []
        for row in state['elements']:
            left, top, right, bottom = row['bbox']
            coordinate = [30, top + 10]
            state['geometry_witnesses'].append({
                'element_id': row['element_id'], 'bbox': row['bbox'], 'rendered_bbox': row['bbox'],
                'samples': [{'ancestor': True, 'point': [x, y]}
                            for x in (left + .5, (left + right) / 2, right - .5)
                            for y in (top + .5, (top + bottom) / 2, bottom - .5)],
                'dispatch_point': {'schema_version': 'click-dispatch-point',
                                   'coordinate': coordinate, 'hit_valid': True},
                'synthetic': True})
        binding = next((b for b in state['capture_controls'] if b['selector'] == selector), None)
        if binding:
            eid = binding['element_id']
            row = next(e for e in state['elements'] if e['element_id'] == eid)
            value = next((v for v in state['values'] if v['element_id'] == eid), {})
            label = value.get('value') or '请输入数量'
            state['target'] = {'element_id': eid, 'coordinate': [30, row['bbox'][1] + 10],
                'hit_valid': True, 'focused': value.get('focused', False),
                'value': value.get('value'),
                'visible_label_evidence': [{'kind': 'visible_native_value' if value.get('value')
                                            else 'visible_placeholder', 'text': label}]}
        else:
            state['target'] = None
        token = int(hashlib.sha256(json.dumps({k: self.state.get(k) for k in
            ('url', 'values', 'scroll', 'document_identity')}, sort_keys=True, default=str).encode()).hexdigest()[:6], 16)
        png = _make_png(token)
        from webcollect.browser import fingerprint
        attempt = {'dom_stable': True, 'before_fingerprint': fingerprint(state),
                   'after_fingerprint': fingerprint(state),
                   'started_ns': time.time_ns(), 'ended_ns': time.time_ns()}
        receipt = {'snapshot_source': 'browser_dom',
            'screenshot_sha256': hashlib.sha256(png).hexdigest(),
            'coordinate_space': 'screenshot_css_pixels', 'attempts': [attempt]}
        if 'capture_readiness' in state:
            import base64
            from webcollect.browser import CAPTURE_VERSION, stability_pair
            from webcollect.action_stability import post_action_document_scope
            proof = stability_pair(state, state, png, png, action_scope=kw.get('action_scope') or post_action_document_scope(state))
            attempt.update(snapshot_before=deepcopy(state), snapshot_after=deepcopy(state), snapshot_final=deepcopy(state),
                           original_png_base64=base64.b64encode(png).decode(), comparison_png_base64=base64.b64encode(png).decode(),
                           stability=proof, final_stability=deepcopy(proof))
            receipt['schema_version'] = CAPTURE_VERSION
        return {'state': state, 'png': png, 'capture': receipt}

    def execute_action(self, action_type, arguments):
        self.executed.append((action_type, deepcopy(arguments)))
        values = self.state['values']
        if action_type == 'click':
            x, y = arguments['x'], arguments['y']
            target = None
            for value in values:
                row = next(e for e in self.state['elements'] if e['element_id'] == value['element_id'])
                box = row['bbox']
                target = value if box[0] <= x < box[2] and box[1] <= y < box[3] else target
            for value in values:
                value['focused'] = value is target
        elif action_type == 'hotkey':
            value = next(v for v in values if v['focused'])
            keys = arguments['keys']
            if keys in (['meta', 'a'], ['ctrl', 'a']):
                value.update(selection_start=0, selection_end=len(value['value']))
            elif keys == ['backspace']:
                value.update(value='', selection_start=0, selection_end=0)
        elif action_type == 'type':
            value = next(v for v in values if v['focused'])
            start, end = value.get('selection_start', 0), value.get('selection_end', 0)
            value['value'] = value['value'][:start] + arguments['text'] + value['value'][end:]
            value.update(selection_start=len(arguments['text']), selection_end=len(arguments['text']))
        elif action_type == 'scroll':
            self.state['scroll'][1] += 480
        elif action_type == 'open_url':
            self.state['url'] = arguments['url']
            self.state['document_identity']['performance_time_origin'] += 1
            self.history.append(self.state['url'])
        elif action_type == 'back':
            if len(self.history) > 1:
                self.history.pop()
                self.state['url'] = self.history[-1]
                self.state['document_identity']['performance_time_origin'] += 1


class FakePage:
    def __init__(self, surface):
        self.surface = surface
        self.context = type('Ctx', (), {'pages': []})()
        self.context.pages = [self]

    @property
    def url(self):
        return self.surface.state['url']

    async def goto(self, url, **kw):
        self.surface.state['url'] = url

    async def wait_for_timeout(self, ms):
        pass

    async def wait_for_load_state(self, *a, **k):
        pass

    async def content(self):
        return '<html><body>' + self.surface.state['visible_text'] + '</body></html>'

    async def evaluate(self, expression, *args):
        if 'scrollWidth' in expression and 'scrollHeight' in expression:
            return list(self.surface.state['screen_resolution'])
        raise AssertionError('Unexpected browser evaluation in offline harness')

    def on(self, event, cb):
        pass

    def set_default_timeout(self, ms):
        pass


class SessionHarness(unittest.IsolatedAsyncioTestCase):
    """Offline session substrate: synthetic surface, patched browser layer."""

    def setUp(self):
        self.network = patch.object(socket.socket, 'connect',
                                    side_effect=AssertionError('external IO forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        state = {'url': 'https://example.org/calculator',
                 'elements': [{'element_id': 'control-0', 'text': '数量', 'inputable': True, 'clickable': True},
                              {'element_id': 'control-1', 'text': '成本', 'inputable': True, 'clickable': True}],
                 'capture_controls': [{'element_id': f'control-{i}', 'selector': f'#control-{i}',
                                       'index': 0, 'tag': 'input'} for i in range(2)],
                 'values': [{'element_id': f'control-{i}', 'value': '10',
                             'focused': False, 'readonly': False} for i in range(2)]}
        self.surface = OfflineSurface(state)
        self.page = FakePage(self.surface)
        for name in ('webcollect.browser.capture',):
            p = patch(name, side_effect=self.surface.capture)
            p.start()
            self.addCleanup(p.stop)
        observation_patch = patch('webcollect.browser.observe', side_effect=self._fake_observe)
        observation_patch.start()
        self.addCleanup(observation_patch.stop)
        execute_patch = patch('webcollect.browser.execute', side_effect=self._fake_execute)
        execute_patch.start()
        self.addCleanup(execute_patch.stop)
        verify_patch = patch('webcollect.browser.verify_execution_state', side_effect=self._fake_verify)
        verify_patch.start()
        self.addCleanup(verify_patch.stop)
        before_patch = patch('webcollect.collect.capture_before_action', side_effect=self._fake_before)
        before_patch.start()
        self.addCleanup(before_patch.stop)

    async def _fake_execute(self, page, action_type, arguments, execution):
        self.surface.execute_action(action_type, arguments)

    async def _fake_observe(self, page, selector=None, index=0, **kw):
        return (await self.surface.capture(page, selector, index))['state']

    async def _fake_verify(self, page, state, selector=None, index=0, **kw):
        return {'matched': True, 'state_fingerprint': hashlib.sha256(
            json.dumps({'url': state['url'], 'identity': state.get('document_identity')},
                       sort_keys=True, default=str).encode()).hexdigest()}

    async def _fake_before(self, page, evidence, selector=None, index=0, **kw):
        observation = await self.surface.capture(page, selector, index, **kw)
        if kw.get('include_html'):
            observation['html'] = await page.content()
        return observation


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
        self.fixture = _GatewayHarness('setUp')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture
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

    def test_timeout_retains_one_unknown_and_blocks_replacement(self):
        ledger, job, gateway, runlog = self._gateway()
        self.f.opener.error = TimeoutError()
        self.fixture.response(self.fixture.message())
        with self.assertRaises(OutcomeUnknown):
            self.fixture.call(gateway, job, attempt_id='claim-1')
        # A second call, or a direct reservation using a new attempt number,
        # must not bypass the unresolved provider result.
        self.f.opener.error = None
        with self.assertRaises(OutcomeUnknown):
            self.fixture.call(gateway, job, attempt_id='claim-1')
        rows = self._calls(runlog)
        retries = [row for row in rows if row['event'] == 'timeout_retry_scheduled']
        started = [row for row in rows if row['event'] == 'request_started']
        finished = [row for row in rows if row['event'] == 'request_finished']
        self.assertEqual([row['state'] for row in finished], ['unknown'])
        self.assertEqual(len(started), 1)
        self.assertEqual(retries, [])
        with ledger.connect() as con:
            original = dict(con.execute('SELECT * FROM model_requests').fetchone())
        material = json.loads(original['request_json'])
        with self.assertRaises(OutcomeUnknown):
            ledger.reserve_request(job, original['purpose'], 1, request_json=material)
        with self.assertRaises(OutcomeUnknown):
            ledger.reserve_request(job, original['purpose'], 1, request_json={**material,
                'timeout_retry_of': original['id'], 'timeout_retry_root': original['id'],
                'timeout_retry_number': 1})
        self.assertEqual(len(self._ledger_request_ids(ledger)), 1)
        self.assertEqual(len(self.f.opener.calls), 1)
        self.assertEqual(original['state'], 'unknown')
        self.assertEqual(finished[0]['requestId'], original['id'])
        self.assertIsNone(finished[0]['inputTokens'])

    def test_invalid_response_still_records_its_usage(self):
        from webcollect.screenshot_plan import decision_tools, normalize_decision
        from webcollect.model_gateway import field_repair_plan, merge_field_repair
        from jsonschema import Draft202012Validator, ValidationError
        ledger, job, gateway, runlog = self._gateway()
        step = {'action': 'click', 'purpose': '打开参考内容', 'rationale': '当前页面有参考入口',
                'expected_result': '参考内容进入视口'}
        original_arguments = {'decision': 'revise', 'reason': '保留已确认事项，只修订尾部', 'answers': [],
                              'remaining_plan': [{**step, 'target': {'text': '参考说明'}}, deepcopy(step)]}
        tools = decision_tools(['revise'], ['click'])
        original_open = self.f.opener.open

        def send(request, timeout):
            if not self.f.opener.calls:
                self.f.response(self.f.message(name='plan_decision', arguments=json.dumps(original_arguments)))
            else:
                payload = json.loads(request.data)
                self.assertEqual(payload['tool_choice'], 'auto')
                self.assertEqual(len(payload['tools']), 1)
                self.assertEqual(payload['tools'][0]['function']['name'], 'repair_tool_arguments')
                self.assertEqual(list(payload['tools'][0]['function']['parameters']['properties']), ['field_0'])
                self.f.response(self.f.message(cid='patch-call', name='repair_tool_arguments',
                    arguments=json.dumps({'field_0': {'text': '计算公式'}})))
            return original_open(request, timeout)

        self.f.opener.open = send
        result = gateway.call_tool(job, 'tools', 'current observation', tools,
            system='trusted policy', reasoning_effort='low', attempt_id='claim-1', attempts=2,
            plan_normalizer=lambda value: normalize_decision(value, ['revise'], ['click']))
        expected = deepcopy(original_arguments)
        expected['remaining_plan'][1]['target'] = {'text': '计算公式'}
        self.assertEqual(result['arguments'], expected)
        self.assertEqual(result['name'], 'plan_decision')
        self.assertEqual(result['assistant_message_origin'], 'host_field_patch')
        self.assertEqual(result['provider_assistant_message']['tool_calls'][0]['function']['name'], 'repair_tool_arguments')
        self.assertEqual(result['argument_repair']['base_arguments'], original_arguments)
        self.assertEqual(result['argument_repair']['provider_patch'], {'field_0': {'text': '计算公式'}})
        self.assertEqual(result['argument_repair']['validated_arguments'], expected)
        finished = [row for row in self._calls(runlog) if row['event'] == 'request_finished']
        self.assertEqual([row['state'] for row in finished], ['invalid_response', 'succeeded'])
        self.assertEqual(finished[0]['inputTokens'], 250)
        self.assertIn(['remaining_plan', 1, 'target'],
                      [row['field_path'] for row in finished[0]['diagnostics']['schema_errors']])
        with ledger.connect() as con:
            retained = [json.loads(row['response']) for row in con.execute('SELECT response FROM model_requests ORDER BY attempt')]
        self.assertEqual(json.loads(retained[0]['provider_response']['choices'][0]['message']['tool_calls'][0]['function']['arguments']), original_arguments)
        self.assertEqual(retained[1]['provider_response']['choices'][0]['message']['tool_calls'][0]['function']['name'], 'repair_tool_arguments')
        self.assertEqual(retained[1]['result']['argument_repair']['merged_arguments'], expected)
        # The patch schema cannot rewrite a valid sibling or bypass full validation.
        schema = tools[0]['function']['parameters']
        error = next(Draft202012Validator(schema).iter_errors(original_arguments))
        repair = field_repair_plan(error, original_arguments, schema, 'plan_decision')
        with self.assertRaises(ValidationError):
            merge_field_repair(repair, {'field_0': {'text': '计算公式'}, 'reason': '越权修改'})
        with self.assertRaises(ValidationError):
            merge_field_repair(repair, {'field_0': 7})
        # A bounded patch covers every independent missing leaf, not only the first.
        from webcollect.screenshot_plan import submit_plan_schema, decision_schema
        from webcollect.model_gateway import schema_errors_feedback
        multi = {'goal': '读取两项正文', 'final_presentation_step': 1,
            'requirements': [{'id': f'r{index}', 'kind': 'content', 'description': f'正文{index}',
                              'evidence_route': {'observation_steps': [1]}} for index in range(2)],
            'steps': [{'action': 'click', 'target': {'text': '正文'}, 'purpose': f'打开正文{index}',
                       'rationale': '正文入口可见', 'expected_result': '正文进入视口'} for index in range(5)]}
        multi_schema = submit_plan_schema(['click'])
        multi_errors = list(Draft202012Validator(multi_schema).iter_errors(multi))
        multi_repair = field_repair_plan(multi_errors[0], multi, multi_schema, 'submit_plan',
                                         validation_errors=multi_errors)
        self.assertEqual(multi_repair['paths'], [
            ['requirements', 0, 'evidence_route', 'source_type'],
            ['requirements', 1, 'evidence_route', 'source_type']])
        merged = merge_field_repair(multi_repair, {'field_0': 'page_content', 'field_1': 'page_content'})
        Draft202012Validator(multi_schema).validate(merged)
        # continue携带替换计划是独立语义错误；反馈必须同时指出它和具体缺失target，
        # 不能先做一个注定仍失败的局部补丁，也不能只回传整段False schema。
        semantic = deepcopy(original_arguments)
        semantic['decision'] = 'continue'
        semantic_schema = decision_schema(['continue', 'revise'], ['click'])
        semantic_errors = list(Draft202012Validator(semantic_schema).iter_errors(semantic))
        feedback = schema_errors_feedback(semantic_errors)
        paths = [row['field_path'] for row in feedback]
        self.assertIn(['remaining_plan'], paths)
        self.assertIn(['remaining_plan', 1, 'target'], paths)
        self.assertTrue(all('False schema' not in row['detail'] for row in feedback))
        self.assertIsNone(field_repair_plan(semantic_errors[0], semantic, semantic_schema, 'plan_decision',
                                            validation_errors=semantic_errors))
        pending = expected['remaining_plan']
        repeated = {'decision': 'continue', 'reason': '原路线仍适用', 'remaining_plan': deepcopy(pending)}
        compact, record = normalize_decision(repeated, ['continue', 'revise'], ['click'], pending_steps=pending)
        Draft202012Validator(semantic_schema).validate(compact)
        self.assertNotIn('remaining_plan', compact)
        self.assertEqual(record['transforms'][0]['transform'], 'exact_pending_tail_removed')
        changed = deepcopy(repeated)
        changed['remaining_plan'][0]['target']['text'] = '不同业务目标'
        retained, _ = normalize_decision(changed, ['continue', 'revise'], ['click'], pending_steps=pending)
        self.assertIn('remaining_plan', retained)
        self.assertFalse(Draft202012Validator(semantic_schema).is_valid(retained))
        # JSON booleans are not numeric durations, even though Python True == 1.
        waiting = [{'action': 'wait', 'duration_ms': 1, 'purpose': '等候加载',
                    'rationale': '加载尚未结束', 'expected_result': '页面加载结束'}]
        bool_tail = deepcopy(waiting)
        bool_tail[0]['duration_ms'] = True
        typed, typed_record = normalize_decision(
            {'decision': 'continue', 'reason': '继续', 'remaining_plan': bool_tail},
            ['continue', 'revise'], ['wait'], pending_steps=waiting)
        self.assertIn('remaining_plan', typed)
        self.assertFalse(typed_record['transforms'])
        self.assertFalse(Draft202012Validator(decision_schema(['continue', 'revise'], ['wait'])).is_valid(typed))
        # The active click schema requests a target, never a null control or
        # unrelated scroll/type parameters from inactive branches.
        full_schema = decision_schema(['revise'], ['click', 'type', 'scroll', 'back'])
        active_errors = list(Draft202012Validator(full_schema).iter_errors(original_arguments))
        active_repair = field_repair_plan(active_errors[0], original_arguments, full_schema, 'plan_decision',
                                          validation_errors=active_errors)
        self.assertEqual(active_repair['paths'], [['remaining_plan', 1, 'target']])
        with self.assertRaises(ValidationError):
            merge_field_repair(active_repair, {'field_0': {'control': None}})

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


class ChooserRunlogTests(SessionHarness):
    """Simulated provider transport through the real screenshot_chooser chain."""

    def setUp(self):
        super().setUp()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.opener = StubOpener()
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
        config = load_json(CONFIG)
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
        plan = {'goal': '修改数量为20、成本为60并核对输入值',
                'final_presentation_step': 6,
                'requirements': [
                    {'id': f'i{i}', 'kind': 'input', 'description': f'{label}设为{value}',
                     'target': {'text': label}, 'expected_value': value,
                     'evidence_route': {'source_type': 'input_state', 'observation_steps': [pos]}}
                    for i, label, value, pos in [(0, '数量', '20', 3), (1, '成本', '60', 6)]],
                'steps': []}
        for label, value in [('数量', '20'), ('成本', '60')]:
            for action, extra, purpose in [
                    ('click', {}, '聚焦输入框'),
                    ('hotkey', {'keys': ['ctrl', 'a']}, '全选原值'),
                    ('type', {'value': value, 'expected_value': value}, '替换原值')]:
                plan['steps'].append({'action': action, 'target': {'text': label},
                    **extra, 'purpose': purpose, 'rationale': f'{label}需要替换为本次值',
                    'expected_result': f'{label}输入框完成{purpose}'})
        self.opener.raw['choices'] = [{'finish_reason': 'tool_calls', 'message': {
            'content': '', 'reasoning_content': 'opaque-offline-protocol-field',
            'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {
                'name': 'submit_plan', 'arguments': json.dumps(plan, ensure_ascii=False)}}]}}]
        # Exercise the actual first request, gateway schema, normalization and
        # admission, rather than validating only the standalone tool response.
        root = self.root / 'entry-session'
        with patch('webcollect.batch_core.BatchLedger.bind_model_session',
                   return_value='CONTROLLED_UNUSED'):
            choose = screenshot_chooser(ledger, self.task, 'claim-1', runlog=runlog)
            session = ScreenshotPlanSession(self.task, root / 'raw', choose, self.page,
                steps_directory=root, attempt_id='claim-1')
            await session._open_entry()
            prompt = session._first_prompt()
            self.assertEqual(prompt['goal_selection']['mode'], 'autonomous')
            self.assertIsNone(prompt['goal'])
            self.assertIn('goal', prompt['tools'][0]['function']['parameters']['allOf'][0]['else']['required'])
            await session._first_plan_round()
        self.assertIsNone(session.initial_feedback)
        self.assertEqual(session.frozen_goal, plan['goal'])
        self.assertEqual(len(session.plan['steps']), 6)
        self.assertEqual(session._branch_prompt('checkpoint')['goal'], plan['goal'])
        self.assertNotIn('goal', session._branch_prompt('checkpoint')['tools'][0]['function']['parameters']['properties'])
        self.assertEqual(session.actual_dispatches, 0)
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

        fixed_goal = '将数量改为20、成本改为60，并核对这两个输入值'
        fixed_task = deepcopy(self.task)
        fixed_task['workflow_proposal']['spec']['goal']['structured'] = {'description': fixed_goal}
        fixed_task['task_id'] = 'react-' + object_sha256(
            {'url': fixed_task['initial_url'], 'spec': fixed_task['workflow_proposal']['spec']})[:24]
        fixed_plan = deepcopy(plan)
        fixed_plan.pop('goal')
        self.opener.raw['choices'][0]['message']['tool_calls'][0]['function']['arguments'] = json.dumps(fixed_plan, ensure_ascii=False)
        root = self.root / 'fixed-session'
        with patch('webcollect.batch_core.BatchLedger.bind_model_session', return_value='CONTROLLED_UNUSED'):
            choose = screenshot_chooser(ledger, fixed_task, 'claim-fixed', runlog=runlog)
            fixed = ScreenshotPlanSession(fixed_task, root / 'raw', choose, self.page,
                steps_directory=root, attempt_id='claim-fixed')
            await fixed._open_entry()
            fixed_prompt = fixed._first_prompt()
            self.assertEqual(fixed_prompt['goal_selection']['mode'], 'fixed')
            self.assertEqual(fixed_prompt['goal'], fixed_goal)
            schema = fixed_prompt['tools'][0]['function']['parameters']
            self.assertNotIn('goal', schema['properties'])
            from jsonschema import Draft202012Validator
            self.assertTrue(list(Draft202012Validator(schema).iter_errors({**fixed_plan, 'goal': '改写目标'})))
            await fixed._first_plan_round()
        self.assertIsNone(fixed.initial_feedback)
        self.assertEqual(fixed.frozen_goal, fixed_goal)
        self.assertEqual(fixed._branch_prompt('checkpoint')['goal'], fixed_goal)
        self.assertEqual(fixed.actual_dispatches, 0)


class ScreenshotSessionRunlogTests(SessionHarness):
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
            {'action': 'hotkey', 'keys': ['ctrl', 'a'], 'target': {'text': '成本'},
             'purpose': '全选原成本', 'rationale': '替换已有成本', 'expected_result': '成本原值全选'},
            {'action': 'type', 'target': {'text': '成本'}, 'value': '60',
             'purpose': '输入成本60', 'rationale': '本次计算使用成本60',
             'expected_result': '成本显示为60', 'expected_value': '60'},
            {'action': 'click', 'target': {'text': '计算'}, 'purpose': '提交计算',
             'rationale': '提交后页面才会计算本次利润率',
             'expected_result': '结果区显示本次利润率'},
        ]

    def _plan(self):
        # Steps 8–9 form the tail after the declared evidence step: the route
        # checkpoint after step 8 must fire before step 9 can be dispatched.
        steps = self._steps() + [
            {'action': 'scroll', 'direction': 'down', 'purpose': '滚动核对结果下方说明',
             'rationale': '提交后核对结果区域周边说明', 'expected_result': '结果下方说明进入视口'},
            {'action': 'click', 'target': {'text': '数量'}, 'purpose': '再次聚焦数量框',
             'rationale': '核对结果后回到输入区', 'expected_result': '数量输入框获得焦点'},
        ]
        return {'goal': '修改数量为20并查看本次利润率结果',
                'requirements': [
                    {'id': 'r1', 'kind': 'result', 'description': '查看本次输入对应的利润率计算结果',
                     'evidence_route': {'source_type': 'page_result', 'observation_steps': [8]}}],
                'final_presentation_step': 8, 'steps': steps}

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

        async def choose(prompt):
            prompts.append(deepcopy(prompt))
            if prompt.get('phase') == 'first':
                return {'name': 'submit_plan', 'arguments': self._plan(),
                        'tool_call_id': 'first', 'assistant_message': {'role': 'assistant'},
                        'request_id': 'mock'}
            if prompt.get('reason') in ('submission_checkpoint', 'action_not_established'):
                # The model defers registration past the submit checkpoint; the
                # scroll still has to produce a route checkpoint before the
                # next planned action (SSD 5.1).
                return {'name': 'plan_decision', 'arguments': {
                    'decision': 'continue', 'reason': '先滚动核对结果下方说明'},
                    'tool_call_id': 'continue', 'request_id': 'mock'}
            evidence_observation = prompt['current_observation']
            regions = prompt.get('regions') or []
            region = next((r for r in regions if '利润率' in r.get('quote', '')), None)
            if region is None:
                # After scrolling, cite the same region in the historical frame
                # that was just reattached; do not demand a fresh page result.
                historical = next((row for row in prompt.get('historical_evidence') or []
                                   if any('利润率' in r.get('quote', '') for r in row.get('regions') or [])), None)
                if historical is not None:
                    evidence_observation = historical['observation']
                    region = next(r for r in historical['regions'] if '利润率' in r.get('quote', ''))
            if region is None:
                return {'name': 'plan_decision', 'arguments': {
                    'decision': 'continue', 'reason': '继续查看结果'},
                    'tool_call_id': 'continue', 'request_id': 'mock'}
            return {'name': 'plan_decision', 'arguments': {
                'decision': 'complete', 'reason': '本次提交的利润率结果已经可见',
                'answers': [{'requirement_id': 'r1', 'observed_result': '利润率：40%',
                             'evidence': [{'observation': evidence_observation,
                                           'region': region['region_id']}]}]},
                'tool_call_id': 'complete', 'request_id': 'mock'}

        session, _ = self._session('logged', choose, runlog=runlog)
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
        self.assertEqual(summary['collection_ending']['goal_completion'], 'VERIFIED')
        self.assertTrue(summary['effective_steps'] >= 5)
        accepted = next(row for row in rows if row['event'] == 'plan_accepted')
        self.assertEqual(accepted['actionHistogram'], {'click': 4, 'hotkey': 2, 'scroll': 1, 'type': 2})
        self.assertEqual(accepted['actionKinds'], 4)
        # The declared observation step (the scroll, plan step 8 of 9) produced a
        # consolidated evidence boundary before the remaining tail action could be dispatched;
        # once the goal verified there, the useless tail step never ran.
        checkpoints = [row for row in rows if row['event'] == 'checkpoint']
        route = next(row for row in checkpoints if row['reason'] == 'planned_evidence_complete')
        self.assertEqual(route['position'], 8)
        self.assertEqual(route['effectiveSteps'], 7)
        self.assertEqual(summary['effective_steps'], 7)
        route_prompt = next(p for p in prompts if p.get('phase') == 'branch'
                            and p.get('reason') == 'planned_evidence_complete')
        self.assertEqual(len(route_prompt['pending_steps']), 1)
        self.assertEqual(route_prompt['missing_requirements'], ['r1'])
        self.assertNotIn('remaining_plan', route_prompt)
        self.assertFalse(any(row['reason'] == 'route_observation' for row in checkpoints))
        # Captured-but-unregistered result rows are shown as candidates; having
        # captured them is not the same as a verified answer.
        self.assertTrue(route_prompt['candidate_results'])
        self.assertTrue(any('利润率' in row['text'] for row in route_prompt['candidate_results']))
        self.assertEqual([row['requirement_id'] for row in route_prompt['confirmed_progress']], [])
        first = next(prompt for prompt in prompts if prompt.get('phase') == 'first')
        affordances = first['interaction_affordances']
        self.assertEqual(affordances['projected_controls'], len(first['controls']))
        self.assertIn('input', affordances['kinds'])
        self.assertTrue(all(row['number'] == index for index, row in enumerate(first['controls'], 1)))

        # A positional selector can move while the same physical control ID
        # survives. Recover the probe once from the newly captured binding,
        # without consuming any business action or declaring a null probe seen.
        probe_session, _ = self._session('binding-probe', self._choose([]))
        await probe_session._open_entry()
        cid='control-0';old=probe_session.current['controls'][cid]['binding']['selector']
        source=next(b for b in self.surface.state['capture_controls'] if b['element_id']==cid)
        source['selector']=old+'-moved'
        actions=len(self.surface.executed);observations=len(probe_session.observations)
        result=await probe_session._observe(cid)
        self.assertTrue(result['data']['target_probe']['acquired'])
        self.assertEqual(probe_session.current['controls'][cid]['probe']['element_id'],cid)
        self.assertEqual(len(probe_session.observations)-observations,2)
        self.assertEqual(len(self.surface.executed),actions)
        self.assertEqual(probe_session.actual_dispatches,0)
        repeated=await probe_session._observe(cid)
        self.assertEqual(repeated['status'],'rejected')
        self.assertTrue(repeated['data']['target_probe']['acquired'])
        self.assertNotIn('inspect',repeated['summary'])
        unavailable, _ = self._session('unavailable-probe', self._choose([]))
        await unavailable._open_entry()
        async def no_target(selector,index):
            return await self.surface.capture(self.page,selector='#not-present')
        with patch.object(unavailable,'_capture_observation',side_effect=no_target):
            missing=await unavailable._observe(cid)
        self.assertFalse(missing['data']['target_probe']['acquired'])
        repeated=await unavailable._observe(cid)
        self.assertEqual(repeated['status'],'rejected')
        self.assertFalse(repeated['data']['target_probe']['acquired'])
        self.assertIn('仅已尝试',repeated['summary'])
        self.assertNotIn('inspect',repeated['summary'])

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
