import unittest
from pathlib import Path
import tempfile
import json
from unittest.mock import patch
from webcollect.consumer_roster import build_roster
from webcollect.telemetry import preparation_phase


class ConsumerRosterTest(unittest.TestCase):
    def scope(self):
        return {k: k for k in ('pool','consumer_db','registry','output','policy','consumer_config','history_set','batch')}

    def test_ten_isolated_workers_original_shared_ledger(self):
        scope = self.scope()
        roster = build_roster(scope, 10, 'run-r02', job_limit=10, campaign_limit=10)
        self.assertEqual(len({w['scope']['consumer_worker'] for w in roster['workers']}), 10)
        self.assertEqual(len({w['scope']['request_prefix'] for w in roster['workers']}), 10)
        for worker in roster['workers']:
            for key, value in scope.items():
                self.assertEqual(worker['scope'][key], value)
        self.assertEqual(roster['workers'][-1]['number'], 10)
        self.assertEqual(roster['launch_state'], 'NOT_STARTED')

    def test_positive_worker_count_is_independent_of_historical_limits(self):
        for count in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                build_roster(self.scope(), count, 'r', job_limit=10, campaign_limit=10)
        for count, limits in ((11, (10, 10)), (10, (5, 10)), (10, (10, 5)), (20, (None, None))):
            roster = build_roster(self.scope(), count, 'r', job_limit=limits[0], campaign_limit=limits[1])
            self.assertEqual(len(roster['workers']), count)

    def test_timing_preserves_errors_and_does_not_create_capture(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'preparation-timings.jsonl'
            with self.assertRaisesRegex(RuntimeError, 'original'):
                with preparation_phase(path, 'validate'):
                    raise RuntimeError('original')
            row = json.loads(path.read_text())
            self.assertEqual(row['outcome'], 'RuntimeError')
            self.assertGreaterEqual(row['elapsed_seconds'], 0)
            self.assertFalse((Path(d) / 'capture').exists())
            with patch.object(Path, 'open', side_effect=OSError('no disk')):
                with preparation_phase(path, 'validate'):
                    pass
