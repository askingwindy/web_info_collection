"""Evidence-bound admission of unknown, observed ordinary form tasks.

This module never authors a completed review, calls a model, allocates IDs or
releases QC. Its real/controlled schemas are deliberately incompatible. A review
is a named independent judgment supported by original image/tree bindings, not
a caller-selected business ID. Historical signatures survive review expiry;
new dispatch always rechecks live source, capability, history and registry.
"""
from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import time
import unicodedata

from PIL import Image
from .batch_core import file_sha, load_json, save_json
from .planning import object_sha256, timestamp, validate_capability

VERSION = 'observed-form-task-admission-1'
SCHEMAS = {'real': ('webcollect-task-admission-packet-1', 'webcollect-task-admission-review-1'),
           'synthetic': ('webcollect-controlled-task-admission-packet-1', 'webcollect-controlled-task-admission-review-1')}
CHECKS = ('observed_controls', 'necessary_actions', 'visible_terminal', 'business_novelty', 'not_parameter_variant')


def _require(condition, reason):
    if not condition:
        raise ValueError('TASK_ADMISSION: ' + reason)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def reference(path):
    original = Path(path)
    _require(not original.is_symlink(), 'missing/unsafe evidence file')
    path = original.resolve()
    _require(path.is_file(), 'missing/unsafe evidence file')
    return {'path': str(path), 'sha256': file_sha(path)}


def _read(ref):
    _require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'}, 'exact path/SHA evidence reference required')
    path = Path(ref['path'])
    _require(path.is_absolute() and path.is_file() and not path.is_symlink() and file_sha(path) == ref['sha256'], 'evidence missing or changed')
    return path


def registry_snapshot(registry, *, exclude_scope=None, own_tasks=()):
    """Freeze immutable tasks, not counters/status changed by this same capture."""
    path = Path(registry).resolve()
    _require(path.is_file(), 'existing original registry required')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        _require('m4_tasks' in tables, 'original M4 history table missing')
        columns = {row[1] for row in con.execute('PRAGMA table_info(m4_tasks)')}
        scope = 'scope_id' if 'scope_id' in columns else 'NULL AS scope_id'
        campaign = 'campaign_id' if 'campaign_id' in columns else 'NULL AS campaign_id'
        rows = []
        for row in con.execute('SELECT ' + scope + ',' + campaign + ',task_json FROM m4_tasks'):
            task = json.loads(row['task_json'])
            if exclude_scope and row['scope_id'] == exclude_scope:
                _require(any(task == own for own in own_tasks), 'resume scope contains an unbound task')
                continue
            rows.append({'scope_id': row['scope_id'], 'campaign_id': row['campaign_id'], 'task': task})
    rows.sort(key=object_sha256)
    return {'registry': str(path), 'rows': rows, 'sha256': object_sha256(rows)}


def context(history_scope, customer_history, registry, *, exclude_scope=None, own_tasks=()):
    from .current_chain import SCOPE_SCHEMA, history_context
    if isinstance(history_scope, dict) and history_scope.get('schema_version') == SCOPE_SCHEMA:
        return history_context(history_scope, customer_history, registry,
                               exclude_scope=exclude_scope, own_tasks=own_tasks)
    _require(isinstance(history_scope, dict) and history_scope.get('schema_version') == 'webcollect-task-history-scope-1', 'frozen customer history scope required')
    _require(isinstance(history_scope.get('formal_anchor'), dict), 'formal LATEST history binding required')
    manifest = history_scope.get('manifest', {})
    _read(manifest)
    anchor = history_scope['formal_anchor']
    _read({'path': anchor['path'], 'sha256': anchor['sha256']})
    snapshot = registry_snapshot(registry, exclude_scope=exclude_scope, own_tasks=own_tasks)
    comparisons = [{'id': 'customer:' + row['sample_id'], 'record': row} for row in customer_history]
    comparisons += [{'id': 'm4:' + object_sha256(row), 'record': row} for row in snapshot['rows']]
    comparisons.sort(key=lambda row: row['id'])
    return {'history_scope': deepcopy(history_scope), 'customer_history_sha256': object_sha256(customer_history),
            'registry_snapshot': snapshot, 'comparisons': comparisons}


