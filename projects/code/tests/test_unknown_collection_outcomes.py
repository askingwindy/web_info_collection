"""Unknown execution outcomes never resend; temporary ledgers only, no browser/model."""
from pathlib import Path
import tempfile
import unittest

from webcollect.runtime import RuntimeStore
from webcollect.site_failure_stop import SiteFailureStore
import m4_runtime_fixtures as fixtures


class UnknownOutcomeTests(unittest.TestCase):
    def run_outcome(self, guarded, recovered=False, network=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = fixtures.make_registry(root / 'registry.sqlite3')
            policy = {'campaign_id': 'CONTROLLED-unknown', 'max_retries': 2}
            stop = None
            if guarded:
                stop = SiteFailureStore.initialize({'ledger': str(root / 'site-stop.sqlite3'),
                    'campaign_id': policy['campaign_id'], 'formal_since': fixtures.NOW - 1})
                policy['site_failure_guard'] = stop.binding
            store = RuntimeStore(registry, 'CONTROLLED-scope')
            store.initialize(policy, now=fixtures.NOW)
            plan, receipt = fixtures.make_plan(root / 'planning')
            store.enqueue_plan(plan, receipt, now=fixtures.NOW)
            first = store.claim_next('worker', request_id='first', now=fixtures.NOW)
            store.start_attempt(first['attempt_id'], 'worker', first['lease_token'], now=fixtures.NOW)
            if recovered:
                store.recover_expired(now=fixtures.NOW + 121)
            else:
                store.finish_attempt(first['attempt_id'], 'worker', first['lease_token'], 'rejected',
                    failure_class='network' if network else 'interrupted',
                    root_cause='CONTROLLED known transport failure' if network else 'CONTROLLED uncertain cancellation',
                    now=fixtures.NOW + 1)
            later = fixtures.NOW + 123
            replacement = store.claim_next('worker', request_id='later', now=later)
            ledger = store.attempt_ledger()
            self.assertEqual(ledger['actual_attempt_count'], 1)
            self.assertFalse(any(row['status'] in ('collected_pending_review', 'reviewed_pass', 'published')
                                 for row in ledger['attempts']))
            if network:
                self.assertIsNotNone(replacement)
                self.assertNotEqual(replacement['sample_id'], first['sample_id'])
            else:
                self.assertIsNone(replacement)
                self.assertEqual(store.snapshot()['tasks'][0]['status'], 'needs_replan')
                self.assertEqual(ledger['attempts'][0]['status'], 'interrupted' if recovered else 'rejected')
            if stop:
                state = stop.status(plan['tasks'][0])
                self.assertEqual(state['unknown_execution_count'], 0 if network else 1)
                self.assertEqual(state['failure_count'], 1 if network else 0)
                self.assertEqual(state['dispatch_blocked'], not network)

    def test_rejected_interrupted_does_not_retry_without_site_guard(self):
        self.run_outcome(False)

    def test_rejected_interrupted_counts_unknown_with_site_guard(self):
        self.run_outcome(True)

    def test_expired_started_lease_does_not_retry_without_site_guard(self):
        self.run_outcome(False, recovered=True)

    def test_expired_started_lease_counts_unknown_with_site_guard(self):
        self.run_outcome(True, recovered=True)

    def test_known_network_failure_remains_retryable_under_explicit_policy(self):
        self.run_outcome(True, network=True)


if __name__ == '__main__':
    unittest.main()
