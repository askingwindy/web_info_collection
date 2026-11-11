"""Read-only candidate details and role-separated GLM accounting for one local project."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import time

from .batch_core import load_json, save_json
from .candidate_monitor import rows
from .current_chain import check_project_guard, check_project_pool, read_chain_scope


def metering(requests):
    """Cached inputs and reasoning are already included in the provider's input/output."""
    known_in = known_out = known_cache = known_reasoning = 0
    cache_unknown = reasoning_unknown = 0
    missing = []
    for request in requests:
        if request['usage']:
            usage = json.loads(request['usage'])
            known_in += usage['input_tokens']
            known_out += usage['output_tokens']
            cached=usage.get('cached_input_tokens');reasoning=usage.get('reasoning_tokens')
            if type(cached) is int and cached >= 0:known_cache += cached
            else:cache_unknown += 1
            if type(reasoning) is int and reasoning >= 0:known_reasoning += reasoning
            else:reasoning_unknown += 1
        else:
            missing.append({k:request[k] for k in ('id','job_id','state','error','started')})
    return {'requests':len(requests),'settled_requests':len(requests)-len(missing),
            'known_input_tokens':known_in,'known_output_tokens':known_out,'known_total_tokens':known_in+known_out,
            'known_cached_input_tokens':known_cache,'known_reasoning_tokens':known_reasoning,
            'cached_usage_unknown_requests':cache_unknown+len(missing),
            'reasoning_usage_unknown_requests':reasoning_unknown+len(missing),
            'usage_coverage':(len(requests)-len(missing))/len(requests) if requests else None,
            'input_tokens':None if missing else known_in,'output_tokens':None if missing else known_out,
            'total_tokens':None if missing else known_in+known_out,'unsettled':missing}


def discovery_shares(requests, publications):
    by_job = defaultdict(list)
    for r in requests:
        by_job[r['job_id']].append(r)
    groups = defaultdict(list)
    for row in publications:
        if row['candidate_id'] not in groups[row['request_id']]:
            groups[row['request_id']].append(row['candidate_id'])
    shares = {}
    for job, ids in groups.items():
        receipts = by_job.get(job,[])
        actual = metering(receipts)
        count = len(ids)
        for index,cid in enumerate(ids):
            # Model usage is observed per request. Apportion exactly once over the NEW rows.
            share = {}
            for field in ('input_tokens','output_tokens'):
                total = actual[field]
                share[field] = None if total is None or not receipts else total//count + int(index < total%count)
            caller = job.startswith(('caller-goals/','caller-entries/'))
            if caller:
                share = {'input_tokens':0,'output_tokens':0}
            share['total_tokens'] = None if share['input_tokens'] is None else share['input_tokens'] + share['output_tokens']
            known={field:0 if caller else actual['known_'+field]//count + int(index<actual['known_'+field]%count)
                   for field in ('input_tokens','output_tokens')}
            known['total_tokens']=known['input_tokens']+known['output_tokens']
            item = {'basis':'caller_entry' if job.startswith('caller-entries/') else 'caller_goal' if caller else 'equal_share_of_new_candidates' if receipts else 'missing_request',
                'job_id':None if caller else job,'request_ids':[r['id'] for r in receipts],
                'shared_request_usage':actual if receipts else None,'new_candidates_sharing_request':count,
                'allocated':share,'known_allocated':known}
            if cid in shares:
                previous=shares[cid]
                item['components']=previous.get('components',[previous])+[{**item}]
                item['request_ids']=previous['request_ids']+item['request_ids']
                item['allocated']={k:previous['allocated'][k]+share[k]
                                   if previous['allocated'][k] is not None and share[k] is not None else None
                                   for k in ('input_tokens','output_tokens','total_tokens')}
                item['known_allocated']={k:previous['known_allocated'][k]+known[k]
                                         for k in ('input_tokens','output_tokens','total_tokens')}
            shares[cid]=item
    return shares, {r['id'] for job in groups for r in by_job[job]}


