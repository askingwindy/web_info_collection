"""Goal-completion attempt ending and evidence-bound closure.

The raw attempt journal includes zero-dispatch and unverified tails. Only a
continuous verified prefix with a proved harmless tail can be a marked sample.
The single current rule: the original goal is actually completed, at least
MINIMUM effective business actions ran, evidence holds, and no related effect
is unresolved. There is no cumulative step ceiling.
"""
from .batch_core import load_json
from .planning import verify_evidence, object_sha256
from .plan_protocol import ENDING_POLICY, PLAN_WAIT_EXECUTION_POLICY
from .reading_progress import same_view

MINIMUM = 5
PROMPT = ('首轮优先把自由目标设计为可用5–8个必要有效动作的完整自然路径，再冻结目标和checks；自然必要路径可以超过8步。'
          '自由目标必须依据首帧可见功能选择单一、具体、结果可核验的完整目标；提交前逐步确认路径可达、终态可证。'
          '固定requested_goal不得缩小或替换，按原目标规划全部必要动作；只有少于5步或无法完成才如实stop。'
          '目标冻结后只重规划剩余必要动作，不设首轮或累计最大步数。全部必要结果有证据且实际至少5步才能形成候选；'
          '完成即结束，实际超过8步不因长度截断或拒绝，也不为凑步添加动作。'
          '阶段完成、可信片段、short_flow或controlled_exception都不是合格结果。无法完成只保留内部原始失败记录。'
          'observe/inspect/wait/finish不算有效业务动作；UNKNOWN保留原件，不重发、不拼接、不声称成功。')


def enabled(task):
    return task.get('fragment', {}).get('ending_policy') == ENDING_POLICY


def completed_goal_only(task):
    """The current ending saves only a complete actual path of >=5 steps."""
    return enabled(task)


def initial_plan_maximum(task):
    """5–8 initial actions are preferred but no hard path maximum applies."""
    return None


def attempt_limit(task, band=None):
    """No cumulative attempt ceiling; only an explicit action budget may bound."""
    budget = task.get('fragment', {}).get('budgets', {}).get('max_actions')
    return budget


def system_prompt(base, task=None):
    start = base.index('通常争取至少五个真实有效操作。')
    end = base.index('\n只引用当前观察', start)
    return base[:start] + PROMPT + base[end:]


def _extended(record):
    """Replay projection must match the session's plan-gated action space."""
    return bool((record.get('task') or {}).get('fragment', {}).get('plan_protocol'))


def state(record, oid):
    return load_json(record['observations'][oid]['state_path'])


def no_effect_proven(raw, observations, *, action_scoped=False):
    """Prove an omitted dispatch harmless using its original before/after states.

    A definite outcome label alone is insufficient. Values and business elements
    must be unchanged; action-scoped text/geometry equality cannot erase inputs.
    Observation values may be raw states or sealed observation rows.
    """
    react = raw.get('react', {})
    if (raw.get('unknown') is True or react.get('unknown') is True
            or raw.get('dispatched') is not True or raw.get('action_executed') is not True
            or react.get('zero_effect') is not True
            or react.get('effect_evidence', {}).get('verified') is True
            or react.get('after_observation_id') not in observations):
        return False
    before = raw.get('state'); after = observations[react['after_observation_id']]
    if 'state_path' in after: after = load_json(after['state_path'])
    elif 'evidence' in after: after = load_json(after['evidence']['state']['path'])
    if not isinstance(before, dict) or not before.get('document_identity'):
        return False
    return (before.get('document_identity') == after.get('document_identity')
            and same_view(before, after))


def validate_plan_page_bindings(record):
    """Replay plan-local page bindings from sealed model-visible registries."""
    from .plan_evidence import PLAN_EXECUTION_POLICY, bind_check_pages
    if record['task']['fragment'].get('plan_execution_policy') != PLAN_EXECUTION_POLICY: return
    from pathlib import Path
    root = Path(record['receipt']['boundary']['path']).parent
    sealed = record['receipt']['files_sha256']; known = {}
    for name in sorted(sealed):
        if not name.endswith(('-conditional-plan.json', '-conditional-plan-revision.json')): continue
        verify_evidence([{'path': str(root / name), 'sha256': sealed[name]}])
        event = load_json(root / name); reference = event.get('page_registry_source') or {}
        source = Path(reference.get('path', ''))
        if source.parent != root or sealed.get(source.name) != reference.get('sha256'):
            raise ValueError('Plan page registry source is outside the sealed original attempt')
        verify_evidence([reference]); prompt = load_json(source).get('prompt') or {}
        registered = event.get('registered_pages')
        if registered is None or prompt.get('registered_pages') != registered:
            raise ValueError('Plan page registry differs from its original model-visible prompt')
        binding = bind_check_pages(event['plan'], registered)
        if event.get('page_binding') != binding:
            raise ValueError('Plan page binding differs from original checks and registered pages')
        for key, url in binding['pages'].items():
            if key in known and known[key] != url:
                raise ValueError('Replanning reused an original page ID for a different URL')
            known[key] = url


