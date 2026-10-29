"""One real record through existing source, execution and independent QC stages.

Stage artifacts are immutable. This module never creates a production chain,
changes its budget, retries UNKNOWN requests, or manufactures review results.
"""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .batch_core import BatchLedger, file_sha, load_json, save_json
from .planning import verify_evidence, validate_capability


def ref(path):
    return {'path': str(Path(path).resolve()), 'sha256': file_sha(path)}


def candidate(pool_path, uri, output):
    from site_planner.site_pool import SitePool, page_uri
    pool = SitePool(pool_path, readonly=True)
    rows = [r for r in pool.rows() if r['uri'] == page_uri(uri)]
    if len(rows) != 1:
        raise ValueError('Select exactly one existing shared-pool page')
    row = rows[0]
    from .site_pool_sync import page_state
    if not page_state(pool, uri)['dispatch_allowed']:
        raise ValueError('Shared pool page already has an active or completed task, or needs synchronization')
    hints = [c for c in row['category_hints'] if c != 'UNKNOWN']
    parent = row['category'] if row['category'] != 'UNKNOWN' else hints[0] if len(hints) == 1 else 'UNKNOWN'
    source_path = Path(output).with_suffix('.sources.json')
    source = {'schema_version': 'webcollect-site-sources-1', 'sources': [
        {'kind': 'seed', 'category': parent, 'uris': [row['uri']], 'discovery_provenance': row['discoveries']}]}
    save_json(source_path, source)
    evidence = list({r['path']: r for d in row['discoveries'] for r in d['source_refs']}.values())
    result = {'schema_version': 'webcollect-site-candidates-1', 'mode': 'real',
        'records': [{'site_uri': row['uri'], 'site_category': parent,
            'source': [{'kind': 'seed', 'source_sha256': file_sha(source_path), 'evidence': evidence}],
            'application_id': row['application_id'], 'page_id': row['page_id']}],
        'source_manifest': str(source_path.resolve()), 'fixed_candidate_count': 1,
        'sample_ids_allocated': 0, 'real_supply_verified': False}
    save_json(output, result)
    return result


async def source(pool_path, uri, config_path, ledger_path, output, *, chain):
    from site_planner.pipeline import probe
    from site_planner.qualification import qualify_catalog
    from site_planner.site_pool import SitePool
    from .current_chain import read_chain_history
    scope = read_chain_history(Path(chain).resolve())[1]
    output = Path(output).resolve()
    roots = [Path(scope['manifest']['path']).parent.parent, *map(Path,scope['current_result_roots'])]
    if not any(output.is_relative_to(root) for root in roots):
        raise ValueError('Source evidence must be inside the original current-chain evidence/result roots; no probe dispatched')
    output.mkdir(parents=True, exist_ok=True)
    frozen = {'pool': str(Path(pool_path).resolve()), 'uri': uri, 'config': ref(config_path),
              'ledger': str(Path(ledger_path).resolve()), 'chain': scope['manifest']}
    save_json(output / 'inputs.json', frozen)
    if (output / 'receipt.json').exists():
        result = load_json(output / 'receipt.json'); verify_evidence([result['catalog']])
        for record in load_json(result['catalog']['path'])['records']:
            validate_capability(record, require_ready=True)
        save_json(Path(result['catalog']['path']).parent / 'site-pool-binding.json', {
            'schema_version': 'webcollect-site-pool-binding-1', 'pool': str(Path(pool_path).resolve()),
            'catalog': result['catalog']})
        return result
    ledger = BatchLedger(ledger_path, load_json(config_path), initialize=not Path(ledger_path).exists())
    from .provider_recovery import holds
    with ledger.connect() as con:
        held=list(holds(con))
    if held:
        result={'status':'PROVIDER_AUTHORIZATION_HOLD','original_request_ids':held,
                'reason':'Reconcile original authorization failure before new source/model dispatch',
                'sample_ids_allocated':0,'model_requests_dispatched':0,'browser_dispatched':False}
        save_json(output/'hold.json',result)
        return result
    path = output / 'candidates.json'; candidate(pool_path, uri, path)
    observed = await probe(ledger, path, output / 'probe')
    if len(observed['records']) != 1 or observed['records'][0].get('schema_version') != 'webcollect-site-capability-1':
        return {'status': 'SOURCE_FAILED', 'probe': observed, 'sample_ids_allocated': 0}
    if observed['records'][0]['status'] == 'rejected':
        return {'status': 'SOURCE_REJECTED', 'probe': observed, 'sample_ids_allocated': 0}
    qualified = await asyncio.to_thread(qualify_catalog, ledger, observed['catalog_file'], output / 'qualification')
    catalog = load_json(qualified['catalog_file'])
    if len(catalog['records']) != 1 or catalog['records'][0]['status'] != 'ready':
        return {'status': 'CAPABILITY_NOT_READY', 'qualification': qualified, 'sample_ids_allocated': 0}
    record = validate_capability(catalog['records'][0], require_ready=True)
    SitePool(pool_path).bind_capability(ref(qualified['catalog_file']))
    save_json(Path(qualified['catalog_file']).parent / 'site-pool-binding.json', {
        'schema_version': 'webcollect-site-pool-binding-1', 'pool': str(Path(pool_path).resolve()),
        'catalog': ref(qualified['catalog_file'])})
    result = {'status': 'CAPABILITY_READY', 'catalog': ref(qualified['catalog_file']),
              'capability_id': record['capability_id'], 'sample_ids_allocated': 0}
    save_json(output / 'receipt.json', result)
    return result


