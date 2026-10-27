#!/usr/bin/env python3
"""Freeze a hash-bound client selection and its necessary audit evidence.

This is preservation only: it never edits a source, invents a review, deletes
history, or reconstructs an unavailable historical prompt/collection plan.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess


DELEGATED_PROMPT = """执行已授权Default模式。先负责冻结数据与逐图独立复核准备（勿改生产/QC代码、勿清理）。请写一个可复用保全脚本到projects/code/scripts/freeze_approved18.py 或独立脚本，执行：固定最新18包到 results/baselines/approved18-20261024/client-original；复制原20人工审核导出、被排除2样本完整原样本与truth；保留完整真实registry（先验证iteration registry覆盖其他2真实库再sqlite backup）到baseline/state，合成registry独立；提取18源raw、manifest、计划及修订/模板/提示词证据到最小必要source-evidence，不能简单保留全部旧结果；保存哈希、来源路径、原工作区git diff+untracked代码副本、冻结receipt。证据来源verify_results/client-output-pipeline-20261023/release-run-20261024/evidence.json。冻结完成发路径，root随后用源18生成新输出。冻结后先独立逐图查看124原图+对应annotation，输出真实AI复核findings，包括必须修订和不能修订的内容；不要伪造人工结论。可用view_image多图拼接辅助但逐帧可辨；保留实际覆盖记录。AI原始prompt用此委派原文落档。避免大日志，定时汇报。"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def registry_rows(path):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as con:
        if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Registry integrity failure: ' + str(path))
        return {table: con.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()
                for table in ('sites', 'batches', 'allocations')}


