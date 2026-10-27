"""Seeds/directory/search-template sources -> persistent rendered capabilities.

HTML-only signals never grant ready status. Every admitted capability binds all
representative original screenshots, probe results and visual review evidence.
Without a configured model, probing still runs and retains unresolved visual
requirements as review_required; it does not manufacture a screen approval.
Automatic task supply remains an estimate until collection succeeds.
"""
from collections import Counter
import asyncio
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from webcollect.batch_core import BudgetStop, OutcomeUnknown, VisitRateWait, file_sha, load_json, save_json
from webcollect.collect import verify_public_url, chinese_ratio
from webcollect.model_gateway import ModelGateway
from webcollect.planning import object_sha256, validate_capability
from webcollect.runtime import domain_key
from webcollect.bmi_strategy import BMI_INVENTORY_JS, ADAPTER_ID as BMI_ADAPTER_ID, matches_uri as bmi_matches_uri
from webcollect.date_strategy import DATE_INVENTORY_JS, ADAPTER_ID as DATE_ADAPTER_ID, matches_uri as date_matches_uri

VERSION = 'site-supply-6-observed-date-widget'


def normalize_uri(value):
    verify_public_url(value)
    p = urlsplit(value)
    host = p.hostname.encode('idna').decode().lower().rstrip('.')
    port = p.port
    host = '['+host+']' if ':' in host else host
    netloc = host if port is None or (p.scheme, port) in (('http', 80), ('https', 443)) else host + ':' + str(port)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith('utm_')]
    return urlunsplit((p.scheme.lower(), netloc, p.path or '/', urlencode(sorted(query)), ''))


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            value = dict(attrs).get('href')
            if value:
                self.hrefs.append(value)


def fetch_public(uri, *, timeout=20, metrics=None):
    verify_public_url(uri)
    metrics = metrics if metrics is not None else {}
    deadline = time.monotonic() + timeout
    class Redirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            verify_public_url(newurl)
            metrics['redirect_request_events'] = metrics.get('redirect_request_events',0) + 1
            metrics.setdefault('redirects',[]).append({'from':req.full_url,'to':newurl,'status':code})
            req.timeout = max(0.01, deadline-time.monotonic())
            if time.monotonic() >= deadline: raise TimeoutError('Source fetch total deadline reached during redirect')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    with build_opener(Redirects()).open(Request(uri, headers={'User-Agent': 'WebCollectSitePlanner/0.1'}), timeout=timeout) as response:
        metrics.update(response_status=response.status,landed_uri=response.url)
        verify_public_url(response.url)
        if response.status != 200 or 'html' not in response.headers.get('Content-Type', ''):
            raise ValueError('Directory source requires accessible HTML')
        chunks = []; size = 0
        while size <= 2_000_000:
            remaining = deadline-time.monotonic()
            if remaining <= 0: raise TimeoutError('Source fetch total deadline reached reading body')
            # Keep each network read within the original whole-fetch deadline.
            try: response.fp.raw._sock.settimeout(remaining)
            except AttributeError: pass
            part = response.read1(min(65536,2_000_001-size))
            if not part: break
            chunks.append(part); size += len(part)
        body = b''.join(chunks)
        if len(body) > 2_000_000:
            raise ValueError('Directory exceeds bounded HTML size')
        return body.decode(response.headers.get_content_charset() or 'utf-8', errors='replace'), response.url


def reserve_visit(ledger, job, uri, purpose):
    while True:
        ledger.heartbeat(job)
        try: return ledger.reserve_visit(job,uri,purpose,domain_key(uri))
        except VisitRateWait as wait: time.sleep(wait.seconds)


async def reserve_visit_async(ledger, job, uri, purpose):
    while True:
        ledger.heartbeat(job)
        try: return ledger.reserve_visit(job,uri,purpose,domain_key(uri))
        except VisitRateWait as wait: await asyncio.sleep(wait.seconds)


async def bounded(ledger, coroutine):
    try: timeout = ledger.remaining_seconds()
    except BaseException:
        coroutine.close();raise
    try: return await asyncio.wait_for(coroutine, timeout=timeout)
    except asyncio.TimeoutError as error:
        if ledger.remaining_seconds() <= 0.05: raise BudgetStop('max_run_seconds reached during browser operation') from error
        raise


