"""One append-only, campaign-bound whole-application failure ledger.

Original collection/model ledgers are read-only sources. This module neither
dispatches work nor retries requests. Unknown outcomes remain explicit holds.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit, urlunsplit

from .batch_core import file_sha, load_json
from .planning import canonical, object_sha256
from .production_identity import page_url

VERSION = 'webcollect-whole-site-failure-stop-1'
LIMIT = 3


class SiteStopped(ValueError):
    pass


def application_key(value):
    """Use the pilot identity's whole-host normalization, never a page key."""
    uri = value['pilot_identity']['application']['canonical_uri'] if isinstance(value, dict) and value.get('pilot_identity') else (
        value.get('site_uri', value.get('initial_url')) if isinstance(value, dict) else value)
    parsed = urlsplit(uri)
    return page_url(urlunsplit((parsed.scheme, parsed.netloc, '/', '', '')))


def execution_id(stage, source, identity):
    return stage + ':' + object_sha256([str(Path(source).resolve()), identity])


def validate_binding(value):
    if (not isinstance(value, dict) or set(value) != {'ledger', 'campaign_id', 'formal_since'}
            or not isinstance(value['ledger'], str) or not Path(value['ledger']).is_absolute()
            or not isinstance(value['campaign_id'], str) or not value['campaign_id'].strip()
            or type(value['formal_since']) not in (int, float) or not 0 < value['formal_since'] < float('inf')):
        raise ValueError('Whole-site failure guard requires a fixed absolute ledger, campaign and formal_since')
    return {**value, 'ledger': str(Path(value['ledger']).resolve())}


