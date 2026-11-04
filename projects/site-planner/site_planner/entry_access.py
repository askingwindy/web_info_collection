"""One accounted, read-only GET before publishing a new candidate."""
import time
import json
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError

from webcollect.batch_core import OutcomeUnknown, load_json, save_json
from webcollect.candidate_contract import application_matches
from webcollect.planning import object_sha256, verify_evidence
from webcollect.site_failure_stop import SiteFailureStore, SiteStopped
from .discovery_tools import reference
from .pipeline import open_public_get, reserve_visit, request_uri
from .site_pool import page_uri

POLICY = 'producer-entry-http-get-1'


def wire_uri(uri):
    return request_uri(page_uri(uri))


def document_http_failure(con, job_id):
    """A sealed HTTP error can be replayed from the original visit, including legacy jobs."""
    return con.execute(
        "SELECT v.id,v.target_uri,v.response_status FROM top_level_visits v JOIN jobs j ON j.id=v.job_id "
        "WHERE j.id=? AND j.kind='application-evidence-get' AND j.state='review_required' AND j.error='HTTPError' "
        "AND v.purpose=j.kind AND v.state='failed' AND v.error_type='HTTPError' "
        "AND v.finished_at IS NOT NULL AND v.response_status BETWEEN 300 AND 599 "
        "AND NOT EXISTS (SELECT 1 FROM top_level_visits other WHERE other.job_id=j.id AND other.id<>v.id)",
        (job_id,)).fetchone()


class RedirectBlocked(ValueError):
    responsibility = 'collector'


def fetch_status(uri, timeout, metrics, mode, aliases, guard=None):
    if mode != 'real':
        raise ValueError('Synthetic entry HTTP needs a controlled response')
    def check_url(url):
        try:
            allowed = application_matches(uri, url, aliases)
        except ValueError as error:
            raise RedirectBlocked(str(error)) from error
        if not allowed:
            raise RedirectBlocked('Entry redirect leaves the source application')
        if guard and url != uri:
            try:
                guard.guard(url)
            except SiteStopped as error:
                raise RedirectBlocked(str(error)) from error
    try:
        with open_public_get(uri, time.monotonic() + timeout, metrics, check_url) as response:
            return response.status, response.geturl()
    except HTTPError as error:
        try:
            return error.code, error.geturl()
        finally:
            error.close()


def _checked_receipt(ledger, jid, uri, ref):
    verify_evidence([ref])
    record = load_json(ref['path'])
    if record['job_id'] != jid or wire_uri(record['entry_uri']) != wire_uri(uri) or record['policy'] != POLICY:
        raise ValueError('Original entry HTTP receipt does not match its job')
    if record['result'] == 'PASS' and ledger.config.get('site_failure_guard'):
        SiteFailureStore(ledger.config['site_failure_guard']).guard(uri)
    return record, ref


def shared_job(ledger, batch, uri, *, purpose='candidate-entry-http', policy=POLICY, recheck=None):
    """Bind old and new batches atomically to one original job in this project DB."""
    conditions = {'access': 'public-anonymous-get',
                  'aliases': (ledger.config.get('site_failure_guard') or {}).get('application_registry')}
    identity = {'project': (ledger.config.get('site_failure_guard') or {}).get('campaign_id', ledger.config['run_id']),
                'request_uri': wire_uri(uri), 'purpose': purpose,
                'conditions': conditions, 'policy': policy}
    key = object_sha256(identity)
    with ledger.transaction() as con:
        con.execute('CREATE TABLE IF NOT EXISTS producer_page_checks ('
                    'identity TEXT PRIMARY KEY, binding TEXT NOT NULL, job_id TEXT NOT NULL)')
        unresolved=con.execute("SELECT id FROM jobs WHERE kind=? AND json_extract(payload,'$.policy')=? "
            "AND (json_extract(payload,'$.uri')=? OR json_extract(payload,'$.check_identity.request_uri')=?) "
            "AND state!='done' AND attempts>0", (purpose,policy,page_uri(uri),identity['request_uri']))
        for original in unresolved:
            if purpose!='application-evidence-get' or not document_http_failure(con,original['id']):
                raise OutcomeUnknown('Original page check unsettled; reconcile original job: '+original['id'])
        prior = con.execute('SELECT job_id FROM producer_page_checks WHERE identity=?', (key,)).fetchone()
        if not prior:
            # Legacy public checks have exactly these access conditions. Do not
            # rewrite their jobs, receipts, visits or counters when indexing them.
            legacy_rows=con.execute("SELECT id,payload,state,attempts FROM jobs WHERE kind=? "
                "AND json_extract(payload,'$.policy')=? AND json_extract(payload,'$.check_identity') IS NULL "
                "ORDER BY CASE WHEN state!='done' AND attempts>0 THEN 0 ELSE 1 END,created,id",
                (purpose,policy)).fetchall()
            matches=[r for r in legacy_rows if wire_uri(json.loads(r['payload'])['uri'])==identity['request_uri']]
            for original in matches:
                if original['state']!='done' and original['attempts'] and not (
                        purpose=='application-evidence-get' and document_http_failure(con,original['id'])):
                    raise OutcomeUnknown('Original page check unsettled; reconcile original job: '+original['id'])
            old=next(iter(matches),None)
            payload = {'uri':page_uri(uri), 'policy':policy, 'check_identity':identity}
            jid = old[0] if old else object_sha256({'kind':purpose, 'payload':payload})
            if not old:
                con.execute("INSERT OR IGNORE INTO jobs(id,kind,payload,state,created,updated) VALUES(?,?,?,'queued',?,?)",
                            (jid,purpose,json.dumps(payload,sort_keys=True),time.time(),time.time()))
            con.execute('INSERT INTO producer_page_checks VALUES(?,?,?)',
                        (key,json.dumps(identity,sort_keys=True),jid))
        else:
            jid = prior[0]
        ledger.event(con,'producer_page_check_reference',{'batch':batch,'entry_url':uri,'identity':key,'job_id':jid})
    if recheck:
        original=ledger.get(jid)
        if original['state']!='done':
            raise OutcomeUnknown('Reconcile original check before any recheck: '+jid)
        record,ref=_checked_receipt(ledger,jid,page_uri(uri),original['result'])
        verify_evidence(recheck.get('references',[]))
        status=record['http_status']
        allowed=(status in (403,404) and recheck.get('condition')=='source_or_access_changed'
                 or status in (408,429,500,502,503,504) and recheck.get('condition')=='temporary_fault_elapsed'
                 and time.time()>=recheck.get('not_before',float('inf')))
        if not allowed or not recheck.get('reason') or not recheck.get('references'):
            raise ValueError('Targeted recheck requires settled status, reason and changed-source/access or elapsed temporary-fault evidence')
        payload={'uri':page_uri(uri),'policy':policy,'check_identity':identity,'recheck_of':jid,'authorization':recheck}
        jid=ledger.enqueue(purpose,payload)
        with ledger.transaction() as con:
            ledger.event(con,'producer_page_recheck',{'batch':batch,'job_id':jid,'original':ref,'authorization':recheck})
    return jid


