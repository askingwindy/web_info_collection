"""Account explicit initial navigations before dispatch through the batch ledger.

Each goto, including a failed/retried goto, consumes one active visit. Browser
redirects and subresources are observed separately; a visit is not an HTTP count.
Action-triggered navigation remains in the collector's full network telemetry.
"""
import asyncio

from .batch_core import VisitRateWait
from .runtime import domain_key


class NavigationTimeoutError(TimeoutError):
    """A timeout while dispatching an explicitly accounted initial navigation."""
    def __init__(self, uri, purpose, timeout_seconds):
        self.uri, self.purpose, self.timeout_seconds = uri, purpose, timeout_seconds
        super().__init__(f'Initial navigation timed out after {timeout_seconds:g}s '
                         f'({purpose}): {uri}')


class NavigationHTTPError(ValueError):
    def __init__(self, uri, status):
        self.uri, self.status = uri, status
        super().__init__('Initial navigation HTTP status ' + str(status))


class BatchNavigation:
    def __init__(self, ledger, job):
        self.ledger, self.job = ledger, job

    def record_preflight_outcome(self, task, record, reference):
        """Settle the actual read-only probe before another task is dispatched."""
        binding = self.ledger.config.get('site_failure_guard')
        # A read-only preflight ERROR on a repeatedly unrenderable page still
        # convicts the site; an advisory REVIEW_REQUIRED routing flag is risk
        # information for QC, never a site failure or a collection gate.
        if (not binding or self.ledger.config['mode'] != 'real'
                or not record.get('error')):
            return
        from .site_failure_stop import SiteFailureStore, execution_id
        from .planning import verify_evidence
        from .batch_core import load_json
        verify_evidence([reference])
        if load_json(reference['path']) != record:
            raise ValueError('Preflight outcome differs from its original evidence')
        visits = [row for row in self.ledger.visits() if row['job_id'] == self.job['id']
                  and row['purpose'] == 'preflight:' + task['task_id']]
        if not visits or visits[-1]['state'] != 'succeeded':
            return  # Navigation failure/UNKNOWN already has its own original fact.
        visit = visits[-1]
        SiteFailureStore(binding).record(task, execution_id('preflight', self.ledger.path, visit['id']),
            stage='probe', state='failed', real_execution=True,
            reason=str(record.get('error') or record['summary']), evidence=[reference],
            usage_refs=[{'ledger': str(self.ledger.path), 'visit_id': visit['id']}])

    async def goto(self, page, uri, *, purpose, timeout_ms=30000):
        from .collect import verify_public_url
        from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
        from urllib.parse import urlsplit, urlunsplit
        verify_public_url(uri)
        while True:
            self.ledger.heartbeat(self.job)
            try:
                visit = self.ledger.reserve_visit(self.job, uri, purpose,
                    domain_key(uri), timeout_seconds=timeout_ms / 1000)
                break
            except VisitRateWait as wait:
                await asyncio.sleep(wait.seconds)
        metrics = {'scope': 'browser events during this explicit goto only',
                   'wait_until': 'domcontentloaded',
                   'request_events': 0, 'main_frame_navigation_events': 0,
                   'redirect_request_events': 0, 'main_document_response_events': 0,
                   'main_frame_committed': False, 'domcontentloaded_observed': False,
                   'failed_request_events': 0, 'failed_requests': [],
                   'frame_unavailable_events': 0}
        def diagnostic_uri(value):
            # Resource URLs can carry credentials or tracking query strings.
            parts = urlsplit(value)
            if parts.scheme not in ('http', 'https'):
                return parts.scheme + ':'
            return urlunsplit((parts.scheme, parts.netloc.rsplit('@', 1)[-1],
                               parts.path, '', ''))[:1000]
        def main_document(request):
            try:
                return request.is_navigation_request() and request.frame == page.main_frame
            except PlaywrightError:
                # Service-worker requests and not-yet-created navigation frames
                # have no frame. Optional diagnostics must not break navigation.
                metrics['frame_unavailable_events'] += 1
                return False
        def requested(request):
            metrics['request_events'] += 1
            if main_document(request):
                metrics['main_frame_navigation_events'] += 1
            if request.redirected_from is not None:
                metrics['redirect_request_events'] += 1
        def responded(event_response):
            if main_document(event_response.request):
                metrics['main_document_response_events'] += 1
                metrics['last_main_document_response'] = {
                    'status': event_response.status, 'uri': diagnostic_uri(event_response.url)}
        def navigated(frame):
            if frame == page.main_frame:
                metrics['main_frame_committed'] = True
                metrics['committed_uri'] = diagnostic_uri(frame.url)
        def content_loaded():
            metrics['domcontentloaded_observed'] = True
        def failed(request):
            metrics['failed_request_events'] += 1
            if len(metrics['failed_requests']) < 8:
                metrics['failed_requests'].append({'uri': diagnostic_uri(request.url),
                    'resource_type': request.resource_type, 'main_document': main_document(request),
                    'failure': (request.failure or '')[:240]})
        listeners = []
        response = None
        try:
            for event, callback in (('request', requested), ('response', responded),
                                    ('framenavigated', navigated), ('domcontentloaded', content_loaded),
                                    ('requestfailed', failed)):
                page.on(event, callback)
                listeners.append((event, callback))
            try:
                response = await asyncio.wait_for(page.goto(uri, wait_until='domcontentloaded',
                    timeout=max(1, int(visit['timeout_seconds'] * 1000))),
                    timeout=visit['timeout_seconds'])
            except (asyncio.TimeoutError, PlaywrightTimeoutError) as error:
                metrics['timeout_error_type'] = type(error).__name__
                raise NavigationTimeoutError(uri, purpose, visit['timeout_seconds']) from error
            if response is not None and response.status >= 400:
                raise NavigationHTTPError(uri, response.status)
        except BaseException as error:
            self.ledger.settle_visit(visit,
                state='unknown' if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)) else 'failed',
                # A response event may precede a DCL timeout. Preserve that
                # observation without turning the failed visit into success.
                response_status=(response.status if response is not None else
                    metrics.get('last_main_document_response', {}).get('status')),
                landed_uri=page.url, error=error, metrics=metrics)
            raise
        else:
            self.ledger.settle_visit(visit, state='succeeded',
                response_status=response.status if response is not None else None,
                landed_uri=page.url, metrics=metrics)
            return response
        finally:
            for event, callback in listeners:
                page.remove_listener(event, callback)
