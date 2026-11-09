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
from site_planner.candidate_pool import CandidatePool
from .batch_core import BatchLedger, BudgetStop, load_json, file_sha, OutcomeUnknown, save_json
from .planning import canonical, verify_evidence
from .agent_controller import exclusive
from .candidate_contract import capability
from .request_quarantine import job_conflicts


def guard_request_scope(ledger, uri, *, candidate_id=None):
    """Check original request ownership before any browser/model dispatch."""
    from .application_identity import canonical_key
    from .current_chain import PROJECT_RULES
    from .request_quarantine import endpoint
    guard = ledger.config.get('site_failure_guard') or {}
    aliases = guard.get('application_registry')
    scoped = guard.get('dispatch_rules')==PROJECT_RULES
    isolated = []
    with ledger.connect() as con:
        from .provider_recovery import holds
        if holds(con):
            raise OutcomeUnknown('Original provider authorization hold; no dispatch')
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
            if str(row['error']).startswith(('HTTPError:401', 'HTTPError:403')) or job_conflicts(
                    ledger,uri,candidate_id,payload,running=row['state']=='reserved',
                    registry=row['registry'],dispatched_attempt=row['dispatch_attempt']):
                raise OutcomeUnknown('Original model request unresolved for this scope; no dispatch: ' + row['id'])
            isolated.append({'kind':'model_request','id':row['id'],'site_uri':site,'state':row['state']})
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='top_level_visits'").fetchone():
            for row in con.execute("SELECT id,state,target_uri FROM top_level_visits WHERE state IN ('reserved_for_dispatch','unknown')"):
                target = row['target_uri']
                if scoped:
                    blocked = not target or bool(uri and endpoint(target,aliases)==endpoint(uri,aliases))
                else:
                    blocked = row['state']=='reserved_for_dispatch' or not target or bool(uri and canonical_key(target,aliases)==canonical_key(uri,aliases))
                if blocked:
                    raise OutcomeUnknown('Original navigation unresolved for this scope; no dispatch: '+row['id'])
                isolated.append({'kind':'navigation','id':row['id'],'site_uri':row['target_uri'],'state':row['state']})
    return isolated


def guard_candidate_dispatch(ledger, uri, *, candidate_id):
    """Read-only preflight shared by candidate selection, collection and targeted recovery."""
    isolated = guard_request_scope(ledger, uri, candidate_id=candidate_id)
    guard = ledger.config.get('site_failure_guard')
    if guard:
        from .site_failure_stop import SiteFailureStore
        SiteFailureStore(guard).guard(uri, candidate_id=candidate_id)
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
                         running=row['state']=='running', registry=row['registry']):
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
            conflict=owner==candidate_id if owner else canonical_key(task['site_uri'],guard.get('application_registry'))==canonical_key(uri,guard.get('application_registry'))
            if conflict:
                from .request_quarantine import accounted_rejected_focus
                if accounted_rejected_focus(registry,attempt_id):continue
                raise OutcomeUnknown('Original formal attempt unresolved for this scope; no dispatch: '+attempt_id)
    return isolated


