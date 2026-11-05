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
        verify_public_url(uri)
        while True:
            self.ledger.heartbeat(self.job)
            try:
                visit = self.ledger.reserve_visit(self.job, uri, purpose,
                    domain_key(uri), timeout_seconds=timeout_ms / 1000)
                break
            except VisitRateWait as wait:
                await asyncio.sleep(wait.seconds)
        metrics = {'scope': 'request events during this explicit goto only',
                   'request_events': 0, 'main_frame_navigation_events': 0,
                   'redirect_request_events': 0}
        def requested(request):
            metrics['request_events'] += 1
            if request.is_navigation_request() and request.frame == page.main_frame:
                metrics['main_frame_navigation_events'] += 1
            if request.redirected_from is not None:
                metrics['redirect_request_events'] += 1
        listening = False
        response = None
        try:
            page.on('request', requested)
            listening = True
            try:
                response = await asyncio.wait_for(page.goto(uri, wait_until='domcontentloaded',
                    timeout=max(1, int(visit['timeout_seconds'] * 1000))),
                    timeout=visit['timeout_seconds'])
            except asyncio.TimeoutError as error:
                raise NavigationTimeoutError(uri, purpose, visit['timeout_seconds']) from error
            if response is not None and response.status >= 400:
                raise NavigationHTTPError(uri, response.status)
        except BaseException as error:
            self.ledger.settle_visit(visit,
                state='unknown' if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)) else 'failed',
                response_status=response.status if response is not None else None,
                landed_uri=page.url, error=error, metrics=metrics)
            raise
        else:
            self.ledger.settle_visit(visit, state='succeeded',
                response_status=response.status if response is not None else None,
                landed_uri=page.url, metrics=metrics)
            return response
        finally:
            if listening:
                page.remove_listener('request', requested)
