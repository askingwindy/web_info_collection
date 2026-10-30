"""Versioned 10/30/100 sampling and quality-unit admission, separate from reviews."""
from copy import deepcopy
import math

VERSION = 'qc-sampling-v1-20261030'


def selected(slots, policy, *, random_only=False):
    from .delivery_sampling import digest
    context = policy['production_sampling']; groups = context['groups']; stages = context['stages']
    chosen = set()
    for group in sorted(set(groups.values())):
        ids = [s['slot_id'] for s in slots if groups[s['slot_id']] == group]
        ranked = sorted(ids, key=lambda sid: (digest([policy['seed'], 'ai', group, sid]), sid))
        chosen.update(ranked[:math.ceil(len(ids)*stages[group]/100)])
    if not random_only:
        chosen.update(context['mandatory'])
        chosen.update(policy.get('risk_selected', {}))
    return chosen


def attach(policy, slots, context):
    from webcollect.sampling_context import verify_context, history_state
    verify_context(context)
    if set(context['groups']) != {s['slot_id'] for s in slots}:
        raise ValueError('Production sampling context differs from the exact captured population')
    state = history_state(context); mandatory = {}
    for sid, pos in context['positions'].items():
        reasons = (['campaign-first-10'] if pos['campaign'] <= 10 else []) + (['group-first-5'] if pos['group'] <= 5 else [])
        if reasons:
            mandatory[sid] = reasons
    policy['production_sampling'] = {**deepcopy(context), 'mandatory': mandatory,
        'stages': {g: 100 if s['full'] else 10 for g, s in state.items()}}


def verify(plan):
    from webcollect.sampling_context import verify_context
    context = plan['policy']['production_sampling']
    verify_context({k: context[k] for k in ('version', 'source', 'groups', 'positions', 'task_sha256', 'predecessors')})
    groups = set(context['groups'].values())
    if (context['version'] != VERSION or plan['policy']['ai_percent'] != 10
            or plan['policy']['human_percent'] != 0 or set(context['stages']) != groups
            or any(p not in (10, 30, 100) for p in context['stages'].values())):
        raise ValueError('Invalid versioned 10/30/100 production policy')
    risks = plan['policy'].get('risk_selected', {})
    if set(risks)-set(context['groups']) or any(not isinstance(v,list) or not v or
            any(not isinstance(reason,str) or not reason.strip() for reason in v) for v in risks.values()):
        raise ValueError('Risk selection must bind known samples and explicit actual reasons')
    expected = {sid: (['campaign-first-10'] if pos['campaign'] <= 10 else []) +
        (['group-first-5'] if pos['group'] <= 5 else []) for sid, pos in context['positions'].items()}
    if context['mandatory'] != {sid: reasons for sid, reasons in expected.items() if reasons}:
        raise ValueError('Startup/new-group mandatory coverage changed')


