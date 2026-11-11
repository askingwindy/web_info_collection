"""Read-only production ordinals for sampled QC; no caller-supplied progress."""
from contextlib import closing
import json
import sqlite3
from pathlib import Path
from .fragment_workflow import is_fragment
from .planning import object_sha256

POLICY = 'qc-sampling'
LEGACY_POLICY = 'qc-sampling-v1-20261030'


def ensure_schema(con):
    con.execute('CREATE TABLE IF NOT EXISTS m4_fragment_captures ('
        'sample_id TEXT PRIMARY KEY,campaign_id TEXT NOT NULL,task_key TEXT NOT NULL,group_id TEXT NOT NULL,'
        'campaign_ordinal INTEGER NOT NULL,group_ordinal INTEGER NOT NULL,task_sha256 TEXT NOT NULL,'
        'UNIQUE(campaign_id,campaign_ordinal),UNIQUE(campaign_id,group_id,group_ordinal))')
    con.execute('CREATE TABLE IF NOT EXISTS m4_quality_admissions ('
        'sample_id TEXT PRIMARY KEY,campaign_id TEXT NOT NULL,group_id TEXT NOT NULL,quality_status TEXT NOT NULL,'
        'ai_status TEXT NOT NULL,force_full INTEGER NOT NULL,report_json TEXT NOT NULL,plan_revision INTEGER NOT NULL)')
    con.execute('CREATE INDEX IF NOT EXISTS m4_quality_group ON m4_quality_admissions(campaign_id,group_id,quality_status,force_full)')


def _is_react(task):
    from .session_core import is_react_task
    return is_react_task(task)


def register_capture(con, row):
    task = json.loads(row['task_json'])
    if not (is_fragment(task) or _is_react(task)):
        return
    ensure_schema(con); group = group_key(task); campaign = row['campaign_id']
    prior = con.execute('SELECT task_sha256 FROM m4_fragment_captures WHERE sample_id=?', (row['sample_id'],)).fetchone()
    if prior:
        if prior[0] != object_sha256(task):
            raise ValueError('Original captured fragment task changed')
        return
    ordinal = con.execute('SELECT COALESCE(MAX(campaign_ordinal),0)+1 FROM m4_fragment_captures WHERE campaign_id=?', (campaign,)).fetchone()[0]
    local = con.execute('SELECT COALESCE(MAX(group_ordinal),0)+1 FROM m4_fragment_captures WHERE campaign_id=? AND group_id=?', (campaign,group)).fetchone()[0]
    con.execute('INSERT INTO m4_fragment_captures VALUES(?,?,?,?,?,?,?)',
        (row['sample_id'],campaign,row['task_key'],group,ordinal,local,object_sha256(task)))


def group_key(task):
    if not (is_fragment(task) or _is_react(task)):
        raise ValueError('Sampled production policy requires an explicitly versioned fragment/react boundary')
    # The group salt stays the task's own persisted sampling policy, so frozen
    # captures keep their original group identity across the policy rename.
    policy = task['fragment'].get('quality_policy_version')
    if not _is_react(task) and policy not in (POLICY, LEGACY_POLICY):
        raise ValueError('New sampled production policy requires an explicitly versioned fragment')
    from .application_identity import host_key
    app = task.get('pilot_identity', {}).get('application', {}).get('canonical_uri', task['site_uri'])
    return object_sha256([host_key(app), task['fragment']['operation_template'], task['fragment']['policy_version'],
                          policy if isinstance(policy, str) and policy else LEGACY_POLICY])


