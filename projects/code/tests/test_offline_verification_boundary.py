"""The verification boundary rejects history paths without opening payloads."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / 'scripts/verify_current_offline.py'
spec = importlib.util.spec_from_file_location('offline_boundary_runner', path)
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


class OfflineBoundaryTests(unittest.TestCase):
    def test_mock_stopall_cannot_disable_payload_guard(self):
        with runner.no_repository_history():
            mocked = patch('io.open'); mocked.start(); patch.stopall()
            for relative in ('request/web操作采集需求/samples/NEVER_OPEN',
                             'request/token/NEVER_OPEN', 'results/NEVER_OPEN'):
                with self.subTest(relative=relative), self.assertRaisesRegex(AssertionError, 'forbids'):
                    (runner.REPO / relative).is_file()
                with self.assertRaisesRegex(AssertionError, 'forbids'):
                    (runner.REPO / relative).read_bytes()

    def test_disposable_fixture_remains_usable(self):
        with tempfile.TemporaryDirectory() as directory, runner.no_repository_history():
            fixture = Path(directory) / 'literal.txt'
            fixture.write_text('SYNTHETIC offline fixture')
            self.assertEqual(fixture.read_text(), 'SYNTHETIC offline fixture')


if __name__ == '__main__': unittest.main()
