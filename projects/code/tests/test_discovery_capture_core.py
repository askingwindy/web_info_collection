"""Producer capture contracts with disposable files and no browser/network IO."""
import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from site_planner.discovery_tools import DiscoveryBrowser, reference
from site_planner.producer_read_policy import PENDING_IMAGES_SCRIPT, READINESS_SCRIPT, VERSION
from webcollect.batch_core import OutcomeUnknown
from webcollect.planning import verify_evidence


URI = 'https://example.org/article'
RAW_BODY = b'<html><body>original GET response</body></html>'


class CaptureFixture:
    def __init__(self, root, signatures, *, status=200, landed_uri=URI):
        self.root = Path(root).resolve()
        self.directory = self.root / 'page-offline-tool'
        self.events = []
        self.signatures = iter(signatures)
        self.observations = 0
        self.frame = 0
        self.pool = Mock()
        self.pool.reserve_tool.return_value = ('offline-tool', None)
        self.visit = {'id': 'offline-visit', 'timeout_seconds': 30,
                      'state': 'reserved_for_dispatch'}
        self.ledger = Mock(config={})
        self.ledger.enqueue.return_value = 'offline-job'
        self.ledger.claim.return_value = {'id': 'offline-job'}
        self.ledger.visits.return_value = [self.visit]
        self.response = SimpleNamespace(status=status, url=URI,
            request=SimpleNamespace(method='GET'), headers={'content-type': 'text/html'},
            body=AsyncMock(side_effect=self.body))
        self.page = SimpleNamespace(url=landed_uri,
            goto=AsyncMock(side_effect=self.goto), route=AsyncMock(),
            evaluate=AsyncMock(side_effect=self.evaluate),
            screenshot=AsyncMock(side_effect=self.screenshot),
            content=AsyncMock(side_effect=self.content), close=AsyncMock(),
            wait_for_timeout=AsyncMock(side_effect=self.wait),
            locator=Mock(return_value=SimpleNamespace(wait_for=AsyncMock(side_effect=self.wait))))
        self.context = SimpleNamespace(new_page=AsyncMock(return_value=self.page), close=AsyncMock())
        self.browser = DiscoveryBrowser(self.pool, self.ledger, 'offline-run', self.root,
            image_screen=True, capture_document=True, fresh_pages=True,
            read_policy=VERSION, frame_policy='producer-frame-sync-1')
        self.browser.browser = SimpleNamespace(new_context=AsyncMock(return_value=self.context))
        self.wait_ready = AsyncMock(side_effect=self.ready)

    async def goto(self, *args, **kwargs):
        self.events.append('goto')
        return self.response

    async def body(self):
        # Model the observed Playwright failure once page work has advanced.
        if self.events != ['goto']:
            raise RuntimeError('original response body no longer available')
        self.events.append('body')
        return RAW_BODY

    async def wait(self, *args, **kwargs):
        self.events.append('wait')

    async def ready(self, page):
        self.events.append('ready')
        return {'policy': VERSION, 'readiness_reason': 'offline_fixture'}

    async def evaluate(self, script):
        self.events.append('evaluate')
        if script == READINESS_SCRIPT:
            signature = next(self.signatures)
            return {'signature': signature, 'meaningful': bool(signature), 'pending_images': 0}
        if script == PENDING_IMAGES_SCRIPT:
            return 0
        if script == 'document.characterSet':
            return 'UTF-8'
        if 'title: document.title, landed_uri: location.href' in script:
            self.observations += 1
            return {'title': '离线正文', 'landed_uri': self.page.url,
                    'text': f'正文观察 {self.observations}', 'links': [], 'controls': []}
        return {'fixture_image_inventory': self.observations}

    async def screenshot(self, *, path, timeout):
        self.events.append('screenshot')
        if 'viewport-confirmed' in Path(path).name:
            self.frame += 1
        Path(path).write_bytes(('offline PNG ' + Path(path).name).encode())

    async def content(self):
        self.events.append('content')
        return f'<main>确认正文 {self.frame}</main>'

    def run(self):
        with ExitStack() as stack:
            stack.enter_context(patch('site_planner.producer_authority.check_producer_stop'))
            stack.enter_context(patch('site_planner.pipeline.reserve_visit_async',
                                      AsyncMock(return_value=self.visit)))
            stack.enter_context(patch('site_planner.discovery_tools.verify_public_url'))
            stack.enter_context(patch('site_planner.producer_read_policy.wait_ready', self.wait_ready))
            stack.enter_context(patch('site_planner.producer_read_policy.image_recheck_delay',
                                      return_value=(0, 'offline_fixture')))
            return asyncio.run(self.browser.read(URI))

    def load(self, name):
        return json.loads((self.directory / name).read_text())


