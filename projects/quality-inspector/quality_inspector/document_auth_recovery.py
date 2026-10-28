"""One explicitly linked documentary increment after a persisted 401 rejection.

The frozen document lane, its failed request, fee reservation and source-bound
receipt are unchanged. Preparation cannot dispatch: a compatible lane receipt
is issued only after a later successful, persisted authentication diagnostic.
"""
import argparse
from contextlib import contextmanager, closing
from copy import deepcopy
import fcntl
import json
from pathlib import Path
import sqlite3
import time

from jsonschema import Draft202012Validator
from webcollect.batch_core import BatchLedger
from webcollect.model_gateway import parse_content, response_usage
from . import document_text_qc as lane, delivery_pipeline as pipeline

VERSION = 'document-auth-recovery-1'
EVENT = 'document_auth_recovery_increment'
AUTH_VERSION = 'webcollect-document-auth-recovery-authorization-1'
PROOF_VERSION = 'webcollect-model-authentication-evidence-1'


def _ref(path): return pipeline._ref(path)
def _read(path): return pipeline._read(path)
def _digest(value): return pipeline._digest(value)


def _put(path, value):
    path = Path(path)
    if path.exists():
        if _read(path) != value: raise ValueError('Existing recovery artifact differs; preserve it')
    else: lane._write(path, value)


def _implementation():
    return {**lane._implementation(), str(Path(__file__).resolve()): pipeline._sha(__file__)}


def _rows(path, sql, parameters=()):
    path = Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('Original existing SQLite ledger required')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row; con.execute('PRAGMA query_only=ON')
        return [dict(row) for row in con.execute(sql, parameters)]


def _original(path):
    value = lane.verify(path); ledger = pipeline._ledger(value); job = ledger.get(value['job_id'])
    requests = _rows(ledger.path, 'SELECT * FROM model_requests WHERE job_id=? ORDER BY started', (job['id'],))
    if len(requests) != 1: raise ValueError('Recovery requires exactly one original documentary request')
    row = requests[0]
    error = json.loads(row['response'] or '{}').get('provider_error', {})
    if (row['state'] != 'unknown' or row['error'] != 'HTTPError:401' or error.get('http_status') != 401
            or str(error.get('provider_code')) != '1000' or row['finished'] is None
            or job['state'] != 'review_required' or job['attempts'] != 1 or job['result'] is not None):
        raise ValueError('Only the preserved terminal 401/1000 authentication rejection is eligible')
    projection = {key: row[key] for key in ('id', 'job_id', 'purpose', 'attempt', 'state', 'reserved_tokens',
        'reserved_cost', 'started', 'finished', 'usage', 'cost', 'response', 'error')}
    projection['request_json_sha256'] = _digest(json.loads(row['request_json'] or '{}'))
    return value, ledger, job, projection


def _authorization(path, original_path, request):
    value = _read(path)
    if (value.get('schema_version') != AUTH_VERSION or value.get('original_document_receipt') != _ref(original_path)
            or value.get('original_request_id') != request['id'] or type(value.get('maximum_additional_requests')) is not int
            or value['maximum_additional_requests'] != 1
            or value.get('explicit_authentication_recovery') is not True
            or not isinstance(value.get('authorization_source'), str) or not value['authorization_source'].strip()
            or not isinstance(value.get('reason'), str) or not value['reason'].strip()):
        raise ValueError('An exact one-request recovery authority with its actual user/session source is required')
    return value


def _budget(ledger, original_ledger):
    old, new = original_ledger.config, ledger.config
    if ledger.path == original_ledger.path: raise ValueError('Never reset or reuse the failed documentary ledger')
    if (new['mode'] != 'real' or new['model'] != old['model'] or new['budget'] != old['budget']
            or new['run_id'] == old['run_id'] or new['budget']['max_model_requests'] != 1
            or new['budget']['max_job_attempts'] != 1 or new['budget']['max_concurrent_jobs'] != 1):
        raise ValueError('Recovery is exactly one separate explicit increment with the unchanged one-request model/budget')


def _events(ledger, identity):
    return [json.loads(row['detail']) for row in _rows(ledger.path,
        'SELECT detail FROM batch_events WHERE event=?', (EVENT,))
        if json.loads(row['detail']).get('recovery_key') == identity]


