"""Compile original observed transitions; independent admission is still required.

No browser, model, production ID or new business strategy is created here.
Every control and page comes from synchronized original observation evidence.
"""
from copy import deepcopy
import ipaddress
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlsplit

from .batch_core import file_sha, load_json, save_json
from .planning import object_sha256, timestamp, validate_capability
from .task_admission import _frame, _read, _review_source, reference

VERSION = 'observed-workflow-1'
TRACE_SCHEMA = 'webcollect-observed-workflow-trace-1'
INTENT_SCHEMA = 'webcollect-observed-workflow-intent-1'
TRANSITION_SCHEMA = 'webcollect-observed-workflow-transition-1'
SCHEMAS = {'real': ('webcollect-observed-workflow-packet-1', 'webcollect-observed-workflow-review-1'),
           'synthetic': ('webcollect-controlled-observed-workflow-packet-1', 'webcollect-controlled-observed-workflow-review-1')}
CHECKS = ('observed_controls', 'necessary_actions', 'visible_terminal', 'trajectory_continuity',
          'business_novelty', 'not_parameter_variant')
DIFFERENCES = ('task_goal', 'operation_path', 'page_states', 'result_judgement')
ACTIONS = {'click', 'type', 'select', 'scroll', 'hotkey', 'back'}
CONTROLS = {'click', 'type', 'select'}


