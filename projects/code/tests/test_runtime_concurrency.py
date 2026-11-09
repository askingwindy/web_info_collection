"""Temporary scheduling rows only: no browser, evidence replay or model calls."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from webcollect.runtime import RuntimeStore
from webcollect.storage import ensure_registry_schema


class RuntimeConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.registry = Path(temporary.name) / 'registry.sqlite3'
        with sqlite3.connect(self.registry) as con:
            ensure_registry_schema(con)
        self.policy = {'campaign_id': 'scheduler-unit', 'max_workers': 3, 'max_domain_workers': 3}
        self.store = RuntimeStore(self.registry, 'unit')
        self.store.initialize(self.policy, now=1000)
        # Seed scheduling-only rows directly; these are not validated trajectories.
        with sqlite3.connect(self.registry) as con:
            for i in range(12):
                task = {'task_id': str(i), 'task_version': '1',
                        'site_uri': 'https://example.org/', 'site_category': '工具'}
                con.execute('INSERT INTO m4_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (str(i), 'unit', 'scheduler-unit', str(i), '1', 'unit-hash',
                             json.dumps(task), '工具', 'example.org', 'queued', 1, 5000, 1000, 1000))
                con.execute('INSERT INTO m4_plan_tasks VALUES(?,?,?,?)', ('unit', 'unit-plan', str(i), i))

    def claim(self, index, worker=None):
        return self.store.claim_next(worker or f'worker-{index}', request_id=f'request-{index}', now=1000)

    def test_live_change_removes_both_caps_without_mutating_policy_or_attempts(self):
        frozen = self.store.snapshot()['policy']
        first = [self.claim(i) for i in range(3)]
        self.assertTrue(all(first))
        self.assertIsNone(self.claim(3))
        self.store.set_consumer_concurrency(reason='isolated removal of three-worker ceilings')
        self.assertTrue(all(self.claim(i) for i in range(3, 10)))
        self.assertIsNone(self.claim(10, worker='worker-0'))  # Ownership is still exclusive.
        self.assertEqual(self.claim(0)['attempt_id'], first[0]['attempt_id'])
        self.assertEqual(self.store.snapshot()['policy'], frozen)
        reopened = RuntimeStore(self.registry, 'unit')
        reopened.initialize(self.policy, now=1001)  # Original startup binding remains valid.
        self.assertEqual(reopened.consumer_concurrency(), {'max_workers': None, 'max_domain_workers': None})
        self.assertEqual(len(reopened.snapshot()['attempts']), 10)

    def test_scope_shares_live_settings_but_other_campaign_does_not(self):
        self.store.set_consumer_concurrency(reason='isolated campaign setting')
        same = RuntimeStore(self.registry, 'peer')
        same.initialize(self.policy, now=1000)
        self.assertIsNone(same.consumer_concurrency()['max_workers'])
        other = RuntimeStore(self.registry, 'other')
        other.initialize({'campaign_id': 'different'}, now=1000)
        self.assertEqual(other.consumer_concurrency(), {'max_workers': 1, 'max_domain_workers': 1})
        same.set_consumer_concurrency(max_workers=1, max_domain_workers=1, reason='isolated live reduction')
        self.assertIsNotNone(self.claim(0))
        self.assertIsNone(self.claim(1))

    def test_repeated_setting_is_idempotent_and_invalid_limits_rejected(self):
        for _ in range(2):
            self.store.set_consumer_concurrency(reason='isolated setting')
        events = [row for row in self.store.snapshot()['events'] if row['event_type'] == 'consumer_concurrency']
        self.assertEqual(len(events), 1)
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.set_consumer_concurrency(max_workers=value)


if __name__ == '__main__':
    unittest.main()
