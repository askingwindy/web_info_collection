"""Offline whole-trajectory derivation from a saved react raw execution.

Reads the immutable raw journal (boundary, observations, trajectory, terminal,
raw receipt) and derives at most one current delivery sample per raw
execution. Deterministic template narration only — no browser, no model IO.
Failed derivations append records and never touch the raw directory.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
import platform
from urllib.parse import urlsplit

from .batch_core import file_sha, load_json
from .planning import object_sha256, verify_evidence
from .agent_controller import exclusive
from .react_session import REACT_VERSION, is_react_task, struct_goal, describe_goal, validate_task
from .react_protocol import VERSION as NATIVE_VERSION, NATIVE_VERSIONS, atomic_effect, RULE_VERSION

VERSION = 'webcollect-postprocess-4'


def _observation_state(record, observation_id):
    entry = record['observations'][observation_id]
    return load_json(entry['state_path'])


def _observation_capture(record, observation_id):
    entry = record['observations'][observation_id]
    return load_json(entry['evidence']['capture']['path'])


def session_record(raw_root, *, allow_unknown_for_prefix=False, _verification=None):
    """Load and verify the immutable raw journal of one react execution."""
    raw_root = Path(raw_root)
    boundary = load_json(raw_root / 'boundary.json')
    terminal = load_json(raw_root / 'terminal.json')
    receipt = load_json(raw_root / 'raw-receipt.json')
    task = boundary['task']
    if not is_react_task(task) or boundary['protocol'] != REACT_VERSION:
        raise ValueError('Raw journal is not a react execution')
    validate_task(task)
    files = {p.relative_to(raw_root).as_posix(): file_sha(p)
             for p in sorted(raw_root.rglob('*')) if p.is_file()}
    expected = {name: digest for name, digest in receipt['files_sha256'].items()
                if name != 'raw-receipt.json'}
    for name, digest in expected.items():
        if files.get(name) != digest:
            raise ValueError('封存原件缺失或字节改变：' + name)
    for name in ('boundary.json', 'terminal.json', 'trajectory.jsonl'):
        if name not in files or files[name] != expected.get(name):
            raise ValueError('原始执行关键文件缺失或字节改变：' + name)
    if terminal.get('unknown') and not allow_unknown_for_prefix:
        raise ValueError('UNKNOWN 原始终态不能进入交付加工；先按原账核对')
    observations = {}
    projected_observations = {}
    for path in sorted(raw_root.glob('observation-*.json')):
        if path.name.endswith('.capture.json'):
            continue
        state = load_json(path)
        n = path.stem.split('-')[1]
        image = raw_root / f'observation-{n}.png'
        capture = raw_root / f'observation-{n}.capture.json'
        html = raw_root / f'observation-{n}.html'
        for ref in (image, capture, html):
            if not ref.is_file():
                raise ValueError('观察证据缺失：' + ref.name)
        evidence = {'image': {'path': str(image.resolve()), 'sha256': file_sha(image)},
                    'capture': {'path': str(capture.resolve()), 'sha256': file_sha(capture)},
                    'state': {'path': str(path.resolve()), 'sha256': file_sha(path)},
                    'html': {'path': str(html.resolve()), 'sha256': file_sha(html)}}
        from .agent_observation import project
        # observation_id hashes the canonical three-key evidence; html stays a
        # separate reference exactly as at capture time.
        canonical = {k: evidence[k] for k in ('image', 'state', 'capture')}
        projected = project(state, canonical, extended_actions=(
            task['fragment'].get('plan_protocol') == 'webcollect-banded-conditional-plan-13'))
        if _verification is not None:
            projected_observations[projected['observation_id']] = projected
        observations[projected['observation_id']] = {
            'state_path': str(path.resolve()), 'url': state.get('url'), 'evidence': evidence}
    trajectory = []
    with (raw_root / 'trajectory.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['before_observation_id'] not in observations or row['after_observation_id'] not in observations:
                raise ValueError('轨迹动作引用的观察缺失：' + row['operation_id'])
            verify_evidence([row['dispatch']])
            trajectory.append(row)
    record = {'protocol': REACT_VERSION, 'task': task, 'boundary': boundary, 'terminal': terminal,
              'receipt': receipt, 'observations': observations, 'trajectory': trajectory,
              'goal_updates': terminal.get('goal_updates') or []}
    if _verification is not None:
        _verification.update(files=files, observations=projected_observations)
    return record


class _VerifiedSession:
    """One close-out's verified raw bytes and projections; never persisted."""

    def __init__(self, raw_root):
        self.root = Path(raw_root).resolve()
        self._verification = {}
        self._source = session_record(self.root, allow_unknown_for_prefix=True,
                                      _verification=self._verification)
        self._source_sha256 = object_sha256(self._source)
        self._prefixes = {}

    def check(self, raw_root):
        if Path(raw_root).resolve() != self.root or object_sha256(self._source) != self._source_sha256:
            raise ValueError('Verified raw execution binding changed')
        actual = {p.relative_to(self.root).as_posix(): file_sha(p)
                  for p in sorted(self.root.rglob('*')) if p.is_file()}
        if actual != self._verification['files']:
            raise ValueError('封存原件缺失或字节改变，不能复用已核验记录')
        # Raw steps may live beside raw/, so retain their independent binding.
        verify_evidence([ref for row in self._source['trajectory']
                         for ref in (row['dispatch'], row.get('raw_step')) if ref])

    def record(self, raw_root):
        self.check(raw_root)
        return deepcopy(self._source)

    def observations(self, record, observation_id=None):
        self.check(self.root)
        if record['observations'] != self._source['observations']:
            raise ValueError('Observation references differ from verified raw execution')
        projected = self._verification['observations']
        return deepcopy(projected if observation_id is None else projected[observation_id])

    def prefix(self, source, raw_root, end_step, ids, rule):
        self.check(raw_root)
        if object_sha256(source) != self._source_sha256:
            raise ValueError('Prefix source differs from verified raw execution')
        key = (rule, end_step, ids['attempt_id'])
        if key not in self._prefixes:
            from .trusted_prefix import _projection
            projected = _projection(source, raw_root, end_step, ids, rule=rule, _verified=self)
            self._prefixes[key] = (deepcopy(projected), object_sha256(projected))
        projected, digest = self._prefixes[key]
        if object_sha256(projected) != digest:
            raise ValueError('Verified prefix projection changed')
        return deepcopy(projected)


def natural_instruction(task, record, effective):
    """Describe the working goal once; retain every executed stage in evidence."""
    app = task['app_name']
    if record.get('trusted_prefix'):
        from .trusted_prefix import natural_instruction as prefix_instruction
        return prefix_instruction(record)
    actual = list(dict.fromkeys(row.get('semantic_goal') or row.get('goal') or '' for row in record['trajectory']))
    focus = (record['terminal'].get('working_goal') or '').strip() or '、'.join(g for g in actual if g)
    if focus:
        from .task_instruction import generated_instruction
        return generated_instruction(f'在「{app}」上{focus}')
    return f'在「{app}」上连续完成{effective}步真实网页操作并查看实际状态'


def completion_evidence(record):
    from .react_protocol import effect_feedback
    from .trajectory_types import classify
    from .reading_progress import ending
    terminal = record['terminal']
    final_id = terminal.get('final_observation_id') or record['trajectory'][-1]['after_observation_id']
    state = _observation_state(record, final_id)
    return {'requested_goal': struct_goal(record['task']), 'working_goal': terminal.get('working_goal'),
            'goal_updates': record['goal_updates'],
            'executed_stages': list(dict.fromkeys(r.get('semantic_goal') or r.get('goal') for r in record['trajectory'])),
            'final_observation_id': final_id, 'final_evidence': record['observations'][final_id]['evidence'],
            'visible_text': state.get('visible_text', ''),
            'dynamic_region_evidence':{oid:{'contract':__import__('webcollect.dynamic_regions',fromlist=['summary']).summary(_observation_state(record,oid)),
                'original_evidence':deepcopy(row['evidence'])} for oid,row in record['observations'].items()
                if 'dynamic_region_contract' in _observation_state(record,oid)},
            'host_stop_reason': terminal.get('stop_reason'), 'agent_summary': terminal.get('stop_summary'),
            'business_completion': 'NOT_CLAIMED',
            **({'goal_evidence':deepcopy(terminal['goal_evidence'])} if terminal.get('goal_evidence') else {}),
            **({'collection_ending':deepcopy(terminal['collection_ending'])} if terminal.get('collection_ending') else {}),
            **({'trusted_prefix':deepcopy(record['trusted_prefix'])} if record.get('trusted_prefix') else {}),
            'ending_evidence': ending(len(record['trajectory']),state),
            'actual_effects': [effect_feedback(row) for row in record['trajectory']],
            'page_hosts': {key: urlsplit(_observation_state(record,key)['url']).hostname
                           for key in record['observations']},
            'planning_intents':deepcopy(terminal.get('planning_intents',[])),
            'continuity_proofs':deepcopy(record.get('continuity_proofs',[])),
            'actual_task_types': classify(record),
            'source_metadata': deepcopy((record['task'].get('candidate_binding') or {}).get('sources', []))}


