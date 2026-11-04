"""Read-only consumer projection of existing bound cumulative QC facts.

No scan, model call, review, registry write, or inferred effective population.
"""
from pathlib import Path
import sqlite3
from .batch_core import load_json, file_sha
from .planning import object_sha256, verify_evidence
from .react_context import collection_facts


def from_registry(registry, report_ref=None):
    result = collection_facts()
    def unknown(reason):
        defaults = collection_facts()
        for key in ('short_flow', 'near_duplicate_unique_samples'):
            result[key] = {**defaults[key], 'reason':reason}
        return result
    if registry is None:
        return unknown('没有当前工程registry绑定')
    try:
        from .current_chain import _meta, read_chain_scope, assert_current_result_path
        binding = _meta(registry)
        scope = read_chain_scope(binding['manifest']['path'])
        if Path(scope['registry']).resolve() != Path(registry).resolve():
            raise ValueError('报告registry与当前工程不匹配')
        if report_ref is None:
            # Existing producer projection is a trusted, explicit opt-in source.
            pool = scope.get('candidate_project', {}).get('pool')
            if not pool:
                return unknown('当前工程没有可选的有效集合报告来源')
            with sqlite3.connect(Path(pool).resolve().as_uri()+'?mode=ro', uri=True) as con:
                if not con.execute("SELECT 1 FROM sqlite_master WHERE name='application_delivery_projection'").fetchone():
                    return unknown('当前工程尚未绑定有效集合报告')
                refs = [row[0] for row in con.execute('SELECT DISTINCT reference FROM application_delivery_projection')]
            if len(refs) != 1:
                return unknown('有效集合报告来源缺失或存在多个不一致绑定')
            import json
            report_ref = json.loads(refs[0])
        verify_evidence([report_ref]); report = load_json(report_ref['path'])
        if (report.get('schema_version') != 'qc-cumulative-report-1'
                or report.get('scope') != 'cumulative-mechanical'
                or report.get('manifest_sha256') != object_sha256(report['manifest'])
                or report.get('input_integrity_checked_before_and_after') is not True):
            raise ValueError('累计报告缺少完整manifest与输入摘要绑定')
        from quality_inspector.profiles import package_files
        from quality_inspector.version_compare import compare_versions
        from quality_inspector.contract import fingerprint
        if report.get('contract_sha256') != fingerprint()[1]:
            raise ValueError('累计报告规则版本与当前安装规则不一致')
        manifest = report['manifest']
        for package in manifest['packages']:
            root = assert_current_result_path(scope, package['path'])
            files = package_files(root)
            if (files != package['package_files_sha256']
                    or files != report['input_files_sha256'].get(str(root))):
                raise ValueError('累计报告包文件摘要已变化')
        versions = compare_versions(manifest, base=Path(report_ref['path']).parent)
        if versions['status'] != 'PASS' or versions != report['version_comparison']:
            raise ValueError('报告有效成员与当前版本解析不一致')
        members = versions['effective_samples']; ids = [m['sample_id'] for m in members]
        if len(ids) != len(set(ids)) or len(ids) != report['sample_count']:
            raise ValueError('有效集合成员与报告分母不一致')
        if not ids:
            return unknown('显式有效集合分母为零')
        if (not report.get('packages')
                or {p.get('path') for p in report['packages']} != {p['path'] for p in manifest['packages']}
                or any(p.get('format_status') != 'PASS' for p in report['packages'])):
            raise ValueError('报告成员格式检查未完成或未通过')
        short = 0
        with sqlite3.connect(Path(registry).resolve().as_uri()+'?mode=ro', uri=True) as con:
            for member in members:
                sample = Path(member['sample_path']).resolve()
                annotation = assert_current_result_path(scope, sample/'annotation.json')
                original = con.execute('''SELECT r.annotation_sha256 FROM current_chain_results r
                    WHERE r.sample_id=? AND EXISTS(SELECT 1 FROM m4_attempts a
                    WHERE a.sample_id=r.sample_id AND a.task_key=r.task_key)''', (member['sample_id'],)).fetchone()
                if not original or original[0] != file_sha(annotation):
                    raise ValueError('有效成员不属于当前工程已绑定原样本')
                value = load_json(annotation)
                if value['sample_id'] != member['sample_id'] or type(value.get('short_flow', False)) is not bool:
                    raise ValueError('有效成员身份或short_flow字段无效')
                short += int(value.get('short_flow', False))
        basis = {'source':report_ref, 'scope':{'chain_id':scope['chain_id'], 'manifest':scope['manifest'],
                 'registry':scope['registry'], 'effective_manifest_sha256':report['manifest_sha256'],
                 'effective_sample_ids_sha256':object_sha256(sorted(ids))},
                 'rules':{'contract_sha256':report['contract_sha256']}}
        def known(n):
            return {'status':'KNOWN','numerator':n,'denominator':len(ids),'ratio':n/len(ids), **basis}
        if type(report['statistics'].get('short_flow_count')) is int and short == report['statistics']['short_flow_count']:
            result['short_flow'] = known(short)
        else:
            result['short_flow']['reason'] = '报告短流程分子与原annotation重算不一致'
        duplicate = report.get('duplicates', {}); summary = duplicate.get('summary', {})
        from quality_inspector.duplicates import summarize
        if (summary.get('analysis_status') == 'COMPLETE'
                and summary.get('unadjudicated_pair_count') == 0
                and set(summary.get('current_sample_ids', [])) == set(ids)
                and summary.get('current_sample_count') == len(ids)
                and {r['sample_id'] for r in duplicate.get('rows', [])} == set(ids)
                and duplicate.get('sample_count') == len(ids)
                and duplicate.get('search', {}).get('exhaustive_verification', {}).get('status') != 'FAIL'):
            try:
                recomputed = summarize(duplicate)
            except (KeyError, ValueError, TypeError):
                recomputed = None
            affected = summary.get('affected_current_sample_ids', [])
            if (recomputed == summary and len(affected) == len(set(affected))
                    and set(affected) <= set(ids) and summary['affected_current_sample_count'] == len(affected)):
                result['near_duplicate_unique_samples'] = known(len(affected))
        verify_evidence([report_ref])  # No mid-read report replacement.
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError, sqlite3.Error) as error:
        # Invalid advice must not block an otherwise eligible candidate.
        return unknown('有效集合报告不可核验：' + str(error))
