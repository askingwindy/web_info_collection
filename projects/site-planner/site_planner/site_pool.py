"""Shared, append-only discovery provenance; never grants collection authority."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit, urlunsplit

from webcollect.batch_core import file_sha, load_json, save_json
from webcollect.collect import verify_public_url
from webcollect.planning import canonical, object_sha256, verify_evidence

SCHEMA = 'webcollect-site-pool-2'
ORIGINS = {'glm_agent', 'codex_session', 'baseline_import'}


def page_uri(uri):
    verify_public_url(uri)
    p = urlsplit(uri)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, ''))


def host_identity(uri):
    """Only the conventional www spelling is normalized; other aliases need proof."""
    host = urlsplit(page_uri(uri)).hostname.lower().rstrip('.')
    return host[4:] if host.startswith('www.') else host


def category(value):
    from .qualification import CANONICAL_CATEGORIES
    if value != 'UNKNOWN' and value not in CANONICAL_CATEGORIES:
        raise ValueError('Use a canonical parent category or UNKNOWN')
    return value


class SitePool:
    def __init__(self, path, *, initialize=False, readonly=False):
        self.path = Path(path).resolve()
        self.readonly = readonly
        if initialize:
            if readonly:
                raise ValueError('Cannot initialize a read-only pool')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path)) as con:
                con.executescript('''
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS pool_meta(id INTEGER PRIMARY KEY CHECK(id=1), schema TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY, host TEXT UNIQUE NOT NULL,
                  name TEXT NOT NULL, category TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS aliases(host TEXT PRIMARY KEY, application_id TEXT NOT NULL,
                  proof TEXT NOT NULL, FOREIGN KEY(application_id) REFERENCES applications(id));
                CREATE TABLE IF NOT EXISTS pages(id TEXT PRIMARY KEY, application_id TEXT NOT NULL,
                  uri TEXT UNIQUE NOT NULL, created REAL NOT NULL,
                  FOREIGN KEY(application_id) REFERENCES applications(id));
                CREATE TABLE IF NOT EXISTS discoveries(id TEXT PRIMARY KEY, page_id TEXT NOT NULL,
                  origin TEXT NOT NULL, run_id TEXT NOT NULL, record TEXT NOT NULL, created REAL NOT NULL,
                  FOREIGN KEY(page_id) REFERENCES pages(id));
                CREATE TABLE IF NOT EXISTS assessments(id TEXT PRIMARY KEY, page_id TEXT NOT NULL,
                  run_id TEXT NOT NULL, record TEXT NOT NULL, created REAL NOT NULL,
                  FOREIGN KEY(page_id) REFERENCES pages(id));
                CREATE TABLE IF NOT EXISTS capabilities(id TEXT PRIMARY KEY, page_id TEXT NOT NULL,
                  reference TEXT NOT NULL, created REAL NOT NULL,
                  FOREIGN KEY(page_id) REFERENCES pages(id));
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, config TEXT NOT NULL,
                  baseline TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS tool_requests(id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                  kind TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, result TEXT,
                  started REAL NOT NULL, finished REAL);
                CREATE TABLE IF NOT EXISTS merges(source TEXT PRIMARY KEY, target TEXT NOT NULL, proof TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS checkpoints(run_id TEXT NOT NULL, key TEXT NOT NULL,
                  value TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(run_id,key));
                ''')
                old = con.execute('SELECT schema FROM pool_meta WHERE id=1').fetchone()
                if old and old[0] != SCHEMA:
                    raise ValueError('Pool schema mismatch; no implicit migration')
                con.execute('INSERT OR IGNORE INTO pool_meta VALUES(1,?)', (SCHEMA,))
                con.commit()
        with self.connect() as con:
            if con.execute('SELECT schema FROM pool_meta WHERE id=1').fetchone()[0] != SCHEMA:
                raise ValueError('Pool schema mismatch')

    def connect(self, *, write=False):
        if write and self.readonly:
            raise ValueError('Read-only site pool')
        con = sqlite3.connect(self.path.as_uri() + ('?mode=rw' if write else '?mode=ro'),
                              uri=True, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        return closing(con)

    def application(self, uri):
        self.verify_identity_evidence()
        host = host_identity(uri)
        with self.connect() as con:
            row = con.execute('SELECT a.* FROM applications a LEFT JOIN aliases x ON x.application_id=a.id '
                              'WHERE a.host=? OR x.host=?', (host, host)).fetchone()
            if row:
                while True:
                    merged = con.execute('SELECT target FROM merges WHERE source=?', (row['id'],)).fetchone()
                    if not merged:
                        return dict(row)
                    row = con.execute('SELECT * FROM applications WHERE id=?', (merged[0],)).fetchone()
            return None

    def verify_identity_evidence(self):
        with self.connect() as con:
            for row in con.execute('SELECT proof FROM aliases UNION ALL SELECT proof FROM merges'):
                verify_evidence(json.loads(row[0]))

    def checkpoint(self, run_id, key, value=None):
        """Immutable completed stages, including failures; conflicts never overwrite."""
        with self.connect(write=value is not None) as con:
            if value is not None:
                con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT value FROM checkpoints WHERE run_id=? AND key=?', (run_id, key)).fetchone()
            if old:
                if value is not None and old[0] != canonical(value):
                    raise ValueError('Checkpoint conflict')
                return json.loads(old[0])
            if value is not None:
                con.execute('INSERT INTO checkpoints VALUES(?,?,?,?)', (run_id, key, canonical(value), time.time()))
                con.commit()
            return value

    def merge(self, source, target, proof):
        """Explicit evidence-backed merge. Keep source rows and original events."""
        verify_evidence(proof)
        with self.connect(write=True) as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='collection_tasks'").fetchone():
                if con.execute('SELECT 1 FROM collection_tasks c JOIN pages p ON p.id=c.page_id '
                               'WHERE p.application_id IN (?,?)', (source,target)).fetchone():
                    raise ValueError('Tracked applications require explicit collection reconciliation before merge')
            if source == target or len(con.execute('SELECT id FROM applications WHERE id IN (?,?)', (source,target)).fetchall()) != 2:
                raise ValueError('Two existing distinct application IDs required')
            if con.execute('SELECT 1 FROM merges WHERE source IN (?,?) OR target=?', (source,target,source)).fetchone():
                raise ValueError('Merge chains require reconciliation; original merge retained')
            con.execute('INSERT INTO merges VALUES(?,?,?)', (source,target,canonical(proof)))
            con.execute('UPDATE pages SET application_id=? WHERE application_id=?', (target,source))
            con.execute('UPDATE aliases SET application_id=? WHERE application_id=?', (target,source))
            con.commit()

    def record(self, value):
        """Identical event replay is a no-op; conflicting event identity is rejected."""
        if value.get('schema_version') != 'webcollect-site-discovery-1' or value.get('origin') not in ORIGINS:
            raise ValueError('Versioned GLM/session/import discovery required')
        if not all(isinstance(value.get(k), str) and value[k].strip()
                   for k in ('event_id', 'run_id', 'uri', 'name', 'category_hint')):
            raise ValueError('Discovery identity, name and category required')
        category(value['category_hint'])
        verify_evidence(value.get('source_refs'))
        uri = page_uri(value['uri']); host = host_identity(uri)
        body = canonical(value); event = object_sha256([value['origin'], value['run_id'], value['event_id']])
        with self.connect(write=True) as con:
            con.execute('BEGIN IMMEDIATE')
            prior = con.execute('SELECT * FROM discoveries WHERE id=?', (event,)).fetchone()
            if prior:
                if prior['record'] != body:
                    raise ValueError('Conflicting discovery event; preserve original')
                p = con.execute('SELECT * FROM pages WHERE id=?', (prior['page_id'],)).fetchone()
                return {'application_id': p['application_id'], 'page_id': p['id'],
                        'discovery_id': event, 'new_application': False, 'new_page': False, 'replayed': True}
            a = con.execute('SELECT a.* FROM applications a LEFT JOIN aliases x ON x.application_id=a.id '
                            'WHERE a.host=? OR x.host=?', (host, host)).fetchone()
            new_application = a is None
            aid = a['id'] if a else 'app-' + object_sha256(host)[:24]
            if a:
                merged = con.execute('SELECT target FROM merges WHERE source=?', (aid,)).fetchone()
                if merged:
                    aid = merged[0]
            if not a:
                con.execute('INSERT INTO applications VALUES(?,?,?,?,?)',
                            (aid, host, value['name'], 'UNKNOWN', time.time()))
            pid = 'page-' + object_sha256(uri)[:24]
            exists = con.execute('SELECT id FROM pages WHERE id=?', (pid,)).fetchone()
            con.execute('INSERT OR IGNORE INTO pages VALUES(?,?,?,?)', (pid, aid, uri, time.time()))
            con.execute('INSERT INTO discoveries VALUES(?,?,?,?,?,?)',
                        (event, pid, value['origin'], value['run_id'], body, time.time()))
            con.commit()
        return {'application_id': aid, 'page_id': pid, 'discovery_id': event,
                'new_application': new_application, 'new_page': not exists, 'replayed': False}

    def add_alias(self, application_id, uri, proof):
        verify_evidence(proof)
        host = host_identity(uri)
        with self.connect(write=True) as con:
            con.execute('BEGIN IMMEDIATE')
            existing = con.execute('SELECT id FROM applications WHERE host=?', (host,)).fetchone()
            if existing and existing['id'] != application_id:
                raise ValueError('Existing application requires an explicit merge, not alias overwrite')
            old = con.execute('SELECT application_id,proof FROM aliases WHERE host=?', (host,)).fetchone()
            if old and tuple(old) != (application_id, canonical(proof)):
                raise ValueError('Alias proof conflict')
            con.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?)', (host, application_id, canonical(proof)))
            con.commit()

    def assess(self, page_id, run_id, decision, evidence):
        """Discovery assessment only. A PROMISING opportunity never creates ready."""
        if decision.get('status') not in ('PROMISING', 'REVIEW_REQUIRED', 'NO_OPPORTUNITY'):
            raise ValueError('Invalid discovery assessment status')
        category(decision.get('category'))
        if not decision.get('reason') or not isinstance(decision.get('task_hint'), str):
            raise ValueError('Evidence-based reason and task hint required')
        verify_evidence(evidence)
        record = {'decision': decision, 'evidence': evidence, 'execution_verified': 'NOT_RUN'}
        identity = object_sha256([page_id, run_id, record])
        with self.connect(write=True) as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('INSERT OR IGNORE INTO assessments VALUES(?,?,?,?,?)',
                        (identity, page_id, run_id, canonical(record), time.time()))
            con.commit()
        return identity

    def freeze_run(self, run_id, config):
        self.verify_identity_evidence()
        with self.connect(write=True) as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if old:
                if old['config'] != canonical(config):
                    raise ValueError('Run configuration cannot change on resume')
                return json.loads(old['baseline'])
            baseline = [dict(r) for r in con.execute('SELECT id,host,name FROM applications ORDER BY id')]
            # Freeze alias and merge identities too; no later import can redefine novelty.
            baseline += [{'id': r['application_id'], 'host': r['host'], 'alias': True}
                         for r in con.execute('SELECT host,application_id FROM aliases ORDER BY host')]
            con.execute('INSERT INTO runs VALUES(?,?,?,?)',
                        (run_id, canonical(config), canonical(baseline), time.time()))
            con.commit()
            return baseline

    def reserve_tool(self, run_id, kind, key, payload, *, maximum=None):
        identity = object_sha256([run_id, kind, key])
        with self.connect(write=True) as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT * FROM tool_requests WHERE id=?', (identity,)).fetchone()
            if old:
                if old['payload'] != canonical(payload):
                    raise ValueError('Tool request payload conflict')
                if old['state'] != 'succeeded':
                    raise ValueError('Tool outcome UNKNOWN/failed; reconcile original, do not resend')
                return identity, json.loads(old['result'])
            if maximum is not None and con.execute('SELECT COUNT(*) FROM tool_requests WHERE run_id=? AND kind=?', (run_id,kind)).fetchone()[0] >= maximum:
                from webcollect.batch_core import BudgetStop
                raise BudgetStop('Discovery tool request limit reached: ' + kind)
            con.execute('INSERT INTO tool_requests VALUES(?,?,?,?,?,?,?,?)',
                        (identity, run_id, kind, canonical(payload), 'reserved', None, time.time(), None))
            con.commit()
            return identity, None

    def settle_tool(self, identity, state, result):
        if state not in ('succeeded', 'failed', 'unknown'):
            raise ValueError('Invalid tool outcome')
        with self.connect(write=True) as con:
            con.execute('BEGIN IMMEDIATE')
            changed = con.execute("UPDATE tool_requests SET state=?,result=?,finished=? WHERE id=? AND state='reserved'",
                                  (state, canonical(result), time.time(), identity)).rowcount
            if changed != 1:
                raise ValueError('Tool request already settled or missing')
            con.commit()

    def bind_capability(self, reference):
        from webcollect.planning import validate_capability
        verify_evidence([reference]); catalog = load_json(reference['path'])
        if catalog.get('schema_version') != 'webcollect-capability-catalog-1':
            raise ValueError('Validated capability catalog required')
        for r in catalog['records']:
            if r.get('mode') != 'real':
                raise ValueError('Real capability evidence required')
            validate_capability(r, require_ready=True)
            if 'site_qualification' not in r and 'review_provenance' not in r:
                raise ValueError('A discovery hint cannot grant capability authority')
        with self.connect(write=True) as con:
            con.execute('BEGIN IMMEDIATE')
            for r in catalog['records']:
                p = con.execute('SELECT id FROM pages WHERE uri=?', (page_uri(r['site_uri']),)).fetchone()
                if not p:
                    raise ValueError('Capability page must already exist in shared pool')
                con.execute('INSERT OR IGNORE INTO capabilities VALUES(?,?,?,?)',
                            (object_sha256([p['id'], reference]), p['id'], canonical(reference), time.time()))
            con.commit()

    def export_candidates(self, output, *, run_id=None):
        source_path = Path(output).with_suffix('.sources.json')
        rows = [row for row in self.rows(run_id=run_id) if row['collection']['dispatch_allowed']]
        save_json(source_path, {'schema_version': 'webcollect-site-sources-1', 'sources': [
            {'kind': 'seed', 'category': row['category'], 'uris': [row['uri']],
             'discovery_provenance': row['discoveries']} for row in rows]})
        records = []
        for row in rows:
            refs = list({r['path']: r for d in row['discoveries'] for r in d['source_refs']}.values())
            records.append({'site_uri': row['uri'], 'site_category': row['category'],
                'application_id': row['application_id'], 'page_id': row['page_id'],
                'source': [{'kind': 'seed', 'source_sha256': file_sha(source_path),
                            'evidence': refs}], 'discovery_assessments': row['assessments'],
                'status': 'review_required', 'execution_verified': 'NOT_RUN'})
        result = {'schema_version': 'webcollect-site-candidates-1', 'mode': 'real', 'records': records,
                  'fixed_candidate_count': len(records), 'real_supply_verified': False,
                  'sample_ids_allocated': 0, 'pool': str(self.path), 'source_manifest': str(source_path.resolve())}
        save_json(output, result)
        return result

    def rows(self, *, run_id=None):
        self.verify_identity_evidence()
        with self.connect() as con:
            sql = 'SELECT p.id AS page_id,p.uri,p.application_id,a.name,a.host,a.category FROM pages p JOIN applications a ON a.id=p.application_id'
            params = ()
            if run_id:
                sql += ' WHERE EXISTS(SELECT 1 FROM discoveries d WHERE d.page_id=p.id AND d.run_id=?)'
                params = (run_id,)
            out = []
            for row in con.execute(sql + ' ORDER BY p.created,p.id', params):
                r = dict(row)
                from webcollect.site_pool_sync import page_state
                r['collection'] = page_state(self, r['uri'])
                scope = ' AND run_id=?' if run_id else ''
                args = (row['page_id'],run_id) if run_id else (row['page_id'],)
                r['discoveries'] = [json.loads(d[0]) for d in con.execute('SELECT record FROM discoveries WHERE page_id=?'+scope+' ORDER BY created,id', args)]
                r['assessments'] = [dict(json.loads(d['record']), run_id=d['run_id']) for d in con.execute('SELECT record,run_id FROM assessments WHERE page_id=?'+scope+' ORDER BY created,id', args)]
                for d in r['discoveries']:
                    verify_evidence(d['source_refs'])
                for a in r['assessments']:
                    verify_evidence(a['evidence'])
                # Consensus is derived; conflicting judgments stay visible and UNKNOWN.
                all_decisions = [json.loads(d[0])['decision']['category'] for d in con.execute(
                    'SELECT s.record FROM assessments s JOIN pages p ON p.id=s.page_id WHERE p.application_id=?', (row['application_id'],))]
                values = set(all_decisions) - {'UNKNOWN'}
                r['category'] = next(iter(values)) if len(values) == 1 else 'UNKNOWN'
                r['category_conflict'] = len(values) > 1
                r['category_hints'] = sorted({d['category_hint'] for d in r['discoveries']})
                out.append(r)
            return out

    def stats(self):
        rows = self.rows()
        from collections import Counter
        cats = {r['application_id']: r['category'] for r in rows}
        hints = {}
        for row in rows:
            hints.setdefault(row['application_id'], set()).update(row['category_hints'])
        hint_counts = Counter(next(iter(h)) if len(h) == 1 else 'UNKNOWN' for h in hints.values())
        with self.connect() as con:
            return {'schema_version': SCHEMA, 'applications': len(cats),
                'pages': con.execute('SELECT COUNT(*) FROM pages').fetchone()[0],
                'discoveries': con.execute('SELECT COUNT(*) FROM discoveries').fetchone()[0],
                'assessments': con.execute('SELECT COUNT(*) FROM assessments').fetchone()[0],
                'application_categories': dict(Counter(cats.values())),
                'application_category_hints': dict(hint_counts),
                'identity_scope': 'host candidates and explicit aliases/merges; not certified independent sites',
                'origins': dict(con.execute('SELECT origin,COUNT(*) FROM discoveries GROUP BY origin')),
                'tool_states': [dict(r) for r in con.execute('SELECT kind,state,COUNT(*) AS count FROM tool_requests GROUP BY kind,state')]}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    sub.add_parser('stats')
    p = sub.add_parser('import-events'); p.add_argument('--input', required=True)
    p = sub.add_parser('export'); p.add_argument('--output', required=True); p.add_argument('--run-id')
    p = sub.add_parser('alias'); p.add_argument('--application-id', required=True); p.add_argument('--uri', required=True); p.add_argument('--proof', required=True)
    p = sub.add_parser('merge'); p.add_argument('--source', required=True); p.add_argument('--target', required=True); p.add_argument('--proof', required=True)
    p = sub.add_parser('bind-capability'); p.add_argument('--catalog', required=True)
    args = parser.parse_args(argv)
    pool = SitePool(args.pool, initialize=args.command == 'init', readonly=args.command == 'stats')
    if args.command == 'import-events':
        payload = load_json(args.input)
        if payload.get('schema_version') != 'webcollect-site-discovery-events-1':
            raise ValueError('Explicit normalized discovery events required')
        results = [pool.record(r) for r in payload['records']]
        result = {'events': results, 'stats': pool.stats()}
    elif args.command == 'export':
        result = pool.export_candidates(args.output, run_id=args.run_id)
    elif args.command == 'alias':
        pool.add_alias(args.application_id, args.uri, load_json(args.proof)); result = pool.stats()
    elif args.command == 'merge':
        pool.merge(args.source, args.target, load_json(args.proof)); result = pool.stats()
    elif args.command == 'bind-capability':
        pool.bind_capability({'path': str(Path(args.catalog).resolve()), 'sha256': file_sha(args.catalog)})
        result = pool.stats()
    else:
        result = pool.stats()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