def identity(catalog_path, output, *, registry=None):
    from .production_identity import VERSION
    catalog = load_json(catalog_path)
    if len(catalog['records']) != 1:
        raise ValueError('Single-record runner requires exactly one capability')
    record = validate_capability(catalog['records'][0], require_ready=True)
    page = record['capabilities'][0]
    anchor = page['page_anchor']; verify_evidence(list(anchor.values()))
    state = load_json(anchor['state']['path']); parsed = urlsplit(record['site_uri'])
    root_uri = urlunsplit((parsed.scheme, parsed.netloc, '/', '', ''))
    application_name = page['title']
    if registry is not None:
        import sqlite3
        from .production_identity import page_url
        # A second function page must retain the original whole-application
        # allocation name, rather than renaming the application to its title.
        with sqlite3.connect(Path(registry).resolve().as_uri()+'?mode=ro',uri=True) as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m4_pilot_applications'").fetchone():
                existing=con.execute('SELECT canonical_uri,name FROM m4_pilot_applications WHERE application_key=?',
                                     (page_url(root_uri),)).fetchone()
                if existing:
                    if page_url(existing[0]) != page_url(root_uri):
                        raise ValueError('Original whole-application mapping differs')
                    application_name=existing[1]
    result = {'schema_version': 'webcollect-page-identities-1', 'pages': {record['site_uri']: {
        'version': VERSION, 'application': {'canonical_uri': root_uri, 'name': application_name,
            'evidence': [anchor['state']]},
        'task_page': {'canonical_uri': record['site_uri'], 'aliases': [record['site_uri']],
            'kind': 'function' if page.get('forms') or page.get('widgets') or any(
                c.get('editable') and c.get('tag') in ('input','textarea','select') for c in page.get('controls',[])) else 'content',
            'description': 'Current observed task page; original synchronized source anchor', 'anchor': anchor},
        'shared_pages': []}}}
    if state['url'] != record['site_uri']:
        raise ValueError('Cross-page landing requires explicit identity reconciliation')
    save_json(output, result)
    return result