def verified_wait_plan_effect(record, effect_name, event, step, position, *, plan_name):
    """Replay a zero-business wait only from its sealed dispatch/result."""
    from .plan_protocol import PLAN_PROTOCOL
    if record['task'].get('fragment', {}).get('plan_protocol') != PLAN_PROTOCOL: return None
    actual = event.get('actual') or {}; tool = actual.get('tool_result') or {}; data = tool.get('data') or {}
    if (step.get('action') != 'wait' or actual.get('actual_effective_delta') != 0
            or event.get('established') is not True or event.get('literal_expected_established') is not True
            or event.get('expected') != step.get('expected') or tool.get('status') != 'ok'
            or data.get('wait_executed') is not True or data.get('effective_steps_delta') != 0
            or data.get('actual_actions_delta') != 0): return None
    from pathlib import Path
    from .agent_observation import project
    from .banded_plan import proves
    root = Path(record['receipt']['boundary']['path']).parent; sealed = record['receipt']['files_sha256']
    def original(name):
        verify_evidence([{'path': str(root / name), 'sha256': sealed[name]}])
        return load_json(root / name)
    original(effect_name)
    hosts = [name for name in sorted(sealed) if plan_name < name < effect_name and name.endswith('-host-plan-step.json')]
    if not hosts: return None
    host_name = hosts[-1]; host = original(host_name)
    if host.get('position') != position or host.get('step') != step: return None
    results = [name for name in sorted(sealed) if host_name < name < effect_name and name.endswith('-wait-result.json')]
    if len(results) != 1: return None
    result_name = results[0]; result = original(result_name); ref = result.get('dispatch') or {}; dispatch_path = Path(ref.get('path', ''))
    if (dispatch_path.parent != root or sealed.get(dispatch_path.name) != ref.get('sha256')
            or not host_name < dispatch_path.name < result_name): return None
    dispatch = original(dispatch_path.name)
    expected = step['expected'].get('text') or ('核验预期条件：' + step['expected']['kind'])
    before_id = result.get('before_observation_id'); after_id = result.get('after_observation_id')
    boundary = record['receipt']['boundary']
    if (dispatch.get('kind') != 'wait-dispatch' or dispatch.get('action') != 'wait'
            or dispatch.get('arguments') != {'duration_ms': step.get('duration_ms')}
            or dispatch.get('purpose') != step.get('purpose') or dispatch.get('expected') != expected
            or dispatch.get('effective_step_delta') != 0 or result.get('effective_step_delta') != 0
            or before_id != host.get('bound_observation_id') or before_id != dispatch.get('before_observation_id')
            or after_id != actual.get('observation_id') or after_id != tool.get('observation_id')
            or any(row.get('boundary') != boundary for row in (host, dispatch, result, event))
            or before_id not in record['observations'] or after_id not in record['observations']): return None
    for key, oid in (('before_evidence', before_id), ('after_evidence', after_id)):
        evidence = {k: v for k, v in record['observations'][oid]['evidence'].items() if k != 'html'}
        if result.get(key) != evidence: return None
        verify_evidence(list(evidence.values()))
    ob = project(state(record, after_id), result['after_evidence'], extended_actions=_extended(record))
    if not proves(step['expected'], ob, state(record, before_id), numeric=True): return None
    return {'policy': PLAN_WAIT_EXECUTION_POLICY, 'plan_step': position,
            'dispatch': ref, 'result': {'path': str(root / result_name), 'sha256': sealed[result_name]},
            'before_observation_id': before_id, 'after_observation_id': after_id,
            'effective_step_delta': 0, 'actual_actions_delta': 0}


