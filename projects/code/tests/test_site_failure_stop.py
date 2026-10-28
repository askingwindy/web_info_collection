"""Deterministic temporary ledgers only; no browsers, model, or original DB IO."""
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from webcollect.site_failure_stop import SiteFailureStore, SiteStopped, application_key, execution_id
from webcollect.runtime import RuntimeStore
import m4_runtime_fixtures as fixtures


class SiteFailureStopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binding = {'ledger': str(self.root / 'stop.sqlite3'), 'campaign_id': 'CONTROLLED-current-chain',
                        'formal_since': fixtures.NOW - 1}
        self.store = SiteFailureStore.initialize(self.binding)

    def fail(self, identity, application='https://example.org/page?q=1', **updates):
        values = {'stage': 'observation', 'state': 'failed', 'reason': 'CONTROLLED execution error',
                  'real_execution': True, 'evidence': [{'fixture': identity}],
                  'usage_refs': [{'request_id': identity, 'usage': 'UNKNOWN', 'cost': 'UNKNOWN'}]}
        values.update(updates)
        return self.store.record(application, identity, **values)

    def runtime(self, count=4):
        registry = fixtures.make_registry(self.root / 'production.sqlite3')
        runtime = RuntimeStore(registry, 'CONTROLLED-scope')
        runtime.initialize({'campaign_id': 'CONTROLLED-formal', 'site_failure_guard': self.binding}, now=fixtures.NOW)
        plan, publication = fixtures.make_plan(self.root / 'plan', count=count, uri='https://example.org/other')
        runtime.enqueue_plan(plan, publication, now=fixtures.NOW)
        return runtime

    def test_cross_page_parameter_scheme_and_restart_never_reset_three_failures(self):
        for number, uri in enumerate(('https://Example.org/a?q=1', 'http://example.org/b#x', 'https://example.org/c')):
            self.fail(str(number), uri)
        reopened = SiteFailureStore(self.binding)
        with self.assertRaises(SiteStopped): reopened.guard('https://example.org/fresh?p=99')
        self.assertEqual(reopened.status('https://example.org/')['failure_count'], 3)
        self.assertFalse(reopened.status('https://other.example/')['dispatch_blocked'])

    def test_execution_id_deduplicates_and_cannot_move_or_reclassify(self):
        self.fail('one'); self.fail('one')
        self.assertEqual(self.store.status('https://example.org/')['failure_count'], 1)
        with self.assertRaisesRegex(ValueError, 'reclassified'):
            self.fail('one', 'https://other.example/')
        with self.assertRaisesRegex(ValueError, 'reclassified'):
            self.fail('one', reason='different cause')
        with self.assertRaises(ValueError): self.fail('approval-denied', real_execution=False)
        self.assertEqual(self.store.status('https://example.org/')['failure_count'], 1)

    def test_unknown_usage_is_preserved_and_holds_without_inventing_failure(self):
        result = self.fail('uncertain', state='unknown')
        self.assertEqual(result['failure_count'], 0)
        self.assertEqual(result['unknown_execution_count'], 1)
        with self.assertRaises(SiteStopped): self.store.guard('https://example.org/')
        with self.store.connect() as con:
            refs = json.loads(con.execute('SELECT usage_refs_json FROM site_executions').fetchone()[0])
        self.assertEqual(refs[0]['usage'], 'UNKNOWN')

    def test_pre_admission_and_formal_failures_merge_before_claim_without_page_reset(self):
        self.fail('pre-admission')
        runtime = self.runtime()
        for number in range(2):
            now = fixtures.NOW + number * 3
            attempt = runtime.claim_next('worker', request_id=str(number), now=now)
            self.assertIsNotNone(attempt)
            runtime.start_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], now=now)
            runtime.finish_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], 'rejected',
                failure_class='program', root_cause='CONTROLLED-' + str(number), now=now + 1)
        self.assertIsNone(runtime.claim_next('worker', request_id='third-formal', now=fixtures.NOW + 9))
        self.assertEqual(self.store.status('https://example.org/')['failure_count'], 3)
        runtime._sync_site_failures()
        self.assertEqual(self.store.status('https://example.org/')['failure_count'], 3)

    def test_start_rechecks_after_reservation_and_policy_cannot_reset_ledger(self):
        runtime = self.runtime(count=1)
        attempt = runtime.claim_next('worker', request_id='reserved', now=fixtures.NOW)
        for number in range(3): self.fail(str(number))
        with self.assertRaises(SiteStopped):
            runtime.start_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], now=fixtures.NOW + 1)
        self.assertIsNone(runtime.snapshot()['attempts'][0]['started_at'])
        changed = {**self.binding, 'formal_since': fixtures.NOW + 100}
        with self.assertRaisesRegex(ValueError, '整站失败账'):
            runtime.update_policy({'site_failure_guard': changed}, 'CONTROLLED reset attempt', now=fixtures.NOW + 1)

    def test_formal_cutoff_excludes_old_activity(self):
        registry = fixtures.make_registry(self.root / 'old-production.sqlite3')
        runtime = RuntimeStore(registry, 'CONTROLLED-old-scope')
        runtime.initialize({'campaign_id': 'CONTROLLED-old-formal'}, now=fixtures.NOW)
        plan, publication = fixtures.make_plan(self.root / 'old-plan', count=1)
        runtime.enqueue_plan(plan, publication, now=fixtures.NOW)
        attempt = runtime.claim_next('worker', request_id='historical', now=fixtures.NOW)
        runtime.start_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], now=fixtures.NOW)
        runtime.finish_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], 'rejected',
            failure_class='program', root_cause='outside current chain time', now=fixtures.NOW + 1)
        newer = SiteFailureStore.initialize({**self.binding, 'ledger': str(self.root / 'later-stop.sqlite3'),
                                            'formal_since': fixtures.NOW + 10})
        runtime.update_policy({'site_failure_guard': newer.binding}, 'CONTROLLED explicit activation', now=fixtures.NOW + 10)
        runtime._sync_site_failures()
        self.assertEqual(newer.status('https://example.org/')['failure_count'], 0)

    def seeded(self):
        seed = {'failure_limit': 3, 'sites': []}
        for host, count in (('udi.nmpa.gov.cn', 4), ('search.dangdang.com', 1)):
            seed['sites'].append({'whole_application': 'https://' + host + '/',
                'failed_real_execution_count': count, 'stop': count >= 3,
                'attempts': [{'ledger': 'CONTROLLED-' + host + str(i) + '.sqlite3', 'job_id': 'job' + str(i),
                              'error_type': 'CONTROLLED failure', 'usage': 'UNKNOWN'} for i in range(count)]})
        path = self.root / 'policy.json'; path.write_text(json.dumps(seed))
        binding = {**self.binding, 'ledger': str(self.root / 'seeded.sqlite3')}
        return SiteFailureStore.initialize(binding, seed_policy=path, source_root=self.root)

    def test_seeded_udi_four_dangdang_one_and_local_adapter_gate(self):
        store = self.seeded()
        path = Path(__file__).resolve().parents[3] / 'verify_results/pilot1000-20261028-r01/pilot_execution_adapter_r01.py'
        spec = importlib.util.spec_from_file_location('CONTROLLED_pilot_adapter', path)
        adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
        binding = self.root / 'binding.json'; binding.write_text(json.dumps(store.binding))
        with self.assertRaises(SiteStopped):
            adapter.site_dispatch_guard(binding, {'site_uri': 'https://udi.nmpa.gov.cn/new?page=2'})
        self.assertEqual(adapter.site_dispatch_guard(binding, {'site_uri': 'https://search.dangdang.com/another'})['failure_count'], 1)
        self.assertEqual(store.status('https://udi.nmpa.gov.cn/')['failure_count'], 4)
        with self.assertRaises(FileExistsError): SiteFailureStore.initialize(store.binding)

    def test_observation_stop_precedes_gateway_browser_output_and_job(self):
        from webcollect import browser_planner
        store = self.seeded()
        intent = self.root / 'intent.json'; capability = self.root / 'capability.json'
        intent.write_text(json.dumps({'site_uri': 'https://udi.nmpa.gov.cn/new',
            'pilot_identity': {'application': {'canonical_uri': 'https://udi.nmpa.gov.cn/'}}}))
        capability.write_text('{}'); output = self.root / 'observation'
        with patch.object(browser_planner, 'validate_observation_intent'), \
                patch.object(browser_planner, 'ModelGateway', side_effect=AssertionError('No gateway construction')):
            with self.assertRaises(SiteStopped):
                asyncio.run(browser_planner.observe_task(object(), intent, capability, output,
                    site_failure_guard=store.binding))
        self.assertFalse(output.exists())

    def test_interrupted_seed_cannot_reopen_as_an_empty_or_lower_count(self):
        store = self.seeded()
        with store.connect(True) as con:
            con.execute('DELETE FROM site_executions WHERE application_key=?', (application_key('https://udi.nmpa.gov.cn/'),))
            con.commit()
        with self.assertRaisesRegex(ValueError, 'seed is incomplete'):
            SiteFailureStore(store.binding)


if __name__ == '__main__': unittest.main()
