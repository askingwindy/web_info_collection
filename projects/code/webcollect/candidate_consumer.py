"""Claim before any observation/planning; reuse ordinary generation and collection.

Only --run performs IO; claim/list/reconcile never launch discovery, models or a
browser. Reconciliation reads original ledgers and receipts, never re-executes.
"""
import argparse
import asyncio
from contextlib import closing, asynccontextmanager, AsyncExitStack
import json
from pathlib import Path
import sqlite3
import time
from site_planner.candidate_pool import CandidatePool, VERSION2 as CANDIDATE_VERSION2
from .batch_core import BatchLedger, BudgetStop, load_json, file_sha, OutcomeUnknown, save_json
from .planning import canonical, verify_evidence
from .agent_controller import exclusive
from .candidate_contract import capability
from .request_quarantine import job_conflicts


def guard_request_scope(ledger, uri, *, candidate_id=None, research_request_id=None):
    """Check original request ownership before any browser/model dispatch."""
    from .application_identity import canonical_key
    from .current_chain import PROJECT_RULES
    from .request_quarantine import endpoint
    guard = ledger.config.get('site_failure_guard') or {}
    aliases = guard.get('application_registry')
    scoped = guard.get('dispatch_rules')==PROJECT_RULES
    isolated = []
    with ledger.connect() as con:
        requests = con.execute("""SELECT m.id,m.state,m.error,j.payload,
                json_extract(m.request_json,'$.dispatch_attempt_id') AS dispatch_attempt,
                json_extract(p.payload,'$.registry') AS registry
            FROM model_requests m LEFT JOIN jobs j ON j.id=m.job_id
            LEFT JOIN jobs p ON p.id=json_extract(j.payload,'$.parent_job_id')
            WHERE m.state IN ('reserved','unknown')""").fetchall()
        for row in requests:
            if row['state'] == 'unknown' and ledger.timeout_retry_answered(con, row['id']):
                continue  # Original UNKNOWN usage remains; its bounded retry supplied a response.
            payload = json.loads(row['payload']) if row['payload'] else {}
            site = payload.get('site_uri')
            if job_conflicts(
                    ledger,uri,candidate_id,payload,running=row['state']=='reserved',
                    registry=row['registry'],dispatched_attempt=row['dispatch_attempt'],candidate_only=True,research_request_id=research_request_id):
                raise OutcomeUnknown('Original model request unresolved for this scope; no dispatch: ' + row['id'])
            isolated.append({'kind':'model_request','id':row['id'],'site_uri':site,'state':row['state']})
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='top_level_visits'").fetchone():
            for row in con.execute("SELECT id,state,target_uri FROM top_level_visits WHERE state IN ('reserved_for_dispatch','unknown')"):
                target = row['target_uri']
                if scoped:
                    blocked = False  # Original job/purpose is fenced by reserve_visit.
                else:
                    blocked = False  # Never turn another navigation into a batch hold.
                if blocked:
                    raise OutcomeUnknown('Original navigation unresolved for this scope; no dispatch: '+row['id'])
                isolated.append({'kind':'navigation','id':row['id'],'site_uri':row['target_uri'],'state':row['state']})
    return isolated


def guard_candidate_dispatch(ledger, uri, *, candidate_id, research_request_id=None):
    """Read-only preflight shared by candidate selection, collection and targeted recovery."""
    isolated = guard_request_scope(ledger, uri, candidate_id=candidate_id,research_request_id=research_request_id)
    guard = ledger.config.get('site_failure_guard')
    # Formal planning also checks unfinished decision jobs, including those
    # without a reserved HTTP request. Use the same owner resolver here before
    # selection/first visit rather than discover this only after claim.
    with ledger.connect() as con:
        jobs = con.execute("""SELECT j.id,j.state,j.payload,json_extract(p.payload,'$.registry') AS registry
            FROM jobs j LEFT JOIN jobs p ON p.id=json_extract(j.payload,'$.parent_job_id')
            WHERE j.kind IN ('task-generation','fragment-decision','react-decision','react-native-decision')
            AND j.state IN ('queued','running','review_required')""").fetchall()
    for row in jobs:
        if job_conflicts(ledger, uri, candidate_id, json.loads(row['payload']),
                         running=row['state']=='running', registry=row['registry'],candidate_only=True,research_request_id=research_request_id):
            raise OutcomeUnknown('Original planning job unresolved for this scope; no dispatch: '+row['id'])
    # Site facts may not yet have ingested a just-interrupted formal attempt.
    # Consult its owning original registry read-only, as formal site_context does.
    from .current_chain import PROJECT_RULES, registry_project, check_project_guard
    registry=ledger.path.with_name('production-registry.sqlite3')
    if (guard or {}).get('dispatch_rules') == PROJECT_RULES and registry.is_file():
        from .application_identity import canonical_key
        with closing(sqlite3.connect(registry.as_uri()+'?mode=ro',uri=True)) as con:
            scope=registry_project(con)
            check_project_guard(scope,guard,ledger.path,role='consumer')
            attempts=con.execute("""SELECT a.attempt_id,t.task_json FROM m4_attempts a
                JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.campaign_id=?
                AND (a.status IN ('reserved','running','interrupted') OR a.failure_class IN ('unknown','interrupted'))""",
                (scope['chain_id'],)).fetchall()
        for attempt_id,raw in attempts:
            task=json.loads(raw);owner=(task.get('candidate_binding') or {}).get('candidate_id')
            conflict=bool(owner and owner==candidate_id)
            if conflict:
                from .request_quarantine import accounted_closed_execution
                if accounted_closed_execution(registry,attempt_id,research_request_id=research_request_id):continue
                raise OutcomeUnknown('Original formal attempt unresolved for this scope; no dispatch: '+attempt_id)
    return isolated


