"""Disposable ledger facts only: no real DB, capture, model, or legacy population."""
from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from webcollect.planning import object_sha256
from webcollect.site_failure_stop import SiteFailureStore, SiteStopped
from webcollect.runtime import RuntimeStore
import m4_runtime_fixtures as fixtures


class SiteFailurePortabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.binding = {'ledger': str(self.root / 'source.sqlite3'),
                        'campaign_id': 'CONTROLLED-portable', 'formal_since': fixtures.NOW - 1}
        self.source = SiteFailureStore.initialize(self.binding)

    def fail(self, store, number, state='failed'):
        return store.record('https://example.org/page-' + str(number), 'CONTROLLED-' + str(number),
            stage='observation', state=state, reason='CONTROLLED original outcome', real_execution=True,
            evidence=[{'sha256': 'a' * 64}], usage_refs=[])

    def target(self):
        return SiteFailureStore.initialize({**self.binding, 'ledger': str(self.root / 'receiving-machine.sqlite3')})

    def test_three_failures_before_first_valid_mark_unavailable_across_reopen(self):
        for number in range(3): self.fail(self.source, number)
        reopened = SiteFailureStore(self.binding)
        state = reopened.status('http://example.org/other?p=4')
        self.assertEqual(state['state'], 'unavailable')
        self.assertTrue(state['unavailable_before_first_valid'])
        self.assertEqual(state['qualified_success_count'], 0)
        self.assertFalse(state['automatic_round_reentry'])
        with self.assertRaises(SiteStopped): reopened.guard('https://example.org/fresh')
        self.assertEqual(reopened.status('https://next.example.org/')['state'], 'available')

    def test_portable_import_keeps_three_failures_and_is_idempotent(self):
        for number in range(3): self.fail(self.source, number)
        payload = self.source.export_facts()
        self.assertNotIn(str(self.root), str(payload))
        target = self.target()
        self.assertEqual(target.import_facts(payload)['imported_facts'], 3)
        self.assertEqual(target.import_facts(payload)['imported_facts'], 0)
        self.assertEqual(target.status('https://example.org/')['state'], 'unavailable')
        self.assertEqual(target.export_facts()['facts_sha256'], payload['facts_sha256'])
        self.assertEqual(target.status('https://example.org/')['failure_count'], 3)

    def test_import_cannot_reset_round_or_reclassify_original_unknown(self):
        self.fail(self.source, 0, 'unknown')
        target = self.target(); original = self.source.export_facts(); target.import_facts(original)
        changed = deepcopy(original); changed['executions'][0]['state'] = 'failed'
        core = {key: changed[key] for key in ('schema_version', 'campaign_id', 'formal_since', 'failure_limit', 'executions', 'successes')}
        changed['facts_sha256'] = object_sha256(core)
        with self.assertRaisesRegex(ValueError, 'reclassified'):
            target.import_facts(changed)
        wrong_round = deepcopy(original); wrong_round['campaign_id'] = 'OTHER-ROUND'
        wrong_round['facts_sha256'] = object_sha256({key: wrong_round[key] for key in core})
        with self.assertRaisesRegex(ValueError, 'no implicit new round'):
            target.import_facts(wrong_round)
        self.assertEqual(target.status('https://example.org/')['state'], 'unknown_hold')
        self.assertEqual(target.status('https://example.org/')['failure_count'], 0)

    def test_import_conflict_is_atomic_even_after_a_new_fact(self):
        self.fail(self.source, 0)
        target = self.target(); payload = self.source.export_facts(); target.import_facts(payload)
        self.fail(self.source, 1)
        changed = self.source.export_facts(); changed['executions'].reverse()
        next(fact for fact in changed['executions'] if fact['fact_id'] == 'CONTROLLED-0')['reason'] = 'Reclassified'
        core = {key: changed[key] for key in ('schema_version', 'campaign_id', 'formal_since', 'failure_limit', 'executions', 'successes')}
        changed['facts_sha256'] = object_sha256(core)
        with self.assertRaises(ValueError): target.import_facts(changed)
        self.assertEqual(target.status('https://example.org/')['failure_count'], 1)

    def test_unavailable_site_is_skipped_while_next_site_remains_dispatchable(self):
        for number in range(3): self.fail(self.source, number)
        registry = fixtures.make_registry(self.root / 'registry.sqlite3')
        policy = {'campaign_id': self.binding['campaign_id'], 'site_failure_guard': self.binding}
        first = RuntimeStore(registry, 'CONTROLLED-unavailable')
        first.initialize(policy, now=fixtures.NOW)
        plan, publication = fixtures.make_plan(self.root / 'first-planning')
        first.enqueue_plan(plan, publication, now=fixtures.NOW)
        self.assertIsNone(first.claim_next('worker', request_id='blocked', now=fixtures.NOW))
        second = RuntimeStore(registry, 'CONTROLLED-next-site')
        second.initialize(policy, now=fixtures.NOW)
        plan, publication = fixtures.make_plan(self.root / 'next-planning', task_prefix='next', uri='https://next.example.net/')
        second.enqueue_plan(plan, publication, now=fixtures.NOW)
        claimed = second.claim_next('next-worker', request_id='next', now=fixtures.NOW)
        self.assertEqual(claimed['task']['site_uri'], 'https://next.example.net/')
        self.assertEqual(self.source.status('https://example.org/')['state'], 'unavailable')

    def test_import_three_formal_failures_then_moved_registry_cannot_reset_or_double_count(self):
        registry = fixtures.make_registry(self.root / 'registry.sqlite3')
        runtime = RuntimeStore(registry, 'CONTROLLED-formal')
        runtime.initialize({'campaign_id': self.binding['campaign_id']}, now=fixtures.NOW)
        plan, publication = fixtures.make_plan(self.root / 'planning', count=3)
        runtime.enqueue_plan(plan, publication, now=fixtures.NOW)
        for number in range(3):
            now = fixtures.NOW + number * 3
            attempt = runtime.claim_next('worker', request_id=str(number), now=now)
            runtime.start_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], now=now)
            runtime.finish_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], 'rejected',
                failure_class='semantic', root_cause='CONTROLLED failed task ' + str(number), now=now + 1)
        self.source.sync_formal(registry, self.binding['campaign_id'])
        payload = self.source.export_facts(); target = self.target(); target.import_facts(payload)
        moved = self.root / 'other-machine-registry.sqlite3'; shutil.copy2(registry, moved)
        target.sync_formal(moved, self.binding['campaign_id'])
        self.assertEqual(target.status('https://example.org/')['failure_count'], 3)
        self.assertEqual(target.status('https://example.org/')['state'], 'unavailable')
        self.assertEqual(target.export_facts()['facts_sha256'], payload['facts_sha256'])

    def test_portable_cli_exports_and_imports_only_temporary_ledgers(self):
        import contextlib
        import io
        from webcollect.site_failure_stop import main
        for number in range(3): self.fail(self.source, number)
        target = self.target()
        artifact = self.root / 'portable-facts.json'
        common = ['--campaign-id', self.binding['campaign_id'], '--formal-since', str(self.binding['formal_since'])]
        with contextlib.redirect_stdout(io.StringIO()):
            main(['export', '--ledger', self.binding['ledger'], '--output', str(artifact), *common])
            main(['import', '--ledger', target.binding['ledger'], '--facts', str(artifact), *common])
        self.assertEqual(target.status('https://example.org/')['failure_count'], 3)
        self.assertEqual(target.status('https://example.org/')['state'], 'unavailable')

    def test_import_then_registry_copy_and_sync_does_not_recount_original_attempt(self):
        registry = fixtures.make_registry(self.root / 'original-registry.sqlite3')
        runtime = RuntimeStore(registry, 'CONTROLLED-scope')
        runtime.initialize({'campaign_id': self.binding['campaign_id']}, now=fixtures.NOW)
        plan, publication = fixtures.make_plan(self.root / 'planning')
        runtime.enqueue_plan(plan, publication, now=fixtures.NOW)
        attempt = runtime.claim_next('worker', request_id='original', now=fixtures.NOW)
        runtime.start_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], now=fixtures.NOW)
        runtime.finish_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], 'rejected',
            failure_class='interrupted', root_cause='CONTROLLED unknown cancellation', now=fixtures.NOW + 1)
        self.source.sync_formal(registry, self.binding['campaign_id'])
        payload = self.source.export_facts(); target = self.target(); target.import_facts(payload)
        moved = self.root / 'moved-registry.sqlite3'; shutil.copy2(registry, moved)
        target.sync_formal(moved, self.binding['campaign_id'])
        target.sync_formal(moved, self.binding['campaign_id'])
        state = target.status('https://example.org/')
        self.assertEqual(state['unknown_execution_count'], 1)
        self.assertEqual(state['failure_count'], 0)
        self.assertEqual(target.export_facts()['facts_sha256'], payload['facts_sha256'])


if __name__ == '__main__': unittest.main()