def _require(value, message):
    if not value:
        raise ValueError('OBSERVED_WORKFLOW: ' + message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def original_control_label(state, element, action_type):
    """Read a native select's current painted option, never an option guess.

    The unchanged observer provides both complete-control value visibility and
    the stricter selected-option target evidence. Neither an accessible name
    nor the desired option argument can supply this fallback label.
    """
    label = element.get('text')
    if _text(label):
        return label
    if (action_type != 'select' or element.get('element_type') != 'select'
            or element.get('native_role') != 'select' or element.get('visible') is not True
            or element.get('enabled') is not True):
        return None
    values = [row for row in state.get('values', []) if row.get('element_id') == element.get('element_id')]
    target = state.get('target') or {}
    if (len(values) != 1 or values[0].get('choice') is not True or values[0].get('value_visible') is not True
            or values[0].get('input_type') not in ('select-one', 'select-multiple')
            or not _text(values[0].get('display_value'))
            or target.get('element_id') != element.get('element_id') or target.get('enabled') is not True
            or target.get('hit_valid') is not True):
        return None
    display = values[0]['display_value']
    if any(row.get('kind') == 'visible_selected_option' and row.get('text') == display
           for row in target.get('visible_label_evidence', [])):
        return display
    return None


def source_identity():
    root = Path(__file__).parent
    return {name: file_sha(root / name) for name in
            ('observed_workflow.py', 'browser.py', 'snapshot.js', 'task_contract.py',
             'task_admission.py', 'task_generation.py', 'planning.py', 'production_identity.py')}


def _review_checks(task):
    from .production_identity import REVIEW_CHECKS
    return CHECKS + REVIEW_CHECKS if task.get('pilot_identity') is not None else CHECKS


def _uri(value, mode):
    _require(_text(value), 'observed page URI is required')
    parsed = urlsplit(value)
    _require(parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password,
             'observed pages need HTTP(S) URIs without credentials')
    if mode == 'real':
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            _require(parsed.hostname not in ('localhost',) and '.' in parsed.hostname,
                     'real workflow cannot use a local host')
        else:
            _require(address.is_global, 'real workflow cannot use private/local addresses')
    return value


def _core(state):
    # Different target/assertion requests cannot manufacture a new page state.
    return {k: v for k, v in state.items() if k not in ('target', 'assertion_targets')}


def _assertions(conditions, state):
    _require(isinstance(conditions, list) and conditions, 'actual visible terminal assertions required')
    for condition in conditions:
        _require(isinstance(condition, dict), 'assertion must be an object')
        if set(condition) == {'visible_text'}:
            _require(_text(condition['visible_text']) and condition['visible_text'] in state['visible_text'],
                     'terminal literal is not visible in the original final frame')
            continue
        keys = set(condition) & {'contains', 'value', 'checked', 'disabled', 'numbers'}
        _require(_text(condition.get('selector')) and len(keys) == 1
                 and set(condition) <= {'selector', 'index', *keys}
                 and type(condition.get('index', 0)) is int and condition.get('index', 0) >= 0,
                 'unsupported/unbound terminal assertion')
        matches = [row for row in state.get('assertion_targets', []) if isinstance(row, dict)
                   and row.get('selector') == condition['selector'] and row.get('index', 0) == condition.get('index', 0)]
        _require(matches and all(row == matches[0] for row in matches) and matches[0].get('visible') is True,
                 'selector terminal target needs an actual synchronized visible assertion observation')
        target = matches[0]; key = next(iter(keys)); expected = condition[key]
        if key in ('value', 'contains', 'numbers') and target.get('value') is not None:
            _require(target.get('value_visible') is not False, 'hidden terminal control value is not evidence')
        actual = (target.get('value') if target.get('value') is not None else target.get('text')) if key in ('contains', 'numbers') else target.get(key)
        if key == 'numbers':
            import math
            _require(isinstance(expected, dict) and {'count', 'minimum', 'maximum_exclusive'} <= set(expected)
                     and set(expected) <= {'count', 'minimum', 'maximum_exclusive', 'integer', 'unique'}
                     and type(expected['count']) is int and expected['count'] > 0
                     and all(type(expected[k]) in (int, float) and math.isfinite(expected[k]) for k in ('minimum', 'maximum_exclusive'))
                     and expected['minimum'] < expected['maximum_exclusive']
                     and all(type(expected[k]) is bool for k in ('integer', 'unique') if k in expected),
                     'numeric predicate must use the existing finite count/range/boolean contract')
            from .collect import check_numbers
            passed = isinstance(actual, str) and check_numbers(actual, expected)
        elif key in ('checked', 'disabled'):
            _require(type(expected) is bool, 'checked/disabled assertions require an explicit boolean')
            passed = actual is expected
        else:
            passed = (_text(expected) and isinstance(actual, str) and expected in actual) if key == 'contains' else actual == expected
        _require(passed, 'terminal assertion differs from original final state')


def _trace(trace_ref):
    trace = load_json(_read(trace_ref)); mode = trace.get('mode')
    _require(trace.get('schema_version') == TRACE_SCHEMA and mode in SCHEMAS, 'trace schema/mode mismatch')
    intent = load_json(_read(trace.get('intent')))
    _require(intent.get('schema_version') == INTENT_SCHEMA and intent.get('mode') == mode,
             'frozen pre-action intent schema/mode mismatch')
    for field in ('site_uri', 'site_category', 'app_name', 'instruction'):
        _require(_text(intent.get(field)), 'intent missing ' + field)
    from .task_instruction import validate_task_instruction
    validate_task_instruction(intent['instruction'])
    from .validate import SCHEMAS as RESOURCES, StrictValidator
    task_types = json.loads(RESOURCES.joinpath('annotation.schema.json').read_text())['properties']['task_type']
    _require(not list(StrictValidator(task_types).iter_errors(intent.get('task_type'))),
             'intent task_type must use the existing customer enumeration')
    _uri(intent['site_uri'], mode)
    created = timestamp(intent.get('created_at'))
    _require(intent.get('created_at') is not None, 'intent must be frozen before the first action')
    if 'natural_settle_ms' in intent:
        _require(type(intent['natural_settle_ms']) is int and 500 <= intent['natural_settle_ms'] <= 5000,
                 'natural_settle_ms must be an integer from 500 to 5000')
    transitions = trace.get('transitions')
    _require(isinstance(transitions, list) and len(transitions) >= 5,
             'at least five actual explicit transitions required; no wait/complete padding')
    from .production_identity import require_actions
    require_actions(intent, len(transitions), final=True)
    frames = []; states = []; labels = []
    previous_after = None; first_started = None
    for index, transition in enumerate(transitions):
        _require(isinstance(transition, dict) and set(transition) == {'before', 'operation', 'execution', 'after'},
                 'each transition requires original before/after, operation and execution receipt')
        before, before_capture = _frame(transition['before'], mode)
        after, after_capture = _frame(transition['after'], mode)
        for state, capture in ((before, before_capture), (after, after_capture)):
            _uri(state.get('url'), mode)
            _require(re.fullmatch(r'[0-9a-f]{64}', capture['observer_sha256']), 'original observer hash is invalid')
        _require(before_capture['observer_sha256'] == after_capture['observer_sha256'], 'transition observer versions differ')
        _require(before['screen_resolution'] == after['screen_resolution'], 'transition viewport dimensions differ')
        if states:
            _require(before['screen_resolution'] == states[0][0]['screen_resolution'], 'workflow viewport dimensions differ')
        if previous_after:
            _require(_core(previous_after) == _core(before), 'trajectory has an unrecorded intermediate state or page jump')
        operation = transition['operation']; action = operation.get('action_type')
        _require(action in ACTIONS, 'unsupported observation action; navigation must be an actual observed action')
        _require(set(operation) <= {'action_type', 'selector', 'index', 'arguments', 'goal', 'rationale', 'expected',
                                    'execution', 'postconditions', 'evidence', 'page_name'},
                 'operation contains an invented strategy/adapter or unsupported instruction field')
        _require(all(_text(operation.get(k)) for k in ('goal', 'rationale', 'expected')),
                 'each pre-action operation needs goal, rationale and expected result')
        if operation.get('execution'):
            _require(set(operation['execution']) <= {'wait_navigation', 'wait_popup', 'settle_ms', 'distance'},
                     'unsupported hidden execution action')
        if 'natural_settle_ms' in intent:
            _require((operation.get('execution') or {}).get('settle_ms') == intent['natural_settle_ms'],
                     'actual operation must bind the frozen natural settle interval')
        from .browser import fingerprint, prepare_action
        effective = deepcopy(operation)
        target_label = None
        if action in CONTROLS:
            target = before.get('target')
            _require(_text(operation.get('selector')) and type(operation.get('index', 0)) is int
                     and operation.get('index', 0) >= 0 and isinstance(target, dict),
                     'control operation needs the actual observed selector and target')
            matches = [row for row in before['elements'] if row.get('element_id') == target.get('element_id')]
            _require(len(matches) == 1 and matches[0].get('visible') is True and matches[0].get('enabled') is True,
                     'target is not a unique visible enabled original tree element')
            target_label = original_control_label(before, matches[0], action)
            _require(_text(target_label) and any(row.get('text') == target_label
                     for row in target.get('visible_label_evidence', [])),
                     'original control name must be readable, not merely an accessible/visual guess')
            _require(not operation.get('evidence') or operation['evidence'] == {'target_label': target_label},
                     'declared control name differs from original DOM evidence')
            effective['evidence'] = {'target_label': target_label}
        arguments, _ = prepare_action(before, effective)
        receipt = load_json(_read(transition['execution']))
        _require(receipt.get('schema_version') == TRANSITION_SCHEMA and receipt.get('mode') == mode
                 and receipt.get('status') == 'success' and receipt.get('operation') == operation,
                 'execution receipt does not bind the exact successful original operation')
        _require(receipt.get('before_frame_sha256') == object_sha256(transition['before'])
                 and receipt.get('after_frame_sha256') == object_sha256(transition['after'])
                 and receipt.get('arguments') == arguments,
                 'execution receipt frame or actual argument binding differs')
        preflight = receipt.get('state_preflight', {})
        _require(preflight.get('matched') is True and preflight.get('state_fingerprint') == fingerprint(before),
                 'original pre-execution synchronized-state verification missing')
        recorded_sources = receipt.get('source_identity', {})
        _require(set(recorded_sources) == {'browser.py', 'snapshot.js'}
                 and all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) for value in recorded_sources.values())
                 and recorded_sources['snapshot.js'] == before_capture['observer_sha256'],
                 'execution used a different observer or lacks browser/action implementation identity')
        started, ended = timestamp(receipt.get('started_at')), timestamp(receipt.get('ended_at'))
        _require(receipt.get('started_at') is not None and receipt.get('ended_at') is not None
                 and created <= started <= ended and (first_started is None or started >= first_started),
                 'intent was not frozen before actions or execution times are inconsistent')
        first_started = ended
        _require(_core(before) != _core(after) or transition['before']['image']['sha256'] != transition['after']['image']['sha256'],
                 'observed action is an unchanged state/no-op; do not pad effective steps')
        if action == 'scroll':
            _require(before.get('scroll') != after.get('scroll') or before['visible_text'] != after['visible_text']
                     or [(e.get('element_id'), e.get('bbox')) for e in before['elements']]
                        != [(e.get('element_id'), e.get('bbox')) for e in after['elements']],
                     'scroll has no observed viewport/content movement')
        if index and _core(states[-1][0]) == _core(after):
            _require(transitions[index-1]['before']['image']['sha256'] != transition['after']['image']['sha256'],
                     'two-action return to the same original state is not an independent useful path')
        previous_after = after
        states.append((before, after)); labels.append(target_label)
        frames.extend((transition['before'], transition['after']))
    if trace.get('final_observation'):
        final_state, final_capture = _frame(trace['final_observation'], mode)
        _require(_core(final_state) == _core(states[-1][1]), 'read-only terminal observation contains an unrecorded state change')
        _require(final_capture['observer_sha256'] == _frame(transitions[-1]['after'], mode)[1]['observer_sha256'],
                 'terminal observation used a different observer')
        states[-1] = (states[-1][0], final_state)
        frames.append(trace['final_observation'])
    _assertions(trace.get('final_assertions'), states[-1][1])
    from .production_identity import validate_identity
    validate_identity(intent, observed_states=[row for pair in states for row in pair])
    # A terminal literal already true before the first action is not completion.
    try:
        _assertions(trace['final_assertions'], states[0][0])
    except ValueError:
        pass
    else:
        raise ValueError('OBSERVED_WORKFLOW: terminal condition already held before the task')
    return trace, intent, states, labels, frames