def _same_view(before, after):
    from .reading_progress import same_view
    return same_view(before,after)


def _delayed_bridge(record, previous, before_id, after_id):
    from .candidate_navigation import delayed_landing, DELAYED_PROTOCOL
    if record['task']['fragment'].get('delayed_navigation_protocol') != DELAYED_PROTOCOL:
        return None
    for proof in record['terminal'].get('delayed_navigations',[]):
        if proof['operation_id'] != previous['operation_id']:
            continue
        source = _observation_state(record, proof['source_observation_id'])
        start = _observation_state(record, proof['from_observation_id'])
        end = _observation_state(record, proof['to_observation_id'])
        operation = load_json(previous['raw_step']['path'])['operation']
        if (proof['source_observation_id'] == previous['before_observation_id']
                and _same_view(start,_observation_state(record,before_id))
                and _same_view(end,_observation_state(record,after_id))
                and delayed_landing(operation,source,start,end,same_tab=proof.get('same_tab') is True,
                    no_other_action=proof.get('no_other_action') is True,no_new_tab=proof.get('no_new_tab') is True)):
            return operation
    return None


def _scoped_continuity(record, previous, row, raw):
    """Explain only adjacent same-document drift using the next action's receipt."""
    from .action_stability import FOLLOWUP_VERSION, POST_VERSION, ACTION_SCOPED_VERSIONS, pair
    if record['task']['fragment'].get('action_stability_protocol') not in (FOLLOWUP_VERSION,POST_VERSION,*ACTION_SCOPED_VERSIONS):return False
    capture=raw.get('capture') or {}
    accepted=[a for a in capture.get('attempts',[]) if (a.get('stability') or {}).get('accepted') and (a.get('final_stability') or {}).get('accepted')]
    pair_receipt=accepted[-1] if accepted else capture
    scope=(pair_receipt.get('stability') or {}).get('action_scope')
    if not scope:
        # Capture wraps the accepted pair in its synchronized capture proof.
        scope=(pair_receipt.get('final_stability') or {}).get('action_scope')
    if not scope:return False
    before_id=previous['after_observation_id'];after_id=row['before_observation_id']
    a,b=record['observations'][before_id],record['observations'][after_id]
    try:
        proof=pair(_observation_state(record,before_id),_observation_state(record,after_id),
                   Path(a['evidence']['image']['path']).read_bytes(),Path(b['evidence']['image']['path']).read_bytes(),scope)
    except (ValueError,KeyError):return False
    if proof['accepted']:
        record.setdefault('continuity_proofs',[]).append({'previous_operation_id':previous['operation_id'],
            'next_operation_id':row['operation_id'],'before_observation_id':before_id,'after_observation_id':after_id,
            'proof':proof,'no_action_replayed':True})
    return proof['accepted']


def flow_classification(effective):
    """Classify only the effective business actions in the saved range."""
    short = 0 < effective < 5
    return short, (f'最终保存轨迹包含 {effective} 个有效业务操作，少于 5 步，自动标记为短流程。' if short else None)


def validate_effective_limit(task, count):
    """V5 freezes a ten-effective-action ceiling, including derived prefixes."""
    from .closing_policy import effective_limit
    limit=effective_limit(task)
    if limit is not None and count>limit:
        raise ValueError('V5 saved interval exceeds ten effective business actions')


def required_result_checks(terminal, task=None):
    """The same evidence gate as the online conditional-plan finish."""
    from .plan_evidence import unverified_required_checks
    if ((task or {}).get('fragment', {}).get('result_execution_policy') == 'webcollect-result-execution-1'
            and (terminal.get('goal_evidence') or {}).get('result_execution_status') == 'UNVERIFIED'):
        return [{'field': '本次输入、提交与实际结果的执行绑定', 'status': 'UNVERIFIED'}]
    if (task or {}).get('fragment', {}).get('wiki_reading_completion_protocol') == 'webcollect-wiki-reading-completion-2':
        ending = terminal.get('collection_ending') or {}
        basis = ending.get('endpoint_evidence') or {}
        objective = basis.get('session_objective_evidence') or {}
        if (ending.get('kind') == 'HOST_PLAN_ENDPOINT' and not ending.get('flagged')
                and ending.get('safe_for_pending_sample') is True
                and objective.get('status') == 'VERIFIED'
                and objective == (terminal.get('goal_evidence') or {}).get('session_objective')):
            # completion-2 owns cumulative original checks and source binding;
            # its sealed replay remains mandatory in validate_record.
            return []
    return unverified_required_checks(terminal.get('goal_evidence') or {})


def ready_requires_prefix(task, terminal):
    from .closing_policy import EFFECTIVE_VERSION
    return (task.get('fragment',{}).get('ending_policy')==EFFECTIVE_VERSION
            and terminal.get('stop_reason')=='ready' and bool(required_result_checks(terminal, task)))


