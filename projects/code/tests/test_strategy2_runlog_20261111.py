"""Shared logging and gateway accounting, with frozen historical fixture helpers.

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
from webcollect.model_gateway import ModelGateway, ProviderRejected, ProviderFinishIncomplete
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
                     patch('webcollect.model_gateway._qc_addresses', return_value=[('CONTROLLED_DNS',)]),
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
        self.context = type('Ctx', (), {'pages': [],
            'on': lambda self, event, callback: None,
            'remove_listener': lambda self, event, callback: None})()
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
        # 同一会话身份的两个来源：claim 即 sessionId；无 claim 直接执行时生成
        # 一次性展示 id，且每次执行互不相同。
        from webcollect.runlog import for_claim
        claim = {'claim_id': 'CL-9', 'candidate_id': 'C-9'}
        self.assertEqual(for_claim(self.root, 'w1', claim).session_id, 'CL-9')
        first = for_direct_run(self.root).session_id
        second = for_direct_run(self.root).session_id
        self.assertNotEqual(first, second)
        self.assertTrue(first and second)

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
        # template_name is an identity key: attach flows it onto stderr lines and
        # runtime.jsonl (and via the gateway identity into model-calls.jsonl).
        from webcollect.runlog import IDENTITY_KEYS, for_claim
        self.assertIn('template_name', IDENTITY_KEYS)
        self.assertEqual(IDENTITY_KEYS.index('template_name'),
                         IDENTITY_KEYS.index('strategy') + 1)
        log.attach(template_name='operation')
        stderr_template, stdout_template = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(stderr_template), contextlib.redirect_stdout(stdout_template):
            log.info('template_selected', template_name='operation', reason='离线断言')
        template_line = stderr_template.getvalue().strip()
        self.assertIn('template_name=operation', template_line)
        template_row = _rows(self.root / 'logs' / 'w1' / 'runtime.jsonl')[-1]
        self.assertEqual(template_row['template_name'], 'operation')
        claim_log = for_claim(self.root, 'w2', {'claim_id': 'CL-7', 'candidate_id': 'C-7'},
                              STRATEGY_SCREENSHOT_PLAN)
        claim_log.attach(template_name='long_reading')
        claim_log.info('claim', claimId='CL-7')
        claim_row = _rows(self.root / 'logs' / 'w2' / 'runtime.jsonl')[-1]
        self.assertEqual(claim_row['template_name'], 'long_reading')

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

    def test_debug_projection_sanitizes_and_keeps_image_files_not_base64(self):
        value = {'headers': {'Cookie': 'session=1', 'api-key': 'k'},
                 'list': [{'Token': 't', 'Password': 'p'}]}
        clean = sanitize_debug(value)
        self.assertEqual(clean['headers']['Cookie'], '<omitted>')
        self.assertEqual(clean['headers']['api-key'], '<omitted>')
        self.assertEqual(clean['list'][0]['Token'], '<omitted>')
        self.assertEqual(clean['list'][0]['Password'], '<omitted>')
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



class GatewayRunlogTests(unittest.TestCase):
    """Model-call records for the real gateway settle chain, offline transport."""

    def setUp(self):
        self.fixture = _GatewayHarness('setUp')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture
        self.serial = 0

    def _gateway(self, level='INFO', *, max_images=None):
        self.serial += 1
        cfg = self.f.config('glm', vision=True)
        if max_images is not None:
            cfg['model']['max_images'] = max_images
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
        # A new explicit job must not recover an unrelated historical lease.
        with ledger.transaction() as con:
            con.execute('UPDATE jobs SET lease=0 WHERE id=?', (job['id'],))
        retained_job = ledger.get(job['id'])
        fresh_id = ledger.enqueue('test', {'new_unrelated_job': True})
        self.assertIsNotNone(ledger.claim('test', job_id=fresh_id))
        self.assertEqual(ledger.get(job['id']), retained_job)
        with ledger.connect() as con:
            retained_request = dict(con.execute('SELECT * FROM model_requests WHERE id=?', (original['id'],)).fetchone())
        self.assertEqual(retained_request, original)

        # The original request timeout is clipped to the remaining hard limit.
        fresh_ledger, fresh_job, fresh_gateway, _ = self._gateway()
        seen_timeouts = []
        def timed_out(request, timeout):
            seen_timeouts.append(timeout)
            raise TimeoutError('controlled clipped wait')
        with patch.object(self.f.opener, 'open', side_effect=timed_out):
            with self.assertRaises(OutcomeUnknown):
                self.fixture.call(fresh_gateway, fresh_job, attempt_id='claim-1',
                    dispatch_deadline=time.monotonic() + 1,
                    request_deadline=time.monotonic() + 2)
        self.assertEqual(len(seen_timeouts), 1)
        self.assertGreater(seen_timeouts[0], 0)
        self.assertLessEqual(seen_timeouts[0], 2)
        with fresh_ledger.connect() as con:
            clipped = dict(con.execute('SELECT * FROM model_requests').fetchone())
        self.assertEqual(clipped['state'], 'unknown')
        self.assertEqual(json.loads(clipped['response'])['request_timeout_seconds'], seen_timeouts[0])

    def _check_stepwise_prospective_images(self):
        from webcollect.stepwise.image_capacity import FinalImagesUnavailable, authorize_final_images, require_image_capacity
        ledger, previous, gateway, _ = self._gateway(max_images=1)
        ledger.finish(previous)
        original_parent = ledger.enqueue('collection', {'test': 'before image authorization'})
        previous_call = ledger.enqueue('stepwise-decision', {'phase': 'writeback', 'case': 'old'})
        with self.assertRaises(FinalImagesUnavailable):
            require_image_capacity(ledger.config, ledger=ledger)
        authorization = authorize_final_images(ledger, 'offline prospective image check')
        self.assertEqual(authorize_final_images(ledger, 'same setting'), authorization)
        reader = BatchLedger(ledger.path, ledger.config)
        self.assertEqual(require_image_capacity(reader.config, ledger=reader), 3)
        old_parent_call = ledger.enqueue('stepwise-decision', {'phase': 'writeback', 'parent_job_id': original_parent})
        for job_id in (previous_call, old_parent_call):
            with self.assertRaises(FinalImagesUnavailable):
                require_image_capacity(reader.config, ledger=reader, job_id=job_id)
        originals = [self.f.image]
        for name, color in [('before', 'red'), ('terminal', 'blue')]:
            path = self.f.root / (name + '.png')
            Image.new('RGB', (8, 8), color).save(path)
            originals.append(path)
        self.fixture.response(self.fixture.message())
        for phase, count in [('decision', 1), ('writeback', 2), ('judgement', 3)]:
            job = ledger.claim('stepwise-decision', job_id=ledger.enqueue(
                'stepwise-decision', {'phase': phase, 'case': 'new'}))
            if count < 3:
                with self.assertRaisesRegex(ValueError, 'Invalid stepwise'):
                    self.fixture.call(gateway, job, attempt_id='claim-1', images=originals[:count + 1])
            self.fixture.call(gateway, job, attempt_id='claim-1', images=originals[:count])
            ledger.finish(job)
        with reader.connect() as connection:
            bound = json.loads(connection.execute('SELECT config FROM batch_meta').fetchone()[0])
            calls = [json.loads(row[0]) for row in connection.execute('SELECT request_json FROM model_requests ORDER BY rowid')]
            self.assertEqual(bound['model']['max_images'], 1)
            self.assertEqual([(call['stepwise_phase'], call['image_count'], call['stage_max_images']) for call in calls],
                             [('decision', 1, 1), ('writeback', 2, 2), ('judgement', 3, 3)])

    def test_provider_rejections_settle_without_unknown_and_preserve_holds(self):
        self._check_stepwise_prospective_images()
        from urllib.error import HTTPError
        from webcollect.provider_recovery import holds
        from site_planner.producer_business_content import _purpose_holds
        from site_planner.discovery_agent import model_decision, model_tool_decision
        from site_planner.candidate_pool import entry_identity
        for status in (400, 401, 403, 408, 429, 499, 500, 503):
            ledger, job, gateway, _ = self._gateway()
            ledger.finish(job)
            job = ledger.claim('stepwise-decision', job_id=ledger.enqueue(
                'stepwise-decision', {'attempt_id': 'claim-1', 'phase': 'decision', 'offline': True}))
            detail = {'code': 'rate_limit_exceeded' if status == 429 else '1301',
                      'message': 'controlled provider rejection'}
            self.f.opener.error = HTTPError('https://provider.invalid/chat/completions', status,
                'controlled', {'Retry-After': '17'}, io.BytesIO(json.dumps({'error': detail}).encode()))
            before = len(self.f.opener.calls)
            expected = ProviderRejected if status < 500 else OutcomeUnknown
            with self.assertRaises(expected):
                self.fixture.call(gateway, job, attempt_id='claim-1', attempts=2, images=[self.f.image])
            with ledger.connect() as con:
                original = dict(con.execute('SELECT * FROM model_requests').fetchone())
                unresolved = ledger.session_http_usage(con, 'claim-1')['unresolved']
                auth = holds(con)
            self.assertEqual(original['state'], 'failed' if status < 500 else 'unknown')
            self.assertEqual(original['cost'], 0 if status < 500 else None)
            self.assertIsNone(original['usage'])
            self.assertEqual(bool(unresolved), status >= 500)
            self.assertEqual(bool(auth), status in (401, 403))
            if status == 429:
                self.assertIn(gateway._account_id(), ledger.unavailable_model_accounts())
                self.assertEqual(json.loads(original['response'])['provider_error']['retry_after_seconds'], 17)
                with ledger.connect() as con:
                    self.assertEqual(con.execute('SELECT status FROM consumer_key_health').fetchone()[0], 'rate_limited')
            # Same job/purpose cannot turn a settled rejection into a new call.
            with self.assertRaises(expected):
                self.fixture.call(gateway, job, attempt_id='claim-1', attempts=2, images=[self.f.image])
            self.assertEqual(len(self.f.opener.calls) - before, 1)
            with ledger.connect() as con:
                self.assertEqual(dict(con.execute('SELECT * FROM model_requests').fetchone()), original)

        # Both producer adapters close their job as failed, retain the reply,
        # and recognize the same failure on later read-back without dispatch.
        for native in (False, True):
            ledger, unused, gateway, _ = self._gateway()
            ledger.finish(unused)
            self.f.opener.error = HTTPError('https://provider.invalid/chat/completions', 400,
                'controlled', {}, io.BytesIO(b'{"error":{"code":"1301"}}'))
            payload = {'scope': 'offline-purpose', 'source_uris': ['https://example.org/page']}
            before = len(self.f.opener.calls)
            def dispatch():
                if native:
                    return model_tool_decision(ledger, gateway, 'ai-target-page-purpose-1',
                        payload, self.f.tools, system='offline policy')
                return model_decision(ledger, gateway, 'ai-target-page-purpose-1',
                    payload, _TOOLS_SCHEMA)
            with patch.object(ledger, 'bind_model_session', return_value='CONTROLLED_UNUSED'):
                with self.assertRaises(ProviderRejected):
                    dispatch()
                with self.assertRaises(ProviderRejected):
                    dispatch()
            self.assertEqual(len(self.f.opener.calls) - before, 1)
            with ledger.connect() as con:
                original = dict(con.execute('SELECT * FROM model_requests').fetchone())
            self.assertEqual(original['state'], 'failed')
            self.assertEqual(ledger.get(original['job_id'])['state'], 'failed')
            page_holds = _purpose_holds(ledger)
            self.assertEqual(page_holds[entry_identity(payload['source_uris'][0])][0]['state'], 'failed')
        self.f.opener.error = None

    def test_missing_usage_is_null_and_invalid_response_keeps_actual_usage(self):
        # 同一事实只算一次：失败请求的用量如实记录——缺 usage 记 null（不是
        # 0），invalid_response 保留 provider 实际返回的 usage。
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
                self.assertEqual(payload['tool_choice'],
                                 {'type': 'function', 'function': {'name': 'repair_tool_arguments'}})
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
        multi = {'goal': '读取两项正文',
            'requirements': [{'id': f'r{index}', 'kind': 'content',
                              'acceptance': {'mode': 'presence', 'subject': f'正文{index}',
                                             'source_quote': '读取两项正文'}}
                             for index in range(2)],
            'steps': [{'action': 'click', 'target': {'text': '正文'}, 'purpose': f'打开正文{index}',
                       'rationale': '正文入口可见', 'expected_result': '正文进入视口'} for index in range(5)]}
        multi_schema = submit_plan_schema(['click'])
        multi_errors = list(Draft202012Validator(multi_schema).iter_errors(multi))
        self.assertEqual([list(error.absolute_path) for error in multi_errors],
                         [['requirements', 0], ['requirements', 1]])
        multi_repair = field_repair_plan(multi_errors[0], multi, multi_schema, 'submit_plan',
                                         validation_errors=multi_errors)
        self.assertEqual(multi_repair['paths'], [
            ['requirements', 0, 'description'],
            ['requirements', 1, 'description']])
        merged = merge_field_repair(multi_repair, {'field_0': '读取第一项正文', 'field_1': '读取第二项正文'})
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

        self.f.opener.open = original_open

        # F output_exhausted/refused分别处理：length不执行截断参数，只允许
        # 一次紧凑重提（实质变化），第二笔仍失败则有界结束，无第三笔请求；
        # refused有界结束不重发。
        self.serial += 1
        ledger2, job2, gateway2, _ = self._gateway()
        self.f.opener.raw = {'id': 'offline-length', 'model': 'offline-model-version',
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50,
                      'prompt_tokens_details': {'cached_tokens': 0}},
            'choices': [{'finish_reason': 'length', 'message': {'content': '{"answer": 4'}}]}
        before_length_calls = len(self.f.opener.calls)
        material = {'goal': '保留目标', 'inputs': {'title': '原值', 'n': 7},
                    'depends_on': [1], 'evidence': ['frame-1'],
                    'facts': list(range(80))}
        padded_tools = deepcopy(self.f.tools)
        padded_tools[0]['function']['parameters']['title'] = 'annotation ' * 100
        padded_system = 'trusted policy' + '\n' * 1000 + 'preserve evidence'
        def compact_call(gateway, job, **kw):
            return gateway.call_tool(job, 'tools', json.dumps(material, indent=40), padded_tools,
                system=padded_system, reasoning_effort='low', attempts=5, attempt_id='claim-1', **kw)
        with self.assertRaises(ValueError):
            compact_call(gateway2, job2)
        self.assertEqual(len(self.f.opener.calls) - before_length_calls, 2)
        correction_payload = json.loads(self.f.opener.calls[before_length_calls + 1].data.decode())
        self.assertIn('紧凑', correction_payload['messages'][-1]['content'][-1]['text'])
        first_payload = json.loads(self.f.opener.calls[before_length_calls].data)
        self.assertLess(len(self.f.opener.calls[before_length_calls + 1].data),
                        len(self.f.opener.calls[before_length_calls].data))
        self.assertEqual(json.loads(correction_payload['messages'][-1]['content'][0]['text']), material)
        self.assertLess(len(correction_payload['messages'][0]['content']), len(first_payload['messages'][0]['content']))
        self.assertNotIn('title', correction_payload['tools'][0]['function']['parameters'])
        from webcollect.model_gateway import compact_retry_context
        annotated = deepcopy(padded_tools)
        annotated_schema = annotated[0]['function']['parameters']
        annotated_schema['properties']['title'] = {'const': {'title': 'literal'},
                                                   'default': {'$comment': 'literal'}}
        immutable_image={'type':'image_url','image_url':{'url':'data:image/png;base64,'+'A'*100000}}
        _, cleaned_parts, cleaned = compact_retry_context(padded_system,
            [{'type': 'text', 'text': json.dumps(material, indent=40)},immutable_image], annotated)
        self.assertEqual(cleaned_parts[-1],immutable_image)
        self.assertEqual(cleaned[0]['function']['parameters']['properties']['title'],
                         annotated_schema['properties']['title'])
        with ledger2.connect() as con:
            settled = [json.loads(row[0]) for row in
                       con.execute('SELECT response FROM model_requests ORDER BY rowid')]
        self.assertEqual([row['failure_diagnostic']['source'] for row in settled],
                         ['output_exhausted', 'output_exhausted'])
        # Already compact input cannot authorize a second paid length request.
        _, compact_job, compact_gateway, _ = self._gateway()
        before = len(self.f.opener.calls)
        with self.assertRaisesRegex(ProviderFinishIncomplete, 'output_exhausted'):
            self.f.call(compact_gateway, compact_job, attempts=5, attempt_id='claim-1')
        self.assertEqual(len(self.f.opener.calls) - before, 1)
        # Different failure kinds still share the same two-request decision budget;
        # no plan normalizer is installed in either direction.
        for finishes in (('length', 'tool_calls'), ('tool_calls', 'length')):
            mixed_ledger, _, mixed_gateway, _ = self._gateway()
            mixed_job = mixed_ledger.claim('collection', job_id=mixed_ledger.enqueue('collection', {'offline': True}))
            before = len(self.f.opener.calls)
            def mixed_open(request, timeout):
                index = len(self.f.opener.calls) - before
                finish = finishes[min(index, 1)]
                self.f.opener.raw['choices'] = [{'finish_reason': finish,
                    'message': ({'content': '{'} if finish == 'length' else
                                self.f.message(arguments='{"answer":"invalid"}'))}]
                return original_open(request, timeout)
            self.f.opener.open = mixed_open
            with self.assertRaises(ValueError):
                compact_call(mixed_gateway, mixed_job)
            self.assertEqual(len(self.f.opener.calls) - before, 2)
        self.f.opener.open = original_open
        # The 40-call gate is inside each reservation, including a correction
        # after the 40th call returned a settled schema failure.
        from webcollect.batch_core import SessionGLMCallLimit
        cap_ledger, _, cap_gateway, _ = self._gateway()
        cap_job = cap_ledger.claim('collection', job_id=cap_ledger.enqueue('collection', {'offline': True}))
        for index in range(39):
            request = cap_ledger.reserve_request(cap_job, 'seed-' + str(index), 0,
                request_json={'protocol': 'native-tools', 'http_dispatch': True,
                              'dispatch_attempt_id': 'claim-1', 'dispatch_max_requests': 40})
            cap_ledger.settle_request(request['id'], state='invalid_response',
                usage={'input_tokens': 1, 'output_tokens': 1, 'cached_input_tokens': 0}, response={})
        self.f.response(self.f.message(arguments='{"answer":"invalid"}'))
        before = len(self.f.opener.calls)
        with self.assertRaises(SessionGLMCallLimit):
            self.f.call(cap_gateway, cap_job, attempts=5, attempt_id='claim-1')
        self.assertEqual(len(self.f.opener.calls) - before, 1)
        with cap_ledger.connect() as con:
            self.assertEqual(cap_ledger.session_http_usage(con, 'claim-1')['used'], 40)
        self.serial += 1
        _ledger3, job3, gateway3, _ = self._gateway()
        self.f.opener.raw = {'id': 'offline-refused', 'model': 'offline-model-version',
            'usage': {'prompt_tokens': 100, 'completion_tokens': 5,
                      'prompt_tokens_details': {'cached_tokens': 0}},
            'choices': [{'finish_reason': 'stop',
                         'message': {'content': '不能协助该请求', 'refusal': 'content policy'}}]}
        before_refused_calls = len(self.f.opener.calls)
        with self.assertRaises(ValueError):
            self.f.call(gateway3, job3, attempts=2, attempt_id='claim-1')
        self.assertEqual(len(self.f.opener.calls) - before_refused_calls, 1)

    def test_debug_level_sanitizes_wire_and_no_runlog_stays_quiet(self):
        # 先验证同一开关的“关”：未接 runlog 时网关保持安静且账本行为不变。
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
        # 再验证“开”：DEBUG 记录净化后的线上往返，不含凭据或内嵌图片。
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


if __name__ == '__main__':
    unittest.main()
