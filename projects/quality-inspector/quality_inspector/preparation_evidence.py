"""Independent preparation evidence checks; no producer imports or visual claims."""
import hashlib
from webcollect import workspace_json as json
from pathlib import Path
from .format_checks import delivered_call_matches_capture

POLICY = 'content-preparation-v1'
PREPARATION_KINDS = {'close_overlay': 'click', 'scroll_to_content': 'scroll'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def full_visible_chinese_ratio(text):
    """Independent recomputation over the full recorded viewport text, not body."""
    letters = [c for c in text if c.isalpha()]
    chinese = sum(0x3400 <= ord(c) <= 0x9fff or 0xf900 <= ord(c) <= 0xfaff or
                  0x20000 <= ord(c) <= 0x323af for c in letters)
    return chinese / len(letters) if letters else 0.0


def audit_preparation(evidence_dir, sample_dir=None, expected_policy=None,
                      expected_observer_sha256=None):
    try:
        return _audit_preparation(evidence_dir, sample_dir, expected_policy, expected_observer_sha256)
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        return {'applicable': True, 'status': 'FAIL',
                'issues': [{'code': 'EVIDENCE_SHAPE', 'location': str(evidence_dir), 'reason': str(error)}],
                'visual_recognition_acceptance': 'NOT_EVALUATED'}


def _audit_preparation(evidence_dir, sample_dir=None, expected_policy=None,
                       expected_observer_sha256=None):
    """Audit new-policy captures, including rejected attempts; legacy is explicit.

    This proves evidence consistency, not correct ad/body recognition. The latter
    needs independently reviewed PNGs. A caller must pass its manifest policy so
    deleting all new-policy files cannot make a new run look like legacy data.
    """
    evidence = Path(evidence_dir)
    sample = Path(sample_dir) if sample_dir is not None else None
    issues = []
    metrics = {'prepared_actions': 0, 'close_actions': 0, 'scroll_actions': 0,
               'observed_frame_ratios': {}, 'delivery_eligible_by_language': None}

    def fail(code, location, reason):
        issues.append({'code': code, 'location': str(location), 'reason': reason})

    raw = {}
    for path in sorted(evidence.glob('step_*.json')):
        try:
            value = read(path)
            if not isinstance(value, dict): raise ValueError('Raw capture must be an object')
            if value.get('step_id') in raw:
                fail('RAW_DUPLICATE_ID', path, 'Raw captures cannot overwrite the same step identity')
            raw[value.get('step_id')] = value
        except (OSError, ValueError, TypeError) as error:
            fail('RAW_INVALID', path, str(error))
    initial_path = evidence / 'initial_capture.json'
    ledger_path = evidence / 'preparation_decisions.json'
    declared = expected_policy is not None or initial_path.exists() or ledger_path.exists() or any(
        r.get('operation_origin') == 'preparation' or r.get('preparation_decision_id') for r in raw.values())
    if not declared:
        return {'applicable': False, 'status': 'NOT_APPLICABLE', 'issues': issues,
                'reason': 'Legacy capture has no preparation policy or preparation markers; no new evidence claimed.',
                'visual_recognition_acceptance': 'NOT_EVALUATED'}
    if expected_policy is not None and expected_policy != POLICY:
        fail('POLICY', evidence, 'Unsupported explicitly declared preparation policy')
    initial = {}; ledger = {}
    for path, name in [(initial_path, 'initial'), (ledger_path, 'ledger')]:
        try:
            value = read(path)
            if not isinstance(value, dict):
                raise ValueError('Evidence must be an object')
            if name == 'initial': initial = value
            else: ledger = value
        except (OSError, ValueError, TypeError) as error:
            fail('MISSING_OR_INVALID_' + name.upper(), path, str(error))
    if initial.get('policy') != POLICY or initial.get('first_step_id') != 1 or initial.get('pre_action') is not True:
        fail('INITIAL_IDENTITY', initial_path, 'Original landing capture must precede every action and retain step 1 identity')
    if ledger.get('schema_version') != POLICY or ledger.get('mode') not in {'enabled', 'disabled'}:
        fail('LEDGER_IDENTITY', ledger_path, 'Declared schema and enabled/disabled mode are required')
    initial_image = evidence / 'initial_capture.png'
    initial_digest = initial.get('capture', {}).get('screenshot_sha256')
    if not initial_image.is_file() or sha(initial_image) != initial_digest:
        fail('INITIAL_HASH', initial_image, 'Original PNG must match its recorded capture SHA')
    if expected_observer_sha256 and initial.get('capture', {}).get('observer_sha256') != expected_observer_sha256:
        fail('INITIAL_OBSERVER', initial_path, 'Initial state must use the captured full-viewport observer identity')
    initial_state = initial.get('state', {})
    if not isinstance(initial_state, dict) or not isinstance(initial_state.get('visible_text'), str):
        fail('INITIAL_STATE', initial_path, 'Full visible viewport state is required')
        initial_state = {}
    initial_ratio = full_visible_chinese_ratio(initial_state.get('visible_text', ''))
    metrics['initial_full_visible_chinese_ratio'] = initial_ratio
    metrics['planned_close_matches_decision'] = 0
    metrics['planned_scroll_matches_decision'] = 0
    metrics['blocked_decisions_without_action'] = 0
    metrics['ineffective_actions_on_rejected_attempt'] = 0
    failure = {}
    failure_path = evidence / 'preparation_failure.json'
    captures = dict(raw)
    if 1 not in captures:
        captures[1] = {'step_id': 1, 'state': initial_state, 'capture': initial.get('capture', {})}
    if failure_path.exists():
        failure = read(failure_path)
        number = failure.get('step_id')
        if failure.get('policy') != POLICY or failure.get('action_executed') is not False or not failure.get('reason') or type(number) is not int or number < 1 or number in raw:
            fail('REJECTION_CAPTURE', failure_path, 'Rejection capture must retain its identity without inventing an executed raw action')
        else:
            captures[number] = failure
    annotation = None
    if sample is not None and (sample / 'annotation.json').is_file():
        try: annotation = read(sample / 'annotation.json')
        except (OSError, ValueError, TypeError) as error: fail('ANNOTATION', sample, str(error))
    steps = annotation.get('steps', []) if isinstance(annotation, dict) else []
    if steps and [s.get('step_id') for s in steps] != list(range(1, len(steps) + 1)):
        fail('STEP_SEQUENCE', sample, 'Inserted actions must retain a single consecutive formal step sequence')
    if steps and set(raw) != set(range(1, len(steps) + 1)):
        fail('FORMAL_RAW_COVERAGE', sample, 'No formal or raw action may disappear during renumbering')
    if sample is not None:
        first_image = sample / (steps[0].get('image_path', '') if steps else 'images/step_001.png')
        if not first_image.is_file() or sha(first_image) != initial_digest:
            fail('INITIAL_NOT_STEP_1', first_image, 'Closing or scrolling must not replace/discard the recorded landing frame')
    if 1 in raw and (raw[1].get('capture', {}).get('screenshot_sha256') != initial_digest or
                     raw[1].get('state') != initial_state):
        fail('INITIAL_RAW_MISMATCH', initial_path, 'First formal raw capture must be the same landing capture')
    native_failure = {}
    if (evidence / 'failure.json').is_file():
        native_failure = read(evidence / 'failure.json')
        if not isinstance(native_failure, dict) or not isinstance(native_failure.get('error'), str) or not native_failure['error'].strip():
            fail('REJECTED_OUTCOME', evidence / 'failure.json', 'Native rejection must retain its explicit error; it is not delivered success')
            native_failure = {}
    if not steps and not failure and not native_failure and not (evidence / 'eligibility_failure.json').is_file():
        fail('NO_ATTEMPT_OUTCOME', evidence, 'No recorded formal trajectory or eligibility rejection')
    metrics['goal_completion_supersedes_scroll'] = 0
    decisions = ledger.get('decisions')
    if not isinstance(decisions, list):
        fail('DECISIONS', ledger_path, 'Every assessment must be retained as an ordered decision list')
        decisions = []
    identifiers = []; before_ids = []; by_action = {}; ratios = []; limits = []; seen_preparation = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            fail('DECISION', ledger_path, 'Decision must be an object'); continue
        identity = decision.get('decision_id'); before_id = decision.get('before_step_id')
        identifiers.append(identity); before_ids.append(before_id)
        if not isinstance(identity, str) or not identity or type(before_id) is not int or before_id < 1:
            fail('DECISION_ID', ledger_path, 'Decision and positive before-step identities are required'); continue
        assessment = decision.get('assessment', {})
        expected_capture = captures.get(before_id, {})
        capture_digest = expected_capture.get('capture', {}).get('screenshot_sha256') or (initial_digest if before_id == 1 else None)
        state = expected_capture.get('state') or (initial_state if before_id == 1 else {})
        if not capture_digest or decision.get('before_image_sha256') != capture_digest:
            fail('DECISION_BEFORE_HASH', identity, 'Decision must bind the actual pre-action screenshot')
        if not isinstance(assessment, dict) or assessment.get('page_url') != state.get('url'):
            fail('ASSESSMENT_PAGE', identity, 'Read-only assessment must refer to the captured current URL')
        if assessment.get('decision', {}).get('action') != decision.get('kind'):
            fail('ASSESSMENT_KIND', identity, 'Ledger decision must preserve the recorded assessment')
        kind = decision.get('kind')
        if kind not in set(PREPARATION_KINDS) | {'ready', 'not_applicable', 'blocked'}:
            fail('DECISION_KIND', identity, 'Unknown preparation decision cannot be accepted')
        if before_id not in raw and (failure.get('step_id') == before_id or
                                    before_id == 1 and (evidence / 'eligibility_failure.json').is_file()):
            if decision.get('action_step_id') is not None:
                fail('PHANTOM_ACTION', identity, 'A blocked/rejected assessment must not count an intended action as executed')
            if failure and failure.get('decision_id') != identity:
                fail('REJECTION_DECISION', identity, 'Rejection capture must bind the actual stopping assessment')
            metrics['blocked_decisions_without_action'] += 1
            continue
        if kind not in PREPARATION_KINDS:
            if decision.get('action_step_id') is not None:
                fail('PHANTOM_ACTION', identity, 'Ready/disabled/blocked judgments must not invent a preparation action')
            continue
        # A real completed goal ends the trajectory before an unnecessary scroll.
        # Do not turn the read-only recommendation into a phantom executed action.
        record_at_capture = raw.get(before_id, {})
        if (kind == 'scroll_to_content' and record_at_capture.get('operation', {}).get('action_type') == 'complete'
                and record_at_capture.get('operation_origin') == 'planned'
                and record_at_capture.get('completion_trigger') == 'goal_already_satisfied'):
            assertions = record_at_capture.get('final_assertions')
            formal = steps[before_id - 1] if steps and 1 <= before_id <= len(steps) else {}
            complete = {'tool_name': 'complete', 'arguments': {'status': 'success'}}
            if (not assertions or not all(isinstance(a, dict) and a.get('passed') is True for a in assertions)
                    or record_at_capture.get('executed_action') != complete
                    or {k: formal.get('tool_call', {}).get(k) for k in ('tool_name', 'arguments')} != complete
                    or before_id != len(steps)
                    or record_at_capture.get('preparation_decision_id') != identity
                    or decision.get('operation_origin') != 'planned'
                    or any(decision.get(k) is not None for k in ('action_step_id', 'after_step_id', 'after_image_sha256'))
                    or decision.get('action_executed') is True):
                fail('GOAL_COMPLETION_PROOF', identity, 'Goal priority requires actual final complete, passed assertions and no claimed preparation execution')
            else:
                metrics['goal_completion_supersedes_scroll'] += 1
            continue
        planned_close = kind == 'close_overlay' and decision.get('performed_by_planned_close') is True
        planned_scroll = kind == 'scroll_to_content' and decision.get('performed_by_planned_scroll') is True
        planned_shared = planned_close or planned_scroll
        if planned_close:
            metrics['planned_close_matches_decision'] += 1
        elif planned_scroll:
            metrics['planned_scroll_matches_decision'] += 1
        else:
            metrics['prepared_actions'] += 1
            metrics['close_actions' if kind == 'close_overlay' else 'scroll_actions'] += 1
        if ledger.get('mode') == 'disabled' and not planned_shared:
            fail('DISABLED_ACTION', identity, 'Disabled preparation arm must not execute preparation actions')
        if (kind, capture_digest) in seen_preparation:
            fail('REPEATED_PREPARATION', identity, 'Do not repeat preparation from the same unchanged observed frame')
        seen_preparation.add((kind, capture_digest))
        settings = assessment.get('settings', {})
        if all(type(settings.get(k)) is int and 0 <= settings[k] <= 20 for k in ('max_actions', 'max_scrolls')):
            limits.append(settings)
        else:
            fail('ACTION_BUDGET', identity, 'Preparation requires explicit finite action and scroll budgets')
        action_id = before_id if planned_shared else decision.get('action_step_id')
        if action_id != before_id or action_id in by_action:
            fail('ACTION_ID', identity, 'Exactly one real preparation action must use this before-step identity')
        if not planned_shared: by_action[action_id] = decision
        record = raw.get(action_id, {})
        if planned_shared:
            if decision.get('action_step_id') is not None or record.get('operation_origin') != 'planned' or type(record.get('planned_operation_index')) is not int or record.get('preparation_decision_id') != identity:
                fail('PLANNED_SHARED_ORIGIN', identity, 'A matching real planned action is executed once as planned, never as an inserted action')
        elif record.get('operation_origin') != 'preparation' or record.get('planned_operation_index', 'missing') is not None or record.get('preparation_decision_id') != identity:
            fail('RAW_ORIGIN', identity, 'Preparation action cannot masquerade as a planned operation')
        if not planned_shared and decision.get('action_executed') is not True:
            fail('EXECUTION_NOT_CONFIRMED', identity, 'Only executed preparation, not a blocked intent, may count as an inserted action')
        action = record.get('executed_action', {})
        if action.get('tool_name') != PREPARATION_KINDS[kind]:
            fail('ACTION_TYPE', identity, 'Only a recorded safe close click or explicit content scroll may be inserted')
        if steps:
            if type(action_id) is not int or not 1 <= action_id <= len(steps):
                fail('ACTION_MISSING', identity, 'Preparation action is absent from the formal annotation')
            elif not delivered_call_matches_capture(action, {k: steps[action_id - 1]['tool_call'][k] for k in ('tool_name', 'arguments')}, (annotation or {}).get('device_info', {}).get('os_name')):
                fail('FORMAL_ACTION', identity, 'Preparation raw and delivered tool call must match')
        after_id = decision.get('after_step_id', before_id + 1 if planned_shared else None)
        following = captures.get(after_id, {})
        after_digest = decision.get('after_image_sha256', following.get('capture', {}).get('screenshot_sha256') if planned_shared else None)
        if after_id != before_id + 1 or not following or after_digest != following.get('capture', {}).get('screenshot_sha256'):
            fail('ACTION_AFTER', identity, 'Inserted action needs the next actual formal capture and its SHA')
        elif capture_digest == after_digest:
            if steps: fail('INEFFECTIVE_ACTION', identity, 'Preparation must not add identical-frame filler')
            else: metrics['ineffective_actions_on_rejected_attempt'] += 1
        if kind == 'scroll_to_content':
            if planned_scroll:
                proof = record.get('planned_scroll_preflight', {})
                operation = record.get('operation', {})
                distance = operation.get('execution', {}).get('distance')
                requested = assessment.get('decision', {}).get('distance')
                body = assessment.get('body', {})
                box = body.get('bbox', {})
                viewport_height = assessment.get('viewport', {}).get('height')
                before_scroll = state.get('scroll')
                after_scroll = following.get('state', {}).get('scroll')
                valid_distance = (type(distance) in (int, float) and type(requested) in (int, float)
                                  and 0 < requested <= distance <= 480)
                body_below = (body.get('found') is True and body.get('visible') is False
                              and type(box.get('y')) in (int, float) and type(box.get('height')) in (int, float)
                              and type(viewport_height) in (int, float) and box['y'] >= 0
                              and box['y'] + box['height'] > viewport_height)
                actual_scroll = (isinstance(before_scroll, list) and isinstance(after_scroll, list)
                                 and len(before_scroll) == len(after_scroll) == 2
                                 and valid_distance and 0 < after_scroll[1] - before_scroll[1] <= distance + 2
                                 and after_scroll[0] == before_scroll[0])
                if (proof.get('matched') is not True or record.get('planned_operation_index') != 0
                        or decision.get('planned_operation_index') != 0
                        or proof.get('decision_id') != identity or proof.get('direction') != 'down'
                        or proof.get('planned_distance') != distance
                        or proof.get('requested_preparation_distance') != requested
                        or proof.get('scroll_before') != before_scroll
                        or operation.get('action_type') != 'scroll'
                        or operation.get('arguments', {}).get('direction') != 'down'
                        or action.get('arguments', {}).get('direction') != 'down'
                        or not valid_distance or not body_below or not actual_scroll):
                    fail('PLANNED_SCROLL_PROOF', identity, 'Only the first real bounded downward planned scroll can fulfill an observed below-viewport content request')
            if steps and record.get('state', {}).get('scroll') == following.get('state', {}).get('scroll'):
                fail('INEFFECTIVE_SCROLL', identity, 'A no-op scroll is not a successful preparation step')
        else:
            target = record.get('target_element')
            if not isinstance(target, dict) or not record.get('target_preflight', {}).get('matched'):
                fail('CLOSE_TARGET', identity, 'Close click requires recorded real target and fresh hit preflight')
            else:
                current = next((e for e in state.get('elements', []) if e.get('element_id') == target.get('element_id')), None)
                if current != target:
                    fail('CLOSE_TREE_TARGET', identity, 'Close target must be the actual synchronized tree element')
                close = assessment.get('obstruction', {}).get('close', {})
                if assessment.get('obstruction', {}).get('present') is not True or not close:
                    fail('CLOSE_SELECTOR', identity, 'No guessed close outside the observed obstruction control')
                if planned_close:
                    proof = record.get('planned_close_preflight', {})
                    if proof.get('matched') is not True or proof.get('planned_selector') != record.get('operation', {}).get('selector') or proof.get('planned_selector_index') != record.get('operation', {}).get('index', 0) or proof.get('close_selector') != close.get('selector') or proof.get('element_id') != target.get('element_id') or proof.get('bbox') != target.get('bbox'):
                        fail('PLANNED_CLOSE_PROOF', identity, 'A marker alone cannot prove both selectors hit the same actual close target')
                elif record.get('operation', {}).get('selector') != close.get('selector'):
                    fail('CLOSE_SELECTOR', identity, 'Inserted close must use the observed obstruction selector')
                x, y = action.get('arguments', {}).get('x'), action.get('arguments', {}).get('y')
                box = target.get('bbox', [])
                if len(box) != 4 or type(x) is not int or type(y) is not int or not (box[0] <= x < box[2] and box[1] <= y < box[3]):
                    fail('CLOSE_COORDINATE', identity, 'Click must hit its recorded real target box')
                if steps and type(action_id) is int and 1 <= action_id <= len(steps):
                    formal_target = steps[action_id - 1].get('action', {})
                    if any(formal_target.get(key) != target.get(source) for key, source in (
                            ('target_element_id', 'element_id'), ('target_text', 'text'), ('target_bbox', 'bbox'))):
                        fail('FORMAL_CLOSE_TARGET', identity, 'Delivered close target must preserve the real raw element')
                    try:
                        ground = read(evidence / 'ground_truth.json')
                        expected = dict(step_id=action_id, element_id=target['element_id'], text=target['text'], bbox=target['bbox'])
                        if expected not in ground: fail('CLOSE_GROUND_TRUTH', identity, 'Observed close target must be retained in the target ledger')
                    except (OSError, ValueError, TypeError, KeyError) as error:
                        fail('CLOSE_GROUND_TRUTH', identity, str(error))
    if len(set(identifiers)) != len(identifiers): fail('DUPLICATE_DECISION', ledger_path, 'Decision IDs must be unique')
    valid_ids = [n for n in before_ids if type(n) is int]
    if valid_ids != sorted(valid_ids): fail('DECISION_ORDER', ledger_path, 'Assessments must retain their observed order')
    planned = []
    for number, record in sorted(captures.items(), key=lambda x: x[0] if type(x[0]) is int else -1):
        if type(number) is not int: fail('RAW_STEP_ID', evidence, 'Raw step ID must be an integer'); continue
        state = record.get('state', {})
        if sample is not None:
            formal = steps[number - 1] if steps and 1 <= number <= len(steps) else {}
            image = sample / formal.get('image_path', f'images/step_{number:03}.png')
            tree = sample / formal.get('ui_tree_path', f'ui_tree/step_{number:03}.json')
            if not image.is_file() or sha(image) != record.get('capture', {}).get('screenshot_sha256'):
                fail('FRAME_HASH', image, 'Actual formal PNG must match the preparation capture chain')
            try:
                tree_state = read(tree)
                if tree_state.get('elements') != state.get('elements') or tree_state.get('screen_resolution') != state.get('screen_resolution'):
                    fail('FRAME_TREE', tree, 'Formal tree must preserve the synchronized captured state')
            except (OSError, ValueError, TypeError) as error:
                fail('FRAME_TREE', tree, str(error))
        else:
            fail('FRAME_DIRECTORY_REQUIRED', number, 'A raw action needs actual formal PNG/tree files for independent binding')
        if isinstance(state.get('visible_text'), str):
            ratio = full_visible_chinese_ratio(state['visible_text']); ratios.append(ratio)
            metrics['observed_frame_ratios'][str(number)] = ratio
        else: fail('FRAME_LANGUAGE_EVIDENCE', number, 'Full visible viewport text is required')
        if number not in raw:
            if expected_observer_sha256 and record.get('capture', {}).get('observer_sha256') != expected_observer_sha256:
                fail('FRAME_OBSERVER', number, 'Rejected capture must still use the full-viewport observer')
            continue
        if record.get('operation_origin') == 'preparation' and number not in by_action:
            fail('UNACCOUNTED_PREPARATION', number, 'No inserted action may be omitted from the decision ledger')
        elif record.get('operation_origin') == 'planned':
            planned.append(record.get('planned_operation_index'))
        elif record.get('operation_origin') != 'preparation':
            fail('OPERATION_ORIGIN', number, 'Applicable captures must distinguish planned and preparation operations')
        if expected_observer_sha256 and record.get('capture', {}).get('observer_sha256') != expected_observer_sha256:
            fail('FRAME_OBSERVER', number, 'Frame must use the declared full-viewport observer')
    if planned != list(range(len(planned))): fail('PLANNED_SEQUENCE', evidence, 'Preparation must not skip or repeat planned operation indices')
    if limits and (metrics['prepared_actions'] > min(x['max_actions'] for x in limits) or
                   metrics['scroll_actions'] > min(x['max_scrolls'] for x in limits)):
        fail('ACTION_BUDGET_EXCEEDED', ledger_path, 'Recorded preparation exceeded its declared bounds')
    # Keep the full-frame diagnostic; language eligibility needs an actual
    # page/control comparison, not a Han/letter threshold or a body-only score.
    metrics['language_policy'] = 'page-control-language-consistency-1'
    metrics['chinese_ratio_diagnostic_only'] = True
    metrics['language_review'] = 'REVIEW_REQUIRED'
    return {'applicable': True, 'status': 'FAIL' if issues else 'PASS', 'issues': issues,
            'policy': POLICY, 'metrics': metrics, 'is_recorded_delivery': bool(steps),
            'attempt_outcome': 'recorded_delivery' if steps else 'rejected_or_incomplete',
            'visual_recognition_acceptance': 'REQUIRES_INDEPENDENT_IMAGE_GROUND_TRUTH',
            'limits': 'Evidence consistency does not prove ad/body correctness or absence of uninstrumented browser API calls.'}