def check_entry(ledger, batch, url, output, *, cached_only=False, recheck=None):
    uri = page_uri(url)
    kind = 'candidate-entry-http'
    # A frozen old batch always reads its own original receipt first.
    legacy = object_sha256({'kind':kind, 'payload':{'batch':batch,'uri':uri,'policy':POLICY}})
    with ledger.connect() as con:
        exists=con.execute('SELECT 1 FROM jobs WHERE id=?',(legacy,)).fetchone()
    jid = legacy if exists and not recheck else shared_job(ledger,batch,url,recheck=recheck)
    original = ledger.get(jid)
    if original['state'] == 'done':
        return _checked_receipt(ledger,jid,uri,original['result'])
    if cached_only or original['state'] != 'queued' or original['attempts']:
        raise OutcomeUnknown('Original entry HTTP check unsettled; no repeat dispatch: ' + jid)
    job = ledger.claim(kind, job_id=jid)
    if not job:
        original = ledger.get(jid)
        if original['state'] == 'done':
            return _checked_receipt(ledger,jid,uri,original['result'])
        raise OutcomeUnknown('Original entry HTTP check not claimable: ' + jid)
    try:
        ledger.consume('probe_pages',jid)
        visit = reserve_visit(ledger,job,uri,kind)
    except Exception as error:
        ledger.finish(job,'review_required',error=type(error).__name__)
        raise
    status = landed = error = None
    metrics = {}
    state = 'unknown'
    try:
        aliases = (ledger.config.get('site_failure_guard') or {}).get('application_registry')
        guard = SiteFailureStore(ledger.config['site_failure_guard']) if ledger.config.get('site_failure_guard') else None
        status, landed = fetch_status(uri,visit['timeout_seconds'],metrics,ledger.config['mode'],aliases,guard)
        state = 'succeeded' if 200 <= status < 300 else 'failed'
        if state == 'failed':
            error = ValueError('Entry HTTP ' + str(status))
    except RedirectBlocked as blocked:
        error, state = blocked, 'failed'
    except (OSError, HTTPException) as failure:
        error = failure
    except Exception as failure:
        # Fixture/configuration and collector errors cannot consume a site's failure margin.
        error, state = failure, 'failed'
        metrics['responsibility'] = 'collector'
    ledger.settle_visit(visit,state=state,response_status=status,landed_uri=landed,error=error,metrics=metrics)
    result = 'PASS' if state=='succeeded' else 'REJECTED' if status is not None else 'HELD'
    record = {'policy':POLICY,'job_id':jid,'visit_id':visit['id'],'method':'GET','entry_uri':uri,
              'landed_uri':landed,'http_status':status,'result':result,'checked_at':time.time(),
              'reason':str(error) if error is not None else None,'redirects':metrics.get('redirects',[]),
              'request_uri':metrics.get('request_uri',uri)}
    path = Path(output) / ('entry-http-' + jid + '.json')
    save_json(path, record)
    ref = reference(path)
    ledger.finish(job,result=ref)
    return _checked_receipt(ledger,jid,uri,ref)
