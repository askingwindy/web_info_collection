"""Optional, hash-bound capture sidecar. Never changes customer file identities."""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence_hashes(sample):
    sample = Path(sample)
    annotation = json.loads((sample / 'annotation.json').read_text())
    result = {}
    for step in annotation.get('steps', []):
        for field in ['image_path', 'ui_tree_path']:
            relative = step.get(field)
            if not isinstance(relative, str) or not relative:
                continue
            path = sample / relative
            if Path(relative).is_absolute() or not path.resolve().is_relative_to(sample.resolve()):
                raise ValueError('Sample evidence path escapes sample')
            if path.is_symlink() or not path.is_file():
                raise ValueError('Missing/symlink sample evidence: ' + relative)
            result[relative] = sha(path)
    return result


def _path(value, parent):
    if not isinstance(value, str) or not value:
        raise ValueError('External source path is absent')
    path = Path(value)
    return (parent / path).resolve() if not path.is_absolute() else path.resolve()


def load(index, layout):
    """Validate customer bytes before granting access to any external raw state.

    A correct sample binding alone does not authenticate mutable capture logs:
    the separate manifest and complete raw file hash sets must also match.
    """
    result = {'status': 'NOT_SUPPLIED', 'path': None, 'sha256': None,
              'errors': [], 'samples': {}, 'not_visual_acceptance': True}
    if index is None:
        return result
    path = Path(index).resolve()
    result.update(path=str(path), status='PASS')
    try:
        result['sha256'] = sha(path)
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get('schema_version') not in ('client-evidence', 'client-evidence'):
            raise ValueError('Unsupported external evidence schema')
        if not isinstance(data.get('samples'), list):
            raise ValueError('External evidence samples must be an array')
    except (OSError, ValueError, TypeError) as error:
        result.update(status='FAIL', errors=[str(error)])
        return result
    byid = {}
    for sample in layout.samples:
        try:
            value = json.loads((sample / 'annotation.json').read_text())
            sid = value['sample_id']
            if sid in byid:
                raise ValueError('Duplicate customer sample ID')
            byid[sid] = sample
        except (OSError, ValueError, TypeError, KeyError) as error:
            result['errors'].append(str(sample) + ': ' + str(error))
    seen = set()
    for record in data['samples']:
        sid = record.get('sample_id') if isinstance(record, dict) else None
        entry = {'status': 'FAIL', 'issues': [], 'evidence_dir': None, 'manifest_path': None}
        try:
            if sid not in byid or sid in seen:
                raise ValueError('Unknown/duplicate external sample ID: ' + str(sid))
            seen.add(sid)
            sample = byid[sid]
            current = evidence_hashes(sample)
            if record.get('annotation_sha256') != sha(sample / 'annotation.json'):
                raise ValueError('External index annotation hash differs from customer sample')
            if record.get('evidence_sha256') != current:
                raise ValueError('External index image/tree hash set differs from customer sample')
            source = _path(record.get('source_sample_path'), path.parent)
            if sha(source / 'annotation.json') != record['annotation_sha256'] or evidence_hashes(source) != current:
                raise ValueError('External source sample bytes differ from customer sample')
            truth = layout.ground_truth(sample)
            if record.get('ground_truth_sha256') is not None and (
                    not truth.is_file() or sha(truth) != record['ground_truth_sha256']):
                raise ValueError('External index ground truth hash differs from customer file')
            if (record.get('machine_evidence_status') == 'UNAVAILABLE' and
                    record.get('source_manifest_path') is None and
                    record.get('source_manifest_sha256') is None and
                    record.get('raw_evidence_files_sha256') == {}):
                entry.update(status='REVIEW_REQUIRED', source_sample_path=str(source), sample_binding_valid=True,
                             issues=['Customer/source sample hashes match, but original manifest/raw evidence is explicitly unavailable'])
                result['samples'][sid] = entry
                continue
            batch = _path(record.get('source_batch_path'), path.parent)
            if source.parent != batch / 'samples':
                raise ValueError('Source sample is not inside the declared batch samples/')
            manifest = _path(record.get('source_manifest_path'), path.parent)
            if manifest != batch / 'manifest.json' or record.get('source_manifest_sha256') != sha(manifest):
                raise ValueError('Missing/stale source manifest hash binding')
            manifest_data = json.loads(manifest.read_text())
            if not isinstance(manifest_data, dict):
                raise ValueError('Source manifest must be an object')
            evidence_dir = batch / 'evidence' / source.name
            actual = {p.relative_to(batch).as_posix(): sha(p)
                      for p in sorted(evidence_dir.rglob('*')) if p.is_file()}
            declared = record.get('raw_evidence_files_sha256')
            if not isinstance(declared, dict) or not declared or declared != actual:
                raise ValueError('Missing/incomplete/stale external raw evidence hash set')
            if evidence_dir.is_symlink() or any(p.is_symlink() for p in evidence_dir.rglob('*')):
                raise ValueError('External raw evidence contains a symlink')
            if not any(Path(relative).name.startswith('step_') for relative in actual):
                raise ValueError('External evidence has no raw step records')
            for relative in actual:
                if Path(relative).name.startswith('step_') and Path(relative).suffix == '.json':
                    captured = json.loads((batch / relative).read_text())
                    if not isinstance(captured, dict):
                        raise ValueError('External raw step must be a JSON object: ' + relative)
            entry.update(status='PASS', evidence_dir=str(evidence_dir), manifest_path=str(manifest),
                         source_sample_path=str(source), source_batch_path=str(batch),
                         source_manifest_sha256=record['source_manifest_sha256'],
                         raw_evidence_files_sha256=actual)
        except (OSError, ValueError, TypeError, KeyError) as error:
            entry['issues'].append(str(error))
            result['errors'].append({'sample_id': sid, 'reason': str(error)})
        if sid is not None:
            result['samples'][sid] = entry
    for sid in byid.keys() - seen:
        result['samples'][sid] = {'status': 'REVIEW_REQUIRED', 'issues': ['No external evidence record for customer sample'],
                                  'evidence_dir': None, 'manifest_path': None}
    if result['errors']:
        result['status'] = 'FAIL'
    elif any(row['status'] != 'PASS' for row in result['samples'].values()):
        result['status'] = 'REVIEW_REQUIRED'
    return result


def context(layout, sample, external):
    """Return only validated external paths, or legacy package-native paths."""
    sample = Path(sample)
    annotation = json.loads((sample / 'annotation.json').read_text())
    sid = annotation.get('sample_id')
    if external['path'] is not None:
        return external['samples'].get(sid, {'status': 'FAIL' if external['status'] == 'FAIL' else 'REVIEW_REQUIRED',
                                            'issues': external['errors'], 'evidence_dir': None, 'manifest_path': None})
    if layout.kind == 'customer-flat':
        return {'status': 'REVIEW_REQUIRED', 'issues': ['Customer package has no external capture evidence index'],
                'evidence_dir': None, 'manifest_path': None}
    return {'status': 'LEGACY_NATIVE', 'issues': [], 'evidence_dir': str(layout.native_evidence(sample)),
            'manifest_path': str(layout.batch_for(sample) / 'manifest.json')}
