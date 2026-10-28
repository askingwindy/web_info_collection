"""Offline protocol and attack cases; no actual GLM, collection or human review."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / 'projects/quality-inspector'), str(REPO / 'projects/quality-inspector/tests')]
import test_delivery_pipeline as support
from webcollect.batch_core import BatchLedger, OutcomeUnknown
from quality_inspector import document_text_qc as lane, delivery_pipeline as pipeline
from delivery_scope_fixture import freeze_scope


class DocumentTextQCTests(unittest.TestCase):
    def setUp(self):
        self.case = support.DeliveryPipelineTests('test_prepare_binds_jobs_to_plan_and_dispatches_no_model_requests')
        self.case.setUp(); self.addCleanup(self.case.doCleanups)
        self.root = self.case.root

    def parent(self, gateway=None, *, enforced_category=False, readonly_claim=None, sample_only=False):
        if enforced_category:
            value = json.loads(self.case.fixture.profile.read_text())
            value['targets']['category_share'] = 'enforced'
            self.case.fixture.profile.write_text(json.dumps(value))
        if readonly_claim:
            path = self.case.dataset / 'README.md'
            path.write_text(path.read_text() + '\n```json\n' + json.dumps(readonly_claim) + '\n```\n')
            self.case.fixture.seal()
            __import__('quality_inspector.delivery_sampling', fromlist=['freeze']).freeze(
                self.case.dataset, self.root / 'replacement-plan.json', ai_percent=100, human_percent=0, seed='CONTROLLED')
            self.case.plan = self.root / 'replacement-plan.json'
            from quality_inspector.cumulative import build_set_manifest
            self.case.effective = self.root / 'replacement-effective.json'
            lane._write(self.case.effective, build_set_manifest([self.case.dataset]))
        old = self.case.real_ledger_fixture()
        self.case.effective,self.case.cross_report=freeze_scope(self.root/'parent-scope',[self.case.dataset])
        prepared = pipeline.prepare(old, self.case.dataset, self.case.plan, self.case.effective, self.root / 'parent-prepared',
                                    profile=self.case.fixture.profile, cross_package_report=self.case.cross_report,
                                    mode='real', document_review_mode='ai')
        with patch.object(pipeline.ai_worker, 'ModelGateway', gateway or self.case.PassingProtocolGateway), \
                patch('urllib.request.build_opener', side_effect=AssertionError('No actual network')):
            state = (lane.run_samples(prepared['receipt'], self.root / 'parent-run')['original_sample_status'] if sample_only else
                     pipeline.run(prepared['receipt'], self.root / 'parent-run', max_jobs=10))
        self.parent_receipt = prepared['receipt']; self.parent_state = state
        self.parent_status = self.root / 'parent-run/status.json'; self.old = old
        return state

    def ledger(self, name='document'):
        config = deepcopy(self.old.config)
        config['run_id'] = 'CONTROLLED-DOCUMENT-TEXT-' + name
        config['budget']['max_model_requests'] = 1
        return BatchLedger(self.root / (name + '.sqlite3'), config, initialize=True)

    def prepare(self, ledger=None, status=None, output='document-prepared'):
        ledger = ledger or self.ledger()
        result = lane.prepare(ledger, self.parent_receipt, status or self.parent_status, self.root / output)
        return ledger, result

    def run_lane(self, prepared, output='document-run', gateway=None):
        with patch.object(lane, 'ModelGateway', gateway or self.case.PassingProtocolGateway), \
                patch('urllib.request.build_opener', side_effect=AssertionError('No actual network')):
            return lane.run(prepared['receipt'], self.root / output)

    def test_original_failure_and_actual_human_override_survive_text_pass_and_finalization(self):
        class FailedSampleAndDocument(self.case.PassingProtocolGateway):
            def transform(self, job, result):
                if job['kind'] in ('ai-visual', 'ai-documents'):
                    next(iter(result['checks'].values()))['status'] = 'FAIL'
                return result
        state = self.parent(FailedSampleAndDocument)
        self.assertEqual(state['human_pending_count'], 1)
        human = self.case.fixture.reviewed(); raw = json.loads(human.read_text()); raw.pop('delivery_document_review', None)
        for row in raw['records']:
            row['reviewer'] = {'kind': 'human', 'name': 'CONTROLLED HUMAN FIXTURE; NOT ACTUAL HUMAN'}
        human.write_text(json.dumps(raw))
        state = pipeline.import_human(self.parent_receipt, [human], self.root / 'human-import')
        self.parent_status = self.root / 'human-import/status.json'
        old_usage = pipeline._usage(self.old, pipeline.verify(self.parent_receipt))
        old_hashes = pipeline._implementation()
        ledger, prepared = self.prepare()
        current = self.run_lane(prepared)
        self.assertEqual(current['text_consistency']['status'], 'PASS')
        self.assertEqual(current['human_document_pending_count'], 0)
        self.assertEqual(current['actual_human_reviewed'], 1)
        report = lane._read(current['report']['path'])
        self.assertEqual(report['semantic_sampling']['rows'][0]['ai_status'], 'FAIL')
        self.assertEqual(report['semantic_sampling']['rows'][0]['status'], 'HUMAN_PASS')
        effective = lane._read(current['review_file']['path'])
        self.assertTrue(any(row['status'] == 'FAIL' for row in effective['document_policy_amendment']['original_document_review']['checks'].values()))
        self.assertEqual(current['original_bound_model_usage'], old_usage)
        self.assertEqual(current['document_model_usage']['model_requests'], 1)
        self.assertEqual(pipeline._implementation(), old_hashes)
        final = lane.finalize(prepared['receipt'], self.root / 'document-run/status.json', self.root / 'final',
                              archive=self.root / 'CONTROLLED-ONLY.zip')
        self.assertTrue(final['release_ready'])
        self.assertEqual(final['customer_acceptance'], 'UNKNOWN')

    def test_truthful_single_category_text_pass_cannot_clear_original_formal_gate(self):
        self.parent(enforced_category=True)
        _, prepared = self.prepare(); current = self.run_lane(prepared)
        self.assertEqual(current['text_consistency']['status'], 'PASS')
        self.assertEqual(current['payload_status'], 'FAIL')
        self.assertFalse(current['release_ready'])
        self.assertTrue(any(row['rule_id'] == 'DELIVERY_CATEGORY_SHARE' and row['status'] == 'FAIL'
                            for row in current['formal_blockers']['dataset_checks']))
        with self.assertRaisesRegex(ValueError, 'distribution'):
            lane.finalize(prepared['receipt'], self.root / 'document-run/status.json', self.root / 'blocked-final')
        # Even an issued parent-compatible status is re-inspected by the old finalizer.
        with self.assertRaisesRegex(ValueError, 'distribution'):
            pipeline.finalize(self.parent_receipt, self.root / 'document-run/status.json', self.root / 'also-blocked')

    def test_ai_fail_unknown_and_replay_never_create_document_humans_or_repeat_charges(self):
        self.parent()
        class FailedText(self.case.PassingProtocolGateway):
            def transform(self, job, result):
                next(iter(result['checks'].values()))['status'] = 'FAIL'; return result
        ledger, prepared = self.prepare()
        failed = self.run_lane(prepared, gateway=FailedText)
        self.assertEqual(failed['document_review_status'], 'REVISE_DOCUMENTS_REQUIRED')
        self.assertEqual(failed['human_document_pending_count'], 0)
        replay = self.run_lane(prepared, output='replayed')
        self.assertEqual(replay['text_consistency']['status'], 'FAIL')
        self.assertEqual(ledger.summary()['model_requests'], 1)
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            lane.finalize(prepared['receipt'], self.root / 'document-run/status.json', self.root / 'failed-final')

    def test_unknown_response_stays_ai_pending_with_original_unknown_charge(self):
        self.parent()
        class UnknownGateway:
            def __init__(self, ledger): self.ledger = ledger
            def call(self, job, purpose, *args, **kwargs):
                ref = self.ledger.reserve_request(job, purpose, 0, request_json={'CONTROLLED': True})
                self.ledger.settle_request(ref['id'], state='unknown', error='CONTROLLED-no-network-unknown')
                raise OutcomeUnknown('CONTROLLED unknown')
        ledger, prepared = self.prepare()
        current = self.run_lane(prepared, gateway=UnknownGateway)
        self.assertEqual(current['text_consistency']['status'], 'REVIEW_REQUIRED')
        self.assertEqual(current['document_review_status'], 'AI_REVIEW_REQUIRED')
        self.assertEqual(current['human_document_pending_count'], 0)
        self.assertEqual(current['document_model_usage']['request_states'], {'unknown': 1})
        self.assertEqual(current['document_model_usage']['input_tokens'], 'UNKNOWN')
        self.run_lane(prepared, output='unknown-replay')
        self.assertEqual(ledger.summary()['model_requests'], 1)

    def test_status_rerender_and_output_change_reuse_same_job_and_new_ledger_is_refused(self):
        self.parent(); ledger, first = self.prepare(); self.run_lane(first)
        pipeline.status(self.parent_receipt, self.root / 'parent-status-rerender')
        _, again = self.prepare(ledger, self.root / 'parent-status-rerender/status.json', 'new-prepare-location')
        self.assertEqual(first['job_id'], again['job_id'])
        self.run_lane(again, output='second-status')
        self.assertEqual(ledger.summary()['model_requests'], 1)
        other = self.ledger('another-scope')
        # Same config is needed to represent the same model policy/cache identity.
        with self.assertRaisesRegex(ValueError, 'another ledger'):
            lane.prepare(BatchLedger(self.root / 'another-path.sqlite3', ledger.config, initialize=True),
                         self.parent_receipt, self.parent_status, self.root / 'forbidden-scope')
        self.assertEqual(other.summary()['model_requests'], 0)

    def test_forged_issued_status_and_changed_materials_stop_before_requests(self):
        self.parent(); raw = lane._read(self.parent_status); raw['actual_human_reviewed'] = 20
        forged = self.root / 'forged-status.json'; lane._write(forged, raw)
        ledger = self.ledger()
        with self.assertRaisesRegex(ValueError, 'not issued'):
            self.prepare(ledger, forged)
        self.assertEqual(ledger.summary()['model_requests'], 0)
        _, prepared = self.prepare(ledger)
        path = self.case.dataset / 'README.md'; path.write_text(path.read_text() + '\nchanged\n')
        with self.assertRaisesRegex(ValueError, 'package changed'):
            self.run_lane(prepared)
        self.assertEqual(ledger.summary()['model_requests'], 0)

    def test_structured_readme_contradiction_is_rejected_mechanically_without_ai_fee(self):
        self.parent(readonly_claim={'sample_count': 2, 'site_count': 9, 'categories': {'虚构': 2}, 'frames': 999})
        ledger, prepared = self.prepare(); current = self.run_lane(prepared)
        self.assertEqual(current['text_consistency']['status'], 'FAIL')
        self.assertEqual(current['document_review_status'], 'REVISE_DOCUMENTS_REQUIRED')
        self.assertEqual(current['payload_status'], 'FAIL')
        self.assertEqual(current['human_document_pending_count'], 0)
        self.assertEqual(ledger.summary()['model_requests'], 0)
        differences = current['text_consistency']['engineering_text_comparison']['comparisons']
        self.assertEqual({row['field'] for row in differences if row['status'] == 'FAIL'},
                         {'sample_count', 'site_count', 'categories', 'frames'})

    def test_future_runner_skips_legacy_document_job_and_records_supersession(self):
        self.parent(sample_only=True)
        receipt = pipeline.verify(self.parent_receipt)
        self.assertEqual(self.old.get(receipt['document_job'])['state'], 'queued')
        with self.old.connect() as con:
            calls = list(con.execute('SELECT job_id FROM model_requests'))
            events = list(con.execute("SELECT * FROM batch_events WHERE event='document_text_legacy_job_superseded'"))
        self.assertTrue(calls); self.assertTrue(events)
        self.assertNotIn(receipt['document_job'], {row['job_id'] for row in calls})
        _, prepared = self.prepare(); current = self.run_lane(prepared)
        self.assertEqual(current['text_consistency']['status'], 'PASS')
        self.assertEqual(current['human_document_pending_count'], 0)
        self.assertEqual(self.old.get(receipt['document_job'])['state'], 'queued')

    def test_partial_statistics_block_and_nested_boolean_count_are_not_skipped(self):
        categories = self.case.fixture.report()['statistics']['categories']
        self.parent(readonly_claim={'site_count': 9, 'frames': 999, 'categories': {key: True for key in categories}})
        ledger, prepared = self.prepare(); current = self.run_lane(prepared)
        self.assertEqual(current['text_consistency']['status'], 'FAIL')
        failed = {row['field'] for row in current['text_consistency']['engineering_text_comparison']['comparisons']
                  if row['status'] == 'FAIL'}
        self.assertEqual(failed, {'site_count', 'frames', 'categories'})
        self.assertEqual(ledger.summary()['model_requests'], 0)

    def test_edited_new_status_cannot_be_finalized(self):
        self.parent(); _, prepared = self.prepare(); self.run_lane(prepared)
        path = self.root / 'document-run/status.json'; state = lane._read(path)
        state['actual_human_reviewed'] = 20; path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, 'not issued'):
            lane.finalize(prepared['receipt'], path, self.root / 'forged-final')

    def test_later_human_failure_invalidates_amendment_before_dispatch(self):
        self.parent(); ledger, prepared = self.prepare()
        human = self.case.fixture.reviewed(); raw = lane._read(human); raw.pop('delivery_document_review', None)
        for row in raw['records']:
            row['reviewer'] = {'kind': 'human', 'name': 'CONTROLLED LATER HUMAN FAIL'}
            row['checks']['terminal_semantics']['status'] = 'FAIL'
        human.write_text(json.dumps(raw))
        pipeline.import_human(self.parent_receipt, [human], self.root / 'later-human-fail')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.run_lane(prepared)
        self.assertEqual(ledger.summary()['model_requests'], 0)

    def test_supporting_fact_hash_and_actual_result_actor_cannot_be_rewritten(self):
        self.parent(); ledger = self.ledger(); facts = self.root / 'actual-facts.json'
        lane._write(facts, {'schema_version': 'CONTROLLED-FACTS', 'actual_samples': 1})
        prepared = lane.prepare(ledger, self.parent_receipt, self.parent_status, self.root / 'with-facts', supporting_files=[facts])
        current = self.run_lane(prepared)
        job = ledger.get(prepared['job_id']); result = deepcopy(job['result']); result['reviewer']['kind'] = 'human'
        with ledger.transaction() as con:
            con.execute('UPDATE jobs SET result=? WHERE id=?', (json.dumps(result), prepared['job_id']))
        with self.assertRaisesRegex(ValueError, 'actor/template'):
            lane.status(prepared['receipt'], self.root / 'forged-actor')
        facts.write_text(json.dumps({'actual_samples': 20}))
        with self.assertRaisesRegex(ValueError, 'input file changed|evidence changed'):
            lane.verify(prepared['receipt'])
        self.assertEqual(current['document_model_usage']['model_requests'], 1)

    def test_support_order_or_budget_and_key_env_changes_cannot_buy_duplicate_review(self):
        self.parent(); ledger = self.ledger(); a = self.root / 'a.md'; b = self.root / 'b.json'
        a.write_text('CONTROLLED supplementary fact A')
        lane._write(b, {'CONTROLLED': 'fact B'})
        first = lane.prepare(ledger, self.parent_receipt, self.parent_status, self.root / 'order-a', supporting_files=[a, b])
        second = lane.prepare(ledger, self.parent_receipt, self.parent_status, self.root / 'order-b', supporting_files=[b, a])
        self.assertEqual(first['job_id'], second['job_id'])
        changed = deepcopy(ledger.config); changed['run_id'] = 'CONTROLLED-changed-budget-same-request'
        changed['model']['reserve_input_tokens'] += 1
        changed['model']['api_key_env'] = 'CONTROLLED_DIFFERENT_KEY_ENV'
        other = BatchLedger(self.root / 'changed-budget.sqlite3', changed, initialize=True)
        with self.assertRaisesRegex(ValueError, 'another ledger'):
            lane.prepare(other, self.parent_receipt, self.parent_status, self.root / 'order-c', supporting_files=[a, b])
        self.assertEqual(other.summary()['model_requests'], 0)


if __name__ == '__main__': unittest.main()
