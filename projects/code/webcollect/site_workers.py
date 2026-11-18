"""Plan or launch foreground producer/consumer workers for selected Table1 sites."""
import argparse
from contextlib import ExitStack
from webcollect import workspace_json as json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

from site_planner.application_discovery import Discovery, classify_homepage, site_context
from site_planner.candidate_pool import CandidatePool
from site_planner.entry_selection import compile_entry_exclusions, entry_is_excluded
from webcollect.batch_core import BatchLedger, file_sha
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
    from .collection_startup import check
    checked=check(scope_path)
    if checked['status']!='PASS':
        raise ValueError('Preparation launch preflight failed: '+json.dumps(checked,ensure_ascii=False))
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


def load_seed_files(paths):
    """Load evidence-backed expansion seeds from JSON lists, grouped by hostname.

    A seed page other than the Table1 decision homepage is fetched with its
    raw HTML, so category/entry seeds let a site expand through its own links;
    the saved homepage decision alone carries no hrefs to extract."""
    grouped = {}
    for path in paths:
        seeds = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(seeds, list):
            raise ValueError(f'Seeds file must hold a JSON list: {path}')
        for seed in seeds:
            host = (urlsplit(seed['uri']).hostname or '').lower()
            reference = seed.get('reference') or {}
            if not host or not reference.get('path') or not reference.get('sha256'):
                raise ValueError(f'Seed needs uri and sha256 evidence reference: {seed.get("uri")}')
            evidence = Path(reference['path'])
            if not evidence.is_file() or file_sha(evidence) != reference['sha256']:
                raise ValueError(f'Seed evidence missing or changed: {seed["uri"]} -> {evidence}')
            grouped.setdefault(host, []).append(seed)
    return grouped


def producer_plan(scope_path, selectors, *, pages_per_site, workers,
                  prefer_simplified_chinese=False, seed_files=(), net_new=False):
    scope_path, scope = load_scope(scope_path)
    pool = CandidatePool(scope['pool'], readonly=True)
    selected = resolve_sites(pool, selectors)
    seeds_by_host = load_seed_files(seed_files)
    site_sources = {site['id']: producer_sources(pool, site) for site in selected}
    sites = []
    for site in selected:
        stats = site_statistics(pool, site)
        source, hosts = site_sources[site['id']]
        seeds = [seed for host in hosts for seed in seeds_by_host.get(host, [])] or [source]
        patterns = compile_entry_exclusions(seeds)
        excluded = 0
        if patterns:
            with pool.pool.connect() as con:
                rows = con.execute(
                    "SELECT DISTINCT c.candidate_id,json_extract(c.body,'$.entry_url') "
                    "FROM data_candidates c JOIN candidate_batch_rows b USING(candidate_id) "
                    "WHERE c.application_id=? AND b.result='NEW'", (site['id'],)).fetchall()
            excluded = sum(entry_is_excluded(row[1], patterns) for row in rows)
        stats['excluded_existing'] = excluded
        stats['eligible_cumulative_new'] = stats['cumulative_new'] - excluded
        stats['startup_cumulative_new'] = stats['cumulative_new']
        stats['target_basis'] = 'round_net_new' if net_new else 'cumulative_new'
        stats['remaining'] = pages_per_site if net_new else max(0, pages_per_site - stats['eligible_cumulative_new'])
        stats['application_new_target'] = (stats['cumulative_new'] + pages_per_site if net_new else pages_per_site + excluded)
        sites.append(stats)
    plan = new_plan('producer', scope_path, scope, sites)
    active = [(site, stats) for site, stats in zip(selected, sites) if stats['remaining']]
    if not active:
        return plan
    selected_hosts = {host for _, hosts in site_sources.values() for host in hosts}
    unmatched = sorted(set(seeds_by_host) - selected_hosts)
    if unmatched:
        raise ValueError(f'Seed hosts do not match any selected site: {", ".join(unmatched)}')
    worker_quotas = split_even(workers, len(active))
    for (site, stats), worker_quota in zip(active, worker_quotas):
        source, hosts = site_sources[site['id']]
        site_seeds = [seed for host in hosts for seed in seeds_by_host.get(host, [])]
        exclusions = sorted({pattern for seed in site_seeds
                             for pattern in seed.get('excluded_entry_patterns', [])})
        for worker_index, target in enumerate(split_even(stats['remaining'], worker_quota)):
            if not target:
                continue
            number = len(plan['workers']) + 1
            worker_id = f'producer-{number:03d}'
            batch_key = f'{plan["plan_id"]}-p{number:03d}'
            seeds = [site_seeds[worker_index % len(site_seeds)]] if site_seeds else [source]
            if net_new:
                seeds=[{**seed,'simplified_chinese_only':True} for seed in seeds]
            if exclusions:
                seeds = [{**seed, 'excluded_entry_patterns': exclusions} for seed in seeds]
            command = [sys.executable, '-B', '-u', '-m',
                       'site_planner.candidate_discovery', 'produce-entries',
                       '--config', scope['producer_config'], '--ledger', scope['producer_db'],
                       '--pool', scope['pool'], '--history-set', scope['history_set'],
                       '--discovery-mode', 'expand', '--site-expansion',
                       '--search-engine', 'public', '--category', site['category'],
                       '--sources', json.dumps(seeds, ensure_ascii=False, separators=(',', ':')),
                       '--target', str(target), '--application-new-target', str(stats['application_new_target']),
                       '--application-pending-cap', str(stats['application_new_target']),
                       '--batch-key', batch_key]
            for host in hosts:
                command.extend(['--allowed-host', host])
            if prefer_simplified_chinese:
                command.append('--prefer-simplified-chinese')
            plan['workers'].append({'worker_id': worker_id, 'application_id': site['id'],
                                    'host': site['host'], 'target': target,
                                    'batch_key': batch_key, 'seeds': [seed['uri'] for seed in seeds], 'command': command})
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


