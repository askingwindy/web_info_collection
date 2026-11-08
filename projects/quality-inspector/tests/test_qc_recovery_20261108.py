"""Bounded visual-evidence recovery and UNKNOWN reconciliation (2026-11-08).

All fixtures are SYNTHETIC; they exercise protocol mechanics only and never
claim actual AI review. The r01-shaped reply mirrors the real invalid class
(complete step observations, PASS checks without evidence_steps).
"""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from make_fixture import fixture as make_candidate
from webcollect.batch_core import BatchLedger
from quality_inspector import ai_worker
from quality_inspector import qc_recovery
from quality_inspector.ai_worker import snapshot
from quality_inspector.contract import fingerprint
from quality_inspector.semantic import rule_ids

LEDGER_CONFIG = {
    'schema_version': 'webcollect-batch-config-1', 'mode': 'synthetic', 'run_id': 'qc-recovery-tests',
    'budget': {'max_concurrent_jobs': 1, 'min_domain_interval_seconds': 1, 'lease_seconds': 300,
               'min_model_interval_seconds': 1, 'currency': 'CNY'},
    'model': {'provider': 'synthetic', 'model': 'synthetic-qc-vision', 'endpoint': 'synthetic://local',
              'api_key_env': 'NONE', 'timeout_seconds': 30, 'reserve_input_tokens': 100000,
              'max_completion_tokens': 2000, 'max_images': 24, 'reserve_cost_micros': 300000,
              'rates': {'version': 'synthetic-test', 'source': 'offline test', 'input': 0,
                        'cached_input': 0, 'output': 0}}}


def reply_without_evidence(ids):
    """The r01 invalid class: full observations, decisions lack evidence_steps."""
    return {'step_observations': [{'step_id': sid, 'note': f'帧{sid}前后状态真实，动作与结果一致'} for sid in ids],
            'checks': {
                'visual_alignment': {'status': 'PASS', 'note': '相邻帧内容续接，声称的可见内容逐一在帧2至帧6中可核验'},
                'terminal_semantics': {'status': 'PASS', 'note': '第6步收尾声称的最终文字在帧6中逐字可见'},
                'language': {'status': 'PASS', 'note': '页面为简体中文，控件语言一致，未见错配证据'},
                'privacy': {'status': 'PASS', 'note': '六帧均未见用户名或任何隐私信息'}}}


def fully_determinable_reply(ids):
    reply = reply_without_evidence(ids)
    reply['checks']['language']['note'] = '帧1至帧6的页面与控件语言一致，未见错配证据'
    return reply


class RecoveryHarness:
    def __init__(self, root, reply):
        self.root = Path(root)
        self.sample = Path(make_candidate(self.root / 'candidate'))
        self.ledger = BatchLedger(self.root / 'ledger.sqlite3', LEDGER_CONFIG, initialize=True)
        identity = {'candidate': snapshot(self.sample), 'model': LEDGER_CONFIG['model'],
                    'prompt_version': ai_worker.PROMPT_VERSION, 'policy_version': ai_worker.POLICY_VERSION,
                    'contract_sha256': fingerprint()[1], 'mode': 'synthetic',
                    'semantic_rule_ids': rule_ids()}
        self.job_id = self.ledger.enqueue('ai-visual', identity)
        outcome = ai_worker.run(self.ledger, controlled={0: reply})
        self.worker = outcome
        self.config_path = self.root / 'config.json'
        self.config_path.write_text(json.dumps(LEDGER_CONFIG, ensure_ascii=False))

    def job(self):
        return self.ledger.get(self.job_id)

    def requests(self, base=None):
        with self.ledger.connect() as con:
            rows = [dict(row) for row in con.execute(
                'SELECT id,purpose,state,response,error FROM model_requests WHERE job_id=? ORDER BY started',
                (self.job_id,))]
        return rows if base is None else [row for row in rows if row['purpose'].startswith(base)]

    def events(self, name):
        with self.ledger.connect() as con:
            return [json.loads(row[0]) for row in con.execute(
                'SELECT detail FROM batch_events WHERE event=? ORDER BY seq', (name,))]


