"""Explicit, initially empty current-run history; never imports old delivery data.

The manifest is immutable. Its dedicated M4 registry owns incremental result
membership. This module does not grant admission, QC approval, or production IDs.
"""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit, urlunsplit

from .batch_core import file_sha, load_json, save_json
from .planning import object_sha256

MANIFEST_SCHEMA = 'webcollect-current-chain-manifest-1'
SCOPE_SCHEMA = 'webcollect-current-chain-1'


def _require(condition, message):
    if not condition:
        raise ValueError('CURRENT_CHAIN: ' + message)


def _path(value):
    path = Path(value)
    _require(path.is_absolute(), 'absolute current-chain paths required')
    _require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink paths are forbidden')
    return path.resolve()


def _ref(path):
    path = _path(path)
    _require(path.is_file(), 'bound file missing')
    return {'path': str(path), 'sha256': file_sha(path)}


def _manifest(path):
    path = _path(path)
    data = load_json(path)
    _require(set(data) == {'schema_version', 'chain_id', 'registry', 'current_result_roots',
                           'created_at', 'history_policy'}
             and data['schema_version'] == MANIFEST_SCHEMA
             and isinstance(data['chain_id'], str) and data['chain_id'].strip()
             and data['history_policy'] == 'current-chain-only', 'explicit current-chain manifest required')
    registry = _path(data['registry'])
    roots = data['current_result_roots']
    _require(isinstance(roots, list) and roots and len(roots) == len(set(roots)), 'unique result roots required')
    actual = [_path(root) for root in roots]
    _require(all(not a.is_relative_to(b) and not b.is_relative_to(a)
                 for i, a in enumerate(actual) for b in actual[i+1:]), 'overlapping result roots')
    _require(registry != path, 'manifest cannot be the registry')
    return data, _ref(path)


def _meta(registry):
    registry = _path(registry)
    _require(registry.is_file(), 'dedicated current-chain registry missing')
    with closing(sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True)) as con:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        _require('current_chain_meta' in tables and 'current_chain_results' in tables,
                 'unmarked/legacy registry cannot enter the current chain')
        rows = list(con.execute('SELECT binding_json FROM current_chain_meta'))
        _require(len(rows) == 1, 'current-chain registry binding missing or ambiguous')
        return json.loads(rows[0][0])


def assert_registry_scope(scope, registry):
    _require(isinstance(scope, dict) and scope.get('schema_version') == SCOPE_SCHEMA,
             'explicit current-chain scope required')
    data, reference = _manifest(scope['manifest']['path'])
    _require(reference == scope['manifest'] and str(_path(registry)) == data['registry']
             and scope.get('registry') == data['registry'] and scope.get('chain_id') == data['chain_id']
             and scope.get('current_result_roots') == data['current_result_roots'],
             'manifest, chain, result roots, or exact registry changed')
    _require(_meta(registry) == {'chain_id': data['chain_id'], 'manifest': reference,
                                'registry': data['registry'], 'current_result_roots': data['current_result_roots']},
             'registry belongs to another or historical chain')


def assert_current_result_path(scope, path):
    path = _path(path)
    _require(any(path.is_relative_to(_path(root)) for root in scope['current_result_roots']),
             'historical/out-of-chain result path rejected')
    return path


def initialize_chain(manifest_path, registry, *, chain_id, current_result_roots, now=None):
    """Create an explicitly new empty population; reuse only its exact binding.

    Existing unmarked registries and populated result directories are rejected,
    rather than copied, reset, deleted, or silently treated as empty.
    """
    manifest_path, registry = _path(manifest_path), _path(registry)
    roots = [str(_path(root)) for root in current_result_roots]
    if manifest_path.exists():
        data, _ = _manifest(manifest_path)
        _require(data['chain_id'] == chain_id and data['registry'] == str(registry)
                 and data['current_result_roots'] == roots, 'cannot rebind an existing chain')
        return read_chain_history(manifest_path)[1]
    _require(not registry.exists(), 'existing registry cannot initialize an empty chain')
    for root in roots:
        folder = Path(root)
        _require(not folder.exists() or not any(folder.rglob('annotation.json')),
                 'initial current result population must be empty; historical packages cannot be adopted')
    data = {'schema_version': MANIFEST_SCHEMA, 'chain_id': chain_id, 'registry': str(registry),
            'current_result_roots': roots, 'created_at': time.time() if now is None else now,
            'history_policy': 'current-chain-only'}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(manifest_path, data)
    reference = _ref(manifest_path)
    binding = {'chain_id': chain_id, 'manifest': reference, 'registry': str(registry),
               'current_result_roots': roots}
    registry.parent.mkdir(parents=True, exist_ok=True)
    from .runtime import SCHEMA
    from .storage import ensure_registry_schema
    with closing(sqlite3.connect(registry)) as con:
        ensure_registry_schema(con)
        con.executescript(SCHEMA)
        con.execute('CREATE TABLE current_chain_meta (id INTEGER PRIMARY KEY CHECK(id=1), binding_json TEXT NOT NULL)')
        con.execute('CREATE TABLE current_chain_results (sample_id TEXT PRIMARY KEY, annotation_path TEXT NOT NULL UNIQUE, '
                    'annotation_sha256 TEXT NOT NULL, site_uri TEXT NOT NULL, task_key TEXT NOT NULL, recorded_at REAL NOT NULL)')
        con.execute('INSERT INTO current_chain_meta VALUES(1,?)', (json.dumps(binding, sort_keys=True),))
        con.commit()
    return read_chain_history(manifest_path)[1]


