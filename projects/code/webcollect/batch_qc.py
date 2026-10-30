"""Explicit batch preparation: full mechanical QC precedes sampled model jobs.

Consumes a saved multi-sample candidate package. Never collects, calls a model,
changes production strategy, runs a worker or grants a review/release.
"""
import argparse
import json
from pathlib import Path
from .batch_core import load_json, save_json, file_sha
from .current_chain import read_chain_history


def prepare(dataset, history_set, output, *, max_batch_size, ai_percent, human_percent, seed,
            stratify='site', risk_selected=None, profile=None, production_sampling=False):
    from quality_inspector.cumulative import build_set_manifest, inspect_set
    from quality_inspector.delivery_sampling import verify
    from .qc_handoff import prepare_qc_inputs
    dataset=Path(dataset).resolve();output=Path(output).resolve()
    if not isinstance(risk_selected,dict):raise ValueError('Explicit risk_selected mapping required, including an empty mapping if no risk applies')
    if type(max_batch_size) is not int or max_batch_size<1:raise ValueError('Explicit positive max_batch_size required')
    candidates=sorted((dataset/'samples').glob('*/annotation.json'))
    if not 1<=len(candidates)<=max_batch_size:raise ValueError('Actual saved batch is empty or exceeds configured size')
    records,scope=read_chain_history(history_set)
    from .qc_handoff import _attempts
    ids=[load_json(path)['sample_id'] for path in candidates]
    _attempts(scope,dataset,ids)
    roots={dataset}|{Path(row['annotation_path']).parents[2] for row in records if row['sample_id'] not in ids}
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in roots):
        raise ValueError('Batch output must be outside all original evidence')
    manifest=build_set_manifest(sorted(roots))
    output.mkdir(parents=True,exist_ok=False)
    from .telemetry import phase
    with phase(output/'phases.jsonl','mechanical_qc'):
        report=inspect_set(manifest,profile=profile)
    # Keep the actual full mechanical report, including failures and denominators.
    save_json(output/'mechanical-report.json',report)
    save_json(output/'effective-set.json',manifest)
    if report['mechanical_status']!='PASS':
        return {'status':'MECHANICALLY_BLOCKED','report':str(output/'mechanical-report.json'),'model_requests':0}
    handoff=prepare_qc_inputs(dataset,history_set,output/'handoff',ai_percent=ai_percent,
        human_percent=human_percent,seed=seed,stratify=stratify,risk_selected=risk_selected,
        production_sampling=production_sampling)
    plan=verify(handoff['sampling_plan'],dataset)
    result={'status':'QC_NOT_RUN','handoff':handoff,'max_batch_size':max_batch_size,
        'denominator':len(plan['slots']),'ai_selected':sum(s['ai_selected'] for s in plan['slots']),
        'risk_selected':len(risk_selected or {}),'model_requests':0,'QC_approval':False,
        'cross_package_report':str(output/'mechanical-report.json'),
        'effective_set':str(output/'effective-set.json'),'profile':str(profile) if profile else None}
    save_json(output/'batch-receipt.json',result)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','history-set','output','policy'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(argv)
    print(json.dumps(prepare(a.dataset,a.history_set,a.output,**load_json(a.policy)),ensure_ascii=False))





def queue_reviews(ledger, batch_receipt, output, *, document_review_mode='ai', supporting_files=(), mode='real', sample_reviews=None):
    """Prepare existing sample and one batch documentary job; dispatch remains explicit.

    Actual sample reviews from a prior run of the same frozen plan are forwarded
    as a documentary supporting file so the documents job can verify review
    coverage instead of reporting NOT_SUPPLIED; visual/difference jobs are
    content-addressed and reuse their completed ledger results.
    """
    from quality_inspector.delivery_pipeline import prepare as prepare_reviews
    receipt=load_json(batch_receipt)
    if receipt['status']!='QC_NOT_RUN':raise ValueError('A mechanically checked batch is required')
    handoff=load_json(receipt['handoff']['receipt'])
    kwargs={'profile':receipt['profile']} if receipt.get('profile') else {}
    return prepare_reviews(ledger,handoff['dataset'],receipt['handoff']['sampling_plan'],
        receipt['effective_set'],output,cross_package_report=receipt['cross_package_report'],
        document_review_mode=document_review_mode,supporting_files=supporting_files,mode=mode,
        sample_reviews=sample_reviews,
        **({'production_handoff':{'path':receipt['handoff']['receipt'],'sha256':file_sha(receipt['handoff']['receipt'])}}
            if mode=='real' else {}),**kwargs)