async def first_observation(ledger, claim, root):
    from playwright.async_api import async_playwright
    from .browser import capture
    from .navigation import BatchNavigation
    from .site_failure_stop import SiteFailureStore
    task={'site_uri':claim['snapshot']['entry_url']}
    guard=ledger.config.get('site_failure_guard')
    guard_candidate_dispatch(ledger, task['site_uri'], candidate_id=claim['candidate_id'])
    jid=ledger.enqueue('candidate-observation',{'claim_id':claim['claim_id'],'site_uri':task['site_uri']})
    old=ledger.get(jid)
    if old['state']=='done':
        verify_evidence(list(old['result'].values())); return old['result']
    if old['state']!='queued' or old['attempts']: raise OutcomeUnknown('Original observation unresolved; reconcile original visits')
    job=ledger.claim('candidate-observation',job_id=jid)
    if not job: raise OutcomeUnknown('Original observation not claimable')
    browser=None; context=None
    try:
        ledger.consume('probe_pages',jid,1)
        async with async_playwright() as pw:
            try:
                browser=await pw.chromium.launch(channel='chrome',headless=True)
                context=await browser.new_context(viewport={'width':1280,'height':720},locale='zh-CN',service_workers='block',accept_downloads=False)
                page=await context.new_page()
                await BatchNavigation(ledger,job).goto(page,task['site_uri'],purpose='candidate-first-observation')
                from .preflight import _wait_visible_readiness, wait_hydration_stable
                exclusive(root/'first-readiness.json',await _wait_visible_readiness(page))
                # Same bounded hydration wait as the entry session: the frozen
                # anchor must be the page this session will actually observe.
                exclusive(root/'first-hydration.json',await wait_hydration_stable(page))
                captured=await capture(page)
                try:
                    layouts=await asyncio.wait_for(page.evaluate('''() => [...document.querySelectorAll('input,textarea,select')].slice(0,32).map(e=>({
                      tag:e.tagName,type:e.getAttribute('type'),name:e.getAttribute('name'),classes:e.className,
                      parents:[e.parentElement,e.parentElement?.parentElement].filter(Boolean).map(p=>({tag:p.tagName,classes:p.className,
                        children:[...p.children].slice(0,8).map(c=>({tag:c.tagName,classes:c.className,
                          leaf_text:c.children.length?'':(c.textContent||'').trim().slice(0,100)}))}))}))'''),3)
                    exclusive(root/'first-control-layouts.json',{'diagnostic_only':True,'layouts':layouts})
                except Exception as diagnostic:
                    exclusive(root/'first-control-layouts.json',{'diagnostic_only':True,'error_type':type(diagnostic).__name__})
                with (root/'first.png').open('xb') as image:
                    image.write(captured['png'])
                anchor={'image':{'path':str(root/'first.png'),'sha256':file_sha(root/'first.png')},
                    'state':exclusive(root/'first-state.json',captured['state']),
                    'capture':exclusive(root/'first-capture.json',captured['capture'])}
                ledger.finish(job,result=anchor)
                return anchor
            finally:
                if context: await context.close()
                if browser: await browser.close()
    except BaseException as error:
        failure={'error_type':type(error).__name__,'reason':str(error),'capture':getattr(error,'capture',None),
                 'job_id':jid,'stage':'first_observation','accepted_as_formal_frame':False}
        failure_ref=exclusive(root/'first-observation-failure.json',failure)
        visits=[v for v in ledger.visits() if v['job_id']==jid]
        if guard and visits and visits[-1]['state']=='succeeded':
            from .site_failure_stop import execution_id
            SiteFailureStore(guard).record(task,execution_id('candidate-observation',ledger.path,jid),
                stage='observation',state='failed',real_execution=True,
                reason=type(error).__name__+': '+str(error),evidence=[failure_ref],
                usage_refs=[{'ledger':str(ledger.path),'job_id':jid,'visit_id':visits[-1]['id']}])
        ledger.finish(job,'review_required',error=type(error).__name__); raise


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
    if research and descriptor.get('schema_version') == 'candidate-research-replay-2':
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
    """Display hints for webcollect-data-candidate-2 entries: the body carries
    only protocol/kind/URL/goal, so classification stays in frozen sources."""
    from site_planner.site_pool import host_identity
    from site_planner.qualification import CANONICAL_CATEGORIES
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