def _frame(frame, mode):
    _require(isinstance(frame, dict) and set(frame) == {'image', 'state', 'capture'}, 'frame needs original image, state and capture binding')
    image, state_path, capture_path = [_read(frame[key]) for key in ('image', 'state', 'capture')]
    state, capture = load_json(state_path), load_json(capture_path)
    if mode == 'real':
        _require(not state.get('diagnostic_only') and not capture.get('diagnostic_only')
                 and capture.get('accepted_as_formal_frame') is not False, 'diagnostic/rejected frame cannot approve real admission')
    if 'state' in state:
        state = state['state']
    if 'capture' in capture:
        capture = capture['capture']
    _require(capture.get('screenshot_sha256') == frame['image']['sha256'] and _text(capture.get('observer_sha256')), 'image/observer capture binding mismatch')
    _require(isinstance(state.get('visible_text'), str) and isinstance(state.get('elements'), list) and state['elements'], 'original visible state/tree required')
    with Image.open(image) as bitmap:
        _require(bitmap.format == 'PNG' and list(bitmap.size) == state.get('screen_resolution'), 'original PNG/tree dimensions differ')
        bitmap.verify()
    if mode == 'real':
        from .browser import fingerprint
        state_fingerprint = fingerprint(state)
        _require(capture.get('attempts') and capture['attempts'][-1].get('before_fingerprint') == state_fingerprint
                 and capture['attempts'][-1].get('after_fingerprint') == state_fingerprint, 'real PNG/tree capture fingerprints differ')
        _require(capture.get('snapshot_source') == 'browser_dom'
                 and capture.get('coordinate_space') == 'screenshot_css_pixels'
                 and capture.get('attempts') and capture['attempts'][-1].get('dom_stable') is True, 'real frame needs original synchronized capture proof')
        _require(not state.get('fixture') and state.get('mode') != 'synthetic' and not capture.get('fixture'), 'controlled frame cannot enter real admission')
    return state, capture


def _base(task):
    return {key: value for key, value in task.items() if key != 'task_admission'}


def _native_roles(capability, spec, task, *, _observer_sha256=None):
    """No new adapter, navigation, virtual targets or free business declaration."""
    from .task_generation import compile_form
    _require(not spec.get('widget_adapter') and not spec.get('deterministic_strategy'), 'admission is only for unknown ordinary forms')
    compiled = compile_form(capability, spec, _observer_sha256=_observer_sha256)
    # A future compiler version must not erase an already admitted historical
    # meaning merely because its version label changed. New dispatch checks
    # the current source identity separately.
    compiled['task_version'] = _base(task).get('task_version')
    _require(compiled == _base(task), 'proposal is not the unchanged ordinary-form compiler output')
    pages = [page for page in capability['capabilities'] if page['page_uri'] == spec['page_uri']]
    _require(len(pages) == 1, 'one exact observed page required')
    targets = [target for target in pages[0].get('result_targets', []) if target['selector'] == spec['completion']['selector']]
    _require(len(targets) == 1, 'one observed terminal container required')
    terminal_role = targets[0].get('label') or targets[0].get('text')
    _require(_text(terminal_role), 'terminal role must already have observed readable label/text')
    return [{'kind': 'input', 'selector': item['selector'], 'label': item['label']} for item in spec['inputs']] + [
        {'kind': 'submit', 'selector': spec['submit']['selector'], 'label': spec['submit']['label']},
        {'kind': 'result', 'selector': targets[0]['selector'], 'label': terminal_role}]


def descriptor(packet):
    def meaning(text):
        text = unicodedata.normalize('NFKC', text).casefold()
        text = re.sub(r'https?://\S+', '<uri>', text)
        text = re.sub(r'\d+(?:\.\d+)?', '<number>', text)
        return re.sub(r'[\s，,。.:：;；!！?？、]+', '', text)
    # Literal arguments, keywords, selectors, URL, task/form titles and goal
    # prose cannot manufacture a new identity. Ambiguous same-role forms stay
    # the same class; only an actual independent review may resolve aliases.
    inputs = sorted(meaning(row['label']) for row in packet['roles'] if row['kind'] == 'input')
    return {'schema_version': 'observed-parameterless-form-meaning-1',
            'input_roles': inputs,
            'submit_role': next(meaning(row['label']) for row in packet['roles'] if row['kind'] == 'submit'),
            'result_role': next(meaning(row['label']) for row in packet['roles'] if row['kind'] == 'result'),
            # Filling the same roles in another order is not a new business.
            'workflow': {'necessary_input_roles': len(inputs), 'result_action': 'submit-visible-result'}}


