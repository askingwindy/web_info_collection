"""Compact, shareable page funnel and failure evidence for the selected cohort."""
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from webcollect.planning import verify_evidence

from run import ARCHIVE, RUN, ROOT


def read(path):
    return json.loads(path.read_text())


def query(path, sql, args=()):
    with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro', uri=True)) as con:
        con.row_factory=sqlite3.Row
        return [dict(row) for row in con.execute(sql, args)]


def main():
    scope=read(ROOT/'database/sqllite/prod/scope.json')
    sites={row['candidate_id']:row['host'].removeprefix('www.') for row in read(ARCHIVE/'selection.json')['pages']}
    segments=sorted(RUN.glob('run-[0-9][0-9]'))
    funnel=read(segments[-1]/'funnel.json')
    plan_for_worker={}
    for segment in segments:
        plan=read(segment/'prepared-plan.json')
        plan_for_worker.update({worker['worker_id']:plan['plan_id'] for worker in plan['workers']})
    peak=max(read(ARCHIVE/(segment.name+'-final.json'))['worker_peak_observed'] for segment in segments)
    placeholders=','.join('?' for _ in sites)
    claims=query(scope['pool'], f"""SELECT candidate_id,claim_id,worker_id,state,reason FROM candidate_claims
        WHERE candidate_id IN ({placeholders})""", list(sites))
    by_claim={c['claim_id']:c for c in claims}
    attempts=query(scope['registry'], """SELECT a.attempt_id,a.sample_id,a.status,a.root_cause,
        json_extract(t.task_json,'$.candidate_binding.claim_id') AS claim_id FROM m4_attempts a
        JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.created_at>=?""",
        (min(read(seg/'summary.json')['started_at'] for seg in segments),))
    by_candidate={row['candidate_id']:row for row in funnel['candidates']}
    codes=defaultdict(Counter)
    judgement=Counter()
    rejections=Counter()
    gaps=defaultdict(Counter)
    saved=[]
    sampled=set()
    for attempt in attempts:
        claim=by_claim.get(attempt['claim_id'])
        if not claim:
            continue
        cid=claim['candidate_id']
        sampled.add(cid)
        site=sites[cid]
        page=by_candidate[cid]
        root=(Path(scope['output'])/plan_for_worker[claim['worker_id']]/claim['worker_id']/claim['claim_id']
              /'execution/capture/evidence'/attempt['sample_id'])
        reason=(attempt['root_cause'] or attempt['status']).split(':',1)[0]
        codes[site][reason]+=1
        phases=page.get('stepwise_evidence',{})
        if page['stages']['effective_steps_ge5']['state']=='reached' and not phases.get('complete_accepted'):
            gaps['five_to_complete'][reason]+=1
        if phases.get('complete_accepted') and not phases.get('writeback_http'):
            gaps['complete_to_writeback'][reason]+=1
        if phases.get('writeback_http') and not phases.get('writeback_validated'):
            gaps['writeback_to_validated'][reason]+=1
        for ref in (root/'stepwise').glob('decision-rejection-*.json'):
            problem=read(ref).get('reason','').split(':',1)[0]
            rejections[problem]+=1
        if phases.get('judgement_http') and (root/'judgement.json').is_file():
            event=read(root/'judgement.json')
            assert event['attempt_id']==attempt['attempt_id']
            decision=event.get('validated') or {}
            if decision:
                for field in ('redundant_steps','mismatch_steps'):
                    if decision[field]:
                        judgement[field]+=1
                for field in ('completed','judgement_supported','instruction_specific'):
                    if decision[field] is False:
                        judgement[field+'_false']+=1
        if page['stages']['formally_saved']['state']=='reached':
            assert attempt['status']=='collected_pending_review' and page['sample_id']==attempt['sample_id']
            verify_evidence(page['stages']['formally_saved']['evidence'])
            saved.append({'site':site,'candidate_id':cid,'sample_id':attempt['sample_id'],
                          'effective_steps':page['effective_steps'],'review':'pending_review'})
    assert len(claims)==len(by_claim)==len({c['candidate_id'] for c in claims})
    assert len(saved)==funnel['saved']
    sites_by_app={row['application_id']:sites[row['candidate_id']] for row in funnel['candidates']}
    data={'plan_ids':sorted(set(plan_for_worker.values())), 'verified_worker_peak':peak,
          'selected':len(sites),'claims':len(claims),'formal_attempts':sum(sum(c.values()) for c in codes.values()),
          'unclaimed':len(sites)-len(claims),'claimed_without_formal_attempt':len(claims)-len(sampled),
          'stages':funnel['stepwise_funnel'],'by_site':{sites_by_app[k]:v for k,v in funnel['stepwise_by_site'].items()},
          'integrity':funnel['integrity'],'issues':funnel['issues'],'attempt_outcomes_by_site':codes,
          'conversion_losses_by_reason':gaps,'decision_rejections_by_event':rejections,
          'independent_judgement_failures_by_flag':judgement,'verified_saved_pending_review':saved}
    (ARCHIVE/'accounting.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(data['stages'],ensure_ascii=False))


if __name__=='__main__':
    main()
