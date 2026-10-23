"""Reconcile a human-authored export with a trusted, unchanged review bundle.

This checks record integrity, not the identity or quality of the human reviewer.
It never changes collection manifests or declares formal delivery ready.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from .validate import read_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_review(record_path, index_path, expected_index_sha256):
    index_path = Path(index_path).resolve()
    if sha(index_path) != expected_index_sha256:
        raise ValueError('核验索引与可信SHA-256不符；应使用阶段验收摘要记录的校验值')
    index = read_json(index_path)
    rows = index['samples']
    expected = {r['sample_id']: r for r in rows}
    if not rows or len(expected) != len(rows):
        raise ValueError('核验索引没有候选或编号重复')
    issues, results = [], []

    def fail(code, path, message):
        issues.append({'code': code, 'path': path, 'message': message})

    record = None
    try:
        record = read_json(Path(record_path))
    except (ValueError, UnicodeError, RecursionError) as error:
        fail('review_json', 'review', str(error))
    if not isinstance(record, dict):
        fail('review_type', 'review', '核验记录必须为对象')
        record = {}
    if record.get('review_type') != 'human_authored':
        fail('review_source', 'review/review_type', '必须是实际核验人导出的human_authored记录')
    if not isinstance(record.get('reviewer'), str) or not record['reviewer'].strip():
        fail('reviewer', 'review/reviewer', '必须填写实际核验人姓名')
    try:
        reviewed_at = datetime.fromisoformat(record.get('reviewed_at', '').replace('Z', '+00:00'))
        if reviewed_at.tzinfo is None:
            raise ValueError('核验时间必须带时区')
    except (TypeError, ValueError, AttributeError) as error:
        fail('review_time', 'review/reviewed_at', str(error))
    if record.get('delivery_ready') is not False:
        fail('delivery_claim', 'review/delivery_ready', '人工记录不能自动声明正式交付通过')
    entries = record.get('records')
    if not isinstance(entries, list):
        fail('review_type', 'review/records', 'records必须为数组')
        entries = []
    seen = set()
    for i, entry in enumerate(entries):
        path = f'review/records/{i}'
        if not isinstance(entry, dict) or not isinstance(entry.get('sample_id'), str):
            fail('review_type', path, '每项须为含sample_id的对象')
            continue
        sid = entry['sample_id']
        if sid in seen:
            fail('duplicate_sample', path + '/sample_id', sid)
            continue
        seen.add(sid)
        if sid not in expected:
            fail('unknown_sample', path + '/sample_id', sid)
            continue
        row = expected[sid]
        for key in ['batch_id', 'annotation_sha256', 'source_file_sha256']:
            if entry.get(key) != row[key]:
                fail('review_binding', path + '/' + key, '记录与核验包不对应')
        decision = entry.get('decision')
        if not isinstance(decision, str) or decision not in {'pending', 'pass', 'reject'}:
            fail('review_decision', path + '/decision', '结论须为pending、pass或reject')
            decision = 'pending'
        visited = entry.get('visited_steps')
        step_ids = [s['step_id'] for s in row['annotation']['steps']]
        if (not isinstance(visited, list) or any(type(s) is not int for s in visited)
                or len(set(visited)) != len(visited) or not set(visited).issubset(step_ids)):
            fail('review_steps', path + '/visited_steps', '步骤须为不重复的合法整数编号')
            visited = []
        for key in ['alignment', 'semantics', 'language']:
            if type(entry.get(key)) is not bool:
                fail('review_type', path + '/' + key, '核对项必须是布尔值')
        if decision == 'pass' and (set(visited) != set(step_ids)
                or any(entry.get(key) is not True for key in ['alignment', 'semantics', 'language'])):
            fail('incomplete_pass', path, '通过须逐张查看并完成三项核对')
        notes = entry.get('notes')
        if not isinstance(notes, str) or (decision == 'reject' and not notes.strip()):
            fail('review_notes', path + '/notes', '备注须为字符串，退回必须说明问题')
        results.append({'sample_id': sid, 'decision': decision})
    for sid in sorted(set(expected) - seen):
        fail('missing_sample', 'review/records', sid)

    # Compare both review copies and originals; an intact export cannot approve
    # data that changed after the reviewer opened it.
    for sid, row in expected.items():
        roots = {'source': Path(row['batch_path']) / 'samples' / sid,
                 'review_copy': index_path.parent / row['asset_path']}
        for kind, root in roots.items():
            root = root.resolve()
            actual_files={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() or p.is_symlink()}
            if actual_files != set(row['source_file_sha256']):
                fail('file_inventory', f'{kind}/{sid}', '文件清单与核验包不符')
            for relative, digest in row['source_file_sha256'].items():
                path = f'{kind}/{sid}/{relative}'
                try:
                    file = root / relative
                    if not file.resolve().is_relative_to(root):
                        raise ValueError('文件逃逸样本目录')
                    if sha(file) != digest:
                        fail('file_changed', path, '文件与核验时的校验值不符')
                except (OSError, ValueError, RuntimeError) as error:
                    fail('file_unavailable', path, str(error))
    valid = not issues
    counts = {key: sum(r['decision'] == key for r in results) for key in ['pass', 'reject', 'pending']}
    return {'record_integrity_pass': valid, 'all_samples_reviewed': valid and counts['pending'] == 0,
            'all_samples_pass': valid and counts['pass'] == len(rows), 'candidate_samples': len(rows),
            'counts': counts, 'reviewer': record.get('reviewer'), 'reviewed_at': record.get('reviewed_at'),
            'record_sha256': sha(Path(record_path)), 'index_sha256': sha(index_path),
            'results': results, 'issues': issues, 'delivery_ready': False,
            'note': '只核对记录完整性和文件一致性；不认证核验人身份，不代替人工看图，不修改批次或阶段状态。'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='对账人工核验导出记录，不自动批准交付')
    parser.add_argument('record', type=Path)
    parser.add_argument('--index', required=True, type=Path)
    parser.add_argument('--expected-index-sha256', required=True)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        index = read_json(args.index)
        report = args.report.resolve()
        roots = [Path(r['batch_path']) / 'samples' / r['sample_id'] for r in index['samples']]
        roots += [args.index.resolve().parent / r['asset_path'] for r in index['samples']]
        if any(report.is_relative_to(root.resolve()) for root in roots):
            raise ValueError('对账报告必须保存在样本目录外')
        if report.exists() or report.is_symlink():
            raise FileExistsError('报告已存在，拒绝覆盖')
        result = verify_review(args.record, args.index, args.expected_index_sha256)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('x', encoding='utf-8') as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
            file.write('\n')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['all_samples_pass'] else 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        print(json.dumps({'error': str(error), 'kind': 'command_or_configuration'}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
