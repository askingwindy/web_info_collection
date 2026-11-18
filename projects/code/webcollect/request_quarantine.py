"""Resolve the owner of an unsettled request from the original project books."""
from webcollect.sqlite_connection import raw_connect as workspace_connect
from contextlib import closing
from webcollect import workspace_json as json
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


def attempt_owner(guard, registry, attempt_id, *, job_ledger=None, research_request_id=None, include_closure=True):
    """The original attempt fixes the candidate across workers, claims and restarts."""
    if not registry or not attempt_id:
        return None
    path = Path(registry)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        return None
    with closing(workspace_connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as con:
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
                'focus_effect_accounted':include_closure and accounted_closed_execution(path,attempt_id,research_request_id=research_request_id)}
    return None


def accounted_rejected_focus(registry, attempt_id):
    """Read the appended original settlement; never infer from harmless intent."""
    from .batch_core import load_json
    from .planning import verify_evidence
    from .postprocess import rejected_focus_dispatch_audit
    with closing(workspace_connect(Path(registry).resolve().as_uri()+'?mode=ro',uri=True)) as con:
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
        frozen=load_json(binding['claim_reference']['path']);claim=CandidatePool(frozen['pool'], readonly=True).get_claim(binding['claim_id'])
        owner=claim.get('binding') or {}
        if owner.get('attempt_id')!=attempt_id or Path(owner.get('registry','')).resolve()!=Path(registry).resolve():continue
        with closing(workspace_connect(Path(owner['ledger']).as_uri()+'?mode=ro',uri=True)) as con:
            requests=list(con.execute("SELECT id,state FROM model_requests WHERE json_extract(request_json,'$.dispatch_attempt_id')=?",(attempt_id,)))
        if requests and {r[0] for r in requests}==set(event['settled_request_ids']) and all(r[1]=='succeeded' for r in requests):return True
    return False


def job_conflicts(ledger, uri, candidate_id, payload, *, running, registry=None, dispatched_attempt=None, candidate_only=False, research_request_id=None):
    """Match work to its original attempt, or to the narrowest provable URL scope."""
    from .current_chain import PROJECT_RULES
    guard = ledger.config.get('site_failure_guard') or {}
    aliases = guard.get('application_registry')
    site = payload.get('site_uri')
    if guard.get('dispatch_rules') != PROJECT_RULES:
        return False if candidate_only else running or not site or bool(uri and canonical_key(site, aliases) == canonical_key(uri, aliases))
    attempt_id = payload.get('attempt_id')
    if attempt_id and dispatched_attempt in (None, attempt_id):
        registry = registry or ledger.path.with_name('production-registry.sqlite3')
        owner = attempt_owner(guard, registry, attempt_id, job_ledger=ledger.path,research_request_id=research_request_id,
                              include_closure=False)
        if owner and payload.get('task_id') == owner['task_id'] and (
                not site or endpoint(site, aliases)[0] == endpoint(owner['site_uri'] or owner['uri'], aliases)[0]):
            if candidate_id and owner['candidate_id'] and candidate_id != owner['candidate_id']:
                return False
            if accounted_closed_execution(registry, attempt_id, research_request_id=research_request_id):
                return False  # Old execution closed; original job/request reservation remains fenced.
            if candidate_id and owner['candidate_id']:
                return candidate_id == owner['candidate_id']
            return bool(uri and endpoint(uri, aliases) == endpoint(owner['uri'], aliases))
    if candidate_only:
        return False  # Unrelated/ownerless history cannot suspend a new candidate.
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
    from .site_failure_stop import matches_execution_id
    identity, _, stage, reason, evidence, refs = fact
    refs = json.loads(refs)
    if stage != 'probe' or len(refs) != 1 or not isinstance(refs[0],dict):
        return None
    ledger = refs[0].get('ledger')
    vid = refs[0].get('visit_id')
    if not ledger or not vid or not matches_execution_id(identity, 'probe', ledger, vid):
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