def freeze(repo, output, evidence, prechange, client):
    if output.exists():
        raise FileExistsError('Refuse to overwrite frozen baseline: ' + str(output))
    d = load(evidence)
    source = Path(d['source_root'])
    selected = [r for r in d['source_samples'] if r['selected']]
    excluded = [r for r in d['source_samples'] if not r['selected']]
    if (len(selected), len(excluded)) != (18, 2):
        raise ValueError('Expected the actual 18/20 selection')
    if {p.name for p in (client / 'samples').iterdir()} != {r['sample_id'] for r in selected}:
        raise ValueError('Client selection differs from bound source evidence')
    # Verify ledger coverage before any backup, with next_sample counters kept.
    registries = [repo / x for x in ('results/iteration-20261022/registry.sqlite3',
                   'results/ten-sites-goal-v1/registry.sqlite3', 'results/_work/M2-registry.sqlite3')]
    rows = [registry_rows(p) for p in registries]
    coverage = []
    for other, data in zip(registries[1:], rows[1:]):
        main_sites = {r[0]: r for r in rows[0]['sites']}
        site_ok = all(r[0] in main_sites and main_sites[r[0]][:4] == r[:4]
                      and main_sites[r[0]][4] >= r[4] for r in data['sites'])
        missing = {t: sorted(set(data[t]) - set(rows[0][t])) for t in ('batches', 'allocations')}
        if not site_ok or any(missing.values()):
            raise ValueError('Primary real ledger does not cover ' + str(other))
        coverage.append({'other_registry': str(other), 'site_identity_and_counter_coverage': True,
                         'missing_rows': missing, 'row_counts': {t: len(v) for t, v in data.items()}})
    if {r[3] for r in rows[0]['sites']} != {'real'}:
        raise ValueError('Real and synthetic ledger namespaces are mixed')
    synthetic = repo / 'projects/sample/integration/registry.sqlite3'
    synth_rows = registry_rows(synthetic)
    if {r[3] for r in synth_rows['sites']} != {'integration'}:
        raise ValueError('Synthetic registry has real IDs')
    review = Path(d['source_review_export']['path'])
    if sha(review) != d['source_review_export']['sha256']:
        raise ValueError('Original human review export changed')
    original_reviews = load(review)
    if len(original_reviews['records']) != 20 or original_reviews != d['source_review_document']:
        raise ValueError('Original human review export does not match the recorded 20')

    output.mkdir(parents=True)
    copied = []
    source_index = {}
    unavailable = []

    def copy(src, relative, expected=None):
        src = Path(src).resolve(); dest = output / relative
        if src.is_symlink() or not src.is_file() or not src.is_relative_to(repo):
            raise ValueError('Unsafe or missing evidence source: ' + str(src))
        before = sha(src)
        if expected is not None and before != expected:
            raise ValueError('Bound source hash mismatch: ' + str(src))
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if sha(dest) != before:
                raise ValueError('Conflicting preserved source: ' + str(dest))
            return dest
        shutil.copyfile(src, dest)
        if sha(dest) != before or sha(src) != before:
            raise ValueError('Source changed while freezing: ' + str(src))
        copied.append({'source': str(src), 'frozen': relative.as_posix(), 'sha256': before,
                       'bytes': dest.stat().st_size})
        source_index[str(src)] = relative.as_posix()
        return dest

    def tree(src, relative):
        for p in sorted(Path(src).rglob('*')):
            if p.is_symlink():
                raise ValueError('Symbolic preservation source: ' + str(p))
            if p.is_file():
                copy(p, relative / p.relative_to(src))

    def preserve_file(src, expected=None):
        p = Path(src).resolve()
        return copy(p, Path('source-evidence/original-paths') / p.relative_to(repo), expected)

    tree(client, Path('client-original'))
    checksum_entries = {}
    for line in (client / 'SHA256SUMS').read_text().splitlines():
        h, name = line.split('  ', 1); checksum_entries[name] = h
    if checksum_entries != {p.relative_to(client).as_posix(): sha(p) for p in client.rglob('*')
                            if p.is_file() and p.name != 'SHA256SUMS'}:
        raise ValueError('Original client SHA256SUMS mismatch')
    copy(evidence, Path('source-evidence/client-export-evidence.original.json'))
    copy(review, Path('reviews/original-human-review20.json'), d['source_review_export']['sha256'])
    write(output / 'reviews/excluded-samples.json', d['excluded_samples'])
    selected_ids = {r['sample_id'] for r in selected}
    for r in d['source_samples']:
        sample = Path(r['source_sample_path']); batch = Path(r['source_batch_path'])
        annotation = load(sample / 'annotation.json')
        if sha(sample / 'annotation.json') != r['annotation_sha256']:
            raise ValueError('Source annotation changed: ' + r['sample_id'])
        for name, digest in r['evidence_sha256'].items():
            if sha(sample / name) != digest:
                raise ValueError('Source sample asset changed: ' + str(sample / name))
        if r['selected']:
            if sha(client / 'samples' / r['sample_id'] / 'annotation.json') != r['annotation_sha256']:
                raise ValueError('Client annotation differs from selected source')
        else:
            tree(sample, Path('excluded-original/samples') / r['sample_id'])
            copy(r['source_ground_truth_path'], Path('excluded-original/ground_truth') / (r['sample_id'] + '.json'), r['ground_truth_sha256'])
        for name, digest in r['raw_evidence_files_sha256'].items():
            copy(batch / name, Path('source-evidence/batches') / batch.name / name, digest)
        copy(r['source_manifest_path'], Path('source-evidence/batches') / batch.name / 'manifest.json', r['source_manifest_sha256'])
        if (batch / 'plan.json').is_file():
            copy(batch / 'plan.json', Path('source-evidence/batches') / batch.name / 'plan.json')
        source_index[str(sample)] = ('client-original/samples/' if r['selected'] else 'excluded-original/samples/') + r['sample_id']

    # Preserve small provenance/documents, not the full preceding data rounds.
    for name in ('annotation-revision-provenance.json', 'mechanical-preservation-receipt.json',
                 'selection-provenance.json', 'source_manifest.json', 'candidate_manifest.json', 'README.md'):
        if (source / name).is_file():
            preserve_file(source / name)
    for name in ('docs', 'provenance'):
        if (source / name).is_dir():
            for p in sorted((source / name).rglob('*')):
                if p.is_file(): preserve_file(p)
    # Explicit predecessor paths support before/after text and capture-plan audits.
    seen_json = set()
    def follow(path, depth=0):
        path = Path(path).resolve()
        if path in seen_json or depth > 7 or path.suffix != '.json': return
        seen_json.add(path)
        try: document = load(path)
        except (OSError, ValueError): return
        def walk(value, key=''):
            if isinstance(value, dict):
                for k, v in value.items(): walk(v, k)
            elif isinstance(value, list):
                for v in value: walk(v, key)
            elif isinstance(value, str) and value.startswith(str(repo) + '/'):
                candidate = Path(value)
                if candidate.is_file() and (key == 'path' or key.endswith('_path') or key in ('source_current_review',)):
                    # Follow only small source/annotation/provenance files, never image inventories.
                    if candidate.suffix in ('.json', '.md', '.py', '.js') and candidate.stat().st_size < 3_000_000:
                        preserve_file(candidate); follow(candidate, depth + 1)
                elif candidate.is_dir() and (key.endswith('sample_path') or key in ('chunk', 'source_batch_path')):
                    paths = [candidate / 'annotation.json', candidate / 'manifest.json', candidate / 'plan.json']
                    for p in paths:
                        if p.is_file(): preserve_file(p); follow(p, depth + 1)
                elif (key == 'path' or key.endswith('_path')) and not candidate.exists():
                    unavailable.append({'path': value, 'referenced_by': str(path), 'reason': 'unavailable_at_freeze'})
        walk(document)
    for p in list(source.rglob('manifest.json')) + [source / 'annotation-revision-provenance.json']:
        follow(p)
    for p in sorted((repo / 'request').rglob('*.md')):
        preserve_file(p)
    # Current capture templates are preserved in the before-change code snapshot.
    if not prechange.is_dir(): raise ValueError('Missing root before-change source snapshot')
    tree(prechange, Path('workspace-before-change'))
    versions = set()
    for p in (output / 'source-evidence').rglob('*.json'):
        if 'manifest' not in p.name: continue
        try: m = load(p)
        except (OSError, ValueError): continue
        if isinstance(m, dict):
            for version in (m.get('program_version'), m.get('annotation_revision', {}).get('capture_program_version')):
                if isinstance(version, str) and len(version) == 40 and all(c in '0123456789abcdef' for c in version):
                    versions.add(version)
    historical_code = []
    for version in sorted(versions):
        for name in ('collect.py', 'browser.py', 'snapshot.js', 'production_quality.py', 'content_preparation.py', 'content_preparation.js'):
            rel = 'projects/code/webcollect/' + name
            result = subprocess.run(['git', '-C', str(repo), 'show', version + ':' + rel], capture_output=True)
            if result.returncode:
                historical_code.append({'commit': version, 'file': rel, 'status': 'UNAVAILABLE_IN_LOCAL_GIT'})
            else:
                dest = output / 'source-evidence/historical-code' / version / name
                dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(result.stdout)
                historical_code.append({'commit': version, 'file': rel, 'status': 'PRESERVED_FROM_LOCAL_GIT', 'sha256': sha(dest)})
    write(output / 'source-evidence/historical-code-index.json', historical_code)
    write(output / 'state/registry-coverage.json', {'primary': str(registries[0]), 'coverage': coverage,
          'primary_row_counts': {t: len(v) for t, v in rows[0].items()}, 'no_ids_reconstructed': True})
    for src, name, expected_rows in ((registries[0], 'production-registry.sqlite3', rows[0]),
                                     (synthetic, 'synthetic-registry.sqlite3', synth_rows)):
        dest = output / 'state' / name
        with sqlite3.connect(src.resolve().as_uri() + '?mode=ro', uri=True) as source_db:
            with sqlite3.connect(dest) as target_db: source_db.backup(target_db)
        if registry_rows(dest) != expected_rows: raise ValueError('SQLite backup logical rows changed')
    write(output / 'state/registry-sources.json', [{'path': str(p), 'sha256_at_freeze': sha(p),
           'logical_rows': {t: len(v) for t, v in registry_rows(p).items()}} for p in registries + [synthetic]])
    prompt = output / 'ai-review/prompt.txt'; prompt.parent.mkdir(parents=True); prompt.write_text(DELEGATED_PROMPT + '\n')
    write(output / 'ai-review/identity.json', {'reviewer_kind': 'ai', 'reviewer': 'Codex / root/case_semantics',
          'human_review_created': False, 'original_prompt_sha256': sha(prompt), 'review_status': 'NOT_STARTED',
          'historical_model_prompt_status': 'UNKNOWN_UNLESS_PRESENT_IN_PRESERVED_SOURCE_RECORDS',
          'no_historical_prompt_reconstruction': True})
    copy(Path(__file__), Path('preservation-script.py'))
    write(output / 'source-path-map.json', source_index)
    write(output / 'copy-manifest.json', copied)
    write(output / 'unavailable-references.json', unavailable)
    write(output / 'freeze-receipt.json', {'schema_version': 'approved18-frozen-baseline-1',
          'created_at': datetime.now(timezone.utc).isoformat(), 'source_client': str(client),
          'source_evidence': str(evidence), 'selection': {'source': 20, 'selected': 18, 'excluded': 2},
          'selected_sample_ids': sorted(selected_ids), 'frames': sum(len(load(client/'samples'/s/'annotation.json')['steps']) for s in selected_ids),
          'source_to_frozen_files': len(copied), 'source_files_copied_byte_identically': True,
          'real_ledger_complete_coverage_verified': True, 'sqlite_backup_api_used': True,
          'workspace_snapshot': 'workspace-before-change', 'cleanup_performed': False,
          'human_review_export_preserved_unchanged': True, 'new_human_review_created': False,
          'not_a_new_collection': True, 'customer_acceptance': 'UNKNOWN',
          'minimal_scope': 'one client18, original20 reviews, excluded2, selected20 raw, manifests/plans/provenance, before-change code and separate ledgers'})
    sums = {p.relative_to(output).as_posix(): sha(p) for p in output.rglob('*') if p.is_file()}
    (output / 'SHA256SUMS').write_text(''.join(h+'  '+p+'\n' for p,h in sorted(sums.items())))
    print(json.dumps({'baseline': str(output), 'files': len(sums)+1,
                      'bytes': sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),
                      'samples': 18, 'frames': 124, 'registry_coverage': 'PASS'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--output', type=Path, default=Path('results/baselines/approved18-20261024'))
    parser.add_argument('--evidence', type=Path, default=Path('verify_results/client-output-pipeline-20261023/release-run-20261024/evidence.json'))
    parser.add_argument('--prechange', type=Path, default=Path('verify_results/client18-contract-20261024/prechange'))
    parser.add_argument('--client', type=Path, default=Path('results/delivery/20261024-program-client18-v1'))
    args = parser.parse_args(); repo = args.repo.resolve()
    freeze(repo, (repo / args.output).resolve(), (repo / args.evidence).resolve(), (repo / args.prechange).resolve(), (repo / args.client).resolve())
