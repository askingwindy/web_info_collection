"""Bounded timeout retries use fake HTTP/time and disposable original ledgers."""
from copy import deepcopy
import io
import json
import unittest
from unittest.mock import patch
import urllib.error

import test_model_provider_protocols as fixtures
from webcollect.batch_core import OutcomeUnknown
from webcollect.candidate_consumer import guard_request_scope


class Clock:
    def __init__(self):
        self.now = 1_800_000_000
        self.sleeps = []
    def time(self):
        return self.now
    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class TimeoutRetryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NativeToolProtocolTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.fixture
        self.clock = Clock()
        for mock in (patch('webcollect.batch_core.time', self.clock),
                     patch('webcollect.model_gateway.time', self.clock)):
            mock.start(); self.addCleanup(mock.stop)
        cfg = self.f.config('glm')
        cfg['model']['model'] = 'glm-5.3-flash'
        self.ledger, self.job, self.gateway = self.f.gateway(cfg)
        self.fixture.response(self.fixture.message())
        self.sent = []

    def transport(self, failures):
        original = self.f.opener.open
        remaining = iter(failures)
        def send(request, timeout):
            self.sent.append((self.clock.time(), deepcopy(request)))
            error = next(remaining, None)
            if error:
                self.f.opener.calls.append(request)
                raise error
            return original(request, timeout)
        self.f.opener.open = send

    def call(self, purpose='test', **kwargs):
        return self.gateway.call_tool(self.job, purpose, 'same observed page', self.fixture.tools,
            system='trusted', attempt_id='original-session', **kwargs)

    def rows(self):
        with self.ledger.connect() as con:
            return [dict(r) for r in con.execute('SELECT * FROM model_requests ORDER BY attempt')]

    def test_timeout_then_answer_preserves_unknown_and_allows_next_decision_and_cache(self):
        self.transport([TimeoutError()])
        result = self.call()
        rows = self.rows()
        self.assertEqual([r['state'] for r in rows], ['unknown','succeeded'])
        first = deepcopy(rows[0])
        follow = json.loads(rows[1]['request_json'])
        self.assertEqual((follow['timeout_retry_of'], follow['timeout_retry_root'],follow['timeout_retry_number']),
                         (first['id'],first['id'],1))
        with self.ledger.connect() as con:
            usage = self.ledger.session_http_usage(con,'original-session')
        self.assertEqual((usage['used'],usage['held'],usage['unresolved']),(2,None,None))
        self.assertEqual(self.call(),result)  # no HTTP on exact replay
        self.call('next decision')
        self.assertEqual(len(self.sent),3)
        self.assertEqual(self.rows()[0],first)
        self.assertEqual(guard_request_scope(self.ledger, None),[])
        self.assertEqual(len({r.headers['Authorization'] for _,r in self.sent}),1)
        self.assertEqual(len({r.headers['X-client-request-id'] for _,r in self.sent}),3)
        self.assertEqual(json.loads(self.sent[0][1].data),json.loads(self.sent[1][1].data))

    def test_three_retries_then_hold_survives_restart_or_new_purpose(self):
        self.transport([TimeoutError()]*4)
        with self.assertRaises(OutcomeUnknown):self.call()
        rows = self.rows()
        self.assertEqual([r['state'] for r in rows],['unknown']*4)
        self.assertEqual([t for t,_ in self.sent],[self.clock.now-35,self.clock.now-30,self.clock.now-20,self.clock.now])
        self.assertEqual([json.loads(r['request_json']).get('timeout_retry_number',0) for r in rows],[0,1,2,3])
        from webcollect.model_gateway import ModelGateway
        self.gateway = ModelGateway(self.ledger)
        for purpose in ('test','changed purpose'):
            with self.assertRaises(OutcomeUnknown):self.call(purpose)
        self.assertEqual(len(self.sent),4)
        self.assertEqual(rows,self.rows())
        self.assertEqual(sum(self.clock.sleeps),35)

    def test_global_interval_can_be_slower_than_backoff(self):
        self.ledger.config['budget']['min_model_interval_seconds'] = 12
        self.transport([urllib.error.URLError(TimeoutError())]*2)
        self.call()
        self.assertEqual([t-self.sent[0][0] for t,_ in self.sent],[0,12,24])

    def test_non_timeout_failures_and_missing_usage_are_not_retried(self):
        for error in (urllib.error.HTTPError('https://provider.invalid/',429,'ignored',{},io.BytesIO(b'{}')),
                      ConnectionResetError(), urllib.error.URLError(OSError())):
            with self.subTest(error=type(error).__name__):
                # A distinct test ledger; provider holds cannot be bypassed by a new purpose.
                self.ledger,self.job,self.gateway = self.f.gateway(self.f.config('glm'))
                self.sent=[];self.f.opener.open=fixtures.StubOpener().open
                self.transport([error])
                with self.assertRaises(OutcomeUnknown):self.call()
                self.assertEqual(len(self.sent),1)
        self.ledger,self.job,self.gateway = self.f.gateway(self.f.config('glm'))
        self.sent=[];self.f.opener.open=fixtures.StubOpener().open
        self.transport([]);self.f.opener.raw.pop('usage')
        # Stub's response owns its raw payload, so test the established transport directly.
        self.f.opener.open=lambda req,timeout: io.BytesIO(json.dumps({'choices':[]}).encode())
        with self.assertRaises(OutcomeUnknown):self.call()
        self.assertEqual(len(self.rows()),1)

    def test_attempt_budget_counts_every_timeout_retry(self):
        self.transport([TimeoutError()]*4)
        with self.assertRaises(OutcomeUnknown):self.call(max_requests=2)
        self.assertEqual(len(self.sent),2)
        self.assertEqual([r['state'] for r in self.rows()],['unknown']*2)

    def test_glm_25_limit_includes_timeout_retries(self):
        self.ledger.finish(self.job)
        self.job=self.ledger.claim('react-native-decision',job_id=self.ledger.enqueue(
            'react-native-decision',{'attempt_id':'original-session'}))
        self.transport([])
        for i in range(24):self.call('prior-'+str(i))
        self.f.opener.error=TimeoutError()
        with self.assertRaises(OutcomeUnknown):self.call('last')
        self.assertEqual(len(self.sent),25)
        with self.ledger.connect() as con:
            self.assertEqual(self.ledger.session_http_usage(con,'original-session')['used'],25)

    def test_retry_cannot_change_payload_or_follow_non_timeout(self):
        self.transport([TimeoutError()]*4)
        with self.assertRaises(OutcomeUnknown):self.call()
        rows=self.rows();previous=rows[-1];material=json.loads(previous['request_json'])
        material.update(timeout_retry_of=previous['id'],timeout_retry_number=4)
        with self.assertRaises(OutcomeUnknown):
            self.ledger.reserve_request(self.job,previous['purpose'],4,request_json=material)
        self.assertEqual(len(self.rows()),4)

    def test_ledger_rejects_changed_retry_payload_and_non_timeout_predecessor(self):
        for reason in ('TimeoutError','ConnectionResetError'):
            self.clock.sleep(1)
            material={'provider':'glm','model':'glm-5.3-flash','account_id':'offline','text':'original'}
            first=self.ledger.reserve_request(self.job,reason,0,request_json=material)
            self.ledger.settle_request(first['id'],state='unknown',error=reason,
                response={'transport_error':{'reason_type':reason}})
            material.update(timeout_retry_of=first['id'],timeout_retry_root=first['id'],timeout_retry_number=1)
            if reason=='TimeoutError':material['text']='changed'
            with self.assertRaises((OutcomeUnknown,ValueError)):
                self.ledger.reserve_request(self.job,reason,1,request_json=material)

    def test_schema_correction_keeps_timeout_count_and_original_unknown_records(self):
        original=self.f.opener.open
        counter=[]
        def send(req,timeout):
            counter.append(req)
            if len(counter) in (1,3):
                raise TimeoutError()
            self.fixture.response(self.fixture.message(name='wrong' if len(counter)==2 else 'act'))
            return original(req,timeout)
        self.f.opener.open=send
        self.call(attempts=2)
        rows=self.rows()
        self.assertEqual([r['state'] for r in rows],['unknown','invalid_response','unknown','succeeded'])
        self.assertEqual([json.loads(r['request_json']).get('timeout_retry_number',0) for r in rows],[0,1,0,2])
        with self.ledger.connect() as con:
            self.assertIsNone(self.ledger.session_http_usage(con,'original-session')['unresolved'])

    def test_existing_invalid_response_budget_is_not_enlarged_by_timeout_allowance(self):
        self.fixture.response(self.fixture.message(name='wrong'))
        self.transport([])
        for _ in range(2):
            with self.assertRaisesRegex(ValueError,'attempts exhausted'):self.call(attempts=2)
        self.assertEqual(len(self.sent),2)
