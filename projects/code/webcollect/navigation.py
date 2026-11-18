"""Account explicit initial navigations before dispatch through the batch ledger.

Each goto, including a failed/retried goto, consumes one active visit. Browser
redirects and subresources are observed separately; a visit is not an HTTP count.
Action-triggered navigation remains in the collector's full network telemetry.
"""
import asyncio


def native_form_encoding(form, source_url):
    """One native urlencoded calculation for dispatch and sealed replay."""
    import re
    from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
    if form.get('method') not in ('get','post') or form.get('enctype') != 'application/x-www-form-urlencoded':
        raise ValueError('NATIVE_FORM_ENCODING_UNSUPPORTED')
    fields=form.get('fields')
    if not isinstance(fields,list) or any(not isinstance(pair,list) or len(pair)!=2
            or any(not isinstance(value,str) for value in pair) for pair in fields):
        raise ValueError('NATIVE_FORM_ENCODING_UNSUPPORTED')
    normalize=lambda value:re.sub(r'\r\n|\r|\n','\r\n',value)
    encoded=urlencode([(normalize(key),normalize(value)) for key,value in fields],safe='*').replace('~','%7E')
    action=urlsplit(urljoin(source_url,form['action']))
    # Browser GET replaces the action query; POST retains it unchanged.
    return urlunsplit((action.scheme,action.netloc,action.path,
        encoded if form['method']=='get' else action.query,'')),encoded


def validate_http_chain(proof, initial_url, landed_url, *, source_url=None, operation_id=None):
    """Recheck a captured Request.redirected_from/Response chain, never aliases."""
    from urllib.parse import urldefrag, urljoin
    from .collect import verify_public_url
    if not isinstance(proof, dict) or proof.get('kind') != 'http_navigation':
        raise ValueError('HTTP_NAVIGATION_CHAIN_UNPROVEN')
    if (proof.get('initial_url') != initial_url or proof.get('landed_url') != landed_url
            or source_url is not None and proof.get('source_url') != source_url
            or operation_id is not None and proof.get('operation_id') != operation_id):
        raise ValueError('HTTP_NAVIGATION_SOURCE_UNPROVEN')
    rows = proof.get('requests')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise ValueError('HTTP_NAVIGATION_CHAIN_UNPROVEN')
    if urldefrag(rows[0].get('url', ''))[0] != urldefrag(initial_url)[0] or rows[-1].get('url') != urldefrag(landed_url)[0]:
        raise ValueError('HTTP_NAVIGATION_ENDPOINT_UNPROVEN')
    seen = set()
    for index, row in enumerate(rows):
        verify_public_url(row['url'])
        if (row.get('request_id') in seen or not row.get('request_id')
                or row.get('redirected_from') != (rows[index-1]['request_id'] if index else None)
                or row.get('response_request_id') != row['request_id']):
            raise ValueError('HTTP_NAVIGATION_REQUEST_LINK_UNPROVEN')
        seen.add(row['request_id'])
        status = row.get('status')
        if type(status) is not int:
            raise ValueError('HTTP_NAVIGATION_RESPONSE_UNPROVEN')
        if index < len(rows)-1:
            if (status not in (301,302,303,307,308) or not row.get('location')
                    or urldefrag(urljoin(row['url'], row['location']))[0] != rows[index+1]['url']):
                raise ValueError('HTTP_NAVIGATION_REDIRECT_UNPROVEN')
        elif not 200 <= status < 300:
            raise ValueError('HTTP_NAVIGATION_FINAL_RESPONSE_UNPROVEN')
    return True


async def capture_http_chain(response, initial_url, landed_url, *, source_url=None, operation_id=None,
                             observed_requests=None, page=None):
    """Serialize browser object links and original response headers without IO."""
    if response is None:
        raise ValueError('HTTP_NAVIGATION_RESPONSE_UNPROVEN')
    request = response.request
    if page is not None and request.frame != page.main_frame:
        raise ValueError('HTTP_NAVIGATION_FRAME_UNPROVEN')
    chain = []
    while request is not None:
        if request in chain or len(chain) >= 20:
            raise ValueError('HTTP_NAVIGATION_CHAIN_UNPROVEN')
        if observed_requests is not None and request not in observed_requests:
            raise ValueError('HTTP_NAVIGATION_DISPATCH_UNPROVEN')
        if not request.is_navigation_request():
            raise ValueError('HTTP_NAVIGATION_REQUEST_UNPROVEN')
        if page is not None and request.frame != page.main_frame:
            raise ValueError('HTTP_NAVIGATION_FRAME_UNPROVEN')
        chain.append(request)
        request = request.redirected_from
    chain.reverse()
    rows = []
    for index, request in enumerate(chain):
        reply = response if index == len(chain)-1 else await asyncio.wait_for(request.response(), timeout=2)
        if reply is None or reply.request is not request:
            raise ValueError('HTTP_NAVIGATION_RESPONSE_BINDING_UNPROVEN')
        headers = reply.headers
        rows.append({'request_id': str(index), 'redirected_from': str(index-1) if index else None,
            'response_request_id': str(index), 'url': request.url, 'method': request.method,
            'post_data': request.post_data, 'content_type': request.headers.get('content-type',''),
            'status': reply.status, 'location': headers.get('location')})
    proof = {'kind':'http_navigation','initial_url':initial_url,'landed_url':landed_url,
        'source_url':source_url,'operation_id':operation_id,'requests':rows}
    validate_http_chain(proof, initial_url, landed_url, source_url=source_url, operation_id=operation_id)
    return proof


def arm_http_navigation(page):
    """Listen before the single action; no request is dispatched by this watcher."""
    watcher = {'context':page.context,'requests':[],'responses':[]}
    def requested(request):
        if request.is_navigation_request():watcher['requests'].append(request)
    def responded(response):
        if response.request.is_navigation_request():watcher['responses'].append(response)
    watcher.update(request_listener=requested,response_listener=responded)
    page.context.on('request', requested)
    page.context.on('response', responded)
    return watcher


def close_http_navigation(watcher):
    if watcher:
        watcher['context'].remove_listener('request',watcher['request_listener'])
        watcher['context'].remove_listener('response',watcher['response_listener'])


async def finish_http_navigation(watcher, page, initial_url, *, source_url, operation_id):
    from urllib.parse import urldefrag
    for response in reversed(watcher['responses']):
        try:
            if response.request.frame != page.main_frame or response.url != urldefrag(page.url)[0]:continue
        except Exception:
            continue
        return await capture_http_chain(response,initial_url,page.url,source_url=source_url,
            operation_id=operation_id,observed_requests=watcher['requests'],page=page)
    raise ValueError('HTTP_NAVIGATION_RESPONSE_UNPROVEN')

from .batch_core import VisitRateWait
from .runtime import domain_key


class NavigationTimeoutError(TimeoutError):
    """A timeout while dispatching an explicitly accounted initial navigation."""
    failure_class = 'network'
    def __init__(self, uri, purpose, timeout_seconds):
        self.uri, self.purpose, self.timeout_seconds = uri, purpose, timeout_seconds
        super().__init__(f'Initial navigation timed out after {timeout_seconds:g}s '
                         f'({purpose}): {uri}')


class NavigationHTTPError(ValueError):
    failure_class = 'network'
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
            # Chromium reports transport errors with a native net::ERR code.
            # Preserve the exception and its diagnostics, but classify this
            # initial page failure as a site/network outcome.
            if 'net::ERR_' in str(error):
                error.failure_class = 'network'
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
