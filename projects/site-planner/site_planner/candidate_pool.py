"""Opt-in additive candidate inventory. Production/QC facts stay in RuntimeStore."""
from contextlib import contextmanager
from copy import deepcopy
import json
import time
import unicodedata
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from webcollect.batch_core import load_json
from webcollect.planning import canonical, object_sha256, verify_evidence
from .site_pool import SitePool, category, host_identity, page_uri

VERSION = 'webcollect-data-candidate-1'
VERSION2 = 'webcollect-data-candidate-2'
EXTENSION = 'candidate-pool-1'
EXTENSION2 = 'candidate-pool-2'
PROTOCOLS = (VERSION, VERSION2)
EXTENSIONS = (EXTENSION, EXTENSION2)
ROW_RESULTS = ('NEW', 'DUPLICATE', 'REJECTED', 'OVER_LIMIT', 'HELD')
# Frozen default: explicit known tracking parameters never create new inventory.
TRACKING_QUERY_PREFIXES = ('utm_',)
TRACKING_QUERY_NAMES = frozenset({'spm', 'from', 'ref', 'ref_src', 'fbclid', 'gclid', 'share_token', 'share_id'})
DDL = [
    'CREATE TABLE candidate_meta(id INTEGER PRIMARY KEY CHECK(id=1), version TEXT NOT NULL)',
    '''CREATE TABLE data_candidates(candidate_id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(id),
       dedup_key TEXT NOT NULL UNIQUE, version INTEGER NOT NULL, body TEXT NOT NULL, created REAL NOT NULL,
       state TEXT NOT NULL CHECK(state IN ('pending','consuming','succeeded','failed','reconcile')))''',
    '''CREATE TABLE candidate_versions(candidate_id TEXT NOT NULL REFERENCES data_candidates(candidate_id) DEFERRABLE INITIALLY DEFERRED, version INTEGER NOT NULL,
       body TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(candidate_id,version))''',
    '''CREATE TABLE candidate_sources(candidate_id TEXT NOT NULL REFERENCES data_candidates(candidate_id), source_key TEXT NOT NULL,
       source TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(candidate_id,source_key))''',
    '''CREATE TABLE candidate_claims(claim_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES data_candidates(candidate_id),
       version INTEGER NOT NULL, snapshot TEXT NOT NULL, worker_id TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE,
       token TEXT NOT NULL UNIQUE, expires REAL NOT NULL, state TEXT NOT NULL, stage TEXT NOT NULL,
       binding TEXT, reason TEXT, created REAL NOT NULL, updated REAL NOT NULL)''',
    'CREATE TABLE candidate_empty_requests(request_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, created REAL NOT NULL)',
    "CREATE UNIQUE INDEX one_candidate_holder ON candidate_claims(candidate_id) WHERE state='consuming'",
    '''CREATE TABLE candidate_events(id INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL, claim_id TEXT,
       kind TEXT NOT NULL, record TEXT NOT NULL, created REAL NOT NULL)''',
    '''CREATE TABLE candidate_results(candidate_id TEXT NOT NULL REFERENCES data_candidates(candidate_id), claim_id TEXT NOT NULL,
       sample_id TEXT NOT NULL, record TEXT NOT NULL, qc_state TEXT NOT NULL, qc_report TEXT, effective INTEGER NOT NULL, PRIMARY KEY(candidate_id,claim_id))''',
    'CREATE UNIQUE INDEX candidate_effective_result ON candidate_results(candidate_id) WHERE effective=1',
]
# Additive candidate-producer-3 extension: frozen claim-time sources and stable
# per-response-row conclusions. One transaction; failure rolls back entirely.
V2_DDL = [
    'ALTER TABLE candidate_claims ADD COLUMN sources TEXT',
    '''CREATE TABLE candidate_batch_rows(row_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, batch INTEGER NOT NULL,
       request_id TEXT NOT NULL, response_sha256 TEXT NOT NULL, raw_index INTEGER NOT NULL,
       result TEXT NOT NULL CHECK(result IN ('NEW','DUPLICATE','REJECTED','OVER_LIMIT','HELD')),
       reason TEXT, candidate_id TEXT, record TEXT NOT NULL, created REAL NOT NULL)''',
    'CREATE INDEX candidate_batch_rows_batch ON candidate_batch_rows(run_id,batch)',
    'CREATE INDEX data_candidates_application ON data_candidates(application_id)',
]


