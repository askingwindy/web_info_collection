"""Candidate assembly only: execution and byte integrity never declare acceptance."""
import hashlib,json,shutil
from collections import Counter
from pathlib import Path
from .production_quality import sha,contract_identity

def sums(root):
    root=Path(root)
    lines=[sha(p)+'  '+p.relative_to(root).as_posix()+'\n' for p in sorted(root.rglob('*')) if p.is_file() and p!=root/'SHA256SUMS']
    (root/'SHA256SUMS').write_text(''.join(lines))

def build_candidate(repo,source,output):
    repo=Path(repo).resolve();source=Path(source).resolve();output=Path(output).resolve()
    if not source.is_dir():raise ValueError('source directory missing')
    if output.exists():raise FileExistsError('refuse to overwrite candidate')
    if output.is_relative_to(source) or source.is_relative_to(output):raise ValueError('input/output cannot contain each other')
    originals={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()}
    # Complete sample evidence is always copied, even when its diagnostics fail.
    shutil.copytree(source,output);docs=output/'docs';docs.mkdir(exist_ok=True)
    authority=contract_identity(repo)
    for rel in authority['authority_files_sha256']:
        shutil.copyfile(repo/rel,docs/Path(rel).name)
    data=[];parse_errors=[];batch_rows=[]
    for marker in sorted(output.glob('*/manifest.json')):
        batch=marker.parent;rows=[]
        for ann in sorted((batch/'samples').glob('*/annotation.json')):
            try:
                a=json.loads(ann.read_text());rows.append({'sample_id':a['sample_id'],'steps':len(a['steps']),'task_type':a['task_type'],'source':a['trajectory_source']});data.append(a)
            except (OSError,ValueError,KeyError,TypeError) as e:parse_errors.append({'path':ann.relative_to(output).as_posix(),'reason':str(e)})
        attempts=json.loads(marker.read_text()).get('attempts')
        attempts_known=isinstance(attempts,list)
        rejected=[row for row in (attempts if attempts_known else []) if isinstance(row,dict) and row.get('status')=='rejected']
        status='FAIL' if any(e['path'].startswith(batch.name+'/') for e in parse_errors) else 'REVIEW_REQUIRED'
        report={'status':status,'sample_count':len(rows),'step_count':sum(row['steps'] for row in rows),'samples':rows,'rejected_count':len(rejected) if attempts_known else None,'attempt_history_available':attempts_known,'rejected_attempts':rejected,'quality_checks':[{'item':i,'status':'REVIEW_REQUIRED','reason':'Independent QC not run by candidate builder; inspect evidence and import real QC result.'} for i in range(1,18)],'parser_errors':[e for e in parse_errors if e['path'].startswith(batch.name+'/')],'human_signed':False,'ai_visual_review_executed_by_builder':False,'customer_actual_program_executed':False}
        (batch/'qc_report.md').write_text('# 候选质检范围记录\n\n本组包程序未执行独立质检，不宣告合格。下列为本次实际输入统计和未执行项，不复用历史审核覆盖数。\n\n```json\n'+json.dumps(report,ensure_ascii=False,indent=2)+'\n```\n')
        batch_rows.append(report);sums(batch)
    if not batch_rows:parse_errors.append({'path':'.','reason':'No batches with manifest.json found'})
    manifest={'document_roles':{'readme':'README.md','fields':'docs/附件A-字段说明.md','synthesis':'docs/合成方式说明.md','source':'docs/来源与合规说明.md'},'candidate_status':'FAIL' if parse_errors else 'REVIEW_REQUIRED','delivery_ready':False,'customer_acceptance':'UNKNOWN','samples':len(data),'frames':sum(len(a['steps']) for a in data),'batches':len(batch_rows),'authority':authority,'source_file_sha256':originals,'errors':parse_errors,'producer':{'module':'webcollect.candidate','sha256':sha(__file__)},'human_signed':False,'ai_review_coverage_claimed':0}
    (output/'candidate_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    (docs/'合成方式说明.md').write_text('# 合成方式与来源\n\n来源字段沿用实际采集，不改human/T6等历史来源。新采集由webcollect正式生成器执行，动作参数依附件B，坐标来自真实同步DOM及截图；步骤文字为状态差异模板及已验证断言，不调用外部模型。内部data_type是生产线编号，不是客户唯一常量。\n\n本候选实际出现的来源配置：\n```json\n'+json.dumps([json.loads(s) for s in sorted({json.dumps(a['trajectory_source'],sort_keys=True) for a in data})],ensure_ascii=False,indent=2)+'\n```\n\n采集配置、站点、账号使用及访问频率事实需逐批核对plan/manifest/evidence；组包器未访问源网站，不推断任意复制源均为公开页面或未登录。缺少来源事实必须待审，不把生产工具的预期策略当作每份输入的已证实事实。本文是待核对的来源索引，不代表网站许可或客户验收通过。\n')
    with (docs/'合成方式说明.md').open('a') as description:
        for dtype in sorted({a['trajectory_source']['data_type'] for a in data}):
            description.write('\n## '+dtype+'\n\n该生产线实际声明的动作空间：'+', '.join(sorted({a['trajectory_source']['action_space'] for a in data if a['trajectory_source']['data_type']==dtype}))+'；实际动作参数依附件B逐项保留，语义与来源身份仍由独立审核核对。\n')
    (docs/'来源与合规说明.md').write_text('本候选来源与采集声明见合成方式说明.md及各批plan/manifest/evidence；若缺少声明，独立质检须退回。组包未进行登录、网站操作或许可核实。')
    (output/'README.md').write_text('# 独立交付候选\n\n状态：'+manifest['candidate_status']+'；正式合格数未宣告。实际批次'+str(len(batch_rows))+'，样本'+str(len(data))+'，截图'+str(manifest['frames'])+'。原始证据随批次保留；质检及视觉审核尚待独立程序执行，SHA只证明完整性。\n\n```json\n'+json.dumps({'apps':dict(Counter(a['app_info']['app_name'] for a in data)),'task_types':dict(Counter(t for a in data for t in a['task_type'])),'step_counts':[len(a['steps']) for a in data]},ensure_ascii=False,indent=2)+'\n```\n')
    sums(output)
    # Business evidence stays identical; only package report/checksum documents may be regenerated.
    modified=[rel for rel,digest in originals.items() if sha(output/rel)!=digest]
    assert all(Path(rel).name in ['SHA256SUMS','qc_report.md','README.md','candidate_manifest.json'] or Path(rel).parts[0]=='docs' for rel in modified),modified
    return {**manifest,'output':str(output),'source_package_documents_regenerated':modified}
