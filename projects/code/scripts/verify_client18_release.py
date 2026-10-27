#!/usr/bin/env python3
"""Read-only preservation/release verification for the frozen approved18 batch.

The independent QC report owns the contract decision. This script verifies that
the report, preserved source assets/actions, ledger, sealed folder and ZIP all
refer to the same actual release. It does not recollect, repair or relabel data.
"""
import argparse
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import zipfile


METADATA_COLUMNS = ['sample_id', 'site_id', 'site_category', 'app_name', 'task_type',
                    'task_instruction', 'steps', 'screen_resolution',
                    'completion_status', 'actions', 'bytes']
EXPECTED_SAMPLES = 18
EXPECTED_FRAMES = 124
EXPECTED_ALLOCATIONS = 203


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + value)))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative_parts(value, directory=False):
    require(isinstance(value, str) and value and '\\' not in value and '\x00' not in value,
            'Unsafe relative filename: ' + repr(value))
    name = value[:-1] if directory and value.endswith('/') else value
    parts = name.split('/')
    require(not PurePosixPath(name).is_absolute() and
            all(part not in ('', '.', '..') for part in parts) and
            not re.match(r'^[A-Za-z]:', name), 'Escaping or noncanonical path: ' + value)
    return parts


def files(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'Input must be an ordinary directory: ' + str(root))
    values = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Symbolic input is not allowed: ' + str(path))
        require(path.is_file() or path.is_dir(), 'Unsupported filesystem object: ' + str(path))
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            relative_parts(relative)
            values[relative] = digest(path)
    return values


def manifest(root, actual):
    path = root / 'SHA256SUMS'
    declared = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        value, relative = line.split('  ', 1)
        require(re.fullmatch(r'[0-9a-f]{64}', value) is not None, 'Invalid SHA256 digest')
        relative_parts(relative)
        require(relative not in declared and relative != 'SHA256SUMS', 'Duplicate or self-referencing manifest entry: ' + relative)
        declared[relative] = value
    expected = {name: value for name, value in actual.items() if name != 'SHA256SUMS'}
    require(declared == expected, 'SHA256SUMS must match every input file exactly: ' + str(root))
    return {'files': len(actual), 'manifest_entries': len(declared), 'manifest_sha256': digest(path)}


def sample_ids(root):
    container = root / 'samples'
    require(container.is_dir(), 'Missing samples directory: ' + str(root))
    children = list(container.iterdir())
    require(all(path.is_dir() and not path.is_symlink() for path in children), 'Unexpected object in samples/')
    return sorted(path.name for path in children)


def preserved_samples(baseline, package):
    original = baseline / 'client-original'
    expected = sample_ids(original)
    require(len(expected) == EXPECTED_SAMPLES, 'Frozen source must contain exactly 18 cases')
    require(sample_ids(package) == expected, 'Release case IDs differ from the fixed frozen18')
    receipt = read_json(baseline / 'freeze-receipt.json')
    require(receipt['selected_sample_ids'] == expected and receipt['frames'] == EXPECTED_FRAMES,
            'Freeze receipt does not identify the same 18 cases and 124 frames')
    frame_count = tree_count = unchanged_actions = unchanged_tools = 0
    for sid in expected:
        before_root, after_root = original / 'samples' / sid, package / 'samples' / sid
        before, after = read_json(before_root / 'annotation.json'), read_json(after_root / 'annotation.json')
        require(before['sample_id'] == after['sample_id'] == sid, 'Changed internal sample ID: ' + sid)
        require(len(before['steps']) == len(after['steps']), 'Changed step population: ' + sid)
        before_assets = {name: value for name, value in files(before_root).items() if name != 'annotation.json'}
        after_assets = {name: value for name, value in files(after_root).items() if name != 'annotation.json'}
        require(before_assets == after_assets, 'Original PNG/UI-tree bytes changed or assets were added/removed: ' + sid)
        pngs = {name for name in after_assets if name.startswith('images/') and name.endswith('.png')}
        trees = {name for name in after_assets if name.startswith('ui_tree/') and name.endswith('.json')}
        require(set(after_assets) == pngs | trees, 'Unexpected sample asset: ' + sid)
        require(len(pngs) == len(trees) == len(after['steps']), 'Step/image/tree counts differ: ' + sid)
        for old, new in zip(before['steps'], after['steps']):
            identity = ('step_id', 'image_path', 'ui_tree_path')
            require(canonical({key: old[key] for key in identity}) == canonical({key: new[key] for key in identity}),
                    'Changed step ordering or file references: ' + sid)
            require(canonical(old['tool_call']) == canonical(new['tool_call']), 'Executed tool record changed: ' + sid)
            old_action = {key: value for key, value in old['action'].items() if key not in ('precondition', 'expected_result')}
            new_action = {key: value for key, value in new['action'].items() if key not in ('precondition', 'expected_result')}
            require(canonical(old_action) == canonical(new_action), 'Actual action or target truth changed: ' + sid)
            unchanged_actions += 1; unchanged_tools += 1
        # True control truth is preserved outside samples as required by the batch.
        require(digest(original / 'ground_truth' / (sid + '.json')) == digest(package / 'ground_truth' / (sid + '.json')),
                'Original target truth archive changed: ' + sid)
        frame_count += len(pngs); tree_count += len(trees)
    require(frame_count == tree_count == EXPECTED_FRAMES, 'Expected 124 original PNGs and 124 original synchronized trees')
    return {'sample_ids': expected, 'samples': len(expected), 'png': frame_count, 'ui_tree': tree_count,
            'byte_identical_png_and_trees': True, 'unchanged_action_records': unchanged_actions,
            'unchanged_tool_calls': unchanged_tools, 'unchanged_ground_truth_files': len(expected)}