def scope_pages(trace_ref):
    _, _, states, _, _ = _trace(trace_ref)
    return sorted({state['url'] for pair in states for state in pair})


def validate_scope(record):
    pages = scope_pages(record.get('observed_workflow_trace'))
    scope = record.get('capability_scope', {})
    _require(scope == {'kind': 'observed-workflow-pages', 'page_uris': pages, 'sitewide': False},
             'workflow page scope must equal actual observed original transition pages')
    _require(record['site_uri'] in pages, 'site identity must be an actual observed workflow page')
    inventories = record.get('capabilities', []); representatives = record.get('representative_pages', [])
    _require(len(inventories) == len(pages) == len(representatives)
             and sorted(row.get('page_uri', '') for row in inventories) == pages
             and sorted(row.get('uri', '') for row in representatives) == pages,
             'workflow page inventories and representatives do not match original observed scope')
    for row in inventories + representatives:
        uri = row.get('page_uri', row.get('uri'))
        _require(all(row.get(k) in (None, uri) for k in ('requested_uri', 'landed_uri')),
                 'workflow page cannot use evidence requested/landed at another URI')
    return set(pages)


def derive_capability(parent_qualified_ref, trace_ref):
    """Derive observed pages without modifying or inheriting a false site PASS."""
    parent = load_json(_read(parent_qualified_ref))
    _require('site_qualification' in parent and 'observed_workflow_parent' not in parent,
             'an original independently qualified site capability is required')
    validate_capability(parent, require_ready=False)
    _require(parent.get('status') == 'ready' and parent['site_qualification'].get('status') == 'ready',
             'parent site qualification has not passed')
    trace, intent, states, _, frames = _trace(trace_ref)
    _require(parent.get('mode') == trace['mode'] and parent['site_uri'] == intent['site_uri']
             and parent['site_category'] == intent['site_category'], 'parent qualified site differs from frozen intent')
    pages = sorted({state['url'] for pair in states for state in pair})
    _require(all(urlsplit(uri).hostname == urlsplit(parent['site_uri']).hostname for uri in pages),
             'derived workflow cannot expand to another qualified application host')
    from .collect import chinese_ratio
    inventories = []; representatives = []
    for uri in pages:
        observed = [state for pair in states for state in pair if state['url'] == uri]
        ratio = min(chinese_ratio(state['visible_text']) for state in observed)
        first = observed[0]
        inventories.append({'page_uri': uri, 'title': first['title'], 'visible_text': first['visible_text'],
                            'elements': deepcopy(first['elements']), 'forms': [],
                            'result_targets': deepcopy(observed[-1].get('assertion_targets', []))})
        representatives.append({'uri': uri, 'title': first['title'], 'chinese_ratio': ratio,
                                'routing': 'NORMAL_M1' if ratio >= .7 else 'REVIEW_REQUIRED',
                                'evidence_kind': 'original-observed-workflow-frame'})
    evidence = [deepcopy(parent_qualified_ref), deepcopy(trace_ref), deepcopy(trace['intent'])]
    evidence += [deepcopy(ref) for frame in frames for ref in frame.values()]
    evidence += [deepcopy(row['execution']) for row in trace['transitions']]
    evidence = list({(row['path'], row['sha256']): row for row in evidence}.values())
    observed_at = max(timestamp(load_json(_read(row['execution']))['ended_at']) for row in trace['transitions'])
    _require(observed_at < timestamp(parent['expires_at']), 'workflow observation occurred after parent capability expiry')
    rejected = any(row['chinese_ratio'] < .7 for row in representatives)
    return {'schema_version': 'webcollect-site-capability-1', 'mode': trace['mode'],
        'capability_id': parent['capability_id'] + '-workflow-' + trace_ref['sha256'][:12],
        'version': object_sha256({'parent': parent_qualified_ref, 'trace': trace_ref, 'compiler': VERSION})[:24],
        'site_uri': parent['site_uri'], 'site_category': parent['site_category'],
        'observed_at': observed_at, 'expires_at': parent['expires_at'],
        'status': 'rejected' if rejected else 'review_required',
        'reason': 'Observed workflow language failed' if rejected else 'Original qualified parent retained; new workflow requires independent full-history admission',
        'supported_actions': sorted({row['operation']['action_type'] for row in trace['transitions']}),
        'task_families': ['observed-workflow'], 'evidence': evidence, 'capabilities': inventories,
        'representative_pages': representatives,
        'capability_scope': {'kind': 'observed-workflow-pages', 'page_uris': pages, 'sitewide': False},
        'observed_workflow_trace': deepcopy(trace_ref),
        'observed_workflow_parent': {'schema_version': 'qualified-parent-observed-workflow-1',
            'qualified_capability': deepcopy(parent_qualified_ref),
            'qualification_sha256': object_sha256(parent['site_qualification']),
            'capacity_verified': False, 'QC_approval': False}}


