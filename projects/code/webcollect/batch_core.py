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


CONSUMER_KINDS = frozenset(('candidate-observation', 'collection', 'react-native-decision',
                            'react-decision', 'fragment-decision', 'task-generation', 'frozen-plan'))


class BudgetStop(ValueError):
    pass


class SessionGLMCallLimit(BudgetStop):
    code = 'glm_session_call_limit'
    limit = 25

    def __init__(self, attempt_id, used):
        self.details = {'code': self.code, 'attempt_id': attempt_id, 'used': used, 'limit': self.limit}
        super().__init__(f'本次会话已派发 {used} 次真实 GLM 请求，达到 {self.limit} 次上限，停止后续调用。')


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
    runtime_fields = {'max_concurrent_jobs', 'min_domain_interval_seconds', 'lease_seconds'}
    model_enabled = value['model'] is not None
    token_only = model_enabled and isinstance(value['model'], dict) and value['model'].get('accounting_mode') == 'tokens-1'
    fields = runtime_fields | (({'min_model_interval_seconds'} | (set() if token_only else {'currency'})) if model_enabled else {'max_job_attempts'})
    # Old serialized ceilings remain part of the frozen configuration hash.
    historical_limits = ({'currency'} if token_only else set()) | {'max_discovery_candidates', 'max_probe_pages', 'max_run_seconds', 'max_top_level_visits'}
    if model_enabled:
        historical_limits.update(('max_model_requests','max_reserved_tokens','max_model_cost_micros'))
    if not isinstance(budget, dict) or not fields <= set(budget) or set(budget) - fields - historical_limits - {'max_job_attempts','cost_control'}:
        raise ValueError('Invalid scheduler or metering configuration; required: ' + ', '.join(sorted(fields)))
    if 'cost_control' in budget and (not model_enabled or budget['cost_control'] not in ('capped','observe_only')):
        raise ValueError('Invalid historical cost-control mode')
    for key in (historical_limits - {'currency'}).intersection(budget):
        if budget[key] is not None:
            _integer(budget[key], key)
    for key in fields - {'currency'}:
        _integer(budget[key], key, 0 if key == 'min_model_interval_seconds' else 1)
    if 'max_job_attempts' in budget:
        _integer(budget['max_job_attempts'], 'max_job_attempts', 1)
    if model_enabled and budget['min_model_interval_seconds']>30:
        raise ValueError('Model interval must be <=30 seconds; use a smaller worker concurrency for lower throughput')
    if budget['lease_seconds'] < 5:
        raise ValueError('lease_seconds >= 5 required')
    if not model_enabled:
        if require_model:
            raise ValueError('Model branch disabled (model:null); this operation requires an explicit model configuration')
        return deepcopy(value)
    if not token_only and (not isinstance(budget['currency'], str) or not budget['currency'].strip()):
        raise ValueError('Explicit model billing currency required')
    model = value['model']
    fields = {'provider', 'model', 'endpoint', 'api_key_env', 'timeout_seconds', 'reserve_input_tokens',
              'max_completion_tokens', 'max_images'} | (set() if token_only else {'reserve_cost_micros', 'rates'})
    capability_fields = {'supports_vision', 'image_tokens_per_image', 'request_overhead_tokens'}
    optional_fields = capability_fields | {'accounting_mode', 'reserve_cost_micros', 'rates', 'image_encoding', 'reasoning_effort', 'api_key_file', 'structured_output'}
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
    if model.get('structured_output') is not None:
        if (model['structured_output'] != 'json_object' or value['mode'] != 'real'
                or model['provider'] != 'glm' or not model.get('supports_vision')):
            raise ValueError('structured_output json_object is an explicit real-mode GLM vision experiment flag')
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
    if model.get('accounting_mode') not in (None, 'tokens-1'):
        raise ValueError('Unknown accounting mode')
    if not token_only:
        _integer(model['reserve_cost_micros'], 'reserve_cost_micros')
    rates = model.get('rates', {'version':'tokens-1','source':'token usage only','input':0,'cached_input':0,'output':0})
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
                or (not token_only and not model['reserve_cost_micros'])):
            raise ValueError('Real calls need credential environment name, a nonzero accounting reservation')
        if not token_only and (not rates['input'] or not rates['output']):
            raise ValueError('Real calls need nonzero verified input/output rates')
        if credentials:
            from .model_credentials import credential
            credential(model)
    minimum = (model['reserve_input_tokens'] * max(rates['input'], rates['cached_input']) +
               model['max_completion_tokens'] * rates['output'] + 999999) // 1_000_000
    if not token_only and model['reserve_cost_micros'] < minimum:
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
                raise ValueError('Run configuration is frozen; resume with the original binding')
            policy = con.execute("SELECT detail FROM batch_events WHERE event='producer_budget_unlimited' ORDER BY seq DESC LIMIT 1").fetchone()
            self.producer_policy = json.loads(policy[0]) if policy else None
            if self.producer_policy and (self.producer_policy['ledger'] != str(self.path)
                    or self.producer_policy['run_id'] != self.config['run_id']
                    or self.producer_policy['config_sha256'] != object_sha256(self.config)):
                raise ValueError('Producer budget decision does not match its original ledger')
            concurrency = con.execute("SELECT detail FROM batch_events WHERE event='producer_concurrency' ORDER BY seq DESC LIMIT 1").fetchone()
            self.producer_concurrency = json.loads(concurrency[0]) if concurrency else None
            if self.producer_concurrency:
                decision = self.producer_concurrency
                if (decision.get('schema_version') != 'webcollect-producer-concurrency-1'
                        or decision.get('ledger') != str(self.path)
                        or decision.get('run_id') != self.config['run_id']
                        or decision.get('config_sha256') != object_sha256(self.config)
                        or type(decision.get('max_concurrent_jobs')) is not int
                        or decision['max_concurrent_jobs'] < 1):
                    raise ValueError('Producer concurrency decision does not match its original ledger')

    @property
    def max_concurrent_jobs(self):
        """Read consumer scheduling changes live; frozen model config stays put."""
        with self.connect() as con:
            return self._job_concurrency_limit(con)

    def consumer_concurrency(self, con=None):
        """A consumer-only setting is separate from the immutable run config."""
        if con is None:
            with self.connect() as current:
                return self.consumer_concurrency(current)
        row = con.execute("SELECT detail FROM batch_events WHERE event='consumer_concurrency' ORDER BY seq DESC LIMIT 1").fetchone()
        if row is None:
            return None
        self.require_consumer_ledger(con)
        decision = json.loads(row[0])
        limit = decision.get('max_concurrent_jobs')
        if (decision.get('schema_version') != 'webcollect-consumer-concurrency-1'
                or decision.get('ledger') != str(self.path)
                or decision.get('run_id') != self.config['run_id']
                or decision.get('config_sha256') != object_sha256(self.config)
                or 'max_concurrent_jobs' not in decision
                or limit is not None and (type(limit) is not int or limit < 1)):
            raise ValueError('Consumer concurrency decision does not match its original ledger')
        return decision

    def require_consumer_ledger(self, con):
        """Use the existing producer markers and project role binding."""
        if (self.producer_policy is not None or self.producer_concurrency is not None
                or con.execute("SELECT 1 FROM batch_events WHERE event IN "
                               "('producer_budget_unlimited','producer_concurrency') LIMIT 1").fetchone()):
            raise ValueError('Consumer concurrency cannot change a producer ledger')
        guard = self.config.get('site_failure_guard')
        if guard:
            from .current_chain import registry_project, check_project_guard
            registry = self.path.with_name('production-registry.sqlite3')
            with sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True,
                                 factory=ClosingConnection) as current:
                check_project_guard(registry_project(current), guard, self.path, role='consumer')

    def _job_concurrency_limit(self, con):
        decision = self.consumer_concurrency(con)
        if decision is not None:
            return decision['max_concurrent_jobs']
        return (self.producer_concurrency or {}).get('max_concurrent_jobs', self.config['budget']['max_concurrent_jobs'])

    def connect(self, create=False, *, timeout=30):
        con = sqlite3.connect(str(self.path) if create else self.path.as_uri() + '?mode=rw',
                              uri=not create, timeout=timeout, factory=ClosingConnection)
        con.row_factory = sqlite3.Row
        return con

    @contextmanager
    def transaction(self, *, timeout=30):
        con = self.connect(timeout=timeout)
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

    def authorize_runtime_window(self, reference):
        """Validate and append a legacy continuation receipt for its original scope."""
        from .planning import verify_evidence
        verify_evidence([reference]);value=load_json(reference['path'])
        with self.transaction() as con:
            start=con.execute('SELECT started FROM batch_meta').fetchone()[0]
            if (value.get('schema_version')!='webcollect-runtime-window-1' or value.get('run_id')!=self.config['run_id']
                    or value.get('ledger')!=str(self.path) or value.get('config_sha256')!=object_sha256(self.config)
                    or value.get('original_started')!=start or not value.get('user_instruction')
                    or not time.time()<value.get('deadline',0)<=time.time()+86400
                    or type(value.get('max_new_consumer_runs')) is not int or not 1<=value['max_new_consumer_runs']<=10):
                raise ValueError('Explicit bounded continuation authorization required')
            if con.execute("SELECT 1 FROM model_requests WHERE state IN ('reserved','unknown') LIMIT 1").fetchone():
                raise OutcomeUnknown('Original model request unresolved; runtime continuation cannot resend')
            if con.execute("SELECT 1 FROM jobs WHERE state='running' LIMIT 1").fetchone():
                raise ValueError('Original worker still active; do not add a concurrent window')
            con.execute('CREATE TABLE IF NOT EXISTS runtime_windows(id TEXT PRIMARY KEY, reference TEXT NOT NULL, deadline REAL NOT NULL)')
            identity=object_sha256(reference)
            inserted=con.execute('INSERT OR IGNORE INTO runtime_windows VALUES(?,?,?)',
                                 (identity,canonical(reference),value['deadline'])).rowcount
            if inserted:self.event(con,'runtime_window_authorized',{'reference':reference,'original_started':start,
                'deadline':value['deadline'],'budgets_and_counters_reset':False})
        return value

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

    def claim(self, kind, *, job_id=None, domain=None, parent_job=None):
        self.recover()
        with self.transaction() as con:
            query = "SELECT * FROM jobs WHERE kind=? AND state='queued'"
            params = [kind]
            if job_id:
                query += ' AND id=?'; params.append(job_id)
            row = con.execute(query + ' ORDER BY created,id LIMIT 1', params).fetchone()
            if not row:
                return None
            attempt_cap = None if kind in CONSUMER_KINDS else self.config['budget'].get('max_job_attempts')
            continued_claim=False
            if kind=='ai-difference' and attempt_cap is not None and row['attempts']>=attempt_cap:
                # Explicit continuation owns one additional claim of the exact
                # original job. It never changes the configured retry cap or
                # permits dispatch of the original unresolved pair requests.
                events=con.execute("SELECT detail FROM batch_events WHERE event='qc_unreviewed_pairs_resumed' AND json_extract(detail,'$.job_id')=?",(row['id'],)).fetchall()
                for event in events:
                    decision=json.loads(event[0])
                    if decision.get('authorized_claim_attempt')!=row['attempts']+1:continue
                    from .planning import verify_evidence
                    verify_evidence([decision['authorization']]);auth=load_json(decision['authorization']['path'])
                    continued_claim=(auth.get('action')=='continue_unreviewed_pairs' and auth.get('job_id')==row['id']
                        and auth.get('preserve_unknown') is True and bool(decision.get('remaining_dispatchable_pairs'))
                        and decision.get('payload_sha256')==object_sha256(json.loads(row['payload']))
                        and not con.execute("SELECT 1 FROM model_requests WHERE job_id=? AND state='reserved'",(row['id'],)).fetchone())
                    if continued_claim:break
            if attempt_cap is not None and row['attempts'] >= attempt_cap and not continued_claim:
                con.execute("UPDATE jobs SET state='review_required',error=?,updated=? WHERE id=?",
                            ('max_job_attempts reached; original attempts retained', time.time(), row['id']))
                self.event(con, 'job_attempt_limit', {'job_id': row['id'], 'attempts': row['attempts'], 'limit': attempt_cap})
                return None
            con.execute('CREATE TABLE IF NOT EXISTS job_parents ('
                        'job_id TEXT PRIMARY KEY REFERENCES jobs(id), parent_id TEXT NOT NULL REFERENCES jobs(id), '
                        'parent_owner TEXT NOT NULL)')
            if parent_job is not None:
                self._owned(con,parent_job)
                if kind not in ('fragment-decision','react-decision','react-native-decision') or parent_job['kind']!='collection' or json.loads(row['payload']).get('parent_job_id')!=parent_job['id']:
                    raise ValueError('Only a bound collection decision may share its parent slot')
                if con.execute("SELECT 1 FROM job_parents p JOIN jobs j ON j.id=p.job_id WHERE p.parent_id=? AND j.state='running'",(parent_job['id'],)).fetchone():
                    raise BudgetStop('Parent already has an active decision; no parallel child')
            running = con.execute("SELECT COUNT(*) FROM jobs j WHERE state='running' AND kind!='frozen-plan' "
                                  'AND NOT EXISTS(SELECT 1 FROM job_parents p WHERE p.job_id=j.id)').fetchone()[0]
            job_limit = None if kind in CONSUMER_KINDS else self._job_concurrency_limit(con)
            if parent_job is None and job_limit is not None and running >= job_limit:
                raise BudgetStop('max_concurrent_jobs reached; queued work retained')
            if domain and kind not in CONSUMER_KINDS:
                last = con.execute('SELECT dispatched FROM domain_dispatch WHERE domain=?', (domain,)).fetchone()
                if last and time.time() - last[0] < self.config['budget']['min_domain_interval_seconds']:
                    raise BudgetStop('domain rate limit; queued work retained')
                con.execute('INSERT OR REPLACE INTO domain_dispatch VALUES(?,?)', (domain, time.time()))
            owner = uuid.uuid4().hex
            con.execute("UPDATE jobs SET state='running',owner=?,lease=?,attempts=attempts+1,updated=? WHERE id=?",
                        (owner, time.time() + self.config['budget']['lease_seconds'], time.time(), row['id']))
            if parent_job is not None:
                con.execute('INSERT INTO job_parents VALUES(?,?,?)',(row['id'],parent_job['id'],parent_job['owner']))
            self.event(con, 'job_claimed', {'job_id': row['id'], 'kind': kind})
            return {**dict(row), 'payload': json.loads(row['payload']), 'owner': owner}

    def _owned(self, con, job):
        row = con.execute('SELECT * FROM jobs WHERE id=?', (job['id'],)).fetchone()
        if not row or row['owner'] != job['owner'] or row['state'] != 'running' or row['lease'] < time.time():
            raise ValueError('Lost/expired job lease')
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='job_parents'").fetchone():
            parent=con.execute('SELECT j.state,j.owner,j.lease,p.parent_owner FROM job_parents p JOIN jobs j ON j.id=p.parent_id WHERE p.job_id=?',(job['id'],)).fetchone()
            if parent and (parent[0]!='running' or parent[1]!=parent[3] or parent[2]<time.time()):
                raise ValueError('Lost/expired parent collection lease')
        return row

    def heartbeat(self, job, *, request_timeout=None):
        with self.transaction() as con:
            row = self._owned(con, job)
            lease_seconds = self.config['budget']['lease_seconds']
            if request_timeout is not None:
                if row['kind'] != 'react-native-decision' or type(request_timeout) is not int or not 1 <= request_timeout <= 600:
                    raise ValueError('Only an owned native decision can extend its bounded request lease')
                lease_seconds = max(lease_seconds, request_timeout + 30)
            con.execute('UPDATE jobs SET lease=? WHERE id=?',
                        (time.time() + lease_seconds, job['id']))

    def finish(self, job, state='done', result=None, error=None):
        if state not in ('done', 'failed', 'review_required', 'queued'):
            raise ValueError('Invalid job state')
        with self.transaction() as con:
            self._owned(con, job)
            con.execute('UPDATE jobs SET state=?,result=?,error=?,owner=NULL,lease=NULL,updated=? WHERE id=?',
                        (state, canonical(result) if result is not None else None, error, time.time(), job['id']))
            self.event(con, 'job_finished', {'job_id': job['id'], 'state': state})

    def request_window(self, job, timeout, *, cleanup_seconds=5):
        """Check current ownership and leave synchronous settlement inside lease."""
        with self.connect() as con:
            row = self._owned(con, job)
            remaining = row['lease'] - time.time() - cleanup_seconds
        if remaining <= 0:
            raise ValueError('Insufficient owned lease for request and cleanup')
        return min(timeout, remaining)

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
        if kind not in ('discovery_candidates', 'probe_pages'):
            raise ValueError('Unknown resource kind')
        _integer(amount, 'resource amount', 1)
        with self.transaction() as con:
            old = con.execute('SELECT kind,amount FROM resources WHERE key=?', (key,)).fetchone()
            if old:
                if tuple(old) != (kind, amount):
                    raise ValueError('Resource identity collision')
                return
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
        """Compatibility with callers combining a run window with their I/O timeout."""
        return math.inf

    def reserve_visit(self, job, target_uri, purpose, domain, *, timeout_seconds=20):
        """Count each dispatch, including failed/repeated visits; never cache-dedup.

        A crash between reservation and the socket call retains a conservative
        unknown attempt. Redirects/subresources are separately observed metrics.
        Unique page reservations remain in resources and are never rewritten.
        """
        consumer = job['kind'] in CONSUMER_KINDS
        if not consumer and self.config['mode'] == 'real' and not self.config.get('site_failure_guard'):
            raise BudgetStop('Real website dispatch requires the original whole-site failure guard; no request sent')
        if not consumer:
            self.sync_visit_failures()
        guard = self.config.get('site_failure_guard')
        if guard and not consumer:
            from .site_failure_stop import SiteFailureStore
            SiteFailureStore(guard).guard(target_uri)
        with self.transaction() as con:
            self._owned(con, job)
            self._ensure_visit_schema(con)
            if not consumer and not con.execute('SELECT history_complete FROM visit_accounting_meta WHERE id=1').fetchone()[0]:
                raise BudgetStop('Legacy top-level visit history UNKNOWN; reconcile original visits before dispatch')
            from .current_chain import PROJECT_RULES
            if not consumer and guard and guard.get('dispatch_rules')==PROJECT_RULES:
                from .request_quarantine import endpoint
                aliases=guard.get('application_registry')
                target=endpoint(target_uri,aliases)
                # A concurrent reservation may have arrived after the site-fact read.
                con.execute("""CREATE INDEX IF NOT EXISTS unresolved_visit_endpoints ON top_level_visits(target_uri,id)
                    WHERE state IN ('reserved_for_dispatch','unknown')""")
                for previous in con.execute("""SELECT id,target_uri FROM top_level_visits
                        WHERE state IN ('reserved_for_dispatch','unknown')"""):
                    if endpoint(previous['target_uri'],aliases)==target:
                        raise OutcomeUnknown('Original visit unresolved for this endpoint; no dispatch: '+previous['id'])
            if consumer and con.execute(
                    "SELECT 1 FROM top_level_visits WHERE job_id=? AND purpose=? AND state IN ('reserved_for_dispatch','unknown')",
                    (job['id'], purpose)).fetchone():
                raise OutcomeUnknown('Original consumer visit unresolved; no replacement dispatch')
            now = time.time()
            last = con.execute('SELECT dispatched FROM domain_dispatch WHERE domain=?', (domain,)).fetchone()
            delay = last[0] + self.config['budget']['min_domain_interval_seconds'] - now if last else 0
            if delay > 0 and not consumer:
                raise VisitRateWait(delay)
            index = con.execute('SELECT COUNT(*)+1 FROM top_level_visits WHERE job_id=? AND purpose=?', (job['id'],purpose)).fetchone()[0]
            rid = uuid.uuid4().hex
            con.execute('INSERT INTO top_level_visits VALUES(?,?,?,?,?,?,?,NULL,?,NULL,NULL,NULL,NULL,NULL)',
                        (rid, job['id'], purpose, index, target_uri, domain, now, 'reserved_for_dispatch'))
            con.execute('INSERT OR REPLACE INTO domain_dispatch VALUES(?,?)', (domain,now))
            self.event(con, 'top_level_visit_dispatched', {'id':rid,'job_id':job['id'],'purpose':purpose,
                'attempt_index':index,'target_uri':target_uri,'domain':domain,'dispatched_at':now})
            return {'id':rid,'attempt_index':index,'dispatched_at':now,'timeout_seconds':timeout_seconds}

    def settle_visit(self, visit, *, state, response_status=None, landed_uri=None, error=None, metrics=None):
        if state not in ('succeeded','failed','unknown'): raise ValueError('Invalid top-level visit state')
        metrics=dict(metrics or {})
        if getattr(error,'responsibility',None):metrics['responsibility']=error.responsibility
        with self.transaction() as con:
            row = con.execute('SELECT * FROM top_level_visits WHERE id=?',(visit['id'],)).fetchone()
            if not row: raise ValueError('Visit missing or already settled')
            if row['state'] != 'reserved_for_dispatch':
                # The lease-recovery/sync path already sealed this reservation as
                # UNKNOWN. The original worker's late definite outcome is kept as
                # its own batch event with the original error and usage; the
                # sealed visit, its execution identity and the site's UNKNOWN
                # fact are never rewritten. A genuine reconciliation keeps its
                # own reassessment route. Any other double settlement is a bug.
                if row['state'] == 'unknown':
                    self.event(con,'top_level_visit_late_outcome',{'id':visit['id'],'job_id':row['job_id'],
                        'sealed_state':'unknown','late_state':state,
                        'late_response_status':response_status,'late_landed_uri':landed_uri,
                        'late_error_type':type(error).__name__ if error else None,
                        'late_error_message':str(error) if error else None,
                        'late_metrics':metrics})
                    return {'late_outcome_recorded':True,'sealed_state':'unknown','state':state,'id':visit['id']}
                raise ValueError('Visit missing or already settled')
            con.execute('UPDATE top_level_visits SET finished_at=?,state=?,response_status=?,landed_uri=?,error_type=?,error_message=?,metrics=? WHERE id=?',
                (time.time(),state,response_status,landed_uri,type(error).__name__ if error else None,str(error) if error else None,
                 canonical(metrics or {}),visit['id']))
            self.event(con,'top_level_visit_finished',{'id':visit['id'],'job_id':row['job_id'],'state':state,
                'response_status':response_status,'landed_uri':landed_uri})
            consumer = con.execute('SELECT kind FROM jobs WHERE id=?', (row['job_id'],)).fetchone()['kind'] in CONSUMER_KINDS
        if not consumer:
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
        from .site_failure_stop import SiteFailureStore, application_key, execution_id
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
            if row['state'] == 'reserved_for_dispatch':
                # jobs and visits above are separate snapshots. Recheck the
                # original pair before turning a concurrent live GET unknown.
                with self.connect() as con:
                    current = con.execute(
                        'SELECT v.state,j.state AS job_state,j.lease FROM top_level_visits v '
                        'JOIN jobs j ON j.id=v.job_id WHERE v.id=?', (row['id'],)).fetchone()
                if current and (current['state'] == 'succeeded' or (
                        current['job_state'] == 'running' and (current['lease'] or 0) > time.time())):
                    continue
            responsibility=row['metrics'].get('responsibility')
            if row['state']=='failed' and responsibility in ('model','configuration','interface','collector'):
                continue  # Retained visit failure, no conviction of this application.
            state = 'failed' if row['state'] == 'failed' and responsibility!='unknown' else 'unknown'
            # An event binding, not a hash of the changing SQLite file.
            fact = {key: row[key] for key in ('id', 'job_id', 'target_uri', 'dispatched_at')}
            identity = execution_id('probe', self.path, row['id'])
            existing = store.execution(identity)
            if existing is not None:
                # Exact late-settlement replay: this same visit was already
                # sealed as UNKNOWN by lease recovery or an earlier sync, and
                # its row has since taken the original worker's late definite
                # outcome. The sealed site fact stays authoritative; the late
                # error is retained as the ledger's own event. Any other
                # difference (application, stage, evidence/usage binding) is a
                # real identity conflict and still raises inside record().
                if (existing['application_key'] == application_key(row['target_uri'], binding.get('application_registry'))
                        and existing['stage'] == 'probe' and existing['state'] == 'unknown'
                        and existing['evidence'] == [{'visit_fact': fact}]
                        and existing['usage_refs'] == [{'ledger': str(self.path), 'visit_id': row['id']}]):
                    continue
            store.record(row['target_uri'], identity,
                stage='probe', state=state, reason=row['error_type'] or 'Unresolved visit dispatch',
                real_execution=True, evidence=[{'visit_fact': fact}],
                usage_refs=[{'ledger': str(self.path), 'visit_id': row['id']}], return_status=False)

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

    def _unavailable_model_accounts(self, con):
        """Read account health from original request records; never reset UNKNOWN.
        1113 needs explicit reconciliation. Rate limits use Retry-After, with a
        conservative 60s local fallback. 1305 is scoped to this configured model.
        """
        unavailable = set()
        for row in con.execute("SELECT request_json,response,finished FROM model_requests WHERE state='unknown'"):
            material = json.loads(row['request_json'] or '{}')
            if not material or not material.get('account_id'):
                continue
            detail = (json.loads(row['response'] or '{}') or {}).get('provider_error', {})
            code = detail.get('provider_code')
            if code == '1113' or (code in ('1302', '1305') and
                    (row['finished'] or 0) + detail.get('retry_after_seconds', 60) > time.time()):
                if code != '1305' or material.get('model') == self.config['model']['model']:
                    unavailable.add(material['account_id'])
        return unavailable

    def unavailable_model_accounts(self):
        with self.connect() as con:
            return self._unavailable_model_accounts(con)

    @property
    def real_glm(self):
        model = self.config['model'] or {}
        return self.config['mode'] == 'real' and (model.get('provider') == 'glm'
            or model.get('model', '').lower().split('/')[-1].startswith('glm-'))

    @staticmethod
    def _answered_timeout_sql():
        # A later answer closes the decision hold, not the original usage/accounting.
        return """EXISTS (SELECT 1 FROM model_requests answered
            WHERE answered.job_id=r.job_id AND answered.purpose=r.purpose
              AND answered.state IN ('succeeded','invalid_response')
              AND json_extract(answered.request_json,'$.timeout_retry_root')=
                  COALESCE(json_extract(r.request_json,'$.timeout_retry_root'),r.id))"""

    def timeout_retry_answered(self, con, request_id):
        return bool(con.execute('SELECT 1 FROM model_requests r WHERE r.id=? AND r.state=\'unknown\' AND '
            + self._answered_timeout_sql(), (request_id,)).fetchone())

    def _timeout_retry_root(self, con, job, purpose, attempt, material):
        fields = ('timeout_retry_of', 'timeout_retry_root', 'timeout_retry_number')
        if not any(k in material for k in fields):
            return None
        if not all(k in material for k in fields):
            raise ValueError('Incomplete timeout retry binding')
        previous = con.execute('SELECT * FROM model_requests WHERE id=?',
                               (material['timeout_retry_of'],)).fetchone()
        if (not previous or previous['job_id'] != job['id'] or previous['purpose'] != purpose
                or previous['attempt'] != attempt-1 or previous['state'] != 'unknown'):
            raise OutcomeUnknown('Timeout retry must follow its original unresolved request')
        detail = json.loads(previous['response'] or '{}').get('transport_error', {})
        if detail.get('reason_type') != 'TimeoutError':
            raise OutcomeUnknown('Only transport timeouts permit bounded retries')
        old = json.loads(previous['request_json'])
        root = old.get('timeout_retry_root') or previous['id']
        count = con.execute("""SELECT COUNT(*) FROM model_requests WHERE job_id=? AND purpose=?
            AND json_extract(request_json,'$.timeout_retry_of') IS NOT NULL""", (job['id'],purpose)).fetchone()[0]
        if (count >= 3 or material['timeout_retry_root'] != root
                or type(material['timeout_retry_number']) is not int or material['timeout_retry_number'] != count+1):
            raise OutcomeUnknown('At most three timeout retries on the original request identity')
        ignored = {*fields, 'cost_control'}
        if {k:v for k,v in material.items() if k not in ignored} != {k:v for k,v in old.items() if k not in ignored}:
            raise ValueError('Timeout retry must preserve payload, account and session')
        return root

    def session_http_usage(self, con, attempt_id, *, timeout_retry_root=None):
        # Native calls carry their session on the request. Legacy ReAct uses
        # its original decision job. Each row represents one dispatch, including retries.
        answered = self._answered_timeout_sql()
        pending = f"""(NOT ({answered}) AND (? IS NULL OR
            COALESCE(json_extract(r.request_json,'$.timeout_retry_root'),r.id)<>?))"""
        return con.execute(f"""SELECT COUNT(*) AS used, COUNT(json_extract(r.request_json,'$.dispatch_attempt_id')) AS native_calls,
            MIN(json_extract(r.request_json,'$.dispatch_max_requests')) AS min_cap,
            MAX(json_extract(r.request_json,'$.dispatch_max_requests')) AS max_cap,
            MAX(j.kind IN ('react-decision','react-native-decision')) AS has_react,
            MIN(CASE WHEN (r.state='unknown' AND {pending}) OR j.state='review_required' THEN r.id END) AS held,
            MIN(CASE WHEN r.state='reserved' OR (r.state='unknown' AND {pending}) OR j.state='review_required' THEN r.id END) AS unresolved
            FROM model_requests r JOIN jobs j ON j.id=r.job_id
            WHERE (json_extract(r.request_json,'$.dispatch_attempt_id')=?
                   AND json_extract(r.request_json,'$.http_dispatch')=1)
               OR (j.kind IN ('react-decision','react-native-decision') AND json_extract(j.payload,'$.attempt_id')=?
                   AND ? AND COALESCE(json_extract(r.request_json,'$.http_dispatch'),1)=1)""",
            (timeout_retry_root, timeout_retry_root, timeout_retry_root, timeout_retry_root,
             attempt_id, attempt_id, self.config['mode']=='real')).fetchone()

    def bind_model_session(self, session_id, *, consumer=False):
        """Select/recover once under the existing short SQLite write lock."""
        from .model_credentials import credential, account_id
        with self.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS model_sessions (session_id TEXT PRIMARY KEY, account_id TEXT NOT NULL)')
            old = con.execute('SELECT account_id FROM model_sessions WHERE session_id=?', (session_id,)).fetchone()
            if old is None:
                accounts = {row[0] for row in con.execute("SELECT DISTINCT json_extract(request_json,'$.account_id') FROM model_requests WHERE json_extract(request_json,'$.dispatch_attempt_id')=? OR job_id=?", (session_id,session_id)) if row[0]}
                if len(accounts) > 1:
                    raise OutcomeUnknown('Original session has conflicting accounts')
                original = next(iter(accounts), None)
            else:
                original = old[0]
            ordinal = con.execute('SELECT COALESCE(MAX(rowid),0) FROM model_sessions').fetchone()[0] if original is None else 0
            excluded = self._unavailable_model_accounts(con) if original is None else set()
            if consumer and original is None:
                from .key_health import unavailable_accounts
                excluded = unavailable_accounts(self, con, historical=excluded)
            secret = credential(self.config['model'], excluded_accounts=excluded,
                                required_account=original, selection_index=None if consumer else ordinal)
            con.execute('INSERT OR IGNORE INTO model_sessions VALUES(?,?)', (session_id, account_id(secret)))
            return secret

    def reserve_request(self, job, purpose, attempt, request_json=None):
        if self.config['model'] is None:
            raise ValueError('Model branch disabled (model:null); no model reservation or dispatch allowed')
        model, budget = self.config['model'], self.config['budget']
        tokens = model['reserve_input_tokens'] + model['max_completion_tokens']
        with self.transaction() as con:
            owned = self._owned(con, job)
            consumer = owned['kind'] in CONSUMER_KINDS
            old = con.execute('SELECT * FROM model_requests WHERE job_id=? AND purpose=? AND attempt=?',
                              (job['id'], purpose, attempt)).fetchone()
            if old:
                if old['state'] == 'succeeded':
                    return dict(old)
                if old['state'] in ('reserved', 'unknown'):
                    raise OutcomeUnknown('Prior request may have been billed; no automatic resend')
                return dict(old)
            if consumer and con.execute(
                    "SELECT 1 FROM model_requests WHERE job_id=? AND purpose=? AND state IN ('reserved','unknown')",
                    (job['id'], purpose)).fetchone():
                raise OutcomeUnknown('Original consumer request unresolved; no replacement dispatch')
            timeout_root = self._timeout_retry_root(con, job, purpose, attempt, request_json or {})
            from .provider_recovery import holds, permits_probe
            if not consumer and holds(con) and not permits_probe(con,job['id'],request_json,attempt):
                raise OutcomeUnknown('Unreconciled provider authorization failure in original ledger; no new request reserved')
            native_http = request_json and request_json.get('protocol') in ('native-tool-1','banded-plain-json-1') and request_json.get('http_dispatch')
            aid = request_json.get('dispatch_attempt_id') if native_http else None
            react = owned['kind'] in ('react-decision','react-native-decision')
            if react and self.real_glm:
                session_id = json.loads(owned['payload']).get('attempt_id')
                if not session_id or (native_http and aid != session_id):
                    raise ValueError('GLM dispatch must bind the original ReAct session')
            else:
                session_id = aid
            if session_id is not None:
                if not isinstance(session_id, str) or not session_id.strip():
                    raise ValueError('Invalid attempt identity')
                prior = self.session_http_usage(con, session_id, timeout_retry_root=timeout_root)
                if not consumer and prior['held']:
                    raise OutcomeUnknown('Original attempt request/decision unresolved; no replacement dispatch')
                if not consumer and self.real_glm and (react or prior['has_react']) and prior['used'] >= SessionGLMCallLimit.limit:
                    unresolved = self.session_http_usage(con, session_id)['unresolved']
                    if unresolved:
                        raise OutcomeUnknown('Original session dispatch unresolved at the GLM call limit: ' + unresolved)
                    raise SessionGLMCallLimit(session_id, prior['used'])
            if native_http:
                cap = request_json.get('dispatch_max_requests')
                if aid is not None and not consumer:
                    if cap is not None and (type(cap) is not int or cap < 1):
                        raise ValueError('Invalid attempt request budget')
                    if prior['native_calls'] and (prior['min_cap'] != cap or prior['max_cap'] != cap):
                        raise ValueError('Frozen attempt request cap differs')
                    if cap is not None and prior['used'] >= cap:
                        if self.session_http_usage(con, session_id)['unresolved']:
                            raise OutcomeUnknown('Original timeout unresolved at the attempt request limit')
                        raise BudgetStop('max_requests reached for original attempt')
                account = request_json.get('account_id')
                if not consumer and account in self._unavailable_model_accounts(con):
                    raise OutcomeUnknown('Original account/model hold; no replacement request')
                producer_kinds=('ai-application-site-classification-1','ai-target-page-purpose-1',
                                'ai-grounded-entry-ids-1','ai-candidate-entry-tool-1','ai-search-plan')
                parallel_producer=bool(self.producer_concurrency and self.producer_concurrency['max_concurrent_jobs']>1
                                       and owned['kind'] in producer_kinds)
                active=con.execute("SELECT r.job_id,j.kind FROM model_requests r JOIN jobs j ON j.id=r.job_id WHERE r.state='reserved' "
                    "AND json_extract(r.request_json,'$.account_id')=? "
                    "AND json_extract(r.request_json,'$.model')=?", (account, model['model']))
                if not consumer and any(not (parallel_producer and r['job_id']!=job['id'] and r['kind'] in producer_kinds) for r in active):
                    raise ModelRateWait(1)
                # A known/unknown request pins its attempt to one account. A new
                # independent attempt may select another healthy authorized key.
                if aid is not None and con.execute("SELECT 1 FROM model_requests "
                    "WHERE json_extract(request_json,'$.dispatch_attempt_id')=? "
                    "AND json_extract(request_json,'$.account_id')<>?", (aid, account)).fetchone():
                    raise OutcomeUnknown('Original attempt account differs; no account rotation')
            last=con.execute('SELECT MAX(started) FROM model_requests').fetchone()[0]
            if last is not None and not consumer:
                delay=last+budget['min_model_interval_seconds']-time.time()
                if delay>0:raise ModelRateWait(delay)
            rid = uuid.uuid4().hex
            con.execute('''INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started,request_json)
                VALUES(?,?,?,?,?,?,?,?,?)''', (rid, job['id'], purpose, attempt, 'reserved', tokens,
                                           model.get('reserve_cost_micros', 0), time.time(),
                                           canonical({**(request_json or {}), 'cost_control':'observe_only'})))
            self.event(con, 'model_reserved', {'request_id': rid, 'job_id': job['id'], 'purpose': purpose,
                                             'model': model['model'], **({} if (request_json or {}).get('accounting_mode') == 'tokens-1' else {'rate_version':model.get('rates', {}).get('version')})})
            return {'id': rid, 'state': 'new'}

    def settle_request(self, request_id, *, state, usage=None, response=None, error=None):
        # Replay only this complete local settlement, after rollback/close.
        # A received provider answer must never trigger another HTTP request.
        for attempt in range(2):
            try:
                return self._settle_request_once(request_id, state=state, usage=usage,
                    response=response, error=error, timeout=30 if attempt == 0 else 1)
            except sqlite3.Error as failure:
                code = getattr(failure, 'sqlite_errorcode', None)
                if attempt or code is None or code & 0xff not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise
                time.sleep(.2)

    def _settle_request_once(self, request_id, *, state, usage, response, error, timeout):
        cost = None
        with self.connect(timeout=timeout) as con:
            original = con.execute('SELECT request_json FROM model_requests WHERE id=?', (request_id,)).fetchone()
        token_only = self.config['model'].get('accounting_mode') == 'tokens-1' or (original and json.loads(original[0] or '{}').get('accounting_mode') == 'tokens-1')
        if usage is not None and not token_only:
            rates = self.config['model']['rates']
            cached = usage.get('cached_input_tokens', 0)
            cost = ((usage['input_tokens'] - cached) * rates['input'] +
                    cached * rates['cached_input'] + usage['output_tokens'] * rates['output'] + 999999) // 1_000_000
        with self.transaction(timeout=timeout) as con:
            row = con.execute('SELECT * FROM model_requests WHERE id=?', (request_id,)).fetchone()
            if not row or row['state'] != 'reserved':
                raise ValueError('Request already settled or missing')
            con.execute('''UPDATE model_requests SET state=?,finished=?,usage=?,cost=?,response=?,error=? WHERE id=?''',
                        (state, time.time(), canonical(usage) if usage else None, cost,
                         canonical(response) if response is not None else None, error, request_id))
            self.event(con, 'model_settled', {'request_id': request_id, 'state': state,
                'usage_source': 'synthetic' if self.config['mode']=='synthetic' else 'provider_response',
                **({} if token_only else {'rate_version': self.config['model'].get('rates', {}).get('version'), 'cost_micros': cost})})

    def summary(self, *, final_qualified=0):
        _integer(final_qualified, 'final_qualified')
        with self.connect() as con:
            requests = [dict(row) for row in con.execute('SELECT * FROM model_requests ORDER BY started')]
            jobs = [dict(row) for row in con.execute('SELECT kind,state,COUNT(*) AS count FROM jobs GROUP BY kind,state')]
            resources = [dict(row) for row in con.execute('SELECT kind,SUM(amount) AS used FROM resources GROUP BY kind')]
            metadata={r['id']:dict(r) for r in con.execute('SELECT id,kind,created FROM jobs')}
            events=[dict(row) for row in con.execute("SELECT at,event,detail FROM batch_events WHERE event IN ('job_claimed','job_finished') ORDER BY seq")]
            start = con.execute('SELECT started FROM batch_meta').fetchone()[0]
        covered = sum(row['usage'] is not None for row in requests)
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
        token_overruns = 0
        for row in requests:
            stage=stages[metadata[row['job_id']]['kind']];stage['model_requests']+=1
            stage['request_states'][row['state']]+=1
            usage = json.loads(row['usage']) if row['usage'] else {}
            model = self.config['model']
            if row['error'] == 'reservation_exceeded' or (usage and model and
                    (usage['input_tokens'] > model['reserve_input_tokens'] or usage['output_tokens'] > model['max_completion_tokens'])):
                token_overruns += 1
            reasoning = usage.get('reasoning_tokens')
            if type(reasoning)is int and reasoning>=0:stage['reasoning_tokens_known']+=reasoning
            else:stage['reasoning_usage_unknown_requests']+=1
            stage['known_model_cost_micros']+=row['cost'] or 0
            stage['uncertain_reserved_cost_micros']+=row['reserved_cost'] if row['cost']is None else 0
            if usage:
                for name in ('input_tokens','output_tokens','cached_input_tokens'):stage[name]+=usage[name]
        result = {'schema_version': 'webcollect-batch-summary-1', 'run_id': self.config['run_id'],
                'mode': self.config['mode'], 'jobs': jobs, 'resources': resources,
                'cost_control': 'observe_only', 'max_model_cost_micros': 'NOT_APPLICABLE',
                'monetary_limit_applied': False,
                'cost_reservation_exceeded_requests': sum(r['cost'] is not None and r['cost'] > r['reserved_cost'] for r in requests),
                'token_reservation_exceeded_requests': token_overruns,
                'top_level_visits_attempted':len(visits) if visit_history['history_complete'] else 'UNKNOWN',
                'top_level_visits_recorded_since_accounting_start':len(visits),
                'top_level_visit_history':visit_history,
                'top_level_visit_states':dict(Counter(row['state'] for row in visits)),
                'max_top_level_visits':None,
                'redirect_requests_observed':sum(row['metrics'].get('redirect_request_events',0) for row in visits),
                'subresources_observed':sum(row['metrics'].get('subresource_or_child_frame_request_events',0) for row in visits),
                'visit_accounting_scope':'Each program-dispatched top-level source fetch/page.goto attempt; cached evidence excluded; redirects and subresources separately observed, not all HTTP requests',
                'model_requests': len(requests), 'usage_covered_requests': covered,
                'model_request_states':dict(Counter(r['state'] for r in requests)),
                'retry_requests':sum(r['attempt']>0 for r in requests),
                'stages':dict(stages),
                'stage_report':__import__('webcollect.stage_metering',fromlist=['report']).report(self),
                'usage_coverage': covered/len(requests) if requests else None,
                'known_model_cost_micros': known, 'uncertain_reserved_cost_micros': reserved,
                'model_cost_micros': known if covered == len(requests) else 'UNKNOWN',
                'model_enabled': self.config['model'] is not None,
                'currency': self.config['budget'].get('currency'),
                'rate_version': self.config['model'].get('rates', {}).get('version') if self.config['model'] else None,
                'wall_seconds': elapsed,
                'model_worker_seconds': sum((r['finished']-r['started']) for r in requests if r['finished']),
                'final_qualified': final_qualified,
                'qualified_per_hour': final_qualified/elapsed*3600 if elapsed else None,
                'end_to_end_cost': 'UNKNOWN: infrastructure, discovery and human costs not supplied',
                'unit_cost': None if not final_qualified else 'UNKNOWN',
                'synthetic_results_are_acceptance': False, 'customer_acceptance': 'UNKNOWN'}

        return token_report(result)

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
                       rate_version=self.config['model'].get('rates', {}).get('version'),currency=self.config['budget'].get('currency'))
        # Snapshots are versioned by content; prior cost reports are retained.
        rows = token_report(rows)
        summary = self.summary()
        save_json(directory / ('summary-' + object_sha256(summary)[:16] + '.json'), summary)
        save_json(directory / ('requests-' + object_sha256(rows)[:16] + '.json'), rows)
        visits = self.visits()
        save_json(directory / ('visits-' + object_sha256(visits)[:16] + '.json'), visits)
        return summary


def token_report(value):
    """New reports omit money; stored historical evidence remains untouched."""
    if isinstance(value, list):
        return [token_report(row) for row in value]
    if isinstance(value, dict):
        return {key:token_report(row) for key,row in value.items() if not any(
            term in key for term in ('cost', 'currency', 'rate_version', 'monetary'))}
    return value
