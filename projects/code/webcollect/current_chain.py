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
PROJECT_RULES = 'candidate-project-2'
POOL_CHECKPOINT = ('webcollect/candidate-project', 'manifest')


class CurrentChainError(ValueError):
    """A deterministic chain/input failure, never a reason to retry dispatch."""

    def __init__(self, message, *, context=None):
        self.message = message
        self.context = dict(context or {})
        detail = ('; context=' + json.dumps(self.context, ensure_ascii=False, sort_keys=True)
                  if self.context else '')
        super().__init__('CURRENT_CHAIN: ' + message + detail)


def _require(condition, message, *, context=None):
    if not condition:
        raise CurrentChainError(message, context=context)


def _path(value):
    path = Path(value)
    _require(path.is_absolute(), 'absolute current-chain paths required')
    _require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink paths are forbidden')
    return path.resolve()


def _ref(path):
    path = _path(path)
    _require(path.is_file(), 'bound file missing')
    return {'path': str(path), 'sha256': file_sha(path)}


def _validate_project(project, registry, manifest):
    _require(isinstance(project, dict) and set(project) == {'rules', 'pool', 'site_ledger'}
             and project['rules'] == PROJECT_RULES, 'unsupported candidate project rules')
    _require(len({_path(project['pool']), _path(project['site_ledger']), registry, manifest}) == 4,
             'candidate project stores must be distinct')