def effective_trajectory(record, *, _audit_cancelled=False, _verified=None):
    """Recount native atomic dispatches from sealed evidence, never model labels.

    A gap, unknown dispatch or ineffective operation rejects the whole chain;
    it cannot be dropped to join otherwise disconnected pieces.
    """
    from .page_language import validate_range
    validate_range(record)
    if record['task']['fragment'].get('decision_protocol') not in NATIVE_VERSIONS:
        return [r for r in record['trajectory'] if r['action'] not in ('observe','inspect','wait','finish','complete')]
    rows, seen = [], {}
    for row_index,row in enumerate(record['trajectory']):
        dispatch_key = row['dispatch']['sha256']
        if dispatch_key in seen:
            if row != seen[dispatch_key]:
                raise ValueError('同一派发身份对应不同原子操作')
            continue
        seen[dispatch_key] = row
        if any(item['operation_id'] == row['operation_id'] for item in rows):
            raise ValueError('原子操作身份重复')
        raw_ref = row.get('raw_step') or {}
        verify_evidence([raw_ref])
        raw = load_json(raw_ref['path'])
        before = _observation_state(record, row['before_observation_id'])
        after = _observation_state(record, row['after_observation_id'])
        dispatch = load_json(row['dispatch']['path'])
        operation = raw.get('operation') or {}
        if (raw.get('dispatched') is not True or raw.get('action_executed') is not True
                or raw.get('postconditions_checked') is not True or raw.get('execution_error')
                or operation.get('operation_id') != row['operation_id']
                or operation.get('action_type') != row['action']
                or operation.get('arguments') != row['arguments']
                or operation.get('evidence', {}).get('state_sha256') != object_sha256(before)
                or raw.get('react', {}).get('before_observation_id') != row['before_observation_id']
                or raw.get('react', {}).get('after_observation_id') != row['after_observation_id']
                or dispatch.get('operation') != operation
                or raw.get('controller_dispatch', {}).get('sha256') != dispatch_key
                or raw.get('state') != before
                or raw.get('capture', {}).get('screenshot_sha256') != record['observations'][row['before_observation_id']]['evidence']['image']['sha256']):
            raise ValueError('原子动作缺少成功派发或同步前后证据：' + row['operation_id'])
        if row['action'] in ('wait', 'complete', 'observe', 'inspect'):
            raise ValueError('非有效操作不能进入连续动作轨迹')
        effect = atomic_effect(before, after, row['action'], row['arguments'],
                               operation.get('evidence', {}).get('anchor_element_id') or
                               operation.get('evidence', {}).get('focused_element_id'),
                               rule_version=record['task']['fragment'].get('effective_action_rule', RULE_VERSION))
        if not effect['verified']:
            raise ValueError('动作对应效果不可核验：' + row['operation_id'])
        if rows and not _same_view(_observation_state(record, rows[-1]['after_observation_id']), before) and not _delayed_bridge(record,rows[-1],rows[-1]['after_observation_id'],row['before_observation_id']) and not _scoped_continuity(record,rows[-1],row,raw):
            raise ValueError('连续轨迹存在未解释的状态缺口')
        if rows and _same_view(_observation_state(record, rows[-1]['before_observation_id']), after):
            navigation_return = (record['task']['fragment'].get('navigation_protocol') == 'observed-navigation-2'
                and row['action'] == 'back' and rows[-1]['action'] in ('click','double_click','open_url','hotkey','type','select')
                and before['url'] != after['url'])
            useful_return=False
            if record['task']['fragment'].get('reading_progress_protocol') and row_index+1 < len(record['trajectory']):
                from .reading_progress import control_return
                following=record['trajectory'][row_index+1]
                next_operation=load_json(following['raw_step']['path'])['operation']
                useful_return=(rows[-1]['action']==row['action']=='scroll'
                    and control_return(_observation_state(record, rows[-1]['before_observation_id']),before,after,next_operation))
            from .consumer_page_policy import enabled as page_policy, returned_pair
            boundary_return=page_policy(record['task']) and returned_pair(
                _observation_state(record, rows[-1]['before_observation_id']),before,after,rows[-1],row)
            if not navigation_return and not useful_return and not boundary_return:
                raise ValueError('存在两步后回到原样的无效往返')
        rows.append(row)
    if rows and record['task']['fragment'].get('navigation_protocol') == 'observed-navigation-2':
        from .candidate_navigation import verify_path
        states,operations = [],[]
        previous_id=None;previous_row=None
        for row in rows:
            before = _observation_state(record,row['before_observation_id'])
            if states:
                bridge=_delayed_bridge(record,previous_row,previous_id,row['before_observation_id']) if previous_id else None
                states.append(before);operations.append(bridge)
            else:
                states.append(before)
            states.append(_observation_state(record,row['after_observation_id']))
            operations.append(load_json(row['raw_step']['path'])['operation'])
            previous_id=row['after_observation_id'];previous_row=row
        verify_path(record['task'],states,operations)
    from .closing_policy import enabled as v2, validate_record as validate_closing
    if _audit_cancelled:
        if record['terminal'].get('actual_actions') != len(rows):
            raise ValueError('Cancelled dispatch count differs from verified effects')
    elif record.get('trusted_prefix'):
        from .trusted_prefix import validate_projection
        validate_projection(record, _verified=_verified)
    elif v2(record['task']):
        marker=validate_closing(record)
        if not marker['safe_for_pending_sample']:
            raise ValueError('V2 raw ending is pending reconciliation, not a deliverable sample')
    elif rows and record['terminal'].get('actual_actions') != len(rows):
        raise ValueError('实际派发数与有证据的原子操作数不一致，不能跳过未记录的动作')
    final_id=record['terminal'].get('final_observation_id')
    if rows and final_id and _observation_state(record,rows[-1]['after_observation_id'])['url'] != _observation_state(record,final_id)['url']:
        if not _delayed_bridge(record,rows[-1],rows[-1]['after_observation_id'],final_id):
            raise ValueError('末帧导航缺少原点击与延迟落地绑定')
    from .direct_article import verify_record
    verify_record(record, _verified=_verified)
    from .wiki_reading import verify_record as verify_wiki
    verify_wiki(record, _verified=_verified)
    validate_effective_limit(record['task'],len(rows))
    return rows


def cancelled_dispatch_audit(raw_root):
    """Account a host cancellation between fully observed actions, never deliver it.

    The original UNKNOWN remains sealed. This proof only distinguishes an
    undispatched next operation from an actually unknown browser side effect.
    """
    raw_root = Path(raw_root).resolve()
    record = session_record(raw_root, allow_unknown_for_prefix=True)
    terminal = record['terminal']; ending = terminal.get('collection_ending') or {}
    if (terminal.get('unknown') is not True or terminal.get('failure_class') != 'interrupted'
            or ending.get('reason') != '会话被取消，保留已执行内容'
            or ending.get('finish_origin') != 'host' or ending.get('unverified_tail_dispatches') != 0):
        raise ValueError('Only sealed host cancellation without an unverified tail is auditable')
    actual = {p.relative_to(raw_root).as_posix() for p in raw_root.rglob('*') if p.is_file()}
    expected = set(record['receipt']['files_sha256']) | {'raw-receipt.json'}
    if actual != expected:
        raise ValueError('Cancelled raw has unsealed additional files')
    rows = effective_trajectory(record, _audit_cancelled=True)
    if not rows or len(rows) != terminal.get('effective_steps') or len(rows) != ending.get('actual_atomic_dispatches'):
        raise ValueError('Every cancelled dispatch must have a verified atomic effect')
    intents = {str(p.resolve()) for p in raw_root.glob('*-dispatch-intent.json')}
    steps = {str(p.resolve()) for p in (raw_root.parent/'action-attempts').glob('*.json')}
    if (intents != {r['dispatch']['path'] for r in rows}
            or steps != {r['raw_step']['path'] for r in rows}
            or len(intents) != len(rows) or terminal['final_observation_id'] != rows[-1]['after_observation_id']):
        raise ValueError('Cancelled execution has an unmatched dispatch, raw step or final observation')
    attempts = [load_json(p) for p in raw_root.glob('*-business-attempt.json')]
    if (len(attempts) != ending.get('business_attempts')
            or any(a.get('outcome') != 'VERIFIED' for a in attempts)
            or sum(a.get('actual_dispatches_delta', 0) for a in attempts) != len(rows)):
        raise ValueError('Cancelled business attempts are not completely verified')
    failure_path = raw_root.parent/'failure.json'
    failure = load_json(failure_path)
    attempt_id = record['boundary'].get('attempt_id') or failure.get('attempt_id')
    if not attempt_id or failure.get('attempt_id') != attempt_id or failure.get('failure_class') != 'interrupted':
        raise ValueError('Cancelled primary failure and boundary identity differ')
    return {'schema_version':'webcollect-cancelled-dispatch-audit-1',
            'raw_receipt':{'path':str(raw_root/'raw-receipt.json'),'sha256':file_sha(raw_root/'raw-receipt.json')},
            'original_failure':{'path':str(failure_path),'sha256':file_sha(failure_path)},
            'attempt_id':attempt_id, 'verified_dispatches':len(rows),
            'dispatches':[r['dispatch'] for r in rows], 'raw_steps':[r['raw_step'] for r in rows],
            'final_observation_id':terminal['final_observation_id'],
            'source_unknown_retained':True, 'operation_unknown':False,
            'deliverable':False, 'goal_completion':'NOT_CLAIMED'}