def fixed_consumer_plan(scope_path, cohort_path, log_root):
    """Prepare 20 static worker shards, five pages each, no exports or save target."""
    from .batch_core import load_json, save_json, file_sha
    scope_path, scope=load_scope(scope_path)
    cohort=load_json(cohort_path)
    rows=cohort['selected']
    sites=sorted({r['application_id'] for r in rows})
    if len(rows)!=100 or len({r['candidate_id'] for r in rows})!=100:
        raise ValueError('Fixed collection requires 100 unique candidates')
    root=Path(log_root).resolve();root.mkdir(parents=True,exist_ok=False)
    from .workspace_paths import prepare_output
    prepare_output(root,scope_path)
    plan=new_plan('consumer',scope_path,scope,sites)
    plan.update(log_root=str(root),cohort=str(Path(cohort_path).resolve()), collection_strategy='screenshot_plan',
                automatic_export=False, stop_after_saves=None, fixed=True)
    for index in range(20):
        shard=[dict(r,order=n+1) for n,r in enumerate(rows[index*5:index*5+5])]
        number=len(plan['workers'])+1;wid=f'fixed-{plan["plan_id"]}-{number:02d}'
        path=root/f'w{number:02d}-cohort.json'
        save_json(path,{**cohort,'selected':shard,'denominator':5})
        output=Path(scope['output'])/plan['plan_id']/wid
        command=[sys.executable,'-B','-u','-m','webcollect.candidate_consumer','run',
            '--pool',scope['pool'],'--config',scope['consumer_config'],'--ledger',scope['consumer_db'],
            '--registry',scope['registry'],'--history-set',scope['history_set'],'--policy',scope['policy'],
            '--output',str(output),'--worker-id',wid,'--request-prefix',wid,'--limit','5',
            '--cohort',str(path),'--collection-strategy','screenshot_plan',
            '--log-dir',str(root/'runtime'/wid)]
        plan['workers'].append({'worker_id':wid,'application_ids':sorted({r['application_id'] for r in shard}),'candidate_ids':[r['candidate_id'] for r in shard],
                                'command':command})
    save_json(root/'prepared-plan.json',plan)
    return plan


def child_environment():
    projects = REPOSITORY / 'projects'
    paths = [str(projects / package) for package in ('code', 'site-planner', 'quality-inspector')]
    if os.environ.get('PYTHONPATH'):
        paths.append(os.environ['PYTHONPATH'])
    return {**os.environ, 'PYTHONPATH': os.pathsep.join(paths), 'PYTHONDONTWRITEBYTECODE': '1'}


