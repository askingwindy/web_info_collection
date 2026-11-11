"""Versioned, three-valued action truth; no accessible-name-to-pixels inference.

Old snapshots remain readable. Missing target probes are UNKNOWN, not evidence
that the site has no routes. Supplemental capture uses the normal browser API.
"""
from copy import deepcopy
from pathlib import Path
from .planning import object_sha256, verify_evidence

VERSION = 'trusted-observation'
PROVEN, UNAVAILABLE, INSUFFICIENT = 'PROVEN', 'UNAVAILABLE', 'INSUFFICIENT'
CONTROL_ACTIONS = {'click', 'double_click', 'right_click', 'type', 'select', 'set_value', 'drag'}
ACTIONS = CONTROL_ACTIONS | {'scroll', 'open_url', 'back', 'hotkey', 'wait'}
LABEL_KINDS = {'rendered_target_text', 'rendered_associated_label', 'rendered_labelledby_text', 'rendered_grouped_button',
               'rendered_adjacent_input_group_label', 'visible_selected_option',
               'visible_native_value', 'visible_placeholder'}


def action_availability(state, element, binding, value, probe, action):
    """One predicate used by observation, dynamic compiler and dispatch guard."""
    def result(status, reason):
        return {'status': status, 'reason': reason}
    if action not in ACTIONS:
        return result(UNAVAILABLE, 'UNSUPPORTED_ACTION')
    if action not in CONTROL_ACTIONS:
        return result(PROVEN, 'PAGE_ACTION_REQUIRES_FROZEN_SCOPE_CHECK')
    if not element or element.get('visible') is False or element.get('enabled') is False:
        return result(UNAVAILABLE, 'TARGET_ABSENT_HIDDEN_OR_DISABLED')
    if element.get('visible') is not True or element.get('enabled') is not True:
        return result(INSUFFICIENT, 'MISSING_CONTROL_STATE')
    box = element.get('bbox'); viewport = state.get('screen_resolution', [])
    if box and len(viewport) == 2 and not (0 <= box[0] < box[2] <= viewport[0] and 0 <= box[1] < box[3] <= viewport[1]):
        return result(UNAVAILABLE, 'TARGET_OUTSIDE_CURRENT_VIEWPORT')
    if not probe or probe.get('element_id') != element['element_id']:
        return result(INSUFFICIENT, 'MISSING_TARGET_PROBE')
    if probe.get('hit_valid') is False:
        return result(UNAVAILABLE, 'TARGET_OCCLUDED')
    if probe.get('hit_valid') is not True:
        return result(INSUFFICIENT, 'MISSING_HIT_EVIDENCE')
    labels = readable_labels(probe)
    pointer_bound=(action in ('click','double_click','right_click') and element.get('clickable') is True
        and isinstance(binding,dict) and bool(binding.get('selector'))
        and binding.get('element_id')==element['element_id'] and probe.get('bbox')==box
        and isinstance(box,list) and len(box)==4 and isinstance(probe.get('coordinate'),list)
        and len(probe['coordinate'])==2 and box[0]<=probe['coordinate'][0]<box[2]
        and box[1]<=probe['coordinate'][1]<box[3])
    if not labels and not pointer_bound:
        return result(INSUFFICIENT, 'MISSING_READABLE_LABEL_EVIDENCE')
    if action in ('type', 'set_value'):
        if not element.get('inputable') or value.get('readonly') is True:
            return result(UNAVAILABLE, 'TARGET_NOT_EDITABLE')
        if value.get('readonly') is not False or not isinstance(value.get('value'), str):
            return result(INSUFFICIENT, 'MISSING_INPUT_STATE')
        if binding.get('tag') not in ('input', 'textarea') or value.get('input_type') in (
                'date', 'time', 'month', 'week', 'datetime-local', 'file', 'password'):
            return result(UNAVAILABLE, 'UNSUPPORTED_NATIVE_INPUT')
        if action == 'type' and probe.get('focused') is not True:
            return result(UNAVAILABLE, 'TYPE_REQUIRES_CURRENT_FOCUS')
    elif action == 'select':
        if binding.get('tag') != 'select':
            return result(UNAVAILABLE, 'NOT_NATIVE_SELECT')
    elif action=='drag':
        if not binding.get('selector') or not box:
            return result(INSUFFICIENT,'MISSING_DRAG_SOURCE_BINDING')
    elif element.get('clickable') is not True:
        return result(UNAVAILABLE, 'NOT_CLICKABLE')
    return result(PROVEN, 'CURRENT_RENDERED_TARGET_PROVED')


def readable_labels(probe):
    return [deepcopy(row) for row in (probe or {}).get('visible_label_evidence', [])
            if row.get('kind') in LABEL_KINDS and isinstance(row.get('text'), str) and row['text'].strip()]


