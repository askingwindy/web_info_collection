"""Controlled recovery protocol tests; no actual provider or human decision."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / 'projects/quality-inspector'), str(REPO / 'projects/code/tests')]
import test_document_text_qc as support
from webcollect.batch_core import BatchLedger, OutcomeUnknown
from webcollect.model_gateway import response_usage
from quality_inspector import document_auth_recovery as recovery, document_text_qc as lane


class DocumentAuthRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.case = support.DocumentTextQCTests('test_unknown_response_stays_ai_pending_with_original_unknown_charge')
        self.case.setUp(); self.addCleanup(self.case.doCleanups)
        self.root = self.case.root

    class RejectedAuthentication:
        def __init__(self, ledger): self.ledger = ledger
        def call(self, job, purpose, *args, **kwargs):
            request = self.ledger.reserve_request(job, purpose, 0, request_json={'CONTROLLED_NO_NETWORK': True})
            self.ledger.settle_request(request['id'], state='unknown', error='HTTPError:401',
                response={'provider_error': {'http_status': 401, 'provider_code': '1000', 'reason': 'provider_http_error'}})
            raise OutcomeUnknown('CONTROLLED authentication rejection, no actual network')

    class PersistThenCrash:
        def __init__(self, ledger): self.ledger = ledger
        def call(self, job, purpose, text, schema, *, synthetic_response=None, **kwargs):
            result = deepcopy(synthetic_response)
            for check in result['checks'].values():
                check.update(status='PASS', note='CONTROLLED persisted response fixture; no actual model review')
            model = self.ledger.config['model']
            request = self.ledger.reserve_request(job, purpose + ':CONTROLLED', 0,
                request_json={'system': 'CONTROLLED', 'text': text, 'schema': schema, 'images': [],
                              'provider': model['provider'], 'model': model['model']})
            raw = {'id': 'CONTROLLED-paid-known-response', 'model': model['model'],
                'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'prompt_tokens_details': {'cached_tokens': 0}}}
            self.ledger.settle_request(request['id'], state='succeeded', usage=response_usage(raw, 'glm'),
                                      response={'result': result, 'provider_response': raw})
            raise KeyboardInterrupt('CONTROLLED crash after successful settlement before job finish')

    def original(self, *, category=False, human=False):
        gateway = None
        if human:
            class FailedVisual(self.case.case.PassingProtocolGateway):
                def transform(self, job, result):
                    if job['kind'] == 'ai-visual': next(iter(result['checks'].values()))['status'] = 'FAIL'
                    return result
            gateway = FailedVisual
        self.case.parent(gateway, enforced_category=category)
        if human:
            raw_path = self.case.case.fixture.reviewed(); raw = lane._read(raw_path); raw.pop('delivery_document_review', None)
            for row in raw['records']: row['reviewer'] = {'kind': 'human', 'name': 'CONTROLLED TEST; NOT ACTUAL HUMAN'}
            raw_path.write_text(json.dumps(raw))
            lane.pipeline.import_human(self.case.parent_receipt, [raw_path], self.root / 'human')
            self.case.parent_status = self.root / 'human/status.json'
        config = deepcopy(self.case.old.config)
        config['run_id'] = 'CONTROLLED-original-document-authentication-rejection'
        config['budget'].update(max_model_requests=1, max_job_attempts=1, max_concurrent_jobs=1)
        self.failed = BatchLedger(self.root / 'failed-document.sqlite3', config, initialize=True)
        self.prepared = lane.prepare(self.failed, self.case.parent_receipt, self.case.parent_status, self.root / 'failed-prepared')
        with patch.object(lane, 'ModelGateway', self.RejectedAuthentication), patch('urllib.request.build_opener', side_effect=AssertionError('No network')):
            lane.run(self.prepared['receipt'], self.root / 'failed-status')
        _, _, _, request = recovery._original(self.prepared['receipt'])
        self.authority = self.root / 'authority.json'
        lane._write(self.authority, {'schema_version': recovery.AUTH_VERSION,
            'original_document_receipt': lane._ref(self.prepared['receipt']), 'original_request_id': request['id'],
            'maximum_additional_requests': 1, 'explicit_authentication_recovery': True,
            'authorization_source': 'CONTROLLED session authority; not an actual user instruction',
            'reason': 'CONTROLLED supplied credential same-key availability recovery; no claim of credential change'})
        self.retry_config = deepcopy(config); self.retry_config['run_id'] = 'CONTROLLED-one-explicit-document-auth-recovery'
        self.retry = BatchLedger(self.root / 'retry.sqlite3', self.retry_config, initialize=True)

    def prepare(self, output='recovery-prepared'):
        return recovery.prepare(self.retry, self.prepared['receipt'], self.authority, self.root / output)

    def authentication(self, *, state='succeeded', different_endpoint=False, name='diagnostic'):
        config = deepcopy(self.retry_config); config['run_id'] = 'CONTROLLED-authentication-' + name
        if different_endpoint: config['model']['endpoint'] = 'https://wrong-service.invalid/chat'
        config_path = self.root / (name + '-config.json'); lane._write(config_path, config)
        ledger = BatchLedger(self.root / (name + '.sqlite3'), config, initialize=True)
        jid = ledger.enqueue('authentication-diagnostic', {'CONTROLLED_FIXTURE': True}); job = ledger.claim('authentication-diagnostic', job_id=jid)
        result = {'authenticated': True}; schema = {'type': 'object', 'properties': {'authenticated': {'const': True}}, 'required': ['authenticated'], 'additionalProperties': False}
        request = ledger.reserve_request(job, 'authentication-diagnostic:CONTROLLED', 0,
            request_json={'system': 'CONTROLLED', 'text': 'CONTROLLED', 'schema': schema, 'images': [],
                          'provider': config['model']['provider'], 'model': config['model']['model']})
        if state == 'succeeded':
            raw = {'id': 'CONTROLLED-auth-provider-response', 'model': config['model']['model'],
                'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'prompt_tokens_details': {'cached_tokens': 0}}}
            ledger.settle_request(request['id'], state='succeeded', usage=response_usage(raw, 'glm'),
                                  response={'result': result, 'provider_response': raw})
            ledger.finish(job, result=result)
        else:
            ledger.settle_request(request['id'], state='unknown', error='HTTPError:401', response={'provider_error': {'http_status': 401}})
            ledger.finish(job, 'review_required', error='CONTROLLED')
        proof = self.root / (name + '-evidence.json')
        lane._write(proof, {'schema_version': recovery.PROOF_VERSION, 'ledger': str(ledger.path),
                           'config': lane._ref(config_path), 'request_id': request['id']})
        return proof, ledger

    def run_recovery(self, prepared, proof, output='recovery-run', gateway=None):
        with patch.object(lane, 'ModelGateway', gateway or self.case.case.PassingProtocolGateway), \
                patch('urllib.request.build_opener', side_effect=AssertionError('No actual network')):
            return recovery.run(prepared['receipt'], proof, self.root / output)

    def test_prepare_is_offline_idempotent_and_cannot_supply_raw_lane_before_authentication(self):
        self.original(); prepared = self.prepare(); receipt = recovery.verify(prepared['receipt'])
        again = self.prepare('another-output')
        self.assertTrue(again['reused']); self.assertEqual(prepared['receipt'], again['receipt'])
        self.assertEqual(self.retry.summary()['model_requests'], 0)
        self.assertFalse(Path(receipt['raw_lane_receipt']).exists())
        with self.assertRaisesRegex(ValueError, 'authentication gate'):
            recovery.status(prepared['receipt'], self.root / 'unactivated-status')
        with self.assertRaises(ValueError): lane.verify(prepared['receipt'])

    def test_later_persisted_auth_success_allows_exactly_one_retry_and_preserves_human_and_unknown_fee(self):
        self.original(human=True); prepared = self.prepare(); proof, _ = self.authentication()
        original = self.failed.get(self.prepared['job_id']); original_usage = self.failed.summary()['uncertain_reserved_cost_micros']
        result = self.run_recovery(prepared, proof)
        status = lane._read(result['status']); accounting = lane._read(result['accounting'])
        self.assertEqual(status['text_consistency']['status'], 'PASS'); self.assertEqual(status['actual_human_reviewed'], 1)
        self.assertEqual(status['human_document_pending_count'], 0)
        report = lane._read(status['report']['path']); self.assertEqual(report['semantic_sampling']['rows'][0]['ai_status'], 'FAIL')
        self.assertEqual(report['semantic_sampling']['rows'][0]['status'], 'HUMAN_PASS')
        self.assertEqual(self.failed.get(self.prepared['job_id']), original)
        self.assertEqual(accounting['uncertain_reserved_cost_micros'], original_usage)
        self.assertFalse(accounting['original_unknown_is_zero_cost'])
        self.assertEqual(accounting['scopes']['original_rejected_document_increment']['request_states'], {'unknown': 1})
        self.assertEqual(self.retry.get(self.prepared['job_id'])['payload'], original['payload'])
        self.assertEqual(accounting['model_requests'], 5)  # parent2 + rejected1 + retry1 + diagnostic1
        self.run_recovery(prepared, proof, 'replayed')
        self.assertEqual(self.retry.summary()['model_requests'], 1)
        final = recovery.finalize(prepared['receipt'], result['status'], self.root / 'controlled-final')
        self.assertTrue(final['release_ready']); self.assertEqual(final['customer_acceptance'], 'UNKNOWN')

    def test_missing_failed_stale_or_wrong_service_diagnostic_never_dispatches(self):
        self.original(); prepared = self.prepare(); proof, diagnostic = self.authentication(state='unknown')
        with self.assertRaisesRegex(ValueError, 'Successful later authentication'):
            self.run_recovery(prepared, proof)
        self.assertEqual(self.retry.summary()['model_requests'], 0)
        self.assertFalse(Path(recovery.verify(prepared['receipt'])['raw_lane_receipt']).exists())

    def test_wrong_provider_and_forged_plain_pass_are_rejected(self):
        self.original(); prepared = self.prepare(); proof, _ = self.authentication(different_endpoint=True)
        with self.assertRaisesRegex(ValueError, 'same real provider'):
            self.run_recovery(prepared, proof)
        fake = self.root / 'plain-PASS.json'; lane._write(fake, {'status': 'PASS', 'authenticated': True})
        with self.assertRaisesRegex(ValueError, 'persisted authentication'):
            self.run_recovery(prepared, fake, 'also-failed')
        self.assertEqual(self.retry.summary()['model_requests'], 0)

    def test_boolean_authority_and_wrong_returned_model_are_rejected(self):
        self.original()
        authority = lane._read(self.authority); authority['maximum_additional_requests'] = True
        bad = self.root / 'boolean-authority.json'; lane._write(bad, authority)
        with self.assertRaisesRegex(ValueError, 'one-request recovery authority'):
            recovery.prepare(self.retry, self.prepared['receipt'], bad, self.root / 'boolean-prepare')
        prepared = self.prepare(); proof, diagnostic = self.authentication()
        with diagnostic.transaction() as con:
            row = con.execute('SELECT id,response FROM model_requests').fetchone(); response = json.loads(row['response'])
            response['provider_response']['model'] = 'not-the-required-model'
            con.execute('UPDATE model_requests SET response=? WHERE id=?', (json.dumps(response), row['id']))
        with self.assertRaisesRegex(ValueError, 'Successful later authentication'):
            self.run_recovery(prepared, proof)
        self.assertEqual(self.retry.summary()['model_requests'], 0)

    def test_expired_auth_success_or_inconsistent_usage_cannot_authorize_request(self):
        self.original(); prepared = self.prepare(); proof, diagnostic = self.authentication()
        with diagnostic.transaction() as con:
            con.execute('UPDATE model_requests SET finished=?', (time.time() - 3700,))
        with self.assertRaisesRegex(ValueError, 'Successful later authentication'):
            self.run_recovery(prepared, proof)
        with diagnostic.transaction() as con:
            con.execute('UPDATE model_requests SET finished=?,usage=?', (time.time(), json.dumps({'input_tokens': 999})))
        with self.assertRaisesRegex(ValueError, 'usage disagree'):
            self.run_recovery(prepared, proof, 'bad-usage')
        self.assertEqual(self.retry.summary()['model_requests'], 0)

    def test_second_scope_or_authority_change_cannot_buy_another_increment(self):
        self.original(); self.prepare()
        other = BatchLedger(self.root / 'another-retry.sqlite3', self.retry_config, initialize=True)
        with self.assertRaisesRegex(ValueError, 'one recovery increment'):
            recovery.prepare(other, self.prepared['receipt'], self.authority, self.root / 'other')
        authority = lane._read(self.authority); authority['reason'] = 'changed'; self.authority.write_text(json.dumps(authority))
        with self.assertRaisesRegex(ValueError, 'one recovery increment'):
            self.prepare('changed-authority')
        self.assertEqual(other.summary()['model_requests'], 0)

    def test_copying_or_extending_original_receipt_cannot_buy_second_recovery(self):
        self.original(); self.prepare()
        original = lane._read(self.prepared['receipt']); original['unrelated_extra'] = 'not a different failed request'
        original['receipt_sha256'] = lane._digest({key: item for key, item in original.items() if key != 'receipt_sha256'})
        copied = self.root / 'relocated-original-with-extra.json'; lane._write(copied, original)
        lane.verify(copied)
        auth = lane._read(self.authority); auth['original_document_receipt'] = lane._ref(copied)
        copied_auth = self.root / 'relocated-authority.json'; lane._write(copied_auth, auth)
        other = BatchLedger(self.root / 'copied-second-scope.sqlite3', self.retry_config, initialize=True)
        with self.assertRaisesRegex(ValueError, 'one recovery increment'):
            recovery.prepare(other, copied, copied_auth, self.root / 'copied-second-output')
        self.assertEqual(other.summary()['model_requests'], 0)

    def test_prepare_crashes_before_link_or_before_enqueue_are_recoverable_without_new_scope(self):
        self.original()
        original_event = BatchLedger.event
        def interrupted_event(ledger, con, kind, detail):
            if kind == recovery.EVENT: raise RuntimeError('CONTROLLED crash after control publication')
            return original_event(ledger, con, kind, detail)
        with patch.object(BatchLedger, 'event', interrupted_event):
            with self.assertRaisesRegex(RuntimeError, 'CONTROLLED crash'):
                self.prepare()
        prepared = self.prepare(); recovery.verify(prepared['receipt'])
        self.assertEqual(self.retry.summary()['model_requests'], 0)

    def test_prepare_crash_after_link_before_enqueue_recovers_the_bound_job(self):
        self.original()
        original_enqueue = BatchLedger.enqueue
        def interrupted_enqueue(ledger, kind, payload):
            if ledger.path == self.retry.path: raise RuntimeError('CONTROLLED crash before enqueue')
            return original_enqueue(ledger, kind, payload)
        with patch.object(BatchLedger, 'enqueue', interrupted_enqueue):
            with self.assertRaisesRegex(RuntimeError, 'CONTROLLED crash'):
                self.prepare()
        prepared = self.prepare(); recovery.verify(prepared['receipt'])
        self.assertTrue(prepared['reused']); self.assertEqual(self.retry.summary()['model_requests'], 0)

    def test_activated_queued_scope_accepts_fresh_diagnostic_without_replacing_old_auth_evidence(self):
        self.original(); prepared = self.prepare(); proof, diagnostic = self.authentication()
        recovery._activate(prepared['receipt'], proof)
        control = recovery.verify(prepared['receipt']); raw = Path(control['raw_lane_receipt']).read_bytes()
        original_clock = recovery.time.time
        future = original_clock() + 3700
        with patch.object(recovery.time, 'time', return_value=future):
            with self.assertRaisesRegex(ValueError, 'Successful later authentication'):
                self.run_recovery(prepared, proof)
        fresh_proof, _ = self.authentication(name='fresh-diagnostic')
        result = self.run_recovery(prepared, fresh_proof)
        self.assertEqual(Path(control['raw_lane_receipt']).read_bytes(), raw)
        self.assertEqual(len(recovery._authentication_events(control)), 2)
        accounting = lane._read(result['accounting'])
        self.assertEqual(accounting['model_requests'], 6)  # parent2 + rejected1 + retry1 + two diagnostics

    def test_status_keeps_old_auth_valid_but_rejects_mutated_auth_sqlite_result(self):
        self.original(); prepared = self.prepare(); proof, diagnostic = self.authentication()
        self.run_recovery(prepared, proof)
        original_clock = recovery.time.time
        with patch.object(recovery.time, 'time', return_value=original_clock() + 3700):
            result = recovery.status(prepared['receipt'], self.root / 'later-status')
        self.assertEqual(lane._read(result['status'])['text_consistency']['status'], 'PASS')
        with diagnostic.transaction() as con:
            con.execute('UPDATE model_requests SET usage=?', (json.dumps({'input_tokens': 999}),))
        with self.assertRaisesRegex(ValueError, 'usage disagree'):
            recovery.status(prepared['receipt'], self.root / 'tampered-auth-status')

    def test_retry_unknown_or_ai_fail_remains_terminal_and_never_creates_document_humans(self):
        self.original(); prepared = self.prepare(); proof, _ = self.authentication()
        result = self.run_recovery(prepared, proof, gateway=self.RejectedAuthentication)
        state = lane._read(result['status'])
        self.assertEqual(state['document_review_status'], 'AI_REVIEW_REQUIRED')
        self.assertEqual(state['human_document_pending_count'], 0)
        self.run_recovery(prepared, proof, 'unknown-replayed')
        self.assertEqual(self.retry.summary()['model_requests'], 1)
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            recovery.finalize(prepared['receipt'], result['status'], self.root / 'blocked-final')

    def test_paid_known_response_recovers_after_finish_interruption_without_new_requests_or_attempt_reset(self):
        self.original(); prepared = self.prepare(); proof, _ = self.authentication()
        with self.assertRaisesRegex(KeyboardInterrupt, 'CONTROLLED crash'):
            self.run_recovery(prepared, proof, gateway=self.PersistThenCrash)
        job = self.retry.get(self.prepared['job_id']); self.assertEqual(job['state'], 'running')
        self.assertEqual(job['attempts'], 1); owner = job['owner']
        active = recovery.status(prepared['receipt'], self.root / 'active-lease-status')
        self.assertEqual(lane._read(active['status'])['text_consistency']['status'], 'REVIEW_REQUIRED')
        self.assertEqual(self.retry.get(job['id'])['owner'], owner)
        with self.retry.transaction() as con: con.execute('UPDATE jobs SET lease=? WHERE id=?', (time.time() - 1, job['id']))
        with patch.object(lane, 'ModelGateway', side_effect=AssertionError('Known response must not call model')):
            healed = recovery.status(prepared['receipt'], self.root / 'healed-known-status')
        self.assertEqual(lane._read(healed['status'])['text_consistency']['status'], 'PASS')
        self.assertEqual(self.retry.get(job['id'])['attempts'], 1)
        self.assertEqual(self.retry.summary()['model_requests'], 1)
        with self.retry.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM batch_events WHERE event='document_auth_recovery_known_result_reconciled'").fetchone()[0], 1)
        replay = self.run_recovery(prepared, self.root / 'nonexistent-proof-not-needed-for-known-result.json', 'known-replayed')
        self.assertEqual(lane._read(replay['status'])['text_consistency']['status'], 'PASS')
        self.assertEqual(self.retry.summary()['model_requests'], 1)

    def test_corrupt_persisted_known_response_is_not_reconstructed(self):
        self.original(); prepared = self.prepare(); proof, _ = self.authentication()
        with self.assertRaises(KeyboardInterrupt): self.run_recovery(prepared, proof, gateway=self.PersistThenCrash)
        with self.retry.transaction() as con:
            con.execute('UPDATE jobs SET lease=?', (time.time() - 1,))
            row = con.execute('SELECT id,request_json FROM model_requests').fetchone(); request = json.loads(row['request_json'])
            request['text'] = 'CONTROLLED tampered request'
            con.execute('UPDATE model_requests SET request_json=? WHERE id=?', (json.dumps(request), row['id']))
        with self.assertRaisesRegex(ValueError, 'complete matching successful request'):
            recovery.status(prepared['receipt'], self.root / 'corrupt-known-status')
        self.assertIsNone(self.retry.get(self.prepared['job_id'])['result'])
        self.assertEqual(self.retry.summary()['model_requests'], 1)

    def test_successful_text_still_cannot_clear_formal_category_gate(self):
        self.original(category=True); prepared = self.prepare(); proof, _ = self.authentication()
        result = self.run_recovery(prepared, proof); state = lane._read(result['status'])
        self.assertEqual(state['text_consistency']['status'], 'PASS'); self.assertEqual(state['payload_status'], 'FAIL')
        with self.assertRaisesRegex(ValueError, 'distribution'):
            recovery.finalize(prepared['receipt'], result['status'], self.root / 'category-blocked')

    def test_control_receipt_copy_source_drift_and_parallel_gate_are_rejected(self):
        self.original(); prepared = self.prepare(); proof, _ = self.authentication()
        copied = self.root / 'copied-control.json'; copied.write_text(Path(prepared['receipt']).read_text())
        with self.assertRaisesRegex(ValueError, 'not issued'):
            recovery.verify(copied)
        actual = recovery._implementation()
        with patch.object(recovery, '_implementation', return_value={**actual, 'CONTROLLED drift': '0' * 64}):
            with self.assertRaisesRegex(ValueError, 'implementation changed'):
                recovery.verify(prepared['receipt'])
        with recovery._gate(prepared['receipt']):
            with self.assertRaisesRegex(ValueError, 'Another operation'):
                self.run_recovery(prepared, proof)
        self.assertEqual(self.retry.summary()['model_requests'], 0)

    def test_same_cli_initialization_flag_preserves_clock_and_symlink_lock_is_rejected(self):
        self.original(); config = self.root / 'retry-config.json'; lane._write(config, self.retry_config)
        with self.retry.connect() as con: started = con.execute('SELECT started FROM batch_meta').fetchone()[0]
        arguments = ['prepare', '--original-receipt', self.prepared['receipt'], '--authorization', str(self.authority),
            '--ledger', str(self.retry.path), '--config', str(config), '--initialize-ledger', '--output', str(self.root / 'cli-prepared')]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(recovery.main(arguments), 0); self.assertEqual(recovery.main(arguments), 0)
        with self.retry.connect() as con: self.assertEqual(con.execute('SELECT started FROM batch_meta').fetchone()[0], started)
        control = self.root / 'cli-prepared/document-auth-recovery-receipt.json'
        sentinel = self.root / 'sentinel.txt'; sentinel.write_text('UNCHANGED')
        control.with_suffix('.dispatch.lock').symlink_to(sentinel)
        proof, _ = self.authentication()
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.run_recovery({'receipt': str(control)}, proof)
        self.assertEqual(sentinel.read_text(), 'UNCHANGED'); self.assertEqual(self.retry.summary()['model_requests'], 0)


if __name__ == '__main__': unittest.main()