def write_json(path, value):
    from .workspace_paths import bind
    bind(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def automatic_report(plan,root,summary):
    """After bounded drain on every exit; diagnostics never skip worker settlement."""
    from .collection_report import build,markdown
    try:
        report=build(plan['scope'],plan['cohort'],root)
        write_json(root/'funnel.json',report)
        (root/'funnel.md').write_text(markdown(report))
        summary['report_integrity']=report['integrity']
        if report['integrity']!='PASS':summary['succeeded']=False
    except BaseException as error:
        summary['report_integrity']='FAILED'
        summary['report_error']={'type':type(error).__name__,'reason':str(error)}
        summary['succeeded']=False
        try:
            write_json(root/'report-error.json',summary['report_error'])
            (root/'funnel.md').write_text('# Collection report failed\n\n'+type(error).__name__+': '+str(error)+'\n')
        except Exception as diagnostic:
            print('REPORT_FAILED: '+str(error)+'; diagnostic failed: '+str(diagnostic),file=sys.stderr)
    try:
        write_json(root/'summary.json',summary)
    except Exception as error:
        print('Summary diagnostic failed after reporting: '+str(error),file=sys.stderr)
    return summary


def launch(plan):
    import signal
    from .failure_policy import RoundFailures
    from .collection_startup import check
    from .workspace_paths import prepare_output
    root=Path(plan['log_root'])
    root.mkdir(parents=True,exist_ok=bool(plan.get('fixed')))
    stop=root/'stop.request';failures=RoundFailures(root/'failure-events.jsonl')
    started_at=time.time();started_monotonic=time.monotonic()
    children=[];interrupted=False;error=None;drain_deadline=None
    stop_reason=None;preflight=None;preparing=True
    def request_stop(signum,frame):
        nonlocal interrupted,drain_deadline
        interrupted=True;stop.touch();drain_deadline=drain_deadline or time.monotonic()+120
        if preparing:raise InterruptedError('Stopped during launch preparation')
    previous={sig:signal.signal(sig,request_stop) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        if stop.exists():raise InterruptedError('Stopped before launch')
        preflight=check(plan['scope'],**({'cohort_path':plan['cohort'],'plan':plan} if plan.get('fixed') else {}))
        if preflight['status']!='PASS':
            stop_reason='preflight_failed'
            raise ValueError('Launch preflight failed; see preflight errors')
        prepare_output(root,plan['scope'])
        write_json(root/'plan.json',plan)
        if plan['role']=='consumer':
            from .batch_core import load_json
            from .key_health import pool_available,probe_accounts
            _,scope=load_scope(plan['scope'])
            ledger=BatchLedger(scope['consumer_db'],load_json(scope['consumer_config']))
            if stop.exists():raise InterruptedError('Stopped before account probes')
            launch_id='fixed-round:'+plan['plan_id']
            probes=[]
            if not pool_available(ledger):probes=probe_accounts(ledger,launch_id)
            write_json(root/'startup-probes.json',{'launch_id':launch_id,'probes':probes})
            if stop.exists():raise InterruptedError('Stopped after account probes')
            if not pool_available(ledger):
                stop_reason='key_pool_unavailable'
                raise ValueError('No available model account')
        env={**child_environment(),'WEBCOLLECT_STOP_FILE':str(stop),'WEBCOLLECT_PRODUCER_STOP_FILE':str(stop),
             'WEBCOLLECT_ROUND_EVENTS':str(failures.path),'WEBCOLLECT_CENTRAL_KEY_HEALTH':'1'}
        if plan['role']=='producer':
            for index,worker in enumerate(plan['workers'],1):
                command=worker['command'];at=command.index('--sources')+1
                sources=json.loads(command[at]);path=root/f'w{index:03d}-sources.json'
                write_json(path,sources);command[at]=str(path);worker['sources_path']=str(path)
            write_json(root/'plan.json',plan)
        preparing=False
        with ExitStack() as stack:
            for index,worker in enumerate(plan['workers'],1):
                if stop.exists() or failures.stopped():break
                command=list(worker['command'])
                log=stack.enter_context((root/f'w{index:03d}.log').open('xb'))
                p=subprocess.Popen(command,cwd=REPOSITORY,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
                children.append({'worker_id':worker['worker_id'],'pid':p.pid,'process':p})
            while any(c['process'].poll() is None for c in children):
                bad=[c for c in children if c['process'].poll() not in (None,0)]
                if bad or failures.stopped() or stop.exists():
                    stop.touch();drain_deadline=drain_deadline or time.monotonic()+120
                    for child in children:
                        if child['process'].poll() is None and not child.get('stop_sent'):
                            child['process'].send_signal(signal.SIGINT);child['stop_sent']=True
                    # Gracefully cancel only owned workers, once, after current dispatch settles or at deadline.
                    if time.monotonic()>=drain_deadline:
                        break
                time.sleep(.2)
    except BaseException as caught:
        interrupted=interrupted or isinstance(caught,(KeyboardInterrupt,InterruptedError))
        stop_reason=stop_reason or ('user_stop' if interrupted else 'launch_error')
        error={'type':type(caught).__name__,'reason':str(caught)};stop.touch()
    finally:
        try:
            # Stop requests fence new claims; SIGINT asks each owned CLI to seal its in-flight session.
            for c in children:
                if c['process'].poll() is None and not c.get('stop_sent'):c['process'].send_signal(signal.SIGINT);c['stop_sent']=True
            deadline=time.monotonic()+125
            while any(c['process'].poll() is None for c in children) and time.monotonic()<deadline:
                time.sleep(.2)
            for c in children:
                if c['process'].poll() is None:c['process'].terminate()
            deadline=time.monotonic()+5
            for c in children:
                try:c['process'].wait(timeout=max(.01,deadline-time.monotonic()))
                except subprocess.TimeoutExpired:c['process'].kill();c['process'].wait(timeout=5)
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)
            summary={'plan_id':plan['plan_id'],'interrupted':interrupted,'error':error,'started_at':started_at,
                     'finished_at':time.time(),'elapsed_seconds':time.monotonic()-started_monotonic,
                     'workers':[{**{k:v for k,v in c.items() if k!='process'},'returncode':c['process'].poll()} for c in children],
                     'unlaunched':len(plan.get('workers',[]))-len(children),'automatic_export':False,
                     'stop_reason':stop_reason,'preflight':preflight}
            summary['succeeded']=bool(children) and len(children)==len(plan.get('workers',[])) and all(c['process'].poll()==0 for c in children) and not interrupted and not error and not stop.exists() and not failures.stopped()
            try:
                write_json(root/'summary.json',summary)
            except Exception as diagnostic_error:
                summary['summary_write_error']=str(diagnostic_error)
                print('Worker drain completed; summary write failed: '+str(diagnostic_error),file=sys.stderr)
            if plan.get('fixed'):automatic_report(plan,root,summary)
            elif plan['role']=='producer':
                try:
                    from .collection_report import producer_round
                    production=producer_round(plan)
                    write_json(root/'producer-summary.json',production)
                    (root/'producer-summary.md').write_text('# Producer round\n\n```json\n'+json.dumps(production,ensure_ascii=False,indent=2)+'\n```\n')
                except Exception as error:
                    summary['producer_report_error']=str(error)
                    summary['succeeded']=False
                    write_json(root/'producer-report-error.json',{'error':str(error)})
                try:write_json(root/'summary.json',summary)
                except Exception as error:print('Producer summary write failed: '+str(error),file=sys.stderr)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='role', required=True)
    prepare = sub.add_parser('prepare', allow_abbrev=False)
    producer = sub.add_parser('producer', allow_abbrev=False)
    consumer = sub.add_parser('consumer', allow_abbrev=False)
    freeze=sub.add_parser('freeze-baseline',allow_abbrev=False)
    freeze.add_argument('--scope',required=True,type=Path)
    freeze.add_argument('--producer-plan',required=True,type=Path)
    freeze.add_argument('--output',required=True,type=Path)
    fixed = sub.add_parser('fixed-consumer', allow_abbrev=False)
    fixed.add_argument('--scope',type=Path,required=True)
    fixed.add_argument('--cohort',type=Path,required=True)
    fixed.add_argument('--log-root',type=Path,required=True)
    fixed.add_argument('--launch',action='store_true')
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
    producer.add_argument('--net-new', action='store_true', help='Target additional NEW above this launch baseline, never historical cumulative inventory')
    producer.add_argument('--prefer-simplified-chinese', action='store_true')
    producer.add_argument('--seeds-file', action='append', default=[], type=Path,
                          help='Evidence-backed seed JSON lists; round-robin across site workers; repeatable')
    consumer.add_argument('--all-pending', action='store_true', required=True,
                          help='Claim all currently eligible pending rows across producer batches; exit when empty')
    args = parser.parse_args(argv)
    try:
        if args.role == 'freeze-baseline':
            from .candidate_cohort import freeze_round
            result=freeze_round(args.scope,args.producer_plan,args.output)
            code=0 if result['ready'] else 2
        elif args.role == 'fixed-consumer':
            plan=fixed_consumer_plan(args.scope,args.cohort,args.log_root)
            result={'launched':False,**plan}
            code=0
            if args.launch:
                summary=launch(plan);result.update(launched=True,launch_summary=summary)
                code=0 if summary['succeeded'] else 2
        elif args.role == 'prepare':
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
                                     prefer_simplified_chinese=args.prefer_simplified_chinese,
                                     seed_files=args.seeds_file, net_new=args.net_new)
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