def normalize(value):
    if isinstance(value, str):
        return ' '.join(unicodedata.normalize('NFKC', value).split())
    if isinstance(value, list):
        return [normalize(v) for v in value]  # Order can be meaningful.
    if isinstance(value, dict):
        out = {normalize(k): normalize(v) for k, v in value.items()}
        if len(out) != len(value):
            raise ValueError('Normalized parameter keys collide')
        return out
    if value is None or isinstance(value, (bool, int, float)):
        canonical(value)  # Reject NaN etc.
        return value
    raise ValueError('Structured JSON target required')


def validate_target(candidate):
    """A page/source is not itself a concrete acquisition objective."""
    target=candidate['target']
    if normalize(target['kind']).casefold() in {'web_page','page','website','site','url','static_read'}:
        raise ValueError('Concrete business target required; a generic page is only a source')
    if target['entity'].strip().startswith(('http://','https://')) and not target['parameters']:
        raise ValueError('URL-only identity lacks a structured business target or parameters')


def entry_identity(uri):
    """Dedup identity for entry candidates: the navigable original stays in body.

    Tracking parameters and plain in-page anchors never create new inventory;
    route-like fragments (``#/search`` style) distinguish business routes.
    """
    page_uri(uri)  # Public http(s) URL validation only; the fragment is kept below.
    parts = urlsplit(uri)
    query = sorted((name, value) for name, value in parse_qsl(parts.query, keep_blank_values=True)
                   if not name.lower().startswith(TRACKING_QUERY_PREFIXES)
                   and name.lower() not in TRACKING_QUERY_NAMES)
    fragment = parts.fragment
    if fragment.startswith('!'):
        fragment = fragment[1:]
    if not fragment[:1] in ('/', '?'):
        fragment = ''
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/',
                       urlencode(query), fragment))


def candidate_dedup_key(value, application_id):
    kind = value['candidate_kind']
    if kind == 'entry':
        return object_sha256([VERSION2, kind, application_id, entry_identity(value['entry_url'])])
    return object_sha256([VERSION2, kind, application_id, normalize(value['requested_goal'])])


def validate_candidate_v2(value):
    """Body of webcollect-data-candidate-2: URL is bound by the program, the
    frozen requested_goal comes only from trusted caller parameters."""
    if not isinstance(value, dict) or set(value) != {'schema_version','candidate_kind','entry_url','requested_goal'}:
        raise ValueError('Entry/target candidate requires schema_version, candidate_kind, entry_url and requested_goal only')
    if value['schema_version'] != VERSION2:
        raise ValueError('Versioned candidate body required')
    if value['candidate_kind'] not in ('entry','target'):
        raise ValueError('candidate_kind must be entry or target')
    if not isinstance(value['entry_url'], str) or not value['entry_url'].strip():
        raise ValueError('Navigable original entry URL required')
    page_uri(value['entry_url'])
    if value['candidate_kind'] == 'entry':
        if value['requested_goal'] is not None:
            raise ValueError('Entry candidates never freeze a requested_goal')
    else:
        goal = value['requested_goal']
        if not isinstance(goal, dict) or set(goal) != {'kind','entity','parameters'}:
            raise ValueError('Frozen requested_goal requires kind, entity and parameters')
        if not all(isinstance(goal.get(k), str) and normalize(goal[k]) for k in ('kind','entity')) \
                or not isinstance(goal['parameters'], dict):
            raise ValueError('Frozen requested_goal requires structured kind/entity and parameter map')
        normalize(goal['parameters'])