def prepare_packet(capability, spec, task, history_context, frames, output, *, mode, producer_context_id, now=None):
    current = timestamp(now)
    _require(mode in SCHEMAS and _text(producer_context_id), 'explicit execution mode and producer context required')
    validate_capability(capability, now=current, require_ready=True)
    _require(capability.get('mode') == mode, 'capability/mode mismatch')
    validate_history_context(history_context)
    from .current_chain import SCOPE_SCHEMA, assert_current_evidence
    if history_context['history_scope'].get('schema_version') == SCOPE_SCHEMA:
        assert_current_evidence(history_context['history_scope'], frames)
        assert_current_evidence(history_context['history_scope'], capability.get('evidence', []))
    roles = _native_roles(capability, spec, task)
    _require(isinstance(frames, list) and frames, 'actual original observation frames required')
    for frame in frames:
        state, _ = _frame(frame, mode)
        _require(state.get('url') == task['initial_url'], 'ordinary-form frame is outside exact page')
    from .task_generation import generation_source_identity
    packet = {'schema_version': SCHEMAS[mode][0], 'version': VERSION, 'mode': mode,
              'created_at': current, 'producer_context_id': producer_context_id,
              'capability': deepcopy(capability), 'spec': deepcopy(spec), 'task': deepcopy(_base(task)),
              'roles': roles, 'frames': deepcopy(frames), 'history_context': deepcopy(history_context),
              'source_identity': generation_source_identity(), 'QC_approval': False}
    packet['meaning'] = descriptor(packet)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    packet_path = output / 'packet.json'; save_json(packet_path, packet)
    template = {'schema_version': SCHEMAS[mode][1], 'packet_sha256': file_sha(packet_path), 'completed': False,
                'reviewer': {'id': '', 'kind': '', 'context_id': ''}, 'reviewed_at': None, 'expires_at': None,
                'checks': {key: 'NOT_REVIEWED' for key in CHECKS}, 'reason': '', 'registered_business_id': None,
                'role_observations': [{'role_index': i, 'frame_index': None, 'observation': ''} for i in range(len(roles))],
                'history_comparisons': [{'id': row['id'], 'relation': 'NOT_REVIEWED', 'reason': ''} for row in history_context['comparisons']],
                'provenance': None}
    save_json(output / 'review-template.json', template)
    return {'packet': reference(packet_path), 'review_template': str(output / 'review-template.json'),
            'status': 'REVIEW_REQUIRED', 'sample_ids_allocated': 0, 'QC_approval': False}


def validate_history_context(value):
    from .current_chain import SCOPE_SCHEMA, validate_history_context as validate_current
    if value.get('history_scope', {}).get('schema_version') == SCOPE_SCHEMA:
        return validate_current(value)
    _require(value.get('registry_snapshot') and value.get('history_scope', {}).get('formal_anchor'),
             'complete frozen history context required')
    return True


def _registered_ids():
    from .task_generation import STRATEGIES
    ids = {item['id'] for item in STRATEGIES}
    for name in ('bmi_strategy', 'date_strategy', 'ascii_art_strategy', 'loan_strategy', 'html_table_strategy', 'qr_strategy', 'placeholder_strategy', 'hmac_strategy', 'pbkdf2_strategy'):
        from importlib import import_module
        module = import_module('webcollect.' + name)
        ids.add(getattr(module, 'BUSINESS_ID', getattr(module, 'STRATEGY_ID', None)))
    return ids


