"""Resolve the owner of an unsettled request from the original project books."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qsl, urlencode, urlsplit

from .application_identity import canonical_key
from .current_chain import check_project_guard, registry_project


def endpoint(uri, aliases=None):
    """HTTP identity for quarantine. Fragments are not transmitted to the server."""
    from site_planner.candidate_pool import TRACKING_QUERY_NAMES, TRACKING_QUERY_PREFIXES
    from site_planner.entry_access import wire_uri
    page = urlsplit(wire_uri(uri))
    host = urlsplit(canonical_key(uri, aliases)).netloc.removeprefix('www.')
    query = [(name, value) for name, value in parse_qsl(page.query, keep_blank_values=True)
             if name.lower() not in TRACKING_QUERY_NAMES and not name.lower().startswith(TRACKING_QUERY_PREFIXES)]
    return host, page.path.rstrip('/') or '/', urlencode(query)


def attempt_owner(guard, registry, attempt_id, *, job_ledger=None):
    """The original attempt fixes the candidate across workers, claims and restarts."""
    if not registry or not attempt_id:
        return None
    path = Path(registry)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        return None
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as con:
        scope = registry_project(con)
        if not scope or Path(scope['registry']).resolve() != path.resolve():
            return None
        try:
            check_project_guard(scope, guard, job_ledger, role='consumer')
        except ValueError:
            return None
        row = con.execute("""SELECT a.status, a.failure_class, t.task_id,
                   json_extract(t.task_json,'$.candidate_binding.candidate_id'),
                   coalesce(json_extract(t.task_json,'$.candidate_binding.candidate.entry_url'),
                            json_extract(t.task_json,'$.initial_url'),json_extract(t.task_json,'$.site_uri')),
                   json_extract(t.task_json,'$.site_uri')
                FROM m4_attempts a JOIN m4_tasks t ON a.task_key=t.task_key
                WHERE a.attempt_id=? AND a.campaign_id=? AND a.campaign_id=t.campaign_id""",
                          (attempt_id, scope['chain_id'])).fetchone()
    if row and row[4]:
        return {**dict(zip(('status','failure_class','task_id','candidate_id','uri','site_uri'), row)),
                'focus_effect_accounted':accounted_rejected_focus(path,attempt_id)}
    return None


def accounted_rejected_focus(registry, attempt_id):
    """Read the appended original settlement; never infer from harmless intent."""
    from .batch_core import load_json
    from .planning import verify_evidence
    from .postprocess import rejected_focus_dispatch_audit
    with closing(sqlite3.connect(Path(registry).resolve().as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        row=con.execute('SELECT status,failure_class,root_cause,evidence_json FROM m4_attempts WHERE attempt_id=?',(attempt_id,)).fetchone()
        if not row or row['status']!='rejected' or row['failure_class']!='interrupted':return False
        events=[json.loads(r[0]) for r in con.execute("SELECT payload_json FROM m4_events WHERE event_type='rejected_focus_effect_accounted' AND attempt_id=?",(attempt_id,))]
    for event in events:
        audit_ref=event.get('rejected_focus_audit')
        if not audit_ref or audit_ref not in json.loads(row['evidence_json']):continue
        verify_evidence([audit_ref,event['original_failure'],event['process_exit'],event['raw_receipt']])
        audit=load_json(audit_ref['path']);failure=load_json(event['original_failure']['path'])
        closed=load_json(event['process_exit']['path'])
        if (audit.get('attempt_id')!=attempt_id or audit.get('original_failure')!=event['original_failure']
                or audit.get('raw_receipt')!=event['raw_receipt'] or failure.get('error')!=row['root_cause']
                or closed.get('attempt_id')!=attempt_id or closed.get('browser_closed') is not True):continue
        if audit!=rejected_focus_dispatch_audit(Path(event['raw_receipt']['path']).parent):continue
        # Settled original model requests are checked again; their account is
        # not replaced by this browser-effect audit.
        raw=Path(event['raw_receipt']['path']).parent
        binding=load_json(raw/'boundary.json')['task']['candidate_binding']
        from site_planner.candidate_pool import CandidatePool
        frozen=load_json(binding['claim_reference']['path']);claim=CandidatePool(frozen['pool']).get_claim(binding['claim_id'])
        owner=claim.get('binding') or {}
        if owner.get('attempt_id')!=attempt_id or Path(owner.get('registry','')).resolve()!=Path(registry).resolve():continue
        with closing(sqlite3.connect(Path(owner['ledger']).as_uri()+'?mode=ro',uri=True)) as con:
            requests=list(con.execute("SELECT id,state FROM model_requests WHERE json_extract(request_json,'$.dispatch_attempt_id')=?",(attempt_id,)))
        if requests and {r[0] for r in requests}==set(event['settled_request_ids']) and all(r[1]=='succeeded' for r in requests):return True
    return False


def job_conflicts(ledger, uri, candidate_id, payload, *, running, registry=None, dispatched_attempt=None):
    """Match work to its original attempt, or to the narrowest provable URL scope."""
    from .current_chain import PROJECT_RULES
    guard = ledger.config.get('site_failure_guard') or {}
    aliases = guard.get('application_registry')
    site = payload.get('site_uri')
    if guard.get('dispatch_rules') != PROJECT_RULES:
        return running or not site or bool(uri and canonical_key(site, aliases) == canonical_key(uri, aliases))
    attempt_id = payload.get('attempt_id')
    if attempt_id and dispatched_attempt in (None, attempt_id):
        registry = registry or ledger.path.with_name('production-registry.sqlite3')
        owner = attempt_owner(guard, registry, attempt_id, job_ledger=ledger.path)
        if owner and payload.get('task_id') == owner['task_id'] and (
                not site or endpoint(site, aliases)[0] == endpoint(owner['site_uri'] or owner['uri'], aliases)[0]):
            if candidate_id and owner['candidate_id']:
                return candidate_id == owner['candidate_id']
            return bool(uri and endpoint(uri, aliases) == endpoint(owner['uri'], aliases))
    if not site:
        return True
    if not uri:
        return False  # The specific owner/page check runs again after claim.
    # A pre-attempt job may identify only a page, or only a whole application.
    # If an asserted attempt binding is inconsistent, keep the application hold.
    original = endpoint(site, aliases)
    target = endpoint(uri, aliases)
    if not attempt_id and dispatched_attempt is None and original[1:] != ('/', ''):
        return original == target
    return original[0] == target[0]


def visit_uri(con, fact):
    """Only an exact, recorded dispatch can narrow a site fact to an HTTP endpoint."""
    from .site_failure_stop import execution_id
    identity, _, stage, reason, evidence, refs = fact
    refs = json.loads(refs)
    if stage != 'probe' or len(refs) != 1 or not isinstance(refs[0],dict):
        return None
    ledger = refs[0].get('ledger')
    vid = refs[0].get('visit_id')
    if not ledger or not vid or identity != execution_id('probe', ledger, vid):
        return None
    visit = con.execute("""SELECT v.id,v.job_id,v.target_uri,v.dispatched_at,v.state,v.error_type,
                j.kind,j.state AS job_state,j.result
            FROM top_level_visits v JOIN jobs j ON j.id=v.job_id WHERE v.id=?""", (vid,)).fetchone()
    if not visit or visit['state'] not in ('reserved_for_dispatch','unknown','failed'):
        return None
    if visit['kind'] == 'candidate-entry-http' and visit['job_state'] == 'done':
        return None  # A completed entry check must pass its full receipt check.
    if visit['job_state'] == 'running' and visit['result'] is not None:
        return None  # An internally inconsistent original cannot narrow the hold.
    if visit['error_type'] and visit['error_type'] != reason:
        return None
    original = {key:visit[key] for key in ('id','job_id','target_uri','dispatched_at')}
    return visit['target_uri'] if json.loads(evidence) == [{'visit_fact':original}] else None
