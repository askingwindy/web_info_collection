"""Offline boundary tests; fake responses are never real review evidence."""
import json
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from quality_inspector import codex_subscription as adapter
from quality_inspector.reviews import SEMANTIC


class SubscriptionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wc-subscription-test-')
        self.root = Path(self.temp.name)
        self.sample = self.root/'sample'
        (self.sample/'images').mkdir(parents=True)
        (self.sample/'ui_tree').mkdir()
        self.annotation = {'sample_id': 'offline_fixture', 'task_instruction': 'OFFLINE fixture',
            'final_result': 'fixture', 'completion_judgement': 'fixture', 'steps': []}
        for number in (1, 2):
            Image.new('RGB', (8, 8), (number*40, 0, 0)).save(self.sample/f'images/{number}.png')
            (self.sample/f'ui_tree/{number}.json').write_text(json.dumps({'elements': []}))
            self.annotation['steps'].append({'step_id': number, 'image_path': f'images/{number}.png',
                'ui_tree_path': f'ui_tree/{number}.json', 'action': {'action_type': 'complete'},
                'page_name': 'fixture', 'step_result': 'fixture', 'user_goal': 'fixture',
                'next_step_rationale': 'fixture', 'tool_result': {}})
        self.save_annotation()
        self.format_patch = patch.object(adapter, 'sample_check', return_value={'confirmed_format_pass': True})
        self.format_patch.start()
        self.auth_patch = patch.object(adapter, 'preflight', return_value={'authentication': 'chatgpt'})
        self.auth_patch.start()
        self.args = dict(sample=self.sample, output=self.root/'out', ledger=self.root/'ledger.sqlite3',
                         run_id='offline-test', model='offline-model', purpose='transport_smoke')
        self.calls = 0

    def tearDown(self):
        self.auth_patch.stop()
        self.format_patch.stop()
        self.temp.cleanup()

    def save_annotation(self):
        (self.sample/'annotation.json').write_text(json.dumps(self.annotation))

    def response(self):
        return {'step_observations': [{'step_id': i, 'note': 'OFFLINE protocol observation'} for i in (1, 2)],
                'checks': {name: {'status': 'PASS', 'note': 'OFFLINE test', 'evidence_steps': [1, 2]}
                           for name in SEMANTIC}}

    def fake_execute(self, args, prompt, directory, timeout):
        self.calls += 1
        with sqlite3.connect(self.args['ledger']) as db:
            self.assertEqual(db.execute('SELECT state FROM requests ORDER BY started DESC LIMIT 1').fetchone()[0], 'requested')
        (directory/'response.json').write_text(json.dumps(self.response()))
        (directory/'events.jsonl').write_text(json.dumps({'type': 'turn.completed',
            'usage': {'input_tokens': 100, 'output_tokens': 40, 'cached_input_tokens': 10}})+'\n')
        return {'returncode': 0, 'timed_out': False}

    def run_fake(self, execute=None):
        with patch.object(adapter, '_execute', side_effect=execute or self.fake_execute):
            return adapter.run(**self.args)

    def test_environment_removes_api_credentials_and_provider_overrides(self):
        safe = adapter.subscription_env({'PATH': '/bin', 'HOME': '/home/a', 'CODEX_HOME': '/auth',
            'OPENAI_API_KEY': 'secret', 'CODEX_API_KEY': 'secret', 'SOME_API_KEY': 'secret',
            'OPENAI_BASE_URL': 'http://other', 'CODEX_MODEL_PROVIDER': 'custom'})
        self.assertEqual(safe, {'PATH': '/bin', 'HOME': '/home/a', 'CODEX_HOME': '/auth'})

    def test_exec_disables_user_config_tools_and_api_fallback(self):
        args = adapter.exec_command('codex', 'fixed-model', self.root, [self.sample/'images/1.png'])
        self.assertIn('--ignore-user-config', args)
        self.assertIn('forced_login_method="chatgpt"', args)
        self.assertFalse(any('model_providers.' in arg for arg in args))
        self.assertIn('shell_tool', args)
        self.assertEqual(args[args.index('--sandbox')+1], 'read-only')

    def test_request_recorded_before_dispatch_and_cache_no_second_call(self):
        first = self.run_fake()
        second = self.run_fake()
        self.assertEqual(self.calls, 1)
        self.assertTrue(second['cache_reused'])
        self.assertEqual(first['cost']['usage']['input_tokens'], 100)

    def test_transport_cannot_be_imported_as_real_review(self):
        result = self.run_fake()
        review = json.loads(Path(result['review_file']).read_text())
        self.assertEqual(review['schema_version'], 'webcollect-subscription-transport-test-1')
        self.assertFalse(review['release_ready'])
        self.assertEqual(result['actual_visual_review_records'], 0)

    def test_substantive_difference_stays_pending_even_if_model_passes(self):
        result = self.run_fake()
        review = json.loads(Path(result['review_file']).read_text())
        self.assertEqual(review['records'][0]['checks']['substantive_difference']['status'], 'REVIEW_REQUIRED')

    def test_timeout_is_durable_unknown_and_never_retried(self):
        def timeout(*args):
            self.calls += 1
            return {'returncode': -9, 'timed_out': True}
        with self.assertRaisesRegex(ValueError, 'failed/timed out'):
            self.run_fake(timeout)
        with self.assertRaisesRegex(ValueError, 'automatic retry'):
            self.run_fake()
        self.assertEqual(self.calls, 1)
        with sqlite3.connect(self.args['ledger']) as db:
            self.assertEqual(db.execute('SELECT state FROM requests').fetchone()[0], 'unknown')

    def test_missing_usage_is_unknown_not_zero(self):
        def missing(*args):
            result = self.fake_execute(*args)
            (args[2]/'events.jsonl').write_text('{"type":"turn.completed"}\n')
            return result
        with self.assertRaisesRegex(ValueError, 'usage missing'):
            self.run_fake(missing)
        outcome = json.loads(next((self.root/'out').glob('*/outcome-unknown.json')).read_text())
        self.assertEqual(outcome['usage'], 'UNKNOWN')

    def test_missing_frame_observation_is_rejected(self):
        def omitted(*args):
            result = self.fake_execute(*args)
            response = self.response()
            response['step_observations'].pop()
            (args[2]/'response.json').write_text(json.dumps(response))
            return result
        with self.assertRaisesRegex(ValueError, 'omitted/repeated'):
            self.run_fake(omitted)

    def test_missing_semantic_check_is_rejected_by_shared_schema(self):
        def omitted(*args):
            result = self.fake_execute(*args)
            response = self.response()
            del response['checks']['privacy']
            (args[2]/'response.json').write_text(json.dumps(response))
            return result
        with self.assertRaises(Exception):
            self.run_fake(omitted)
        with sqlite3.connect(self.args['ledger']) as db:
            self.assertEqual(db.execute('SELECT state FROM requests').fetchone()[0], 'unknown')

    def test_changed_original_during_request_is_not_accepted(self):
        def changed(*args):
            result = self.fake_execute(*args)
            Image.new('RGB', (8, 8), 'blue').save(self.sample/'images/1.png')
            return result
        with self.assertRaisesRegex(ValueError, 'Candidate bytes changed'):
            self.run_fake(changed)

    def test_changed_input_does_not_reset_request_budget(self):
        self.run_fake()
        self.annotation['final_result'] = 'new'
        self.save_annotation()
        with self.assertRaisesRegex(ValueError, 'limit exhausted'):
            self.run_fake()
        self.assertEqual(self.calls, 1)

    def test_changed_run_identity_does_not_reset_budget(self):
        self.run_fake()
        self.args['run_id'] = 'another-id'
        with self.assertRaisesRegex(ValueError, 'configuration changed'):
            self.run_fake()

    def test_cached_result_tampering_is_rejected(self):
        result = self.run_fake()
        path = Path(result['review_file']).parent/'result.json'
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Cached result bytes changed'):
            self.run_fake()

    def test_cached_review_tampering_is_rejected(self):
        result = self.run_fake()
        Path(result['review_file']).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Cached evidence artifact bytes changed'):
            self.run_fake()

    def test_known_usage_survives_invalid_review_response(self):
        def bad(*args):
            result = self.fake_execute(*args)
            (args[2]/'response.json').write_text('{}')
            return result
        with self.assertRaises(Exception):
            self.run_fake(bad)
        outcome = json.loads(next((self.root/'out').glob('*/outcome-unknown.json')).read_text())
        self.assertEqual(outcome['usage']['input_tokens'], 100)

    def test_more_images_than_bound_rejected_before_auth_or_dispatch(self):
        self.args['max_images'] = 1
        with self.assertRaisesRegex(ValueError, 'whole trajectory'):
            self.run_fake()
        self.assertEqual(self.calls, 0)

    def test_sample_mechanical_failure_rejected_before_dispatch(self):
        with patch.object(adapter, 'sample_check', return_value={'confirmed_format_pass': False}):
            with self.assertRaisesRegex(ValueError, 'mechanical'):
                self.run_fake()
        self.assertEqual(self.calls, 0)

    def test_evidence_symlink_rejected(self):
        image = self.sample/'images/1.png'
        image.unlink()
        image.symlink_to(self.sample/'images/2.png')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.run_fake()

    def test_active_human_blind_batch_excluded(self):
        self.args['sample'] = self.root/'wave-a-20-r01'/'samples'/'any'
        with self.assertRaisesRegex(ValueError, 'blind-review'):
            self.run_fake()

    def test_output_inside_candidate_rejected(self):
        self.args['output'] = self.sample/'output'
        with self.assertRaisesRegex(ValueError, 'outside candidate'):
            self.run_fake()

    def test_multiple_execs_and_excessive_wall_budget_rejected(self):
        self.args['max_requests'] = 2
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.run_fake()
        self.args['max_requests'] = 1
        self.args['max_wall_seconds'] = 121
        with self.assertRaisesRegex(ValueError, '120'):
            self.run_fake()

    def test_unexpected_tools_are_rejected(self):
        path = self.root/'events.jsonl'
        path.write_text(json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution'}})+'\n'+
                        json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 1, 'output_tokens': 1}}))
        with self.assertRaisesRegex(ValueError, 'unexpected tool'):
            adapter.event_summary(path)