def evaluate(plan, ai, human, failures, errors):
    """Inputs have passed the existing full-frame review intake, never raw claims."""
    from .delivery_sampling import _status
    from webcollect.sampling_context import history_state
    if human:
        raise ValueError('Fragment batch policy records independent AI only; do not relabel human decisions as AI. Legacy explicit human review remains separate.')
    policy = plan['policy']; ctx = policy['production_sampling']
    source = {k: ctx[k] for k in ('version', 'source', 'groups', 'positions', 'task_sha256', 'predecessors')}
    history = history_state(source); decisions = {}; effective = {}; rows = []
    unknown_input = any(e.get('sample_id') not in (None, *ctx['groups']) for e in errors)
    for slot in plan['slots']:
        sid = slot['current']['sample_id']; record = human.get(sid) or ai.get(sid)
        invalid = unknown_input or any(e.get('sample_id') in (None, sid) for e in errors)
        result = _status(record) if record and not invalid and not failures.get(sid) else 'REVIEW_REQUIRED'
        if record and result in ('PASS', 'FAIL'):
            effective[sid] = record['record']
        decisions[sid] = result if slot['ai_selected'] or record else 'NOT_SELECTED'
    units = {}
    for group in sorted(set(ctx['groups'].values())):
        ids = [s['slot_id'] for s in plan['slots'] if ctx['groups'][s['slot_id']] == group]
        bad = [sid for sid in ids if decisions[sid] == 'FAIL']
        pending = [sid for sid in ids if decisions[sid] == 'REVIEW_REQUIRED']
        severe = any(any(name in ('privacy', 'visual_alignment') and c['status'] == 'FAIL'
            for name, c in (human.get(sid) or ai.get(sid))['record']['checks'].items()) for sid in bad)
        mandatory_fail = any(sid in ctx['mandatory'] for sid in bad)
        localized = set()
        for sid in bad:
            record = (human.get(sid) or ai.get(sid))['record']; detail = record.get('failure_assessment', {})
            if (detail.get('scope') == 'LOCAL' and isinstance(detail.get('reason'), str) and detail['reason'].strip()
                    and detail.get('evidence_steps') and set(detail['evidence_steps']) <=
                    {r['step_id'] for r in record['step_observations']}):
                localized.add(sid)
        stage = ctx['stages'][group]
        target = 100 if history[group]['full'] or severe or mandatory_fail or len(bad) >= 2 or not set(bad) <= localized else 30 if bad else 10
        target = max(stage, target)
        ready = (stage >= target and not pending and not history[group]['pending'])
        units[group] = {'stage_percent': stage, 'required_percent': target, 'original_denominator': len(ids),
            'failures': bad, 'pending': pending, 'history_pending': history[group]['pending'],
            'force_full': target == 100, 'new_group_issue': target==100 and bool(bad),
            'status': 'ACCEPTED' if ready else 'EXPANDING' if target > stage else 'PENDING'}
        for slot in plan['slots']:
            sid = slot['current']['sample_id']
            if sid not in ids:
                continue
            decision = decisions[sid]; accepted = ready and decision not in ('FAIL', 'REVIEW_REQUIRED')
            rows.append({'sample_id': sid, 'slot_id': slot['slot_id'], 'site_id': slot['site_id'], 'group_id': group,
                'ai_selected': slot['ai_selected'], 'human_random_selected': False,
                'ai_status': decision, 'human_status': _status(human[sid]) if sid in human else 'NOT_SELECTED',
                'human_required': False, 'replacement': False,
                'status': 'AI_PASS' if decision == 'PASS' else 'REJECTED' if decision == 'FAIL' else 'AI_REQUIRED' if decision == 'REVIEW_REQUIRED' else 'NOT_SELECTED',
                'admission_status': 'PASS' if accepted else 'FAIL' if decision == 'FAIL' else 'REVIEW_REQUIRED',
                'quality_admission': 'ACCEPTED_BY_BATCH_POLICY' if accepted else 'REJECTED' if decision == 'FAIL' else 'PENDING',
                'force_full': target == 100, 'ai_source': ai.get(sid, {}).get('source'), 'human_source': human.get(sid, {}).get('source'),
                'evidence_sha256': slot['current']['evidence_sha256'], 'annotation_sha256': slot['current']['annotation_sha256'],
                'semantic_review_claimed': decision == 'PASS'})
    return rows, effective, units


def advance(plan_path, dataset, output, *, ai_reviews=(), human_reviews=(), ai_failures=()):
    """Re-evaluate actual intake and freeze a monotone successor; never dispatch."""
    from . import delivery_sampling as s
    plan = s.verify(plan_path, dataset)
    if not plan['policy'].get('production_sampling'):
        raise ValueError('Only the explicit production policy can expand this way')
    assessment, _ = s.evaluate(plan_path, dataset, ai_reviews=ai_reviews, human_reviews=human_reviews, ai_failures=ai_failures)
    successor = deepcopy(plan); ctx = successor['policy']['production_sampling']
    for group, unit in assessment['quality_units'].items():
        ctx['stages'][group] = max(ctx['stages'][group], unit['required_percent'])
    if ctx['stages'] == plan['policy']['production_sampling']['stages']:
        return {'changed': False, 'assessment': assessment, 'plan': str(plan_path)}
    successor['parent'] = s._source(plan_path); successor['revision'] += 1
    successor['expansion'] = {'policy_version': VERSION,
        'ai_reviews': [s._source(p) for p in ai_reviews], 'human_reviews': [s._source(p) for p in human_reviews],
        'ai_failures': [s._source(p) for p in ai_failures], 'assessment_sha256': s.digest(assessment)}
    for slot in successor['slots']:
        slot['ai_selected'] = slot['slot_id'] in selected(successor['slots'], successor['policy'])
    successor = s._seal(successor); s.write(output, successor)
    s.verify(output, dataset)
    return {'changed': True, 'assessment': assessment, 'plan': str(output)}


