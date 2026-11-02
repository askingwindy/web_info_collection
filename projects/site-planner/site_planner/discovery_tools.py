"""Audited GLM search and fresh-profile read-only browser tools."""
import asyncio
from email.utils import parsedate_to_datetime
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit
import urllib.error
import urllib.request
import json
import re

from webcollect.batch_core import OutcomeUnknown, file_sha, save_json
from webcollect.collect import verify_public_url
from webcollect.planning import object_sha256, verify_evidence
from .site_pool import host_identity, page_uri

SEARCH_ENDPOINT = 'https://open.bigmodel.cn/api/paas/v4/web_search'


def search_channel_hold(pool, run_id):
    """A channel receipt is separate from unresolved request settlement."""
    with pool.connect() as con:
        rows = con.execute("SELECT id,run_id,state,result FROM tool_requests WHERE kind='search' ORDER BY started,id")
        for row in rows:
            result = json.loads(row['result'] or '{}')
            if str(result.get('provider_code')) == '1113' or (row['run_id']==run_id and row['state']=='unknown' and result.get('http_status') in (401,403)):
                return {'request_id':row['id'],'state':row['state'],
                        'reason':'search_channel_unavailable' if str(result.get('provider_code'))=='1113' else 'search_authorization_hold',
                        'http_status':result.get('http_status'),'provider_code':result.get('provider_code'),
                        'error_response':result.get('error_response')}
    return None


def reference(path):
    return {'path': str(Path(path).resolve()), 'sha256': file_sha(path)}


