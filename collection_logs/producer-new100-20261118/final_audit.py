#!/usr/bin/env python3
"""Read-only producer audit; output contains metadata, never page/request bodies.

Smoke: .venv/bin/python -B results/producer-new100-20261118-r01/final_audit.py --smoke --output-dir results/producer-new100-20261118-r01/audit-smoke-r01
Final: .venv/bin/python -B results/producer-new100-20261118-r01/final_audit.py
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
BATCH_PREFIX = 'producer-new100-20261118-dpm-'
RUN_PATTERN = '%/entry-batch/' + BATCH_PREFIX + '%'
APPLICATION = 'app-54680a484ea549505a7bd126'
HOSTS = {'dpm.org.cn', 'www.dpm.org.cn'}
PRODUCT_ROOTS = ('projects/code/webcollect', 'projects/site-planner/site_planner',
                 'projects/quality-inspector/quality_inspector')


def read_json(path):
    return json.loads(Path(path).read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def row_sha(row):
    return digest(json.dumps(dict(row), sort_keys=True, ensure_ascii=False,
                             separators=(',', ':')).encode())


def connect(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=90)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    return con


def uri_identity(uri):
    parsed = urlsplit(uri or '')
    host = (parsed.hostname or '').lower().removeprefix('www.')
    # This site's landing audit folds www and plain anchors; it preserves query/routes.
    fragment = parsed.fragment.removeprefix('!')
    if not fragment.startswith(('/', '?')):
        fragment = ''
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or '/', parsed.query, fragment))


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def belongs(payload):
    values = list(strings(payload))
    if any(BATCH_PREFIX in value for value in values):
        return 'explicit_round_batch'
    for value in values:
        if value.startswith(('http://', 'https://')) and urlsplit(value).hostname in HOSTS:
            return 'new_job_exact_site_url'
    return None


def select_ids(con, table, ids, *, key='id', columns='*'):
    result = []
    ids = sorted(set(filter(None, ids)))
    for offset in range(0, len(ids), 400):
        chunk = ids[offset:offset + 400]
        result.extend(dict(row) for row in con.execute(
            f'SELECT {columns} FROM {table} WHERE {key} IN ({",".join("?" for _ in chunk)})', chunk))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke', action='store_true', help='Always label result IN_PROGRESS; never claim final completion')
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output != ROOT and ROOT not in output.parents:
        parser.error('Output must remain inside this run directory')
    output.mkdir(parents=True, exist_ok=True)
    began = time.time()
    active = read_json(ROOT / 'active-run.json')
    started = active['started_at']
    scope = read_json(active['scope'])
    baseline = read_json(ROOT / 'baseline.json')
    old_candidates = set(baseline['candidate_ids'])
    old_applications = set(baseline['application_ids'])
    issues = []
    evidence_cache = {}
    related_jobs, related_requests = set(), set()

    def issue(code, candidate_id=None, **detail):
        issues.append({'code': code, **({'candidate_id': candidate_id} if candidate_id else {}), **detail})

    def evidence(ref, cid, label, *, json_body=True):
        if not isinstance(ref, dict) or not isinstance(ref.get('path'), str) or not isinstance(ref.get('sha256'), str):
            issue('reference_missing', cid, reference=label)
            return {}, None
        projection = {'path': ref['path'], 'sha256': ref['sha256']}
        key = (ref['path'], ref['sha256'])
        if key not in evidence_cache:
            try:
                content = Path(ref['path']).read_bytes()
                valid = digest(content) == ref['sha256']
                document = json.loads(content) if valid and json_body else None
                evidence_cache[key] = (valid, document)
            except (OSError, ValueError):
                evidence_cache[key] = (False, None)
        valid, document = evidence_cache[key]
        if not valid:
            issue('reference_integrity_failed', cid, reference=label, path=ref['path'])
        return projection, document

    with closing(connect(scope['pool'])) as con:
        batch_rows = [dict(row) for row in con.execute(
            'SELECT row_id,run_id,result,reason,candidate_id,created FROM candidate_batch_rows WHERE run_id LIKE ? ORDER BY created,row_id',
            (RUN_PATTERN,))]
        new_ids = {row['candidate_id'] for row in batch_rows if row['result'] == 'NEW' and row['candidate_id']}
        candidates = select_ids(con, 'data_candidates', new_ids, key='candidate_id')
        source_rows = select_ids(con, 'candidate_sources', new_ids, key='candidate_id')
    sources = defaultdict(list)
    published = defaultdict(list)
    for row in batch_rows:
        if row['result'] == 'NEW':
            published[row['candidate_id']].append(row)
    for row in source_rows:
        source = json.loads(row['source'])
        # Sources store the project producer ID, not the batch ID. The NEW row
        # and source are inserted in the same publish transaction, source first.
        # Exclude any later source appended by a different/duplicate batch.
        if row['created'] >= started and any(
                source.get('run_id') == item['run_id'].split('/entry-batch/')[0]
                and row['created'] <= item['created'] for item in published[row['candidate_id']]):
            sources[row['candidate_id']].append(source)
    if len(candidates) != len(new_ids):
        issue('published_candidate_missing')
    rows = []
    landings = defaultdict(list)
    from opencc import OpenCC
    converter = OpenCC('t2s')
    for candidate in sorted(candidates, key=lambda row: row['candidate_id']):
        cid = candidate['candidate_id']
        body = json.loads(candidate['body'])
        uri = body['entry_url']
        initial_errors = len(issues)
        if cid in old_candidates or candidate['created'] < started:
            issue('candidate_not_new', cid)
        if candidate['application_id'] in old_applications or candidate['application_id'] != APPLICATION:
            issue('application_not_expected_new_site', cid)
        if urlsplit(uri).hostname not in HOSTS:
            issue('entry_outside_site', cid)
        if len(sources[cid]) != 1:
            issue('round_source_not_unique', cid, count=len(sources[cid]))
        source = sources[cid][0] if sources[cid] else {}
        language = source.get('page_language_evidence') or {}
        if source.get('simplified_chinese_only') is not True or language.get('eligible') is not True or language.get('required_language') != 'zh-Hans' or language.get('traditional_conversion_would_change_text') is not False:
            issue('simplified_language_evidence_failed', cid)
        refs = {}
        refs['entry_http'], http = evidence(source.get('entry_http'), cid, 'entry_http')
        http = http or {}
        status = http.get('http_status')
        if http.get('result') != 'PASS' or http.get('method') != 'GET' or type(status) is not int or not 200 <= status < 300 or http.get('reused_original_browser_GET') is not True:
            issue('entry_http_not_verified_GET_2xx', cid)
        landed = http.get('landed_uri', '')
        if urlsplit(landed).hostname not in HOSTS or uri_identity(http.get('entry_uri')) != uri_identity(uri):
            issue('entry_http_binding_failed', cid)
        for pattern in source.get('excluded_entry_patterns', []):
            if re.search(pattern, uri, re.I) or re.search(pattern, landed, re.I):
                issue('operator_excluded_entry_or_landing', cid)
        if landed:
            landings[uri_identity(landed)].append(cid)
        refs['source_document'], document = evidence(http.get('source_document'), cid, 'source_document')
        refs['source_observation'], observation = evidence(http.get('source_observation'), cid, 'source_observation')
        document, observation = document or {}, observation or {}
        for name in ('raw_html', 'rendered_dom'):
            refs[name], _ = evidence(document.get(name), cid, name, json_body=False)
        if (document.get('method') != 'GET' or document.get('anonymous_context') is not True
                or document.get('initial_cookies') != 0 or document.get('login_performed') is not False
                or document.get('http_status') != status or document.get('landed_uri') != landed
                or uri_identity(document.get('uri')) != uri_identity(uri)
                or uri_identity(document.get('response_uri')) != uri_identity(landed)
                or document.get('job_id') != http.get('job_id') or document.get('visit_id') != http.get('visit_id')
                or observation.get('document') != http.get('source_document')
                or observation.get('landed_uri') != landed or observation.get('http_status') != status
                or observation.get('navigation_error')
                or document.get('content') != observation.get('text')):
            issue('shared_rendered_binding_failed', cid)
        text = document.get('content') or ''
        stripped = re.sub(r'繁體中文|繁体中文|简体中文|簡體中文|中文[（(](?:繁體|繁体|简体|簡體)[）)]', '', text)
        han = len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]', stripped))
        if han < 40 or converter.convert(stripped) != stripped or language.get('han_characters') != han:
            issue('original_rendered_language_recheck_failed', cid)
        related_jobs.add(http.get('job_id'))
        for call in (source.get('purpose_evidence') or {}).get('model_calls', []):
            related_jobs.add(call.get('job_id'))
            related_requests.add(call.get('request_id'))
        rows.append({'candidate_id': cid, 'application_id': candidate['application_id'],
                     'entry_url': uri, 'landed_url': landed, 'candidate_state': candidate['state'],
                     'audit_state': 'VERIFIED' if len(issues) == initial_errors else 'FAILED',
                     'language': {'simplified_chinese_only': source.get('simplified_chinese_only'),
                                  **{key: language.get(key) for key in ('required_language', 'eligible', 'reason', 'han_characters', 'traditional_conversion_would_change_text', 'source_text_modified')}},
                     'http': {'method': http.get('method'), 'result': http.get('result'), 'status': status,
                              'job_id': http.get('job_id'), 'visit_id': http.get('visit_id')}, 'references': refs})
    duplicate_landings = {uri: ids for uri, ids in landings.items() if len(ids) > 1}
    for uri, ids in duplicate_landings.items():
        issue('duplicate_actual_landing', candidate_ids=ids, url=uri)
        for row in rows:
            if row['candidate_id'] in ids:
                row['audit_state'] = 'FAILED'

    with closing(connect(scope['producer_db'])) as con:
        all_new_jobs = [dict(row) for row in con.execute('SELECT id,kind,state,created,payload,result FROM jobs WHERE created>=?', (started,))]
        attribution = {}
        for job in all_new_jobs:
            why = belongs(json.loads(job['payload']))
            if why:
                related_jobs.add(job['id'])
                attribution[job['id']] = why
        jobs = select_ids(con, 'jobs', related_jobs)
        for job in jobs:
            attribution.setdefault(job['id'], 'exact_published_evidence_reference')
        models = select_ids(con, 'model_requests', related_jobs, key='job_id',
                            columns='id,job_id,state,started,finished,usage,cost,reserved_cost,error')
        models_by_id = {row['id']: row for row in models}
        for row in select_ids(con, 'model_requests', related_requests,
                              columns='id,job_id,state,started,finished,usage,cost,reserved_cost,error'):
            models_by_id[row['id']] = row
        models = list(models_by_id.values())
        visits = select_ids(con, 'top_level_visits', related_jobs, key='job_id',
                            columns='id,job_id,state,dispatched_at,finished_at,response_status,target_uri,landed_uri,error_type')
    visit_map = {visit['id']: visit for visit in visits}
    job_map = {job['id']: job for job in jobs}
    for row in rows:
        http = row['http']; visit = visit_map.get(http['visit_id']); job = job_map.get(http['job_id'])
        result = json.loads(job['result'] or '{}') if job else {}
        if not visit or visit['state'] != 'succeeded' or visit['response_status'] != http['status'] or visit['landed_uri'] != row['landed_url'] or uri_identity(visit['target_uri']) != uri_identity(row['entry_url']) or not job or job['state'] != 'done' or job['kind'] != 'site-discovery-page':
            issue('original_GET_or_job_ledger_binding_failed', row['candidate_id'])
            row['audit_state'] = 'FAILED'
        if result.get('document') != row['references']['source_document'] or result.get('observation') != row['references']['source_observation'] or result.get('visit_id') != http['visit_id']:
            issue('original_job_artifact_binding_failed', row['candidate_id'])
            row['audit_state'] = 'FAILED'
    new_models = [row for row in models if row['started'] >= started]
    new_visits = [row for row in visits if row['dispatched_at'] >= started]
    new_jobs = [row for row in jobs if row['created'] >= started]
    tokens = Counter(); missing_usage = 0
    for row in new_models:
        if row['usage'] is None:
            missing_usage += 1
            continue
        usage = json.loads(row['usage'])
        for key in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'prompt_tokens', 'completion_tokens', 'total_tokens'):
            if type(usage.get(key)) in (int, float):
                tokens[key] += usage[key]

    protected = read_json(ROOT / 'protected-before.json')
    protected_counts = {}; protected_drift = []
    for role, tables in protected.items():
        with closing(connect(scope[role + '_db'])) as con:
            for table, records in tables.items():
                if table not in ('jobs', 'model_requests'):
                    raise ValueError('Unexpected protected table')
                protected_counts[role + '.' + table] = len(records)
                for rid, expected in records.items():
                    row = con.execute('SELECT * FROM ' + table + ' WHERE id=?', (rid,)).fetchone()
                    if row is None or row_sha(row) != expected['sha256']:
                        protected_drift.append({'role': role, 'table': table, 'id': rid,
                                                'old_state': expected['state'], 'new_state': row['state'] if row else None})
    if protected_drift:
        issue('protected_history_changed', count=len(protected_drift))
    before = read_json(ROOT / 'source-before.json')
    after = {str(path.relative_to(REPO)): digest(path.read_bytes()) for folder in PRODUCT_ROOTS
             for path in (REPO / folder).rglob('*') if path.is_file() and path.suffix in ('.py', '.js', '.json')}
    source_changes = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
    if source_changes:
        issue('product_source_changed', paths=source_changes)

    process_rows = [{'role': 'controller', 'pid': active['controller_pid']},
                    {'role': 'worker', 'pid': active['worker_pid']}]
    expansion_path = ROOT / 'expansion-active.json'
    if expansion_path.exists():
        expansion = read_json(expansion_path)
        process_rows.append({'role': 'expansion_controller', 'pid': expansion['controller_pid']})
        process_rows.extend({'role': 'worker', 'pid': item['pid']} for item in expansion['workers'])
    for row in process_rows:
        probe = subprocess.run(['ps', '-p', str(row['pid']), '-o', 'stat='], capture_output=True, text=True)
        row['alive'] = probe.returncode == 0 and bool(probe.stdout.strip()) and not probe.stdout.strip().startswith('Z')
    exit_names = ['controller-exit.json'] + (['expansion-exit.json'] if expansion_path.exists() else [])
    exits = {name: read_json(ROOT / name) if (ROOT / name).exists() else None for name in exit_names}
    exit_claims = (bool(exits['controller-exit.json']) and exits['controller-exit.json'].get('worker_exited') is True
                   and (not expansion_path.exists() or bool(exits['expansion-exit.json']) and exits['expansion-exit.json'].get('all_children_exited') is True))
    exited = not any(row['alive'] for row in process_rows) and exit_claims
    target = active['target_net_new']
    net_new = new_ids - old_candidates
    if len(net_new) > target:
        issue('target_overshoot', count=len(net_new), target=target)
    if not args.smoke and exited and len(net_new) != target:
        issue('target_not_reached', count=len(net_new), target=target)
    status = 'IN_PROGRESS' if args.smoke or not exited else 'PASS' if not issues and len(net_new) == target else 'REQUIRES_REVIEW'
    report = {'status': status, 'snapshot_at': began, 'audit_seconds': round(time.time() - began, 3),
              'read_only_database': True, 'smoke': args.smoke, 'target': target,
              'counting_pattern': RUN_PATTERN, 'batch_row_states': dict(Counter(row['result'] for row in batch_rows)),
              'published_NEW_unique': len(new_ids), 'net_new_candidates': len(net_new),
              'new_application_ids': sorted({row['application_id'] for row in candidates} - old_applications),
              'verified_pages': sum(row['audit_state'] == 'VERIFIED' for row in rows),
              'actual_landing_unique': len(landings), 'duplicate_landings': duplicate_landings,
              'verified_reference_files': len(evidence_cache),
              'accounting': {'attribution': dict(Counter(attribution.values())),
                             'new_jobs_outside_round_attribution': len(all_new_jobs) - len(new_jobs),
                             'new_jobs': len(new_jobs), 'job_states': dict(Counter(row['state'] for row in new_jobs)),
                             'model_requests': len(new_models), 'model_states': dict(Counter(row['state'] for row in new_models)),
                             'tokens': dict(tokens), 'model_requests_missing_usage': missing_usage,
                             'known_cost_micros': sum(row['cost'] for row in new_models if row['cost'] is not None),
                             'cost_unknown_requests': sum(row['cost'] is None for row in new_models),
                             'reserved_cost_for_unknown_charge_micros': sum(row['reserved_cost'] for row in new_models if row['cost'] is None),
                             'GET_requests': len(new_visits), 'GET_states': dict(Counter(row['state'] for row in new_visits)),
                             'GET_statuses': dict(Counter(str(row['response_status']) for row in new_visits)),
                             'reused_preexisting_jobs': len(jobs) - len(new_jobs),
                             'reused_preexisting_model_requests': len(models) - len(new_models),
                             'reused_preexisting_GETs': len(visits) - len(new_visits)},
              'protected_counts': protected_counts, 'protected_drift': protected_drift,
              'source_file_count': len(before), 'source_unchanged': not source_changes,
              'source_changes': source_changes, 'processes': process_rows, 'all_processes_exited': exited,
              'exit_receipts': exits, 'issues': issues,
              'consumer_QC_started_by_this_audit': False, 'human_review': 'NOT_RUN', 'published': False}
    (output / 'page-results.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows))
    (output / 'final-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'net_new_candidates', 'verified_pages', 'actual_landing_unique', 'source_unchanged', 'all_processes_exited')}, ensure_ascii=False))
    print(json.dumps({'issues': len(issues), 'protected_drift': len(protected_drift), 'output_dir': str(output)}, ensure_ascii=False))
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
