"""Pure read-only launch validation. Preparation is a separate explicit command."""
import argparse
from contextlib import closing
import importlib.util
from webcollect import workspace_json as json
import os
from pathlib import Path
import shutil

from .batch_core import load_json
from .sqlite_connection import connect

REQUIRED = {
    'pool': {'data_candidates': ('candidate_id','version','application_id','state','body'),
             'candidate_claims': ('claim_id','candidate_id','version','state','binding'),
             'candidate_results': ('candidate_id','claim_id','record'),
             'candidate_batch_rows': ('candidate_id','run_id','result')},
    'producer_db': {'batch_meta':('config','started'),'jobs': ('id','state','payload'), 'model_requests': ('id','state','job_id','request_json')},
    'consumer_db': {'batch_meta':('config','started'),'jobs': ('id','state','payload'), 'model_requests': ('id','state','job_id','request_json')},
    'registry': {'m4_tasks': ('task_key','task_json'), 'm4_attempts': ('attempt_id','status','evidence_json'),
                 'm4_campaigns': ('campaign_id','policy_json'), 'current_chain_meta': ('binding_json',)},
    'site_ledger': {'stop_meta': ('value',), 'site_executions': ('execution_id','state','evidence_json')},
}


def required_schema():
    """Read the owning DDL literals; never instantiate a database to discover schema."""
    import ast,inspect,re
    from site_planner.site_pool import SitePool
    from site_planner.candidate_pool import DDL,V2_DDL,TEMPLATE_SITES_DDL
    from .batch_core import BatchLedger
    from .runtime import SCHEMA
    from .storage import ensure_registry_schema
    from .current_chain import initialize_chain
    from .site_failure_stop import SiteFailureStore
    from .key_health import ensure_schema
    def literals(function):
        import textwrap
        tree=ast.parse(textwrap.dedent(inspect.getsource(function)))
        return [n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
    def parse(texts):
        result={}
        for text in texts:
            for match in re.finditer(r'CREATE TABLE(?: IF NOT EXISTS)? (\w+)\s*\((.*?)\)(?:;|$)',text,re.S|re.I):
                table,body=match.groups()
                columns={m[1] for part in body.split(',') if (m:=re.match(r'\s*(\w+)\s+(?:TEXT|INTEGER|REAL|BLOB|NUMERIC)\b',part,re.I))}
                result.setdefault(table,set()).update(columns)
            for match in re.finditer(r'ALTER TABLE (\w+) ADD COLUMN (\w+)',text,re.I):
                result.setdefault(match[1],set()).add(match[2])
        return result
    ledger=literals(BatchLedger.__init__)+literals(BatchLedger._ensure_visit_schema)
    expected={key:{table:set(cols) for table,cols in value.items()} for key,value in REQUIRED.items()}
    additions={'pool':parse([*DDL,*V2_DDL,TEMPLATE_SITES_DDL,*literals(SitePool.__init__)]),
               'producer_db':parse(ledger),'consumer_db':parse(ledger+literals(ensure_schema)),
               'registry':parse([SCHEMA,*literals(ensure_registry_schema),*literals(initialize_chain)]),
               'site_ledger':parse(literals(SiteFailureStore.initialize))}
    for role,tables in additions.items():
        for table,columns in tables.items():expected[role].setdefault(table,set()).update(columns)
    return expected


def check(scope_path, *, cohort_path=None, plan=None, minimum_free_bytes=2 * 1024**3):
    """No constructors, DDL, recovery, writes, DNS, credentials or browser calls."""
    from .site_inventory import load_scope
    errors = []
    def fail(code, field, reason):
        errors.append({'code': code, 'field': field, 'reason': reason})
    try:
        _, scope = load_scope(scope_path)
        config = load_json(scope['consumer_config'])
        policy = load_json(scope['policy'])
        paths = {**scope, 'site_ledger': config.get('site_failure_guard', {}).get('ledger')}
        for role, tables in required_schema().items():
            path = Path(paths.get(role) or '')
            if not path.is_file() or path.is_symlink():
                fail('STORE_MISSING', role, str(path)); continue
            try:
                with closing(connect(path, readonly=True)) as con:
                    if con.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'wal':
                        fail('STORE_NOT_WAL', role, str(path))
                    for table, columns in tables.items():
                        actual = {r[1] for r in con.execute('PRAGMA table_info(' + table + ')')}
                        if set(columns) - actual:
                            fail('SCHEMA_MISSING', role + '.' + table, sorted(set(columns)-actual))
            except Exception as error:
                fail('STORE_UNREADABLE', role, str(error))
        for role in ('producer','consumer'):
            expected=load_json(scope[role+'_config'])
            with closing(connect(scope[role+'_db'],readonly=True)) as con:
                frozen=con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()
                if not frozen or json.loads(frozen[0])!=expected:
                    fail('CONFIG_BINDING_MISMATCH',role+'_config','stored config differs from launch file')
        from .current_chain import read_chain_scope, assert_current_result_path, check_project_guard
        chain = read_chain_scope(scope['history_set'])
        assert_current_result_path(chain, scope['output'])
        check_project_guard(chain, config.get('site_failure_guard'), Path(scope['consumer_db']), role='consumer')
        with closing(connect(scope['registry'],readonly=True)) as con:
            original=con.execute('SELECT policy_json FROM m4_campaigns WHERE campaign_id=?',(policy.get('campaign_id'),)).fetchone()
            if not original or json.loads(original[0])!=policy:
                fail('POLICY_BINDING_MISMATCH','policy','stored campaign policy differs')
        if config.get('site_failure_guard') != policy.get('site_failure_guard'):
            fail('BINDING_MISMATCH', 'site_failure_guard', 'config differs from policy')
        limits = config.get('session_limits') or {}
        from .batch_core import SessionGLMCallLimit
        effective = {'http_limit': SessionGLMCallLimit.limit, 'soft_seconds': limits.get('soft_seconds', 1800),
                     'closeout_grace_seconds': limits.get('closeout_grace_seconds', 120)}
        if effective != {'http_limit':40,'soft_seconds':1800,'closeout_grace_seconds':120}:
            fail('LIMITS_MISMATCH','session_limits',effective)
        for field in ('policy','producer_config','consumer_config','history_set'):
            if not Path(scope[field]).is_file():
                fail('PATH_MISSING',field,scope[field])
        output = Path(scope['output'])
        while not output.exists():
            output = output.parent
        if not os.access(output, os.W_OK):
            fail('OUTPUT_NOT_WRITABLE','output',str(output))
        if shutil.disk_usage(output).free < minimum_free_bytes:
            fail('DISK_LOW','output',{'minimum_free_bytes':minimum_free_bytes})
        for dependency in ('playwright','jsonschema','yaml'):
            if importlib.util.find_spec(dependency) is None:
                fail('DEPENDENCY_MISSING','interpreter',dependency)
        if cohort_path:
            from .candidate_consumer import _cohort_rows, preflight_cohort_sources
            from site_planner.candidate_pool import CandidatePool
            pool = CandidatePool(scope['pool'], readonly=True)
            _, rows = _cohort_rows(cohort_path,pool,scope['registry'],None)
            from collections import Counter
            counts = Counter(r['application_id'] for r in rows)
            if len(rows)!=100 or len(counts)!=2 or set(counts.values())!={50}:
                fail('COHORT_DENOMINATOR','selected',dict(counts))
            if len({r['candidate_id'] for r in rows}) != len(rows):
                fail('COHORT_DUPLICATE','selected','candidate ids must be unique')
            with pool.pool.connect() as con:
                for row in rows:
                    original=con.execute('SELECT version,state FROM data_candidates WHERE candidate_id=?',(row['candidate_id'],)).fetchone()
                    if not original or original['version']!=row['version'] or original['state']!='pending':
                        fail('COHORT_UNAVAILABLE',row['candidate_id'],'version/state differs')
                    if con.execute('SELECT 1 FROM candidate_claims WHERE candidate_id=?',(row['candidate_id'],)).fetchone():
                        fail('COHORT_PRIOR_CLAIM',row['candidate_id'],'original claim retained')
            from .candidate_cohort import inspect_rows
            _,inspected,_=inspect_rows(scope_path,candidate_ids=[r['candidate_id'] for r in rows])
            audited={r['candidate_id']:r for r in inspected}
            for frozen in rows:
                actual=audited.get(frozen['candidate_id'],{})
                fields=('version','application_id','producer_batch','producer_row_id','producer_row_response_sha256','body_sha256','sources_sha256','entry_http')
                if not actual.get('eligible') or any(actual.get(k)!=frozen.get(k) for k in fields):
                    fail('COHORT_EVIDENCE_MISMATCH',frozen['candidate_id'],actual.get('rejection') or 'frozen source differs')
            preflight_cohort_sources(pool,rows,scope['registry'])
        if plan:
            # Only the coordinator inventories predecessors; its own workers run later.
            import subprocess,shlex
            processes=subprocess.check_output(['ps','-axo','pid=,command='],text=True)
            for line in processes.splitlines():
                parts=line.strip().split(None,1)
                if len(parts)!=2 or int(parts[0])==os.getpid():continue
                try:args=shlex.split(parts[1])
                except ValueError:continue
                module=args[args.index('-m')+1] if '-m' in args and args.index('-m')+1<len(args) else None
                if module in ('site_planner.candidate_discovery','webcollect.candidate_consumer','webcollect.consumer_campaign') or any(v.endswith('/sequence_controller.py') for v in args):
                    fail('PREDECESSOR_ACTIVE','process',{'pid':int(parts[0]),'module':module or 'sequence_controller'})
            workers = plan.get('workers',[])
            if plan.get('collection_strategy')!='screenshot_plan' or plan.get('automatic_export') is not False or plan.get('stop_after_saves') is not None:
                fail('PLAN_POLICY','plan','strategy2, no export, no save early stop required')
            shards = [w.get('candidate_ids',[]) for w in workers]
            flat = [cid for shard in shards for cid in shard]
            if len(workers)!=20 or any(len(s)!=5 for s in shards) or len(set(flat))!=100:
                fail('PLAN_SHARDS','workers','20 disjoint shards of 5 required')
            if cohort_path and set(flat)!={r['candidate_id'] for r in rows}:
                fail('PLAN_COHORT_MISMATCH','workers','shards differ from frozen cohort')
        return {'status':'FAILED' if errors else 'PASS','errors':errors,'effective_limits':effective,
                'dispatches':0,'browser_calls':0,'account_probes':0,'ledger_writes':0}
    except Exception as error:
        fail('STARTUP_INVALID','scope',type(error).__name__+': '+str(error))
        return {'status':'FAILED','errors':errors,'dispatches':0,'browser_calls':0,'account_probes':0,'ledger_writes':0}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scope',required=True,type=Path)
    p.add_argument('--cohort',type=Path)
    a=p.parse_args(argv); result=check(a.scope,cohort_path=a.cohort)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='PASS' else 2

if __name__=='__main__':
    raise SystemExit(main())
