"""Controlled launch gates; every record here is synthetic, never human evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from webcollect.runtime import RuntimeStore, validate_policy
from webcollect.telemetry import NetworkMeter, start_phase, finish_phase
from m4_runtime_fixtures import make_registry


class ResourceGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = make_registry(self.root / 'registry.sqlite3')
        self.output = self.root / 'outputs' / 'batch'
        self.output.mkdir(parents=True)
        self.store = RuntimeStore(self.registry, 'scope-1')

    def test_storage_usage_is_metered_without_allocating_or_deleting(self):
        self.store.initialize({'resource_root': str(self.output.parent), 'max_output_bytes': 2})
        evidence = self.output / 'evidence.txt'; evidence.write_bytes(b'123')
        result = self.store.resource_checkpoint(self.output)
        self.assertEqual(result['status'], 'PASS')
        self.assertGreaterEqual(result['stored_bytes'],3)
        self.assertEqual(self.store.snapshot()['scope']['state'], 'active')
        self.assertEqual(self.store.snapshot()['attempts'], [])
        self.assertEqual(evidence.read_bytes(), b'123')
        with self.assertRaisesRegex(ValueError, '不能更换'):
            self.store.update_policy({'resource_root': str(self.root/'empty')}, 'Synthetic reset attempt')

    def test_free_disk_stop_and_out_of_root_rejection(self):
        from types import SimpleNamespace
        self.store.initialize({'resource_root': str(self.output.parent), 'min_free_disk_bytes': 10})
        with patch('shutil.disk_usage', return_value=SimpleNamespace(free=9)):
            self.assertEqual(self.store.resource_checkpoint(self.output)['status'], 'PASS')
        with patch('shutil.disk_usage', return_value=SimpleNamespace(free=0)):
            self.assertEqual(self.store.resource_checkpoint(self.output)['reasons'], ['disk_full'])
        with self.assertRaisesRegex(ValueError, 'resource_root'):
            self.store.resource_checkpoint(self.root / 'bypass')

    def test_worker_time_is_cumulative_across_scopes_and_unfinished_is_upper_bound(self):
        policy = {'max_worker_seconds': 5, 'resource_root': str(self.output.parent)}
        self.store.initialize(policy, now=100)
        self.store.worker_session('worker-first', self.output, now=100)
        self.store.worker_session('worker-first', self.output, finished=True, now=104)
        other = RuntimeStore(self.registry, 'scope-2'); other.initialize(policy, now=104)
        second = self.output.parent / 'batch-2'; second.mkdir()
        other.worker_session('worker-second', second, now=104)
        result = other.resource_checkpoint(second, now=106)
        self.assertEqual(result['campaign_worker_seconds'], 6)
        self.assertEqual(result['open_sessions'], ['worker-second'])
        self.assertEqual(result['status'], 'PASS')
        with self.assertRaisesRegex(ValueError, 'unique and ordered'):
            other.worker_session('worker-second', second, now=107)
        # Raising a budget is explicit; counters and previous events remain.
        other.update_policy({'max_worker_seconds': 20}, 'Synthetic operator budget adjustment', now=107)
        self.assertEqual(other.resource_checkpoint(second, now=108)['campaign_worker_seconds'], 8)
        self.assertEqual(other.snapshot()['scope']['state'], 'active')

    def test_historical_limits_accept_zero_and_reject_invalid_types(self):
        for value in [True, -1, 1.5]:
            with self.assertRaises(ValueError): validate_policy({'max_worker_seconds': value})
        self.assertEqual(validate_policy({'max_worker_seconds': 0})['max_worker_seconds'],0)
        self.assertIsNone(validate_policy({'max_output_bytes': 100})['resource_root'])
        with self.assertRaises(ValueError): validate_policy({'resource_root': 'relative'})


class PhaseTests(unittest.TestCase):
    def test_original_timing_and_unknown_usage_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / 'phases.jsonl'
            phase_id = start_phase(ledger, 'synthetic_review', scope={'not_real': True})
            first = ledger.read_bytes()
            finish_phase(ledger, phase_id)
            self.assertTrue(ledger.read_bytes().startswith(first))
            record = json.loads(ledger.read_text().splitlines()[-1])
            self.assertEqual(record['cost'], 'UNKNOWN'); self.assertEqual(record['usage'], 'UNKNOWN')
            with self.assertRaisesRegex(ValueError, 'no prior finish'):
                finish_phase(ledger, phase_id)

    def test_network_callback_write_loss_is_not_silently_accepted(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as directory:
            meter = NetworkMeter(MagicMock(), Path(directory)/'attempt', {'attempt_id':'synthetic'})
            with patch('webcollect.telemetry.append_event', side_effect=OSError('synthetic full disk')):
                meter.record('request','https://example.org/private?secret=do-not-save')
            with self.assertRaisesRegex(ValueError,'计量记录失败'):
                meter.ensure_recorded()
            summary = meter.close('synthetic_failure')
            self.assertEqual(summary['measurement_status'],'FAIL')
            self.assertEqual(summary['measurement_error'],'OSError')


class NetworkMeterBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_local_requests_status_failure_and_secret_redaction(self):
        import asyncio
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from playwright.async_api import async_playwright
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/drop'):
                    self.connection.close(); self.close_connection = True; return
                status = 429 if self.path.startswith('/limit') else 403 if self.path.startswith('/denied') else 500 if self.path.startswith('/server-error') else 200
                self.send_response(status); self.end_headers(); self.wfile.write(b'controlled local fixture')
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(channel='chrome', headless=True)
                    context = await browser.new_context()
                    meter = NetworkMeter(context, Path(directory) / 'attempt', {'attempt_id': 'SYNTHETIC_ONLY'})
                    page = await context.new_page()
                    base = 'http://127.0.0.1:' + str(server.server_port)
                    await page.goto(base + '/?private=DO_NOT_RETAIN_SECRET')
                    await page.evaluate("""async () => { await Promise.all(['/limit?token=DO_NOT_RETAIN_SECRET','/denied','/server-error','/drop'].map(p=>fetch(p).catch(()=>null))); }""")
                    await context.close()
                    summary = meter.close('synthetic_test_completed')
                    await browser.close()
                self.assertGreaterEqual(summary['counts']['request'], 5)
                self.assertGreaterEqual(summary['counts']['requestfailed'], 1)
                for code in ('200', '429', '403', '500'):
                    self.assertGreaterEqual(summary['response_statuses'][code], 1)
                text = meter.events.read_text()
                for secret in ('DO_NOT_RETAIN_SECRET', '/limit', '/denied', 'private='):
                    self.assertNotIn(secret, text)
                self.assertEqual(set(summary['request_hosts']), {'127.0.0.1'})
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close(); thread.join()


if __name__ == '__main__': unittest.main(verbosity=2)
