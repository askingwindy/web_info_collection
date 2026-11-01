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


def guard_request_scope(ledger, uri):
    """Quarantine unresolved requests by proved application; never replay them.

    Unscoped uncertainty and in-flight dispatch block all consumers. A request
    proved to belong to another application retains its original reservation.
    Provider authorization holds are still enforced by ModelGateway itself.
    """
    from .application_identity import canonical_key
    aliases = ledger.config.get('site_failure_guard', {}).get('application_registry')
    target = canonical_key(uri, aliases) if uri is not None else None
    isolated = []
    with ledger.connect() as con:
        from .provider_recovery import holds
        if holds(con):
            raise OutcomeUnknown('Original provider authorization hold; no dispatch')
        requests = con.execute("""SELECT m.id,m.state,m.error,j.payload FROM model_requests m
            LEFT JOIN jobs j ON j.id=m.job_id WHERE m.state IN ('reserved','unknown')""").fetchall()
        for row in requests:
            payload = json.loads(row['payload']) if row['payload'] else {}
            site = payload.get('site_uri')
            if (row['state'] == 'reserved' or not site
                    or str(row['error']).startswith(('HTTPError:401', 'HTTPError:403'))
                    or canonical_key(site, aliases) == target):
                raise OutcomeUnknown('Original model request unresolved for this scope; no dispatch: ' + row['id'])
            isolated.append({'kind':'model_request','id':row['id'],'site_uri':site,'state':row['state']})
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='top_level_visits'").fetchone():
            for row in con.execute("SELECT id,state,target_uri FROM top_level_visits WHERE state IN ('reserved_for_dispatch','unknown')"):
                if row['state']=='reserved_for_dispatch' or not row['target_uri'] or canonical_key(row['target_uri'],aliases)==target:
                    raise OutcomeUnknown('Original navigation unresolved for this scope; no dispatch: '+row['id'])
                isolated.append({'kind':'navigation','id':row['id'],'site_uri':row['target_uri'],'state':row['state']})
    return isolated


async def first_observation(ledger, claim, root):
    from playwright.async_api import async_playwright
    from .browser import capture
    from .navigation import BatchNavigation
    from .site_failure_stop import SiteFailureStore
    task={'site_uri':claim['snapshot']['entry_url']}
    guard=ledger.config.get('site_failure_guard')
    if guard: SiteFailureStore(guard).guard(task['site_uri'])
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
                from .preflight import _wait_visible_readiness
                exclusive(root/'first-readiness.json',await _wait_visible_readiness(page))
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
        found.append({'registry':claim['binding']['registry'],'attempt_id':row['attempt_id'],'task_key':row['task_key'],
            'sample_id':row['sample_id'],'save_receipt':receipt,'result_location':str(sample), 'scope_id':row['scope_id']})
    if len(found)>1: raise ValueError('More than one saved result for candidate claim; reconciliation required')
    return found[0] if found else None


