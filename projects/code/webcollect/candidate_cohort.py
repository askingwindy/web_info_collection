"""Read-only Table2 dispatch audit and reproducible frozen worker cohorts.

This entry never claims, recovers, visits, or calls a provider. Output is a new
directory; a fixed list is never topped up when one of its members is rejected.
"""
from webcollect.sqlite_connection import raw_connect as workspace_connect
import argparse
from collections import Counter
import hashlib
from webcollect import workspace_json as json
from pathlib import Path
import sqlite3

from .batch_core import BatchLedger, ClosingConnection, OutcomeUnknown, load_json, save_json
from .candidate_consumer import guard_candidate_dispatch
from .planning import object_sha256, verify_evidence
from .agent_feedback import reference

VERSION = 'candidate-dispatch-selection'


class ReadOnlyLedger(BatchLedger):
    def connect(self, create=False):
        if create:
            raise ValueError('Selection cannot create a ledger')
        con = workspace_connect(self.path.as_uri()+'?mode=ro', uri=True,
                              timeout=90, factory=ClosingConnection)
        con.row_factory = sqlite3.Row
        return con


def verify_get(pool, ledger, uri, ref):
    """Verify a receipt against its original settled job and unique GET visit."""
    from site_planner.entry_access import POLICY, wire_uri
    from site_planner import producer_observation
    verify_evidence([ref]);access=load_json(ref['path'])
    if access.get('policy') == producer_observation.RECEIPT_POLICY:
        # Current producers reuse one shared anonymous observation visit; the
        # observation module owns that lineage's job/visit/document binding.
        try:
            document,_result=producer_observation.from_pool(pool,ledger,uri)
        except OutcomeUnknown as error:
            raise ValueError('GET_original_job_or_visit_missing') from error
        if (document is None or document.get('job_id') != access.get('job_id')
                or document.get('visit_id') != access.get('visit_id')
                or document.get('landed_uri') != access.get('landed_uri')
                or document.get('http_status') != access.get('http_status')):
            raise ValueError('GET_receipt_identity_or_status_mismatch')
        verify_evidence([access['source_observation'],access['source_document']])
        return access
    if (access.get('policy') != POLICY or access.get('result') != 'PASS' or access.get('method') != 'GET'
            or type(access.get('http_status')) is not int or not 200 <= access['http_status'] < 300
            or wire_uri(access.get('entry_uri','')) != wire_uri(uri)):
        raise ValueError('GET_receipt_identity_or_status_mismatch')
    with ledger.connect() as con:
        job=con.execute('SELECT kind,state,result,payload FROM jobs WHERE id=?',(access.get('job_id'),)).fetchone()
        visits=con.execute('SELECT * FROM top_level_visits WHERE job_id=?',(access.get('job_id'),)).fetchall()
    if (not job or job['kind']!='candidate-entry-http' or job['state']!='done'
            or json.loads(job['result'] or 'null') != ref or len(visits)!=1):
        raise ValueError('GET_original_job_or_visit_missing')
    visit=visits[0];payload=json.loads(job['payload'])
    if (visit['id']!=access.get('visit_id') or visit['state']!='succeeded'
            or visit['response_status']!=access['http_status'] or visit['finished_at'] is None
            or wire_uri(visit['target_uri'])!=wire_uri(uri)
            or wire_uri(payload['uri'])!=wire_uri(uri) or payload.get('policy')!=POLICY
            or visit['landed_uri']!=access.get('landed_uri')):
        raise ValueError('GET_original_dispatch_or_landing_mismatch')
    return access


