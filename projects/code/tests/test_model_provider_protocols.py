"""Offline provider dialect contracts; no provider/model/billing validation."""
from copy import deepcopy
import io
import itertools
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error

from PIL import Image

from webcollect.batch_core import BatchLedger, OutcomeUnknown, load_json, validate_config
from webcollect.model_gateway import ModelGateway


CONFIG = Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json'
SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'integer'}},
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


class ProviderProtocolTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.opener = StubOpener()
        for mock in (patch.dict('os.environ', {'WEBCOLLECT_OFFLINE_TEST_KEY': 'offline-secret-never-export'}),
                     patch('webcollect.model_gateway.socket.getaddrinfo',return_value=[('CONTROLLED_DNS',)]),
                     patch('urllib.request.build_opener', return_value=self.opener)):
            mock.start()
            self.addCleanup(mock.stop)
        self.image = self.root / 'original.png'
        Image.new('RGB', (8, 8), 'white').save(self.image)
        self.serial = 0

    def config(self, provider='deepseek', *, vision=False):
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

    def test_new_provider_fields_are_explicit_and_legacy_representation_is_unchanged(self):
        legacy = load_json(CONFIG)
        self.assertEqual(validate_config(legacy), legacy)
        partial = deepcopy(legacy)
        partial['model']['supports_vision'] = False
        with self.assertRaisesRegex(ValueError, 'supplied together'):
            validate_config(partial)
        for provider in ('deepseek', 'glm'):
            config = self.config(provider)
            self.assertEqual(validate_config(config), config)
            for field in ('supports_vision', 'image_tokens_per_image', 'request_overhead_tokens'):
                missing = deepcopy(config)
                del missing['model'][field]
                with self.subTest(provider=provider, field=field), self.assertRaises(ValueError):
                    validate_config(missing)

    def test_invalid_vision_and_token_allowances_are_rejected(self):
        cases = ({'supports_vision': 1}, {'image_tokens_per_image': 1},
                 {'supports_vision': True, 'image_tokens_per_image': 0},
                 {'request_overhead_tokens': 0}, {'request_overhead_tokens': True})
        for updates in cases:
            config = self.config()
            config['model'].update(updates)
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                validate_config(config)

    def test_text_provider_payloads_include_schema_and_use_max_tokens(self):
        for provider in ('deepseek', 'glm'):
            ledger, job, gateway = self.gateway(self.config(provider))
            with self.subTest(provider=provider):
                self.assertEqual(gateway.call(job, 'text', 'JSON测试', SCHEMA), {'answer': 42})
                payload = json.loads(self.opener.calls[-1].data)
                self.assertEqual(payload['response_format'], {'type': 'json_object'})
                self.assertEqual(payload['max_tokens'], ledger.config['model']['max_completion_tokens'])
                self.assertNotIn('max_completion_tokens', payload)
                self.assertNotIn('store', payload)
                system = payload['messages'][0]['content']
                self.assertEqual(json.loads(system.split('JSON Schema exactly:\n', 1)[1]), SCHEMA)
                self.assertEqual(ledger.summary()['usage_covered_requests'], 1)

    def test_glm_native_tool_calls_are_forwarded_and_parsed(self):
        """Official GLM function calling: forced react_decision arguments are
        the structured output; finish_reason tool_calls is a complete answer."""
        tools = [{'type': 'function', 'function': {
            'name': 'react_decision', 'description': 'decide', 'parameters': SCHEMA}}]
        forced = {'type': 'function', 'function': {'name': 'react_decision'}}
        ledger, job, gateway = self.gateway(self.config('glm', vision=True))
        self.opener.raw['choices'][0] = {'finish_reason': 'tool_calls', 'message': {
            'content': '', 'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {
                'name': 'react_decision', 'arguments': '{"answer": 7}'}}]}}
        self.assertEqual(gateway.call(job, 'decision', 'prompt', SCHEMA, tools=tools), {'answer': 7})
        payload = json.loads(self.opener.calls[-1].data)
        self.assertEqual(payload['tools'], tools)
        self.assertEqual(payload['tool_choice'], forced)
        self.assertEqual(payload['thinking'], {'type': 'enabled'})
        self.assertNotIn('response_format', payload)
        with ledger.connect() as con:
            row = con.execute('SELECT response FROM model_requests ORDER BY id DESC LIMIT 1').fetchone()
        settled = json.loads(row[0])
        self.assertEqual(settled['tool_call_name'], 'react_decision')
        # A content-only answer still parses while tools are declared.
        self.opener.raw['choices'][0] = {'finish_reason': 'stop', 'message': {'content': '{"answer": 42}'}}
        job = ledger.claim('test', job_id=ledger.enqueue('test', {'offline': 2}))
        self.assertEqual(gateway.call(job, 'decision', 'prompt-fallback', SCHEMA, tools=tools), {'answer': 42})
        # Other providers never receive the GLM native-tools payload shape.
        _, job, gateway = self.gateway(self.config('deepseek'))
        gateway.call(job, 'decision', 'prompt', SCHEMA, tools=tools)
        payload = json.loads(self.opener.calls[-1].data)
        self.assertNotIn('tools', payload)
        self.assertEqual(payload['response_format'], {'type': 'json_object'})

    def test_native_tool_arguments_must_stay_strict_json(self):
        """Provider-generated arguments are strict-loaded; broken JSON is a
        charged invalid response with bounded retries, never repaired."""
        tools = [{'type': 'function', 'function': {
            'name': 'react_decision', 'description': 'decide', 'parameters': SCHEMA}}]
        _, job, gateway = self.gateway(self.config('glm', vision=True))
        self.opener.raw['choices'][0] = {'finish_reason': 'tool_calls', 'message': {
            'content': '', 'tool_calls': [{'function': {
                'name': 'react_decision', 'arguments': '{"answer":'}}]}}
        with self.assertRaisesRegex(ValueError, 'Bounded model attempts exhausted'):
            gateway.call(job, 'decision', 'prompt', SCHEMA, tools=tools, attempts=2)
        self.assertEqual(len(self.opener.calls), 2)

    def test_deepseek_vision_uses_original_png_data_uri(self):
        _, job, gateway = self.gateway(self.config(vision=True))
        gateway.call(job, 'pixels', 'JSON pixels', SCHEMA, images=[self.image])
        payload = json.loads(self.opener.calls[0].data)
        image = payload['messages'][1]['content'][1]['image_url']
        self.assertTrue(image['url'].startswith('data:image/png;base64,'))
        self.assertEqual(image['detail'], 'high')
        self.assertEqual(payload['response_format'], {'type': 'json_object'})

    def test_glm_vision_omits_text_only_response_format_even_without_images(self):
        for images in ((), (self.image,)):
            _, job, gateway = self.gateway(self.config('glm', vision=True))
            gateway.call(job, 'pixels', 'JSON pixels', SCHEMA, images=images)
            payload = json.loads(self.opener.calls[-1].data)
            self.assertNotIn('response_format', payload)
            self.assertIn('JSON Schema', payload['messages'][0]['content'])
            self.assertEqual(payload['thinking'], {'type': 'enabled'})
            if images:
                import base64
                image = payload['messages'][1]['content'][1]['image_url']
                self.assertEqual(image, {'url': base64.b64encode(self.image.read_bytes()).decode()})

    def test_glm_explicit_data_url_preserves_original_png_and_enabled_thinking(self):
        import base64
        config = self.config('glm', vision=True)
        config['model'].update(model='glm-5.3-flash', image_encoding='data_url', reasoning_effort='low')
        self.assertEqual(validate_config(config), config)
        _, job, gateway = self.gateway(config)
        gateway.call(job, 'pixels', 'JSON pixels', SCHEMA, images=[self.image])
        payload = json.loads(self.opener.calls[-1].data)
        image = payload['messages'][1]['content'][1]['image_url']
        self.assertEqual(image, {'url': 'data:image/png;base64,' + base64.b64encode(self.image.read_bytes()).decode()})
        self.assertEqual(payload['thinking'], {'type': 'enabled'})
        self.assertEqual(payload['reasoning_effort'], 'low')
        self.assertNotIn('response_format', payload)

    def test_glm_single_json_fence_and_bare_json_keep_original_response(self):
        contents = ('{"answer":42}', '```json\n{"answer":42}\n```',
                    ' \n```json\r\n{"answer":42}\r\n```\t')
        for content in contents:
            self.opener.raw['choices'][0]['message']['content'] = content
            ledger, job, gateway = self.gateway(self.config('glm'))
            with self.subTest(content=content):
                self.assertEqual(gateway.call(job, 'text', 'JSON', SCHEMA), {'answer': 42})
                with ledger.connect() as con:
                    stored = json.loads(con.execute('SELECT response FROM model_requests').fetchone()[0])
                self.assertEqual(stored['provider_response']['choices'][0]['message']['content'], content)
                self.assertEqual(stored['content_envelope_normalized'], content.strip().startswith('```json'))
                self.assertEqual(ledger.summary()['usage_covered_requests'], 1)
                payload = json.loads(self.opener.calls[-1].data)
                self.assertIn('without Markdown, code fences', payload['messages'][0]['content'])

    def test_glm_rejects_explanation_multiple_fences_or_invalid_fenced_json(self):
        contents = ('Here is JSON:\n```json\n{"answer":42}\n```',
                    '```json\n{"answer":42}\n```\nDone.',
                    '```json\n{"answer":42}\n```\n```json\n{"answer":43}\n```',
                    '```\n{"answer":42}\n```',
                    '```json\n{"answer":42,}\n```',
                    '```json\n{"answer":42}\n{"answer":43}\n```')
        for content in contents:
            self.opener.raw['choices'][0]['message']['content'] = content
            ledger, job, gateway = self.gateway(self.config('glm'))
            with self.subTest(content=content), self.assertRaisesRegex(ValueError, 'attempts exhausted'):
                gateway.call(job, 'text', 'JSON', SCHEMA, attempts=1)
            with ledger.connect() as con:
                state, response = con.execute('SELECT state,response FROM model_requests').fetchone()
            self.assertEqual(state, 'invalid_response')
            self.assertEqual(json.loads(response)['provider_response']['choices'][0]['message']['content'], content)
            self.assertEqual(ledger.summary()['usage_covered_requests'], 1)

    def test_glm_fenced_json_still_requires_schema_and_complete_usage(self):
        self.opener.raw['choices'][0]['message']['content'] = '```json\n{"answer":"wrong"}\n```'
        ledger, job, gateway = self.gateway(self.config('glm'))
        with self.assertRaisesRegex(ValueError, 'attempts exhausted'):
            gateway.call(job, 'text', 'JSON', SCHEMA, attempts=1)
        with ledger.connect() as con:
            self.assertEqual(con.execute('SELECT state FROM model_requests').fetchone()[0], 'invalid_response')
        self.opener.raw['choices'][0]['message']['content'] = '```json\n{"answer":42}\n```'
        self.opener.raw['usage'] = {'prompt_tokens': 250, 'completion_tokens': 50}
        ledger, job, gateway = self.gateway(self.config('glm'))
        before = len(self.opener.calls)
        for _ in range(2):
            with self.assertRaises(OutcomeUnknown):
                gateway.call(job, 'text', 'JSON', SCHEMA)
        self.assertEqual(len(self.opener.calls), before + 1)
        self.assertEqual(ledger.summary()['usage_covered_requests'], 0)

    def test_other_providers_reject_json_fences(self):
        self.opener.raw['choices'][0]['message']['content'] = '```json\n{"answer":42}\n```'
        for provider in ('deepseek', 'chat-completions'):
            ledger, job, gateway = self.gateway(self.config(provider))
            with self.subTest(provider=provider), self.assertRaisesRegex(ValueError, 'attempts exhausted'):
                gateway.call(job, 'text', 'JSON', SCHEMA, attempts=1)
            with ledger.connect() as con:
                self.assertEqual(con.execute('SELECT state FROM model_requests').fetchone()[0], 'invalid_response')

    def test_explicit_reasoning_effort_is_forwarded_without_implicit_value(self):
        for provider in ('deepseek', 'glm'):
            for effort in ('low', 'high', 'max'):
                config = self.config(provider)
                config['model']['reasoning_effort'] = effort
                _, job, gateway = self.gateway(config)
                gateway.call(job, 'text', 'JSON', SCHEMA)
                payload = json.loads(self.opener.calls[-1].data)
                self.assertEqual(payload['reasoning_effort'], effort)
        _, job, gateway = self.gateway(self.config())
        gateway.call(job, 'text', 'JSON', SCHEMA)
        self.assertNotIn('reasoning_effort', json.loads(self.opener.calls[-1].data))

    def test_encoding_and_reasoning_options_are_strictly_scoped(self):
        cases = [('glm', {'image_encoding': 'jpeg'}), ('glm', {'image_encoding': None}),
                 ('deepseek', {'image_encoding': 'data_url'}),
                 ('chat-completions', {'image_encoding': 'raw_base64'}),
                 ('glm', {'reasoning_effort': 'none'}), ('deepseek', {'reasoning_effort': 'minimal'}),
                 ('chat-completions', {'reasoning_effort': 'low'}),
                 ('glm', {'thinking': {'type': 'disabled'}})]
        for provider, updates in cases:
            config = self.config(provider)
            config['model'].update(updates)
            with self.subTest(provider=provider, updates=updates), self.assertRaises(ValueError):
                validate_config(config)

    def test_text_models_reject_images_before_reservation_or_network(self):
        for provider in ('deepseek', 'glm'):
            ledger, job, gateway = self.gateway(self.config(provider))
            with self.subTest(provider=provider), self.assertRaisesRegex(ValueError, 'does not support'):
                gateway.call(job, 'pixels', 'JSON', SCHEMA, images=[self.image])
            self.assertEqual(ledger.summary()['model_requests'], 0)
        self.assertEqual(self.opener.calls, [])

    def test_system_schema_and_images_reach_transport_above_reservation_estimates(self):
        cases = ({'reserve_input_tokens': 200}, {'request_overhead_tokens': 60_000},
                 {'image_tokens_per_image': 50_000})
        for provider in ('deepseek', 'glm'):
            for updates in cases:
                config = self.config(provider, vision=True)
                config['model'].update(updates)
                ledger, job, gateway = self.gateway(config)
                with self.subTest(provider=provider, updates=updates):
                    result=gateway.call(job,'above-estimate','JSON',SCHEMA,images=[self.image])
                    self.assertEqual(result,{'answer':42})
                    self.assertEqual(ledger.summary()['model_requests'],1)
        self.assertEqual(len(self.opener.calls),6)

    def test_non_png_bytes_are_rejected_before_dispatch(self):
        disguised = self.root / 'jpeg-disguised.png'
        Image.new('RGB', (8, 8), 'white').save(disguised, format='JPEG')
        ledger, job, gateway = self.gateway(self.config(vision=True))
        with self.assertRaisesRegex(ValueError, 'must be PNG'):
            gateway.call(job, 'pixels', 'JSON', SCHEMA, images=[disguised])
        self.assertEqual(ledger.summary()['model_requests'], 0)
        self.assertEqual(self.opener.calls, [])

    def test_legacy_provider_keeps_actual_usage_above_image_estimate(self):
        config = self.config('chat-completions', vision=True)
        config['model']['image_tokens_per_image'] = 50_000
        ledger, job, gateway = self.gateway(config)
        self.assertEqual(gateway.call(job, 'pixels', 'JSON', SCHEMA, images=[self.image]),{'answer':42})
        self.assertEqual(ledger.summary()['model_requests'], 1)
        self.assertEqual(len(self.opener.calls), 1)

    def test_deepseek_cache_hit_usage_and_identical_request_reuse(self):
        self.opener.raw['usage'] = {'prompt_tokens': 250, 'completion_tokens': 50, 'prompt_cache_hit_tokens': 100}
        ledger, job, gateway = self.gateway(self.config())
        for _ in range(2):
            self.assertEqual(gateway.call(job, 'text', 'JSON', SCHEMA), {'answer': 42})
        self.assertEqual(len(self.opener.calls), 1)
        with ledger.connect() as con:
            usage = json.loads(con.execute('SELECT usage FROM model_requests').fetchone()[0])
            recorded = json.loads(con.execute('SELECT request_json FROM model_requests').fetchone()[0])
        payload = json.loads(self.opener.calls[0].data)
        self.assertEqual(recorded['system'], payload['messages'][0]['content'])
        self.assertEqual(recorded['provider'], 'deepseek')
        self.assertEqual(usage['cached_input_tokens'], 100)
        self.assertEqual(usage['provider_request_id'], 'offline-provider-response')
        self.assertEqual(ledger.summary()['usage_covered_requests'], 1)
        ledger.export(self.root / 'metering')
        self.assertNotIn('offline-secret-never-export', ''.join(p.read_text() for p in (self.root / 'metering').glob('*.json')))

    def test_matching_cache_fields_are_accepted(self):
        self.opener.raw['usage']['prompt_cache_hit_tokens'] = 100
        ledger, job, gateway = self.gateway(self.config())
        self.assertEqual(gateway.call(job, 'text', 'JSON', SCHEMA), {'answer': 42})
        self.assertEqual(ledger.summary()['usage_coverage'], 1)

    def test_missing_conflicting_or_invalid_cache_usage_stays_unknown_and_is_not_resent(self):
        caches = ({}, {'prompt_cache_hit_tokens': None}, {'prompt_cache_hit_tokens': True},
                  {'prompt_cache_hit_tokens': -1}, {'prompt_cache_hit_tokens': 251},
                  {'prompt_tokens_details': {'cached_tokens': 100}, 'prompt_cache_hit_tokens': 99})
        for provider in ('deepseek', 'glm'):
            for cache in caches:
                self.opener.raw['usage'] = {'prompt_tokens': 250, 'completion_tokens': 50, **cache}
                ledger, job, gateway = self.gateway(self.config(provider))
                before = len(self.opener.calls)
                with self.subTest(provider=provider, cache=cache):
                    for _ in range(2):
                        with self.assertRaises(OutcomeUnknown):
                            gateway.call(job, 'text', 'JSON', SCHEMA)
                    self.assertEqual(len(self.opener.calls), before + 1)
                    self.assertEqual(ledger.summary()['usage_covered_requests'], 0)
                    self.assertEqual(ledger.summary()['model_request_states'].get('unknown'), 1)

    def test_local_schema_failure_is_charged_invalid_response(self):
        self.opener.raw['choices'][0]['message']['content'] = '{"answer":"wrong"}'
        for provider in ('deepseek', 'glm'):
            ledger, job, gateway = self.gateway(self.config(provider))
            with self.subTest(provider=provider), self.assertRaisesRegex(ValueError, 'attempts exhausted'):
                gateway.call(job, 'text', 'JSON', SCHEMA, attempts=1)
            with ledger.connect() as con:
                self.assertEqual(con.execute('SELECT state FROM model_requests').fetchone()[0], 'invalid_response')
            self.assertEqual(ledger.summary()['usage_covered_requests'], 1)

    def test_http_failure_keeps_unknown_reservation_without_fallback(self):
        self.opener.error = urllib.error.HTTPError('https://provider.invalid/', 400, 'controlled rejection', {}, None)
        ledger, job, gateway = self.gateway(self.config())
        for _ in range(2):
            with self.assertRaises(OutcomeUnknown):
                gateway.call(job, 'text', 'JSON', SCHEMA)
        self.assertEqual(len(self.opener.calls), 1)
        self.assertEqual(ledger.summary()['model_request_states'].get('unknown'), 1)

    def test_provider_examples_require_real_configuration_before_ledger_creation(self):
        for provider in ('deepseek', 'glm'):
            config = load_json(CONFIG.parent / f'batch-{provider}.example.json')
            with self.subTest(provider=provider), self.assertRaises(ValueError):
                self.gateway(config)
        self.assertEqual(list(self.root.glob('*.sqlite3')), [])
        self.assertEqual(self.opener.calls, [])



class NativeToolProtocolTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.tools = [{'type': 'function', 'function': {'name': 'act', 'parameters': SCHEMA}}]

    def message(self, cid='tc1', name='act', arguments='{"answer":7}'):
        return {'role': 'assistant', 'content': None, 'reasoning_content': 'opaque-offline-protocol-field',
                'tool_calls': [{'id': cid, 'type': 'function',
                                'function': {'name': name, 'arguments': arguments}}]}

    def response(self, message):
        self.fixture.opener.raw['choices'] = [{'finish_reason': 'tool_calls', 'message': message}]

    def call(self, gateway, job, **kw):
        return gateway.call_tool(job, 'tools', 'current observation', self.tools,
                                 system='trusted policy', reasoning_effort='low', **kw)

    def test_glm_native_roundtrip_id_history_reasoning_and_current_png(self):
        f = self.fixture
        ledger, job, gateway = f.gateway(f.config('glm', vision=True))
        self.response(self.message())
        first = self.call(gateway, job, images=[f.image], attempt_id='one', max_requests=3)
        self.assertEqual((first['name'], first['arguments'], first['tool_call_id']), ('act', {'answer': 7}, 'tc1'))
        history = [first['user_message'], first['assistant_message'],
                   {'role': 'tool', 'tool_call_id': 'tc1', 'content': '{"actual":"scrolled"}'}]
        self.response(self.message('tc2'))
        second = self.call(gateway, job, history=history, images=[f.image], attempt_id='one', max_requests=3)
        payload = json.loads(f.opener.calls[-1].data)
        self.assertEqual(payload['messages'], [{'role':'system','content':'trusted policy'}] + history + [second['user_message']])
        self.assertEqual(payload['tools'], self.tools)
        self.assertEqual(payload['tool_choice'], 'auto')
        self.assertEqual(payload['thinking'], {'type':'enabled', 'clear_thinking':False})
        self.assertEqual(payload['reasoning_effort'], 'low')
        self.assertNotIn('response_format', payload)
        self.assertTrue(first['user_message']['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
        with patch('webcollect.model_gateway.socket.getaddrinfo', side_effect=AssertionError('cached call must not resolve DNS')):
            self.assertEqual(self.call(gateway, job, history=history, images=[f.image], attempt_id='one', max_requests=3), second)
        self.assertEqual(len(f.opener.calls), 2)
        ledger.export(f.root / 'native-export')
        self.assertNotIn('opaque-offline-protocol-field', ''.join(p.read_text() for p in (f.root/'native-export').glob('*.json')))

    def test_history_png_transport_bytes_use_image_allowance_without_mutating_wire(self):
        f = self.fixture
        ledger, job, gateway = f.gateway(f.config('glm', vision=True))
        url = 'data:image/png;base64,' + 'A'*60000
        history = [{'role':'user','content':[{'type':'image_url','image_url':{'url':url}}]},
                   self.message(), {'role':'tool','tool_call_id':'tc1','content':'actual result'}]
        self.response(self.message('tc2'))
        self.call(gateway, job, history=history, images=[f.image])
        payload = json.loads(f.opener.calls[-1].data)
        self.assertEqual(payload['messages'][1]['content'][0]['image_url']['url'], url)
        self.assertEqual(history[0]['content'][0]['image_url']['url'], url)

    def test_bad_tool_protocol_is_charged_without_content_fallback(self):
        messages = [self.message(name='wrong'), self.message(cid=''), self.message(cid='  '),
                    self.message(arguments='{"answer":'), self.message(arguments='[]'),
                    self.message(arguments='{"answer":"bad"}'), self.message(arguments='{"answer":7,"extra":1}'),
                    {'content':'{"answer":7}'}, self.message()]
        messages[-1]['tool_calls'].append(deepcopy(messages[-1]['tool_calls'][0]))
        for message in messages:
            with self.subTest(message=message):
                ledger, job, gateway = self.fixture.gateway(self.fixture.config('glm'))
                self.response(message)
                before = len(self.fixture.opener.calls)
                with self.assertRaisesRegex(ValueError, 'attempts exhausted'):
                    self.call(gateway, job)
                self.assertEqual(len(self.fixture.opener.calls), before + 1)
                with ledger.connect() as con:
                    row = con.execute('SELECT state,cost FROM model_requests').fetchone()
                self.assertEqual(tuple(row), ('invalid_response', None))

    def test_history_and_schema_validation_are_zero_send(self):
        f = self.fixture
        ledger, job, gateway = f.gateway(f.config('glm'))
        for history in ([{'role':'system','content':'duplicate system'}],
                        [self.message()], [self.message(), {'role':'tool','tool_call_id':'wrong','content':'x'}],
                        [{'role':'tool','tool_call_id':'tc1','content':'x'}]):
            with self.subTest(history=history), self.assertRaises(ValueError):
                self.call(gateway, job, history=history)
        with self.assertRaises(ValueError):
            gateway.call_tool(job, 't', 'x', self.tools*2, system='s')
        with self.assertRaises(ValueError):
            self.call(gateway, job, max_requests=2)
        self.assertEqual(f.opener.calls, [])
        self.assertEqual(ledger.summary()['model_requests'], 0)

    def test_history_images_and_reasoning_above_estimate_reach_transport_intact(self):
        f = self.fixture
        cfg = f.config('glm', vision=True)
        cfg['model']['reserve_input_tokens'] = 2500
        ledger, job, gateway = f.gateway(cfg)
        self.response(self.message('tc2'))
        history = [{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,controlled'}}]},
                   self.message(), {'role':'tool','tool_call_id':'tc1','content':'x'}]
        history[1]['reasoning_content'] = 'x'*60000
        self.call(gateway, job, history=history, images=[f.image], attempt_id='original')
        self.assertEqual(json.loads(f.opener.calls[0].data)['messages'][1:-1],history)
        self.assertEqual(ledger.summary()['model_requests'],1)

    def test_http_unknown_is_not_reissued_under_another_purpose_or_job_in_attempt(self):
        f = self.fixture
        ledger, job, gateway = f.gateway(f.config('glm'))
        f.opener.error = TimeoutError('controlled')
        with patch('webcollect.model_gateway.time.sleep'), patch('webcollect.batch_core.time', wraps=time) as clock:
            clock.time.side_effect=itertools.count(time.time(),2).__next__
            for purpose in ('original', 'different-purpose'):
                with self.assertRaises(OutcomeUnknown):
                    gateway.call_tool(job, purpose, 'x', self.tools, system='s', attempt_id='a', max_requests=2)
        self.assertEqual(len(f.opener.calls), 2)  # frozen cap tightens the three-retry policy
        self.assertEqual(ledger.summary()['usage_covered_requests'], 0)

    def test_actual_http_retry_and_frozen_attempt_cap(self):
        from webcollect.batch_core import BudgetStop
        f = self.fixture
        ledger, job, gateway = f.gateway(f.config('glm'))
        self.response(self.message(name='wrong'))
        with self.assertRaisesRegex(BudgetStop, 'max_requests'):
            self.call(gateway, job, attempts=3, attempt_id='one', max_requests=2)
        self.assertEqual(len(f.opener.calls), 2)
        with self.assertRaisesRegex(ValueError, 'Frozen attempt'):
            self.call(gateway, job, attempt_id='one', max_requests=3)
        self.assertEqual(len(f.opener.calls), 2)

    def test_synthetic_fixture_is_explicit_assistant_and_counts_no_http(self):
        f = self.fixture
        ledger, job, gateway = f.gateway(load_json(CONFIG))
        with self.assertRaisesRegex(ValueError, 'explicit assistant'):
            self.call(gateway, job)
        self.assertEqual(ledger.summary()['model_requests'], 0)
        result = self.call(gateway, job, synthetic_response=self.message(), attempt_id='a', max_requests=1)
        self.assertEqual(result['tool_call_id'], 'tc1')
        with ledger.connect() as con:
            material = json.loads(con.execute('SELECT request_json FROM model_requests').fetchone()[0])
        self.assertFalse(material['http_dispatch'])
        self.assertEqual(f.opener.calls, [])

    def test_glm_session_25_is_atomic_across_workers_and_bound_to_original_attempt(self):
        from concurrent.futures import ThreadPoolExecutor
        from webcollect.batch_core import SessionGLMCallLimit
        import itertools
        import time
        f = self.fixture
        cfg=f.config('glm')
        cfg['budget']['lease_seconds']=3600
        self.response(self.message())
        with patch('webcollect.batch_core.time',wraps=time) as clock:
            clock.time.side_effect=itertools.count(time.time(),2).__next__
            ledger, unused, gateway = f.gateway(cfg)
            ledger.finish(unused)
            def job(kind, aid):
                return ledger.claim(kind, job_id=ledger.enqueue(kind,{'attempt_id':aid}))
            aid='formal-session'
            original=job('react-native-decision',aid)
            for n in range(24):
                gateway.call_tool(original,'before-'+str(n),'x',self.tools,system='s',attempt_id=aid)
            other=job('shared-tool',aid)
            def send(item):
                try:
                    gateway.call_tool(item,'potential-last-'+item['kind'],'x',self.tools,system='s',attempt_id=aid)
                    return 'sent'
                except (SessionGLMCallLimit,OutcomeUnknown):
                    return 'stopped'
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertCountEqual(list(pool.map(send,[original,other])),['sent','stopped'])
            with self.assertRaises(SessionGLMCallLimit) as stop:
                gateway.call_tool(other,'after-restart','x',self.tools,system='s',attempt_id=aid)
            self.assertEqual(stop.exception.details['used'],25)
            self.assertEqual(len(f.opener.calls),25)
            with self.assertRaisesRegex(ValueError,'original ReAct session'):
                gateway.call_tool(original,'wrong binding','x',self.tools,system='s',attempt_id='independent')
            # A generic native purpose outside the original session still has its own accounting.
            gateway.call_tool(other,'unrelated','x',self.tools,system='s',attempt_id='independent')
            self.assertEqual(len(f.opener.calls),26)

    def test_non_glm_transport_does_not_consume_a_glm_session_limit(self):
        import itertools
        import time
        f=self.fixture
        cfg=f.config('deepseek')
        cfg['budget']['lease_seconds']=3600
        self.response(self.message())
        with patch('webcollect.batch_core.time',wraps=time) as clock:
            clock.time.side_effect=itertools.count(time.time(),2).__next__
            ledger,unused,gateway=f.gateway(cfg)
            ledger.finish(unused)
            aid='other-provider'
            job=ledger.claim('react-native-decision',job_id=ledger.enqueue('react-native-decision',{'attempt_id':aid}))
            for i in range(26):
                gateway.call_tool(job,str(i),'x',self.tools,system='s',attempt_id=aid)
        self.assertEqual(len(f.opener.calls),26)
        self.assertFalse(ledger.real_glm)

    def test_twenty_fifth_concurrent_dispatch_is_denied_in_original_transaction(self):
        from concurrent.futures import ThreadPoolExecutor
        from webcollect.batch_core import BudgetStop
        f = self.fixture
        cfg = f.config('glm')
        cfg['budget'].update(max_model_cost_micros=10_000_000, lease_seconds=3600)
        # Controlled elapsed provider intervals keep this SQLite concurrency
        # regression independent of 24 seconds of wall-clock rate waiting.
        import itertools
        import time
        ticks = itertools.count(time.time(), 2)
        self.response(self.message())
        with patch('webcollect.batch_core.time.time', side_effect=lambda: next(ticks)):
            ledger, job, gateway = f.gateway(cfg)
            def send(index):
                try:
                    gateway.call_tool(job, 'parallel-' + str(index), 'x', self.tools, system='s',
                                      attempt_id='shared-attempt', max_requests=24)
                    return 'sent'
                except BudgetStop:
                    return 'denied'
            with ThreadPoolExecutor(max_workers=4) as executor:
                outcomes = list(executor.map(send, range(25)))
        self.assertEqual(outcomes.count('sent'), 24)
        self.assertEqual(outcomes.count('denied'), 1)
        self.assertEqual(len(f.opener.calls), 24)
        self.assertEqual(ledger.summary()['model_requests'], 24)

if __name__ == '__main__':
    unittest.main()
