import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import sqlite3
from zoneinfo import ZoneInfo
from .metadata import export_metadata
from .scaffold import scaffold
from .storage import write_json
from .validate import read_json, validate_sample


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'site-pool':
        from .site_pool_reader import main as pool_main
        return pool_main(argv[1:])
    parser=argparse.ArgumentParser(description='WebCollect：真实轨迹采集、合同校验与客户交付封包')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('site-pool',help='只读共享站点池候选或严格验证既有能力；不派发采集')
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
    collect.add_argument('--publication',type=Path,help='严格M4计划的发布收据，含已验证站点能力与预检绑定')
    collect.add_argument('--policy',type=Path,help='M4初始运行预算JSON；续跑沿用已冻结策略')
    collect.add_argument('--resume',action='store_true',help='恢复同目录M4任务；不拼接中断轨迹或回收编号')
    publish=sub.add_parser('plan-publish',help='校验并冻结M4计划、能力和预检证据；不启动浏览器或分配编号')
    publish.add_argument('--plan',required=True,type=Path)
    publish.add_argument('--capabilities',required=True,type=Path)
    publish.add_argument('--output',required=True,type=Path)
    status=sub.add_parser('runtime-status',help='只读查看M4队列、尝试、编号与预算；不初始化账本')
    status.add_argument('--registry',required=True,type=Path)
    status.add_argument('--output',required=True,type=Path,help='既有M4批次输出目录')
    policy=sub.add_parser('runtime-policy',help='带原因修改既有campaign预算，保留变更事件；不启动采集')
    policy.add_argument('--registry',required=True,type=Path)
    policy.add_argument('--output',required=True,type=Path)
    policy.add_argument('--updates',required=True,type=Path)
    policy.add_argument('--reason',required=True)
    resume_scope=sub.add_parser('runtime-resume',help='带原因恢复暂停的M4范围；下次claim仍重新核查全部预算')
    resume_scope.add_argument('--registry',required=True,type=Path)
    resume_scope.add_argument('--output',required=True,type=Path)
    resume_scope.add_argument('--reason',required=True)
    close_scope=sub.add_parser('runtime-close-replan',help='永久关闭已暂停且全失败的scope，保留全部原文件与attempt并释放未开始任务配额')
    close_scope.add_argument('--registry',required=True,type=Path)
    close_scope.add_argument('--output',required=True,type=Path)
    close_scope.add_argument('--reason',required=True)
    close_scope.add_argument('--evidence',required=True,type=Path,help='关闭原因的绝对路径及SHA256证据列表JSON')
    preflight=sub.add_parser('preflight',help='只读预检全部候选页面并输出风险与完整调度计划，不宣告质检通过')
    preflight.add_argument('--plan',required=True,type=Path)
    preflight.add_argument('--output',required=True,type=Path)
    preflight.add_argument('--samples',type=int,default=3)
    preflight.add_argument('--interval-ms',type=int,default=400)
    preflight.add_argument('--preserve-order',action='store_true',help='固定对照保留原任务顺序')
    package=sub.add_parser('package',help='导出客户samples布局，独立质检须读取导出结果')
    package.add_argument('--source',required=True,type=Path)
    package.add_argument('--output',required=True,type=Path)
    package.add_argument('--layout',choices=['client','candidate'],default='client')
    package.add_argument('--reviews',type=Path,help='精确绑定原样本的qc-review-1/2记录；v2同时提供selection-report')
    package.add_argument('--selection-report',type=Path,help='v2审核选集所需：实际客户来源目录的独立QC报告')
    package.add_argument('--approved-only',action='store_true',help='仅选实际人工五项PASS，完整总体记录留在包外')
    package.add_argument('--evidence-output',type=Path,help='客户包外的机器证据索引，拒绝覆盖')
    package.add_argument('--review-output',type=Path,help='包外所选样本原始审核记录，不继承旧包级审核')
    package.add_argument('--facts',type=Path,help='实际生产事实，用于生成需求指定的来源与合成说明')
    package.add_argument('--revisions',type=Path,help='按原标注哈希及图树证据绑定的叙述修订计划；不改图树或动作')
    finalize=sub.add_parser('finalize-client',help='仅封装精确绑定且PASS的payload质检结果，再以final模式只读复验')
    finalize.add_argument('--source',required=True,type=Path)
    finalize.add_argument('--qc-report',required=True,type=Path)
    finalize.add_argument('--output',required=True,type=Path)
    archive=sub.add_parser('archive-client',help='仅压缩已通过final只读质检的客户包并生成ZIP校验文件')
    archive.add_argument('--source',required=True,type=Path)
    archive.add_argument('--qc-report',required=True,type=Path)
    archive.add_argument('--output',required=True,type=Path)
    for release in (finalize, archive):
        release.add_argument('--effective-set',required=True,type=Path,help='显式冻结的当前有效交付集合')
        release.add_argument('--cross-package-report',required=True,type=Path,help='绑定有效集合的独立跨包PASS报告')
    args=parser.parse_args(argv)
    try:
        if args.command=='archive-client':
            from .client_reports import archive_client_package
            result=archive_client_package(args.source,args.qc_report,args.output,
                effective_set=args.effective_set,cross_package_report=args.cross_package_report)
        elif args.command=='finalize-client':
            from .client_reports import finalize_client_package
            result=finalize_client_package(Path(__file__).resolve().parents[3],args.source,args.qc_report,args.output,
                effective_set=args.effective_set,cross_package_report=args.cross_package_report)
        elif args.command=='package':
            if args.layout=='candidate':
                if args.reviews or args.approved_only or args.evidence_output or args.review_output or args.facts or args.revisions or args.selection_report:
                    raise ValueError('人工筛选和包外证据参数仅用于 --layout client')
                from .candidate import build_candidate
                result=build_candidate(Path(__file__).resolve().parents[3],args.source,args.output)
            else:
                from .client_package import build_client_package
                result=build_client_package(Path(__file__).resolve().parents[3],args.source,args.output,
                    reviews=args.reviews,approved_only=args.approved_only,
                    evidence_output=args.evidence_output,review_output=args.review_output,
                    facts=args.facts,revisions=args.revisions,selection_report=args.selection_report)
        elif args.command=='preflight':
            import asyncio
            from .preflight import preflight_plan
            result=asyncio.run(preflight_plan(args.plan,args.output,args.samples,args.interval_ms,args.preserve_order))
        elif args.command=='runtime-close-replan':
            from .collect_runtime import close_scope_for_replan
            result=close_scope_for_replan(args.output,args.registry,args.reason,read_json(args.evidence))
        elif args.command in ('runtime-status','runtime-policy','runtime-resume'):
            from .collect_runtime import runtime_scope
            from .runtime import RuntimeStore
            store=RuntimeStore(args.registry,runtime_scope(args.output))
            if args.command=='runtime-resume':
                store.set_scope_paused(False,args.reason)
                result=store.snapshot()
            else:
                result=(store.snapshot() if args.command=='runtime-status' else
                        store.update_policy(read_json(args.updates),args.reason))
        elif args.command=='plan-publish':
            from .collect import validate_plan
            from .planning import publish_plan
            plan=read_json(args.plan)
            validate_plan(plan)
            result=publish_plan(plan,read_json(args.capabilities))
            args.output.parent.mkdir(parents=True,exist_ok=True)
            # Exclusive create: a publication is never silently overwritten.
            with args.output.open('x',encoding='utf-8') as handle:
                json.dump(result,handle,ensure_ascii=False,indent=2,allow_nan=False)
                handle.write('\n')
        elif args.command=='collect':
            import asyncio
            from .collect import collect_plan
            result=asyncio.run(collect_plan(args.plan,args.output,args.registry,
                publication_path=args.publication,policy_path=args.policy,resume=args.resume))
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
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error) as e:
        print(json.dumps({'error':str(e),'kind':'command_or_configuration'},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    sys.exit(main())
