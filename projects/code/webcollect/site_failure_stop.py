"""One append-only, campaign-bound whole-application failure ledger.

Original collection/model ledgers are read-only sources. This module neither
dispatches work nor retries requests. Unknown outcomes remain explicit holds.
"""
import argparse
from contextlib import ExitStack, closing
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit, urlunsplit

from .batch_core import file_sha, load_json
from .planning import canonical, object_sha256
from .plan_protocol import REACT_SESSION_PROTOCOL
from .production_identity import page_url

VERSION = 'webcollect-whole-site-failure-stop-1'
LIMIT = 3
# Sealed historical react terminals/receipts keep 'webcollect-react-session-1';
# current writers emit the stable name. Read-side dual acceptance.
SEALED_REACT_SESSION_PROTOCOLS = (REACT_SESSION_PROTOCOL, 'webcollect-react-session-1')


class SiteStopped(ValueError):
    pass


def application_key(value, registry=None):
    """Use the pilot identity's whole-host normalization, never a page key."""
    uri = value['pilot_identity']['application']['canonical_uri'] if isinstance(value, dict) and value.get('pilot_identity') else (
        value.get('site_uri', value.get('initial_url')) if isinstance(value, dict) else value)
    from .application_identity import canonical_key
    return canonical_key(uri, registry)


def execution_id(stage, source, identity):
    return stage + ':' + object_sha256([str(Path(source).resolve()), identity])


def validate_binding(value):
    if (not isinstance(value, dict) or not {'ledger', 'campaign_id', 'formal_since'} <= set(value)
            or set(value) - {'ledger', 'campaign_id', 'formal_since', 'application_registry', 'dispatch_rules'}
            or not isinstance(value['ledger'], str) or not Path(value['ledger']).is_absolute()
            or not isinstance(value['campaign_id'], str) or not value['campaign_id'].strip()
            or type(value['formal_since']) not in (int, float) or not 0 < value['formal_since'] < float('inf')):
        raise ValueError('Whole-site failure guard requires a fixed absolute ledger, campaign and formal_since')
    if 'dispatch_rules' in value:
        from .current_chain import PROJECT_RULES
        if value['dispatch_rules'] != PROJECT_RULES:
            raise ValueError('Unsupported site dispatch rules')
    if value.get('application_registry') is not None:
        from .application_identity import aliases
        aliases(value['application_registry'])
    return {**value, 'ledger': str(Path(value['ledger']).resolve())}


def _verify_persisted_reassessment_evidence(refs):
    """Revalidate persisted reassessment evidence without freezing source code.

    Data evidence (failure receipts, capture outcomes, criteria documents) is
    byte-verified forever. A reference into the collector's own source tree is
    a provenance record of the reviewed code version: the file must still
    exist, the receipt keeps the reviewed sha256, but the live tree may evolve
    — otherwise any later code change would globally block dispatch through
    export_facts/status. Byte equality for source files is still enforced at
    append/apply time, when the review is actually decided.
    """
    from .planning import verify_evidence
    source_root = Path(__file__).resolve().parent
    criteria_root = source_root.parents[2] / 'request'
    data, provenance = [], []
    for ref in refs:
        if isinstance(ref, dict) and isinstance(ref.get('path'), str) and ref['path']:
            resolved = None
            try:
                resolved = Path(ref['path']).resolve()
            except OSError:
                resolved = None
            inside_source = bool(resolved and resolved.is_relative_to(source_root))
            # Criteria documents under request/ are living requirement texts:
            # like collector source refs they are provenance (the receipt keeps
            # the reviewed sha256), never byte-frozen dispatch preconditions —
            # otherwise any authorized criteria revision blocks all dispatch.
            inside_criteria = bool(resolved and criteria_root.is_dir()
                                   and resolved.is_relative_to(criteria_root))
            (provenance if inside_source or inside_criteria else data).append(ref)
        else:
            data.append(ref)
    if data:
        verify_evidence(data)
    for ref in provenance:
        path = Path(ref['path'])
        if ref.get('sha256') and (not path.is_file() or path.is_symlink()):
            raise ValueError('Reviewed provenance file no longer exists: ' + ref['path'])