def read_chain_history(manifest_path):
    data, reference = _manifest(manifest_path)
    scope = {'schema_version': SCOPE_SCHEMA, 'manifest': reference, 'chain_id': data['chain_id'],
             'registry': data['registry'], 'current_result_roots': data['current_result_roots']}
    assert_registry_scope(scope, data['registry'])
    with closing(sqlite3.connect(Path(data['registry']).as_uri() + '?mode=ro', uri=True)) as con:
        stored = list(con.execute('SELECT sample_id,annotation_path,annotation_sha256,site_uri,task_key '
                                  'FROM current_chain_results ORDER BY sample_id'))
        records, references = [], []
        for sample_id, annotation_path, digest, site_uri, task_key in stored:
            path = assert_current_result_path(scope, annotation_path)
            _require(_ref(path)['sha256'] == digest, 'current result annotation changed')
            annotation = load_json(path)
            _require(annotation.get('sample_id') == sample_id and path.parent.name == sample_id,
                     'current result identity changed')
            _require(con.execute('SELECT 1 FROM m4_attempts WHERE sample_id=? AND task_key=?',
                                 (sample_id, task_key)).fetchone() is not None,
                     'result is not an actual attempt in the dedicated registry')
            uri = urlsplit(site_uri)
            _require(uri.scheme in ('http', 'https') and uri.hostname and not uri.username and not uri.password,
                     'public current result site identity required')
            from .task_generation import annotation_business_strategy, semantic_signature
            strategy = annotation_business_strategy(annotation, path.parent)
            references.append({'path': str(path), 'sha256': digest})
            records.append({'sample_id': sample_id, 'annotation_path': str(path), 'annotation_sha256': digest,
                            'site_uri': site_uri, 'origin': urlunsplit((uri.scheme, uri.netloc, '', '', '')),
                            'strategy_id': strategy,
                            'classification': 'KNOWN_STRATEGY' if strategy else 'UNKNOWN_REQUIRES_COMPARISON',
                            'semantic_signature': semantic_signature({'site_uri': site_uri,
                                'deterministic_strategy': {'id': strategy}}) if strategy else None})
    scope.update(current_results_refs=references, customer_samples=len(records), package_count=0, packages=[],
                 known_strategy_samples=sum(r['strategy_id'] is not None for r in records),
                 unknown_strategy_samples=sum(r['strategy_id'] is None for r in records),
                 coverage='current-chain-only; initial population may be empty')
    return records, scope


def scope_for_registry(registry):
    binding = _meta(registry)
    scope = read_chain_history(binding['manifest']['path'])[1]
    assert_registry_scope(scope, registry)
    return scope


def is_current_registry(registry):
    path = Path(registry).resolve()
    if not path.is_file():
        return False
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as con:
        return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='current_chain_meta'").fetchone() is not None


def registry_snapshot(scope, registry, *, exclude_scope=None, own_tasks=()):
    assert_registry_scope(scope, registry)
    from .task_admission import registry_snapshot as original_snapshot
    snapshot = original_snapshot(registry, exclude_scope=exclude_scope, own_tasks=own_tasks)
    # Every current task must originate from a plan explicitly bound to this
    # chain. Copying old tasks into a new database cannot import old history.
    with closing(sqlite3.connect(Path(registry).resolve().as_uri() + '?mode=ro', uri=True)) as con:
        for row in snapshot['rows']:
            plans = [load for (raw,) in con.execute('SELECT plan_json FROM m4_plans WHERE scope_id=?',
                     (row['scope_id'],)) for load in [json.loads(raw)]]
            _require(any(any(same_chain(plan.get(key, {}).get('history_scope'), scope) for key in
                            ('generation', 'observed_workflow_generation')) and row['task'] in plan.get('tasks', [])
                         for plan in plans), 'task was not registered by a plan bound to this current chain')
    return snapshot