def validate_derived_capability(record, *, now=None):
    parent = record.get('observed_workflow_parent', {})
    _require(parent.get('schema_version') == 'qualified-parent-observed-workflow-1', 'derived parent schema mismatch')
    expected = derive_capability(parent.get('qualified_capability'), record.get('observed_workflow_trace'))
    admission = record.get('workflow_capability_admission')
    if not admission:
        _require(record == expected, 'pending derived capability was changed or manually promoted')
        return record['status']
    _require(expected['status'] != 'rejected'
             and set(admission) == {'packet', 'review', 'base_sha256', 'semantic_signature', 'QC_approval'}
             and admission['QC_approval'] is False and admission['base_sha256'] == object_sha256(expected),
             'derived ready disposition has invalid admission/base binding')
    packet = load_json(_read(admission['packet']))
    _require(packet.get('capability') == expected, 'ready disposition reviewed a different observed capability')
    _, review, signature = _validate(admission['packet'], admission['review'], packet['task'],
                                     mode=expected['mode'], current=now, live=now is not None)
    _require(signature == admission['semantic_signature'], 'ready disposition workflow meaning changed')
    ready = {**expected, 'status': 'ready', 'reason': review['reason'], 'workflow_capability_admission': admission}
    _require(record == ready, 'ready disposition changed observed capabilities or provenance')
    return 'ready'