def finish_or_reconcile(pool, claim, *, reconciliation=False):
    """Expired token never commits; explicit reconciler derives facts from original stores."""
    original=pool.get_claim(claim['claim_id'])
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
                con.execute("UPDATE data_candidates SET state='reconcile' WHERE candidate_id=?",(claim['candidate_id'],))
                pool.event(con,claim['candidate_id'],claim['claim_id'],'lease_expired',{})
            original=pool.get_claim(claim['claim_id'])
        return {'state':original['state'],'saved':False,'reason':'No committed complete save; inspect original model/visit/runtime ledgers; no resend'}
    with pool.transaction() as con:
        latest=con.execute('SELECT claim_id FROM candidate_claims WHERE candidate_id=? ORDER BY created DESC LIMIT 1',(claim['candidate_id'],)).fetchone()
        own_result=con.execute('SELECT effective FROM candidate_results WHERE candidate_id=? AND claim_id=?',
                               (claim['candidate_id'],claim['claim_id'])).fetchone()
        if latest[0]!=claim['claim_id'] or own_result and not own_result[0]:
            raise ValueError('Retired claim cannot replace an explicit retry')
        if not reconciliation and original['state']!='succeeded':
            pool._fence(con,claim)
        elif not reconciliation and original['expires'] <= time.time():
            raise ValueError('Expired token cannot commit; explicit receipt reconciliation required')
        elif original['state'] not in ('consuming','reconcile','succeeded','failed'):
            raise ValueError('Not reconcilable')
        previous=con.execute('SELECT record FROM candidate_results WHERE candidate_id=? AND effective=1',(claim['candidate_id'],)).fetchone()
        if previous and previous[0]!=canonical(result): raise ValueError('One effective result per candidate; old result retained')
        con.execute('INSERT OR IGNORE INTO candidate_results VALUES(?,?,?,?,?,NULL,1)',
            (claim['candidate_id'],claim['claim_id'],result['sample_id'],canonical(result),'pending_review'))
        con.execute("UPDATE candidate_claims SET state='succeeded',stage='saved',updated=? WHERE claim_id=?",(time.time(),claim['claim_id']))
        con.execute("UPDATE data_candidates SET state='succeeded' WHERE candidate_id=?",(claim['candidate_id'],))
        pool.event(con,claim['candidate_id'],claim['claim_id'],'saved_reconciled' if reconciliation else 'saved',result)
    from .site_pool_sync import sync_candidate_qc
    sync_candidate_qc(pool.path,result['registry'])
    with pool.pool.connect() as con:
        qc = con.execute('SELECT qc_state FROM candidate_results WHERE candidate_id=? AND claim_id=? AND effective=1',
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
    category = '综合'
    category_proven = False
    name = None
    for source in claim.get('sources') or []:
        hint = source.get('category_hint')
        if hint in CANONICAL_CATEGORIES and category == '综合':
            category = hint
            category_proven = True
        if name is None and source.get('application_hint'):
            name = source['application_hint']
    return {'category': category, 'name': name or host_identity(snapshot['entry_url']),
            'category_proven': category_proven}


def startup_check(ledger, *, output, registry, policy, history_set, qc_policy=None):
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
    if not any(Path(paths['output']).is_relative_to(p) for p in current_evidence_roots(scope)):
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
        attempts = con.execute('SELECT COUNT(*) FROM m4_attempts WHERE campaign_id=?', (supplied['campaign_id'],)).fetchone()[0]
        pending = con.execute("SELECT COUNT(*) FROM m4_tasks WHERE campaign_id=? AND status='collected_pending_review'", (supplied['campaign_id'],)).fetchone()[0]
        if attempts >= supplied['attempt_cap'] or pending >= supplied['pending_review_cap']:
            from .batch_core import BudgetStop
            raise BudgetStop('Original campaign attempt/pending limit reached before claim')
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
    if guard:
        SiteFailureStore(guard).guard(uri)
    guard_request_scope(ledger, uri)
    jid = ledger.enqueue('candidate-observation', {'claim_id': claim['claim_id'], 'site_uri': uri})
    previous = ledger.get(jid)
    if previous['state'] != 'queued' or previous['attempts']:
        raise OutcomeUnknown('Original entry observation already started; reconcile without dispatch')
    job = ledger.claim('candidate-observation', job_id=jid)
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
                    try:
                        await verify_execution_state(page, captured['state'])
                        break
                    except EvidenceStale as error:
                        exclusive(root/(prefix+'-stale.json'), {'reason':str(error), 'capture':getattr(error,'capture',None)})
                        if refresh == 2:
                            raise
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
                'error_type':type(error).__name__, 'reason':str(error), 'accepted_as_formal_frame':False})
            visits = [v for v in ledger.visits() if v['job_id']==jid]
            # Navigation already records its own failure or UNKNOWN in the ledger.
            # A local capture, identity or file error does not establish a site failure.
            if guard and access_rejection is not None and visits and visits[-1]['state']=='succeeded':
                SiteFailureStore(guard).record({'site_uri':uri}, execution_id('candidate-observation',ledger.path,jid),
                    stage='observation', state='failed', real_execution=True, reason=str(access_rejection), evidence=[failure],
                    usage_refs=[{'ledger':str(ledger.path),'job_id':jid,'visit_id':visits[-1]['id']}])
            ledger.finish(job, 'review_required', error=type(error).__name__)
        raise