def same_chain(left, right):
    """Stable chain ownership; result membership is checked separately live."""
    keys = ('schema_version', 'manifest', 'chain_id', 'registry', 'current_result_roots')
    return (isinstance(left, dict) and isinstance(right, dict)
            and left.get('schema_version') == right.get('schema_version') == SCOPE_SCHEMA
            and all(left.get(key) == right.get(key) for key in keys))


def validate_history_context(value):
    scope = value.get('history_scope', {})
    records, actual = read_chain_history(scope.get('manifest', {}).get('path', ''))
    _require(scope == actual and value == history_context(actual, records, actual['registry']),
             'current context contains missing, historical, or unbound comparisons')
    return True


def assert_current_evidence(scope, value):
    """Fence adoption of this run's raw evidence, without changing its bytes.

    The scope folder is inside the explicitly named current-run evidence root.
    Only that run and the new result roots may supply observed sample evidence;
    old delivery/candidate/registry references are not followed.
    """
    assert_registry_scope(scope, scope['registry'])
    evidence_root = _path(scope['manifest']['path']).parent.parent
    roots = [evidence_root, *[_path(root) for root in scope['current_result_roots']]]
    visited = set()
    def walk(item):
        if isinstance(item, list):
            for entry in item:
                walk(entry)
        elif isinstance(item, dict):
            if item.get('schema_version') in ('webcollect-task-history-scope-1', 'qc-cumulative-set-1'):
                raise ValueError('CURRENT_CHAIN: historical population reference rejected')
            if set(item) == {'path', 'sha256'}:
                path = _path(item['path'])
                _require(any(path.is_relative_to(root) for root in roots),
                         'historical/out-of-chain observation reference rejected')
                _require(_ref(path) == item, 'current observation reference changed')
                if path.suffix == '.json' and str(path) not in visited:
                    visited.add(str(path)); walk(load_json(path))
            else:
                for entry in item.values():
                    walk(entry)
    walk(value)
    return True


def history_context(scope, records, registry, *, exclude_scope=None, own_tasks=()):
    actual_records, actual_scope = read_chain_history(scope['manifest']['path'])
    _require(scope == actual_scope and records == actual_records, 'current population or scope changed')
    snapshot = registry_snapshot(scope, registry, exclude_scope=exclude_scope, own_tasks=own_tasks)
    comparisons = [{'id': 'customer:' + row['sample_id'], 'record': row} for row in records]
    comparisons += [{'id': 'm4:' + object_sha256(row), 'record': row} for row in snapshot['rows']]
    return {'history_scope': deepcopy(scope), 'customer_history_sha256': object_sha256(records),
            'registry_snapshot': snapshot, 'comparisons': sorted(comparisons, key=lambda row: row['id'])}


def append_current_result(manifest_path, annotation_path, *, site_uri, task_key):
    """Index a real current attempt for later comparisons; never marks QC PASS."""
    _, scope = read_chain_history(manifest_path)
    path = assert_current_result_path(scope, annotation_path)
    annotation = load_json(path); sample_id = annotation.get('sample_id')
    _require(isinstance(sample_id, str) and path.name == 'annotation.json' and path.parent.name == sample_id,
             'actual current annotation/sample identity required')
    with closing(sqlite3.connect(scope['registry'])) as con:
        _require(con.execute('SELECT 1 FROM m4_attempts WHERE sample_id=? AND task_key=?',
                             (sample_id, task_key)).fetchone() is not None,
                 'result has no original current-chain attempt')
        old = con.execute('SELECT annotation_path,annotation_sha256,site_uri,task_key FROM current_chain_results '
                          'WHERE sample_id=?', (sample_id,)).fetchone()
        values = (str(path), file_sha(path), site_uri, task_key)
        if old:
            _require(tuple(old) == values, 'cannot replace a registered current result')
        else:
            con.execute('INSERT INTO current_chain_results VALUES(?,?,?,?,?,?)',
                        (sample_id, *values, time.time()))
            con.commit()
    return read_chain_history(manifest_path)