def rejected_focus_dispatch_audit(raw_root):
    """Account one focus click from sealed rejected PNG/DOM pairs, never deliver.

    This is deliberately separate from an accepted capture or cancellation:
    the original capture rejection and UNKNOWN remain unchanged.
    """
    import base64
    from .action_stability import post_observation_scope, pair, projection, searchable
    raw_root=Path(raw_root).resolve();record=session_record(raw_root,allow_unknown_for_prefix=True)
    terminal=record['terminal'];ending=terminal.get('collection_ending') or {}
    if (terminal.get('unknown') is not True or terminal.get('failure_class')!='interrupted'
            or terminal.get('actual_actions')!=1 or terminal.get('effective_steps')!=0
            or record['trajectory'] or not ending.get('reason','').startswith('CAPTURE_AFTER_ACTION_UNVERIFIED:')):
        raise ValueError('Only one originally rejected focus dispatch is auditable')
    actual={p.relative_to(raw_root).as_posix() for p in raw_root.rglob('*') if p.is_file()}
    if actual!=set(record['receipt']['files_sha256'])|{'raw-receipt.json'}:
        raise ValueError('Rejected raw contains unsealed files')
    intents=list(raw_root.glob('*-dispatch-intent.json'));steps=list((raw_root.parent/'action-attempts').glob('*.json'))
    businesses=list(raw_root.glob('*-business-attempt.json'));rejections=list(raw_root.glob('*-capture-rejected.json'))
    if any(len(rows)!=1 for rows in (intents,steps,businesses,rejections)):
        raise ValueError('Rejected focus audit requires exactly one complete original dispatch')
    def ref(path):return {'path':str(path),'sha256':file_sha(path)}
    intent=load_json(intents[0]);step=load_json(steps[0]);business=load_json(businesses[0]);rejection=load_json(rejections[0])
    if (business.get('raw_steps')!=[ref(steps[0])] or business.get('outcome')!='EFFECT_UNKNOWN'
            or business.get('actual_dispatches_delta')!=1 or business.get('effective_steps_delta')!=0
            or step.get('controller_dispatch')!=ref(intents[0]) or step.get('operation')!=intent['operation']
            or step.get('dispatched') is not True or step.get('action_executed') is not True
            or step.get('phase')!='post_dispatch' or step.get('execution_error')
            or rejection.get('after_dispatch') is not True):
        raise ValueError('Original dispatch accounting differs')
    operation=intent['operation'];source=step['state'];node=operation.get('evidence',{}).get('anchor_element_id')
    before_id=step.get('react',{}).get('before_observation_id')
    if (operation.get('action_type')!='click' or before_id not in record['observations']
            or source!=_observation_state(record,before_id)
            or projection(source,node)['value'].get('focused') is not False
            or not searchable(projection(source,node))):
        raise ValueError('Rejected audit is only an originally observed unfocused search input')
    verify_evidence([rejection['evidence'],intent['formal_frame']])
    if Path(rejection['evidence']['path']).parent!=raw_root:
        raise ValueError('Rejected diagnostic must belong to this sealed raw')
    scope=post_observation_scope(source,operation);proofs=[]
    for attempt in load_json(rejection['evidence']['path']).get('diagnostic',{}).get('attempts',[]):
        try:
            states=[attempt[k] for k in ('snapshot_before','snapshot_after','snapshot_final')]
            png=base64.b64decode(attempt['original_png_base64'],validate=True)
            other=base64.b64decode(attempt['comparison_png_base64'],validate=True)
            checks=[pair(states[0],state,png,other,scope) for state in states[1:]]
            if all(check['accepted'] for check in checks):
                proofs.append({'attempt':attempt['attempt'],'pairs':checks})
        except (ValueError,KeyError,TypeError):continue
    if not proofs:raise ValueError('No sealed synchronous pair proves the actual focus effect')
    failure_path=raw_root.parent/'failure.json';failure=load_json(failure_path)
    if (not failure.get('attempt_id') or record['boundary'].get('attempt_id',failure['attempt_id'])!=failure['attempt_id']
            or failure.get('failure_class')!='interrupted' or 'CAPTURE_AFTER_ACTION_UNVERIFIED:' not in failure.get('error','')):
        raise ValueError('Rejected focus primary failure identity differs')
    return {'schema_version':'webcollect-rejected-focus-dispatch-audit-1','attempt_id':failure['attempt_id'],
            'raw_receipt':ref(raw_root/'raw-receipt.json'),'original_failure':ref(failure_path),
            'dispatch':ref(intents[0]),'raw_step':ref(steps[0]),'rejected_capture':rejection['evidence'],
            'proofs':proofs,'accounted_dispatches':1,'operation_unknown':False,
            'original_capture_accepted':False,'source_unknown_retained':True,
            'deliverable':False,'goal_completion':'NOT_CLAIMED'}


def terminal_outcome(task, record, final_state):
    """Describe the delivered frame; host stop and business success stay separate."""
    from .collect import observed_frame_description, visible_result_description
    description = (visible_result_description(final_state)
                   or observed_frame_description(final_state, task['instruction']))
    # Quote only observed rendered content, never a planned second stage or a
    # model finish claim. Full text/intent/stop remain in completion evidence.
    lines = list(dict.fromkeys(s.strip() for s in (final_state.get('visible_text') or '').splitlines() if s.strip()))
    from .direct_completion import enabled as direct_completion_enabled
    scoped_passage = None
    if direct_completion_enabled(task):
        from .direct_article import body
        objective = record['terminal'].get('goal_evidence', {}).get('session_objective', {})
        selected = objective.get('selected_passage') or {}
        matches = [p for p in body(final_state) if p['quote'] == selected.get('quote')]
        if objective.get('status') == 'VERIFIED' and len(matches) == 1:
            scoped_passage = matches[0]['quote']
    if scoped_passage:
        # The whole viewport (including source-code examples and navigation)
        # remains in the raw observation. The delivery narrative describes the
        # independently rechecked, currently visible reading passage only.
        description = '当前正文可见「' + scoped_passage + '」'
    title = (final_state.get('title') or '').strip().casefold()
    visible = (final_state.get('visible_text') or '').strip().casefold()
    denial = ('您的访问被阻止', '访问被拒绝', '访问受限', 'access denied', 'verify you are human',
              '请求被拦截', '请求被阻止', '无法访问此网站', '网页无法打开', '网站暂时无法访问')
    challenge = ('安全验证', '人机验证', '验证码', 'captcha')
    first_line = visible.splitlines()[0].strip() if visible else ''
    blocked = (title.startswith(denial) or first_line.startswith(denial)
               or title in challenge or first_line in challenge
               or ('samwaf' in title + ' ' + visible and any(phrase in visible for phrase in denial)))
    terminal = record['terminal']
    if record.get('trusted_prefix') and lines and not blocked:
        values=[str(v['value']) for v in final_state.get('values',[]) if v.get('value_visible') and v.get('value') not in (None,'')]
        first_state=_observation_state(record,record['trajectory'][0]['before_observation_id'])
        prior=set((first_state.get('visible_text') or '').splitlines())
        facts=list(dict.fromkeys(line.strip() for line in lines
            if line.strip() and line not in prior and re.search(r'\d',line)
            and re.search(r'[\u4e00-\u9fffA-Za-z]',line)))
        if facts:
            actual='末帧可见'+ '、'.join('「'+line[:160]+'」' for line in facts[:6])
        elif values:
            actual='末帧输入字段实际显示'+ '、'.join('「'+v+'」' for v in values)
        else:
            actual=description or '末帧保留已执行区间及其可见内容'
        # A verified historical interval is not proof that the original goal
        # completed. Keep that distinction in the customer-facing status.
        return 'controlled_exception', actual
    if task['fragment'].get('ending_policy') and not lines:
        return 'failed', description
    from .closing_policy import enabled as v2
    marker=terminal.get('collection_ending')
    if v2(task) and marker and marker.get('safe_for_pending_sample') and marker.get('flagged') and not blocked:
        return 'controlled_exception','本段异常收尾，完整目标未确认完成；'+marker['reason']+'；'+description
    if blocked or terminal.get('unknown') or terminal.get('stop_reason') in ('blocked', 'no_path'):
        # Exception eligibility must be frozen by the trusted caller. A model
        # finish summary or a WAF page cannot grant it.
        if (blocked and task['fragment'].get('allow_controlled_exception') is True
                and not terminal.get('unknown')):
            return 'controlled_exception', description
        return 'failed', description
    if terminal.get('stop_reason') not in ('ready', 'budget'):
        return 'failed', description
    if task['fragment'].get('ending_policy'):
        checks=(terminal.get('goal_evidence') or {}).get('checks') or []
        unverified=[str(c.get('field') or '未命名检查项') for c in required_result_checks(terminal, task)]
        if unverified:
            # Declared result checks that remain UNVERIFIED can never export as
            # success. PENDING auxiliary checks keep their established
            # non-blocking semantics and stay for later evidence binding work.
            return 'failed','目标声明的结果检查项未核验：'+'、'.join(unverified)+'；'+description
        verified=[c for c in checks if c.get('status')=='VERIFIED' and str(c.get('visible_text') or '').strip()]
        if verified:
            # The delivery summary quotes host-verified goal facts first,
            # never arbitrary viewport prose such as FAQ or page descriptions.
            facts='；'.join(str(c.get('field') or '已核验项')+'「'+str(c.get('observed_visible_text') or c['visible_text']).strip()[:120]+'」'
                           for c in verified[:3])
            description='已核验目标事实：'+facts+'。'+description
    return 'success', description


def terminal_judgement(completion_status, final_result):
    """Identify the visible terminal basis without repeating the whole viewport."""
    prefix = '末帧完成判定依据：' if completion_status == 'success' else '末帧状态判定依据：'
    return prefix + final_result


