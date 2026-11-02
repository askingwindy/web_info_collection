"""Initialize a local candidate project. Publish the launch scope after all stores are ready."""
import argparse
from contextlib import closing
import json
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
        with closing(sqlite3.connect(Path(registry).resolve().as_uri() + '?mode=ro', uri=True)) as con:
            values = [('site', con.execute('SELECT COALESCE(MAX(id),0) FROM sites').fetchone()[0])]
            for (bid,) in con.execute('SELECT id FROM batches'):
                prefix, number = bid.rsplit('_',1)
                values.append((prefix, int(number)))
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='allocation_floors'").fetchone():
                values.extend(con.execute('SELECT name,last_number FROM allocation_floors'))
            for name, number in values:
                floors[name] = max(floors.get(name,0),number)
    return floors


def initialize(root, project_id, policy_template, producer_template, consumer_template, *, numbering_from=(), qc_policy=None):
    from site_planner.site_pool import SitePool
    from site_planner.candidate_pool import CandidatePool
    if not re.fullmatch(r'[\w.-]+',project_id) or project_id in ('.','..'):
        raise ValueError('A project requires a distinct local project ID')
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError('Project root cannot be a symbolic link')
    root = root.resolve()
    state = root/'state'
    registry = state/'production-registry.sqlite3'
    pool_path = state/'candidate-pool.sqlite3'
    manifest = root/'chain'/'manifest.json'
    results = root/'collections'
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
    root.mkdir(parents=True,exist_ok=False)
    # An incomplete initialization keeps its files for diagnosis. The scope is published last.
    results.mkdir()
    owner = initialize_chain(manifest,registry,chain_id=project_id,current_result_roots=[results],
                             now=since,candidate_project=project)
    with closing(sqlite3.connect(registry)) as con:
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
    for name in ('root','project-id','policy-template','producer-config','consumer-config'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--numbering-from',action='append',default=[],help='Read numeric high-water marks from an earlier registry')
    parser.add_argument('--qc-policy',type=Path)
    args=parser.parse_args(argv)
    scope=initialize(args.root,args.project_id,load_json(args.policy_template),load_json(args.producer_config),
                     load_json(args.consumer_config),numbering_from=args.numbering_from,
                     qc_policy=load_json(args.qc_policy) if args.qc_policy else None)
    print(json.dumps({'scope':str(scope),'rules':PROJECT_RULES,'roles_started':0}))


if __name__=='__main__':
    main()
