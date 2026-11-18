"""Read-only fixed-cohort funnel. Missing evidence stays unknown, never invented zero."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
from webcollect import workspace_json as json
from pathlib import Path

from .batch_core import load_json, save_json
from .planning import verify_evidence
from .sqlite_connection import connect

STAGES=('claimed','first_frame','template_selected','model_http','initial_plan_accepted',
        'effective_steps_ge5','goal_verified','formally_saved')


def rows(path, table):
    with closing(connect(path, readonly=True)) as con:
        con.row_factory=__import__('sqlite3').Row
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
            return None
        return [dict(r) for r in con.execute('SELECT * FROM '+table)]


def jsonl(root, name):
    result=[]
    for path in sorted(Path(root).rglob(name)):
        for n,line in enumerate(path.read_text().splitlines(),1):
            if line.strip():
                from .workspace_paths import bind
                bind(path)
                try:result.append({**json.loads(line),'_evidence':{'path':str(path),'line':n}})
                except ValueError:result.append({'event':'unreadable_event','_evidence':{'path':str(path),'line':n}})
    return result


def request_summary(requests):
    states=Counter();dispatch=Counter();known_in=known_out=missing=0
    for r in requests:
        states[r['state']]+=1
        request=json.loads(r.get('request_json') or '{}');response=json.loads(r.get('response') or '{}')
        sent=request.get('http_dispatch')
        # Reserved intentions do not prove an HTTP dispatch. Transport facts take priority.
        timing=response.get('http_timing') or response.get('timing') or response.get('transport_timing') or {}
        actual=timing.get('http_dispatched',response.get('http_dispatched'))
        if timing.get('headers_ms') is not None or (response.get('provider_error') or {}).get('http_status') is not None:
            actual=True
        if actual is False:kind='not_dispatched'
        elif actual is True or request.get('provider') not in (None,'synthetic') and r['state'] in ('succeeded','invalid_response') or sent is True and r['state'] in ('succeeded','invalid_response','available','insufficient_balance','rate_limited','model_limited'):kind='dispatched'
        elif sent is False:kind='not_dispatched'
        else:kind='unproven'
        dispatch[kind]+=1
        usage=json.loads(r.get('usage') or r.get('usage_json') or 'null')
        inp=usage.get('prompt_tokens',usage.get('input_tokens')) if isinstance(usage,dict) else None
        out=usage.get('completion_tokens',usage.get('output_tokens')) if isinstance(usage,dict) else None
        if inp is None or out is None:missing+=1
        known_in+=inp or 0;known_out+=out or 0
    return {'requests':len(requests),'states':dict(states),'dispatch':dict(dispatch),
            'input_tokens':known_in if not missing else None,'output_tokens':known_out if not missing else None,
            'known_input_tokens':known_in,'known_output_tokens':known_out,'unknown_usage_requests':missing,'cost':'UNKNOWN'}


def belongs_to_batches(payload,batches):
    """Only native scope fields; no time, filename or URI-based attribution."""
    if isinstance(payload,dict):
        for key,value in payload.items():
            if key in ('scope','batch_scope','run_id','batch') and isinstance(value,str):
                if any(value==batch or value.startswith(batch+'/') for batch in batches):return True
            if isinstance(value,(dict,list)) and belongs_to_batches(value,batches):return True
    elif isinstance(payload,list):
        return any(belongs_to_batches(value,batches) for value in payload)
    return False


def producer_requests(scope,batches):
    all_requests=rows(scope['producer_db'],'model_requests') or []
    batch_rows=rows(scope['pool'],'candidate_batch_rows') or []
    # Native row request_id can be the model job ID; retain both exact forms.
    identities={r['request_id'] for r in batch_rows if r['run_id'] in batches}
    jobs={r['id']:json.loads(r['payload']) for r in rows(scope['producer_db'],'jobs') or []}
    chosen=[r for r in all_requests if r['id'] in identities or r['job_id'] in identities
            or belongs_to_batches(jobs.get(r['job_id'],{}),batches)]
    return chosen,len(all_requests)-len(chosen)


def producer_round(plan):
    from .site_inventory import load_scope
    _,scope=load_scope(plan['scope']);config=load_json(scope['producer_config'])
    batches={config['run_id']+'/entry-batch/'+w['batch_key'] for w in plan['workers']}
    candidates=rows(scope['pool'],'data_candidates') or []
    owners={r['candidate_id']:r['application_id'] for r in candidates}
    published=rows(scope['pool'],'candidate_batch_rows') or []
    selected=[r for r in published if r['run_id'] in batches]
    sites=[]
    for site in plan['sites']:
        aid=site['application_id'];ids={r['candidate_id'] for r in selected if r['result']=='NEW' and owners.get(r['candidate_id'])==aid}
        sites.append({'application_id':aid,'startup_cumulative_new':site.get('startup_cumulative_new'),
                      'round_net_new':len(ids),'round_target':site['remaining'],
                      'shortfall':max(0,site['remaining']-len(ids))})
    requests,unattributed=producer_requests(scope,batches)
    fault_path=Path(plan['log_root'])/'failure-events.jsonl'
    faults=[json.loads(line) for line in fault_path.read_text().splitlines() if line.strip()] if fault_path.is_file() else []
    busy=sum(r.get('operation')=='begin_immediate' and r.get('disposition')=='transient' for r in faults)
    return {'plan_id':plan['plan_id'],'round_batches':sorted(batches),'sites':sites,'producer_model':request_summary(requests),
            'unattributed_requests_outside_round':unattributed,'natural_busy_locked_events':busy,'faults':faults,'dispatch_or_request_replay':False,
            'units':{'pages':'distinct NEW candidate identity','requests':'physical request records'},'real_baseline_acceptance':'NOT_EVALUATED'}


def build(scope_path, cohort_path, run_root, *, running=False):
    from .site_inventory import load_scope
    _,scope=load_scope(scope_path);cohort=load_json(cohort_path);selected=cohort['selected']
    identities={(r['candidate_id'],r['version']) for r in selected}
    issues=[]
    site_counts=Counter(r['application_id'] for r in selected)
    if cohort.get('site_denominators') and dict(site_counts)!=cohort['site_denominators']:
        issues.append('fixed_site_denominators_changed')
    if len(identities)!=len(selected) or cohort.get('denominator')!=len(selected):issues.append('invalid_cohort_denominator_or_duplicates')
    all_claims=rows(scope['pool'],'candidate_claims') or []
    tasks=rows(scope['registry'],'m4_tasks') or [];attempts=rows(scope['registry'],'m4_attempts') or []
    consumer_jobs=rows(scope['consumer_db'],'jobs') or []
    consumer_requests=rows(scope['consumer_db'],'model_requests') or []
    result_rows=rows(scope['pool'],'candidate_results') or []
    events=jsonl(run_root,'runtime.jsonl');model_logs=jsonl(run_root,'model-calls.jsonl')
    claims_by=defaultdict(list)
    for r in all_claims:
        if (r['candidate_id'],r['version']) in identities:claims_by[(r['candidate_id'],r['version'])].append(r)
    task_by_claim=defaultdict(list)
    for t in tasks:
        task=json.loads(t['task_json']);binding=task.get('candidate_binding') or {}
        if binding.get('claim_id'):task_by_claim[binding['claim_id']].append((t,task))
    job_claim={}
    for j in consumer_jobs:
        payload=json.loads(j['payload']);cb=payload.get('candidate_binding') or {}
        cid=payload.get('claim_id') or cb.get('claim_id')
        if cid:job_claim[j['id']]=cid
    # Exact native parent edges only. Never correlate by close timestamps or filenames.
    parents=rows(scope['consumer_db'],'job_parents') or []
    changed=True
    while changed:
        changed=False
        for j in consumer_jobs:
            parent=json.loads(j['payload']).get('parent_job_id')
            if parent in job_claim and j['id'] not in job_claim:job_claim[j['id']]=job_claim[parent];changed=True
        for edge in parents:
            if edge['parent_id'] in job_claim and edge['job_id'] not in job_claim:
                job_claim[edge['job_id']]=job_claim[edge['parent_id']];changed=True
    detail=[];used_requests={};faults=[]
    for selected_row in selected:
        key=(selected_row['candidate_id'],selected_row['version']);claims=claims_by[key]
        facts={stage:{'state':'unknown','evidence':[]} for stage in STAGES}
        item={'candidate_id':key[0],'version':key[1],'application_id':selected_row['application_id'],
              'template':'unselected','template_source':None,'stages':facts,'inconsistencies':[],
              'claim_elapsed_seconds':None,'session_elapsed_seconds':None,'effective_steps':None,'first_request_plan_accepted':None,'closure_proven':False}
        facts['claimed']={'state':'reached' if claims else 'not_reached','evidence':[{'table':'candidate_claims','claim_id':c['claim_id']} for c in claims]}
        if len(claims)>1:item['inconsistencies'].append('multiple_claims_for_frozen_candidate')
        claim_ids={c['claim_id'] for c in claims}
        own=[e for e in events if e.get('claimId') in claim_ids]
        for e in own:
            event=e.get('event')
            if event=='first_frame_completed':
                try:verify_evidence(list(e['anchor'].values()));facts['first_frame']={'state':'reached','evidence':[e['_evidence']]}
                except (ValueError,OSError,KeyError):item['inconsistencies'].append('first_frame_bytes_missing_or_changed')
            if event=='template_selected':
                item['template']=e.get('template_name') or e.get('templateName') or 'unselected'
                item['template_source']=e.get('source')
                facts['template_selected']={'state':'reached','evidence':[e['_evidence']]}
            if event=='first_plan_result':
                accepted=e.get('accepted')
                if accepted is True:item['plan_accept_log']=e['_evidence']
                elif accepted is False and facts['initial_plan_accepted']['state']!='reached':facts['initial_plan_accepted']={'state':'failed','code':e.get('reason') or e.get('code') or 'plan_rejected','evidence':[e['_evidence']]}
            if event=='session_finished':item['session_elapsed_seconds']=e.get('elapsedSeconds')
        for j in consumer_jobs:
            if j['kind']!='candidate-observation' or job_claim.get(j['id']) not in claim_ids:continue
            result=json.loads(j.get('result') or '{}')
            if result.get('first_frame_completed') is False and result.get('failure'):
                try:
                    ref=result['failure'];verify_evidence([ref]);failure=load_json(ref['path'])
                    if failure.get('job_id')!=j['id'] or failure.get('accepted_as_formal_frame') is not False:raise ValueError('entry failure identity mismatch')
                    item['closure_proven']=True
                    facts['first_frame']={'state':'failed','code':failure.get('error_type') or 'ENTRY_FAILED','evidence':[ref]}
                    for later in ('template_selected','initial_plan_accepted','effective_steps_ge5','goal_verified','formally_saved'):
                        if facts[later]['state']=='unknown':facts[later]['state']='not_reached'
                except (ValueError,OSError,KeyError) as error:item['inconsistencies'].append('entry_failure_unreadable:'+str(error))
        selected_tasks=[pair for cid in claim_ids for pair in task_by_claim[cid]]
        task_keys={t['task_key'] for t,task in selected_tasks}
        own_attempts=[a for a in attempts if a['task_key'] in task_keys]
        attempt_ids={a['attempt_id'] for a in own_attempts}
        own_requests=[r for r in consumer_requests if job_claim.get(r['job_id']) in claim_ids
                      or json.loads(r.get('request_json') or '{}').get('dispatch_attempt_id') in attempt_ids]
        for r in own_requests:used_requests[r['id']]=r
        if request_summary(own_requests)['dispatch'].get('dispatched',0):facts['model_http']={'state':'reached','evidence':[{'request_id':r['id']} for r in own_requests]}
        elif claims and request_summary(own_requests)['dispatch'].get('unproven',0)==0:facts['model_http']={'state':'not_reached','evidence':[{'request_id':r['id']} for r in own_requests]}
        for a in own_attempts:
            try:
                refs=json.loads(a['evidence_json']);raw_refs=[r for r in refs if Path(r.get('path','')).name=='raw-receipt.json']
                for ref in raw_refs:
                    verify_evidence([ref]);receipt=load_json(ref['path']);verify_evidence([receipt['terminal']]);terminal=load_json(receipt['terminal']['path'])
                    task_of_attempt = next((task for t, task in selected_tasks
                                            if t['task_key'] == a['task_key']), None)
                    if ((terminal.get('strategy') or {}).get('id') == 'stepwise'
                            or ((task_of_attempt or {}).get('fragment') or {}).get(
                                'collection_strategy', {}).get('id') == 'stepwise'):
                        # 策略 3：按本策略终态读取（模板匹配、整份计划等策略 2
                        # 专属阶段记不适用，不伪造达成）。
                        item['template'] = 'stepwise'
                        item['template_source'] = 'not_applicable'
                        if a['status'] == 'collected_pending_review' and a.get('finished_at') is not None:
                            item['closure_proven'] = True
                        count = terminal.get('effective_steps'); item['effective_steps'] = count
                        if count is not None:
                            facts['effective_steps_ge5'] = {'state': 'reached' if count >= 5 else 'failed',
                                'code': 'effective_steps_below_5' if count < 5 else None, 'evidence': [ref]}
                        for stage in ('template_selected', 'initial_plan_accepted'):
                            if facts[stage]['state'] == 'unknown':
                                facts[stage] = {'state': 'not_applicable', 'evidence': [],
                                                'strategy': 'stepwise'}
                        goal = (terminal.get('goal_evidence') or {}).get('business_goal_status')
                        if goal == 'VERIFIED':
                            facts['goal_verified'] = {'state': 'reached', 'evidence': [receipt['terminal']]}
                        elif goal:
                            facts['goal_verified'] = {'state': 'failed', 'code': goal,
                                                      'evidence': [receipt['terminal']]}
                        continue
                    # The accepted initial plan must exist in the same hash-verified seal.
                    raw_root=Path(ref['path']).parent
                    from .postprocess import session_record
                    from .screenshot_planners import template_module, task_template_name
                    record=session_record(raw_root,allow_unknown_for_prefix=True)
                    binding=record['task'].get('candidate_binding') or {}
                    if binding.get('candidate_id')!=key[0] or binding.get('version')!=key[1] or binding.get('claim_id') not in claim_ids:
                        raise ValueError('Raw terminal/task identity differs from frozen cohort')
                    accepted=[]
                    for name in receipt['files_sha256']:
                        if name.endswith('-screenshot-plan.json'):
                            event=load_json(raw_root/name)
                            if event.get('kind')=='screenshot-plan' and event.get('phase')=='first':accepted.append({'path':str(raw_root/name),'sha256':receipt['files_sha256'][name]})
                    if accepted:
                        facts['initial_plan_accepted']={'state':'reached','evidence':accepted}
                        accepted_id=load_json(accepted[0]['path']).get('request_id')
                        actual_requests=[r for r in own_requests if request_summary([r])['dispatch'].get('dispatched')]
                        if accepted_id and actual_requests:
                            first=min(actual_requests,key=lambda r:(r['started'],r['id']))
                            item['first_request_plan_accepted']=accepted_id==first['id']
                    elif facts['initial_plan_accepted']['state']=='reached':facts['initial_plan_accepted']={'state':'unknown','evidence':[]}

                    if a['status']=='collected_pending_review' and a.get('finished_at') is not None:item['closure_proven']=True
                    count=terminal.get('effective_steps');item['effective_steps']=count
                    if count is not None:facts['effective_steps_ge5']={'state':'reached' if count>=5 else 'failed','code':'effective_steps_below_5' if count<5 else None,'evidence':[ref]}
                    goal=(terminal.get('goal_evidence') or {}).get('business_goal_status')
                    if goal=='VERIFIED':
                        marker=template_module(task_template_name(record['task'])).validate_ending_marker(record)
                        if marker.get('goal_completion')=='VERIFIED':facts['goal_verified']={'state':'reached','evidence':[receipt['terminal']]}
                        else:item['inconsistencies'].append('goal_terminal_missing_normal_completion')
                    elif goal:facts['goal_verified']={'state':'failed','code':goal,'evidence':[receipt['terminal']]}
                for ref in refs:
                    if Path(ref.get('path','')).name=='failure.json':
                        verify_evidence([ref]);failure=load_json(ref['path'])
                        if (raw_refs and a['status']=='rejected' and a.get('finished_at') is not None
                                and failure.get('attempt_id')==a['attempt_id'] and failure.get('failure_class')==a.get('failure_class')
                                and (failure.get('root_cause') or failure.get('error'))==a.get('root_cause')):item['closure_proven']=True
                        faults.append({'claim_id':next(iter(claim_ids),None),'attempt_id':a['attempt_id'],
                            'failure_class':a.get('failure_class'),'reason':a.get('root_cause'),
                            **(failure.get('failure_disposition') or {'disposition':'unclassified'})})
                if a['status'] in ('reserved','running') or not a.get('finished_at'):item['inconsistencies'].append('unsettled_attempt')
            except (ValueError,OSError,KeyError) as error:item['inconsistencies'].append('attempt_evidence_unreadable:'+str(error))
        for c in claims:
            if c['state'] in ('failed','reconcile') and not own_attempts:
                abandoned=next((e for e in own if e.get('event')=='abandoned'),None)
                faults.append({'claim_id':c['claim_id'],'failure_class':None,'reason':c.get('reason'),
                               'disposition':'business' if abandoned else 'unclassified',
                               'reason_owner':'business' if abandoned else 'unknown',
                               'code':abandoned.get('reason') if abandoned else None,'retry_count':0})
            if c['state'] not in ('consuming','reconcile') and c.get('updated') is not None:item['claim_elapsed_seconds']=max(0,c['updated']-c['created'])
            try:
                from .candidate_consumer import verified_saved
                hydrated={**c,'binding':json.loads(c.get('binding') or '{}'),'snapshot':json.loads(c['snapshot'])}
                saved=verified_saved(hydrated)
                if saved:
                    if any(r['claim_id']==c['claim_id'] and r['candidate_id']==key[0] and r.get('effective')==1
                           and r.get('sample_id')==saved['sample_id'] and json.loads(r['record']).get('attempt_id')==saved['attempt_id'] for r in result_rows):
                        facts['formally_saved']={'state':'reached','evidence':[saved['save_receipt']]};item['sample_id']=saved['sample_id']
                    else:item['inconsistencies'].append('runtime_saved_missing_candidate_writeback')
                elif c['state']=='succeeded':item['inconsistencies'].append('saved_state_without_verified_receipt')
            except (ValueError,OSError,KeyError) as error:item['inconsistencies'].append('save_evidence_unreadable:'+str(error))
        if not claims:
            for stage in STAGES[1:]:facts[stage]['state']='not_reached'
        # Later facts cannot repair missing predecessor evidence. 策略 2 专属阶段
        # 对策略 3 记 not_applicable，按透明阶段处理（既非达成也非缺失）。
        prefix=True
        for stage in STAGES:
            state=facts[stage]['state']
            if state=='not_applicable':
                facts[stage]['prefix_reached']=prefix
                continue
            if state=='reached' and not prefix:item['inconsistencies'].append('later_fact_without_prefix:'+stage)
            prefix=prefix and state=='reached';facts[stage]['prefix_reached']=prefix
        item['task_terminal_proven']=bool(claims) and item['closure_proven'] and all(
            c['state'] in ('failed','succeeded','observed','reconcile') for c in claims)
        item['requests']=request_summary(own_requests)
        detail.append(item)
    def aggregate(chosen):
        return {stage:{'independent':sum(i['stages'][stage]['state']=='reached' for i in chosen),
                       'prefix':sum(i['stages'][stage]['prefix_reached'] for i in chosen),
                       'states':dict(Counter(i['stages'][stage]['state'] for i in chosen)),
                       'top5_rejections':[{'code':code,'unique_candidates':len({i['candidate_id'] for i in chosen if i['stages'][stage].get('code')==code}),
                                           'events':count} for code,count in Counter(i['stages'][stage].get('code') for i in chosen if i['stages'][stage]['state']=='failed').most_common(5)]}
                for stage in STAGES}
    all_producers=rows(scope['producer_db'],'model_requests') or []
    batches={r.get('producer_batch') for r in selected if r.get('producer_batch')}
    if cohort.get('audit'):
        verify_evidence([cohort['audit']])
        batches.update(load_json(cohort['audit']['path']).get('round_batches',[]))
    producers,producer_unattributed=producer_requests(scope,batches)
    probe_ids=set()
    plan_path=Path(run_root)/'plan.json'
    central=Path(run_root)/'startup-probes.json'
    if central.is_file():probe_ids.add(load_json(central)['launch_id'])
    if plan_path.is_file():
        plan=load_json(plan_path)
        for worker in plan.get('workers',[]):
            command=worker.get('command',[])
            if '--request-prefix' in command:probe_ids.add('candidate-run:'+command[command.index('--request-prefix')+1])
    probe_rows=rows(scope['consumer_db'],'consumer_key_probes')
    probes=[p for p in probe_rows or [] if p.get('launch_id') in probe_ids]
    probe_requests=[{**p,'id':p['probe_id'],'usage':p.get('usage_json'),
                     'request_json':json.dumps({'http_dispatch':True})} for p in probes]
    visits=[v for v in rows(scope['consumer_db'],'top_level_visits') or [] if job_claim.get(v['job_id']) in {c['claim_id'] for group in claims_by.values() for c in group}]
    tool_requests=[r for r in rows(scope['pool'],'tool_requests') or [] if r.get('run_id') in batches]
    cache_hits=[e for e in model_logs if e.get('claimId') in {c['claim_id'] for group in claims_by.values() for c in group} and (e.get('cacheHit') is True or e.get('event')=='cache_hit')]
    round_seconds=None
    summary_path=Path(run_root)/'summary.json'
    if summary_path.is_file():round_seconds=load_json(summary_path).get('elapsed_seconds')
    event_path=Path(run_root)/'failure-events.jsonl'
    round_faults=[]
    if event_path.is_file():
        round_faults=[json.loads(line) for line in event_path.read_text().splitlines() if line.strip()]
    seen={(r.get('claim_id'),r.get('error_feature'),r.get('disposition')) for r in round_faults}
    faults=round_faults+[r for r in faults if (r.get('claim_id'),r.get('error_feature'),r.get('disposition')) not in seen]
    saved=sum(i['stages']['formally_saved']['state']=='reached' for i in detail)
    totals=request_summary(list(used_requests.values())+producers+probe_requests)
    if len([i for i in detail if i['stages']['claimed']['state']=='reached'])!=100:issues.append('fixed_100_claims_incomplete')
    if len(selected)!=100:issues.append('fixed_denominator_is_not_100')
    if any(i['inconsistencies'] for i in detail):issues.append('candidate_evidence_inconsistencies')
    if any(not i['task_terminal_proven'] for i in detail if i['stages']['claimed']['state']=='reached'):issues.append('unsettled_claims')
    return {'denominator':len(selected),'expected_denominator':100,'site_denominators':dict(site_counts),'expected_site_denominators':cohort.get('site_denominators',dict(site_counts)),
            'template_denominators':dict(Counter(i['template'] for i in detail)),'stage_order':list(STAGES),'running_snapshot':running,
            'integrity':'FAILED' if issues else 'PASS','issues':issues,'funnel':aggregate(detail),
            'by_site':{site:aggregate([i for i in detail if i['application_id']==site]) for site in sorted({i['application_id'] for i in detail})},
            'by_template':{t:aggregate([i for i in detail if i['template']==t]) for t in sorted({i['template'] for i in detail})},
            'faults':faults,'fault_categories':dict(Counter(r.get('disposition','unclassified') for r in faults)),
            'reason_owners':dict(Counter(r.get('reason_owner','unknown') for r in faults)),
            'units':{'funnel':'unique frozen candidate','requests':'unique physical request id','tokens':'provider tokens','elapsed':'seconds'},
            'usage':{'producer':request_summary(producers),'consumer':request_summary(list(used_requests.values())),
                     'startup_probes':request_summary(probe_requests),'total':totals},
            'unattributed_requests':{'consumer':len(consumer_requests)-len(used_requests),'startup_probes_scope_unknown':probe_rows is None or not bool(probe_ids),'producer':producer_unattributed},
            'saved':saved,'mean_saved_input_tokens':sum(i['requests']['known_input_tokens'] for i in detail if i['stages']['formally_saved']['state']=='reached')/saved if saved and all(i['requests']['unknown_usage_requests']==0 for i in detail if i['stages']['formally_saved']['state']=='reached') else None,
            'amortized_input_tokens':totals['input_tokens']/saved if saved and totals['input_tokens'] is not None else None,
            'mean_saved_session_seconds':sum(i['session_elapsed_seconds'] for i in detail if i['stages']['formally_saved']['state']=='reached')/saved if saved and all(i['session_elapsed_seconds'] is not None for i in detail if i['stages']['formally_saved']['state']=='reached') else None,
            'mean_saved_output_tokens':sum(i['requests']['known_output_tokens'] for i in detail if i['stages']['formally_saved']['state']=='reached')/saved if saved and all(i['requests']['unknown_usage_requests']==0 for i in detail if i['stages']['formally_saved']['state']=='reached') else None,
            'amortized_output_tokens':totals['output_tokens']/saved if saved and totals['output_tokens'] is not None else None,
            'amortized_session_seconds':sum(i['session_elapsed_seconds'] for i in detail if i['session_elapsed_seconds'] is not None)/saved if saved and all(i['session_elapsed_seconds'] is not None for i in detail if i['stages']['claimed']['state']=='reached') else None,
            'round_elapsed_seconds':round_seconds,'cache_hits':len(cache_hits),
            'web_visits':{'count':len(visits),'states':dict(Counter(v['state'] for v in visits))},
            'tool_requests':{'count':len(tool_requests),'states':dict(Counter(r['state'] for r in tool_requests))},'candidates':detail,'qc':'NOT_RUN','human_review':'NOT_RUN','published':False,'acceptance':'UNKNOWN'}


def markdown(report):
    lines=[f"# Collection funnel\n\nDenominator: {report['denominator']}; integrity: {report['integrity']}; saved: {report['saved']}.",
           '| Stage | Independent | Prefix | States |','|---|---:|---:|---|']
    lines += [f"| {stage} | {r['independent']} | {r['prefix']} | {json.dumps(r['states'],ensure_ascii=False)} |" for stage,r in report['funnel'].items()]
    lines += ['\nUsage and per-candidate evidence are in funnel.json.', '\nIssues: '+json.dumps(report['issues'],ensure_ascii=False),
              '\nSaved mean input tokens: '+str(report['mean_saved_input_tokens'])+'; amortized input tokens: '+str(report['amortized_input_tokens'])]
    lines += ['\n## Complete machine facts\n','```json',json.dumps(report,ensure_ascii=False,indent=2),'```']
    return '\n'.join(lines)+'\n'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('scope','cohort','run-root','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--running',action='store_true');a=p.parse_args(argv)
    report=build(a.scope,a.cohort,a.run_root,running=a.running);a.output.mkdir(parents=True,exist_ok=True)
    from .workspace_paths import prepare_output
    prepare_output(a.output,a.scope)
    save_json(a.output/'funnel.json',report);(a.output/'funnel.md').write_text(markdown(report))
    return 0 if report['integrity']=='PASS' else 2

if __name__=='__main__':raise SystemExit(main())
