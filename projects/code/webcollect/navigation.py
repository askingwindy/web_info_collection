"""Account explicit initial navigations before dispatch through the batch ledger.

Each goto, including a failed/retried goto, consumes one active visit. Browser
redirects and subresources are observed separately; a visit is not an HTTP count.
Action-triggered navigation remains in the collector's full network telemetry.
"""
import asyncio

from .batch_core import VisitRateWait
from .runtime import domain_key


class BatchNavigation:
    def __init__(self, ledger, job):
        self.ledger, self.job = ledger, job

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
            response = await asyncio.wait_for(page.goto(uri, wait_until='domcontentloaded',
                timeout=max(1, int(visit['timeout_seconds'] * 1000))),
                timeout=visit['timeout_seconds'])
            if response is not None and response.status >= 400:
                raise ValueError('Initial navigation HTTP status ' + str(response.status))
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
