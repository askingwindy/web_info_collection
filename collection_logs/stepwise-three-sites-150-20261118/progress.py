import argparse
import json
import os
import re
import sqlite3
import time
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path

from webcollect.collection_report import request_summary

from launch_run import before
from select_pages import RUN, SCOPE


ARCHIVE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    temporary = path.with_suffix(f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def records(path):
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.strip():
                yield json.loads(line)


def select(path, sql, args=()):
    with closing(sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True, timeout=15)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, args)]


def issue_type(reason):
    if 'Image limit exceeded' in (reason or ''):
        return 'STEPWISE_IMAGE_CAPACITY'
    if 'Scoped action proof was lost or changed before dispatch' in (reason or ''):
        return 'SCOPED_ACTION_PROOF_CHANGED'
    if 'database is locked' in (reason or '').lower():
        return 'SQLITE_BUSY'
    for pattern in (r'net::(ERR_[A-Z_]+)', r'\b([A-Z][A-Z_]{4,})\b', r'\b([A-Za-z]+(?:Error|Timeout))\b', r'\b(stepwise_[a-z_]+)\b'):
        match = re.search(pattern, reason or '')
        if match:
            return match.group(1)
    return 'see_local_original'


def snapshot(directory, scope, baseline, sites):
    marks = ','.join('?' for _ in sites)
    claims = select(scope['pool'], f'''SELECT c.candidate_id,c.claim_id,c.state,c.stage,r.sample_id,r.qc_state
        FROM candidate_claims c LEFT JOIN candidate_results r ON c.claim_id=r.claim_id AND r.candidate_id=c.candidate_id
        WHERE c.candidate_id IN ({marks})''', list(sites))
    by_claim = {row['claim_id']: sites[row['candidate_id']] for row in claims}
    by_site = {site: {'selected': 50, 'claimed': 0, 'claim_states': Counter(), 'attempt_states': Counter(), 'saved_pending_review': 0} for site in sites.values()}
    for row in claims:
        item = by_site[by_claim[row['claim_id']]]
        item['claimed'] += 1
        item['claim_states'][row['state']] += 1
        if row['sample_id'] and row['qc_state'] == 'pending_review':
            item['saved_pending_review'] += 1
    first_start = read(RUN / 'run-01/controller-start.json')['started']
    attempts = select(scope['registry'], '''SELECT a.attempt_id,a.status,json_extract(t.task_json,'$.candidate_binding.claim_id') AS claim_id
        FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key WHERE a.created_at>=?''', (datetime.fromisoformat(first_start).timestamp(),))
    by_attempt = {row['attempt_id']: by_claim[row['claim_id']] for row in attempts if row['claim_id'] in by_claim}
    for row in attempts:
        if row['attempt_id'] in by_attempt:
            by_site[by_attempt[row['attempt_id']]]['attempt_states'][row['status']] += 1
    requests = select(scope['consumer_db'], '''SELECT r.state,r.usage,r.response,
        json_object('provider',json_extract(r.request_json,'$.provider'),'http_dispatch',json(CASE json_type(r.request_json,'$.http_dispatch')
                WHEN 'true' THEN 'true' WHEN 'false' THEN 'false' ELSE 'null' END)) AS request_json,
        coalesce(json_extract(r.request_json,'$.dispatch_attempt_id'),json_extract(j.payload,'$.attempt_id')) AS attempt_id,
        coalesce(json_extract(j.payload,'$.claim_id'),json_extract(j.payload,'$.candidate_binding.claim_id')) AS claim_id
        FROM model_requests r JOIN jobs j ON r.job_id=j.id WHERE r.rowid>?''', (baseline['consumer_db']['last_request_rowid'],))
    owned = [row for row in requests if row['attempt_id'] in by_attempt or row['claim_id'] in by_claim]
    faults = []
    for path in sorted(RUN.glob('run-*/failure-events.jsonl')):
        for event in records(path):
            faults.append({'segment': path.parent.name, 'at': event.get('at'), 'site': by_claim.get(event.get('claim_id')),
                'claim_id': event.get('claim_id'), 'disposition': event.get('disposition'), 'owner': event.get('reason_owner'),
                'feature': event.get('error_feature'), 'reason_code': issue_type(event.get('reason')),
                'stop_dispatch': event.get('stop_dispatch')})
    peaks = list(records(directory / 'worker-observations.jsonl'))
    summary = read(directory / 'summary.json') if (directory / 'summary.json').exists() else {}
    report_done = 'report_integrity' in summary
    result = {'at': datetime.now().astimezone().isoformat(timespec='seconds'), 'segment': directory.name,
        'plan_id': read(directory / 'controller-start.json')['plan_id'], 'strategy': 'stepwise', 'worker_target': 20,
        'worker_peak_observed': max((row['peak'] for row in peaks), default=0),
        'state': 'FINISHED' if report_done else 'REPORTING' if summary.get('finished_at') else 'RUNNING',
        'unique_claims': len(by_claim), 'unclaimed': len(sites) - len({row['candidate_id'] for row in claims}),
        'formal_attempts': len(by_attempt), 'saved_pending_review': sum(site['saved_pending_review'] for site in by_site.values()),
        'by_site': by_site, 'consumer_model': request_summary(owned), 'new_consumer_requests_not_yet_attributed': len(requests) - len(owned),
        'issues_recorded': len(faults), 'stop_requested': (directory / 'stop.request').exists(),
        'qc': 'NOT_RUN', 'human_review': 'NOT_RUN', 'dataset_published': False, 'customer_acceptance': 'UNKNOWN'}
    if summary:
        result['controller'] = {key: summary.get(key) for key in ('succeeded', 'interrupted', 'unlaunched', 'stop_reason', 'report_integrity', 'elapsed_seconds')}
        result['controller']['worker_exit_codes'] = dict(Counter(str(worker['returncode']) for worker in summary['workers']))
    if result['stop_requested'] and (directory / 'stop.request').read_text().startswith('ENGINEERING_STOP:'):
        result['dispatch_stop_origin'] = 'OPERATOR_ENGINEERING_STOP'
        if report_done and result['unclaimed']:
            result['collection_outcome'] = 'STOPPED_INCOMPLETE'
    return result, faults


