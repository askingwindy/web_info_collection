import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
from .metadata import export_metadata
from .scaffold import scaffold
from .storage import write_json
from .validate import read_json, validate_sample


def main(argv=None):
    parser=argparse.ArgumentParser(description='WebCollect M1：联调样本及结构检查；不代表交付验收')
    sub=parser.add_subparsers(dest='command',required=True)
    generate=sub.add_parser('scaffold',help='生成合成联调样本，不得交付')
    day=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
    generate.add_argument('--output',type=Path,default=Path(f'projects/sample/integration/B{day}_001'))
    generate.add_argument('--registry',type=Path,help='跨批共用编号注册表；默认输出父目录下 registry.sqlite3')
    check=sub.add_parser('validate',help='检查单条样本结构')
    check.add_argument('sample',type=Path)
    check.add_argument('--mode',choices=['integration','delivery'],default='delivery')
    check.add_argument('--manifest',type=Path)
    check.add_argument('--report',type=Path)
    metadata=sub.add_parser('metadata',help='从已检查结构的样本生成索引')
    metadata.add_argument('batch',type=Path)
    metadata.add_argument('--output',required=True,type=Path)
    collect=sub.add_parser('collect',help='按任务计划采集真实网页，保留待人工核验状态')
    collect.add_argument('--plan',required=True,type=Path)
    collect.add_argument('--output',required=True,type=Path)
    collect.add_argument('--registry',required=True,type=Path)
    preflight=sub.add_parser('preflight',help='只读预检全部候选页面并输出风险与完整调度计划，不宣告质检通过')
    preflight.add_argument('--plan',required=True,type=Path)
    preflight.add_argument('--output',required=True,type=Path)
    preflight.add_argument('--samples',type=int,default=3)
    preflight.add_argument('--interval-ms',type=int,default=400)
    preflight.add_argument('--preserve-order',action='store_true',help='固定对照保留原任务顺序')
    package=sub.add_parser('package',help='生成待独立质检的候选包，不宣告合格')
    package.add_argument('--source',required=True,type=Path)
    package.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        if args.command=='package':
            from .candidate import build_candidate
            result=build_candidate(Path(__file__).resolve().parents[3],args.source,args.output)
        elif args.command=='preflight':
            import asyncio
            from .preflight import preflight_plan
            result=asyncio.run(preflight_plan(args.plan,args.output,args.samples,args.interval_ms,args.preserve_order))
        elif args.command=='collect':
            import asyncio
            from .collect import collect_plan
            result=asyncio.run(collect_plan(args.plan,args.output,args.registry))
        elif args.command=='scaffold':
            result=scaffold(args.output,args.registry)
        elif args.command=='metadata':
            rows=export_metadata(args.batch,args.output)
            result={'rows':len(rows),'output':str(args.output)}
        else:
            if args.mode=='delivery' and not args.manifest:
                raise ValueError('delivery 模式必须提供 --manifest')
            if args.report:
                report=args.report.resolve()
                sample=args.sample.resolve()
                if report.is_relative_to(sample) or (sample.parent.name=='samples' and report.is_relative_to(sample.parent)):
                    raise ValueError('检查报告必须位于样本及 samples 目录之外')
                if report.exists(): raise FileExistsError('报告已存在，拒绝覆盖')
            manifest=read_json(args.manifest) if args.manifest else None
            result=validate_sample(args.sample,args.mode,manifest)
            if args.report:
                args.report.parent.mkdir(parents=True,exist_ok=True)
                write_json(args.report,result)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0 if result['structural_pass'] else 1
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 1 if (args.command=='collect' and result['rejected']) or (args.command=='preflight' and result['probe_errors']) else 0
    except (OSError,ValueError,TypeError,KeyError) as e:
        print(json.dumps({'error':str(e),'kind':'command_or_configuration'},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    sys.exit(main())
