"""Compact, shareable page funnel and failure evidence for the selected cohort."""
import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from webcollect.planning import verify_evidence
from webcollect.stepwise import finalize, observation

from run import ARCHIVE, RUN, ROOT


def read(path):
    return json.loads(path.read_text())


def query(path, sql, args=()):
    with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro', uri=True)) as con:
        con.row_factory=sqlite3.Row
        return [dict(row) for row in con.execute(sql, args)]


def check_rejected_frame(ref, record, counts):
    reason = record['reason']
    if not reason.startswith(('CURRENT_FRAME_CITATION:', 'HOTKEY_KEYS_NOT_ALLOWED:')):
        return
    frame_no = int(record['frame_id'][1:])
    state = read(ref.parent / f'observation-{frame_no:03d}.json')
    decision = read(ref.parent / f"decision-{record['round']:03d}.json")
    assert decision['frame_id'] == record['frame_id']
    arguments = decision['arguments']
    if reason.startswith('HOTKEY_KEYS_NOT_ALLOWED:'):
        keys = arguments.get('keys')
        if isinstance(keys, list) and len(keys) == 1 and isinstance(keys[0], str) and '+' in keys[0]:
            split = keys[0].lower().split('+')
            counts['plus_joined_hotkey_decisions'] += 1
            if observation._hotkey_allowed(state, split):
                counts['split_hotkey_accepted_by_same_frame_focus_and_key_checks'] += 1
                try:
                    action, _ = observation.bind_action(state, observation.actionable_rows(state), arguments)
                    observation.require_action(state, action)
                except (ValueError, observation.ActionRejected):
                    pass
                else:
                    counts['plus_joined_original_decision_now_fully_bindable'] += 1
        return
    counts['citation_rejection_decisions'] += 1
    corpus = finalize._corpus(state)
    visible_ids = {item['element_id'] for item in state.get('elements', []) if item.get('visible')}
    values = {''.join(str(item[key]).split()) for item in state.get('values', [])
              if item.get('value_visible') and item.get('element_id') in visible_ids
              for key in ('value', 'display_value') if item.get(key)}
    missing = {''.join(quote.split()) for field in ('page_name', 'precondition', 'last_step_result')
               if f'{field} 引文' in reason for quote in finalize.quoted_segments(arguments.get(field))
               if ''.join(quote.split()) not in corpus}
    assert missing
    if missing & values:
        counts['citation_decisions_with_exact_visible_control_value'] += 1
    option_labels = {''.join(label.split()) for label in finalize.prompt.selected_option_labels(state).values()}
    if missing & option_labels:
        counts['citation_decisions_with_verified_selected_label'] += 1
        if missing <= option_labels:
            counts['citation_decisions_with_all_missing_quotes_resolved'] += 1
    if frame_no > 1:
        previous = finalize._corpus(read(ref.parent / f'observation-{frame_no-1:03d}.json'))
        if any(quote in previous for quote in missing):
            counts['citation_decisions_with_quote_in_previous_frame_text'] += 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--original-remainder',action='store_true')
    args=parser.parse_args()
    archive=ARCHIVE
    run=RUN
    if args.original_remainder:
        archive=ARCHIVE.parent/'stepwise-three-sites-150-20261118'
        run=RUN.parent/archive.name
    subset=read(archive/'run-04-selection.json') if args.original_remainder else None
    scope=read(ROOT/'database/sqllite/prod/scope.json')
    sites={row['candidate_id']:row['host'].removeprefix('www.') for row in (subset or read(archive/'selection.json'))['pages']}
    segments=[s for s in sorted(run.glob('run-[0-9][0-9]')) if not subset or int(s.name[4:]) >= 4]
    funnel=read(segments[-1]/'funnel.json')
    plan_for_worker={}
    for segment in segments:
        plan=read(segment/'prepared-plan.json')
        plan_for_worker.update({worker['worker_id']:plan['plan_id'] for worker in plan['workers']})
    peak=max(read(archive/(segment.name+'-final.json'))['worker_peak_observed'] for segment in segments)
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
    judgement_examples=[]
    rejections=Counter()
    pages_with_rejections=defaultdict(set)
    rejected_frames=Counter()
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
        steps=max(page['effective_steps'] or 0, page.get('effective_steps_lower_bound',0))
        if phases.get('decision_http') and steps == 0:
            gaps['decision_to_first_action'][reason]+=1
        if 0 < steps < 5:
            gaps['one_to_five_actions'][reason]+=1
        if page['stages']['effective_steps_ge5']['state']=='reached' and not phases.get('complete_accepted'):
            gaps['five_to_complete'][reason]+=1
        if phases.get('complete_accepted') and not phases.get('writeback_http'):
            gaps['complete_to_writeback'][reason]+=1
        if phases.get('writeback_http') and not phases.get('writeback_validated'):
            gaps['writeback_to_validated'][reason]+=1
        for ref in (root/'stepwise').glob('decision-rejection-*.json'):
            record=read(ref)
            problem=record.get('reason','').split(':',1)[0]
            rejections[problem]+=1
            pages_with_rejections[problem].add(cid)
            if subset:
                check_rejected_frame(ref, record, rejected_frames)
        if phases.get('judgement_http') and (root/'judgement.json').is_file():
            event=read(root/'judgement.json')
            assert event['attempt_id']==attempt['attempt_id']
            decision=event.get('validated') or {}
            if decision:
                if not finalize.judgement_passed(decision):
                    judgement_examples.append({'site':site,'candidate_id':cid,**{
                        name:decision[name] for name in ('instruction_specific','completed',
                            'judgement_supported','redundant_steps','mismatch_steps')}})
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
    assert len(saved)+(subset['previously_saved'] if subset else 0)==funnel['saved']
    pages=[row for row in funnel['candidates'] if row['candidate_id'] in sites]
    def stages(group):
        def stage(name):
            return sum(p['stages'][name]['state']=='reached' for p in group)
        def phase(name):
            return sum(bool(p.get('stepwise_evidence',{}).get(name)) for p in group)
        return dict(selected=len(group),claimed=stage('claimed'),first_frame=stage('first_frame'),
            decision_http=phase('decision_http'),effective_ge1=sum(
                max(p['effective_steps'] or 0,p.get('effective_steps_lower_bound',0))>=1 for p in group),
            effective_ge5=stage('effective_steps_ge5'),complete_accepted=phase('complete_accepted'),
            writeback_http=phase('writeback_http'),writeback_validated=phase('writeback_validated'),
            judgement_http=phase('judgement_http'),judgement_passed=phase('judgement_passed'),formally_saved=stage('formally_saved'))
    assert stages(funnel['candidates'])==funnel['stepwise_funnel']
    data={'plan_ids':sorted(set(plan_for_worker.values())), 'verified_worker_peak':peak,
          'selected':len(sites),'claims':len(claims),'formal_attempts':sum(sum(c.values()) for c in codes.values()),
          'unclaimed':len(sites)-len(claims),'claimed_without_formal_attempt':len(claims)-len(sampled),
          'stages':stages(pages),'by_site':{site:stages([p for p in pages if sites[p['candidate_id']]==site]) for site in sorted(set(sites.values()))},
          'integrity':funnel['integrity'],'integrity_scope':'entire_fixed_cohort',
          'issues':funnel['issues'],'attempt_outcomes_by_site':codes,
          'conversion_losses_by_reason':gaps,'decision_rejections_by_event':rejections,
          'decision_rejections_by_affected_page':{reason:len(ids) for reason,ids in pages_with_rejections.items()},
          'independent_judgement_failures_by_flag':judgement,'verified_saved_pending_review':saved}
    if subset:
        data['same_frame_rejection_replay']=rejected_frames
        data['judgements_rejected_with_valid_response']=judgement_examples
        data['original_150_cumulative']=funnel['stepwise_funnel']
        data['previous_saved_and_remaining']=dict(saved=subset['previously_saved'],remaining=subset['remaining'])
        reports=[read(archive/(segment.name+'-final.json')) for segment in segments]
        usage=[report['segment_consumer_model'] for report in reports]
        states=sum((Counter(item['states']) for item in usage),Counter())
        dispatch=sum((Counter(item['dispatch']) for item in usage),Counter())
        totals={key:sum(item[key] for item in usage) for key in (
            'requests','known_input_tokens','known_output_tokens','unknown_usage_requests')}
        prior=read(archive/'run-03-final.json')['consumer_model']
        cumulative=reports[-1]['consumer_model']
        assert all(prior[key]+value==cumulative[key] for key,value in totals.items())
        assert Counter(prior['states'])+states==Counter(cumulative['states'])
        assert Counter(prior['dispatch'])+dispatch==Counter(cumulative['dispatch'])
        data['consumer_model']={**totals,'states':states,'dispatch':dispatch,'cost':'UNKNOWN'}
        data['candidate_evidence_inconsistencies_in_remainder']=sum(bool(p.get('inconsistencies')) for p in pages)
        data['segment_results']=[{'segment':report['segment'],'claimed':report['segment_new_claims'],
            'formal_attempts':report['segment_new_attempts'],'saved_pending_review':report['segment_saved_pending_review'],
            'worker_peak_observed':report['worker_peak_observed']} for report in reports]
    (archive/('remainder-accounting.json' if subset else 'accounting.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(data['stages'],ensure_ascii=False))


if __name__=='__main__':
    main()