def planned_terminal_narrative(record, final_state, final_id):
    """Describe verified goal evidence separately from the final viewport.

    Used only for first generation of V13 samples, never historical status
    correction. Reading may have cumulative evidence outside the final frame.
    """
    evidence = record['terminal'].get('goal_evidence') or {}
    from .result_execution import completion_result_summary
    numeric = completion_result_summary(evidence, final_observation_id=final_id)
    if numeric:
        return numeric
    objective = evidence.get('session_objective') or {}
    completion = objective.get('completion') or {}
    checks = completion.get('original_checks') or []
    answers = (completion.get('answer') or {}).get('check_answers') or []
    if objective.get('status') != 'VERIFIED' or not checks or len(answers) != len(checks):
        return None
    basis = []
    final_quotes = []
    for answer in answers:
        index = answer.get('check_index')
        if type(index) is not int or not 0 <= index < len(checks):
            return None
        passages = answer.get('passages') or []
        quotes = list(dict.fromkeys(p['quote'] for p in passages if p.get('quote')))
        final_quotes.extend(p['quote'] for p in passages if p.get('observation_id') == final_id
                            and p.get('quote') and p['quote'] in final_state.get('visible_text', ''))
        field = str(checks[index].get('field') or f'第{index + 1}项')
        if quotes:
            basis.append(field + '，已观察的正文或操作目标包括' + '、'.join('「' + q + '」' for q in quotes[:2]))
        elif answer.get('operation_ids'):
            basis.append(field + '，已有对应实际操作记录')
        else:
            return None
    title = str(final_state.get('title') or '任务页面')
    last = record['trajectory'][-1]
    if last['action'] == 'back':
        final_result = '完成任务内查阅并返回后，当前页面为「' + title + '」。'
    elif final_quotes:
        final_result = '最终页面「' + title + '」可见' + '、'.join('「' + q + '」' for q in list(dict.fromkeys(final_quotes))[:2]) + '。'
    else:
        final_result = '阅读结束时停留在「' + title + '」；原问题的正文依据保留在先前已观察页面中。'
    return {'final_result': final_result, 'completion_judgement': '原任务各项依据：' + '；'.join(basis) + '。',
            'basis': answers, 'is_ai_review': False}


def delivery_expectation(expected, action, element, label):
    """Keep navigation URLs in the raw trace, not in customer-facing prose."""
    if re.search(r'https?://|%[0-9A-Fa-f]{2}', expected):
        if action == 'back':
            return '预期返回已访问的页面'
        if (element and element.get('native_role') == 'a' and label
                and not re.search(r'https?://|%[0-9A-Fa-f]{2}', label)):
            return '预期打开「' + label + '」页面'
        return '预期打开所选页面'
    return expected if re.search(r'[\u4e00-\u9fff]', expected) else '预期状态：「' + expected + '」'