def inspect_rows(scope_path, *, candidate_ids=None):
    """Layered denominators include rejections, not just the final eligible pool."""
    from site_planner.candidate_pool import CandidatePool, candidate_dedup_key, validate_candidate_v2
    scope_path = Path(scope_path).resolve(); scope = load_json(scope_path)
    pool = CandidatePool(scope['pool'], readonly=True)
    ledger = ReadOnlyLedger(scope['consumer_db'], load_json(scope['consumer_config']))
    producer = ReadOnlyLedger(scope['producer_db'], load_json(scope['producer_config']))
    requested = set(candidate_ids) if candidate_ids is not None else None
    parameters = sorted(requested) if requested is not None else []
    predicate = 'candidate_id IN ('+','.join('?' for _ in parameters)+')' if parameters else ('0' if requested is not None else '1')
    rows = []; counts = Counter({key:0 for key in ('table2','published_NEW','pending_without_disposition',
        'never_claimed','row_sources_GET_verified','dispatch_guard_pass')}); reasons = Counter()
    # Materialize quickly and close the read transaction before guard/file reads.
    with pool.pool.connect() as con:
        inventory = [dict(r) for r in con.execute('SELECT * FROM data_candidates WHERE '+predicate+' ORDER BY created,candidate_id',parameters)]
        claims = {r[0] for r in con.execute('SELECT DISTINCT candidate_id FROM candidate_claims WHERE '+predicate,parameters)}
        published = {}
        for r in con.execute("SELECT * FROM candidate_batch_rows WHERE result='NEW' AND "+predicate+" ORDER BY created,row_id",parameters):
            published.setdefault(r['candidate_id'], dict(r))
        versions = {(r['candidate_id'],r['version']):r['body'] for r in con.execute('SELECT * FROM candidate_versions WHERE '+predicate,parameters)}
        sources = {}
        for r in con.execute('SELECT * FROM candidate_sources WHERE '+predicate+' ORDER BY created,source_key',parameters):
            sources.setdefault(r['candidate_id'], []).append(json.loads(r['source']))
        dispositions = {}
        for r in con.execute("SELECT candidate_id,record FROM candidate_events WHERE kind='disposition' AND "+predicate+" ORDER BY id",parameters):
            dispositions[r['candidate_id']] = json.loads(r['record'])
    for row in inventory:
        cid = row['candidate_id']
        if requested is not None and cid not in requested:
            continue
        counts['table2'] += 1
        result = {'candidate_id':cid, 'state':row['state'], 'eligible':False}
        try:
            pub = published.get(cid)
            if not pub: raise ValueError('not_published_NEW')
            counts['published_NEW'] += 1
            if row['state'] != 'pending': raise ValueError('state_'+row['state'])
            if cid in dispositions: raise ValueError('disposition_hold')
            counts['pending_without_disposition'] += 1
            if cid in claims: raise ValueError('historical_claim')
            counts['never_claimed'] += 1
            body = json.loads(row['body']); validate_candidate_v2(body)
            if (versions.get((cid,row['version'])) != row['body']
                    or candidate_dedup_key(body,row['application_id']) != row['dedup_key']
                    or json.loads(pub['record']).get('candidate_id') != cid):
                raise ValueError('row_version_or_identity_mismatch')
            srcs = sources.get(cid, [])
            if not srcs: raise ValueError('missing_sources')
            receipts = []
            for src in srcs:
                verify_evidence(src['references'])  # same frozen sources checked by claim_next
                ref = src.get('entry_http')
                if ref:
                    verify_get(pool,producer,body['entry_url'],ref)
                    receipts.append(ref)
            if not receipts: raise ValueError('missing_bound_GET_2xx')
            counts['row_sources_GET_verified'] += 1
            isolated = guard_candidate_dispatch(ledger, body['entry_url'], candidate_id=cid)
            counts['dispatch_guard_pass'] += 1
            result.update(eligible=True, version=row['version'], application_id=row['application_id'],
                requested_goal_source='producer_table2' if body['requested_goal'] is not None else 'entry_unspecified',sources=srcs,
                body_sha256=hashlib.sha256(row['body'].encode()).hexdigest(), body=body,
                entry_url=body['entry_url'], requested_goal=body['requested_goal'],
                producer_batch=pub['run_id'], producer_row_id=pub['row_id'],
                producer_row_response_sha256=pub['response_sha256'], entry_http=receipts[0],
                sources_sha256=object_sha256(srcs), isolated_unknowns=isolated,
                category=next((s.get('category_hint') for s in srcs if s.get('category_hint')), 'UNKNOWN'))
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, RuntimeError) as error:
            result['rejection'] = {'type':type(error).__name__, 'reason':str(error)}
            reasons[str(error)] += 1
        rows.append(result)
    if requested is not None:
        for cid in sorted(requested-{r['candidate_id'] for r in rows}):
            rows.append({'candidate_id':cid,'eligible':False,'rejection':{'type':'ValueError','reason':'candidate_missing'}})
            reasons['candidate_missing'] += 1
    return scope, rows, {'layers':dict(counts), 'rejections':dict(reasons),
                        'scope':reference(scope_path), 'manifest':reference(scope['history_set']),
                        'consumer_config':reference(scope['consumer_config']),
                        'dispatch_check':'guard_candidate_dispatch(uri, candidate_id=original_candidate_id)',
                        'writes_to_original_stores':False, 'dispatches':0}


