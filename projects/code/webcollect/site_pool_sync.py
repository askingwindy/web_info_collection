"""Evidence-bound production projection into the shared pool; no external IO.

The production registry remains authoritative. Pool updates are idempotent and
serialized by SQLite; a failed write is retried before the next dispatch, never
by replaying a browser attempt or a model request.
"""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from .batch_core import file_sha, load_json
from .planning import canonical, object_sha256, verify_evidence

POOL_SCHEMA = '''
CREATE TABLE IF NOT EXISTS collection_sources (
 registry TEXT NOT NULL, scope_id TEXT NOT NULL, revision INTEGER NOT NULL,
 digest TEXT NOT NULL, PRIMARY KEY(registry,scope_id));
CREATE TABLE IF NOT EXISTS collection_tasks (
 registry TEXT NOT NULL, task_key TEXT NOT NULL, scope_id TEXT NOT NULL,
 page_id TEXT NOT NULL, page_key TEXT NOT NULL, task_id TEXT NOT NULL,
 task_version TEXT NOT NULL, status TEXT NOT NULL, blocking INTEGER NOT NULL,
 record TEXT NOT NULL, PRIMARY KEY(registry,task_key));
CREATE INDEX IF NOT EXISTS collection_page ON collection_tasks(page_key);
CREATE TABLE IF NOT EXISTS collection_events (
 id TEXT PRIMARY KEY, registry TEXT NOT NULL, scope_id TEXT NOT NULL,
 revision INTEGER NOT NULL, record TEXT NOT NULL);
'''
BLOCKING = {'queued', 'reserved', 'running', 'collected_pending_review',
            'reviewed_pass', 'published', 'qc_failed'}


def _exists(con, table):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def pool_for_catalog(catalog):
    path = Path(catalog).resolve().parent / 'site-pool-binding.json'
    if not path.exists():
        return None
    value = load_json(path)
    if value.get('schema_version') != 'webcollect-site-pool-binding-1' or value.get('catalog') != {
            'path': str(Path(catalog).resolve()), 'sha256': file_sha(catalog)}:
        raise ValueError('Shared pool catalog binding changed')
    return str(Path(value['pool']).resolve())


def _page(pool, uri):
    from site_planner.site_pool import page_uri
    app = pool.application(uri)
    if app is None:
        raise ValueError('Collection page must already exist in the shared pool')
    path = urlsplit(page_uri(uri)).path.rstrip('/') or '/'
    key = object_sha256([app['id'], path])
    with pool.connect() as con:
        candidates = [row for row in con.execute(
            'WITH RECURSIVE related(id) AS (SELECT ? UNION SELECT m.source FROM merges m JOIN related r ON m.target=r.id) '
            'SELECT p.id,p.uri FROM pages p JOIN related r ON p.application_id=r.id', (app['id'],))
            if (urlsplit(row['uri']).path.rstrip('/') or '/') == path]
    if not candidates:
        raise ValueError('Collection page must already exist in the shared pool')
    exact = [row for row in candidates if row['uri'] == page_uri(uri)]
    return (exact or candidates)[0]['id'], key


def _revision(con, scope):
    return con.execute('SELECT COALESCE(MAX(event_id),0) FROM m4_events WHERE scope_id=?', (scope,)).fetchone()[0]


