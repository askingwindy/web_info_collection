"""Versioned M4 execution requirements; machine evidence is never semantic approval.

Legacy plans are read unchanged. The versioned entry point deliberately has a
smaller supported capability set than the customer action space.
"""
import hashlib
import json
import re

PLAN_SCHEMA = 'webcollect-plan-m4-1'
CONTROL_ACTIONS = {'click', 'double_click', 'right_click', 'drag', 'select', 'type'}
NON_EFFECTIVE = {'wait', 'complete'}


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def is_m4_task(task):
    return task.get('_plan_schema_version') == PLAN_SCHEMA


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_prompt_stages(declaration):
    """Validate actual declarations before any browser/ID allocation, not invent them."""
    if not isinstance(declaration, dict):
        raise ValueError('M4 requires production_facts before collection')
    for field in ('accounts_and_privacy', 'narrative_generation', 'narrative_mode'):
        if not _text(declaration.get(field)):
            raise ValueError('M4 production_facts missing ' + field)
    if declaration['narrative_mode'] not in ('template', 'model', 'mixed'):
        raise ValueError('M4 narrative_mode must be template/model/mixed')
    stages = declaration.get('prompt_stages')
    if not isinstance(stages, dict) or not {'planning', 'narrative'} <= stages.keys():
        raise ValueError('M4 requires separate planning and narrative prompt_stages')
    for name, stage in stages.items():
        if name not in ('planning', 'narrative', 'revision') or not isinstance(stage, dict):
            raise ValueError('Unsupported M4 prompt stage')
        if stage.get('mode') not in ('template', 'model') or not _text(stage.get('description')):
            raise ValueError('M4 prompt stage needs actual mode and description')
        if stage['mode'] == 'model' and not _text(stage.get('prompt')):
            raise ValueError('M4 model prompt stage requires its actual prompt')
        if stage['mode'] == 'template' and not _text(stage.get('template_version')):
            raise ValueError('M4 template stage requires template_version')
    return stages


def _assertions(conditions):
    if not isinstance(conditions, list) or not conditions:
        raise ValueError('M4 evidence requires nonempty assertions')
    value_keys = {'contains', 'value', 'number', 'numbers', 'time_seconds', 'checked', 'disabled'}
    for condition in conditions:
        if not isinstance(condition, dict):
            raise ValueError('M4 assertion must be an object')
        if 'visible_text' in condition:
            if not _text(condition['visible_text']) or 'selector' in condition:
                raise ValueError('M4 visible_text assertion must be nonempty and unambiguous')
        elif not _text(condition.get('selector')) or len(value_keys & condition.keys()) != 1:
            raise ValueError('M4 selector assertion requires exactly one expected value')


