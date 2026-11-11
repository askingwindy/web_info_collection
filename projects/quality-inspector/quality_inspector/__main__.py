import argparse,json,sys
from pathlib import Path
from .engine import inspect,baseline_load
from .reporting import write_outputs
from .packaging import build
from .checksums import verify_manifest
from .profiles import DEFAULT_DELIVERY_PROFILE

def main(argv=None):
    ap=argparse.ArgumentParser(description='Independent sample-baseline QC; never claims actual customer-program acceptance.');sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('check');p.add_argument('--baseline',type=Path,help='Optional engineering/reference audit; excluded from the delivery gate');p.add_argument('--samples',type=Path);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reviews',type=Path,help='Actual evidence-bound AI or human inspection decisions');p.add_argument('--ai-evidence',type=Path);p.add_argument('--evidence',type=Path,help='Optional engineering capture audit; excluded from the delivery gate');p.add_argument('--profile',type=Path,default=DEFAULT_DELIVERY_PROFILE,help='Delivery contract by default; an explicit pilot profile retains pilot compatibility')
    b=sub.add_parser('baseline');b.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--stage',choices=['payload','final'],default='final',help='payload checks immutable content before QC summary attachment; final checks the complete sealed report too')
    p.add_argument('--delivery-sampling-plan',type=Path,help='Explicit frozen delivery sampling contract; default remains full semantic review')
    p.add_argument('--human-reviews',type=Path,action='append',default=[],help='Actual human escalation/random/replacement decisions for an explicit delivery sampling plan')
    p.add_argument('--ai-failures',type=Path,action='append',default=[],help='Read-only model-ledger-bound failed/unknown/invalid request receipts')
    cumulative=sub.add_parser('check-set',help='Read-only cumulative mechanical scope; never release-ready')
    cumulative.add_argument('--manifest',type=Path,required=True);cumulative.add_argument('--profile',type=Path,default=DEFAULT_DELIVERY_PROFILE)
    cumulative.add_argument('--output',type=Path,required=True);cumulative.add_argument('--cache',type=Path)
    cumulative.add_argument('--verify-exhaustive',action='store_true')
    manifest=sub.add_parser('set-manifest',help='Freeze current package file hashes without approving them')
    manifest.add_argument('--input',type=Path,action='append',required=True);manifest.add_argument('--output',type=Path,required=True)
    manifest.add_argument('--quality-batch-ids',type=Path,help='JSON array of current formal batch sample IDs; check-set verifies these 5000 and the cumulative set')
    manifest.add_argument('--application-registry',type=Path,help='Frozen site-pool snapshot resolving application aliases for the 500-sample limit')
    review=sub.add_parser('review',help='Create a separate evidence-bound blind human workspace; never imports decisions')
    review.add_argument('--report',type=Path,required=True)
    review.add_argument('--output',type=Path,required=True)
    review.add_argument('--blind',action='store_true',required=True)
    review.add_argument('--context',type=Path,required=True,help='Neutral source_statement/input_statement JSON; no review history')
    review.add_argument('--receipt',type=Path,required=True,help='Operator receipt outside the blind workspace and source package')
    review.add_argument('--reviewer',default='hemiao')
    v=sub.add_parser('verify-package');v.add_argument('--input',type=Path,required=True)
    b=sub.add_parser('package');b.add_argument('--repo',type=Path,required=True);b.add_argument('--source',type=Path,required=True);b.add_argument('--output',type=Path,required=True)
    args=ap.parse_args(argv)
    try:
        if args.cmd=='review':
            from .blind import write_workspace
            result=write_workspace(args.report,args.output,context_path=args.context,receipt_path=args.receipt,reviewer_name=args.reviewer)
            print(json.dumps({'mode':'blind','samples':result['sample_count'],'frames':result['frame_count'],'entry':str(args.output/'review.html'),'decisions_prefilled':False,'human_reviews_created':0},ensure_ascii=False));return 0
        if args.cmd=='set-manifest':
            from .cumulative import build_set_manifest
            from .contract import fingerprint
            from .format_checks import run
            roots=args.input if isinstance(args.input,list) else [args.input]
            if any(args.output.resolve().is_relative_to(root.resolve()) for root in roots):raise ValueError('Output must be outside inspected packages')
            members = json.loads(args.quality_batch_ids.read_text()) if args.quality_batch_ids else None
            if args.quality_batch_ids and members is None:
                raise ValueError('Quality batch file must contain an array of sample IDs')
            value = build_set_manifest(roots, quality_batch_ids=members,application_registry=args.application_registry)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
            print(json.dumps({'output':str(args.output),'not_an_acceptance':True},ensure_ascii=False));return 0
        if args.cmd=='check-set':
            from .cumulative import inspect_set
            raw=json.loads(args.manifest.read_text())
            for item in raw.get('packages',[]):
                root=Path(item['path']);root=(args.manifest.resolve().parent/root).resolve() if not root.is_absolute() else root.resolve()
                if args.output.resolve().is_relative_to(root):raise ValueError('Output must be outside inspected packages')
            result=inspect_set(args.manifest,args.profile,cache=args.cache,verify_exhaustive=args.verify_exhaustive)
            args.output.mkdir(parents=True,exist_ok=False)
            (args.output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({key:result[key] for key in ('scope','mechanical_status','sample_count','release_ready')},ensure_ascii=False))
            return 0 if result['mechanical_status']=='PASS' else 1
        if args.cmd=='check':
            if args.output.resolve().is_relative_to(args.input.resolve()):raise ValueError('Reports must be outside inspected inputs; never mutate the package.')
            r=inspect(args.baseline,args.input,args.reviews,args.ai_evidence,args.samples,args.profile,evidence=args.evidence,inspection_stage=args.stage,delivery_sampling_plan=args.delivery_sampling_plan,human_reviews=args.human_reviews,ai_failures=args.ai_failures);write_outputs(r,args.output);print(json.dumps({'status':r['status'],'local_acceptance_status':r.get('local_acceptance_status','NOT_CONFIGURED'),'samples':r['sample_count'],'sample_status_counts':r['sample_status_counts'],'report':str(args.output/'report.json'),'customer_acceptance':'UNKNOWN'},ensure_ascii=False));return {'PASS':0,'FAIL':1,'REVIEW_REQUIRED':2}[r.get('local_acceptance_status',r['status'])]
        if args.cmd=='baseline':
            r=baseline_load(args.baseline);print(json.dumps(r,ensure_ascii=False,indent=2));return 1 if r['integrity']=='FAIL' else 2
        if args.cmd=='verify-package':
            r=verify_manifest(args.input);print(json.dumps(r,ensure_ascii=False,indent=2));return 0 if r['pass'] else 1
        print(json.dumps(build(args.repo,args.source,args.output),ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError) as e:
        print(json.dumps({'status':'FAIL','execution_error':str(e),'customer_acceptance':'UNKNOWN'},ensure_ascii=False),file=sys.stderr);return 3
if __name__=='__main__':raise SystemExit(main())