def _review_source(packet, review):
    reviewer = review['reviewer']; mode = packet['mode']
    _require(set(reviewer) == {'kind', 'id', 'context_id'} and reviewer['kind'] in ('session_ai', 'human', 'model')
             and _text(reviewer['id']) and _text(reviewer['context_id'])
             and reviewer['context_id'] != packet['producer_context_id'], 'named independent reviewer required; do not impersonate a human/model')
    provenance = review['provenance']; path = _read(provenance); source = load_json(path)
    _require(source.get('schema_version') == ('webcollect-independent-task-review-source-1' if mode == 'real' else 'webcollect-controlled-task-review-source-1')
             and source.get('reviewer') == reviewer and source.get('packet_sha256') == review['packet_sha256']
             and source.get('completed') is True and source.get('reviewed_at') == review['reviewed_at']
             and source.get('review_body_sha256') == object_sha256({k: v for k, v in review.items() if k != 'provenance'}), 'independent review source/body binding mismatch')
    expected_images = sorted({frame['image']['sha256'] for frame in packet['frames']})
    expected_states = sorted({frame['state']['sha256'] for frame in packet['frames']})
    _require(source.get('reviewed_frame_sha256') == expected_images
             and source.get('reviewed_tree_sha256') == expected_states, 'independent source did not cover original images/trees')
    if mode == 'real':
        _require(not source.get('fixture'), 'controlled provenance cannot approve a real task')
    if reviewer['kind'] == 'model':
        _require(source.get('actual_external_model_call') is True, 'uncalled model cannot be recorded as real model')
        trace = source.get('model_trace', {})
        ledger = Path(trace.get('ledger', '')).resolve()
        _require(ledger.is_file(), 'real model review needs its original request ledger')
        with closing(sqlite3.connect(ledger.as_uri() + '?mode=ro', uri=True)) as con:
            con.row_factory = sqlite3.Row
            config = json.loads(con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()[0])
            row = con.execute('SELECT * FROM model_requests WHERE id=?', (trace.get('request_id'),)).fetchone()
            _require(config.get('mode') == 'real' and config.get('model', {}).get('provider') != 'synthetic'
                     and row is not None and row['state'] == 'succeeded', 'uncalled/synthetic/uncertain model cannot be recorded as real model')
            request, response = json.loads(row['request_json']), json.loads(row['response'])
            _require(set(expected_images) <= {image.get('sha256') for image in request.get('images', [])},
                     'model request did not receive every claimed original frame')
            _require(request.get('provider') != 'synthetic' and request.get('model') == reviewer['id']
                     and review['packet_sha256'] in request.get('text', '')
                     and response.get('result') == {k: v for k, v in review.items() if k != 'provenance'}, 'model response is not this exact independent admission review')
    else:
        _require(not source.get('model_trace') and source.get('actual_external_model_call') is False, 'session/human review must not claim a GLM call')