def admit_capability(derived_ref, packet_ref, review_ref, live_context, *, mode, now=None):
    derived = load_json(_read(derived_ref))
    validate_derived_capability(derived)
    _require(derived['status'] == 'review_required', 'only a pending observed capability can be admitted')
    packet = load_json(_read(packet_ref))
    _require(packet.get('capability') == derived, 'admission packet binds another derived capability')
    task = attach(packet['task'], packet_ref, review_ref, live_context, mode=mode, now=now)
    review = load_json(_read(review_ref))
    result = {**derived, 'status': 'ready', 'reason': review['reason'],
              'workflow_capability_admission': {'packet': deepcopy(packet_ref), 'review': deepcopy(review_ref),
                  'base_sha256': object_sha256(derived), 'semantic_signature': task['workflow_admission']['semantic_signature'],
                  'QC_approval': False}}
    validate_derived_capability(result, now=timestamp(now))
    return result


def compile_task(capability, trace_ref, *, require_current_sources=True):
    trace, intent, states, labels, frames = _trace(trace_ref)
    if require_current_sources:
        sources = source_identity()
        _require(all(_frame(frame, trace['mode'])[1]['observer_sha256'] == sources['snapshot.js'] for frame in frames)
                 and all(load_json(_read(row['execution']))['source_identity'] ==
                         {key: sources[key] for key in ('browser.py', 'snapshot.js')} for row in trace['transitions']),
                 'workflow observation used another current browser/observer implementation')
    validate_capability(capability, require_ready=False)
    _require(capability.get('mode') == trace['mode'] and capability['site_uri'] == intent['site_uri']
             and capability['site_category'] == intent['site_category'], 'intent/capability identity differs')
    observed = {state['url'] for pair in states for state in pair}
    from .planning import _scoped_page_uris
    allowed = _scoped_page_uris(capability)
    if allowed is not None:
        _require(observed <= allowed, 'workflow left the actual observed capability page scope')
    operations = []
    for index, (transition, label) in enumerate(zip(trace['transitions'], labels), 1):
        operation = deepcopy(transition['operation'])
        operation.update(operation_id='observed-' + str(index), subgoal_id='workflow')
        if label:
            operation['evidence'] = {'target_label': label}
        if operation.get('postconditions'):
            _assertions(operation['postconditions'], states[index-1][1])
        operations.append(operation)
    task = {'task_id': intent.get('task_id') or 'observed-' + trace_ref['sha256'][:20],
            'task_version': VERSION + '-' + trace_ref['sha256'][:16],
            'site_uri': intent['site_uri'], 'site_category': intent['site_category'],
            'app_name': intent['app_name'], 'instruction': intent['instruction'],
            'task_type': deepcopy(intent.get('task_type')), 'initial_url': states[0][0]['url'],
            'capability_id': capability['capability_id'], 'capability_version': capability['version'],
            'task_family': 'observed-workflow', 'stop_when_final': True, 'operations': operations,
            'required_actions': [op['operation_id'] for op in operations],
            'subgoals': [{'id': 'workflow', 'description': intent['instruction'],
                          'evidence': [{'final_assertion_index': i} for i in range(len(trace['final_assertions']))]}],
            'final_assertions': deepcopy(trace['final_assertions']),
            'final_result': intent.get('final_result') or trace.get('final_result'),
            'completion_judgement': intent.get('completion_judgement') or trace.get('completion_judgement'),
            'allowed_hosts': sorted({urlsplit(uri).hostname for uri in observed}),
            'observed_workflow': {'version': VERSION, 'trace': deepcopy(trace_ref),
                                  'mode': trace['mode'], 'QC_approval': False}}
    if intent.get('pilot_identity') is not None:
        task['pilot_identity'] = deepcopy(intent['pilot_identity'])
    if 'natural_settle_ms' in intent:
        task['initial_settle_ms'] = intent['natural_settle_ms']
    _require(all(_text(task.get(k)) for k in ('final_result', 'completion_judgement')),
             'concrete terminal descriptions required')
    from .task_contract import validate_m4_task
    validate_m4_task(task)
    return task