def validate_reading_completion(record, basis):
    """Recompute the flag's early-end coverage from its sealed plan and facts."""
    from .wiki_reading import enabled as wiki
    if wiki(record['task']): return  # Explicit original checks, not optional route coverage.
    from .plan_evidence import READING_COMPLETION_POLICY, facts, remaining_plan_coverage
    if record['task']['fragment'].get('reading_completion_policy') != READING_COMPLETION_POLICY: return
    from pathlib import Path
    from types import SimpleNamespace
    from .agent_observation import project
    from .session_core import struct_goal
    receipt = basis.get('reading_plan_completion') or {}
    if receipt.get('policy') != READING_COMPLETION_POLICY:
        raise ValueError('Reading endpoint is missing frozen remaining-plan completion receipt')
    root = Path(record['receipt']['boundary']['path']).parent
    sealed = record['receipt']['files_sha256']
    plans = sorted(name for name in sealed if name.endswith(('-conditional-plan.json', '-conditional-plan-revision.json')))
    if not plans: raise ValueError('Reading endpoint has no sealed source plan')
    loaded = []
    for key, expected_name, expected_kind in (('original_plan', plans[0], 'conditional-plan'),
                                               ('current_plan', plans[-1], None)):
        ref = receipt.get(key) or {}; path = Path(ref.get('path', ''))
        if path.parent != root or path.name != expected_name or sealed.get(path.name) != ref.get('sha256'):
            raise ValueError('Reading completion plan reference is outside the sealed original route')
        verify_evidence([ref]); event = load_json(path)
        if expected_kind is not None and event.get('kind') != expected_kind:
            raise ValueError('Reading completion original-plan kind mismatch')
        loaded.append(event)
    original, current = loaded; plan = current['plan']; position = receipt.get('position')
    from .plan_evidence import PLAN_EXECUTION_POLICY
    execution_policy = record['task']['fragment'].get('plan_execution_policy') == PLAN_EXECUTION_POLICY
    if execution_policy: validate_plan_page_bindings(record)
    if (receipt.get('original_plan_sha256') != object_sha256(original['plan'])
            or receipt.get('current_plan_sha256') != object_sha256(plan)
            or type(position) is not int or not 0 <= position <= len(plan['steps'])):
        raise ValueError('Reading completion plan hash or remaining position mismatch')
    # A supplied position cannot silently discard unexecuted plan slots.
    effects = []
    after_ids = {r['after_observation_id'] for r in record['trajectory']}
    for name in sorted(sealed):
        if name <= plans[-1] or not name.endswith('-plan-effect.json'): continue
        event = load_json(root / name); actual = event.get('actual') or {}
        index = actual.get('position')
        if actual.get('actual_effective_delta') != 1:
            if (type(index) is int and 0 <= index < len(plan['steps'])
                    and verified_wait_plan_effect(record, name, event, plan['steps'][index], index, plan_name=plans[-1])):
                effects.append(index)
            continue
        if (type(index) is not int or not 0 <= index < len(plan['steps'])
                or event.get('expected') != plan['steps'][index]['expected']
                or actual.get('observation_id') not in after_ids):
            raise ValueError('Reading completed-step evidence differs from the sealed plan')
        if execution_policy:
            verify_evidence([{'path': str(root / name), 'sha256': sealed[name]}])
            if event.get('established') is not True:
                continue
            proof = event.get('execution_proof')
            late = event.get('late_observation')
            if late:
                if late.get('plan_sha256') != object_sha256(plan) or late.get('plan') != receipt['current_plan']:
                    raise ValueError('Late plan effect belongs to a different original plan')
                matches = [row for row in record['trajectory'] if row['operation_id'] == late.get('operation_id')]
                oid = late.get('observation_id')
                if (len(matches) != 1 or oid not in record['observations']
                        or matches[0]['raw_step'] != late.get('raw_step')
                        or matches[0]['after_observation_id'] != late.get('action_after_observation_id')
                        or matches[0]['after_observation_id'] != actual.get('observation_id')
                        or late.get('evidence') != {key: value for key, value in record['observations'][oid]['evidence'].items() if key != 'html'}):
                    raise ValueError('Late plan effect lost its original action or synchronized observation')
                late_observations = {key: project(state(record, key), {k: value['evidence'][k] for k in ('image', 'state', 'capture')},
                    extended_actions=_extended(record))
                                     for key, value in record['observations'].items()}
                for key, observation in late_observations.items():
                    observation['html'] = Path(record['observations'][key]['evidence']['html']['path']).read_text()
                late_session = SimpleNamespace(task=record['task'], trajectory=record['trajectory'],
                    observation_records=late_observations, current=late_observations[oid],
                    business_attempt_refs=(record['terminal'].get('collection_ending') or {}).get('attempt_refs', []),
                    requested_goal=struct_goal(record['task']), working_goal=record['terminal'].get('working_goal'),
        attempt_id=record['boundary'].get('attempt_id'), result_completion=sealed_result_completion(record))
                from .banded_plan import Controller
                controller = Controller(); controller.plan = plan; controller.frozen_plan = original['plan']
                visual_ref = late.get('visual_confirmation')
                if visual_ref:
                    visual_path = Path(visual_ref['path'])
                    if visual_path.parent != root or sealed.get(visual_path.name) != visual_ref['sha256']:
                        raise ValueError('Late visual proof is outside the sealed attempt')
                    verify_evidence([visual_ref]); visual = load_json(visual_path)
                    if (visual.get('kind') != 'model-visual-confirmation' or visual.get('predicate') != event['expected']
                            or visual.get('observation_id') != oid or visual.get('image') != late_session.current['evidence']['image']):
                        raise ValueError('Late visual proof differs from its predicate or image')
                    decision = visual.get('decision_event'); verify_evidence([decision])
                    branch = load_json(decision['path'])
                    if branch.get('response', {}).get('choice') != 'visual_yes':
                        raise ValueError('Late visual proof lacks its original visual confirmation decision')
                    controller.visual_confirmations[controller.visual_key(event['expected'], late_session)] = visual_ref
                if not controller.proved(event['expected'], late_session):
                    raise ValueError('Late synchronized observation does not establish the original predicate')
            elif proof is not None:
                from .plan_execution import step_execution_proof
                matches = [row for row in record['trajectory'] if row['operation_id'] == proof.get('operation_id')]
                if len(matches) != 1: raise ValueError('Plan execution proof lacks one original effective operation')
                row = matches[0]
                replay = step_execution_proof(record['task'], plan['steps'][index], row,
                    state(record, row['before_observation_id']), state(record, row['after_observation_id']),
                    target_id=proof.get('source_node'))
                if replay is None or replay != proof:
                    raise ValueError('Plan execution proof differs from original navigation and atomic effect')
            elif event.get('literal_expected_established') is not True:
                raise ValueError('Completed plan slot lacks literal predicate or original execution proof')
        effects.append(index)
    if effects != list(range(position)):
        raise ValueError('Reading remaining-plan position skips unexecuted or unresolved actions')
    observations = {}
    for oid, row in record['observations'].items():
        observations[oid] = project(state(record, oid), {k: row['evidence'][k] for k in ('image', 'state', 'capture')},
                    extended_actions=_extended(record))
    session = SimpleNamespace(task=record['task'], trajectory=record['trajectory'], observation_records=observations,
        business_attempt_refs=(record['terminal'].get('collection_ending') or {}).get('attempt_refs', []),
        requested_goal=struct_goal(record['task']), working_goal=record['terminal'].get('working_goal'),
        attempt_id=record['boundary'].get('attempt_id'), result_completion=sealed_result_completion(record))
    evidence = facts(session, original['plan'], page_urls=original.get('check_page_urls', {}),
                   page_binding=original.get('page_binding') if execution_policy else None)
    expected = remaining_plan_coverage(session, plan, position, evidence)
    if expected != receipt.get('coverage') or expected['status'] != 'COVERED':
        raise ValueError('Reading remaining purposes are not covered by sealed body goal facts')
    return receipt


