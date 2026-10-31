"""Provider failures retain status without echoing credentials or retrying."""
import io
import json
import unittest
import urllib.error
import socket
from unittest.mock import patch
import test_model_provider_protocols as provider_fixtures
from webcollect.batch_core import OutcomeUnknown


class ProviderHTTPDiagnostics(unittest.TestCase):
    def setUp(self):
        self.fixture = provider_fixtures.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_http_status_and_code_retained_without_body_or_secret(self):
        f = self.fixture
        f.opener.error = urllib.error.HTTPError('https://provider.invalid/', 429, 'secret prose', {},
            io.BytesIO(json.dumps({'error': {'code': '1302', 'message': 'offline-secret-never-export'}}).encode()))
        ledger, job, gateway = f.gateway(f.config('glm'))
        with self.assertRaisesRegex(OutcomeUnknown, 'HTTP status 429'):
            gateway.call(job, 'http-failure', 'offline check', provider_fixtures.SCHEMA)
        self.assertEqual(len(f.opener.calls), 1)
        with ledger.connect() as con:
            row = dict(con.execute('SELECT * FROM model_requests').fetchone())
        self.assertEqual(row['state'], 'unknown')
        self.assertEqual(row['error'], 'HTTPError:429')
        self.assertEqual(json.loads(row['response']), {'provider_error': {'http_status': 429,
            'provider_code': '1302', 'reason': 'provider_http_error'}})
        self.assertNotIn('offline-secret-never-export', row['response'])
        self.assertIsNone(row['cost'])

    def test_arbitrary_error_code_is_not_logged(self):
        f = self.fixture
        f.opener.error = urllib.error.HTTPError('https://provider.invalid/', 400, 'error', {},
            io.BytesIO(json.dumps({'error': {'code': 'Bearer offline-secret-never-export'}}).encode()))
        ledger, job, gateway = f.gateway(f.config('glm'))
        with self.assertRaises(OutcomeUnknown):
            gateway.call(job, 'http-failure', 'offline check', provider_fixtures.SCHEMA)
        with ledger.connect() as con:
            row = con.execute('SELECT response FROM model_requests').fetchone()[0]
        self.assertNotIn('offline-secret', row)

    def test_dns_failure_is_zero_send_without_request_reservation(self):
        f=self.fixture;ledger,job,gateway=f.gateway(f.config('glm'))
        with patch('webcollect.model_gateway.socket.getaddrinfo',side_effect=socket.gaierror(-2,'offline-secret')):
            with self.assertRaisesRegex(ValueError,'before reservation/HTTP dispatch'):
                gateway.call(job,'dns-local','offline check',provider_fixtures.SCHEMA)
        self.assertEqual(f.opener.calls,[]);self.assertEqual(ledger.summary()['model_requests'],0)
        self.assertNotIn(b'offline-secret',ledger.path.read_bytes())

    def test_transport_unknown_keeps_safe_cause_and_cache_never_needs_dns(self):
        f=self.fixture;ledger,job,gateway=f.gateway(f.config('glm'))
        self.assertEqual(gateway.call(job,'cached','offline check',provider_fixtures.SCHEMA),{'answer':42})
        with patch('webcollect.model_gateway.socket.getaddrinfo',side_effect=AssertionError('No cache IO')):
            self.assertEqual(gateway.call(job,'cached','offline check',provider_fixtures.SCHEMA),{'answer':42})
        f.opener.error=urllib.error.URLError(OSError(8,'offline-secret-never-export'))
        with self.assertRaises(OutcomeUnknown):gateway.call(job,'transport-failure','offline check',provider_fixtures.SCHEMA)
        with ledger.connect() as con:
            row=dict(con.execute("SELECT * FROM model_requests WHERE state='unknown'").fetchone())
        detail=json.loads(row['response'])['transport_error']
        self.assertEqual(detail['errno'],8);self.assertEqual(detail['error_type'],'URLError')
        self.assertNotIn('offline-secret',row['response']);self.assertIsNone(row['cost'])