class SiteFailureStore:
    def __init__(self, binding, *, _seeding=False):
        self.binding = validate_binding(binding)
        self.path = Path(self.binding['ledger'])
        self.failure_limit = None if 'dispatch_rules' in self.binding else LIMIT
        self.facts_schema = 'webcollect-site-execution-facts-2' if self.failure_limit is None else 'webcollect-site-execution-facts-1'
        with self.connect() as con:
            meta = json.loads(con.execute('SELECT value FROM stop_meta WHERE id=1').fetchone()[0])
        if meta['binding'] != self.binding or meta['version'] != VERSION or meta['failure_limit'] != self.failure_limit:
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
        if seed_policy is not None and 'dispatch_rules' in binding:
            raise ValueError('New candidate projects start without historical site decisions')
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
                'failure_limit': None if 'dispatch_rules' in binding else LIMIT, 'seed_policy': {'path': str(Path(seed_policy).resolve()),
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

    def record(self, application, identity, *, stage, state, reason, real_execution, evidence, usage_refs, return_status=True):
        if (real_execution is not True or state not in ('failed', 'unknown') or stage not in ('probe', 'observation', 'formal')
                or not isinstance(reason, str) or not reason.strip() or not identity or not evidence
                or not isinstance(usage_refs, list)):
            raise ValueError('Only evidenced real execution failures/unknown outcomes may enter the site ledger')
        body = (identity, application_key(application, self.binding.get('application_registry')), stage, state, reason, canonical(evidence), canonical(usage_refs))
        with self.connect(True) as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT execution_id,application_key,stage,state,reason,evidence_json,usage_refs_json '
                              'FROM site_executions WHERE execution_id=?', (identity,)).fetchone()
            if old and tuple(old) != body:
                raise ValueError('Original execution identity cannot be reclassified or moved to another site')
            if not old:
                con.execute('INSERT INTO site_executions VALUES(?,?,?,?,?,?,?,?)', (*body, time.time()))
            con.commit()
        if return_status:
            return self.status(application)

    def execution(self, identity):
        """Read-only sealed fact for one exact execution identity, or None."""
        with self.connect() as con:
            row = con.execute('SELECT execution_id,application_key,stage,state,reason,evidence_json,usage_refs_json '
                              'FROM site_executions WHERE execution_id=?', (identity,)).fetchone()
        if not row:
            return None
        return {'execution_id': row[0], 'application_key': row[1], 'stage': row[2], 'state': row[3],
                'reason': row[4], 'evidence': json.loads(row[5]), 'usage_refs': json.loads(row[6])}

    def enable_closed_entry_uri_scope(self, manifest, producer_ledger, reason):
        """Bind this local decision to the original new project's producer book."""
        from .current_chain import check_project_guard, read_chain_scope
        chain = read_chain_scope(Path(manifest).absolute())
        if not chain.get('candidate_project') or not reason.strip():
            raise ValueError('Original candidate project and explicit URI isolation instruction required')
        check_project_guard(chain, self.binding, producer_ledger, role='producer')
        record = {'producer_ledger':str(Path(producer_ledger).resolve()), 'manifest':chain['manifest'],
                  'reason':reason, 'policy':'closed-read-only-entry-get-uri-1'}
        with self.connect(True) as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('CREATE TABLE IF NOT EXISTS entry_get_uri_policy(id INTEGER PRIMARY KEY CHECK(id=1), decision TEXT NOT NULL, created REAL NOT NULL)')
            con.execute('INSERT OR IGNORE INTO entry_get_uri_policy VALUES(1,?,?)',(canonical(record),time.time()))
            original = json.loads(con.execute('SELECT decision FROM entry_get_uri_policy WHERE id=1').fetchone()[0])
            if original['producer_ledger'] != record['producer_ledger'] or original['manifest'] != record['manifest']:
                raise ValueError('Original entry GET isolation binding changed')
            con.commit()
        return original

    @staticmethod
    def _closed_producer_get_uri(ledger, database, fact):
        """A finished visit alone is insufficient. Require the sealed, zero-model GET job."""
        from .planning import verify_evidence
        identity, _, stage, reason, evidence, usage = fact
        refs = json.loads(usage)
        if stage != 'probe' or len(refs) != 1 or not isinstance(refs[0],dict) or refs[0].get('ledger') != database:
            return None
        visit_id = refs[0].get('visit_id')
        if not visit_id or identity != execution_id('probe', database, visit_id):
            return None
        row = ledger.execute(
            "SELECT v.*,j.payload,j.result FROM top_level_visits v JOIN jobs j ON j.id=v.job_id "
            "WHERE v.id=? AND v.purpose='candidate-entry-http' AND v.state='unknown' AND v.finished_at IS NOT NULL "
            "AND v.response_status IS NULL AND v.error_type=? AND j.kind='candidate-entry-http' AND j.state='done' "
            "AND NOT EXISTS(SELECT 1 FROM model_requests r WHERE r.job_id=j.id)",(visit_id,reason)).fetchone()
        if row is None or not row['result']:
            return None
        original = {k:row[k] for k in ('id','job_id','target_uri','dispatched_at')}
        if json.loads(evidence) != [{'visit_fact':original}]:
            return None
        payload, ref = json.loads(row['payload']), json.loads(row['result'])
        verify_evidence([ref])
        receipt = load_json(ref['path'])
        if (payload.get('uri') == row['target_uri'] == receipt.get('entry_uri') and
                payload.get('policy') == receipt.get('policy') == 'producer-entry-http-get-1' and
                receipt.get('method') == 'GET' and receipt.get('job_id') == row['job_id'] and
                receipt.get('visit_id') == visit_id and receipt.get('result') == 'HELD' and
                'http_status' in receipt and receipt['http_status'] is None and
                receipt.get('reason') == row['error_message'] and receipt.get('checked_at',0) >= row['finished_at']):
            return row['target_uri']
        return None

    @staticmethod
    def _closed_producer_document_uri(ledger, database, fact):
        """Narrow a retained stale-dispatch fact using its sealed zero-model GET."""
        from .planning import verify_evidence
        identity, _, stage, _, evidence, usage = fact
        refs = json.loads(usage)
        if (stage != 'probe' or len(refs) != 1 or refs[0].get('ledger') != database
                or identity != execution_id('probe', database, refs[0].get('visit_id'))):
            return None
        row = ledger.execute(
            "SELECT v.*,j.kind,j.state AS job_state,j.payload,j.result FROM top_level_visits v "
            "JOIN jobs j ON j.id=v.job_id WHERE v.id=?", (refs[0]['visit_id'],)).fetchone()
        if (not row or row['purpose'] != 'application-evidence-get' or row['kind'] != row['purpose']
                or row['state'] != 'succeeded' or row['finished_at'] is None
                or row['job_state'] != 'done' or not row['result']
                or not isinstance(row['response_status'], int) or not 200 <= row['response_status'] < 300
                or ledger.execute('SELECT 1 FROM model_requests WHERE job_id=? LIMIT 1', (row['job_id'],)).fetchone()):
            return None
        original = {k: row[k] for k in ('id', 'job_id', 'target_uri', 'dispatched_at')}
        if json.loads(evidence) != [{'visit_fact': original}]:
            return None
        payload, ref = json.loads(row['payload']), json.loads(row['result'])
        verify_evidence([ref])
        document = load_json(ref['path'])
        if (payload.get('policy') != 'producer-site-tables-1'
                or payload.get('uri') != row['target_uri']
                or document.get('job_id') != row['job_id']
                or document.get('uri') != row['landed_uri']
                or document.get('request_uri') != row['target_uri']
                or document.get('http_status') != row['response_status']
                or not document.get('raw_html')):
            return None
        verify_evidence([document['raw_html']])
        return row['target_uri']

    def _fact_scope(self, fact, books, producer):
        from .request_quarantine import attempt_owner, visit_uri
        identity, _, stage, _, _, raw_refs = fact
        refs = json.loads(raw_refs)
        if len(refs) != 1 or not isinstance(refs[0], dict):
            return None
        ref = refs[0]
        if stage == 'formal':
            attempt_id = ref.get('attempt_id')
            if not attempt_id or identity != 'formal:'+object_sha256({'attempt_id':attempt_id}):
                return None
            owner = attempt_owner(self.binding, ref.get('registry'), attempt_id)
            if owner and (owner['status']=='interrupted' or owner['failure_class']=='interrupted'):
                return owner
        if stage == 'probe':
            database = ref.get('ledger')
            ledger = books.get(database)
            if ledger is not None:
                sealed = (self._closed_producer_get_uri(ledger, database, fact)
                          or self._closed_producer_document_uri(ledger, database, fact)) if database==producer else None
                uri = sealed or visit_uri(ledger, fact)
                if uri:
                    return {'uri':uri, 'closed_entry':bool(sealed)}
        return None

    def _project_holds(self, application, key, applied, candidate_id):
        from .request_quarantine import endpoint
        holds = {'pages':0, 'closed_entries':0, 'tasks':0, 'matching_pages':[], 'matching_tasks':[]}
        uri = (application.get('initial_url') or application.get('site_uri')) if isinstance(application,dict) else application
        aliases = self.binding.get('application_registry')
        if not uri:
            return holds
        if isinstance(application,dict):
            candidate_id = (application.get('candidate_binding') or {}).get('candidate_id') or candidate_id
        netloc = urlsplit(key).netloc
        other = '//'+(netloc[4:] if netloc.startswith('www.') else 'www.'+netloc)+'/'
        producer = self.path.with_name('producer-jobs.sqlite3')
        with self.connect() as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='entry_get_uri_policy'").fetchone():
                policy = json.loads(con.execute('SELECT decision FROM entry_get_uri_policy WHERE id=1').fetchone()[0])
                producer = Path(policy['producer_ledger'])
            facts = con.execute("SELECT execution_id,application_key,stage,reason,evidence_json,usage_refs_json "
                                "FROM site_executions WHERE application_key IN (?,?) AND state='unknown'",
                                (key,other)).fetchall()
        if not facts:
            return holds
        target = endpoint(uri,aliases)
        if target[0] != netloc.removeprefix('www.'):
            return holds
        # Probe facts name the book needed to resolve their original visit.
        # Formal facts resolve through their registry in _fact_scope instead;
        # an unrelated consumer book must not block producer page screening.
        referenced_books=set()
        for fact in facts:
            if fact[0] in applied or fact[2]!='probe':continue
            refs=json.loads(fact[5])
            if len(refs)==1 and isinstance(refs[0],dict) and refs[0].get('ledger'):
                referenced_books.add(refs[0]['ledger'])
        with ExitStack() as stack:
            books = {}
            for path in (producer, producer.with_name('consumer-jobs.sqlite3')):
                if str(path) not in referenced_books:continue
                if path.is_file() and not path.is_symlink():
                    ledger = stack.enter_context(closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=30)))
                    ledger.row_factory = sqlite3.Row
                    if ledger.execute("SELECT 1 FROM sqlite_master WHERE name='batch_meta'").fetchone():
                        bound = ledger.execute("SELECT json_extract(config,'$.site_failure_guard') FROM batch_meta WHERE id=1").fetchone()
                        if bound and json.loads(bound[0] or 'null') == self.binding:
                            books[str(path)] = ledger
            # Count scope and totals from this same immutable fact snapshot.
            # Earlier returns omit these keys so the caller retains whole-site
            # protection when no endpoint scope can be established.
            holds.update(unknown_total=0, unknown_effective=0, whole_unknowns=0)
            for fact in facts:
                own_key = fact[1] == key
                holds['unknown_total'] += int(own_key)
                if fact[0] in applied:
                    continue
                holds['unknown_effective'] += int(own_key)
                owner = self._fact_scope(fact, books, str(producer))
                if not owner or endpoint(owner.get('site_uri') or owner['uri'], aliases)[0] != urlsplit(fact[1]).netloc.removeprefix('www.'):
                    holds['whole_unknowns'] += int(own_key)
                    continue
                same_page = endpoint(owner['uri'], aliases) == target
                if owner.get('candidate_id'):
                    holds['tasks'] += int(own_key)
                    # A plain URL is a read-only request. Executing a task supplies
                    # its stable candidate ID, including when claiming it again.
                    if not owner.get('focus_effect_accounted') and (candidate_id == owner['candidate_id'] or (
                            isinstance(application, dict) and not candidate_id and
                            (application.get('task_id') == owner['task_id'] or same_page))):
                        holds['matching_tasks'].append(fact[0])
                else:
                    holds['pages'] += int(own_key)
                    holds['closed_entries'] += int(own_key and bool(owner.get('closed_entry')))
                    if same_page:
                        holds['matching_pages'].append(fact[0])
        return holds

    def append_reassessment(self, identity, *, responsibility, reason, evidence):
        """Append evidence only. Original counts and stop/hold decisions remain binding."""
        from .planning import verify_evidence
        if responsibility not in ('site','model','configuration','interface','collector','unknown') or not reason.strip():
            raise ValueError('Explicit responsibility and reason required')
        if not evidence:raise ValueError('Reassessment evidence required')
        verify_evidence(evidence)
        with self.connect(True) as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT * FROM site_executions WHERE execution_id=?',(identity,)).fetchone()
            if not row:raise ValueError('Original execution not found')
            original=self._execution_fact(row)
            value={'original':original,'responsibility':responsibility,'reason':reason,'evidence':evidence,
                   'changes_stop_decision':False}
            key=object_sha256(value)
            con.execute('CREATE TABLE IF NOT EXISTS site_reassessments (id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, receipt TEXT NOT NULL)')
            con.execute('INSERT OR IGNORE INTO site_reassessments VALUES(?,?,?)',(key,identity,canonical(value)))
            con.commit()
        return value

    def apply_reassessments(self, application, authorization):
        """Apply an explicit operational decision after evidenced review; never auto-unstop."""
        from .planning import verify_evidence
        verify_evidence([authorization]);decision=load_json(authorization['path'])
        key=application_key(application,self.binding.get('application_registry'))
        if (decision.get('action')!='apply_evidenced_failure_reassessments' or decision.get('application_key')!=key
                or decision.get('campaign_id')!=self.binding['campaign_id'] or not decision.get('user_instruction')
                or not isinstance(decision.get('execution_ids'),list) or not decision['execution_ids']
                or len(set(decision['execution_ids']))!=len(decision['execution_ids'])):
            raise ValueError('Explicit original-campaign reassessment authorization required')
        reviews=[]
        with self.connect(True) as con:
            con.execute('BEGIN IMMEDIATE')
            for identity in decision['execution_ids']:
                original=con.execute('SELECT * FROM site_executions WHERE execution_id=? AND application_key=?',(identity,key)).fetchone()
                if not original:raise ValueError('Original execution required')
                if original[3]=='unknown':
                    reconciled=decision.get('reconciliation_proofs',{}).get(identity)
                    if reconciled is not None:
                        self._verify_reconciled_interruption(original, reconciled)
                    else:
                        self._verify_closed_visit(original, decision.get('visit_proofs',{}).get(identity))
                elif original[3]!='failed':raise ValueError('Original failure or proved closed visit required')
                rows=con.execute('SELECT receipt FROM site_reassessments WHERE execution_id=?',(identity,)).fetchall()
                values=[json.loads(row[0]) for row in rows]
                if not values or len({v['responsibility'] for v in values})!=1 or values[0]['responsibility'] not in ('model','configuration','interface','collector'):
                    raise ValueError('Unambiguous evidenced engineering responsibility required')
                for value in values:
                    verify_evidence(value['evidence'])
                    if value['original']!=self._execution_fact(original):raise ValueError('Original failure changed')
                reviews.extend(values)
            value={'application_key':key,'authorization':authorization,'reviews':reviews,'execution_ids':sorted(decision['execution_ids'])}
            con.execute('CREATE TABLE IF NOT EXISTS site_reassessment_decisions(id TEXT PRIMARY KEY, application_key TEXT NOT NULL, receipt TEXT NOT NULL)')
            con.execute('INSERT OR IGNORE INTO site_reassessment_decisions VALUES(?,?,?)',(object_sha256(value),key,canonical(value)))
            con.commit()
        return self.status(application)

    @staticmethod
    def _verify_reconciled_interruption(original, proof):
        """Release an interrupted-unknown only through the original books.

        The production attempt must carry an explicit m4_events
        'attempt_reconciled' receipt from interrupted to an engineering
        responsibility, the registry row must already hold that class, and
        the receipt's controller terminal must prove zero dispatched actions.
        Failure counts are never cleared by this route.
        """
        from .planning import verify_evidence
        if not isinstance(proof, dict):
            raise ValueError('Reconciliation proof required')
        verify_evidence([proof['terminal']])
        usage = json.loads(original[6])
        registry = proof.get('registry') or next(
            (ref.get('registry') for ref in usage if isinstance(ref, dict) and ref.get('registry')), None)
        attempt = proof.get('attempt_id') or next(
            (ref.get('attempt_id') for ref in usage if isinstance(ref, dict) and ref.get('attempt_id')), None)
        if not registry or not attempt:
            raise ValueError('Original usage references lack the registry attempt identity')
        terminal = load_json(proof['terminal']['path'])
        zero_dispatch = (terminal.get('used') or {}).get('max_actions') == 0
        sealed_react = False
        if terminal.get('protocol') in SEALED_REACT_SESSION_PROTOCOLS:
            # A react interruption may carry fully evidenced dispatched actions:
            # every trajectory row has a proven after observation and the raw
            # receipt seals the whole journal by SHA. The only remaining
            # unknown is the retained model request itself.
            from .batch_core import file_sha
            raw_dir = Path(proof['terminal']['path']).parent
            receipt_path = raw_dir / 'raw-receipt.json'
            if receipt_path.is_file():
                receipt = load_json(receipt_path)
                rows = [json.loads(line) for line in
                        (raw_dir / 'trajectory.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
                sealed_react = (receipt.get('protocol') in SEALED_REACT_SESSION_PROTOCOLS
                                and terminal.get('unknown') is True
                                and receipt.get('files_sha256', {}).get('terminal.json')
                                    == file_sha(raw_dir / 'terminal.json')
                                and receipt.get('files_sha256', {}).get('trajectory.jsonl')
                                    == file_sha(raw_dir / 'trajectory.jsonl')
                                and all(row.get('effective') and row.get('after_observation_id') for row in rows))
        if not ((terminal.get('kind') == 'terminal' and zero_dispatch) or sealed_react):
            raise ValueError('Terminal evidence does not prove zero dispatched actions')
        engineering = ('program', 'configuration', 'model', 'interface', 'collector')
        with closing(sqlite3.connect(Path(registry).resolve().as_uri() + '?mode=ro', uri=True)) as con:
            con.row_factory = sqlite3.Row
            row = con.execute('SELECT status,failure_class FROM m4_attempts WHERE attempt_id=?', (attempt,)).fetchone()
            if not row or row['status'] != 'rejected' or row['failure_class'] not in engineering:
                raise ValueError('Registry attempt was not reconciled to an engineering responsibility')
            events = [json.loads(r[0]) for r in con.execute(
                "SELECT payload_json FROM m4_events WHERE event_type='attempt_reconciled' AND attempt_id=?", (attempt,))]
        terminal_path = str(Path(proof['terminal']['path']).resolve())
        if not any(item.get('from') == 'interrupted' and item.get('to') == row['failure_class']
                   and str(Path(item.get('evidence', '')).resolve()) == terminal_path for item in events):
            raise ValueError('No original reconciliation receipt binds this terminal evidence')

    @staticmethod
    def _verify_closed_visit(original, proof):
        """Only resolve attribution of a known failed, zero-model visit.

        A model UNKNOWN, interrupted/reserved visit or a transport error can
        never be released through this route.
        """
        from .batch_core import BatchLedger
        from .planning import verify_evidence
        if not isinstance(proof,dict):raise ValueError('Closed visit proof required')
        verify_evidence([proof['diagnostic']])
        diagnostic=load_json(proof['diagnostic']['path'])
        ledger=Path(proof['ledger']).resolve()
        with closing(sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True)) as con:
            con.row_factory=sqlite3.Row
            row=con.execute('SELECT * FROM top_level_visits WHERE id=?',(proof['visit_id'],)).fetchone()
            if not row:raise ValueError('Original visit missing')
            row=dict(row);row['metrics']=json.loads(row['metrics'] or '{}')
            requests=con.execute('SELECT COUNT(*) FROM model_requests WHERE job_id=?',(row['job_id'],)).fetchone()[0]
        usage=json.loads(original[6])
        if (row['state']!='failed' or row['finished_at'] is None or requests or
            not isinstance(row['response_status'],int) or not 200<=row['response_status']<400 or
            diagnostic.get('visit_id')!=row['id'] or diagnostic.get('error_message')!=row['error_message'] or
            not any(token in row['error_message'] for token in ('ReferenceError:', 'SyntaxError:')) or
            not any(ref.get('visit_id')==row['id'] and ref.get('ledger')==str(ledger) for ref in usage) or
            proof.get('visit_sha256')!=object_sha256(row)):
            raise ValueError('Only evidenced observer fault in finished zero-model visit may resolve attribution')

    @staticmethod
    def _success_schema(con):
        con.execute('CREATE TABLE IF NOT EXISTS site_successes ('
                    'fact_id TEXT PRIMARY KEY,application_key TEXT NOT NULL,fact_json TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS site_success_verifications ('
                    'fact_id TEXT PRIMARY KEY,report_reference_json TEXT NOT NULL,verified_at REAL NOT NULL)')

    @staticmethod
    def _has_successes(con):
        return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='site_successes'").fetchone() is not None

    @staticmethod
    def _execution_fact(row):
        identity, app, stage, state, reason, evidence, usage, recorded = row
        evidence, usage = json.loads(evidence), json.loads(usage)
        if (len(evidence) == 1 and isinstance(evidence[0], dict)
                and set(evidence[0]) == {'portable_execution_fact'}):
            return evidence[0]['portable_execution_fact']
        source_ids = {str(ref['attempt_id' if stage == 'formal' else 'job_id']) for ref in usage
                      if isinstance(ref, dict) and ref.get('attempt_id' if stage == 'formal' else 'job_id')}
        key = stage + ':' + next(iter(source_ids)) if len(source_ids) == 1 else identity
        digests = sorted({ref['sha256'] for ref in evidence if isinstance(ref, dict)
                          and isinstance(ref.get('sha256'), str) and len(ref['sha256']) == 64})
        return {'fact_id': identity, 'execution_key': key, 'application_key': app, 'stage': stage,
                'state': state, 'reason': reason, 'evidence_sha256': digests,
                'evidence_binding_sha256': object_sha256(evidence), 'usage_binding_sha256': object_sha256(usage),
                'recorded_at': recorded}

    def export_facts(self):
        """Portable immutable facts; local paths are excluded from their identity.

        application_states is advisory. Receivers must import the facts and
        recompute status; imported success claims never grant local QC PASS.
        """
        with self.connect() as con:
            con.execute('BEGIN')
            executions = [self._execution_fact(row) for row in con.execute(
                'SELECT execution_id,application_key,stage,state,reason,evidence_json,usage_refs_json,recorded_at '
                'FROM site_executions ORDER BY execution_id')]
            successes = [json.loads(row[0]) for row in con.execute('SELECT fact_json FROM site_successes ORDER BY fact_id')] if self._has_successes(con) else []
        for fact in executions:
            self._validate_fact(fact)
        for fact in successes:
            self._validate_fact(fact, True)
        core = {'schema_version': self.facts_schema,
                'campaign_id': self.binding['campaign_id'], 'formal_since': self.binding['formal_since'],
                'failure_limit': self.failure_limit, 'executions': executions, 'successes': successes}
        apps = sorted({row['application_key'] for row in executions + successes})
        return {**core, 'facts_sha256': object_sha256(core),
                'application_states': [self.status('https:' + app) for app in apps]}

    @staticmethod
    def _validate_fact(fact, success=False):
        import math
        if not isinstance(fact, dict):
            raise ValueError('Portable site fact must be an object')
        shared = {'fact_id', 'application_key', 'recorded_at'}
        fields = (shared | {'sample_id', 'attempt_id', 'report_sha256', 'sample_files_sha256', 'verification'}
                  if success else shared | {'execution_key', 'stage', 'state', 'reason', 'evidence_sha256',
                                            'evidence_binding_sha256', 'usage_binding_sha256'})
        if set(fact) != fields or any(not isinstance(fact.get(key), str) or not fact[key].strip()
                                     for key in fields - {'recorded_at', 'evidence_sha256', 'sample_files_sha256'}):
            raise ValueError('Portable site fact fields are incomplete or unsupported')
        if (application_key('https:' + fact['application_key']) != fact['application_key']
                or type(fact['recorded_at']) not in (int, float) or not math.isfinite(fact['recorded_at'])
                or fact['recorded_at'] <= 0):
            raise ValueError('Portable fact application/time is invalid')
        def digest(value):
            return isinstance(value, str) and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)
        if success:
            if (fact['verification'] != 'source-bound-independent-qc-pass'
                    or not digest(fact['report_sha256']) or not isinstance(fact['sample_files_sha256'], dict)
                    or not fact['sample_files_sha256'] or not all(digest(value) for value in fact['sample_files_sha256'].values())
                    or any(not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts
                           for name in fact['sample_files_sha256'])):
                raise ValueError('Portable success must retain original QC and saved-file bindings')
        elif (fact['stage'] not in ('probe', 'observation', 'formal') or fact['state'] not in ('failed', 'unknown')
              or not isinstance(fact['evidence_sha256'], list) or not all(digest(x) for x in fact['evidence_sha256'])
              or not digest(fact['evidence_binding_sha256']) or not digest(fact['usage_binding_sha256'])):
            raise ValueError('Portable execution outcome/evidence is invalid')

    def import_facts(self, payload):
        """Atomic, idempotent merge; neither reclassify nor reset original facts."""
        keys = ('schema_version', 'campaign_id', 'formal_since', 'failure_limit', 'executions', 'successes')
        if (not isinstance(payload, dict) or not set(keys).issubset(payload)
                or set(payload) - set(keys) - {'facts_sha256', 'application_states'}):
            raise ValueError('Unsupported portable site ledger fields')
        core = {key: payload.get(key) for key in keys}
        if (core['schema_version'] != self.facts_schema
                or core['campaign_id'] != self.binding['campaign_id']
                or core['formal_since'] != self.binding['formal_since'] or core['failure_limit'] != self.failure_limit
                or not isinstance(core['executions'], list) or not isinstance(core['successes'], list)
                or payload.get('facts_sha256') != object_sha256(core)):
            raise ValueError('Portable ledger campaign/cutoff/policy/hash changed; no implicit new round')
        incoming = {}
        for success, facts in ((False, core['executions']), (True, core['successes'])):
            for fact in facts:
                self._validate_fact(fact, success)
                if fact['fact_id'] in incoming:
                    raise ValueError('Duplicate portable fact identity')
                incoming[fact['fact_id']] = (success, fact)
        added = 0
        with self.connect(True) as con:
            con.execute('BEGIN IMMEDIATE')
            self._success_schema(con)
            existing = {row[0]: self._execution_fact(row) for row in con.execute(
                'SELECT execution_id,application_key,stage,state,reason,evidence_json,usage_refs_json,recorded_at FROM site_executions')}
            existing.update({identity: json.loads(body) for identity, body in con.execute('SELECT fact_id,fact_json FROM site_successes')})
            # Validate the entire import before adding any fact.
            logical = {fact['execution_key']: identity for identity, fact in existing.items() if 'execution_key' in fact}
            for identity, (_, fact) in incoming.items():
                if identity in existing and existing[identity] != fact:
                    raise ValueError('Original execution/success identity cannot be reclassified or changed')
                if 'execution_key' in fact:
                    key = fact['execution_key']
                    if key in logical and logical[key] != identity:
                        raise ValueError('Portable logical execution has conflicting fact aliases')
                    logical[key] = identity
            for identity, (success, fact) in incoming.items():
                if identity in existing:
                    continue
                if success:
                    con.execute('INSERT INTO site_successes VALUES(?,?,?)',
                                (identity, fact['application_key'], canonical(fact)))
                    # No local verification row: this is only an immutable
                    # source claim until actual local QC artifacts are checked.
                else:
                    con.execute('INSERT INTO site_executions VALUES(?,?,?,?,?,?,?,?)',
                        (identity, fact['application_key'], fact['stage'], fact['state'], fact['reason'],
                         canonical([{'portable_execution_fact': fact}]), canonical([]), fact['recorded_at']))
                added += 1
            con.commit()
        return {'imported_facts': added, 'existing_facts': len(incoming) - added,
                'local_QC_approval_granted': False, 'campaign_id': self.binding['campaign_id']}

    def sync_successes(self, registry, campaign_id):
        """Register only already-committed, independently bound local QC passes."""
        from .runtime import _bound_quality_report
        from .collect_runtime import verify_committed_samples, sample_hashes
        registry = Path(registry).resolve()
        with closing(sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True)) as con:
            rows = con.execute('SELECT a.attempt_id,a.sample_id,a.status,a.evidence_json,t.task_json,'
                'r.evidence_json,r.at FROM m4_attempts a JOIN m4_tasks t ON a.task_key=t.task_key '
                'JOIN m4_reviews r ON r.sample_id=a.sample_id '
                "WHERE a.campaign_id=? AND a.started_at>=? AND r.decision='pass'", (campaign_id, self.binding['formal_since'])).fetchall()
        for attempt_id, sid, outcome, saved_refs, task, qc_refs, at in rows:
            identity = 'qc-success:' + object_sha256([self.binding['campaign_id'], attempt_id, sid])
            with self.connect() as con:
                if self._has_successes(con) and con.execute('SELECT 1 FROM site_success_verifications WHERE fact_id=?', (identity,)).fetchone():
                    continue  # An immutable historical success, not a fresh release approval.
            if outcome != 'collected_pending_review':
                raise ValueError('A pending/failed capture cannot become a valid site success')
            evidence = json.loads(qc_refs)
            report, reference = _bound_quality_report(evidence)
            matches = [row for row in report['samples'] if row['sample_id'] == sid]
            if len(matches) != 1 or matches[0].get('status') != 'PASS':
                raise ValueError('Site success requires the exact independent QC sample PASS')
            refs = json.loads(saved_refs)
            receipts = [Path(ref['path']) for ref in refs if Path(ref.get('path', '')).name == 'saved_sample.json']
            if len(receipts) != 1:
                raise ValueError('Site success requires the original committed capture receipt')
            receipt = load_json(receipts[0])
            source = receipts[0].parents[2]
            verify_committed_samples(source, [{'attempt_id': attempt_id, 'sample_id': sid,
                'status': outcome, 'evidence': refs}])
            if sample_hashes(Path(report['dataset']) / 'samples' / sid) != receipt['sample_files_sha256']:
                raise ValueError('QC success files differ from the original committed capture')
            fact = {'fact_id': identity, 'application_key': application_key(json.loads(task), self.binding.get('application_registry')),
                    'sample_id': sid, 'attempt_id': attempt_id, 'report_sha256': reference['sha256'],
                    'sample_files_sha256': receipt['sample_files_sha256'],
                    'verification': 'source-bound-independent-qc-pass', 'recorded_at': at}
            self._validate_fact(fact, True)
            with self.connect(True) as con:
                con.execute('BEGIN IMMEDIATE'); self._success_schema(con)
                old = con.execute('SELECT fact_json FROM site_successes WHERE fact_id=?', (identity,)).fetchone()
                if old and json.loads(old[0]) != fact:
                    raise ValueError('Original QC success fact cannot be changed')
                con.execute('INSERT OR IGNORE INTO site_successes VALUES(?,?,?)', (identity, fact['application_key'], canonical(fact)))
                con.execute('INSERT OR IGNORE INTO site_success_verifications VALUES(?,?,?)',
                            (identity, canonical(reference), time.time()))
                con.commit()
        return {'source_reviews_consulted': len(rows), 'local_QC_approval_granted': False}

    def status(self, application, *, candidate_id=None):
        key = application_key(application, self.binding.get('application_registry'))
        with self.connect() as con:
            counts = dict(con.execute('SELECT state,COUNT(*) FROM site_executions WHERE application_key=? GROUP BY state', (key,)))
            successes = verified = 0
            if self._has_successes(con):
                successes = con.execute('SELECT COUNT(*) FROM site_successes WHERE application_key=?', (key,)).fetchone()[0]
                verified = con.execute('SELECT COUNT(*) FROM site_successes s JOIN site_success_verifications v ON s.fact_id=v.fact_id WHERE s.application_key=?', (key,)).fetchone()[0]
        failed, unknown = counts.get('failed', 0), counts.get('unknown', 0)
        unavailable = failed >= LIMIT and not verified
        state = 'unknown_hold' if unknown else 'unavailable' if unavailable else 'succeeded' if verified else 'available'
        reassessments=[]
        with self.connect() as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='site_reassessments'").fetchone():
                reassessments=[json.loads(row[0]) for row in con.execute(
                    'SELECT r.receipt FROM site_reassessments r JOIN site_executions e ON r.execution_id=e.execution_id WHERE e.application_key=? ORDER BY r.id',(key,))]
        from .planning import verify_evidence
        reviewed={}
        for row in reassessments:
            _verify_persisted_reassessment_evidence(row['evidence'])
            reviewed.setdefault(row['original']['fact_id'],set()).add(row['responsibility'])
        failed_ids={r['original']['fact_id'] for r in reassessments if r['original']['state']=='failed'}
        unknown_ids={r['original']['fact_id'] for r in reassessments if r['original']['state']=='unknown'}
        adjusted=failed-sum(identity in failed_ids and len(opinions)==1 and next(iter(opinions)) in ('model','configuration','interface','collector') for identity,opinions in reviewed.items())
        applied=set()
        with self.connect() as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='site_reassessment_decisions'").fetchone():
                for (raw,) in con.execute('SELECT receipt FROM site_reassessment_decisions WHERE application_key=?',(key,)):
                    decision=json.loads(raw);verify_evidence([decision['authorization']])
                    for receipt in decision['reviews']:
                        if receipt not in reassessments:raise ValueError('Applied failure reassessment changed')
                    authorization=load_json(decision['authorization']['path'])
                    for identity in decision['execution_ids']:
                        if identity in unknown_ids:
                            original=con.execute('SELECT * FROM site_executions WHERE execution_id=?',(identity,)).fetchone()
                            reconciled=authorization.get('reconciliation_proofs',{}).get(identity)
                            if reconciled is not None:
                                self._verify_reconciled_interruption(original,reconciled)
                            else:
                                self._verify_closed_visit(original,authorization.get('visit_proofs',{}).get(identity))
                    applied.update(identity for identity in decision['execution_ids'] if len(reviewed.get(identity,set()))==1)
        effective=failed-len(applied & failed_ids)
        effective_unknown=unknown-len(applied & unknown_ids)
        scopes = self._project_holds(application,key,applied,candidate_id) if self.failure_limit is None else {}
        uri_holds = scopes.get('matching_pages',[])
        task_holds = scopes.get('matching_tasks',[])
        if 'unknown_total' in scopes:
            unknown = scopes['unknown_total']
            effective_unknown = scopes['unknown_effective']
        whole_unknown = scopes.get('whole_unknowns', effective_unknown - scopes.get('pages',0) - scopes.get('tasks',0))
        stopped=self.failure_limit is not None and effective>=self.failure_limit
        unavailable=stopped and not verified
        state='unknown_hold' if whole_unknown else 'task_hold' if task_holds else 'entry_uri_hold' if uri_holds else 'unavailable' if unavailable else 'succeeded' if verified else 'available'
        return {'application_key': key, 'failure_count': failed,'historical_stopped':self.failure_limit is not None and failed>=self.failure_limit,
                'effective_site_failure_count':effective,'explicitly_reassessed_executions':sorted(applied),'reassessment_count':len(reassessments),
                'reassessed_site_failure_count':max(0,adjusted),'reassessment_changes_dispatch':bool(applied), 'unknown_execution_count': unknown,
                'effective_unknown_execution_count':effective_unknown, 'failure_limit': self.failure_limit, 'qualified_success_count': verified,
                'source_reported_success_count': successes - verified, 'used': bool(failed or unknown or successes),
                'unavailable_before_first_valid': unavailable, 'state': state,
                'round_id': self.binding['campaign_id'], 'automatic_round_reentry': False,
                **({'closed_entry_uri_unknowns':scopes['closed_entries'],'page_scoped_unknowns':scopes['pages'],
                    'task_scoped_unknowns':scopes['tasks'],'matching_entry_uri_holds':uri_holds,
                    'matching_task_holds':task_holds,'whole_application_unknowns':whole_unknown} if scopes and (unknown or uri_holds or task_holds) else {}),
                'stopped': stopped, 'dispatch_blocked': stopped or bool(whole_unknown or uri_holds or task_holds)}

    def guard(self, application, *, candidate_id=None):
        state = self.status(application,candidate_id=candidate_id)
        if state['dispatch_blocked']:
            reason = {'entry_uri_hold':'Original page request unresolved','task_hold':'Original candidate task unresolved'}.get(state['state'],'Whole application dispatch stopped')
            raise SiteStopped(reason + ': ' + canonical(state))
        return state

    def sync_formal(self, registry, campaign_id):
        """Merge only committed new failures, including other pages/scopes."""
        registry = Path(registry).resolve()
        with closing(sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True)) as con:
            rows = con.execute('SELECT a.attempt_id,a.status,a.failure_class,a.root_cause,a.evidence_json,t.task_json '
                'FROM m4_attempts a JOIN m4_tasks t ON a.task_key=t.task_key '
                'WHERE a.campaign_id=? AND a.started_at>=? AND a.finished_at IS NOT NULL '
                "AND a.status IN ('rejected','interrupted')", (campaign_id, self.binding['formal_since'])).fetchall()
        existing = {fact['execution_key']: fact for fact in self.export_facts()['executions']}
        for identity, status, failure_class, reason, evidence, task in rows:
            # Existing historical entries remain unchanged; new program faults
            # remain in RuntimeStore without creating a site failure.
            if failure_class in ('program','configuration','model','interface','collector'):
                continue
            state = 'unknown' if status == 'interrupted' or failure_class == 'interrupted' else 'failed'
            app = application_key(json.loads(task)); key = 'formal:' + identity
            if key in existing:
                old = existing[key]
                from .request_quarantine import accounted_closed_execution
                if (failure_class=='interrupted' and status=='rejected'
                        and (old['application_key'],old['stage'],old['state'],old['reason'])==(app,'formal',state,reason or status)
                        and set(old['evidence_sha256']) <= {r['sha256'] for r in json.loads(evidence) if isinstance(r,dict) and 'sha256' in r}
                        and accounted_closed_execution(registry,identity)):
                    continue  # Keep the original site fact and its original evidence binding.
                if ((old['application_key'], old['stage'], old['state'], old['reason']) != (app, 'formal', state, reason or status)
                        or json.loads(evidence) and old['evidence_binding_sha256'] != object_sha256(json.loads(evidence))):
                    raise ValueError('Imported formal execution cannot be reclassified on this machine')
                continue
            refs = [{'registry': str(registry), 'attempt_id': identity, 'usage': 'UNKNOWN', 'cost': 'UNKNOWN'}]
            self.record(json.loads(task), 'formal:' + object_sha256({'attempt_id': identity}), stage='formal',
                state=state, reason=reason or status, real_execution=True,
                evidence=json.loads(evidence) or refs, usage_refs=refs)