def glm_search(pool, run_id, model, query, output, *, engine='search_std', maximum=None, count=10, batch_scope=None):
    if not isinstance(query, str) or not 1 <= len(query) <= 70:
        raise ValueError('Search query must contain 1–70 characters')
    if type(count) is not int or not 1 <= count <= 50:
        raise ValueError('Search result count must be 1–50')
    # A previously issued query retains its original result size and receipt.
    identity = object_sha256([run_id, 'search', query])
    with pool.connect() as con:
        first = con.execute('SELECT payload FROM tool_requests WHERE id=?',(identity,)).fetchone()
    if not first and search_channel_hold(pool, run_id):
        raise OutcomeUnknown('Original search channel unavailable; no new dispatch')
    payload = {'search_engine': engine, 'search_query': query, 'search_intent': False,
               'count': json.loads(first[0])['count'] if first else count, 'content_size': 'medium'}
    rid, old = pool.reserve_tool(run_id, 'search', query, payload, maximum=maximum, batch_scope=batch_scope)
    if old is not None:
        verify_evidence([old['reference']])
        return old
    from webcollect.model_credentials import credential
    # Redirects must never carry the Authorization header to another host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    try:
        # Search remains a separate BigModel service even when Ark supplies the
        # model reasoning. Never send an Ark credential to the BigModel host.
        search_model = ({'provider': 'glm', 'api_key_env': 'GLM_API_KEY'}
                        if model.get('provider') == 'ark' else model)
        request = urllib.request.Request(SEARCH_ENDPOINT,
            json.dumps({**payload, 'request_id': rid}).encode(), headers={
                'Authorization': 'Bearer ' + credential(search_model), 'Content-Type': 'application/json'})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=45) as response:
            body = response.read(4_000_001)
        path = Path(output) / ('search-' + rid + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as handle:
            handle.write(body)
        if len(body) > 4_000_000:
            raise ValueError('Search response exceeds bounded size; saved prefix only')
        raw = json.loads(body)
        if not isinstance(raw.get('search_result'), list):
            detail = raw.get('error', {})
            if isinstance(detail, dict) and str(detail.get('code')) == '1113':
                pool.settle_tool(rid, 'unknown', {'http_status':200,'provider_code':'1113',
                    'error_response':reference(path),'outcome_and_charge':'UNKNOWN'})
                raise OutcomeUnknown('Search channel 1113; original receipt retained')
            raise ValueError('Search response has no structured result list')
        results = []; rejected = []
        for index, row in enumerate(raw['search_result']):
            try:
                uri = page_uri(row['link'])
            except (ValueError, KeyError, TypeError) as error:
                rejected.append({'index': index, 'reason': type(error).__name__})
                continue
            results.append({'index': index, 'uri': uri, 'title': row.get('title', ''),
                            'content': row.get('content', ''), 'reference': reference(path)})
        result = {'request_id': rid, 'query': query, 'results': results,
                  'raw_result_count': len(raw['search_result']), 'rejected_results': rejected,
                  'reference': reference(path), 'usage': raw.get('usage', 'UNKNOWN'),
                  'cost': 'UNKNOWN', 'cost_scope': 'search service, separate from model token cost'}
        pool.settle_tool(rid, 'succeeded', result)
        return result
    except Exception as error:
        # A structured 200 error has already been saved and settled above.
        if isinstance(error, OutcomeUnknown):
            raise
        result = {'error_type': type(error).__name__, 'http_status': getattr(error, 'code', None),
                  'outcome_and_charge': 'UNKNOWN'}
        if isinstance(error, urllib.error.HTTPError):
            # Keep the original provider response before closing it. A 429 can
            # mean account balance or rate limiting; neither authorizes a retry.
            try:
                body=error.read(65537)
                if body:
                    failure_path=Path(output)/('search-error-'+rid+'.json')
                    failure_path.parent.mkdir(parents=True,exist_ok=True)
                    with failure_path.open('xb') as handle:handle.write(body)
                    result['error_response']=reference(failure_path)
                    if len(body)<=65536:
                        raw_error=json.loads(body)
                        detail=raw_error.get('error',{}) if isinstance(raw_error,dict) else {}
                        if isinstance(detail,dict) and detail.get('code') is not None:
                            result['provider_code']=str(detail['code'])
            except (OSError,ValueError,TypeError):
                pass  # The original HTTP outcome and request identity still win.
        if result['http_status']==429:
            value=error.headers.get('Retry-After','') if error.headers else ''
            try:
                result['retry_after_seconds']=max(0,int(value) if value.isdigit() else
                                                   int(parsedate_to_datetime(value).timestamp()-time.time())+1)
            except (ValueError,TypeError,OverflowError):
                result['retry_after_seconds']=60
        pool.settle_tool(rid, 'unknown', result)
        if isinstance(error, urllib.error.HTTPError):
            error.close()
        raise OutcomeUnknown('Search outcome/charge UNKNOWN; original request retained: ' + rid) from None


class DiscoveryBrowser:
    def __init__(self, pool, ledger, run_id, output):
        self.pool, self.ledger, self.run_id = pool, ledger, run_id
        self.output = Path(output)

    async def __aenter__(self):
        from playwright.async_api import async_playwright
        self.pw = self.browser = self.context = None
        try:
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.launch(channel='chrome', headless=True)
            self.context = await self.browser.new_context(viewport={'width': 1280, 'height': 720},
                locale='zh-CN', service_workers='block', accept_downloads=False)
        except BaseException:
            await self.__aexit__()
            raise
        return self

    async def __aexit__(self, *args):
        try:
            if self.context:
                await asyncio.wait_for(self.context.close(), timeout=10)
        finally:
            try:
                if self.browser:
                    await asyncio.wait_for(self.browser.close(), timeout=10)
            finally:
                if self.pw:
                    await asyncio.wait_for(self.pw.stop(), timeout=5)

    async def read(self, uri):
        # Covers new_page, JS evaluation and screenshot as well as navigation.
        return await asyncio.wait_for(self._read(uri), timeout=60)

    async def _read(self, uri):
        from .pipeline import reserve_visit_async
        from webcollect.site_failure_stop import SiteFailureStore
        uri = page_uri(uri)
        rid, cached = self.pool.reserve_tool(self.run_id, 'browser', uri, {'uri': uri})
        if cached is not None:
            verify_evidence([cached['observation'], cached['image']])
            return cached
        jid = self.ledger.enqueue('site-discovery-page', {'uri': uri, 'run_id': self.run_id})
        job = None; page = None; visit = None
        directory = self.output / ('page-' + rid)
        nav_error = None; nav_code = None; status = None; redirects = []; blocked = []
        async def route(request_route):
            request = request_route.request
            try:
                if request.method not in ('GET', 'HEAD'):
                    raise ValueError('Read-only discovery blocks non-GET/HEAD requests')
                if request.url.startswith(('data:', 'blob:')):
                    await request_route.continue_(); return
                verify_public_url(request.url)
                if request.is_navigation_request() and request.frame == page.main_frame:
                    if self.ledger.config.get('site_failure_guard'):
                        SiteFailureStore(self.ledger.config['site_failure_guard']).guard(request.url)
                    redirects.append(request.url)
                await request_route.continue_()
            except Exception:
                blocked.append(request.url.split('?')[0]); await request_route.abort()
        try:
            if self.ledger.config.get('site_failure_guard'):
                SiteFailureStore(self.ledger.config['site_failure_guard']).guard(uri)
            job = self.ledger.claim('site-discovery-page', job_id=jid)
            if not job:
                raise OutcomeUnknown('Browser job is unresolved; original visit retained')
            page = await self.context.new_page()
            await page.route('**/*', route)
            directory.mkdir(parents=True, exist_ok=False)
            self.ledger.consume('probe_pages', jid)
            visit = await reserve_visit_async(self.ledger, job, uri, 'discovery-read')
            try:
                response = await page.goto(uri, wait_until='domcontentloaded', timeout=visit['timeout_seconds']*1000)
                status = response.status if response else None
            except Exception as error:
                nav_error = type(error).__name__
                codes = re.findall(r'net::ERR_[A-Z_]+', str(error))
                nav_code = codes[0] if codes else 'UNKNOWN'
            # Same-page bounded observation, no form entry, button dispatch or replay.
            try:
                await page.locator('body').wait_for(state='visible', timeout=5000)
            except Exception:
                pass
            await page.wait_for_timeout(1200)
            observation = await page.evaluate('''() => ({
                title: document.title, landed_uri: location.href,
                text: document.body ? document.body.innerText : '',
                links: Array.from(document.querySelectorAll('a[href]')).filter(e=>e.getClientRects().length)
                    .map(e=>({text:e.innerText,uri:e.href})),
                controls: Array.from(document.querySelectorAll('input:not([type=hidden]),textarea,select,button'))
                    .filter(e=>e.getClientRects().length).map(e=>({tag:e.tagName,type:e.type||'',
                        label:e.getAttribute('aria-label')||e.getAttribute('placeholder')||e.innerText||'',
                        disabled:e.disabled||false}))
            })''')
            try:
                verify_public_url(observation['landed_uri']); landed_public = True
            except ValueError:
                landed_public = False
            image = directory / 'viewport.png'; await page.screenshot(path=str(image), timeout=10000)
            observation.update({'requested_uri': uri, 'http_status': status if status is not None else 'UNKNOWN',
                'navigation_error': nav_error, 'redirect_observations': redirects, 'blocked_requests': blocked,
                'navigation_error_code': nav_code, 'landed_public_http': landed_public,
                'observed_at': time.time(), 'interaction_scope': 'navigation and reading only'})
            # Store full visible evidence; only a bounded subset is sent to the model.
            evidence_path = directory / 'observation.json'; save_json(evidence_path, observation)
            readable = landed_public and bool(observation['text'].strip()) and (status is None or status < 400)
            result = {'uri': uri, 'landed_uri': observation['landed_uri'], 'title': observation['title'],
                'readable': readable, 'same_application_host': landed_public and host_identity(uri) == host_identity(observation['landed_uri']),
                'observation': reference(evidence_path), 'image': reference(image),
                'navigation_error': nav_error, 'navigation_error_code': nav_code, 'http_status': observation['http_status']}
            self.ledger.settle_visit(visit, state='succeeded' if readable else 'failed',
                response_status=status, landed_uri=observation['landed_uri'],
                error=None if readable else ValueError('Page evidence not readable'), metrics={
                    'navigation_error': nav_error, 'redirect_request_events': max(0,len(redirects)-1),
                    'blocked_request_events': len(blocked)})
            self.pool.settle_tool(rid, 'succeeded', result)
            self.ledger.finish(job, result=result)
            return result
        except BaseException as error:
            failure = {'uri': uri, 'error_type': type(error).__name__, 'charge': 'UNKNOWN'}
            if visit and any(v['id'] == visit['id'] and v['state'] == 'reserved_for_dispatch' for v in self.ledger.visits()):
                self.ledger.settle_visit(visit, state='failed', error=error)
            self.pool.settle_tool(rid, 'failed', failure)
            if job:
                self.ledger.finish(job, 'review_required', result=failure, error=type(error).__name__)
            raise
        finally:
            if page:
                try:
                    await asyncio.wait_for(page.close(), timeout=5)
                except Exception:
                    pass  # Context/browser cleanup still has its own bounded finally.
            self.ledger.sync_visit_failures()
