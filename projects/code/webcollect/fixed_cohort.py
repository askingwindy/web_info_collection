"""Freeze a formal cohort, preserve every attempt, and finalize one read-only QC.

This module allocates no production IDs and performs no semantic review. It only
binds existing collection/QC evidence and prevents a second, improved score for
the same finalized cohort. The production registry remains authoritative.
"""
import argparse
import csv
from collections import Counter, defaultdict
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
from webcollect import workspace_json as json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from .batch_core import file_sha, load_json, save_json
from .planning import canonical, object_sha256

VERSION = 'fixed-cohort'
LEGACY_VERSION = 'webcollect-fixed-cohort-1'
TARGET = 1000
SITES = 50
PER_SITE = 20
STATES = ('PASS', 'FAIL', 'REVIEW_REQUIRED')
SEMANTIC = ('visual_alignment', 'terminal_semantics', 'language', 'privacy',
            'substantive_difference')
REQUIRED_RULES = tuple(f'C{i:02}' for i in range(1, 18) if i not in (13, 14))
REQUIRED_BATCH_RULES = ('C13', 'C14', 'DELIVERY_DOCUMENT_CONTENT', 'DELIVERY_ATTACHMENT',
    'DELIVERY_DOCUMENT_ROLES', 'DELIVERY_ACCOUNTING', 'DELIVERY_VIEWPORT_SPECS',
    'DELIVERY_SHORT_FLOW_SHARE', 'DELIVERY_CATEGORY_SHARE', 'ROOT_CHECKSUM', 'DELIVERY_DOCUMENT_REVIEW')
BINDING_GROUPS = ('capture_sources', 'qc_sources', 'rules', 'prompts', 'model',
                  'rates', 'history')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _path(value):
    path = Path(value)
    if not path.is_absolute() or path.is_symlink():
        raise ValueError('An absolute nonsymlink path is required: ' + str(path))
    return path.resolve()


def _ref(value):
    if not isinstance(value, dict) or set(value) != {'path', 'sha256'}:
        raise ValueError('A binding must contain exactly path and sha256')
    path = _path(value['path'])
    if not path.is_file() or file_sha(path) != value['sha256']:
        raise ValueError('Binding bytes differ: ' + str(path))
    return {'path': str(path), 'sha256': value['sha256']}


def _files(root):
    root = _path(root)
    if not root.is_dir():
        raise ValueError('Capture/package root is not a directory: ' + str(root))
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('A sealed tree cannot contain symlinks: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = file_sha(path)
    return result


def _outside(path, root):
    path = _path(path)
    if path == root or path.is_relative_to(root):
        raise ValueError('State, QC and reports must be outside sealed capture bytes')
    return path


def _outside_history(path, packages):
    for root in packages:
        _outside(path, Path(root))
    return path


@contextmanager
def _lock(path):
    path = _path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + '.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield path


def _state_write(path, value):
    value['state_sha256'] = object_sha256({k: v for k, v in value.items()
                                          if k != 'state_sha256'})
    data = canonical(value) + '\n'
    descriptor, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _state_read(path):
    value = load_json(path)
    if (value.get('schema_version') not in (VERSION, LEGACY_VERSION) or value.get('state_sha256') !=
            object_sha256({k: v for k, v in value.items() if k != 'state_sha256'})
            or value.get('spec_sha256') != object_sha256(value.get('spec'))):
        raise ValueError('Cohort state/spec integrity differs')
    previous = value['spec_sha256']
    for index, event in enumerate(value['attempts'], 1):
        if (event.get('sequence') != index or event.get('previous_sha256') != previous
                or event.get('event_sha256') != object_sha256(
                    {k: v for k, v in event.items() if k != 'event_sha256'})):
            raise ValueError('Append-only attempt history integrity differs')
        previous = event['event_sha256']
    return value


def _binding_errors(state):
    errors = deepcopy(state.get('integrity_breaches', []))
    for group, refs in state['spec']['bindings'].items():
        for value in refs:
            try:
                _ref(value)
            except (OSError, ValueError) as error:
                try:
                    observed = file_sha(value['path'])
                except OSError:
                    observed = 'UNREADABLE'
                errors.append({'kind': 'FROZEN_BINDING_CHANGED', 'group': group,
                               'path': value['path'], 'expected_sha256': value['sha256'],
                               'observed_sha256': observed, 'reason': str(error)})
    try:
        observed = file_sha(__file__)
        if observed != state['implementation_sha256']:
            errors.append({'kind': 'COHORT_IMPLEMENTATION_CHANGED',
                           'expected_sha256': state['implementation_sha256'], 'observed_sha256': observed})
    except OSError as error:
        errors.append({'kind': 'COHORT_IMPLEMENTATION_UNREADABLE', 'reason': str(error)})
    return errors


def _latch_breaches(path, state, errors):
    """An observed freeze violation remains even if the original bytes return."""
    breaches = state.setdefault('integrity_breaches', [])
    for error in errors:
        if error not in breaches:
            breaches.append(error)
    _state_write(path, state)


def _history(spec):
    packages = {}
    for ref in spec['bindings']['history']:
        manifest = load_json(ref['path'])
        if manifest.get('schema_version') not in ('qc-cumulative-set', 'qc-cumulative-set-1'):
            raise ValueError('History must bind qc-cumulative-set manifests')
        for item in manifest.get('packages', []):
            path = Path(item['path'])
            if not path.is_absolute():
                path = Path(ref['path']).parent / path
            path = _path(path)
            files = item.get('package_files_sha256')
            if not isinstance(files, dict) or not files:
                raise ValueError('History requires complete frozen package file hashes')
            if str(path) in packages and packages[str(path)] != files:
                raise ValueError('Conflicting effective history versions')
            packages[str(path)] = files
    if not packages:
        raise ValueError('Existing effective history cannot silently be empty')
    return packages


def _historical_ids(packages):
    result = set()
    for root, files in packages.items():
        for relative, digest in files.items():
            if Path(relative).name != 'annotation.json':
                continue
            path = Path(root) / relative
            if (Path(relative).is_absolute() or not path.resolve().is_relative_to(Path(root))
                    or path.is_symlink() or file_sha(path) != digest):
                raise ValueError('Historical annotation differs from frozen history')
            sid = load_json(path).get('sample_id')
            if not isinstance(sid, str) or not sid:
                raise ValueError('Historical sample ID is missing')
            result.add(sid)
    return sorted(result)


def _spec(value):
    spec = deepcopy(load_json(value) if isinstance(value, (str, Path)) else value)
    for key in ('cohort_id', 'campaign_id', 'capture_run_id', 'counting_policy'):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise ValueError('A fixed nonempty ' + key + ' is required')
    if (spec.get('target_count'), spec.get('site_count'), spec.get('samples_per_site')) != (TARGET, SITES, PER_SITE):
        raise ValueError('This formal protocol requires exactly 1000 tasks at 50 sites x 20')
    spec['capture_root'] = str(_path(spec['capture_root']))
    maximum = spec.setdefault('max_attempts_per_task', 2)
    if type(maximum) is not int or maximum not in (1, 2):
        raise ValueError('Only one or two bounded attempts per fixed task are supported')
    tasks = spec.get('tasks')
    if not isinstance(tasks, list) or len(tasks) != TARGET:
        raise ValueError('Freeze all 1000 tasks before formal collection')
    ids = set()
    sites = defaultdict(list)
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError('Each fixed task must be an object')
        for key in ('task_id', 'site_id', 'domain', 'uri', 'category'):
            if not isinstance(task.get(key), str) or not task[key].strip():
                raise ValueError('Each task needs ' + key)
        if task['task_id'] in ids:
            raise ValueError('Repeated fixed task_id')
        ids.add(task['task_id'])
        uri = urlsplit(task['uri'])
        domain = task['domain'].lower()
        if (uri.scheme not in ('http', 'https') or not uri.hostname or uri.username or uri.password
                or not (uri.hostname == domain or uri.hostname.endswith('.' + domain))):
            raise ValueError('Task domain and exact public URI differ')
        sites[task['site_id']].append(task)
    if len(sites) != SITES or any(len(rows) != PER_SITE for rows in sites.values()):
        raise ValueError('Frozen site allocation differs from 50 x 20')
    uris = set()
    for rows in sites.values():
        identity = {(row['domain'], row['uri'], row['category']) for row in rows}
        if len(identity) != 1 or rows[0]['uri'] in uris:
            raise ValueError('Each counted site needs one distinct exact URI and stable category/domain')
        uris.add(rows[0]['uri'])
    excluded = spec.get('development_exclusion')
    if not isinstance(excluded, dict) or set(excluded) != {'run_ids', 'sample_ids'}:
        raise ValueError('Declare development run and sample exclusions before formal collection')
    for key, values in excluded.items():
        if (not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values)
                or len(values) != len(set(values))):
            raise ValueError('Invalid development exclusion ' + key)
    if spec['capture_run_id'] in excluded['run_ids']:
        raise ValueError('Formal capture run cannot be a development run')
    if set(spec.get('bindings', {})) != set(BINDING_GROUPS):
        raise ValueError('Freeze capture/QC sources, rules, prompts, model, rates and history')
    for group, refs in spec['bindings'].items():
        if not isinstance(refs, list) or not refs:
            raise ValueError('Missing frozen binding group: ' + group)
        spec['bindings'][group] = [_ref(ref) for ref in refs]
    capture = Path(spec['capture_root'])
    if any(capture == Path(root) or capture.is_relative_to(Path(root))
           or Path(root).is_relative_to(capture) for root in _history(spec)):
        raise ValueError('New capture and effective historical packages must not overlap')
    return spec