def sealed_result_completion(record):
    """Return only an original finish-result decision inside this raw seal."""
    from pathlib import Path
    reference = (record['terminal'].get('goal_evidence') or {}).get('result_completion')
    if not reference:
        return None
    root = Path(record['receipt']['boundary']['path']).parent
    path = Path(reference.get('path', ''))
    if (path.parent != root
            or record['receipt']['files_sha256'].get(path.name) != reference.get('sha256')):
        raise ValueError('Result completion decision is outside the sealed attempt')
    verify_evidence([reference])
    event = load_json(path)
    if (event.get('boundary') != record['receipt']['boundary']
            or event.get('response', {}).get('attempt_id') != record['boundary']['attempt_id']):
        raise ValueError('Result completion decision belongs to a different original attempt')
    return reference


def validate_result_completion(record):
    """Recompute the result gate from the sealed original plan and raws."""
    from .result_execution import RESULT_EXECUTION_POLICY
    from .result_completion import enabled as explicit_result_completion
    if (record['task'].get('fragment', {}).get('result_execution_policy') != RESULT_EXECUTION_POLICY
            and not explicit_result_completion(record['task'])):
        return
    from pathlib import Path
    from types import SimpleNamespace
    from .agent_observation import project
    from .session_core import struct_goal
    from .plan_evidence import facts, unverified_required_checks
    root = Path(record['receipt']['boundary']['path']).parent
    sealed = record['receipt']['files_sha256']
    plans = sorted(name for name in sealed if name.endswith('-conditional-plan.json'))
    if not plans:
        if record['terminal'].get('goal_evidence'):
            raise ValueError('Result evidence has no sealed original plan')
        return
    path = root / plans[0]; verify_evidence([{'path': str(path), 'sha256': sealed[path.name]}])
    original = load_json(path)
    observations = {oid: project(state(record, oid), {k: row['evidence'][k] for k in ('image', 'state', 'capture')},
                    extended_actions=_extended(record))
                  for oid, row in record['observations'].items()}
    marker = record['terminal'].get('collection_ending') or {}
    for ref in marker.get('attempt_refs', []):
        verify_evidence([ref])
        for raw in load_json(ref['path']).get('raw_steps', []): verify_evidence([raw])
    session = SimpleNamespace(task=record['task'], trajectory=record['trajectory'], observation_records=observations,
        business_attempt_refs=marker.get('attempt_refs', []), requested_goal=struct_goal(record['task']),
        working_goal=record['terminal'].get('working_goal'),
        attempt_id=record['boundary'].get('attempt_id'), result_completion=sealed_result_completion(record))
    stored = record['terminal'].get('goal_evidence') or {}
    actual = facts(session, original['plan'], page_urls=original.get('check_page_urls', {}),
        objective_evidence=stored.get('session_objective'), page_binding=original.get('page_binding'))
    if actual != {k: v for k, v in stored.items() if k != 'session_objective'}:
        raise ValueError('Result completion facts differ from sealed input, submit and result observations')
    if marker.get('kind') == 'HOST_PLAN_ENDPOINT' and unverified_required_checks(actual):
        raise ValueError('Host result endpoint is missing required executed result evidence')