class AuthenticationPreflightTests(unittest.TestCase):
    def preflight_results(self, auth):
        return [subprocess.CompletedProcess([], 0, 'codex-cli fixture', ''),
                subprocess.CompletedProcess([], 0,
                    '--ignore-user-config --output-schema --image --json --ephemeral --sandbox', ''),
                subprocess.CompletedProcess([], 0, '', auth)]

    def test_saved_api_auth_is_rejected(self):
        with patch.object(adapter.subprocess, 'run', side_effect=self.preflight_results('Logged in using an API key')):
            with self.assertRaisesRegex(ValueError, 'API fallback prohibited'):
                adapter.preflight()

    def test_existing_chatgpt_auth_is_accepted_without_token_output(self):
        with patch.object(adapter.subprocess, 'run', side_effect=self.preflight_results('Logged in using ChatGPT\n')):
            result = adapter.preflight()
        self.assertEqual(result['authentication'], 'chatgpt')
        self.assertEqual(result['model_requests'], 0)

    def test_old_cli_missing_isolation_flag_is_rejected(self):
        results = self.preflight_results('Logged in using ChatGPT')
        results[1].stdout = '--json'
        with patch.object(adapter.subprocess, 'run', side_effect=results):
            with self.assertRaisesRegex(ValueError, 'isolated exec options'):
                adapter.preflight()