def _write_delivery_bytes(path, data):
    """Create-or-identical binary write; a failed derivation's own bytes may
    be rewritten only when they are exactly the bytes about to be written."""
    path = Path(path)
    if path.exists():
        if path.read_bytes() == data:
            return
        raise ValueError('交付文件已存在且内容不同，不能覆盖：' + path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def derive(task, record, delivery, ids, manifest, *, resume=False):
    """Build the complete delivery sample from the raw execution; no IO models."""
    try:
        trajectory = effective_trajectory(record)
    except (ValueError, KeyError, TypeError) as error:
        return {'status': 'processing_failed', 'error': str(error), 'effective_steps': 0}
    return _derive_verified(task, record, trajectory, delivery, ids, manifest, resume=resume)


def _derive_verified(task, record, trajectory, delivery, ids, manifest, *, resume=False):
    """Internal derivation from the caller's already verified effective rows."""
    from .collect import chinese_ratio, describe_change, observed_frame_description
    from .task_contract import narrative_evidence, canonical_sha
    from .validate import validate_sample
    from .action_normalization import normalize_delivery_step
    from .browser import POINTER
    from .validate import CONTROL
    delivery = Path(delivery)
    native = task['fragment'].get('decision_protocol') in NATIVE_VERSIONS
    if not trajectory:
        return {'status': 'no_actions', 'effective_steps': 0}
    effective = len(trajectory)
    validate_effective_limit(task,effective)
    short, reason = flow_classification(effective)
    length_qualified = effective > 0
    result = {'status': 'length_unqualified' if not length_qualified else 'deriving',
              'effective_steps': effective, 'short_flow': short,
              'short_flow_reason': reason if short else None,
              'length_qualified': length_qualified}
    if not length_qualified:
        return result
    final_id = record['terminal'].get('final_observation_id') or trajectory[-1]['after_observation_id']
    final_state = _observation_state(record, final_id)
    completion_status, final_result = terminal_outcome(task, record, final_state) if native else ('success', None)
    # New capture narration reuses deterministic, pre-action facts. The
    # separately callable correction API never re-runs this status derivation.
    new_narration = task['fragment'].get('plan_protocol') == 'webcollect-banded-conditional-plan-13'
    terminal_narrative = None
    if new_narration and completion_status == 'success':
        terminal_narrative = planned_terminal_narrative(record, final_state, final_id)
        if terminal_narrative:
            final_result = terminal_narrative['final_result']
    if completion_status == 'failed':
        return {**result, 'status': 'terminal_failed', 'completion_status': 'failed',
                'final_result': final_result}
    # Require a fresh destination on the first derivation. A recorded failed
    # derivation may continue in place: every write below refuses differing
    # bytes, so the same sealed raw can only reproduce identical delivery.
    if native and delivery.exists() and not resume:
        raise FileExistsError('后加工必须使用新目录，不能覆盖原交付或失败派生：' + str(delivery))
    (delivery / 'images').mkdir(parents=True, exist_ok=True)
    (delivery / 'ui_tree').mkdir(parents=True, exist_ok=True)
    instruction = natural_instruction(task, record, effective)
    steps = []
    ratios = []
    narrative_rows = []
    for index, row in enumerate(trajectory, 1):
        before = _observation_state(record, row['before_observation_id'])
        after = _observation_state(record, row['after_observation_id'])
        raw_step = load_json(row['raw_step']['path']) if row.get('raw_step') else {}
        element = raw_step.get('target_element')
        op = {'action_type': row['action'], 'arguments': deepcopy(row['arguments']),
              'goal': row['goal'], 'expected': row['expected'],
              'selector': (row.get('target') or {}).get('selector'),
              'evidence': {'target_label': (row.get('target') or {}).get('label')}}
        step_result = describe_change(before, after, op, element)
        observed_result, narrative = narrative_evidence(step_result, before, after, op)
        if observed_result is None:
            result.update(status='processing_failed',
                          error='NARRATIVE_EVIDENCE_UNSUPPORTED', step_id=index)
            return result
        # Delivery frames bind the pre-action observation: the state each
        # recorded action actually acted upon (audit_capture semantics).
        image_path = f'images/step_{index:03}.png'
        _write_delivery_bytes(delivery / image_path,
            Path(record['observations'][row['before_observation_id']]['evidence']['image']['path']).read_bytes())
        ratios.append(chinese_ratio(before.get('visible_text', '')))
        write_json_file(delivery / f'ui_tree/step_{index:03}.json',
                        {'image_path': image_path, 'screen_resolution': before['screen_resolution'],
                         'elements': before['elements']})
        arguments = row['arguments']
        action = {'action_type': row['action'],
                  'target_element_id': element['element_id'] if element else '',
                  'target_text': (element['text'] if element else
                                  (op['evidence']['target_label'] or '')),
                  'coordinate': [arguments['x'], arguments['y']] if row['action'] in POINTER else [],
                  'input_text': (arguments['text'] if row['action'] == 'type' else
                                 '+'.join(arguments['keys']) if row['action'] == 'hotkey' else ''),
                  'precondition': f'当前页面为「{before["title"]}」' + (
                      f'，可见「{op["evidence"]["target_label"]}」目标控件'
                      if element and op['evidence'].get('target_label') else ''),
                  'expected_result': delivery_expectation(row['expected'], row['action'], element,
                                                          op['evidence']['target_label'])}
        if element:
            action.update(target_bbox=element['bbox'], target_control_type=element['element_type'])
        step = {'step_id': index, 'image_path': image_path,
                'ui_tree_path': f'ui_tree/step_{index:03}.json',
                'page_name': '网页「' + before['title'] + '」',
                'user_goal': row.get('semantic_goal') or row['goal'],
                'action': action,
                'tool_call': {'tool_name': row['action'], 'call_id': f'{ids["sample_id"]}_{index:03}',
                              'arguments': deepcopy(arguments),
                              'timestamp': raw_step.get('started_at') or datetime.now().isoformat(),
                              'context': 'Web / ' + (urlsplit(before['url']).hostname if task['fragment'].get('navigation_protocol') == 'observed-navigation-2' else task['app_name'])},
                'tool_result': {'status': 'success', 'return_value': {}, 'error': ''},
                'next_step_rationale': row.get('semantic_goal') or row['goal'],
                'step_result': observed_result, 'exception_evidence': []}
        step = normalize_delivery_step(step, platform.system())
        if new_narration:
            from .annotation_corrections import step_narratives
            wording = step_narratives(row, before, element)
            # These strings were emitted by the existing visual planning call
            # before execution; expected is still the separate machine predicate.
            expected_prose = row.get('semantic_expected_result') or wording.get('expected_result')
            rationale = row.get('semantic_rationale') or wording.get('next_step_rationale')
            if expected_prose:
                step['action']['expected_result'] = expected_prose
            if rationale:
                step['next_step_rationale'] = rationale
        steps.append(step)
        narrative_rows.append({'step_id': index, 'source_operation_id': row['operation_id'],
                               'before_observation_id': row['before_observation_id'],
                               'after_observation_id': row['after_observation_id'],
                               'narrative': narrative})
    result.update(minimum_chinese_character_ratio=min(ratios), chinese_ratio_diagnostic_only=True,
                  language_policy='page-control-language-consistency-1', language_review='REVIEW_REQUIRED')
    # The finish tool refreshed the terminal observation inside the session.
    final_id = record['terminal'].get('final_observation_id') or trajectory[-1]['after_observation_id']
    if final_id not in record['observations']:
        final_id = trajectory[-1]['after_observation_id']
    final_state = _observation_state(record, final_id)
    final_description = final_result if native else observed_frame_description(final_state, instruction)
    # Byte-stable completion timestamp: derived from the raw terminal capture
    # itself so re-derivation reproduces identical delivery artifacts.
    final_capture = _observation_capture(record, final_id)
    final_ns = (final_capture.get('attempts') or [{}])[-1].get('ended_ns')
    from datetime import datetime, timezone
    final_timestamp = (datetime.fromtimestamp(final_ns / 1e9, timezone.utc).isoformat()
                       if isinstance(final_ns, int) else terminal_fallback_timestamp(record))
    final_image = f'images/step_{effective + 1:03}.png'
    _write_delivery_bytes(delivery / final_image,
        Path(record['observations'][final_id]['evidence']['image']['path']).read_bytes())
    write_json_file(delivery / f'ui_tree/step_{effective + 1:03}.json',
                    {'image_path': final_image, 'screen_resolution': final_state['screen_resolution'],
                     'elements': final_state['elements']})
    final_goal = '确认本段结束页面，' + final_description
    complete_action = {'action_type': 'complete', 'target_element_id': '', 'target_text': '',
                       'coordinate': [], 'input_text': '',
                       'precondition': f'当前页面为「{final_state["title"]}」',
                       'expected_result': final_description}
    steps.append({'step_id': effective + 1, 'image_path': final_image,
                  'ui_tree_path': f'ui_tree/step_{effective + 1:03}.json',
                  'page_name': '网页「' + final_state['title'] + '」',
                  'user_goal': final_goal, 'action': complete_action,
                  'tool_call': {'tool_name': 'complete', 'call_id': f'{ids["sample_id"]}_{effective + 1:03}',
                                'arguments': {'status': 'success'},
                                'timestamp': final_timestamp,
                                'context': 'Web / ' + (urlsplit(final_state['url']).hostname if task['fragment'].get('navigation_protocol') == 'observed-navigation-2' else task['app_name'])},
                  'tool_result': {'status': 'success', 'return_value': {}, 'error': ''},
                  'next_step_rationale': final_description,
                  'step_result': '最终页面已确认，' + final_goal,
                  'exception_evidence': []})
    if record.get('trusted_prefix'):
        steps[-1]['exception_evidence']=['原始执行未确认完整目标完成；本样本仅保留连续可信操作区间，按可控异常交付。']
    if record['terminal'].get('collection_ending'):
        marker=record['terminal']['collection_ending']
        if marker['flagged']:
            steps[-1]['exception_evidence']=["本段按原始异常收尾依据结束；目标未确认完成，尾部原件已单独保留。",
                f"业务动作尝试{marker['business_attempts']}次，真实原子派发{marker['actual_atomic_dispatches']}次，已验证有效步{effective}，未验证尾步{marker['unverified_tail_dispatches']}。"]
            steps[-1]['step_result']='异常收尾后保留可信末态；'+final_goal
    for position in range(len(steps) - 1):
        steps[position]['tool_result']['return_value']['screen_changed'] = \
            file_sha(delivery / steps[position]['image_path']) != file_sha(delivery / steps[position + 1]['image_path'])
    stop_summary = (record['terminal'].get('stop_summary') or '').strip()
    final_result = final_result if native else stop_summary or task['final_result']
    completion_judgement = terminal_judgement(completion_status, final_result) if native else final_result
    if terminal_narrative:
        completion_judgement = terminal_narrative['completion_judgement']
        steps[-1]['next_step_rationale'] = completion_judgement
        steps[-1]['action']['expected_result'] = '预期结束页面保留本次操作的最终状态，可据已保存的任务证据核对完成情况。'
    from .trajectory_types import classify
    actual_types=classify(record) if task['fragment'].get('planning_intent_protocol') else {'task_type':task['task_type'],'status':'LEGACY'}
    result['actual_task_types']=actual_types
    if not actual_types['task_type']:
        return {**result,'status':'task_type_pending','error':'No evidence-backed customer task_type'}
    annotation = {'sample_id': ids['sample_id'], 'task_instruction': instruction,
        'task_type': actual_types['task_type'], 'terminal_type': 'Web',
        'device_info': {'device_model': '', 'os_name': 'macOS' if platform.system() == 'Darwin' else platform.system(),
                        'os_version': (platform.mac_ver()[0] or platform.release())
                        if platform.system() == 'Darwin' else platform.release(),
                        'screen_resolution': final_state['screen_resolution']},
        'app_info': {'app_name': task['app_name'], 'app_version': '',
                     'environment': '真实网站 / 隔离浏览器上下文', 'ui_language': 'zh'},
        'risk_level': 'normal',
        'trajectory_source': {'source_type': 'agent', 'data_type': 'webcollect_agent_v1',
                              'action_space': 'unified_gui_v4'},
        'steps': steps, 'final_state_image': final_image, 'final_result': final_result,
        'completion_status': completion_status, 'completion_judgement': completion_judgement}
    if short:
        annotation['short_flow'] = True
        annotation['short_flow_reason'] = reason
    write_json_file(delivery / 'annotation.json', annotation)
    report = validate_sample(delivery, 'delivery', manifest)
    if not report['structural_pass']:
        result.update(status='processing_failed',
                      error='结构检查不通过：' + json.dumps(report['issues'], ensure_ascii=False)[:500])
        return result
    result.update(status='derived', structural_report=report,
                  source_mapping=narrative_rows,
                  instruction=instruction, final_result=final_result)
    if new_narration:
        result['annotation_rule_version'] = 'webcollect-annotation-corrections-1'
        result['terminal_narrative_basis'] = terminal_narrative
    return result


def terminal_fallback_timestamp(record):
    from .collect import now as collect_now
    return collect_now()


def _write_terminal_step(evidence, record, ids):
    """Project the finish tool's terminal observation as the complete raw step."""
    trajectory = record['trajectory']
    final_id = record['terminal'].get('final_observation_id') or trajectory[-1]['after_observation_id']
    if final_id not in record['observations']:
        final_id = trajectory[-1]['after_observation_id']
    state = _observation_state(record, final_id)
    capture = _observation_capture(record, final_id)
    ended_ns = (capture.get('attempts') or [{}])[-1].get('ended_ns')
    from datetime import datetime, timezone
    now = (datetime.fromtimestamp(ended_ns / 1e9, timezone.utc).isoformat()
           if isinstance(ended_ns, int) else terminal_fallback_timestamp(record))
    number = len(trajectory) + 1
    raw = {'step_id': number, 'state': state, 'capture': capture,
           'operation': {'operation_id': 'react-finish', 'subgoal_id': 'react',
                         'action_type': 'complete', 'goal': '结束并确认本段实际末状态',
                         'rationale': record['terminal'].get('stop_summary') or 'react finish',
                         'expected': '保存本段真实末状态截图', 'arguments': {'status': 'success'}},
           'target_element': None, 'started_at': now, 'ended_at': now,
           'executed_action': {'tool_name': 'complete', 'arguments': {'status': 'success'}},
           'completion_trigger': 'react_finish',
           'react': {'stop_reason': record['terminal'].get('stop_reason'),
                     'final_observation_id': final_id}}
    write_json_file(evidence / f'step_{number:03}.json', raw)
    return raw


def process(evidence_root, delivery_root, ids, manifest, *, derivation=None, validators=(), prefix_end_step=None, prefix_rule=None, _verified=None):
    """Derive, validate, record and seal; reprocessing appends, never re-collects.

    `validators` are deterministic delivery checks (capture audit, producer
    duplicate index) run after derivation and before the sample is sealed;
    their failures record a delivery_rejected derivation without touching raw.
    """
    evidence_root = Path(evidence_root)
    raw_root = evidence_root / 'raw'
    verified = _verified if _verified is not None else _VerifiedSession(raw_root)
    record = verified.record(raw_root)
    if record['terminal'].get('unknown') and prefix_end_step is None:
        raise ValueError('UNKNOWN 原始终态不能进入交付加工；先按原账核对')
    if prefix_end_step is not None:
        from .trusted_prefix import project_prefix, VERSION as PREFIX_RULE_V1
        record = project_prefix(record, raw_root, prefix_end_step, ids,
                                rule=prefix_rule or PREFIX_RULE_V1, _verified=verified)
    task = record['task']
    if prefix_end_step is not None:
        validate_effective_limit(task,len(record['trajectory']))
    derivations_path = evidence_root / 'derivations.jsonl'
    prior = []
    if derivations_path.is_file():
        prior = [json.loads(line) for line in derivations_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if prefix_end_step is not None and any(row.get('status') == 'derived_saved' for row in prior):
        saved = load_json(evidence_root / 'saved_sample.json')
        binding = saved.get('raw_execution', {}).get('trusted_prefix')
        actual = {p.relative_to(delivery_root).as_posix(): file_sha(p) for p in Path(delivery_root).rglob('*') if p.is_file()}
        captures={p.relative_to(evidence_root).as_posix():file_sha(p) for p in evidence_root.rglob('*') if p.is_file() and not post_seal_name(p.name)}
        if (binding != record['trusted_prefix'] or saved.get('sample_id') != ids['sample_id']
                or actual != saved.get('sample_files_sha256') or captures!=saved.get('capture_files_sha256')):
            raise ValueError('Existing prefix differs from immutable interval or saved sample')
        return {'schema_version': VERSION, 'status': 'derived_saved', 'idempotent_reuse': True,
                'effective_steps': prefix_end_step, 'saved_sample': str((evidence_root/'saved_sample.json').resolve()),
                'trusted_prefix': binding, 'browser_calls': 0, 'model_calls': 0}
    if any(row.get('status') == 'derived_saved' for row in prior):
        raise ValueError('本原始执行已有当前有效交付版本；本轮一条原始执行最多一个有效交付样本')
    version = (derivation or len(prior) + 1)
    projection_root=evidence_root/f'trusted-prefix-{version:02}' if prefix_end_step is not None else evidence_root
    prefix_projection=None
    browser_calls = 0
    model_calls = 0
    try:
        # The same canonical, dispatch-deduplicated list drives annotation,
        # terminal complete numbering, capture summaries and sealed receipts.
        # Raw journal bytes and their original order remain unchanged.
        if prefix_end_step is not None:
            from .trusted_prefix import validate_projection
            # Projection already checked this exact interval's atomic effects.
            # Recheck its bound bytes and result, without rebuilding the source.
            validate_projection(record, _verified=verified)
            trajectory = record['trajectory']
        else:
            trajectory = effective_trajectory(record, _verified=verified)
        record = {**record, 'trajectory': trajectory}
        derived = _derive_verified(task, record, trajectory, delivery_root, ids, manifest, resume=bool(prior))
    except Exception as error:  # noqa: BLE001 - recorded verbatim, raw stays intact
        failure = {'schema_version': VERSION, 'derivation': version, 'status': 'processing_failed',
                   'error_type': type(error).__name__, 'error': str(error),
                   'browser_calls': browser_calls, 'model_calls': model_calls}
        exclusive(evidence_root / f'derived-failed-{version:02}.json', failure)
        _append_derivation(derivations_path, {**failure, 'record_ref':
                        {'path': str((evidence_root / f'derived-failed-{version:02}.json').resolve()),
                         'sha256': file_sha(evidence_root / f'derived-failed-{version:02}.json')}})
        return failure
    if derived['status'] != 'derived':
        row = {'schema_version': VERSION, 'derivation': version, 'status': derived['status'],
               'effective_steps': derived.get('effective_steps'),
               'short_flow': derived.get('short_flow'), 'browser_calls': 0, 'model_calls': 0}
        if derived['status'] == 'processing_failed':
            exclusive(evidence_root / f'derived-failed-{version:02}.json', derived)
            row['record_ref'] = {'path': str((evidence_root / f'derived-failed-{version:02}.json').resolve()),
                                 'sha256': file_sha(evidence_root / f'derived-failed-{version:02}.json')}
        _append_derivation(derivations_path, row)
        return row
    try:
        # Success path: project raw steps (actions already written live by the
        # session; the terminal complete record is projected here), identity and
        # the sealed delivery receipt.
        verified.check(raw_root)
        from .closing_policy import enabled as v2
        projection_root.mkdir(parents=True, exist_ok=True)
        if prefix_end_step is not None:
            prefix_projection=exclusive(evidence_root/f'trusted-prefix-projection-{version:02}.json',
                {'protocol':record['trusted_prefix']['protocol'],'directory':projection_root.name,'binding':record['trusted_prefix']})
        if v2(task) or prefix_end_step is not None:
            # Project verified prefix copies only. Failed/unverified tail files stay
            # in action-attempts and remain bound by the raw attempt journal.
            for number,row in enumerate(record['trajectory'],1):
                _write_delivery_bytes(projection_root/f'step_{number:03}.json',
                    Path(row['raw_step']['path']).read_bytes())
        final_raw = _write_terminal_step(projection_root, record, ids)
        # The capture audit re-derives the per-step target ground truth from the
        # same raw steps and compares it to this manifest; write it from those
        # identical sources so the delivered sample carries the original truth.
        ground_truth = []
        for number in range(1, final_raw['step_id'] + 1):
            step_path = projection_root / f'step_{number:03}.json'
            if not step_path.exists():
                continue
            step_raw = load_json(step_path)
            target = step_raw.get('target_element')
            if target:
                ground_truth.append({'step_id': step_raw['step_id'], 'element_id': target['element_id'],
                                     'text': target['text'], 'bbox': target['bbox']})
        write_json_file(projection_root / 'ground_truth.json', ground_truth)
        validation_errors = []
        for validate in validators:
            validation_errors.extend(validate(delivery_root) or [])
        if validation_errors:
            row = {'schema_version': VERSION, 'derivation': version, 'status': 'delivery_rejected',
                   'effective_steps': derived['effective_steps'],
                   'errors': validation_errors, 'browser_calls': 0, 'model_calls': 0}
            exclusive(evidence_root / f'derived-failed-{version:02}.json', row)
            row = {**row, 'record_ref': {'path': str((evidence_root / f'derived-failed-{version:02}.json').resolve()),
                                         'sha256': file_sha(evidence_root / f'derived-failed-{version:02}.json')}}
            _append_derivation(derivations_path, row)
            return row
        ground_truth = []
        for index, row in enumerate(record['trajectory'], 1):
            raw = load_json(row['raw_step']['path'])
            if raw.get('target_element'):
                target = raw['target_element']
                ground_truth.append({'step_id': index, 'element_id': target['element_id'],
                                     'text': target['text'], 'bbox': target['bbox']})
        write_json_file(projection_root / 'ground_truth.json', ground_truth)
        language = {key: derived[key] for key in ('minimum_chinese_character_ratio',
            'chinese_ratio_diagnostic_only', 'language_policy', 'language_review')}
        write_json_file(evidence_root / 'capture_summary.json',
            {'snapshot_source': 'browser_dom', 'capture_count': len(record['trajectory']) + 1,
             **language,
             'human_review': 'pending', 'agent_visual_review': 'pending',
             'task_id': task['task_id'], 'protocol': REACT_VERSION,
             'preparation_policy': 'content-preparation-v1', 'preparation_actions': 0,
             'preparation_scrolls': 0})
        write_json_file(evidence_root / 'task_contract.json',
            {'schema_version': 'webcollect-task-contract-evidence-1',
             'task_id': task['task_id'], 'task_version': task['task_version'],
             'task_sha256': object_sha256({k: v for k, v in task.items() if not k.startswith('_')}),
             'machine_status': 'PASS', 'semantic_status': 'REVIEW_REQUIRED',
             'business_completion': 'NOT_CLAIMED', 'fragment': task['fragment'],
             'review_binding': {'annotation_sha256': file_sha(delivery_root / 'annotation.json')}})
        if task.get('pilot_identity') is not None:
            from .production_identity import actual_proof
            raws = [load_json(row['raw_step']['path']) for row in record['trajectory']] + [final_raw]
            write_json_file(evidence_root / 'pilot_identity.json',
                            {**actual_proof(task, raws),
                             'annotation_sha256': file_sha(delivery_root / 'annotation.json')})
        derived_record = {'schema_version': VERSION, 'derivation': version, 'status': 'derived_saved',
            **language,
            'effective_steps': derived['effective_steps'], 'short_flow': derived.get('short_flow'),
            'short_flow_reason': derived.get('short_flow_reason'),
            'instruction': derived['instruction'], 'final_result': derived['final_result'],
            'stop_reason': record['terminal'].get('stop_reason'),
            'source_mapping': derived['source_mapping'],
            'structural_report': {'structural_pass': derived['structural_report']['structural_pass'],
                                  'rule_version': derived['structural_report']['rule_version']},
            'browser_calls': 0, 'model_calls': 0}
        write_json_file(evidence_root / 'completion-evidence.json', completion_evidence(record))
        derived_ref = exclusive(evidence_root / 'derived.json', derived_record)
        sample_files = {p.relative_to(delivery_root).as_posix(): file_sha(p)
                        for p in sorted(delivery_root.rglob('*')) if p.is_file()}
        # The append-only derivation ledger and the attempt close-out feedback
        # receipts (canonical and every versioned append) are written after the
        # seal by design; the frozen capture hash never covers them.
        capture_files = {p.relative_to(evidence_root).as_posix(): file_sha(p)
                         for p in sorted(evidence_root.rglob('*')) if p.is_file()
                         and not post_seal_name(p.name)}
        saved = {'attempt_id': ids.get('attempt_id'), 'sample_id': ids['sample_id'],
                 'sample_files_sha256': sample_files, 'capture_files_sha256': capture_files,
                 'semantic_review': 'REVIEW_REQUIRED',
                 'raw_execution': {'protocol': REACT_VERSION,
                                   **({'trusted_prefix':deepcopy(record['trusted_prefix'])} if record.get('trusted_prefix') else {}),
                                   **({'goal_evidence':deepcopy(record['terminal']['goal_evidence'])} if record['terminal'].get('goal_evidence') else {}),
                                   **({'collection_ending':deepcopy(record['terminal']['collection_ending'])} if record['terminal'].get('collection_ending') else {}),
                                   **({'stop_details':record['terminal']['stop_details']} if 'stop_details' in record['terminal'] else {}),
                                   'receipt': record['receipt']['terminal'],
                                   'stop_reason': record['terminal'].get('stop_reason'),
                                   'effective_steps': derived['effective_steps'],
                                   'not_a_delivery_sample_by_itself': True},
                 'derivation': {'version': version, 'record': derived_ref,
                                **({'prefix_projection':prefix_projection} if prefix_projection else {}),
                                'source_mapping_sha256': object_sha256(derived['source_mapping'])}}
        verified.check(raw_root)
        write_json_file(evidence_root / 'saved_sample.json', saved)
        _append_derivation(derivations_path, {'schema_version': VERSION, 'derivation': version,
            'status': 'derived_saved', 'effective_steps': derived['effective_steps'],
            'saved_sample': {'path': str((evidence_root / 'saved_sample.json').resolve()),
                             'sha256': file_sha(evidence_root / 'saved_sample.json')},
            'record_ref': derived_ref})
        return {'schema_version': VERSION, 'derivation': version, 'status': 'derived_saved',
                **language,
                'effective_steps': derived['effective_steps'], 'short_flow': derived.get('short_flow'),
                'stop_reason': record['terminal'].get('stop_reason'),
                **({'trusted_prefix':deepcopy(record['trusted_prefix'])} if record.get('trusted_prefix') else {}),
                'browser_calls': 0, 'model_calls': 0,
                'saved_sample': str((evidence_root / 'saved_sample.json').resolve())}
    except Exception as error:  # noqa: BLE001 - recorded verbatim, raw stays intact
        # The seal (projection, validators, identity proof, receipts) is an
        # engineering processing stage: its failures append a derivation row
        # instead of escaping, so the attempt settles recoverably and the
        # sealed raw keeps every original byte.
        failure = {'schema_version': VERSION, 'derivation': version, 'status': 'processing_failed',
                   'error_type': type(error).__name__, 'error': str(error), 'stage': 'seal',
                   'effective_steps': derived['effective_steps'],
                   'browser_calls': 0, 'model_calls': 0}
        exclusive(evidence_root / f'derived-failed-{version:02}.json', failure)
        row = {**failure, 'record_ref': {'path': str((evidence_root / f'derived-failed-{version:02}.json').resolve()),
                                         'sha256': file_sha(evidence_root / f'derived-failed-{version:02}.json')}}
        _append_derivation(derivations_path, row)
        return row


def _append_derivation(path, row):
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')


def post_seal_name(name):
    """Post-seal close-out receipts never belong to the frozen capture hash.

    Covers the canonical historical feedback names and every versioned
    appended receipt (same prefix, attempt/content digest suffix).
    """
    return (name in ('saved_sample.json', 'context_cleanup_error.json', 'derivations.jsonl')
            or name.startswith('planning-feedback-'))


def write_json_file(path, value):
    """Create-or-identical rewrite: a sealed receipt never covers a different
    body; re-derivation of the same unsealed version may rewrite equal bytes."""
    path = Path(path)
    if path.exists():
        import json as _json
        try:
            if _json.loads(path.read_text(encoding='utf-8')) == value:
                return
        except (ValueError, OSError):
            pass
        raise ValueError('交付文件已存在且内容不同，不能覆盖：' + path.name)
    from .storage import write_json
    write_json(path, value)


def revise(evidence_root, revision_root, ids, manifest, *, reason, fix_version):
    """Derive a pending revision into a fresh, isolated location from sealed raw.

    The original effective result and its QC remain authoritative. This receipt
    does not activate a replacement or reuse the original review for new bytes.
    """
    if not reason or not fix_version:
        raise ValueError('Revision requires reason and repair version')
    evidence_root, revision_root = Path(evidence_root).resolve(), Path(revision_root).absolute()
    if any(p.is_symlink() for p in (revision_root, *revision_root.parents)):
        raise ValueError('Revision destination cannot use symlinks')
    if revision_root.is_relative_to(evidence_root.parent.parent) or evidence_root.is_relative_to(revision_root):
        raise ValueError('Revision must be outside the original dataset')
    original_ref = {'path': str(evidence_root / 'saved_sample.json'), 'sha256': file_sha(evidence_root / 'saved_sample.json')}
    original = load_json(original_ref['path'])
    if original['sample_id'] != ids['sample_id'] or original.get('attempt_id') != ids.get('attempt_id'):
        raise ValueError('Revision identity differs from original receipt')
    for name, digest in original['capture_files_sha256'].items():
        path = evidence_root / name
        if Path(name).is_absolute() or not path.resolve().is_relative_to(evidence_root) or path.is_symlink() or file_sha(path) != digest:
            raise ValueError('Original sealed capture changed')
    source_sample = evidence_root.parent.parent / 'samples' / ids['sample_id']
    for name, digest in original['sample_files_sha256'].items():
        path = source_sample / name
        if Path(name).is_absolute() or not path.resolve().is_relative_to(source_sample) or path.is_symlink() or file_sha(path) != digest:
            raise ValueError('Original sealed delivery changed')
    record = session_record(evidence_root / 'raw')
    record = {**record, 'trajectory': effective_trajectory(record)}
    revision_root.mkdir(parents=True, exist_ok=False)
    delivery = revision_root / 'samples' / ids['sample_id']
    derived = derive(record['task'], record, delivery, ids, manifest)
    completion_ref = exclusive(revision_root / 'completion-evidence.json', completion_evidence(record))
    receipt = {'schema_version': VERSION, 'status': 'revision_pending_review' if derived['status'] == 'derived' else derived['status'],
               'reason': reason, 'fix_version': fix_version, 'original_save_receipt': original_ref,
               'raw_receipt': {'path': str(evidence_root / 'raw/raw-receipt.json'), 'sha256': file_sha(evidence_root / 'raw/raw-receipt.json')},
               'sample_id': ids['sample_id'], 'attempt_id': ids.get('attempt_id'), 'manifest': manifest,
               'effective_result': 'original_unchanged', 'quality_review': 'REVIEW_REQUIRED',
               'browser_calls': 0, 'model_calls': 0, 'completion_evidence': completion_ref,
               'derived': derived, 'revision_files_sha256': {p.relative_to(revision_root).as_posix(): file_sha(p) for p in sorted(revision_root.rglob('*')) if p.is_file()}}
    return {**receipt, 'receipt': exclusive(revision_root / 'revision.json', receipt)}