def history(scope, baseline):
    current = before(scope)
    result = {}
    for role in ('pool', 'registry', 'consumer_db', 'producer_db'):
        key = {'pool': 'prior_claims', 'registry': 'prior_attempts'}.get(role, role)
        old, new = (baseline[key], current[key]) if role in ('pool', 'registry') else (baseline[role]['unsettled'], current[role]['unsettled'])
        indexed = {row[0]: list(row) for row in new}
        result[role] = {'protected': len(old), 'different_or_missing_ids': [row[0] for row in old if list(row) != indexed.get(row[0])]}
        if role in ('consumer_db', 'producer_db'):
            jobs = {row[1] for row in old}
            fresh = select(scope[role], 'SELECT id,job_id FROM model_requests WHERE rowid>?', (baseline[role]['last_request_rowid'],))
            result[role]['new_request_rows_on_prior_unsettled_jobs'] = sum(row['job_id'] in jobs for row in fresh)
            result[role]['all_new_request_rows'] = len(fresh)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('segment', type=int)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    directory = RUN / f'run-{args.segment:02d}'
    sites = {row['candidate_id']: row['host'].removeprefix('www.') for row in read(ARCHIVE / 'selection.json')['pages']}
    scope, baseline = read(SCOPE), read(RUN / 'before.json')
    while True:
        try:
            status, faults = snapshot(directory, scope, baseline, sites)
        except (sqlite3.OperationalError, json.JSONDecodeError) as error:
            if not args.watch:
                raise
            print(datetime.now().isoformat(), 'observation unavailable:', type(error).__name__, flush=True)
            time.sleep(10)
            continue
        stamp = directory.name
        write(ARCHIVE / f'{stamp}-status.json', status)
        write(ARCHIVE / f'{stamp}-issues.json', faults)
        with (RUN / f'{stamp}-progress.jsonl').open('a') as stream:
            stream.write(json.dumps(status, ensure_ascii=False) + '\n')
        print(status['at'], status['state'], 'claims', status['unique_claims'], 'attempts', status['formal_attempts'], 'saved', status['saved_pending_review'], flush=True)
        if status['state'] == 'FINISHED':
            write(ARCHIVE / f'{stamp}-ledger-check.json', history(scope, baseline))
        if not args.watch or status['state'] == 'FINISHED':
            break
        time.sleep(90)


if __name__ == '__main__':
    main()
