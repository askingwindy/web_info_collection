"""Bounded concurrent site collection using one authoritative production ledger.

This schedules existing, published M4 plans. It does not discover sites, invent
tasks, increase production budgets, issue model calls or grant QC acceptance.
"""
import argparse
import asyncio
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from .collect_runtime import collect_m4, source_identity
from .planning import canonical, object_sha256
from .production_quality import sha
from .runtime import domain_key, validate_policy
from .storage import write_json

VERSION = 'site-schedule'
LEGACY_VERSION = 'webcollect-site-schedule-1'


def _absolute(value, label):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError(label + ' must be an absolute path')
    return str(Path(value).resolve())


def validate_schedule(value):
    config = deepcopy(value)
    if not isinstance(config, dict) or set(config) - {
            'schema_version', 'registry', 'max_parallel_sites', 'max_schedule_seconds', 'sites'}:
        raise ValueError('Unknown site schedule fields')
    if config.get('schema_version') not in (None, VERSION, LEGACY_VERSION):
        raise ValueError('Unsupported site schedule version')
    maximum = config.get('max_parallel_sites')
    if type(maximum) is not int or maximum < 1:
        raise ValueError('max_parallel_sites must be a positive integer')
    seconds = config.setdefault('max_schedule_seconds', None)
    if seconds is not None and (type(seconds) is not int or seconds < 1):
        raise ValueError('max_schedule_seconds must be a positive integer')
    config['registry'] = _absolute(config.get('registry'), 'registry')
    if not Path(config['registry']).is_file():
        raise ValueError('The existing production registry is required')
    sites = config.get('sites')
    if not isinstance(sites, list) or not sites:
        raise ValueError('A nonempty frozen site list is required')
    keys, outputs, policy, bindings = set(), set(), None, {}
    for site in sites:
        if not isinstance(site, dict) or set(site) != {'site_key', 'batches'}:
            raise ValueError('A site needs site_key and batches')
        key = site.get('site_key')
        if not isinstance(key, str) or not key.strip() or key in keys:
            raise ValueError('site_key must be nonempty and unique; all its batches run serially')
        keys.add(key)
        if not isinstance(site['batches'], list) or not site['batches']:
            raise ValueError('A site requires at least one published batch')
        domains = set()
        for batch in site['batches']:
            if not isinstance(batch, dict) or set(batch) - {'plan', 'publication', 'policy', 'output', 'resume', 'channel', 'headless'}:
                raise ValueError('Unknown scheduled batch fields')
            for name in ('plan', 'publication', 'policy', 'output'):
                batch[name] = _absolute(batch.get(name), name)
            if batch['output'] in outputs:
                raise ValueError('Concurrent sites must have distinct output directories')
            outputs.add(batch['output'])
            for name in ('plan', 'publication', 'policy'):
                bindings[batch[name]] = sha(batch[name])
            current_policy = validate_policy(json.loads(Path(batch['policy']).read_text()))
            if policy is None:
                policy = current_policy
            elif policy != current_policy:
                raise ValueError('All sites must share the same campaign and complete policy')
            for name in ('resume', 'headless'):
                if name in batch and type(batch[name]) is not bool:
                    raise ValueError(name + ' must be boolean')
            if 'channel' in batch and (not isinstance(batch['channel'], str) or not batch['channel'].strip()):
                raise ValueError('channel must be nonempty')
            plan = json.loads(Path(batch['plan']).read_text())
            if not isinstance(plan.get('tasks'), list) or not plan['tasks']:
                raise ValueError('Every batch needs a published nonempty task plan')
            domains.update(domain_key(task['site_uri']) for task in plan['tasks'])
        if len(domains) != 1:
            raise ValueError('One logical site may use multiple URIs, but must have one conservative traffic domain')
    if maximum != policy['max_workers']:
        raise ValueError('max_parallel_sites must equal shared policy.max_workers while each site has one worker; explicitly update the original campaign policy first')
    con = sqlite3.connect(Path(config['registry']).as_uri() + '?mode=ro', uri=True)
    try:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m4_campaigns'").fetchone()
        row = con.execute('SELECT policy_json FROM m4_campaigns WHERE campaign_id=?',
                          (policy['campaign_id'],)).fetchone() if exists else None
        if row and json.loads(row[0]) != policy:
            raise ValueError('Existing campaign policy differs; scheduler cannot change or reset its limits')
    finally:
        con.close()
    for first in outputs:
        for second in outputs:
            if first != second and Path(first).is_relative_to(Path(second)):
                raise ValueError('Scheduled batch outputs must not contain one another')
    return config, policy, bindings


