"""Immutable peer reservations for concurrently dispatched observed workflows.

Reservations are engineering duplicate guards, not AI peer review or QC. They
allocate no production identifiers and are never silently released on failure.
Only exact prebound peer rows may differ from the independently reviewed base.
"""
from webcollect.sqlite_connection import raw_connect as workspace_connect
from contextlib import closing
from copy import deepcopy
from webcollect import workspace_json as json
from pathlib import Path
import sqlite3
import time

from .planning import canonical, object_sha256

VERSION = 'admission-cohort'
LEGACY_VERSION = 'webcollect-admission-cohort-1'
SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS m4_admission_cohorts (
       cohort_id TEXT PRIMARY KEY, binding_json TEXT NOT NULL, created_at REAL NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS m4_admission_members (
       scope_id TEXT PRIMARY KEY, cohort_id TEXT NOT NULL, plan_sha256 TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS m4_admission_reservations (
       semantic_signature TEXT PRIMARY KEY, structural_signature TEXT NOT NULL UNIQUE,
       task_sha256 TEXT NOT NULL UNIQUE, cohort_id TEXT NOT NULL, scope_id TEXT NOT NULL)''',
)


def _require(condition, message):
    if not condition:
        raise ValueError('ADMISSION_COHORT: ' + message)


def ensure_schema(con):
    # execute, not executescript: callers may already own BEGIN IMMEDIATE.
    for statement in SCHEMA:
        con.execute(statement)


def _has_table(con):
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'm4_admission_%'")}
    if tables:
        _require({'m4_admission_cohorts', 'm4_admission_members', 'm4_admission_reservations'} <= tables,
                 'incomplete reservation schema; do not downgrade to an unbound scope')
    return bool(tables)


def _rows(con):
    rows = [{'scope_id': scope, 'campaign_id': campaign, 'task': json.loads(task)}
            for scope, campaign, task in con.execute('SELECT scope_id,campaign_id,task_json FROM m4_tasks')]
    return sorted(rows, key=object_sha256)


def _snapshot(registry, rows):
    rows = sorted(rows, key=object_sha256)
    return {'registry': str(Path(registry).resolve()), 'rows': rows, 'sha256': object_sha256(rows)}


def _workflows(plan):
    return [task for task in plan.get('tasks', []) if 'observed_workflow' in task
            or 'workflow_admission' in task or task.get('task_family') == 'observed-workflow']


def _contexts(plan):
    from .batch_core import load_json
    from .task_admission import _read
    return [load_json(_read(task.get('workflow_admission', {}).get('packet')))['history_context']
            for task in _workflows(plan)]


def _file_stamps(scope):
    """Metadata fence around a full content read, without hashing under writer lock."""
    current = scope.get('schema_version') == 'webcollect-current-chain-1'
    if current:
        from .current_chain import assert_registry_scope, assert_current_result_path
        assert_registry_scope(scope, scope['registry'])
        paths = {Path(scope['manifest']['path']), *[assert_current_result_path(scope, ref['path'])
                                                  for ref in scope['current_results_refs']]}
    else:
        paths = {Path(scope['manifest']['path']), Path(scope['formal_anchor']['path'])}
    for package in ([] if current else scope['packages']):
        root = Path(package['path'])
        _require(root.is_dir() and not root.is_symlink(), 'original customer package missing or unsafe')
        paths.add(root)
        paths.update(root.rglob('*'))
    stamps = {}
    for path in sorted(paths):
        _require(not path.is_symlink(), 'original customer evidence gained a symlink')
        info = path.stat()
        stamps[str(path)] = [info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
    return stamps


def validate_customer_history(plan):
    """Full read-only dispatch/commit check, always before a SQLite writer lock.

    The proof is in-memory and bound to the complete reviewed context and file
    identities. No time-only cache is used. A changed file invalidates it.
    """
    from .task_admission import _read
    from .task_generation import read_customer_history, bind_formal_history
    proofs = {}
    for expected in _contexts(plan):
        identity = object_sha256(expected)
        if identity in proofs:
            continue
        before = _file_stamps(expected['history_scope'])
        if expected['history_scope'].get('schema_version') == 'webcollect-current-chain-1':
            from .current_chain import read_chain_history, assert_registry_scope
            assert_registry_scope(expected['history_scope'], expected['registry_snapshot']['registry'])
            history, scope = read_chain_history(_read(expected['history_scope']['manifest']))
        else:
            history, scope = read_customer_history(_read(expected['history_scope']['manifest']))
            scope = bind_formal_history(scope)
        customers = sorted([{'id': 'customer:' + row['sample_id'], 'record': row} for row in history], key=lambda row: row['id'])
        _require(scope == expected['history_scope'] and object_sha256(history) == expected['customer_history_sha256']
                 and customers == [row for row in expected['comparisons'] if row['id'].startswith('customer:')],
                 'original formal/customer history changed before dispatch/commit')
        after = _file_stamps(scope)
        _require(before == after, 'original customer files changed during content verification')
        proofs[identity] = {'context_sha256': identity, 'file_stamps': after}
    return proofs


def _check_customer_references(expected, history_proof=None):
    from .task_admission import _read
    scope = expected['history_scope']
    _read(scope['manifest'])
    if scope.get('schema_version') == 'webcollect-current-chain-1':
        from .current_chain import assert_registry_scope, assert_current_result_path
        assert_registry_scope(scope, expected['registry_snapshot']['registry'])
        for ref in scope['current_results_refs']:
            assert_current_result_path(scope, ref['path'])
            _read(ref)
    else:
        _read({key: scope['formal_anchor'][key] for key in ('path', 'sha256')})
    if history_proof is not None:
        identity = object_sha256(expected)
        proof = history_proof.get(identity, {})
        _require(proof.get('context_sha256') == identity and proof.get('file_stamps') == _file_stamps(scope),
                 'customer content proof expired before atomic registry operation')


def _exact_scope_tasks(con, scope_id, campaign_id, plan, publication):
    """Check immutable columns and exact plan membership, never status counters."""
    from .runtime import domain_key
    capabilities = {(row['task_id'], row['task_version']): row for row in publication['tasks']}
    expected, links = [], []
    for ordinal, task in enumerate(plan['tasks']):
        key = object_sha256([campaign_id, task['task_id'], task['task_version']])
        expected.append((key, scope_id, campaign_id, task['task_id'], task['task_version'], object_sha256(task),
                         canonical(task), task['site_category'], domain_key(task['site_uri']),
                         capabilities[(task['task_id'], task['task_version'])]['capability_expires_at']))
        links.append((scope_id, publication['plan_sha256'], key, ordinal))
    actual = [tuple(row) for row in con.execute('SELECT task_key,scope_id,campaign_id,task_id,task_version,task_sha256,'
        'task_json,category,domain_key,capability_expires_at FROM m4_tasks WHERE scope_id=?', (scope_id,))]
    actual = [(*row[:6], canonical(json.loads(row[6])), *row[7:]) for row in actual]
    _require(sorted(actual) == sorted(expected), 'enqueued scope exact tasks/metadata missing, duplicated or changed')
    actual_links = [tuple(row) for row in con.execute('SELECT scope_id,plan_sha256,task_key,ordinal FROM m4_plan_tasks WHERE scope_id=?', (scope_id,))]
    _require(sorted(actual_links) == sorted(links), 'enqueued scope plan-task membership/ordinal changed')


def _exact_enqueued_members(con, binding):
    for member in binding['members']:
        plans = list(con.execute('SELECT plan_json,publication_json FROM m4_plans WHERE scope_id=?', (member['scope_id'],)))
        if not plans:
            _require(con.execute('SELECT 1 FROM m4_tasks WHERE scope_id=?', (member['scope_id'],)).fetchone() is None
                     and con.execute('SELECT 1 FROM m4_plan_tasks WHERE scope_id=?', (member['scope_id'],)).fetchone() is None,
                     'unstarted reserved peer has unbound queue rows')
            continue
        _require(len(plans) == 1 and json.loads(plans[0][0]) == member['plan']
                 and json.loads(plans[0][1]) == member['publication'], 'enqueued peer plan/publication changed')
        _exact_scope_tasks(con, member['scope_id'], binding['campaign_id'], member['plan'], member['publication'])


def _signatures(task):
    from .observed_workflow import static_identity
    from .task_generation import task_signature
    return {'semantic_signature': static_identity(task), 'structural_signature': task_signature(task),
            'task_sha256': object_sha256(task)}


def _reservations(binding):
    return sorted([dict(signature, cohort_id=object_sha256(binding), scope_id=member['scope_id'])
                   for member in binding['members'] for signature in member['signatures']],
                  key=lambda row: row['task_sha256'])


def _load_cohort(con, scope_id, plan, registry, *, capture_output=None):
    if not _has_table(con):
        return None
    row = con.execute('SELECT c.cohort_id,c.binding_json FROM m4_admission_members m '
                      'JOIN m4_admission_cohorts c ON c.cohort_id=m.cohort_id WHERE m.scope_id=?', (scope_id,)).fetchone()
    if row is None:
        _require(con.execute('SELECT 1 FROM m4_admission_reservations WHERE scope_id=?', (scope_id,)).fetchone() is None,
                 'reserved scope membership missing; do not downgrade to an unbound scope')
        _require(not any(any(member.get('scope_id') == scope_id for member in json.loads(raw)['members'])
                         for raw, in con.execute('SELECT binding_json FROM m4_admission_cohorts')),
                 'cohort still declares a missing member; do not downgrade to an unbound scope')
        return None
    cohort_id, raw = row
    binding = json.loads(raw)
    _require(object_sha256(binding) == cohort_id and binding.get('schema_version') in (VERSION, LEGACY_VERSION),
             'reservation binding changed')
    _require(binding['registry'] == str(Path(registry).resolve()), 'reservation original ledger changed')
    members = [member for member in binding['members'] if member['scope_id'] == scope_id]
    _require(len(members) == 1 and members[0]['plan'] == plan, 'reserved scope/plan changed')
    if capture_output is not None:
        _require(members[0]['output'] == str(Path(capture_output).resolve()), 'reserved output changed')
    from .batch_core import file_sha, load_json
    proof = binding['schedule']
    path = Path(proof['path'])
    _require(path.is_absolute() and path.is_file() and not path.is_symlink()
             and file_sha(path) == proof['sha256'], 'frozen schedule proof missing or changed')
    frozen = load_json(path)
    _require(object_sha256(frozen) == binding['schedule_binding_sha256'], 'schedule body changed')
    from .collect_runtime import source_identity
    _require(frozen['source_files_sha256'] == source_identity(), 'cohort implementation changed')
    actual_members = sorted([{'scope_id': scope, 'plan_sha256': digest}
                             for scope, digest in con.execute('SELECT scope_id,plan_sha256 FROM m4_admission_members WHERE cohort_id=?', (cohort_id,))],
                            key=lambda member: member['scope_id'])
    expected_members = sorted([{'scope_id': member['scope_id'], 'plan_sha256': member['publication']['plan_sha256']}
                               for member in binding['members']], key=lambda member: member['scope_id'])
    _require(actual_members == expected_members, 'cohort member reservations changed')
    actual = sorted([dict(zip(('semantic_signature', 'structural_signature', 'task_sha256', 'cohort_id', 'scope_id'), values))
                     for values in con.execute('SELECT semantic_signature,structural_signature,task_sha256,cohort_id,scope_id '
                                               'FROM m4_admission_reservations WHERE cohort_id=?', (cohort_id,))],
                    key=lambda item: item['task_sha256'])
    _require(actual == _reservations(binding), 'atomic semantic/structure reservations changed')
    _exact_enqueued_members(con, binding)
    return binding


def _without_exact_peers(expected, live, binding):
    _require(expected == binding['history_context'], 'packet uses a different cohort baseline')
    baseline = {object_sha256(row) for row in expected['registry_snapshot']['rows']}
    peers = {object_sha256({'scope_id': member['scope_id'], 'campaign_id': binding['campaign_id'], 'task': task})
             for member in binding['members'] for task in member['plan']['tasks']}
    removed = {object_sha256(row) for row in live['registry_snapshot']['rows']
               if object_sha256(row) not in baseline and object_sha256(row) in peers}
    normalized = deepcopy(live)
    normalized['registry_snapshot'] = _snapshot(binding['registry'],
        [row for row in live['registry_snapshot']['rows'] if object_sha256(row) not in removed])
    normalized['comparisons'] = [row for row in live['comparisons'] if row['id'] not in {'m4:' + digest for digest in removed}]
    return normalized


def assert_history_context(plan, registry, capture_output, expected_context, live_context, *, connection=None):
    """Exact equality, permitting only the exact atomically reserved peer rows.

    The original live context (including peers) remains available to the caller
    for historical semantic duplicate checks. Nothing is changed in place.
    """
    from .collect_runtime import runtime_scope
    def check(con):
        binding = _load_cohort(con, runtime_scope(capture_output), plan, registry, capture_output=capture_output)
        actual = _without_exact_peers(expected_context, live_context, binding) if binding else live_context
        _require(expected_context == actual, 'workflow original registry/customer history drift; unbound change is not a peer')
    if connection is not None:
        return check(connection)
    with closing(workspace_connect(Path(registry).resolve().as_uri() + '?mode=ro', uri=True)) as con:
        return check(con)


def guard_enqueue(con, registry, scope_id, plan, publication, campaign_id, *, history_proof=None):
    """Run inside the queue transaction, before insertion or number allocation."""
    binding = _load_cohort(con, scope_id, plan, registry)
    tasks = _workflows(plan)
    if not tasks and binding is None:
        return
    if binding:
        member = next(item for item in binding['members'] if item['scope_id'] == scope_id)
        _require(member['publication'] == publication and binding['campaign_id'] == campaign_id,
                 'reserved publication/campaign changed')
    rows = _rows(con)
    existing = con.execute('SELECT plan_json,publication_json FROM m4_plans WHERE scope_id=?', (scope_id,)).fetchone()
    if existing:
        _require(json.loads(existing[0]) == plan and json.loads(existing[1]) == publication,
                 'resume queue is not bound to the original plan/publication')
        _exact_scope_tasks(con, scope_id, campaign_id, plan, publication)
        rows = [row for row in rows if row['scope_id'] != scope_id]
    checked = set()
    for expected in _contexts(plan):
        identity = object_sha256(expected)
        if identity in checked:
            continue
        checked.add(identity)
        _check_customer_references(expected, history_proof)
        snapshot = _snapshot(registry, rows)
        live = deepcopy(expected)
        live['registry_snapshot'] = snapshot
        live['comparisons'] = sorted([row for row in expected['comparisons'] if not row['id'].startswith('m4:')]
            + [{'id': 'm4:' + object_sha256(row), 'record': row} for row in rows], key=lambda row: row['id'])
        actual = _without_exact_peers(expected, live, binding) if binding else live
        _require(actual == expected, 'workflow original registry/customer history drift before queue/dispatch/commit')
    if _has_table(con):
        for task in tasks:
            signature = _signatures(task)
            other = con.execute('SELECT scope_id FROM m4_admission_reservations WHERE '
                                '(semantic_signature=? OR structural_signature=?) AND scope_id<>?',
                                (signature['semantic_signature'], signature['structural_signature'], scope_id)).fetchone()
            _require(other is None, 'semantic/structure already reserved by a different scope')


def guard_scope(con, registry, scope_id, *, history_proof=None):
    row = con.execute('SELECT p.plan_json,p.publication_json,s.campaign_id FROM m4_plans p '
                      'JOIN m4_scopes s ON s.scope_id=p.scope_id WHERE p.scope_id=?', (scope_id,)).fetchone()
    if row:
        guard_enqueue(con, registry, scope_id, json.loads(row[0]), json.loads(row[1]), row[2], history_proof=history_proof)


def reserve_schedule(frozen, schedule_path):
    """Validate all members and atomically reserve peers before any enqueue.

    Legacy-only schedules keep their previous path. Mixing a new workflow with
    ordinary-form/legacy tasks is rejected rather than relaxing their gates.
    """
    from .batch_core import file_sha, load_json
    from .collect_runtime import runtime_scope
    from .observed_workflow import verify_entry
    from .planning import verify_publication
    config, policy = frozen['config'], frozen['shared_policy']
    batches = [batch for site in config['sites'] for batch in site['batches']]
    plans = [load_json(batch['plan']) for batch in batches]
    if not any(_workflows(plan) for plan in plans):
        return None
    _require(all(plan.get('tasks') and len(_workflows(plan)) == len(plan['tasks'])
                 and all('workflow_admission' in task and 'task_admission' not in task for task in plan['tasks'])
                 for plan in plans), 'mixed observed-workflow/legacy/form schedule is unsupported; use a homogeneous cohort')
    path = Path(schedule_path).resolve()
    _require(load_json(path) == frozen, 'frozen scheduler binding changed')
    contexts, members, seen_semantic, seen_structure = [], [], set(), set()
    for batch, plan in zip(batches, plans):
        publication = load_json(batch['publication'])
        verify_publication(plan, publication)
        verify_entry(plan, config['registry'], batch['output'])
        signatures = [_signatures(task) for task in plan['tasks']]
        for signature in signatures:
            _require(signature['semantic_signature'] not in seen_semantic and signature['structural_signature'] not in seen_structure,
                     'parameter-only/duplicate meaning or structure inside concurrent cohort')
            seen_semantic.add(signature['semantic_signature']); seen_structure.add(signature['structural_signature'])
        contexts.extend(_contexts(plan))
        members.append({'scope_id': runtime_scope(batch['output']), 'output': batch['output'],
                        'plan': plan, 'publication': publication, 'signatures': signatures})
    _require(all(item == contexts[0] for item in contexts), 'all peers require the same exact independently reviewed history baseline')
    binding = {'schema_version': VERSION, 'registry': config['registry'], 'campaign_id': policy['campaign_id'],
               'history_context': contexts[0], 'schedule': {'path': str(path), 'sha256': file_sha(path)},
               'schedule_binding_sha256': object_sha256(frozen),
               'members': sorted(members, key=lambda member: member['scope_id'])}
    cohort_id = object_sha256(binding)
    history_proof = validate_customer_history(plans[0])
    con = workspace_connect(Path(config['registry']).as_uri() + '?mode=rw', uri=True, timeout=90)
    try:
        con.execute('BEGIN IMMEDIATE')
        ensure_schema(con)
        previous = con.execute('SELECT binding_json FROM m4_admission_cohorts WHERE cohort_id=?', (cohort_id,)).fetchone()
        if previous:
            _require(json.loads(previous[0]) == binding, 'existing cohort body changed')
            for member in members:
                guard_enqueue(con, config['registry'], member['scope_id'], member['plan'], member['publication'], policy['campaign_id'],
                              history_proof=history_proof)
        else:
            _check_customer_references(contexts[0], history_proof)
            _require(_snapshot(config['registry'], _rows(con)) == contexts[0]['registry_snapshot'],
                     'original registry changed before atomic cohort reservation')
            for member in members:
                _require(con.execute('SELECT 1 FROM m4_plans WHERE scope_id=?', (member['scope_id'],)).fetchone() is None,
                         'existing output scope cannot acquire a retroactive cohort')
            con.execute('INSERT INTO m4_admission_cohorts VALUES(?,?,?)', (cohort_id, canonical(binding), time.time()))
            for member in members:
                con.execute('INSERT INTO m4_admission_members VALUES(?,?,?)',
                            (member['scope_id'], cohort_id, member['publication']['plan_sha256']))
            for row in _reservations(binding):
                try:
                    con.execute('INSERT INTO m4_admission_reservations VALUES(?,?,?,?,?)',
                                tuple(row[key] for key in ('semantic_signature', 'structural_signature', 'task_sha256', 'cohort_id', 'scope_id')))
                except sqlite3.IntegrityError as error:
                    raise ValueError('ADMISSION_COHORT: peer meaning/structure/scope is already reserved; keep original reservation') from error
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return {'schema_version': VERSION + '-reservation', 'cohort_id': cohort_id, 'member_scopes': len(members),
            'tasks_prebound': sum(len(member['plan']['tasks']) for member in members),
            'sample_ids_allocated': 0, 'peer_comparison': 'ENGINEERING_SIGNATURE_GUARDS_ONLY', 'QC_approval': False}