@asynccontextmanager
async def entry_session(ledger, pool, claim, root):
    """One owned page from the first accounted visit through formal close-out."""
    from playwright.async_api import async_playwright
    from .browser import capture, verify_execution_state, EvidenceStale
    from .navigation import BatchNavigation
    from .production_quality import require_public_task_state
    from .candidate_contract import application_matches
    from .preflight import _wait_visible_readiness
    from .site_failure_stop import SiteFailureStore, execution_id
    uri = claim['snapshot']['entry_url']
    guard = ledger.config.get('site_failure_guard')
    guard_candidate_dispatch(ledger, uri, candidate_id=claim['candidate_id'])
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
                await BatchNavigation(ledger, job).goto(page, uri, purpose='candidate-entry:'+claim['claim_id'])
                exclusive(root/'first-readiness.json', await _wait_visible_readiness(page))
                for refresh in range(3):
                    captured = await capture(page)
                    try:
                        require_public_task_state(captured['state'])
                    except ValueError as rejected:
                        access_rejection = rejected
                        raise
                    if not application_matches(uri, captured['state']['url'], claim.get('application_registry')):
                        raise ValueError('Candidate entry landed outside the evidence-backed application')
                    html = await page.content()
                    prefix = 'first' if refresh == 0 else 'first-refresh-'+str(refresh)
                    with (root/(prefix+'.png')).open('xb') as image:
                        image.write(captured['png'])
                    anchor = {'image': {'path': str(root/(prefix+'.png')), 'sha256': file_sha(root/(prefix+'.png'))},
                        'state': exclusive(root/(prefix+'-state.json'),captured['state']),
                        'capture': exclusive(root/(prefix+'-capture.json'),captured['capture'])}
                    from .consumer_page_policy import full_image
                    image_failure=full_image(captured['state'])
                    if image_failure:
                        # No action/plan will use this frame. Retain the trusted
                        # capture and reject immediately, without live re-probes.
                        exclusive(root/'first-frame-image-policy.json',image_failure)
                        break
                    try:
                        await verify_execution_state(page, captured['state'])
                    except EvidenceStale as error:
                        exclusive(root/(prefix+'-stale.json'), {'reason':str(error), 'capture':getattr(error,'capture',None)})
                        if refresh == 2:
                            raise
                        continue
                    # Client hydration may still insert header/navigation after
                    # capture readiness. Freeze the anchor only once the live
                    # DOM reproduces it; a bounded timeout keeps the snapshot.
                    from .preflight import wait_hydration_stable
                    hydration = await wait_hydration_stable(page, reference=captured['state'])
                    exclusive(root/(prefix+'-hydration.json'), hydration)
                    if hydration['status'] == 'stable':
                        break
                    if refresh < 2:
                        continue
                    exclusive(root/'first-hydration-timeout.json', {
                        'status': hydration['status'], 'wait_receipt': hydration,
                        'anchor_retained': True, 'retries_exhausted': True})
                    break
                visits = [v['id'] for v in ledger.visits() if v['job_id']==jid]
                ledger.finish(job, result=anchor)
                observed = True
                def bind_attempt(attempt):
                    pool.stage(claim, 'execution', {'attempt_id':attempt['attempt_id'], 'entry_job_id':jid, 'entry_visit_ids':visits})
                    with ledger.transaction() as con:
                        ledger.event(con, 'candidate_entry_attempt', {'claim_id':claim['claim_id'],
                            'attempt_id':attempt['attempt_id'], 'job_id':jid, 'visit_ids':visits})
                yield {'browser':browser, 'context':context, 'page':page, 'anchor':anchor,
                    'claim_id':claim['claim_id'], 'entry_observation':{'captured':captured,'html':html},
                    'bind_attempt':bind_attempt}
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


