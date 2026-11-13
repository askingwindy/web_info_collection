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


from .closing_policy import COMPLETED_GOAL_DELIVERY, completion_delivery_decision

# The one current campaign schema. Historical state files written as
# 'consumer-site-campaign-3', 'consumer-site-campaign-4' or
# 'consumer-site-campaign-5' still load: their delivery rows keep their stored
# counting fields as plain data, which the current code never reinterprets.
CAMPAIGN_SCHEMA = 'consumer-site-campaign'
TARGET_REASONS = ('ORDINARY_TARGET_REACHED', 'TARGET_REACHED')


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


def stop_engineering_failure(path, details):
    """Fence new claims and retain the first recorded stop decision."""
    with locked(path) as state:
        state['dispatch_stopped'] = True
        if not state.get('stop_reason'):
            state['stop_reason'] = 'ENGINEERING_FAILURE'
            state['stop_details'] = details
        write_state(path, state)


def target_count(state, application_id=None):
    """A delivery counts toward the target iff ordinary_target_eligible."""
    return sum(row.get('ordinary_target_eligible') is True for row in state['deliveries']
               if application_id is None or row.get('application_id') == application_id)


def site_reached(state, application_id):
    target = state.get('site_targets', {}).get(application_id)
    return target is not None and target_count(state, application_id) >= target


def target_reached(state):
    if state.get('site_targets'):
        return all(site_reached(state, app) for app in state['site_targets'])
    return state.get('target') is not None and target_count(state) >= state['target']


def completed_goal_completion(saved):
    """Single qualification: original-goal-complete ordinary delivery."""
    from .batch_core import load_json, file_sha
    receipt = load_json(saved['save_receipt']['path'])
    annotation = Path(saved['result_location']) / 'annotation.json'
    if file_sha(annotation) != receipt['sample_files_sha256']['annotation.json']:
        raise ValueError('Campaign annotation differs from saved receipt')
    result = completion_delivery_decision(load_json(annotation), receipt.get('raw_execution', {}))
    return {**result, 'counting_policy': COMPLETED_GOAL_DELIVERY,
            'target_count_status': ('ordinary_goal_completed_pending_review'
                if result['delivery_eligible'] else 'retained_outside_ordinary_target'),
            'target_count_is_QC_pass': False}


def reached(path):
    with locked(path) as state:
        return target_reached(state)


def stopped(path, application_id=None):
    with locked(path) as state:
        return bool(state.get('dispatch_stopped') or target_reached(state) or site_reached(state, application_id))


def claim_if_open(path, claim, application_id=None):
    with locked(path) as state:
        return None if state.get('dispatch_stopped') or target_reached(state) or site_reached(state, application_id) else claim()


