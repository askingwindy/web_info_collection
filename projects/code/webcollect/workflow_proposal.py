"""Compile explicit DOM workflow proposals for the ordinary single execution.

Read-only source frames bind control labels, not prior successful executions.
Every target and result is checked again by the collector; this grants no QC.
"""
from copy import deepcopy

from .planning import object_sha256, verify_evidence

SCHEMA = 'webcollect-workflow-proposals-1'


def compile_workflow(capability, spec, version):
    from .task_admission import _frame
    from .task_contract import validate_m4_task, CONTROL_ACTIONS
    from .collect import validate_plan
    from .task_instruction import validate_task_instruction
    required = {'capability_id', 'capability_version', 'task_family', 'initial_url', 'instruction',
                'task_type', 'operations', 'subgoals', 'required_actions', 'final_assertions',
                'final_result', 'completion_judgement', 'anchors'}
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError('Explicit workflow proposal fields required')
    if (spec['capability_id'] != capability['capability_id'] or spec['capability_version'] != capability['version']
            or spec['task_family'] not in capability['task_families']):
        raise ValueError('Workflow proposal must bind the actual capability version and family')
    if not isinstance(spec['anchors'], list) or not spec['anchors']:
        raise ValueError('Workflow needs original read-only page anchors')
    pages = {page['page_uri'] for page in capability['capabilities']}
    states = [_frame(frame, capability['mode'])[0] for frame in spec['anchors']]
    if spec['initial_url'] not in pages or any(state['url'] not in pages for state in states):
        raise ValueError('Workflow anchors must belong to the observed capability pages')
    refs = [ref for frame in spec['anchors'] for ref in frame.values()]
    for ref in refs:
        verify_evidence([ref])
    operations = deepcopy(spec['operations'])
    if not isinstance(operations, list) or not 5 <= len(operations) <= 10:
        raise ValueError('Workflow needs 5-10 necessary proposed actions; no wait/complete padding')
    for operation in operations:
        action = operation.get('action_type')
        if action not in set(capability['supported_actions']) - {'wait', 'complete'}:
            raise ValueError('Unsupported observed workflow action')
        if action in CONTROL_ACTIONS:
            evidence = operation.get('evidence', {})
            index = evidence.get('anchor_index'); identity = evidence.get('anchor_element_id')
            if type(index) is not int or not 0 <= index < len(states):
                raise ValueError('Workflow target needs an original anchor index')
            matches = [row for row in states[index]['elements'] if row.get('element_id') == identity
                       and row.get('visible') is True and row.get('enabled') is True
                       and row.get('text') == evidence.get('target_label')]
            if len(matches) != 1 or not evidence.get('target_label'):
                raise ValueError('Workflow target label is not present in the original visible tree')
    task = {key: deepcopy(value) for key, value in spec.items() if key != 'anchors'}
    task.update(task_id='workflow-' + object_sha256(spec)[:24], task_version=version,
                site_uri=capability['site_uri'], site_category=capability['site_category'],
                app_name=next(page['title'] for page in capability['capabilities']
                              if page['page_uri'] == spec['initial_url']),
                stop_when_final=True, content_preparation=False,
                workflow_proposal={'schema_version': SCHEMA, 'spec': deepcopy(spec),
                                   'evidence': refs, 'semantic_status': 'REVIEW_REQUIRED'})
    validate_task_instruction(task['instruction'])
    validate_m4_task(task)
    validate_plan({'tasks': [task]})
    return task


def verify_task(task, capability):
    binding = task.get('workflow_proposal')
    if binding is None:
        return
    compiled = compile_workflow(capability, binding['spec'], task['task_version'])
    if task.get('pilot_identity'):
        from .production_identity import validate_identity
        validate_identity(task)
        compiled['app_name'] = task['pilot_identity']['application']['name']
        if task.get('mode') != capability['mode']:
            raise ValueError('Workflow identity mode differs from its source capability')
        compiled['mode'] = capability['mode']
    actual = {key: value for key, value in task.items()
              if key not in ('_plan_schema_version', 'require_public_origin', 'pilot_identity')}
    if compiled != actual:
        raise ValueError('Workflow proposal changed from its source-bound compilation')