def _closed_execution(registry, attempt_id, authorization, *, definite=False, transport=False):
    """Verify a definite parameter rejection separately from UNKNOWN accounting."""
    from .batch_core import load_json, file_sha
    from .planning import verify_evidence
    from .postprocess import session_record, failed_execution_trajectory
    from .candidate_contract import validate_task_binding
    from site_planner.candidate_pool import CandidatePool
    if (authorization.get('attempt_id') != attempt_id
            or authorization.get('allow_new_attempt') is not True
            or not str(authorization.get('user_authorization') or '').strip()):
        raise ValueError('Explicit user authorization for a new complete attempt required')
    refs = [authorization[key] for key in ('raw_receipt', 'original_failure', 'process_exit')]
    verify_evidence(refs)
    raw_ref, failure_ref, exit_ref = refs
    raw = Path(raw_ref['path']).resolve().parent
    if Path(raw_ref['path']).name != 'raw-receipt.json' or Path(failure_ref['path']).resolve() != raw.parent/'failure.json':
        raise ValueError('Original sealed raw and primary failure required')
    record = session_record(raw, allow_unknown_for_prefix=True)
    primary = load_json(failure_ref['path']); closed = load_json(exit_ref['path'])
    extra_refs = [authorization[key] for key in ('run_intent', 'process_start', 'launcher', 'worker')]
    verify_evidence(extra_refs)
    report = Path(exit_ref['path']).resolve().parent
    _verify_execution_entry(registry, attempt_id, authorization, report, load_json(authorization['process_start']['path']), transport=transport)
    intent = load_json(authorization['run_intent']['path'])
    started = load_json(authorization['process_start']['path'])
    import os
    process_pid = started.get('pid') if transport else closed.get('pid')
    if type(process_pid) is not int or process_pid <= 0:
        raise ValueError('Original positive process PID required')
    try:
        os.kill(process_pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError('Original process PID still exists; inspect original execution')
    if ((not transport and (closed.get('pid') != started.get('pid')
                            or closed.get('started_at') != started.get('started_at')))
            or closed.get('finished_at', 0) <= started.get('started_at', 0)
            or closed.get('source_drift') != []
            or authorization.get('reviewed_normal_entry_browser_cleanup') is not True):
        raise ValueError('Original launch/exit binding and reviewed normal-entry browser cleanup required')
    if (primary.get('attempt_id') != attempt_id or not primary.get('failure_class')
            or (primary.get('failure_class') in ('unknown', 'interrupted') if definite
                else primary.get('failure_class') != 'interrupted')
            or type(closed.get('exit_code')) is not int or closed['exit_code'] != 0):
        raise ValueError('Original naturally exited process and closed browser required')
    rows = failed_execution_trajectory(record)
    terminal = record['terminal']; ending = terminal.get('collection_ending') or {}
    if (terminal.get('actual_actions') != len(rows)
            or ending.get('unverified_tail_dispatches') != 0
            or {str(p.resolve()) for p in raw.glob('*-dispatch-intent.json')} != {r['dispatch']['path'] for r in rows}
            or {str(p.resolve()) for p in (raw.parent/'action-attempts').glob('*.json')} != {r['raw_step']['path'] for r in rows}):
        raise ValueError('All original browser dispatches must have verified after evidence')
    binding = validate_task_binding(record['task'])
    frozen = load_json(binding['claim_reference']['path'])
    claim = CandidatePool(frozen['pool'], readonly=True).get_claim(binding['claim_id'])
    owner = claim.get('binding') or {}
    scope = load_json(intent['scope'])
    intended_output = Path(intent['output_root'])/report.name/'consumer' if transport else Path(intent.get('output', ''))
    if (intent.get('candidate_id') != binding['candidate_id']
            or intended_output.resolve()/binding['claim_id'] != Path(owner.get('output', '')).resolve()
            or raw != Path(owner['output']).resolve()/'execution/capture/evidence'/raw.parent.name/'raw'
            or Path(scope['registry']).resolve() != Path(registry).resolve()
            or Path(scope['consumer_db']).resolve() != Path(owner['ledger']).resolve()):
        raise ValueError('Original run intent and scope must bind this candidate, output and ledger')
    if owner.get('attempt_id') != attempt_id or Path(owner.get('registry', '')).resolve() != Path(registry).resolve():
        raise ValueError('Original claim and runtime registry differ')
    with closing(workspace_connect(Path(registry).resolve().as_uri()+'?mode=ro', uri=True)) as con:
        row = con.execute('SELECT a.status,a.failure_class,a.root_cause,t.task_json,a.sample_id FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.attempt_id=?', (attempt_id,)).fetchone()
    if not row or row[:3] != ('rejected', primary.get('failure_class'), primary.get('error')):
        raise ValueError('Original rejected attempt and failure must remain unchanged')
    original_task = json.loads(row[3])
    executed_task = dict(record['task'])
    for name, expected in (('_plan_schema_version', load_json(raw.parents[2]/'plan.json')['schema_version']),
                           ('require_public_origin', True)):
        if name not in original_task and executed_task.pop(name, None) != expected:
            raise ValueError('Original runner flags differ from frozen plan')
    if original_task != executed_task or row[4] != raw.parent.name:
        raise ValueError('Original registered task/sample differs from sealed execution')
    with closing(workspace_connect(Path(owner['ledger']).resolve().as_uri()+'?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        requests = list(con.execute("SELECT id,state,error,response,request_json,usage,cost,purpose FROM model_requests WHERE json_extract(request_json,'$.dispatch_attempt_id')=?", (attempt_id,)))
    unknown = [row for row in requests if row['state'] not in ('succeeded', 'invalid_response')]
    if transport:
        if (len(unknown) != 1 or unknown[0]['id'] != authorization.get('request_id')
                or terminal.get('unknown') is not True):
            raise ValueError('Exactly one original planning transport UNKNOWN required')
        request = unknown[0]; response = json.loads(request['response'] or '{}')
        payload = json.loads(request['request_json'] or '{}')
        prompt = json.loads(payload.get('text') or '{}')
        if (request['state'] != 'unknown' or request['error'] != 'TimeoutError'
                or response != {'transport_error': {'error_type':'TimeoutError','reason_type':'TimeoutError'}}
                or request['usage'] is not None or request['cost'] is not None
                or not request['purpose'].startswith('screenshot_plan:')
                or payload.get('protocol') != 'native-tools' or payload.get('dispatch_attempt_id') != attempt_id
                or [tool.get('function',{}).get('name') for tool in payload.get('tools',[])] != ['plan_decision']
                or prompt.get('phase') != 'branch' or prompt.get('attempt_id') != attempt_id
                or prompt.get('goal') != terminal.get('working_goal')
                or prompt.get('current_observation') != terminal.get('final_observation_id')):
            raise ValueError('Only a pure screenshot planning transport timeout can be isolated')
        business = [load_json(path) for path in raw.glob('*-business-attempt.json')]
        if (len(business) != ending.get('business_attempts')
                or any(item.get('outcome') not in ('VERIFIED','NOT_DISPATCHED') for item in business)
                or any(item.get('actual_dispatches_delta') != 0 for item in business if item.get('outcome') == 'NOT_DISPATCHED')
                or sum(item.get('actual_dispatches_delta',0) for item in business) != len(rows)
                or not rows or rows[-1]['after_observation_id'] != terminal.get('final_observation_id')):
            raise ValueError('Transport timeout has an unclosed browser business attempt')
        from .session_objective import bind as bind_objective
        objective_ref = authorization['objective']; verify_evidence([objective_ref])
        bind_objective(objective_ref, claim)
        if (file_sha(Path(owner['output'])/'session-objective.json') != objective_ref['sha256']
                or load_json(objective_ref['path']) != intent.get('fixed_objective_value')
                or intent.get('strategy') != 'screenshot_plan'):
            raise ValueError('Timeout isolation changes the original frozen goal')
        permit_scope = load_json(authorization['bounded_authorization']['path'])
        verify_evidence([authorization['bounded_authorization']])
        next_round = authorization.get('next_round')
        next_request = authorization.get('next_request_id')
        if (type(next_round) is not int or next_round != int(report.name.split('-')[-1])+1
                or not 1 <= next_round <= min(5, intent.get('maximum_attempts',0))
                or next_request != intent['run_id']+f'-r{next_round:02d}/new-research'
                or permit_scope.get('run_id') != intent['run_id'] or permit_scope.get('maximum_attempts') != intent['maximum_attempts']
                or permit_scope.get('candidate_id') != binding['candidate_id'] or permit_scope.get('production_counted') is not False
                or Path(permit_scope.get('pool','')).resolve() != Path(frozen['pool']).resolve()
                or Path(permit_scope.get('registry','')).resolve() != Path(registry).resolve()):
            raise ValueError('Timeout isolation requires the exact next bounded research request')
        return {'attempt_id':attempt_id,'claim_id':binding['claim_id'],'candidate_id':binding['candidate_id'],
                'pool':frozen['pool'],'ledger':owner['ledger'],'request_id':request['id'],
                'next_request_id':next_request,'verified_dispatches':len(rows),
                'usage':'UNKNOWN','cost':'UNKNOWN','original_fields_retained':True}
    if definite:
        if record['terminal'].get('unknown') is not False or not requests or unknown:
            raise ValueError('Definite execution requires all original requests answered and no UNKNOWN terminal')
        return {'attempt_id': attempt_id, 'claim_id': binding['claim_id'],
                'candidate_id': binding['candidate_id'], 'ledger': owner['ledger'],
                'verified_dispatches': len(rows),
                'request_states': {row['id']: row['state'] for row in requests},
                'original_fields_retained': True}
    if len(unknown) != 1 or unknown[0]['id'] != authorization.get('request_id'):
        raise ValueError('Exactly the authorized original rejected request must remain UNKNOWN')
    request = unknown[0]; response = json.loads(request['response'] or '{}')
    provider = response.get('provider_error') or {}
    if (request['state'] != 'unknown' or request['error'] != 'HTTPError:400'
            or provider.get('http_status') != 400 or str(provider.get('provider_code')) != '1210'
            or provider.get('reason') != 'provider_http_error'
            or any(response.get(key) for key in ('choices', 'output', 'tool_calls', 'arguments'))):
        raise ValueError('Only definite HTTP400/1210 parameter rejection without model actions qualifies')
    return {'attempt_id': attempt_id, 'claim_id': binding['claim_id'],
            'candidate_id': binding['candidate_id'], 'request_id': request['id'],
            'ledger': owner['ledger'], 'verified_dispatches': len(rows),
            'usage': 'UNKNOWN', 'cost': 'UNKNOWN', 'original_fields_retained': True}


def http400_closed_execution(registry, attempt_id, authorization):
    return _closed_execution(registry, attempt_id, authorization)


def definite_closed_execution(registry, attempt_id, authorization):
    """Known failed execution can be retried; its format-review job stays intact."""
    return _closed_execution(registry, attempt_id, authorization, definite=True)


def authorized_http400_retry(registry, attempt_id):
    """An appended explicit permit closes execution only, never model accounting."""
    from .batch_core import load_json
    from .planning import verify_evidence
    with closing(workspace_connect(Path(registry).resolve().as_uri()+'?mode=ro', uri=True)) as con:
        events = list(con.execute("SELECT payload_json FROM m4_events WHERE event_type IN ('http400_new_attempt_authorized','closed_execution_new_attempt_authorized') AND attempt_id=?", (attempt_id,)))
    for raw in events:
        event = json.loads(raw[0]); ref = event['authorization']
        verify_evidence([ref])
        verify = definite_closed_execution if event.get('definite_execution') else http400_closed_execution
        if verify(registry, attempt_id, load_json(ref['path'])) == event['closed_execution']:
            return True
    return False


def accounted_closed_execution(registry, attempt_id, *, research_request_id=None):
    return (authorized_http400_retry(registry, attempt_id) or accounted_rejected_focus(registry, attempt_id)
            or authorized_transport_research(registry, attempt_id, request_id=research_request_id))


def transport_closed_execution(registry, attempt_id, authorization):
    """Account browser effects without settling a timed-out planning request."""
    return _closed_execution(registry, attempt_id, authorization, transport=True)


def authorized_transport_research(registry, attempt_id, *, request_id=None):
    """Require the exact request identity; never infer caller scope from activity."""
    if not request_id:
        return False
    from .batch_core import load_json
    from .planning import verify_evidence
    with closing(workspace_connect(Path(registry).resolve().as_uri()+'?mode=ro', uri=True)) as con:
        events = con.execute("SELECT payload_json FROM m4_events WHERE event_type='planning_timeout_research_authorized' AND attempt_id=?",(attempt_id,)).fetchall()
    for (raw,) in events:
        event=json.loads(raw); reference=event['authorization'];verify_evidence([reference])
        facts=transport_closed_execution(registry,attempt_id,load_json(reference['path']))
        if facts != event['closed_execution']:continue
        if request_id != facts['next_request_id']:continue
        with closing(workspace_connect(Path(facts['pool']).resolve().as_uri()+'?mode=ro',uri=True)) as con:
            row=con.execute('SELECT state,binding,candidate_id,expires,version FROM candidate_claims WHERE request_id=?',(request_id,)).fetchone()
            original=con.execute('SELECT candidate_id,version FROM candidate_claims WHERE claim_id=?',(facts['claim_id'],)).fetchone()
        if row is None:
            return True  # Exact permit, before this request's sole claim exists.
        import time
        if (not original or row[0]!='consuming' or row[2]!=facts['candidate_id']
                or (row[2],row[4]) != tuple(original) or row[3]<=time.time()):continue
        binding=json.loads(row[1]);replay=binding.get('research_replay') or {}
        if (replay.get('original_claim_id')!=facts['claim_id'] or replay.get('production_counted') is not False
                or Path(binding.get('ledger','')).resolve()!=Path(facts['ledger']).resolve()
                or Path(binding.get('registry','')).resolve()!=Path(registry).resolve()):continue
        verify_evidence([replay['authorization']])
        own_authorization=load_json(replay['authorization']['path'])
        if own_authorization.get('new_request_id')==request_id:return True
    return False


def _verify_execution_entry(registry, attempt_id, authorization, report, started, *, transport):
    """Bind actual recorded launch sources; retain only already sealed old permits."""
    from .batch_core import load_json
    from .planning import verify_evidence
    root=report.parent if transport else report
    if (Path(authorization['run_intent']['path']).resolve()!=root/'run-intent.json'
            or Path(authorization['process_start']['path']).resolve()!=report/'process.json'):
        raise ValueError('Execution intent/process references differ from the original report')
    if transport and 'command' in started:
        command=started['command']
        if (not isinstance(command,list) or len(command)!=3 or not all(isinstance(x,str) for x in command)
                or not Path(command[0]).is_absolute() or not Path(command[0]).is_file()
                or started.get('launcher')!=authorization['launcher']
                or started.get('worker')!=authorization['worker']
                or Path(command[1]).resolve()!=Path(authorization['worker']['path']).resolve()
                or Path(command[2]).resolve()!=report):
            raise ValueError('Recorded actual execution command and source hashes differ')
        verify_evidence([started['launcher'],started['worker']])
        return
    if any(Path(authorization[key]['path']).resolve()!=root/name
           for key,name in (('launcher','launch.py'),('worker','worker.py'))):
        raise ValueError('Unrecorded execution source cannot substitute another launcher or worker')
    if transport:
        # Only the already appended original permit has reviewed old static
        # entry evidence. New executions must record their actual command.
        with closing(workspace_connect(Path(registry).resolve().as_uri()+'?mode=ro',uri=True)) as con:
            events=con.execute("SELECT payload_json FROM m4_events WHERE event_type='planning_timeout_research_authorized' AND attempt_id=?",(attempt_id,)).fetchall()
        for (raw,) in events:
            reference=json.loads(raw)['authorization'];verify_evidence([reference])
            if load_json(reference['path'])==authorization:return
        raise ValueError('New timeout isolation requires recorded actual launch command evidence')