@contextmanager
def _file_gate(path):
    path = Path(path)
    if path.is_symlink(): raise ValueError('Recovery lock cannot be a symlink')
    with path.open('a') as stream:
        try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Another operation owns this recovery increment') from None
        try: yield
        finally: fcntl.flock(stream, fcntl.LOCK_UN)


def prepare(ledger, original_receipt, authorization, output):
    original, failed, job, request = _original(original_receipt)
    _authorization(authorization, original_receipt, request); _budget(ledger, failed)
    parent_path = original['parent_receipt']['path']; parent = pipeline.verify(parent_path); parent_ledger = pipeline._ledger(parent)
    identity = _digest({'version': VERSION, 'failed_ledger': str(failed.path), 'failed_config': _digest(failed.config),
                        'job_id': job['id'], 'request_id': request['id']})
    output = Path(output).resolve()
    if any(ledger.path.is_relative_to(root) for root in pipeline._roots(parent)):
        raise ValueError('Recovery ledger must be outside inspected packages')
    # The failed-ledger path is stable even if receipt files are relocated.
    with _file_gate(failed.path.with_name(failed.path.name + '.auth-recovery.prepare.lock')), pipeline._lock(parent_path):
        original, failed, job, current = _original(original_receipt)
        if current != request: raise ValueError('Original rejection changed during recovery preparation')
        existing = _events(parent_ledger, identity)
        if existing:
            event = existing[0]
            if (len(existing) != 1 or event['ledger'] != str(ledger.path)
                    or event['ledger_config_sha256'] != _digest(ledger.config)
                    or event['authorization']['sha256'] != _ref(authorization)['sha256']):
                raise ValueError('This authentication rejection already has its one recovery increment; resume that ledger')
            reference = event['control_receipt']
            pipeline._check_ref(reference)
            ledger.enqueue(lane.KIND, job['payload'])  # recover a crash after linkage but before enqueue
            verify(reference['path'])
            return {'receipt': reference['path'], 'reused': True, 'model_requests_created': 0}
        if any(output.is_relative_to(root) for root in pipeline._roots(parent)):
            raise ValueError('Recovery output must be outside inspected packages')
        value = {'schema_version': VERSION, 'recovery_key': identity, 'original_document_receipt': _ref(original_receipt),
            'original_request': request, 'original_job_id': job['id'], 'original_payload_sha256': _digest(job['payload']),
            'original_document_model_usage': pipeline._usage(failed, {'jobs': {job['id']: {}}, 'mode': 'real'}),
            'original_document_budget': failed.config['budget'], 'authorization': _ref(authorization),
            'ledger': str(ledger.path), 'ledger_config_sha256': _digest(ledger.config),
            'implementation_sha256': _implementation(), 'additional_request_limit': 1,
            'authentication_required_before_dispatch': True, 'credential_change_claimed': False,
            'raw_lane_receipt': str(output / 'authenticated-document-text-receipt.json')}
        value['receipt_sha256'] = _digest(value)
        control = output / 'document-auth-recovery-receipt.json'
        if output.exists() and (not control.is_file() or _read(control) != value):
            raise ValueError('Existing recovery output has another binding; preserve it')
        output.mkdir(parents=True, exist_ok=True)
        _put(control, value)
        event = {'recovery_key': identity, 'control_receipt': _ref(control), 'ledger': str(ledger.path),
                 'ledger_config_sha256': _digest(ledger.config), 'authorization': _ref(authorization),
                 'original_request_id': request['id'], 'original_unknown_charge_preserved': True}
        with parent_ledger.transaction() as con: parent_ledger.event(con, EVENT, event)
        ledger.enqueue(lane.KIND, job['payload'])  # same payload and same job identity; no model dispatch
        verify(control)
        return {'receipt': str(control), 'reused': False, 'model_requests_created': 0,
                'requires_successful_authentication_diagnostic': True}