def model_usage_refs(ledger, job_id):
    with ledger.connect() as con:
        rows = con.execute('SELECT id,state,usage,cost,reserved_cost FROM model_requests WHERE job_id=? ORDER BY id', (job_id,)).fetchall()
    return [{'ledger': str(ledger.path), 'job_id': job_id, 'request_id': row[0], 'state': row[1],
             'usage': json.loads(row[2]) if row[2] else 'UNKNOWN', 'cost': row[3] if row[3] is not None else 'UNKNOWN',
             'reserved_cost_not_actual_debit': row[4]} for row in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'status', 'export', 'import'))
    parser.add_argument('--ledger', required=True); parser.add_argument('--campaign-id', required=True)
    parser.add_argument('--formal-since', type=float, required=True)
    parser.add_argument('--seed-policy', type=Path); parser.add_argument('--source-root', type=Path)
    parser.add_argument('--application')
    parser.add_argument('--facts', type=Path, help='Portable immutable facts to import')
    parser.add_argument('--output', type=Path, help='Fresh portable export artifact; otherwise print JSON')
    args = parser.parse_args(argv)
    binding = {key: getattr(args, key) for key in ('ledger', 'campaign_id', 'formal_since')}
    store = SiteFailureStore.initialize(binding, seed_policy=args.seed_policy, source_root=args.source_root) if args.command == 'init' else SiteFailureStore(binding)
    if args.command == 'export':
        result = store.export_facts()
        if args.output:
            from .batch_core import save_json
            save_json(args.output, result)
    elif args.command == 'import':
        if args.facts is None:
            parser.error('import requires --facts')
        result = store.import_facts(load_json(args.facts))
    else:
        result = store.status(args.application) if args.application else {'binding': store.binding, 'failure_limit': store.failure_limit}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
