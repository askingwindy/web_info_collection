"""Explicit failed-scope receipts permit repair, never erase production history."""
from webcollect.sqlite_connection import raw_connect as workspace_connect
from webcollect import workspace_json as json
from pathlib import Path
import sqlite3

from .batch_core import file_sha, load_json
from .planning import object_sha256, verify_evidence


def validated_replans(registry, references):
    references = references or []
    if not references:
        return {}, set()
    verify_evidence(references)
    allowed, campaigns = {}, set()
    with workspace_connect(Path(registry).resolve().as_uri() + '?mode=ro', uri=True) as con:
        for ref in references:
            receipt = load_json(ref['path'])
            scope = receipt.get('scope_id')
            if receipt.get('schema_version') != 'webcollect-runtime-scope-closure-1' or scope in allowed:
                raise ValueError('Invalid or duplicate failed-scope closure')
            row = con.execute('SELECT campaign_id,state FROM m4_scopes WHERE scope_id=?', (scope,)).fetchone()
            if row != (receipt.get('campaign_id'), 'closed_replanned'):
                raise ValueError('Repair requires an actually closed original campaign scope')
            events = [json.loads(r[0]) for r in con.execute(
                "SELECT payload_json FROM m4_events WHERE scope_id=? AND event_type='scope_closed_replanned'", (scope,))]
            if len(events) != 1 or any(events[0].get(k) != ref.get(k) for k in ('path', 'sha256')):
                raise ValueError('Repair closure is not bound to its committed ledger event')
            verify_evidence(receipt['source_files'])
            verify_evidence(receipt['evidence_refs'])
            cursor = con.execute('SELECT a.*,t.task_id,t.task_version,t.task_json,t.domain_key,t.capability_expires_at '
                'FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.scope_id=? ORDER BY a.created_at,a.rowid', (scope,))
            from .runtime import RuntimeStore
            attempt_rows = [RuntimeStore._view(dict(zip([c[0] for c in cursor.description], r))) for r in cursor]
            if (attempt_rows != receipt['registry_attempt_ledger']
                    or object_sha256(attempt_rows) != receipt.get('registry_attempt_ledger_sha256')):
                raise ValueError('Original rejected attempt ledger changed after closure')
            attempts = [(r['attempt_id'], r['status'], r['started_at'], r['finished_at']) for r in attempt_rows]
            if (not attempts or any(r[1] != 'rejected' or r[2] is None or r[3] is None for r in attempts)
                    or {r[0] for r in attempts} != {r['attempt_id'] for r in receipt['registry_attempt_ledger']}):
                raise ValueError('Repair scope must contain only the original terminal rejected attempts')
            tasks = con.execute('SELECT task_json,status,quota_reserved FROM m4_tasks WHERE scope_id=?', (scope,)).fetchall()
            if not tasks or any(r[1] != 'needs_replan' or r[2] != 0 for r in tasks):
                raise ValueError('Repair cannot bypass active, saved, or reserved tasks')
            actual = {object_sha256(json.loads(r[0])) for r in tasks}
            if actual != {object_sha256(t) for t in receipt['planned_tasks']}:
                raise ValueError('Repair task population changed since closure')
            cursor = con.execute('SELECT * FROM m4_tasks WHERE scope_id=? ORDER BY created_at,task_id,task_version', (scope,))
            task_rows = [RuntimeStore._view(dict(zip([c[0] for c in cursor.description], r))) for r in cursor]
            expected_tasks = [{**r, 'status': 'needs_replan', 'quota_reserved': 0}
                              for r in receipt['registry_tasks_before']]
            if task_rows != expected_tasks:
                raise ValueError('Original failed task ledger changed after closure')
            allowed[scope] = actual
            campaigns.add(row[0])
    return allowed, campaigns


def closure_references(paths):
    return [{'path': str(Path(p).resolve()), 'sha256': file_sha(p)} for p in paths or []]
