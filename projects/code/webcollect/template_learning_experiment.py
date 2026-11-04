"""Frozen bounded template-library consumer and asynchronous independent QC entry.

Uses the original project, claims, runtime store and model ledgers. Never recovers
foreign leases, replaces a candidate or resends an attempted QC job.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import sqlite3
import time
from .batch_core import BatchLedger, load_json, file_sha
from .agent_feedback import reference
from .planning import verify_evidence, object_sha256
from .template_learning import TemplateLibrary, enabled, qc_binding, VERSION, SESSION_WIRING


def write_new(path, value):
    with Path(path).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')


def db(path):
    c=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c


def request_costs(ledger_path, *, job_ids=None, attempt_id=None):
    requests=[]
    with db(ledger_path) as c:
        for raw in c.execute('SELECT id,job_id,state,usage,started,finished,request_json,response FROM model_requests ORDER BY started,id'):
            r=dict(raw);req=json.loads(r.pop('request_json') or '{}');response=json.loads(r.pop('response') or '{}')
            if job_ids is not None and r['job_id'] not in job_ids:continue
            if attempt_id is not None and req.get('dispatch_attempt_id')!=attempt_id:continue
            usage=json.loads(r['usage'] or '{}')
            provider=usage.get('source')=='provider_response' and bool(usage.get('provider_request_id')) and 'provider_response' in response
            r['http']=bool(req.get('http_dispatch')==1 or provider)
            r['http_evidence']='dispatch_marker' if req.get('http_dispatch')==1 else 'bound_provider_response' if provider else 'unconfirmed'
            requests.append(r)
    tally=Counter()
    for r in requests:
        for k,v in json.loads(r['usage'] or '{}').items():
            if k in ('input_tokens','output_tokens','cached_input_tokens','reasoning_tokens'):tally[k]+=v or 0
    return {'requests':requests,'http':sum(r['http'] for r in requests),'unknown':sum(r['state']=='unknown' for r in requests),
            'missing_usage':sum(r['http'] and not r['usage'] for r in requests),
            'unconfirmed_http':sum(not r['http'] for r in requests),'tokens':dict(tally)}


def audit(cohort_path, directory):
    from .candidate_consumer import verified_saved
    from site_planner.candidate_pool import CandidatePool
    cohort=load_json(cohort_path);scope=load_json(cohort['scope']['path']);pool=CandidatePool(scope['pool'],readonly=True)
    rows=[];timeline=[json.loads(l) for l in (directory/'timeline.jsonl').read_text().splitlines()] if (directory/'timeline.jsonl').exists() else []
    with db(scope['pool']) as pc,db(scope['registry']) as rc:
        for frozen in cohort['selected']:
            row={k:frozen[k] for k in ('order','candidate_id','version','entry_url','requested_goal','producer_batch')}
            claims=pc.execute('SELECT claim_id FROM candidate_claims WHERE candidate_id=?',(row['candidate_id'],)).fetchall()
            row.update(saved=False,formal_attempts=0,atomic_dispatches=0,effective_steps=0,route='NOT_EXECUTED',http=0,tokens={},unknown=0,missing_usage=0)
            if not claims:row['state']='UNCLAIMED';rows.append(row);continue
            if len(claims)!=1:raise ValueError('Unexpected candidate claim history')
            claim=pool.get_claim(claims[0][0]);row.update(claim_id=claim['claim_id'],state=claim['state'],stage=claim['stage'],reason=claim.get('reason'))
            binding=claim.get('binding') or {};aid=binding.get('attempt_id');root=Path(binding['output']) if binding.get('output') else None
            row['root']=str(root) if root else None
            if aid:
                attempt=rc.execute('SELECT * FROM m4_attempts WHERE attempt_id=?',(aid,)).fetchone()
                row.update(attempt_id=aid,sample_id=attempt['sample_id'],formal_attempts=1,runtime_status=attempt['status'],root_cause=attempt['root_cause'])
                row.update(request_costs(scope['consumer_db'],attempt_id=aid))
                raw=root/'execution/capture/evidence'/attempt['sample_id']/'raw';row['raw']=str(raw)
                if (raw/'terminal.json').exists():
                    terminal=load_json(raw/'terminal.json');row.update(atomic_dispatches=terminal.get('actual_actions',0),effective_steps=terminal.get('effective_steps',0),
                        working_goal=terminal.get('working_goal'),visible_terminal=terminal.get('stop_summary'),stop_reason=terminal.get('stop_reason'),raw_unknown=terminal.get('unknown'),
                        short_flow=terminal.get('short_flow'),collection_ending=terminal.get('collection_ending'))
                    for p in sorted(raw.glob('*-template-route-summary.json')):
                        route=load_json(p);row.update(route=route['route'],template_atomic=route['atomic_template_dispatches'],reactive_rounds=route['reactive_rounds'])
                    row['static_matches']=[load_json(p)['static_matches'] for p in raw.glob('*-template-library-lookup.json')]
                    row['fallbacks']=[load_json(p)['reason'] for p in raw.glob('*-template-fallback.json')]
                    row['verifier_events']=[reference(p) for p in raw.glob('*-template-verifier.json')]
                saved=verified_saved(claim)
                if saved:row.update(saved=True,save_receipt=saved['save_receipt'],result_location=saved['result_location'],customer_package=str(root/'execution/candidate'),qc_handoff=str(root/'execution/qc-inputs/receipt.json'))
            for e in timeline:
                if e.get('phase')=='candidate_finished' and e.get('candidate_id')==row['candidate_id']:
                    row.update(natural_seconds=e['natural_seconds'],started=e['started'],finished=e['finished'])
            rows.append(row)
    summary={k:sum(r[k] for r in rows) for k in ('saved','formal_attempts','atomic_dispatches','effective_steps','http','unknown','missing_usage')}
    summary.update(denominator=len(rows),states=dict(Counter(r['state'] for r in rows)),routes=dict(Counter(r['route'] for r in rows)))
    return {'summary':summary,'rows':rows}


async def capture(cohort_path, directory, worker):
    from . import candidate_consumer
    from site_planner.candidate_pool import CandidatePool
    cohort=load_json(cohort_path);rows=cohort['selected']
    if cohort.get('learning_version')!=VERSION or not 1<=len(rows)<=3 or cohort['denominator']!=len(rows):raise ValueError('Bounded frozen learning cohort required')
    if cohort.get('session_wiring')!=SESSION_WIRING:raise ValueError('Explicit frozen original four-tool ReAct wiring required')
    for key in ('scope','manifest','source_freeze','offline','initial_library','before'):verify_evidence([cohort[key]])
    if load_json(cohort['offline']['path'])['status']!='PASS':raise ValueError('Offline verification failed')
    frozen=load_json(cohort['source_freeze']['path']);checkout=Path(cohort['checkout'])
    for path,sha in frozen.items():
        if file_sha(checkout/path)!=sha:raise ValueError('Frozen checkout changed: '+path)
    scope=load_json(cohort['scope']['path']);pool=CandidatePool(scope['pool']);ledger=BatchLedger(scope['consumer_db'],load_json(scope['consumer_config']))
    library=TemplateLibrary(cohort['library'],scope['history_set'],scope['pool'])
    if library.snapshot()!=load_json(cohort['initial_library']['path']):raise ValueError('Initial library changed before dispatch')
    target=Path(scope['output'])/worker
    if target.exists() or (directory/'capture-started.json').exists():raise ValueError('Existing run must be inspected, never replayed')
    def event(phase,**data):
        r={'phase':phase,'at':datetime.now(timezone.utc).isoformat(),**data}
        with (directory/'timeline.jsonl').open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
        print(json.dumps(r,ensure_ascii=False),flush=True)
    async def wait_slot(claim=None):
        logged=False
        while True:
            with ledger.connect() as c:busy=[dict(r) for r in c.execute("SELECT id,kind FROM jobs WHERE state='running' AND kind!='frozen-plan'")]
            if not busy:return
            if not logged:event('waiting_original_shared_slot',jobs=busy);logged=True
            if claim:pool.heartbeat(claim)
            await asyncio.sleep(5)
    await wait_slot()
    write_new(directory/'capture-started.json',{'worker':worker,'started':time.time(),'cohort':reference(cohort_path)})
    original=candidate_consumer.consume
    async def consume(*args,**kwargs):
        claim=args[1];await wait_slot(claim);started=time.time()
        event('candidate_started',candidate_id=claim['candidate_id'],claim_id=claim['claim_id'])
        try:
            # Each candidate snapshots the current persisted library, so a later
            # explicit version never changes the hit-time evidence of an earlier one.
            with enabled(library):result=await original(*args,**kwargs)
            event('candidate_finished',candidate_id=claim['candidate_id'],started=started,finished=time.time(),natural_seconds=time.time()-started,result=result)
            saved=candidate_consumer.verified_saved(pool.get_claim(claim['claim_id']))
            if saved:
                t=time.time()
                try:
                    learned=library.learn(pool,claim['claim_id'])
                    event('success_trace_learned',sample_id=saved['sample_id'],template_id=learned['template_id'],seconds=time.time()-t,http=0,tokens=0)
                except (ValueError,KeyError) as exc:event('success_trace_not_applicable',sample_id=saved['sample_id'],reason=str(exc),seconds=time.time()-t,http=0)
            write_new(directory/(claim['candidate_id']+'-readback.json'),audit(cohort_path,directory))
            return result
        except BaseException as exc:
            event('candidate_exception',candidate_id=claim['candidate_id'],type=type(exc).__name__,reason=str(exc));raise
    candidate_consumer.consume=consume
    try:
        result=await candidate_consumer.run(pool,ledger,worker_id=worker,request_prefix=worker,cohort=cohort_path,
            output=target,registry=scope['registry'],policy=scope['policy'],history_set=scope['history_set'],qc_policy=scope['qc_policy'])
        write_new(directory/'official-run-result.json',result);write_new(directory/'capture-readback.json',audit(cohort_path,directory))
    finally:candidate_consumer.consume=original


class SelectedJobs:
    def __init__(self,ledger,ids):self.ledger=ledger;self.ids=ids;self.attempted=set()
    def __getattr__(self,k):return getattr(self.ledger,k)
    def claim(self,kind):
        for jid in self.ids.get(kind,[]):
            if jid in self.attempted:continue
            self.attempted.add(jid);job=self.ledger.get(jid)
            if job['state']=='queued' and not job['attempts']:return self.ledger.claim(kind,job_id=jid)
        return None


def independent_qc(cohort_path,directory):
    from quality_inspector import ai_worker
    from quality_inspector.profiles import package_files
    from quality_inspector.cumulative import build_set_manifest
    cohort=load_json(cohort_path);scope=load_json(cohort['scope']['path']);before=load_json(cohort['before']['path'])
    if not (directory/'official-run-result.json').exists():raise ValueError('Capture must have original terminal receipt')
    verify_evidence([before[k] for k in ('qc_config','profile')])
    ledger=BatchLedger(before['qc_ledger'],load_json(before['qc_config']['path']))
    library=TemplateLibrary(cohort['library'],scope['history_set'],scope['pool'])
    D=directory/'independent-qc';D.mkdir(exist_ok=True)
    if (D/'completion.json').exists():raise ValueError('QC complete; inspect original evidence')
    saved=[r for r in audit(cohort_path,directory)['rows'] if r['saved']];paths=set();members=[]
    for row in saved:
        handoff=load_json(row['qc_handoff']);package=Path(row['customer_package'])
        if handoff['dataset']!=str(package) or handoff['candidate_files_sha256']!=package_files(package):raise ValueError('QC handoff bytes differ')
        if not any(a['sample_id']==row['sample_id'] and a['attempt_id']==row['attempt_id'] for a in handoff['attempts']):raise ValueError('QC attempt binding differs')
        paths.update(p['path'] for p in handoff['request']['effective_set']['packages']);paths.add(str(package))
        checks={'path':str(Path(row['qc_handoff']).parent/'collection-checks.json'),'sha256':handoff['bound_checks_sha256']};verify_evidence([checks]);members.append((row,checks))
    comparison=D/'comparison-original-packages.json'
    if members and not comparison.exists():write_new(comparison,build_set_manifest(sorted(paths)))
    entries=[];started=time.time()
    for row,checks in members:
        sid=row['sample_id'];loc=D/sid;loc.mkdir(exist_ok=True);pointer=loc/'queue-reference.json';t=time.time()
        if not pointer.exists():
            prepared=ai_worker.prepare(ledger,row['customer_package'],loc/'prepared',effective_set=comparison,sample_ids=[sid],collection_checks=checks)
            write_new(pointer,reference(prepared['queue_file']))
        ref=load_json(pointer);verify_evidence([ref]);queue=load_json(ref['path'])
        ids={'ai-visual':[j['visual_job'] for j in queue['jobs']],'ai-difference':[j['difference_job'] for j in queue['jobs']]}
        all_ids=[j for values in ids.values() for j in values]
        while True:
            with ledger.connect() as c:busy=c.execute("SELECT count(*) FROM jobs WHERE state='running'").fetchone()[0]
            if not busy:break
            time.sleep(5)
        print('QC_START',sid,flush=True)
        if not (loc/'worker.json').exists():
            result=ai_worker.run(SelectedJobs(ledger,ids));write_new(loc/'worker.json',{'outcomes':result['outcomes'],'stopped':result['stopped']})
        if not (loc/'summary.json').exists():write_new(loc/'summary.json',ai_worker.report(ledger,ref['path'],loc/'report',profile=before['profile']['path']))
        summary=load_json(loc/'summary.json');report=next((loc/'report').glob('qc-*/report.json'))
        bound=qc_binding(report,summary['review_file'],ref['path'],ledger)[sid]
        costs=request_costs(ledger.path,job_ids=all_ids)
        entry={**bound,**costs,'natural_seconds':time.time()-t,'save_receipt':row['save_receipt'],'original_handoff':row['qc_handoff']}
        try:library.apply_qc(row['save_receipt']['sha256'],bound);entry['library_qc_applied']=True
        except ValueError as exc:entry.update(library_qc_applied=False,library_reason=str(exc))
        if not (loc/'final.json').exists():write_new(loc/'final.json',entry)
        entries.append(entry);print('QC_END',sid,bound['status'],'five_pass',bound['all_five_pass'],flush=True)
    write_new(D/'completion.json',{'saved':len(saved),'entries':entries,'natural_seconds':time.time()-started,
        'http':sum(e['http'] for e in entries),'unknown':sum(e['unknown'] for e in entries),
        'actual_full_frame_reviewed':sum(e['full_frames'] for e in entries),'all_five_pass':sum(e['all_five_pass'] for e in entries),
        'human_review':'NOT_RUN','formal_batch_admission':'NOT_RUN','published':0,'customer_acceptance':'NOT_RUN'})
    write_new(directory/'final-library.json',library.snapshot())


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('capture','independent-qc','audit'))
    p.add_argument('--cohort',type=Path,required=True);p.add_argument('--directory',type=Path,required=True);p.add_argument('--worker')
    a=p.parse_args(argv);directory=a.directory.resolve();cohort=a.cohort.resolve()
    with (directory/(a.action+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.action=='capture':
            if not a.worker:p.error('--worker required for capture')
            asyncio.run(capture(cohort,directory,a.worker))
        elif a.action=='independent-qc':independent_qc(cohort,directory)
        else:print(json.dumps(audit(cohort,directory),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
