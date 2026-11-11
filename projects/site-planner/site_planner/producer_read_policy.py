"""Opt-in bounded readiness and evidence for confirmed HTTP failures."""
import asyncio
import time

VERSION = 'producer-readiness'
# Old receipts were stamped with the generational values; reads accept them.
PREVIOUS_VERSION = 'producer-readiness-1'
OPTIMIZATION = 'observation-feedback-1'
FAILURE_VERSION = 'producer-http-failure'
PREVIOUS_FAILURE_VERSION = 'producer-http-failure-1'
PENDING_IMAGES_SCRIPT = '''() => [...document.images].filter(e=>{
    const r=e.getBoundingClientRect();return !e.complete && r.width>0 && r.height>0 &&
        r.right>0 && r.bottom>0 && r.left<innerWidth && r.top<innerHeight &&
        getComputedStyle(e).visibility==='visible';}).length'''

# Read-only observations. Ads/live announcements and changing image pixels do
# not enter the stability signature; visible images must finish loading.
READINESS_SCRIPT = r'''() => {
    const root = document.querySelector('main,[role="main"],article') || document.body;
    if (!root) return {meaningful:false, pending_images:0, signature:''};
    const excluded = 'script,style,nav,aside,header,footer,[aria-live],[role="status"],[role="alert"],.ad,.ads,[data-ad],.advertisement';
    const visible = e => { const r=e.getBoundingClientRect(); return r.width>0 && r.height>0 &&
        r.bottom>0 && r.top<innerHeight && getComputedStyle(e).visibility!=='hidden'; };
    const walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    let text='', node, seen=0;
    while ((node=walk.nextNode()) && seen++<2000 && text.length<2048) {
        const p=node.parentElement;
        if (p && !p.closest(excluded) && visible(p)) text+=node.textContent.trim()+' ';
    }
    const controls=[...root.querySelectorAll('input:not([type="hidden"]),textarea,select,button')]
        .filter(e=>!e.closest(excluded) && visible(e)).map(e=>[e.tagName,e.type||'',e.disabled]);
    const pending=[...document.images].filter(e=>!e.closest(excluded) && visible(e) && !e.complete).length;
    return {meaningful:!!text.trim() || controls.length>0,pending_images:pending,
        signature:JSON.stringify([text.trim(),controls])};
}'''


async def wait_ready(page):
    """At most the former 1200 ms window; readiness never grants eligibility."""
    start=time.monotonic(); deadline=start+1.2; last=None; stable=0; samples=0
    reason='bounded_window_elapsed'
    while time.monotonic()<deadline:
        try:
            state=await asyncio.wait_for(page.evaluate(READINESS_SCRIPT), deadline-time.monotonic())
        except TimeoutError:
            break
        samples+=1
        if state['meaningful'] and not state['pending_images']:
            stable=stable+1 if state['signature']==last else 1
            last=state['signature']
            if stable>=3:
                reason='visible_content_stable'; break
        else:
            stable=0; last=None
        remaining=deadline-time.monotonic()
        if remaining>0:await page.wait_for_timeout(min(200,remaining*1000))
    return {'policy':VERSION,'readiness_seconds':round(time.monotonic()-start,4),
            'readiness_reason':reason,'readiness_samples':samples}


def image_recheck_delay(view, pending_images=0):
    from .page_consumption import assess, OBSERVATION_VERSION
    # Only a complete, known inventory below the unchanged >=95% exclusion can
    # omit the delay. The caller still performs a second actual JS observation.
    below=(not pending_images and view.get('schema_version')==OBSERVATION_VERSION and view.get('inventory_complete') is True
           and assess(view)['reason']=='viewport_not_image_filled')
    return (0,'complete_inventory_below_threshold') if below else (1200,'retain_image_exclusion_recheck')


def validate_http_failure(pool, ledger, result, identity):
    """Read a failed tool receipt without converting it into a successful probe."""
    import json
    from webcollect.batch_core import load_json
    from webcollect.planning import verify_evidence
    from .candidate_pool import entry_identity
    ref=result['http_failure']; verify_evidence([ref]); receipt=load_json(ref['path'])
    job=ledger.get(result['job_id'])
    with ledger.connect() as con:
        visit=con.execute('SELECT * FROM top_level_visits WHERE id=?',(result['visit_id'],)).fetchone()
    with pool.pool.connect() as con:
        tool=con.execute('SELECT state,result FROM tool_requests WHERE id=?',(identity,)).fetchone()
    status=receipt.get('http_status')
    if (receipt.get('schema_version') not in (FAILURE_VERSION, PREVIOUS_FAILURE_VERSION)
        or receipt.get('read_policy') not in (VERSION, PREVIOUS_VERSION)
        or type(status) is not int or not 400<=status<600 or receipt.get('method')!='GET'
        or receipt.get('navigation_error') is not None or receipt.get('tool_request_id')!=identity
        or receipt.get('job_id')!=job['id'] or receipt.get('visit_id')!=result['visit_id']
        or job['kind']!='site-discovery-page' or job['state']!='done' or job['result']!=result
        or not tool or tool['state']!='failed' or json.loads(tool['result'])!=result
        or not visit or visit['job_id']!=job['id'] or visit['state']!='failed'
        or visit['response_status']!=status or result.get('http_status')!=status
        or visit['landed_uri']!=receipt.get('landed_uri')
        or any(entry_identity(value)!=entry_identity(result['uri']) for value in
               (receipt['uri'],job['payload']['uri'],visit['target_uri']))):
        raise ValueError('Original confirmed HTTP failure binding mismatch')
    return {'policy':FAILURE_VERSION,'status':'DISCARDED' if status==403 else 'HELD',
            'reason':'entry_http_403' if status==403 else 'confirmed_http_failure',
            'http_status':status,'tool_request_id':identity,'reference':ref}