def numeric_workflow(catalog_path, output, *, inputs, submit_label, assertions, instruction, result_scroll=None):
    """Author a proposal from actual visible DOM controls, never a prior execution."""
    from .workflow_proposal import compile_workflow, SCHEMA
    from .task_generation import VERSION
    from decimal import Decimal
    catalog = load_json(catalog_path)
    if len(catalog['records']) != 1:
        raise ValueError('Exactly one actual capability required')
    capability = validate_capability(catalog['records'][0], require_ready=True)
    page = capability['capabilities'][0]; anchor = page['page_anchor']
    verify_evidence(list(anchor.values())); state = load_json(anchor['state']['path'])
    controls = page.get('controls', []); operations = []; goals = []
    if len({label for label, _ in inputs}) != len(inputs):
        raise ValueError('Repeated inputs cannot create necessary actions')
    def target(label, predicate):
        found = [c for c in controls if c['label'] == label and c['visible'] and c['enabled'] and predicate(c)]
        nodes = [e for e in state['elements'] if e.get('text') == label and e.get('visible') and e.get('enabled')
                 and (e.get('inputable') if found and found[0]['tag'] in ('input', 'textarea') else e.get('clickable'))]
        if len(found) != 1 or len(nodes) != 1:
            raise ValueError('Unique visible source control and original anchor label required: ' + label)
        return found[0], {'anchor_index': 0, 'anchor_element_id': nodes[0]['element_id'], 'target_label': label}
    for n, (label, value) in enumerate(inputs):
        control, evidence = target(label, lambda c: c['tag']=='input' and c['type']=='number' and c['editable'])
        number=Decimal(value)
        if not number.is_finite() or not str(value).strip() or str(value)==control['value']:
            raise ValueError('A changed finite numeric input is required')
        for bound in ('min', 'max'):
            if control.get(bound) and ((bound=='min' and number<Decimal(control[bound])) or (bound=='max' and number>Decimal(control[bound]))):
                raise ValueError('Numeric proposal exceeds observed bounds')
        key='input-'+str(n)
        common={'subgoal_id':key,'selector':control['selector'],'evidence':evidence}
        operations.append({**common,'operation_id':key+'-focus','action_type':'click',
            'goal':'选中「'+label+'」','rationale':'聚焦必要输入位置','expected':'光标进入「'+label+'」'})
        if control['value']:
            operations.append({'operation_id':key+'-replace','subgoal_id':key,'action_type':'hotkey',
                'arguments':{'keys':['meta','a']},'goal':'选中原输入内容','rationale':'整体替换已有值','expected':'原值被选中'})
        operations.append({**common,'operation_id':key+'-type','action_type':'type','arguments':{'text':str(value)},
            'goal':'将「'+label+'」填写为'+str(value),'rationale':'填写任务所需系数','expected':'显示输入值'+str(value),
            'postconditions':[{'selector':control['selector'],'value':str(value)}]})
        goals.append({'id':key,'description':'填写「'+label+'」','evidence':[{'operation_id':key+'-type','postcondition_index':0}]})
    button,evidence=target(submit_label, lambda c:c['tag']=='button' or c['type'] in ('button','submit'))
    allowed={r['selector'] for r in page.get('result_targets',[])}
    if not assertions or any(a.get('selector') not in allowed for a in assertions):
        raise ValueError('Final assertions must bind an observed result container')
    operations.append({'operation_id':'calculate','subgoal_id':'result','action_type':'click',
        'selector':button['selector'],'evidence':evidence,'goal':'点击「'+submit_label+'」',
        'rationale':'取得任务要求的计算结果','expected':'显示实际计算结果','postconditions':assertions})
    if result_scroll is not None:
        operations[-1].pop('postconditions')
        operations.append({'operation_id':'read-complete-result','subgoal_id':'result','action_type':'scroll',
            'selector':assertions[0]['selector'],'arguments':{'direction':'down'},'execution':{'distance':result_scroll},
            'completion_view':{'schema_version':'webcollect-live-completion-view-1','distance':result_scroll},
            'goal':'查看完整计算结果','rationale':'仅当实际结果被视口截断时向下查看','expected':'完整结果进入视口',
            'postconditions':assertions})
    goals.append({'id':'result','description':'核对完整计算结果','evidence':[{'final_assertion_index':i} for i in range(len(assertions))]})
    spec={'capability_id':capability['capability_id'],'capability_version':capability['version'],
        'task_family':capability['task_families'][0],'initial_url':capability['site_uri'],
        'instruction':instruction,'task_type':['填写表单','数据查看'],'operations':operations,'subgoals':goals,
        'required_actions':[o['operation_id'] for o in operations],'final_assertions':assertions,
        'final_result':instruction,'completion_judgement':'核对最终原始截图中任务要求的计算结果。','anchors':[anchor]}
    compile_workflow(capability,spec,VERSION)
    result={'schema_version':SCHEMA,'tasks':[spec]};save_json(output,result);return result


def plan(config_path, ledger_path, catalog_path, chain, output, *, generator='deterministic', workflow_specs=None):
    from .current_chain import read_chain_history
    from .task_generation import generate
    scope = read_chain_history(Path(chain).resolve())[1]
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    identities = output / 'page-identities.json'; identity_value = identity(catalog_path, identities,registry=scope['registry'])
    from .current_chain import assert_current_evidence
    assert_current_evidence(scope, identity_value)
    ledger = BatchLedger(ledger_path, load_json(config_path), initialize=not Path(ledger_path).exists())
    result = generate(ledger, catalog_path, output / 'generation', history_set=Path(chain).resolve(),
        history_registry=scope['registry'], generator=generator, workflow_specs=workflow_specs,
        page_identities=identities, max_tasks=1)
    if result.get('plan_file'):
        from .current_chain import assert_current_evidence
        assert_current_evidence(scope, load_json(result['plan_file']))
    return result


async def collect(config_path, ledger_path, catalog_path, plan_path, chain, policy, output, *, resume=False):
    from .current_chain import read_chain_history, assert_current_result_path
    from .task_generation import execute
    scope = read_chain_history(Path(chain).resolve())[1]
    output = assert_current_result_path(scope, Path(output).resolve())
    value = load_json(plan_path)
    if len(value.get('tasks', [])) != 1:
        raise ValueError('Exactly one generated real task required')
    # Explicit experiment policy: full AI review; no invented human review.
    qc_policy = output.parent / (output.name + '-qc-policy.json')
    save_json(qc_policy, {'ai_percent': 100, 'human_percent': 0, 'seed': 'single-record-20261029-r01'})
    ledger = BatchLedger(ledger_path, load_json(config_path), initialize=not Path(ledger_path).exists())
    return await execute(ledger, plan_path, catalog_path, output, scope['registry'], policy,
                         resume=resume, qc_policy=qc_policy)