async def consume(pool, claim, ledger, *, output, registry, policy, history_set, qc_policy=None, skip_wechat_articles=False, session_objective=None, effort_profile=None,
                  session_soft_seconds=720, session_hard_seconds=900):
    """Exactly one original claim, one goal and at most one saved result."""
    if not 0 < session_soft_seconds < session_hard_seconds:
        raise ValueError('Session limits require 0 < soft < hard')
    session_started = time.monotonic()
    if claim.get('state')!='consuming': return {'state':claim.get('state'),'dispatched':False}
    current=pool.get_claim(claim['claim_id'])
    if current['token']!=claim['token'] or current['snapshot']!=claim['snapshot']:
        raise ValueError('Original candidate credential or target differs')
    if current['state']!='consuming': return {'state':current['state'],'dispatched':False}
    with pool.transaction() as con: pool._fence(con,claim)
    if current['stage']!='claimed': return finish_or_reconcile(pool,claim)
    paths = startup_check(ledger, output=output, registry=registry, policy=policy, history_set=history_set, qc_policy=qc_policy, pool=pool)
    output, registry, policy, history_set = (paths[k] for k in ('output','registry','policy','history_set'))
    snapshot = claim['snapshot']
    # A never-before-claimed candidate whose entry URL and requested goal already
    # hold a registry task re-derives that task's key: execution would be refused
    # as a paused duplicate. Close it now with zero browser and model cost, before
    # the claim stage advances. Legitimate research/recovery re-runs carry prior
    # claims on the same candidate and pass.
    if (not pool.has_prior_claims(claim['candidate_id'], claim['claim_id'])
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
    isolated_unknown = guard_candidate_dispatch(ledger, claim['snapshot']['entry_url'], candidate_id=claim['candidate_id'])
    root = Path(output)/claim['claim_id']
    # The transaction elects the sole executor before directories or external IO.
    won = pool.stage(claim, 'observation', {'registry':registry, 'ledger':str(ledger.path),
        'output':str(root), 'policy':policy, 'history_set':history_set,
        'isolated_unknown':isolated_unknown}, expected_stage='claimed')
    if not won:
        return finish_or_reconcile(pool, claim)
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
        'application_registry':supplied_policy.get('site_failure_guard',{}).get('application_registry')}
    claim_ref = exclusive(root/'claim.json', claim)
    pool.stage(claim, 'observation', {'claim_reference':claim_ref})
    async def renew():
        while True:
            await asyncio.sleep(2); pool.heartbeat(claim)
    stage='observation'
    async def work_in(stack):
        nonlocal stage
        snapshot = claim['snapshot']
        from .task_generation import generate, execute
        session = None
        if snapshot.get('schema_version') == 'webcollect-data-candidate-2':
            session = await stack.enter_async_context(entry_session(ledger, pool, claim, root))
            session['host_limits'] = {'soft_seconds':session_soft_seconds,
                'hard_seconds':session_hard_seconds, 'started_monotonic':session_started}
            from .candidate_batch import first_frame_disposition, VERSION as ROUTING_VERSION
            route = first_frame_disposition(load_json(session['anchor']['state']['path']))
            if route:
                disposition, reason = route
                pool.record_disposition(claim, disposition=disposition, reason=reason, stage='first_frame',
                    evidence=list(session['anchor'].values()), policy_version=ROUTING_VERSION)
                return {'state':'failed', 'disposition':disposition, 'reason':reason, 'formal_attempts':0}
            hints = _entry_hints(claim)
            record = capability(claim, session['anchor'], claim_ref, ledger.config['mode'],
                category=hints['category'], name=hints['name'])
            # Consumer evidence belongs to this claim/attempt. Table1's site
            # identity, category, page inventory and availability are producer-owned.
            catalog = root/'catalog.json'
            exclusive(catalog, {'schema_version':'webcollect-capability-catalog-1','mode':ledger.config['mode'],'records':[record]})
            from .single_record import identity
            identities = root/'identities.json'
            identity(catalog, identities, registry=registry, candidate_observation=True)
            pool.stage(claim, 'planning', {'catalog':str(catalog)})
            stage = 'planning'
            generated = await asyncio.to_thread(generate, ledger, catalog, root/'planning',
                generator='react-url', history_registry=registry, history_set=history_set,
                react_url=record['site_uri'], react_goal=snapshot['requested_goal'], page_identities=identities,
                react_site_category=hints['category'], react_app_name=hints['name'],
                react_candidate={'claim':claim,'claim_reference':claim_ref,'skip_wechat_articles':skip_wechat_articles,'session_objective':objective_binding,
                    **({'effort_profile':effort_profile} if effort_profile else {})})
            catalog = root/'planning/catalog.json'
        else:
            anchor=await first_observation(ledger,claim,root)
            record=capability(claim,anchor,claim_ref,ledger.config['mode'])
            catalog=root/'catalog.json'; exclusive(catalog,{'schema_version':'webcollect-capability-catalog-1','mode':ledger.config['mode'],'records':[record]})
            pool.stage(claim,'planning',{'catalog':str(catalog)}); stage='planning'
            from .single_record import identity
            identities=root/'identities.json'
            identity(catalog,identities,registry=registry,candidate_observation=True)
            generated=await asyncio.to_thread(generate,ledger,catalog,root/'planning',generator='agent-model',history_registry=registry,
                history_set=history_set,page_identities=identities,max_tasks=1,
                fragment_context={'candidate_consumption':record['candidate_observation']})
        exclusive(root/'planning/generation-result.json',generated)
        pool.stage(claim,'planned',{'planning_result':str(root/'planning/generation-result.json'),
            'planning_jobs':[r['job_id'] for r in generated.get('model_responses',[])]})
        if generated.get('pending'):
            state,outcomes=planning_failure(ledger,generated['pending'])
            pool.finish(claim,state=state,stage='planning',reason=canonical(outcomes))
            return {'state':state,'stage':'planning','requests':outcomes,'formal_attempts':0}
        if not generated['generated_tasks']:
            pool.finish(claim,state='failed',stage='planning',reason=canonical(generated)); return {'state':'failed','stage':'planning','formal_attempts':0}
        plan=root/'planning/plan.json'; stage='execution'
        pool.stage(claim,stage,{'plan':str(plan),'queue_job_id':generated.get('queue_job_id')})
        execution=await execute(ledger,plan,catalog,root/'execution',registry,policy,qc_policy=qc_policy,site_pool=pool.path,
            **({'entry_session':session} if session is not None else {}))
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
        done,_=await asyncio.wait((keeper,working),return_when=asyncio.FIRST_COMPLETED,
            timeout=max(0, session_hard_seconds-(time.monotonic()-session_started)))
        if not done:
            raise TimeoutError('consumer_session_hard_deadline')
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
            state='reconcile' if stage=='execution' or isinstance(error,(OutcomeUnknown,asyncio.CancelledError,TimeoutError)) else 'failed'
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
    multi=cohort.get('schema_version') == 'webcollect-consumer-multibatch-cohort-1'
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
              protocols=None, poll_seconds=None, producer_batch=None, target=None, target_basis='saved', recovery_version=None, cohort=None, skip_wechat_articles=False, session_objective=None, **kwargs):
    rows = None
    if cohort is not None:
        if any((categories, application_id, recovery_version, target is not None, poll_seconds is not None)) or protocols not in (None, ('webcollect-data-candidate-2',)):
            raise ValueError('Frozen cohort defines its own selection and fixed denominator')
        producer_batch, rows = _cohort_rows(cohort, pool, kwargs['registry'], producer_batch)
        protocols = ('webcollect-data-candidate-2',)
    skipped = []
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError('Processing limit must be a positive integer')
    if limit is None and not producer_batch:
        limit = 1  # The unscoped entry point claims a single candidate.
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
    from .current_chain import PROJECT_RULES
    from .site_failure_stop import SiteStopped
    project_worker = (ledger.config.get('site_failure_guard') or {}).get('dispatch_rules') == PROJECT_RULES
    stop_reason = 'processing_limit'
    stop_details = None
    poll = 0
    while limit is None or len(results) < limit:
        if rows is not None and poll == len(rows):
            stop_reason = 'cohort_exhausted'
            break
        if target is not None and report(pool, producer_batch, target=target, basis=target_basis)['shortfall'] == 0:
            stop_reason = 'target_reached'
            break
        try:
            checked = startup_check(ledger, pool=pool, before_claim=True, **kwargs)
            if producer_batch or project_worker:
                guard_request_scope(ledger, None)
        except (BudgetStop, OutcomeUnknown) as error:
            if target is None and rows is None:
                raise
            stop_reason = 'resource_pause' if isinstance(error, BudgetStop) else 'account_reconciliation'
            stop_details = {'error_type':type(error).__name__, 'reason':str(error)}
            break
        if 'resource_stop' in checked:
            if target is None and rows is None:
                results.append({'state':'paused', **checked})
            stop_reason = 'resource_pause'
            stop_details = checked['resource_stop']
            break
        kwargs.update(checked)
        selected = rows[poll] if rows is not None else None
        row_batch = selected.get('producer_batch',producer_batch) if selected else producer_batch
        claim=pool.claim_next(worker_id,f'{request_prefix}/{poll}',categories=categories,application_id=application_id,
                              protocols=protocols, **({'candidate_id':selected['candidate_id'], 'frozen_row':selected} if selected else {}),
                              **({'producer_batch': row_batch} if row_batch else {}),
                              **({'recovery_version':recovery_version} if recovery_version else {}))
        poll += 1
        if selected and claim['state'] in ('EMPTY','ALREADY_CLAIMED'):
            skipped.append({'candidate_id':selected['candidate_id'],'reason':claim['state']})
            continue
        if claim['state']=='EMPTY':
            if producer_batch and pool.producer_batch_drained(producer_batch, **({'recovery_version':recovery_version} if recovery_version else {})):
                stop_reason = 'candidates_exhausted'
                break
            if poll_seconds is None:
                if target is None: results.append(claim)
                stop_reason = 'inventory_empty_producer_open'
                break
            await asyncio.sleep(poll_seconds)
            continue
        try:
            result=await consume(pool,claim,ledger,**kwargs,session_objective=session_objective,**({'skip_wechat_articles':True} if skip_wechat_articles else {}))
        except BudgetStop as error:
            if target is None and rows is None: raise
            current = pool.get_claim(claim['claim_id'])
            if current['state'] == 'consuming':
                pool.finish(claim,state='reconcile',stage=current['stage'],reason=str(error))
            result = {'state':'reconcile','resource_stop':{'reason':str(error)}}
        except Exception as error:
            if not producer_batch and not (project_worker and isinstance(error,(SiteStopped,OutcomeUnknown))):
                raise
            current = pool.get_claim(claim['claim_id'])
            if current['state'] == 'consuming' and current['stage'] == 'claimed' and isinstance(error,(SiteStopped,OutcomeUnknown)):
                pool.finish(claim, state='reconcile', stage='claimed', reason=str(error))
                current = pool.get_claim(claim['claim_id'])
            if current['state'] not in ('failed','reconcile'):
                raise
            result = {'state':current['state'], 'stage':current['stage'], 'reason':current.get('reason') or str(error)}
        if producer_batch:
            record_outcome(pool, claim, result)
        results.append({**result, 'claim_id':claim['claim_id'], 'candidate_id':claim['candidate_id']} if producer_batch else result)
        if result.get('resource_stop') or (result['state']=='reconcile' and not (producer_batch or project_worker)):
            stop_reason = 'resource_pause' if result.get('resource_stop') else 'account_reconciliation'
            break
    if rows is not None:
        return {'denominator':len(rows), 'processed':len(results), 'results':results, 'skipped':skipped,
                'unexamined':len(rows)-poll, 'stop_reason':stop_reason, 'stop_details':stop_details}
    if target is None:
        return results
    summary = report(pool, producer_batch, target=target, basis=target_basis)
    if summary['shortfall'] == 0: stop_reason = 'target_reached'
    elif target_basis == 'qualified' and summary['pending_review'] and stop_reason == 'candidates_exhausted':
        stop_reason = 'awaiting_review'
    elif summary['states'].get('reconcile') and stop_reason == 'candidates_exhausted':
        stop_reason = 'account_reconciliation'
    return {'processing_limit':limit, 'processed':len(results), 'stop_reason':stop_reason, 'stop_details':stop_details, 'results':results, 'summary':summary}