def verify(receipt_path):
    value = _read(receipt_path)
    if (value.get('schema_version') != VERSION or value.get('receipt_sha256') != _digest(
            {key: item for key, item in value.items() if key != 'receipt_sha256'})
            or value.get('implementation_sha256') != _implementation()):
        raise ValueError('Recovery receipt or implementation changed')
    pipeline._check_ref(value['original_document_receipt']); pipeline._check_ref(value['authorization'])
    original, failed, job, request = _original(value['original_document_receipt']['path'])
    _authorization(value['authorization']['path'], value['original_document_receipt']['path'], request)
    if request != value['original_request'] or job['id'] != value['original_job_id'] or _digest(job['payload']) != value['original_payload_sha256']:
        raise ValueError('Original unknown rejection or documentary payload changed')
    ledger = pipeline._ledger(value); _budget(ledger, failed)
    retry_job = ledger.get(job['id'])
    if retry_job['kind'] != lane.KIND or retry_job['payload'] != job['payload']:
        raise ValueError('Recovery must retain the same original documentary payload and job identity')
    parent = pipeline._ledger(pipeline.verify(original['parent_receipt']['path']))
    events = _events(parent, value['recovery_key'])
    if len(events) != 1 or events[0]['control_receipt'] != _ref(receipt_path):
        raise ValueError('Recovery receipt was not issued by its original parent ledger')
    return value


def _authentication(path, value, *, require_fresh=True):
    proof = _read(path)
    if proof.get('schema_version') != PROOF_VERSION: raise ValueError('Actual persisted authentication evidence required')
    pipeline._check_ref(proof['config']); config = _read(proof['config']['path'])
    metadata = _rows(proof['ledger'], 'SELECT config FROM batch_meta WHERE id=1')
    if len(metadata) != 1 or json.loads(metadata[0]['config']) != config: raise ValueError('Authentication ledger/config mismatch')
    original = lane.verify(value['original_document_receipt']['path']); expected = pipeline._ledger(original).config['model']
    if config.get('mode') != 'real' or any(config.get('model', {}).get(key) != expected.get(key) for key in ('provider', 'model', 'endpoint')):
        raise ValueError('Authentication proof must use the same real provider/model/endpoint')
    records = _rows(proof['ledger'], 'SELECT * FROM model_requests WHERE id=?', (proof['request_id'],))
    if len(records) != 1: raise ValueError('Authentication request is missing')
    row = records[0]; request = json.loads(row['request_json'] or '{}'); response = json.loads(row['response'] or '{}')
    job_rows = _rows(proof['ledger'], 'SELECT state,result FROM jobs WHERE id=?', (row['job_id'],))
    if (row['state'] != 'succeeded' or row['error'] is not None or row['finished'] is None or not value['original_request']['finished'] < row['finished'] <= time.time() + 5
            or require_fresh and time.time() - row['finished'] > 3600 or 'auth' not in row['purpose'].lower()
            or 'diagnostic' not in row['purpose'].lower() or row['usage'] is None
            or len(job_rows) != 1 or job_rows[0]['state'] != 'done'
            or json.loads(job_rows[0]['result'] or 'null') != response.get('result')
            or request.get('provider') != expected['provider'] or request.get('model') != expected['model']
            or response.get('provider_response', {}).get('model') != expected['model']
            or not isinstance(response.get('provider_response', {}).get('choices'), list)
            or not response['provider_response']['choices']):
        raise ValueError('Successful later authentication diagnostic with persisted request/response is required')
    Draft202012Validator(request['schema']).validate(response['result'])
    raw = response['provider_response']; choice = raw['choices'][0]
    parsed, _ = parse_content(choice['message']['content'], expected['provider'])
    if (choice.get('finish_reason') != 'stop' or choice['message'].get('refusal') or parsed != response['result']
            or json.loads(row['usage']) != response_usage(raw, expected['provider'])):
        raise ValueError('Authentication persisted provider response/result/usage disagree')
    later = _rows(proof['ledger'], 'SELECT response FROM model_requests WHERE started>?', (row['finished'],))
    if require_fresh and any(json.loads(item['response'] or '{}').get('provider_error', {}).get('http_status') == 401 for item in later):
        raise ValueError('Authentication was rejected again after this diagnostic')
    all_requests = _rows(proof['ledger'], 'SELECT * FROM model_requests ORDER BY started')
    parent_ledger = pipeline._ledger(pipeline.verify(original['parent_receipt']['path']))
    if (len(all_requests) != 1 or config['budget']['max_model_requests'] != 1
            or Path(proof['ledger']).resolve() in (Path(value['ledger']), pipeline._ledger(original).path, parent_ledger.path)):
        raise ValueError('Authentication must use its own isolated one-request diagnostic ledger')
    complete = all(item['usage'] is not None for item in all_requests)
    usage = {'scope': 'all requests in the explicitly supplied authentication diagnostic ledger', 'mode': 'real',
        'model_requests': len(all_requests), 'known_model_cost_micros': sum(item['cost'] or 0 for item in all_requests),
        'uncertain_reserved_cost_micros': sum(item['reserved_cost'] for item in all_requests if item['cost'] is None),
        'usage_coverage_complete': complete, 'actual_account_debit': 'UNKNOWN'}
    return {'proof': _ref(path), 'config': proof['config'], 'ledger': str(Path(proof['ledger']).resolve()),
        'request_id': row['id'], 'finished': row['finished'], 'request_projection_sha256': _digest({key: row[key] for key in
            ('id', 'job_id', 'purpose', 'state', 'started', 'finished', 'usage', 'cost', 'request_json', 'response')}),
        'diagnostic_ledger_usage': usage,
        'credential_change_claimed': False, 'authentication_scope': 'later successful same-service diagnostic; no claim of future availability'}


