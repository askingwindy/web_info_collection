"""Temporary tokens and stub HTTP only; never read the project credential."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from webcollect import model_credentials
from webcollect.batch_core import BatchLedger, validate_config
from webcollect.model_gateway import ModelGateway
import test_model_provider_protocols as protocol


class RuntimeCredentialTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.token = self.root / 'token'
        self.token.write_text('temporary-offline-token\n')
        dns=patch('webcollect.model_gateway.socket.getaddrinfo', return_value=[('OFFLINE',)])
        dns.start(); self.addCleanup(dns.stop)
        for guard in (patch.dict('os.environ', {}, clear=True),
                      patch.object(model_credentials, 'PROJECT_GLM_YAML', self.root/'token.yaml'),
                      patch.object(model_credentials, 'PROJECT_GLM_ACCOUNT', 'glm1'),
                      patch.object(model_credentials, 'PROJECT_GLM_TOKEN', self.token)):
            guard.start(); self.addCleanup(guard.stop)

    def config(self):
        return protocol.ProviderProtocolTests.config(self, 'glm', vision=True)

    def test_project_glm_file_is_used_without_mutating_config_or_environment(self):
        import os
        config = self.config()
        self.assertEqual(validate_config(config, credentials=True), config)
        self.assertNotIn(config['model']['api_key_env'], os.environ)
        self.assertEqual(model_credentials.credential(config['model']), 'temporary-offline-token')
        other = dict(config['model'], provider='deepseek')
        with self.assertRaisesRegex(ValueError, 'Missing model credential environment'):
            model_credentials.credential(other)

    def test_explicit_file_and_environment_priority(self):
        config = self.config(); config['model']['api_key_file'] = str(self.token)
        self.assertEqual(validate_config(config), config)
        self.token.unlink()
        with patch.dict('os.environ', {config['model']['api_key_env']: 'temporary-env-token'}):
            self.assertEqual(model_credentials.credential(config['model']), 'temporary-env-token')
        config['model']['api_key_file'] = 'relative-token'
        with self.assertRaisesRegex(ValueError, 'absolute'):
            validate_config(config)

    def test_labelled_glm_file_requires_one_unambiguous_provider_token(self):
        token = 'temporaryidentifier.temporarysecret'
        self.token.write_text('智谱 API 凭据：' + token)
        self.assertEqual(model_credentials.credential(self.config()['model']), token)
        self.token.write_text('两个凭据：' + token + ' anotheridentifier.anothersecret')
        with self.assertRaisesRegex(ValueError, 'suppressed'):
            model_credentials.credential(self.config()['model'])

    def test_missing_empty_or_multiline_token_stops_before_reservation(self):
        config = self.config(); ledger = BatchLedger(self.root / 'ledger.sqlite3', config, initialize=True)
        for text in ('', 'first\nsecond', 'x' * 4097, '{"token":"temporary"}'):
            self.token.write_text(text)
            with self.subTest(text_length=len(text)), self.assertRaisesRegex(ValueError, 'suppressed'):
                model_credentials.credential(config['model'])
        self.token.unlink()
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            model_credentials.credential(config['model'])
        self.assertEqual(ledger.summary()['model_requests'], 0)

    def test_request_reads_token_but_persistent_evidence_contains_no_secret(self):
        config = self.config(); ledger = BatchLedger(self.root / 'ledger.sqlite3', config, initialize=True)
        job = ledger.claim('test', job_id=ledger.enqueue('test', {'offline': True}))
        opener = protocol.StubOpener()
        with patch('urllib.request.build_opener', return_value=opener):
            result = ModelGateway(ledger).call(job, 'temporary-token-test', 'JSON测试', protocol.SCHEMA, attempts=1)
        self.assertEqual(result, {'answer': 42})
        self.assertEqual(opener.calls[0].get_header('Authorization'), 'Bearer temporary-offline-token')
        self.assertNotIn(b'temporary-offline-token', ledger.path.read_bytes())
        self.assertNotIn('temporary-offline-token', json.dumps(ledger.summary()))

    def test_glm1_yaml_selection_trims_whitespace_and_never_uses_ark1(self):
        path=self.root/'token.yaml';path.write_text('glm1: "  offline-glm-credential  "\nark1: "offline-other-credential"\n')
        config=self.config();ledger=BatchLedger(self.root/'yaml-ledger.sqlite3',config,initialize=True)
        job=ledger.claim('test',job_id=ledger.enqueue('test',{'offline':True}));opener=protocol.StubOpener()
        with patch('urllib.request.build_opener',return_value=opener):
            result=ModelGateway(ledger).call(job,'yaml-glm1-test','JSON测试',protocol.SCHEMA,attempts=1)
        self.assertEqual(result,{'answer':42})
        self.assertEqual(opener.calls[0].get_header('Authorization'),'Bearer offline-glm-credential')
        for secret in (b'offline-glm-credential',b'offline-other-credential'):
            self.assertNotIn(secret,ledger.path.read_bytes())

    def test_yaml_missing_or_duplicate_glm1_never_falls_back_to_another_account(self):
        path=self.root/'token.yaml'
        for material in ('ark1: "other"\n','glm1: "first"\nglm1: "second"\n','glm1: ["invalid"]\n'):
            path.write_text(material)
            with self.assertRaisesRegex(ValueError,'suppressed'):
                model_credentials.credential(self.config()['model'])

    def test_authorized_glm_list_accepts_indent_tabs_and_pins_first_account(self):
        path=self.root/'token.yaml';path.write_text('glm:\n\t- "offline-first"\n\t- "offline-second"\nark1: "offline-other"\n')
        with patch.object(model_credentials,'PROJECT_GLM_ACCOUNT','glm'):
            self.assertEqual(model_credentials.credential(self.config()['model'],selection_index=1),'offline-second')
            self.assertEqual(model_credentials.credential(self.config()['model']),'offline-first')
            path.write_text('glm:\n  - "invalid credential with spaces"\n  - "offline-second"\n')
            with self.assertRaisesRegex(ValueError,'suppressed'):
                model_credentials.credential(self.config()['model'])