def _validate(packet_ref, review_ref, task, *, current=None, live=False, mode=None):
    packet_path, review_path = _read(packet_ref), _read(review_ref)
    packet, review = load_json(packet_path), load_json(review_path)
    actual_mode = packet.get('mode'); _require(actual_mode in SCHEMAS and (mode is None or actual_mode == mode), 'real/controlled mode mismatch')
    _require(packet.get('schema_version') == SCHEMAS[actual_mode][0] and review.get('schema_version') == SCHEMAS[actual_mode][1]
             and packet.get('version') == VERSION and packet.get('QC_approval') is False, 'schema/version mismatch')
    allowed = {'schema_version', 'packet_sha256', 'completed', 'reviewer', 'reviewed_at', 'expires_at', 'checks', 'reason',
               'registered_business_id', 'role_observations', 'history_comparisons', 'provenance'}
    _require(set(review) == allowed and review.get('completed') is True and review['packet_sha256'] == packet_ref['sha256'], 'unreviewed, extra self-declared identity, or changed packet')
    reviewed, expiry = timestamp(review.get('reviewed_at')), timestamp(review.get('expires_at'))
    _require(review.get('reviewed_at') is not None and review.get('expires_at') is not None
             and packet['created_at'] <= reviewed < expiry <= timestamp(packet['capability']['expires_at']), 'review timing invalid/extends capability expiry')
    _require(set(review.get('checks', {})) == set(CHECKS) and all(value == 'PASS' for value in review['checks'].values())
             and _text(review.get('reason')), 'FAIL/uncertainty/missing checks are not admission')
    source = packet.get('source_identity')
    observer = source.get('snapshot.js') if isinstance(source, dict) else None
    _require(isinstance(observer, str) and re.fullmatch(r'[0-9a-f]{64}', observer),
             'bound packet observer identity missing or malformed')
    # Historical meaning is recompiled against its own SHA-bound observation.
    # Live entry still compiles with the current observer and checks all sources.
    _require(packet['task'] == _base(task) and packet['roles'] == _native_roles(
                 packet['capability'], packet['spec'], task,
                 _observer_sha256=None if live else observer)
             and packet.get('meaning') == descriptor(packet), 'compiled proposal/roles/meaning changed')
    pairs = [_frame(frame, actual_mode) for frame in packet['frames']]
    _require(all(capture.get('observer_sha256') == observer for _, capture in pairs),
             'observation used a different frozen observer')
    states = [state for state, _ in pairs]
    observed = review['role_observations']
    _require(isinstance(observed, list) and len(observed) == len(packet['roles']), 'every actual role requires observation')
    for index, row in enumerate(observed):
        _require(set(row) == {'role_index', 'frame_index', 'observation'} and row['role_index'] == index
                 and type(row['frame_index']) is int and 0 <= row['frame_index'] < len(states)
                 and _text(row['observation']), 'missing/ambiguous role observation')
        role, state = packet['roles'][index], states[row['frame_index']]
        _require(re.sub(r'\s+', '', role['label']) in re.sub(r'\s+', '', state['visible_text']), 'role label not painted in referenced original frame')
        if role['kind'] in ('input', 'submit'):
            matches = [element for element in state['elements'] if element.get('text') == role['label']
                       and element.get('visible') is True and element.get('enabled') is True
                       and (element.get('inputable') if role['kind'] == 'input' else element.get('clickable'))]
            _require(len(matches) == 1, 'role has no unambiguous visible enabled control in original tree')
    expected = [row['id'] for row in packet['history_context']['comparisons']]
    comparisons = review['history_comparisons']
    _require(isinstance(comparisons, list) and len(comparisons) == len(expected)
             and [row.get('id') for row in comparisons] == expected, 'whole frozen history comparison coverage missing')
    _require(all(set(row) == {'id', 'relation', 'reason'} and row['relation'] == 'DISTINCT' and _text(row['reason']) for row in comparisons), 'same business, parameter variant or uncertain historical comparison rejects')
    legacy = review['registered_business_id']
    _require(legacy is None or legacy in _registered_ids(), 'arbitrary business ID cannot self-approve new inventory')
    _review_source(packet, review)
    signature = object_sha256({'strategy': legacy}) if legacy else object_sha256({'admitted_form_meaning': packet['meaning']})
    if live:
        current = timestamp(current)
        _require(reviewed <= current < expiry, 'review expired or future')
        validate_capability(packet['capability'], now=current, require_ready=True)
        from .task_generation import generation_source_identity
        _require(packet['source_identity'] == generation_source_identity(), 'admission source version changed')
    return packet, review, signature


def attach(task, packet_ref, review_ref, live_context, *, mode, now=None):
    packet, _, signature = _validate(packet_ref, review_ref, task, current=now, live=True, mode=mode)
    _require(packet['history_context'] == live_context, 'frozen customer/registry history drift; obtain a new bound review')
    result = deepcopy(task)
    result['task_admission'] = {'version': VERSION, 'packet': deepcopy(packet_ref), 'review': deepcopy(review_ref),
                                'semantic_signature': signature, 'mode': mode, 'QC_approval': False}
    return result


def static_identity(task):
    binding = task.get('task_admission', {})
    _require(set(binding) == {'version', 'packet', 'review', 'semantic_signature', 'mode', 'QC_approval'}
             and binding.get('version') == VERSION and binding.get('QC_approval') is False, 'admission binding malformed')
    _, _, signature = _validate(binding['packet'], binding['review'], task, mode=binding['mode'])
    _require(binding['semantic_signature'] == signature, 'admission semantic signature changed')
    return signature


