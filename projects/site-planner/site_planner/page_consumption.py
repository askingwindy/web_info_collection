"""Producer-owned first-frame image exclusion; original evidence and QC stay separate."""
import asyncio
import json
from pathlib import Path
import time
from PIL import Image
from webcollect.batch_core import load_json, OutcomeUnknown
from webcollect.planning import canonical, object_sha256, verify_evidence
from .candidate_pool import entry_identity

LEGACY_VERSION = 'producer-image-only-entry-1'
VERSION = 'producer-first-frame-image-2'
OBSERVATION_VERSION = 'producer-image-viewport-observation-2'
RUN = 'producer-page-consumption-1'
SCREEN_RUN = 'producer-image-screen-1'
VISIBLE_FRAME_VERSION = 'producer-visible-first-frame-1'
LOGIN_REQUIRED_VERSION = 'producer-login-page-exclusion-2'


def required_login_exclusion(result):
    """Reject an observed login entry before purpose selection or publication."""
    refs = [result['observation'], result['image']]
    verify_evidence(refs)
    observation = load_json(result['observation']['path'])
    from webcollect.consumer_page_policy import login_entry_exclusion
    decision = login_entry_exclusion(observation)
    if decision is None:
        return None
    return {'policy': LOGIN_REQUIRED_VERSION, 'status': 'REJECTED',
            'reason': decision['reason'], 'references': refs,
            'login_exclusion': decision, 'QC': 'NOT_RUN'}


def blank_frame_exclusion(result):
    """Reject a proven blank original frame, without guessing from empty text alone."""
    refs = [result['observation'], result['image']]
    verify_evidence(refs)
    observation = load_json(result['observation']['path'])
    if ((observation.get('visible_text', observation.get('text', '')) or '').strip()
            or observation.get('controls') or observation.get('links')):
        return None
    with Image.open(result['image']['path']) as image:
        extrema = image.convert('RGB').getextrema()
    if any(low != high for low, high in extrema):
        return None
    return {'policy': VISIBLE_FRAME_VERSION, 'status': 'REJECTED',
            'reason': 'blank_first_frame', 'references': refs,
            'evidence': {'readable_text': False, 'visible_controls': False,
                         'visible_links': False, 'uniform_rgb': [low for low, _ in extrema]},
            'language_QC': 'NOT_RUN'}


class ObservationUnavailable(ValueError):
    """A verified original observation is not a usable public first-party page."""


def key(uri):return object_sha256(entry_identity(uri))


def lookup(pool, uri, con=None):
    if con is None:
        with pool.pool.connect() as c:return lookup(pool,uri,c)
    row=con.execute('SELECT value FROM checkpoints WHERE run_id=? AND key=?',(RUN,key(uri))).fetchone()
    if not row:return None
    record=json.loads(row[0]);verify_evidence(record['references'])
    if record.get('policy') not in (LEGACY_VERSION,VERSION) or record.get('status')!='NO_CONSUME' or entry_identity(uri) not in record['entry_identities']:
        raise ValueError('Invalid original producer consumption decision')
    return record


def exclusion(pool, uri, *, kind='entry', con=None):
    """Legacy marks cover entries; V2 matches the consumer for targets too."""
    if kind not in ('entry','target'):return None  # Do not alter V1 historical dispatch.
    record=lookup(pool,uri,con)
    return record if record and (kind=='entry' or record.get('scope')=='entry_and_target') else None


def assess(view):
    """Use the consumer's >=95% geometry rule without semantic exceptions."""
    from webcollect.consumer_page_policy import full_image
    out={'policy':VERSION,'status':'UNKNOWN','reason':'image_coverage_not_established'}
    if view.get('schema_version') not in (LEGACY_VERSION,OBSERVATION_VERSION):
        return {**out,'reason':'incomplete_rendered_inventory'}
    image=full_image(view)
    if not image:return {**out,'reason':'viewport_not_image_filled'}
    out['image_viewport_ratio']=image['image_viewport_ratio']
    if view.get('inventory_complete') is not True:return {**out,'reason':'incomplete_rendered_inventory'}
    return {**out,'status':'NO_CONSUME','reason':'first_frame_image_fills_viewport',
            'consumer_policy':image['policy'],'threshold':image['threshold'],
            'scope':'entry_and_target','needs_consumption':False,'label':'无需消费','image_boxes':image['image_boxes']}


