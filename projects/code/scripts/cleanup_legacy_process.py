"""Clean explicitly authorized legacy process data only after a verified release.

Defaults to an inventory. --execute requires a successful independent release
receipt, immutable baseline, and successful current regression receipts.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True,type=Path)
    ap.add_argument('--verified-release',required=True,type=Path);ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--regression',required=True,type=Path);ap.add_argument('--isolation',required=True,type=Path)
    ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    root=args.repo.resolve();receipt=json.loads(args.verified_release.read_text())
    if receipt.get('status')!='PASS':raise ValueError('Independent release validation must PASS before cleanup')
    regression=json.loads(args.regression.read_text());isolation=json.loads(args.isolation.read_text())
    if regression.get('status')!='PASS' or isolation.get('status')!='PASS':
        raise ValueError('Regression and isolation validation must PASS before cleanup')
    for row in regression.get('logs',[]):
        p=root/row['path']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Regression evidence changed or disappeared')
    baseline=(root/'results/baselines/approved18-20261024').resolve()
    retained_qc=(root/'verify_results/client18-contract-20261024').resolve()
    package=(root/'results/delivery/20261024-client18-contract-v2').resolve()
    keep_delivery={package,package.with_suffix('.zip'),Path(str(package)+'.zip.sha256'),root/'results/delivery/LATEST.md',root/'results/delivery/.gitkeep'}
    if not package.is_dir() or not baseline.is_dir():raise ValueError('Verified release or frozen baseline is missing')
    if receipt.get('package')!=str(package) or receipt.get('baseline')!=str(baseline):
        raise ValueError('Release receipt belongs to a different package or baseline')
    archive=package.with_suffix('.zip')
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest()!=receipt.get('archive_sha256'):
        raise ValueError('Verified release archive changed')
    # Recheck the original seal immediately before any deletion.
    for line in (baseline/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);p=baseline/name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('Frozen baseline changed: '+name)
    targets=[]
    for p in (root/'results').iterdir():
        if p.name not in {'baselines','delivery','.gitkeep'}:targets.append(p)
    for p in (root/'results/delivery').iterdir():
        if p not in keep_delivery:targets.append(p)
    for p in (root/'verify_results').iterdir():
        if p!=retained_qc and p.name!='.gitkeep':targets.append(p)
    for p in (root/'m1-sample',root/'projects/sample'):
        if p.exists():targets.append(p)
    # Current scratch copies are reproducible from the retained source/facts;
    # preserve reports and review decisions, remove redundant data copies.
    for name in ('candidate','candidate-v2','candidate-v3','run-inputs','run-inputs-v2','prechange'):
        p=retained_qc/name
        if p.exists():targets.append(p)
    isolated_workspace=Path(isolation.get('workspace','')).resolve()
    if isolated_workspace.is_relative_to(retained_qc/'isolation') and isolated_workspace.is_dir():
        targets.append(isolated_workspace)
    for parent in (root/'projects/code',root/'projects/quality-inspector'):
        for p in parent.rglob('__pycache__'):
            if '.venv' not in p.parts:targets.append(p)
        p=parent/'.pytest_cache'
        if p.exists():targets.append(p)
    targets=sorted(set(targets));protected=[baseline,package,retained_qc,root/'request',root/'projects/code/webcollect',root/'projects/quality-inspector/quality_inspector']
    rows=[]
    for p in targets:
        if p.is_symlink() or not p.resolve().is_relative_to(root) or any(q==p or q.is_relative_to(p) for q in protected):
            raise ValueError('Unsafe cleanup path: '+str(p))
        files=[p] if p.is_file() else [q for q in p.rglob('*') if q.is_file() and not q.is_symlink()]
        rows.append({'path':str(p.relative_to(root)),'files':len(files),'bytes':sum(q.stat().st_size for q in files)})
    result={'status':'PLANNED','authorization':'User explicitly authorized legacy process cleanup after successful 18-case validation, 2026-10-24',
        'created_at':datetime.now(timezone.utc).isoformat(),'release_receipt_sha256':hashlib.sha256(args.verified_release.read_bytes()).hexdigest(),
        'targets':rows,'total_files':sum(x['files'] for x in rows),'total_bytes':sum(x['bytes'] for x in rows),
        'protected':['raw approved18 baseline and original20 reviews/excluded evidence','real and synthetic numbering registries','source code/tests/request/engineering docs','new release and current validation records']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():raise FileExistsError('Refuse to overwrite cleanup receipt')
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if args.execute:
        for p in targets:
            if p.is_dir():shutil.rmtree(p)
            else:p.unlink()
        result['status']='COMPLETE';result['remaining_targets']=[str(p) for p in targets if p.exists()]
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:result[key] for key in ('status','total_files','total_bytes')},ensure_ascii=False))


if __name__=='__main__':main()
