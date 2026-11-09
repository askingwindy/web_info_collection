"""Continuous site consumers with immediate, minute-directory customer exports."""
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
from zoneinfo import ZoneInfo


@contextmanager
def locked(path):
    path = Path(path)
    with path.with_suffix('.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield json.loads(path.read_text())


def write_state(path, state):
    temporary = Path(path).with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def target_reached(state):
    return state.get('target') is not None and len(state['deliveries']) >= state['target']


def reached(path):
    with locked(path) as state:
        return target_reached(state)


def stopped(path):
    with locked(path) as state:
        return bool(state.get('dispatch_stopped') or target_reached(state))


def claim_if_open(path, claim):
    with locked(path) as state:
        return None if state.get('dispatch_stopped') or target_reached(state) else claim()


def deliver(path, pool, claim):
    """Queue close-out immediately; exporter IO never holds the dispatch lock."""
    with locked(path) as state:
        if any(row['claim_id'] == claim['claim_id'] for row in state['deliveries']):
            return {'state':'exported', 'claim_id':claim['claim_id']}
        pending = state.setdefault('pending_deliveries', [])
        if not any(row['claim_id'] == claim['claim_id'] for row in pending):
            pending.append({'claim_id':claim['claim_id'], 'candidate_id':claim['candidate_id']})
            write_state(path, state)
    return {'state':'queued', 'claim_id':claim['claim_id']}


def publish_pending(path, pool):
    from .candidate_consumer import verified_saved
    from .client_package import append_client_package
    from .batch_core import file_sha
    with locked(path) as state:
        if not state.get('pending_deliveries'):
            return
        pending = dict(state['pending_deliveries'][0])
        output, evidence_root = Path(state['delivery_root']), Path(state['evidence_root'])
    # The coordinator is the sole publisher for this campaign. Other campaigns
    # using the same minute serialize only package updates in the exporter.
    result = None
    try:
        original = pool.get_claim(pending['claim_id'])
        saved = verified_saved(original)
        if saved:
            capture = Path(saved['result_location']).parent.parent
            source = capture.parent / 'candidate'
            receipt = capture.parent / 'candidate-receipt.json'
            if not source.is_dir() or not receipt.is_file():
                raise ValueError('Saved sample awaits its customer export receipt')
            expected = json.loads(receipt.read_text())['files_sha256']
            append_client_package(Path(__file__).resolve().parents[3], source, output,
                                  files_sha256=expected, staging_root=evidence_root)
            result = {**saved, **pending, 'customer_output':str(output),
                'customer_sample':str(output / 'samples' / saved['sample_id']),
                'exported_at':datetime.now(timezone.utc).isoformat(),
                'source_receipt':{'path':str(receipt), 'sha256':file_sha(receipt)},
                'format_status':'EXPORTED_FORMAT_VALID', 'independent_AI_QC':'NOT_RUN',
                'human_review':'NOT_RUN', 'published':False}
            sidecar = evidence_root / (saved['sample_id'] + '.json')
            sidecar.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        with locked(path) as state:
            state['pending_deliveries'] = [row for row in state['pending_deliveries']
                                           if row['claim_id'] != pending['claim_id']]
            if result and not any(row['sample_id'] == result['sample_id'] for row in state['deliveries']):
                state['deliveries'].append(result)
            write_state(path, state)
    except Exception as error:
        # Retry publication from the saved package, never replay browser work.
        # Rotate failed exports so another valid sample can publish immediately.
        with locked(path) as state:
            queue = state['pending_deliveries']
            item = next((row for row in queue if row['claim_id'] == pending['claim_id']), None)
            if item:
                queue.remove(item)
                item.update(last_error=type(error).__name__ + ': ' + str(error), last_attempt=time.time())
                queue.append(item)
            write_state(path, state)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scope', type=Path, required=True)
    p.add_argument('--site', action='append', required=True, help='original applications.host; repeat for sites')
    p.add_argument('--workers-per-site', type=int, required=True)
    p.add_argument('--target', type=int, help='optional explicit number of new exported samples; otherwise continuous')
    p.add_argument('--output', type=Path, required=True, help='new campaign state/log directory')
    p.add_argument('--delivery-root', type=Path, default=Path('delivery'))
    p.add_argument('--prefix', required=True)
    a = p.parse_args()
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, lambda signum, frame: signal.default_int_handler(signum, frame))
    if a.workers_per_site < 1 or (a.target is not None and a.target < 1):
        p.error('workers and explicit target must be positive')
    scope = json.loads(a.scope.read_text())
    from .consumer_roster import build_roster
    from site_planner.candidate_pool import CandidatePool
    pool = CandidatePool(scope['pool'])
    roster = build_roster(scope, len(a.site) * a.workers_per_site, a.prefix, job_limit=None, campaign_limit=None)
    applications = []
    with closing(sqlite3.connect(Path(scope['pool']).resolve().as_uri() + '?mode=ro', uri=True)) as con:
        for site in a.site:
            row = con.execute('SELECT id FROM applications WHERE host=?', (site,)).fetchone()
            if not row: raise ValueError('Site absent from original application pool: ' + site)
            applications.extend([row[0]] * a.workers_per_site)
    a.output.mkdir(parents=True, exist_ok=False)
    evidence = a.output / 'delivery-evidence'; evidence.mkdir()
    launch_delivery = a.delivery_root.resolve() / datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d%H%M')
    state = a.output / 'campaign.json'
    write_state(state, {'schema_version':'consumer-site-campaign-2', 'target':a.target,
        'delivery_root':str(launch_delivery), 'evidence_root':str(evidence.resolve()),
        'scope':str(a.scope.resolve()), 'sites':a.site, 'deliveries':[],
        'pending_deliveries':[], 'dispatch_stopped':False})
    from .consumer_ab import adjust_concurrency
    from .runtime import RuntimeStore
    reason = 'consumer_campaign ' + a.prefix
    adjustment = adjust_concurrency(scope['consumer_db'], scope['consumer_config'], target=None, authorization=reason)
    runtime = RuntimeStore(scope['registry'], 'project-setup').set_consumer_concurrency(max_workers=None, max_domain_workers=None, reason=reason)
    (a.output / 'concurrency-adjustment.json').write_text(json.dumps({'consumer':adjustment,'runtime':runtime}, indent=2) + '\n')
    processes = {}

    def launch(worker, application):
        generation = worker.get('generation', 0) + 1
        ws = worker['scope']
        identity = f"{a.prefix}-w{worker['number']}-g{generation}"
        command = [sys.executable, '-m', 'webcollect.candidate_consumer', '--pool', ws['pool'], 'run', '--protocol', 'entry']
        for flag, key in (('config','consumer_config'),('ledger','consumer_db'),('output','output'),('registry','registry'),('policy','policy'),('history-set','history_set')):
            command += ['--' + flag, str(ws[key])]
        command += ['--worker-id',identity,'--request-prefix',identity,'--application-id',application,
                    '--campaign',str(state.resolve()),'--first-plan-effort','high','--branch-effort','high']
        with (a.output / (identity + '.log')).open('ab') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        processes[worker['number']] = process
        worker.update(application_id=application,pid=process.pid,command=command,generation=generation)
        (a.output / 'roster.json').write_text(json.dumps(roster, ensure_ascii=False, indent=2) + '\n')

    try:
        for worker, application in zip(roster['workers'], applications):
            launch(worker, application)
        while not stopped(state):
            publish_pending(state, pool)
            if stopped(state): break
            for worker, application in zip(roster['workers'], applications):
                if processes[worker['number']].poll() is not None:
                    launch(worker, application)
            time.sleep(0.2)
    finally:
        with locked(state) as current:
            current['dispatch_stopped'] = True
            write_state(state, current)
        for process in processes.values():
            if process.poll() is None: process.send_signal(signal.SIGINT)
        deadline=time.monotonic()+10
        for process in processes.values():
            if process.poll() is None:
                try: process.wait(timeout=max(0,deadline-time.monotonic()))
                except subprocess.TimeoutExpired: process.terminate()
        for process in processes.values():
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        # Dispatch is closed; finish publishing already saved items only.
        # One shutdown pass leaves failed exports durably queued for resume.
        with locked(state) as current:
            pending_count=len(current.get('pending_deliveries',[]))
        for _ in range(pending_count):
            publish_pending(state,pool)
        (a.output / 'launch-result.json').write_text(json.dumps({
            'returncodes':[process.returncode for process in processes.values()],
            'target_reached':reached(state), 'statuses':'saved_pending_review; QC and publication separate'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