class SiteFailureStore:
    def __init__(self, binding, *, _seeding=False):
        self.binding = validate_binding(binding)
        self.path = Path(self.binding['ledger'])
        with self.connect() as con:
            meta = json.loads(con.execute('SELECT value FROM stop_meta WHERE id=1').fetchone()[0])
        if meta['binding'] != self.binding or meta['version'] != VERSION or meta['failure_limit'] != LIMIT:
            raise ValueError('Whole-site failure ledger identity/policy changed')
        if meta.get('seed_policy') and not _seeding:
            seed_ref = meta['seed_policy']
            if file_sha(seed_ref['path']) != seed_ref['sha256']:
                raise ValueError('Original whole-site failure seed changed')
            for site in load_json(seed_ref['path'])['sites']:
                if self.status(site['whole_application'])['failure_count'] < site['failed_real_execution_count']:
                    raise ValueError('Original whole-site seed is incomplete; dispatch remains blocked')

    def connect(self, writable=False):
        return closing(sqlite3.connect(self.path.as_uri() + ('?mode=rw' if writable else '?mode=ro'), uri=True, timeout=30))

    @classmethod
    def initialize(cls, binding, *, seed_policy=None, source_root=None):
        binding = validate_binding(binding); path = Path(binding['ledger'])
        seed = load_json(seed_policy) if seed_policy else None
        if seed_policy is not None and (not isinstance(seed, dict) or seed.get('failure_limit') != LIMIT or not source_root):
            raise ValueError('Seed policy must preserve limit three and explicit original source root')
        if seed:
            for site in seed['sites']:
                application_key(site['whole_application'])
                if (type(site['failed_real_execution_count']) is not int
                        or site['failed_real_execution_count'] != len(site['attempts'])
                        or site.get('stop') is not (site['failed_real_execution_count'] >= LIMIT)):
                    raise ValueError('Seed count/stop must equal its original execution identities')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb'): pass  # Never replace/reset an existing stop ledger.
        with closing(sqlite3.connect(path)) as con:
            con.executescript('CREATE TABLE stop_meta(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL);'
                'CREATE TABLE site_executions(execution_id TEXT PRIMARY KEY,application_key TEXT NOT NULL,'
                'stage TEXT NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL,evidence_json TEXT NOT NULL,'
                'usage_refs_json TEXT NOT NULL,recorded_at REAL NOT NULL);')
            con.execute('INSERT INTO stop_meta VALUES(1,?)', (canonical({'version': VERSION, 'binding': binding,
                'failure_limit': LIMIT, 'seed_policy': {'path': str(Path(seed_policy).resolve()),
                'sha256': file_sha(seed_policy)} if seed_policy else None}),))
            con.commit()
        store = cls(binding, _seeding=True)
        if seed:
            for site in seed['sites']:
                for attempt in site['attempts']:
                    source = (Path(source_root) / attempt['ledger']).resolve()
                    store.record(site['whole_application'], execution_id('observation', source, attempt['job_id']),
                        stage='observation', state='failed', reason=attempt['error_type'], real_execution=True,
                        evidence=[{'path': str(Path(seed_policy).resolve()), 'sha256': file_sha(seed_policy)}],
                        usage_refs=[{**attempt, 'ledger': str(source)}])
        return cls(binding)

    def record(self, application, identity, *, stage, state, reason, real_execution, evidence, usage_refs):
        if (real_execution is not True or state not in ('failed', 'unknown') or stage not in ('probe', 'observation', 'formal')
                or not isinstance(reason, str) or not reason.strip() or not identity or not evidence
                or not isinstance(usage_refs, list)):
            raise ValueError('Only evidenced real execution failures/unknown outcomes may enter the site ledger')
        body = (identity, application_key(application), stage, state, reason, canonical(evidence), canonical(usage_refs))
        with self.connect(True) as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT execution_id,application_key,stage,state,reason,evidence_json,usage_refs_json '
                              'FROM site_executions WHERE execution_id=?', (identity,)).fetchone()
            if old and tuple(old) != body:
                raise ValueError('Original execution identity cannot be reclassified or moved to another site')
            if not old:
                con.execute('INSERT INTO site_executions VALUES(?,?,?,?,?,?,?,?)', (*body, time.time()))
            con.commit()
        return self.status(application)

    def status(self, application):
        key = application_key(application)
        with self.connect() as con:
            counts = dict(con.execute('SELECT state,COUNT(*) FROM site_executions WHERE application_key=? GROUP BY state', (key,)))
        failed, unknown = counts.get('failed', 0), counts.get('unknown', 0)
        return {'application_key': key, 'failure_count': failed, 'unknown_execution_count': unknown,
                'failure_limit': LIMIT, 'stopped': failed >= LIMIT, 'dispatch_blocked': failed >= LIMIT or bool(unknown)}

    def guard(self, application):
        state = self.status(application)
        if state['dispatch_blocked']:
            raise SiteStopped('Whole application dispatch stopped: ' + canonical(state))
        return state

    def sync_formal(self, registry, campaign_id):
        """Merge only committed new failures, including other pages/scopes."""
        registry = Path(registry).resolve()
        with closing(sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True)) as con:
            rows = con.execute('SELECT a.attempt_id,a.status,a.root_cause,a.evidence_json,t.task_json '
                'FROM m4_attempts a JOIN m4_tasks t ON a.task_key=t.task_key '
                'WHERE a.campaign_id=? AND a.started_at>=? AND a.finished_at IS NOT NULL '
                "AND a.status IN ('rejected','interrupted')", (campaign_id, self.binding['formal_since'])).fetchall()
        for identity, status, reason, evidence, task in rows:
            refs = [{'registry': str(registry), 'attempt_id': identity, 'usage': 'UNKNOWN', 'cost': 'UNKNOWN'}]
            self.record(json.loads(task), execution_id('formal', registry, identity), stage='formal',
                state='unknown' if status == 'interrupted' else 'failed', reason=reason or status,
                real_execution=True, evidence=json.loads(evidence) or refs, usage_refs=refs)


def model_usage_refs(ledger, job_id):
    with ledger.connect() as con:
        rows = con.execute('SELECT id,state,usage,cost,reserved_cost FROM model_requests WHERE job_id=? ORDER BY id', (job_id,)).fetchall()
    return [{'ledger': str(ledger.path), 'job_id': job_id, 'request_id': row[0], 'state': row[1],
             'usage': json.loads(row[2]) if row[2] else 'UNKNOWN', 'cost': row[3] if row[3] is not None else 'UNKNOWN',
             'reserved_cost_not_actual_debit': row[4]} for row in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'status'))
    parser.add_argument('--ledger', required=True); parser.add_argument('--campaign-id', required=True)
    parser.add_argument('--formal-since', type=float, required=True)
    parser.add_argument('--seed-policy', type=Path); parser.add_argument('--source-root', type=Path)
    parser.add_argument('--application')
    args = parser.parse_args(argv)
    binding = {key: getattr(args, key) for key in ('ledger', 'campaign_id', 'formal_since')}
    store = SiteFailureStore.initialize(binding, seed_policy=args.seed_policy, source_root=args.source_root) if args.command == 'init' else SiteFailureStore(binding)
    print(json.dumps(store.status(args.application) if args.application else {'binding': store.binding, 'failure_limit': LIMIT}, ensure_ascii=False))


if __name__ == '__main__': main()
