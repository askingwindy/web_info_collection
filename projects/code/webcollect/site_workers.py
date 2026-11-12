"""Plan or launch foreground producer/consumer workers for selected Table1 sites."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

from site_planner.application_discovery import Discovery, classify_homepage, site_context
from site_planner.candidate_pool import CandidatePool
from webcollect.batch_core import BatchLedger
from webcollect.current_chain import current_evidence_roots, read_chain_scope
from webcollect.planning import object_sha256, verify_evidence
from .site_inventory import load_scope, resolve_sites, site_statistics


REPOSITORY = Path(__file__).resolve().parents[3]


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def split_even(total, parts):
    base, extra = divmod(total, parts)
    return [base + (1 if index < extra else 0) for index in range(parts)]


def new_plan(role, scope_path, scope, sites):
    plan_id = time.strftime('%Y%m%d%H%M%S') + '-' + uuid.uuid4().hex[:8]
    return {'plan_id': plan_id, 'role': role, 'scope': str(scope_path),
            'log_root': str(REPOSITORY / 'results' / 'site-workers' / plan_id),
            'sites': sites, 'workers': []}


def producer_sources(pool, site):
    record = Discovery(pool).get(site['id'])
    if (not record or record['classification_state'] != 'confirmed'
            or not record.get('decision', {}).get('homepage')):
        raise ValueError(f'Producer expansion requires a confirmed Table1 site: {site["id"]}')
    homepage = record['decision']['homepage']
    source = {'uri': homepage['uri'], 'title': site['name'], 'content': '',
              'reference': homepage['reference']}
    with pool.pool.connect() as con:
        aliases = [row[0] for row in con.execute(
            'SELECT host FROM aliases WHERE application_id=? ORDER BY host', (site['id'],))]
    hosts = sorted({site['host'], urlsplit(homepage['uri']).hostname.lower(), *aliases})
    return source, hosts


def prepare_plan(scope_path, selectors, *, sources_path=None):
    scope_path, scope = load_scope(scope_path)
    pool = CandidatePool(scope['pool'], readonly=True)
    selected = resolve_sites(pool, selectors)
    sites = [site_statistics(pool, site) for site in selected]
    plan = new_plan('prepare', scope_path, scope, sites)
    plan['sources'] = str(sources_path.absolute()) if sources_path else None
    plan['prepared'] = [{'application_id': site['application_id'],
                         'action': 'reuse' if site['classification_state'] == 'confirmed' else 'classify_serially'}
                        for site in sites]
    return plan


def prepare_sites(scope_path, selectors, *, sources_path=None):
    """Confirm selected Table1 rows serially; never produce Table2 candidates."""
    scope_path, scope = load_scope(scope_path)
    plan = prepare_plan(scope_path, selectors, sources_path=sources_path)
    pending = [site for site in plan['sites'] if site['classification_state'] != 'confirmed']
    if not pending:
        plan['ready'] = True
        return plan
    if not sources_path:
        raise ValueError('Pending Table1 sites require a homepage sources JSON file')
    sources = json.loads(Path(sources_path).read_text(encoding='utf-8'))
    if not isinstance(sources, list) or not sources:
        raise ValueError('Table1 preparation sources must be a nonempty JSON list')
    verify_evidence([source['reference'] for source in sources])
    pool = CandidatePool(scope['pool'])
    selected_ids = {site['application_id'] for site in plan['sites']}
    for source in sources:
        application = pool.pool.application(source['uri'])
        if not application or application['id'] not in selected_ids:
            raise ValueError('Preparation source is outside the selected Table1 sites')
    config = json.loads(Path(scope['producer_config']).read_text(encoding='utf-8'))
    chain = read_chain_scope(Path(scope['history_set']).absolute())
    root = current_evidence_roots(chain)[0] / 'producer-evidence' / object_sha256(
        [config['run_id'], 'table1-prepare'])
    root.mkdir(parents=True, exist_ok=True)
    ledger = BatchLedger(scope['producer_db'], config)
    batch = config['run_id'] + '/table1-prepare'
    context, failures = site_context(pool, ledger, batch, sources, root)
    if failures:
        raise ValueError('Table1 homepage preparation failed: ' + json.dumps(failures, ensure_ascii=False))
    for site in pending:
        homepages = [document for document in context
                     if document.get('site_evidence') == 'homepage'
                     and (pool.pool.application(document['uri']) or {}).get('id') == site['application_id']]
        if not homepages:
            raise ValueError(f'Missing prepared homepage for {site["id"]}')
        classify_homepage(pool, ledger, homepages[0], root, protocol='producer-site-classification-6')
    pool = CandidatePool(scope['pool'], readonly=True)
    selected = resolve_sites(pool, selectors)
    plan['sites'] = [site_statistics(pool, site) for site in selected]
    plan['ready'] = all(site['classification_state'] == 'confirmed' for site in plan['sites'])
    return plan


def producer_plan(scope_path, selectors, *, pages_per_site, workers,
                  prefer_simplified_chinese=False):
    scope_path, scope = load_scope(scope_path)
    pool = CandidatePool(scope['pool'], readonly=True)
    selected = resolve_sites(pool, selectors)
    sites = []
    for site in selected:
        stats = site_statistics(pool, site)
        stats['remaining'] = max(0, pages_per_site - stats['cumulative_new'])
        sites.append(stats)
    plan = new_plan('producer', scope_path, scope, sites)
    active = [(site, stats) for site, stats in zip(selected, sites) if stats['remaining']]
    if not active:
        return plan
    worker_quotas = split_even(workers, len(active))
    for (site, stats), worker_quota in zip(active, worker_quotas):
        source, hosts = producer_sources(pool, site)
        for target in split_even(stats['remaining'], worker_quota):
            if not target:
                continue
            number = len(plan['workers']) + 1
            worker_id = f'producer-{number:03d}'
            batch_key = f'{plan["plan_id"]}-p{number:03d}'
            command = [sys.executable, '-B', '-u', '-m',
                       'site_planner.candidate_discovery', 'produce-entries',
                       '--config', scope['producer_config'], '--ledger', scope['producer_db'],
                       '--pool', scope['pool'], '--history-set', scope['history_set'],
                       '--discovery-mode', 'expand', '--site-expansion',
                       '--search-engine', 'public', '--category', site['category'],
                       '--sources', json.dumps([source], ensure_ascii=False, separators=(',', ':')),
                       '--target', str(target), '--application-new-target', str(pages_per_site),
                       '--application-pending-cap', str(pages_per_site),
                       '--batch-key', batch_key]
            for host in hosts:
                command.extend(['--allowed-host', host])
            if prefer_simplified_chinese:
                command.append('--prefer-simplified-chinese')
            plan['workers'].append({'worker_id': worker_id, 'application_id': site['id'],
                                    'host': site['host'], 'target': target,
                                    'batch_key': batch_key, 'command': command})
    return plan


def consumer_plan(scope_path, selectors, *, workers):
    scope_path, scope = load_scope(scope_path)
    pool = CandidatePool(scope['pool'], readonly=True)
    selected = resolve_sites(pool, selectors)
    sites = [site_statistics(pool, site) for site in selected]
    plan = new_plan('consumer', scope_path, scope, sites)
    for site, worker_quota in zip(selected, split_even(workers, len(selected))):
        for _ in range(worker_quota):
            number = len(plan['workers']) + 1
            worker_id = f'{scope["consumer_worker"]}-{plan["plan_id"]}-c{number:03d}'
            request_prefix = f'{scope["request_prefix"]}/{plan["plan_id"]}/c{number:03d}'
            command = [sys.executable, '-B', '-u', '-m', 'webcollect.candidate_consumer', 'run',
                       '--pool', scope['pool'], '--config', scope['consumer_config'],
                       '--ledger', scope['consumer_db'], '--output', scope['output'],
                       '--registry', scope['registry'], '--policy', scope['policy'],
                       '--history-set', scope['history_set'], '--worker-id', worker_id,
                       '--request-prefix', request_prefix, '--application-id', site['id'],
                       '--stop-when-empty']
            if scope.get('qc_policy'):
                command.extend(['--qc-policy', scope['qc_policy']])
            plan['workers'].append({'worker_id': worker_id, 'application_id': site['id'],
                                    'host': site['host'], 'request_prefix': request_prefix,
                                    'command': command})
    return plan


def child_environment():
    projects = REPOSITORY / 'projects'
    paths = [str(projects / package) for package in ('code', 'site-planner', 'quality-inspector')]
    if os.environ.get('PYTHONPATH'):
        paths.append(os.environ['PYTHONPATH'])
    return {**os.environ, 'PYTHONPATH': os.pathsep.join(paths), 'PYTHONDONTWRITEBYTECODE': '1'}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def launch(plan):
    root = Path(plan['log_root'])
    root.mkdir(parents=True, exist_ok=False)
    if plan['role'] == 'producer':
        for index, worker in enumerate(plan['workers'], 1):
            command = worker['command']
            source_index = command.index('--sources') + 1
            sources = json.loads(command[source_index])
            source_path = root / f'w{index:03d}-sources.json'
            write_json(source_path, sources)
            command[source_index] = str(source_path)
            worker['sources_path'] = str(source_path)
    write_json(root / 'plan.json', plan)
    children = []
    interrupted = False
    with ExitStack() as stack:
        try:
            for index, worker in enumerate(plan['workers'], 1):
                log = stack.enter_context((root / f'w{index:03d}.log').open('wb'))
                process = subprocess.Popen(worker['command'], cwd=REPOSITORY,
                                           env=child_environment(), stdout=log,
                                           stderr=subprocess.STDOUT)
                children.append({'worker_id': worker['worker_id'], 'pid': process.pid,
                                 'log': str(root / f'w{index:03d}.log'), 'process': process})
            for child in children:
                child['returncode'] = child['process'].wait()
        except KeyboardInterrupt:
            interrupted = True
            for child in children:
                if child['process'].poll() is None:
                    child['process'].terminate()
            for child in children:
                child['returncode'] = child['process'].wait()
        except BaseException:
            for child in children:
                if child['process'].poll() is None:
                    child['process'].terminate()
            for child in children:
                child['process'].wait()
            raise
    summary = {'interrupted': interrupted,
               'workers': [{key: value for key, value in child.items() if key != 'process'}
                           for child in children]}
    summary['succeeded'] = all(child['returncode'] == 0 for child in children) and not interrupted
    write_json(root / 'summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='role', required=True)
    prepare = sub.add_parser('prepare', allow_abbrev=False)
    producer = sub.add_parser('producer', allow_abbrev=False)
    consumer = sub.add_parser('consumer', allow_abbrev=False)
    for role in (producer, consumer):
        role.add_argument('--scope', type=Path, required=True)
        role.add_argument('--site', action='append', required=True,
                          help='applications.id or registered primary/alias host; repeatable')
        role.add_argument('--workers', type=positive, required=True,
                          help='Total operating-system worker processes, divided evenly across sites')
        role.add_argument('--launch', action='store_true',
                          help='Actually launch and wait; without this flag only print the plan')
    prepare.add_argument('--scope', type=Path, required=True)
    prepare.add_argument('--site', action='append', required=True,
                         help='Existing applications.id or registered primary/alias host; repeatable')
    prepare.add_argument('--sources', type=Path,
                         help='Homepage source list required only when a selected site is pending')
    prepare.add_argument('--launch', action='store_true',
                         help='Serially classify pending Table1 sites; never produce Table2 rows')
    producer.add_argument('--pages-per-site', type=positive, required=True,
                          help='Cumulative distinct NEW ceiling per site in this project')
    producer.add_argument('--prefer-simplified-chinese', action='store_true')
    consumer.add_argument('--all-pending', action='store_true', required=True,
                          help='Claim all currently eligible pending rows across producer batches; exit when empty')
    args = parser.parse_args(argv)
    try:
        if args.role == 'prepare':
            if args.launch:
                result = {'launched': True, **prepare_sites(args.scope, args.site, sources_path=args.sources)}
                code = 0 if result['ready'] else 2
            else:
                result = {'launched': False, **prepare_plan(args.scope, args.site, sources_path=args.sources)}
                code = 0
        else:
            if args.role == 'producer':
                plan = producer_plan(args.scope, args.site, pages_per_site=args.pages_per_site,
                                     workers=args.workers,
                                     prefer_simplified_chinese=args.prefer_simplified_chinese)
            else:
                plan = consumer_plan(args.scope, args.site, workers=args.workers)
            if not args.launch:
                result = {'launched': False, **plan}
                code = 0
            else:
                summary = launch(plan)
                result = {'launched': True, **plan, 'launch_summary': summary}
                code = 130 if summary['interrupted'] else 0 if summary['succeeded'] else 1
    except (KeyError, ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
