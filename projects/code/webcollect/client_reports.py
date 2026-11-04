"""Attach a verified QC summary to a new customer output; never edit QC input."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from .client_package import read_json, sample_hashes, sha, validate_client_layout


def _file_hashes(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Cannot bind a symbolic customer file: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def _aggregate(values):
    values = list(values)
    return 'FAIL' if 'FAIL' in values else 'REVIEW_REQUIRED' if not values or 'REVIEW_REQUIRED' in values else 'PASS'


def _protect_scope_output(output, scope):
    output = Path(output).resolve()
    if any(output.is_relative_to(Path(root)) or Path(root).is_relative_to(output)
           for root in scope['package_roots']):
        raise ValueError('Release output must be outside every effective-set source package')
    if any(output == Path(scope[key]['path']) or Path(scope[key]['path']).is_relative_to(output)
           for key in ('effective_set', 'cross_package_report')):
        raise ValueError('Release output cannot replace delivery binding evidence')


class StaleSemanticRules(ValueError):
    """A cached report predates the current semantic rule versions."""


def validate_report_semantic_rules(report):
    """Reject stale cached PASS without rerunning or inventing a review."""
    from quality_inspector.semantic import rule_ids
    current = rule_ids(); saved = report.get('semantic_rule_ids')
    affected = sorted(set(current) | (set(saved) if isinstance(saved, dict) else set()))
    if isinstance(saved, dict):
        affected = [name for name in affected if name not in saved or name not in current or saved[name] != current[name]]
    if affected:
        raise StaleSemanticRules('Cached QC report has missing/changed semantic rules; affected checks: '
                         + ', '.join(affected) + '; run independent deterministic QC again before packaging')
    return current


def _bound_report(source, report_path):
    report = read_json(report_path)
    if not isinstance(report, dict) or report.get('program') != 'quality-inspector':
        raise ValueError('A quality-inspector report is required')
    dataset = report.get('dataset')
    if not isinstance(dataset, str) or Path(dataset).resolve() != source:
        raise ValueError('QC report dataset differs from the customer source')
    files = _file_hashes(source)
    declared = report.get('input_files_sha256', report.get('package_files_sha256'))
    if not isinstance(declared, dict) or not declared or declared != files:
        raise ValueError('QC report has no complete current customer-file hash binding')
    checksum = report.get('root_checksum', {})
    if not isinstance(checksum, dict) or checksum.get('pass') is not True:
        raise ValueError('QC report did not verify the complete customer SHA256SUMS')
    # Do not use an edited checksum to make an incomplete manifest look bound.
    expected_manifest = ''.join(digest + '  ' + relative + '\n'
                                for relative, digest in files.items() if relative != 'SHA256SUMS')
    if (source / 'SHA256SUMS').read_text() != expected_manifest:
        raise ValueError('Customer checksum manifest is not complete and byte-reproducible')
    actual = {path.parent.name: path.parent for path in (source / 'samples').glob('*/annotation.json')}
    rows = report.get('samples')
    if not isinstance(rows, list) or len(rows) != len(actual):
        raise ValueError('QC report sample population differs from the customer source')
    seen = set()
    for row in rows:
        sid = row.get('sample_id') if isinstance(row, dict) else None
        if sid not in actual or sid in seen:
            raise ValueError('QC report sample IDs are missing, duplicate or unknown')
        seen.add(sid)
        hashes = sample_hashes(actual[sid])
        if row.get('annotation_sha256') != hashes.pop('annotation.json') or row.get('evidence_sha256') != hashes:
            raise ValueError('QC report sample annotation/image/tree binding differs: ' + sid)
        if not isinstance(row.get('sample_path'), str) or Path(row['sample_path']).resolve() != actual[sid]:
            raise ValueError('QC report did not inspect the actual client sample path: ' + sid)
    validate_report_semantic_rules(report)
    return report, files


def _delivery_report_bindings(report):
    """A cached PASS must retain its current requirement and profile bindings.

    Rechecking these local facts does not rerun any semantic review. A report
    without a contract identity cannot opt out of the cross-package comparison.
    """
    from quality_inspector.contract import fingerprint
    from quality_inspector.profiles import load as load_profile
    baseline = report.get('requirements_baseline')
    current_contract = fingerprint()[1]
    if not isinstance(baseline, dict) or baseline.get('sha256') != current_contract:
        raise ValueError('QC report requirement identity is missing or changed; rerun deterministic QC with the original reviews')
    profile = report.get('local_profile')
    try:
        current_profile = load_profile(profile['path'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError('QC report profile binding is missing or changed') from error
    if profile != current_profile:
        raise ValueError('QC report profile binding changed; rerun deterministic QC with the original reviews')
    return current_contract


def _source_population(report):
    """A missing original denominator stays unknown; never substitute selected N."""
    source = Path(report.get('dataset', '')) / '来源与合规说明.md'
    if source.is_file():
        for block in re.findall(r'```json\s*\n(.*?)\n```', source.read_text(encoding='utf-8'), re.S):
            try:
                selection = json.loads(block)
            except ValueError:
                continue
            if isinstance(selection, dict) and {'total_samples', 'selected_count', 'excluded_count'} <= selection.keys():
                return {'status': 'RECORDED', 'population': {k: selection[k] for k in ('total_samples', 'selected_count', 'excluded_count')},
                        'excluded_samples': selection.get('excluded_samples', []), 'source': '来源与合规说明.md',
                        'scope': selection.get('scope', '当前交付来源说明声明的筛选总体；不推断其他历史批次'),
                        'selection_exclusions_are_not_all_historical_capture_rejections': True}
    evidence = report.get('external_evidence', {})
    if not isinstance(evidence, dict) or evidence.get('status') != 'PASS':
        return {'status': 'UNKNOWN', 'reason': 'No complete bound source population index'}
    path = evidence.get('path')
    if not isinstance(path, str) or not Path(path).is_file() or sha(path) != evidence.get('sha256'):
        return {'status': 'UNKNOWN', 'reason': 'Original evidence index is unavailable or changed'}
    index = read_json(Path(path))
    if not isinstance(index, dict) or index.get('schema_version') != 'webcollect-client-evidence-1':
        return {'status': 'UNKNOWN', 'reason': 'No supported source population index'}
    excluded = []
    for record in index.get('excluded_samples', []):
        review = record.get('review') or {}
        checks = review.get('checks', {})
        excluded.append({'sample_id': record.get('sample_id'), 'selection_reason': record.get('reason'),
                         'non_pass_human_checks': {key: value for key, value in checks.items()
                                                   if value.get('status') != 'PASS'}})
    return {'status': 'RECORDED', 'population': index.get('source_population'),
            'excluded_samples': excluded,
            'selection_exclusions_are_not_all_historical_capture_rejections': True}


def _render_summary(source, report_path, report, files, batch_name=None):
    samples = report['samples']
    by_sample = [{check['rule_id']: check for check in row.get('local_checks', row.get('checks', []))}
                 for row in samples]
    requirements = [
        (1, 'JSON可解析、必填字段及类型', ['C01']),
        (2, '图树数量、连续命名、样本目录树', ['C05', 'C06']),
        (3, '图片与界面树路径存在', ['C06']),
        (4, 'PNG分辨率及图树坐标空间一致', ['C06']),
        (5, 'step_id从1连续', ['C05']),
        (6, '至少5有效操作或明确短流程', ['C11']),
        (7, '指针、目标框与整数像素坐标', ['C08']),
        (8, '同步控件ID与原文引用', ['C07']),
        (9, '统一动作、工具名及参数', ['C09']),
        (10, '执行成功及完成状态', ['C10']),
        (11, '末步complete与终态', ['C10']),
        (12, '任务类型标签', ['C03']),
        (13, '中文、完整性及原文名称', ['REVIEW_LANGUAGE']),
        (14, '叙述无明确禁止的机器引用', ['C12']),
        (15, '叙述无明确禁止的采集过程说法', ['C12']),
        (16, '动作变化、连续性与任务完成',
         ['REVIEW_VISUAL_ALIGNMENT', 'REVIEW_TERMINAL_SEMANTICS']),
        (17, '隐私', ['REVIEW_PRIVACY']),
    ]
    lines = ['# 客户输出独立质检摘要', '',
             '本摘要来自已实际检查的客户文件，不由导出结构自检替代。'
             '来源检查对象是下列来源包；附入新目录时需要再次质检，新目录复验报告独立保存在包外。', '',
             '- 来源客户包：' + source.name,
             '- 来源完整文件清单SHA256：' + files['SHA256SUMS'],
             '- 原始独立QC报告SHA256：' + sha(report_path),
             '- 质检器：' + str(report.get('program')) + ' / ' + str(report.get('version')), '',
             '| 需求项 | 核对内容 | 实际结果 | 规则依据 |', '|---:|---|---|---|']
    if report.get('scope') == 'delivery':
        lines[2] = '本报告记录对本批实际交付内容的全量检查与逐图复核。内容摘要绑定所有样本及配套文件，报告和校验和文件不参与自身内容摘要；最终封包采用只读复验。'
        lines[4] = '- 批次：' + (batch_name or source.name)
    sampling = report.get('semantic_sampling')
    if sampling:
        lines[2] = '本报告记录全量工程检查及按冻结策略进行的语义抽检。未抽中样本不记作AI或人工审核通过；最终封包重新核对实际文件与策略绑定。'
    for number, title, rules in requirements:
        state = _aggregate(checks.get(rule, {}).get('status', 'REVIEW_REQUIRED')
                           for checks in by_sample for rule in rules)
        if sampling and any(rule.startswith('REVIEW_') for rule in rules):
            state = '按抽检策略核验，实际覆盖见下表'
        lines.append(f'| {number} | {title} | {state} | {", ".join(rules)} |')
    semantic = ['visual_alignment', 'terminal_semantics', 'language', 'privacy', 'substantive_difference']
    coverage = {'human_complete_samples': 0, 'ai_complete_samples': 0, 'pending_or_missing_samples': 0}
    reviewer_counts = Counter()
    for checks in by_sample:
        selected = [checks.get('REVIEW_' + name.upper(), {}) for name in semantic]
        kinds = {(check.get('reviewer') or {}).get('kind') for check in selected}
        definite = all(check.get('status') in ['PASS', 'FAIL'] for check in selected)
        identities = {((check.get('reviewer') or {}).get('kind'),
                       (check.get('reviewer') or {}).get('name')) for check in selected}
        if definite and len(identities) == 1:
            identity = next(iter(identities))
            if identity[0] in ('ai', 'human') and isinstance(identity[1], str) and identity[1].strip():
                reviewer_counts[identity] += 1
        if definite and kinds == {'human'}:
            coverage['human_complete_samples'] += 1
        elif definite and kinds == {'ai'}:
            coverage['ai_complete_samples'] += 1
        else:
            coverage['pending_or_missing_samples'] += 1
    coverage['selection'] = 'Counted imported evidence-bound decisions; not a claim of new or random human sampling'
    coverage['samples_in_this_output'] = len(samples)
    coverage['reviewer_sources'] = [{'kind': kind, 'name': name, 'samples': count}
                                  for (kind, name), count in sorted(reviewer_counts.items())]
    if sampling:
        coverage.update(
            acceptance_basis='frozen_sampling_policy',
            policy=sampling.get('policy'),
            original_denominator=sampling.get('original_denominator'),
            actual_ai_reviewed=sampling.get('actual_ai_reviewed'),
            actual_human_reviewed=sampling.get('actual_human_reviewed'),
            not_selected=sampling.get('not_selected'),
            human_pending_count=sampling.get('human_pending_count'),
            replacement_required_count=sampling.get('replacement_required_count'),
            unselected_is_not_semantic_pass=True)
    duplicates = report.get('duplicates', {})
    distribution = {}
    with (source / 'metadata.csv').open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    distribution.update(sample_count=len(rows), site_count=len({row['site_id'] for row in rows}),
                        categories=dict(Counter(row['site_category'] for row in rows)),
                        task_types=dict(Counter(task for row in rows for task in json.loads(row['task_type']))),
                        step_counts=dict(Counter(int(row['steps']) for row in rows)))
    conclusions = {'sample_status_counts': report.get('local_sample_status_counts', report.get('sample_status_counts')),
                   'acceptance_scopes': {key: {'status': value.get('status'),
                                               'non_pass_rules': [check['rule_id'] for check in value.get('checks', [])
                                                                  if check.get('status') != 'PASS']}
                                         for key, value in report.get('acceptance_scopes', {}).items()},
                   'local_acceptance_status': report.get('local_acceptance_status', 'NOT_CONFIGURED'),
                   'package_review': report.get('package_review', {}).get('status', 'REVIEW_REQUIRED'),
                   'customer_actual_acceptance': report.get('customer_actual_acceptance', 'UNKNOWN')}
    data = {'distribution': distribution, 'review_coverage': coverage,
            'four_route_duplicates': {'pair_comparisons': duplicates.get('pair_comparisons'),
                                      'route1': duplicates.get('route1', {}).get('confirmed_pair_count'),
                                      **{route: duplicates.get(route, {}).get('count')
                                         for route in ['route2', 'route3', 'route4']},
                                      'resolution':{key:value for key,value in duplicates.get('summary',{}).items()
                                                    if key not in ('pair_adjudications','current_sample_ids','affected_current_sample_ids')},
                                      'customer_algorithm_equivalence': 'UNKNOWN'},
            'original_source_population': _source_population(report),
            'capture_history_total_rejections': 'UNKNOWN; selection exclusions are recorded separately',
            'conclusions': conclusions}
    if report.get('delivery_scope'):
        data['delivery_scope'] = report['delivery_scope']
    if report.get('contract_status'):
        data['contract_status'] = report['contract_status']
    if report.get('delivery_status'):
        data['delivery_status'] = report['delivery_status']
    if report.get('scope') == 'delivery':
        data.pop('capture_history_total_rejections', None)
        data['rejection_statistics_scope'] = data['original_source_population'].get('scope', '本批已记录的来源筛选总体；未记录的历史尝试不作推断。')
        data['delivery_document_review'] = report.get('delivery_document_review',
            {'status': 'REVIEW_REQUIRED', 'reason': 'Actual delivery-document review was not supplied.'})
    if sampling:
        data['semantic_sampling'] = {key: sampling.get(key) for key in (
            'policy', 'plan_sha256', 'original_denominator', 'actual_ai_reviewed',
            'actual_human_reviewed', 'not_selected', 'human_pending_count', 'replacement_required_count')}
    # Hash the inspected payload rather than the report/checksum that contain it.
    # This binding survives attaching this report and recomputing SHA256SUMS.
    excluded = {'qc_report.md', 'SHA256SUMS'} if 'delivery_status' in report else {'qc_report.md', 'SHA256SUMS', 'README.md'}
    data['payload_files_sha256'] = {name: digest for name, digest in files.items() if name not in excluded}
    data['payload_sha256'] = hashlib.sha256(json.dumps(data['payload_files_sha256'], ensure_ascii=False,
                                                      sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    lines += ['', '## 分布、去重、来源分母与真实审核覆盖', '', '```json',
              json.dumps(data, ensure_ascii=False, indent=2), '```', '',
              '附件A/B的结构、字段、参数与坐标规则由程序逐项核查；中文可读性、实际图像可见性、'
              '完整语义和隐私结论按绑定样本的实际审核记录导入。没有审核或无法证明的项目仍为待审。'
              '本摘要不新增或更改真人签署，不把导出、文件完整或已有样本审核结论推定为整批分布和客户验收通过。', '']
    if sampling:
        lines += ['本批采用显式抽检策略；未抽中只表示按策略准入，不表示逐条语义审核通过。AI问题全部转人工，人工否决后的替换样本须复检。', '']
    return '\n'.join(lines)


def finalize_client_package(repo, source, qc_report, output, *, effective_set=None, cross_package_report=None):
    """Create a new customer package with an honest summary of a bound QC run."""
    source = Path(source).resolve()
    report_path = Path(qc_report).resolve()
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refuse to overwrite finalized customer output')
    output = output.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Customer source and finalized output cannot contain each other')
    validate_client_layout(source)
    report, original_files = _bound_report(source, report_path)
    if report.get('delivery_status') != 'PASS' or report.get('inspection_stage') != 'payload':
        raise ValueError('Customer release requires a PASS delivery check; no failed or pending release')
    contract_hash = _delivery_report_bindings(report)
    from quality_inspector.delivery_scope import verify_delivery_scope
    scope = verify_delivery_scope(effective_set, cross_package_report, dataset=source,
        expected_contract=contract_hash)
    from quality_inspector.profiles import verify_member_release
    verify_member_release(report, scope)
    _protect_scope_output(output, scope)
    report_sha256 = sha(report_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.' + output.name + '.staging-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'client'
        shutil.copytree(source, staged)
        (staged / 'qc_report.md').write_text(_render_summary(source, report_path, report, original_files, output.name), encoding='utf-8')
        if 'delivery_status' not in report:
            readme = (staged / 'README.md').read_text()
            readme = readme.replace('当前独立QC状态：NOT_RUN', '已附入来源客户包的实际质检摘要；本新包复验报告由独立程序另存')
            readme += '\n\n质检摘要见[qc_report.md](qc_report.md)。各项状态保留原报告范围，未满足的分布要求、待审资料和客户UNKNOWN不因附报告而消失。\n'
            (staged / 'README.md').write_text(readme, encoding='utf-8')
        (staged / 'SHA256SUMS').write_text(''.join(sha(path) + '  ' + path.relative_to(staged).as_posix() + '\n'
                                                  for path in sorted(staged.rglob('*'))
                                                  if path.is_file() and path != staged / 'SHA256SUMS'), encoding='utf-8')
        validate_client_layout(staged)
        for sample in (source / 'samples').iterdir():
            if sample_hashes(sample) != sample_hashes(staged / 'samples' / sample.name):
                raise ValueError('Finalization modified an already-reviewed sample')
        if _file_hashes(source) != original_files or sha(report_path) != report_sha256:
            raise ValueError('QC source/report changed during finalization')
        final_scope = verify_delivery_scope(effective_set, cross_package_report, dataset=staged, phase='final',
            expected_contract=scope['contract_sha256'])
        if final_scope != scope:
            raise ValueError('Effective delivery binding changed during finalization')
        if output.exists():
            raise FileExistsError('Customer output appeared during finalization')
        staged.rename(output)
    return {'output': str(output), 'layout': 'client', 'source_qc_report_sha256': report_sha256,
            'source_customer_manifest_sha256': original_files['SHA256SUMS'],
            'samples': len(report['samples']), 'sample_files_byte_identical': True,
            'delivery_scope': scope,
            'next_step': 'Run independent QC directly on this new customer directory; existing sample evidence/review bindings remain applicable',
            'customer_acceptance': 'UNKNOWN', 'new_package_qc_status': 'NOT_RUN'}


def archive_client_package(source, qc_report, output, *, effective_set=None, cross_package_report=None):
    """Archive only a final, read-only-QC-verified release without changing it."""
    source=Path(source).resolve();output=Path(output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(source):
        raise ValueError('Archive must be a new file outside the verified input')
    checksum_path=Path(str(output)+'.sha256')
    if checksum_path.exists():raise FileExistsError('Archive checksum already exists')
    validate_client_layout(source)
    report,original=_bound_report(source,Path(qc_report).resolve())
    if report.get('delivery_status')!='PASS' or report.get('inspection_stage')!='final' or report.get('release_ready') is not True:
        raise ValueError('Archive requires a final PASS release-ready QC report')
    contract_hash = _delivery_report_bindings(report)
    from quality_inspector.delivery_scope import verify_delivery_scope
    scope = verify_delivery_scope(effective_set, cross_package_report, dataset=source, phase='final',
        expected_contract=contract_hash)
    from quality_inspector.profiles import verify_member_release
    verify_member_release(report, scope)
    _protect_scope_output(output, scope)
    _protect_scope_output(checksum_path, scope)
    report_hash = sha(qc_report)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.'+output.stem+'-',dir=output.parent) as temporary:
        candidate=Path(temporary)/output.name
        with zipfile.ZipFile(candidate,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for relative in sorted(original):archive.write(source/relative,source.name+'/'+relative)
        if _file_hashes(source)!=original:raise ValueError('Verified input changed during archiving')
        if (verify_delivery_scope(effective_set, cross_package_report, dataset=source, phase='final') != scope
                or sha(qc_report) != report_hash):
            raise ValueError('Effective delivery binding changed during archiving')
        candidate.rename(output)
    digest=sha(output);checksum_path.write_text(digest+'  '+output.name+'\n',encoding='utf-8')
    return {'archive':str(output.resolve()),'archive_sha256':digest,'members':len(original),'source':str(source),
            'delivery_scope':scope,
            'input_unchanged':True,'customer_acceptance':'UNKNOWN'}