def _snapshot(registry, scope):
    registry = Path(registry).resolve()
    with closing(sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        con.execute('BEGIN')
        revision = _revision(con, scope)
        rows = []
        for row in con.execute('SELECT * FROM m4_tasks WHERE scope_id=? ORDER BY task_key', (scope,)):
            task = json.loads(row['task_json'])
            uri = task.get('pilot_identity', {}).get('task_page', {}).get('canonical_uri', task['site_uri'])
            attempts = [dict(a) for a in con.execute(
                'SELECT attempt_id,sample_id,status,failure_class,root_cause,evidence_json FROM m4_attempts '
                'WHERE task_key=? ORDER BY created_at,rowid', (row['task_key'],))]
            for attempt in attempts:
                attempt['evidence'] = json.loads(attempt.pop('evidence_json'))
            qc = con.execute("SELECT payload_json FROM m4_events WHERE task_key=? AND event_type='pool_qc_result' "
                             'ORDER BY event_id DESC LIMIT 1', (row['task_key'],)).fetchone()
            qc = json.loads(qc[0]) if qc else None
            status = row['status']
            if qc and qc['status'] == 'FAIL':
                status = 'qc_failed'
            elif qc and qc['status'] == 'REVIEW_REQUIRED':
                status = 'collected_pending_review'
            elif status == 'needs_replan':
                status = 'failed'
            elif status == 'queued' and attempts:
                status = 'failed'  # Retry eligibility stays in the original task status.
            rows.append({'task_key': row['task_key'], 'task_id': row['task_id'],
                'task_version': row['task_version'], 'uri': uri, 'status': status,
                'production_status': row['status'], 'attempts': attempts, 'qc': qc,
                'blocking': row['status'] in BLOCKING})
    return {'registry': str(registry), 'scope_id': scope, 'revision': revision, 'tasks': rows}


def sync(pool_path, registry, scope):
    from site_planner.site_pool import SitePool
    pool = SitePool(pool_path)
    value = _snapshot(registry, scope)
    digest = object_sha256(value)
    mapped = [(row, *_page(pool, row['uri'])) for row in value['tasks']]
    with pool.connect(write=True) as con:
        con.executescript(POOL_SCHEMA)  # Additive, opt-in extension; base schema and evidence stay intact.
        con.execute('BEGIN IMMEDIATE')
        prior = con.execute('SELECT revision,digest FROM collection_sources WHERE registry=? AND scope_id=?',
                            (value['registry'], scope)).fetchone()
        if prior and prior['revision'] > value['revision']:
            return prior['revision']
        if prior and prior['revision'] == value['revision']:
            if prior['digest'] != digest:
                raise ValueError('Production state changed without a bound runtime event')
            return value['revision']
        for row, page_id, page_key in mapped:
            if row['blocking']:
                other = con.execute('SELECT registry,task_key FROM collection_tasks WHERE (page_key=? OR task_id=?) AND blocking=1 '
                                    'AND NOT(registry=? AND task_key=?)',
                                    (page_key, row['task_id'], value['registry'], row['task_key'])).fetchone()
                if other:
                    raise ValueError('Shared pool page already has an active or completed task')
            con.execute('INSERT INTO collection_tasks VALUES(?,?,?,?,?,?,?,?,?,?) '
                        'ON CONFLICT(registry,task_key) DO UPDATE SET status=excluded.status,blocking=excluded.blocking,record=excluded.record',
                        (value['registry'], row['task_key'], scope, page_id, page_key, row['task_id'],
                         row['task_version'], row['status'], int(row['blocking']), canonical(row)))
        con.execute('INSERT INTO collection_events VALUES(?,?,?,?,?)',
                    (digest, value['registry'], scope, value['revision'], canonical(value)))
        con.execute('INSERT INTO collection_sources VALUES(?,?,?,?) '
                    'ON CONFLICT(registry,scope_id) DO UPDATE SET revision=excluded.revision,digest=excluded.digest',
                    (value['registry'], scope, value['revision'], digest))
        con.commit()
    return value['revision']


def page_state(pool, uri):
    from site_planner.site_pool import page_uri
    with pool.connect() as con:
        if not _exists(con, 'collection_tasks'):
            if not con.execute('SELECT 1 FROM pages WHERE uri=?', (page_uri(uri),)).fetchone():
                _page(pool, uri)  # Unknown pages and unresolved aliases still fail closed.
            return {'status': 'not_started', 'dispatch_allowed': True, 'tasks': []}
    _, key = _page(pool, uri)
    with pool.connect() as con:
        tasks = [dict(r) for r in con.execute('SELECT * FROM collection_tasks WHERE page_key=?', (key,))]
        pending = False
        for task in tasks:
            record = json.loads(task['record'])
            if record.get('qc'):
                verify_evidence([record['qc']['report']])
            source = con.execute('SELECT revision FROM collection_sources WHERE registry=? AND scope_id=?',
                                 (task['registry'], task['scope_id'])).fetchone()
            try:
                with closing(sqlite3.connect(Path(task['registry']).as_uri() + '?mode=ro', uri=True)) as runtime:
                    pending |= _revision(runtime, task['scope_id']) != source[0]
            except (OSError, sqlite3.Error):
                pending = True
    states = {t['status'] for t in tasks}
    status = next((s for s in ('published', 'reviewed_pass', 'qc_failed', 'collected_pending_review',
                               'running', 'reserved', 'queued', 'failed') if s in states), 'not_started')
    return {'status': status, 'sync_pending': pending,
            'dispatch_allowed': not pending and not any(t['blocking'] for t in tasks),
            'tasks': [{**json.loads(t['record']), 'registry': t['registry'], 'scope_id': t['scope_id']} for t in tasks]}


def guard_plan(pool_path, registry, scope, plan):
    from site_planner.site_pool import SitePool
    pool = SitePool(pool_path, readonly=True)
    path = Path(registry).resolve()
    if path.is_file():
        from .runtime import RuntimeStore
        store = RuntimeStore(path, scope)
        binding = store.site_pool_binding()
        if binding:
            if binding['pool_path'] != str(pool.path):
                raise ValueError('Cannot replace an existing shared pool binding')
            store.sync_site_pool()
    for task in plan['tasks']:
        uri = task.get('pilot_identity', {}).get('task_page', {}).get('canonical_uri', task['site_uri'])
        state = page_state(pool, uri)
        foreign = [t for t in state['tasks'] if t['blocking'] and not (
            t['registry'] == str(Path(registry).resolve()) and t['scope_id'] == scope
            and t['task_id'] == task['task_id'] and t['task_version'] == task['task_version'])]
        if state.get('sync_pending') or foreign:
            raise ValueError('Shared pool page already has an active or completed task, or needs synchronization')
        with pool.connect() as con:
            if _exists(con, 'collection_tasks'):
                prior = con.execute('SELECT registry,scope_id,task_version FROM collection_tasks WHERE task_id=? AND blocking=1',
                                    (task['task_id'],)).fetchall()
                if any((r['registry'], r['scope_id'], r['task_version']) !=
                       (str(Path(registry).resolve()), scope, task['task_version']) for r in prior):
                    raise ValueError('Shared pool logical task already active or completed')


def validate_handoff(handoff_reference, dataset):
    """Check original capture bytes before QC jobs can be dispatched."""
    verify_evidence([handoff_reference])
    handoff = load_json(handoff_reference['path'])
    if handoff.get('schema_version') != 'webcollect-qc-handoff-1':
        raise ValueError('Original current-chain QC handoff required')
    from quality_inspector.profiles import package_files
    from .qc_handoff import _attempts
    if str(Path(dataset).resolve()) != handoff['dataset']:
        raise ValueError('QC dataset differs from the original capture handoff')
    if package_files(dataset) != handoff['candidate_files_sha256']:
        raise ValueError('Original QC handoff candidate bytes changed')
    ids = [a['sample_id'] for a in handoff['attempts']]
    actual = _attempts(handoff['history_scope'], Path(handoff['dataset']), ids)
    if actual != handoff['attempts']:
        raise ValueError('Original capture handoff binding changed')
    return handoff


def apply_qc(report_path, handoff_reference):
    """Revalidate the frozen capture handoff before registering actual QC results."""
    from .runtime import RuntimeStore, _bound_quality_report
    report_ref = {'path': str(Path(report_path).resolve()), 'sha256': file_sha(report_path)}
    report, _ = _bound_quality_report([report_ref])
    handoff = validate_handoff(handoff_reference, report['dataset'])
    ids = [a['sample_id'] for a in handoff['attempts']]
    if set(ids) != {r['sample_id'] for r in report['samples']}:
        raise ValueError('QC report sample set differs from the original handoff')
    registry = handoff['history_scope']['registry']
    with closing(sqlite3.connect(Path(registry).as_uri() + '?mode=ro', uri=True)) as con:
        scopes = {r[0] for sid in ids for r in con.execute('SELECT scope_id FROM m4_attempts WHERE sample_id=?', (sid,))}
    for scope in scopes:
        store = RuntimeStore(registry, scope)
        if store.site_pool_binding() is not None:
            store.record_qc_report(report_ref)


def main(argv=None):
    import argparse
    from .runtime import RuntimeStore
    parser = argparse.ArgumentParser(description='Repair only the bound shared-pool projection; no collection or model calls')
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--scope', required=True)
    args = parser.parse_args(argv)
    store = RuntimeStore(args.registry, args.scope)
    if store.site_pool_binding() is None:
        raise ValueError('No original shared pool binding to reconcile')
    store.sync_site_pool()
    print(json.dumps(store.site_pool_binding(), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