def freeze(spec, state_path):
    """Register an immutable formal assignment before its first attempt."""
    spec = _spec(spec)
    state_path = _outside(state_path, Path(spec['capture_root']))
    _outside_history(state_path, _history(spec))
    with _lock(state_path):
        if state_path.exists():
            current = _state_read(state_path)
            if current['spec'] != spec:
                raise ValueError('Cannot replace a fixed cohort or move sample ownership')
            return current
        value = {'schema_version': VERSION, 'phase': 'COLLECTING',
                 'created_at_utc': _now(), 'spec': spec, 'spec_sha256': object_sha256(spec),
                 'implementation_sha256': file_sha(__file__), 'attempts': [],
                 'history_packages': _history(spec)}
        value['historical_sample_ids'] = _historical_ids(value['history_packages'])
        _state_write(state_path, value)
        return value


def record(state_path, attempt):
    """Append a real attempt; failures and prior IDs can never be removed."""
    attempt = deepcopy(load_json(attempt) if isinstance(attempt, (str, Path)) else attempt)
    with _lock(state_path) as path:
        state = _state_read(path)
        if state['phase'] != 'COLLECTING':
            raise ValueError('Sealed/finalized cohorts reject attempt or membership changes')
        errors = _binding_errors(state)
        if errors:
            _latch_breaches(path, state, errors)
            raise ValueError('Frozen implementation/configuration changed during collection')
        spec = state['spec']
        if 'cost_reference' not in attempt:
            attempt['cost_reference'] = 'UNKNOWN'
        if attempt.get('sample_path'):
            sample = _path(attempt['sample_path'])
            if not sample.is_relative_to(Path(spec['capture_root'])):
                raise ValueError('Attempt sample is outside frozen capture root')
            attempt['sample_path'] = str(sample)
        for key in ('attempt_id', 'task_id', 'run_id', 'status'):
            if not isinstance(attempt.get(key), str) or not attempt[key]:
                raise ValueError('An attempt needs ' + key)
        if (attempt['task_id'] not in {t['task_id'] for t in spec['tasks']}
                or attempt['run_id'] != spec['capture_run_id']
                or attempt['run_id'] in spec['development_exclusion']['run_ids']
                or attempt['status'] not in ('FAILED', 'SUCCEEDED')):
            raise ValueError('Attempt is outside the predeclared formal cohort')
        previous = [event['attempt'] for event in state['attempts']]
        same = [row for row in previous if row['attempt_id'] == attempt['attempt_id']]
        if same:
            if same[0] != attempt:
                raise ValueError('An existing attempt is immutable')
            return state
        task_attempts = [row for row in previous if row['task_id'] == attempt['task_id']]
        if any(row['status'] == 'SUCCEEDED' for row in task_attempts):
            raise ValueError('A successful fixed task cannot be collected again')
        if len(task_attempts) >= spec['max_attempts_per_task']:
            raise ValueError('Fixed per-task attempt limit reached')
        sid = attempt.get('sample_id')
        if sid is not None:
            if (not isinstance(sid, str) or not sid
                    or sid in spec['development_exclusion']['sample_ids']
                    or sid in state['historical_sample_ids']
                    or sid in {row.get('sample_id') for row in previous}):
                raise ValueError('A development or previously allocated sample ID cannot be reused')
        if attempt['status'] == 'SUCCEEDED':
            if not sid or not attempt.get('sample_path'):
                raise ValueError('A successful capture needs its actual sample ID and path')
            annotation = load_json(Path(attempt['sample_path']) / 'annotation.json')
            if annotation.get('sample_id') != sid or annotation.get('completion_status') != 'success':
                raise ValueError('Recorded success differs from the actual annotation')
        event = {'sequence': len(previous) + 1, 'recorded_at_utc': _now(), 'attempt': attempt,
                 'previous_sha256': state['attempts'][-1]['event_sha256'] if previous else state['spec_sha256']}
        event['event_sha256'] = object_sha256(event)
        state['attempts'].append(event)
        _state_write(path, state)
        return state