@contextmanager
def _gate(receipt_path):
    verify(receipt_path)  # Validate the issued external control before creating a lock file.
    path = Path(receipt_path).resolve().with_suffix('.dispatch.lock')
    with _file_gate(path): yield


def _authentication_events(value):
    original = lane.verify(value['original_document_receipt']['path'])
    parent = pipeline._ledger(pipeline.verify(original['parent_receipt']['path']))
    return [json.loads(row['detail']) for row in _rows(parent.path,
        "SELECT detail FROM batch_events WHERE event='document_auth_recovery_authentication_observed'")
        if json.loads(row['detail']).get('recovery_key') == value['recovery_key']]


def _verify_activation(receipt_path, value):
    clone = lane.verify(value['raw_lane_receipt'])
    if clone.get('authentication_recovery', {}).get('control_receipt') != _ref(receipt_path):
        raise ValueError('Authenticated lane receipt belongs to another recovery increment')
    events = _authentication_events(value)
    if not events: raise ValueError('No authenticated activation event was issued')
    for event in events:
        pipeline._check_ref(event['authentication'])
        snapshot = _read(event['authentication']['path'])
        current = _authentication(snapshot['proof']['path'], value, require_fresh=False)
        if snapshot != current: raise ValueError('Persisted authentication diagnostic changed after activation')
    return events


def _activate(receipt_path, proof_path):
    value = verify(receipt_path); authentication = _authentication(proof_path, value)
    original = lane.verify(value['original_document_receipt']['path']); parent_path = original['parent_receipt']['path']
    parent = pipeline.verify(parent_path); parent_ledger = pipeline._ledger(parent); ledger = pipeline._ledger(value)
    output = Path(receipt_path).resolve().parent
    auth_file = output / ('verified-authentication-' + _digest(authentication) + '.json')
    with pipeline._lock(parent_path):
        verify(receipt_path); _put(auth_file, authentication)
        event = {'recovery_key': value['recovery_key'], 'control_receipt': _ref(receipt_path), 'authentication': _ref(auth_file)}
        with parent_ledger.transaction() as con:
            observed = [json.loads(row['detail']) for row in con.execute(
                "SELECT detail FROM batch_events WHERE event='document_auth_recovery_authentication_observed'")]
            if event not in observed: parent_ledger.event(con, 'document_auth_recovery_authentication_observed', event)
        if Path(value['raw_lane_receipt']).exists():
            _verify_activation(receipt_path, value)
            return value  # fresh evidence is additive; the first authenticated lane receipt stays immutable
        clone = deepcopy(original)
        clone.update(ledger=str(ledger.path), ledger_config_sha256=_digest(ledger.config),
            authentication_recovery={'control_receipt': _ref(receipt_path), 'authentication': _ref(auth_file),
                'original_document_model_usage': value['original_document_model_usage'],
                'original_unknown_request': value['original_request'], 'increment_request_limit': 1})
        clone['evidence_refs'] += [_ref(receipt_path), value['original_document_receipt'], value['authorization'],
            _ref(auth_file), authentication['proof'], authentication['config'], _ref(__file__)]
        clone['receipt_sha256'] = _digest({key: item for key, item in clone.items() if key != 'receipt_sha256'})
        link = {'schema_version': lane.VERSION + '-amendment', 'cache_key': clone['job_id'],
            'semantic_request_sha256': clone['semantic_request_sha256'], 'parent_receipt': original['parent_receipt'],
            'parent_status': original['parent_status'], 'human_history_sha256': original['human_history_sha256'],
            'policy': lane.POLICY, 'ledger': str(ledger.path), 'ledger_config_sha256': _digest(ledger.config),
            'job_id': clone['job_id'], 'explicit_authentication_recovery': _ref(receipt_path),
            'verified_authentication': _ref(auth_file), 'original_unknown_charge_preserved': True}
        with parent_ledger.transaction() as con:
            links = [json.loads(row['detail']) for row in con.execute(
                "SELECT detail FROM batch_events WHERE event='document_text_policy_amendment'")]
            if link not in links: parent_ledger.event(con, 'document_text_policy_amendment', link)
        _put(value['raw_lane_receipt'], clone); lane.verify(value['raw_lane_receipt'])
    return value