def register(pool, ledger, result):
    """Only a completed producer probe can create an immutable page exclusion."""
    if result.get('image_policy') not in (LEGACY_VERSION,VERSION):raise ValueError('Versioned producer image probe required')
    refs=[result['observation'],result['image']];verify_evidence(refs)
    observation=load_json(result['observation']['path']);job=ledger.get(result['job_id'])
    if (job['payload'].get('image_policy')!=result['image_policy']
        or job['kind']!='site-discovery-page' or entry_identity(job['payload']['uri'])!=entry_identity(result['uri'])):raise ValueError('Original producer probe job mismatch')
    # Tool success is committed just before the original ledger job completes.
    # Another worker may observe that short window; hold, never redispatch.
    if job['state']=='running':
        raise ObservationUnavailable('Original producer probe job not settled')
    if job['state']!='done' or job['result']!=result:raise ValueError('Original producer probe job mismatch')
    with ledger.connect() as con:visit=con.execute('SELECT * FROM top_level_visits WHERE id=?',(result['visit_id'],)).fetchone()
    if (not visit or visit['job_id']!=job['id'] or visit['state'] not in ('succeeded','failed')
        or observation.get('http_status')!=visit['response_status']
        or observation['landed_uri']!=visit['landed_uri'] or entry_identity(visit['target_uri'])!=entry_identity(result['uri'])
        ):
        raise ValueError('No completed first-party HTTP observation')
    if (type(visit['response_status']) is not int or not 200<=visit['response_status']<300
        or observation.get('navigation_error') or result.get('same_application_host') is not True):
        raise ObservationUnavailable('Original page HTTP/access observation is not eligible')
    from webcollect.candidate_contract import application_matches
    aliases=(ledger.config.get('site_failure_guard') or {}).get('application_registry')
    if not application_matches(result['uri'],observation['landed_uri'],aliases):raise ObservationUnavailable('Probe left first party')
    view=observation.get('image_view',{})
    if view!=observation.get('image_view_after'):return {'policy':VERSION,'status':'UNKNOWN','reason':'render_changed_during_capture'}
    if entry_identity(view.get('url','https://invalid.example/'))!=entry_identity(observation['landed_uri']):raise ValueError('Viewport URI mismatch')
    with Image.open(result['image']['path']) as img:
        if list(img.size)!=view.get('screen_resolution'):raise ValueError('Viewport/image dimensions mismatch')
    assessment=assess(view)
    if assessment['status']!='NO_CONSUME':return assessment
    record={**assessment,'uri':result['uri'],'entry_identities':sorted({entry_identity(result['uri']),entry_identity(observation['landed_uri'])}),
        'references':refs,'job_id':job['id'],'visit_id':visit['id']}
    # Same project DB and existing short transaction / checkpoint unique key.
    # First completed decision wins; no original evidence or candidate is rewritten.
    with pool.transaction() as con:
        old=lookup(pool,result['uri'],con)
        if old:
            # Keep original scopes and receipts intact across policy updates.
            return old
        for uri in record['entry_identities']:
            if lookup(pool,uri,con):continue
            con.execute('INSERT INTO checkpoints VALUES(?,?,?,?)',(RUN,key(uri),canonical(record),time.time()))
    return record


async def _probe(pool,ledger,uri,root):
    if ledger.config.get('mode')!='real':raise ValueError('Real image probe requires mode=real; fixtures must supply a controlled probe')
    from .discovery_tools import DiscoveryBrowser
    async with DiscoveryBrowser(pool.pool,ledger,SCREEN_RUN,root,image_screen=True) as browser:
        return await browser.read(uri)


