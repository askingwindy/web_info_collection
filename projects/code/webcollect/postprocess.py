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
from pathlib import Path
import platform

from .batch_core import file_sha, load_json
from .planning import object_sha256, verify_evidence
from .agent_controller import exclusive
from .react_session import REACT_VERSION, is_react_task, struct_goal, describe_goal

VERSION = 'webcollect-postprocess-1'


def _observation_state(record, observation_id):
    entry = record['observations'][observation_id]
    return load_json(entry['state_path'])


def _observation_capture(record, observation_id):
    entry = record['observations'][observation_id]
    return load_json(entry['evidence']['capture']['path'])


def session_record(raw_root):
    """Load and verify the immutable raw journal of one react execution."""
    raw_root = Path(raw_root)
    boundary = load_json(raw_root / 'boundary.json')
    terminal = load_json(raw_root / 'terminal.json')
    receipt = load_json(raw_root / 'raw-receipt.json')
    task = boundary['task']
    if not is_react_task(task) or boundary['protocol'] != REACT_VERSION:
        raise ValueError('Raw journal is not a react execution')
    files = {p.relative_to(raw_root).as_posix(): file_sha(p)
             for p in sorted(raw_root.rglob('*')) if p.is_file()}
    expected = {name: digest for name, digest in receipt['files_sha256'].items()
                if name != 'raw-receipt.json'}
    for name in ('boundary.json', 'terminal.json', 'trajectory.jsonl'):
        if name not in files or files[name] != expected.get(name):
            raise ValueError('原始执行关键文件缺失或字节改变：' + name)
    if terminal.get('unknown'):
        raise ValueError('UNKNOWN 原始终态不能进入交付加工；先按原账核对')
    observations = {}
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
        observations[project(state, canonical)['observation_id']] = {
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
    return record


def natural_instruction(task, record, effective):
    """Delivery instruction from the structured goal and the real trajectory."""
    app = task['app_name']
    goal = describe_goal(struct_goal(task))
    working = (record['goal_updates'] or [{}])[-1].get('description')
    focus = goal or working
    if focus:
        return f'在「{app}」上围绕{focus}，连续完成{effective}步真实网页操作并查看实际状态'
    return f'在「{app}」上连续完成{effective}步真实网页操作并查看实际状态'


def derive(task, record, delivery, ids, manifest):
    """Build the complete delivery sample from the raw execution; no IO models."""
    from .collect import chinese_ratio, describe_change, observed_frame_description
    from .task_contract import narrative_evidence, canonical_sha
    from .validate import validate_sample
    from .action_normalization import normalize_delivery_step
    from .browser import POINTER
    from .validate import CONTROL
    delivery = Path(delivery)
    (delivery / 'images').mkdir(parents=True, exist_ok=True)
    (delivery / 'ui_tree').mkdir(parents=True, exist_ok=True)
    trajectory = record['trajectory']
    if not trajectory:
        return {'status': 'no_actions', 'effective_steps': 0}
    effective = len(trajectory)
    short = bool(record['terminal'].get('short_flow'))
    reason = record['terminal'].get('short_flow_reason')
    length_qualified = effective >= 5 or (short and bool((reason or '').strip()))
    result = {'status': 'length_unqualified' if not length_qualified else 'deriving',
              'effective_steps': effective, 'short_flow': short,
              'short_flow_reason': reason if short else None,
              'length_qualified': length_qualified}
    if not length_qualified:
        return result
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
        (delivery / image_path).write_bytes(
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
                  'expected_result': row['expected']}
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
                              'context': 'Web / ' + task['app_name']},
                'tool_result': {'status': 'success', 'return_value': {}, 'error': ''},
                'next_step_rationale': row.get('semantic_goal') or row['goal'],
                'step_result': observed_result, 'exception_evidence': []}
        step = normalize_delivery_step(step, platform.system())
        steps.append(step)
        narrative_rows.append({'step_id': index, 'source_operation_id': row['operation_id'],
                               'before_observation_id': row['before_observation_id'],
                               'after_observation_id': row['after_observation_id'],
                               'narrative': narrative})
    if min(ratios) < 0.70:
        result.update(status='processing_failed',
                      error=f'visible_chinese_ratio={min(ratios):.3f} 低于 0.70', step_id=None)
        return result
    # The finish tool refreshed the terminal observation inside the session.
    final_id = record['terminal'].get('final_observation_id') or trajectory[-1]['after_observation_id']
    if final_id not in record['observations']:
        final_id = trajectory[-1]['after_observation_id']
    final_state = _observation_state(record, final_id)
    final_description = observed_frame_description(final_state, instruction)
    # Byte-stable completion timestamp: derived from the raw terminal capture
    # itself so re-derivation reproduces identical delivery artifacts.
    final_capture = _observation_capture(record, final_id)
    final_ns = (final_capture.get('attempts') or [{}])[-1].get('ended_ns')
    from datetime import datetime, timezone
    final_timestamp = (datetime.fromtimestamp(final_ns / 1e9, timezone.utc).isoformat()
                       if isinstance(final_ns, int) else terminal_fallback_timestamp(record))
    final_image = f'images/step_{effective + 1:03}.png'
    (delivery / final_image).write_bytes(
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
                                'context': 'Web / ' + task['app_name']},
                  'tool_result': {'status': 'success', 'return_value': {}, 'error': ''},
                  'next_step_rationale': final_description,
                  'step_result': '最终页面已确认，' + final_goal,
                  'exception_evidence': []})
    for position in range(len(steps) - 1):
        steps[position]['tool_result']['return_value']['screen_changed'] = \
            file_sha(delivery / steps[position]['image_path']) != file_sha(delivery / steps[position + 1]['image_path'])
    stop_summary = (record['terminal'].get('stop_summary') or '').strip()
    final_result = stop_summary or task['final_result']
    annotation = {'sample_id': ids['sample_id'], 'task_instruction': instruction,
        'task_type': task['task_type'], 'terminal_type': 'Web',
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
        'completion_status': 'success', 'completion_judgement': final_result}
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