def verify_live(task, live_context, *, mode, now=None):
    binding = task['task_admission']
    attached = attach(_base(task), binding['packet'], binding['review'], live_context, mode=mode, now=now)
    _require(attached == task, 'live admission task/binding changed')
    return static_identity(task)


def verify_collection_entry(plan, registry, capture_output):
    """Recheck real reviewed tasks before direct collection can allocate or navigate.

    The generation wrapper owns the directory immediately above ``capture``.
    Its original history and exact bootstrap are also required for own resume;
    static identity alone never grants dispatch permission.
    """
    admitted = [task for task in plan.get('tasks', []) if 'task_admission' in task]
    if not admitted:
        return
    from .task_generation import (generation_source_identity, read_customer_history,
                                  bind_formal_history, verify_task_admissions)
    generation = plan.get('generation', {})
    _require(generation.get('mode') == 'real', 'direct admission collection requires real generation')
    sources = generation_source_identity()
    _require(generation.get('source_identity') == sources, 'generation source changed before direct collection')
    capture = Path(capture_output).resolve()
    _require(Path(capture_output).name == 'capture' and capture.name == 'capture',
             'admitted direct output must be the generation wrapper output/capture; use generation execute')
    scope = generation.get('history_scope')
    from .current_chain import SCOPE_SCHEMA
    _require(isinstance(scope, dict) and scope.get('schema_version') in ('webcollect-task-history-scope-1', SCOPE_SCHEMA),
             'direct admission collection requires frozen original history')
    manifest = _read(scope.get('manifest'))
    history, current_scope = read_customer_history(manifest)
    current_scope = bind_formal_history(current_scope)
    _require(current_scope == scope, 'formal LATEST/customer history changed before direct collection')
    records = []
    for task in admitted:
        packet = load_json(_read(task['task_admission']['packet']))
        _require(packet.get('mode') == 'real', 'controlled packet cannot enter real direct collection')
        if packet['capability'] not in records:
            records.append(packet['capability'])
    verify_task_admissions(plan, {'records': records}, registry, capture.parent,
                           customer_history=history, history_scope=current_scope)
    _require(generation_source_identity() == sources, 'source changed during direct admission validation')
    return {'machine_status': 'PASS', 'scope': 'live admission binding only; not QC approval',
            'admitted_tasks_checked': len(admitted), 'history_records_checked': len(history)}