async def consume(pool, claim, ledger, *, output, registry, policy, history_set, qc_policy=None):
    """Exactly one original claim, one goal and at most one saved result."""
    if claim.get('state')!='consuming': return {'state':claim.get('state'),'dispatched':False}
    current=pool.get_claim(claim['claim_id'])
    if current['token']!=claim['token'] or current['snapshot']!=claim['snapshot']:
        raise ValueError('Original candidate credential or target differs')
    if current['state']!='consuming': return {'state':current['state'],'dispatched':False}
    with pool.transaction() as con: pool._fence(con,claim)
    if current['stage']!='claimed': return finish_or_reconcile(pool,claim)
    paths = startup_check(ledger, output=output, registry=registry, policy=policy, history_set=history_set, qc_policy=qc_policy)
    output, registry, policy, history_set = (paths[k] for k in ('output','registry','policy','history_set'))
    supplied_policy = load_json(policy)
    isolated_unknown = guard_request_scope(ledger, claim['snapshot']['entry_url'])
    guard = ledger.config.get('site_failure_guard')
    if guard:
        from .site_failure_stop import SiteFailureStore
        SiteFailureStore(guard).guard(claim['snapshot']['entry_url'])
    root = Path(output)/claim['claim_id']
    # The transaction elects the sole executor before directories or external IO.
    won = pool.stage(claim, 'observation', {'registry':registry, 'ledger':str(ledger.path),
        'output':str(root), 'policy':policy, 'history_set':history_set,
        'isolated_unknown':isolated_unknown}, expected_stage='claimed')
    if not won:
        return finish_or_reconcile(pool, claim)
    root.mkdir(parents=True, exist_ok=False)
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
            hints = _entry_hints(claim)
            record = capability(claim, session['anchor'], claim_ref, ledger.config['mode'],
                category=hints['category'], name=hints['name'])
            pool.pool.record({'schema_version':'webcollect-site-discovery-1','origin':'codex_session',
                'run_id':ledger.config['run_id'],'event_id':'candidate-landing/'+claim['claim_id'],
                'uri':record['site_uri'],'name':hints['name'],
                'category_hint':hints['category'] if hints['category']!='综合' else 'UNKNOWN',
                'source_refs':[claim_ref,*session['anchor'].values()], 'stage':'consumer_observation'})
            catalog = root/'catalog.json'
            exclusive(catalog, {'schema_version':'webcollect-capability-catalog-1','mode':ledger.config['mode'],'records':[record]})
            from .single_record import identity
            identities = root/'identities.json'
            identity(catalog, identities, registry=registry, candidate_observation=True)
            pool.stage(claim, 'planning', {'catalog':str(catalog)})
            stage = 'planning'
            if not hints['category_proven']:
                reason = 'Entry category UNKNOWN; display fallback cannot consume a formal category quota'
                pool.finish(claim, state='failed', stage=stage, reason=reason)
                return {'state':'failed', 'stage':stage, 'reason':reason, 'formal_attempts':0}
            generated = await asyncio.to_thread(generate, ledger, catalog, root/'planning',
                generator='react-url', history_registry=registry, history_set=history_set,
                react_url=record['site_uri'], react_goal=snapshot['requested_goal'], page_identities=identities,
                react_site_category=hints['category'], react_app_name=hints['name'],
                react_candidate={'claim':claim,'claim_reference':claim_ref})
            catalog = root/'planning/catalog.json'
        else:
            anchor=await first_observation(ledger,claim,root)
            record=capability(claim,anchor,claim_ref,ledger.config['mode'])
            pool.pool.record({'schema_version':'webcollect-site-discovery-1','origin':'codex_session',
                'run_id':ledger.config['run_id'],'event_id':'candidate-landing/'+claim['claim_id'],
                'uri':record['site_uri'],'name':claim['snapshot']['name'],
                'category_hint':claim['snapshot']['parent_category'],
                'source_refs':[claim_ref,*anchor.values()], 'stage':'consumer_observation'})
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
            uncertain=any(r['status'] in ('reserved','running','interrupted') or r.get('failure_class') in ('unknown','interrupted') for r,t in _original_attempts(pool.get_claim(claim['claim_id'])))
            pool.finish(claim,state='reconcile' if uncertain else 'failed',stage='execution',reason=canonical(execution))
            result={'state':'reconcile' if uncertain else 'failed','execution':execution}
        return result
    async def work():
        async with AsyncExitStack() as stack:
            return await work_in(stack)
    keeper=asyncio.create_task(renew()); working=asyncio.create_task(work())
    try:
        done,_=await asyncio.wait((keeper,working),return_when=asyncio.FIRST_COMPLETED)
        if keeper in done: keeper.result(); raise ValueError('Candidate heartbeat stopped')
        return await working
    except BaseException as error:
        # Cross-process failure is conservative. Original requests/attempts are never reset.
        try:
            reconciled=finish_or_reconcile(pool,claim)
            if reconciled.get('saved') and not isinstance(error, asyncio.CancelledError): return reconciled
            state='reconcile' if stage=='execution' or isinstance(error,(OutcomeUnknown,asyncio.CancelledError)) else 'failed'
            pool.finish(claim,state=state,stage=stage,reason=type(error).__name__+': '+str(error))
        except Exception:
            pass  # A lost lease stays fenced; the explicit reconciler handles it.
        raise
    finally:
        for task in (keeper,working):
            if not task.done(): task.cancel()
        await asyncio.gather(keeper,working,return_exceptions=True)