class CandidatePool:
    def __init__(self, path, *, install=False, readonly=False):
        self.pool = SitePool(path, readonly=readonly)
        self.path = self.pool.path
        if install:
            if readonly:
                raise ValueError('Cannot install a read-only candidate pool')
            with self.pool.connect(write=True) as con:
                con.execute('BEGIN IMMEDIATE')
                try:
                    present = con.execute("SELECT 1 FROM sqlite_master WHERE name='candidate_meta'").fetchone()
                    row = con.execute('SELECT version FROM candidate_meta WHERE id=1').fetchone() if present else None
                    if row is None:
                        for sql in DDL:
                            con.execute(sql)
                        for sql in V2_DDL:
                            con.execute(sql)
                        con.execute('INSERT INTO candidate_meta VALUES(1,?)', (EXTENSION2,))
                    elif row[0] == EXTENSION:
                        columns = {r[1] for r in con.execute('PRAGMA table_info(candidate_claims)')}
                        if 'sources' not in columns:
                            for sql in V2_DDL:
                                con.execute(sql)
                        elif not con.execute("SELECT 1 FROM sqlite_master WHERE name='candidate_batch_rows'").fetchone():
                            for sql in V2_DDL[1:]:
                                con.execute(sql)
                        con.execute("UPDATE candidate_meta SET version=? WHERE id=1 AND version=?", (EXTENSION2, EXTENSION))
                    elif row[0] != EXTENSION2:
                        raise ValueError('Unknown candidate extension version: ' + row[0])
                    con.commit()
                except BaseException:
                    con.rollback()
                    raise
        with self.pool.connect() as con:
            row = con.execute('SELECT version FROM candidate_meta WHERE id=1').fetchone()
            tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            expected={'data_candidates','candidate_versions','candidate_sources','candidate_claims',
                      'candidate_empty_requests','candidate_events','candidate_results'}
            if not row or row[0] not in EXTENSIONS or not expected <= tables:
                raise ValueError('Explicit candidate extension install required')
            if row[0] == EXTENSION2 and 'candidate_batch_rows' not in tables:
                raise ValueError('Candidate producer extension incomplete; explicit reinstall required')
            self.extension_version = row[0]
            check=con.execute('PRAGMA foreign_key_check').fetchone()
            if check: raise ValueError('Candidate pool foreign-key integrity failed')

    @property
    def entry_protocol_installed(self):
        return self.extension_version == EXTENSION2

    def _require_v2(self):
        if not self.entry_protocol_installed:
            raise ValueError('Explicit candidate-pool-2 install required for webcollect-data-candidate-2')

    @contextmanager
    def transaction(self):
        with self.pool.connect(write=True) as con:
            con.execute('BEGIN IMMEDIATE')
            yield con
            con.commit()

    def event(self, con, cid, claim, kind, record):
        con.execute('INSERT INTO candidate_events(candidate_id,claim_id,kind,record,created) VALUES(?,?,?,?,?)',
                    (cid, claim, kind, canonical(record), time.time()))

    def put(self, candidate, source):
        value = deepcopy(candidate)
        if value.get('schema_version') == VERSION2:
            return self._put_v2(value, source)[0]
        if set(value) != {'schema_version','name','business_kind','description','parent_category','entry_url','target'}:
            raise ValueError('Candidate IDs/state are assigned by the program, not supplied')
        if value.get('schema_version') != VERSION or set(value['target']) != {'kind','entity','parameters'}:
            raise ValueError('Versioned structured target required')
        for key in ('name','business_kind','description'):
            if not isinstance(value.get(key), str) or not value[key].strip():
                raise ValueError('Candidate requires ' + key)
        if not all(isinstance(value['target'].get(k), str) and normalize(value['target'][k]) for k in ('kind','entity')) or not isinstance(value['target']['parameters'], dict):
            raise ValueError('Target kind, entity and parameter map required')
        category(value['parent_category']); value['entry_url'] = page_uri(value['entry_url'])
        validate_target(value)
        verify_evidence(source['references'])
        # This retains the original discovery contract without page browsing/assessment.
        inserted = self.pool.record({'schema_version':'webcollect-site-discovery-1',
            'origin':source['origin'], 'run_id':source['run_id'],
            'event_id':object_sha256([value, source]), 'uri':value['entry_url'],
            'name':value['name'], 'category_hint':value['parent_category'], 'source_refs':source['references']})
        aid = inserted['application_id']
        key = object_sha256([VERSION, aid, normalize(value['target'])])
        with self.transaction() as con:
            old = con.execute('SELECT * FROM data_candidates WHERE dedup_key=?', (key,)).fetchone()
            cid = old['candidate_id'] if old else 'candidate-' + str(uuid.uuid4())
            # Description, classification and discovery URL are metadata, never identity.
            version = old['version'] if old else 1
            if not old or json.loads(old['body']) != value:
                if old: version += 1
                con.execute('INSERT INTO candidate_versions VALUES(?,?,?,?)', (cid,version,canonical(value),time.time()))
                if old:
                    con.execute('UPDATE data_candidates SET version=?,body=? WHERE candidate_id=?', (version,canonical(value),cid))
                else:
                    # Version and candidate become visible in the same transaction.
                    con.execute('INSERT INTO data_candidates VALUES(?,?,?,?,?,?,?)',
                                (cid,aid,key,version,canonical(value),time.time(),'pending'))
            con.execute('INSERT OR IGNORE INTO candidate_sources VALUES(?,?,?,?)', (cid,object_sha256(source),canonical(source),time.time()))
            self.event(con,cid,None,'discovered',{'version':version,'source':source})
            return cid

    def _put_v2(self, value, source, *, application_id=None, row_header=None):
        """Insert/append a webcollect-data-candidate-2 candidate.

        The body is immutable for one identity: later suggestions or tracking-
        parameter variants only append sources and never rewrite a frozen
        candidate, version, body or claim snapshot.
        """
        self._require_v2()
        validate_candidate_v2(value)
        verify_evidence(source['references'])
        if row_header is not None:
            if row_header.get('result') not in (None, 'NEW', 'DUPLICATE'):
                raise ValueError('Publishing rows only conclude NEW or DUPLICATE')
        aid = application_id
        if aid is None:
            aid = self.pool.record({'schema_version':'webcollect-site-discovery-1',
                'origin':source['origin'], 'run_id':source['run_id'],
                'event_id':object_sha256([value, source]), 'uri':value['entry_url'],
                'name':source.get('application_hint') or host_identity(value['entry_url']),
                'category_hint':source.get('category_hint') or 'UNKNOWN',
                'candidate_kind':value['candidate_kind'], 'source_refs':source['references']})['application_id']
        key = candidate_dedup_key(value, aid)
        with self.transaction() as con:
            if row_header is not None:
                prior = con.execute('SELECT response_sha256,record FROM candidate_batch_rows WHERE row_id=?',
                                    (row_header['row_id'],)).fetchone()
                if prior:
                    if prior['response_sha256'] != row_header['response_sha256']:
                        raise ValueError('Row conclusion digest conflict; verify the original response')
                    return json.loads(prior['record'])
            old = con.execute('SELECT candidate_id FROM data_candidates WHERE dedup_key=?', (key,)).fetchone()
            duplicate = old is not None
            cid = old['candidate_id'] if old else 'candidate-' + str(uuid.uuid4())
            if not old:
                con.execute('INSERT INTO candidate_versions VALUES(?,?,?,?)', (cid,1,canonical(value),time.time()))
                con.execute('INSERT INTO data_candidates VALUES(?,?,?,?,?,?,?)',
                            (cid,aid,key,1,canonical(value),time.time(),'pending'))
            con.execute('INSERT OR IGNORE INTO candidate_sources VALUES(?,?,?,?)', (cid,object_sha256(source),canonical(source),time.time()))
            if not old:
                self.event(con,cid,None,'discovered',{'version':1,'protocol':VERSION2,'source':source})
            elif row_header is not None:
                self.event(con,cid,None,'source_appended',{'protocol':VERSION2,'source':source})
            if row_header is None:
                return cid, duplicate
            record = {'row_id':row_header['row_id'],'raw_index':row_header['raw_index'],
                      'result':'DUPLICATE' if duplicate else 'NEW','candidate_id':cid,'reason':row_header.get('reason')}
            con.execute('INSERT INTO candidate_batch_rows(row_id,run_id,batch,request_id,response_sha256,raw_index,result,reason,candidate_id,record,created)'
                        ' VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (row_header['row_id'],row_header['run_id'],row_header['batch'],row_header['request_id'],
                         row_header['response_sha256'],row_header['raw_index'],record['result'],record['reason'],
                         cid,canonical(record),time.time()))
            return record

    def publish_row(self, row_header, candidate, source, *, application_id=None):
        """One transaction makes candidate, version, source and this response
        row's conclusion visible together; replay returns the original verdict."""
        record = self._put_v2(deepcopy(candidate), source, application_id=application_id, row_header=row_header)
        return record if isinstance(record, dict) else {'row_id':row_header['row_id'],'raw_index':row_header['raw_index'],
                                                        'result':'DUPLICATE','candidate_id':record,'reason':row_header.get('reason')}

    def record_row_conclusion(self, row_header, *, result, reason, original_row=None, entry_http=None):
        if result not in ('REJECTED','OVER_LIMIT','HELD') or not reason:
            raise ValueError('Conclusion-only rows record REJECTED/OVER_LIMIT/HELD with a reason')
        record = {'row_id':row_header['row_id'],'raw_index':row_header['raw_index'],'result':result,
                  'reason':reason,'candidate_id':None,'row':original_row}
        if entry_http is not None:
            verify_evidence([entry_http])
            record['entry_http'] = entry_http
            record['http_status'] = load_json(entry_http['path'])['http_status']
        with self.transaction() as con:
            prior = con.execute('SELECT response_sha256,record FROM candidate_batch_rows WHERE row_id=?',
                                (row_header['row_id'],)).fetchone()
            if prior:
                if prior['response_sha256'] != row_header['response_sha256']:
                    raise ValueError('Row conclusion digest conflict; verify the original response')
                return json.loads(prior['record'])
            con.execute('INSERT INTO candidate_batch_rows(row_id,run_id,batch,request_id,response_sha256,raw_index,result,reason,candidate_id,record,created)'
                        ' VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (row_header['row_id'],row_header['run_id'],row_header['batch'],row_header['request_id'],
                         row_header['response_sha256'],row_header['raw_index'],result,reason,None,canonical(record),time.time()))
            return record

    def batch_row(self, row_id):
        with self.pool.connect() as con:
            row = con.execute('SELECT record FROM candidate_batch_rows WHERE row_id=?', (row_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def batch_row_identity(self, row_id):
        """Stored response digest plus conclusion for replay verification."""
        with self.pool.connect() as con:
            row = con.execute('SELECT response_sha256,record FROM candidate_batch_rows WHERE row_id=?', (row_id,)).fetchone()
            return (row['response_sha256'], json.loads(row['record'])) if row else None

    def batch_rows(self, run_id, batch):
        with self.pool.connect() as con:
            return [json.loads(r[0]) for r in con.execute(
                'SELECT record FROM candidate_batch_rows WHERE run_id=? AND batch=? ORDER BY raw_index', (run_id,batch))]

    def resolve_applications(self, uris):
        """Targeted per-batch application resolution; alias/merge evidence is
        still verified, but no full candidate/entity table is loaded."""
        self.pool.verify_identity_evidence()
        out = {}
        with self.pool.connect() as con:
            for uri in dict.fromkeys(uris):
                host = host_identity(uri)
                row = con.execute('SELECT a.id FROM applications a LEFT JOIN aliases x ON x.application_id=a.id '
                                  'WHERE a.host=? OR x.host=?', (host,host)).fetchone()
                aid = row['id'] if row else None
                while aid:
                    merged = con.execute('SELECT target FROM merges WHERE source=?', (aid,)).fetchone()
                    if not merged:
                        break
                    aid = merged[0]
                out[uri] = aid
            return out

    def candidate_state(self, uri, *, candidate_kind='entry'):
        """Targeted dedup probe for one batch entry; returns matching candidate
        state without loading pool entities."""
        aid = self.resolve_applications([uri])[uri]
        if aid is None:
            return None
        from copy import deepcopy as _copy
        probe = {'schema_version':VERSION2,'candidate_kind':candidate_kind,
                 'entry_url':uri,'requested_goal':None}
        key = candidate_dedup_key(probe, aid)
        with self.pool.connect() as con:
            row = con.execute('SELECT candidate_id,state FROM data_candidates WHERE dedup_key=?', (key,)).fetchone()
            return {'candidate_id':row['candidate_id'],'state':row['state']} if row else None

    def reject_unconsumed(self, candidate_id, reason):
        if not reason: raise ValueError('Rejection reason required')
        with self.transaction() as con:
            row=con.execute('SELECT state FROM data_candidates WHERE candidate_id=?',(candidate_id,)).fetchone()
            if not row or row[0] not in ('pending','failed'): raise ValueError('Cannot quarantine an active or saved candidate')
            con.execute("UPDATE data_candidates SET state='failed' WHERE candidate_id=?",(candidate_id,))
            self.event(con,candidate_id,None,'producer_target_rejected',{'reason':reason})

    def rows(self, *, categories=None, application_id=None, state=None, protocols=None):
        """Rows visible to one protocol generation. Callers that did not opt in
        to the entry protocol only ever see webcollect-data-candidate-1 rows."""
        if protocols is None:
            protocols = (VERSION,)
        protocols = tuple(protocols)
        if protocols and not set(protocols) <= set(PROTOCOLS):
            raise ValueError('Supported candidate body protocols required')
        with self.pool.connect() as con:
            out = []
            for r in con.execute('SELECT * FROM data_candidates ORDER BY created,candidate_id'):
                row = dict(r); row['candidate'] = json.loads(row.pop('body'))
                if row['candidate'].get('schema_version') not in protocols: continue
                if categories and self._row_category(row, con) not in categories: continue
                if application_id and row['application_id'] != application_id: continue
                if state and row['state'] != state: continue
                row['sources'] = [json.loads(s[0]) for s in con.execute('SELECT source FROM candidate_sources WHERE candidate_id=? ORDER BY created', (row['candidate_id'],))]
                for source in row['sources']: verify_evidence(source['references'])
                row['result'] = con.execute('SELECT record,qc_state,qc_report FROM candidate_results WHERE candidate_id=? AND effective=1', (row['candidate_id'],)).fetchone()
                row['result'] = dict(row['result']) if row['result'] else None
                if row['result']:
                    row['result']['record']=json.loads(row['result']['record'])
                    row['result']['qc_report']=json.loads(row['result']['qc_report']) if row['result']['qc_report'] else None
                out.append(row)
            return out

    def _row_category(self, row, con):
        body = row['candidate'] if 'candidate' in row.keys() else json.loads(row['body'])
        if 'parent_category' in body:
            return body['parent_category']
        # Entry candidates keep classification in source context; UNKNOWN stays visible.
        for source in con.execute('SELECT source FROM candidate_sources WHERE candidate_id=? ORDER BY created', (row['candidate_id'],)):
            hint = json.loads(source[0]).get('category_hint')
            if hint:
                return hint
        return 'UNKNOWN'

    @staticmethod
    def _claim(row):
        value = dict(row)
        for key in ('snapshot','binding'):
            value[key] = json.loads(value[key]) if value[key] else None
        value['sources'] = json.loads(value['sources']) if value.get('sources') else None
        return value

    def claim_next(self, worker_id, request_id, *, lease_seconds=300, categories=None, application_id=None, candidate_id=None, protocols=None, producer_batch=None):
        if not worker_id or not request_id or not 1 <= lease_seconds <= 86400:
            raise ValueError('Worker, unique request and bounded lease required')
        if protocols is None:
            protocols = (VERSION,)
        protocols = tuple(protocols)
        if protocols and not set(protocols) <= set(PROTOCOLS):
            raise ValueError('Supported candidate body protocols required')
        if producer_batch and protocols != (VERSION2,):
            raise ValueError('Producer batch selection requires the entry protocol')
        if VERSION2 in protocols:
            self._require_v2()
        with self.transaction() as con:
            now = time.time()
            for old in con.execute("SELECT * FROM candidate_claims WHERE state='consuming' AND expires<=?", (now,)).fetchall():
                con.execute("UPDATE candidate_claims SET state='reconcile',reason='lease_expired',updated=? WHERE claim_id=?", (now,old['claim_id']))
                con.execute("UPDATE data_candidates SET state='reconcile' WHERE candidate_id=?", (old['candidate_id'],))
                self.event(con,old['candidate_id'],old['claim_id'],'lease_expired',{})
            empty=con.execute('SELECT worker_id FROM candidate_empty_requests WHERE request_id=?',(request_id,)).fetchone()
            if empty:
                if empty[0]!=worker_id: raise ValueError('Claim request owner conflict')
                return {'state':'EMPTY'}
            prior = con.execute('SELECT * FROM candidate_claims WHERE request_id=?', (request_id,)).fetchone()
            if prior:
                if prior['worker_id'] != worker_id: raise ValueError('Claim request owner conflict')
                if candidate_id and prior['candidate_id']!=candidate_id:raise ValueError('Claim request target conflict')
                if producer_batch and not con.execute("SELECT 1 FROM candidate_batch_rows WHERE run_id=? AND result='NEW' AND candidate_id=?", (producer_batch, prior['candidate_id'])).fetchone():
                    raise ValueError('Claim request producer batch conflict')
                return self._claim(prior)
            sql = "SELECT * FROM data_candidates WHERE state='pending'"
            if producer_batch:
                sql += " AND candidate_id IN (SELECT candidate_id FROM candidate_batch_rows WHERE run_id=? AND result='NEW')"
            for row in con.execute(sql+' ORDER BY created,candidate_id', (producer_batch,) if producer_batch else ()):
                if candidate_id and row['candidate_id']!=candidate_id:continue
                body = json.loads(row['body'])
                if body.get('schema_version') not in protocols: continue
                if categories and self._row_category(row, con) not in categories: continue
                if application_id and row['application_id'] != application_id: continue
                sources=[json.loads(s[0]) for s in con.execute('SELECT source FROM candidate_sources WHERE candidate_id=?', (row['candidate_id'],))]
                for src in sources:
                    verify_evidence(src['references'])
                cid = row['candidate_id']; claim = str(uuid.uuid4()); token = str(uuid.uuid4())
                # The lease freezes id, version, body and the source references
                # visible at claim time; later suggestions cannot alter it.
                if self.entry_protocol_installed:
                    con.execute('INSERT INTO candidate_claims(claim_id,candidate_id,version,snapshot,worker_id,request_id,token,expires,state,stage,binding,reason,created,updated,sources)'
                                ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                (claim,cid,row['version'],canonical(body),worker_id,request_id,token,now+lease_seconds,'consuming','claimed',None,None,now,now,
                                 canonical(sources)))
                else:
                    con.execute('INSERT INTO candidate_claims VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                (claim,cid,row['version'],canonical(body),worker_id,request_id,token,now+lease_seconds,'consuming','claimed',None,None,now,now))
                con.execute("UPDATE data_candidates SET state='consuming' WHERE candidate_id=?", (cid,))
                self.event(con,cid,claim,'claimed',{'request_id':request_id,'version':row['version'],'protocols':list(protocols)})
                return self._claim(con.execute('SELECT * FROM candidate_claims WHERE claim_id=?', (claim,)).fetchone())
            con.execute('INSERT INTO candidate_empty_requests VALUES(?,?,?)',(request_id,worker_id,now))
            return {'state':'EMPTY'}

    def producer_batch_drained(self, producer_batch):
        # A producer can insert the last row between the worker's empty poll and this read.
        with self.pool.connect() as con:
            return bool(con.execute("""SELECT EXISTS(SELECT 1 FROM checkpoints WHERE run_id=? AND key LIKE 'entry-complete/%')
                AND NOT EXISTS(SELECT 1 FROM candidate_batch_rows b JOIN data_candidates c USING(candidate_id)
                    WHERE b.run_id=? AND b.result='NEW' AND c.state='pending')""", (producer_batch, producer_batch)).fetchone()[0])

    def _fence(self, con, claim):
        row = con.execute('SELECT * FROM candidate_claims WHERE claim_id=?', (claim['claim_id'],)).fetchone()
        if not row or row['token'] != claim['token'] or row['worker_id'] != claim['worker_id'] or row['state'] != 'consuming' or row['expires'] <= time.time():
            raise ValueError('Expired or invalid candidate credential; reconcile original')
        if json.loads(row['snapshot']) != claim['snapshot'] or row['version'] != claim['version']:
            raise ValueError('Claim target changed')
        return row

    def heartbeat(self, claim, seconds=300):
        if not 1 <= seconds <= 86400: raise ValueError('Bounded lease required')
        with self.transaction() as con:
            self._fence(con,claim)
            con.execute('UPDATE candidate_claims SET expires=?,updated=? WHERE claim_id=?', (time.time()+seconds,time.time(),claim['claim_id']))

    def stage(self, claim, stage, binding=None, *, expected_stage=None):
        with self.transaction() as con:
            row = self._fence(con,claim)
            if expected_stage is not None and row['stage'] != expected_stage:
                return False
            old = json.loads(row['binding'] or '{}')
            for key,value in (binding or {}).items():
                if key in old and old[key] != value: raise ValueError('Original execution binding cannot change')
                old[key] = value
            con.execute('UPDATE candidate_claims SET stage=?,binding=?,updated=? WHERE claim_id=?', (stage,canonical(old),time.time(),claim['claim_id']))
            self.event(con,row['candidate_id'],row['claim_id'],stage,old)
            return True

    def finish(self, claim, *, state, reason, stage):
        if state not in ('failed','reconcile') or not reason: raise ValueError('Failure/uncertainty reason required')
        with self.transaction() as con:
            row = self._fence(con,claim)
            con.execute('UPDATE candidate_claims SET state=?,stage=?,reason=?,updated=? WHERE claim_id=?', (state,stage,reason,time.time(),claim['claim_id']))
            con.execute('UPDATE data_candidates SET state=? WHERE candidate_id=?', (state,row['candidate_id']))
            self.event(con,row['candidate_id'],row['claim_id'],state,{'stage':stage,'reason':reason})

    def get_claim(self, claim_id):
        with self.pool.connect() as con:
            row = con.execute('SELECT * FROM candidate_claims WHERE claim_id=?', (claim_id,)).fetchone()
            if not row: raise ValueError('Unknown claim')
            return self._claim(row)

    def stats(self):
        with self.pool.connect() as con:
            counts = {r[0]:r[1] for r in con.execute('SELECT state,COUNT(*) FROM data_candidates GROUP BY state')}
            by_protocol = {p:0 for p in PROTOCOLS}
            for r in con.execute("SELECT json_extract(body,'$.schema_version') AS v, COUNT(*) FROM data_candidates GROUP BY v"):
                if r[0] in by_protocol: by_protocol[r[0]] = r[1]
            qc = {r[0]:r[1] for r in con.execute('SELECT qc_state,COUNT(*) FROM candidate_results WHERE effective=1 GROUP BY qc_state')}
            return {'candidate_total':sum(counts.values()), **{k:counts.get(k,0) for k in ('pending','consuming','succeeded','failed','reconcile')},
                    'by_protocol':by_protocol,
                    'consumption_attempts':con.execute('SELECT COUNT(*) FROM candidate_claims').fetchone()[0], 'QC':qc}