def discover(ledger, sources_path, output):
    sources = load_json(sources_path)
    if sources.get('schema_version') != 'webcollect-site-sources-1' or not sources.get('sources'):
        raise ValueError('Nonempty versioned discovery sources required')
    for source in sources['sources']:
        if 'max_candidates' in source and (type(source['max_candidates']) is not int or source['max_candidates'] < 1):
            raise ValueError('Source max_candidates must be a positive integer')
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    save_json(output/'sources-frozen.json', sources)
    jid = ledger.enqueue('discovery', {'source_sha256': file_sha(sources_path), 'version': VERSION,
                                     'output': str(output)})
    job = ledger.claim('discovery', job_id=jid)
    if not job:
        prior = ledger.get(jid)
        if prior['state'] == 'done':
            return prior['result']
        return {'job_id': jid, 'stopped': prior['state']}
    candidates, rejects, source_errors, occurrences = {}, [], [], 0
    deferred, source_summaries, unprocessed_sources = [], [], []
    selection_stopped = False
    try:
        for number, source in enumerate(sources['sources']):
            if selection_stopped or len(candidates) >= ledger.config['budget']['max_discovery_candidates']:
                unprocessed_sources.append({'index':number, 'source':source,
                    'reason':'global candidate selection limit reached; source not fetched',
                    'link_occurrences':len(source.get('uris',[])) if source.get('kind')=='seed' else 'UNKNOWN'})
                continue
            if source.get('kind') not in ('seed', 'directory', 'search-template', 'synthetic-directory') or not source.get('category'):
                raise ValueError('Discovery source kind/category required')
            ledger.heartbeat(job)
            if source['kind'] == 'seed':
                uris = source.get('uris', []); base = None; source_ref = {'kind': 'seed', 'source_sha256': file_sha(sources_path)}
            else:
                if source['kind'] == 'synthetic-directory':
                    if ledger.config['mode'] != 'synthetic':
                        raise ValueError('Synthetic directory cannot enter a real run')
                    html = source['html']; base = normalize_uri(source['base_uri'])
                else:
                    if ledger.config['mode'] != 'real':
                        raise ValueError('Synthetic runs cannot fetch public sources')
                    uri = source.get('uri') if source['kind']=='directory' else source['url_template'].format(q=quote(source['query']))
                    uri = normalize_uri(uri)
                    source_file = output / ('source-' + str(number) + '.json')
                    failure_file=output/('source-failure-'+str(number)+'.json')
                    if failure_file.exists():
                        source_errors.append(load_json(failure_file));continue
                    ledger.consume('probe_pages', jid + ':source:' + str(number))
                    if source_file.exists():
                        cached = load_json(source_file); html, base = cached['html'], cached['landed_uri']
                    else:
                        visit = reserve_visit(ledger, job, uri, 'source:'+str(number)); metrics = {}
                        try:
                            html, base = fetch_public(uri,timeout=visit['timeout_seconds'],metrics=metrics)
                            ledger.settle_visit(visit,state='succeeded',response_status=metrics.get('response_status',200),landed_uri=base,metrics=metrics)
                            save_json(source_file, {'uri': uri, 'landed_uri': base, 'html': html,'visit_id':visit['id']})
                        except Exception as error:
                            if not any(v['id']==visit['id'] and v['state']!='reserved_for_dispatch' for v in ledger.visits()):
                                ledger.settle_visit(visit,state='failed',response_status=metrics.get('response_status',getattr(error,'code',None)),
                                    landed_uri=metrics.get('landed_uri',getattr(error,'url',None)),error=error,metrics=metrics)
                            failure={'source':uri,'reason':type(error).__name__,'error_message':str(error),'visit_id':visit['id'],
                                'response_status':metrics.get('response_status',getattr(error,'code',None)),
                                'landed_uri':metrics.get('landed_uri',getattr(error,'url',None))}
                            if hasattr(error,'close'):error.close()
                            save_json(output/('source-failure-'+str(number)+'.json'),failure)
                            source_errors.append(failure); continue
                parser = Links(); parser.feed(html); uris = [urljoin(base, href) for href in parser.hrefs]
                source_ref = {'kind': source['kind'], 'uri': base, 'content_sha256': object_sha256(html)}
            source_selected = 0
            for raw in uris:
                occurrences += 1
                try:
                    uri = normalize_uri(raw)
                except ValueError as error:
                    rejects.append({'uri': raw, 'source': source_ref, 'reason': str(error)}); continue
                if source.get('allowed_domains') and urlsplit(uri).hostname not in source['allowed_domains']:
                    rejects.append({'uri': uri, 'source': source_ref, 'reason': 'outside configured source domain scope'}); continue
                if uri not in candidates:
                    if source_selected >= source.get('max_candidates', len(uris)) or selection_stopped:
                        deferred.append({'uri':uri,'source':source_ref,'reason':
                            'global candidate selection limit reached' if selection_stopped else 'source max_candidates reached'})
                        continue
                    try:
                        ledger.consume('discovery_candidates', jid + ':candidate:' + object_sha256(uri))
                    except BudgetStop as error:
                        if 'max_discovery_candidates' not in str(error):
                            raise
                        selection_stopped = True
                        deferred.append({'uri':uri,'source':source_ref,'reason':'global candidate selection limit reached'})
                        continue
                    save_json(output/'discovered-links'/(str(occurrences).zfill(6)+'.json'),
                              {'uri':uri,'source':source_ref,'category':source['category']})
                    candidates[uri] = {'site_uri': uri, 'site_category': source['category'], 'source': [],
                                       'discovered_at': datetime.fromtimestamp(job['created'],timezone.utc).isoformat()}
                    source_selected += 1
                if source_ref not in candidates[uri]['source']:
                    candidates[uri]['source'].append(source_ref)
            source_summaries.append({'index':number,'link_occurrences':len(uris),
                                     'new_candidates':source_selected,'max_candidates':source.get('max_candidates')})
        result = {'schema_version': 'webcollect-site-candidates-1', 'mode': ledger.config['mode'],
                  'version': VERSION, 'input_source_sha256': file_sha(sources_path), 'records': list(candidates.values()),
                  'discovery_link_occurrences': occurrences, 'rejected_sources_or_links': rejects,
                  'source_errors': source_errors, 'fixed_candidate_count': len(candidates),
                  'deferred_links':deferred, 'source_summaries':source_summaries,
                  'unprocessed_sources':unprocessed_sources,
                  'candidate_selection_truncated':bool(deferred or unprocessed_sources),
                  'source_manifest':str(output/'sources-frozen.json'),
                  'link_denominator_complete':not unprocessed_sources and not source_errors,
                  'independent_host_count': len({urlsplit(uri).hostname for uri in candidates}),
                  'traffic_domain_groups': len({domain_key(uri) for uri in candidates}),
                  'sample_ids_allocated': 0, 'real_supply_verified': False}
        save_json(output / 'candidates.json', result)
        result={'candidate_file':str(output/'candidates.json'),**result}
        ledger.finish(job,result=result)
        return result
    except BudgetStop as error:
        partial={'records':list(candidates.values()),'rejected_sources_or_links':rejects,
                 'source_errors':source_errors,'link_occurrences_seen':occurrences,'stopped':str(error)}
        save_json(output/('partial-'+object_sha256(partial)[:16]+'.json'),partial)
        ledger.finish(job, 'queued', error=str(error))
        return {'job_id': jid, 'stopped': str(error), 'retained_denominator': 'source input and resource reservations retained'}
    except Exception as error:
        ledger.finish(job, 'failed', error=type(error).__name__); raise