class ReferenceExtractionTests(unittest.TestCase):
    def test_determinable_alias_patterns(self):
        allowed = [1, 2, 3, 4, 5, 6]
        self.assertEqual(extract('在帧2至帧6中核验', allowed)['steps'], [2, 3, 4, 5, 6])
        self.assertEqual(extract('帧6中逐字可见', allowed)['steps'], [6])
        self.assertEqual(extract('第6步complete复用终帧', allowed)['steps'], [6])
        self.assertEqual(extract('六帧均未见隐私信息', allowed)['steps'], [1, 2, 3, 4, 5, 6])
        combined = extract('帧2至帧6续接且第6步可见，六帧均无遮挡', allowed)
        self.assertTrue(combined['determinable'])
        self.assertEqual(combined['steps'], [1, 2, 3, 4, 5, 6])
        self.assertEqual([match['rule'] for match in combined['matches']],
                         ['frame-range', 'step', 'whole-set-count'])

    def test_indeterminable_references_are_rejected(self):
        allowed = [1, 2, 3, 4, 5, 6]
        self.assertFalse(extract('页面为简体中文，未见错配证据', allowed)['determinable'])
        self.assertFalse(extract('两帧之间有变化', allowed)['determinable'])       # count != supplied set
        self.assertFalse(extract('帧9显示了其他页面', allowed)['determinable'])     # out of bounds
        self.assertFalse(extract('帧4至帧9连续', allowed)['determinable'])          # range leaves the set
        self.assertFalse(extract('第8步执行了确认', allowed)['determinable'])

    def test_partial_noncontiguous_sets_never_invent_ids(self):
        allowed = [2, 4, 9]
        self.assertEqual(extract('帧4与帧9可核验', allowed)['steps'], [4, 9])
        self.assertFalse(extract('帧2至帧4连续', allowed)['determinable'])  # 3 was never supplied
        self.assertFalse(extract('三帧均检查过', allowed)['determinable'])  # not the contiguous whole set

    def test_non_frame_numerals_are_not_citations(self):
        allowed = [1, 2, 3, 4, 5, 6]
        self.assertFalse(extract('参考文献第3条与列表1-7一致', allowed)['determinable'])


def extract(note, allowed):
    return qc_recovery.extract_evidence_references(note, allowed)


class VisualRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def harness(self, reply):
        return RecoveryHarness(self.root / f'h{len(list(self.root.iterdir()))}', reply)

    def test_complete_legal_reply_needs_no_recovery(self):
        ids = [1, 2, 3, 4, 5, 6]
        legal = fully_determinable_reply(ids)
        for name in legal['checks']:
            legal['checks'][name]['evidence_steps'] = ids
        harness = self.harness(legal)
        self.assertEqual(harness.job()['state'], 'done')
        result = harness.job()['result']
        self.assertNotIn('evidence_recovery', result)
        for name, check in result['checks'].items():
            self.assertEqual(check['evidence_steps'], ids)

    def test_missing_evidence_normalizes_only_determinable_checks(self):
        harness = self.harness(reply_without_evidence([1, 2, 3, 4, 5, 6]))
        self.assertEqual(harness.job()['state'], 'review_required')
        original = harness.requests('visual-part-0:')[0]
        plan = qc_recovery.visual_recovery_plan(harness.ledger, harness.job())
        self.assertEqual(plan['indeterminate_checks'], ['language'])
        receipt = qc_recovery.recover_visual(harness.config_path, harness.ledger.path, harness.job_id,
                                              output=self.root / 'plan.json')
        self.assertEqual(receipt['status'], 'correction_required')
        self.assertEqual(receipt['model_requests_dispatched'], 0)
        self.assertTrue(receipt['synthetic_result'])
        # No authorization: the job and its original receipt stay untouched.
        self.assertEqual(harness.job()['state'], 'review_required')
        self.assertEqual(harness.requests('visual-part-0:')[0]['response'], original['response'])
        self.assertEqual(harness.requests(), harness.requests('visual-part-0:'))
        self.assertEqual(sorted(receipt['normalizable_checks']['0']),
                         ['privacy', 'terminal_semantics', 'visual_alignment'])

    def test_correction_is_single_bounded_and_audited(self):
        ids = [1, 2, 3, 4, 5, 6]
        harness = self.harness(reply_without_evidence(ids))
        before = harness.requests('visual-part-0:')[0]
        correction = {'checks': {'language': {'status': 'PASS',
            'note': 'SYNTHETIC restate: 帧1至帧6控件均为简体中文',
            'evidence_steps': ids}}}
        receipt = qc_recovery.recover_visual(harness.config_path, harness.ledger.path, harness.job_id,
                                             allow_correction=True, controlled={'0': correction},
                                             output=self.root / 'recovered.json')
        self.assertEqual(receipt['status'], 'done')
        self.assertEqual(receipt['model_requests_dispatched'], 1)
        job = harness.job()
        self.assertEqual(job['state'], 'done')
        merged = job['result']
        self.assertEqual(merged['checks']['visual_alignment']['evidence_steps'], [2, 3, 4, 5, 6])
        self.assertEqual(merged['checks']['terminal_semantics']['evidence_steps'], [6])
        self.assertEqual(merged['checks']['privacy']['evidence_steps'], ids)
        self.assertEqual(merged['checks']['language']['evidence_steps'], ids)
        self.assertIn('第6步', merged['checks']['terminal_semantics']['note'])  # original note retained
        audit = merged['evidence_recovery']
        self.assertEqual(audit['protocol'], qc_recovery.RECOVERY_PROTOCOL)
        self.assertEqual(audit['original_invalid_retained'][0]['request_id'], before['id'])
        self.assertEqual(audit['original_invalid_retained'][0]['state'], 'invalid_response')
        correction_rows = harness.requests('visual-part-0-evidence-recovery:')
        self.assertEqual(len(correction_rows), 1)
        self.assertEqual(correction_rows[0]['state'], 'succeeded')
        # The original invalid receipt is preserved byte-for-byte.
        after = harness.requests('visual-part-0:')[0]
        self.assertEqual(after['state'], 'invalid_response')
        self.assertEqual(after['response'], before['response'])
        self.assertTrue(harness.events('qc_visual_evidence_recovered'))
        self.assertTrue(harness.events('semantic_result_bound'))
        self.assertTrue(receipt['synthetic_result'])

    def test_correction_refuses_a_second_bounded_attempt(self):
        ids = [1, 2, 3, 4, 5, 6]
        harness = self.harness(reply_without_evidence(ids))
        invalid_correction = {'checks': {'language': {'status': 'PASS',
            'note': 'SYNTHETIC out-of-bounds citation', 'evidence_steps': [9]}}}
        with self.assertRaises(Exception):
            qc_recovery.recover_visual(harness.config_path, harness.ledger.path, harness.job_id,
                                       allow_correction=True, controlled={'0': invalid_correction},
                                       output=self.root / 'r1.json')
        self.assertEqual(harness.job()['state'], 'review_required')
        rows = harness.requests('visual-part-0-evidence-recovery:')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['state'], 'invalid_response')
        # The failed correction is retained: a second authorized attempt never re-dispatches.
        with self.assertRaises(Exception):
            qc_recovery.recover_visual(harness.config_path, harness.ledger.path, harness.job_id,
                                       allow_correction=True,
                                       controlled={'0': {'checks': {'language': {
                                           'status': 'PASS', 'note': 'SYNTHETIC later fix',
                                           'evidence_steps': ids}}}},
                                       output=self.root / 'r2.json')
        self.assertEqual(len(harness.requests('visual-part-0-evidence-recovery:')), 1)

    def test_fully_determinable_reply_recovers_without_any_dispatch(self):
        harness = self.harness(fully_determinable_reply([1, 2, 3, 4, 5, 6]))
        receipt = qc_recovery.recover_visual(harness.config_path, harness.ledger.path, harness.job_id,
                                             output=self.root / 'normalized.json')
        self.assertEqual(receipt['status'], 'done')
        self.assertEqual(receipt['model_requests_dispatched'], 0)
        self.assertEqual(harness.job()['state'], 'done')
        self.assertEqual(harness.job()['result']['checks']['language']['evidence_steps'],
                         [1, 2, 3, 4, 5, 6])
        self.assertEqual(len(harness.requests()), 1)  # only the original invalid row

    def test_invalid_status_or_damaged_reply_is_unrecoverable(self):
        ids = [1, 2, 3, 4, 5, 6]
        damaged = reply_without_evidence(ids)
        damaged['checks']['language']['status'] = 'MAYBE'
        harness = self.harness(damaged)
        receipt = qc_recovery.recover_visual(harness.config_path, harness.ledger.path, harness.job_id,
                                             output=self.root / 'stopped.json')
        self.assertEqual(receipt['status'], 'stopped')
        self.assertEqual(receipt['unrecoverable_parts'], [0])
        self.assertEqual(harness.job()['state'], 'review_required')

    def test_wrong_duplicate_or_out_of_bounds_citations_need_the_model(self):
        ids = [1, 2, 3, 4, 5, 6]
        reply = reply_without_evidence(ids)
        reply['checks']['language'] = {'status': 'PASS', 'note': '帧9控件语言一致'}  # out of bounds
        harness = self.harness(reply)
        plan = qc_recovery.visual_recovery_plan(harness.ledger, harness.job())
        self.assertEqual(plan['indeterminate_checks'], ['language'])
        self.assertNotIn('language', plan['parts'][0]['normalization'])

    def test_candidate_bytes_changed_blocks_recovery(self):
        harness = self.harness(reply_without_evidence([1, 2, 3, 4, 5, 6]))
        annotation = self._annotation_path(harness)
        original = json.loads(annotation.read_text())
        original['final_result'] = 'changed after queue preparation'
        annotation.write_text(json.dumps(original, ensure_ascii=False))
        with self.assertRaises(ValueError):
            qc_recovery.recover_visual(harness.config_path, harness.ledger.path, harness.job_id,
                                       output=self.root / 'blocked.json')
        self.assertEqual(harness.job()['state'], 'review_required')

    def test_rule_version_binding_rejects_changed_semantics(self):
        harness = self.harness(reply_without_evidence([1, 2, 3, 4, 5, 6]))
        tampered = dict(rule_ids())
        tampered['language'] = '0' * 64
        with patch.object(qc_recovery, 'rule_ids', lambda: tampered):
            with self.assertRaises(ValueError):
                qc_recovery.recover_visual(harness.config_path, harness.ledger.path, harness.job_id,
                                           output=self.root / 'rules.json')
        self.assertEqual(harness.job()['state'], 'review_required')

    def test_payload_identity_tampering_is_rejected(self):
        harness = self.harness(reply_without_evidence([1, 2, 3, 4, 5, 6]))
        with harness.ledger.transaction() as con:
            payload = json.loads(con.execute('SELECT payload FROM jobs WHERE id=?', (harness.job_id,)).fetchone()[0])
            payload['candidate']['sample_id'] = 'SOMEONE_ELSE'
            con.execute('UPDATE jobs SET payload=? WHERE id=?', (json.dumps(payload), harness.job_id))
        with self.assertRaises(ValueError):
            qc_recovery.recover_visual(harness.config_path, harness.ledger.path, harness.job_id,
                                       output=self.root / 'identity.json')

    def _annotation_path(self, harness):
        return Path(harness.job()['payload']['candidate']['path']) / 'annotation.json'


