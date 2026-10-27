"""Rebuild and inspect a delivery while historical result paths are inaccessible.

The parent copies explicit inputs. Worker processes install an audit hook before
importing production/QC code; metadata access is guarded as well because Python's
stat/exists operations do not emit open audit events. This is a reproducible
Python file-access isolation check, not a claim of a general OS security sandbox.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hashes(root):
    root=Path(root)
    if not root.is_dir() or root.is_symlink():raise ValueError('Expected a real input directory: '+str(root))
    result={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Symbolic inputs are not isolated copies: '+str(path))
        if path.is_file():result[path.relative_to(root).as_posix()]=digest(path)
    return result


def write_json(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def install_history_guard(repo,workspace):
    """Block historical result paths, including metadata probes and symlink aliases."""
    repo=Path(repo).resolve();workspace=Path(workspace).resolve()
    roots=[str(repo/'results'),str(repo/'verify_results')]
    workspace_string=str(workspace)
    original_realpath=os.path.realpath
    original_stat=os.stat;original_lstat=os.lstat;original_access=os.access
    original_readlink=os.readlink
    guard=threading.local()
    state={'blocked_roots':roots,'allowed_exception':workspace_string,
           'denied_access_attempts':[],'checked_path_events':0,
           'enforcement':'Python audit hook plus stat/lstat/access/realpath/readlink guards',
           'scope':'No historical results/raw/baseline/review path outside the copied workspace may be accessed'}

    def beneath(path,base):
        a=os.path.normpath(path).casefold();b=os.path.normpath(base).casefold()
        return a==b or a.startswith(b+os.sep)

    def checked(path,event):
        if getattr(guard,'active',False) or isinstance(path,int):return
        if path is None:path=os.getcwd()
        if not isinstance(path,(str,bytes,os.PathLike)):return
        value=os.fsdecode(path)
        guard.active=True
        try:
            absolute=os.path.abspath(value)
            canonical=original_realpath(absolute)
        finally:guard.active=False
        state['checked_path_events']+=1
        if any(beneath(absolute,root) or beneath(canonical,root) for root in roots) and not (
                beneath(absolute,workspace_string) and beneath(canonical,workspace_string)):
            state['denied_access_attempts'].append({'event':event,'path':value,'resolved_path':canonical})
            raise PermissionError('Historical result path is unavailable in isolation: '+value)

    def hook(event,args):
        if getattr(guard,'active',False):return
        if event=='open' or event in {'os.listdir','os.scandir','os.chdir','os.mkdir','os.remove','os.rmdir','os.chmod','os.truncate','os.utime'}:
            if args:checked(args[0],event)
        elif event in {'os.rename','os.link','shutil.copyfile','shutil.copymode','shutil.copystat','shutil.copytree'}:
            for path in args[:2]:checked(path,event)
        elif event=='os.symlink':
            for path in args[:2]:checked(path,event)
        elif event in {'subprocess.Popen','os.system','os.exec','os.posix_spawn'}:
            state['denied_access_attempts'].append({'event':event,'path':'child process creation is disabled in isolation workers'})
            raise PermissionError('Nested process creation would bypass the file-access audit')

    def metadata_wrapper(original,event):
        def wrapped(path,*args,**kwargs):
            checked(path,event)
            return original(path,*args,**kwargs)
        return wrapped

    def guarded_realpath(path,*args,**kwargs):
        checked(path,'os.path.realpath')
        previous=getattr(guard,'active',False);guard.active=True
        try:return original_realpath(path,*args,**kwargs)
        finally:guard.active=previous

    sys.addaudithook(hook)
    os.stat=metadata_wrapper(original_stat,'os.stat')
    os.lstat=metadata_wrapper(original_lstat,'os.lstat')
    os.access=metadata_wrapper(original_access,'os.access')
    os.readlink=metadata_wrapper(original_readlink,'os.readlink')
    os.path.realpath=guarded_realpath
    return state


def worker(args):
    repo=Path(args.repo).resolve();workspace=Path(args.workspace).resolve()
    report_path=workspace/'reports'/(args.worker+'.json')
    audit=install_history_guard(repo,workspace)
    sys.path.insert(0,str(repo/'projects/code'))
    sys.path.insert(0,str(repo/'projects/quality-inspector'))
    started=time.monotonic();result=None;error=None;status='FAIL'
    try:
        if args.worker=='producer':
            from webcollect.client_package import build_client_package
            result=build_client_package(repo,workspace/'inputs/client-original',workspace/'regenerated',
                facts=workspace/'inputs/facts.json',revisions=workspace/'inputs/revisions.json',
                evidence_output=workspace/'reports/regenerated-provenance.json')
            status='PASS' if result.get('contract',{}).get('structural_pass') is True else 'FAIL'
        else:
            from quality_inspector.engine import inspect
            final=args.worker=='qc-final'
            result=inspect(None,workspace/('final-input' if final else 'regenerated'),
                reviews=workspace/'inputs/reviews.json',profile=workspace/'inputs/profile.json',
                inspection_stage='final' if final else 'payload')
            status='PASS' if result.get('delivery_status')=='PASS' and (not final or result.get('release_ready') is True) else 'FAIL'
    except Exception as exception:
        error={'type':type(exception).__name__,'message':str(exception),'traceback':traceback.format_exc()}
    if audit['denied_access_attempts']:status='FAIL'
    write_json(report_path,{'phase':args.worker,'status':status,'seconds':time.monotonic()-started,
        'audit':audit,'result':result,'error':error})
    print(json.dumps({'phase':args.worker,'status':status,'report':str(report_path),
                     'denied_access_attempts':len(audit['denied_access_attempts'])},ensure_ascii=False))
    return 0 if status=='PASS' else 1


def copy_file(source,target):
    source=Path(source).resolve()
    if not source.is_file() or source.is_symlink():raise ValueError('Expected a real input file: '+str(source))
    expected=digest(source);shutil.copyfile(source,target)
    if digest(source)!=expected or digest(target)!=expected:raise ValueError('Input changed while copying: '+str(source))
    return {'source':str(source),'isolated_copy':str(target),'sha256':expected}


def run(args):
    repo=Path(args.repo).resolve();baseline=Path(args.baseline).resolve();package=Path(args.package).resolve()
    output=Path(args.output).resolve()
    if output.exists():raise FileExistsError('Refuse to overwrite an isolation record: '+str(output))
    output.mkdir(parents=True)
    workspace=Path(tempfile.mkdtemp(prefix='workspace-',dir=output))
    (workspace/'inputs').mkdir();(workspace/'reports').mkdir()
    original_hashes=hashes(baseline/'client-original');package_hashes=hashes(package)
    shutil.copytree(baseline/'client-original',workspace/'inputs/client-original')
    shutil.copytree(package,workspace/'final-input')
    if hashes(workspace/'inputs/client-original')!=original_hashes or hashes(baseline/'client-original')!=original_hashes:
        raise ValueError('Frozen source changed while copying')
    if hashes(workspace/'final-input')!=package_hashes or hashes(package)!=package_hashes:
        raise ValueError('Final package changed while copying')
    inputs={name:copy_file(getattr(args,name),workspace/'inputs'/(name+'.json')) for name in ('facts','revisions','reviews','profile')}
    phases=[]
    for phase in ('producer','qc-payload','qc-final'):
        command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'--worker',phase,
                 '--repo',str(repo),'--workspace',str(workspace)]
        with (output/(phase+'.stdout.log')).open('w') as stdout,(output/(phase+'.stderr.log')).open('w') as stderr:
            completed=subprocess.run(command,cwd=workspace,stdout=stdout,stderr=stderr,check=False)
        report_path=workspace/'reports'/(phase+'.json')
        report=json.loads(report_path.read_text()) if report_path.is_file() else None
        phases.append({'phase':phase,'command':command,'exit_code':completed.returncode,
            'status':report.get('status') if report else 'NO_REPORT','report_path':str(report_path),
            'report_sha256':digest(report_path) if report_path.is_file() else None,
            'denied_access_attempts':len(report['audit']['denied_access_attempts']) if report else None,
            'checked_path_events':report['audit']['checked_path_events'] if report else None})
    excluded={'qc_report.md','SHA256SUMS'}
    regenerated=hashes(workspace/'regenerated') if (workspace/'regenerated').is_dir() else {}
    payload={name:sha for name,sha in regenerated.items() if name not in excluded}
    delivered_payload={name:sha for name,sha in package_hashes.items() if name not in excluded}
    mismatches=[{'path':name,'regenerated_sha256':payload.get(name),'final_sha256':delivered_payload.get(name)}
                for name in sorted(payload.keys()|delivered_payload.keys()) if payload.get(name)!=delivered_payload.get(name)]
    source_unchanged=hashes(baseline/'client-original')==original_hashes
    final_unchanged=hashes(package)==package_hashes
    success=all(phase['exit_code']==0 and phase['status']=='PASS' and phase['denied_access_attempts']==0 for phase in phases)
    success=success and not mismatches and bool(payload) and source_unchanged and final_unchanged
    receipt={'schema_version':'webcollect-delivery-isolation-1','status':'PASS' if success else 'FAIL',
        'workspace':str(workspace),'repo':str(repo),'frozen_baseline':str(baseline),'final_package':str(package),
        'isolation':'Worker Python audit hooks deny all historical results/verify_results access except the copied workspace; metadata probes and nested process creation are guarded',
        'phases':phases,'denied_access_attempts':sum(phase['denied_access_attempts'] or 0 for phase in phases),
        'inputs':inputs,'source_files_sha256':original_hashes,'final_package_files_sha256':package_hashes,
        'regenerated_candidate_files_sha256':regenerated,'payload_files_sha256':payload,
        'payload_files_equal':not mismatches and bool(payload),'payload_mismatches':mismatches,
        'source_unchanged':source_unchanged,'final_package_unchanged':final_unchanged,
        'payload_excluded_files':sorted(excluded),'formal_cases_added':0,
        'script_sha256':digest(Path(__file__))}
    write_json(output/'isolation-report.json',receipt)
    print(json.dumps({'status':receipt['status'],'report':str(output/'isolation-report.json'),
        'workspace':str(workspace),'phase_exit_codes':{row['phase']:row['exit_code'] for row in phases},
        'denied_access_attempts':receipt['denied_access_attempts'],'payload_files_equal':receipt['payload_files_equal']},ensure_ascii=False))
    return 0 if success else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','baseline','package','facts','revisions','reviews','profile','output','workspace'):
        parser.add_argument('--'+name,type=Path,help=argparse.SUPPRESS if name=='workspace' else None)
    parser.add_argument('--worker',choices=('producer','qc-payload','qc-final'),help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:
        if not args.repo or not args.workspace:parser.error('Worker needs repo/workspace')
        return worker(args)
    for name in ('repo','baseline','package','facts','revisions','reviews','profile','output'):
        if getattr(args,name) is None:parser.error('--'+name+' is required')
    return run(args)


if __name__=='__main__':raise SystemExit(main())