# Selectors are an unexecuted inventory, not an assertion that controls can be
# operated. Runtime rechecks original labels, focus, clipping and hit testing.
INVENTORY_JS = r'''() => {
 const bmi=(''' + BMI_INVENTORY_JS + r''')();
 const date=(''' + DATE_INVENTORY_JS + r''')();
 const clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const selector=e=>e.id?'#'+CSS.escape(e.id):e.tagName.toLowerCase()+
   (e.name?'[name="'+CSS.escape(e.name)+'"]':':nth-of-type('+([...e.parentNode.children].filter(x=>x.tagName===e.tagName).indexOf(e)+1)+')');
 return {title:document.title,widgets:[...bmi.widgets,...date.widgets],widget_rejections:[...bmi.widget_rejections,...date.widget_rejections],
   result_targets:[...document.querySelectorAll('output,[role="status"],[aria-live],#result')]
   .filter(e=>e.checkVisibility()).map(e=>({selector:selector(e),text:clean(e.innerText)})).concat(bmi.result_targets,date.result_targets),
   forms:[...document.forms].map(f=>({
   label:clean(f.getAttribute('aria-label')||f.querySelector('legend,h1,h2,h3')?.innerText||document.title),
   fields:[...f.elements].filter(e=>['INPUT','TEXTAREA','SELECT','BUTTON'].includes(e.tagName)).map(e=>({
     selector:selector(e),tag:e.tagName.toLowerCase(),type:e.type||'',name:e.name||'',
     label:clean(e.labels?.[0]?.innerText||e.innerText||e.placeholder||''),
     visible:!!e.checkVisibility()&&e.getBoundingClientRect().bottom>0&&e.getBoundingClientRect().top<innerHeight,
     min:e.min||'',max:e.max||'',value:e.value||'',options:e.options?[...e.options].map(o=>({label:o.text,value:o.value})):[]}))})),
 links:[...document.querySelectorAll('a[href]')].filter(e=>e.checkVisibility()).map(e=>({label:clean(e.innerText),uri:e.href})).filter(e=>e.label).slice(0,50)};
}'''

