"""Reuse one evidence-bound anonymous GET for screening, purpose and publication."""
import asyncio
import json
from pathlib import Path
from . import page_consumption as images
from .candidate_pool import entry_identity
from .discovery_tools import DiscoveryBrowser,reference
from webcollect.batch_core import load_json,save_json,OutcomeUnknown
from webcollect.planning import object_sha256,verify_evidence
from webcollect.candidate_contract import application_matches

VERSION='producer-shared-observation-1'

def screen(pool,ledger,links,root,*,read_policy=None):
    browser=None
    with asyncio.Runner() as runner:
        def probe(_pool,_ledger,uri,_root):
            nonlocal browser
            if ledger.config.get('mode')!='real':raise ValueError('Real shared observation requires mode=real')
            if browser is None:
                browser=DiscoveryBrowser(pool.pool,ledger,images.SCREEN_RUN,root,image_screen=True,capture_document=True,fresh_pages=True,
                                         **({'read_policy':read_policy} if read_policy else {}))
                runner.run(browser.__aenter__())
            return runner.run(browser.read(uri))
        try:return images.screen(pool,ledger,links,root,probe=probe)
        finally:
            if browser:runner.run(browser.__aexit__())

def from_pool(pool,ledger,uri):
    identity=object_sha256([images.SCREEN_RUN,'browser',entry_identity(uri)])
    with pool.pool.connect() as con:row=con.execute('SELECT state,result FROM tool_requests WHERE id=?',(identity,)).fetchone()
    if not row:return None
    if row['state']!='succeeded':raise OutcomeUnknown('Original shared page observation unsettled; no repeat: '+identity)
    result=json.loads(row['result'])
    if not result.get('document'):return None
    verify_evidence([result['observation'],result['image'],result['document']])
    job=ledger.get(result['job_id']);obs=load_json(result['observation']['path']);doc=load_json(result['document']['path'])
    if (job['kind']!='site-discovery-page' or job['state']!='done' or job['result']!=result
        or job['payload'].get('document_policy')!=VERSION or job['payload'].get('access')!='fresh_context_no_login_get_only'
        or doc.get('document_policy')!=VERSION or obs.get('document')!=result['document']
        or doc.get('method')!='GET' or doc.get('anonymous_context') is not True
        or doc.get('initial_cookies')!=0 or doc.get('login_performed') is not False
        or doc.get('job_id')!=job['id'] or doc.get('visit_id')!=result['visit_id']
        or any(entry_identity(value)!=entry_identity(uri) for value in (doc['uri'],job['payload']['uri'],result['uri']))):
        raise ValueError('Original shared document/job/URI binding mismatch')
    with ledger.connect() as con:visit=con.execute('SELECT * FROM top_level_visits WHERE id=?',(doc['visit_id'],)).fetchone()
    if (not visit or visit['job_id']!=job['id'] or visit['state']!='succeeded' or type(visit['response_status']) is not int
        or not 200<=visit['response_status']<300 or visit['response_status']!=doc['http_status']
        or visit['landed_uri']!=doc['landed_uri'] or obs['landed_uri']!=doc['landed_uri']
        or obs.get('navigation_error') or entry_identity(visit['target_uri'])!=entry_identity(uri)):
        raise ValueError('Original shared GET visit/status binding mismatch')
    aliases=(ledger.config.get('site_failure_guard') or {}).get('application_registry')
    if not application_matches(uri,doc['landed_uri'],aliases):raise ValueError('Shared document leaves first party')
    from .entry_access import wire_uri
    if wire_uri(doc['response_uri'])!=wire_uri(doc['landed_uri']):raise ValueError('Document response does not match the observed landing')
    verify_evidence([doc['raw_html'],doc['rendered_dom']])
    return doc,result

def entry_receipt(pool,ledger,uri,root):
    original=from_pool(pool,ledger,uri)
    if original is None:return None
    doc,result=original
    if ledger.config.get('site_failure_guard'):
        from webcollect.site_failure_stop import SiteFailureStore
        SiteFailureStore(ledger.config['site_failure_guard']).guard(uri)
    record={'policy':'producer-entry-observed-get-2','job_id':doc['job_id'],'visit_id':doc['visit_id'],'method':'GET',
        'entry_uri':uri,'landed_uri':doc['landed_uri'],'http_status':doc['http_status'],'result':'PASS',
        'checked_at':load_json(result['observation']['path'])['observed_at'],'reason':None,
        'source_observation':result['observation'],'source_document':result['document'],'reused_original_browser_GET':True}
    path=Path(root)/('entry-observed-'+object_sha256([uri,result['document']])+'.json')
    if path.exists():
        if load_json(path)!=record:raise ValueError('Original observed entry receipt changed')
    else:save_json(path,record)
    return record,reference(path)