class AmendmentTests(unittest.TestCase):
    setUp = SubscriptionAdapterTests.setUp
    tearDown = SubscriptionAdapterTests.tearDown
    save_annotation = SubscriptionAdapterTests.save_annotation
    response = SubscriptionAdapterTests.response
    fake_execute = SubscriptionAdapterTests.fake_execute
    run_fake = SubscriptionAdapterTests.run_fake

    def establish_amendment(self):
        def stopped(*args):
            return {'returncode': 1, 'timed_out': False}
        with self.assertRaises(ValueError):
            self.run_fake(stopped)
        self.negative = self.root/'negative-case'
        shutil.copytree(self.sample, self.negative)
        annotation = json.loads((self.negative/'annotation.json').read_text())
        annotation['final_result'] = 'OFFLINE injected false terminal claim'
        (self.negative/'annotation.json').write_text(json.dumps(annotation))
        with sqlite3.connect(self.args['ledger']) as db:
            self.original = adapter.ledger_snapshot(db)
        artifacts = {}
        for row in self.original['requests']:
            for path in Path(row[3]).iterdir():
                if path.is_file():
                    artifacts[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.authorization = {'schema_version': 'webcollect-subscription-amendment-1',
            'amendment_id': 'offline-amendment', 'authorization_source': 'OFFLINE test only',
            'authorization_quote': 'OFFLINE explicit two-invocation allowance', 'reason': 'OFFLINE recovery test',
            'prior_snapshot': self.original, 'prior_snapshot_sha256': adapter.digest(self.original),
            'prior_artifacts_sha256': artifacts,
            'acknowledged_unresolved_request_keys': [row[0] for row in self.original['requests']],
            'config': adapter.run_config('offline-test', 'offline-model', 'transport_smoke', 2, 120, 8),
            'contract_sha256': adapter.fingerprint()[1],
            'expires_at': (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            'time_accounting': 'new_per_exec_reservations_preserve_original_start',
            'slots': [{'slot': 1, 'role': 'positive_transport', 'candidate': adapter.snapshot(self.sample)},
                      {'slot': 2, 'role': 'negative_calibration', 'depends_on': 1,
                       'candidate': adapter.snapshot(self.negative)}]}
        self.authorization_path = self.root/'authorization.json'
        self.authorization_path.write_text(json.dumps(self.authorization))
        adapter.amend(self.args['ledger'], self.authorization_path, self.root/'amendment-receipt.json')
        self.args.update(amendment_id='offline-amendment', slot=1, max_requests=2)

    def test_amendment_preserves_old_rows_and_unknown_state(self):
        self.establish_amendment()
        self.run_fake()
        with sqlite3.connect(self.args['ledger']) as db:
            original = adapter.ledger_snapshot(db, [row[0] for row in self.original['requests']])
            self.assertEqual(original, self.original)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM requests').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT reserved_seconds FROM amendment_slots').fetchone()[0], 120)

    def test_second_slot_requires_transport_completion(self):
        self.establish_amendment()
        self.args.update(slot=2, sample=self.negative)
        with self.assertRaisesRegex(ValueError, 'completed transport first'):
            self.run_fake()
        self.assertEqual(self.calls, 0)

    def test_two_slots_complete_and_reentry_reuses_cache(self):
        self.establish_amendment()
        self.run_fake()
        self.args.update(slot=2, sample=self.negative)
        result = self.run_fake()
        self.assertEqual(result['budget_amendment']['slot'], 2)
        self.assertTrue(self.run_fake()['cache_reused'])
        self.assertEqual(self.calls, 2)
        with sqlite3.connect(self.args['ledger']) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM requests').fetchone()[0], 3)

    def test_unknown_transport_blocks_calibration_without_extra_call(self):
        self.establish_amendment()
        def stopped(*args):
            self.calls += 1
            return {'returncode': -9, 'timed_out': True}
        with self.assertRaises(ValueError):
            self.run_fake(stopped)
        self.args.update(slot=2, sample=self.negative)
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            self.run_fake()
        self.assertEqual(self.calls, 1)

    def test_authorization_repeated_is_idempotent(self):
        self.establish_amendment()
        adapter.amend(self.args['ledger'], self.authorization_path, self.root/'amendment-receipt.json')
        with sqlite3.connect(self.args['ledger']) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM amendments').fetchone()[0], 1)

    def test_changed_authorization_cannot_replace_same_id(self):
        self.establish_amendment()
        self.authorization['reason'] = 'changed'
        self.authorization_path.write_text(json.dumps(self.authorization))
        with self.assertRaisesRegex(ValueError, 'changed authorization'):
            adapter.amend(self.args['ledger'], self.authorization_path, self.root/'other.json')

    def test_new_amendment_id_cannot_stack_budget(self):
        self.establish_amendment()
        self.authorization['amendment_id'] = 'stacked'
        self.authorization_path.write_text(json.dumps(self.authorization))
        with self.assertRaisesRegex(ValueError, 'cannot be stacked'):
            adapter.amend(self.args['ledger'], self.authorization_path, self.root/'other.json')

    def test_changed_calibration_evidence_is_rejected(self):
        self.establish_amendment()
        self.run_fake()
        Image.new('RGB', (8, 8), 'green').save(self.negative/'images/1.png')
        self.args.update(slot=2, sample=self.negative)
        with self.assertRaisesRegex(ValueError, 'frozen amendment slot'):
            self.run_fake()

    def test_changed_prior_failure_artifacts_are_rejected(self):
        self.establish_amendment()
        (Path(self.original['requests'][0][3])/'execution.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Original failure artifact changed'):
            self.run_fake()

    def test_unknown_prior_request_must_be_acknowledged(self):
        self.establish_amendment()
        self.authorization['acknowledged_unresolved_request_keys'] = []
        with self.assertRaisesRegex(ValueError, 'explicitly acknowledged'):
            adapter.validate_amendment(self.authorization)

    def test_changed_implementation_cannot_silently_use_amendment(self):
        self.establish_amendment()
        with patch.object(adapter, 'implementation_sha256', return_value={'changed': 'sha'}):
            with self.assertRaisesRegex(ValueError, 'implementation differs'):
                self.run_fake()


