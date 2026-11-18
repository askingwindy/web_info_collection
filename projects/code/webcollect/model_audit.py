"""Read-only request attribution and rate-based cost audit, never a cash bill.

Related samples do not imply allocation. Explicit equal-weight allocations form
a separate estimated view; original shared requests are counted exactly once.
"""
from webcollect.sqlite_connection import raw_connect as workspace_connect
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
from fractions import Fraction
import hashlib
import io
from webcollect import workspace_json as json
import math
from pathlib import Path
import re
import sqlite3

UNKNOWN = 'UNKNOWN'
TABLES = ('batch_meta', 'jobs', 'model_requests')
TOKEN_FIELDS = ('input_tokens', 'output_tokens', 'cached_input_tokens', 'image_tokens',
                'reasoning_tokens', 'provider_total_tokens')
ERROR_TYPES = frozenset({'AssertionError', 'AttributeError', 'BudgetStop', 'ConnectionError',
    'ConnectionRefusedError', 'ConnectionResetError', 'ContentTooShortError', 'EOFError',
    'FileNotFoundError', 'HTTPError', 'JSONDecodeError', 'KeyError', 'ModelRateWait', 'OSError',
    'OutcomeUnknown', 'OverflowError', 'PermissionError', 'SchemaError', 'TimeoutError',
    'TypeError', 'URLError', 'UnicodeDecodeError', 'ValidationError', 'ValueError', 'reservation_exceeded'})


def _loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Non-finite JSON number')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _obj_sha(value):
    return _sha(_json(value).encode())


def _int(value):
    return type(value) is int and value >= 0


def _required_int(value, name):
    if not _int(value):
        raise ValueError(name + ' must be a nonnegative integer')
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + ' must be a nonempty string')
    return value


def _declared_text(value):
    return value if isinstance(value, str) and value.strip() else UNKNOWN


def _identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/@+\-]{0,255}', value) else UNKNOWN


def _metadata_sha(value):
    return _obj_sha(value) if value is not None else UNKNOWN


def _purpose_label(value):
    patterns = (
        (r'site-screen-v\d+', 'site-screen'),
        (r'task-generation-[A-Za-z0-9_.-]+', 'task-generation'),
        (r'visual-part-\d+', 'visual-part'),
        (r'visual-whole-continuity', 'visual-whole-continuity'),
        (r'difference-\d+-part-\d+', 'difference-part'),
        (r'difference-\d+-whole', 'difference-whole'),
        (r'delivery-documents', 'delivery-documents'),
        (r'image-smoke', 'model-smoke'))
    for pattern, label in patterns:
        if isinstance(value, str) and re.fullmatch(pattern + r':[a-f0-9]{64}', value):
            return label
    return UNKNOWN


