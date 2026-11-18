"""Prepare or launch a chosen number of consumers on the original shared scope."""
import argparse
from webcollect import workspace_json as json
from pathlib import Path
import re
import subprocess
import sys




def build_roster(scope, count, prefix, *, job_limit, campaign_limit):
    if type(count) is not int or count < 1:
        raise ValueError('consumer count must be positive')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', prefix):
        raise ValueError('use a nonempty filesystem-safe run prefix')
    shared = ('pool', 'consumer_db', 'registry', 'output', 'policy', 'consumer_config', 'history_set', 'batch')
    if any(not scope.get(k) for k in shared):
        raise ValueError('complete original consumer scope required')
    # Output is shared intentionally: candidate claims own unique subdirectories.
    # Never create a replacement pool/registry to evade an unresolved claim.
    return {'schema_version': 'consumer-roster', 'authorized_job_limit': job_limit, 'authorized_campaign_limit': campaign_limit,
            'count': count, 'prefix': prefix, 'launch_state': 'NOT_STARTED',
            'workers': [{'number': i, 'scope_file': f'scope-w{i}.json',
                         'scope': {**scope, 'consumer_worker': f'{prefix}-w{i}',
                                   'request_prefix': f'{prefix}-w{i}'}}
                        for i in range(1, count + 1)]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scope', type=Path, required=True)
    p.add_argument('--workers', type=int, required=True)
    p.add_argument('--prefix', required=True)
    p.add_argument('--output', type=Path, required=True, help='new preparation and launch log directory')
    p.add_argument('--launch', action='store_true')
    p.add_argument('--limit', type=int, required=True, help='total candidate limit across all workers')
    selection = p.add_mutually_exclusive_group()
    selection.add_argument('--cohort', type=Path)
    selection.add_argument('--recovery-version', help='only consume candidates recovered for this exact repair version')
    p.add_argument('--first-plan-effort', choices=('low', 'high', 'max'), default='high')
    p.add_argument('--branch-effort', choices=('low', 'high', 'max'), default='high')
    a = p.parse_args()
    if a.limit < 1:
        p.error('--limit must be positive')
    scope = json.loads(a.scope.read_text())
    config = json.loads(Path(scope['consumer_config']).read_text())
    policy = json.loads(Path(scope['policy']).read_text())
    if a.workers < 1:
        p.error('--workers must be positive')
    a.output.mkdir(parents=True, exist_ok=False)
    if a.launch:
        reason = f'consumer_roster --workers {a.workers} --prefix {a.prefix}'
        from .consumer_ab import adjust_concurrency
        adjusted = adjust_concurrency(scope['consumer_db'], scope['consumer_config'], target=None, authorization=reason)
        from .runtime import RuntimeStore
        runtime_setting = RuntimeStore(scope['registry'], 'project-setup').set_consumer_concurrency(
            max_workers=None, max_domain_workers=None, reason=reason)
        # Frozen config/policy files stay bound to existing in-flight work.
        # Worker count controls this launch; retired Runtime ceilings are not
        # rewritten merely to match the requested process count.
        (a.output / 'concurrency-adjustment.json').write_text(json.dumps(adjusted, indent=2) + '\n')
        (a.output / 'runtime-concurrency.json').write_text(json.dumps(runtime_setting, indent=2) + '\n')
    roster = build_roster(scope, a.workers, a.prefix,
                          job_limit=None, campaign_limit=None)
    roster['concurrency_control'] = 'launched_consumer_workers'
    roster['concurrency_settings_applied'] = a.launch
    roster['historical_config_limits'] = {
        'max_concurrent_jobs': config['budget']['max_concurrent_jobs'],
        'max_workers': policy['max_workers'], 'max_domain_workers': policy['max_domain_workers']}
    roster['total_limit'] = a.limit
    roster['recovery_version'] = a.recovery_version
    roster['effort_profile'] = {'first_plan': a.first_plan_effort, 'branch': a.branch_effort}
    cohort = json.loads(a.cohort.read_text()) if a.cohort else None
    selected = cohort['selected'][:a.limit] if cohort else None
    for worker in roster['workers']:
        worker['limit'] = a.limit // a.workers + (worker['number'] <= a.limit % a.workers)
        if cohort:
            rows = selected[worker['number'] - 1::a.workers]
            worker['limit'] = len(rows)
            if rows:
                shard = {**cohort, 'selected': [{**row, 'order': i} for i, row in enumerate(rows, 1)], 'denominator': len(rows)}
                shard_path = (a.output / f"cohort-w{worker['number']}.json").resolve()
                shard_path.write_text(json.dumps(shard, ensure_ascii=False, indent=2) + '\n')
                worker['cohort'] = str(shard_path)
        (a.output / worker['scope_file']).write_text(json.dumps(worker['scope'], ensure_ascii=False, indent=2) + '\n')
    (a.output / 'roster.json').write_text(json.dumps(roster, ensure_ascii=False, indent=2) + '\n')
    processes = []
    if a.launch:
        for worker in roster['workers']:
            if not worker['limit']:
                continue
            ws = worker['scope']
            command = [sys.executable, '-m', 'webcollect.candidate_consumer', '--pool', ws['pool'], 'run', '--protocol', 'entry']
            for flag, key in (('config', 'consumer_config'), ('ledger', 'consumer_db'), ('output', 'output'), ('registry', 'registry'), ('policy', 'policy'), ('history-set', 'history_set'), ('worker-id', 'consumer_worker'), ('request-prefix', 'request_prefix')):
                command += ['--' + flag, str(ws[key])]
            command += ['--limit', str(worker['limit']), '--producer-batch', str(ws['batch']),
                        '--first-plan-effort', a.first_plan_effort, '--branch-effort', a.branch_effort]
            if a.cohort:
                command += ['--cohort', worker['cohort']]
            if a.recovery_version:
                command += ['--recovery-version', a.recovery_version]
            log = (a.output / ('worker-' + str(worker['number']) + '.log')).open('xb')
            try:
                processes.append(subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT))
            finally:
                log.close()
        roster['launch_state'] = 'FINISHED'
        roster['returncodes'] = [process.wait() for process in processes]
        (a.output / 'launch-result.json').write_text(json.dumps(roster, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'prepared': a.workers, 'launched': len(processes), 'roster': str(a.output / 'roster.json')}))


if __name__ == '__main__':
    main()
