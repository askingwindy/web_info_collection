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


def _projection(source, raw_root, end_step, ids):
    from .postprocess import effective_trajectory
    from .agent_observation import project
    from .react_session import struct_goal
    if type(end_step) is not int or not MINIMUM <= end_step <= len(source['trajectory']):
        raise ValueError('Trusted prefix requires at least six original consecutive effective actions')
    if source['boundary'].get('attempt_id') not in (None, ids['attempt_id']):
        raise ValueError('Prefix attempt differs from its sealed source attempt')
    rows = deepcopy(source['trajectory'][:end_step])
    final_id = rows[-1]['after_observation_id']
    final = source['observations'][final_id]
    state = load_json(final['state_path'])
    ob = project(state, {k: final['evidence'][k] for k in ('image', 'state', 'capture')})
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
    recount = {**source, 'task': task, 'trajectory': rows, 'terminal': terminal}
    if len(effective_trajectory(recount)) != end_step:
        raise ValueError('Prefix interval contains duplicate dispatches')
    source_receipt = {'path': str((Path(raw_root)/'raw-receipt.json').resolve()),
                      'sha256': file_sha(Path(raw_root)/'raw-receipt.json')}
    binding = {'protocol': VERSION, 'kind': 'TRUSTED_HISTORICAL_PREFIX', 'flagged': False, 'source_attempt_id': ids['attempt_id'],
        'source_interval': {'start_step': 1, 'end_step': end_step},
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
        'interval_key': object_sha256({'attempt_id': ids['attempt_id'],
            'raw_receipt': source_receipt, 'start_step': 1, 'end_step': end_step})}
    # Keep the original task and all source observations/goals. Only the
    # derivative terminal points at the historical boundary.
    return {**source, 'trajectory': rows, 'terminal': terminal, 'trusted_prefix': binding}


def project_prefix(source, raw_root, end_step, ids):
    return _projection(source, raw_root, end_step, ids)


def validate_projection(record):
    from .postprocess import session_record
    binding = record['trusted_prefix']
    verify_evidence([binding['raw_receipt'], binding['source_terminal']])
    root = Path(binding['raw_receipt']['path']).parent
    source = session_record(root, allow_unknown_for_prefix=True)
    expected = _projection(source, root, binding['source_interval']['end_step'],
                           {'attempt_id': binding['source_attempt_id']})
    if (binding != expected['trusted_prefix'] or record['task'] != expected['task']
            or record['trajectory'] != expected['trajectory'] or record['terminal'] != expected['terminal']):
        raise ValueError('Prefix projection differs from its independently rechecked source interval')
    return binding


def candidate_end(raw_root):
    """Largest historical boundary available; no unknown tail is retried."""
    from .postprocess import session_record
    source = session_record(raw_root, allow_unknown_for_prefix=True)
    return len(source['trajectory']) if len(source['trajectory']) >= MINIMUM else None


def natural_instruction(record):
    """Describe actual visible activities, never intended or excluded actions."""
    from .collect import observed_frame_description
    from .task_instruction import generated_instruction
    activities=[]
    for row in record['trajectory']:
        raw=load_json(row['raw_step']['path'])
        before=load_json(record['observations'][row['before_observation_id']]['state_path'])
        after=load_json(record['observations'][row['after_observation_id']]['state_path'])
        label=(raw.get('target_element') or {}).get('text') or (row.get('target') or {}).get('label') or ''
        action=row['action']
        if action=='type':
            activities.append('在'+('「'+label+'」' if label else '当前输入框')+'填写「'+row['arguments']['text']+'」')
        elif action=='select':activities.append('选择「'+row['arguments']['option']+'」')
        elif action=='scroll':activities.append('向'+{'down':'下','up':'上','left':'左','right':'右'}[row['arguments']['direction']]+'浏览「'+before['title']+'」的页面内容')
        elif action=='back':activities.append('返回上一个页面')
        elif action in ('click','double_click','open_url'):
            activities.append(('打开' if before['url']!=after['url'] else '操作')+('「'+label+'」' if label else '当前可见页面控件'))
        elif action=='hotkey':activities.append('使用快捷键修改当前文字选择或页面状态')
        else:activities.append('操作'+('「'+label+'」' if label else '当前可见页面控件'))
    actual=list(dict.fromkeys(activities))
    final=load_json(record['observations'][record['terminal']['final_observation_id']]['state_path'])
    result=observed_frame_description(final)
    import re
    first=load_json(record['observations'][record['trajectory'][0]['before_observation_id']]['state_path'])
    prior=set((first.get('visible_text') or '').splitlines())
    new=[line.strip() for line in (final.get('visible_text') or '').splitlines()
         if line.strip() and line not in prior and re.search(r'\d',line) and re.search(r'[\u4e00-\u9fffA-Za-z]',line)]
    if new:result+='，可见'+ '、'.join('「'+line[:160]+'」' for line in dict.fromkeys(new))
    return generated_instruction('在「'+record['task']['app_name']+'」中'+'，'.join(actual)+'，查看结束页面：'+result)


def model_context(binding):
    """Bound QC context contains no local paths or original private protocol."""
    return {'protocol':VERSION,'source_attempt_id':binding['source_attempt_id'],
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