def _file(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Existing input file required')
    return path


def read_snapshot(ledger):
    """Hash all columns of the three accounting tables in one RO transaction."""
    ledger = _file(ledger)
    with closing(workspace_connect(ledger.as_uri() + '?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        tables = {}
        for table in TABLES:
            schema = [list(r) for r in con.execute('PRAGMA table_info(' + table + ')')]
            if not schema:
                raise ValueError('Missing accounting table: ' + table)
            rows = [dict(r) for r in con.execute('SELECT * FROM ' + table + ' ORDER BY id')]
            tables[table] = {'schema': schema, 'rows': rows}
        con.rollback()
    meta = tables['batch_meta']['rows']
    if len(meta) != 1 or meta[0]['id'] != 1:
        raise ValueError('Expected one frozen batch configuration')
    config = _loads(meta[0]['config'])
    return {'tables': tables, 'config': config,
            'binding': {'logical_sha256': _obj_sha(tables), 'config_sha256': _obj_sha(config)}}


def fingerprint(ledger):
    snapshot = read_snapshot(ledger)
    return {'schema_version': 'model-ledger-binding', **snapshot['binding'],
            'fingerprint_scope': list(TABLES),
            'model_requests': len(snapshot['tables']['model_requests']['rows'])}


def _sample_ids(value):
    if not isinstance(value, list) or not value or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError('Explicit nonempty sample ID list required')
    if len(value) != len(set(value)):
        raise ValueError('Repeated sample ID')
    return sorted(value)


def validate_manifest(manifest, snapshot):
    required = {'schema_version', 'ledger_binding', 'jobs'}
    if (not isinstance(manifest, dict) or not required <= set(manifest)
            or set(manifest) - required - {'request_classifications'}
            or manifest['schema_version'] not in ('model-attribution', 'webcollect-model-attribution-1')):
        raise ValueError('Invalid attribution manifest schema')
    if manifest['ledger_binding'] != snapshot['binding']:
        raise ValueError('Attribution ledger/config binding drift')
    if not isinstance(manifest['jobs'], dict):
        raise ValueError('Job attribution mapping required')
    known = {r['id'] for r in snapshot['tables']['jobs']['rows']}
    for job_id, value in manifest['jobs'].items():
        if job_id not in known:
            raise ValueError('Attribution references unknown job ID')
        fields = {'scope', 'scope_id', 'classification'}
        if (not isinstance(value, dict) or not fields <= set(value)
                or set(value) - fields - {'related_sample_ids', 'allocation'}):
            raise ValueError('Invalid job attribution fields')
        if value['scope'] not in ('sample', 'site', 'batch', 'engineering'):
            raise ValueError('Invalid attribution scope')
        _text(value['scope_id'], 'scope_id'); _text(value['classification'], 'classification')
        if 'related_sample_ids' in value:
            ids = _sample_ids(value['related_sample_ids'])
            if value['scope'] == 'sample' and ids != [value['scope_id']]:
                raise ValueError('Direct sample scope must identify one sample')
        if 'allocation' in value:
            allocation = value['allocation']
            if (value['scope'] not in ('site', 'batch') or not isinstance(allocation, dict)
                    or set(allocation) != {'method', 'sample_ids'} or allocation['method'] != 'equal_weight'):
                raise ValueError('Only explicit site/batch equal-weight allocation is supported')
            _sample_ids(allocation['sample_ids'])
    overrides = manifest.get('request_classifications', {})
    requests = {r['id'] for r in snapshot['tables']['model_requests']['rows']}
    if not isinstance(overrides, dict):
        raise ValueError('Invalid request classification mapping')
    for request_id, value in overrides.items():
        if (request_id not in requests or not isinstance(value, dict) or 'classification' not in value
                or set(value) - {'classification', 'note'}):
            raise ValueError('Request override may change only classification and note')
        _text(value['classification'], 'request classification')
        if 'note' in value:
            _text(value['note'], 'classification note')


def _usage(value):
    value = _loads(value) if value is not None else {}
    if not isinstance(value, dict):
        raise ValueError('Usage must be a JSON object')
    if any(k in value and value[k] is not None and not _int(value[k]) for k in TOKEN_FIELDS):
        raise ValueError('Usage counts must be nonnegative integers, never booleans')
    result = {key: value.get(key) if _int(value.get(key)) else UNKNOWN for key in TOKEN_FIELDS}
    if (_int(result['input_tokens']) and _int(result['cached_input_tokens'])
            and result['cached_input_tokens'] > result['input_tokens']):
        result['cached_input_tokens'] = UNKNOWN
    return result, value


def _provider_token_details(usage, response):
    counts = response.get('usage', {})
    counts = counts if isinstance(counts, dict) else {}
    details = counts.get('completion_tokens_details', {})
    details = details if isinstance(details, dict) else {}
    observed = {'reasoning_tokens': details.get('reasoning_tokens'), 'provider_total_tokens': counts.get('total_tokens')}
    consistency = {}
    for key, value in observed.items():
        status = UNKNOWN if value is None else 'MATCH' if _int(value) else 'INCONSISTENT'
        if _int(value):
            if key == 'reasoning_tokens':
                valid = value <= usage['output_tokens'] if _int(usage['output_tokens']) else None
            else:
                valid = value == usage['input_tokens'] + usage['output_tokens'] if all(_int(usage[k]) for k in TOKEN_FIELDS[:2]) else None
            status = UNKNOWN if valid is None else 'MATCH' if valid else 'INCONSISTENT'
        usage[key] = value if _int(value) and status != 'INCONSISTENT' else UNKNOWN
        consistency[key] = status
    return consistency


def _evidence(request):
    parsed = _loads(request['request_json']) if request.get('request_json') is not None else {}
    if not isinstance(parsed, dict):
        raise ValueError('Request evidence must be an object')
    images = parsed.get('images', [])
    if not isinstance(images, list):
        raise ValueError('Invalid image evidence list')
    result = {'request_json_sha256': _sha(request['request_json'].encode()) if request.get('request_json') is not None else UNKNOWN,
              'prompt_sha256': _sha(parsed['text'].encode()) if isinstance(parsed.get('text'), str) else UNKNOWN,
              'system_sha256': _sha(parsed['system'].encode()) if isinstance(parsed.get('system'), str) else UNKNOWN,
              'schema_sha256': _obj_sha(parsed['schema']) if 'schema' in parsed else UNKNOWN,
              'images': [], 'image_files_verified': False}
    if parsed.get('cost_control') == 'observe_only':
        result['dispatch_cost_control'] = 'observe_only'
    for image in images:
        if not isinstance(image, dict):
            raise ValueError('Invalid original-image reference')
        checksum = image.get('sha256')
        result['images'].append({'evidence_sha256_recorded': checksum if isinstance(checksum, str)
                                 and len(checksum) == 64 and all(c in '0123456789abcdef' for c in checksum) else UNKNOWN,
                                 'path_sha256': _sha(image['path'].encode()) if isinstance(image.get('path'), str) else UNKNOWN})
    return result


def _aggregate(rows):
    rows = list(rows)
    known = sum(r['known_estimated_cost_micros'] for r in rows if _int(r['known_estimated_cost_micros']))
    unknown_cost = sum(not _int(r['known_estimated_cost_micros']) for r in rows)
    result = {'request_count': len(rows), 'known_estimated_cost_micros': known,
              'unknown_cost_requests': unknown_cost,
              'estimated_cost_micros': UNKNOWN if unknown_cost else known,
              'uncertain_reserved_cost_micros': sum(r['uncertain_reserved_cost_micros'] for r in rows)}
    for field in TOKEN_FIELDS:
        values = [r['usage'][field] for r in rows]
        subtotal = sum(v for v in values if _int(v)); missing = sum(not _int(v) for v in values)
        result[field] = UNKNOWN if missing else subtotal
        result['known_' + field] = subtotal
        result[field + '_unknown_requests'] = missing
    return result


def _split(value, count, index):
    return value // count + (index < value % count) if _int(value) else UNKNOWN


def _attribution_views(rows):
    stages = defaultdict(list); scopes = defaultdict(list); direct = defaultdict(list); allocated = defaultdict(list)
    retained = []
    for row in rows:
        stages[row['job_kind']].append(row)
        scopes[(row['scope'], row['scope_id'], row['classification'])].append(row)
        if row['scope'] == 'sample':
            direct[row['scope_id']].append(row)
        elif row['allocation']:
            samples = _sample_ids(row['allocation']['sample_ids'])
            for index, sample in enumerate(samples):
                part = {**row, 'known_estimated_cost_micros': _split(row['known_estimated_cost_micros'], len(samples), index),
                        'uncertain_reserved_cost_micros': _split(row['uncertain_reserved_cost_micros'], len(samples), index),
                        'usage': {k: _split(row['usage'][k], len(samples), index) for k in TOKEN_FIELDS},
                        'request_equivalent': Fraction(1, len(samples))}
                if row['token_consistency']['provider_total_tokens'] == 'MATCH':
                    part['usage']['provider_total_tokens'] = part['usage']['input_tokens'] + part['usage']['output_tokens']
                allocated[sample].append(part)
        else:
            retained.append(row)
    samples = []
    for sample in sorted(set(direct) | set(allocated)):
        equivalent = sum((r['request_equivalent'] for r in allocated[sample]), Fraction())
        samples.append({'sample_id': sample, 'direct': _aggregate(direct[sample]),
                        'shared_reference_count': len(allocated[sample]),
                        'shared_request_equivalent_numerator': equivalent.numerator,
                        'shared_request_equivalent_denominator': equivalent.denominator,
                        'allocated_shared_estimate': _aggregate(allocated[sample]),
                        'combined_explicit_estimate': _aggregate([*direct[sample], *allocated[sample]]),
                        'allocation_is_estimate': bool(allocated[sample]),
                        'allocated_tokens_are_provider_sample_measurements': False})
    totals = _aggregate(rows)
    reclassified = [r for group in direct.values() for r in group] + [r for group in allocated.values() for r in group] + retained
    conserved = {k: _aggregate(reclassified)[k] == totals[k] for k in
                 ('known_estimated_cost_micros', 'uncertain_reserved_cost_micros', *('known_' + f for f in TOKEN_FIELDS))}
    equivalents = sum(len(v) for v in direct.values()) + sum((r['request_equivalent'] for v in allocated.values() for r in v), Fraction()) + len(retained)
    conserved['request_equivalents'] = equivalents == len(rows)
    if not all(conserved.values()):
        raise ValueError('Attribution/allocation failed conservation')
    return {'samples': samples, 'stages': [{'job_kind': k, **_aggregate(v)} for k, v in sorted(stages.items())],
            'scopes': [{'scope': k[0], 'scope_id': k[1], 'classification': k[2], **_aggregate(v)} for k, v in sorted(scopes.items())],
            'totals': totals, 'retained': retained, 'conservation': conserved, 'direct': direct, 'allocated': allocated}


def build_audit(snapshot, manifest):
    validate_manifest(manifest, snapshot)
    config = snapshot['config']; model = config.get('model') or {}; rates = model.get('rates') or {}
    currency = _declared_text(config.get('budget', {}).get('currency'))
    jobs = {r['id']: r for r in snapshot['tables']['jobs']['rows']}
    rows = []
    for request in snapshot['tables']['model_requests']['rows']:
        job = jobs.get(request['job_id'], {})
        binding = manifest['jobs'].get(request['job_id'], {'scope': 'UNATTRIBUTED', 'scope_id': 'UNATTRIBUTED',
                                                          'classification': 'UNATTRIBUTED'})
        usage, raw_usage = _usage(request.get('usage'))
        known = request.get('cost') if request.get('cost') is not None else UNKNOWN
        if known != UNKNOWN:
            _required_int(known, 'stored cost')
        reserved = _required_int(request['reserved_cost'], 'reserved cost')
        recomputed = UNKNOWN
        if all(_int(usage[k]) for k in TOKEN_FIELDS[:3]) and all(_int(rates.get(k)) for k in ('input', 'cached_input', 'output')):
            recomputed = ((usage['input_tokens'] - usage['cached_input_tokens']) * rates['input']
                          + usage['cached_input_tokens'] * rates['cached_input']
                          + usage['output_tokens'] * rates['output'] + 999999) // 1000000
        if _int(known) and _int(recomputed) and known != recomputed:
            raise ValueError('Stored/recomputed rate-based cost mismatch for request ' + request['id'])
        started, finished = request['started'], request.get('finished')
        if (type(started) not in (int, float) or not math.isfinite(started)
                or finished is not None and (type(finished) not in (int, float) or not math.isfinite(finished) or finished < started)):
            raise ValueError('Invalid request timing')
        override = manifest.get('request_classifications', {}).get(request['id'], {})
        response = _loads(request['response']) if request.get('response') is not None else {}
        provider_response = response.get('provider_response', {}) if isinstance(response, dict) else {}
        if not isinstance(provider_response, dict):
            provider_response = {}
        token_consistency = _provider_token_details(usage, provider_response)
        error = request.get('error')
        provider_metadata = {'provider': model.get('provider'), 'configured_model': model.get('model'),
                             'returned_model': raw_usage.get('returned_model') or provider_response.get('model'),
                             'provider_request_id': raw_usage.get('provider_request_id') or provider_response.get('id')}
        row = {'request_id': request['id'], 'job_id': request['job_id'], 'job_kind': job.get('kind', UNKNOWN),
               'job_state': job.get('state', UNKNOWN), 'purpose': _purpose_label(request['purpose']),
               'purpose_sha256': _sha(request['purpose'].encode()) if isinstance(request['purpose'], str) else UNKNOWN,
               'attempt': request['attempt'],
               'request_state': request['state'],
               'error_type': None if error in (None, '') else error if isinstance(error, str) and error in ERROR_TYPES else 'REDACTED_ERROR',
               'error_sha256': _sha(error.encode()) if isinstance(error, str) else UNKNOWN,
               **{k: _identifier(v) for k, v in provider_metadata.items()},
               'provider_metadata_sha256': {k: _metadata_sha(v) for k, v in provider_metadata.items()},
               'provider_response_recorded': bool(provider_response),
               'started_at_unix': started, 'finished_at_unix': finished if finished is not None else UNKNOWN,
               'duration_seconds': finished - started if finished is not None else UNKNOWN,
               'usage': usage, 'token_consistency': token_consistency,
               'known_estimated_cost_micros': known, 'recomputed_cost_micros': recomputed,
               'cost_reconciliation': 'MATCH' if _int(known) and _int(recomputed) else UNKNOWN,
               'reserved_cost_micros': reserved, 'reserved_tokens': _required_int(request['reserved_tokens'], 'reserved tokens'),
               'uncertain_reserved_cost_micros': reserved if known == UNKNOWN else 0,
               'exceeded_request_reservation': _int(known) and known > reserved,
               'currency': currency, 'rate_unit': _declared_text(rates.get('unit')),
               'rate_basis': _declared_text(rates.get('basis')),
               'rate_source': _declared_text(rates.get('source')),
               'rate_time': _declared_text(rates.get('time')),
               'rates_micros_per_million_tokens': {k: rates[k] if _int(rates.get(k)) else UNKNOWN for k in ('input', 'cached_input', 'output')},
               'scope': binding['scope'], 'scope_id': binding['scope_id'],
               'classification': override.get('classification', binding['classification']),
               'classification_note': override.get('note', ''),
               'related_sample_ids': binding.get('related_sample_ids', []), 'allocation': binding.get('allocation'),
               'evidence': _evidence(request)}
        rows.append(row)
        _required_int(row['attempt'], 'zero-based request attempt')
    views = _attribution_views(rows)
    totals, retained, conserved = views['totals'], views['retained'], views['conservation']
    metered = sum(r['evidence'].get('dispatch_cost_control') == 'observe_only' for r in rows)
    # A retained request without a marker predates the metering-only dispatch policy.
    config_budget = config.get('budget', {})
    raw_budget = config_budget.get('max_model_cost_micros', UNKNOWN)
    cost_control = ('observe_only' if metered or not rows or raw_budget in (None, UNKNOWN)
                    else config_budget.get('cost_control', 'capped'))
    if cost_control not in ('capped', 'observe_only'):
        raise ValueError('Unsupported accounting cost-control mode')
    budget = 'NOT_APPLICABLE' if cost_control == 'observe_only' else raw_budget if _int(raw_budget) else UNKNOWN
    summary = {'ledger_totals': totals, 'request_states': dict(Counter(r['request_state'] for r in rows)),
               'execution_mode': config.get('mode') if config.get('mode') in ('real', 'synthetic') else UNKNOWN,
               'metered_dispatches': metered, 'unmarked_historical_requests': len(rows) - metered,
               'cost_control': cost_control, 'monetary_limit_applied': bool(model) and cost_control == 'capped',
               'retry_request_count': sum(r['attempt'] > 0 for r in rows),
               'retry_request_count_basis': 'Zero-based attempt > 0 only; changed job/prompt identities are not inferred retries',
               'request_count_basis': 'One retained model_requests reservation/attempt row, including invalid, reserved and unknown outcomes',
               'provider_response_recorded_count': sum(r['provider_response_recorded'] for r in rows),
               'actual_network_dispatch_count': UNKNOWN, 'local_cached_result_reuse_count': UNKNOWN,
               'token_inconsistency_requests': sum('INCONSISTENT' in r['token_consistency'].values() for r in rows),
               'reasoning_tokens_are_output_subset': True,
               'provider_total_tokens_are_input_plus_output': True,
               'token_accounting_note': 'Reasoning is a subset of output, cached/image tokens are input subsets, and provider total is input plus output. These columns are not additional token charges.',
               'request_reservation_exceeded_count': sum(r['exceeded_request_reservation'] for r in rows),
               'budget_max_model_cost_micros': budget,
               'known_cost_exceeds_budget': ('NOT_APPLICABLE' if cost_control == 'observe_only' else
                                             totals['known_estimated_cost_micros'] > budget if _int(budget) else UNKNOWN),
               'known_plus_uncertain_reservation_exceeds_budget': ('NOT_APPLICABLE' if cost_control == 'observe_only' else
                     totals['known_estimated_cost_micros'] + totals['uncertain_reserved_cost_micros'] > budget if _int(budget) else UNKNOWN),
               'unattributed': _aggregate(r for r in rows if r['scope'] == 'UNATTRIBUTED'),
               'retained_non_sample_scopes': _aggregate(retained), 'conservation': conserved,
               'currency': currency, 'cash_deducted_micros': UNKNOWN,
               'cost_basis': 'Configured-rate estimate from recorded token usage; the actual prices and their unit/basis/source/time are retained, not independently verified; not a provider bill or cash deduction',
               'aggregation_scope': 'One frozen ledger/model/billing currency; no cross-currency summation',
               'attribution_basis': 'Explicit manifest declaration; semantic job/sample relationships are not inferred or automatically verified',
               'allocation_warning': 'Shared reference counts are not new API calls; allocated costs/tokens and request equivalents are estimates. Never add shared scope totals to allocated sample totals.'}
    return {'schema_version': 'model-audit', 'requests': rows, 'sample_summaries': views['samples'],
            'stages': views['stages'], 'scopes': views['scopes'],
            'summary': summary}


def _flat(value, prefix=''):
    result = {}
    for key, item in value.items():
        name = prefix + key
        if isinstance(item, dict):
            result.update(_flat(item, name + '.'))
        else:
            result[name] = _json(item) if isinstance(item, list) else item
    return result


def _csv(rows, empty_columns=()):
    rows = [_flat(r) for r in rows]
    columns = sorted({k for r in rows for k in r}) if rows else list(empty_columns)
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: "'" + v if isinstance(v, str) and re.match(r'^\s*[=+\-@]', v) else v for k, v in row.items()})
    return buffer.getvalue()


def export_audit(ledger, attribution, output):
    ledger, attribution = _file(ledger), _file(attribution)
    if Path(output).is_symlink():
        raise ValueError('Output cannot be a symlink')
    output = Path(output).resolve()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError('Output must be a new directory in an existing parent')
    if output in (ledger, attribution, ledger.parent, attribution.parent):
        raise ValueError('Output cannot overwrite an input or input directory')
    manifest_bytes = attribution.read_bytes(); manifest = _loads(manifest_bytes.decode())
    snapshot = read_snapshot(ledger); audit = build_audit(snapshot, manifest)
    audit['source'] = {'ledger_path': str(ledger), **snapshot['binding'],
                       'execution_mode': audit['summary']['execution_mode'],
                       'cost_control': audit['summary']['cost_control'],
                       'fingerprint_scope': list(TABLES), 'attribution_sha256': _sha(manifest_bytes)}
    contents = {'audit.json': json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n',
                'summary.json': json.dumps({'schema_version': audit['schema_version'], 'source': audit['source'], **audit['summary']}, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'}
    for name, key in [('requests.csv', 'requests'), ('sample-summary.csv', 'sample_summaries'),
                      ('stages.csv', 'stages'), ('scopes.csv', 'scopes')]:
        empty = {'requests': ('request_id', 'job_id', 'request_state', 'job_state'),
                 'sample_summaries': ('sample_id', 'direct.request_count', 'shared_reference_count',
                                      'shared_request_equivalent_numerator', 'shared_request_equivalent_denominator'),
                 'stages': ('job_kind', 'request_count'), 'scopes': ('scope', 'scope_id', 'request_count')}
        contents[name] = _csv(audit[key], empty[key])
    if attribution.read_bytes() != manifest_bytes or read_snapshot(ledger)['binding'] != snapshot['binding']:
        raise ValueError('Source or attribution changed during audit; no output published')
    output.mkdir(exist_ok=False)
    for name, content in contents.items():
        with (output / name).open('x', encoding='utf-8', newline='') as target:
            target.write(content)
    return audit


def _keys(value, fields, name):
    if not isinstance(value, dict) or not set(fields) <= set(value):
        raise ValueError('Missing required ' + name + ' fields')


def _same(actual, expected, name):
    if _json(actual) != _json(expected):
        raise ValueError('Audit conservation/integrity mismatch: ' + name)


def validate_exported_audit(audit):
    """Validate the exported arithmetic, not the unavailable original database."""
    _keys(audit, ('schema_version', 'source', 'requests', 'sample_summaries', 'stages', 'scopes', 'summary'), 'audit')
    if audit['schema_version'] not in ('model-audit', 'webcollect-model-audit-1'):
        raise ValueError('Unsupported audit schema')
    source, summary = audit['source'], audit['summary']
    _keys(source, ('logical_sha256', 'config_sha256', 'attribution_sha256', 'execution_mode', 'fingerprint_scope'), 'source')
    for key in ('logical_sha256', 'config_sha256', 'attribution_sha256'):
        if not isinstance(source[key], str) or not re.fullmatch(r'[a-f0-9]{64}', source[key]):
            raise ValueError('Invalid source binding hash')
    _same(source['fingerprint_scope'], list(TABLES), 'fingerprint scope')
    _keys(summary, ('ledger_totals', 'request_states', 'retry_request_count', 'unattributed',
                    'retained_non_sample_scopes', 'conservation', 'currency', 'execution_mode',
                    'provider_response_recorded_count'), 'summary')
    _text(summary['currency'], 'billing currency')
    cost_control = summary.get('cost_control', 'capped')
    if cost_control not in ('capped', 'observe_only'):
        raise ValueError('Invalid audit cost-control mode')
    if 'cost_control' not in source and cost_control != 'capped':
        raise ValueError('Legacy source without cost_control can only be capped')
    if 'cost_control' in source:
        _same(source['cost_control'], cost_control, 'cost-control mode')
    budget = summary.get('budget_max_model_cost_micros', UNKNOWN)
    if cost_control == 'observe_only':
        if 'cost_control' not in summary or 'cost_control' not in source:
            raise ValueError('Observe-only mode must be explicit in source and summary')
        for key, expected in (('budget_max_model_cost_micros', 'NOT_APPLICABLE'), ('monetary_limit_applied', False),
                              ('known_cost_exceeds_budget', 'NOT_APPLICABLE'),
                              ('known_plus_uncertain_reservation_exceeds_budget', 'NOT_APPLICABLE')):
            _same(summary.get(key), expected, 'observe-only ' + key)
    else:
        if budget != UNKNOWN and not _int(budget):
            raise ValueError('Capped monetary limit must be an integer or UNKNOWN, never NOT_APPLICABLE')
        if 'monetary_limit_applied' in summary:
            if _int(budget):
                _same(summary['monetary_limit_applied'], True, 'capped monetary_limit_applied')
            elif type(summary['monetary_limit_applied']) is not bool:
                raise ValueError('Invalid legacy monetary-limit flag')
    if source['execution_mode'] not in ('real', 'synthetic', UNKNOWN):
        raise ValueError('Invalid execution mode')
    _same(summary['execution_mode'], source['execution_mode'], 'execution mode')
    if not isinstance(audit['requests'], list):
        raise ValueError('Audit request list required')
    required = ('request_id', 'job_id', 'job_kind', 'job_state', 'request_state', 'attempt', 'usage',
                'known_estimated_cost_micros', 'recomputed_cost_micros', 'cost_reconciliation',
                'reserved_cost_micros', 'uncertain_reserved_cost_micros', 'currency',
                'rates_micros_per_million_tokens', 'scope', 'scope_id', 'classification',
                'related_sample_ids', 'allocation', 'token_consistency', 'provider_response_recorded')
    ids = set()
    for row in audit['requests']:
        _keys(row, required, 'request')
        for key in ('request_id', 'job_id', 'job_kind'):
            if _identifier(row[key]) == UNKNOWN and row[key] != UNKNOWN:
                raise ValueError('Invalid request identifier')
        if row['request_id'] in ids:
            raise ValueError('Duplicate audit request ID')
        ids.add(row['request_id'])
        if row['request_state'] not in ('reserved', 'succeeded', 'invalid_response', 'unknown'):
            raise ValueError('Unsupported request state')
        if row['job_state'] not in ('queued', 'running', 'done', 'failed', 'review_required', UNKNOWN):
            raise ValueError('Unsupported job state')
        _required_int(row['attempt'], 'attempt')
        if type(row['provider_response_recorded']) is not bool:
            raise ValueError('Invalid provider-response observation flag')
        _same(row['currency'], summary['currency'], 'mixed billing currencies')
        if row['scope'] not in ('sample', 'site', 'batch', 'engineering', 'UNATTRIBUTED'):
            raise ValueError('Unsupported request scope')
        _text(row['scope_id'], 'scope ID'); _text(row['classification'], 'classification')
        if not isinstance(row['related_sample_ids'], list) or any(not isinstance(v, str) or not v.strip() for v in row['related_sample_ids']):
            raise ValueError('Invalid related sample IDs')
        if len(set(row['related_sample_ids'])) != len(row['related_sample_ids']):
            raise ValueError('Repeated related sample ID')
        allocation = row['allocation']
        if allocation is not None:
            if (row['scope'] not in ('site', 'batch') or not isinstance(allocation, dict)
                    or set(allocation) != {'method', 'sample_ids'} or allocation['method'] != 'equal_weight'):
                raise ValueError('Invalid shared allocation')
            _sample_ids(allocation['sample_ids'])
        _keys(row['usage'], TOKEN_FIELDS, 'usage')
        for key in TOKEN_FIELDS:
            if row['usage'][key] != UNKNOWN:
                _required_int(row['usage'][key], key)
        usage = row['usage']
        if all(_int(usage[k]) for k in ('cached_input_tokens', 'input_tokens')) and usage['cached_input_tokens'] > usage['input_tokens']:
            raise ValueError('Cached tokens exceed input')
        if all(_int(usage[k]) for k in ('image_tokens', 'input_tokens')) and usage['image_tokens'] > usage['input_tokens']:
            raise ValueError('Image tokens exceed input')
        if all(_int(usage[k]) for k in ('reasoning_tokens', 'output_tokens')) and usage['reasoning_tokens'] > usage['output_tokens']:
            raise ValueError('Reasoning tokens exceed output')
        if all(_int(usage[k]) for k in ('provider_total_tokens', 'input_tokens', 'output_tokens')) and usage['provider_total_tokens'] != usage['input_tokens'] + usage['output_tokens']:
            raise ValueError('Provider total tokens mismatch')
        _keys(row['token_consistency'], ('reasoning_tokens', 'provider_total_tokens'), 'token consistency')
        for key, state in row['token_consistency'].items():
            if state not in ('MATCH', 'INCONSISTENT', UNKNOWN) or state == 'INCONSISTENT' and usage.get(key) != UNKNOWN:
                raise ValueError('Invalid token consistency state')
            compared = ('output_tokens',) if key == 'reasoning_tokens' else ('input_tokens', 'output_tokens')
            if state == 'MATCH' and not all(_int(usage.get(k)) for k in (key, *compared)):
                raise ValueError('Invalid token consistency MATCH on unknown values')
        known, reserved = row['known_estimated_cost_micros'], row['reserved_cost_micros']
        if known != UNKNOWN:
            _required_int(known, 'known estimated cost')
        _required_int(reserved, 'reserved cost')
        _same(row['uncertain_reserved_cost_micros'], reserved if known == UNKNOWN else 0, 'uncertain reservation')
        rates = row['rates_micros_per_million_tokens']
        _keys(rates, ('input', 'cached_input', 'output'), 'rates')
        for value in rates.values():
            if value != UNKNOWN:
                _required_int(value, 'rate')
        recomputed = UNKNOWN
        if all(_int(usage[k]) for k in TOKEN_FIELDS[:3]) and all(_int(rates[k]) for k in ('input', 'cached_input', 'output')):
            recomputed = ((usage['input_tokens'] - usage['cached_input_tokens']) * rates['input']
                          + usage['cached_input_tokens'] * rates['cached_input']
                          + usage['output_tokens'] * rates['output'] + 999999) // 1000000
        _same(row['recomputed_cost_micros'], recomputed, 'request rate recomputation')
        if _int(known) and _int(recomputed) and known != recomputed:
            raise ValueError('Request cost differs from rates')
        _same(row['cost_reconciliation'], 'MATCH' if _int(known) and _int(recomputed) else UNKNOWN, 'request cost reconciliation')
    views = _attribution_views(audit['requests'])
    if cost_control == 'capped':
        for key, expected in (
                ('known_cost_exceeds_budget', views['totals']['known_estimated_cost_micros'] > budget if _int(budget) else UNKNOWN),
                ('known_plus_uncertain_reservation_exceeds_budget',
                 views['totals']['known_estimated_cost_micros'] + views['totals']['uncertain_reserved_cost_micros'] > budget if _int(budget) else UNKNOWN)):
            _same(summary.get(key, UNKNOWN), expected, 'capped ' + key)
    for key, expected in (('sample_summaries', views['samples']), ('stages', views['stages']), ('scopes', views['scopes'])):
        _same(audit[key], expected, key)
    for key, expected in (('ledger_totals', views['totals']), ('conservation', views['conservation']),
                          ('request_states', dict(Counter(r['request_state'] for r in audit['requests']))),
                          ('retry_request_count', sum(r['attempt'] > 0 for r in audit['requests'])),
                          ('provider_response_recorded_count', sum(r['provider_response_recorded'] for r in audit['requests'])),
                          ('unattributed', _aggregate(r for r in audit['requests'] if r['scope'] == 'UNATTRIBUTED')),
                          ('retained_non_sample_scopes', _aggregate(views['retained']))):
        _same(summary[key], expected, key)
    return views


def _money_metrics(rows, currency, *, references=False):
    result = _aggregate(rows)
    if references:
        result['request_reference_count'] = result.pop('request_count')
    def amount(value):
        return f'{value // 1000000}.{value % 1000000:06d}' if _int(value) else UNKNOWN
    result.update(currency=currency, known_estimated_cost_units=amount(result['known_estimated_cost_micros']),
                  estimated_cost_units=amount(result['estimated_cost_micros']),
                  uncertain_reserved_cost_units=amount(result['uncertain_reserved_cost_micros']),
                  estimated_cost_cny=amount(result['estimated_cost_micros']) if currency == 'CNY' else UNKNOWN,
                  cash_deducted_units=UNKNOWN)
    return result


def _fraction(value):
    return {'numerator': value.numerator, 'denominator': value.denominator}


def query_audit(path, sample_id=None):
    """Query one exported report offline; shared references are never new calls."""
    path = _file(path); payload = path.read_bytes(); audit = _loads(payload.decode())
    views = validate_exported_audit(audit); rows = audit['requests']; currency = audit['summary']['currency']
    known_samples = {s['sample_id'] for s in views['samples']}
    if sample_id is not None and sample_id not in known_samples:
        raise ValueError('Sample ID is not present in explicit direct/allocation attribution')
    selected = sorted(known_samples) if sample_id is None else [sample_id]
    samples = []
    for sid in selected:
        direct, shared = views['direct'][sid], views['allocated'][sid]
        equivalents = sum((r['request_equivalent'] for r in shared), Fraction())
        stage_names = sorted({r['job_kind'] for r in [*direct, *shared]})
        stages = []
        for name in stage_names:
            d = [r for r in direct if r['job_kind'] == name]; s = [r for r in shared if r['job_kind'] == name]
            stages.append({'job_kind': name, 'direct': _money_metrics(d, currency),
                           'allocated_shared_estimate': _money_metrics(s, currency, references=True),
                           'total_explicit_estimate': _money_metrics([*d, *s], currency, references=True)})
        attention = []
        for group, members in (('direct', direct), ('allocated_shared_estimate', shared)):
            for row in members:
                if row['request_state'] != 'succeeded' or row['job_state'] != 'done':
                    attention.append({'request_id': row['request_id'], 'job_id': row['job_id'], 'job_kind': row['job_kind'],
                                      'request_state': row['request_state'], 'job_state': row['job_state'], 'attribution_view': group,
                                      'estimated_cost_micros': row['known_estimated_cost_micros'],
                                      'uncertain_reserved_cost_micros': row['uncertain_reserved_cost_micros']})
        samples.append({'sample_id': sid, 'direct_request_count': len(direct), 'shared_request_reference_count': len(shared),
                        'shared_request_equivalent': _fraction(equivalents),
                        'total_request_equivalent': _fraction(Fraction(len(direct)) + equivalents),
                        'direct': _money_metrics(direct, currency),
                        'allocated_shared_estimate': _money_metrics(shared, currency, references=True),
                        'total_explicit_estimate': _money_metrics([*direct, *shared], currency, references=True),
                        'stages': stages, 'direct_request_states': dict(Counter(r['request_state'] for r in direct)),
                        'direct_job_states': dict(Counter(r['job_state'] for r in direct)),
                        'shared_reference_request_states': dict(Counter(r['request_state'] for r in shared)),
                        'shared_reference_job_states': dict(Counter(r['job_state'] for r in shared)),
                        'unsuccessful_or_pending_requests': attention,
                        'allocated_tokens_are_provider_sample_measurements': False})
    return {'schema_version': 'model-audit-query', 'audit_sha256': _sha(payload),
            'execution_mode': audit['summary']['execution_mode'], 'currency': currency,
            'cost_control': audit['summary'].get('cost_control', 'capped'),
            'budget_max_model_cost_micros': audit['summary'].get('budget_max_model_cost_micros', UNKNOWN),
            'source_binding': {k: audit['source'][k] for k in ('logical_sha256', 'config_sha256', 'attribution_sha256')},
            'integrity_scope': 'Schema, request/rate arithmetic and all exported attribution views checked; original database not consulted and no external authenticity inferred',
            'ledger_request_count': len(rows), 'actual_network_dispatch_count': UNKNOWN, 'local_cached_result_reuse_count': UNKNOWN,
            'provider_response_recorded_count': sum(r['provider_response_recorded'] for r in rows),
            'ledger_totals': _money_metrics(rows, currency),
            'unattributed': _money_metrics([r for r in rows if r['scope'] == 'UNATTRIBUTED'], currency),
            'retained_non_sample_scopes': _money_metrics(views['retained'], currency),
            'stages': [{'job_kind': name, **_money_metrics([r for r in rows if r['job_kind'] == name], currency)}
                       for name in sorted({r['job_kind'] for r in rows})],
            'request_states': dict(Counter(r['request_state'] for r in rows)),
            'job_states': dict(Counter(r['job_state'] for r in rows)), 'samples': samples,
            'warnings': ['Shared reference counts are not new API calls; only exact fractional equivalents may be added across allocated samples.',
                         'Shared estimates do not include unallocated shared, engineering or unattributed pools.',
                         'Reasoning/cache/image counts are subsets; do not add them to provider total or charge again.',
                         'All money is a configured-rate estimate in the stated currency; cash deduction remains UNKNOWN.']}


def _compact_query(value):
    """Select a concise view only after query_audit has validated everything."""
    def pool(metrics):
        return {'requests': metrics['request_count'], 'cost_micros': metrics['estimated_cost_micros'],
                'uncertain_reserved_micros': metrics['uncertain_reserved_cost_micros']}
    samples = []
    for sample in value['samples']:
        direct, shared, total = sample['direct'], sample['allocated_shared_estimate'], sample['total_explicit_estimate']
        equivalent = sample['shared_request_equivalent']; combined = sample['total_request_equivalent']
        samples.append({'sample_id': sample['sample_id'], 'direct_requests': sample['direct_request_count'],
                        'shared_reference_count': sample['shared_request_reference_count'],
                        'shared_request_equivalent': f"{equivalent['numerator']}/{equivalent['denominator']}",
                        'total_request_equivalent': f"{combined['numerator']}/{combined['denominator']}",
                        'direct_cost_micros': direct['estimated_cost_micros'], 'direct_cost_cny': direct['estimated_cost_cny'],
                        'shared_cost_micros': shared['estimated_cost_micros'], 'shared_cost_cny': shared['estimated_cost_cny'],
                        'total_cost_micros': total['estimated_cost_micros'], 'total_cost_cny': total['estimated_cost_cny'],
                        'known_total_cost_micros': total['known_estimated_cost_micros'],
                        'unknown_cost_references': total['unknown_cost_requests'],
                        'uncertain_reserved_micros': total['uncertain_reserved_cost_micros'],
                        **{key: total[key] for key in TOKEN_FIELDS},
                        'attention_reference_count': len(sample['unsuccessful_or_pending_requests']),
                        'shared_cost_and_tokens_are_estimates': sample['shared_request_reference_count'] > 0})
    total = value['ledger_totals']
    return {'audit_sha256': value['audit_sha256'], 'execution_mode': value['execution_mode'], 'currency': value['currency'],
            'cost_control': value['cost_control'], 'budget_max_model_cost_micros': value['budget_max_model_cost_micros'],
            'ledger': {'requests': value['ledger_request_count'], 'cost_micros': total['estimated_cost_micros'],
                       'cost_cny': total['estimated_cost_cny'], 'known_cost_micros': total['known_estimated_cost_micros'],
                       'unknown_cost_requests': total['unknown_cost_requests'],
                       'uncertain_reserved_micros': total['uncertain_reserved_cost_micros']},
            'stages': {row['job_kind']: {'requests': row['request_count'], 'cost_micros': row['estimated_cost_micros'],
                                       'cost_cny': row['estimated_cost_cny']} for row in value['stages']},
            'unattributed': pool(value['unattributed']), 'unallocated_non_sample': pool(value['retained_non_sample_scopes']),
            'states': {'requests': value['request_states'], 'jobs': value['job_states']}, 'samples': samples}


def token_audit(ledger):
    """Read token usage from original requests, independently of historical rates."""
    from .stage_metering import stage_for
    with closing(workspace_connect(Path(ledger).resolve().as_uri()+'?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        requests = list(con.execute('SELECT r.id,r.state,r.usage,r.job_id,j.kind,j.payload FROM model_requests r JOIN jobs j ON j.id=r.job_id ORDER BY r.started,r.id'))
    rows=[]
    for request in requests:
        usage=json.loads(request['usage']) if request['usage'] else None
        payload=json.loads(request['payload'])
        rows.append({'request_id':request['id'],'state':request['state'],'job_id':request['job_id'],
            'stage':stage_for(request['kind']),'attempt_id':payload.get('attempt_id'),
            'usage':usage,'usage_known':usage is not None})
    def total(selected):
        known=[row['usage'] for row in selected if row['usage'] is not None]
        return {'requests':len(selected),'usage_covered_requests':len(known),
                'usage_unknown_requests':len(selected)-len(known),
                'input_tokens':sum(row['input_tokens'] for row in known),
                'output_tokens':sum(row['output_tokens'] for row in known),
                'cached_input_tokens':sum(row.get('cached_input_tokens',0) for row in known),
                'reasoning_tokens_known':sum(row.get('reasoning_tokens') or 0 for row in known),
                'reasoning_usage_unknown_requests':sum(row.get('reasoning_tokens') is None for row in known)}
    return {'schema_version':'token-audit','requests':rows,'totals':total(rows),
            'stages':{stage:total([row for row in rows if row['stage']==stage]) for stage in sorted({row['stage'] for row in rows})},
            'subsets':'cache is included in input; reasoning is included in output; do not add twice'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    tokens = sub.add_parser('tokens', help='Read original request token usage without rates or credentials')
    tokens.add_argument('--ledger', required=True, type=Path)
    for name in ('fingerprint', 'export'):
        child = sub.add_parser(name); child.add_argument('--ledger', required=True, type=Path)
        if name == 'export':
            child.add_argument('--attribution', required=True, type=Path)
            child.add_argument('--output', required=True, type=Path)
    query = sub.add_parser('query', help='Read one exported audit offline with optional sample attribution filter')
    query.add_argument('--audit', required=True, type=Path)
    query.add_argument('--sample-id')
    query.add_argument('--compact', action='store_true', help='Show core costs/tokens after full audit validation')
    args = parser.parse_args(argv)
    try:
        value = token_audit(args.ledger) if args.command == 'tokens' else (query_audit(args.audit, args.sample_id) if args.command == 'query' else
                 fingerprint(args.ledger) if args.command == 'fingerprint' else export_audit(args.ledger, args.attribution, args.output)['summary'])
        if args.command == 'query' and args.compact:
            value = _compact_query(value)
        print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)); return 0
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
        print(json.dumps({'status': 'STOP', 'reason': type(error).__name__ + ': ' + str(error)}, ensure_ascii=False)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
