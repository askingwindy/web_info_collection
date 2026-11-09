"""Explicit historical-prefix projection; never rewrites the source attempt.

A prefix is an ordinary independent review candidate, not completion of the
original goal. Its historical after-frame remains usable when a later action's
result is unknown. No browser or model call is made here.
"""
from copy import deepcopy
from pathlib import Path

from .batch_core import file_sha, load_json
from .planning import object_sha256, verify_evidence

VERSION = 'webcollect-trusted-prefix-1'
MINIMUM = 6
# V2 accepts any nonempty consecutive effective-action prefix: 1-4 effective
# actions classify short_flow, >=5 ordinary, zero actions never a sample. The
# V1 six-action rule keeps explaining its own historical receipts.
V2_VERSION = 'webcollect-trusted-prefix-2'
V2_MINIMUM = 1
RULES = {VERSION: MINIMUM, V2_VERSION: V2_MINIMUM}
CLASSIFICATION = '1-4 effective actions -> short_flow; >=5 -> ordinary; 0 -> not a sample'


def _projection(source, raw_root, end_step, ids, *, rule=VERSION, _verified=None):
    from .postprocess import effective_trajectory
    from .agent_observation import project
    from .react_session import struct_goal
    minimum = RULES.get(rule)
    if minimum is None:
        raise ValueError('Unknown trusted-prefix rule')
    if type(end_step) is not int or not minimum <= end_step <= len(source['trajectory']):
        raise ValueError('Trusted prefix requires at least '
                         + ('six' if rule == VERSION else str(minimum))
                         + ' original consecutive effective actions')
    if source['boundary'].get('attempt_id') not in (None, ids['attempt_id']):
        raise ValueError('Prefix attempt differs from its sealed source attempt')
    rows = deepcopy(source['trajectory'][:end_step])
    final_id = rows[-1]['after_observation_id']
    final = source['observations'][final_id]
    state = load_json(final['state_path'])
    ob = (_verified.observations(source, final_id) if _verified is not None else
          project(state, {k: final['evidence'][k] for k in ('image', 'state', 'capture')}))
    if not ob['capture_verified'] or not (state.get('visible_text') or '').strip():
        raise ValueError('Historical boundary has no independently verified image and synchronized tree')
    # Use the established atomic-effect and continuity checks without the old
    # terminal contract: the new ending concerns the historical boundary only.
    task = deepcopy(source['task'])
    task['fragment'].pop('ending_policy', None)
    terminal = {**deepcopy(source['terminal']), 'unknown': False,
        'actual_actions': end_step, 'effective_steps': end_step,
        'final_observation_id': final_id, 'stop_reason': 'ready',
        'stop_summary': '历史可信区间结束；不声称完整原目标完成'}
    terminal.pop('collection_ending', None)
    terminal.pop('goal_evidence', None)
    recount = {**source, 'task': task, 'trajectory': rows, 'terminal': terminal,
               'continuity_proofs': deepcopy(source.get('continuity_proofs', []))}
    if len(effective_trajectory(recount, _verified=_verified)) != end_step:
        raise ValueError('Prefix interval contains duplicate dispatches')
    source_receipt = {'path': str((Path(raw_root)/'raw-receipt.json').resolve()),
                      'sha256': file_sha(Path(raw_root)/'raw-receipt.json')}
    binding = {'protocol': rule, 'kind': 'TRUSTED_HISTORICAL_PREFIX', 'flagged': False, 'source_attempt_id': ids['attempt_id'],
        'source_interval': {'start_step': 1, 'end_step': end_step},
        'effective_actions': end_step, 'classification_rule': CLASSIFICATION,
        'source_operations': [row['operation_id'] for row in rows],
        'raw_receipt': source_receipt, 'source_terminal': deepcopy(source['receipt']['terminal']),
        'boundary_observation_id': final_id, 'boundary_evidence': deepcopy(final['evidence']),
        'source_task_sha256': object_sha256(source['task']),
        'requested_goal': deepcopy(struct_goal(source['task'])),
        'session_objective':deepcopy(source['task'].get('fragment',{}).get('session_objective')),
        'working_goal': deepcopy(source['terminal'].get('working_goal')),
        'excluded_tail': {'source_unknown': source['terminal'].get('unknown') is True,
            'actual_dispatches': max(0, source['terminal'].get('actual_actions', 0)-end_step),
            'verified_effective_steps': len(source['trajectory'])-end_step,
            'stop_reason': source['terminal'].get('stop_reason'),
            'source_ending': deepcopy(source['terminal'].get('collection_ending'))},
        'original_goal_completed': False, 'QC_approval': False,
        'cost_attribution': 'Original attempt and model-request ledger retained; no new model calls',
        'interval_key': object_sha256({'rule': rule, 'attempt_id': ids['attempt_id'],
            'raw_receipt': source_receipt, 'start_step': 1, 'end_step': end_step})}
    # Keep the original task and all source observations/goals. Only the
    # derivative terminal points at the historical boundary.
    return {**source, 'trajectory': rows, 'terminal': terminal, 'trusted_prefix': binding,
            **({'continuity_proofs': deepcopy(recount['continuity_proofs'])}
               if recount.get('continuity_proofs') else {})}