def _capture_errors(state):
    if 'seal' not in state:
        return [{'kind': 'CAPTURE_NOT_SEALED'}]
    try:
        actual = _files(state['spec']['capture_root'])
    except (OSError, ValueError) as error:
        return [{'kind': 'SEALED_CAPTURE_UNREADABLE', 'reason': str(error)}]
    expected = state['seal']['files_sha256']
    if actual == expected:
        return []
    return [{'kind': 'SEALED_CAPTURE_CHANGED',
             'added': sorted(actual.keys() - expected.keys()),
             'removed': sorted(expected.keys() - actual.keys()),
             'changed': sorted(key for key in actual.keys() & expected.keys() if actual[key] != expected[key])}]


def _history_errors(state):
    errors = []
    for root, expected in state['history_packages'].items():
        try:
            if _files(root) != expected:
                errors.append({'kind': 'FROZEN_HISTORY_PACKAGE_CHANGED', 'path': root})
        except (OSError, ValueError) as error:
            errors.append({'kind': 'FROZEN_HISTORY_PACKAGE_UNREADABLE', 'path': root, 'reason': str(error)})
    return errors


def seal(state_path, capture_root=None):
    """Hash every capture/log/metadata byte without writing inside the tree."""
    with _lock(state_path) as path:
        state = _state_read(path)
        if capture_root is not None and _path(capture_root) != Path(state['spec']['capture_root']):
            raise ValueError('Cannot move the fixed capture root')
        if state['phase'] != 'COLLECTING':
            errors = _binding_errors(state) + _capture_errors(state)
            if errors:
                raise ValueError('Previously sealed bytes changed: ' + canonical(errors))
            return state
        errors = _binding_errors(state)
        if errors:
            _latch_breaches(path, state, errors)
        root = Path(state['spec']['capture_root'])
        _outside(path, root)
        files = _files(root)
        successes = [e['attempt'] for e in state['attempts'] if e['attempt']['status'] == 'SUCCEEDED']
        for attempt in successes:
            relative = (Path(attempt['sample_path']) / 'annotation.json').relative_to(root).as_posix()
            if relative not in files:
                raise ValueError('A recorded successful sample is missing at seal')
        if _files(root) != files:
            raise ValueError('Capture files changed while sealing')
        state['seal'] = {'created_at_utc': _now(), 'files_sha256': files,
                         'files_manifest_sha256': object_sha256(files),
                         'successful_captures': len(successes),
                         'attempt_count': len(state['attempts'])}
        state['phase'] = 'SEALED'
        _state_write(path, state)
        return state


def _sample_decision(row, attempt):
    """Use imported QC checks; absence remains pending rather than inferred PASS."""
    reasons = []
    path = Path(attempt['sample_path'])
    try:
        annotation = load_json(path / 'annotation.json')
        if annotation.get('sample_id') != attempt['sample_id'] or annotation.get('completion_status') != 'success':
            reasons.append('ACTUAL_ANNOTATION_ID_OR_COMPLETION_DIFFERS')
        if row.get('annotation_sha256') != file_sha(path / 'annotation.json'):
            reasons.append('QC_ANNOTATION_BINDING')
        expected = {}
        for step in annotation['steps']:
            for key in ('image_path', 'ui_tree_path'):
                relative = step[key]
                source = path / relative
                if Path(relative).is_absolute() or not source.resolve().is_relative_to(path):
                    raise ValueError('Step evidence escapes the frozen sample')
                expected[relative] = file_sha(source)
        if row.get('evidence_sha256') != expected:
            reasons.append('QC_FRAME_TREE_BINDING')
        if _path(row.get('sample_path', '')) != path:
            reasons.append('QC_SAMPLE_PATH_BINDING')
        step_ids = [step['step_id'] for step in annotation['steps']]
        if not step_ids or any(type(s) is not int for s in step_ids) or len(step_ids) != len(set(step_ids)):
            raise ValueError('Annotation step IDs are missing, repeated or invalid')
    except (OSError, ValueError, KeyError, TypeError) as error:
        return 'FAIL', ['UNREADABLE_OR_UNBOUND_SAMPLE:' + str(error)]
    checks = row.get('checks')
    if not isinstance(checks, list) or not checks:
        return 'REVIEW_REQUIRED', reasons + ['MISSING_QC_CHECKS']
    if any(not isinstance(c, dict) or c.get('status') not in STATES
           or not isinstance(c.get('rule_id'), str) for c in checks):
        return 'FAIL', reasons + ['INVALID_QC_CHECK_STATUS']
    failed = [c['rule_id'] for c in checks if c['status'] == 'FAIL']
    pending = [c['rule_id'] for c in checks if c['status'] == 'REVIEW_REQUIRED']
    ids = {c.get('rule_id') for c in checks}
    missing = set(REQUIRED_RULES) - ids
    if missing:
        pending.extend('MISSING_' + rule for rule in sorted(missing))
    for name in SEMANTIC:
        matches = [c for c in checks if c.get('rule_id') == 'REVIEW_' + name.upper()]
        if len(matches) != 1:
            pending.append('MISSING_OR_REPEATED_REVIEW_' + name.upper())
            continue
        check = matches[0]
        reviewer = check.get('reviewer') or {}
        provenance = check.get('provenance') or {}
        if not isinstance(reviewer, dict) or not isinstance(provenance, dict):
            pending.append('MISSING_BOUND_SEMANTIC_EVIDENCE_' + name)
            continue
        viewed = provenance.get('frames_viewed')
        if (reviewer.get('kind') not in ('ai', 'human')
                or not isinstance(reviewer.get('name'), str) or not reviewer['name'].strip()
                or not isinstance(viewed, list) or len(viewed) != len(step_ids)
                or any(type(step) is not int for step in viewed)
                or set(viewed) != set(step_ids)):
            pending.append('MISSING_BOUND_SEMANTIC_EVIDENCE_' + name)
    if 'DUPLICATE_SEQUENCE' not in ids:
        pending.append('MISSING_DUPLICATE_SEQUENCE')
    for route in ('route3', 'route4'):
        if not any(c.get('rule_id') == 'NEAR_DUPLICATES' and c.get('route') == route for c in checks):
            pending.append('MISSING_' + route)
    if row.get('status') == 'FAIL':
        failed.append('QC_ROW_FAIL')
    elif row.get('status') != 'PASS':
        pending.append('QC_ROW_UNRESOLVED')
    return ('FAIL' if reasons or failed else 'REVIEW_REQUIRED' if pending else 'PASS',
            reasons + failed + pending)