def guard_original_dispatch(original):
    """Read the original execution accounts; no retry or state transition."""
    binding = original.get('binding') or {}
    candidate_id = original['candidate_id']
    for row,task in _original_attempts(original):
        if list(unverified_original_actions(row)):
            raise OutcomeUnknown('Original dispatched action has no verified after observation; no retry or replacement attempt')
        if row['status'] in ('reserved','running','interrupted') or row.get('failure_class') in ('unknown','interrupted'):
            from .request_quarantine import accounted_rejected_focus
            if not accounted_rejected_focus(binding['registry'],row['attempt_id']):
                raise ValueError('Original runtime attempt unresolved; no retry')
    if binding.get('ledger'):
        with closing(sqlite3.connect(Path(binding['ledger']).resolve().as_uri()+'?mode=ro',uri=True)) as con:
            config=json.loads(con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()[0])
            jobs=con.execute("""SELECT j.state,j.payload,json_extract(p.payload,'$.registry') FROM jobs j
                LEFT JOIN jobs p ON p.id=json_extract(j.payload,'$.parent_job_id')
                WHERE j.state IN ('running','review_required') AND j.kind IN ('task-generation','fragment-decision','react-decision','react-native-decision')""").fetchall()
        ledger=BatchLedger(binding['ledger'],config)
        uri=original['snapshot']['entry_url']
        guard_candidate_dispatch(ledger,uri,candidate_id=candidate_id)
        for state,raw,registry in jobs:
            if job_conflicts(ledger,uri,candidate_id,json.loads(raw),running=state=='running',registry=registry):
                raise ValueError('Original planning/decision unresolved for this scope; no retry')