@contextmanager
def _run_lock(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.parent / ('.site-schedule-' + hashlib.sha256(str(output).encode()).hexdigest() + '.lock')
    with lock_path.open('a+') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('This schedule already has an active runner') from error
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


async def run_schedule(value, output, *, resume=False, collector=None):
    """Run sites concurrently, batches within each site serially.

    collector injection is a Python-only test seam; the CLI always uses the
    real M4 collector with publication/admission/resource/recovery guards.
    """
    config, policy, bindings = validate_schedule(value)
    output = Path(output).resolve()
    for site in config['sites']:
        for batch in site['batches']:
            capture = Path(batch['output'])
            if output == capture or output.is_relative_to(capture) or capture.is_relative_to(output):
                raise ValueError('Schedule evidence and capture outputs must be separate directories')
    frozen = {'schema_version': VERSION + '-binding', 'config': config,
              'input_files_sha256': bindings, 'shared_policy': policy,
              'source_files_sha256': source_identity()}
    with _run_lock(output):
        if output.exists():
            if not resume or not (output / 'schedule.json').is_file():
                raise FileExistsError('Schedule output exists; explicit bound resume is required')
            if json.loads((output / 'schedule.json').read_text()) != frozen:
                raise ValueError('Schedule/config/input binding changed; keep the original run')
        else:
            output.mkdir(parents=True)
            write_json(output / 'schedule.json', frozen)
        from .admission_cohort import reserve_schedule
        try:
            cohort = reserve_schedule(frozen, output / 'schedule.json')
            if cohort:
                receipt = output / 'admission-cohort.json'
                if receipt.exists():
                    if json.loads(receipt.read_text()) != cohort:
                        raise ValueError('Frozen cohort reservation receipt changed')
                else:
                    write_json(receipt, cohort)
        except Exception as error:
            write_json(output / ('admission-reservation-failure-' + str(time.time_ns()) + '.json'),
                       {'error': str(error), 'sample_ids_allocated_by_reservation': 0,
                        'reservation_released': False, 'QC_approval': False})
            raise
        runner = collector or collect_m4
        slots = asyncio.Semaphore(config['max_parallel_sites'])
        domains = {}
        results, events = [], []
        stopped = asyncio.Event()
        active, peak = 0, 0
        started = time.time()
        def event(kind, **detail):
            row = {'at': time.time(), 'event': kind, **detail}
            events.append(row)
            with (output / 'events.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(canonical(row) + '\n')

        async def one_site(site):
            nonlocal active, peak
            plan = json.loads(Path(site['batches'][0]['plan']).read_text())
            domain = domain_key(plan['tasks'][0]['site_uri'])
            domain_slots = domains.setdefault(domain, asyncio.Semaphore(policy['max_domain_workers']))
            # Same-domain waiting must not consume a global site slot and
            # starve unrelated domains behind it.
            async with domain_slots, slots:
                active += 1
                peak = max(peak, active)
                event('site_started', site_key=site['site_key'], domain_key=domain, active_sites=active)
                try:
                    for batch in site['batches']:
                        if stopped.is_set():
                            results.append({'site_key': site['site_key'], 'output': batch['output'], 'status': 'NOT_STARTED_AFTER_ERROR'})
                            break
                        if (any(sha(path) != digest for path, digest in bindings.items())
                                or source_identity() != frozen['source_files_sha256']):
                            stopped.set()
                            raise ValueError('Frozen scheduled inputs or implementation changed before dispatch')
                        options = {'publication_path': Path(batch['publication']), 'policy_path': Path(batch['policy']),
                                   'resume': resume or batch.get('resume', False),
                                   'channel': batch.get('channel', 'chrome'), 'headless': batch.get('headless', True)}
                        outcome = await runner(Path(batch['plan']), Path(batch['output']), Path(config['registry']), **options)
                        expected = len(json.loads(Path(batch['plan']).read_text())['tasks'])
                        state = ('COLLECTED_PENDING_REVIEW' if outcome['collection_status'] == 'finished_pending_review'
                                 and outcome.get('collected') == expected else
                                 'INCOMPLETE_REQUIRES_REPLAN' if outcome['collection_status'] == 'finished_pending_review' else 'PAUSED')
                        results.append({'site_key': site['site_key'], 'output': batch['output'], 'status': state, 'result': outcome})
                        event('batch_finished', site_key=site['site_key'], output=batch['output'], status=state)
                        if state != 'COLLECTED_PENDING_REVIEW':
                            break
                except asyncio.CancelledError:
                    event('site_cancelled', site_key=site['site_key'], partial_trajectories_are_not_success=True)
                    raise
                except Exception as error:
                    stopped.set()
                    results.append({'site_key': site['site_key'], 'status': 'ERROR', 'error': str(error)})
                    event('site_error', site_key=site['site_key'], error=str(error))
                finally:
                    active -= 1
                    event('site_finished', site_key=site['site_key'], active_sites=active)

        tasks = [asyncio.create_task(one_site(site)) for site in config['sites']]
        interrupted = False
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=config['max_schedule_seconds'])
        except (asyncio.TimeoutError, asyncio.CancelledError):
            interrupted = True
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            event('schedule_interrupted', reason='timeout_or_cancel', recovery='explicit resume; never stitch partial trajectories')
        report = {'schema_version': VERSION + '-result', 'config_sha256': object_sha256(config),
                  'started_at': started, 'finished_at': time.time(), 'interrupted': interrupted,
                  'max_parallel_sites': config['max_parallel_sites'], 'peak_active_sites': peak,
                  'shared_max_workers': policy['max_workers'], 'shared_max_domain_workers': policy['max_domain_workers'],
                  'site_count': len(config['sites']), 'batch_results': results,
                  'admission_cohort': cohort,
                  'status': 'ERROR' if any(row['status'] == 'ERROR' for row in results) else
                            'PAUSED' if interrupted or len(results) != sum(len(site['batches']) for site in config['sites']) or
                            any(row['status'] != 'COLLECTED_PENDING_REVIEW' for row in results) else 'COLLECTED_PENDING_REVIEW',
                  'qualified_samples': 0, 'qc_status': 'NOT_GRANTED', 'customer_acceptance': 'UNKNOWN'}
        # Every invocation gets its own immutable report; events remain append-only.
        write_json(output / ('result-' + str(time.time_ns()) + '.json'), report)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)
    result = asyncio.run(run_schedule(json.loads(Path(args.config).read_text()), args.output, resume=args.resume))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'COLLECTED_PENDING_REVIEW' else 1


if __name__ == '__main__':
    raise SystemExit(main())