def _manifest(path):
    path = _path(path)
    data = load_json(path)
    _require(set(data) - {'candidate_project'} == {'schema_version', 'chain_id', 'registry', 'current_result_roots',
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
    if 'candidate_project' in data:
        _validate_project(data['candidate_project'], registry, path)
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
    _require(scope.get('candidate_project') == data.get('candidate_project'), 'candidate project binding changed')
    binding = {'chain_id': data['chain_id'], 'manifest': reference, 'registry': data['registry'],
               'current_result_roots': data['current_result_roots']}
    if 'candidate_project' in data:
        binding['candidate_project'] = data['candidate_project']
    _require(_meta(registry) == binding, 'registry belongs to another or historical chain')


def assert_current_result_path(scope, path):
    path = _path(path)
    _require(any(path.is_relative_to(_path(root)) for root in scope['current_result_roots']),
             'historical/out-of-chain result path rejected')
    return path


def initialize_chain(manifest_path, registry, *, chain_id, current_result_roots, now=None, candidate_project=None):
    """Create an explicitly new empty population; reuse only its exact binding.

    Existing unmarked registries and populated result directories are rejected,
    rather than copied, reset, deleted, or silently treated as empty.
    """
    manifest_path, registry = _path(manifest_path), _path(registry)
    if candidate_project is not None:
        _validate_project(candidate_project, registry, manifest_path)
    roots = [str(_path(root)) for root in current_result_roots]
    if manifest_path.exists():
        data, _ = _manifest(manifest_path)
        _require(data['chain_id'] == chain_id and data['registry'] == str(registry)
                 and data['current_result_roots'] == roots and data.get('candidate_project') == candidate_project,
                 'cannot rebind an existing chain')
        return read_chain_history(manifest_path)[1]
    _require(not registry.exists(), 'existing registry cannot initialize an empty chain')
    for root in roots:
        folder = Path(root)
        _require(not folder.exists() or not any(folder.rglob('annotation.json')),
                 'initial current result population must be empty; historical packages cannot be adopted')
    data = {'schema_version': MANIFEST_SCHEMA, 'chain_id': chain_id, 'registry': str(registry),
            'current_result_roots': roots, 'created_at': time.time() if now is None else now,
            'history_policy': 'current-chain-only'}
    project_fields = {'candidate_project': candidate_project} if candidate_project is not None else {}
    data.update(project_fields)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(manifest_path, data)
    reference = _ref(manifest_path)
    binding = {'chain_id': chain_id, 'manifest': reference, 'registry': str(registry),
               'current_result_roots': roots, **project_fields}
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


def read_chain_scope(manifest_path):
    data, reference = _manifest(manifest_path)
    scope = {'schema_version': SCOPE_SCHEMA, 'manifest': reference, 'chain_id': data['chain_id'],
             'registry': data['registry'], 'current_result_roots': data['current_result_roots']}
    if 'candidate_project' in data:
        scope['candidate_project'] = data['candidate_project']
    assert_registry_scope(scope, data['registry'])
    return scope


def read_chain_history(manifest_path):
    scope = read_chain_scope(manifest_path)
    with closing(sqlite3.connect(Path(scope['registry']).as_uri() + '?mode=ro', uri=True)) as con:
        # Pin membership and task/attempt identity to one SQLite read snapshot;
        # peer consumers may append while original files are being checked.
        con.execute('BEGIN')
        stored = list(con.execute(
            'SELECT r.sample_id,r.annotation_path,r.annotation_sha256,r.site_uri,r.task_key,t.task_json, '
            'EXISTS(SELECT 1 FROM m4_attempts a WHERE a.sample_id=r.sample_id AND a.task_key=r.task_key) '
            'FROM current_chain_results r LEFT JOIN m4_tasks t ON t.task_key=r.task_key ORDER BY r.sample_id'))
        # Release the short read transaction before hashing original files.
        con.rollback()
    records, references, research_references = [], [], []
    for sample_id, annotation_path, digest, site_uri, task_key, task_json, actual_attempt in stored:
        path = assert_current_result_path(scope, annotation_path)
        _require(_ref(path)['sha256'] == digest, 'current result annotation changed')
        annotation = load_json(path)
        _require(annotation.get('sample_id') == sample_id and path.parent.name == sample_id,
                 'current result identity changed')
        _require(actual_attempt, 'result is not an actual attempt in the dedicated registry')
        if task_json:
            from .candidate_contract import research_duplicate_basis
            research = research_duplicate_basis(json.loads(task_json), scope['registry'])
            if research:
                research_references.append({'sample_id':sample_id,'annotation':{'path':str(path),'sha256':digest},
                                            'claim_id':research['research_claim_id'],'production_counted':False})
                continue
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
                 research_results_refs=research_references, research_samples=len(research_references),
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


def _physical(value):
    """Physical location of a recorded chain path. The retained project-layout
    symlinks keep pre-migration records pointing at the same files; identity
    comparisons resolve through them, execution paths stay real (see _path)."""
    return Path(value).resolve()


def _chain_identity(value):
    """Layout-stable chain identity. The project moved its databases to the
    prod anchor and re-declared the manifest under the new paths; chain
    membership is the same physical registry, stores, result roots and id."""
    if not isinstance(value, dict):
        return None
    manifest = value.get('manifest') if isinstance(value.get('manifest'), dict) else {}
    project = value.get('candidate_project') if isinstance(value.get('candidate_project'), dict) else None
    identity = {
        'schema_version': value.get('schema_version'),
        'chain_id': value.get('chain_id'),
        'manifest': str(_physical(manifest['path'])) if manifest.get('path') else None,
        'registry': str(_physical(value.get('registry'))),
        'current_result_roots': [str(_physical(root)) for root in value.get('current_result_roots') or []]}
    if project is not None:
        identity['candidate_project'] = {key: (str(_physical(project[key])) if key in ('pool', 'site_ledger')
                                               else project.get(key))
                                         for key in ('rules', 'pool', 'site_ledger')}
    return identity


def same_chain(left, right):
    """Stable chain ownership; result membership is checked separately live."""
    return (isinstance(left, dict) and isinstance(right, dict)
            and left.get('schema_version') == right.get('schema_version') == SCOPE_SCHEMA
            and _chain_identity(left) == _chain_identity(right))


def history_scope_extends(bound, actual):
    """Candidate-project history v2: immutable binding with append-only results.

    Frozen legacy chains retain exact population semantics. Every bound result
    must still exist with the original reference; read_chain_history validates
    bytes and registry identity before this comparison.
    """
    if not same_chain(bound, actual) or not bound.get('candidate_project'):
        return bound == actual
    changing = {'current_results_refs', 'research_results_refs', 'customer_samples',
                'research_samples', 'known_strategy_samples', 'unknown_strategy_samples'}
    identity_keys = {'schema_version', 'manifest', 'chain_id', 'registry', 'current_result_roots', 'candidate_project'}
    if {k: v for k, v in bound.items() if k not in changing and k not in identity_keys} != {
            k: v for k, v in actual.items() if k not in changing and k not in identity_keys}:
        return False
    if _chain_identity(bound) != _chain_identity(actual):
        return False
    for value in (bound, actual):
        if (value.get('customer_samples') != len(value.get('current_results_refs', []))
                or value.get('research_samples') != len(value.get('research_results_refs', []))
                or value.get('known_strategy_samples', 0) + value.get('unknown_strategy_samples', 0)
                   != value.get('customer_samples')):
            return False
    for key in ('current_results_refs', 'research_results_refs'):
        if any(ref not in actual.get(key, []) for ref in bound.get(key, [])):
            return False
    return True


def registry_project(con):
    """Return the frozen owner only for a new-generation registry, including inside a transaction."""
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='current_chain_meta'").fetchone():
        binding = json.loads(con.execute('SELECT binding_json FROM current_chain_meta WHERE id=1').fetchone()[0])
        if 'candidate_project' in binding:
            return binding
    return None


def check_project_pool(scope, pool):
    project = (scope or {}).get('candidate_project')
    marker = pool.checkpoint(*POOL_CHECKPOINT)
    _require(marker == (scope['manifest'] if project else None)
             and (not project or str(pool.path) == project['pool']), 'candidate pool belongs to another project')
    return bool(project)


def check_project_guard(scope, guard, job_ledger=None, *, role=None):
    project = (scope or {}).get('candidate_project')
    guard = guard or {}
    if project or 'dispatch_rules' in guard:
        _require(project and guard.get('dispatch_rules') == project['rules']
                 and guard.get('campaign_id') == scope['chain_id'] and guard.get('ledger') == project['site_ledger'],
                 'site execution ledger and rules must match the candidate project')
        if job_ledger is not None:
            path = _path(Path(job_ledger).absolute())
            _require(role in ('producer','consumer') and
                     path == _path(scope['registry']).with_name(role + '-jobs.sqlite3'),
                     'use the original role job ledger of this candidate project')


def require_plan(plan, registry, policy):
    """Marked registries require evidence identity and their original dispatch rules.

    Legacy unmarked registries retain their original contract. Validate before
    preflight/dispatch, without creating or resetting any ledger.
    """
    if not is_current_registry(registry):
        return False
    scope = scope_for_registry(registry)
    supplied = plan.get('generation', {}).get('history_scope') or plan.get('observed_workflow_generation', {}).get('history_scope')
    _require(isinstance(supplied, dict) and same_chain(scope, supplied), 'new task must bind the exact current chain')
    _require(policy.get('pilot_identity_required') is True and bool(policy.get('site_failure_guard')),
             'current chain requires page identity and original whole-site failure guard')
    check_project_guard(scope, policy['site_failure_guard'])
    if 'candidate_project' in scope:
        _require(policy['campaign_id'] == scope['chain_id'], 'runtime campaign belongs to another project')
        for root in plan.get('dedup_roots', []):
            assert_current_result_path(scope, root)
    from .production_identity import validate_plan
    validate_plan(plan, required=True)
    assert_current_evidence(scope, plan)
    from .site_failure_stop import SiteFailureStore
    guard = SiteFailureStore(policy['site_failure_guard'])
    for task in plan['tasks']:
        application = task['pilot_identity']['application']
        _require(application.get('application_registry') == guard.binding.get('application_registry'),
                 'page identity and dispatch guard must use the same frozen application aliases')
    return True


def validate_history_context(value):
    scope = value.get('history_scope', {})
    records, actual = read_chain_history(scope.get('manifest', {}).get('path', ''))
    _require(scope == actual and value == history_context(actual, records, actual['registry']),
             'current context contains missing, historical, or unbound comparisons')
    return True


def current_evidence_roots(scope):
    return [_physical(scope['manifest']['path']).parent.parent, *(_physical(root) for root in scope['current_result_roots'])]


def require_evidence_path(path, roots, *, context=None):
    """A path frozen into historical evidence resolves through the retained
    project-layout symlinks; the roots and byte-hash checks fence it."""
    recorded = str(path)
    path = _physical(path)
    _require(any(path.is_relative_to(_physical(root)) for root in roots),
             'historical/out-of-chain observation reference rejected',
             context={**(context or {}), 'path': recorded, 'resolved_path': str(path),
                      'allowed_roots': [str(_physical(root)) for root in roots]})
    return path


def assert_current_evidence(scope, value):
    """Fence adoption of this run's raw evidence, without changing its bytes.

    The scope folder is inside the explicitly named current-run evidence root.
    Only that run and the new result roots may supply observed sample evidence;
    old delivery/candidate/registry references are not followed.
    """
    assert_registry_scope(scope, scope['registry'])
    roots = current_evidence_roots(scope)
    visited = set()
    relocations = {}
    def find_relocations(item):
        if isinstance(item,list):
            for entry in item:find_relocations(entry)
        elif isinstance(item,dict):
            if item.get('schema_version')=='webcollect-rejected-frame-relocation-1':
                old=_physical(item['original_path']);current=_physical(item['current']['path']);dispatch=_physical(item['dispatch']['path'])
                _require(all(any(p.is_relative_to(root) for root in roots) for p in (old,current,dispatch)),
                         'out-of-chain frame relocation rejected')
                _require(old.suffix=='.png' and len(old.parents)>3 and old.parent.name=='images'
                         and old.parents[2].name=='samples'
                         and current==old.parents[3]/'rejected'/old.parents[1].name/'images'/old.name,
                         'frame relocation must be original samples-to-rejected move')
                _require(_ref(current)==item['current'] and item['current']['sha256']==item['original_sha256']
                         and _ref(dispatch)==item['dispatch'], 'frame relocation bytes changed')
                _require(load_json(dispatch).get('formal_frame')=={'path':item['original_path'],'sha256':item['original_sha256']},
                         'frame relocation lacks original dispatch binding')
                relocations[(str(old),item['original_sha256'])]=current
            for entry in item.values():find_relocations(entry)
    find_relocations(value)
    def walk(item, location='$', reference_chain=()):
        context = {'json_location': location, 'reference_chain': list(reference_chain)}
        if isinstance(item, dict) and set(item) == {'path', 'sha256'}:
            context['path'] = item['path']
        try:
            walk_item(item, location, reference_chain, context)
        except CurrentChainError as error:
            if error.context:
                raise
            raise CurrentChainError(error.message, context=context) from error
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise CurrentChainError('invalid current evidence: ' + str(error),
                                    context={**context, 'error_type': type(error).__name__}) from error

    def walk_item(item, location, reference_chain, context):
        if isinstance(item, list):
            for index, entry in enumerate(item):
                walk(entry, f'{location}[{index}]', reference_chain)
        elif isinstance(item, dict):
            if item.get('schema_version') in ('candidate-research-replay-2', 'candidate-research-replay-3',
                                              'candidate-research-replay'):
                from .candidate_contract import research_v2_inputs
                authorization = research_v2_inputs(item)
                _require(_physical(authorization['registry']) == _physical(scope['registry']),
                         'research v2 registry differs from current chain')
                # These are frozen task inputs and explicitly named comparison
                # receipts, not observations or completed facts for the new run.
                return
            if item.get('schema_version')=='candidate-research-replay-1':
                required={'schema_version','original_claim_id','objective','authorization','production_counted'}
                fields=set(item)
                _require((fields==required or fields==required|{'objective_origin'})
                         and item.get('objective_origin','original') in ('original','model-proposed-research')
                         and item['production_counted'] is False and bool(item['original_claim_id']), 'invalid research input metadata')
                _require(all(_ref(Path(item[k]['path']))==item[k] for k in ('objective','authorization')), 'research input metadata changed')
                objective=load_json(item['objective']['path']);authorization=load_json(item['authorization']['path'])
                _require(objective.get('schema_version')=='webcollect-session-objective-1'
                         and authorization.get('candidate_id')==objective.get('candidate_id')
                         and authorization.get('version')==objective.get('version')
                         and authorization.get('objective')==item['objective']
                         and authorization.get('scope')=='original-two-baselines-only'
                         and authorization.get('production_counted') is False, 'research authorization and original objective differ')
                # These two files are explicit task inputs. They confer no page,
                # model-answer or action-evidence status and are never traversed
                # as observations; every other reference still uses current roots.
                return
            if item.get('schema_version') in ('webcollect-task-history-scope-1', 'qc-cumulative-set-1'):
                raise CurrentChainError('historical population reference rejected', context=context)
            if set(item) == {'path', 'sha256'}:
                path = require_evidence_path(item['path'], roots, context=context)
                if not path.is_file() and (str(path),item['sha256']) in relocations:
                    path=relocations[(str(path),item['sha256'])]
                    _require(_ref(path)['sha256']==item['sha256'],'relocated frame bytes changed')
                else:
                    # The recorded path may carry the pre-migration layout; it
                    # already resolved to this roots-fenced file, so bytes decide.
                    _require(_ref(path)['sha256'] == item['sha256'], 'current observation reference changed')
                if path.suffix == '.json' and str(path) not in visited:
                    visited.add(str(path))
                    walk(load_json(path), '$', (*reference_chain,
                         {'path': str(path), 'json_location': location}))
            else:
                for key, entry in item.items():
                    walk(entry, f'{location}.{key}', reference_chain)
    walk(value)
    return True


def history_context(scope, records, registry, *, exclude_scope=None, own_tasks=()):
    actual_records, actual_scope = read_chain_history(scope['manifest']['path'])
    _require(history_scope_extends(scope, actual_scope)
             and (records == actual_records or (scope.get('candidate_project')
                  and all(record in actual_records for record in records))),
             'current population or scope changed')
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