def production_context(scope, sample_ids):
    registry = str(Path(scope['registry']).resolve())
    with closing(sqlite3.connect(Path(registry).as_uri()+'?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        candidates = con.execute('SELECT a.sample_id,a.campaign_id FROM m4_attempts a WHERE a.sample_id IN ('+
            ','.join('?' for _ in sample_ids)+')', list(sample_ids)).fetchall()
        if len(candidates) != len(sample_ids) or len({r['campaign_id'] for r in candidates}) != 1:
            raise ValueError('Sampling population must bind unique captures in one original campaign')
        campaign = candidates[0]['campaign_id']
        rows = con.execute('SELECT c.*,t.task_json FROM m4_fragment_captures c JOIN m4_tasks t ON t.task_key=c.task_key WHERE c.sample_id IN ('+
            ','.join('?' for _ in sample_ids)+')', list(sample_ids)).fetchall()
        positions = {}; groups = {}; first = {}; task_hashes = {}
        for row in rows:
            task = json.loads(row['task_json']); sid = row['sample_id']; group = group_key(task)
            if object_sha256(task) != row['task_sha256'] or group != row['group_id']:
                raise ValueError('Captured fragment index differs from original frozen task')
            positions[sid] = {'campaign': row['campaign_ordinal'], 'group': row['group_ordinal']}
            groups[sid] = group; task_hashes[sid] = row['task_sha256']
        for group in set(groups.values()):
            first[group] = list(con.execute('SELECT sample_id,campaign_ordinal FROM m4_fragment_captures '
                'WHERE campaign_id=? AND group_id=? AND group_ordinal<=5', (campaign,group)))
    if not set(sample_ids) <= set(positions):
        raise ValueError('All sampled captures must have matching original fragment task bindings')
    active = {groups[sid] for sid in sample_ids}
    return {'version': POLICY, 'source': {'registry': registry, 'campaign_id': campaign},
        'groups': {sid: groups[sid] for sid in sample_ids},
        'positions': {sid: positions[sid] for sid in sample_ids},
        'task_sha256': {sid: task_hashes[sid] for sid in sample_ids},
        'predecessors': {g: [row['sample_id'] for row in first.get(g, []) if row['sample_id'] not in sample_ids and
            row['campaign_ordinal'] < max(positions[s]['campaign'] for s in sample_ids)] for g in active}}


def verify_context(context):
    actual = production_context(context['source'], list(context['groups']))
    # A frozen sampling context may predate the policy rename; its group
    # identities were salted with the policy it declares.
    if (context.get('version') not in (POLICY, LEGACY_POLICY)
            or actual != {**context, 'version': actual['version']}):
        raise ValueError('Original sampling groups/ordinals/tasks changed')


def history_state(context):
    """A later batch cannot declare itself stable by omitting prior captures."""
    verify_context(context)
    state = {g: {'pending': [], 'full': False, 'sources': []} for g in set(context['groups'].values())}
    path = Path(context['source']['registry'])
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='m4_quality_admissions'").fetchone()
        rows = []
        if exists:
            for group in state:
                rows.extend(con.execute('SELECT * FROM m4_quality_admissions WHERE campaign_id=? AND group_id=? AND force_full=1 LIMIT 1',
                    (context['source']['campaign_id'],group)))
            predecessors = {sid for ids in context['predecessors'].values() for sid in ids}
            for sid in predecessors:
                rows.extend(con.execute('SELECT * FROM m4_quality_admissions WHERE sample_id=?', (sid,)))
    by_id = {row['sample_id']: row for row in rows}
    for group, info in state.items():
        relevant = [r for r in rows if r['group_id'] == group and r['sample_id'] not in context['groups']]
        for row in relevant:
            from .planning import verify_evidence
            reference = json.loads(row['report_json'])
            verify_evidence([reference])  # Imported only by RuntimeStore's independently rechecked report gate.
            info['sources'].append(reference)
            if row['force_full'] or row['quality_status'] in ('REJECTED', 'REVOKED'):
                info['full'] = True
        for sid in context['predecessors'].get(group, []):
            row = by_id.get(sid)
            if row is None or row['quality_status'] == 'PENDING' and row['ai_status'] != 'PASS':
                info['pending'].append(sid)
            elif row['ai_status'] != 'PASS':
                info['full'] = True
    return state