def validate_m4_task(task):
    if not _text(task.get('task_version')):
        raise ValueError('M4 task_version is required')
    if task.get('stop_when_final') is not True:
        raise ValueError('M4 stop_when_final must be true; do not disable natural completion to add steps')
    _assertions(task.get('final_assertions'))
    operations = task.get('operations')
    subgoals = task.get('subgoals')
    if not isinstance(operations, list) or not operations or not isinstance(subgoals, list) or not subgoals:
        raise ValueError('M4 requires operations and explicit subgoals')
    ids = [op.get('operation_id') for op in operations if isinstance(op, dict)]
    if len(ids) != len(operations) or any(not _text(x) for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('M4 operation_id must be nonempty and unique')
    goals = [goal.get('id') for goal in subgoals if isinstance(goal, dict)]
    if len(goals) != len(subgoals) or any(not _text(x) for x in goals) or len(set(goals)) != len(goals):
        raise ValueError('M4 subgoal IDs must be nonempty and unique')
    by_id = dict(zip(ids, operations))
    for op in operations:
        if op.get('subgoal_id') not in goals:
            raise ValueError('M4 operation must reference an existing subgoal')
        if op.get('observation'):
            raise ValueError('M4 cannot promote planned observation prose to an actual result')
        if op.get('postconditions') is not None:
            _assertions(op['postconditions'])
        if op.get('action_type') in CONTROL_ACTIONS:
            evidence = op.get('evidence', {})
            if not isinstance(evidence, dict):
                raise ValueError('M4 target evidence must be an object')
            kind = evidence.get('target_visual_kind', 'text')
            if kind != 'text':
                raise ValueError('M4_CAPABILITY_REVIEW_REQUIRED: icon targets need a separately verified visual adapter; not a customer prohibition')
            if not _text(evidence.get('target_label')):
                raise ValueError('M4 control action requires actual visible target_label evidence')
    required = task.get('required_actions')
    if not isinstance(required, list) or any(not _text(x) for x in required) or len(set(required)) != len(required):
        raise ValueError('M4 required_actions must be a unique list of operation IDs')
    if any(x not in by_id or by_id[x].get('action_type') in NON_EFFECTIVE for x in required):
        raise ValueError('M4 required_actions must reference actual effective planned actions')
    for goal in subgoals:
        if not _text(goal.get('description')) or not isinstance(goal.get('evidence'), list) or not goal['evidence']:
            raise ValueError('M4 subgoal needs a description and evidence references')
        for reference in goal['evidence']:
            if not isinstance(reference, dict):
                raise ValueError('M4 subgoal evidence reference must be an object')
            if set(reference) == {'final_assertion_index'}:
                index = reference['final_assertion_index']
                if type(index) is not int or not 0 <= index < len(task['final_assertions']):
                    raise ValueError('M4 final assertion evidence index is invalid')
            elif set(reference) == {'operation_id', 'postcondition_index'}:
                operation = by_id.get(reference['operation_id'], {})
                index = reference['postcondition_index']
                if (type(index) is not int or not 0 <= index < len(operation.get('postconditions', []))
                        or operation.get('subgoal_id') != goal['id']):
                    raise ValueError('M4 operation postcondition evidence reference is invalid')
            else:
                raise ValueError('M4 evidence must reference a final assertion or operation postcondition')
    return task


def validate_m4_plan(plan):
    if plan.get('schema_version') != PLAN_SCHEMA:
        return False
    validate_prompt_stages(plan.get('production_facts'))
    if not isinstance(plan.get('tasks'), list) or not plan['tasks']:
        raise ValueError('M4 plan requires tasks')
    for task in plan['tasks']:
        validate_m4_task(task)
    return True


def executed_action_ids(raw_records):
    return {row['operation']['operation_id'] for row in raw_records
            if row.get('operation_origin') == 'planned' and row.get('ended_at')
            and not row.get('execution_error') and row.get('operation', {}).get('operation_id')}


def completion_decision(task, raw_records, next_operation):
    """Called only when current literal terminal checks pass.

    Essential actions from the instruction may remain (e.g. start/pause).
    Unrelated planned scrolling is never allowed merely to fill the step count.
    """
    missing = set(task['required_actions']) - executed_action_ids(raw_records)
    if not missing:
        return 'complete'
    if next_operation.get('operation_id') not in missing:
        raise ValueError('M4 terminal facts already hold but next action is not a remaining required action; replan without padding')
    return 'required_action_pending'


def terminal_evidence(task, raw_records, assertions, final_binding):
    executed = executed_action_ids(raw_records)
    missing = set(task['required_actions']) - executed
    if missing:
        raise ValueError('M4 cannot complete before required actions: ' + ', '.join(sorted(missing)))
    by_id = {row['operation']['operation_id']: row for row in raw_records
             if row.get('operation', {}).get('operation_id') in executed}
    observations = []
    for goal in task['subgoals']:
        references = []
        for reference in goal['evidence']:
            if 'final_assertion_index' in reference:
                result = assertions[reference['final_assertion_index']]
                binding = final_binding
            else:
                raw = by_id.get(reference['operation_id'], {})
                bound = raw.get('postconditions_saved_frame', {})
                index = reference['postcondition_index']
                if index >= len(bound.get('assertions', [])):
                    raise ValueError('M4 subgoal lacks a saved-frame postcondition: ' + goal['id'])
                result = bound['assertions'][index]
                binding = bound['binding']
            if result.get('passed') is not True:
                raise ValueError('M4 subgoal evidence did not pass: ' + goal['id'])
            references.append({'reference': reference, 'observation': result, 'binding': binding})
        observations.append({'subgoal_id': goal['id'], 'evidence': references})
    return {'schema_version': 'webcollect-task-contract-evidence-1',
            'task_id': task['task_id'], 'task_version': task['task_version'],
            'machine_status': 'PASS', 'required_actions': task['required_actions'],
            'executed_operation_ids': sorted(executed), 'subgoals': observations,
            'semantic_status': 'REVIEW_REQUIRED',
            'semantic_reason': 'Literal assertions and execution records do not prove instruction completeness, earliest synonymous completion, useful steps or visual meaning; independent review of the bound files is required.'}


def narrative_evidence(text, before, after, operation):
    """Bind quotations to painted observations; unsupported prose is not exportable."""
    normalize = lambda value: re.sub(r'\s+', '', value)
    sources = [('after_visible_text', after.get('visible_text', ''))]
    if '已不在当前视口' in text:
        sources.append(('before_visible_text', before.get('visible_text', '')))
    # The existing producer explicitly calls these accessible names, not pixels.
    accessible = {e.get('text', '') for e in after.get('elements', [])}
    elements = {e.get('element_id'): e for e in after.get('elements', [])}
    visible_values = set()
    for value in after.get('values', []):
        element = elements.get(value.get('element_id'))
        displayed = value.get('display_value')
        if (element and element.get('visible') is True and value.get('value_visible') is True
                and isinstance(displayed, str)):
            visible_values.add(displayed)
    quotes = re.findall(r'「([^「」]*)」', text)
    matches = []
    missing = []
    for quote in quotes:
        source = next((name for name, value in sources if normalize(quote) in normalize(value)), None)
        if source is None and '可访问名称「' + quote + '」' in text and quote in accessible:
            source = 'explicit_accessible_name_not_visible_text'
        if source is None and quote in visible_values:
            source = 'after_fully_visible_control_value'
        if source is None:
            missing.append(quote)
        else:
            matches.append({'quote': quote, 'source': source})
    placeholder = ('具体可见变化待独立审核' in text or
                   '已执行本步动作并保存后续实际视口' in text)
    safe = None if missing or placeholder else text
    return safe, {'schema_version': 'webcollect-narrative-evidence-1',
                  'machine_status': 'REVIEW_REQUIRED' if missing or placeholder else 'PASS',
                  'semantic_status': 'REVIEW_REQUIRED', 'quoted_evidence': matches,
                  'unsupported_quotes': missing, 'proposed_text': text,
                  'exportable': safe is not None,
                  'placeholder_result': placeholder,
                  'operation_id': operation.get('operation_id'),
                  'reason': 'Quotations are source checks only; relevance and full-sentence meaning require review.'}
