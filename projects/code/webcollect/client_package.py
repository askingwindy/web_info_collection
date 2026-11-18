"""Customer layout export. Copies evidence bytes; never manufactures review or truth."""
import copy
import csv
from collections import Counter
from datetime import datetime, timezone
import hashlib
from webcollect import workspace_json as json
import re
import shutil
import tempfile
from pathlib import Path
from PIL import Image
from .metadata import COLUMNS
from .validate import SCHEMAS, StrictValidator, read_json
from .task_instruction import validate_task_instruction
from .action_normalization import ACTUAL_KEYBOARD_VERSION, normalize_delivery_step

ROOT_FILES = {'README.md', 'metadata.csv', 'qc_report.md', 'SHA256SUMS', 'site-list.json',
              '附件A-字段说明.md', '附件B-动作空间与坐标系.md', '合成方式说明.md',
              '来源与合规说明.md', '动作空间与系统提示.md'}
EXECUTION_FILE = 'actual-execution.json'
EXECUTION_VERSION = 'actual-execution'
CHECKS = {'visual_alignment', 'terminal_semantics', 'language', 'privacy', 'substantive_difference'}
PARAMS = {'click': {'x', 'y'}, 'double_click': {'x', 'y'}, 'right_click': {'x', 'y'},
          'type': {'text'}, 'hotkey': {'keys'}, 'scroll': {'x', 'y', 'direction'},
          'drag': {'x', 'y', 'end_x', 'end_y'}, 'back': set(), 'open_url': {'url'},
          'select': {'x', 'y', 'option'}, 'wait': set(), 'complete': {'status'}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def safe_name(value):
    if (not isinstance(value, str) or not value.strip() or value in ('.', '..') or
            any(c in value for c in ('/', '\\')) or any(ord(c) < 32 for c in value)):
        raise ValueError('Unsafe sample or site ID: ' + repr(value))
    return value


def real_file(path, base):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(base.resolve()):
        raise ValueError('Missing, symbolic, or escaping source file: ' + str(path))
    if any(p.is_symlink() for p in path.parents if p.is_relative_to(base)):
        raise ValueError('Symbolic source directory: ' + str(path))
    return path


def sample_hashes(sample):
    return {p.relative_to(sample).as_posix(): sha(real_file(p, sample))
            for p in sorted(sample.rglob('*')) if p.is_file() or p.is_symlink()}


def validate_client_sample(sample, *, allow_legacy_narrative=False, allow_legacy_hotkeys=False):
    """Annex A/B structural contract, without producer-only ID/source constants."""
    sample = Path(sample)
    data = read_json(real_file(sample / 'annotation.json', sample))
    schema = copy.deepcopy(json.loads(SCHEMAS.joinpath('annotation.schema.json').read_text()))
    schema['properties']['sample_id'] = {'type': 'string', 'minLength': 1}
    source = schema['properties']['trajectory_source']['properties']
    source['source_type'] = {'enum': ['human', 'agent', 'human_agent_hybrid']}
    source['data_type'] = {'type': 'string', 'minLength': 1}
    source['action_space'] = {'type': 'string', 'minLength': 1}
    errors = list(StrictValidator(schema).iter_errors(data))
    if errors:
        raise ValueError('Invalid customer annotation ' + str(sample) + ': ' + errors[0].message)
    if not allow_legacy_narrative:
        validate_task_instruction(data['task_instruction'])
    if safe_name(data['sample_id']) != sample.name:
        raise ValueError('Sample directory and sample_id differ')
    dtype = data['trajectory_source']['data_type']
    if not dtype.strip() or '\n' in dtype or '\r' in dtype or any(ord(c) < 32 for c in dtype):
        raise ValueError('Unsafe data_type chapter name')
    if data['terminal_type'] != 'Web':
        raise ValueError('This exporter supports Web trajectories')
    if {p.name for p in sample.iterdir()} != {'annotation.json', 'images', 'ui_tree'}:
        raise ValueError('A sample must contain only annotation.json, images/, ui_tree/')
    if not all((sample / d).is_dir() and not (sample / d).is_symlink() for d in ('images', 'ui_tree')):
        raise ValueError('Sample asset folders must be real directories')
    if {p.relative_to(sample).as_posix() for p in sample.rglob('*') if p.is_dir()} != {'images', 'ui_tree'}:
        raise ValueError('Sample asset folders must not contain extra directories')
    expected = {'annotation.json'}
    res = data['device_info']['screen_resolution']
    if data['app_info']['ui_language'] != 'zh' or data['completion_status'] == 'failed':
        raise ValueError('Customer delivery requires Chinese UI and a completed trajectory')
    effective = sum(s['action']['action_type'] not in ('wait', 'complete') for s in data['steps'])
    from .closing_policy import annotation_errors
    ending_errors=annotation_errors(data)
    if ending_errors:raise ValueError('; '.join(ending_errors))
    if effective < 5 and not (data.get('short_flow') is True and data.get('short_flow_reason', '').strip()):
        raise ValueError('Fewer than five effective actions require a short-flow reason')
    if data.get('short_flow') is True and (effective >= 5 or not data.get('short_flow_reason', '').strip()):
        raise ValueError('Invalid short-flow declaration')
    if data['steps'][-1]['action']['action_type'] != 'complete':
        raise ValueError('Customer delivery must end with complete(success)')
    generic_goal = re.sub(r'[\s，。！：、]', '', data['steps'][-1]['user_goal'])
    if not allow_legacy_narrative and generic_goal in {'确认最终页面符合任务要求', '确认任务完成', '确认最终状态', '完成任务'}:
        raise ValueError('Final user_goal must identify the actual page/content, not a generic confirmation')
    calls = set()
    for n, step in enumerate(data['steps'], 1):
        action = step['action']; call = step['tool_call']; name = action['action_type']; args = call['arguments']
        if step['step_id'] != n or name not in PARAMS or call['tool_name'] != name or set(args) != PARAMS[name]:
            raise ValueError('Step numbering or Annex B action/parameter mismatch')
        if call['call_id'] in calls or not call['call_id'].strip():
            raise ValueError('Tool call IDs must be nonempty and unique')
        calls.add(call['call_id'])
        if call['timestamp']:
            try:
                if datetime.fromisoformat(call['timestamp'].replace('Z', '+00:00')).tzinfo is None:
                    raise ValueError('Missing timezone')
            except ValueError as error:
                raise ValueError('Tool timestamp must be ISO8601 with timezone, or empty') from error
        if step['tool_result']['status'] != 'success' or step['tool_result']['error']:
            raise ValueError('Every delivered tool result must be success without an error')
        if n < len(data['steps']) and 'screen_changed' not in step['tool_result']['return_value']:
            raise ValueError('Nonterminal steps require screen_changed')
        for key in ('x', 'y', 'end_x', 'end_y'):
            if key in args and type(args[key]) is not int:
                raise ValueError('Coordinates must be integer screenshot pixels')
        for key in ('text', 'url', 'option', 'direction', 'status'):
            if key in args and not isinstance(args[key], str):
                raise ValueError('Action string parameter has wrong type')
        if 'x' in args and (action['coordinate'] != [args['x'], args['y']] or
                            not (0 <= args['x'] < res[0] and 0 <= args['y'] < res[1])):
            raise ValueError('Pointer is outside screenshot or differs from action.coordinate')
        if 'x' not in args and action['coordinate']:
            raise ValueError('Non-pointer coordinate must be empty')
        if name == 'drag' and (action.get('end_coordinate') != [args['end_x'], args['end_y']] or
                               not (0 <= args['end_x'] < res[0] and 0 <= args['end_y'] < res[1])):
            raise ValueError('Drag end coordinate differs or lies outside screenshot')
        if name != 'drag' and 'end_coordinate' in action:
            raise ValueError('Only drag can have end_coordinate')
        box = action.get('target_bbox')
        if box is not None and not (0 <= box[0] < box[2] <= res[0] and 0 <= box[1] < box[3] <= res[1]):
            raise ValueError('Action target bbox lies outside screenshot')
        if name in {'scroll', 'wait', 'back', 'open_url', 'complete'} and (
                action['target_element_id'] or action['target_text'] or box is not None or action.get('target_control_type')):
            raise ValueError('Non-control action must not claim a target control')
        if name == 'hotkey' and (action['target_element_id'] or box is not None or
                                 action.get('target_control_type') or not action['target_text']):
            raise ValueError('Hotkey must name keys without claiming a target control')
        if name == 'scroll' and args['direction'] not in ('up', 'down', 'left', 'right'):
            raise ValueError('Invalid scroll direction')
        if name == 'hotkey' and (not isinstance(args['keys'], list) or not args['keys'] or
                                any(not isinstance(k, str) or not k for k in args['keys']) or
                                action['input_text'] != '+'.join(args['keys'])):
            raise ValueError('Hotkey input_text must preserve actual keys')
        if not allow_legacy_hotkeys and normalize_delivery_step(step, data['device_info'].get('os_name')) != step:
            raise ValueError('Actual keyboard delivery requires matching keys, input_text and key display')
        if name == 'type' and action['input_text'] != args['text']:
            raise ValueError('Type input_text differs from executed text')
        if name not in ('type', 'hotkey') and action['input_text']:
            raise ValueError('Non-input action must have empty input_text')
        if name == 'complete' and (n != len(data['steps']) or args['status'] != 'success'):
            raise ValueError('Complete must be the final step with status success')
        if step['image_path'] != f'images/step_{n:03}.png':
            raise ValueError('Step image path must use images/step_NNN.png')
        expected.add(step['image_path'])
        with Image.open(real_file(sample / step['image_path'], sample)) as image:
            if image.format != 'PNG' or list(image.size) != res:
                raise ValueError('PNG resolution differs from annotation')
            image.verify()
        if not step['ui_tree_path']:
            raise ValueError('Every Web delivery step requires a synchronized UI tree')
        if step['ui_tree_path']:
            if step['ui_tree_path'] != f'ui_tree/step_{n:03}.json':
                raise ValueError('Tree path must use ui_tree/step_NNN.json')
            expected.add(step['ui_tree_path'])
            tree = read_json(real_file(sample / step['ui_tree_path'], sample))
            errors = list(StrictValidator(json.loads(SCHEMAS.joinpath('ui_tree.schema.json').read_text())).iter_errors(tree))
            if errors or tree['image_path'] != step['image_path'] or tree['screen_resolution'] != res:
                raise ValueError('Tree schema or image/resolution synchronization mismatch')
            elements = {e['element_id']: e for e in tree['elements']}
            if len(elements) != len(tree['elements']):
                raise ValueError('Duplicate tree element ID')
            for e in elements.values():
                b = e['bbox']
                if not (0 <= b[0] < b[2] <= res[0] and 0 <= b[1] < b[3] <= res[1]):
                    raise ValueError('Tree bbox lies outside screenshot pixels')
                if not e['visible'] or e['element_id'] == 'root':
                    raise ValueError('Only visible elements with non-reserved IDs may be delivered')
                seen = {e['element_id']}; parent = e['parent_id']
                while parent != 'root':
                    if parent not in elements or parent in seen:
                        raise ValueError('Tree parent is missing or cyclic')
                    seen.add(parent); parent = elements[parent]['parent_id']
            target_id = action['target_element_id']
            if name in {'click', 'double_click', 'right_click', 'type', 'drag', 'select'} and not target_id:
                raise ValueError('Control actions require a synchronized target ID and bbox')
            if target_id:
                target = elements.get(target_id)
                if not target or target['text'] != action['target_text'] or target['bbox'] != action.get('target_bbox'):
                    raise ValueError('Action target and synchronized tree differ')
                if not target['enabled'] or (name == 'type' and not target['inputable']):
                    raise ValueError('Target must be enabled and accept the requested action')
                if action.get('target_control_type') and action['target_control_type'] != target['element_type']:
                    raise ValueError('Target control type differs from synchronized tree')
                if 'x' in args:
                    b = target['bbox']
                    if not (b[0] <= args['x'] < b[2] and b[1] <= args['y'] < b[3]):
                        raise ValueError('Pointer lies outside target bbox')
        elif action['target_element_id']:
            raise ValueError('A sample without a tree cannot reference tree element IDs')
    final = data.get('final_state_image', '')
    if final != data['steps'][-1]['image_path']:
        raise ValueError('Web final_state_image must identify the final step screenshot')
    if final:
        if Path(final).parent.as_posix() != 'images':
            raise ValueError('Final image must stay inside images/')
        with Image.open(real_file(sample / final, sample)) as image:
            if image.format != 'PNG' or list(image.size) != res:
                raise ValueError('Final PNG resolution differs from annotation')
            image.verify()
        expected.add(final)
    if final and data['steps'][-1]['action']['action_type'] == 'complete' and final != data['steps'][-1]['image_path']:
        raise ValueError('Complete final_state_image must identify final step screenshot')
    if set(sample_hashes(sample)) != expected:
        raise ValueError('Sample contains unreferenced or missing files')
    return data


def _unavailable_execution(record):
    data = record['data']
    return {'sample_id': data['sample_id'],
            'annotation_sha256': record.get('hashes', {}).get('annotation.json'),
            'platform': data['device_info'].get('os_name', ''),
            'steps': [{'step_id': step['step_id'], 'tool_name': step['tool_call']['tool_name'],
                       'arguments': copy.deepcopy(step['tool_call']['arguments']),
                       'status': 'HOST_TERMINAL' if step['action']['action_type'] == 'complete' else 'UNAVAILABLE'}
                      for step in data['steps']]}


def _execution_record(record, supplied=None):
    """Bind delivered actions to immutable dispatches; never fix their values.

    Supplied entries use sample_id/annotation_sha256/platform/steps. Each actual
    step contains step_id/tool_name/arguments and dispatch_ref/raw_step_ref
    {path,sha256}; the latter proves successful execution of that dispatch.
    Only the whitelisted operation fields are copied into the customer file.
    """
    data = record['data']; sid = record['sample_id']
    if supplied is not None:
        if (supplied.get('sample_id') != sid or
                supplied.get('annotation_sha256') != record['hashes']['annotation.json'] or
                supplied.get('platform') != data['device_info'].get('os_name', '')):
            raise ValueError('Actual execution source annotation/platform binding differs')
        entries = supplied['steps']
    else:
        raw_root = record['batch'] / 'evidence' / sid / 'raw'
        if (raw_root / 'raw-receipt.json').is_file():
            from .postprocess import session_record, effective_trajectory
            raw = session_record(raw_root)
            rows = effective_trajectory(raw)
            entries = [{'step_id': index, 'tool_name': row['action'],
                        'arguments': row['arguments'], 'dispatch_ref': row['dispatch'],
                        'raw_step_ref': row['raw_step']}
                       for index, row in enumerate(rows, 1)]
        elif (record['batch'] / EXECUTION_FILE).is_file():
            validate_execution_attachment(record['batch'])
            matches = [row for row in read_json(record['batch'] / EXECUTION_FILE)['samples'] if row['sample_id'] == sid]
            if len(matches) != 1:
                raise ValueError('Actual execution attachment sample missing')
            return copy.deepcopy(matches[0])
        else:
            result = _unavailable_execution(record)
            if any(step['action']['action_type'] == 'hotkey' for step in data['steps']):
                raise ValueError('Actual hotkey dispatch evidence missing; do not infer keys from OS')
            return result
    mapping = {row['step_id']: row for row in entries}
    business = [step for step in data['steps'] if step['action']['action_type'] != 'complete']
    if len(mapping) != len(entries) or set(mapping) != {step['step_id'] for step in business}:
        raise ValueError('Actual execution step coverage differs')
    result = _unavailable_execution(record)
    for step, actual in zip(data['steps'], result['steps']):
        if step['action']['action_type'] == 'complete':
            continue
        row = mapping[step['step_id']]; ref = row['dispatch_ref']
        path = Path(ref['path'])
        if (path.is_symlink() or not path.is_file() or
                not re.fullmatch('[0-9a-f]{64}', str(ref.get('sha256', ''))) or sha(path) != ref['sha256']):
            raise ValueError('Actual dispatch original file/hash differs')
        dispatch = read_json(path); operation = dispatch.get('operation', {})
        if (operation.get('action_type') != row['tool_name'] or
                operation.get('arguments') != row['arguments'] or
                step['tool_call']['tool_name'] != row['tool_name'] or
                step['tool_call']['arguments'] != row['arguments']):
            raise ValueError('Delivered action differs from actual dispatch; explicit revision required')
        execution_ref = row['raw_step_ref']; execution_path = Path(execution_ref['path'])
        if (execution_path.is_symlink() or not execution_path.is_file() or
                sha(execution_path) != execution_ref.get('sha256')):
            raise ValueError('Actual execution receipt hash differs')
        execution = read_json(execution_path)
        if (execution.get('dispatched') is not True or execution.get('action_executed') is not True or
                execution.get('postconditions_checked') is not True or execution.get('execution_error') or
                execution.get('controller_dispatch', {}).get('sha256') != ref['sha256'] or
                execution.get('operation') != operation):
            raise ValueError('Dispatch lacks matching successful actual execution receipt')
        actual['execution_ref'] = {'file': execution_path.name, 'sha256': execution_ref['sha256']}
        actual.update(status='VERIFIED_DISPATCH', dispatch_ref={
            'file': path.name, 'sha256': ref['sha256']},
            operation_id=operation.get('operation_id', ''))
    return result


def validate_execution_attachment(root):
    """Validate the public minimal receipt without reading private raw logs."""
    root = Path(root); document = read_json(root / EXECUTION_FILE)
    if (set(document) != {'schema_version', 'keyboard_policy', 'samples'} or
            document['schema_version'] not in (EXECUTION_VERSION, 'webcollect-actual-execution-1') or
            document['keyboard_policy'] != ACTUAL_KEYBOARD_VERSION or
            not isinstance(document['samples'], list)):
        raise ValueError('Invalid actual execution attachment version')
    rows = document['samples']; ids = {p.name for p in (root / 'samples').iterdir()}
    if len({row['sample_id'] for row in rows}) != len(rows) or {row['sample_id'] for row in rows} != ids:
        raise ValueError('Actual execution sample coverage differs')
    for row in rows:
        if set(row) != {'sample_id', 'annotation_sha256', 'platform', 'steps'}:
            raise ValueError('Actual execution sample contains unsupported fields')
        sample = root / 'samples' / safe_name(row['sample_id'])
        annotation = read_json(sample / 'annotation.json')
        if (sha(sample / 'annotation.json') != row['annotation_sha256'] or
                row['platform'] != annotation['device_info'].get('os_name', '') or
                len(row['steps']) != len(annotation['steps'])):
            raise ValueError('Actual execution annotation/platform/step binding differs')
        for step, actual in zip(annotation['steps'], row['steps']):
            status = actual.get('status')
            fields = {'step_id', 'tool_name', 'arguments', 'status'}
            if status == 'VERIFIED_DISPATCH':
                fields |= {'dispatch_ref', 'execution_ref', 'operation_id'}
                ref = actual.get('dispatch_ref', {})
                execution_ref = actual.get('execution_ref', {})
                if (set(execution_ref) != {'file', 'sha256'} or
                        safe_name(execution_ref['file']) != execution_ref['file'] or
                        not re.fullmatch('[0-9a-f]{64}', str(execution_ref['sha256']))):
                    raise ValueError('Invalid actual execution reference')
                if (set(ref) != {'file', 'sha256'} or safe_name(ref['file']) != ref['file'] or
                        not re.fullmatch('[0-9a-f]{64}', str(ref['sha256'])) or
                        not isinstance(actual.get('operation_id'), str)):
                    raise ValueError('Invalid original dispatch reference')
            elif status not in {'UNAVAILABLE', 'HOST_TERMINAL'}:
                raise ValueError('Unknown actual execution status')
            if (set(actual) != fields or actual['step_id'] != step['step_id'] or
                    actual['tool_name'] != step['tool_call']['tool_name'] or
                    actual['arguments'] != step['tool_call']['arguments'] or
                    (status == 'HOST_TERMINAL') != (step['action']['action_type'] == 'complete') or
                    (step['action']['action_type'] == 'hotkey' and status != 'VERIFIED_DISPATCH')):
                raise ValueError('Actual execution step differs or hotkey evidence missing')
    return document


def _discover(source):
    if (source / 'samples').is_dir():
        roots = [source]
    else:
        roots = [p for p in sorted(source.iterdir()) if p.is_dir() and (p / 'samples').is_dir()]
    if not roots:
        raise ValueError('No samples/ source found')
    records = []; seen = set()
    for batch in roots:
        if batch.is_symlink() or (batch / 'samples').is_symlink():
            raise ValueError('Symbolic sample source')
        manifest_path = batch / 'manifest.json'
        manifest = read_json(real_file(manifest_path, batch)) if manifest_path.exists() else None
        if manifest and manifest.get('sample_kind') == 'integration':
            raise ValueError('Synthetic integration batches cannot be exported as customer data')
        sites = manifest.get('sites', []) if manifest else []
        mapping = {}
        if (batch / 'site-list.json').exists():
            site_list = read_json(real_file(batch / 'site-list.json', batch))
            sites = site_list['sites']
            mapping = {r['sample_id']: r['site_id'] for r in site_list['samples']}
            actual_ids = {p.name for p in (batch / 'samples').iterdir()}
            if len(mapping) != len(site_list['samples']) or set(mapping) != actual_ids:
                raise ValueError('Source site-list has duplicate or unmatched samples')
            for site in sites:
                if (len(site.get('sample_ids', [])) != len(set(site.get('sample_ids', []))) or
                        set(site.get('sample_ids', [])) != {sid for sid, key in mapping.items() if key == site['site_id']}):
                    raise ValueError('Source site-list ownership mismatch')
        site_map = {s['site_id']: s for s in sites}
        if len(site_map) != len(sites):
            raise ValueError('Duplicate site ID in source')
        for sample in sorted((batch / 'samples').iterdir()):
            if not sample.is_dir() or sample.is_symlink():
                raise ValueError('Sample source must be a real directory')
            data = validate_client_sample(sample, allow_legacy_narrative=True, allow_legacy_hotkeys=True); sid = data['sample_id']
            if sid in seen:
                raise ValueError('Duplicate sample ID: ' + sid)
            seen.add(sid)
            site_id = mapping.get(sid)
            if site_id is None and manifest:
                attempts = [r for r in manifest.get('attempts', []) if r.get('sample_id') == sid and r.get('site_id')]
                site_id = attempts[-1]['site_id'] if attempts else sid.split('_sample_')[0]
            site = site_map.get(site_id)
            if not site or not all(isinstance(site.get(k), str) and site[k].strip() for k in ('site_id', 'uri', 'site_category')):
                raise ValueError('Missing explicit URI/category/site mapping for ' + sid)
            safe_name(site_id)
            if not re.match(r'^https?://[^\s/]+', site['uri']):
                raise ValueError('Invalid source site URI')
            from .trusted_prefix import projection_index
            prefix_index=projection_index(batch/'evidence'/sid)
            if prefix_index is not None:
                projection=read_json(prefix_index)
                truths=[batch/'evidence'/sid/projection['directory']/'ground_truth.json']
            else:
                truths = [p for p in (batch / 'ground_truth' / (sid + '.json'), batch / 'evidence' / sid / 'ground_truth.json') if p.exists()]
            if not truths:
                raise ValueError('Missing original capture ground truth for ' + sid)
            for truth in truths:
                real_file(truth, batch)
            if len({sha(p) for p in truths}) != 1:
                raise ValueError('Conflicting source truth files')
            truth = truths[0]; observed = read_json(truth)
            expected = [{'step_id': s['step_id'], 'element_id': s['action']['target_element_id'],
                         'text': s['action']['target_text'], 'bbox': s['action']['target_bbox']}
                        for s in data['steps'] if s['action'].get('target_element_id') and 'target_bbox' in s['action']]
            if observed != expected:
                raise ValueError('Original ground truth differs from annotation targets: ' + sid)
            hashes = sample_hashes(sample)
            raw_dir = batch / 'evidence' / sid
            raw_hashes = {p.relative_to(batch).as_posix(): sha(real_file(p, batch))
                          for p in sorted(raw_dir.rglob('*')) if p.is_file() or p.is_symlink()} if raw_dir.is_dir() else {}
            files = dict(raw_hashes)
            if (batch / EXECUTION_FILE).exists():
                files[EXECUTION_FILE] = sha(real_file(batch / EXECUTION_FILE, batch))
            if manifest:
                files['manifest.json'] = sha(manifest_path)
            records.append(dict(sample_id=sid, sample=sample, batch=batch, data=data, site=dict(site_id=site_id, uri=site['uri'], site_category=site['site_category']), truth=truth,
                                hashes=hashes, truth_sha256=sha(truth), raw_hashes=raw_hashes, source_files=files, manifest=manifest,
                                manifest_path=manifest_path if manifest else None))
        if manifest and isinstance(manifest.get('samples'), list) and set(manifest['samples']) != {r['sample_id'] for r in records if r['batch'] == batch}:
            raise ValueError('Manifest sample list differs from source samples/')
    return records


def _v2_review_records(repo, path, records, source, report_path):
    """Reuse the independent checker's intake against an inspected client directory.

    The report may contain rejected samples. Only a current PASS sample and an
    actual human PASS record can be selected; package-level PASS is not inferred.
    """
    if report_path is None:
        raise ValueError('qc-review-2 selection requires --selection-report from the actual client source')
    from .client_reports import _bound_report
    import importlib.util
    import importlib
    import sys
    report, _ = _bound_report(source, Path(report_path))
    # Keep the checker independent: load its real implementation, do not copy or
    # weaken its coverage/contract rules in the producer.
    package = Path(repo) / 'projects' / 'quality-inspector' / 'quality_inspector'
    name = '_webcollect_selection_qc'
    if not (package / '__init__.py').is_file():
        raise ValueError('Independent QC source is required for qc-review-2 selection')
    implementation = {file: sha(package / file) for file in ('__init__.py', 'contract.py',
        'format_checks.py', 'engine.py', 'reviews.py', 'profiles.py', 'duplicates.py',
        'cumulative.py', 'checksums.py', 'layout.py')}
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, package / '__init__.py',
                                                     submodule_search_locations=[str(package)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        module._selection_code_sha256 = implementation
    elif Path(sys.modules[name].__file__).resolve() != (package / '__init__.py').resolve():
        raise ValueError('Independent QC module path changed during selection')
    elif sys.modules[name]._selection_code_sha256 != implementation:
        raise ValueError('Independent QC implementation changed during selection process')
    contract = importlib.import_module(name + '.contract')
    review_rules = importlib.import_module(name + '.reviews')
    _, fingerprint = contract.fingerprint()
    if report.get('baseline', {}).get('config_sha256') != fingerprint:
        raise ValueError('Selection QC report uses a stale/different contract')
    byid, errors, migrated = review_rules.intake(path,
        [{'sample_id': row['sample_id'], 'sample_path': str(row['sample'])} for row in records], fingerprint)
    if errors or migrated:
        raise ValueError('Invalid current qc-review-2 selection records: ' + str(errors or migrated))
    rows = {row['sample_id']: row for row in report['samples']}
    for sid, review in byid.items():
        checks = {row['rule_id']: row for row in rows[sid].get('checks', [])}
        for key, value in review['checks'].items():
            check = checks.get('REVIEW_' + key.upper(), {})
            if (check.get('status') != value['status'] or check.get('reason') != value.get('note')
                    or check.get('reviewer') != review['reviewer']
                    or check.get('provenance') != review['provenance']):
                raise ValueError('Selection report does not contain the supplied review decision: ' + sid)
    return byid, read_json(path), rows


def _review_records(path, records, approved_only, baseline_sha256=None):
    if not path:
        if approved_only:
            raise ValueError('--approved-only requires --reviews')
        return {}, None
    export = read_json(path)
    if export.get('schema_version') not in ('qc-review-1', 'qc-review-2', 'qc-review') or not isinstance(export.get('records'), list):
        raise ValueError('Review export must be qc-review-1, qc-review-2 or qc-review')
    byid = {}; samples = {r['sample_id']: r for r in records}
    for review in export['records']:
        sid = review.get('sample_id')
        if sid in byid or sid not in samples:
            raise ValueError('Duplicate or unknown review sample: ' + str(sid))
        sample = samples[sid]
        evidence = {p: h for p, h in sample['hashes'].items() if p != 'annotation.json'}
        if review.get('annotation_sha256') != sample['hashes']['annotation.json'] or review.get('evidence_sha256') != evidence:
            raise ValueError('Review annotation/evidence binding mismatch: ' + sid)
        if baseline_sha256 is not None and review.get('baseline_sha256') != baseline_sha256:
            raise ValueError('Review customer baseline binding mismatch: ' + sid)
        byid[sid] = review
    return byid, export


def _approved(review):
    return (isinstance(review, dict) and review.get('reviewer', {}).get('kind') == 'human'
            and isinstance(review.get('reviewer', {}).get('name'), str) and bool(review['reviewer']['name'].strip())
            and isinstance(review.get('provenance'), dict)
            and all(isinstance(review['provenance'].get(k), str) and review['provenance'][k].strip()
                    for k in ('description', 'reviewed_at'))
            and all(review.get('checks', {}).get(k, {}).get('status') == 'PASS'
                    and isinstance(review['checks'][k].get('note'), str) and review['checks'][k]['note'].strip()
                    for k in CHECKS))


def render_qc_report(report):
    """Render a separately verified report, retaining its original dataset scope.

    This function does not verify report identity. A caller must bind dataset,
    root checksum manifest and all sample/evidence hashes before using it in a
    new export, then QC that new package separately.
    """
    return ('# 独立质检记录\n\n本报告的检查对象以dataset字段和报告内文件哈希为准。'
            '附入新目录不表示新目录已被检查；新目录仍须单独QC。客户验收仅以实际执行记录为准。\n\n```json\n'
            + json.dumps(report, ensure_ascii=False, indent=2) + '\n```\n')


def _documents(repo, out, records):
    authority = repo / 'request/web操作采集需求'
    for name in ('附件A-字段说明.md', '附件B-动作空间与坐标系.md'):
        shutil.copyfile(real_file(authority / name, repo), out / name)
    annex = (out / '附件B-动作空间与坐标系.md').read_text()
    dtypes = sorted({r['data']['trajectory_source']['data_type'] for r in records})
    chapters = []; descriptions = []
    for dtype in dtypes:
        origins = sorted({r['data']['trajectory_source']['source_type'] for r in records if r['data']['trajectory_source']['data_type'] == dtype})
        spaces = sorted({r['data']['trajectory_source']['action_space'] for r in records if r['data']['trajectory_source']['data_type'] == dtype})
        version = '实际声明的action_space版本为' + '、'.join(spaces) + '。'
        known = dtype == 'webcollect_agent_v1' and set(origins) <= {'agent', 'human_agent_hybrid'}
        chapters.append('\n## ' + dtype + '\n\n原始source_type为' + '、'.join(origins) + '。' + version + '本类型的输出动作格式采用第1节Web子集，坐标采用第2节。第3节是随附参考系统提示，不据此声称历史采集实际调用了该提示。' + ('本线为计划驱动采集；采集参数和原始记录在包外证据索引绑定。' if known else '原始操作/提示生成过程为待核验项；导出器没有改写来源或补造历史系统提示。') + '\n')
        descriptions.append('## ' + dtype + '\n\n来源身份保留为' + '、'.join(origins) + '。' + version + '同名动作格式章节见[动作空间与系统提示](动作空间与系统提示.md)。PNG和界面树按字节复制；标注中的快捷键保留实际执行键，不作跨平台功能替换，其他标注修订见包外追溯清单；导出器未进行新采集、模型重写或真人审核。' + ('本线采集状态差异模板的声明与离线标注修订须结合包外记录核验，不能将全部历史文字笼统称为模板生成。' if known else '历史文字生成方式和原始系统提示缺少可验证记录时保持UNKNOWN。') + '\n')
    (out / '动作空间与系统提示.md').write_text(annex + '\n' + '\n'.join(chapters))
    mapping = '\n## 动作映射与坐标\n\n输出采用附件B动作空间，坐标为原PNG像素。hotkey的keys与input_text保留实际执行键；Meta、Command与Ctrl不互换。历史delivery-windows-keys-2映射仅说明旧版本，不适用于本次输出。实际参数、平台、步骤与原派发哈希见actual-execution.json；原始日志、模型请求和网络头留在包外。附件中UNAVAILABLE表示缺原派发证据，不能当作已经核实。complete是宿主终态声明，不冒称浏览器派发。\n\n图像为动作前界面，末步complete同时为终态；结构自检不表示独立QC或客户验收通过。\n'
    (out / '合成方式说明.md').write_text('# 合成方式说明\n\n' + '\n'.join(descriptions) + mapping)
    capture_configuration = []
    for manifest_path in sorted({r['manifest_path'] for r in records if r['manifest_path']}):
        manifest = read_json(manifest_path)
        configuration = manifest.get('configuration', {})
        if not isinstance(configuration, dict):
            configuration = {}
        capture_configuration.append({
            'source_batch': manifest.get('batch_id', manifest_path.parent.name),
            'selected_samples': sum(r['manifest_path'] == manifest_path for r in records),
            'recorded_configuration': {key: configuration[key] for key in
                ['viewport', 'device_scale_factor', 'locale', 'timezone',
                 'task_interval_seconds', 'default_settle_ms'] if key in configuration},
            'configuration_is_not_a_full_network_frequency_audit': True,
        })
    (out / '来源与合规说明.md').write_text('# 来源与合规说明\n\n站点URI、类目与样本归属见[site-list.json](site-list.json)。来源身份逐条保留trajectory_source；导出器不访问网站、不登录、不推断授权许可。未记录的账号、实际网络访问频率和合规事实保持UNKNOWN。人工审核记录和原始总体分母留在包外，样本筛选不改写来源采集总体的通过率。\n\n## 已记录的捕获配置\n\n下列为原捕获清单实际记载的配置；配置间隔不是完整请求日志审计。来源未提供捕获清单时不补造配置。\n\n```json\n' + json.dumps(capture_configuration, ensure_ascii=False, indent=2) + '\n```\n')
    statistics = {
        'sample_count': len(records),
        'site_count': len({r['site']['site_id'] for r in records}),
        'site_sample_counts': dict(Counter(r['site']['site_id'] for r in records)),
        'categories': dict(Counter(r['site']['site_category'] for r in records)),
        'task_types': dict(Counter(t for r in records for t in r['data']['task_type'])),
        'step_counts': dict(Counter(len(r['data']['steps']) for r in records)),
        'effective_step_counts': dict(Counter(sum(s['action']['action_type'] not in ('wait', 'complete')
                                                  for s in r['data']['steps']) for r in records)),
        'frames': sum(len(r['data']['steps']) for r in records),
        'actions': dict(Counter(s['action']['action_type'] for r in records for s in r['data']['steps'])),
    }
    (out / 'README.md').write_text('# Web轨迹样本\n\n样本位于samples/<sample_id>/，每条仅有annotation.json、images和ui_tree。字段与动作见根目录附件A/B；原采集目标真值位于ground_truth/<sample_id>.json。站点归属见site-list.json，索引见metadata.csv；实际执行依据见actual-execution.json。\n\n```text\nsamples/<sample_id>/\n  annotation.json\n  images/step_NNN.png\n  ui_tree/step_NNN.json\n```\n\n## 实际分布\n\n统计取自本目录实际选入的样本，不重命名类目或变更原输入总体分母。\n\n```json\n' + json.dumps(statistics, ensure_ascii=False, indent=2) + '\n```\n\n本次导出样本' + str(len(records)) + '条；不包含内部raw、审核记录、批次manifest或追溯档案。导出结构检查不代表独立QC、真人审核或客户验收。当前独立QC状态：NOT_RUN；客户验收：UNKNOWN。\n')
    (out / 'qc_report.md').write_text('# 质检状态\n\n独立QC：NOT_RUN（本次仅完成导出与结构自检）。客户验收：UNKNOWN。真实QC报告必须由后续程序在包外生成，不能回写或伪称本输入包已经通过。\n')


def validate_client_layout(root):
    root = Path(root)
    if {p.name for p in root.iterdir()} not in (ROOT_FILES | {'samples', 'ground_truth'}, ROOT_FILES | {'samples', 'ground_truth', EXECUTION_FILE}):
        raise ValueError('Customer root contains missing or internal files')
    for p in root.rglob('*'):
        if p.is_symlink():
            raise ValueError('Customer export must not contain symlinks')
    if (root / EXECUTION_FILE).exists():
        validate_execution_attachment(root)
    site_list = read_json(root / 'site-list.json')
    if site_list.get('schema_version') not in ('site-list', 'webcollect-site-list-1'):
        raise ValueError('Unknown site-list schema')
    sample_map = {r['sample_id']: r['site_id'] for r in site_list['samples']}
    sites = {r['site_id']: r for r in site_list['sites']}
    if len(sites) != len(site_list['sites']):
        raise ValueError('Duplicate client site ID')
    ids = {p.name for p in (root / 'samples').iterdir()}
    if len(sample_map) != len(site_list['samples']) or set(sample_map) != ids:
        raise ValueError('Site map sample coverage mismatch')
    if {p.name for p in (root / 'ground_truth').iterdir()} != {sid + '.json' for sid in ids}:
        raise ValueError('Ground truth coverage mismatch')
    for key, site in sites.items():
        if (not all(isinstance(site.get(k), str) and site[k].strip() for k in ('site_id', 'uri', 'site_category')) or
                len(site['sample_ids']) != len(set(site['sample_ids'])) or
                set(site['sample_ids']) != {sid for sid, site_id in sample_map.items() if site_id == key}):
            raise ValueError('Site list and sample mapping disagree')
    with (root / 'metadata.csv').open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != COLUMNS:
            raise ValueError('Metadata columns differ from customer export contract')
        metadata = list(reader)
    meta = {row['sample_id']: row for row in metadata}
    if len(meta) != len(metadata) or set(meta) != ids:
        raise ValueError('Metadata sample coverage mismatch')
    steps = 0
    for sid in sorted(ids):
        d = validate_client_sample(root / 'samples' / sid); steps += len(d['steps'])
        if sample_map[sid] not in sites or sid not in sites[sample_map[sid]]['sample_ids']:
            raise ValueError('Site ownership mismatch')
        row = meta[sid]
        if (row['site_id'] != sample_map[sid] or row['site_category'] != sites[sample_map[sid]]['site_category'] or
                int(row['steps']) != len(d['steps']) or json.loads(row['actions']) != [s['action']['action_type'] for s in d['steps']] or
                json.loads(row['screen_resolution']) != d['device_info']['screen_resolution'] or
                json.loads(row['task_type']) != d['task_type'] or row['task_instruction'] != d['task_instruction'] or
                row['app_name'] != d['app_info']['app_name'] or row['completion_status'] != d['completion_status'] or
                int(row['bytes']) != sum(p.stat().st_size for p in (root / 'samples' / sid).rglob('*') if p.is_file())):
            raise ValueError('Metadata values differ from annotation/site mapping')
        expected_truth = [{'step_id': s['step_id'], 'element_id': s['action']['target_element_id'],
                           'text': s['action']['target_text'], 'bbox': s['action']['target_bbox']}
                          for s in d['steps'] if s['action'].get('target_element_id') and 'target_bbox' in s['action']]
        if read_json(root / 'ground_truth' / (sid + '.json')) != expected_truth:
            raise ValueError('Customer truth differs from sample targets')
        if '\n## ' + d['trajectory_source']['data_type'] + '\n' not in (root / '动作空间与系统提示.md').read_text():
            raise ValueError('Missing data_type system prompt chapter')
    listed = {}
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        digest, relative = line.split('  ', 1)
        if relative in listed or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Invalid or duplicate checksum entry')
        listed[relative] = digest
    actual = {p.relative_to(root).as_posix(): sha(p) for p in root.rglob('*') if p.is_file() and p != root / 'SHA256SUMS'}
    if listed != actual:
        raise ValueError('Root checksum manifest differs from complete customer files')
    return {'structural_pass': True, 'samples': len(ids), 'steps': steps, 'customer_acceptance': 'UNKNOWN'}


def append_client_package(repo, source, output, *, files_sha256, staging_root):
    """Append an already exported item without recopying prior screenshots.

    Source format and save receipts are established by the ordinary exporter.
    Only the new payload is copied/hashed; package indexes and documents are
    regenerated. The output lock is separate from consumer dispatch locks.
    """
    import fcntl
    repo, source, output = Path(repo), Path(source), Path(output)
    if files_sha256 != {p.relative_to(source).as_posix(): sha(p)
                       for p in source.rglob('*') if p.is_file()}:
        raise ValueError('Saved customer export changed before delivery')
    if (source / EXECUTION_FILE).exists():
        validate_execution_attachment(source)
    elif any(step['action']['action_type'] == 'hotkey'
             for path in (source / 'samples').iterdir()
             for step in read_json(path / 'annotation.json')['steps']):
        raise ValueError('Append requires actual hotkey execution evidence')
    source_sites = read_json(source / 'site-list.json')
    with (source / 'metadata.csv').open(newline='', encoding='utf-8') as stream:
        incoming = list(csv.DictReader(stream))
    Path(staging_root).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_root, prefix='publish-') as temporary:
        stage = Path(temporary)
        for name in ('samples', 'ground_truth'):
            shutil.copytree(source / name, stage / name)
        lock_dir = output.parent.parent / ('.' + output.parent.name + '-locks')
        lock_dir.mkdir(parents=True, exist_ok=True)
        with (lock_dir / (output.name + '.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            output.mkdir(parents=True, exist_ok=True)
            for name in ('samples', 'ground_truth'):
                (output / name).mkdir(exist_ok=True)
            current = read_json(output / 'site-list.json') if (output / 'site-list.json').exists() else {
                'schema_version':'site-list', 'sites':[], 'samples':[]}
            if (output / EXECUTION_FILE).exists():
                validate_execution_attachment(output)
            elif any(step['action']['action_type'] == 'hotkey'
                     for path in (output / 'samples').iterdir()
                     for step in read_json(path / 'annotation.json')['steps']):
                raise ValueError('Historical hotkeys need an explicit revision before append')
            sites = {row['site_id']:row for row in current['sites']}
            members = {row['sample_id']:row['site_id'] for row in current['samples']}
            for row in source_sites['sites']:
                old = sites.get(row['site_id'])
                if old and any(old[key] != row[key] for key in ('uri','site_category')):
                    raise ValueError('Conflicting delivery site identity')
                sites.setdefault(row['site_id'], {**row, 'sample_ids':[]})
            for row in source_sites['samples']:
                sid, site_id = row['sample_id'], row['site_id']
                if sid in members and members[sid] != site_id:
                    raise ValueError('Conflicting delivery sample owner')
                # A publication interrupted between payload and index updates
                # resumes from the same saved sample; it never recollects it.
                for relative in (Path('samples') / sid, Path('ground_truth') / (sid + '.json')):
                    destination = output / relative
                    if destination.exists():
                        paths = list(destination.rglob('*')) if destination.is_dir() else [destination]
                        actual={path.relative_to(output).as_posix():sha(path) for path in paths if path.is_file()}
                        prefix=relative.as_posix()
                        expected={name:digest for name,digest in files_sha256.items()
                                  if name==prefix or name.startswith(prefix+'/')}
                        if actual!=expected:
                            raise ValueError('Existing delivered sample is incomplete or differs from its original export')
                    else:
                        (stage / relative).replace(destination)
                members[sid] = site_id
            for site_id, row in sites.items():
                row['sample_ids'] = [sid for sid, owner in members.items() if owner == site_id]
            write_json(stage / 'site-list.json', {'schema_version':'site-list',
                'sites':list(sites.values()),
                'samples':[{'sample_id':sid,'site_id':owner} for sid,owner in members.items()]})
            metadata = {}
            if (output / 'metadata.csv').exists():
                with (output / 'metadata.csv').open(newline='', encoding='utf-8') as stream:
                    metadata.update((row['sample_id'],row) for row in csv.DictReader(stream))
            metadata.update((row['sample_id'],row) for row in incoming)
            with (stage / 'metadata.csv').open('w', newline='', encoding='utf-8') as stream:
                writer=csv.DictWriter(stream, fieldnames=COLUMNS); writer.writeheader()
                writer.writerows(metadata.values())
            records=[{'sample_id':sid, 'data':read_json(output/'samples'/sid/'annotation.json'),
                      'site':sites[owner], 'manifest_path':None,
                      'hashes':{'annotation.json':sha(output/'samples'/sid/'annotation.json')}} for sid,owner in members.items()]
            execution_rows = {}
            for package_root in (output, source):
                if (package_root / EXECUTION_FILE).exists():
                    for item in read_json(package_root / EXECUTION_FILE)['samples']:
                        if item['sample_id'] in execution_rows and execution_rows[item['sample_id']] != item:
                            raise ValueError('Conflicting actual execution evidence')
                        execution_rows[item['sample_id']] = item
            for record in records:
                execution_rows.setdefault(record['sample_id'], _unavailable_execution(record))
            write_json(stage / EXECUTION_FILE, {'schema_version': EXECUTION_VERSION,
                'keyboard_policy': ACTUAL_KEYBOARD_VERSION, 'samples': list(execution_rows.values())})
            _documents(repo, stage, records)
            hashes = {}
            if (output / 'SHA256SUMS').exists():
                for line in (output / 'SHA256SUMS').read_text().splitlines():
                    digest, relative = line.split('  ',1); hashes[relative]=digest
            hashes.update({relative:digest for relative,digest in files_sha256.items()
                           if relative.startswith(('samples/','ground_truth/'))})
            for name in sorted((ROOT_FILES | {EXECUTION_FILE}) - {'SHA256SUMS'}):
                hashes[name] = sha(stage / name)
                (stage / name).replace(output / name)
            (stage / 'SHA256SUMS').write_text(''.join(
                digest + '  ' + relative + '\n' for relative,digest in sorted(hashes.items())))
            (stage / 'SHA256SUMS').replace(output / 'SHA256SUMS')
    return {'customer_output':str(output), 'sample_ids':[row['sample_id'] for row in incoming]}


def build_client_package(repo, source, output, *, reviews=None, approved_only=False,
                         evidence_output=None, review_output=None, facts=None, revisions=None,
                         selection_report=None, source_packages=None, delivery_policy=None, execution_evidence=None):
    repo = Path(repo).resolve(); source = Path(source).resolve(); output = Path(output).absolute()
    from .contract_documents import load_facts, render as render_documents
    from .narrative_revisions import load_plan, apply as revise_narratives
    production_facts = load_facts(facts)
    revision_plan = load_plan(revisions)
    frozen_review_sha = sha(reviews) if reviews else None
    frozen_selection_sha = sha(selection_report) if selection_report else None
    if review_output is not None and reviews is None:
        raise ValueError('--review-output requires --reviews')
    if selection_report is not None and reviews is None:
        raise ValueError('--selection-report requires --reviews')
    if output.is_symlink() or output.exists():
        raise FileExistsError('Refuse to overwrite customer output')
    output = output.resolve()
    if not source.is_dir() or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Source/output missing or containing each other')
    evidence_output = Path(evidence_output).absolute() if evidence_output else output.with_name(output.name + '.evidence.json')
    review_output = Path(review_output).absolute() if review_output else evidence_output.with_name(evidence_output.stem + '.selected-reviews.json')
    destinations = [output, evidence_output] + ([review_output] if reviews else [])
    if len(set(p.resolve() for p in destinations)) != len(destinations):
        raise ValueError('Output paths must be distinct')
    for path in destinations[1:]:
        if path.exists() or path.is_symlink():
            raise FileExistsError('Refuse to overwrite sidecar: ' + str(path))
        if path.resolve().is_relative_to(output) or path.resolve().is_relative_to(source):
            raise ValueError('Evidence/review output must be outside customer output and source')
    sources=[Path(item).resolve() for item in source_packages] if source_packages is not None else [source]
    if not sources or len(set(sources))!=len(sources):raise ValueError('Explicit unique source packages required')
    for root in sources:
        if output.is_relative_to(root) or root.is_relative_to(output):raise ValueError('Batch output overlaps an original package')
    records=[record for root in sources for record in _discover(root)]
    if len({record['sample_id'] for record in records})!=len(records):raise ValueError('Duplicate original sample across batch sources')
    if not records:
        raise ValueError('No samples found')
    # Every newly generated customer package uses the current save criteria.
    # Existing packages and their historical receipts remain untouched.
    if delivery_policy is None:
        from .closing_policy import COMPLETED_GOAL_DELIVERY
        delivery_policy = COMPLETED_GOAL_DELIVERY
    delivery_decisions = {}
    if delivery_policy is not None:
        from .closing_policy import COMPLETED_GOAL_DELIVERY, completion_delivery_decision
        if delivery_policy != COMPLETED_GOAL_DELIVERY:
            raise ValueError('Unknown explicit customer delivery policy')
        eligible = []
        for record in records:
            saved_path = record['batch'] / 'evidence' / record['sample_id'] / 'saved_sample.json'
            saved = read_json(real_file(saved_path, record['batch']))
            if saved.get('sample_files_sha256') != record['hashes']:
                raise ValueError('Delivery policy needs the original saved sample binding')
            decision = completion_delivery_decision(record['data'], saved.get('raw_execution', {}))
            delivery_decisions[record['sample_id']] = decision
            if decision['delivery_eligible']:
                eligible.append(record)
        if not eligible:
            raise ValueError('No original-goal-complete ordinary delivery candidates')
    baseline = repo / 'projects/quality-inspector/config/customer-samples.json'
    if reviews and not baseline.is_file():
        raise ValueError('Customer review baseline is missing')
    selection_rows = None
    if reviews and read_json(reviews).get('schema_version') == 'qc-review-2':
        review_map, review_export, selection_rows = _v2_review_records(repo, Path(reviews), records,
                                                                     source, selection_report)
    else:
        if selection_report is not None:
            raise ValueError('--selection-report is only supported for qc-review-2')
        review_map, review_export = _review_records(Path(reviews) if reviews else None, records, approved_only,
                                                   sha(baseline) if reviews else None)
    selected = [r for r in records if
                (delivery_policy is None or delivery_decisions[r['sample_id']]['delivery_eligible']) and
                (not approved_only or (_approved(review_map.get(r['sample_id'])) and
                 (selection_rows is None or selection_rows[r['sample_id']]['status'] == 'PASS')))]
    if not selected:
        raise ValueError('No selected samples; approved-only never infers approval')
    if selection_rows is not None and approved_only and production_facts is not None:
        if production_facts['selection'].get('selected_count') != len(selected):
            raise ValueError('Selected facts must describe the new selected population, retaining original exclusions')
    revision_map = {row['sample_id']: row for row in revision_plan['samples']} if revision_plan else {}
    if set(revision_map) - {r['sample_id'] for r in selected}:
        raise ValueError('Narrative revision refers to an unselected sample')
    if revision_plan is not None and reviews is not None:
        raise ValueError('Revised annotations require fresh QC reviews; do not re-sign old records')
    # Export never repairs historical keys implicitly. Actual dispatch mismatch
    # is rejected by the execution evidence binding below.
    execution_plan = read_json(execution_evidence) if isinstance(execution_evidence, (str, Path)) else execution_evidence
    if execution_plan is not None and execution_plan.get('schema_version') not in (EXECUTION_VERSION, 'webcollect-actual-execution-1'):
        raise ValueError('Unknown actual execution evidence version')
    execution_inputs = {row['sample_id']: row for row in execution_plan['samples']} if execution_plan else {}
    if set(execution_inputs) - {record['sample_id'] for record in selected}:
        raise ValueError('Actual execution evidence refers to an unselected sample')
    if execution_plan and len(execution_inputs) != len(execution_plan['samples']):
        raise ValueError('Duplicate actual execution sample')
    execution_rows = [_execution_record(record, execution_inputs.get(record['sample_id'])) for record in selected]
    excluded = [dict(sample_id=r['sample_id'], reason=(
        'ORIGINAL_GOAL_DELIVERY_POLICY_EXCLUDED' if delivery_policy is not None and not delivery_decisions[r['sample_id']]['delivery_eligible'] else
        'CURRENT_QC_SAMPLE_NOT_PASS' if selection_rows is not None and selection_rows[r['sample_id']]['status'] != 'PASS'
        else 'HUMAN_FIVE_CHECKS_NOT_ALL_PASS' if r['sample_id'] in review_map else 'MISSING_REVIEW'),
        review=review_map.get(r['sample_id'])) for r in records if r not in selected]
    # Validate every source before creating anything. Staging keeps failed contracts out of final output.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.' + output.name + '.staging-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'client'; staged.mkdir(); (staged / 'samples').mkdir(); (staged / 'ground_truth').mkdir()
        exported = []
        for record in selected:
            sid = record['sample_id']; shutil.copytree(record['sample'], staged / 'samples' / sid)
            shutil.copyfile(record['truth'], staged / 'ground_truth' / (sid + '.json'))
            if (sample_hashes(staged / 'samples' / sid) != record['hashes'] or
                    sha(staged / 'ground_truth' / (sid + '.json')) != record['truth_sha256']):
                raise ValueError('Copied sample hashes differ')
            if sid in revision_map:
                revise_narratives(staged / 'samples' / sid, revision_map[sid])
            current = validate_client_sample(staged / 'samples' / sid)
            current_hashes = sample_hashes(staged / 'samples' / sid)
            if any(h != current_hashes[k] for k, h in record['hashes'].items() if k != 'annotation.json'):
                raise ValueError('Revision modified immutable image/tree evidence')
            exported.append({**record, 'data': current, 'export_hashes': current_hashes})
        site_map = {}
        for r in selected:
            site = r['site']; key = site['site_id']
            if key in site_map and any(site_map[key][k] != site[k] for k in ('uri', 'site_category')):
                raise ValueError('Conflicting source site mapping')
            site_map.setdefault(key, {**site, 'sample_ids': []})['sample_ids'].append(r['sample_id'])
        write_json(staged / 'site-list.json', {'schema_version': 'site-list', 'sites': list(site_map.values()), 'samples': [dict(sample_id=r['sample_id'], site_id=r['site']['site_id']) for r in selected]})
        with (staged / 'metadata.csv').open('x', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS); writer.writeheader()
            for r in exported:
                a = r['data']; writer.writerow(dict(sample_id=r['sample_id'], site_id=r['site']['site_id'], site_category=r['site']['site_category'], app_name=a['app_info']['app_name'], task_type=json.dumps(a['task_type'], ensure_ascii=False), task_instruction=a['task_instruction'], steps=len(a['steps']), screen_resolution=json.dumps(a['device_info']['screen_resolution']), completion_status=a['completion_status'], actions=json.dumps([s['action']['action_type'] for s in a['steps']], ensure_ascii=False), bytes=sum(p.stat().st_size for p in (staged / 'samples' / r['sample_id']).rglob('*') if p.is_file())))
        final_annotations = {r['sample_id']: r['export_hashes']['annotation.json'] for r in exported}
        for execution_row in execution_rows:
            execution_row['annotation_sha256'] = final_annotations[execution_row['sample_id']]
        write_json(staged / EXECUTION_FILE, {'schema_version': EXECUTION_VERSION, 'keyboard_policy': ACTUAL_KEYBOARD_VERSION, 'samples': execution_rows})
        _documents(repo, staged, exported)
        render_documents(staged, exported, production_facts, revision_plan)
        (staged / 'SHA256SUMS').write_text(''.join(sha(p) + '  ' + p.relative_to(staged).as_posix() + '\n' for p in sorted(staged.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
        contract = validate_client_layout(staged)
        sidecar_samples = []
        for r in records:
            sidecar_samples.append(dict(sample_id=r['sample_id'], selected=r in selected, source_sample_path=str(r['sample']), source_batch_path=str(r['batch']), annotation_sha256=r['hashes']['annotation.json'], evidence_sha256={k: v for k, v in r['hashes'].items() if k != 'annotation.json'}, ground_truth_sha256=r['truth_sha256'], source_ground_truth_path=str(r['truth']), source_manifest_path=str(r['manifest_path']) if r['manifest_path'] else None, source_manifest_sha256=sha(r['manifest_path']) if r['manifest_path'] else None, raw_evidence_files_sha256=r['raw_hashes'], source_files_sha256=r['source_files'], machine_evidence_status='AVAILABLE' if r['manifest_path'] and r['raw_hashes'] else 'UNAVAILABLE'))
        selected_sidecar = [r for r in sidecar_samples if r['selected']]
        evidence = dict(delivery_policy=delivery_policy, completion_delivery_decisions=delivery_decisions, schema_version='client-evidence', created_at=datetime.now(timezone.utc).isoformat(), client_root=str(output), source_root=str(source), samples=selected_sidecar, source_population=dict(total_samples=len(records), selected_count=len(selected), excluded_count=len(excluded)), source_samples=sidecar_samples, excluded_samples=excluded, source_review_export=dict(path=str(Path(reviews).resolve()), sha256=sha(reviews)) if reviews else None, source_review_records=review_export['records'] if review_export else None, source_review_document=review_export, source_package_review_applied=False, selected_review_output=str(review_output.resolve()) if reviews else None, independent_qc_status='NOT_RUN', customer_acceptance='UNKNOWN')
        evidence['actual_execution_attachment'] = {'file': EXECUTION_FILE,
            'sha256': sha(staged / EXECUTION_FILE), 'schema_version': EXECUTION_VERSION,
            'keyboard_policy': ACTUAL_KEYBOARD_VERSION}
        if execution_inputs:
            evidence['actual_execution_sources'] = [{
                'sample_id': row['sample_id'], 'annotation_sha256': row['annotation_sha256'],
                'steps': [{'step_id': step['step_id'],
                           'dispatch_ref': {key: step['dispatch_ref'][key] for key in ('path', 'sha256')},
                           'raw_step_ref': {key: step['raw_step_ref'][key] for key in ('path', 'sha256')}}
                          for step in row['steps']]} for row in execution_inputs.values()]
        if selection_report is not None:
            evidence['selection_qc_report'] = {'path': str(Path(selection_report).resolve()),
                                               'sha256': sha(selection_report)}
            evidence['selection_does_not_release_new_package'] = True
        if revision_plan is not None:
            # Original capture evidence binds the source annotation only. A prose
            # revision must never masquerade as an unchanged capture index.
            revision_path = Path(revisions).resolve()
            revision_bytes = revision_path.read_bytes()
            if json.loads(revision_bytes.decode('utf-8')) != revision_plan:
                raise ValueError('Narrative revision plan changed during export')
            revision_sha256 = hashlib.sha256(revision_bytes).hexdigest()
            exports_by_id = {r['sample_id']: r for r in exported}
            for row in sidecar_samples:
                row['source_annotation_sha256'] = row.pop('annotation_sha256')
                exported_record = exports_by_id.get(row['sample_id'])
                row['export_annotation_sha256'] = exported_record['export_hashes']['annotation.json'] if exported_record else None
                row['export_sample_path'] = str(output / 'samples' / row['sample_id']) if exported_record else None
                row['source_capture_evidence_status'] = row.pop('machine_evidence_status')
                row['capture_binding_status'] = 'NOT_A_CAPTURE_BINDING'
                row['narrative_revision_applied'] = row['sample_id'] in revision_map
            evidence.update(schema_version='narrative-provenance',
                            capture_binding=False,
                            provenance_scope='Source-to-export annotation revisions; not proof that revised prose was captured or human-approved',
                            revision_plan={'path': str(revision_path), 'sha256': revision_sha256,
                                           'canonical_sha256': hashlib.sha256(json.dumps(revision_plan, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()},
                            requires_fresh_export_review=True)
        # Recheck source bytes after staging; do not silently bind changed sources.
        if any(sample_hashes(r['sample']) != r['hashes'] or sha(r['truth']) != r['truth_sha256'] or
               any(sha(r['batch'] / k) != h for k, h in r['source_files'].items()) for r in records):
            raise ValueError('Source changed during export')
        if any(sha(step[key]['path']) != step[key]['sha256']
               for row in execution_inputs.values() for step in row['steps']
               for key in ('dispatch_ref', 'raw_step_ref')):
            raise ValueError('Original actual execution evidence changed during export')
        if revision_plan is not None and sha(revision_path) != revision_sha256:
            raise ValueError('Narrative revision plan changed before provenance was sealed')
        if (reviews and sha(reviews) != frozen_review_sha) or (selection_report and sha(selection_report) != frozen_selection_sha):
            raise ValueError('Review or selection report changed during export')
        for path in destinations[1:]:
            path.parent.mkdir(parents=True, exist_ok=True)
        if reviews:
            with review_output.open('x', encoding='utf-8') as stream:
                json.dump({'schema_version': 'qc-review', 'records': [review_map[r['sample_id']] for r in selected if r['sample_id'] in review_map]}, stream, ensure_ascii=False, indent=2); stream.write('\n')
        with evidence_output.open('x', encoding='utf-8') as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2); stream.write('\n')
        if output.exists():
            raise FileExistsError('Customer output appeared during export')
        staged.rename(output)
    return dict(output=str(output), layout='client', evidence_output=str(evidence_output.resolve()), review_output=str(review_output.resolve()) if reviews else None, source_population=evidence['source_population'], samples=len(selected), frames=contract['steps'], contract=contract, independent_qc_status='NOT_RUN', customer_acceptance='UNKNOWN')