class DiscoveryCaptureCore(unittest.TestCase):
    def test_original_body_is_saved_before_page_work_and_bound_to_document(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = CaptureFixture(root, ['stable', 'stable'])
            result = fixture.run()
            self.assertEqual(fixture.events[:2], ['goto', 'body'])
            fixture.response.body.assert_awaited_once()
            fixture.page.goto.assert_awaited_once_with(URI, wait_until='domcontentloaded', timeout=30000)
            fixture.wait_ready.assert_awaited_once()
            document = fixture.load('document.json')
            self.assertEqual(Path(document['raw_html']['path']).read_bytes(), RAW_BODY)
            self.assertEqual(document['response_uri'], result['landed_uri'])
            self.assertEqual(document['raw_html'], reference(fixture.directory / 'response-body.bin'))
            verify_evidence([result['observation'], result['image'], result['document'],
                             document['raw_html'], document['rendered_dom']])
            self.assertEqual(fixture.load('observation.json')['frame_capture']['confirmation_attempt'], 1)
            self.assertEqual(fixture.pool.settle_tool.call_args.args[1], 'succeeded')
            fixture.page.close.assert_awaited_once()
            fixture.context.close.assert_awaited_once()

    def test_one_local_recapture_keeps_first_failure_and_uses_second_frame(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = CaptureFixture(root, ['before', 'after', 'settled', 'settled'])
            result = fixture.run()
            observation = fixture.load('observation.json')
            failure = fixture.load('frame-confirmation-unstable.json')
            first = failure['frame_capture']
            final = observation['frame_capture']
            self.assertFalse(first['stable'])
            self.assertEqual(first['reason'], 'main_region_changed')
            self.assertEqual(Path(first['confirmed_image']['path']).name, 'viewport-confirmed.png')
            self.assertEqual(Path(first['rendered_dom']['path']).read_text(), '<main>确认正文 1</main>')
            self.assertEqual(failure['text'], '正文观察 2')
            self.assertTrue(final['stable'])
            self.assertEqual(final['confirmation_attempt'], 2)
            self.assertEqual(final['prior_unstable_frames'],
                             [reference(fixture.directory / 'frame-confirmation-unstable.json')])
            self.assertEqual(observation['text'], '正文观察 3')
            self.assertEqual(Path(result['image']['path']).name, 'viewport-confirmed-2.png')
            self.assertEqual((fixture.directory / 'rendered-dom.html').read_text(), '<main>确认正文 2</main>')
            verify_evidence([first['confirmed_image'], first['rendered_dom'],
                             *final['prior_unstable_frames'], result['image'], result['document']])
            self.assertFalse((fixture.directory / 'frame-confirmation-unstable-2.json').exists())
            self.assertEqual(fixture.wait_ready.await_count, 2)
            self.assertEqual(fixture.page.screenshot.await_count, 3)
            fixture.page.goto.assert_awaited_once()
            fixture.response.body.assert_awaited_once()
            fixture.pool.reserve_tool.assert_called_once()

    def test_persistent_changed_or_empty_main_region_fails_after_two_confirmations(self):
        cases = [(['a', 'b', 'c', 'd'], 'main_region_changed', 'Main business region changed'),
                 (['', '', '', ''], 'main_region_empty', 'Main business region has no visible')]
        for signatures, reason, message in cases:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as root:
                fixture = CaptureFixture(root, signatures)
                with self.assertRaisesRegex(ValueError, message):
                    fixture.run()
                for name in ('frame-confirmation-unstable.json', 'frame-confirmation-unstable-2.json'):
                    failed = fixture.load(name)['frame_capture']
                    self.assertFalse(failed['stable'])
                    self.assertEqual(failed['reason'], reason)
                    verify_evidence([failed['confirmed_image'], failed['rendered_dom']])
                self.assertFalse((fixture.directory / 'document.json').exists())
                self.assertFalse((fixture.directory / 'observation.json').exists())
                self.assertFalse((fixture.directory / 'viewport-confirmed-3.png').exists())
                self.assertEqual(fixture.page.screenshot.await_count, 3)
                self.assertEqual(fixture.wait_ready.await_count, 2)
                self.assertEqual(fixture.ledger.settle_visit.call_args.kwargs['state'], 'failed')
                self.assertNotEqual(fixture.pool.settle_tool.call_args.args[1], 'succeeded')
                fixture.page.goto.assert_awaited_once()
                fixture.response.body.assert_awaited_once()

    def test_changed_url_remains_unknown_with_original_body_retained(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = CaptureFixture(root, ['stable', 'stable'], landed_uri='https://example.org/other')
            with self.assertRaisesRegex(OutcomeUnknown, 'moved beyond the captured GET response'):
                fixture.run()
            self.assertEqual((fixture.directory / 'response-body.bin').read_bytes(), RAW_BODY)
            self.assertFalse((fixture.directory / 'document.json').exists())
            self.assertEqual(fixture.ledger.settle_visit.call_args.kwargs['state'], 'unknown')
            self.assertEqual(fixture.pool.settle_tool.call_args.args[1], 'unknown')
            fixture.page.goto.assert_awaited_once()
            fixture.response.body.assert_awaited_once()

    def test_confirmed_http_failure_keeps_fast_failure_without_body_or_screenshots(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = CaptureFixture(root, [], status=403)
            result = fixture.run()
            self.assertEqual(result['http_status'], 403)
            self.assertFalse(result['readable'])
            self.assertEqual(fixture.load('http-failure.json')['reason'], 'confirmed_http_failure_before_capture')
            self.assertEqual(fixture.ledger.settle_visit.call_args.kwargs['state'], 'failed')
            self.assertEqual(fixture.pool.settle_tool.call_args.args[1], 'failed')
            fixture.response.body.assert_not_awaited()
            fixture.page.screenshot.assert_not_awaited()
            fixture.wait_ready.assert_not_awaited()
            self.assertFalse((fixture.directory / 'response-body.bin').exists())


if __name__ == '__main__':
    unittest.main()