def validate_record(record):
    """Recompute tail accounting from immutable attempt/raw references."""
    from .plan_protocol import PLAN_PROTOCOL
    marker = record['terminal'].get('collection_ending')
    policy = (record['task'].get('fragment', {}) or {}).get('ending_policy')
    if not enabled(record['task']) or not marker or marker.get('protocol') != policy:
        raise ValueError('Missing closure binding')
    if ((record['task'].get('fragment', {}) or {}).get('collection_strategy') or {}).get('id') == 'screenshot_plan' \
            or marker.get('kind') == 'AGENT_COMPLETE_VERIFIED':
        # 策略 2 owns its ending semantics: no plan pages/result-completion
        # policies apply; the verified completion receipt is replayed instead.
        from .screenshot_plan import validate_ending_marker
        validate_ending_marker(record)
    validate_plan_page_bindings(record)
    validate_result_completion(record)
    band = marker.get('attempt_band')
    limit = attempt_limit(record['task'], band)
    if marker.get('attempt_limit') != limit or marker.get('attempt_band') != band:
        raise ValueError('Closure attempt budget differs from its frozen task/band')
    if marker.get('flagged'):
        raise ValueError('Exceptional closure is raw-only and cannot become a formal sample')
    attempts = []; raws = []; raw_refs = []
    for ref in marker['attempt_refs']:
        verify_evidence([ref]); attempt = load_json(ref['path'])
        if attempt.get('kind') != 'business-attempt':
            raise ValueError('Not an original business-attempt event')
        attempts.append(attempt)
        for raw_ref in attempt.get('raw_steps', []):
            verify_evidence([raw_ref]); raws.append(load_json(raw_ref['path'])); raw_refs.append(raw_ref)
    if ([a['number'] for a in attempts] != list(range(1, len(attempts) + 1))
            or (limit is not None and len(attempts) > limit)
            or marker['business_attempts'] != len(attempts)):
        raise ValueError('Business-attempt count changed')
    kind = marker.get('kind')
    dispatched = [r for r in raws if r.get('dispatched') is True]
    verified = [r for r in dispatched if r.get('action_executed') is True
              and r.get('postconditions_checked') is True and r.get('react', {}).get('effect_evidence', {}).get('verified') is True]
    verified_refs = [ref for ref, raw in zip(raw_refs, raws) if raw in verified]
    if (len({ref['path'] for ref in raw_refs}) != len(raw_refs)
            or sorted((r['path'], r['sha256']) for r in verified_refs)
               != sorted((r['raw_step']['path'], r['raw_step']['sha256']) for r in record['trajectory'])):
        raise ValueError('Attempt journal does not account for the exact verified prefix')
    for attempt in attempts:
        original = [load_json(ref['path']) for ref in attempt.get('raw_steps', [])]
        if (attempt['actual_dispatches_delta'] != sum(r.get('dispatched') is True for r in original)
                or attempt['effective_steps_delta'] != sum(r in verified for r in original)):
            raise ValueError('Per-attempt accounting differs from original raw')
    if (len(dispatched) != marker['actual_atomic_dispatches']
            or len(dispatched) != record['terminal']['actual_actions']
            or len(verified) != len(record['trajectory'])
            or marker['verified_effective_steps'] != len(verified)
            or marker['unverified_tail_dispatches'] != len(dispatched) - len(verified)):
        raise ValueError('Dispatch/effective/tail accounting differs from original raw')
    prefix = record['trajectory']; final = record['terminal'].get('final_observation_id')
    safe = bool(prefix and final in record['observations'] and not record['terminal'].get('unknown')
              and (state(record, final).get('visible_text') or '').strip())
    if safe and len(dispatched) > len(verified):
        tail = [r for r in dispatched if r not in verified]
        screenshot_tail = ((record['task'].get('fragment', {}) or {}).get('collection_strategy') or {}).get('id') == 'screenshot_plan'
        if screenshot_tail:
            from .screenshot_plan import tail_effect_observed as _observed
            from types import SimpleNamespace
            session = SimpleNamespace(observation_records=record['observations'],
                                    trajectory=record['trajectory'],
                                    current={'observation_id': marker.get('final_observation_id')} if marker.get('final_observation_id') in record['observations'] else None)
            safe = all(no_effect_proven(raw, record['observations']) or _observed(raw, session) for raw in tail)
        else:
            safe = all(no_effect_proven(raw, record['observations']) for raw in tail)
    if safe:
        from .action_stability import action_scoped_view_stable
        if record['task']['fragment'].get('action_stability_protocol'):
            # Offline mirror of the online action-scoped ending check: same
            # document/scroll and retained visible reading material; unrelated
            # decorative image/overlay membership changes are not endpoint
            # changes.
            safe = action_scoped_view_stable(state(record, prefix[-1]['after_observation_id']), state(record, final))
        else:
            safe = same_view(state(record, prefix[-1]['after_observation_id']), state(record, final))
        bridge = marker.get('direct_terminal_bridge')
        if bridge:
            from .direct_completion import enabled as explicit, bridge_evidence
            if not explicit(record['task']) or len(dispatched) != len(verified) or marker.get('kind') != 'HOST_PLAN_ENDPOINT':
                raise ValueError('Direct terminal bridge cannot cover unknown/tail/other closure')
            actual = bridge_evidence(record['task'], record['observations'][prefix[-1]['after_observation_id']]['evidence'],
                record['observations'][final]['evidence'], target_ids=[(r.get('target') or {}).get('control_id') for r in prefix])
            if actual != bridge: raise ValueError('Direct terminal bridge differs from original frames')
            safe = safe or actual['proof']['accepted'] is True
    if marker['safe_for_pending_sample'] and not safe:
        raise ValueError('Closure cannot prove a safe continuous prefix and terminal')
    if marker.get('kind') == 'HOST_BOUNDARY_RETURN':
        from .consumer_page_policy import ending_evidence
        actual = ending_evidence(record['task'], prefix, {oid: state(record, oid) for oid in record['observations']}, final)
        if (not actual or actual != marker.get('boundary_return_evidence')
                or marker.get('plan_protocol') != PLAN_PROTOCOL
                or marker.get('plan_protocol') != record['task']['fragment'].get('plan_protocol') or not safe):
            raise ValueError('Boundary return lacks two original effective actions and a sealed safe return')
    if marker.get('kind') == 'HOST_PLAN_ENDPOINT':
        if (marker.get('plan_protocol') != record['task']['fragment'].get('plan_protocol')
                or marker.get('plan_protocol') != PLAN_PROTOCOL):
            raise ValueError('Host endpoint is not bound to the original plan task')
        basis = marker.get('endpoint_evidence') or {}
        if basis.get('source') != 'host_result_completion':
            validate_reading_completion(record, basis)
        final_evidence = record['observations'][final]['evidence']
        if basis.get('image') != final_evidence['image']:
            raise ValueError('Endpoint image differs from sealed final observation')
        from .wiki_reading import enabled as wiki, replay as replay_wiki
        from .plan_protocol import PLAN_PROTOCOL
        ordinary_wiki = wiki(record['task'])
        if ordinary_wiki:
            actual = replay_wiki(record, basis.get('session_objective_evidence'), basis=basis)
        elif basis.get('source') != 'host_result_completion':
            from types import SimpleNamespace
            from pathlib import Path
            from .agent_observation import project
            from .session_objective import progress
            observations = {}
            for oid, row in record['observations'].items():
                ob = project(state(record, oid), {k: row['evidence'][k] for k in ('image', 'state', 'capture')},
                    extended_actions=_extended(record))
                ob['html'] = Path(row['evidence']['html']['path']).read_text()
                observations[oid] = ob
            session = SimpleNamespace(task=record['task'], trajectory=record['trajectory'],
                observation_records=observations, current=observations[final],
                business_attempt_refs=marker.get('attempt_refs', []))
            # The live session exposes its structured goal to the evidence
            # machinery; the offline replay must reconstruct the same surface,
            # or objective requirements derived from the goal description
            # (downward reading) would silently differ between both sides.
            from .session_core import struct_goal
            session.requested_goal = struct_goal(record['task'])
            from .goal_evidence import contract_for
            if contract_for(session.task):
                session.attempt_id = record['boundary']['attempt_id']
                session.binding = record['receipt']['boundary']
                session.answer_citation = (basis.get('session_objective_evidence') or {}).get('citation_event')
                from .direct_completion import enabled as explicit
                if explicit(session.task):
                    plans = sorted(Path(session.binding['path']).parent.glob('*-conditional-plan.json'))
                    from types import SimpleNamespace
                    session.plan_controller = SimpleNamespace(frozen_plan=load_json(plans[0])['plan'])
                    session.reading_completion = ((basis.get('session_objective_evidence') or {}).get('completion') or {}).get('decision')
                    if session.reading_completion:
                        p = Path(session.reading_completion['path'])
                        if p.parent != Path(session.binding['path']).parent or record['receipt']['files_sha256'].get(p.name) != session.reading_completion['sha256']:
                            raise ValueError('Direct completion is outside the sealed attempt')
                if session.answer_citation:
                    path = Path(session.answer_citation['path'])
                    if (path.parent != Path(session.binding['path']).parent or
                            record['receipt']['files_sha256'].get(path.name) != session.answer_citation['sha256']):
                        raise ValueError('Reading citation is outside this sealed attempt')
            actual = progress(session, basis.get('initial_observation_id'))
            if actual['required'] and (actual['status'] != 'VERIFIED' or actual != basis.get('session_objective_evidence')):
                raise ValueError('Explicit session objective is not established by the sealed original trace')
        if ordinary_wiki:
            if basis.get('source') not in ('host_wiki_reading_completion', 'host_rendered_state'):
                raise ValueError('Unknown Wiki explicit completion evidence source')
        elif basis.get('source') == 'host_result_completion':
            from .result_completion import enabled as result_completion_enabled
            from .plan_evidence import unverified_required_checks
            reference = sealed_result_completion(record)
            goal = record['terminal'].get('goal_evidence') or {}
            if (not result_completion_enabled(record['task']) or not reference
                    or basis.get('result_completion') != reference
                    or (basis.get('finish_route') or {}).get('completion_origin') != 'agent_finish_result'
                    or goal.get('business_goal_status') != 'VERIFIED'
                    or unverified_required_checks(goal)):
                raise ValueError('Result endpoint lacks sealed original-check completion evidence')
        elif basis.get('source') == 'host_rendered_state':
            from .agent_observation import project
            from .banded_plan import proves
            observation = project(state(record, final), {k: final_evidence[k] for k in ('image', 'state', 'capture')},
                    extended_actions=_extended(record))
            if not proves(basis['predicate'], observation):
                raise ValueError('Sealed host endpoint predicate is not independently established')
        elif basis.get('source') == 'host_goal_evidence':
            from .goal_evidence import contract_for
            if (not contract_for(record['task']) or basis.get('predicate', {}).get('kind') != 'goal_evidence'
                    or not actual['required'] or actual['status'] != 'VERIFIED'):
                raise ValueError('Host goal endpoint requires the sealed explicit evidence contract')
        elif basis.get('source') == 'model_visual':
            proof = basis.get('visual_confirmation'); verify_evidence([proof]); visual = load_json(proof['path'])
            decision = visual.get('decision_event'); verify_evidence([decision]); branch = load_json(decision['path'])
            if (visual.get('kind') != 'model-visual-confirmation' or visual.get('predicate') != basis.get('predicate')
                    or visual.get('image', {}).get('sha256') != final_evidence['image']['sha256']
                    or visual.get('document_identity') != state(record, final).get('document_identity')
                    or branch.get('kind') != 'plan-branch' or branch['response'].get('choice') != 'visual_yes'
                    or branch['response'].get('visual_evidence') != visual.get('interpretation')
                    or branch['response'].get('observation_id') != visual.get('observation_id')
                    or visual.get('boundary') != branch.get('boundary')):
                raise ValueError('Visual endpoint lacks its original image/ordinary decision binding')
        else: raise ValueError('Unknown host endpoint evidence source')
    return {**marker, 'safe_for_pending_sample': bool(marker['safe_for_pending_sample'] and safe)}