def project(state, evidence, *, extended_actions=False):
    verify_evidence(list(evidence.values()))
    from .batch_core import load_json
    if load_json(evidence['state']['path']) != state:
        raise ValueError('Observation differs from bound original state')
    from .browser import validate_capture_receipt
    capture_verified = False
    try:
        validate_capture_receipt(state, load_json(evidence['capture']['path']),
            Path(evidence['image']['path']).read_bytes())
        capture_verified = True
    except (ValueError, KeyError, TypeError, IndexError):
        pass  # Original missing proof remains UNKNOWN; request a fresh capture.
    values = {v['element_id']: v for v in state.get('values', [])}
    elements = {e['element_id']: e for e in state.get('elements', [])}
    probe = state.get('target')
    controls = {}
    control_actions=CONTROL_ACTIONS if extended_actions else CONTROL_ACTIONS-{'drag'}
    page_actions=(ACTIONS-CONTROL_ACTIONS) if extended_actions else (ACTIONS-CONTROL_ACTIONS)-{'wait'}
    # Keep unavailable and unprobed inventory. Nothing is silently filtered out.
    for binding in state.get('capture_controls', []):
        eid = binding['element_id']; element = elements.get(eid)
        if element is None:
            continue
        current = probe if probe and probe.get('element_id') == eid else None
        value = values.get(eid, {})
        controls[eid] = {'element': deepcopy(element), 'binding': deepcopy(binding),
            'value': deepcopy(value), 'probe': deepcopy(current), 'readable_labels': readable_labels(current),
            'actions': {action: action_availability(state, element, binding, value, current, action)
                        for action in sorted(control_actions)}}
    if not capture_verified:
        for control in controls.values():
            control['readable_labels'] = []
            control['actions'] = {action:{'status':INSUFFICIENT,'reason':'MISSING_SYNCHRONIZED_CAPTURE_PROOF'}
                                  for action in control['actions']}
    identity = state.get('document_identity')
    result = {'schema_version': VERSION, 'url': state['url'], 'document_identity': identity,
        'capture_verified': capture_verified, 'viewport': state['screen_resolution'], 'scroll': state.get('scroll'), 'evidence': deepcopy(evidence),
        'state_sha256': object_sha256(state), 'visible_text': state.get('visible_text', ''), 'controls': controls,
        'page_actions': sorted(page_actions),
        'supplemental_observation': {'kind': 'capture_target', 'control_ids': list(controls),
            'read_only': True, 'state_changing_requests_must_be_actions': True}}
    if 'dynamic_region_contract' in state:
        from .dynamic_regions import summary as dynamic_summary
        result['dynamic_region_contract']=deepcopy(state['dynamic_region_contract'])
        result['dynamic_region_summary']=dynamic_summary(state)
    result['observation_id'] = object_sha256(result)
    return result


def require_action(state, operation):
    """New protocol only; archived plans keep their exact original validators."""
    if operation.get('evidence', {}).get('observation_protocol') != VERSION:
        return
    evidence = operation['evidence']
    if evidence.get('state_sha256') != object_sha256(state):
        raise ValueError('STALE_OBSERVATION: action must bind the current document, viewport and values')
    if operation['action_type'] == 'hotkey' and evidence.get('focused_element_id'):
        target = state.get('target') or {}
        if target.get('element_id') != evidence['focused_element_id'] or target.get('focused') is not True:
            raise ValueError('STALE_HOTKEY_FOCUS')
    if operation['action_type'] in CONTROL_ACTIONS:
        target = state.get('target') or {}; eid = evidence.get('anchor_element_id')
        element = next((e for e in state['elements'] if e['element_id'] == eid), None)
        binding = next((b for b in state['capture_controls'] if b['element_id'] == eid), {})
        value = next((v for v in state.get('values', []) if v['element_id'] == eid), {})
        if binding.get('selector') != operation.get('selector') or binding.get('index', 0) != operation.get('index', 0):
            raise ValueError('UNBOUND_SELECTOR')
        status = action_availability(state, element, binding, value, target, operation['action_type'])
        if status['status'] != PROVEN:
            raise ValueError(status['status'] + ': ' + status['reason'])
        if evidence.get('target_label') not in [r['text'] for r in readable_labels(target)] and not (
                operation['action_type'] in ('click','double_click','right_click') and evidence.get('target_label')==''):
            raise ValueError('MISSING_CURRENT_READABLE_LABEL')
        if 'replace_selected_number' in evidence:
            if (operation['action_type'] != 'type' or value.get('input_type') != 'number'
                    or value.get('focused') is not True or value.get('all_text_selected') is not True
                    or not value.get('value') or value['value'] != evidence['replace_selected_number']):
                raise ValueError('NUMERIC_REPLACEMENT_REQUIRES_CURRENT_FULL_SELECTION')