def screen(pool,ledger,links,root,*,probe=None,eligibility_policy=None):
    """Before purpose-model dispatch; one project-shared probe per entry URI."""
    admitted=[];records=[]
    for link in links:
        uri=link['uri'];old=lookup(pool,uri)
        if old:records.append({'uri':uri,'decision':old,'reused':True});continue
        identity=object_sha256([SCREEN_RUN,'browser',entry_identity(uri)])
        with pool.pool.connect() as con:prior=con.execute('SELECT state,result FROM tool_requests WHERE id=?',(identity,)).fetchone()
        if prior:
            result=json.loads(prior['result'] or '{}')
            if prior['state']!='succeeded' and not (prior['state']=='failed' and result.get('http_failure')):
                records.append({'uri':uri,'decision':{'status':'HELD','reason':'original_image_probe_unsettled','tool_request_id':identity}});continue
        else:
            if ledger.config.get('site_failure_guard'):
                from webcollect.site_failure_stop import SiteFailureStore,SiteStopped
                try:SiteFailureStore(ledger.config['site_failure_guard']).guard(uri)
                except SiteStopped:
                    records.append({'uri':uri,'decision':{'status':'HELD','reason':'original_project_dispatch_hold'}});continue
            try:result=probe(pool,ledger,uri,root) if probe else asyncio.run(_probe(pool,ledger,uri,root))
            except OutcomeUnknown:
                records.append({'uri':uri,'decision':{'status':'HELD','reason':'image_probe_outcome_unknown','tool_request_id':identity}});continue
            except Exception as error:
                # Browser errors and concurrent reservations both leave an
                # original tool record. Unrecorded host failures still stop
                # for diagnosis.
                with pool.pool.connect() as con:
                    original=con.execute('SELECT state,result FROM tool_requests WHERE id=?',(identity,)).fetchone()
                if not original:raise
                # Another worker may have reserved or finished the shared
                # probe after our initial read. Respect its exclusive record.
                if original['state']=='succeeded':
                    prior=original
                    result=json.loads(original['result'] or '{}')
                else:
                    records.append({'uri':uri,'decision':{'status':'HELD','reason':'original_image_probe_unsettled',
                        'original_state':original['state'],'error_type':type(error).__name__,'tool_request_id':identity}})
                    continue
        if result.get('http_failure'):
            from .producer_read_policy import validate_http_failure
            verdict=validate_http_failure(pool,ledger,result,identity)
            records.append({'uri':uri,'decision':verdict,'reused':bool(prior),
                            'probe':{k:result[k] for k in ('job_id','visit_id','http_failure')}})
            continue
        probe_refs={k:result[k] for k in ('job_id','visit_id','observation','image')}
        try:verdict=register(pool,ledger,result)
        except ObservationUnavailable:
            records.append({'uri':uri,'decision':{'status':'HELD','reason':'original_image_observation_not_eligible',
                'http_status':result.get('http_status'),'tool_request_id':identity},'reused':bool(prior),'probe':probe_refs})
            continue
        if verdict['status'] != 'NO_CONSUME':
            blank = blank_frame_exclusion(result) or required_login_exclusion(result)
            from webcollect.page_language import assess as assess_language
            language = assess_language(load_json(result['observation']['path']))
            if blank:
                verdict = blank
            elif language['excluded']:
                verdict = {**language, 'status':'REJECTED', 'references':[result['observation'],result['image']]}
        if eligibility_policy:
            from .producer_eligibility import assess as assess_entry, VERSION as entry_policy
            if eligibility_policy!=entry_policy:raise ValueError('Unsupported page eligibility policy')
            stricter=assess_entry(load_json(result['observation']['path']))
            if stricter['status']=='REJECTED':verdict={**stricter,'references':[result['observation'],result['image']]}
        records.append({'uri':uri,'decision':verdict,'reused':bool(prior),'probe':probe_refs})
        if verdict['status'] not in ('NO_CONSUME','REJECTED'):admitted.append(link)
    return admitted,records


def main(argv=None):
    import argparse
    from webcollect.batch_core import BatchLedger
    from .candidate_pool import CandidatePool
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool',required=True,type=Path)
    parser.add_argument('--uri',required=True)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--ledger',type=Path)
    parser.add_argument('--history-set',type=Path)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--result',type=Path,help='Original completed image-screen result; local validation only')
    mode.add_argument('--probe',action='store_true',help='One real producer-only readonly browser check; never starts a consumer')
    parser.add_argument('--output',type=Path,help='Original project evidence directory for --probe')
    args=parser.parse_args(argv);pool=CandidatePool(args.pool,readonly=not (args.result or args.probe))
    if args.result or args.probe:
        if not args.config or not args.ledger or not args.history_set:parser.error('--result/--probe needs original --config, --ledger and --history-set')
        from webcollect.current_chain import read_chain_scope,check_project_pool,check_project_guard,assert_current_evidence
        chain=read_chain_scope(args.history_set.absolute());config=load_json(args.config)
        check_project_pool(chain,pool.pool);check_project_guard(chain,config.get('site_failure_guard'),args.ledger,role='producer')
        ledger=BatchLedger(args.ledger,config)
        if args.probe:
            if not args.output:parser.error('--probe needs --output')
            from webcollect.current_chain import require_evidence_path,current_evidence_roots
            require_evidence_path(args.output.absolute(),current_evidence_roots(chain))
            admitted,records=screen(pool,ledger,[{'uri':args.uri}],args.output.absolute())
            value={'uri':args.uri,'records':records,'consumer_started':False,'trajectory_QC_started':False}
        else:
            result=load_json(args.result)
            if entry_identity(result['uri'])!=entry_identity(args.uri):parser.error('Original result URI mismatch')
            assert_current_evidence(chain,[result['observation'],result['image']])
            value=register(pool,ledger,result)
    else:value=lookup(pool,args.uri) or {'policy':VERSION,'status':'UNKNOWN','uri':args.uri}
    print(json.dumps(value,ensure_ascii=False))

if __name__=='__main__':main()