def _base(task):
    return {key: value for key, value in task.items()
            if key not in ('workflow_admission', '_plan_schema_version', 'require_public_origin')}


def meaning(task, trace_ref):
    _, _, states, labels, _ = _trace(trace_ref)
    def normalized(value):
        value = unicodedata.normalize('NFKC', value).casefold()
        value = re.sub(r'https?://\S+', '<uri>', value)
        value = re.sub(r'\d+(?:\.\d+)?', '<number>', value)
        return re.sub(r'[\s，,。.:：;；!！?？、]+', '', value)
    # URI, selectors, argument values, prose and freely declared strategy IDs
    # never create a business identity. Independent history judgment is separate.
    roles = sorted([row['operation']['action_type'], normalized(label)]
                   for row, label in zip(load_json(_read(trace_ref))['transitions'], labels) if label)
    terminal = task['final_assertions']
    roles += [['terminal', normalized(row.get('visible_text', row.get('contains', str(row.get('value', '')))))]
              for row in terminal]
    return {'version': 'observed-workflow-parameterless-meaning-1', 'roles': roles,
            'terminal_page_title': normalized(states[-1][1]['title'])}


def prepare_admission(capability, trace_ref, history_context, output, *, mode, producer_context_id, now=None):
    task = compile_task(capability, trace_ref)
    trace, _, _, _, frames = _trace(trace_ref)
    _require(mode in SCHEMAS and mode == trace['mode'] and _text(producer_context_id), 'packet mode/producer identity required')
    _require(history_context.get('registry_snapshot') and history_context.get('history_scope', {}).get('formal_anchor')
             and isinstance(history_context.get('comparisons'), list), 'whole frozen original customer/registry history required')
    packet = {'schema_version': SCHEMAS[mode][0], 'version': VERSION, 'mode': mode,
              'created_at': timestamp(now), 'producer_context_id': producer_context_id,
              'capability': deepcopy(capability), 'trace': deepcopy(trace_ref), 'task': task,
              'frames': frames, 'history_context': deepcopy(history_context),
              'source_identity': source_identity(), 'meaning': meaning(task, trace_ref), 'QC_approval': False}
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    path = output / 'packet.json'; save_json(path, packet)
    template = {'schema_version': SCHEMAS[mode][1], 'packet_sha256': file_sha(path), 'completed': False,
        'reviewer': {'kind': '', 'id': '', 'context_id': ''}, 'reviewed_at': None, 'expires_at': None,
        'checks': {key: 'NOT_REVIEWED' for key in _review_checks(task)},
        'step_observations': [{'transition_index': i, 'before_image_sha256': row['before']['image']['sha256'],
                               'after_image_sha256': row['after']['image']['sha256'], 'observation': ''}
                              for i, row in enumerate(trace['transitions'])],
        'history_comparisons': [{'id': row['id'], 'relation': 'NOT_REVIEWED',
                                'differences': {key: '' for key in DIFFERENCES}, 'reason': ''}
                               for row in history_context['comparisons']], 'reason': '', 'provenance': None}
    template_path = output / 'review-template.json'; save_json(template_path, template)
    return {'packet': reference(path), 'review_template': str(template_path),
            'status': 'REVIEW_REQUIRED', 'sample_ids_allocated': 0, 'QC_approval': False}


