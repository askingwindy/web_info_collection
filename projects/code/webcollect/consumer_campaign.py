"""Bounded site workers sharing original accounts and a receipt-counted goal."""
import argparse
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time


@contextmanager
def locked(path):
    path = Path(path)
    with path.with_suffix('.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield json.loads(path.read_text())


def reached(path):
    with locked(path) as state:
        return len(state['deliveries']) >= state['target']


def claim_if_open(path, claim):
    # The check and original pool atomic claim share this short local lock.
    with locked(path) as state:
        return None if state.get('dispatch_stopped') or len(state['deliveries']) >= state['target'] else claim()


def deliver(path, pool, claim):
    from .candidate_consumer import verified_saved
    from .client_package import build_client_package
    from .batch_core import file_sha
    original = pool.get_claim(claim['claim_id'])
    saved = verified_saved(original)
    if not saved:
        return None
    with locked(path) as state:
        if any(row['sample_id'] == saved['sample_id'] for row in state['deliveries']):
            return None
        if state.get('dispatch_stopped') or len(state['deliveries']) >= state['target']:
            return {'sample_id': saved['sample_id'], 'delivery': 'not_exported_target_reached', 'saved': True}
        sample = Path(saved['result_location'])
        capture = sample.parent.parent
        source = capture.parent / 'candidate'
        receipt = capture.parent / 'candidate-receipt.json'
        if not source.is_dir() or not receipt.is_file():
            return None
        expected = json.loads(receipt.read_text())['files_sha256']
        if expected != {p.relative_to(source).as_posix(): file_sha(p) for p in source.rglob('*') if p.is_file()}:
            raise ValueError('Customer candidate changed after complete save')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        output = Path(state['delivery_root']) / (stamp + '-' + saved['sample_id'])
        # Rebuild through the ordinary exporter, which validates customer layout.
        evidence = Path(state['evidence_root']) / (output.name + '.evidence.json')
        build_client_package(Path(__file__).resolve().parents[3], capture, output,
                             facts=capture.parent / 'facts.json', evidence_output=evidence)
        row = {**saved, 'claim_id': claim['claim_id'], 'candidate_id': claim['candidate_id'],
               'exported_at': datetime.now(timezone.utc).isoformat(), 'customer_output': str(output),
               'format_status': 'EXPORTED_FORMAT_VALID', 'independent_AI_QC': 'NOT_RUN',
               'human_review': 'NOT_RUN', 'published': False}
        state['deliveries'].append(row)
        temporary = Path(path).with_suffix('.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(path)
        return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scope', type=Path, required=True)
    p.add_argument('--site', action='append', required=True, help='original applications.host; repeat for sites')
    p.add_argument('--workers-per-site', type=int, required=True)
    p.add_argument('--target', type=int, required=True)
    p.add_argument('--output', type=Path, required=True, help='new campaign state/log directory')
    p.add_argument('--delivery-root', type=Path, required=True)
    p.add_argument('--prefix', required=True)
    a = p.parse_args()
    signal.signal(signal.SIGINT, signal.default_int_handler)
    if min(a.workers_per_site, a.target) < 1: p.error('workers and target must be positive')
    scope = json.loads(a.scope.read_text())
    from .consumer_roster import build_roster
    roster = build_roster(scope, len(a.site) * a.workers_per_site, a.prefix, job_limit=None, campaign_limit=None)
    applications = []
    with closing(sqlite3.connect(Path(scope['pool']).resolve().as_uri() + '?mode=ro', uri=True)) as con:
        for site in a.site:
            row = con.execute('SELECT id FROM applications WHERE host=?', (site,)).fetchone()
            if not row: raise ValueError('Site absent from original application pool: ' + site)
            applications.extend([row[0]] * a.workers_per_site)
    a.output.mkdir(parents=True, exist_ok=False)
    a.delivery_root.mkdir(parents=True, exist_ok=True)
    evidence = a.output / 'delivery-evidence'; evidence.mkdir()
    launch_delivery = a.delivery_root / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    launch_delivery.mkdir()
    state = a.output / 'campaign.json'
    state.write_text(json.dumps({'schema_version': 'consumer-site-campaign-1', 'target': a.target,
        'delivery_root': str(launch_delivery.resolve()), 'evidence_root': str(evidence.resolve()),
        'scope': str(a.scope.resolve()), 'sites': a.site, 'deliveries': []}, indent=2) + '\n')
    # Same explicit launch authorization as consumer_roster, without changing frozen config.
    from .consumer_ab import adjust_concurrency
    from .runtime import RuntimeStore
    reason = 'consumer_campaign ' + a.prefix
    adjustment = adjust_concurrency(scope['consumer_db'], scope['consumer_config'], target=None, authorization=reason)
    runtime = RuntimeStore(scope['registry'], 'project-setup').set_consumer_concurrency(max_workers=None, max_domain_workers=None, reason=reason)
    (a.output / 'concurrency-adjustment.json').write_text(json.dumps({'consumer': adjustment, 'runtime': runtime}, indent=2) + '\n')
    processes = []
    try:
        for worker, application in zip(roster['workers'], applications):
            ws = worker['scope']
            command = [sys.executable, '-m', 'webcollect.candidate_consumer', '--pool', ws['pool'], 'run', '--protocol', 'entry']
            for flag, key in (('config','consumer_config'),('ledger','consumer_db'),('output','output'),('registry','registry'),('policy','policy'),('history-set','history_set'),('worker-id','consumer_worker'),('request-prefix','request_prefix')):
                command += ['--' + flag, str(ws[key])]
            command += ['--application-id', application, '--campaign', str(state.resolve()), '--first-plan-effort', 'high', '--branch-effort', 'high']
            with (a.output / ('worker-' + str(worker['number']) + '.log')).open('xb') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process)
            worker.update(application_id=application, pid=process.pid, command=command)
        (a.output / 'roster.json').write_text(json.dumps(roster, ensure_ascii=False, indent=2) + '\n')
        stopped = False
        while any(process.poll() is None for process in processes):
            if reached(state) and not stopped:
                stopped = True
                for process in processes:
                    if process.poll() is None: process.send_signal(signal.SIGINT)
            time.sleep(0.2)
    finally:
        # Close dispatch before cancelling workers, including an external interrupt.
        with locked(state) as current:
            current['dispatch_stopped'] = True
            temporary = state.with_suffix('.tmp')
            temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n')
            temporary.replace(state)
        for process in processes:
            if process.poll() is None: process.send_signal(signal.SIGINT)
        codes = [process.wait() for process in processes]
        (a.output / 'launch-result.json').write_text(json.dumps({'returncodes': codes, 'target_reached': reached(state), 'statuses': 'saved_pending_review; QC and publication separate'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