def metadata(package):
    with (package / 'metadata.csv').open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == METADATA_COLUMNS, 'metadata.csv must have the documented 11 columns in order')
        rows = list(reader)
    expected_ids = sample_ids(package)
    require(len(rows) == EXPECTED_SAMPLES and sorted(row['sample_id'] for row in rows) == expected_ids,
            'metadata.csv must identify each of the same 18 samples exactly once')
    source = read_json(package / 'site-list.json')
    sites = {row['site_id']: row for row in source['sites']}
    assignments = {row['sample_id']: row['site_id'] for row in source['samples']}
    total_steps = 0
    for row in rows:
        sid = row['sample_id']; path = package / 'samples' / sid; data = read_json(path / 'annotation.json')
        site = sites[assignments[sid]]
        expected = {'sample_id': sid, 'site_id': assignments[sid], 'site_category': site['site_category'],
                    'app_name': data['app_info']['app_name'], 'task_instruction': data['task_instruction'],
                    'steps': str(len(data['steps'])), 'completion_status': data['completion_status'],
                    'bytes': str(sum(child.stat().st_size for child in path.rglob('*') if child.is_file()))}
        for key, value in expected.items():
            require(row[key] == value, 'metadata value differs from actual sample: ' + sid + '/' + key)
        for key, value in [('task_type', data['task_type']), ('screen_resolution', data['device_info']['screen_resolution']),
                           ('actions', [step['action']['action_type'] for step in data['steps']])]:
            require(canonical(json.loads(row[key])) == canonical(value), 'metadata array differs: ' + sid + '/' + key)
        total_steps += len(data['steps'])
    require(total_steps == EXPECTED_FRAMES, 'metadata steps must total 124')
    return {'columns': len(METADATA_COLUMNS), 'rows': len(rows), 'steps': total_steps}


def bound_qc(package, path, actual):
    report = read_json(path)
    require(report.get('program') == 'quality-inspector' and report.get('scope') == 'delivery', 'Not an independent delivery QC report')
    require(report.get('inspection_stage') == 'final' and report.get('release_ready') is True, 'QC has not approved a final sealed release')
    for field in ('status', 'delivery_status', 'contract_status', 'local_acceptance_status'):
        require(report.get(field) == 'PASS', 'QC field is not PASS: ' + field)
    require(Path(report['dataset']).resolve() == package, 'QC inspected a different directory')
    require(report.get('input_files_sha256') == actual, 'QC file bindings are stale or incomplete')
    require(report.get('input_integrity', {}).get('status') == 'PASS' and report.get('root_checksum', {}).get('pass') is True,
            'QC did not establish sealed input integrity')
    require(report.get('sample_count') == EXPECTED_SAMPLES and report.get('local_sample_status_counts') == {'PASS': EXPECTED_SAMPLES},
            'QC does not report exactly 18 sample passes')
    expected_ids = sample_ids(package); rows = report['samples']
    require(len(rows) == EXPECTED_SAMPLES and sorted(row['sample_id'] for row in rows) == expected_ids, 'QC sample IDs differ')
    for row in rows:
        sid = row['sample_id']; sample = package / 'samples' / sid
        require(Path(row['sample_path']).resolve() == sample, 'QC sample path differs: ' + sid)
        require(row['annotation_sha256'] == digest(sample / 'annotation.json'), 'QC annotation binding differs: ' + sid)
        expected = {name: value for name, value in files(sample).items() if name != 'annotation.json'}
        require(row['evidence_sha256'] == expected, 'QC evidence binding differs: ' + sid)
    return {'scope': 'delivery', 'inspection_stage': 'final', 'release_ready': True,
            'sample_passes': EXPECTED_SAMPLES, 'report_sha256': digest(path), 'dataset': str(package)}