async def run(pool, ledger, *, worker_id, request_prefix, limit=1, categories=None, application_id=None,
              protocols=None, poll_seconds=None, producer_batch=None, **kwargs):
    if type(limit)is not int or limit<1: raise ValueError('Explicit positive processing limit required')
    if poll_seconds is not None and (type(poll_seconds) is not int or poll_seconds < 1):
        raise ValueError('Polling interval must be a positive number of seconds')
    results=[]
    poll = 0
    while len(results) < limit:
        kwargs.update(startup_check(ledger, **kwargs))
        if poll_seconds is not None:
            ledger.remaining_seconds()
        if producer_batch:
            # Known application-local holds are checked again for the actual candidate.
            guard_request_scope(ledger, None)
        claim=pool.claim_next(worker_id,f'{request_prefix}/{poll}',categories=categories,application_id=application_id,
                              protocols=protocols, **({'producer_batch': producer_batch} if producer_batch else {}))
        poll += 1
        if claim['state']=='EMPTY':
            if producer_batch and pool.producer_batch_drained(producer_batch):
                break
            if poll_seconds is None:
                results.append(claim)
                break
            await asyncio.sleep(min(poll_seconds, ledger.remaining_seconds()))
            continue
        try:
            result=await consume(pool,claim,ledger,**kwargs)
        except BudgetStop:
            raise
        except Exception as error:
            if not producer_batch:
                raise
            from .site_failure_stop import SiteStopped
            current = pool.get_claim(claim['claim_id'])
            if current['state'] == 'consuming' and current['stage'] == 'claimed' and isinstance(error,(SiteStopped,OutcomeUnknown)):
                pool.finish(claim, state='reconcile', stage='claimed', reason=str(error))
                current = pool.get_claim(claim['claim_id'])
            if current['state'] not in ('failed','reconcile'):
                raise
            result = {'state':current['state'], 'stage':current['stage'], 'reason':current.get('reason') or str(error)}
        results.append({**result, 'claim_id':claim['claim_id'], 'candidate_id':claim['candidate_id']} if producer_batch else result)
        if result['state']=='reconcile' and not producer_batch: break
    return results


