"""Initialize a local candidate project. Publish the launch scope after all stores are ready."""
from webcollect.sqlite_connection import raw_connect as workspace_connect
import argparse
from contextlib import closing
from webcollect import workspace_json as json
from pathlib import Path
import re
import sqlite3
import time

from .batch_core import load_json, save_json, validate_config
from .current_chain import PROJECT_RULES, POOL_CHECKPOINT, initialize_chain
from .runtime import RuntimeStore, validate_policy
from .site_failure_stop import SiteFailureStore


def numbering_floors(registries):
    """Carry numeric reservations across a cutover, without carrying page or site decisions."""
    floors = {}
    for registry in registries:
        with closing(workspace_connect(Path(registry).resolve().as_uri() + '?mode=ro', uri=True)) as con:
            values = [('site', con.execute('SELECT COALESCE(MAX(id),0) FROM sites').fetchone()[0])]
            for (bid,) in con.execute('SELECT id FROM batches'):
                prefix, number = bid.rsplit('_',1)
                values.append((prefix, int(number)))
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='allocation_floors'").fetchone():
                values.extend(con.execute('SELECT name,last_number FROM allocation_floors'))
            for name, number in values:
                floors[name] = max(floors.get(name,0),number)
    return floors


def initialize(root, project_id, policy_template, producer_template, consumer_template, *, numbering_from=(), qc_policy=None, output_root=None):
    from site_planner.site_pool import SitePool
    from site_planner.candidate_pool import CandidatePool
    if not re.fullmatch(r'[\w.-]+',project_id) or project_id in ('.','..'):
        raise ValueError('A project requires a distinct local project ID')
    repository = Path(__file__).resolve().parents[3]
    root = (Path(root) if root is not None else
            repository / 'database' / 'sqllite' / 'prod').absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError('Project root cannot be a symbolic link')
    root = root.resolve()
    if {'results', 'verify_results'} & set(root.parts):
        raise ValueError('Persistent project root cannot be inside results or verify_results')
    state = root
    registry = state/'production-registry.sqlite3'
    pool_path = state/'candidate-pool.sqlite3'
    manifest = root/'chain'/'manifest.json'
    results = (Path(output_root) if output_root is not None else
               repository / 'results' / project_id / 'collections').absolute()
    if any(p.is_symlink() for p in (results, *results.parents)):
        raise ValueError('Output root cannot be a symbolic link')
    results = results.resolve()
    if results == root or root.is_relative_to(results):
        raise ValueError('Output root cannot contain the persistent project root')
    since = time.time()
    guard = {'ledger':str(state/'site-facts.sqlite3'),'campaign_id':project_id,
             'formal_since':since,'dispatch_rules':PROJECT_RULES}
    project = {'rules':PROJECT_RULES,'pool':str(pool_path),'site_ledger':guard['ledger']}
    policy = validate_policy({**policy_template,'campaign_id':project_id,'baseline_category_counts':{},
                              'resource_root':str(results),'pilot_identity_required':True,'site_failure_guard':guard})
    configs = {}
    for role, template in (('producer', producer_template), ('consumer', consumer_template)):
        configs[role] = validate_config({**template, 'run_id':project_id+'-'+role,'site_failure_guard':guard})
    if qc_policy is not None:
        from .task_generation import _qc_policy
        qc_policy = _qc_policy(qc_policy)
    floors = numbering_floors(numbering_from)
    owned = [root/'scope.json',manifest,registry,pool_path,state/'site-facts.sqlite3',
             state/'producer-jobs.sqlite3',state/'consumer-jobs.sqlite3',state/'policy.json',
             state/'producer-config.json',state/'consumer-config.json']
    if qc_policy is not None:
        owned.append(state/'qc-policy.json')
    existing = [str(path) for path in owned if path.exists() or path.is_symlink()]
    if existing:
        raise ValueError('Persistent project root already contains project files: ' + ', '.join(existing))
    if root.exists() and not root.is_dir():
        raise ValueError('Persistent project root must be a directory')
    # The fixed root may contain unrelated legacy project subdirectories. Only
    # this root's own scope/config/database files exclude a new initialization.
    root.mkdir(parents=True,exist_ok=True)
    from .workspace_paths import prepare
    common = Path(__import__('os').path.commonpath((root, results)))
    prepare(root, common)
    prepare(results, common)
    # An incomplete initialization keeps its files for diagnosis. The scope is published last.
    results.mkdir(parents=True, exist_ok=True)
    owner = initialize_chain(manifest,registry,chain_id=project_id,current_result_roots=[results],
                             now=since,candidate_project=project)
    with closing(workspace_connect(registry)) as con:
        con.execute('CREATE TABLE allocation_floors(name TEXT PRIMARY KEY,last_number INTEGER NOT NULL)')
        con.executemany('INSERT INTO allocation_floors VALUES(?,?)',floors.items())
        con.commit()
    SiteFailureStore.initialize(guard)
    SitePool(pool_path,initialize=True)
    pool = CandidatePool(pool_path,install=True)
    pool.pool.checkpoint(*POOL_CHECKPOINT,owner['manifest'])
    RuntimeStore(registry,'project-setup').initialize(policy,now=since)
    save_json(state/'policy.json',policy)
    scope = {'batch':configs['producer']['run_id']+'/entry-batch/main',
             'pool':str(pool_path),'history_set':str(manifest),'registry':str(registry),
             'policy':str(state/'policy.json'),'output':str(results/'consumer'),
             'consumer_worker':project_id+'-worker-1','request_prefix':project_id+'-main-1','started_at':since}
    for role, config in configs.items():
        path = state/(role+'-config.json')
        save_json(path,config)
        from .batch_core import BatchLedger
        prepared_ledger=BatchLedger(state/(role+'-jobs.sqlite3'), config, initialize=True)
        if role=='consumer':
            from .key_health import ensure_schema
            with prepared_ledger.transaction() as con:
                ensure_schema(con)
        scope[role+'_config'] = str(path)
        scope[role+'_db'] = str(state/(role+'-jobs.sqlite3'))
    if qc_policy is not None:
        path = state/'qc-policy.json'
        save_json(path,qc_policy)
        scope['qc_policy'] = str(path)
    save_json(root/'scope.json',scope)
    return root/'scope.json'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init'])
    parser.add_argument('--root', type=Path,
                        help='Persistent project root (default: database/sqllite/prod for production; '
                             'verification projects use an explicit --root under database/sqllite/verification)')
    parser.add_argument('--output-root', type=Path,
                        help='Collection output root (default: results/<project-id>/collections)')
    for name in ('project-id','policy-template','producer-config','consumer-config'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--numbering-from',action='append',default=[],help='Read numeric high-water marks from an earlier registry')
    parser.add_argument('--qc-policy',type=Path)
    args=parser.parse_args(argv)
    scope=initialize(args.root,args.project_id,load_json(args.policy_template),load_json(args.producer_config),
                     load_json(args.consumer_config),numbering_from=args.numbering_from,
                     qc_policy=load_json(args.qc_policy) if args.qc_policy else None,
                     output_root=args.output_root)
    print(json.dumps({'scope':str(scope),'rules':PROJECT_RULES,'roles_started':0}))


if __name__=='__main__':
    main()


def prepare_existing_wal(scope_path, backup_root, *, drained=False):
    """Explicit offline preparation only; never called from startup checks/workers."""
    from .site_inventory import load_scope
    from .sqlite_connection import backup,connect,prepare_wal
    if drained is not True:raise ValueError('All users must be drained before preparing existing stores')
    _,scope=load_scope(scope_path)
    guard=load_json(scope['consumer_config'])['site_failure_guard']
    paths=[Path(scope[k]) for k in ('pool','producer_db','consumer_db','registry')]+[Path(guard['ledger'])]
    backup_root=Path(backup_root).resolve();backup_root.mkdir(parents=True,exist_ok=False)
    # Existing undecided requests remain original rows, including reserved/UNKNOWN.
    # Reject active leases; this is not an automatic recovery or lease reset.
    for role in ('producer_db','consumer_db'):
        with closing(connect(scope[role],readonly=True)) as con:
            if con.execute("SELECT 1 FROM jobs WHERE state='running' AND lease>? LIMIT 1",(time.time(),)).fetchone():
                raise ValueError('Live job lease remains; do not switch shared stores')
    with closing(connect(scope['pool'],readonly=True)) as con:
        if con.execute("SELECT 1 FROM candidate_claims WHERE state='consuming' AND expires>? LIMIT 1",(time.time(),)).fetchone():
            raise ValueError('Live candidate lease remains; do not switch shared stores')
    with closing(connect(scope['registry'],readonly=True)) as con:
        if con.execute("SELECT 1 FROM m4_attempts WHERE status IN ('reserved','running') AND lease_expires_at>? LIMIT 1",(time.time(),)).fetchone():
            raise ValueError('Live attempt lease remains; do not switch shared stores')
    report=[]
    for path in paths:
        target=backup_root/path.name;backup(path,target)
        with closing(connect(path,durable=path.name not in ('candidate-pool.sqlite3','site-facts.sqlite3'))) as con:
            previous=con.execute('PRAGMA journal_mode').fetchone()[0];prepare_wal(con)
        report.append({'path':str(path),'backup':str(target),'previous':previous,'journal_mode':'wal'})
    save_json(backup_root/'preparation.json',{'drained':True,'stores':report,'cross_database_atomic':False,'original_rows_rewritten':False})
    return report