def _accounting(value, state, output):
    original = lane.verify(value['original_document_receipt']['path']); failed = pipeline._ledger(original)
    retry = pipeline._ledger(value)
    scopes = {'original_sample_and_legacy_document_pipeline': original['original_bound_model_usage'],
        'original_rejected_document_increment': pipeline._usage(failed, {'jobs': {original['job_id']: {}}, 'mode': 'real'}),
        'explicit_authentication_recovery_increment': pipeline._usage(retry, {'jobs': {value['original_job_id']: {}}, 'mode': 'real'})}
    diagnostics = {_read(event['authentication']['path'])['ledger']: _read(event['authentication']['path'])
                   for event in _authentication_events(value)}
    for index, (_, authentication) in enumerate(sorted(diagnostics.items())):
        scopes['authentication_diagnostic_ledger_' + str(index + 1)] = authentication['diagnostic_ledger_usage']
    report = {'schema_version': VERSION + '-accounting', 'raw_status': _ref(Path(output) / 'status.json'),
        'scope': 'parent pipeline plus original documentary rejection plus explicit recovery plus its authentication diagnostic ledger; excludes other project ledgers',
        'scopes': scopes, 'model_requests': sum(row['model_requests'] for row in scopes.values()),
        'known_model_cost_micros': sum(row['known_model_cost_micros'] for row in scopes.values()),
        'uncertain_reserved_cost_micros': sum(row['uncertain_reserved_cost_micros'] for row in scopes.values()),
        'actual_account_debit': 'UNKNOWN', 'original_unknown_is_zero_cost': False,
        'document_human_pending_count': state['human_document_pending_count'], 'release_ready': state['release_ready']}
    _put(Path(output) / 'recovery-accounting.json', report)
    return {'status': str(Path(output) / 'status.json'), 'accounting': str(Path(output) / 'recovery-accounting.json'),
            'document_review_status': state['document_review_status'], 'human_document_pending_count': 0}


def _recorded_requests(value):
    return _rows(value['ledger'], 'SELECT * FROM model_requests WHERE job_id=? ORDER BY started', (value['original_job_id'],))


