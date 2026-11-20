"""本批只读进度和最终对账，分母来自领页前固定的名单。"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from run import ARCHIVE, RUN, SCOPE
from progress import history, read, records, select, write
from webcollect.stepwise.finalize import judgement_passed


def accounting(final=False):
    cohort = read(ARCHIVE / 'selection.json')['pages']
    sites = {row['candidate_id']: row['host'].removeprefix('www.') for row in cohort}
    scope = read(SCOPE)
    segments = sorted(RUN.glob('run-??'))
    plans = [read(seg / 'prepared-plan.json') for seg in segments]
    worker_plan = {w['worker_id']: p['plan_id'] for p in plans for w in p['workers']}
    marks = ','.join('?' for _ in sites)
    claims = select(scope['pool'], f'''SELECT c.candidate_id,c.claim_id,c.worker_id,c.state,c.stage,
        r.sample_id,r.qc_state FROM candidate_claims c LEFT JOIN candidate_results r
        ON r.claim_id=c.claim_id AND r.candidate_id=c.candidate_id WHERE c.candidate_id IN ({marks})''', list(sites))
    assert all(c['worker_id'] in worker_plan for c in claims)
    assert len(claims) == len({c['candidate_id'] for c in claims})
    start = datetime.fromisoformat(read(segments[0] / 'controller-start.json')['started']).timestamp()
    by_claim = {c['claim_id']: c for c in claims}
    attempts = {r['claim_id']: r for r in select(scope['registry'], '''SELECT a.attempt_id,a.sample_id,a.status,
        a.root_cause,json_extract(t.task_json,'$.candidate_binding.claim_id') claim_id FROM m4_attempts a
        JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.created_at>=?''', (start,)) if r['claim_id'] in by_claim}
    by_site = {site: dict(selected=n, claimed=0, formal=0, saved=0) for site, n in Counter(sites.values()).items()}
    reasons = defaultdict(Counter)
    for cid, claim in by_claim.items():
        site = sites[claim['candidate_id']]
        item = by_site[site]
        item['claimed'] += 1
        if cid in attempts:
            item['formal'] += 1
            if attempts[cid]['root_cause']:
                reasons[site][attempts[cid]['root_cause'].split(':', 1)[0]] += 1
        if claim['sample_id'] and claim['qc_state'] == 'pending_review':
            item['saved'] += 1
    obs = [r for seg in segments for r in records(seg / 'worker-observations.jsonl')]
    out = dict(at=datetime.now().astimezone().isoformat(timespec='seconds'), per_site=by_site,
               claim_states=dict(Counter(r['state'] for r in claims)), root_causes=reasons,
               observed_peak=max((r['peak'] for r in obs), default=0))
    if not final:
        return out
    summary = read(segments[-1] / 'summary.json')
    funnel = read(segments[-1] / 'funnel.json')
    data = {p['candidate_id']: p for p in funnel['candidates']}
    assert len(data) == len(cohort) == funnel['denominator'] == 30
    out.update(worker_exit_codes=dict(Counter(str(w['returncode']) for w in summary['workers'])),
               stop_reason=summary['stop_reason'], integrity=funnel['integrity'], issues=funnel['issues'],
               funnel=funnel['stepwise_funnel'], per_site_funnel={
                   sites[cid]: funnel['stepwise_by_site'][p['application_id']] for cid, p in data.items()},
               usage=funnel['usage']['consumer'], pages=[], saved_samples=[])
    for cid, claim in by_claim.items():
        candidate_id = claim['candidate_id']
        page = data[candidate_id]
        attempt = attempts.get(cid)
        item = dict(candidate_id=candidate_id, site=sites[candidate_id], claim_state=claim['state'],
                    attempt_status=attempt['status'] if attempt else None, sample_id=claim['sample_id'],
                    effective_steps=page['effective_steps'], phases=page.get('stepwise_evidence', {}),
                    cause=attempt['root_cause'] if attempt else None)
        if attempt:
            root = (Path(scope['output']) / worker_plan[claim['worker_id']] / claim['worker_id'] / cid /
                    'execution/capture/evidence' / attempt['sample_id'])
            rejected = Counter(read(p)['reason'].split(':',1)[0] for p in (root / 'stepwise').glob('decision-rejection-*.json'))
            item['decision_rejections'] = dict(rejected)
            if (root / 'judgement.json').is_file():
                j = read(root / 'judgement.json')
                item['judgement'] = j['validated'] or {'mechanical_problem': j['mechanical_problem']}
            if page['stages']['formally_saved']['state'] == 'reached':
                assert (claim['qc_state'] == 'pending_review' and claim['state'] == 'succeeded'
                        and attempt['status'] == 'collected_pending_review'
                        and claim['sample_id'] == attempt['sample_id'] == page['sample_id']
                        and judgement_passed(item['judgement']))
                finalization = read(root / 'stepwise-finalization.json')
                out['saved_samples'].append(dict(site=sites[candidate_id], sample_id=claim['sample_id'],
                    candidate_id=candidate_id, effective_steps=page['effective_steps'],
                    instruction=finalization.get('task_instruction') or finalization['writeback']['model_instruction'],
                    evidence=str(root.relative_to(ARCHIVE.parents[1]))))
        out['pages'].append(item)
    assert sum(r['saved'] for r in by_site.values()) == len(out['saved_samples']) == funnel['saved']
    out['target_passed'] = funnel['saved'] >= 6 and by_site['dpm.org.cn']['saved'] >= 1
    out['history'] = history(scope, read(RUN / 'before.json'))
    out['failure_events'] = [dict(segment=seg.name, **{k: r.get(k) for k in
        ('at','claim_id','reason_owner','disposition','reason','sqlite_database','sqlite_operation','retry_count','stop_dispatch')})
        for seg in segments for r in records(seg / 'failure-events.jsonl')]
    return out


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    result = accounting(args.final)
    if args.final:
        write(ARCHIVE / 'accounting.json', result)
    print(json.dumps({k:v for k,v in result.items() if k in
          ('at','per_site','claim_states','root_causes','observed_peak','integrity','funnel','target_passed')}, ensure_ascii=False))
