"""One accounted, read-only GET before publishing a new candidate."""
import time
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError

from webcollect.batch_core import OutcomeUnknown, load_json, save_json
from webcollect.candidate_contract import application_matches
from webcollect.planning import object_sha256, verify_evidence
from webcollect.site_failure_stop import SiteFailureStore, SiteStopped
from .discovery_tools import reference
from .pipeline import open_public_get, reserve_visit
from .site_pool import page_uri

POLICY = 'producer-entry-http-get-1'


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
    if record['job_id'] != jid or record['entry_uri'] != uri or record['policy'] != POLICY:
        raise ValueError('Original entry HTTP receipt does not match its job')
    if record['result'] == 'PASS' and ledger.config.get('site_failure_guard'):
        SiteFailureStore(ledger.config['site_failure_guard']).guard(uri)
    return record, ref


def check_entry(ledger, batch, url, output, *, cached_only=False):
    uri = page_uri(url)
    payload = {'batch':batch, 'uri':uri, 'policy':POLICY}
    kind = 'candidate-entry-http'
    if cached_only:
        jid = object_sha256({'kind':kind, 'payload':payload})
    else:
        jid = ledger.enqueue(kind,payload)
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