def load_reviews(paths):
    """Resolve explicit packet+review pairs; duplicates never overwrite one another."""
    result = {}
    for path in paths or []:
        manifest = load_json(path)
        _require(manifest.get('schema_version') == 'webcollect-task-admission-references-1', 'review reference manifest schema invalid')
        for row in manifest.get('reviews', []):
            packet = load_json(_read(row['packet']))
            key = object_sha256({'capability': packet['capability'], 'spec': packet['spec']})
            _require(key not in result, 'duplicate admission reference')
            result[key] = row
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--spec', type=Path, required=True, help='One existing ordinary-form SPEC_SCHEMA task object')
    parser.add_argument('--capability-id', required=True)
    parser.add_argument('--history-set', type=Path, required=True)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--frames', type=Path, required=True, help='JSON array of original image/state/capture references')
    parser.add_argument('--producer-context-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    from .task_generation import read_customer_history, bind_formal_history, compile_form
    catalog, spec = load_json(args.catalog), load_json(args.spec)
    matches = [record for record in catalog['records'] if record['capability_id'] == args.capability_id]
    _require(len(matches) == 1 and catalog['mode'] == 'real', 'CLI prepares explicit real capability only')
    records, history = read_customer_history(args.history_set); history = bind_formal_history(history)
    task = compile_form(matches[0], spec)
    result = prepare_packet(matches[0], spec, task, context(history, records, args.registry), load_json(args.frames),
                            args.output, mode='real', producer_context_id=args.producer_context_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _action_core(operation):
    return {'action_type': operation['action_type'], 'selector': operation.get('selector'),
            'index': operation.get('index', 0), 'arguments': operation.get('arguments', {}),
            'target_label': operation.get('evidence', {}).get('target_label')}


def _terminal_target(state, selector):
    targets = [row for row in state.get('assertion_targets', [])
               if row.get('selector') == selector and row.get('index', 0) == 0]
    _require(targets and all(row == targets[0] for row in targets), 'missing/ambiguous synchronized terminal visibility observation')
    return targets[0]


def _flow_record(spec, mode):
    view = spec.get('completion_view')
    _require(isinstance(view, dict) and set(view) == {'schema_version', 'record'}
             and view['schema_version'] == 'webcollect-bound-completion-view-1', 'unbound completion scroll is forbidden')
    record = load_json(_read(view['record']))
    expected = 'webcollect-observed-form-functional-flow-1' if mode == 'real' else 'webcollect-controlled-form-functional-flow-1'
    _require(record.get('schema_version') == expected and record.get('mode') == mode
             and record.get('initial_url') == spec['page_uri'], 'completion-view source/mode/exact URI mismatch')
    return record


def completion_scroll(capability, spec, operations, assertions, *, _observer_sha256=None):
    """Compile one observed necessary view action, never an arbitrary step pad."""
    _require(not spec.get('widget_adapter') and not spec.get('deterministic_strategy'), 'completion-view proof is for reviewed ordinary groups only')
    mode = capability.get('mode'); _require(mode in SCHEMAS, 'completion-view execution mode required')
    record = _flow_record(spec, mode)
    frames = record.get('frames', []); actions = record.get('action_refs', [])
    _require(len(actions) == len(operations) and len(frames) == len(actions) + 2, 'functional action/frame sequence incomplete')
    pairs = [_frame(frame, mode) for frame in frames]; states = [pair[0] for pair in pairs]
    _require(all(state.get('url') == spec['page_uri'] for state in states), 'functional frames changed exact page')
    from .task_generation import generation_source_identity
    observer = generation_source_identity()['snapshot.js'] if _observer_sha256 is None else _observer_sha256
    _require(isinstance(observer, str) and re.fullmatch(r'[0-9a-f]{64}', observer),
             'functional observer identity missing or malformed')
    _require(all(capture.get('observer_sha256') == observer for _, capture in pairs), 'functional observer/source drift')
    _require(all(state.get('scroll') == states[0].get('scroll') for state in states[:-1]), 'unrecorded view actions precede completion')
    for index, (action_ref, operation) in enumerate(zip(actions, operations)):
        actual = load_json(_read(action_ref))
        _require(actual.get('ordinal') == index + 1 and actual.get('before_frame') == index
                 and actual.get('after_frame') == index + 1 and actual.get('dispatch_returned') is True
                 and actual.get('before_state_sha256') == frames[index]['state']['sha256']
                 and actual.get('after_state_sha256') == frames[index + 1]['state']['sha256']
                 and actual.get('pre_execute_same_state', {}).get('matched') is True
                 and _action_core(actual.get('operation', {})) == _action_core(operation), 'observed functional action/parameters/frame order mismatch')
        prepared = actual.get('prepared_element', {})
        _require(prepared.get('visible') is True and prepared.get('enabled') is True,
                 'functional action target was not usable')
        if operation['action_type'] == 'click' and prepared.get('inputable'):
            _require(actual['pre_execute_same_state'].get('target', {}).get('focused') is False,
                     'redundant focus cannot become a necessary action')
    source = load_json(_read(record['source_summary']))
    observed_status = 'REAL_FUNCTIONAL_OBSERVATION_PASS_REVIEW_REQUIRED' if mode == 'real' else 'PASS'
    _require(source.get('status') == observed_status and source.get('failure') is None
             and source.get('controlled_saved_html_mode') is (mode == 'synthetic')
             and source.get('actual_frame_count') == len(frames)
             and source.get('explicit_actions_dispatched') == len(actions)
             and source.get('necessary_scrolls_dispatched') == 1
             and source.get('initial_gate_pass') is True and source.get('terminal_oracle_visibility_pass') is True,
             'functional observation did not establish this exact successful view transition')
    events = [json.loads(line) for line in _read(record['scroll_log']).read_text().splitlines() if line.strip()]
    starts = [row for row in events if row.get('action') == 'necessary_result_scroll_start']
    finishes = [row for row in events if row.get('action') == 'necessary_result_scroll_finished']
    _require(len(starts) == len(finishes) == 1, 'exactly one observed necessary result scroll required')
    operation = starts[0].get('operation', {})
    distance = operation.get('execution', {}).get('distance')
    _require(operation.get('action_type') == 'scroll' and operation.get('arguments') == {'direction': 'down'}
             and type(distance) is int and 1 <= distance <= 480
             and starts[0].get('same_state', {}).get('matched') is True
             and finishes[0].get('frame') == len(frames) - 1
             and finishes[0].get('scroll') == states[-1].get('scroll'), 'missing actual bounded scroll dispatch/finish evidence')
    before, after = states[-2], states[-1]
    _require(after['scroll'][0] == before['scroll'][0] and after['scroll'][1] - before['scroll'][1] == distance,
             'scroll distance differs from actual viewport displacement')
    selector = spec['completion']['selector']; first = _terminal_target(before, selector); last = _terminal_target(after, selector)
    height = before['screen_resolution'][1]; width = before['screen_resolution'][0]
    box = first.get('bbox', [])
    _require(len(box) == 4 and first.get('visible') is False and _text(first.get('text'))
             and box[0] >= 0 and box[2] <= width and box[1] >= 0 and box[3] > height,
             'already fully visible, empty, covered or unrelated terminal cannot justify extra scrolling')
    box = last.get('bbox', [])
    _require(last.get('visible') is True and len(box) == 4 and 0 <= box[0] < box[2] <= width
             and 0 <= box[1] < box[3] <= height, 'scroll did not reveal complete result in original frame')
    _require(assertions and all(condition.get('selector') == selector and 'contains' in condition
                               and condition['contains'] in last.get('text', '') for condition in assertions),
             'observed final result does not satisfy frozen proposal assertions')
    return {'operation_id': 'reveal-complete-result', 'subgoal_id': 'result', 'action_type': 'scroll',
            'selector': selector, 'arguments': {'direction': 'down'},
            'execution': {'distance': distance, 'settle_ms': 500},
            'goal': '向下滚动，完整查看计算结果',
            'rationale': '真实功能观测的结果下半部超出视口，需一次有界滚动才能完整核验',
            'expected': '完整显示已生成的计算结果', 'postconditions': deepcopy(assertions),
            'completion_view': deepcopy(spec['completion_view'])}


def validate_live_completion_scroll(task, operation, state):
    """The collector calls this on the synchronized pre-action original frame."""
    _require(operation.get('completion_view') and task.get('task_admission'), 'view scroll needs current reviewed admission')
    packet = load_json(_read(task['task_admission']['packet']))
    record = _flow_record(packet['spec'], packet['mode'])
    _require(operation == packet['task']['operations'][-1], 'current scroll differs from frozen compiled operation')
    before = _frame(record['frames'][-2], packet['mode'])[0]
    expected = _terminal_target(before, packet['spec']['completion']['selector'])
    actual = _terminal_target(state, packet['spec']['completion']['selector'])
    _require(state.get('url') == packet['spec']['page_uri'] and state.get('scroll') == before.get('scroll'),
             'current page/viewport differs from observed necessary view transition')
    _require(actual.get('visible') is False, 'PADDING_SCROLL: terminal is already completely visible')
    box = actual.get('bbox', []); width, height = state.get('screen_resolution', [0, 0])
    _require(len(box) == 4 and 0 <= box[0] < box[2] <= width and box[1] >= 0 and box[3] > height
             and _text(actual.get('text')) and re.sub(r'\s+', '', actual['text']) == re.sub(r'\s+', '', expected['text']),
             'current result is not the same generated, clipped terminal; no speculative scroll')
    _require(operation.get('completion_view') == packet['spec']['completion_view'], 'view operation lost frozen proof binding')
    return {'machine_status': 'PASS', 'scope': 'one necessary result-view action only; not semantic/QC approval',
            'observed_before_result_bbox': box, 'proof': packet['spec']['completion_view']['record']}


if __name__ == '__main__':
    raise SystemExit(main())