def qc(config_path, ledger_path, execution_result, profile, output, *, supporting_files=(),sample_reviews=None):
    from quality_inspector.cumulative import inspect_set
    from quality_inspector.delivery_pipeline import prepare, run, verify
    result = load_json(execution_result)
    if not result.get('candidate') or result.get('qc_status') != 'QC_NOT_RUN':
        raise ValueError('A saved real candidate and frozen QC handoff are required')
    inputs = result['qc_inputs']; dataset = Path(result['candidate']).resolve()
    output = Path(output).resolve()
    if output.is_relative_to(dataset) or dataset.is_relative_to(output):
        raise ValueError('Independent QC output must be outside the candidate')
    output.mkdir(parents=True, exist_ok=True)
    capture = Path(result['collection']['output']).resolve()
    defaults = [capture/'manifest.json', capture/'runtime-snapshot.json', capture.parent/'facts.json',
                Path(inputs['sampling_plan'])]
    supporting = list(dict.fromkeys([*defaults, *map(Path,supporting_files)]))
    for path in supporting:
        if not path.is_file():
            raise ValueError('Actual source census/review supporting file missing: ' + str(path))
    frozen = {'execution_result': ref(execution_result), 'profile': ref(profile),
              'config': ref(config_path), 'ledger': str(Path(ledger_path).resolve()),
              'supporting_files': [ref(p) for p in supporting],
              'sample_reviews':ref(sample_reviews) if sample_reviews else None}
    save_json(output / 'inputs.json', frozen)
    cross_path = output / 'cross-package-report.json'
    if not cross_path.exists():
        cross = inspect_set(inputs['effective_set'], profile=profile, verify_exhaustive=True)
        save_json(cross_path, cross)
    ledger = BatchLedger(ledger_path, load_json(config_path), initialize=not Path(ledger_path).exists())
    receipt = output / 'prepared/pipeline-receipt.json'
    if not receipt.exists():
        prepare(ledger, dataset, inputs['sampling_plan'], inputs['effective_set'], output / 'prepared',
            profile=profile, cross_package_report=cross_path, collection_checks=inputs.get('collection_checks'),
            mode='real', document_review_mode='ai', supporting_files=supporting,sample_reviews=sample_reviews,
            **({'production_handoff': ref(inputs['receipt'])} if inputs.get('receipt') else {}))
    runs = sorted(output.glob('run-*'))
    completed = [p/'status.json' for p in runs if (p/'status.json').exists()]
    if completed:
        verify(receipt, ledger)
        result = load_json(completed[-1]); verify_evidence([result['report']])
        if inputs.get('receipt'):
            from .site_pool_sync import apply_qc
            apply_qc(result['report']['path'], ref(inputs['receipt']))
        return result
    return run(receipt, output / ('run-' + str(len(runs)+1).zfill(3)), max_jobs=10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p=sub.add_parser('candidate')
    for name in ('pool','uri','output'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('source')
    for name in ('pool','uri','config','ledger','output','chain'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('plan')
    for name in ('config','ledger','catalog','chain','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--generator',choices=['deterministic','model'],default='deterministic')
    p.add_argument('--workflow-specs')
    p=sub.add_parser('collect')
    for name in ('config','ledger','catalog','plan','chain','policy','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--resume',action='store_true')
    p=sub.add_parser('qc')
    for name in ('config','ledger','execution-result','profile','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--supporting-file',action='append',default=[])
    p.add_argument('--sample-reviews',help='Existing actual independent sample review; revalidated against the frozen plan')
    args=vars(parser.parse_args(argv)); command=args.pop('command')
    if command=='candidate': result=candidate(args['pool'],args['uri'],args['output'])
    elif command=='source':result=asyncio.run(source(args['pool'],args['uri'],args['config'],args['ledger'],args['output'],chain=args['chain']))
    elif command=='plan':result=plan(args['config'],args['ledger'],args['catalog'],args['chain'],args['output'],generator=args['generator'],workflow_specs=args['workflow_specs'])
    elif command=='collect':result=asyncio.run(collect(args['config'],args['ledger'],args['catalog'],args['plan'],args['chain'],args['policy'],args['output'],resume=args['resume']))
    else:result=qc(args['config'],args['ledger'],args['execution_result'],args['profile'],args['output'],supporting_files=args['supporting_file'],sample_reviews=args['sample_reviews'])
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if command=='source' and result.get('status')!='CAPABILITY_READY':return 2
    if command=='plan' and result.get('generated_tasks')!=1:return 2
    if command=='collect' and result.get('collection',{}).get('collected')!=1:return 2
    if command=='qc' and result.get('payload_status')!='PASS':return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
