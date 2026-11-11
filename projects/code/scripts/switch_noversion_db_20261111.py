"""One-time no-version database structure switch (2026-11-11, r01).

Drops only the constraints that block current writes after the no-version
refactor: m4_tasks.task_version (column + UNIQUE(campaign_id,task_id,task_version))
and collection_tasks.task_version. Every business ID, task_key, state, claim,
UNKNOWN and fee record is copied verbatim; nothing is recomputed or reset.

Usage: python switch_noversion_db_20261111.py <db.sqlite3> [--apply]
Without --apply the change runs on an in-memory copy and reports only.
"""
import json
import sqlite3
import sys


def snapshot(con):
    rows = {}
    for table in ('m4_tasks', 'm4_attempts', 'm4_plan_tasks', 'collection_tasks'):
        try:
            rows[table] = con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        except sqlite3.OperationalError:
            rows[table] = None
    fees = None
    try:
        fees = con.execute('SELECT COUNT(*), COALESCE(SUM(cost),0) FROM model_requests').fetchone()
    except sqlite3.OperationalError:
        pass
    return {'tables': rows, 'model_requests': fees}


def rebuild(db_path, apply):
    src = sqlite3.connect(db_path)
    before = snapshot(src)
    con = sqlite3.connect(':memory:')
    src.backup(con)
    src.close()
    report = {'db': db_path, 'before': before}

    cols = [r[1] for r in con.execute('PRAGMA table_info(m4_tasks)')]
    if 'task_version' in cols:
        con.executescript('''
BEGIN;
CREATE TABLE m4_tasks_nv (
 task_key TEXT PRIMARY KEY, scope_id TEXT NOT NULL, campaign_id TEXT NOT NULL,
 task_id TEXT NOT NULL, task_sha256 TEXT NOT NULL,
 task_json TEXT NOT NULL, category TEXT NOT NULL, domain_key TEXT NOT NULL,
 status TEXT NOT NULL, quota_reserved INTEGER NOT NULL, capability_expires_at REAL NOT NULL,
 next_eligible_at REAL NOT NULL, created_at REAL NOT NULL);
INSERT INTO m4_tasks_nv SELECT task_key,scope_id,campaign_id,task_id,task_sha256,task_json,category,domain_key,status,quota_reserved,capability_expires_at,next_eligible_at,created_at FROM m4_tasks;
DROP TABLE m4_tasks;
ALTER TABLE m4_tasks_nv RENAME TO m4_tasks;
COMMIT;
''')
    else:
        report['m4_tasks'] = 'already switched'

    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'collection_tasks' in tables:
        ccols = [r[1] for r in con.execute('PRAGMA table_info(collection_tasks)')]
        if 'task_version' in ccols:
            con.executescript('''
BEGIN;
CREATE TABLE collection_tasks_nv (
 registry TEXT NOT NULL, task_key TEXT NOT NULL, scope_id TEXT NOT NULL,
 page_id TEXT NOT NULL, page_key TEXT NOT NULL, task_id TEXT NOT NULL,
 status TEXT NOT NULL, blocking INTEGER NOT NULL,
 record TEXT NOT NULL, PRIMARY KEY(registry,task_key));
INSERT INTO collection_tasks_nv SELECT registry,task_key,scope_id,page_id,page_key,task_id,status,blocking,record FROM collection_tasks;
DROP TABLE collection_tasks;
ALTER TABLE collection_tasks_nv RENAME TO collection_tasks;
COMMIT;
''')
        report['collection_tasks'] = 'switched'
    else:
        report['collection_tasks'] = 'absent'

    report['integrity'] = con.execute('PRAGMA integrity_check').fetchone()[0]
    report['after'] = snapshot(con)
    m4_cols = [r[1] for r in con.execute('PRAGMA table_info(m4_tasks)')]
    report['m4_tasks_columns'] = m4_cols
    unchanged = (report['before']['tables'] == report['after']['tables']
                 and report['before']['model_requests'] == report['after']['model_requests'])
    report['row_and_fee_counts_unchanged'] = unchanged
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if apply:
        out = sqlite3.connect(db_path)
        con.backup(out)
        out.close()
        print('APPLIED to', db_path)
    con.close()


if __name__ == '__main__':
    rebuild(sys.argv[1], '--apply' in sys.argv)
