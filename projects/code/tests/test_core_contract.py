"""Core no-version contract tests (2026-11-11 rewrite).

Replaces the retired 260-file suite. Only current business contracts are
asserted: stable protocol names, the single completion rule, strategy-result
close-out, candidate-pool v2 claiming, and the documented CLI entries.
All checks are offline; no real GLM, browser or production database is used.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from site_planner.candidate_pool import CandidatePool
from webcollect.candidate_contract import VERSION as CONSUMPTION_VERSION
from webcollect.collection_strategy import (DEFAULT_STRATEGY, RESULT_CONTRACT,
                                            STRATEGIES, STRATEGY_BANDED_REACT,
                                            STRATEGY_SCREENSHOT_PLAN,
                                            finalize_strategy_result, freeze,
                                            strategy_id)
from webcollect.closing_policy import MINIMUM, attempt_limit, completion_delivery_decision
from webcollect.plan_protocol import (ENDING_POLICY, PLAN_PROTOCOL, REACT_PROTOCOL,
                                      RESULT_COMPLETION_PROTOCOL, RESULT_EXECUTION_POLICY)


class PlanProtocolContract(unittest.TestCase):
    def test_stable_names_are_the_single_owner_values(self):
        self.assertEqual(PLAN_PROTOCOL, 'conditional-plan')
        self.assertEqual(ENDING_POLICY, 'goal-completion-ending')
        self.assertEqual(RESULT_EXECUTION_POLICY, 'result-execution')
        self.assertEqual(RESULT_COMPLETION_PROTOCOL, 'result-completion')
        self.assertEqual(REACT_PROTOCOL, 'react-native')
        self.assertEqual(tuple(STRATEGIES), ('react', 'screenshot_plan'))
        self.assertEqual(DEFAULT_STRATEGY, STRATEGY_BANDED_REACT)

    def test_candidate_consumption_binding_name_is_stable(self):
        self.assertEqual(CONSUMPTION_VERSION, 'candidate-consumption')


class ClosingPolicyContract(unittest.TestCase):
    """Single rule: original goal success + >= MINIMUM effective steps, no ceiling."""

    @staticmethod
    def _annotation(steps, *, status='success'):
        return {'completion_status': status,
                'steps': [{'action': {'action_type': kind}} for kind in steps]}

    @staticmethod
    def _raw(*, effective, ending_kind='HOST_PLAN_ENDPOINT', safe=True, flagged=False,
             unknown=False, stop_reason='ready'):
        return {'effective_steps': effective,
                'collection_ending': {'kind': ending_kind, 'safe_for_pending_sample': safe,
                                      'flagged': flagged, 'external_effect_unknown': unknown,
                                      'endpoint_evidence': {
                                          'image': {'path': 'x'}, 'source': 'host_plan_endpoint',
                                          'session_objective_evidence': {'completion': {
                                              'answer': {'check_answers': [{'check_index': 0}]},
                                              'original_checks': ['c0']}}}},
                'goal_evidence': {'checks': [{'status': 'VERIFIED'}]},
                'stop_reason': stop_reason, 'unknown': unknown, 'trusted_prefix': None}

    def test_five_effective_steps_with_verified_endpoint_are_eligible(self):
        annotation = {'completion_status': 'success',
                      'steps': [{'action': {'action_type': 'click'}} for _ in range(MINIMUM)]}
        raw = self._raw(effective=MINIMUM)
        decision = completion_delivery_decision(annotation, raw)
        self.assertEqual(decision['delivery_policy'], 'completed-goal-delivery')
        self.assertTrue(decision['original_goal_completed'])
        self.assertTrue(decision['delivery_eligible'])

    def test_under_five_effective_steps_cannot_be_eligible(self):
        annotation = self._annotation(['click', 'type', 'click'])
        raw = self._raw(effective=3)
        decision = completion_delivery_decision(annotation, raw)
        self.assertFalse(decision['delivery_eligible'])

    def test_more_than_ten_steps_is_not_rejected(self):
        annotation = {'completion_status': 'success',
                      'steps': [{'action': {'action_type': 'click'}} for _ in range(12)]}
        raw = self._raw(effective=12)
        decision = completion_delivery_decision(annotation, raw)
        self.assertTrue(decision['delivery_eligible'])
        self.assertEqual(decision['effective_steps'], 12)

    def test_flagged_or_unknown_endings_stay_ineligible(self):
        annotation = self._annotation(['click'] * MINIMUM)
        for raw in (self._raw(effective=MINIMUM, flagged=True),
                    self._raw(effective=MINIMUM, unknown=True),
                    self._raw(effective=MINIMUM, safe=False),
                    self._raw(effective=MINIMUM, stop_reason='no_path')):
            self.assertFalse(completion_delivery_decision(annotation, raw)['delivery_eligible'])

    def test_no_cumulative_attempt_ceiling_exists(self):
        task = {'fragment': {'ending_policy': ENDING_POLICY}}
        self.assertIsNone(attempt_limit(task))
        task['fragment']['budgets'] = {'max_actions': 40}
        self.assertEqual(attempt_limit(task), 40)


class StrategyResultContract(unittest.TestCase):
    def test_freeze_records_strategy_and_dispatch_follows(self):
        task = {'task_id': 't', 'fragment': {}, 'workflow_proposal': {'spec': {}}}
        freeze(task, STRATEGY_SCREENSHOT_PLAN)
        self.assertEqual(strategy_id(task), STRATEGY_SCREENSHOT_PLAN)

    def test_finalize_replaces_transient_end_with_actual_outcome(self):
        result = {'result_contract': RESULT_CONTRACT,
                  'strategy': {'id': STRATEGY_BANDED_REACT},
                  'goal': {'goal_status': 'VERIFIED'},
                  'execution': {'effective_steps': 6},
                  'end': {'goal_status': 'VERIFIED', 'end_reason': 'ready',
                          'save_eligibility': 'unresolved', 'save_status': 'unresolved'}}
        saved = finalize_strategy_result(result, save_status='collected_pending_review',
                                         eligibility='eligible')
        self.assertEqual(saved['end']['save_status'], 'collected_pending_review')
        self.assertEqual(saved['end']['save_eligibility'], 'eligible')
        self.assertEqual(saved['result_contract'], 'strategy-result')
        # The sealed session originals are never rewritten by finalization.
        self.assertEqual(result['end']['save_status'], 'unresolved')

    def test_not_saved_defaults_to_ineligible(self):
        result = {'result_contract': RESULT_CONTRACT, 'strategy': {'id': 'react'},
                  'goal': {'goal_status': 'unconfirmed'},
                  'execution': {'effective_steps': 0},
                  'end': {'goal_status': 'unconfirmed', 'end_reason': 'no_path',
                          'save_eligibility': 'unresolved', 'save_status': 'unresolved'}}
        finalized = finalize_strategy_result(result, save_status='not_saved')
        self.assertEqual(finalized['end']['save_status'], 'not_saved')
        self.assertEqual(finalized['end']['save_eligibility'], 'ineligible')


class CandidatePoolContract(unittest.TestCase):
    def test_v2_body_put_and_claim_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            from site_planner.site_pool import SitePool
            SitePool(Path(tmp) / 'pool.sqlite3', initialize=True)
            pool = CandidatePool(Path(tmp) / 'pool.sqlite3', install=True)
            proof = Path(tmp) / 'source.json'
            proof.write_text(json.dumps({'CONTROLLED': 'offline fixture'}))
            from site_planner.discovery_tools import reference
            body = {'schema_version': 'webcollect-data-candidate-2', 'candidate_kind': 'target',
                    'entry_url': 'https://example.org/', 'requested_goal': {
                        'kind': 'edit', 'entity': 'fields', 'parameters': {'quantity': 1}}}
            cid = pool.put(body, {'origin': 'codex_session', 'run_id': 'offline-core-tests',
                                  'references': [reference(proof)]})
            claim = pool.claim_next('core-test-worker', 'core/0')
            self.assertEqual(claim['candidate_id'], cid)
            self.assertEqual(claim['snapshot']['schema_version'], 'webcollect-data-candidate-2')

            # Two producers race for one remaining per-application NEW slot.
            # The limit is rechecked in the same transaction as publication.
            with pool.pool.connect() as connection:
                application_id = connection.execute(
                    'SELECT application_id FROM data_candidates WHERE candidate_id=?', (cid,)).fetchone()[0]
            run_id = 'offline-core-tests/entry-batch/concurrent-limit'
            pool.pool.freeze_run(run_id, {'application_new_target': 1,
                                         'application_pending_cap': 100}, inventory=False)
            source = {'origin': 'codex_session', 'run_id': 'offline-core-tests',
                      'references': [reference(proof)]}

            def publish(index):
                candidate = {'schema_version': 'webcollect-data-candidate-2',
                             'candidate_kind': 'entry',
                             'entry_url': f'https://example.org/page-{index}',
                             'requested_goal': None}
                header = {'row_id': f'row-{index}', 'run_id': run_id, 'batch': 0,
                          'request_id': f'request-{index}', 'response_sha256': f'digest-{index}',
                          'raw_index': index}
                return CandidatePool(Path(tmp) / 'pool.sqlite3').publish_row(
                    header, candidate, source, application_id=application_id)

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(publish, (1, 2)))
            self.assertEqual(sorted(item['result'] for item in outcomes), ['NEW', 'OVER_LIMIT'])
            with pool.pool.connect() as connection:
                count = connection.execute(
                    'SELECT COUNT(*) FROM data_candidates WHERE application_id=?',
                    (application_id,)).fetchone()[0]
            self.assertEqual(count, 2)  # The original roundtrip row plus exactly one raced NEW.

    def test_v1_body_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            from site_planner.site_pool import SitePool
            SitePool(Path(tmp) / 'pool.sqlite3', initialize=True)
            pool = CandidatePool(Path(tmp) / 'pool.sqlite3', install=True)
            with self.assertRaises(ValueError):
                pool.put({'schema_version': 'webcollect-data-candidate-1'}, {'origin': 'x'})


class CliEntriesSmoke(unittest.TestCase):
    """The documented module entries must still parse their own arguments."""

    ENTRIES = ('webcollect.task_generation', 'webcollect.candidate_consumer',
               'site_planner.candidate_discovery', 'quality_inspector')

    def test_help_exits_zero(self):
        for entry in self.ENTRIES:
            done = subprocess.run([sys.executable, '-m', entry, '--help'],
                                  capture_output=True, env={
                                      'PATH': '/usr/bin:/bin',
                                      'PYTHONPATH': 'projects/code:projects/site-planner:projects/quality-inspector'},
                                  timeout=120)
            self.assertEqual(done.returncode, 0, (entry, done.stderr[-500:]))


if __name__ == '__main__':
    unittest.main()
