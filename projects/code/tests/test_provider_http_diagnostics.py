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


class NativeAccountHealth(unittest.TestCase):
    def setUp(self):
        self.fixture = provider_fixtures.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.tools = [{'type':'function','function':{'name':'act','parameters':provider_fixtures.SCHEMA}}]

    def test_native_1113_holds_account_new_independent_session_selects_other_authorized_key(self):
        from webcollect.model_gateway import ModelGateway
        from webcollect.model_credentials import account_id
        f = self.fixture
        keys = ['offline-authorized-one', 'offline-authorized-two']
        source = f.root/'offline-accounts.yaml'
        source.write_text('glm:\n' + ''.join('  - '+key+'\n' for key in keys))
        cfg = f.config('glm')
        cfg['model'].update(api_key_file=str(source), api_key_env='CONTROLLED_UNUSED_ENV')
        ledger, job, gateway = f.gateway(cfg)
        f.opener.error = urllib.error.HTTPError('https://provider.invalid',429,'opaque',{},
            io.BytesIO(b'{"error":{"code":"1113"}}'))
        with self.assertRaises(OutcomeUnknown):
            gateway.call_tool(job,'first','x',self.tools,system='s',attempt_id='a',max_requests=2)
        with ledger.connect() as con:
            original = dict(con.execute('SELECT * FROM model_requests').fetchone())
        self.assertEqual(ledger.unavailable_model_accounts(), {account_id(keys[0])})
        # A session already bound to key one cannot rotate after its failure.
        with self.assertRaises(OutcomeUnknown):
            gateway.call_tool(job,'next','x',self.tools,system='s',attempt_id='a',max_requests=2)
        self.assertEqual(len(f.opener.calls),1)
        f.opener.error = None
        f.opener.raw['choices'] = [{'finish_reason':'tool_calls','message':{
            'tool_calls':[{'id':'other','type':'function','function':{'name':'act','arguments':'{"answer":1}'}}]}}]
        next_gateway = ModelGateway(ledger)
        other_job = ledger.claim('test',job_id=ledger.enqueue('test',{'offline':'independent'}))
        next_gateway.call_tool(other_job,'other','x',self.tools,system='s',attempt_id='b',max_requests=2)
        self.assertEqual(len(f.opener.calls),2)
        self.assertEqual(f.opener.calls[-1].get_header('Authorization'),'Bearer '+keys[1])
        with ledger.connect() as con:
            self.assertEqual(dict(con.execute('SELECT * FROM model_requests WHERE id=?',(original['id'],)).fetchone()),original)
        for key in keys:
            self.assertNotIn(key.encode(), ledger.path.read_bytes())

    def test_native_rate_codes_respect_original_retry_after_and_remain_unknown(self):
        from webcollect.model_credentials import account_id
        f = self.fixture
        for code in ('1302','1305'):
            ledger, job, gateway = f.gateway(f.config('glm'))
            f.opener.error = urllib.error.HTTPError('https://provider.invalid',429,'opaque',{'Retry-After':'120'},
                io.BytesIO(json.dumps({'error':{'code':code}}).encode()))
            with self.assertRaises(OutcomeUnknown):
                gateway.call_tool(job,'rate','x',self.tools,system='s',attempt_id=code,max_requests=2)
            with ledger.connect() as con:
                row = dict(con.execute('SELECT * FROM model_requests').fetchone())
            self.assertEqual(row['state'],'unknown')
            self.assertIsNone(row['cost'])
            detail = json.loads(row['response'])['provider_error']
            self.assertEqual(detail['retry_after_seconds'],120)
            self.assertEqual(ledger.unavailable_model_accounts(), {account_id('offline-secret-never-export')})
            with patch('webcollect.batch_core.time.time',return_value=row['finished']+121):
                self.assertEqual(ledger.unavailable_model_accounts(),set())
            # Expiry of rate backoff does not authorize an UNKNOWN replay.
            with self.assertRaises(OutcomeUnknown):
                gateway.call_tool(job,'new-purpose','x',self.tools,system='s',attempt_id=code,max_requests=2)
            with ledger.connect() as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0],1)

    def test_held_account_filter_keeps_existing_yaml_dictionary_key_entries(self):
        from webcollect.model_credentials import credential, account_id
        f = self.fixture
        source = f.root/'offline-dictionary-accounts.yaml'
        source.write_text('glm:\n  - api_key: offline-dict-one\n  - api_key: offline-dict-two\n')
        model = f.config('glm')['model']
        model.update(api_key_file=str(source), api_key_env='CONTROLLED_UNUSED_ENV')
        self.assertEqual(credential(model, excluded_accounts={account_id('offline-dict-one')}), 'offline-dict-two')