def review_schema(packet_ref):
    """Strict model response body; provenance is attached from the real ledger."""
    packet = load_json(_read(packet_ref)); mode = packet['mode']
    trace = load_json(_read(packet['trace']))
    def obj(properties):
        return {'type': 'object', 'additionalProperties': False,
                'required': list(properties), 'properties': properties}
    text = {'type': 'string', 'minLength': 1}
    observations = [obj({'transition_index': {'const': i},
        'before_image_sha256': {'const': row['before']['image']['sha256']},
        'after_image_sha256': {'const': row['after']['image']['sha256']}, 'observation': text})
        for i, row in enumerate(trace['transitions'])]
    comparisons = [obj({'id': {'const': row['id']}, 'relation': {'enum': ['DISTINCT', 'SAME', 'UNCERTAIN']},
        'differences': obj({key: {'type': 'string'} for key in DIFFERENCES}), 'reason': text})
        for row in packet['history_context']['comparisons']]
    def array(items):
        return {'type': 'array', 'prefixItems': items, 'items': False,
                'minItems': len(items), 'maxItems': len(items)}
    return obj({'schema_version': {'const': SCHEMAS[mode][1]}, 'packet_sha256': {'const': packet_ref['sha256']},
        'completed': {'type': 'boolean'},
        'reviewer': obj({'kind': {'enum': ['model', 'session_ai', 'human']}, 'id': text,
                         'context_id': {'type': 'string', 'minLength': 1, 'not': {'const': packet['producer_context_id']}}}),
        'reviewed_at': {'type': 'number', 'minimum': packet['created_at']},
        'expires_at': {'type': 'number', 'maximum': timestamp(packet['capability']['expires_at'])},
        'checks': obj({key: {'enum': ['PASS', 'FAIL', 'REVIEW_REQUIRED']} for key in _review_checks(packet['task'])}),
        'step_observations': array(observations), 'history_comparisons': array(comparisons), 'reason': text})


def _validate(packet_ref, review_ref, task, *, mode=None, current=None, live=False):
    packet = load_json(_read(packet_ref)); review = load_json(_read(review_ref)); actual_mode = packet.get('mode')
    _require(actual_mode in SCHEMAS and (mode is None or mode == actual_mode), 'real/controlled admission mode mismatch')
    _require(packet.get('schema_version') == SCHEMAS[actual_mode][0] and packet.get('version') == VERSION
             and packet.get('QC_approval') is False and review.get('schema_version') == SCHEMAS[actual_mode][1],
             'packet/review schema/version mismatch')
    _require(set(review) == {'schema_version', 'packet_sha256', 'completed', 'reviewer', 'reviewed_at', 'expires_at',
                            'checks', 'step_observations', 'history_comparisons', 'reason', 'provenance'}
             and review.get('completed') is True and review.get('packet_sha256') == packet_ref['sha256'],
             'unreviewed packet or unsupported caller-selected identity field')
    _require(set(review.get('checks', {})) == set(_review_checks(task)) and all(value == 'PASS' for value in review['checks'].values())
             and _text(review.get('reason')), 'independent FAIL/uncertainty cannot grant admission')
    compiled = compile_task(packet['capability'], packet['trace'], require_current_sources=live)
    _require(compiled == packet['task'] == _base(task) and packet['meaning'] == meaning(task, packet['trace']),
             'compiled workflow/proposal/meaning changed')
    trace, _, _, _, frames = _trace(packet['trace'])
    _require(frames == packet['frames'], 'original workflow frames changed')
    observations = review.get('step_observations')
    _require(isinstance(observations, list) and len(observations) == len(trace['transitions']), 'every transition must be independently observed')
    for index, (observation, transition) in enumerate(zip(observations, trace['transitions'])):
        _require(set(observation) == {'transition_index', 'before_image_sha256', 'after_image_sha256', 'observation'}
                 and observation['transition_index'] == index and _text(observation.get('observation'))
                 and observation['before_image_sha256'] == transition['before']['image']['sha256']
                 and observation['after_image_sha256'] == transition['after']['image']['sha256'],
                 'independent observation omitted/changed an original before/after frame')
    comparisons = review.get('history_comparisons'); expected = packet['history_context']['comparisons']
    _require(isinstance(comparisons, list) and len(comparisons) == len(expected)
             and [row.get('id') for row in comparisons] == [row['id'] for row in expected], 'whole historical comparison coverage missing')
    for row in comparisons:
        _require(set(row) == {'id', 'relation', 'differences', 'reason'} and row['relation'] == 'DISTINCT'
                 and set(row.get('differences', {})) == set(DIFFERENCES)
                 and all(_text(value) for value in row['differences'].values()) and _text(row.get('reason')),
                 'same/uncertain/parameter-only task or missing goal/path/state/result comparison')
    reviewed, expiry = timestamp(review.get('reviewed_at')), timestamp(review.get('expires_at'))
    _require(review.get('reviewed_at') is not None and review.get('expires_at') is not None
             and packet['created_at'] <= reviewed < expiry <= timestamp(packet['capability']['expires_at']), 'admission review timing exceeds observed capability')
    _review_source(packet, review)
    if live:
        now = timestamp(current)
        _require(reviewed <= now < expiry, 'workflow admission expired/future')
        if 'observed_workflow_parent' in packet['capability']:
            validate_capability(packet['capability'], now=now, require_ready=False)
            _require(packet['capability']['status'] == 'review_required' and timestamp(packet['capability']['expires_at']) > now,
                     'derived workflow capability is rejected/expired')
        else:
            validate_capability(packet['capability'], now=now, require_ready=True)
        _require(packet['source_identity'] == source_identity(), 'workflow source implementation changed before dispatch')
    return packet, review, object_sha256({'observed_workflow_meaning': packet['meaning']})