def annotation_errors(annotation):
    marker = annotation.get('steps', [{}])[-1].get('tool_result', {}).get('return_value', {}).get('collection_ending')
    if not marker: return []
    policy = marker.get('protocol')
    effective = sum(s.get('action', {}).get('action_type') not in ('wait', 'complete') for s in annotation['steps'])
    errors = []
    if (policy != ENDING_POLICY or marker.get('verified_effective_steps') != effective
            or type(marker.get('business_attempts')) is not int or marker['business_attempts'] < 0
            or marker.get('attempt_limit') is not None
            or marker.get('actual_atomic_dispatches', -1) != effective + marker.get('unverified_tail_dispatches', -1)
            or marker.get('safe_for_pending_sample') is not True or marker.get('external_effect_unknown') is not False
            or not marker.get('final_observation_id') or not marker.get('final_evidence')
            or marker.get('finish_count', 0) != 1):
        errors.append('Ending counts, finish, final evidence or safe-state binding is invalid')
    if marker.get('flagged'):
        errors.append('Exceptional ending cannot be a formal annotation')
    if marker.get('goal_completion') not in ('NOT_CLAIMED', 'AGENT_REPORTED_VISIBLE_GOAL'):
        errors.append('Closure cannot invent business success')
    kind = marker.get('kind'); attempts = marker.get('business_attempts', -1)
    ready = ('VISIBLE_GOAL_REPORTED', 'HOST_PLAN_ENDPOINT', 'HOST_BOUNDARY_RETURN')
    if ((annotation.get('task') or {}).get('fragment', {}).get('collection_strategy') or {}).get('id') == 'screenshot_plan' \
            or marker.get('collection_strategy', {}).get('id') == 'screenshot_plan':
        ready = ready + ('AGENT_COMPLETE_VERIFIED',)
    if (marker.get('flagged') is not (kind not in ready)
            or marker.get('finish_origin') not in ('host', 'agent')
            or marker.get('finish_is_business_action') is not False or marker.get('wait_is_business_action') is not False
            or len(marker.get('attempt_refs', [])) != attempts
            or (marker.get('flagged') and (kind not in ('MODEL_BUDGET_LIMIT', 'KNOWN_NO_EFFECT', 'NOT_DISPATCHED', 'AGENT_STOP', 'HOST_INTERRUPTED')
                or attempts < 1))
            or (marker.get('unverified_tail_dispatches', 0) > 0 and kind != 'KNOWN_NO_EFFECT')):
        errors.append('Exceptional closure kind/range/attempt references are inconsistent')
    if kind == 'HOST_BOUNDARY_RETURN':
        from .consumer_page_policy import PAGE_POLICY, PLAN_PROTOCOL as CURRENT_PLAN
        proof = marker.get('boundary_return_evidence') or {}
        if (marker.get('plan_protocol') != CURRENT_PLAN
                or proof.get('policy') != PAGE_POLICY
                or marker.get('goal_completion') != 'NOT_CLAIMED' or marker.get('finish_origin') != 'host'
                or effective < 2 or marker.get('unverified_tail_dispatches') != 0):
            errors.append('Boundary return must preserve two verified operations without a login/download success claim')
    if kind == 'HOST_PLAN_ENDPOINT' and (marker.get('plan_protocol') is None
            or marker.get('finish_origin') != 'host' or marker.get('goal_completion') != 'NOT_CLAIMED'):
        errors.append('Host endpoint requires frozen conditional-plan binding and no business-success claim')
    if (annotation.get('completion_status') != 'success'
            or annotation.get('short_flow') or effective < MINIMUM):
        errors.append('Formal annotation requires original-goal success and at least five effective steps')
    return errors