def assemble(packages, history_set, output, *, max_batch_size, facts=None):
    """Merge explicit committed candidates using the existing exporter, retaining originals."""
    from .qc_handoff import _attempts
    from .current_chain import assert_current_result_path
    from .client_package import build_client_package
    from quality_inspector.profiles import package_files
    records,scope=read_chain_history(history_set)
    packages=[assert_current_result_path(scope,Path(path).resolve()) for path in packages]
    output=assert_current_result_path(scope,Path(output).resolve())
    if not packages or len(set(packages))!=len(packages):raise ValueError('Unique explicit original packages required')
    snapshots={str(path):package_files(path) for path in packages}; ids=[];attempts=[]
    for path in packages:
        members=[load_json(p)['sample_id'] for p in sorted((path/'samples').glob('*/annotation.json'))]
        if not members:raise ValueError('Empty batch source')
        attempts.extend(_attempts(scope,path,members));ids.extend(members)
    if len(ids)!=len(set(ids)) or not 1<=len(ids)<=max_batch_size:raise ValueError('Duplicate originals or batch size exceeded')
    request={'packages':snapshots,'attempts':attempts,'max_batch_size':max_batch_size,'facts':str(facts) if facts else None}
    receipt=output.with_name(output.name+'-assembly.json')
    if receipt.exists():
        previous=load_json(receipt)
        if previous['request']!=request or package_files(output)!=previous['files']:raise ValueError('Frozen assembled batch changed')
        return previous
    repo=Path(__file__).resolve().parents[3]
    if output.exists():
        import tempfile
        with tempfile.TemporaryDirectory(prefix='.batch-recovery-',dir=output.parent) as temporary:
            expected=Path(temporary)/'candidate'
            build_client_package(repo,packages[0],expected,source_packages=packages,facts=facts)
            if package_files(output)!=package_files(expected):raise ValueError('Interrupted batch differs from its original sources')
    else:
        build_client_package(repo,packages[0],output,source_packages=packages,facts=facts)
    _attempts(scope,output,ids)
    if any(package_files(path)!=snapshots[str(path)] for path in packages):raise ValueError('Original changed while assembling batch')
    value={'request':request,'dataset':str(output),'files':package_files(output),'QC_approval':False}
    save_json(receipt,value);return value


def expand_risk(batch_receipt, assessment, workflow_groups, output):
    """Freeze a successor covering affected workflows; successful reviews stay reusable."""
    from quality_inspector.delivery_sampling import verify,freeze
    from .batch_core import file_sha
    old=load_json(batch_receipt);handoff=load_json(old['handoff']['receipt'])
    plan=verify(old['handoff']['sampling_plan'],handoff['dataset'])
    evaluation=load_json(assessment);evaluation=evaluation.get('semantic_sampling',evaluation)
    if evaluation.get('plan_sha256')!=plan['plan_sha256']:raise ValueError('Assessment must bind the original frozen sampling plan')
    ids={slot['current']['sample_id'] for slot in plan['slots']}
    if set(workflow_groups)!=ids or any(not isinstance(g,str) or not g.strip() for g in workflow_groups.values()):raise ValueError('Workflow groups must cover the exact frozen population')
    rows=evaluation.get('rows',[])
    if len(rows)!=len(ids) or {r['sample_id'] for r in rows}!=ids:raise ValueError('Assessment population changed')
    affected={workflow_groups[r['sample_id']] for r in rows if r.get('status') in ('HUMAN_REQUIRED','REPLACE_REQUIRED') or r.get('admission_status') in ('FAIL','REVIEW_REQUIRED')}
    risk={k:list(v) for k,v in plan['policy'].get('risk_selected',{}).items()}
    for sid,group in workflow_groups.items():
        if group in affected:risk.setdefault(sid,[]).append('affected workflow: '+group)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    policy=plan['policy']
    successor=freeze(handoff['dataset'],output/'sampling-plan.json',ai_percent=policy['ai_percent'],human_percent=policy['human_percent'],seed=policy['seed'],stratify=policy['stratify'],risk_selected=risk)
    value={**old,'handoff':{**old['handoff'],'sampling_plan':str(output/'sampling-plan.json')},
        'expansion':{'rule_version':'affected-workflow-expansion-1','parent_plan_sha256':plan['plan_sha256'],
            'assessment':{'path':str(Path(assessment).resolve()),'sha256':file_sha(assessment)},'workflow_groups':workflow_groups,'affected_groups':sorted(affected)},
        'ai_selected':sum(slot['ai_selected'] for slot in successor['slots']),'QC_approval':False}
    save_json(output/'batch-receipt.json',value);return value


if __name__=='__main__':main()