class SlotRepairTests(unittest.TestCase):
    setUp = SubscriptionAdapterTests.setUp
    tearDown = SubscriptionAdapterTests.tearDown
    save_annotation = SubscriptionAdapterTests.save_annotation
    response = SubscriptionAdapterTests.response
    fake_execute = SubscriptionAdapterTests.fake_execute
    run_fake = SubscriptionAdapterTests.run_fake
    establish_amendment = AmendmentTests.establish_amendment

    def establish_repair(self):
        self.establish_amendment()
        with self.assertRaises(ValueError):
            self.run_fake(lambda *args: {'returncode': 1, 'timed_out': False})
        with sqlite3.connect(self.args['ledger']) as db:
            before = adapter.ledger_snapshot(db)
            amendment_sha = db.execute('SELECT sha256 FROM amendments').fetchone()[0]
        cli = (self.root/'bundled-codex-fixture').resolve()
        cli.write_text('OFFLINE executable identity only; never executed')
        artifacts = {}
        for row in before['requests']:
            for path in Path(row[3]).iterdir():
                if path.is_file():
                    artifacts[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.revision = {'schema_version': 'webcollect-subscription-slot-revision-1',
            'revision_id': 'offline-repair', 'amendment_id': 'offline-amendment', 'slot': 2,
            'authorization_source': 'OFFLINE explicit instruction', 'authorization_quote': 'OFFLINE repurpose unused slot',
            'reason': 'OFFLINE CLI repair', 'amendment_sha256': amendment_sha,
            'prior_snapshot': before, 'prior_snapshot_sha256': adapter.digest(before),
            'acknowledged_unresolved_request_keys': [row[0] for row in before['requests']],
            'prior_artifacts_sha256': artifacts, 'config': self.authorization['config'],
            'contract_sha256': adapter.fingerprint()[1], 'role': 'repair_transport',
            'candidate': adapter.snapshot(self.sample),
            'cli': {'path': str(cli), 'sha256': hashlib.sha256(cli.read_bytes()).hexdigest(), 'version': 'OFFLINE'}}
        self.revision_path = self.root/'repair-authorization.json'
        self.revision_path.write_text(json.dumps(self.revision))
        adapter.repurpose(self.args['ledger'], self.revision_path, self.root/'repair-receipt.json')
        self.args.update(slot=2, repair_id='offline-repair', codex=str(cli))

    def test_explicit_repair_preserves_two_unknowns_and_consumes_last_slot(self):
        self.establish_repair()
        result = self.run_fake()
        self.assertEqual(result['budget_amendment']['slot_role'], 'repair_transport')
        self.assertEqual(result['budget_amendment']['negative_calibration'], 'NOT_RUN')
        with sqlite3.connect(self.args['ledger']) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM requests').fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM requests WHERE state='unknown'").fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT SUM(reserved_seconds) FROM amendment_slots').fetchone()[0], 240)
            old = adapter.ledger_snapshot(db, [row[0] for row in self.revision['prior_snapshot']['requests']])
            self.assertEqual(old, self.revision['prior_snapshot'])

    def test_successful_repair_reentry_uses_cache(self):
        self.establish_repair()
        self.run_fake()
        self.assertTrue(self.run_fake()['cache_reused'])
        self.assertEqual(self.calls, 1)

    def test_failed_repair_cannot_retry(self):
        self.establish_repair()
        with self.assertRaises(ValueError):
            self.run_fake(lambda *args: {'returncode': 1, 'timed_out': False})
        with self.assertRaisesRegex(ValueError, 'automatic retry'):
            self.run_fake()
        with sqlite3.connect(self.args['ledger']) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM requests').fetchone()[0], 3)

    def test_repair_rejects_wrong_cli_binary(self):
        self.establish_repair()
        Path(self.args['codex']).write_text('changed binary')
        with self.assertRaisesRegex(ValueError, 'CLI identity changed'):
            self.run_fake()

    def test_repair_cannot_change_model_or_allowance(self):
        self.establish_repair()
        self.revision['config'] = {**self.revision['config'], 'model': 'different-model'}
        with sqlite3.connect(self.args['ledger']) as db:
            with self.assertRaisesRegex(ValueError, 'cannot change model'):
                adapter.validate_slot_revision(db, self.revision)

    def test_extra_repair_revision_cannot_add_allowance(self):
        self.establish_repair()
        self.revision['revision_id'] = 'second-repair'
        self.revision_path.write_text(json.dumps(self.revision))
        with self.assertRaisesRegex(ValueError, 'Only one unused-slot repair'):
            adapter.repurpose(self.args['ledger'], self.revision_path, self.root/'extra-repair.json')


if __name__ == '__main__':
    unittest.main()