COMPLETED_GOAL_DELIVERY = 'completed-goal-delivery'


def completion_delivery_decision(annotation, raw_execution):
    """Delivery eligibility from sealed collection facts, never a QC grant.

    The single current rule: the original goal is completed with sealed
    evidence, at least MINIMUM effective business actions ran, and no
    cumulative step ceiling applies.
    """
    effective = sum(s.get('action', {}).get('action_type') not in
                    ('wait', 'finish', 'complete') for s in annotation.get('steps', []))
    ending = raw_execution.get('collection_ending') or {}
    basis = ending.get('endpoint_evidence') or {}
    objective = basis.get('session_objective_evidence') or {}
    goal = raw_execution.get('goal_evidence') or {}
    checks = goal.get('checks') or []
    completion = objective.get('completion') or {}
    original_checks = completion.get('original_checks') or []
    answers = (completion.get('answer') or {}).get('check_answers') or []
    from .wiki_reading import WIKI_READING_COMPLETION
    wiki_complete = bool(
        objective.get('policy') == WIKI_READING_COMPLETION
        and objective.get('status') == 'VERIFIED'
        and objective == goal.get('session_objective')
        and completion.get('policy') == WIKI_READING_COMPLETION
        and completion.get('decision') and completion.get('original_working_goal')
        and completion.get('original_plan_sha256') and original_checks
        and [a.get('check_index') for a in answers] == list(range(len(original_checks))))
    complete_checks = bool(checks) and all(c.get('status') == 'VERIFIED' for c in checks)
    # 策略 2 completions carry their own verified receipt (replayed by
    # validate_record); they never forge a HOST_PLAN_ENDPOINT marker.
    screenshot_complete = bool(ending.get('kind') == 'AGENT_COMPLETE_VERIFIED'
                               and ending.get('safe_for_pending_sample') is True
                               and (basis or {}).get('source') == 'host_screenshot_completion'
                               and (basis or {}).get('completion')
                               and (basis or {}).get('image')
                               and complete_checks)
    proof = bool(ending.get('kind') == 'HOST_PLAN_ENDPOINT'
                 and ending.get('safe_for_pending_sample') is True
                 and basis.get('image') and (wiki_complete or complete_checks)) or screenshot_complete
    completed = bool(proof and annotation.get('completion_status') == 'success'
                     and not raw_execution.get('trusted_prefix')
                     and not ending.get('flagged')
                     and not ending.get('external_effect_unknown')
                     and not raw_execution.get('unknown')
                     and not raw_execution.get('external_effect_unknown')
                     and not any(step.get('exception_evidence') for step in annotation.get('steps', []))
                     and raw_execution.get('stop_reason') == 'ready')
    eligible = completed and effective >= MINIMUM and not annotation.get('short_flow')
    return {'delivery_policy': COMPLETED_GOAL_DELIVERY,
            'effective_steps': effective, 'completion_status': annotation.get('completion_status'),
            'original_goal_completed': completed, 'ordinary_target_eligible': eligible,
            'delivery_eligible': eligible, 'QC_approval': False}