def _reconcile_known_success(value):
    """Recover a paid, known response after finish was interrupted; never call HTTP."""
    ledger = pipeline._ledger(value); job = ledger.get(value['original_job_id']); rows = _recorded_requests(value)
    if job['state'] == 'done' or not rows or rows[0]['state'] != 'succeeded': return False
    if len(rows) != 1: raise ValueError('Recovery scope contains more than its one allowed request')
    if job['state'] == 'running' and job['lease'] is not None and job['lease'] >= time.time():
        return False  # Do not steal an active lease, even when its provider response is known.
    row = rows[0]; request = json.loads(row['request_json'] or '{}'); response = json.loads(row['response'] or '{}')
    text, schema = lane._request(job['payload']); model = ledger.config['model']; raw = response.get('provider_response', {})
    if (row['error'] is not None or row['usage'] is None or request.get('text') != text or request.get('schema') != schema
            or request.get('provider') != model['provider'] or request.get('model') != model['model']
            or request.get('images') != [] or not row['purpose'].startswith('document-text-consistency:')
            or raw.get('model') != model['model'] or not raw.get('choices')):
        raise ValueError('Persisted documentary response is not a complete matching successful request')
    choice = raw['choices'][0]; parsed, _ = parse_content(choice['message']['content'], model['provider'])
    if (choice.get('finish_reason') != 'stop' or choice['message'].get('refusal') or parsed != response.get('result')
            or response_usage(raw, model['provider']) != json.loads(row['usage'])):
        raise ValueError('Persisted documentary provider response/result/usage disagree')
    Draft202012Validator(schema).validate(parsed)
    class PersistedResponse:
        def call(self, _job, purpose, actual_text, actual_schema, **_kwargs):
            if purpose != 'document-text-consistency' or actual_text != text or actual_schema != schema:
                raise ValueError('Known response does not match this exact documentary request')
            return parsed
    result = lane._response(job, ledger, PersistedResponse())
    with ledger.transaction() as con:
        current = dict(con.execute('SELECT * FROM jobs WHERE id=?', (job['id'],)).fetchone())
        if (current['state'] != job['state'] or current['owner'] != job['owner'] or current['lease'] != job['lease']
                or current['attempts'] != job['attempts'] or current['result'] is not None
                or current['state'] == 'running' and current['lease'] is not None and current['lease'] >= time.time()):
            raise ValueError('Documentary worker state changed during known-result reconciliation')
        con.execute("UPDATE jobs SET state='done',result=?,owner=NULL,lease=NULL,error=NULL,updated=? WHERE id=?",
                    (json.dumps(result, ensure_ascii=False, sort_keys=True), time.time(), job['id']))
        ledger.event(con, 'document_auth_recovery_known_result_reconciled',
            {'job_id': job['id'], 'request_id': row['id'], 'source_state': job['state'],
             'attempts_preserved': job['attempts'], 'provider_response_sha256': _digest(response), 'new_requests': 0})
    lane._check_result(ledger, ledger.get(job['id']), 'real')
    return True


def run(receipt_path, proof_path, output):
    with _gate(receipt_path):
        value = verify(receipt_path)
        if Path(value['raw_lane_receipt']).exists() and _recorded_requests(value):
            _verify_activation(receipt_path, value)
            _reconcile_known_success(value)
            pipeline._ledger(value).recover()  # expired reservations become UNKNOWN; no resend
            state = lane.status(value['raw_lane_receipt'], output)
            return _accounting(value, state, output)
        value = _activate(receipt_path, proof_path)
        _verify_activation(receipt_path, value)
        state = lane.run(value['raw_lane_receipt'], output)
        verify(receipt_path)
        _verify_activation(receipt_path, value)
        return _accounting(value, state, output)


def status(receipt_path, output):
    with _gate(receipt_path):
        value = verify(receipt_path)
        if not Path(value['raw_lane_receipt']).is_file(): raise ValueError('Recovery has not passed its authentication gate')
        _verify_activation(receipt_path, value)
        _reconcile_known_success(value)
        pipeline._ledger(value).recover()
        state = lane.status(value['raw_lane_receipt'], output)
        return _accounting(value, state, output)


def finalize(receipt_path, status_path, output, *, archive=None):
    with _gate(receipt_path):
        value = verify(receipt_path)
        _verify_activation(receipt_path, value)
        return lane.finalize(value['raw_lane_receipt'], status_path, output, archive=archive)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    for name in ('original-receipt', 'authorization', 'ledger', 'config', 'output'): p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--initialize-ledger', action='store_true')
    for name in ('run', 'status', 'finalize'):
        p = sub.add_parser(name); p.add_argument('--receipt', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
        if name == 'run': p.add_argument('--auth-proof', type=Path, required=True)
        if name == 'finalize': p.add_argument('--status', type=Path, required=True); p.add_argument('--archive', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            original, _, _, _ = _original(args.original_receipt)
            if any(args.ledger.resolve().is_relative_to(root) for root in pipeline._roots(pipeline.verify(original['parent_receipt']['path']))):
                raise ValueError('Recovery ledger cannot be inside inspected packages')
            # A repeated --initialize-ledger validates the existing frozen run;
            # it never replaces config, original start, attempts or charges.
            result = prepare(BatchLedger(args.ledger, _read(args.config), initialize=args.initialize_ledger and not args.ledger.exists()), args.original_receipt, args.authorization, args.output)
        elif args.command == 'run': result = run(args.receipt, args.auth_proof, args.output)
        elif args.command == 'finalize': result = finalize(args.receipt, args.status, args.output, archive=args.archive)
        else: result = status(args.receipt, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (ValueError, OSError, KeyError) as error: parser.exit(2, str(error) + '\n')


if __name__ == '__main__': raise SystemExit(main())