def registry(baseline):
    path = baseline / 'state/production-registry.sqlite3'
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as con:
        integrity = con.execute('PRAGMA integrity_check').fetchall()
        require(integrity == [('ok',)], 'Frozen production registry integrity_check failed')
        sites = con.execute('SELECT id,uri,category,kind,next_sample FROM sites').fetchall()
        batches = con.execute('SELECT id,kind FROM batches').fetchall()
        allocations = con.execute('SELECT sample_id,site_id,batch_id FROM allocations').fetchall()
    require(len(allocations) == EXPECTED_ALLOCATIONS, 'The complete 203-allocation production ledger was not retained')
    require(len(sites) == 19 and len(batches) == 34, 'Frozen production site/batch ledger population differs')
    require(all(row[3] == 'real' for row in sites) and all(row[1] == 'real' for row in batches), 'Synthetic and real numbering namespaces are mixed')
    counters = {'S' + str(row[0]).zfill(6): row[4] for row in sites}; batch_ids = {row[0] for row in batches}
    for sid, site, batch in allocations:
        match = re.fullmatch(r'(S\d{6})_sample_(\d{6,})', sid)
        require(match is not None and match.group(1) == site and site in counters and batch in batch_ids, 'Invalid preserved allocation: ' + sid)
        require(type(counters[site]) is int and counters[site] > int(match.group(2)), 'Next-sample counter can reuse an allocated ID: ' + sid)
    require(set(sample_ids(baseline / 'client-original')) <= {row[0] for row in allocations}, 'Approved case IDs are missing from the global ledger')
    coverage = read_json(baseline / 'state/registry-coverage.json')
    require(coverage['primary_row_counts'] == {'sites': 19, 'batches': 34, 'allocations': EXPECTED_ALLOCATIONS}, 'Ledger preservation receipt differs')
    require(all(row['site_identity_and_counter_coverage'] is True and not any(row['missing_rows'].values()) for row in coverage['coverage']),
            'Other historical real ledgers were not fully covered')
    synthetic = baseline / 'state/synthetic-registry.sqlite3'
    with closing(sqlite3.connect(synthetic.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as con:
        require(con.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'Frozen synthetic registry integrity_check failed')
        kinds = {row[0] for row in con.execute('SELECT kind FROM sites')}
        require(kinds == {'integration'}, 'Synthetic numbering state contains a real site')
    return {'sqlite_integrity': 'ok', 'sites': len(sites), 'batches': len(batches), 'allocations': len(allocations),
            'counter_reuse_prevented': True, 'sha256': digest(path), 'synthetic_registry_integrity': 'ok',
            'synthetic_registry_sha256': digest(synthetic)}


def archive(package, path, actual):
    expected = {package.name + '/' + name: value for name, value in actual.items()}
    directories = {package.name} | {package.name + '/' + p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_dir()}
    seen = set(); members = {}; directory_count = 0
    with zipfile.ZipFile(path, 'r') as zipped:
        for info in zipped.infolist():
            parts = relative_parts(info.filename, directory=info.is_dir())
            require(parts[0] == package.name, 'ZIP contains a different or additional root directory')
            require(info.filename not in seen, 'ZIP contains a duplicate member: ' + info.filename)
            seen.add(info.filename)
            require(stat.S_IFMT(info.external_attr >> 16) != stat.S_IFLNK, 'ZIP symlink is forbidden')
            if info.is_dir():
                require('/'.join(parts) in directories, 'ZIP contains an extra directory: ' + info.filename)
                directory_count += 1; continue
            require(info.filename in expected and len(parts) > 1, 'ZIP contains an extra or unrooted file: ' + info.filename)
            relative = '/'.join(parts[1:])
            require(info.file_size == (package / relative).stat().st_size, 'ZIP member size differs: ' + info.filename)
            h = hashlib.sha256()
            with zipped.open(info, 'r') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):h.update(block)
            require(h.hexdigest() == expected[info.filename], 'ZIP member bytes differ: ' + info.filename)
            members[info.filename] = h.hexdigest()
    require(members == expected, 'ZIP is missing delivered files')
    return {'root': package.name, 'file_members': len(members), 'directory_members': directory_count,
            'every_member_byte_identical': True, 'sha256': digest(path), 'bytes': path.stat().st_size}


def verify_release(baseline, package, qc_report, zip_path):
    baseline, package, qc_report, zip_path = (Path(value).resolve() for value in (baseline, package, qc_report, zip_path))
    result = {'schema_version': 'webcollect-client18-release-verification-1',
              'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'FAIL',
              'baseline': str(baseline), 'package': str(package), 'qc_report': str(qc_report), 'archive': str(zip_path),
              'qc_report_sha256': digest(qc_report) if qc_report.is_file() else None,
              'archive_sha256': digest(zip_path) if zip_path.is_file() else None,
              'inputs_read_only': True, 'checks': {}, 'errors': []}
    baseline_files = {}; package_files = {}
    def check(name, operation):
        try:
            value = operation(); result['checks'][name] = {'status': 'PASS', **value}; return value
        except Exception as error:
            result['checks'][name] = {'status': 'FAIL', 'error': str(error)}
            result['errors'].append({'check': name, 'error': str(error)}); return None
    scanned = check('baseline_files', lambda: {'hashes': files(baseline)})
    if scanned is not None:
        baseline_files = scanned['hashes']; result['checks']['baseline_files'] = {'status': 'PASS', 'count': len(baseline_files)}
        check('baseline_manifest', lambda: manifest(baseline, baseline_files))
    scanned = check('package_files', lambda: {'hashes': files(package)})
    if scanned is not None:
        package_files = scanned['hashes']; result['checks']['package_files'] = {'status': 'PASS', 'count': len(package_files)}
        check('package_manifest', lambda: manifest(package, package_files))
    check('preserved_samples', lambda: preserved_samples(baseline, package))
    check('metadata', lambda: metadata(package))
    check('final_qc_binding', lambda: bound_qc(package, qc_report, package_files))
    check('production_registry', lambda: registry(baseline))
    check('archive', lambda: archive(package, zip_path, package_files))
    def unchanged():
        require(files(baseline) == baseline_files and files(package) == package_files, 'Directory inputs changed during release verification')
        require(digest(qc_report) == result['qc_report_sha256'] and digest(zip_path) == result['archive_sha256'], 'Report/archive inputs changed during verification')
        return {'checked_before_and_after': True}
    check('read_only_input_integrity', unchanged)
    result['status'] = 'FAIL' if result['errors'] else 'PASS'
    result['statistics'] = {name: row for name, row in result['checks'].items() if name in ('preserved_samples', 'metadata', 'production_registry', 'archive')}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'package', 'qc-report', 'archive', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(argv); output = args.output.resolve()
    try:
        require(not output.exists(), 'Refuse to overwrite an existing verification receipt')
        for root in (args.baseline.resolve(), args.package.resolve()):
            require(not output.is_relative_to(root), 'Verification receipt must stay outside read-only input directories')
        require(output not in (args.qc_report.resolve(), args.archive.resolve()), 'Receipt must not overwrite an input')
        report = verify_release(args.baseline, args.package, args.qc_report, args.archive)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as stream:json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
        print(json.dumps({'status': report['status'], 'package': report['package'], 'baseline': report['baseline'],
                          'output': str(output), 'errors': report['errors']}, ensure_ascii=False))
        return 0 if report['status'] == 'PASS' else 1
    except Exception as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error), 'output': str(output)}, ensure_ascii=False)); return 1


if __name__ == '__main__':raise SystemExit(main())