class PipelineIntegrationTests(unittest.TestCase):
    """prepare → invalid reply → bounded recovery → worker report (SYNTHETIC)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.sample = Path(make_candidate(self.root / 'candidate'))
        self.dataset = self.sample.parents[1]  # .../candidate/batch
        self.ledger = BatchLedger(self.root / 'ledger.sqlite3', LEDGER_CONFIG, initialize=True)
        self.config_path = self.root / 'config.json'
        self.config_path.write_text(json.dumps(LEDGER_CONFIG, ensure_ascii=False))

    def test_recovered_visual_job_flows_through_the_worker_report(self):
        queue = ai_worker.prepare(self.ledger, self.dataset, self.root / 'queue-out')
        queue_path = queue['queue_file']
        outcome = ai_worker.run(self.ledger, controlled={0: reply_without_evidence([1, 2, 3, 4, 5, 6])})
        self.assertTrue(outcome['outcomes'])
        with self.ledger.connect() as con:
            states = {row[0]: row[1] for row in con.execute('SELECT kind,state FROM jobs')}
        self.assertEqual(states['ai-visual'], 'review_required')
        self.assertEqual(states['ai-difference'], 'done')  # honest empty-set result, no neighbors
        receipt = qc_recovery.recover_visual(self.config_path, self.ledger.path,
                                             self._job_of_kind('ai-visual'),
                                             allow_correction=True,
                                             controlled={'0': {'checks': {'language': {
                                                 'status': 'PASS',
                                                 'note': 'SYNTHETIC restate: 帧1至帧6控件均为简体中文',
                                                 'evidence_steps': [1, 2, 3, 4, 5, 6]}}}},
                                             output=self.root / 'recovery-receipt.json')
        self.assertEqual(receipt['status'], 'done')
        summary = ai_worker.report(self.ledger, queue_path, self.root / 'report-out')
        self.assertEqual(summary['raw_model_records'], 1)
        exported = json.loads(Path(summary['review_file']).read_text())
        self.assertEqual(exported['schema_version'], 'webcollect-synthetic-review-test-1')
        record = exported['records'][0]
        self.assertIn('evidence_recovery', record)
        self.assertEqual(record['evidence_recovery']['protocol'], qc_recovery.RECOVERY_PROTOCOL)
        self.assertEqual(record['evidence_recovery']['original_invalid_retained'][0]['state'],
                         'invalid_response')
        for name in ('visual_alignment', 'terminal_semantics', 'language', 'privacy'):
            self.assertTrue(record['checks'][name]['evidence_steps'])
        # The empty-set difference stays the honest NOT_APPLICABLE result; no PASS invented.
        self.assertEqual(record['checks']['substantive_difference']['status'], 'REVIEW_REQUIRED')
        provenance = record['provenance']
        self.assertEqual(len(provenance['request_accounting']['requests']), 2)
        self.assertEqual(summary['independent_qc_status'], 'NOT_RUN')

    def _job_of_kind(self, kind):
        with self.ledger.connect() as con:
            return con.execute('SELECT id FROM jobs WHERE kind=?', (kind,)).fetchone()[0]


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.ledger = BatchLedger(self.root / 'ledger.sqlite3', LEDGER_CONFIG, initialize=True)
        self.job_id = self.ledger.enqueue('ai-documents', {'dataset': str(self.root), 'mode': 'synthetic',
                                                           'documents': {}, 'supplementary_evidence': {}})
        self.config_path = self.root / 'config.json'
        self.config_path.write_text(json.dumps(LEDGER_CONFIG, ensure_ascii=False))

    def insert_request(self, request_id, state, *, purpose='delivery-documents:abc', request_json=None,
                       response=None, error='TimeoutError', attempt=0):
        with self.ledger.transaction() as con:
            con.execute('INSERT INTO model_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (request_id, self.job_id, purpose, attempt, state, 1000, 300000, 1.0, 2.0, None, None,
                         response or json.dumps({'transport_error': {'reason_type': 'TimeoutError'}}),
                         error, json.dumps(request_json or {})))

    def test_unknown_without_late_answer_is_retained_without_resend(self):
        self.insert_request('req-unknown', 'unknown')
        receipt = qc_recovery.reconcile(self.config_path, self.ledger.path, self.job_id,
                                        self.root / 'reconcile.json')
        self.assertEqual(receipt['job_state'], 'queued')
        self.assertEqual(receipt['retained_unknown_requests'], ['req-unknown'])
        self.assertEqual(receipt['late_answers'], {})
        self.assertEqual(receipt['resend_dispatched'], 0)
        self.assertTrue(receipt['unknown_fees_remain_unknown'])
        with self.ledger.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0], 1)

    def test_late_answer_is_reported_when_actually_settled(self):
        self.insert_request('req-root', 'unknown', purpose='delivery-documents:abc')
        self.insert_request('req-retry', 'succeeded', purpose='delivery-documents:abc', attempt=1,
                            request_json={'timeout_retry_of': 'req-root', 'timeout_retry_root': 'req-root',
                                          'timeout_retry_number': 1},
                            response=json.dumps({'result': {'checks': {}}}), error=None)
        receipt = qc_recovery.reconcile(self.config_path, self.ledger.path, self.job_id,
                                        self.root / 'late.json')
        self.assertEqual(receipt['late_answers'], {'req-root': 'req-retry'})
        self.assertEqual(receipt['retained_unknown_requests'], [])

    def test_unrelated_purpose_does_not_answer_the_unknown(self):
        self.insert_request('req-unknown', 'unknown')
        self.insert_request('req-other', 'succeeded', purpose='delivery-documents:other',
                            response=json.dumps({'result': {}}), error=None)
        receipt = qc_recovery.reconcile(self.config_path, self.ledger.path, self.job_id,
                                        self.root / 'unrelated.json')
        self.assertEqual(receipt['late_answers'], {})
        self.assertEqual(receipt['retained_unknown_requests'], ['req-unknown'])

    def test_reconcile_requires_the_frozen_configuration(self):
        self.insert_request('req-unknown', 'unknown')
        changed = deepcopy(LEDGER_CONFIG)
        changed['run_id'] = 'other-run'
        path = self.root / 'changed.json'
        path.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            qc_recovery.reconcile(path, self.ledger.path, self.job_id, self.root / 'x.json')


if __name__ == '__main__':
    unittest.main()