def _population_errors(state, dataset, successes):
    """Bind real sample directories and site metadata to the frozen assignment."""
    try:
        flat = dataset / 'samples'
        legacy = sorted(p / 'samples' for p in dataset.iterdir() if p.is_dir()
                        and p.name != 'samples' and (p / 'samples').exists())
        if flat.exists() and legacy:
            raise ValueError('Mixed customer-flat and legacy sample containers')
        containers = [flat] if flat.exists() else legacy
        actual = {}
        for container in containers:
            if not container.is_dir() or container.is_symlink():
                raise ValueError('Invalid sample container')
            for path in container.iterdir():
                if not path.is_dir() or path.is_symlink():
                    raise ValueError('Unexpected sample-container member')
                annotation = load_json(path / 'annotation.json')
                sid = annotation.get('sample_id')
                if not isinstance(sid, str) or not sid or sid in actual:
                    raise ValueError('Missing/repeated actual annotation sample ID')
                actual[sid] = (path.resolve(), annotation)
        expected = {row['sample_id']: row for row in successes.values()}
        if set(actual) != set(expected):
            raise ValueError('Actual sample directory population differs from successful fixed tasks')
        for sid, attempt in expected.items():
            if actual[sid][0] != Path(attempt['sample_path']):
                raise ValueError('Registered sample is outside the inspected dataset: ' + sid)
        tasks = {task['task_id']: task for task in state['spec']['tasks']}
        frozen_sites = {task['site_id']: task for task in state['spec']['tasks']}
        listing = load_json(dataset / 'site-list.json')
        if listing.get('schema_version') not in ('site-list', 'webcollect-site-list-1'):
            raise ValueError('A current actual site-list is required')
        sites = {row['site_id']: row for row in listing['sites']}
        assignments = {row['sample_id']: row['site_id'] for row in listing['samples']}
        if (len(sites) != len(listing['sites']) or len(assignments) != len(listing['samples'])
                or set(assignments) != set(expected) or not set(sites) <= set(frozen_sites)):
            raise ValueError('Actual site/sample population differs from frozen assignment')
        for site_id, site in sites.items():
            frozen = frozen_sites[site_id]
            assigned = {sid for sid, owner in assignments.items() if owner == site_id}
            members = site['sample_ids']
            if (site.get('uri') != frozen['uri'] or site.get('site_category') != frozen['category']
                    or not isinstance(members, list) or len(members) != len(set(members))
                    or set(members) != assigned):
                raise ValueError('Actual exact URI/category/membership differs: ' + site_id)
        with (dataset / 'metadata.csv').open(encoding='utf-8-sig', newline='') as stream:
            metadata = list(csv.DictReader(stream))
        mapped = {row['sample_id']: row for row in metadata}
        if len(mapped) != len(metadata) or set(mapped) != set(expected):
            raise ValueError('Actual metadata population differs from successful fixed tasks')
        for sid, attempt in expected.items():
            task = tasks[attempt['task_id']]
            if (assignments[sid] != task['site_id'] or mapped[sid]['site_id'] != task['site_id']
                    or mapped[sid]['site_category'] != task['category']):
                raise ValueError('A sample was reassigned to another fixed site/category: ' + sid)
            instruction = task.get('task_instruction')
            if isinstance(instruction, str) and actual[sid][1].get('task_instruction') != instruction:
                raise ValueError('Actual task instruction differs from frozen task: ' + sid)
        return []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, csv.Error) as error:
        return [{'kind': 'QC_DATASET_COHORT_POPULATION_DIFFERS', 'reason': str(error)}]