def build_report(scope, *, batches=(), since=None, until=None):
    from site_planner.site_pool import SitePool
    if since is not None and until is not None and since > until:
        raise ValueError('Invalid accounting window')
    chain = read_chain_scope(Path(scope['history_set']).absolute())
    if not check_project_pool(chain, SitePool(scope['pool'],readonly=True)) or chain['registry'] != scope['registry']:
        raise ValueError('Original candidate project pool and registry required')
    at = time.time() if until is None else until
    role_requests = {}
    totals = {}
    for role in ('producer','consumer'):
        db = scope[role+'_db']
        config = load_json(scope[role+'_config'])
        check_project_guard(chain,config['site_failure_guard'],db,role=role)
        requests = rows(db,"SELECT id,job_id,state,usage,error,started,json_extract(request_json,'$.dispatch_attempt_id') AS attempt_id "
                            "FROM model_requests WHERE started<=? ORDER BY started,id",(at,))
        role_requests[role] = requests
        totals[role] = {'project':metering(requests),'window':metering([r for r in requests if since is None or r['started']>=since])}
    pool = scope['pool']
    pubs = rows(pool,"SELECT candidate_id,run_id,request_id FROM candidate_batch_rows WHERE result='NEW' AND created<=? "
                     "ORDER BY run_id,batch,raw_index,row_id",(at,))
    shares, attributed = discovery_shares(role_requests['producer'],pubs)
    tables={r['name'] for r in rows(pool,"SELECT name FROM sqlite_master WHERE type='table'")}
    mining_publications=[]; site_decisions={}
    if 'application_mining_requests' in tables:
        from .planning import verify_evidence
        for item in rows(pool,'SELECT m.job_id,m.reference,i.conclusion FROM application_mining_requests m '
                              'JOIN application_scope_items i USING(scope_id) WHERE i.conclusion IS NOT NULL ORDER BY i.rowid'):
            verify_evidence([json.loads(item['reference'])])
            conclusion=json.loads(item['conclusion'])
            # Selection calls already allocated over NEW rows must not be charged twice.
            if conclusion.get('result')=='NEW' and item['job_id'] not in {r['request_id'] for r in pubs}:
                mining_publications.append({'request_id':item['job_id'],'candidate_id':conclusion['candidate_id']})
        for item in rows(pool,'SELECT d.application_id,d.decision_id,d.homepage,d.language,d.classification_state,d.mining_state,d.scope_id,a.category '
                              'FROM application_discovery d JOIN applications a ON a.id=d.application_id'):
            site_decisions[item['application_id']]=item
    mining_shares, mining_attributed=discovery_shares(role_requests['producer'],mining_publications)
    attributed.update(mining_attributed)
    batch_of = {r['candidate_id']:r['run_id'] for r in pubs}
    claims = defaultdict(list)
    for r in rows(pool,'SELECT claim_id,candidate_id,worker_id,state,stage,reason,binding FROM candidate_claims ORDER BY created,claim_id'):
        r['binding'] = json.loads(r['binding'] or '{}')
        claims[r['candidate_id']].append(r)
    attempts = defaultdict(list)
    for r in rows(scope['registry'],"SELECT json_extract(t.task_json,'$.candidate_binding.claim_id') AS claim_id,"
                  "a.attempt_id,a.sample_id,a.status,a.failure_class,a.root_cause FROM m4_attempts a JOIN m4_tasks t USING(task_key) "
                  "WHERE json_extract(t.task_json,'$.candidate_binding.claim_id') IS NOT NULL ORDER BY a.created_at"):
        attempts[r['claim_id']].append(r)
    results = defaultdict(list)
    for r in rows(pool,'SELECT candidate_id,claim_id,sample_id,record,qc_state,qc_report,effective FROM candidate_results'):
        r['record'] = json.loads(r['record'])
        r['qc_report'] = json.loads(r['qc_report']) if r['qc_report'] else None
        results[r['candidate_id']].append(r)
    sources = defaultdict(list)
    for r in rows(pool,'SELECT candidate_id,source FROM candidate_sources ORDER BY created,source_key'):
        sources[r['candidate_id']].append(json.loads(r['source']))
    consumer_by_attempt = defaultdict(list)
    consumer_by_job = defaultdict(list)
    for r in role_requests['consumer']:
        if r['attempt_id']:
            consumer_by_attempt[r['attempt_id']].append(r)
        consumer_by_job[r['job_id']].append(r)
    records = []
    attributed_consumer = set()
    selected_consumer = set()
    selected_discovery = set()
    for r in rows(pool,'SELECT candidate_id,application_id,version,state,body,created FROM data_candidates WHERE created<=? ORDER BY created,candidate_id',(at,)):
        cid = r['candidate_id']
        batch = batch_of.get(cid)
        associated = {}
        history = []
        for claim in claims[cid]:
            binding = claim['binding']
            formal = attempts[claim['claim_id']]
            ids = {a['attempt_id'] for a in formal}
            if binding.get('attempt_id'):
                ids.add(binding['attempt_id'])
            for aid in ids:
                associated.update((a['id'],a) for a in consumer_by_attempt[aid])
            for jid in binding.get('planning_jobs',[]):
                associated.update((a['id'],a) for a in consumer_by_job[jid])
            history.append({**{k:claim[k] for k in ('claim_id','worker_id','state','stage','reason')},'attempts':formal})
        attributed_consumer.update(associated)
        if batches and batch not in batches:
            continue
        selected_consumer.update(associated)
        selected_discovery.update(shares.get(cid,{}).get('request_ids',[]))
        selected_discovery.update(mining_shares.get(cid,{}).get('request_ids',[]))
        r['candidate'] = json.loads(r.pop('body'))
        discovery=shares.get(cid,{'basis':'missing_publication','allocated':None})
        if cid in mining_shares:
            discovery={**discovery,'site_mining':mining_shares[cid]}
            a,b=discovery.get('allocated'),mining_shares[cid]['allocated']
            discovery['allocated']=({k:a[k]+b[k] if a[k] is not None and b[k] is not None else None
                                     for k in ('input_tokens','output_tokens','total_tokens')} if a else b)
            discovery['known_allocated']={k:discovery.get('known_allocated',{}).get(k,0)+mining_shares[cid]['known_allocated'][k]
                                          for k in ('input_tokens','output_tokens','total_tokens')}
        r.update(batch=batch,sources=sources[cid],site_discovery=site_decisions.get(r['application_id']),discovery_tokens=discovery,
                 consumer_result={'state':r['state'] if history else 'unclaimed','claims':history,'saved_results':results[cid],
                                  'request_ids':list(associated),'glm':metering(list(associated.values()))})
        records.append(r)
    for role,selected in (('producer',selected_discovery),('consumer',selected_consumer)):
        window=[r for r in role_requests[role] if since is None or r['started']>=since]
        totals[role]['linked_to_selected_candidates_in_window']=metering([r for r in window if r['id'] in selected])
        totals[role]['other_window_requests']=metering([r for r in window if r['id'] not in selected])
    allocations=[r['discovery_tokens'].get('known_allocated') for r in records]
    allocation_totals={field:sum(a[field] for a in allocations if a and a.get(field) is not None)
                       for field in ('input_tokens','output_tokens','total_tokens')}
    all_known=[shares.get(cid,{}).get('known_allocated',{}) for cid in shares]
    all_known += [s.get('known_allocated',{}) for s in mining_shares.values()]
    unallocated=metering([r for r in role_requests['producer'] if r['id'] not in attributed])
    balance={field:{'allocated':sum(s.get(field,0) for s in all_known),
                    'unallocated':unallocated['known_'+field],
                    'role_total':totals['producer']['project']['known_'+field]}
             for field in ('input_tokens','output_tokens','total_tokens')}
    for values in balance.values():values['balanced']=values['allocated']+values['unallocated']==values['role_total']
    search_tools=rows(pool,"SELECT state,COUNT(*) AS count FROM tool_requests WHERE kind='search' GROUP BY state")
    return {'schema_version':'candidate-role-accounting','project':chain['chain_id'],'batch_filter':list(batches),
            'selected_candidate_known_allocations':allocation_totals,
            'project_producer_allocation_balance':balance,
            'search_tools_without_token_usage':{'states':search_tools,'token_usage':'UNKNOWN; not included in GLM totals'},
            'since':since,'until':at,'roles':totals,'net_new':sum(r['candidate_id'] in batch_of for r in records),
            'unallocated_project_discovery':unallocated,
            'unlinked_project_consumer':metering([r for r in role_requests['consumer'] if r['id'] not in attributed_consumer]),
            'allocation':'Vendor usage is measured per model request. Input and output are divided separately over its NEW rows, in original row order. A request without a NEW row stays unallocated. Consumer results reflect the read time.',
            'candidates':records}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--batch',action='append',default=[])
    parser.add_argument('--since',type=float)
    parser.add_argument('--until',type=float)
    args=parser.parse_args()
    report=build_report(load_json(args.scope),batches=args.batch,since=args.since,until=args.until)
    save_json(args.output,report)
    print(json.dumps({'net_new':report['net_new'],'roles':report['roles'],'output':str(args.output.absolute())},ensure_ascii=False))


if __name__=='__main__':
    main()
