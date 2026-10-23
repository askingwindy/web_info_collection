import argparse,json,sys
from pathlib import Path
from .engine import inspect,baseline_load
from .reporting import write_outputs
from .packaging import build
from .checksums import verify_manifest

def main(argv=None):
    ap=argparse.ArgumentParser(description='Independent sample-baseline QC; never claims actual customer-program acceptance.');sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('check');p.add_argument('--baseline',type=Path,required=True);p.add_argument('--samples',type=Path);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reviews',type=Path);p.add_argument('--ai-evidence',type=Path);p.add_argument('--profile',type=Path,help='Explicit local pilot acceptance configuration; external customer result remains UNKNOWN')
    b=sub.add_parser('baseline');b.add_argument('--baseline',type=Path,required=True)
    v=sub.add_parser('verify-package');v.add_argument('--input',type=Path,required=True)
    b=sub.add_parser('package');b.add_argument('--repo',type=Path,required=True);b.add_argument('--source',type=Path,required=True);b.add_argument('--output',type=Path,required=True)
    args=ap.parse_args(argv)
    try:
        if args.cmd=='check':
            if args.output.resolve().is_relative_to(args.input.resolve()):raise ValueError('Reports must be outside inspected inputs; never mutate the package.')
            r=inspect(args.baseline,args.input,args.reviews,args.ai_evidence,args.samples,args.profile);write_outputs(r,args.output);print(json.dumps({'status':r['status'],'local_acceptance_status':r.get('local_acceptance_status','NOT_CONFIGURED'),'samples':r['sample_count'],'sample_status_counts':r['sample_status_counts'],'report':str(args.output/'report.json'),'customer_acceptance':'UNKNOWN'},ensure_ascii=False));return {'PASS':0,'FAIL':1,'REVIEW_REQUIRED':2}[r.get('local_acceptance_status',r['status'])]
        if args.cmd=='baseline':
            r=baseline_load(args.baseline);print(json.dumps(r,ensure_ascii=False,indent=2));return 1 if r['integrity']=='FAIL' else 2
        if args.cmd=='verify-package':
            r=verify_manifest(args.input);print(json.dumps(r,ensure_ascii=False,indent=2));return 0 if r['pass'] else 1
        print(json.dumps(build(args.repo,args.source,args.output),ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError) as e:
        print(json.dumps({'status':'FAIL','execution_error':str(e),'customer_acceptance':'UNKNOWN'},ensure_ascii=False),file=sys.stderr);return 3
if __name__=='__main__':raise SystemExit(main())