def _duplicate_evidence(report, *, cumulative=False, expected_ids=None):
    prefix = 'CUMULATIVE' if cumulative else 'LOCAL'
    duplicate = report.get('duplicates')
    if not isinstance(duplicate, dict):
        return 'REVIEW_REQUIRED', [{'kind': prefix + '_DUPLICATE_EVIDENCE_MISSING', 'status': 'REVIEW_REQUIRED'}]
    issues = []
    if expected_ids is not None:
        expected_ids = set(expected_ids)
        rows = duplicate.get('rows')
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            issues.append({'kind': prefix + '_DUPLICATE_POPULATION_MISSING', 'status': 'REVIEW_REQUIRED'})
        else:
            ids = [row.get('sample_id') for row in rows]
            if (any(not isinstance(sid, str) for sid in ids) or len(ids) != len(expected_ids)
                    or set(ids) != expected_ids):
                issues.append({'kind': prefix + '_DUPLICATE_POPULATION_DIFFERS', 'status': 'FAIL'})
        count = len(expected_ids)
        if type(duplicate.get('sample_count')) is not int or duplicate['sample_count'] != count:
            issues.append({'kind': prefix + '_DUPLICATE_SAMPLE_COUNT_DIFFERS', 'status': 'FAIL'})
        if (type(duplicate.get('pair_comparisons')) is not int
                or duplicate['pair_comparisons'] != count * (count - 1) // 2):
            issues.append({'kind': prefix + '_DUPLICATE_PAIR_DOMAIN_DIFFERS', 'status': 'FAIL'})
    for route, count_key, rows_key in (
            ('route1', 'confirmed_pair_count', 'pairs'), ('route2', 'count', 'confirmed_pairs'),
            ('route3', 'count', 'candidates'), ('route4', 'count', 'candidates')):
        row = duplicate.get(route)
        if not isinstance(row, dict) or type(row.get(count_key)) is not int or row[count_key] < 0:
            issues.append({'kind': prefix + '_DUPLICATE_ROUTE_MISSING', 'route': route, 'status': 'REVIEW_REQUIRED'})
            continue
        pairs = row.get(rows_key)
        if not isinstance(pairs, list):
            issues.append({'kind': prefix + '_DUPLICATE_PAIRS_MISSING', 'route': route, 'status': 'REVIEW_REQUIRED'})
            continue
        if pairs or row[count_key]:
            issues.append({'kind': prefix + '_DUPLICATE', 'route': route, 'status': 'FAIL'})
        if row[count_key] != len(pairs):
            issues.append({'kind': prefix + '_DUPLICATE_COUNT_DIFFERS', 'route': route, 'status': 'FAIL'})
    if duplicate.get('error'):
        issues.append({'kind': prefix + '_DUPLICATE_CHECK_ERROR', 'status': 'REVIEW_REQUIRED',
                       'reason': str(duplicate['error'])})
    verification = duplicate.get('search', {}).get('exhaustive_verification', {})
    if verification.get('status') == 'FAIL':
        issues.append({'kind': prefix + '_DUPLICATE_INDEX_VERIFICATION_FAILED', 'status': 'FAIL'})
    return ('FAIL' if any(i['status'] == 'FAIL' for i in issues) else
            'REVIEW_REQUIRED' if issues else 'PASS', issues)


def _issue_failed(issue):
    if issue.get('status') in STATES:
        return issue['status'] == 'FAIL'
    return issue['kind'] not in ('MISSING_CUMULATIVE_QC', 'BATCH_QC_PENDING', 'CHECKER_GLOBAL_PENDING')


def _cumulative(state, path, dataset):
    if path is None:
        return 'REVIEW_REQUIRED', [{'kind': 'MISSING_CUMULATIVE_QC'}], None
    try:
        report = load_json(path)
        if report.get('schema_version') not in ('qc-cumulative-report', 'qc-cumulative-report-1'):
            raise ValueError('Unsupported cumulative QC evidence')
        declared = report.get('input_files_sha256')
        expected = {**state['history_packages'], str(dataset): _files(dataset)}
        if declared != expected:
            raise ValueError('Cumulative QC omits/changes the frozen history or current dataset')
        for root, files in expected.items():
            if _files(root) != files:
                raise ValueError('Cumulative history bytes changed: ' + root)
        if report.get('input_integrity_checked_before_and_after') is not True:
            return 'REVIEW_REQUIRED', [{'kind': 'CUMULATIVE_INPUT_INTEGRITY_MISSING', 'status': 'REVIEW_REQUIRED'}], report
        expected_ids = set(state['historical_sample_ids']) | {
            event['attempt']['sample_id'] for event in state['attempts'] if event['attempt']['status'] == 'SUCCEEDED'}
        if type(report.get('sample_count')) is not int or report['sample_count'] != len(expected_ids):
            raise ValueError('Cumulative QC sample count differs from the frozen union')
        manifest = report.get('manifest') or {}
        declared_manifest = {}
        for item in manifest.get('packages', []):
            root = str(_path(item['path']))
            if root in declared_manifest:
                raise ValueError('Cumulative manifest repeats a package')
            declared_manifest[root] = item['package_files_sha256']
        if (manifest.get('schema_version') not in ('qc-cumulative-set', 'qc-cumulative-set-1') or declared_manifest != expected
                or report.get('manifest_sha256') != object_sha256(manifest)):
            raise ValueError('Cumulative manifest does not bind exactly the frozen union')
        duplicate_status, duplicate_issues = _duplicate_evidence(report, cumulative=True, expected_ids=expected_ids)
        if duplicate_status != 'PASS':
            return duplicate_status, duplicate_issues, report
        if report.get('status') != 'PASS' or report.get('mechanical_status') != 'PASS' or report.get('errors'):
            return 'FAIL', [{'kind': 'CUMULATIVE_QC_FAILED', 'errors': report.get('errors')}], report
        return 'PASS', [], report
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return 'FAIL', [{'kind': 'INVALID_CUMULATIVE_QC', 'reason': str(error)}], None


def _summarize(state, qc_path, cumulative_path, checker_error, expected_inputs=None):
    spec = state['spec']
    issues = _binding_errors(state) + _capture_errors(state)
    limitations = []
    report = None
    dataset = None
    if checker_error:
        limitations.append({'kind': 'CHECKER_EXCEPTION', 'detail': checker_error})
    if qc_path:
        try:
            report = load_json(qc_path)
            dataset = _path(report.get('dataset', ''))
            if report.get('program') != 'quality-inspector' or report.get('scope') != 'delivery':
                raise ValueError('Only an actual quality-inspector report is accepted')
            if not dataset.is_relative_to(Path(spec['capture_root'])):
                raise ValueError('QC dataset is outside the sealed capture tree')
            if report.get('input_files_sha256', report.get('package_files_sha256')) != _files(dataset):
                raise ValueError('QC is not completely bound to sealed dataset bytes')
            if not isinstance(report.get('samples'), list):
                raise ValueError('QC sample results are absent')
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            limitations.append({'kind': 'QC_REPORT_EXCEPTION', 'detail': str(error)})
            report = None
    if report is None and not checker_error and not limitations:
        limitations.append({'kind': 'MISSING_QC_REPORT'})
    batch_failed = False
    batch_pending = False
    if report:
        checks = report.get('dataset_checks')
        if not isinstance(checks, list) or not checks or any(not isinstance(c, dict) for c in checks):
            limitations.append({'kind': 'MISSING_BATCH_QC_CHECKS'})
        else:
            batch_failed = any(c.get('status') == 'FAIL' for c in checks)
            batch_pending = any(c.get('status') != 'PASS' for c in checks)
            if batch_pending:
                issues.append({'kind': 'BATCH_QC_FAILED' if batch_failed else 'BATCH_QC_PENDING',
                               'rules': [c.get('rule_id') for c in checks if c.get('status') != 'PASS']})
            ids = Counter(c.get('rule_id') for c in checks)
            required_batch = set(REQUIRED_BATCH_RULES)
            if report.get('inspection_stage') == 'final':
                required_batch.add('DELIVERY_QC_REPORT')
            targets = report.get('local_profile', {}).get('configuration', {}).get('targets', {})
            if targets.get('expected_samples') is not None:
                required_batch.add('DELIVERY_EXPECTED_SAMPLES')
            if targets.get('expected_sites') is not None:
                required_batch.add('DELIVERY_EXPECTED_SITES')
            missing = sorted(rule for rule in required_batch if not ids[rule])
            if missing:
                issues.append({'kind': 'MISSING_REQUIRED_BATCH_RULES', 'rules': missing, 'status': 'REVIEW_REQUIRED'})
            if ids['DELIVERY_DOCUMENT_CONTENT'] < 2 or ids['DELIVERY_ATTACHMENT'] < 2:
                issues.append({'kind': 'INCOMPLETE_DOCUMENT_OR_ATTACHMENT_CHECKS', 'status': 'REVIEW_REQUIRED'})
        if report.get('status') not in STATES:
            limitations.append({'kind': 'INVALID_CHECKER_STATUS'})
        elif report['status'] != 'PASS' and not batch_pending and all(
                isinstance(row, dict) and row.get('status') == 'PASS' for row in report['samples']):
            batch_failed = report['status'] == 'FAIL'
            issues.append({'kind': 'CHECKER_GLOBAL_FAILED' if batch_failed else 'CHECKER_GLOBAL_PENDING'})
        for name in ('contract_status', 'delivery_status', 'local_acceptance_status'):
            if name in report and report[name] != report.get('status'):
                issues.append({'kind': 'CHECKER_STATUS_CONTRADICTION', 'field': name,
                               'status': 'FAIL' if 'FAIL' in (report[name], report.get('status')) else 'REVIEW_REQUIRED'})
        integrity = report.get('input_integrity') or {}
        if not isinstance(integrity, dict) or integrity.get('status') != 'PASS' or integrity.get('checked_before_and_after') is not True:
            issues.append({'kind': 'CHECKER_INPUT_INTEGRITY', 'status':
                'FAIL' if isinstance(integrity, dict) and integrity.get('status') == 'FAIL' else 'REVIEW_REQUIRED'})
        checksum = report.get('root_checksum') or {}
        if not isinstance(checksum, dict) or checksum.get('pass') is not True:
            issues.append({'kind': 'CHECKER_ROOT_CHECKSUM', 'status':
                'FAIL' if isinstance(checksum, dict) and checksum.get('pass') is False else 'REVIEW_REQUIRED'})
        if report.get('inspection_stage') not in ('payload', 'final'):
            issues.append({'kind': 'CHECKER_INSPECTION_STAGE_MISSING', 'status': 'REVIEW_REQUIRED'})
    cumulative_status, cumulative_issues, cumulative = _cumulative(state, cumulative_path, dataset) if dataset else (
        'REVIEW_REQUIRED', [{'kind': 'MISSING_CUMULATIVE_QC'}], None)
    issues.extend(cumulative_issues)
    attempts = [event['attempt'] for event in state['attempts']]
    successes = {row['task_id']: row for row in attempts if row['status'] == 'SUCCEEDED'}
    expected_ids = {row['sample_id'] for row in successes.values()}
    if report:
        issues.extend(_population_errors(state, dataset, successes))
        _, duplicate_issues = _duplicate_evidence(report, expected_ids=expected_ids)
        issues.extend(duplicate_issues)
    qc_rows = defaultdict(list)
    for row in (report or {}).get('samples', []):
        if not isinstance(row, dict) or not isinstance(row.get('sample_id'), str):
            issues.append({'kind': 'INVALID_QC_SAMPLE_ROW'})
            continue
        qc_rows[row['sample_id']].append(row)
    if set(qc_rows) - expected_ids:
        issues.append({'kind': 'EXTRA_QC_SAMPLES', 'sample_ids': sorted(set(qc_rows) - expected_ids)})
    if report and report.get('sample_count') != len(report['samples']):
        issues.append({'kind': 'QC_SAMPLE_COUNT_DIFFERS'})
    invalid_global_binding = any(_issue_failed(issue) for issue in issues)
    rows = []
    for task in spec['tasks']:
        attempt = successes.get(task['task_id'])
        task_attempts = [row for row in attempts if row['task_id'] == task['task_id']]
        sid = attempt['sample_id'] if attempt else None
        if not attempt:
            status = 'FAIL' if task_attempts else 'REVIEW_REQUIRED'
            reasons = ['CAPTURE_FAILED' if task_attempts else 'NOT_COLLECTED']
        elif len(qc_rows[sid]) != 1:
            status = 'FAIL' if len(qc_rows[sid]) > 1 else 'REVIEW_REQUIRED'
            reasons = ['REPEATED_QC_SAMPLE' if len(qc_rows[sid]) > 1 else 'MISSING_QC_SAMPLE']
        else:
            status, reasons = _sample_decision(qc_rows[sid][0], attempt)
        if attempt and status != 'FAIL' and (issues or limitations):
            status = 'FAIL' if invalid_global_binding or cumulative_status == 'FAIL' or batch_failed else 'REVIEW_REQUIRED'
            reasons += ['GLOBAL_EVIDENCE_UNRESOLVED']
        rows.append({key: task[key] for key in ('task_id', 'site_id', 'domain', 'uri', 'category')} |
                    {'sample_id': sid, 'collected': bool(attempt), 'status': status,
                     'business_id': task.get('business_id') if isinstance(task.get('business_id'), str) else 'UNKNOWN',
                     'reasons': reasons, 'attempt_ids': [r['attempt_id'] for r in task_attempts]})
    final_binding_errors = _binding_errors(state) + _capture_errors(state) + _history_errors(state)
    for name, ref in (expected_inputs or {}).items():
        if ref:
            try:
                actual_sha = file_sha(ref['path'])
            except OSError:
                actual_sha = None
            if actual_sha != ref.get('sha256'):
                final_binding_errors.append({'kind': 'QC_EVIDENCE_CHANGED_DURING_REPORT', 'input': name})
    if final_binding_errors:
        issues += [error for error in final_binding_errors if error not in issues]
        for row in rows:
            if row['collected']:
                row['status'] = 'FAIL'
                row['reasons'].append('FROZEN_BYTES_CHANGED_DURING_REPORT')
    counts = {status: sum(row['status'] == status for row in rows) for status in STATES}
    collected_counts = {status: sum(row['collected'] and row['status'] == status for row in rows) for status in STATES}
    passed = counts['PASS']
    collected = len(successes)
    by_site = {}
    by_category = {}
    by_domain = {}
    by_business = {}
    by_rule = Counter()
    for key, target in (('site_id', by_site), ('category', by_category),
                        ('domain', by_domain), ('business_id', by_business)):
        for identity in sorted({row[key] for row in rows}):
            selected = [row for row in rows if row[key] == identity]
            target[identity] = {status: sum(row['status'] == status for row in selected) for status in STATES}
    for row in rows:
        by_rule.update(row['reasons'])
    finished = _now()
    elapsed = (datetime.fromisoformat(finished) - datetime.fromisoformat(state['created_at_utc'])).total_seconds()
    capture_elapsed = (datetime.fromisoformat(state['seal']['created_at_utc']) -
                       datetime.fromisoformat(state['created_at_utc'])).total_seconds()
    return {'schema_version': VERSION + '-report', 'created_at_utc': finished,
            'cohort_id': spec['cohort_id'], 'campaign_id': spec['campaign_id'],
            'spec_sha256': state['spec_sha256'], 'seal_manifest_sha256': state['seal']['files_manifest_sha256'],
            'status': 'FAIL' if (report or {}).get('status') == 'FAIL' or counts['FAIL'] or any(_issue_failed(i) for i in issues) else
                      'REVIEW_REQUIRED' if counts['REVIEW_REQUIRED'] or limitations else 'PASS',
            'target_count': TARGET, 'collected_count': collected, 'collection_gap': TARGET - collected,
            'formal_1000_collection_complete': collected == TARGET,
            'cohort_status_counts': counts, 'collected_sample_status_counts': collected_counts,
            'primary_success_rate': {'numerator': passed, 'denominator': TARGET, 'value': passed / TARGET,
                                     'label': 'formal cohort pass rate' if collected == TARGET else 'target pass coverage'},
            'collected_sample_pass_rate': {'numerator': passed, 'denominator': collected,
                                          'value': passed / collected if collected else None,
                                          'label': 'collected samples only'},
            'capture_attempt_count': len(attempts),
            'failed_capture_attempt_count': sum(row['status'] == 'FAILED' for row in attempts),
            'capture_success_per_attempt': collected / len(attempts) if attempts else None,
            'measured_wall_seconds': {'freeze_to_seal': capture_elapsed, 'freeze_to_qc_summary': elapsed,
                                      'seal_to_qc_summary': elapsed - capture_elapsed},
            'qualified_samples_per_hour_including_qc': passed * 3600 / elapsed if elapsed > 0 else None,
            'by_site': by_site, 'by_domain': by_domain, 'by_category': by_category,
            'by_business': by_business, 'by_rule_or_failure_reason': dict(by_rule),
            'samples': rows, 'attempts': attempts,
            'cost_evidence': [{'attempt_id': row['attempt_id'], 'reference': row['cost_reference']} for row in attempts],
            'actual_provider_charge': 'UNKNOWN', 'issues': issues, 'limitations': limitations,
            'qc_evidence': deepcopy(expected_inputs or {}),
            'source_qc_sample_status_counts': dict(Counter(row.get('status') if isinstance(row.get('status'), str) else 'INVALID' for row in
                (report or {}).get('samples', []) if isinstance(row, dict))),
            'source_qc_dataset_checks': (report or {}).get('dataset_checks', []),
            'checker_status': (report or {}).get('status', 'EXCEPTION_OR_NOT_RUN'),
            'source_qc_inspection_stage': (report or {}).get('inspection_stage', 'UNKNOWN'),
            'source_qc_release_ready': (report or {}).get('release_ready', 'UNKNOWN'),
            'cumulative_status': cumulative_status,
            'evidence_semantics': 'Summarizes bound QC; no new semantic judgment, human approval or customer acceptance.',
            'customer_acceptance': 'UNKNOWN', 'post_qc_action': 'STOP_AND_WAIT_FOR_USER'}


def _exception_report(state, error, inputs):
    """A broken checker/summarizer closes the round; it never invites rescoring."""
    attempts = [event['attempt'] for event in state['attempts']]
    successes = {row['task_id']: row for row in attempts if row['status'] == 'SUCCEEDED'}
    failed_tasks = {row['task_id'] for row in attempts if row['status'] == 'FAILED'} - successes.keys()
    rows = []
    for task in state['spec']['tasks']:
        attempt = successes.get(task['task_id'])
        rows.append({key: task[key] for key in ('task_id', 'site_id', 'domain', 'uri', 'category')} |
            {'sample_id': attempt.get('sample_id') if attempt else None, 'collected': bool(attempt),
             'status': 'FAIL' if task['task_id'] in failed_tasks else 'REVIEW_REQUIRED',
             'reasons': ['CHECKER_SUMMARIZER_EXCEPTION']})
    count = len(successes)
    grouped = {}
    for field in ('site_id', 'domain', 'category'):
        grouped[field] = {identity: {status: sum(row[field] == identity and row['status'] == status for row in rows)
                                    for status in STATES} for identity in sorted({row[field] for row in rows})}
    return {'schema_version': VERSION + '-report', 'created_at_utc': _now(),
        'cohort_id': state['spec']['cohort_id'], 'campaign_id': state['spec']['campaign_id'],
        'spec_sha256': state['spec_sha256'], 'seal_manifest_sha256': state['seal']['files_manifest_sha256'],
        'status': 'FAIL', 'target_count': TARGET, 'collected_count': count, 'collection_gap': TARGET - count,
        'formal_1000_collection_complete': count == TARGET,
        'cohort_status_counts': {'PASS': 0, 'FAIL': len(failed_tasks), 'REVIEW_REQUIRED': TARGET - len(failed_tasks)},
        'collected_sample_status_counts': {'PASS': 0, 'FAIL': 0, 'REVIEW_REQUIRED': count},
        'primary_success_rate': {'numerator': 0, 'denominator': TARGET, 'value': 0,
            'label': 'formal cohort pass rate' if count == TARGET else 'target pass coverage'},
        'collected_sample_pass_rate': {'numerator': 0, 'denominator': count, 'value': 0 if count else None,
                                       'label': 'collected samples only'},
        'capture_attempt_count': len(attempts),
        'failed_capture_attempt_count': sum(row['status'] == 'FAILED' for row in attempts),
        'capture_success_per_attempt': count / len(attempts) if attempts else None,
        'attempts': attempts, 'samples': rows, 'qc_evidence': deepcopy(inputs),
        'by_site': grouped['site_id'], 'by_domain': grouped['domain'], 'by_category': grouped['category'],
        'by_business': {'UNKNOWN': {'PASS': 0, 'FAIL': len(failed_tasks), 'REVIEW_REQUIRED': TARGET - len(failed_tasks)}},
        'by_rule_or_failure_reason': {'CHECKER_SUMMARIZER_EXCEPTION': TARGET},
        'cost_evidence': [{'attempt_id': row['attempt_id'], 'reference': row['cost_reference']} for row in attempts],
        'issues': [], 'limitations': [{'kind': 'CHECKER_SUMMARIZER_EXCEPTION',
            'exception_type': type(error).__name__, 'detail': str(error)}],
        'checker_status': 'EXCEPTION', 'actual_provider_charge': 'UNKNOWN',
        'customer_acceptance': 'UNKNOWN', 'post_qc_action': 'STOP_AND_WAIT_FOR_USER'}


def finalize(state_path, qc_report=None, output=None, *, cumulative_report=None, checker_error=None):
    """Publish exactly one score, persist checker exceptions, and stop the cohort."""
    with _lock(state_path) as path:
        state = _state_read(path)
        root = Path(state['spec']['capture_root'])
        if output is None:
            raise ValueError('An external output path is required')
        output = _outside(output, root)
        _outside_history(output, state['history_packages'])
        if output == path:
            raise ValueError('A report cannot replace cohort state')
        inputs = {}
        for name, source in (('qc_report', qc_report), ('cumulative_report', cumulative_report)):
            if source:
                source = _outside(source, root)
                _outside_history(source, state['history_packages'])
                if source in (path, output):
                    raise ValueError('QC evidence, report and state need distinct paths')
                try:
                    inputs[name] = {'path': str(source), 'sha256': file_sha(source)}
                except OSError as error:
                    inputs[name] = {'path': str(source), 'sha256': None,
                                    'read_error': type(error).__name__}
            else:
                inputs[name] = None
        request = {'inputs': inputs, 'checker_error': checker_error, 'output': str(output)}
        result = None
        if state['phase'] in ('EVALUATING', 'FINALIZING', 'FINALIZED'):
            if request != state['finalization']['request']:
                raise ValueError('This cohort already has its fixed evaluation; rescoring is prohibited')
            if state['phase'] == 'FINALIZED':
                if file_sha(output) != state['finalization']['report_sha256']:
                    raise ValueError('Finalized report bytes changed')
                if _binding_errors(state) or _capture_errors(state) or _history_errors(state):
                    raise ValueError('Finalized evidence bytes changed; score remains immutable')
                return load_json(output)
            result = state['finalization'].get('report')
        else:
            if state['phase'] != 'SEALED':
                raise ValueError('Seal all capture files before unified QC finalization')
            # Freeze exact QC inputs before reading decisions. A hard interruption
            # cannot reopen the round with a different/improved checker output.
            state['phase'] = 'EVALUATING'
            state['finalization'] = {'request': request, 'started_at_utc': _now()}
            _state_write(path, state)
        if result is None:
            try:
                result = _summarize(state, qc_report, cumulative_report, checker_error, inputs)
            except Exception as error:
                result = _exception_report(state, error, inputs)
            # Seal the score before publication; crash recovery cannot recompute it.
            state['phase'] = 'FINALIZING'
            state['finalization']['report'] = result
            _state_write(path, state)
        save_json(output, result)
        state['phase'] = 'FINALIZED'
        state['finalization']['report_sha256'] = file_sha(output)
        state['finalization']['completed_at_utc'] = _now()
        _state_write(path, state)
        return result


def verify(state_path):
    """Read-only recheck; post-QC modifications are reported without rescoring."""
    state = _state_read(_path(state_path))
    errors = _binding_errors(state)
    if state['phase'] != 'COLLECTING':
        errors += _capture_errors(state) + _history_errors(state)
    if state['phase'] == 'FINALIZED':
        final = state['finalization']
        try:
            if file_sha(final['request']['output']) != final['report_sha256']:
                errors.append({'kind': 'FINALIZED_REPORT_CHANGED'})
        except OSError as error:
            errors.append({'kind': 'FINALIZED_REPORT_MISSING', 'reason': str(error)})
    if state['phase'] in ('EVALUATING', 'FINALIZING', 'FINALIZED'):
        for name, ref in state['finalization']['request']['inputs'].items():
            if ref:
                try:
                    actual = file_sha(ref['path'])
                except OSError:
                    actual = None
                if actual != ref.get('sha256'):
                    errors.append({'kind': 'FROZEN_QC_INPUT_CHANGED', 'input': name})
    return {'schema_version': VERSION + '-verification', 'phase': state['phase'],
            'status': 'FAIL' if errors else 'PASS', 'errors': errors,
            'cohort_id': state['spec']['cohort_id'], 'attempt_count': len(state['attempts']),
            'formal_collection_stopped': bool(state.get('integrity_breaches')) or
                state['phase'] in ('SEALED', 'EVALUATING', 'FINALIZING', 'FINALIZED')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('freeze'); p.add_argument('--spec', required=True); p.add_argument('--state', required=True)
    p = commands.add_parser('record'); p.add_argument('--state', required=True); p.add_argument('--attempt', required=True)
    p = commands.add_parser('seal'); p.add_argument('--state', required=True); p.add_argument('--capture-root')
    p = commands.add_parser('finalize'); p.add_argument('--state', required=True); p.add_argument('--qc-report')
    p.add_argument('--cumulative-report'); p.add_argument('--checker-error'); p.add_argument('--output', required=True)
    for name in ('verify', 'read'):
        p = commands.add_parser(name); p.add_argument('--state', required=True)
    args = parser.parse_args(argv)
    if args.command == 'freeze': result = freeze(args.spec, args.state)
    elif args.command == 'record': result = record(args.state, args.attempt)
    elif args.command == 'seal': result = seal(args.state, args.capture_root)
    elif args.command == 'finalize': result = finalize(args.state, args.qc_report, args.output,
        cumulative_report=args.cumulative_report, checker_error=args.checker_error)
    elif args.command == 'verify': result = verify(args.state)
    else: result = _state_read(_path(args.state))
    if args.command in ('freeze', 'record', 'seal'):
        result = {'state': str(_path(args.state)), 'phase': result['phase'],
                  'attempt_count': len(result['attempts']), 'spec_sha256': result['spec_sha256']}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