def _original_attempts(claim):
    binding=claim.get('binding') or {}
    registry=binding.get('registry')
    if not registry or not Path(registry).is_file(): return []
    with closing(sqlite3.connect(Path(registry).resolve().as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='m4_attempts'").fetchone(): return []
        rows=[]
        for r in con.execute('SELECT a.*,t.task_json FROM m4_attempts a JOIN m4_tasks t ON a.task_key=t.task_key'):
            task=json.loads(r['task_json']); cb=task.get('candidate_binding',{})
            if cb.get('candidate_id')==claim['candidate_id'] and cb.get('claim_id')==claim['claim_id']:
                rows.append((dict(r),task))
        return rows


def settle_unstarted_research(pool, claim_id, *, process_exit):
    """Settle one returned zero-attempt research failure; preserve production state."""
    verify_evidence([process_exit]);closed=load_json(process_exit['path'])
    if closed.get('claim_id')!=claim_id or type(closed.get('returncode')) is not int:
        raise ValueError('Original closed process receipt required')
    claim=pool.get_claim(claim_id);research=pool.research_claim(claim)
    if not research or claim['state']!='reconcile':raise ValueError('Only a reconciliable research execution is eligible')
    original=pool.get_claim(research['original_claim_id'])
    proof=known_unstarted_historical_claim(claim,original['binding'])
    if not proof:raise ValueError('Research requests, visits or formal actions remain unresolved')
    with pool.transaction() as con:
        row=con.execute('SELECT state,binding FROM candidate_claims WHERE claim_id=?',(claim_id,)).fetchone()
        if row['state']!='reconcile' or json.loads(row['binding'])!=claim['binding']:
            raise ValueError('Research binding changed during reconciliation')
        con.execute("UPDATE candidate_claims SET state='failed',reason='known_unstarted_research_failure',updated=? WHERE claim_id=?",(time.time(),claim_id))
        pool.event(con,claim['candidate_id'],claim_id,'research_unstarted_reconciled',{'process_exit':process_exit,'proof':proof})
    return pool.get_claim(claim_id)


def known_unstarted_historical_claim(claim, successor_binding):
    """Read-only proof for an expired pre-execution error, not UNKNOWN clearance."""
    b=claim.get('binding') or {}
    if not b.get('ledger') or not b.get('registry') or any(b.get(k)!=successor_binding.get(k) for k in ('ledger','registry')):
        return None
    if not Path(b['registry']).is_file() or _original_attempts(claim):return None
    with closing(sqlite3.connect(Path(b['ledger']).resolve().as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        jobs=[dict(r) for r in con.execute('SELECT id,kind,state,payload FROM jobs')]
        ids={r['id'] for r in jobs if json.loads(r['payload']).get('claim_id')==claim['claim_id'] or r['id']==b.get('queue_job_id')}
        if not ids:return None
        edges=list(con.execute('SELECT job_id,parent_id FROM job_parents')) if con.execute("SELECT 1 FROM sqlite_master WHERE name='job_parents'").fetchone() else []
        while True:
            expanded=ids|{r['id'] for r in jobs if json.loads(r['payload']).get('parent_job_id') in ids}|{r['job_id'] for r in edges if r['parent_id'] in ids}
            if expanded==ids:break
            ids=expanded
        chosen=[r for r in jobs if r['id'] in ids]
        if any(not ((r['kind']=='candidate-observation' and r['state']=='done') or
                    (r['kind']=='frozen-plan' and r['state']=='queued')) for r in chosen):return None
        requests=[dict(r) for r in con.execute('SELECT id,job_id,state FROM model_requests') if r['job_id'] in ids]
        visits=[dict(r) for r in con.execute('SELECT id,job_id,state FROM top_level_visits') if r['job_id'] in ids]
        if requests or any(r['state']!='succeeded' for r in visits):return None
    return {'claim_id':claim['claim_id'],'proof':'expired_historical_zero_formal_attempt_zero_model_request',
            'jobs':[{k:r[k] for k in ('id','kind','state')} for r in chosen],'visits':visits,
            'original_registry':b['registry'],'original_ledger':b['ledger'],'original_state_unchanged':True}


def unverified_original_actions(attempt):
    """Read old dispatch gaps conservatively; never reinterpret them as zero actions."""
    references=json.loads(attempt.get('evidence_json') or '[]')
    for ref in references:
        if Path(ref.get('path','')).name != 'raw-receipt.json':
            continue
        verify_evidence([ref])
        raw_root=Path(ref['path']).parent
        receipt=load_json(ref['path'])
        verify_evidence([receipt['terminal']])
        if load_json(receipt['terminal']['path']).get('unknown'):
            from .postprocess import cancelled_dispatch_audit
            from .postprocess import rejected_focus_dispatch_audit
            audited = False
            for candidate in references:
                if Path(candidate.get('path','')).suffix != '.json':continue
                verify_evidence([candidate]);value=load_json(candidate['path'])
                if value.get('schema_version')=='webcollect-cancelled-dispatch-audit-1' and value.get('raw_receipt')==ref:
                    audited = (value==cancelled_dispatch_audit(raw_root)
                               and value['attempt_id']==attempt['attempt_id']
                               and attempt.get('root_cause')=='host_cancelled_between_verified_actions'
                               and attempt['status']=='rejected')
                if value.get('schema_version')=='webcollect-rejected-focus-dispatch-audit-1' and value.get('raw_receipt')==ref:
                    audited=(value==rejected_focus_dispatch_audit(raw_root)
                             and value['attempt_id']==attempt['attempt_id']
                             and (attempt.get('root_cause')=='rejected_focus_effect_audited'
                                  or (attempt.get('root_cause')==load_json(value['original_failure']['path'])['error']
                                      and attempt.get('failure_class')=='interrupted'))
                             and attempt['status']=='rejected')
            if not audited:yield receipt['terminal']
            continue
        from .postprocess import session_record
        record=session_record(raw_root)
        root=raw_root.parent
        for path in sorted(root.glob('step_*.json')):
            raw=load_json(path)
            if (raw.get('dispatched') is True and raw.get('action_executed') is True
                    and raw.get('phase')=='post_dispatch' and raw.get('react')
                    and raw['react'].get('after_observation_id') not in record['observations']):
                yield {'path':str(path),'sha256':file_sha(path)}


def verified_saved(claim):
    """Only RuntimeStore committed pending attempts with a complete receipt qualify."""
    found=[]
    for row,task in _original_attempts(claim):
        if row['status']!='collected_pending_review': continue
        from .candidate_contract import validate_task_binding
        cb=validate_task_binding(task)
        if cb['candidate']!=claim['snapshot'] or cb['version']!=claim['version']: raise ValueError('Runtime target differs from claim')
        refs=json.loads(row['evidence_json']); verify_evidence(refs)
        from .production_identity import verify_saved
        verify_saved(task,row['sample_id'],refs)
        receipts=[r for r in refs if Path(r['path']).name=='saved_sample.json']
        if len(receipts)!=1: raise ValueError('Complete original save receipt required')
        receipt=receipts[0]; saved=load_json(receipt['path']); raw=Path(receipt['path']).parent
        sample=raw.parent.parent/'samples'/row['sample_id']
        if saved.get('sample_id')!=row['sample_id']: raise ValueError('Saved sample ID mismatch')
        for base,key in ((sample,'sample_files_sha256'),(raw,'capture_files_sha256')):
            files=saved.get(key)
            if not files or 'annotation.json' not in files and key=='sample_files_sha256': raise ValueError('Incomplete receipt')
            for name,digest in files.items():
                p=base/name
                if Path(name).is_absolute() or p.is_symlink() or not p.resolve().is_relative_to(base.resolve()) or file_sha(p)!=digest:
                    raise ValueError('Saved bytes changed')
        stop_details = saved.get('raw_execution', {}).get('stop_details')
        prefix = saved.get('raw_execution', {}).get('trusted_prefix')
        found.append({'registry':claim['binding']['registry'],'attempt_id':row['attempt_id'],'task_key':row['task_key'],
            **({'stop_details':stop_details} if stop_details else {}),
            **({'trusted_prefix':prefix,'original_goal_completed':False} if prefix else {}),
            'sample_id':row['sample_id'],'save_receipt':receipt,'result_location':str(sample), 'scope_id':row['scope_id']})
    if len(found)>1: raise ValueError('More than one saved result for candidate claim; reconciliation required')
    return found[0] if found else None


def finish_or_reconcile(pool, claim, *, reconciliation=False):
    """Expired token never commits; explicit reconciler derives facts from original stores."""
    original=pool.get_claim(claim['claim_id'])
    descriptor=pool.research_claim(original)
    research=bool(descriptor)
    with pool.pool.connect() as con:
        latest=con.execute('SELECT claim_id FROM candidate_claims WHERE candidate_id=? ORDER BY created DESC LIMIT 1',(claim['candidate_id'],)).fetchone()
    if latest[0]!=claim['claim_id']:
        raise ValueError('Historical claim cannot replace a newer explicit consumption attempt')
    if original['token']!=claim['token'] or original['snapshot']!=claim['snapshot']: raise ValueError('Original claim credential/target differs')
    result=verified_saved(original)
    if not result:
        if reconciliation and original['state']=='consuming' and original['expires']<=time.time():
            with pool.transaction() as con:
                con.execute("UPDATE candidate_claims SET state='reconcile',reason='lease_expired',updated=? WHERE claim_id=? AND state='consuming'",(time.time(),claim['claim_id']))
                if not research:
                    con.execute("UPDATE data_candidates SET state='reconcile' WHERE candidate_id=?",(claim['candidate_id'],))
                pool.event(con,claim['candidate_id'],claim['claim_id'],'lease_expired',{})
            original=pool.get_claim(claim['claim_id'])
        return {'state':original['state'],'saved':False,'reason':'No committed complete save; inspect original model/visit/runtime ledgers; no resend'}
    if research and descriptor.get('schema_version') in ('candidate-research-replay-1', 'candidate-research-replay-2',
                                                         'candidate-research-replay-3', 'candidate-research-replay'):
        result = {**result, 'research_replay': descriptor, 'production_counted': False}
    with pool.transaction() as con:
        latest=con.execute('SELECT claim_id FROM candidate_claims WHERE candidate_id=? ORDER BY created DESC LIMIT 1',(claim['candidate_id'],)).fetchone()
        own_result=con.execute('SELECT effective FROM candidate_results WHERE candidate_id=? AND claim_id=?',
                               (claim['candidate_id'],claim['claim_id'])).fetchone()
        if latest[0]!=claim['claim_id'] or own_result and not own_result[0] and not research:
            raise ValueError('Retired claim cannot replace an explicit retry')
        if not reconciliation and original['state']!='succeeded':
            pool._fence(con,claim)
        elif not reconciliation and original['expires'] <= time.time():
            raise ValueError('Expired token cannot commit; explicit receipt reconciliation required')
        elif original['state'] not in ('consuming','reconcile','succeeded','failed'):
            raise ValueError('Not reconcilable')
        previous=con.execute('SELECT record FROM candidate_results WHERE candidate_id=? AND effective=1',(claim['candidate_id'],)).fetchone()
        if previous and previous[0]!=canonical(result) and not research: raise ValueError('One effective result per candidate; old result retained')
        con.execute('INSERT OR IGNORE INTO candidate_results VALUES(?,?,?,?,?,NULL,?)',
            (claim['candidate_id'],claim['claim_id'],result['sample_id'],canonical(result),'pending_review',0 if research else 1))
        con.execute("UPDATE candidate_claims SET state='succeeded',stage='saved',updated=? WHERE claim_id=?",(time.time(),claim['claim_id']))
        if not research:
            con.execute("UPDATE data_candidates SET state='succeeded' WHERE candidate_id=?",(claim['candidate_id'],))
        pool.event(con,claim['candidate_id'],claim['claim_id'],'saved_reconciled' if reconciliation else 'saved',result)
    from .site_pool_sync import sync_candidate_qc
    sync_candidate_qc(pool.path,result['registry'])
    with pool.pool.connect() as con:
        qc = con.execute('SELECT qc_state FROM candidate_results WHERE candidate_id=? AND claim_id=?',
            (claim['candidate_id'], claim['claim_id'])).fetchone()
    return {'state':'succeeded','saved':True,'result':result,'QC':qc['qc_state']}


def planning_failure(ledger, pending):
    """Retain UNKNOWN; close only proved zero-send/settled failures, never retry."""
    outcomes=[]
    for item in pending:
        jid=item['job_id']; job=ledger.get(jid)
        with ledger.connect() as con:
            requests=[dict(r) for r in con.execute('SELECT state,error FROM model_requests WHERE job_id=?',(jid,))]
        if any(r['state'] in ('reserved','unknown') for r in requests): outcome='UNKNOWN'
        elif requests: outcome='DEFINITE_MODEL_FAILURE'
        elif item['state']=='budget_stopped' or job.get('error') in ('ValueError','KeyError','FileNotFoundError'):
            outcome='LOCAL_NOT_SENT'
        else: outcome='UNKNOWN'
        outcomes.append({'job_id':jid,'outcome':outcome,'original_error':job.get('error')})
        if outcome!='UNKNOWN' and job['state']=='review_required':
            with ledger.transaction() as con:
                con.execute("UPDATE jobs SET state='failed' WHERE id=? AND state='review_required'",(jid,))
                ledger.event(con,'candidate_definite_planning_failure',outcomes[-1])
    return ('reconcile' if any(r['outcome']=='UNKNOWN' for r in outcomes) else 'failed'),outcomes


def _entry_hints(claim):
    """Display hints for candidate entries: the body carries only protocol/kind/
    URL/goal, so classification stays in frozen sources."""
    from site_planner.site_pool import host_identity
    from site_planner.qualification import BUSINESS_CATEGORIES as CANONICAL_CATEGORIES
    snapshot = claim['snapshot']
    category = 'UNKNOWN'
    category_proven = False
    name = None
    for source in claim.get('sources') or []:
        hint = source.get('category_hint')
        if hint in CANONICAL_CATEGORIES and category == 'UNKNOWN':
            category = hint
            category_proven = True
        if name is None and source.get('application_hint'):
            name = source['application_hint']
    from site_planner.entry_selection import confirmed_category
    confirmed = confirmed_category(claim.get('sources') or [])
    if confirmed is not None:
        category_proven = confirmed in CANONICAL_CATEGORIES
        category = confirmed if category_proven else 'UNKNOWN'
    return {'category': category, 'name': host_identity(snapshot['entry_url']),
            'category_proven': category_proven}


def startup_check(ledger, *, output, registry, policy, history_set, qc_policy=None, pool=None, before_claim=False):
    """Validate the original local execution scope before taking a candidate."""
    from .current_chain import read_chain_history, assert_registry_scope, current_evidence_roots
    from .runtime import validate_policy
    paths = {}
    for key, value in dict(output=output, registry=registry, policy=policy, history_set=history_set).items():
        path = Path(value).absolute()
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Consumer execution paths cannot use symlinks')
        paths[key] = str(path.resolve())
    _, scope = read_chain_history(paths['history_set'])
    assert_registry_scope(scope, paths['registry'])
    from .current_chain import check_project_guard, check_project_pool
    check_project_guard(scope, ledger.config.get('site_failure_guard'), ledger.path, role='consumer')
    if pool is not None:
        check_project_pool(scope, pool.pool)
    if scope.get('candidate_project'):
        from .current_chain import assert_current_result_path
        assert_current_result_path(scope, paths['output'])
    elif not any(Path(paths['output']).is_relative_to(p) for p in current_evidence_roots(scope)):
        raise ValueError('Consumer evidence must stay inside the original current-chain roots')
    supplied = validate_policy(load_json(paths['policy']))
    if ledger.config.get('site_failure_guard') != supplied.get('site_failure_guard'):
        raise ValueError('Consumer must use the original whole-application failure guard')
    if ledger.config['mode'] != 'real':
        raise ValueError('Synthetic consumers must patch IO boundaries in offline tests')
    if qc_policy is not None:
        from .task_generation import _qc_policy
        _qc_policy(qc_policy)
    with closing(sqlite3.connect(Path(paths['registry']).as_uri()+'?mode=ro',uri=True)) as con:
        row = con.execute('SELECT policy_json FROM m4_campaigns WHERE campaign_id=?', (supplied['campaign_id'],)).fetchone()
        if not row or json.loads(row[0]) != supplied:
            raise ValueError('Consumer must use the exact original authorized campaign policy')
    return paths


def preflight_candidate_sources(registry, sources):
    """Validate the same evidence closure as execution, before browser dispatch."""
    from .current_chain import CurrentChainError, assert_current_evidence, scope_for_registry
    if not isinstance(sources, list) or not sources:
        raise CurrentChainError('candidate source evidence is missing')
    for source in sources:
        try:
            verify_evidence(source['references'])
        except (KeyError, TypeError, ValueError, OSError) as error:
            raise CurrentChainError('invalid candidate source evidence: ' + str(error)) from error
    assert_current_evidence(scope_for_registry(registry), sources)


def preflight_cohort_sources(pool, rows, registry):
    """Read only the frozen cohort's inputs; do not claim, probe or navigate."""
    from .current_chain import CurrentChainError
    from .planning import object_sha256
    with closing(sqlite3.connect(pool.path.as_uri() + '?mode=ro', uri=True)) as con:
        for row in rows:
            sources = [json.loads(source[0]) for source in con.execute(
                'SELECT source FROM candidate_sources WHERE candidate_id=? ORDER BY created,source_key',
                (row['candidate_id'],))]
            if row.get('sources_sha256') and object_sha256(sources) != row['sources_sha256']:
                raise CurrentChainError('frozen candidate sources changed: ' + row['candidate_id'])
            try:
                if row.get('sources_sha256'):
                    # This is the exact reference consumed by claim_next, not
                    # a new visit. Validate it before any worker account/browser IO.
                    reference = row['entry_http']
                    verify_evidence([reference])
                    if not any(source.get('entry_http') == reference for source in sources):
                        raise ValueError('entry_http is not an original candidate source')
                preflight_candidate_sources(registry, sources)
            except CurrentChainError as error:
                error.candidate_id = row['candidate_id']
                raise
            except (KeyError, TypeError, ValueError, OSError) as error:
                fault = CurrentChainError('invalid frozen candidate claim input: ' + str(error))
                fault.candidate_id = row['candidate_id']
                raise fault from error


@asynccontextmanager
async def entry_session(ledger, pool, claim, root, *, session_soft_seconds=None, session_hard_seconds=None):
    """One owned page from the first accounted visit through formal close-out."""
    import time as _time
    limits = ledger.config.get('session_limits') or {}
    soft = int(session_soft_seconds or limits.get('soft_seconds') or 1800)
    hard = int(session_hard_seconds or (soft + int(limits.get('closeout_grace_seconds') or 120)))
    if hard <= soft:
        raise ValueError('Session hard deadline must leave a closeout grace after the soft deadline')
    host_limits = {'soft_seconds': soft, 'hard_seconds': hard,
                   'started_monotonic': _time.monotonic()}
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    from .browser import capture
    from .navigation import BatchNavigation, NavigationTimeoutError
    from .production_quality import require_public_task_state
    from .candidate_contract import application_matches
    from .telemetry import phase
    from .site_failure_stop import SiteFailureStore, execution_id
    uri = claim['snapshot']['entry_url']
    guard = ledger.config.get('site_failure_guard')
    guard_candidate_dispatch(ledger, uri, candidate_id=claim['candidate_id'],
        research_request_id=claim['request_id'] if pool.research_claim(claim) else None)
    jid = ledger.enqueue('candidate-observation', {'claim_id': claim['claim_id'], 'site_uri': uri})
    previous = ledger.get(jid)
    if previous['state'] != 'queued' or previous['attempts']:
        raise OutcomeUnknown('Original entry observation already started; reconcile without dispatch')
    from .consumer_lifecycle import claim_job
    job = await claim_job(ledger, 'candidate-observation', job_id=jid)
    if not job:
        raise OutcomeUnknown('Original entry observation not claimable')
    browser = context = None
    observed = False
    access_rejection = None
    try:
        ledger.consume('probe_pages', jid, 1)
        async with async_playwright() as pw:
            try:
                with pool.transaction() as con:
                    pool._fence(con, claim)
                browser = await pw.chromium.launch(channel='chrome', headless=True)
                context = await browser.new_context(viewport={'width':1280,'height':720}, device_scale_factor=1,
                    locale='zh-CN', timezone_id='Asia/Shanghai', service_workers='block', accept_downloads=False)
                page = await context.new_page()
                with pool.transaction() as con:
                    pool._fence(con, claim)
                with phase(root/'phases.jsonl', 'entry_navigation', scope={'claim_id':claim['claim_id']}):
                    try:
                        entry_response = await BatchNavigation(ledger, job).goto(page, uri, purpose='candidate-entry:'+claim['claim_id'], timeout_ms=30000)
                    except PlaywrightTimeoutError as error:
                        # BatchNavigation has already settled this explicit visit as failed.
                        raise NavigationTimeoutError(uri, 'candidate-entry:'+claim['claim_id'], 30) from error
                with phase(root/'phases.jsonl', 'entry_capture_identity_save', scope={'claim_id':claim['claim_id']}):
                    from .action_stability import post_action_document_scope
                    entry_scope = post_action_document_scope({'url': uri})
                    entry_scope['purpose'] = 'entry_observation'
                    captured = await capture(page, action_scope=entry_scope)
                    try:
                        require_public_task_state(captured['state'])
                    except ValueError as rejected:
                        access_rejection = rejected
                        raise
                    html = await page.content()
                    prefix = 'first'
                    with (root/(prefix+'.png')).open('xb') as image:
                        image.write(captured['png'])
                    anchor = {'image': {'path': str(root/(prefix+'.png')), 'sha256': file_sha(root/(prefix+'.png'))},
                        'state': exclusive(root/(prefix+'-state.json'),captured['state']),
                        'capture': exclusive(root/(prefix+'-capture.json'),captured['capture'])}
                    entry_http_reference = None
                    if captured['state']['url'] != uri:
                        from .navigation import capture_http_chain
                        entry_http = await capture_http_chain(entry_response,uri,captured['state']['url'],
                            source_url=uri,operation_id='candidate-entry:'+claim['claim_id'],page=page)
                        entry_http_reference = exclusive(root/'first-entry-http.json',entry_http)
                    from .consumer_page_policy import full_image
                    image_failure=full_image(captured['state'])
                    if image_failure:
                        # No action/plan will use this frame. Retain the trusted
                        # capture and reject immediately, without live re-probes.
                        exclusive(root/'first-frame-image-policy.json',image_failure)
    
                visits = [v['id'] for v in ledger.visits() if v['job_id']==jid]
                ledger.finish(job, result=anchor)
                observed = True
                def bind_attempt(attempt):
                    pool.stage(claim, 'execution', {'attempt_id':attempt['attempt_id'], 'entry_job_id':jid, 'entry_visit_ids':visits})
                    with ledger.transaction() as con:
                        ledger.event(con, 'candidate_entry_attempt', {'claim_id':claim['claim_id'],
                            'attempt_id':attempt['attempt_id'], 'job_id':jid, 'visit_ids':visits})
                yield {'browser':browser, 'context':context, 'page':page, 'anchor':anchor,
                    'claim_id':claim['claim_id'], 'entry_http':entry_http_reference,
                    'entry_observation':{'captured':captured,'html':html},
                    'host_limits':host_limits, 'bind_attempt':bind_attempt}
            finally:
                try:
                    if context is not None:
                        await context.close()
                finally:
                    if browser is not None:
                        await browser.close()
    except BaseException as error:
        if not observed:
            failure = exclusive(root/'first-observation-failure.json', {'job_id':jid, 'stage':'entry_observation',
                'error_type':type(error).__name__, 'reason':str(error), 'accepted_as_formal_frame':False,
                'capture':getattr(error,'capture',None)})
            visits = [v for v in ledger.visits() if v['job_id']==jid]
            # Navigation already records its own failure or UNKNOWN in the ledger.
            # A local capture, identity or file error does not establish a site failure.
            if guard and access_rejection is not None and visits and visits[-1]['state']=='succeeded':
                SiteFailureStore(guard).record({'site_uri':uri}, execution_id('candidate-observation',ledger.path,jid),
                    stage='observation', state='failed', real_execution=True, reason=str(access_rejection), evidence=[failure],
                    usage_refs=[{'ledger':str(ledger.path),'job_id':jid,'visit_id':visits[-1]['id']}])
            ledger.finish(job, 'review_required', error=type(error).__name__)
        raise


def release_observation(ledger, pool, claim):
    """Finish a settled observation-only claim while leaving the candidate pending."""
    from .candidate_feedback import _frame
    from .planning import object_sha256
    current=pool.get_claim(claim['claim_id'])
    binding=current.get('binding') or {}
    if not binding.get('first_frame_only') or current['stage']!='observation':
        raise ValueError('Only an explicit observation-only claim can be released')
    if any(binding.get(k) for k in ('attempt_id','planning_jobs','sample_id')):
        raise ValueError('Formal execution cannot be released as observation-only')
    with ledger.connect() as con:
        jobs=con.execute("SELECT * FROM jobs WHERE kind='candidate-observation' AND json_extract(payload,'$.claim_id')=?",(claim['claim_id'],)).fetchall()
        if len(jobs)!=1:raise ValueError('One original observation job required')
        job=dict(jobs[0]);visits=[dict(r) for r in con.execute('SELECT * FROM top_level_visits WHERE job_id=? ORDER BY dispatched_at,id',(job['id'],))]
        if len(visits)!=1 or visits[0]['state']!='succeeded':
            raise ValueError('Observation visit must be settled successfully')
        other=con.execute("SELECT 1 FROM jobs WHERE id!=? AND (json_extract(payload,'$.claim_id')=? OR json_extract(payload,'$.candidate_binding.claim_id')=?) LIMIT 1",(job['id'],claim['claim_id'],claim['claim_id'])).fetchone()
        if other:raise ValueError('Claim has other work; retain original state')
    valid,availability,evidence=_frame(job,visits[0],claim['snapshot']['entry_url'],claim.get('application_registry'))
    if not valid:raise ValueError('Verified original first frame required before release')
    with pool.transaction() as con:
        pool._fence(con,claim)
        con.execute("UPDATE candidate_claims SET state='observed',stage='first_frame_only_complete',reason=?,updated=? WHERE claim_id=?",
                    ('Settled observation-only receipt; candidate remains available for formal consumption',time.time(),claim['claim_id']))
        con.execute("UPDATE data_candidates SET state='pending' WHERE candidate_id=?",(claim['candidate_id'],))
        pool.event(con,claim['candidate_id'],claim['claim_id'],'observation_complete',{'ledger':str(ledger.path),'job_id':job['id'],'visit_id':visits[0]['id'],'evidence':evidence,'availability':availability})
    return {'state':'observed','candidate_state':'pending','job_id':job['id'],'evidence':evidence}


def normalize_entry_url(url):
    """Merge safe URL-form differences for task-duplicate matching: scheme
    upgrade (http==https), lowercase host, percent-decoded path, default-port
    drop. Genuine redirects (.html drop, path changes) stay distinct -- only
    the live browser observation can resolve those."""
    from urllib.parse import urlsplit, urlunsplit, unquote
    if not isinstance(url, str) or not url:
        return url
    parts = urlsplit(url.strip())
    scheme = 'https' if parts.scheme in ('http', 'https') else parts.scheme.lower()
    host = (parts.hostname or '').lower()
    if parts.port and parts.port not in (80, 443):
        host = f'{host}:{parts.port}'
    return urlunsplit((scheme, host, unquote(parts.path or '/'), parts.query, parts.fragment))


def tasked_entry_index(registry_path):
    """Normalized (entry_url, requested_goal) pairs that already hold consumer
    tasks. A fresh candidate re-deriving an existing task's key would be
    refused as a paused duplicate only after burning a claim and an entry
    observation; the 2026-11-06 effort experiment lost 28% of its pages to
    exactly this."""
    import sqlite3
    con = sqlite3.connect(f"file:{Path(registry_path).resolve()}?mode=ro", uri=True)
    try:
        pairs = set()
        for (task_json,) in con.execute('SELECT task_json FROM m4_tasks'):
            try:
                task = json.loads(task_json)
            except (TypeError, ValueError):
                continue
            goal = ((task.get('workflow_proposal') or {}).get('spec') or {}).get('goal', {}).get('structured')
            pairs.add((normalize_entry_url(task.get('initial_url')), canonical(goal)))
        return pairs
    finally:
        con.close()


def settle_cancelled_claim(pool, claim):
    """Local receipt close-out only; a valid owner fence remains mandatory."""
    current = pool.get_claim(claim['claim_id'])
    if current['state'] != 'consuming':
        return {'state':current['state'], 'cancel_closeout':'already_settled'}
    with pool.transaction() as con:
        pool._fence(con, claim)
    # Reuse the normal committed-save validator and commit path. This never
    # dispatches browser/model work, nor touches request/runtime UNKNOWN state.
    result = finish_or_reconcile(pool, claim)
    if result.get('saved'):
        return result
    current = pool.get_claim(claim['claim_id'])
    if current['state'] != 'consuming':
        return {'state':current['state'], 'cancel_closeout':'already_settled'}
    # The claimed stage precedes observation dispatch. All later stages can
    # contain in-flight or UNKNOWN work and require explicit reconciliation.
    undispatched = current['stage'] == 'claimed' and not _original_attempts(current)
    state = 'failed' if undispatched else 'reconcile'
    pool.finish(claim, state=state, stage=current['stage'],
                reason='Cancelled before dispatch' if undispatched else
                       'Cancelled without committed complete save; retain original requests and attempts; no resend')
    return {'state':state, 'saved':False, 'cancel_closeout':'local_facts_only'}


async def consume(pool, claim, ledger, **kwargs):
    """Renew from claim preparation through close-out, including synchronous IO."""
    import threading
    if claim.get('state') != 'consuming':
        return {'state':claim.get('state'), 'dispatched':False}
    pool.heartbeat(claim)
    loop = asyncio.get_running_loop()
    caller = asyncio.current_task()
    stop = threading.Event()
    lost = []
    lease_cancelled = False
    runlog = kwargs.get('runlog')

    def receipt(event, **fields):
        if runlog is not None:
            runlog.info(event, claimId=claim['claim_id'], taskName=owner.get_name(), **fields)

    def cancel_for_lease(error):
        # Queued callbacks own this claim's child, never the worker poller.
        nonlocal lease_cancelled
        receipt('lease_cancel_requested', errorType=type(error).__name__, reason=str(error)[:200])
        if stop.is_set() or owner.done():
            receipt('lease_cancel_ignored', reason='claim_task_finished')
            return
        try:
            current = pool.get_claim(claim['claim_id'])
            if current['state'] != 'consuming':
                receipt('lease_cancel_ignored', reason='claim_already_settled', claimState=current['state'])
                return
        except Exception:
            # Unreadable ownership is not permission to continue dispatch.
            pass
        lost.append(error)
        lease_cancelled = owner.cancel('candidate_lease_lost')
        receipt('lease_cancel_applied', cancelled=lease_cancelled)

    def renew_claim():
        current = claim
        while not stop.wait(2):
            try:
                current = pool.get_claim(claim['claim_id'])
                if current['state'] != 'consuming':
                    return
                pool.heartbeat(claim)
            except sqlite3.OperationalError as error:
                # A busy short writer does not prove a lost lease. Retry only
                # within the last confirmed lease; heartbeat still fences it.
                if (getattr(error, 'sqlite_errorcode', 0) & 255) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    if current and current.get('expires', 0) > time.time():
                        continue
                loop.call_soon_threadsafe(cancel_for_lease, error)
                return
            except Exception as error:
                loop.call_soon_threadsafe(cancel_for_lease, error)
                return

    async def claim_work():
        try:
            thread.start()
            return await _consume(pool, claim, ledger, **kwargs)
        finally:
            # Invalidate callbacks before the child wakes its caller. A daemon
            # observes stop after its short transaction; no blocking join.
            stop.set()
            receipt('claim_task_finished', reason='lease_monitor_stopped')

    thread = threading.Thread(target=renew_claim, daemon=True)
    owner = asyncio.create_task(claim_work(), name='candidate:' + claim['claim_id'])
    try:
        return await owner
    except asyncio.CancelledError:
        # Genuine worker cancellation remains cancellation even when racing a
        # lease callback. Never clear cancellation state or swallow the signal.
        if lease_cancelled and not caller.cancelling():
            receipt('claim_cancelled', reason='candidate_lease_lost')
            raise ValueError('Candidate lease lost; original claim remains fenced') from lost[0]
        receipt('claim_cancelled', reason='worker_or_external_cancel')
        try:
            settle_cancelled_claim(pool, claim)
        except Exception as error:
            receipt('cancel_closeout_unresolved', errorType=type(error).__name__, reason=str(error)[:200])
        raise
    finally:
        stop.set()


async def _consume(pool, claim, ledger, *, output, registry, policy, history_set, qc_policy=None, skip_wechat_articles=False, session_objective=None, effort_profile=None,
                  session_soft_seconds=None, session_hard_seconds=None, collection_strategy=None, runlog=None):
    """Exactly one original claim, one goal and at most one saved result."""
    # 会话软时限/收尾宽限经host_limits贯通到session与网关；软时限后停止
    # 新增业务动作与模型请求，未决请求保留UNKNOWN。
    if claim.get('state')!='consuming': return {'state':claim.get('state'),'dispatched':False}
    current=pool.get_claim(claim['claim_id'])
    if current['token']!=claim['token'] or current['snapshot']!=claim['snapshot']:
        raise ValueError('Original candidate credential or target differs')
    if current['state']!='consuming': return {'state':current['state'],'dispatched':False}
    with pool.transaction() as con: pool._fence(con,claim)
    if current['stage']!='claimed': return finish_or_reconcile(pool,claim)
    snapshot = claim['snapshot']
    # Legacy pre-entry-protocol rows (e.g. webcollect-data-candidate-1) became
    # claimable again when the protocol filter was removed; their frozen bodies
    # lack the entry/target goal contract this consumer executes. Settle the
    # claim cleanly instead of crashing mid-dispatch and leaving it consuming.
    if (not isinstance(snapshot, dict) or snapshot.get('schema_version') != CANDIDATE_VERSION2
            or snapshot.get('candidate_kind') not in ('entry', 'target')
            or not isinstance(snapshot.get('entry_url'), str)
            or 'requested_goal' not in snapshot):
        reason = ('LEGACY_SNAPSHOT: claimed candidate body is not a current '
                  + CANDIDATE_VERSION2 + ' entry/target snapshot; no dispatch')
        pool.finish(claim, state='failed', stage='claim', reason=reason)
        return {'state': 'failed', 'stage': 'claim', 'reason': reason,
                'formal_attempts': 0, 'browser_calls': 0, 'model_calls': 0}
    paths = startup_check(ledger, output=output, registry=registry, policy=policy, history_set=history_set, qc_policy=qc_policy, pool=pool)
    output, registry, policy, history_set = (paths[k] for k in ('output','registry','policy','history_set'))
    # A never-before-claimed candidate whose entry URL and requested goal already
    # hold a registry task re-derives that task's key: execution would be refused
    # as a paused duplicate. Close it now with zero browser and model cost, before
    # the claim stage advances. Legitimate research/recovery re-runs carry prior
    # claims on the same candidate and pass.
    if (snapshot.get('requested_goal') and not pool.has_prior_claims(claim['candidate_id'], claim['claim_id'])
            and (normalize_entry_url(snapshot.get('entry_url')), canonical(snapshot.get('requested_goal')))
                in tasked_entry_index(registry)):
        reason = 'TASKED_URL_DUPLICATE: 该入口 URL 与目标在注册库已存在任务（task_key 重复）'
        pool.finish(claim, state='failed', stage='claim', reason=reason)
        return {'state': 'failed', 'stage': 'claim', 'reason': reason,
                'formal_attempts': 0, 'browser_calls': 0, 'model_calls': 0}
    supplied_policy = load_json(policy)
    objective_binding=None
    if session_objective is not None:
        from .session_objective import bind
        objective_binding=bind(session_objective,claim)
    research=pool.research_claim(current)
    if research and session_objective!=research['objective']:
        raise ValueError('Research must use frozen original objective reference')
    isolated_unknown = guard_candidate_dispatch(ledger, claim['snapshot']['entry_url'], candidate_id=claim['candidate_id'],
        research_request_id=claim['request_id'] if research else None)
    root = Path(output)/claim['claim_id']
    # The transaction elects the sole executor before directories or external IO.
    won = pool.stage(claim, 'observation', {'registry':registry, 'ledger':str(ledger.path),
        'output':str(root), 'policy':policy, 'history_set':history_set,
        'isolated_unknown':isolated_unknown}, expected_stage='claimed')
    if not won:
        return finish_or_reconcile(pool, claim)
    from .current_chain import CurrentChainError
    try:
        preflight_candidate_sources(registry, current.get('sources'))
    except CurrentChainError as error:
        # The elected executor has only performed local input checks.
        # No observation job, browser or model request has been dispatched here.
        pool.finish(claim, state='failed', stage='input_preflight',
                    reason=type(error).__name__ + ': ' + str(error))
        error.no_dispatch_proof = {'claim_id': claim['claim_id'],
            'proof': 'source_preflight_before_observation', 'browser_calls': 0,
            'model_calls': 0, 'formal_attempts': 0}
        raise
    root.mkdir(parents=True, exist_ok=False)
    if objective_binding is not None:
        # A user goal is input metadata, not an out-of-chain observation. Freeze
        # the exact validated bytes inside this original project's claim root.
        original_reference=objective_binding['reference']
        local_reference=exclusive(root/'session-objective.json',load_json(original_reference['path']))
        exclusive(root/'session-objective-binding.json',{'original':original_reference,'local':local_reference,
            'candidate_id':claim['candidate_id'],'version':claim['version']})
        objective_binding={**objective_binding,'reference':local_reference}
    claim = {**current, 'pool':str(pool.path),
        'application_registry':supplied_policy.get('site_failure_guard',{}).get('application_registry'),
        'site_id_version':'table1-rowid-site-id-1',
        'site_id':pool.delivery_site_id(claim['candidate_id'])}
    if runlog is not None:
        runlog.attach(siteId=claim['site_id'])
    claim_ref = exclusive(root/'claim.json', claim)
    pool.stage(claim, 'observation', {'claim_reference':claim_ref})
    async def renew():
        while True:
            await asyncio.sleep(2)
    stage='observation'
    if runlog is not None:
        runlog.info('processing', stage='observation')
    async def work_in(stack):
        nonlocal stage
        snapshot = claim['snapshot']
        for source in claim.get('sources',[]):
            verify_evidence(source['references'])
        from .task_generation import generate, execute
        session = await stack.enter_async_context(entry_session(ledger, pool, claim, root,
            session_soft_seconds=session_soft_seconds, session_hard_seconds=session_hard_seconds))
        from .candidate_batch import first_frame_disposition, VERSION as ROUTING_VERSION
        route = first_frame_disposition(load_json(session['anchor']['state']['path']))
        if route:
            disposition, reason = route
            from .consumer_page_policy import LOGIN_ENTRY_VERSION
            route_policy = LOGIN_ENTRY_VERSION if reason in ('login_page', 'explicit_login_required_to_use') else ROUTING_VERSION
            pool.record_disposition(claim, disposition=disposition, reason=reason, stage='first_frame',
                evidence=list(session['anchor'].values()), policy_version=route_policy)
            if runlog is not None:
                runlog.info('abandoned', disposition=disposition, reason=reason, stage='first_frame')
            return {'state':'failed', 'disposition':disposition, 'reason':reason, 'formal_attempts':0}
        hints = _entry_hints(claim)
        record = capability(claim, session['anchor'], claim_ref, ledger.config['mode'],
            category=hints['category'], name=hints['name'],entry_http=session.get('entry_http'))
        # Consumer evidence belongs to this claim/attempt. Table1's site
        # identity, category, page inventory and availability are producer-owned.
        catalog = root/'catalog.json'
        exclusive(catalog, {'schema_version':'capability-catalog','mode':ledger.config['mode'],'records':[record]})
        from .single_record import identity
        identities = root/'identities.json'
        identity(catalog, identities, registry=registry, candidate_observation=True)
        pool.stage(claim, 'planning', {'catalog':str(catalog)})
        stage = 'planning'
        if runlog is not None:
            runlog.info('processing', stage='planning')
        generated = await asyncio.to_thread(generate, ledger, catalog, root/'planning',
            generator='react-url', history_registry=registry, history_set=history_set,
            react_url=record['site_uri'], react_goal=snapshot['requested_goal'], page_identities=identities,
            react_site_category=hints['category'], react_app_name=hints['name'],
            react_candidate={'claim':claim,'claim_reference':claim_ref,'skip_wechat_articles':skip_wechat_articles,'session_objective':objective_binding,
                **({'effort_profile':effort_profile} if effort_profile else {}),
                **({'collection_strategy':collection_strategy} if collection_strategy else {})})
        catalog = root/'planning/catalog.json'
        exclusive(root/'planning/generation-result.json',generated)
        pool.stage(claim,'planned',{'planning_result':str(root/'planning/generation-result.json'),
            'planning_jobs':[r['job_id'] for r in generated.get('model_responses',[])]})
        if generated.get('pending'):
            state,outcomes=planning_failure(ledger,generated['pending'])
            pool.finish(claim,state=state,stage='planning',reason=canonical(outcomes))
            if runlog is not None:
                runlog.info('failed', stage='planning', state=state, reason=canonical(outcomes)[:200])
            return {'state':state,'stage':'planning','requests':outcomes,'formal_attempts':0}
        if not generated['generated_tasks']:
            pool.finish(claim,state='failed',stage='planning',reason=canonical(generated)); return {'state':'failed','stage':'planning','formal_attempts':0}
        plan=root/'planning/plan.json'; stage='execution'
        if runlog is not None:
            runlog.info('processing', stage='execution')
        pool.stage(claim,stage,{'plan':str(plan),'queue_job_id':generated.get('queue_job_id')})
        execution=await execute(ledger,plan,catalog,root/'execution',registry,policy,qc_policy=qc_policy,site_pool=pool.path,
            entry_session=session, runlog=runlog)
        pool.stage(claim,'save_reconciliation',{'execution_result':execution})
        result=finish_or_reconcile(pool,claim)
        if not result.get('saved'):
            stop = execution.get('collection', {}).get('resource_stop')
            if stop and ledger.config.get('site_failure_guard',{}).get('dispatch_rules'):
                pool.finish(claim,state='reconcile',stage='execution',reason=canonical(stop))
                return {'state':'reconcile','execution':execution,'resource_stop':stop}
            uncertain=any(r['status'] in ('reserved','running','interrupted') or r.get('failure_class') in ('unknown','interrupted') for r,t in _original_attempts(pool.get_claim(claim['claim_id'])))
            pool.finish(claim,state='reconcile' if uncertain else 'failed',stage='execution',reason=canonical(execution))
            result={'state':'reconcile' if uncertain else 'failed','execution':execution}
        return result
    async def work():
        async with AsyncExitStack() as stack:
            try:
                return await work_in(stack)
            finally:
                keeper.cancel()
                await asyncio.gather(keeper, return_exceptions=True)
    keeper=asyncio.create_task(renew()); working=asyncio.create_task(work())
    try:
        done,_=await asyncio.wait((keeper,working),return_when=asyncio.FIRST_COMPLETED)
        if keeper in done and not keeper.cancelled():
            keeper.result()
            raise ValueError('Candidate heartbeat stopped')
        return await working
    except BaseException as error:
        # Drain Runtime and collection close-out before deriving the claim outcome.
        if not working.done(): working.cancel()
        await asyncio.gather(working, return_exceptions=True)
        # Cross-process failure is conservative. Original requests/attempts are never reset.
        try:
            reconciled=finish_or_reconcile(pool,claim)
            if reconciled.get('saved'):
                if isinstance(error, asyncio.CancelledError): raise
                return reconciled
            from .navigation import NavigationTimeoutError
            entry_timeout = stage=='observation' and isinstance(error, NavigationTimeoutError)
            no_dispatch = None
            if isinstance(error, CurrentChainError):
                original = pool.get_claim(claim['claim_id'])
                no_dispatch = known_unstarted_historical_claim(original, original.get('binding') or {})
                if no_dispatch:
                    error.no_dispatch_proof = no_dispatch
            state='failed' if entry_timeout or no_dispatch else ('reconcile' if stage=='execution' or isinstance(error,(OutcomeUnknown,asyncio.CancelledError,TimeoutError)) else 'failed')
            pool.finish(claim,state=state,stage=stage,reason=type(error).__name__+': '+str(error))
            from .navigation import NavigationHTTPError
            if stage=='observation' and isinstance(error,NavigationHTTPError) and error.status==403:
                failure=root/'first-observation-failure.json'
                pool.record_disposition(pool.get_claim(claim['claim_id']),disposition='abandon',
                    reason='entry_http_403',stage='entry_availability',
                    evidence=[claim_ref,{'path':str(failure),'sha256':file_sha(failure)}],
                    policy_version='candidate-entry-403-user-rule-20261105')
        except Exception:
            pass  # A lost lease stays fenced; the explicit reconciler handles it.
        raise
    finally:
        for task in (keeper,working):
            if not task.done(): task.cancel()
        await asyncio.gather(keeper,working,return_exceptions=True)


def _cohort_rows(path, pool, registry, batch):
    cohort = load_json(path)
    multi=cohort.get('schema_version') == 'consumer-multibatch-cohort'
    if not multi and cohort.get('schema_version') != 'webcollect-validation-cohort-1':
        raise ValueError('Unsupported frozen validation cohort')
    scope_ref=cohort['scope'] if multi else cohort['source_scope']
    verify_evidence([scope_ref])
    scope = load_json(scope_ref['path'])
    if ((not multi and scope['batch'] != cohort['producer_batch']) or batch not in (None, scope['batch'])
            or any(Path(v).resolve() != pool.path for v in (scope['pool'],cohort['pool']))
            or any(Path(v).resolve() != Path(registry).resolve() for v in (scope['registry'],cohort['registry']))):
        raise ValueError('Frozen cohort belongs to another project or batch')
    rows = cohort['selected']
    if (not rows or cohort['denominator'] != len(rows)
            or [r['order'] for r in rows] != list(range(1, len(rows) + 1))
            or len({r['candidate_id'] for r in rows}) != len(rows)):
        raise ValueError('Invalid frozen candidate list')
    if multi:
        verify_evidence([cohort['manifest']])
        if Path(cohort['manifest']['path']).resolve()!=Path(scope['history_set']).resolve() or any(not r.get('producer_batch') for r in rows):
            raise ValueError('Multibatch cohort lost original manifest or source batch')
    return scope['batch'] if multi else cohort['producer_batch'], rows


async def run(pool, ledger, *, worker_id, request_prefix, limit=None, categories=None, application_id=None,
              poll_seconds=None, stop_when_empty=False, producer_batch=None, campaign=None, target=None, target_basis='saved', recovery_version=None, cohort=None, skip_wechat_articles=False, session_objective=None, effort_profile=None, collection_strategy=None, log_level='INFO', log_dir=None, **kwargs):
    if effort_profile is not None:
        from .session_core import validate_effort_profile
        effort_profile = validate_effort_profile(effort_profile)
    rows = None
    if cohort is not None:
        if any((categories, application_id, recovery_version, target is not None, poll_seconds is not None)):
            raise ValueError('Frozen cohort defines its own selection and fixed denominator')
        producer_batch, rows = _cohort_rows(cohort, pool, kwargs['registry'], producer_batch)
    skipped = []
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError('Processing limit must be a positive integer')
    if poll_seconds is not None and (type(poll_seconds) is not int or poll_seconds < 1):
        raise ValueError('Polling interval must be a positive number of seconds')
    results=[]
    if target is not None and (type(target) is not int or target < 1 or not producer_batch):
        raise ValueError('Result target requires a positive integer and explicit producer batch')
    if target_basis not in ('saved','qualified'):
        raise ValueError('Target basis must be saved or qualified')
    if recovery_version and not producer_batch:
        raise ValueError('Recovery requires an explicit producer batch')
    from .candidate_batch import report, record_outcome
    stop_reason = 'processing_limit'
    stop_details = None
    poll = processed = 0
    bounded = limit is not None or rows is not None or target is not None
    delay = poll_seconds or 2
    events = Path(kwargs['output']) / (worker_id + '-events.jsonl')
    events.parent.mkdir(parents=True, exist_ok=True)

    def record(event, **value):
        with events.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'at':time.time(), 'event':event, **value}, ensure_ascii=False) + '\n')

    from .current_chain import CurrentChainError

    def stop_dispatch(error, *, phase, claim=None, diagnostic=None):
        nonlocal stop_reason, stop_details
        stop_reason = 'engineering_failure'
        if stop_details is None:
            stop_details = {'error_type': type(error).__name__, 'reason': str(error), 'phase': phase,
                'claim_id': claim.get('claim_id') if claim else None,
                'candidate_id': claim.get('candidate_id') if claim else getattr(error, 'candidate_id', None),
                'evidence_context': getattr(error, 'context', None),
                'no_dispatch_proof': getattr(error, 'no_dispatch_proof', None)}
            if diagnostic:
                stop_details['diagnostic'] = diagnostic
        if campaign:
            try:
                from .consumer_campaign import stop_engineering_failure
                stop_engineering_failure(campaign, stop_details)
            except Exception as stop_error:
                # This worker still stops; report that sibling fencing failed.
                stop_details['campaign_stop_error'] = type(stop_error).__name__ + ': ' + str(stop_error)
        record('engineering_failure', details=stop_details)

    # Campaigns probe centrally before launching workers. A standalone run owns
    # the same startup responsibility, with a stable launch identity so an
    # interrupted/UNKNOWN probe is never replayed on restart.
    try:
        kwargs.update(startup_check(ledger, pool=pool, **kwargs))
        if rows is not None:
            preflight_cohort_sources(pool, rows, kwargs['registry'])
    except Exception as error:
        stop_dispatch(error, phase='startup_preflight')
        return {'denominator': len(rows) if rows is not None else None, 'processed': 0,
                'results': [], 'skipped': [], 'unexamined': len(rows) if rows is not None else None,
                'stop_reason': stop_reason, 'stop_details': stop_details, 'events': str(events)}
    from .key_health import probe_accounts, pool_available
    if not campaign and not await asyncio.to_thread(pool_available, ledger):
        probes = await asyncio.to_thread(probe_accounts, ledger, 'candidate-run:' + request_prefix)
        record('key_health_startup', probes=probes)
    if not await asyncio.to_thread(pool_available, ledger):
        record('key_pool_unavailable', reason='no_available_model_account', application_id=application_id)
        return {'processed': 0, 'results': [], 'stop_reason': 'key_pool_unavailable', 'events': str(events)}

    while limit is None or processed < limit:
        if campaign:
            from .consumer_campaign import stopped
            if stopped(campaign, application_id):
                stop_reason = 'campaign_stopped'
                break
        from .key_health import pool_available
        if not await asyncio.to_thread(pool_available, ledger):
            record('key_pool_unavailable', reason='no_available_model_account', application_id=application_id)
            return {'processed': processed, 'results': results, 'stop_reason': 'key_pool_unavailable', 'events': str(events)}
        if rows is not None and poll >= len(rows):
            stop_reason = 'cohort_exhausted'
            break
        if target is not None and report(pool, producer_batch, target=target, basis=target_basis)['shortfall'] == 0:
            stop_reason = 'target_reached'
            break
        claim = None
        selected = rows[poll] if rows is not None else None
        try:
            try:
                kwargs.update(startup_check(ledger, pool=pool, before_claim=True, **kwargs))
            except Exception as error:
                stop_dispatch(error, phase='before_claim_preflight')
                break
            row_batch = selected.get('producer_batch',producer_batch) if selected else producer_batch
            request_id = f'{request_prefix}/{poll}'
            def claim_next():
                return pool.claim_next(worker_id,request_id,categories=categories,application_id=application_id,
                    **({'candidate_id':selected['candidate_id'], 'frozen_row':selected} if selected else {}),
                    **({'producer_batch':row_batch} if row_batch else {}),
                    **({'recovery_version':recovery_version} if recovery_version else {}))
            if campaign:
                from .consumer_campaign import claim_if_open
                claim = claim_if_open(campaign, claim_next, application_id)
                if claim is None:
                    stop_reason = 'campaign_stopped'
                    break
            else:
                claim = claim_next()
            poll += 1
            if selected and claim['state'] in ('EMPTY','ALREADY_CLAIMED'):
                skipped.append({'candidate_id':selected['candidate_id'],'reason':claim['state']})
                continue
            if claim['state']=='EMPTY':
                record('inventory_empty', application_id=application_id)
                if stop_when_empty:
                    stop_reason = 'candidates_exhausted'
                    break
                await asyncio.sleep(delay)
                continue
            # 一条claim对应一次消费：claim_id本身作为展示sessionId，从领取到收尾全程不变。
            from .runlog import for_claim
            runlog = for_claim(kwargs['output'], worker_id, claim, strategy=collection_strategy,
                               level=log_level, log_dir=log_dir)
            runlog.attach(siteId=claim.get('site_id'))
            runlog.info('claim', claimId=claim['claim_id'], candidateId=claim['candidate_id'])
            try:
                result=await consume(pool,claim,ledger,**kwargs,session_objective=session_objective,
                    collection_strategy=collection_strategy, runlog=runlog,
                    **({'effort_profile':effort_profile} if effort_profile else {}),
                    **({'skip_wechat_articles':True} if skip_wechat_articles else {}))
            except asyncio.CancelledError:
                runlog.info('cancelled', claimId=claim['claim_id'], reason='worker_cancelled')
                if campaign:
                    shutdown=load_json(campaign)
                    record('campaign_worker_cancelled',claim_id=claim['claim_id'],
                           candidate_id=claim['candidate_id'],
                           shutdown_reason=shutdown.get('worker_shutdown_reason') or shutdown.get('stop_reason'),
                           claim_state=pool.get_claim(claim['claim_id'])['state'])
                raise
            except Exception as error:
                import traceback
                diagnostic = {'error_type':type(error).__name__,
                    'stage':claim.get('stage'), 'stage_source':'claim_snapshot',
                    'stack':[{'file':frame.filename, 'line':frame.lineno, 'function':frame.name}
                             for frame in traceback.extract_tb(error.__traceback__)],
                    'sqlite_errorcode':getattr(error, 'sqlite_errorcode', None),
                    'sqlite_errorname':getattr(error, 'sqlite_errorname', None)}
                record('candidate_error', claim_id=claim['claim_id'], diagnostic=diagnostic)
                # A registry busy read that outlived its bounded wait is transient:
                # settle this claim and keep consuming instead of stopping the batch.
                from .registry_db import is_locked
                engineering = isinstance(error, (CurrentChainError, sqlite3.Error, KeyError, NameError, AttributeError, TypeError)) and not is_locked(error)
                if engineering:
                    stop_dispatch(error, phase='candidate_execution', claim=claim, diagnostic=diagnostic)
                runlog.info('failed', claimId=claim['claim_id'],
                    errorType=type(error).__name__, reason=str(error)[:200])
                try:
                    current=pool.get_claim(claim['claim_id'])
                    if current['state']=='consuming':
                        pool.finish(claim,state='reconcile',stage=current['stage'],reason=type(error).__name__+': '+str(error))
                        current=pool.get_claim(claim['claim_id'])
                    result={'state':current['state'],'stage':current['stage'],
                            'reason':current.get('reason') or str(error), 'error_diagnostic':diagnostic}
                    if engineering:
                        result.update(failure_class='program', engineering_failure=True,
                                      no_dispatch_proof=getattr(error, 'no_dispatch_proof', None))
                    elif is_locked(error):
                        result.update(failure_class='transient')
                except sqlite3.Error as settlement_error:
                    # Keep the original failure; no successful settlement is asserted.
                    result={'state':'reconcile', 'stage':claim.get('stage'),
                            'reason':type(error).__name__+': '+str(error),
                            'error_diagnostic':diagnostic,
                            'settlement_error_type':type(settlement_error).__name__}
            # A saved item is queued before optional disposition write-back, so
            # a reporting failure never loses its independent export work.
            if campaign:
                from .consumer_campaign import deliver
                result['campaign_delivery']=deliver(campaign,pool,claim)
            if producer_batch or campaign:
                record_outcome(pool,claim,result)
            result={**result,'claim_id':claim['claim_id'],'candidate_id':claim['candidate_id']}
            processed += 1
            record('candidate_finished',result=result)
            runlog.info('candidate_finished', state=result.get('state'),
                saved=bool(result.get('saved')), stage=result.get('stage'))
            if bounded:results.append(result)
            if stop_reason == 'engineering_failure':
                break
        except Exception as error:
            record('consumer_error',claim_id=claim.get('claim_id') if claim else None,
                   error_type=type(error).__name__,reason=str(error))
            from .registry_db import is_locked
            engineering = isinstance(error, (CurrentChainError, sqlite3.Error, KeyError, NameError, AttributeError, TypeError)) and not is_locked(error)
            if engineering:
                stop_dispatch(error, phase='consumer_loop', claim=claim)
            # Original claims/requests remain fenced. A known shared engineering
            # fault must not consume the next candidate under the same inputs.
            if claim and claim.get('claim_id'):
                processed += 1
                if bounded:results.append({'state':'reconcile','claim_id':claim['claim_id'],'reason':str(error)})
            elif selected:
                skipped.append({'candidate_id':selected['candidate_id'],'reason':str(error)})
                poll += 1
            if stop_reason == 'engineering_failure':
                break
            await asyncio.sleep(delay)
    if rows is not None:
        return {'denominator':len(rows),'processed':processed,'results':results,'skipped':skipped,
                'unexamined':len(rows)-poll,'stop_reason':stop_reason,'stop_details':stop_details}
    if stop_reason == 'engineering_failure':
        return {'processed':processed,'results':results,'stop_reason':stop_reason,
                'stop_details':stop_details,'events':str(events)}
    if target is not None:
        return {'processing_limit':limit,'processed':processed,'stop_reason':stop_reason,'results':results,
                'summary':report(pool,producer_batch,target=target,basis=target_basis)}
    return results if bounded else {'processed':processed,'stop_reason':stop_reason,'events':str(events)}


def guard_original_dispatch(original, *, research_request_id=None):
    """Read the original execution accounts; no retry or state transition."""
    binding = original.get('binding') or {}
    candidate_id = original['candidate_id']
    for row,task in _original_attempts(original):
        from .request_quarantine import authorized_http400_retry, authorized_transport_research
        if (authorized_http400_retry(binding['registry'], row['attempt_id'])
                or authorized_transport_research(binding['registry'],row['attempt_id'],request_id=research_request_id)):
            continue
        if list(unverified_original_actions(row)):
            raise OutcomeUnknown('Original dispatched action has no verified after observation; no retry or replacement attempt')
        if row['status'] in ('reserved','running','interrupted') or row.get('failure_class') in ('unknown','interrupted'):
            from .request_quarantine import accounted_closed_execution
            if not accounted_closed_execution(binding['registry'],row['attempt_id']):
                raise ValueError('Original runtime attempt unresolved; no retry')
    if binding.get('ledger'):
        with closing(sqlite3.connect(Path(binding['ledger']).resolve().as_uri()+'?mode=ro',uri=True)) as con:
            config=json.loads(con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()[0])
            jobs=con.execute("""SELECT j.state,j.payload,json_extract(p.payload,'$.registry') FROM jobs j
                LEFT JOIN jobs p ON p.id=json_extract(j.payload,'$.parent_job_id')
                WHERE j.state IN ('running','review_required') AND j.kind IN ('task-generation','fragment-decision','react-decision','react-native-decision')""").fetchall()
        ledger=BatchLedger(binding['ledger'],config)
        uri=original['snapshot']['entry_url']
        guard_candidate_dispatch(ledger,uri,candidate_id=candidate_id,research_request_id=research_request_id)
        for state,raw,registry in jobs:
            if job_conflicts(ledger,uri,candidate_id,json.loads(raw),running=state=='running',registry=registry,research_request_id=research_request_id):
                raise ValueError('Original planning/decision unresolved for this scope; no retry')


def retry(pool, candidate_id, *, reason, recovery=None, authorization=None, closed_authorization=None):
    """Explicit retry only after reconciling original requests, visits and saves."""
    if not reason: raise ValueError('Explicit retry reason required')
    if authorization and closed_authorization:
        raise ValueError('Choose one original execution authorization')
    definite = bool(closed_authorization)
    authorization = closed_authorization or authorization
    if recovery:
        with pool.pool.connect() as con:
            for r in con.execute("SELECT record FROM candidate_events WHERE candidate_id=? AND kind='disposition'", (candidate_id,)):
                previous = json.loads(r[0])
                if previous.get('fix_version') == recovery['fix_version']:
                    if any(previous.get(k) != v for k, v in recovery.items()):
                        raise ValueError('Repair version already bound to a different recovery selection')
                    return {'candidate_id':candidate_id,'state':'already_recovered','dispatched':False}
    from .site_pool_sync import sync_candidate_qc
    with pool.pool.connect() as con:
        rows=[pool._claim(r) for r in con.execute('SELECT * FROM candidate_claims WHERE candidate_id=? ORDER BY created',(candidate_id,))]
    if not rows: raise ValueError('Candidate has no original consumption attempt')
    original=rows[-1]
    # A committed result always wins over a stale failure projection.
    saved=verified_saved(original)
    if saved: finish_or_reconcile(pool,original,reconciliation=True)
    binding=original.get('binding') or {}
    if binding.get('registry'): sync_candidate_qc(pool.path,binding['registry'])
    if authorization:
        from .runtime import RuntimeStore
        # This is an explicit appended permit, never a rewrite of the old claim.
        with closing(sqlite3.connect(Path(binding['registry']).resolve().as_uri()+'?mode=ro', uri=True)) as con:
            row = con.execute('SELECT scope_id FROM m4_attempts WHERE attempt_id=?', (binding['attempt_id'],)).fetchone()
        RuntimeStore(binding['registry'], row[0]).authorize_http400_new_attempt(
            binding['attempt_id'], authorization={'path': str(Path(authorization).resolve()), 'sha256': file_sha(authorization)}, definite=definite)
    guard_original_dispatch(original)
    with pool.transaction() as con:
        disposition = pool.disposition(con, candidate_id)
        if recovery:
            prior = con.execute("SELECT record FROM candidate_events WHERE candidate_id=? AND kind='disposition'", (candidate_id,)).fetchall()
            if any(json.loads(r[0]).get('fix_version') == recovery['fix_version'] for r in prior):
                return {'candidate_id':candidate_id,'state':'already_recovered','dispatched':False}
            if not disposition or disposition['disposition'] not in ('optimize','reconcile','paused') or disposition['reason'] not in recovery['reasons']:
                raise ValueError('Candidate does not match the selected repair reason')
            verify_evidence(disposition['evidence'])
        elif disposition:
            raise ValueError('Disposition requires targeted recovery or isolated reprocessing')
        latest = con.execute('SELECT claim_id FROM candidate_claims WHERE candidate_id=? ORDER BY created DESC,rowid DESC LIMIT 1', (candidate_id,)).fetchone()
        if latest[0] != original['claim_id']:
            raise ValueError('Candidate gained a newer attempt during reconciliation; inspect original accounts')
        current=con.execute('SELECT state FROM data_candidates WHERE candidate_id=?',(candidate_id,)).fetchone()
        result=con.execute('SELECT qc_state FROM candidate_results WHERE candidate_id=? AND effective=1',(candidate_id,)).fetchone()
        if current['state']=='consuming': raise ValueError('Active holder cannot be retried')
        if current['state']=='succeeded' and (not result or result[0]!='failed'):
            raise ValueError('Saved pending/accepted candidate cannot be consumed again')
        if current['state'] not in ('failed','reconcile','succeeded'): raise ValueError('Candidate is not retryable')
        con.execute('UPDATE candidate_results SET effective=0 WHERE candidate_id=?',(candidate_id,))
        con.execute("UPDATE data_candidates SET state='pending' WHERE candidate_id=?",(candidate_id,))
        pool.event(con,candidate_id,original['claim_id'],'explicit_retry',
            {'reason':reason,'prior_state':current['state'], 'original_disposition':disposition,
             'http400_authorization': str(Path(authorization).resolve()) if authorization else None})
        if recovery:
            pool.event(con,candidate_id,original['claim_id'],'disposition',
                {**disposition, **recovery, 'disposition':'recovery_ready','original_disposition':disposition})
    return {'candidate_id':candidate_id,'state':'pending'}


def statistics(pool):
    counts=pool.stats(); attempts={}; saved=set();research_attempts={};research_saved=set()
    with pool.pool.connect() as con:
        claims=[pool._claim(r) for r in con.execute('SELECT * FROM candidate_claims')]
    for claim in claims:
        for row,task in _original_attempts(claim):
            if pool.research_claim(claim):
                research_attempts[row['attempt_id']]=row
                if row['status']=='collected_pending_review':research_saved.add(row['sample_id'])
            else:
                attempts[row['attempt_id']]=row
                if row['status']=='collected_pending_review': saved.add(row['sample_id'])
    targets={}
    for claim in claims:
        binding=claim.get('binding') or {}
        if binding.get('registry') and binding.get('policy'):
            policy=load_json(binding['policy'])
            with closing(sqlite3.connect(Path(binding['registry']).resolve().as_uri()+'?mode=ro',uri=True)) as con:
                active=con.execute('SELECT policy_json FROM m4_campaigns WHERE campaign_id=?',(policy['campaign_id'],)).fetchone()
                if active: targets[policy['campaign_id']]=json.loads(active[0])['target_total']
    counts.update(formal_attempts=len(attempts),collected=len(saved),qualified_targets=targets,
        research_formal_attempts=len(research_attempts),research_collected=len(research_saved),research_production_counted=False,
        pending_review=counts['QC'].get('pending_review',0),
        QC_accepted=counts['QC'].get('accepted',0)+counts['QC'].get('published',0),
        published=counts['QC'].get('published',0))
    return counts


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--pool',required=True)
    sub=p.add_subparsers(dest='command',required=True)
    listp=sub.add_parser('list')
    retry_p=sub.add_parser('retry'); retry_p.add_argument('--candidate-id',required=True); retry_p.add_argument('--reason',required=True); retry_p.add_argument('--http400-authorization',type=Path); retry_p.add_argument('--closed-execution-authorization',type=Path)
    claim=sub.add_parser('claim'); claim.add_argument('--worker-id',required=True); claim.add_argument('--request-id',required=True)
    reconcile=sub.add_parser('reconcile'); reconcile.add_argument('--claim-id',required=True)
    runp=sub.add_parser('run')
    for name in ('config','ledger','output','registry','policy','history-set','worker-id','request-prefix'): runp.add_argument('--'+name,required=True)
    runp.add_argument('--limit',type=int); runp.add_argument('--category',action='append'); runp.add_argument('--application-id'); runp.add_argument('--qc-policy')
    runp.add_argument('--campaign',type=Path,help='Shared site campaign receipt-counted delivery target')
    runp.add_argument('--cohort',type=Path,help='Visit only never-claimed members of the frozen validation cohort, in order')
    runp.add_argument('--session-objective',type=Path,
        help='Explicit session objective JSON file; bound to the claimed candidate with its SHA256')
    runp.add_argument('--skip-wechat-articles', action='store_true', help='Record observed WeChat article links and skip them for this entry run')
    runp.add_argument('--target',type=int,help='Receipt-counted result target, separate from --limit')
    runp.add_argument('--target-basis',choices=('saved','qualified'),default='saved')
    runp.add_argument('--first-plan-effort',choices=('low','high','max'))
    runp.add_argument('--branch-effort',choices=('low','high','max'))
    runp.add_argument('--recovery-version',help='Only claim the finite candidates prepared for this repair version')
    runp.add_argument('--poll-seconds',type=int,help='Wait this many seconds between empty claims; default waits continuously (2 seconds between empty claims)')
    runp.add_argument('--stop-when-empty',action='store_true',help='Stop with candidates_exhausted instead of polling when the selected inventory is empty')
    from .collection_strategy import STRATEGIES, STRATEGY_BANDED_REACT, STRATEGY_SCREENSHOT_PLAN
    runp.add_argument('--collection-strategy',choices=STRATEGIES,default=STRATEGY_BANDED_REACT,
        help='Freeze the collection strategy for new tasks: react (default, strategy 1) or screenshot_plan (strategy 2)')
    runp.add_argument('--producer-batch',help='Consume only newly published rows from this producer batch; wait when inventory is empty')
    runp.add_argument('--log-level',choices=('INFO','DEBUG'),default='INFO',
        help='Display log level; DEBUG additionally records model input/output to model-debug.jsonl')
    runp.add_argument('--log-dir',type=Path,help='Override the default <output>/logs/<workerId> log directory')
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    for i, value in enumerate(argv):
        if value == '--pool' and i + 1 < len(argv):
            argv = argv[i:i+2] + argv[:i] + argv[i+2:]
            break
        if value.startswith('--pool='):
            argv = [value] + argv[:i] + argv[i+1:]
            break
    a=p.parse_args(argv)
    if a.command == 'run' and bool(a.first_plan_effort) != bool(a.branch_effort):
        p.error('--first-plan-effort and --branch-effort must be specified together')
    session_objective = None
    if a.command == 'run' and a.session_objective is not None:
        objective_path = a.session_objective.resolve(strict=True)
        session_objective = {'path': str(objective_path), 'sha256': file_sha(objective_path)}
        load_json(objective_path)
        verify_evidence([session_objective])
    pool=CandidatePool(a.pool)
    if a.command=='list':
        records=pool.rows()
        from .current_chain import POOL_CHECKPOINT
        marker=pool.pool.checkpoint(*POOL_CHECKPOINT)
        if marker:
            from .candidate_accounting import build_report
            scope=load_json(Path(marker['path']).parent.parent/'scope.json')
            if Path(scope['pool']).resolve()!=pool.path:
                raise ValueError('Candidate list scope belongs to a different pool')
            details={r['candidate_id']:r for r in build_report(scope)['candidates']}
            for r in records:
                detail=details[r['candidate_id']]
                r.update(discovery_tokens=detail['discovery_tokens'],consumer_result=detail['consumer_result'])
        result={'records':records,'statistics':statistics(pool)}
    elif a.command=='retry': result=retry(pool,a.candidate_id,reason=a.reason,authorization=a.http400_authorization,closed_authorization=a.closed_execution_authorization)
    elif a.command=='claim': result=pool.claim_next(a.worker_id,a.request_id)
    elif a.command=='reconcile': result=finish_or_reconcile(pool,pool.get_claim(a.claim_id),reconciliation=True)
    else:
        config = load_json(a.config)
        guard = config.get('site_failure_guard', {})
        new_project = 'dispatch_rules' in guard
        if new_project:
            from .current_chain import read_chain_scope, check_project_pool, check_project_guard
            scope = read_chain_scope(Path(a.history_set).absolute())
            check_project_pool(scope, pool.pool)
            check_project_guard(scope, guard, a.ledger, role='consumer')
        ledger=BatchLedger(a.ledger,config,initialize=new_project)
        if a.campaign:
            import signal
            signal.signal(signal.SIGINT, signal.default_int_handler)
            signal.signal(signal.SIGTERM, signal.default_int_handler)
        result=asyncio.run(run(pool,ledger,worker_id=a.worker_id,request_prefix=a.request_prefix,limit=a.limit,cohort=a.cohort,skip_wechat_articles=a.skip_wechat_articles,
            session_objective=session_objective,
            effort_profile={'first_plan':a.first_plan_effort,'branch':a.branch_effort} if a.first_plan_effort else None,
            categories=a.category,application_id=a.application_id,poll_seconds=a.poll_seconds,stop_when_empty=a.stop_when_empty,producer_batch=a.producer_batch,campaign=a.campaign,target=a.target,target_basis=a.target_basis,recovery_version=a.recovery_version,output=a.output,registry=a.registry,policy=a.policy,history_set=a.history_set,qc_policy=a.qc_policy,
            collection_strategy=a.collection_strategy,log_level=a.log_level,log_dir=a.log_dir))
    print(json.dumps(result,ensure_ascii=False))
    return 2 if isinstance(result, dict) and result.get('stop_reason') == 'engineering_failure' else 0


if __name__=='__main__':
    raise SystemExit(main())
