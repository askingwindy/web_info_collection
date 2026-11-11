"""Shared GLM credential health; probe accounting is separate from collection requests.

Only the coordinator probes. UNKNOWN never authorizes replay or account rotation.
Secrets exist only in the transport call, never in persisted health or probe rows.
"""
from contextlib import closing
import hashlib
import http.client
import json
import time
import uuid
import urllib.request
import urllib.error


def model_identity(ledger):
    model = ledger.config['model']
    return hashlib.sha256(json.dumps([model['provider'], model['endpoint'], model['model']]).encode()).hexdigest()


def ensure_schema(con):
    con.execute('''CREATE TABLE IF NOT EXISTS consumer_key_health (
        model_id TEXT, account_id TEXT, status TEXT NOT NULL, checked REAL NOT NULL,
        retry_at REAL, probe_id TEXT, last_success REAL, PRIMARY KEY(model_id,account_id))''')
    con.execute('''CREATE TABLE IF NOT EXISTS consumer_key_probes (
        probe_id TEXT PRIMARY KEY, launch_id TEXT NOT NULL, model_id TEXT NOT NULL,
        account_id TEXT NOT NULL, state TEXT NOT NULL, started REAL NOT NULL,
        finished REAL, usage_json TEXT, provider_code TEXT,
        UNIQUE(launch_id,model_id,account_id))''')


def health_status(code=None, *, success=False):
    if success:
        return 'available'
    return {'1113': 'insufficient_balance', '1302': 'rate_limited',
            '1305': 'model_limited'}.get(str(code), 'unknown')


def record_result(ledger, account, *, success=False, code=None, retry_after=60, probe_id=None):
    status = health_status(code, success=success)
    now = time.time()
    with ledger.transaction() as con:
        ensure_schema(con)
        old = con.execute('SELECT status,last_success FROM consumer_key_health WHERE model_id=? AND account_id=?',
                          (model_identity(ledger), account)).fetchone()
        # Only an explicit successful coordinator probe restores an insolvent key.
        if old and old[0] == 'insufficient_balance' and not (success and probe_id):
            status = 'insufficient_balance'
        con.execute('INSERT OR REPLACE INTO consumer_key_health VALUES(?,?,?,?,?,?,?)',
                    (model_identity(ledger), account, status, now,
                     now + retry_after if status in ('rate_limited', 'model_limited') else None, probe_id,
                     now if success and probe_id else old[1] if old else None))
    return status


def unavailable_accounts(ledger, con, *, historical=(), readonly=False):
    if not readonly:
        ensure_schema(con)
    from .model_credentials import configured_credentials
    # New sessions require a successful probe for this exact model/endpoint.
    unavailable = {account for account, _ in configured_credentials(ledger.config['model'])} | set(historical)
    if readonly and not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='consumer_key_health'").fetchone():
        return unavailable
    for row in con.execute('SELECT account_id,status,checked,retry_at,probe_id,last_success FROM consumer_key_health WHERE model_id=?',
                           (model_identity(ledger),)):
        account, status, checked, retry_at, probe, last_success = row
        eligible = bool(last_success and status != 'insufficient_balance'
                        and (not retry_at or retry_at <= time.time()))
        if eligible:
            later = con.execute("SELECT 1 FROM model_requests WHERE json_extract(request_json,'$.account_id')=? AND finished>? AND json_extract(response,'$.provider_error.provider_code')='1113' LIMIT 1",
                                (account, last_success)).fetchone()
            if not later:
                unavailable.discard(account)
    return unavailable


def pool_available(ledger):
    if not ledger.real_glm:
        return True
    from .model_credentials import configured_credentials
    import sqlite3
    # Availability is a read-only query: do not take a SQLite write lock while
    # other fixed workers are claiming candidates or renewing their leases.
    with closing(sqlite3.connect(ledger.path.as_uri() + '?mode=ro', uri=True, timeout=90)) as con:
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA busy_timeout=90000')
        excluded = unavailable_accounts(ledger, con, historical=ledger._unavailable_model_accounts(con), readonly=True)
    return any(account not in excluded for account, _ in configured_credentials(ledger.config['model']))


def probe_transport(model, secret, request_id):
    """One lightweight request to the configured model and endpoint; no retries."""
    from .model_gateway import native_generation_options
    payload = {'model': model['model'], 'messages': [{'role': 'user', 'content': 'Reply OK.'}],
               **native_generation_options(model, output_limit=min(256, model['max_completion_tokens'])),
               'request_id': request_id}
    request = urllib.request.Request(model['endpoint'], json.dumps(payload).encode(), headers={
        'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=model['timeout_seconds']) as response:
            raw = json.loads(response.read(1048576))
        return {'success': bool(raw.get('choices')), 'usage': raw.get('usage')}
    except urllib.error.HTTPError as error:
        code = None
        try:
            candidate = (json.loads(error.read(65536)).get('error') or {}).get('code')
            if str(candidate) in ('1113', '1302', '1305'):
                code = str(candidate)
        except (ValueError, TypeError, AttributeError, OSError):
            pass
        return {'success': False, 'code': code}
    except (OSError, ValueError, http.client.HTTPException):
        return {'success': False}


def probe_accounts(ledger, launch_id, transport=probe_transport):
    """Coordinator-only, at most once per account/launch; never replay reserved probes."""
    if not ledger.real_glm:
        return []
    from .model_credentials import configured_credentials
    results = []
    for account, secret in configured_credentials(ledger.config['model']):
        probe_id = 'key-probe-' + uuid.uuid4().hex
        with ledger.transaction() as con:
            ensure_schema(con)
            inserted = con.execute('INSERT OR IGNORE INTO consumer_key_probes(probe_id,launch_id,model_id,account_id,state,started) VALUES(?,?,?,?,?,?)',
                                   (probe_id, launch_id, model_identity(ledger), account, 'unknown', time.time())).rowcount
        if not inserted:
            continue
        result = transport(ledger.config['model'], secret, probe_id)
        status = record_result(ledger, account, success=result.get('success', False), code=result.get('code'), probe_id=probe_id)
        with ledger.transaction() as con:
            con.execute('UPDATE consumer_key_probes SET state=?,finished=?,usage_json=?,provider_code=? WHERE probe_id=?',
                        (status, time.time(), json.dumps(result.get('usage')), result.get('code'), probe_id))
        results.append({'account_id': account, 'status': status, 'probe_id': probe_id})
    return results