SCREEN_SCHEMA = {'type': 'object', 'properties': {
    'status': {'type':'string','enum': ['ready', 'rejected', 'review_required']}, 'reason': {'type': 'string'},
    'page_observations': {'type': 'array', 'items': {'type': 'string'}}},
    'required': ['status', 'reason', 'page_observations'], 'additionalProperties': False}


def inventory_support(uri, inventories):
    """Register actions/workflows only for the exact observed candidate page.

    Same-host navigation says nothing about task-page equivalence. A different
    landed page, or a widget copied from another page, cannot extend this scope.
    This is mechanical inventory support; it never changes screening status.
    """
    forms, fields, widget_fields, controls = [], [], [], []
    for inventory in inventories:
        if normalize_uri(inventory['page_uri']) != uri:
            raise ValueError('Observed inventory is outside the exact candidate page scope')
        widgets = inventory.get('widgets', [])
        for widget in widgets:
            matcher = {BMI_ADAPTER_ID: bmi_matches_uri, DATE_ADAPTER_ID: date_matches_uri}.get(widget.get('adapter_id'))
            if (matcher is None or
                    not matcher(uri) or not matcher(widget.get('page_uri', '')) or
                    normalize_uri(widget['page_uri']) != uri):
                raise ValueError('Typed widget is unregistered or outside its observed page scope')
            widget_fields.extend(field for field in widget['fields']
                                 if field['visible'] and field.get('enabled') is True)
        controls.extend(e for e in inventory['elements'] if e.get('clickable') or e.get('inputable'))
        for form in inventory['forms'] + widgets:
            visible = [field for field in form['fields'] if field['visible']]
            fields.extend(visible)
            if (sum(field['tag'] in ('input', 'textarea') and field['type'] in
                    ('text', 'number', 'textarea', 'search', 'email', 'url', 'tel') for field in visible) >= 2
                    and any(field['type'] in ('submit', 'button') for field in visible)):
                forms.append(form)
    actions = {'scroll'}
    if controls or any(field['type'] in ('submit', 'button') for field in widget_fields):
        actions.add('click')
    if (any(element.get('inputable') for element in controls) or
            any(field['tag'] in ('input', 'textarea') and field['type'] in
                ('text', 'number', 'textarea', 'search', 'email', 'url', 'tel') for field in widget_fields)):
        actions.update(('click', 'type', 'hotkey'))
    if any(field['tag'] == 'select' for field in fields):
        actions.add('select')
    return controls, forms, sorted(actions)