def verify_expansion(plan, parent):
    from . import delivery_sampling as s
    if (not parent['policy'].get('production_sampling') or plan['original_denominator'] != parent['original_denominator']
            or plan['revision'] != parent['revision']+1):
        raise ValueError('Expansion must retain its original population and parent')
    old = deepcopy(parent); new = deepcopy(plan)
    # Recompute escalation from bound, independently validated original reviews.
    proof = plan['expansion']
    paths = {}
    for name in ('ai_reviews', 'human_reviews', 'ai_failures'):
        for ref in proof[name]:
            if s.sha(ref['path']) != ref['sha256']:
                raise ValueError('Expansion review evidence changed')
        paths[name] = [ref['path'] for ref in proof[name]]
    dataset = parent['slots'][0]['current']['source_path']
    from pathlib import Path
    dataset = Path(dataset).parents[1]
    assessment, _ = s.evaluate(plan['parent']['path'], dataset, **paths)
    if s.digest(assessment) != proof['assessment_sha256']:
        raise ValueError('Expansion assessment changed')
    expected = {g: max(parent['policy']['production_sampling']['stages'][g], u['required_percent'])
                for g, u in assessment['quality_units'].items()}
    if new['policy']['production_sampling']['stages'] != expected:
        raise ValueError('Expansion stage is not justified by the original assessment')
    for value in (old, new):
        for key in ('parent', 'revision', 'expansion', 'plan_sha256'):
            value.pop(key, None)
        value['policy']['production_sampling'].pop('stages')
        for slot in value['slots']:
            slot.pop('ai_selected')
    if old != new:
        raise ValueError('Expansion cannot change source, seed, groups, slots or original reviews')


def quality_report(report, effective_set, cross_package_report, production_handoff=None):
    """Recompute program checks and actual intake; no report flag grants admission."""
    from . import delivery_sampling as s
    from .format_checks import run as formats_run
    from .duplicates import analyze
    from .delivery_scope import verify_delivery_scope
    sampling = report['semantic_sampling']
    if sampling.get('production_policy') != VERSION or report.get('pipeline_execution_mode') == 'controlled':
        raise ValueError('Only actual versioned production QC can register quality admission')
    if production_handoff is None:
        raise ValueError('Original production capture handoff is required for batch admission')
    from webcollect.site_pool_sync import validate_handoff
    validate_handoff(production_handoff, report['dataset'])
    refs = sampling['review_sources']; failure_refs = sampling.get('ai_failure_sources', [])
    for ref in [*refs['ai'], *refs['human'], *failure_refs]:
        if s.sha(ref['path']) != ref['sha256']:
            raise ValueError('Actual review source changed')
    actual, _ = s.evaluate(sampling['plan']['path'], report['dataset'],
        ai_reviews=[r['path'] for r in refs['ai']], human_reviews=[r['path'] for r in refs['human']],
        ai_failures=[r['path'] for r in failure_refs])
    if actual != sampling:
        raise ValueError('Batch sampling/admission differs from actual review intake')
    scope = verify_delivery_scope(effective_set['path'], cross_package_report['path'], dataset=report['dataset'], phase='payload')
    if s.sha(effective_set['path']) != effective_set['sha256'] or s.sha(cross_package_report['path']) != cross_package_report['sha256']:
        raise ValueError('Cumulative comparison binding changed')
    cross = s.read(cross_package_report['path']); formats = formats_run(None, report['dataset']); duplicates = analyze(report['dataset'])
    global_pass = (cross.get('mechanical_status') == 'PASS' and not formats['package_errors'] and
        duplicates['summary'].get('analysis_status') == 'COMPLETE' and
        duplicates['summary'].get('unadjudicated_pair_count') == 0 and not duplicates['route1']['pairs'])
    program = {r['sample_id']: bool(r.get('confirmed_format_pass')) for r in formats['samples']}
    rows = []
    for row in actual['rows']:
        value = deepcopy(row); value['program_check'] = 'PASS' if program.get(row['sample_id']) else 'FAIL'
        if not program.get(row['sample_id']):
            value['quality_admission'] = 'REJECTED'
        elif not global_pass and value['quality_admission'] == 'ACCEPTED_BY_BATCH_POLICY':
            value['quality_admission'] = 'PENDING'
        rows.append(value)
    accepted = [r for r in rows if r['quality_admission'] == 'ACCEPTED_BY_BATCH_POLICY']
    return {'policy_version': VERSION, 'effective_set': effective_set, 'cross_package_report': cross_package_report,
        'production_handoff': production_handoff,
        'global_program_check': 'PASS' if global_pass else 'REVIEW_REQUIRED', 'delivery_scope': scope,
        'rows': rows, 'quality_units': actual['quality_units'], 'accepted_count': len(accepted),
        'accepted_ai_pass': sum(r['ai_status']=='PASS' for r in accepted),
        'accepted_not_selected': sum(r['ai_status']=='NOT_SELECTED' for r in accepted),
        'published': False, 'customer_acceptance': 'UNKNOWN'}