def deliver(path, pool, claim):
    """Queue close-out immediately; exporter IO never holds the dispatch lock."""
    with pool.pool.connect() as con:
        application_id = con.execute('SELECT application_id FROM data_candidates WHERE candidate_id=?', (claim['candidate_id'],)).fetchone()[0]
    with locked(path) as state:
        if any(row['claim_id'] == claim['claim_id'] for row in state['deliveries']):
            return {'state':'exported', 'claim_id':claim['claim_id']}
        pending = state.setdefault('pending_deliveries', [])
        if not any(row['claim_id'] == claim['claim_id'] for row in pending):
            pending.append({'claim_id':claim['claim_id'], 'candidate_id':claim['candidate_id'],
                            'application_id':application_id})
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
            qualification = completed_goal_completion(saved)
            if qualification.get('delivery_eligible') is not True:
                with locked(path) as state:
                    state.setdefault('internal_retained', []).append({**saved, **pending, **qualification, 'sample_id':saved['sample_id']})
                    state['pending_deliveries'] = [r for r in state['pending_deliveries'] if r['claim_id'] != pending['claim_id']]
                    write_state(path, state)
                return
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
            result.update(qualification)
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
    p.add_argument('--target-per-site', type=int, help='Independent target for each selected site; uses campaign v5')
    p.add_argument('--target', type=int, help='optional exported-sample target under --counting-policy; otherwise continuous')
    p.add_argument('--counting-policy', choices=(COMPLETED_GOAL_DELIVERY,), default=COMPLETED_GOAL_DELIVERY,
                   help='Campaigns count original-goal-complete ordinary deliveries only')
    p.add_argument('--target-stop-mode', choices=('drain', 'cancel'), default='drain',
                   help='drain finishes in-flight work; cancel signals only this launch workers after target export')
    p.add_argument('--output', type=Path, required=True, help='new campaign state/log directory')
    p.add_argument('--delivery-root', type=Path, default=Path('delivery'))
    p.add_argument('--prefix', required=True)
    a = p.parse_args()
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, lambda signum, frame: signal.default_int_handler(signum, frame))
    if a.target_per_site is not None and (a.target_per_site < 1 or a.target is not None):
        p.error('--target-per-site must be positive and cannot combine with --target')
    if len(set(a.site)) != len(a.site):
        p.error('duplicate sites are not allowed')
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
    write_state(state, {'schema_version':CAMPAIGN_SCHEMA,
        'counting_policy':a.counting_policy, 'target_stop_mode':a.target_stop_mode, 'target':a.target,
        'delivery_root':str(launch_delivery), 'evidence_root':str(evidence.resolve()),
        'scope':str(a.scope.resolve()), 'sites':a.site, 'deliveries':[],
        'site_targets':dict.fromkeys(applications, a.target_per_site) if a.target_per_site else {},
        'pending_deliveries':[], 'dispatch_stopped':False})
    from .consumer_ab import adjust_concurrency
    from .runtime import RuntimeStore
    reason = 'consumer_campaign ' + a.prefix
    adjustment = adjust_concurrency(scope['consumer_db'], scope['consumer_config'], target=None, authorization=reason)
    runtime = RuntimeStore(scope['registry'], 'project-setup').set_consumer_concurrency(max_workers=None, max_domain_workers=None, reason=reason)
    (a.output / 'concurrency-adjustment.json').write_text(json.dumps({'consumer':adjustment,'runtime':runtime}, indent=2) + '\n')
    # Central startup probe, before launching any worker; workers only read health.
    from .batch_core import BatchLedger, load_json
    from .key_health import probe_accounts
    health_ledger = BatchLedger(scope['consumer_db'], load_json(scope['consumer_config']))
    probes = probe_accounts(health_ledger, a.prefix + ':' + str(state.resolve()))
    (a.output / 'key-health-probes.json').write_text(json.dumps(probes, indent=2) + '\n')
    processes = {}
    launched_workers = []

    def launch(worker, application):
        generation = worker.get('generation', 0) + 1
        ws = worker['scope']
        identity = f"{a.prefix}-w{worker['number']}-g{generation}"
        command = [sys.executable, '-m', 'webcollect.candidate_consumer', '--pool', ws['pool'], 'run']
        for flag, key in (('config','consumer_config'),('ledger','consumer_db'),('output','output'),('registry','registry'),('policy','policy'),('history-set','history_set')):
            command += ['--' + flag, str(ws[key])]
        command += ['--worker-id',identity,'--request-prefix',identity,'--application-id',application,
                    '--campaign',str(state.resolve()),'--first-plan-effort','high','--branch-effort','high']
        with (a.output / (identity + '.log')).open('ab') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        processes[worker['number']] = process
        launched_workers.append(identity)
        worker.update(application_id=application,pid=process.pid,command=command,generation=generation)
        (a.output / 'roster.json').write_text(json.dumps(roster, ensure_ascii=False, indent=2) + '\n')

    interrupted=False
    target_cancelled=False
    cancelled_sites=set()
    try:
        for worker, application in zip(roster['workers'], applications):
            launch(worker, application)
        while True:
            publish_pending(state, pool)
            with locked(state) as current:
                engineering_drain = current.get('stop_reason') == 'ENGINEERING_FAILURE'
                external_stop=bool(current.get('dispatch_stopped') and current.get('stop_reason') not in TARGET_REASONS)
                dispatch_closed=bool(current.get('dispatch_stopped') or target_reached(current))
                closed_sites={app for app in current.get('site_targets', {}) if site_reached(current, app)}
                if target_reached(current) and not current.get('dispatch_stopped'):
                    current.update(dispatch_stopped=True, stop_reason='ORDINARY_TARGET_REACHED')
                    write_state(state,current)
            if a.target_stop_mode == 'cancel' and not engineering_drain:
                for worker in roster['workers']:
                    if worker['application_id'] in closed_sites and worker['number'] not in cancelled_sites:
                        process=processes[worker['number']]
                        if process.poll() is None: process.send_signal(signal.SIGINT)
                        cancelled_sites.add(worker['number'])
            if external_stop and current.get('stop_reason') != 'ENGINEERING_FAILURE':
                interrupted=True
                break
            if dispatch_closed:
                if a.target_stop_mode == 'cancel' and not engineering_drain and reached(state):
                    target_cancelled=True
                    break
                # Reaching the target closes new claims. Already dispatched
                # consumers finish their original evidence and exports naturally.
                if all(process.poll() is not None for process in processes.values()):break
            else:
                for worker, application in zip(roster['workers'], applications):
                    if application not in closed_sites and processes[worker['number']].poll() is not None:
                        launch(worker, application)
            time.sleep(0.2)
    except KeyboardInterrupt:
        interrupted=True
    finally:
        with locked(state) as current:
            current['dispatch_stopped'] = True
            if interrupted and not current.get('stop_reason'):current['stop_reason']='INTERRUPTED_BY_USER'
            elif target_cancelled and not current.get('stop_reason'):
                current.update(stop_reason='TARGET_REACHED', worker_shutdown_reason='TARGET_REACHED')
            write_state(state, current)
        if not interrupted and not target_cancelled:
            try:
                while any(process.poll() is None for process in processes.values()):
                    publish_pending(state,pool)
                    time.sleep(0.2)
            except KeyboardInterrupt:
                interrupted=True
                with locked(state) as current:
                    if not current.get('stop_reason'): current['stop_reason']='INTERRUPTED_BY_USER'
                    current['user_interrupted']=True
                    write_state(state,current)
        if interrupted or target_cancelled:
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
        # A worker may seal a sample just before cancellation, before its
        # ordinary run loop queues the export. Inspect only identities launched
        # by this coordinator, using the same saved-receipt validator.
        from .candidate_consumer import verified_saved
        closeout_errors=[]
        with pool.pool.connect() as db:
            own_claim_ids=([row[0] for identity in launched_workers for row in db.execute(
                'SELECT claim_id FROM candidate_claims WHERE worker_id=?', (identity,))]
                if target_cancelled or cancelled_sites else [])
        for claim_id in own_claim_ids:
            try:
                own_claim=pool.get_claim(claim_id)
                if verified_saved(own_claim):
                    deliver(state,pool,own_claim)
            except Exception as error:
                closeout_errors.append({'claim_id':claim_id, 'error_type':type(error).__name__,
                                        'reason':str(error)})
        # Dispatch is closed; finish publishing already saved items only.
        # One shutdown pass leaves failed exports durably queued for resume.
        with locked(state) as current:
            pending_count=len(current.get('pending_deliveries',[]))
        for _ in range(pending_count):
            publish_pending(state,pool)
        with locked(state) as current:
            exported=len(current['deliveries'])
            counted=target_count(current)
            ordinary=sum(row.get('ordinary_target_eligible') is True for row in current['deliveries'])
            stop_reason=current.get('stop_reason')
            pending_count=len(current.get('pending_deliveries',[]))
        (a.output / 'launch-result.json').write_text(json.dumps({
            'returncodes':[process.returncode for process in processes.values()],
            'saved_closeout_errors':closeout_errors,
            'target_reached':reached(state), 'interrupted':interrupted,
            'target_cancelled':target_cancelled, 'stop_reason':stop_reason,
            'counting_policy':a.counting_policy, 'target_stop_mode':a.target_stop_mode,
            'site_target_counts':{app:target_count(current, app) for app in current.get('site_targets', {})},
            'target_eligible_exports':counted,
            'exported_pending_review':exported,'ordinary_goal_completed_pending_review':ordinary,
            'retained_outside_ordinary_target':exported-ordinary,'pending_exports':pending_count,
            'statuses':'saved_pending_review; QC and publication separate'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