def attach(task, packet_ref, review_ref, live_context, *, mode, now=None):
    packet, _, signature = _validate(packet_ref, review_ref, task, mode=mode, current=now, live=True)
    _require(packet['history_context'] == live_context, 'original customer/registry history changed before admission')
    result = deepcopy(task)
    result['workflow_admission'] = {'version': VERSION, 'packet': deepcopy(packet_ref), 'review': deepcopy(review_ref),
                                    'semantic_signature': signature, 'mode': mode, 'QC_approval': False}
    return result


def static_identity(task):
    binding = task.get('workflow_admission', {})
    _require(set(binding) == {'version', 'packet', 'review', 'semantic_signature', 'mode', 'QC_approval'}
             and binding['version'] == VERSION and binding['QC_approval'] is False, 'compiled workflow has not received independent admission')
    _, _, signature = _validate(binding['packet'], binding['review'], task, mode=binding['mode'])
    _require(signature == binding['semantic_signature'], 'workflow admission identity changed')
    return signature


def verify_entry(plan, registry, capture_output):
    tasks = [task for task in plan.get('tasks', []) if 'observed_workflow' in task or 'workflow_admission' in task
             or task.get('task_family') == 'observed-workflow']
    if not tasks:
        return None
    from .task_admission import context
    from .task_generation import read_customer_history, bind_formal_history
    from .collect_runtime import runtime_scope
    generation = plan.get('observed_workflow_generation', {})
    _require(generation.get('mode') == 'real' and generation.get('source_identity') == source_identity(),
             'real workflow generation/source binding required at direct collection entry')
    history_scope = generation.get('history_scope', {})
    history, actual_scope = read_customer_history(_read(history_scope.get('manifest')))
    actual_scope = bind_formal_history(actual_scope)
    _require(actual_scope == history_scope, 'original formal/customer history changed')
    capture = Path(capture_output).resolve(); own_scope = runtime_scope(capture); own_tasks = ()
    bootstrap = capture / 'bootstrap.json'
    if bootstrap.exists():
        saved = load_json(bootstrap)
        _require(saved.get('output_path') == str(capture) and saved.get('registry_path') == str(Path(registry).resolve())
                 and saved.get('plan') == plan, 'workflow resume is not bound to the exact original plan/output/registry')
        own_tasks = tuple(plan['tasks'])
    live = context(actual_scope, history, registry, exclude_scope=own_scope if own_tasks else None, own_tasks=own_tasks)
    seen = set()
    for task in tasks:
        binding = task.get('workflow_admission', {})
        packet, _, signature = _validate(binding.get('packet'), binding.get('review'), task, mode='real', current=time.time(), live=True)
        from .admission_cohort import assert_history_context
        assert_history_context(plan, registry, capture_output, packet['history_context'], live)
        _require(signature not in seen, 'parameter-only/duplicate workflow meaning within this plan')
        seen.add(signature)
        for old in live['registry_snapshot']['rows']:
            if 'workflow_admission' in old['task']:
                _require(static_identity(old['task']) != signature, 'same admitted workflow already exists in production history')
    return {'machine_status': 'PASS', 'workflows_checked': len(tasks), 'QC_approval': False,
            'scope': 'current independently reviewed observed workflow admission only'}
