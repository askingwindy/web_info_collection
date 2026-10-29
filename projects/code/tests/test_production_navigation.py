import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from webcollect.batch_core import BatchLedger, BudgetStop, load_json
from webcollect.navigation import BatchNavigation, NavigationTimeoutError
from webcollect.collect_runtime import classify_failure, _root_cause


class Page:
    def __init__(self, ledger, status=200, error=None, delay=0):
        self.ledger, self.status, self.error, self.delay = ledger, status, error, delay
        self.calls, self.listeners, self.url = [], {}, 'about:blank'
        self.main_frame = object()

    def on(self, name, listener):
        self.listeners[name] = listener

    def remove_listener(self, name, listener):
        assert self.listeners.pop(name) == listener

    async def goto(self, uri, **kwargs):
        assert self.ledger.visits()[-1]['state'] == 'reserved_for_dispatch'
        self.calls.append((uri, kwargs))
        self.url = uri
        request = type('Request', (), {'frame': self.main_frame, 'redirected_from': None,
                     'is_navigation_request': lambda _: True})()
        self.listeners['request'](request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return type('Response', (), {'status': self.status})()


class ProductionNavigationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = load_json(Path(__file__).resolve().parents[1] / 'config/batch-no-model.json')
        from webcollect.site_failure_stop import SiteFailureStore
        import time
        config['site_failure_guard'] = SiteFailureStore.initialize({
            'ledger': str(self.root/'stop.sqlite3'), 'campaign_id': 'CONTROLLED-navigation',
            'formal_since': time.time()-1}).binding
        config['budget'].update(max_top_level_visits=2, min_domain_interval_seconds=1)
        self.ledger = BatchLedger(self.root / 'ledger.sqlite3', config, initialize=True)
        self.job = self.ledger.claim('test', job_id=self.ledger.enqueue('test', {'case': self._testMethodName}))
        self.navigation = BatchNavigation(self.ledger, self.job)

    async def test_preflight_and_collection_share_visit_cap_before_dispatch(self):
        page = Page(self.ledger)
        await self.navigation.goto(page, 'https://example.org/task', purpose='preflight:task')
        await self.navigation.goto(page, 'https://example.org/task', purpose='collection:sample')
        with self.assertRaisesRegex(BudgetStop, 'max_top_level_visits'):
            await self.navigation.goto(page, 'https://example.org/task', purpose='collection:retry')
        self.assertEqual(len(page.calls), 2)
        visits = self.ledger.visits()
        self.assertEqual([v['state'] for v in visits], ['succeeded', 'succeeded'])
        self.assertGreaterEqual(visits[1]['dispatched_at'] - visits[0]['dispatched_at'], 0.99)
        self.assertEqual(visits[0]['metrics']['main_frame_navigation_events'], 1)
        self.assertEqual(page.listeners, {})

    async def test_failed_dispatch_consumes_visit_and_keeps_error(self):
        page = Page(self.ledger, error=RuntimeError('transport failed'))
        with self.assertRaisesRegex(RuntimeError, 'transport failed'):
            await self.navigation.goto(page, 'https://example.org/task', purpose='preflight:task')
        self.assertEqual(self.ledger.visits()[0]['state'], 'failed')
        self.assertEqual(self.ledger.visits()[0]['error_type'], 'RuntimeError')
        self.assertEqual(page.listeners, {})

    async def test_http_error_is_not_a_successful_landing(self):
        page = Page(self.ledger, status=404)
        with self.assertRaisesRegex(ValueError, 'HTTP status 404'):
            await self.navigation.goto(page, 'https://example.org/missing', purpose='collection:sample')
        self.assertEqual(self.ledger.visits()[0]['response_status'], 404)
        self.assertEqual(self.ledger.visits()[0]['state'], 'failed')

    async def test_cancelled_dispatch_retains_unknown(self):
        page = Page(self.ledger, error=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await self.navigation.goto(page, 'https://example.org/task', purpose='collection:sample')
        self.assertEqual(self.ledger.visits()[0]['state'], 'unknown')
        self.assertEqual(page.listeners, {})

    async def test_deadline_bounds_the_entire_goto_even_if_page_ignores_timeout(self):
        page = Page(self.ledger, delay=1)
        with self.assertRaises(NavigationTimeoutError) as caught:
            await self.navigation.goto(page, 'https://example.org/task', purpose='preflight:task', timeout_ms=20)
        self.assertEqual(self.ledger.visits()[0]['state'], 'failed')
        self.assertEqual(self.ledger.visits()[0]['error_type'], 'NavigationTimeoutError')
        self.assertEqual(classify_failure(caught.exception), 'network')
        self.assertEqual(_root_cause(caught.exception), 'navigation_timeout')
        self.assertEqual(caught.exception.purpose, 'preflight:task')
        self.assertIsInstance(caught.exception.__cause__, TimeoutError)
        self.assertEqual(page.listeners, {})
        self.assertLessEqual(page.calls[0][1]['timeout'], 20)

    async def test_expired_run_does_not_dispatch(self):
        with self.ledger.transaction() as con:
            con.execute('UPDATE batch_meta SET started=started-?', (self.ledger.config['budget']['max_run_seconds'] + 1,))
        page = Page(self.ledger)
        with self.assertRaises(BudgetStop):
            await self.navigation.goto(page, 'https://example.org/task', purpose='preflight:task')
        self.assertEqual(page.calls, [])
        self.assertEqual(self.ledger.visits(), [])

    async def test_private_url_rejected_before_reservation(self):
        page = Page(self.ledger)
        with self.assertRaises(ValueError):
            await self.navigation.goto(page, 'http://127.0.0.1/task', purpose='preflight:task')
        self.assertEqual(page.calls, [])
        self.assertEqual(self.ledger.visits(), [])


if __name__ == '__main__':
    unittest.main()
