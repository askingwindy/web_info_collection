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
    """Describe actual visible activities, never intended or excluded actions."""
    from .task_instruction import generated_instruction
    activities=[]
    for row in record['trajectory']:
        raw=load_json(row['raw_step']['path'])
        before=load_json(record['observations'][row['before_observation_id']]['state_path'])
        after=load_json(record['observations'][row['after_observation_id']]['state_path'])
        label=(raw.get('target_element') or {}).get('text') or (row.get('target') or {}).get('label') or ''
        action=row['action']
        if action=='type':
            node=(row.get('target') or {}).get('control_id')
            value=next((v.get('value') for v in after.get('values',[]) if v.get('element_id')==node and v.get('value_visible')),None)
            activities.append('在'+('「'+label+'」' if label else '当前输入框')+'键入「'+row['arguments']['text']+'」'
                + ('，字段实际显示「'+str(value)+'」' if value is not None else ''))
        elif action=='select':activities.append('选择「'+row['arguments']['option']+'」')
        elif action=='scroll':activities.append('向'+{'down':'下','up':'上','left':'左','right':'右'}[row['arguments']['direction']]+'浏览「'+before['title']+'」的页面内容')
        elif action=='back':activities.append('返回上一个页面')
        elif action in ('click','double_click','open_url'):
            activities.append(('打开' if before['url']!=after['url'] else '操作')+('「'+label+'」' if label else '当前可见页面控件'))
        elif action=='hotkey':activities.append('使用快捷键修改当前文字选择或页面状态')
        else:activities.append('操作'+('「'+label+'」' if label else '当前可见页面控件'))
    actual=list(dict.fromkeys(activities))
    final=load_json(record['observations'][record['terminal']['final_observation_id']]['state_path'])
    final_values=[str(v['value']) for v in final.get('values',[]) if v.get('value_visible') and v.get('value') not in (None,'')]
    result=('输入字段实际显示'+ '、'.join('「'+v+'」' for v in final_values)) if final_values else '保留末帧所示已执行片段，原目标完成未确认'
    import re
    first=load_json(record['observations'][record['trajectory'][0]['before_observation_id']]['state_path'])
    prior=set((first.get('visible_text') or '').splitlines())
    new=[line.strip() for line in (final.get('visible_text') or '').splitlines()
         if line.strip() and line not in prior and re.search(r'\d',line) and re.search(r'[\u4e00-\u9fffA-Za-z]',line)]
    if new:result+='，可见'+ '、'.join('「'+line[:160]+'」' for line in dict.fromkeys(new))
    return generated_instruction('在「'+record['task']['app_name']+'」中'+'，'.join(actual)+'，查看结束页面：'+result)


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