def freeze(scope_path, output, *, count=50, seed='round2', candidate_ids=None, dry_run=False):
    if type(count) is not int or count < 1: raise ValueError('Positive sample count required')
    if candidate_ids is not None and (not isinstance(candidate_ids,list) or not candidate_ids
            or any(not isinstance(cid,str) or not cid for cid in candidate_ids)
            or len(set(candidate_ids)) != len(candidate_ids)):
        raise ValueError('Fixed list must be nonempty with distinct candidate IDs')
    output = Path(output).resolve()
    scope, rows, audit = inspect_rows(scope_path, candidate_ids=candidate_ids)
    eligible = [r for r in rows if r['eligible']]
    if candidate_ids is not None:
        byid = {r['candidate_id']:r for r in eligible}
        selected = [byid[c] for c in candidate_ids if c in byid]
        expected = len(candidate_ids)
    else:
        # Stable category/application rotation. No Python hash/random seed drift.
        selected = []; cats = Counter(); apps = Counter()
        while eligible and len(selected) < count:
            row = min(eligible, key=lambda r:(cats[r['category']],apps[r['application_id']],
                object_sha256([seed,r['candidate_id']])))
            selected.append(row); eligible.remove(row)
            cats[row['category']] += 1; apps[row['application_id']] += 1
        expected = count
    audit.update(schema_version=VERSION, selection_seed=seed, requested_count=expected,
                 eligible_count=sum(r['eligible'] for r in rows), selected_count=len(selected),
                 selection_complete=len(selected)==expected, dry_run=dry_run)
    output.mkdir(parents=True, exist_ok=False)
    save_json(output/'audit.json',audit); save_json(output/'rows.json',rows)
    if not dry_run and audit['selection_complete']:
        cohort = {'schema_version':'consumer-multibatch-cohort',
            'selection_protocol':VERSION, 'selection_seed':seed, 'scope':audit['scope'],
            'manifest':audit['manifest'], 'pool':scope['pool'], 'registry':scope['registry'],
            'consumer_ledger':scope['consumer_db'], 'denominator':len(selected),
            'selected':[{**r,'order':n} for n,r in enumerate(selected,1)],
            'audit':reference(output/'audit.json'), 'replacement_allowed':False}
        save_json(output/'cohort.json',cohort)
    return {'output':str(output), **audit,
            'cohort':str(output/'cohort.json') if (output/'cohort.json').exists() else None}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scope',required=True); p.add_argument('--output',required=True)
    p.add_argument('--count',type=int,default=50); p.add_argument('--seed',default='round2')
    p.add_argument('--candidate-list',type=Path,help='JSON list of original IDs, exact order, no replacement')
    p.add_argument('--dry-run',action='store_true',help='Write audit/list only, never a dispatchable cohort')
    a=p.parse_args(argv)
    result=freeze(a.scope,a.output,count=a.count,seed=a.seed,
                  candidate_ids=load_json(a.candidate_list) if a.candidate_list else None,dry_run=a.dry_run)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()


def freeze_round(scope_path, producer_plan, output):
    """Earliest 50 usable NEW pages/site from this round's native producer batches."""
    from site_planner.candidate_pool import CandidatePool
    scope=load_json(scope_path);plan=load_json(producer_plan)
    if plan.get('role')!='producer' or len(plan.get('sites',[]))!=2:
        raise ValueError('A two-site producer round plan is required')
    exit_receipt=load_json(Path(plan['log_root'])/'summary.json')
    if exit_receipt.get('plan_id')!=plan['plan_id'] or exit_receipt.get('succeeded') is not True or any(w.get('returncode')!=0 for w in exit_receipt.get('workers',[])):
        raise ValueError('Producer round has not drained successfully')
    production=load_json(Path(plan['log_root'])/'producer-summary.json')
    if production.get('plan_id')!=plan['plan_id'] or production.get('natural_busy_locked_events')!=0 or any(s.get('shortfall')!=0 for s in production['sites']):
        raise ValueError('Producer net-new target incomplete; cannot freeze baseline')
    config=load_json(scope['producer_config'])
    batches={config['run_id']+'/entry-batch/'+w['batch_key'] for w in plan['workers']}
    pool=CandidatePool(scope['pool'],readonly=True)
    with pool.pool.connect() as con:
        published=[dict(r) for r in con.execute("SELECT b.*,c.application_id FROM candidate_batch_rows b JOIN data_candidates c USING(candidate_id) WHERE b.result='NEW' ORDER BY b.created,c.candidate_id") if r['run_id'] in batches]
    by_id={}
    for row in published:by_id.setdefault(row['candidate_id'],row)
    _,audited,audit=inspect_rows(scope_path,candidate_ids=list(by_id))
    eligible={r['candidate_id']:r for r in audited if r['eligible']}
    selected=[];counts=Counter()
    for cid,pub in by_id.items():
        if cid in eligible and counts[pub['application_id']]<50:
            row=eligible[cid]
            if row['producer_batch'] not in batches:raise ValueError('NEW provenance belongs to another producer round')
            selected.append(row);counts[pub['application_id']]+=1
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    complete=len(counts)==2 and set(counts.values())=={50}
    save_json(output/'audit.json',{**audit,'producer_plan':reference(producer_plan),'round_batches':sorted(batches),
                                  'counts':dict(counts),'selection_complete':complete,'requested_denominator':100})
    save_json(output/'rows.json',audited)
    if not complete:return {'ready':False,'counts':dict(counts),'cohort':None}
    cohort={'schema_version':'consumer-multibatch-cohort','selection_protocol':VERSION,
            'selection_order':'published_at,candidate_id','scope':reference(scope_path),'manifest':reference(scope['history_set']),
            'pool':scope['pool'],'registry':scope['registry'],'consumer_ledger':scope['consumer_db'],
            'denominator':100,'site_denominators':dict(counts),'selected':[{**r,'order':n} for n,r in enumerate(selected,1)],
            'audit':reference(output/'audit.json'),'replacement_allowed':False}
    save_json(output/'cohort.json',cohort)
    return {'ready':True,'counts':dict(counts),'cohort':str(output/'cohort.json')}