def project_prefix(source, raw_root, end_step, ids, *, rule=VERSION, _verified=None):
    if _verified is not None:
        return _verified.prefix(source, raw_root, end_step, ids, rule)
    return _projection(source, raw_root, end_step, ids, rule=rule)


def validate_projection(record, *, _verified=None):
    from .postprocess import _VerifiedSession
    binding = record['trusted_prefix']
    verify_evidence([binding['raw_receipt'], binding['source_terminal']])
    root = Path(binding['raw_receipt']['path']).parent
    verified = _verified if _verified is not None else _VerifiedSession(root)
    source = verified.record(root)
    expected = project_prefix(source, root, binding['source_interval']['end_step'],
                              {'attempt_id': binding['source_attempt_id']},
                              rule=binding['protocol'], _verified=verified)
    if (binding != expected['trusted_prefix'] or record['task'] != expected['task']
            or record['trajectory'] != expected['trajectory'] or record['terminal'] != expected['terminal']
            or record['observations'] != expected['observations']):
        raise ValueError('Prefix projection differs from its independently rechecked source interval')
    return binding


def candidate_end(raw_root, *, rule=VERSION, _verified=None):
    """Largest historical boundary available; no unknown tail is retried."""
    from .postprocess import session_record
    minimum = RULES.get(rule)
    if minimum is None:
        raise ValueError('Unknown trusted-prefix rule')
    source = (_verified.record(raw_root) if _verified is not None else
              session_record(raw_root, allow_unknown_for_prefix=True))
    return len(source['trajectory']) if len(source['trajectory']) >= minimum else None


def natural_instruction(record):
    """Use the verified business goal, not a step-by-step replay of the trace."""
    from .task_instruction import generated_instruction
    focus=(record['terminal'].get('working_goal')
           or record['trusted_prefix'].get('working_goal') or '').strip()
    if focus:
        return generated_instruction('在「'+record['task']['app_name']+'」上'+focus)
    requested=record['trusted_prefix'].get('requested_goal') or {}
    if isinstance(requested,dict):
        focus=str(requested.get('instruction') or requested.get('goal') or '').strip()
        if focus:
            return generated_instruction(focus)
    raise ValueError('Trusted prefix has no verified business goal for customer instruction')


def model_context(binding):
    """Bound QC context contains no local paths or original private protocol."""
    return {'protocol':binding['protocol'],'source_attempt_id':binding['source_attempt_id'],
        'source_interval':binding['source_interval'],'source_operations':binding['source_operations'],
        'historical_boundary_image_sha256':binding['boundary_evidence']['image']['sha256'],
        'historical_boundary_tree_sha256':binding['boundary_evidence']['state']['sha256'],
        'excluded_tail_unknown':binding['excluded_tail']['source_unknown'],
        'excluded_tail_dispatches':binding['excluded_tail']['actual_dispatches'],
        'original_goal_completed':False,'QC_approval':False}


def projection_index(evidence):
    """Saved receipts select one projection; failed revisions remain immutable."""
    evidence=Path(evidence)
    saved=evidence/'saved_sample.json'
    if saved.exists():
        ref=load_json(saved).get('derivation',{}).get('prefix_projection')
        if ref:
            verify_evidence([ref])
            path=Path(ref['path'])
            if path.parent.resolve()!=evidence.resolve():raise ValueError('Prefix projection outside source evidence')
            return path
        return None
    candidates=sorted(evidence.glob('trusted-prefix-projection-[0-9][0-9].json'))
    return candidates[-1] if candidates else None