def retry(pool, candidate_id, *, reason, recovery=None):
    """Explicit retry only after reconciling original requests, visits and saves."""
    if not reason: raise ValueError('Explicit retry reason required')
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
        pool.event(con,candidate_id,original['claim_id'],'explicit_retry',{'reason':reason,'prior_state':current['state']})
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
    listp.add_argument('--protocol',choices=['legacy','entry'])
    retry_p=sub.add_parser('retry'); retry_p.add_argument('--candidate-id',required=True); retry_p.add_argument('--reason',required=True)
    claim=sub.add_parser('claim'); claim.add_argument('--worker-id',required=True); claim.add_argument('--request-id',required=True)
    claim.add_argument('--protocol',choices=['legacy','entry'],help='legacy=webcollect-data-candidate-1 only (default); entry declares webcollect-data-candidate-2')
    reconcile=sub.add_parser('reconcile'); reconcile.add_argument('--claim-id',required=True)
    runp=sub.add_parser('run')
    for name in ('config','ledger','output','registry','policy','history-set','worker-id','request-prefix'): runp.add_argument('--'+name,required=True)
    runp.add_argument('--limit',type=int); runp.add_argument('--category',action='append'); runp.add_argument('--application-id'); runp.add_argument('--qc-policy')
    runp.add_argument('--cohort',type=Path,help='Visit only never-claimed members of the frozen validation cohort, in order')
    runp.add_argument('--skip-wechat-articles', action='store_true', help='Record observed WeChat article links and skip them for this entry run')
    runp.add_argument('--target',type=int,help='Receipt-counted result target, separate from --limit')
    runp.add_argument('--target-basis',choices=('saved','qualified'),default='saved')
    runp.add_argument('--recovery-version',help='Only claim the finite candidates prepared for this repair version')
    runp.add_argument('--poll-seconds',type=int,help='Wait this many seconds between empty claims; default exits on EMPTY')
    runp.add_argument('--producer-batch',help='Consume only newly published V2 rows from this producer batch; stop when its report is committed and its queue is empty')
    runp.add_argument('--protocol',choices=['legacy','entry'],help='legacy=webcollect-data-candidate-1 only (default); entry declares webcollect-data-candidate-2')
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    for i, value in enumerate(argv):
        if value == '--pool' and i + 1 < len(argv):
            argv = argv[i:i+2] + argv[:i] + argv[i+2:]
            break
        if value.startswith('--pool='):
            argv = [value] + argv[:i] + argv[i+1:]
            break
    a=p.parse_args(argv); pool=CandidatePool(a.pool)
    if a.command=='list':
        records=pool.rows(protocols=('webcollect-data-candidate-2',) if a.protocol=='entry' else None)
        if a.protocol=='entry':
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
    elif a.command=='retry': result=retry(pool,a.candidate_id,reason=a.reason)
    elif a.command=='claim': result=pool.claim_next(a.worker_id,a.request_id,
        protocols=('webcollect-data-candidate-2',) if getattr(a,'protocol',None)=='entry' else None)
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
        result=asyncio.run(run(pool,ledger,worker_id=a.worker_id,request_prefix=a.request_prefix,limit=a.limit,cohort=a.cohort,skip_wechat_articles=a.skip_wechat_articles,
            categories=a.category,application_id=a.application_id,poll_seconds=a.poll_seconds,producer_batch=a.producer_batch,target=a.target,target_basis=a.target_basis,recovery_version=a.recovery_version,output=a.output,registry=a.registry,policy=a.policy,history_set=a.history_set,qc_policy=a.qc_policy,
            protocols=('webcollect-data-candidate-2',) if getattr(a,'protocol',None)=='entry' else None))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': main()
