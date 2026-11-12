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

    def test_saved_research_requires_frozen_production_comparison(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        import sqlite3
        from webcollect.batch_core import file_sha
        from webcollect.candidate_contract import validate_research_v2
        from webcollect.session_objective import VERSION
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def freeze(name, value):
                path = root / name
                path.write_text(json.dumps(value))
                return {'path': str(path), 'sha256': file_sha(path)}
            objective = freeze('session-objective.json', {'schema_version': VERSION,
                'candidate_id': 'candidate', 'version': 1})
            receipt = freeze('saved.json', {'sample_id': 'sample'})
            binding = {'output': str(root), 'registry': str(root/'registry'),
                       'ledger': str(root/'ledger'), 'history_set': str(root/'manifest')}
            comparison = {'role': 'comparison', 'claim_id': 'original',
                          'sample_id': 'sample', 'save_receipt': receipt}
            auth = {'scope': 'fixed-baseline-research-only', 'candidate_id': 'candidate',
                    'version': 1, 'original_claim_id': 'original', 'objective': objective,
                    'comparisons': [comparison], 'production_counted': False,
                    'pool': str(root/'pool'), 'registry': binding['registry']}
            descriptor = {'schema_version': 'candidate-research-replay',
                'original_claim_id': 'original', 'objective': objective,
                'authorization': freeze('authorization.json', auth),
                'comparisons': [comparison], 'production_counted': False}
            con = sqlite3.connect(':memory:'); con.row_factory = sqlite3.Row
            con.execute('CREATE TABLE candidate_claims(candidate_id,claim_id,binding,state)')
            con.execute('CREATE TABLE candidate_results(candidate_id,claim_id,sample_id,record,effective)')
            saved = {'sample_id': 'sample', 'registry': binding['registry'], 'save_receipt': receipt}
            con.execute('INSERT INTO candidate_claims VALUES(?,?,?,?)',
                        ('candidate','original',json.dumps(binding),'succeeded'))
            con.execute('INSERT INTO candidate_results VALUES(?,?,?,?,1)',
                        ('candidate','original','sample',json.dumps(saved))); con.commit()
            @contextmanager
            def connect():
                yield con
            pool = SimpleNamespace(path=root/'pool', pool=SimpleNamespace(connect=connect))
            original = {'candidate_id':'candidate','claim_id':'original','version':1,
                        'state':'succeeded','binding':binding}
            validate_research_v2(descriptor, pool, original)
            self.assertEqual(con.execute('SELECT effective FROM candidate_results').fetchone()[0], 1)
            auth['comparisons'] = []; descriptor['comparisons'] = []
            descriptor['authorization'] = freeze('authorization.json', auth)
            with self.assertRaisesRegex(ValueError, 'production comparison'):
                validate_research_v2(descriptor, pool, original)
            # The browser-close proof permits only its named next research
            # request; ordinary guards use it only while that claim is active.
            from unittest.mock import patch
            from webcollect.request_quarantine import authorized_transport_research
            con.execute('ALTER TABLE candidate_claims ADD COLUMN request_id')
            with sqlite3.connect(root/'pool') as disk:
                con.backup(disk)
            facts = {'pool':str(root/'pool'),'candidate_id':'candidate',
                     'claim_id':'original','next_request_id':'run-r03/new-research'}
            with sqlite3.connect(root/'registry') as registry:
                registry.execute('CREATE TABLE m4_events(event_type,attempt_id,payload_json)')
                registry.execute('INSERT INTO m4_events VALUES(?,?,?)',
                    ('planning_timeout_research_authorized','attempt',json.dumps({
                     'authorization':descriptor['authorization'],'closed_execution':facts})))
            with patch('webcollect.request_quarantine.transport_closed_execution', return_value=facts):
                self.assertTrue(authorized_transport_research(root/'registry','attempt',request_id='run-r03/new-research'))
                self.assertFalse(authorized_transport_research(root/'registry','attempt',request_id='run-r04/new-research'))
                self.assertFalse(authorized_transport_research(root/'registry','attempt'))
                with sqlite3.connect(root/'pool') as disk:
                    disk.execute('INSERT INTO candidate_claims VALUES(?,?,?,?,?)',
                        ('candidate','next',json.dumps({'research_replay':{
                         'original_claim_id':'original','production_counted':False}}),
                         'consuming','run-r03/new-research'))
                self.assertTrue(authorized_transport_research(root/'registry','attempt'))
                with sqlite3.connect(root/'pool') as disk:
                    disk.execute("UPDATE candidate_claims SET state='failed' WHERE claim_id='next'")
                self.assertFalse(authorized_transport_research(root/'registry','attempt'))
            con.close()


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
