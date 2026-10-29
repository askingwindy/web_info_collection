"""Shared job and expenditure ledger. This never allocates collection IDs.

One frozen configuration per run/database; reservations survive crashes. Unknown
provider outcomes keep their full reservation and cannot be automatically resent.
Amounts are integer millionths of the configured currency, never floats.
"""
from contextlib import contextmanager
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid

from .planning import canonical, object_sha256


class BudgetStop(ValueError):
    pass


class OutcomeUnknown(ValueError):
    responsibility='model'


class ModelRateWait(ValueError):
    def __init__(self, seconds):
        self.seconds=seconds
        super().__init__('Model dispatch rate limit')


class VisitRateWait(ValueError):
    def __init__(self, seconds):
        self.seconds = seconds
        super().__init__('Top-level visit domain rate limit')


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    """Atomic, recoverable output. Existing different bytes are never replaced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n'
    if path.exists():
        if path.read_text() != data:
            raise ValueError('Refuse to replace different artifact: ' + str(path))
        return
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        stream.write(data)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    try:
        import os
        os.link(temporary, path)
    except FileExistsError:
        if path.read_text() != data:
            raise ValueError('Conflicting artifact publication')
    finally:
        temporary.unlink()


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(name + ' must be an integer >= ' + str(minimum))


def validate_config(value, *, credentials=False, require_model=False):
    """Validate only dependencies of the configured branches.

    ``model: null`` is an explicit disabled branch, in either real or synthetic
    mode. It has no rates/credentials/currency and cannot reserve model calls.
    Existing frozen model configurations retain their exact representation.
    """
    import os
    from urllib.parse import urlsplit
    if (not isinstance(value, dict) or not {'schema_version', 'run_id', 'mode', 'budget', 'model'} <= set(value)
            or set(value) - {'schema_version', 'run_id', 'mode', 'budget', 'model', 'site_failure_guard'}):
        raise ValueError('Expected exact webcollect-batch-config-1 fields')
    if 'site_failure_guard' in value:
        from .site_failure_stop import validate_binding
        validate_binding(value['site_failure_guard'])
    if value['schema_version'] != 'webcollect-batch-config-1' or value['mode'] not in ('real', 'synthetic'):
        raise ValueError('Invalid batch schema/mode')
    if not isinstance(value['run_id'], str) or not value['run_id'].strip():
        raise ValueError('run_id required')
    budget = value['budget']
    runtime_fields = {'max_discovery_candidates', 'max_probe_pages', 'max_run_seconds',
                      'max_concurrent_jobs', 'min_domain_interval_seconds', 'lease_seconds'}
    model_fields = {'max_model_requests', 'max_reserved_tokens', 'max_model_cost_micros',
                    'currency', 'min_model_interval_seconds'}
    model_enabled = value['model'] is not None
    fields = runtime_fields | (model_fields if model_enabled else {'max_job_attempts'})
    if not isinstance(budget, dict) or not fields <= set(budget) or set(budget) - fields - {'max_job_attempts', 'max_top_level_visits', 'cost_control'}:
        raise ValueError('Explicit independent budget fields required: ' + ', '.join(sorted(fields)))
    cost_control = budget.get('cost_control', 'capped')
    if cost_control not in ('capped', 'observe_only'):
        raise ValueError('cost_control must be capped or observe_only')
    if 'cost_control' in budget and not model_enabled:
        raise ValueError('cost_control requires the explicit model branch')
    if cost_control == 'observe_only' and budget['max_model_cost_micros'] is not None:
        raise ValueError('observe_only requires explicit max_model_cost_micros:null')
    for key in fields - {'currency'}:
        if key == 'max_model_cost_micros' and cost_control == 'observe_only':
            continue
        _integer(budget[key], key, 0 if key=='min_model_interval_seconds' or key.startswith('max_') and key not in
                 ('max_run_seconds', 'max_concurrent_jobs') else 1)
    if 'max_job_attempts' in budget:
        _integer(budget['max_job_attempts'], 'max_job_attempts', 1)
    if 'max_top_level_visits' in budget:
        _integer(budget['max_top_level_visits'], 'max_top_level_visits')
    if model_enabled and budget['min_model_interval_seconds']>30:
        raise ValueError('Model interval must be <=30 seconds; use a smaller worker concurrency for lower throughput')
    if budget['lease_seconds'] < 5:
        raise ValueError('lease_seconds >= 5 required')
    if not model_enabled:
        if require_model:
            raise ValueError('Model branch disabled (model:null); this operation requires an explicit model configuration')
        return deepcopy(value)
    if not isinstance(budget['currency'], str) or not budget['currency'].strip():
        raise ValueError('Explicit model billing currency required')
    model = value['model']
    fields = {'provider', 'model', 'endpoint', 'api_key_env', 'timeout_seconds', 'reserve_input_tokens',
              'max_completion_tokens', 'max_images', 'reserve_cost_micros', 'rates'}
    capability_fields = {'supports_vision', 'image_tokens_per_image', 'request_overhead_tokens'}
    optional_fields = capability_fields | {'image_encoding', 'reasoning_effort', 'api_key_file'}
    if not isinstance(model, dict) or not fields <= set(model) or set(model) - fields - optional_fields:
        raise ValueError('Explicit model adapter fields required: ' + ', '.join(sorted(fields)))
    if model['provider'] not in ('synthetic', 'chat-completions', 'deepseek', 'glm', 'ark'):
        raise ValueError('Unsupported model provider')
    if 'api_key_file' in model and (value['mode'] != 'real'
            or not isinstance(model['api_key_file'], str) or not Path(model['api_key_file']).is_absolute()):
        raise ValueError('Model credential file must be an explicit absolute real-mode path')
    if set(model) & capability_fields and not capability_fields <= set(model):
        raise ValueError('Vision and request token allowance fields must be supplied together')
    if model['provider'] in ('deepseek', 'glm', 'ark') and not capability_fields <= set(model):
        raise ValueError('Provider requires explicit vision and request token allowances')
    if 'supports_vision' in model and type(model['supports_vision']) is not bool:
        raise ValueError('supports_vision must be an explicit boolean')
    if 'image_tokens_per_image' in model:
        _integer(model['image_tokens_per_image'], 'image_tokens_per_image')
        if model.get('supports_vision', True) != (model['image_tokens_per_image'] > 0):
            raise ValueError('Vision needs positive image tokens; text-only models require zero image tokens')
    if 'request_overhead_tokens' in model:
        _integer(model['request_overhead_tokens'], 'request_overhead_tokens', 1)
    if 'image_encoding' in model:
        if model['provider'] != 'glm' or model['image_encoding'] not in ('raw_base64', 'data_url'):
            raise ValueError('image_encoding must be raw_base64 or data_url for the GLM provider')
    if 'reasoning_effort' in model:
        if model['provider'] not in ('glm', 'deepseek', 'ark') or model['reasoning_effort'] not in ('low', 'high', 'max'):
            raise ValueError('reasoning_effort must be low, high or max for GLM/DeepSeek/Ark')
    if (value['mode'] == 'synthetic') != (model['provider'] == 'synthetic'):
        raise ValueError('Synthetic and real modes cannot share model results')
    for key in ('timeout_seconds', 'reserve_input_tokens', 'max_completion_tokens', 'max_images'):
        _integer(model[key], key, 1)
    if model['timeout_seconds'] + 5 >= budget['lease_seconds']:
        raise ValueError('Lease must exceed model timeout by more than 5 seconds')
    _integer(model['reserve_cost_micros'], 'reserve_cost_micros')
    rates = model['rates']
    if not isinstance(rates, dict) or set(rates) != {'version', 'source', 'input', 'cached_input', 'output'}:
        raise ValueError('Versioned rates in micros per million tokens required')
    for key in ('input', 'cached_input', 'output'):
        _integer(rates[key], key)
    for key in ('version', 'source'):
        if not isinstance(rates[key], str) or not rates[key].strip():
            raise ValueError('Rate version and source required')
    if not isinstance(model['model'], str) or not model['model'].strip():
        raise ValueError('Explicit model/version required')
    if model['provider'] == 'ark':
        # These are Ark model IDs, never aliases for the original providers.
        if model['model'] not in ('glm-5-3-flash-260828', 'deepseek-v4-1-flash-261017',
                                  'deepseek-v4-1-flash-economy-261017'):
            raise ValueError('Unsupported Ark model version')
        if model['endpoint'] != 'https://ark.cn-beijing.volces.com/api/v3/chat/completions':
            raise ValueError('Ark requires the Beijing data-plane Chat Completions endpoint')
        if model['max_completion_tokens'] > 65536:
            raise ValueError('Ark max_completion_tokens must be <=65536')
    if value['mode'] == 'real':
        endpoint = urlsplit(model['endpoint'])
        if (endpoint.scheme != 'https' or not endpoint.hostname or endpoint.username or endpoint.password
                or endpoint.query or endpoint.fragment):
            raise ValueError('Real model endpoint must be an explicit credential-free HTTPS URL')
        if (not isinstance(model['api_key_env'], str) or not model['api_key_env'].isidentifier()
                or (cost_control == 'capped' and not budget['max_model_cost_micros']) or not model['reserve_cost_micros']):
            raise ValueError('Real calls need credential environment name, nonzero reservation and an explicit cost-control mode')
        if not rates['input'] or not rates['output']:
            raise ValueError('Real calls need nonzero verified input/output rates')
        if budget['min_model_interval_seconds']<1:
            raise ValueError('Real model dispatch requires an explicit nonzero rate interval')
        if credentials:
            from .model_credentials import credential
            credential(model)
    minimum = (model['reserve_input_tokens'] * max(rates['input'], rates['cached_input']) +
               model['max_completion_tokens'] * rates['output'] + 999999) // 1_000_000
    if model['reserve_cost_micros'] < minimum:
        raise ValueError('Monetary reservation below configured conservative token ceiling')
    return deepcopy(value)


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class BatchLedger:
    def __init__(self, path, config, *, initialize=False):
        self.path = Path(path).resolve()
        self.config = validate_config(config)
        if initialize:
            if self.path.name == 'production-registry.sqlite3':
                raise ValueError('Job ledger must be separate from the production ID registry')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect(create=True) as con:
                con.executescript('''
                CREATE TABLE IF NOT EXISTS batch_meta (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL, started REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                  state TEXT NOT NULL, owner TEXT, lease REAL, attempts INTEGER NOT NULL DEFAULT 0,
                  created REAL NOT NULL, updated REAL NOT NULL, result TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS model_requests (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, purpose TEXT NOT NULL,
                  attempt INTEGER NOT NULL, state TEXT NOT NULL, reserved_tokens INTEGER NOT NULL, reserved_cost INTEGER NOT NULL,
                  started REAL NOT NULL, finished REAL, usage TEXT, cost INTEGER, response TEXT, error TEXT, request_json TEXT,
                  UNIQUE(job_id,purpose,attempt));
                CREATE TABLE IF NOT EXISTS resources (key TEXT PRIMARY KEY, kind TEXT NOT NULL, amount INTEGER NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS domain_dispatch (domain TEXT PRIMARY KEY, dispatched REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS batch_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS generated_task_index (signature TEXT PRIMARY KEY, job_id TEXT NOT NULL, task_json TEXT NOT NULL);
                ''')
                inserted = con.execute('INSERT OR IGNORE INTO batch_meta VALUES(1,?,?)', (canonical(self.config), time.time())).rowcount
                self._ensure_visit_schema(con, complete=bool(inserted))
                con.commit()
        with self.connect() as con:
            row = con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()
            if not row or json.loads(row[0]) != self.config:
                raise ValueError('Run configuration is frozen; resume cannot reset or enlarge its budget')

    def connect(self, create=False):
        con = sqlite3.connect(str(self.path) if create else self.path.as_uri() + '?mode=rw',
                              uri=not create, timeout=30, factory=ClosingConnection)
        con.row_factory = sqlite3.Row
        return con

    @contextmanager
    def transaction(self):
        con = self.connect()
        try:
            con.execute('BEGIN IMMEDIATE')
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def event(self, con, event, detail):
        con.execute('INSERT INTO batch_events(at,event,detail) VALUES(?,?,?)',
                    (time.time(), event, canonical(detail)))

    def _time_limit(self, con):
        start = con.execute('SELECT started FROM batch_meta').fetchone()[0]
        if time.time() - start >= self.config['budget']['max_run_seconds']:
            raise BudgetStop('max_run_seconds reached (resume retains original start)')

    def enqueue(self, kind, payload):
        identity = object_sha256({'kind': kind, 'payload': payload})
        with self.transaction() as con:
            con.execute('INSERT OR IGNORE INTO jobs(id,kind,payload,state,created,updated) VALUES(?,?,?,\'queued\',?,?)',
                        (identity, kind, canonical(payload), time.time(), time.time()))
        return identity

    def recover(self):
        with self.transaction() as con:
            rows = con.execute("SELECT * FROM jobs WHERE state='running' AND lease<?", (time.time(),)).fetchall()
            for row in rows:
                unknown = con.execute("SELECT id FROM model_requests WHERE job_id=? AND state='reserved'", (row['id'],)).fetchall()
                con.execute("UPDATE model_requests SET state='unknown',error='lease_expired_after_dispatch' WHERE job_id=? AND state='reserved'", (row['id'],))
                if con.execute("SELECT 1 FROM sqlite_master WHERE name='top_level_visits'").fetchone():
                    con.execute("UPDATE top_level_visits SET state='unknown',error_type='LeaseExpired',error_message='Dispatch reservation survived worker interruption; counted conservatively' WHERE job_id=? AND state='reserved_for_dispatch'",(row['id'],))
                con.execute('UPDATE jobs SET state=?,owner=NULL,lease=NULL,error=?,updated=? WHERE id=?',
                            ('review_required' if unknown or row['kind'] in ('collection','frozen-plan') else 'queued',
                             'Expired lease; unknown charge/collection side effects require reconciliation' if unknown or row['kind'] in ('collection','frozen-plan') else None,
                             time.time(), row['id']))
                self.event(con, 'lease_expired', {'job_id': row['id'], 'unknown_requests': len(unknown)})
        return len(rows)

    def claim(self, kind, *, job_id=None, domain=None):
        self.recover()
        with self.transaction() as con:
            self._time_limit(con)
            query = "SELECT * FROM jobs WHERE kind=? AND state='queued'"
            params = [kind]
            if job_id:
                query += ' AND id=?'; params.append(job_id)
            row = con.execute(query + ' ORDER BY created,id LIMIT 1', params).fetchone()
            if not row:
                return None
            attempt_cap = self.config['budget'].get('max_job_attempts')
            if attempt_cap is not None and row['attempts'] >= attempt_cap:
                con.execute("UPDATE jobs SET state='review_required',error=?,updated=? WHERE id=?",
                            ('max_job_attempts reached; original attempts retained', time.time(), row['id']))
                self.event(con, 'job_attempt_limit', {'job_id': row['id'], 'attempts': row['attempts'], 'limit': attempt_cap})
                return None
            running = con.execute("SELECT COUNT(*) FROM jobs WHERE state='running' AND kind!='frozen-plan'").fetchone()[0]
            if running >= self.config['budget']['max_concurrent_jobs']:
                raise BudgetStop('max_concurrent_jobs reached; queued work retained')
            if domain:
                last = con.execute('SELECT dispatched FROM domain_dispatch WHERE domain=?', (domain,)).fetchone()
                if last and time.time() - last[0] < self.config['budget']['min_domain_interval_seconds']:
                    raise BudgetStop('domain rate limit; queued work retained')
                con.execute('INSERT OR REPLACE INTO domain_dispatch VALUES(?,?)', (domain, time.time()))
            owner = uuid.uuid4().hex
            con.execute("UPDATE jobs SET state='running',owner=?,lease=?,attempts=attempts+1,updated=? WHERE id=?",
                        (owner, time.time() + self.config['budget']['lease_seconds'], time.time(), row['id']))
            self.event(con, 'job_claimed', {'job_id': row['id'], 'kind': kind})
            return {**dict(row), 'payload': json.loads(row['payload']), 'owner': owner}

    def _owned(self, con, job):
        row = con.execute('SELECT * FROM jobs WHERE id=?', (job['id'],)).fetchone()
        if not row or row['owner'] != job['owner'] or row['state'] != 'running' or row['lease'] < time.time():
            raise ValueError('Lost/expired job lease')

    def heartbeat(self, job):
        with self.transaction() as con:
            self._owned(con, job)
            self._time_limit(con)
            con.execute('UPDATE jobs SET lease=? WHERE id=?',
                        (time.time() + self.config['budget']['lease_seconds'], job['id']))

    def finish(self, job, state='done', result=None, error=None):
        if state not in ('done', 'failed', 'review_required', 'queued'):
            raise ValueError('Invalid job state')
        with self.transaction() as con:
            self._owned(con, job)
            con.execute('UPDATE jobs SET state=?,result=?,error=?,owner=NULL,lease=NULL,updated=? WHERE id=?',
                        (state, canonical(result) if result is not None else None, error, time.time(), job['id']))
            self.event(con, 'job_finished', {'job_id': job['id'], 'state': state})

    def get(self, job_id):
        with self.connect() as con:
            row = con.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise ValueError('Unknown job')
        result = dict(row)
        for key in ('payload', 'result'):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def consume(self, kind, key, amount=1):
        limits = {'discovery_candidates': 'max_discovery_candidates', 'probe_pages': 'max_probe_pages'}
        if kind not in limits:
            raise ValueError('Unknown resource kind')
        _integer(amount, 'resource amount', 1)
        with self.transaction() as con:
            self._time_limit(con)
            old = con.execute('SELECT kind,amount FROM resources WHERE key=?', (key,)).fetchone()
            if old:
                if tuple(old) != (kind, amount):
                    raise ValueError('Resource identity collision')
                return
            used = con.execute('SELECT COALESCE(SUM(amount),0) FROM resources WHERE kind=?', (kind,)).fetchone()[0]
            if used + amount > self.config['budget'][limits[kind]]:
                raise BudgetStop(limits[kind] + ' reached')
            con.execute('INSERT INTO resources VALUES(?,?,?,?)', (key, kind, amount, time.time()))

    @staticmethod
    def _ensure_visit_schema(con, *, complete=False):
        con.execute('''CREATE TABLE IF NOT EXISTS top_level_visits (
            id TEXT PRIMARY KEY, job_id TEXT NOT NULL, purpose TEXT NOT NULL,
            attempt_index INTEGER NOT NULL, target_uri TEXT NOT NULL, domain TEXT NOT NULL,
            dispatched_at REAL NOT NULL, finished_at REAL, state TEXT NOT NULL,
            response_status INTEGER, landed_uri TEXT, error_type TEXT, error_message TEXT, metrics TEXT)''')
        con.execute('''CREATE TABLE IF NOT EXISTS visit_accounting_meta (
            id INTEGER PRIMARY KEY CHECK(id=1), started REAL NOT NULL,
            history_complete INTEGER NOT NULL, prior_unique_pages INTEGER NOT NULL)''')
        prior = con.execute("SELECT COALESCE(SUM(amount),0) FROM resources WHERE kind='probe_pages'").fetchone()[0]
        con.execute('INSERT OR IGNORE INTO visit_accounting_meta VALUES(1,?,?,?)',
            (time.time(),int(complete or prior==0),prior))

    def remaining_seconds(self):
        with self.connect() as con:
            self._time_limit(con)
            return self.config['budget']['max_run_seconds'] - (time.time() - con.execute('SELECT started FROM batch_meta').fetchone()[0])

    def reserve_visit(self, job, target_uri, purpose, domain, *, timeout_seconds=20):
        """Count each dispatch, including failed/repeated visits; never cache-dedup.

        A crash between reservation and the socket call retains a conservative
        unknown attempt. Redirects/subresources are separately observed metrics.
        Unique page reservations remain in resources and are never rewritten.
        """
        if self.config['mode'] == 'real' and not self.config.get('site_failure_guard'):
            raise BudgetStop('Real website dispatch requires the original whole-site failure guard; no request sent')
        self.sync_visit_failures()
        if self.config.get('site_failure_guard'):
            from .site_failure_stop import SiteFailureStore
            SiteFailureStore(self.config['site_failure_guard']).guard(target_uri)
        with self.transaction() as con:
            self._owned(con, job); self._time_limit(con)
            self._ensure_visit_schema(con)
            if not con.execute('SELECT history_complete FROM visit_accounting_meta WHERE id=1').fetchone()[0]:
                raise BudgetStop('Legacy top-level visit history UNKNOWN; cannot enable a bounded dispatch from this ledger')
            used = con.execute('SELECT COUNT(*) FROM top_level_visits').fetchone()[0]
            maximum = self.config['budget'].get('max_top_level_visits', self.config['budget']['max_probe_pages'])
            if used >= maximum: raise BudgetStop('max_top_level_visits reached (failed/unknown attempts retained)')
            now = time.time()
            last = con.execute('SELECT dispatched FROM domain_dispatch WHERE domain=?', (domain,)).fetchone()
            delay = last[0] + self.config['budget']['min_domain_interval_seconds'] - now if last else 0
            remaining = self.config['budget']['max_run_seconds'] - (now - con.execute('SELECT started FROM batch_meta').fetchone()[0])
            if delay > 0:
                if delay >= remaining: raise BudgetStop('max_run_seconds: insufficient time for domain interval')
                raise VisitRateWait(delay)
            if remaining <= 0.05: raise BudgetStop('max_run_seconds: no dispatch time remaining')
            index = con.execute('SELECT COUNT(*)+1 FROM top_level_visits WHERE job_id=? AND purpose=?', (job['id'],purpose)).fetchone()[0]
            rid = uuid.uuid4().hex
            con.execute('INSERT INTO top_level_visits VALUES(?,?,?,?,?,?,?,NULL,?,NULL,NULL,NULL,NULL,NULL)',
                        (rid, job['id'], purpose, index, target_uri, domain, now, 'reserved_for_dispatch'))
            con.execute('INSERT OR REPLACE INTO domain_dispatch VALUES(?,?)', (domain,now))
            self.event(con, 'top_level_visit_dispatched', {'id':rid,'job_id':job['id'],'purpose':purpose,
                'attempt_index':index,'target_uri':target_uri,'domain':domain,'dispatched_at':now})
            return {'id':rid,'attempt_index':index,'dispatched_at':now,'timeout_seconds':min(timeout_seconds,remaining)}

    def settle_visit(self, visit, *, state, response_status=None, landed_uri=None, error=None, metrics=None):
        if state not in ('succeeded','failed','unknown'): raise ValueError('Invalid top-level visit state')
        metrics=dict(metrics or {})
        if getattr(error,'responsibility',None):metrics['responsibility']=error.responsibility
        with self.transaction() as con:
            row = con.execute('SELECT * FROM top_level_visits WHERE id=?',(visit['id'],)).fetchone()
            if not row or row['state'] != 'reserved_for_dispatch': raise ValueError('Visit missing or already settled')
            con.execute('UPDATE top_level_visits SET finished_at=?,state=?,response_status=?,landed_uri=?,error_type=?,error_message=?,metrics=? WHERE id=?',
                (time.time(),state,response_status,landed_uri,type(error).__name__ if error else None,str(error) if error else None,
                 canonical(metrics or {}),visit['id']))
            self.event(con,'top_level_visit_finished',{'id':visit['id'],'job_id':row['job_id'],'state':state,
                'response_status':response_status,'landed_uri':landed_uri})
        self.sync_visit_failures()

    def sync_visit_failures(self):
        """Reconcile immutable visit facts before every source/probe/goto dispatch.

        Collection navigation belongs to the production attempt, whose full
        failure is imported by RuntimeStore, so it must not count twice here.
        A retained dispatch reservation is UNKNOWN and blocks reentry.
        """
        binding = self.config.get('site_failure_guard')
        if binding is None or self.config['mode'] != 'real':
            return
        from .site_failure_stop import SiteFailureStore, execution_id
        store = SiteFailureStore(binding)
        with self.connect() as con:
            jobs = {row['id']: dict(row) for row in con.execute('SELECT id,kind,state,lease FROM jobs')}
        for row in self.visits():
            job = jobs.get(row['job_id'], {})
            if row['purpose'].startswith('collection:') or row['state'] == 'succeeded':
                continue
            if (row['state'] == 'reserved_for_dispatch' and job.get('state') == 'running'
                    and (job.get('lease') or 0) > time.time()):
                continue  # A live visit is not an interrupted UNKNOWN fact.
            responsibility=row['metrics'].get('responsibility')
            if row['state']=='failed' and responsibility in ('model','configuration','interface','collector'):
                continue  # Retained visit failure, no conviction of this application.
            state = 'failed' if row['state'] == 'failed' and responsibility!='unknown' else 'unknown'
            # An event binding, not a hash of the changing SQLite file.
            fact = {key: row[key] for key in ('id', 'job_id', 'target_uri', 'dispatched_at')}
            store.record(row['target_uri'], execution_id('probe', self.path, row['id']),
                stage='probe', state=state, reason=row['error_type'] or 'Unresolved visit dispatch',
                real_execution=True, evidence=[{'visit_fact': fact}],
                usage_refs=[{'ledger': str(self.path), 'visit_id': row['id']}])

    def record_probe_outcome(self, job, application, record, reference):
        """Retain a rendered probe failure even when navigation itself succeeded."""
        binding = self.config.get('site_failure_guard')
        if not binding or self.config['mode'] != 'real':
            return
        if not (record.get('status') == 'rejected' or record.get('error_message')):
            return  # Pending semantic review is not an executed failure.
        from .planning import verify_evidence
        from .site_failure_stop import SiteFailureStore, execution_id
        verify_evidence([reference])
        if load_json(reference['path']) != record:
            raise ValueError('Probe outcome differs from its original evidence')
        # Unknown attribution is a retained engineering diagnostic, not a site conviction.
        if record.get('responsibility') not in ('site',) and record.get('status')!='rejected':
            return
        visits = [row for row in self.visits() if row['job_id'] == job['id']]
        if not visits or any(row['state'] != 'succeeded' for row in visits):
            return  # Original failed/UNKNOWN dispatches were already reconciled.
        visit = visits[-1]
        SiteFailureStore(binding).record(application, execution_id('probe-outcome', self.path, visit['id']),
            stage='probe', state='failed', real_execution=True,
            reason=record.get('error_message') or record.get('reason') or 'Rendered source rejected', evidence=[reference],
            usage_refs=[{'ledger': str(self.path), 'visit_id': visit['id'], 'job_id': job['id']}])

    def visits(self):
        with self.connect() as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='top_level_visits'").fetchone(): return []
            values = [dict(row) for row in con.execute('SELECT * FROM top_level_visits ORDER BY dispatched_at,id')]
        for row in values: row['metrics'] = json.loads(row['metrics']) if row['metrics'] else {}
        return values

    def visit_history(self):
        with self.connect() as con:
            prior = con.execute("SELECT COALESCE(SUM(amount),0) FROM resources WHERE kind='probe_pages'").fetchone()[0]
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='visit_accounting_meta'").fetchone():
                return dict(con.execute('SELECT * FROM visit_accounting_meta WHERE id=1').fetchone())
        return {'history_complete':not bool(prior),'prior_unique_pages':prior,'started':None}

    def register_generated_task(self, signature, job_id, task):
        with self.transaction() as con:
            old=con.execute('SELECT job_id,task_json FROM generated_task_index WHERE signature=?',(signature,)).fetchone()
            if old and (old['job_id']!=job_id or json.loads(old['task_json'])!=task):
                raise ValueError('Task form/action structure already generated in this run; parameter-only replacement rejected')
            con.execute('INSERT OR IGNORE INTO generated_task_index VALUES(?,?,?)',(signature,job_id,canonical(task)))

    def reserve_request(self, job, purpose, attempt, request_json=None):
        if self.config['model'] is None:
            raise ValueError('Model branch disabled (model:null); no model reservation or dispatch allowed')
        model, budget = self.config['model'], self.config['budget']
        tokens = model['reserve_input_tokens'] + model['max_completion_tokens']
        with self.transaction() as con:
            self._owned(con, job)
            self._time_limit(con)
            old = con.execute('SELECT * FROM model_requests WHERE job_id=? AND purpose=? AND attempt=?',
                              (job['id'], purpose, attempt)).fetchone()
            if old:
                if old['state'] == 'succeeded':
                    return dict(old)
                if old['state'] in ('reserved', 'unknown'):
                    raise OutcomeUnknown('Prior request may have been billed; no automatic resend')
                return dict(old)
            from .provider_recovery import holds, permits_probe
            if holds(con) and not permits_probe(con,job['id'],request_json,attempt):
                raise OutcomeUnknown('Unreconciled provider authorization failure in original ledger; no new request reserved')
            used = con.execute('''SELECT COUNT(*),COALESCE(SUM(COALESCE(cost,reserved_cost)),0),
                COALESCE(SUM(CASE WHEN usage IS NULL THEN reserved_tokens ELSE
                json_extract(usage,'$.input_tokens')+json_extract(usage,'$.output_tokens') END),0)
                FROM model_requests''').fetchone()
            if used[0] + 1 > budget['max_model_requests']:
                raise BudgetStop('max_model_requests reached')
            if budget.get('cost_control', 'capped') == 'capped' and used[1] + model['reserve_cost_micros'] > budget['max_model_cost_micros']:
                raise BudgetStop('max_model_cost_micros reached (including uncertain reservations)')
            if used[2] + tokens > budget['max_reserved_tokens']:
                raise BudgetStop('max_reserved_tokens reached')
            started=con.execute('SELECT started FROM batch_meta').fetchone()[0]
            if started+budget['max_run_seconds']-time.time()<model['timeout_seconds']:
                raise BudgetStop('Insufficient remaining run time for the next bounded model request')
            exceeded = ("error='reservation_exceeded'" if budget.get('cost_control', 'capped') == 'observe_only'
                        else "cost>reserved_cost OR error='reservation_exceeded'")
            if con.execute('SELECT 1 FROM model_requests WHERE ' + exceeded).fetchone():
                raise BudgetStop('Provider usage exceeded conservative reservation; reconcile before further dispatch')
            last=con.execute('SELECT MAX(started) FROM model_requests').fetchone()[0]
            if last is not None:
                delay=last+budget['min_model_interval_seconds']-time.time()
                if delay>0:raise ModelRateWait(delay)
            rid = uuid.uuid4().hex
            con.execute('''INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started,request_json)
                VALUES(?,?,?,?,?,?,?,?,?)''', (rid, job['id'], purpose, attempt, 'reserved', tokens,
                                           model['reserve_cost_micros'], time.time(),canonical(request_json)))
            self.event(con, 'model_reserved', {'request_id': rid, 'job_id': job['id'], 'purpose': purpose,
                                             'model': model['model'], 'rate_version': model['rates']['version']})
            return {'id': rid, 'state': 'new'}

    def settle_request(self, request_id, *, state, usage=None, response=None, error=None):
        cost = None
        if usage is not None:
            rates = self.config['model']['rates']
            cached = usage.get('cached_input_tokens', 0)
            cost = ((usage['input_tokens'] - cached) * rates['input'] +
                    cached * rates['cached_input'] + usage['output_tokens'] * rates['output'] + 999999) // 1_000_000
        with self.transaction() as con:
            row = con.execute('SELECT * FROM model_requests WHERE id=?', (request_id,)).fetchone()
            if not row or row['state'] != 'reserved':
                raise ValueError('Request already settled or missing')
            if usage and (usage['input_tokens']>self.config['model']['reserve_input_tokens'] or
                          usage['output_tokens']>self.config['model']['max_completion_tokens']):
                error = 'reservation_exceeded'
            con.execute('''UPDATE model_requests SET state=?,finished=?,usage=?,cost=?,response=?,error=? WHERE id=?''',
                        (state, time.time(), canonical(usage) if usage else None, cost,
                         canonical(response) if response is not None else None, error, request_id))
            self.event(con, 'model_settled', {'request_id': request_id, 'state': state,
                'usage_source': 'synthetic' if self.config['mode']=='synthetic' else 'provider_response',
                'rate_version': self.config['model']['rates']['version'], 'cost_micros': cost})

    def summary(self, *, final_qualified=0):
        _integer(final_qualified, 'final_qualified')
        with self.connect() as con:
            requests = [dict(row) for row in con.execute('SELECT * FROM model_requests ORDER BY started')]
            jobs = [dict(row) for row in con.execute('SELECT kind,state,COUNT(*) AS count FROM jobs GROUP BY kind,state')]
            resources = [dict(row) for row in con.execute('SELECT kind,SUM(amount) AS used FROM resources GROUP BY kind')]
            metadata={r['id']:dict(r) for r in con.execute('SELECT id,kind,created FROM jobs')}
            events=[dict(row) for row in con.execute("SELECT at,event,detail FROM batch_events WHERE event IN ('job_claimed','job_finished') ORDER BY seq")]
            start = con.execute('SELECT started FROM batch_meta').fetchone()[0]
        covered = sum(row['cost'] is not None for row in requests)
        known = sum(row['cost'] or 0 for row in requests)
        reserved = sum(row['reserved_cost'] for row in requests if row['cost'] is None)
        elapsed = time.time() - start
        visits = self.visits()
        visit_history = self.visit_history()
        stages=defaultdict(lambda:{'model_requests':0,'known_model_cost_micros':0,'uncertain_reserved_cost_micros':0,
                                   'input_tokens':0,'output_tokens':0,'cached_input_tokens':0,
                                   'worker_seconds':0.0,'queue_wait_seconds':0.0,'reasoning_tokens_known':0,'reasoning_usage_unknown_requests':0,'request_states':defaultdict(int)})
        active={};first_claim=set()
        for event in events:
            detail=json.loads(event['detail']);jid=detail['job_id'];kind=metadata[jid]['kind']
            if event['event']=='job_claimed':
                active[jid]=event['at']
                if jid not in first_claim:
                    stages[kind]['queue_wait_seconds']+=event['at']-metadata[jid]['created'];first_claim.add(jid)
            elif jid in active:
                stages[kind]['worker_seconds']+=event['at']-active.pop(jid)
        for row in requests:
            stage=stages[metadata[row['job_id']]['kind']];stage['model_requests']+=1
            stage['request_states'][row['state']]+=1
            reasoning=json.loads(row['usage']).get('reasoning_tokens') if row['usage'] else None
            if type(reasoning)is int and reasoning>=0:stage['reasoning_tokens_known']+=reasoning
            else:stage['reasoning_usage_unknown_requests']+=1
            stage['known_model_cost_micros']+=row['cost'] or 0
            stage['uncertain_reserved_cost_micros']+=row['reserved_cost'] if row['cost']is None else 0
            if row['usage']:
                usage=json.loads(row['usage'])
                for name in ('input_tokens','output_tokens','cached_input_tokens'):stage[name]+=usage[name]
        return {'schema_version': 'webcollect-batch-summary-1', 'run_id': self.config['run_id'],
                'mode': self.config['mode'], 'jobs': jobs, 'resources': resources,
                'cost_control': self.config['budget'].get('cost_control', 'capped'),
                'max_model_cost_micros': ('NOT_APPLICABLE' if self.config['budget'].get('cost_control', 'capped') == 'observe_only'
                                          else self.config['budget'].get('max_model_cost_micros', 'UNKNOWN')),
                'monetary_limit_applied': self.config['model'] is not None and self.config['budget'].get('cost_control', 'capped') == 'capped',
                'cost_reservation_exceeded_requests': sum(r['cost'] is not None and r['cost'] > r['reserved_cost'] for r in requests),
                'token_reservation_exceeded_requests': sum(r['error'] == 'reservation_exceeded' for r in requests),
                'top_level_visits_attempted':len(visits) if visit_history['history_complete'] else 'UNKNOWN',
                'top_level_visits_recorded_since_accounting_start':len(visits),
                'top_level_visit_history':visit_history,
                'top_level_visit_states':dict(Counter(row['state'] for row in visits)),
                'max_top_level_visits':self.config['budget'].get('max_top_level_visits',self.config['budget']['max_probe_pages']),
                'redirect_requests_observed':sum(row['metrics'].get('redirect_request_events',0) for row in visits),
                'subresources_observed':sum(row['metrics'].get('subresource_or_child_frame_request_events',0) for row in visits),
                'visit_accounting_scope':'Each program-dispatched top-level source fetch/page.goto attempt; cached evidence excluded; redirects and subresources separately observed, not all HTTP requests',
                'model_requests': len(requests), 'usage_covered_requests': covered,
                'model_request_states':dict(Counter(r['state'] for r in requests)),
                'retry_requests':sum(r['attempt']>0 for r in requests),
                'stages':dict(stages),
                'usage_coverage': covered/len(requests) if requests else None,
                'known_model_cost_micros': known, 'uncertain_reserved_cost_micros': reserved,
                'model_cost_micros': known if covered == len(requests) else 'UNKNOWN',
                'model_enabled': self.config['model'] is not None,
                'currency': self.config['budget'].get('currency'),
                'rate_version': self.config['model']['rates']['version'] if self.config['model'] else None,
                'wall_seconds': elapsed,
                'model_worker_seconds': sum((r['finished']-r['started']) for r in requests if r['finished']),
                'final_qualified': final_qualified,
                'qualified_per_hour': final_qualified/elapsed*3600 if elapsed else None,
                'end_to_end_cost': 'UNKNOWN: infrastructure, discovery and human costs not supplied',
                'unit_cost': None if not final_qualified else 'UNKNOWN',
                'synthetic_results_are_acceptance': False, 'customer_acceptance': 'UNKNOWN'}

    def export(self, directory):
        """One summary plus traceable request details; no keys, headers or pixels."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            rows = [dict(row) for row in con.execute('SELECT * FROM model_requests ORDER BY started')]
        for row in rows:
            row.pop('response')
            row.pop('request_json')
            row.update(model=self.config['model']['model'],provider=self.config['model']['provider'],
                       rate_version=self.config['model']['rates']['version'],currency=self.config['budget']['currency'])
        # Snapshots are versioned by content; prior cost reports are retained.
        summary = self.summary()
        save_json(directory / ('summary-' + object_sha256(summary)[:16] + '.json'), summary)
        save_json(directory / ('requests-' + object_sha256(rows)[:16] + '.json'), rows)
        visits = self.visits()
        save_json(directory / ('visits-' + object_sha256(visits)[:16] + '.json'), visits)
        return summary
