"""Ark protocol and dual-route boundaries using disposable, offline fixtures."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error

from webcollect import model_credentials
from webcollect.batch_core import OutcomeUnknown, validate_config
from webcollect.model_gateway import ModelGateway
import test_model_provider_protocols as protocol


MODELS = ('glm-5-3-flash-260828', 'deepseek-v4-1-flash-economy-261017')
ENDPOINT = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'


class ArkProviderTests(unittest.TestCase):
    setUp = protocol.ProviderProtocolTests.setUp
    gateway = protocol.ProviderProtocolTests.gateway

    def config(self, model=MODELS[0], *, vision=True):
        config = protocol.ProviderProtocolTests.config(self, 'ark', vision=vision)
        config['model'].update(model=model, endpoint=ENDPOINT, reasoning_effort='low')
        self.opener.raw['model'] = model
        return config

    def test_both_models_use_ark_auth_and_total_output_limit(self):
        for model in MODELS:
            ledger, job, gateway = self.gateway(self.config(model))
            self.assertEqual(gateway.call(job, 'ark-json', 'JSON测试', protocol.SCHEMA, attempts=1), {'answer': 42})
            request = self.opener.calls[-1]; payload = json.loads(request.data)
            self.assertEqual(request.full_url, ENDPOINT)
            self.assertEqual(request.get_header('Authorization'), 'Bearer offline-secret-never-export')
            self.assertEqual(payload['model'], model)
            self.assertEqual(payload['max_completion_tokens'], ledger.config['model']['max_completion_tokens'])
            self.assertNotIn('max_tokens', payload)
            self.assertNotIn('store', payload)
            self.assertEqual(payload['thinking'], {'type': 'enabled'})
            self.assertEqual(payload['reasoning_effort'], 'low')
            self.assertEqual('response_format' in payload, model == MODELS[1])
            self.assertIn('JSON Schema exactly:', payload['messages'][0]['content'])
            self.assertEqual(ledger.summary()['model_cost_micros'], 300)
            with ledger.connect() as con:
                recorded = json.loads(con.execute('SELECT request_json FROM model_requests').fetchone()[0])
            self.assertEqual(recorded['provider'], 'ark')
            self.assertEqual(recorded['model'], model)
            self.assertNotIn(b'offline-secret-never-export', ledger.path.read_bytes())

    def test_vision_sends_unmodified_original_png_as_data_url(self):
        import base64
        for model in MODELS:
            _, job, gateway = self.gateway(self.config(model))
            gateway.call(job, 'ark-vision', 'JSON pixels', protocol.SCHEMA, images=[self.image], attempts=1)
            payload = json.loads(self.opener.calls[-1].data)
            image = payload['messages'][1]['content'][1]['image_url']
            self.assertEqual(image['url'], 'data:image/png;base64,' + base64.b64encode(self.image.read_bytes()).decode())
            self.assertEqual(image['detail'], 'high')

    def test_existing_standard_model_ledgers_remain_readable_and_keep_their_dialect(self):
        from quality_inspector.delivery_pipeline import _mode
        config = self.config('deepseek-v4-1-flash-261017')
        self.assertEqual(validate_config(config), config)
        ledger, job, gateway = self.gateway(config)
        _mode(ledger, 'real')
        self.assertEqual(gateway.call(job, 'legacy-standard', 'JSON', protocol.SCHEMA, attempts=1), {'answer': 42})
        payload = json.loads(self.opener.calls[-1].data)
        self.assertEqual(payload['model'], 'deepseek-v4-1-flash-261017')
        self.assertEqual(payload['response_format'], {'type': 'json_object'})

    def test_capabilities_endpoint_model_and_output_limit_are_explicit(self):
        for update in ({'endpoint': 'https://open.bigmodel.cn/api/paas/v4/chat/completions'},
                       {'model': 'glm-5.3-flash'}, {'max_completion_tokens': 65537},
                       {'image_encoding': 'raw_base64'}):
            config = self.config(); config['model'].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_config(config)
        for field in ('supports_vision', 'image_tokens_per_image', 'request_overhead_tokens'):
            config = self.config(); del config['model'][field]
            with self.assertRaises(ValueError): validate_config(config)

    def test_selected_model_must_match_provider_response(self):
        ledger, job, gateway = self.gateway(self.config())
        self.opener.raw['model'] = MODELS[1]
        with self.assertRaisesRegex(ValueError, 'attempts exhausted'):
            gateway.call(job, 'model-version', 'JSON', protocol.SCHEMA, attempts=1)
        with ledger.connect() as con:
            self.assertEqual(con.execute('SELECT state FROM model_requests').fetchone()[0], 'invalid_response')
        self.assertEqual(ledger.summary()['model_cost_micros'], 300)

    def test_fenced_json_preserves_raw_and_success_replay_uses_original_request(self):
        for model in MODELS:
            ledger, job, gateway = self.gateway(self.config(model))
            content = '```json\n{"answer":42}\n```'
            self.opener.raw['choices'][0]['message']['content'] = content
            before = len(self.opener.calls)
            for _ in range(2):
                self.assertEqual(gateway.call(job, 'fence', 'JSON', protocol.SCHEMA), {'answer': 42})
            self.assertEqual(len(self.opener.calls), before + 1)
            with ledger.connect() as con:
                saved = json.loads(con.execute('SELECT response FROM model_requests').fetchone()[0])
            self.assertEqual(saved['provider_response']['choices'][0]['message']['content'], content)
            self.assertTrue(saved['content_envelope_normalized'])

    def test_http_timeout_or_unknown_usage_never_switches_or_resends(self):
        failures = (TimeoutError(), urllib.error.HTTPError(ENDPOINT, 401, 'suppressed', {}, None),
                    urllib.error.HTTPError(ENDPOINT, 429, 'suppressed', {}, None), None)
        for error in failures:
            ledger, job, gateway = self.gateway(self.config())
            self.opener.error = error
            if error is None: self.opener.raw['usage'].pop('prompt_tokens_details')
            before = len(self.opener.calls)
            for _ in range(2):
                with self.assertRaises(OutcomeUnknown):
                    gateway.call(job, 'unknown', 'JSON', protocol.SCHEMA)
            self.assertEqual(len(self.opener.calls), before + 1)
            self.assertEqual(json.loads(self.opener.calls[-1].data)['model'], MODELS[0])
            self.assertEqual(ledger.summary()['model_cost_micros'], 'UNKNOWN')

    def test_text_only_capability_blocks_images_before_reservation(self):
        ledger, job, gateway = self.gateway(self.config(vision=False))
        with self.assertRaisesRegex(ValueError, 'does not support'):
            gateway.call(job, 'no-image', 'JSON', protocol.SCHEMA, images=[self.image])
        self.assertEqual(ledger.summary()['model_requests'], 0)
        self.assertEqual(self.opener.calls, [])

    def test_ark1_label_is_selected_without_reading_glm_into_configuration(self):
        shared = self.root / 'token'
        shared.write_text('glm：offlineidentifier.offlinesecret\nark1：offline-ark-key\n')
        config = self.config(); config['model']['api_key_env'] = 'OFFLINE_ARK_EMPTY'
        with patch.dict('os.environ', {}, clear=True), patch.object(model_credentials, 'PROJECT_ARK_TOKEN', shared):
            self.assertEqual(model_credentials.credential(config['model']), 'offline-ark-key')
            self.assertEqual(validate_config(config, credentials=True), config)
            self.assertNotIn('offline-ark-key', json.dumps(config))
            # The existing GLM resolver still selects its own credential.
            glm = dict(config['model'], provider='glm', api_key_file=str(shared))
            self.assertEqual(model_credentials.credential(glm), 'offlineidentifier.offlinesecret')

    def test_ark1_directory_explicit_file_and_environment_priority(self):
        folder = self.root / 'tokens'; folder.mkdir()
        (folder / 'ark1').write_text('offline-ark-file')
        config = self.config(); config['model']['api_key_file'] = str(folder)
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(model_credentials.credential(config['model']), 'offline-ark-file')
        with patch.dict('os.environ', {config['model']['api_key_env']: 'offline-ark-env'}):
            self.assertEqual(model_credentials.credential(config['model']), 'offline-ark-env')

    def test_cli_configuration_check_recognizes_runtime_file_without_exporting_secret(self):
        from webcollect.batch import main
        source = self.root / 'ark1'; source.write_text('offline-ark-file')
        config = self.config(); config['model']['api_key_file'] = str(source)
        path = self.root / 'config.json'; path.write_text(json.dumps(config))
        out = io.StringIO()
        with patch.dict('os.environ', {}, clear=True), redirect_stdout(out):
            self.assertEqual(main(['validate-config', '--config', str(path)]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result['missing'], [])
        self.assertFalse(result['real_model_verified'])
        self.assertNotIn('offline-ark-file', out.getvalue())

    def test_yaml_selects_ark1_for_ark_and_glm1_for_glm_without_cross_provider_keys(self):
        source = self.root / 'token.yaml'
        source.write_text('glm1: "offline-glm-yaml-secret"\nark1: "  offline-ark-yaml-secret  "\n')
        config = self.config(); config['model']['api_key_file'] = str(source)
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(model_credentials.credential(config['model']), 'offline-ark-yaml-secret')
            glm = dict(config['model'], provider='glm')
            self.assertEqual(model_credentials.credential(glm), 'offline-glm-yaml-secret')
            ledger, job, gateway = self.gateway(config)
            self.assertEqual(gateway.call(job, 'yaml-ark-only', 'JSON', protocol.SCHEMA, attempts=1), {'answer': 42})
        self.assertEqual(self.opener.calls[-1].get_header('Authorization'), 'Bearer offline-ark-yaml-secret')
        for secret in (b'offline-glm-yaml-secret', b'offline-ark-yaml-secret'):
            self.assertNotIn(secret, ledger.path.read_bytes())

    def test_yaml_missing_duplicate_or_invalid_ark1_never_uses_glm1(self):
        source = self.root / 'token.yaml'
        config = self.config(); config['model']['api_key_file'] = str(source)
        for text in ('glm1: "offline-glm-only"\n', 'ark1: "one"\nark1: "two"\n',
                     'glm1: "offline-glm-only"\nark1: ["invalid"]\n'):
            source.write_text(text)
            with patch.dict('os.environ', {}, clear=True), self.assertRaisesRegex(ValueError, 'suppressed'):
                model_credentials.credential(config['model'])
        source.write_text('glm1: {api_key: "offline-glm-nested"}\nark1: {api_key: "offline-ark-nested"}\n')
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(model_credentials.credential(config['model']), 'offline-ark-nested')

    def test_renamed_yaml_with_legacy_labels_reads_only_explicit_top_level_ark1(self):
        source = self.root / 'token.yaml'
        config = self.config(); config['model']['api_key_file'] = str(source)
        source.write_text('glm1: [unfinished legacy content\nark1: offline-ark-labelled-only\n')
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(model_credentials.credential(config['model']), 'offline-ark-labelled-only')
            ledger, job, gateway = self.gateway(config)
            self.assertEqual(gateway.call(job, 'legacy-yaml-ark1', 'JSON', protocol.SCHEMA, attempts=1), {'answer': 42})
        self.assertEqual(self.opener.calls[-1].get_header('Authorization'), 'Bearer offline-ark-labelled-only')
        self.assertNotIn(b'offline-ark-labelled-only', ledger.path.read_bytes())

    def test_legacy_yaml_fallback_rejects_missing_duplicate_or_nested_only_ark1(self):
        source = self.root / 'token.yaml'
        config = self.config(); config['model']['api_key_file'] = str(source)
        for text in ('glm1: [unfinished\n',
                     'glm1: [unfinished\nark1: one\nark1: two\n',
                     'glm1: [unfinished\n  ark1: nested-only\n',
                     'glm1: [unfinished\nark1: "unclosed\n'):
            source.write_text(text)
            with patch.dict('os.environ', {}, clear=True), self.assertRaisesRegex(ValueError, 'suppressed'):
                model_credentials.credential(config['model'])

    def test_missing_ambiguous_or_oversized_shared_file_stops_before_reservation(self):
        source = self.root / 'token'
        config = self.config(); config['model']['api_key_file'] = str(source)
        ledger, _, _ = self.gateway(config)  # Environment avoids opening missing file.
        for content in ('glm：offlineidentifier.offlinesecret', 'ark1：one\nark1：two',
                        'ark1：\nglm：wrong', 'ark1：one\n' + 'x' * 4096, ''):
            source.write_text(content)
            with patch.dict('os.environ', {}, clear=True), self.subTest(length=len(content)), self.assertRaises(ValueError):
                ModelGateway(ledger)
        self.assertEqual(ledger.summary()['model_requests'], 0)

    def test_examples_are_bounded_and_glm_is_the_preferred_profile(self):
        folder = Path(__file__).resolve().parents[1] / 'config'
        for name, model in zip(('glm', 'deepseek'), MODELS):
            config = json.loads((folder / f'batch-ark-{name}.example.json').read_text())
            self.assertEqual(validate_config(config), config)
            self.assertEqual(config['model']['provider'], 'ark')
            self.assertEqual(config['model']['model'], model)
            self.assertEqual(config['budget']['max_model_requests'], 1)
            self.assertEqual(config['budget']['max_probe_pages'], 0)

    def test_delivery_pipeline_accepts_explicit_ark_vision_and_rejects_wrong_versions(self):
        from quality_inspector.delivery_pipeline import _mode
        for model in MODELS:
            config = self.config(model)
            _mode(SimpleNamespace(config=config), 'real')
            for update in ({'supports_vision': False}, {'model': 'glm-5.3-flash'}, {'provider': 'glm'}):
                wrong = deepcopy(config); wrong['model'].update(update)
                with self.subTest(update=update), self.assertRaises(ValueError):
                    _mode(SimpleNamespace(config=wrong), 'real')

    def test_site_qualification_rechecks_exact_ark_prompt_and_image_provenance(self):
        from test_site_qualification_provenance import QualificationProvenance
        from site_planner.qualification import qualify_catalog, validate_qualification
        from webcollect.batch_core import BatchLedger, load_json
        fixture = QualificationProvenance()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        self.opener.raw['choices'][0]['message']['content'] = json.dumps(fixture.decision)
        with patch('urllib.request.build_opener', return_value=self.opener):
            for i, model in enumerate(MODELS):
                config = self.config(model)
                ledger = BatchLedger(self.root / f'qualification-{i}.sqlite3', config, initialize=True)
                result = qualify_catalog(ledger, fixture.catalog, self.root / f'qualified-{i}')
                record = load_json(result['catalog_file'])['records'][0]
                self.assertEqual(validate_qualification(record)['status'], 'ready')
                self.assertFalse(record['site_qualification']['sample_qc_approval'])
                request = self.opener.calls[-1]; payload = json.loads(request.data)
                self.assertEqual(len(payload['messages'][1]['content']) - 1, len(fixture.images))

    def test_discovery_search_uses_separate_glm_key_and_never_sends_ark_key_to_bigmodel(self):
        from site_planner.discovery_tools import glm_search, SEARCH_ENDPOINT
        settled = []
        pool = SimpleNamespace(reserve_tool=lambda *a, **kw: ('offline-search-id', None),
                               settle_tool=lambda *a: settled.append(a))
        config = self.config()
        self.opener.raw = {'search_result': []}
        with patch.dict('os.environ', {'GLM_API_KEY': 'offline-glm-search-only'}):
            result = glm_search(pool, 'offline-ark-run', config['model'], '公开图书', self.root)
        self.assertEqual(result['results'], [])
        request = self.opener.calls[-1]
        self.assertEqual(request.full_url, SEARCH_ENDPOINT)
        self.assertEqual(request.get_header('Authorization'), 'Bearer offline-glm-search-only')
        self.assertNotIn(b'offline-secret-never-export', request.data)
        self.assertEqual(settled[0][1], 'succeeded')


if __name__ == '__main__': unittest.main()