def process(evidence_root, delivery_root, ids, manifest, *, derivation=None, validators=()):
    """Derive, validate, record and seal; reprocessing appends, never re-collects.

    `validators` are deterministic delivery checks (capture audit, producer
    duplicate index) run after derivation and before the sample is sealed;
    their failures record a delivery_rejected derivation without touching raw.
    """
    evidence_root = Path(evidence_root)
    raw_root = evidence_root / 'raw'
    record = session_record(raw_root)
    task = record['task']
    derivations_path = evidence_root / 'derivations.jsonl'
    prior = []
    if derivations_path.is_file():
        prior = [json.loads(line) for line in derivations_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if any(row.get('status') == 'derived_saved' for row in prior):
        raise ValueError('本原始执行已有当前有效交付版本；本轮一条原始执行最多一个有效交付样本')
    version = (derivation or len(prior) + 1)
    browser_calls = 0
    model_calls = 0
    try:
        derived = derive(task, record, delivery_root, ids, manifest)
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
    # Success path: project raw steps (actions already written live by the
    # session; the terminal complete record is projected here), identity and
    # the sealed delivery receipt.
    final_raw = _write_terminal_step(evidence_root, record, ids)
    # The capture audit re-derives the per-step target ground truth from the
    # same raw steps and compares it to this manifest; write it from those
    # identical sources so the delivered sample carries the original truth.
    ground_truth = []
    for number in range(1, final_raw['step_id'] + 1):
        step_path = evidence_root / f'step_{number:03}.json'
        if not step_path.exists():
            continue
        step_raw = load_json(step_path)
        target = step_raw.get('target_element')
        if target:
            ground_truth.append({'step_id': step_raw['step_id'], 'element_id': target['element_id'],
                                 'text': target['text'], 'bbox': target['bbox']})
    write_json_file(evidence_root / 'ground_truth.json', ground_truth)
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
    write_json_file(evidence_root / 'ground_truth.json', ground_truth)
    write_json_file(evidence_root / 'capture_summary.json',
        {'snapshot_source': 'browser_dom', 'capture_count': len(record['trajectory']) + 1,
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
        'effective_steps': derived['effective_steps'], 'short_flow': derived.get('short_flow'),
        'short_flow_reason': derived.get('short_flow_reason'),
        'instruction': derived['instruction'], 'final_result': derived['final_result'],
        'stop_reason': record['terminal'].get('stop_reason'),
        'source_mapping': derived['source_mapping'],
        'structural_report': {'structural_pass': derived['structural_report']['structural_pass'],
                              'rule_version': derived['structural_report']['rule_version']},
        'browser_calls': 0, 'model_calls': 0}
    derived_ref = exclusive(evidence_root / 'derived.json', derived_record)
    sample_files = {p.relative_to(delivery_root).as_posix(): file_sha(p)
                    for p in sorted(delivery_root.rglob('*')) if p.is_file()}
    # The append-only derivation ledger and the attempt close-out feedback
    # receipt are written after the seal by design; the frozen capture hash
    # never covers them.
    post_seal = ('saved_sample.json', 'context_cleanup_error.json', 'derivations.jsonl',
                 'planning-feedback-collected_pending_review.json')
    capture_files = {p.relative_to(evidence_root).as_posix(): file_sha(p)
                     for p in sorted(evidence_root.rglob('*')) if p.is_file()
                     and p.name not in post_seal}
    saved = {'attempt_id': ids.get('attempt_id'), 'sample_id': ids['sample_id'],
             'sample_files_sha256': sample_files, 'capture_files_sha256': capture_files,
             'semantic_review': 'REVIEW_REQUIRED',
             'raw_execution': {'protocol': REACT_VERSION,
                               'receipt': record['receipt']['terminal'],
                               'stop_reason': record['terminal'].get('stop_reason'),
                               'effective_steps': derived['effective_steps'],
                               'not_a_delivery_sample_by_itself': True},
             'derivation': {'version': version, 'record': derived_ref,
                            'source_mapping_sha256': object_sha256(derived['source_mapping'])}}
    write_json_file(evidence_root / 'saved_sample.json', saved)
    _append_derivation(derivations_path, {'schema_version': VERSION, 'derivation': version,
        'status': 'derived_saved', 'effective_steps': derived['effective_steps'],
        'saved_sample': {'path': str((evidence_root / 'saved_sample.json').resolve()),
                         'sha256': file_sha(evidence_root / 'saved_sample.json')},
        'record_ref': derived_ref})
    return {'schema_version': VERSION, 'derivation': version, 'status': 'derived_saved',
            'effective_steps': derived['effective_steps'], 'short_flow': derived.get('short_flow'),
            'stop_reason': record['terminal'].get('stop_reason'),
            'browser_calls': 0, 'model_calls': 0,
            'saved_sample': str((evidence_root / 'saved_sample.json').resolve())}


def _append_derivation(path, row):
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')


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