async def probe(ledger, candidates_path, output, *, fixture_pages=None):
    from playwright.async_api import async_playwright
    from webcollect.preflight import inspect_page
    from webcollect.browser import observe
    candidates = load_json(candidates_path)
    if candidates.get('schema_version') != 'webcollect-site-candidates-1' or candidates.get('mode') != ledger.config['mode']:
        raise ValueError('Candidates/mode mismatch')
    if ledger.config['mode']=='synthetic' and fixture_pages is None:
        raise ValueError('Synthetic probe requires the dedicated controlled integration fixture runner')
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    records, stopped = [], None
    gateway = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True)
        context = await browser.new_context(viewport={'width':1280,'height':720},device_scale_factor=1,locale='zh-CN')
        try:
            for candidate in candidates['records']:
                uri = normalize_uri(candidate['site_uri'])
                jid = ledger.enqueue('site-probe', {'candidate': candidate, 'version': VERSION,
                    'output': str(output), 'mode': ledger.config['mode'],
                    'fixture_sha256': object_sha256(fixture_pages.get(uri)) if fixture_pages else None})
                old = ledger.get(jid)
                if old['state']=='done':
                    record = old['result']; validate_capability(record, require_ready=False)
                    records.append(record); continue
                try:
                    # Rate enforcement belongs to each actual dispatch, not to
                    # the logical job (which can fetch two pages or hit cache).
                    job = ledger.claim('site-probe', job_id=jid)
                except BudgetStop as error:
                    stopped = str(error); break
                if not job:
                    prior = ledger.get(jid)
                    records.append({**(prior['result'] or {'site_uri':uri}),'status':prior['state'],'reason':prior['error']}); continue
                page = await context.new_page(); directory = output / jid
                directory.mkdir(parents=True, exist_ok=True)
                urls, pages, images, capabilities, visit_ids = [uri], [], [], [], []
                try:
                    # A candidate denotes one task page. Arbitrary same-host
                    # links (often a home page) need their own candidate probe.
                    for index, target in enumerate(urls):
                        ledger.heartbeat(job)
                        cache_file = directory / ('page-cache-'+str(index)+'.json')
                        visit = None; metrics = {}; response_status = None; landed_uri = None
                        if cache_file.exists():
                            cached = load_json(cache_file)
                            if any(file_sha(path)!=digest for path,digest in cached['files_sha256'].items()):
                                raise ValueError('Cached probe evidence changed')
                            result, inventory = load_json(cached['result_path']),load_json(cached['inventory_path'])
                            evidence_dir = Path(cached['result_path']).parent
                            response_status,landed_uri = cached['response_status'],cached['landed_uri']
                            if cached['visit_id']:visit_ids.append(cached['visit_id'])
                        else:
                            ledger.consume('probe_pages',jid+':page:'+str(index))
                            if fixture_pages is None:
                                verify_public_url(target)
                                visit = await reserve_visit_async(ledger,job,target,'probe-page:'+str(index))
                                visit_ids.append(visit['id'])
                            attempt = visit['attempt_index'] if visit else ledger.get(jid)['attempts']
                            evidence_dir = directory / ('page-'+str(index)) / ('attempt-'+str(attempt).zfill(3))
                            evidence_dir.parent.mkdir(parents=True,exist_ok=True)
                            def on_request(request):
                                metrics['observed_request_events']=metrics.get('observed_request_events',0)+1
                                if request.is_navigation_request() and request.frame==page.main_frame:
                                    metrics['top_level_navigation_request_events']=metrics.get('top_level_navigation_request_events',0)+1
                                    if request.redirected_from is not None:
                                        metrics['redirect_request_events']=metrics.get('redirect_request_events',0)+1
                                else:
                                    metrics['subresource_or_child_frame_request_events']=metrics.get('subresource_or_child_frame_request_events',0)+1
                            if visit:page.on('request',on_request)
                            error = None
                            try:
                                if fixture_pages is not None:
                                    await bounded(ledger,page.set_content(fixture_pages[target]))
                                else:
                                    response = await bounded(ledger,page.goto(target,wait_until='domcontentloaded',timeout=visit['timeout_seconds']*1000))
                                    response_status = response.status if response else None;landed_uri=page.url
                                    verify_public_url(page.url)
                                    if not response or response_status>=400: raise ValueError('Page inaccessible: HTTP '+str(response_status))
                                task={'task_id':jid+'-'+str(index),'site_uri':uri,'initial_url':target,
                                      'instruction':'只读站点能力探测','content_preparation':False,'operations':[{'action_type':'wait'}]}
                                result = await bounded(ledger,inspect_page(page,task,evidence_dir,samples=2,interval_ms=100,
                                    url_check=verify_public_url if fixture_pages is None else None))
                                state = await bounded(ledger,observe(page))
                                inventory={'page_uri':normalize_uri(landed_uri) if landed_uri else target,
                                    'requested_uri':target,'landed_uri':landed_uri,'visible_text':state['visible_text'],
                                    'elements':state['elements'],**await bounded(ledger,page.evaluate(INVENTORY_JS))}
                                inventory_file=evidence_dir/'inventory.json';save_json(inventory_file,inventory)
                                metrics['rendered_inventory_saved']=True
                                save_json(cache_file,{'result_path':str(evidence_dir/'result.json'),'inventory_path':str(inventory_file),
                                    'response_status':response_status,'landed_uri':landed_uri,
                                    'visit_id':visit['id'] if visit else None,
                                    'files_sha256':{str(path):file_sha(path) for path in (evidence_dir/'result.json',inventory_file)}})
                            except BaseException as caught:
                                error=caught
                                evidence_dir.mkdir(parents=True,exist_ok=True)
                                save_json(evidence_dir/'visit-failure.json',{'target_uri':target,'visit_id':visit['id'] if visit else None,
                                    'response_status':response_status,'landed_uri':landed_uri,'error_type':type(caught).__name__,'error_message':str(caught)})
                                raise
                            finally:
                                if visit:
                                    page.remove_listener('request',on_request)
                                    ledger.settle_visit(visit,state='failed' if error else 'succeeded',response_status=response_status,
                                        landed_uri=landed_uri,error=error,metrics=metrics)
                        inventory_support(uri, [inventory])
                        pages.append({'uri':target,'landed_uri':landed_uri,'response_status':response_status,
                            'accessible':response_status is not None and response_status<400,'rendered':True,
                            'chinese_ratio':chinese_ratio(inventory['visible_text']),'routing':result['summary']['routing'],'error':result['error']})
                        images += [evidence_dir/f['path'] for f in result['frames']];capabilities.append(inventory)
                    evidence=[{'path':str(path),'sha256':file_sha(path)} for path in sorted(directory.rglob('*')) if path.is_file()]
                    controls, forms, actions = inventory_support(uri, capabilities)
                    chinese_controls=[e for e in controls if chinese_ratio(e.get('text',''))>=0.7]
                    cheap_reject=any(r['chinese_ratio']<0.7 or r['error'] for r in pages) or not chinese_controls
                    response={'status':'rejected' if cheap_reject else 'ready','reason':'Controlled synthetic screen, never real site approval',
                        'page_observations':['Synthetic fixture original viewport captured' for _ in pages]}
                    if cheap_reject:decision={'status':'rejected','reason':'rendered language/control/evidence check failed','page_observations':[]}
                    elif ledger.config['model'] is None:
                        decision={'status':'review_required','reason':'Automatic rendered preflight complete; visible Chinese, overlays and task-page semantics require review evidence',
                            'page_observations':[],'review_source':'not_reviewed','automatic_status':'MECHANICAL_PREFLIGHT_ONLY'}
                    else:
                        if gateway is None:gateway=ModelGateway(ledger)
                        decision=gateway.call(job,'site-screen-v1',json.dumps({'instruction':'Inspect every representative page image. Chinese visible text >=70%, Chinese navigation/controls, no mandatory login or blocking overlay. Dynamic/advertising uncertainties route to review_required. Supply one observation per page; readiness is provisional capability, not trajectory QC.','pages':pages},ensure_ascii=False),SCREEN_SCHEMA,images=images,synthetic_response=response)
                        if len(decision['page_observations'])!=len(pages) or not decision['reason'].strip():raise ValueError('Incomplete site screening evidence')
                    if any(r['routing']=='REVIEW_REQUIRED' for r in pages) and decision['status']=='ready':
                        decision={**decision,'status':'review_required','reason':'Preflight requires unresolved risk adjudication'}
                    record={'schema_version':'webcollect-site-capability-1','capability_id':'site-'+object_sha256(uri)[:20],
                        'version':object_sha256({'pages':capabilities,'screen':decision,'version':VERSION})[:24],
                        'site_uri':uri,'site_category':candidate['site_category'],'source':candidate['source'],
                        'observed_at':time.time(),'expires_at':time.time()+604800,'status':decision['status'],'reason':decision['reason'],
                        'supported_actions':actions,'action_support_basis':'visible controls and scoped observed form/widget fields; original target labels/hits/focus revalidated by existing runtime',
                        'capability_scope':{'kind':'exact-candidate-page','page_uris':[uri],'sitewide':False},
                        'representative_page_policy':'candidate URI only; other task pages require independent candidates',
                        'task_families':['form-workflow'] if forms else ['navigation-reading'],'evidence':evidence,'capabilities':capabilities,
                        'representative_pages':pages,'visit_ids':visit_ids,'accessible':any(p['accessible'] for p in pages),
                        'rendered':bool(pages),'unique_task_capacity_estimate':len(forms),'capacity_basis':'distinct observed forms or typed business widgets; not measured accepted trajectories',
                        'screening':decision,'mode':ledger.config['mode'],'QC_approval':False}
                    validate_capability(record,require_ready=False);save_json(directory/'capability.json',record)
                    ledger.finish(job,result=record);records.append(record)
                except BudgetStop as error:
                    partial={'site_uri':uri,'site_category':candidate['site_category'],'status':'queued','reason':str(error),
                        'representative_pages':pages,'capabilities':capabilities,'visit_ids':visit_ids,
                        'accessible':any(v['response_status'] is not None and v['response_status']<400 for v in ledger.visits() if v['id'] in visit_ids),
                        'rendered':bool(list(directory.rglob('*.png'))),
                        'evidence':[{'path':str(path),'sha256':file_sha(path)} for path in sorted(directory.rglob('*')) if path.is_file()]}
                    save_json(directory/('partial-attempt-'+str(ledger.get(jid)['attempts'])+'.json'),partial)
                    ledger.finish(job,'queued',result=partial,error=str(error));records.append(partial);stopped=str(error);break
                except Exception as error:
                    failure={'site_uri':uri,'site_category':candidate['site_category'],'status':'review_required',
                        'reason':type(error).__name__,'error_message':str(error),'representative_pages':pages,
                        'capabilities':capabilities,'visit_ids':visit_ids,
                        'accessible':any(v['response_status'] is not None and v['response_status']<400 for v in ledger.visits() if v['id'] in visit_ids),
                        'rendered':bool(list(directory.rglob('*.png'))),
                        'evidence':[{'path':str(path),'sha256':file_sha(path)} for path in sorted(directory.rglob('*')) if path.is_file()]}
                    save_json(directory/('failure-attempt-'+str(ledger.get(jid)['attempts'])+'.json'),failure)
                    ledger.finish(job,'review_required',result=failure,error=type(error).__name__);records.append(failure)
                finally:await page.close()
        finally:
            await context.close();await browser.close()
    result={'schema_version':'webcollect-capability-catalog-1','mode':ledger.config['mode'],'records':records,
        'fixed_candidate_count':len(candidates['records']),'status_counts':dict(Counter(r['status'] for r in records)),
        'unprocessed':len(candidates['records'])-len(records),'stopped':stopped,
        'domain_count':len({urlsplit(r['site_uri']).hostname for r in records}),'categories':dict(Counter(r.get('site_category','UNKNOWN') for r in records)),
        'sample_ids_allocated':0,'real_supply_verified':False,'top_level_visits_attempted':ledger.summary()['top_level_visits_attempted']}
    path=output/('catalog-'+object_sha256(result)[:16]+'.json');save_json(path,result)
    return {'catalog_file':str(path),**result}