def retry(pool, candidate_id, *, reason):
    """Explicit retry only after reconciling original requests, visits and saves."""
    if not reason: raise ValueError('Explicit retry reason required')
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
    for row,task in _original_attempts(original):
        if row['status'] in ('reserved','running','interrupted') or row.get('failure_class') in ('unknown','interrupted'):
            raise ValueError('Original runtime attempt unresolved; no retry')
    if binding.get('ledger'):
        with closing(sqlite3.connect(Path(binding['ledger']).resolve().as_uri()+'?mode=ro',uri=True)) as con:
            config=json.loads(con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()[0])
            jobs=con.execute("SELECT state,payload FROM jobs WHERE state IN ('running','review_required') AND kind IN ('task-generation','fragment-decision','react-decision','react-native-decision')").fetchall()
        ledger=BatchLedger(binding['ledger'],config)
        guard_request_scope(ledger,original['snapshot']['entry_url'])
        from .application_identity import canonical_key
        aliases=config.get('site_failure_guard',{}).get('application_registry')
        target=canonical_key(original['snapshot']['entry_url'],aliases)
        for state,raw in jobs:
            site=json.loads(raw).get('site_uri')
            if state=='running' or not site or canonical_key(site,aliases)==target:
                raise ValueError('Original planning/decision unresolved for this scope; no retry')
        if config.get('site_failure_guard'):
            from .site_failure_stop import SiteFailureStore
            SiteFailureStore(config['site_failure_guard']).guard(original['snapshot']['entry_url'])
    with pool.transaction() as con:
        current=con.execute('SELECT state FROM data_candidates WHERE candidate_id=?',(candidate_id,)).fetchone()
        result=con.execute('SELECT qc_state FROM candidate_results WHERE candidate_id=? AND effective=1',(candidate_id,)).fetchone()
        if current['state']=='consuming': raise ValueError('Active holder cannot be retried')
        if current['state']=='succeeded' and (not result or result[0]!='failed'):
            raise ValueError('Saved pending/accepted candidate cannot be consumed again')
        if current['state'] not in ('failed','reconcile','succeeded'): raise ValueError('Candidate is not retryable')
        con.execute('UPDATE candidate_results SET effective=0 WHERE candidate_id=?',(candidate_id,))
        con.execute("UPDATE data_candidates SET state='pending' WHERE candidate_id=?",(candidate_id,))
        pool.event(con,candidate_id,original['claim_id'],'explicit_retry',{'reason':reason,'prior_state':current['state']})
    return {'candidate_id':candidate_id,'state':'pending'}


def statistics(pool):
    counts=pool.stats(); attempts={}; saved=set()
    with pool.pool.connect() as con:
        claims=[pool._claim(r) for r in con.execute('SELECT * FROM candidate_claims')]
    for claim in claims:
        for row,task in _original_attempts(claim):
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
    runp.add_argument('--limit',type=int,default=1); runp.add_argument('--category',action='append'); runp.add_argument('--application-id'); runp.add_argument('--qc-policy')
    runp.add_argument('--poll-seconds',type=int,help='Wait this many seconds between empty claims within the original runtime window; default exits on EMPTY')
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
    if a.command=='list': result={'records':pool.rows(protocols=('webcollect-data-candidate-2',)
        if a.protocol=='entry' else None),'statistics':statistics(pool)}
    elif a.command=='retry': result=retry(pool,a.candidate_id,reason=a.reason)
    elif a.command=='claim': result=pool.claim_next(a.worker_id,a.request_id,
        protocols=('webcollect-data-candidate-2',) if getattr(a,'protocol',None)=='entry' else None)
    elif a.command=='reconcile': result=finish_or_reconcile(pool,pool.get_claim(a.claim_id),reconciliation=True)
    else:
        ledger=BatchLedger(a.ledger,load_json(a.config))
        result=asyncio.run(run(pool,ledger,worker_id=a.worker_id,request_prefix=a.request_prefix,limit=a.limit,
            categories=a.category,application_id=a.application_id,poll_seconds=a.poll_seconds,producer_batch=a.producer_batch,output=a.output,registry=a.registry,policy=a.policy,history_set=a.history_set,qc_policy=a.qc_policy,
            protocols=('webcollect-data-candidate-2',) if getattr(a,'protocol',None)=='entry' else None))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': main()
