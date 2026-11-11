"""Review-record validation, never evidence that a person or AI actually read pixels.

Legacy decisions are immutable. A separately authored migration assessment may
reference an unchanged legacy record; this module never manufactures assessment.
"""
import hashlib
import json
from pathlib import Path

SEMANTIC = ['visual_alignment', 'terminal_semantics', 'language', 'privacy', 'substantive_difference']
STATES = {'PASS', 'FAIL', 'REVIEW_REQUIRED'}
REVIEW_POLICY = {
    'version': 'whole-trajectory-review-4',
    'required_checks': SEMANTIC,
    'coverage': 'exactly one observation per actual step and complete frames_viewed; explicit human ok decisions may omit written notes, other observations require nonempty notes',
    'decisions': 'resolved checks cite actual step IDs; all five must resolve before release; explicit human PASS may omit a written reason, FAIL and AI decisions require written reasons',
    'identity_authenticated': False, 'actual_reading_authenticated': False,
    'legacy': 'explicit hash-bound unchanged-record migration assessment only',
}


def decision_note_valid(result, reviewer):
    """A human's explicit PASS needs no manufactured prose; preserve all notes."""
    note = result.get('note')
    return (isinstance(note, str) and
            (result.get('status') == 'REVIEW_REQUIRED' or bool(note.strip()) or
             (isinstance(reviewer, dict) and reviewer.get('kind') == 'human'
              and result.get('status') == 'PASS')))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record_hash(record):
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def evidence_files(sample):
    root = Path(sample).resolve()
    annotation = read(root / 'annotation.json')
    result = {}
    for step in annotation['steps']:
        for key in ('image_path', 'ui_tree_path'):
            relative = step[key]
            path = root / relative
            if Path(relative).is_absolute() or not path.resolve().is_relative_to(root) or path.is_symlink():
                raise ValueError('Review evidence escapes sample or is a symlink')
            result[relative] = sha(path)
    return result


def coverage_errors(record, annotation, strict=True):
    errors = []
    steps = [row['step_id'] for row in annotation['steps']]
    resolved = any(isinstance(value, dict) and value.get('status') in ('PASS', 'FAIL')
                   for value in record.get('checks', {}).values())
    if not resolved:
        return errors  # An untouched pending template does not assert any review.
    viewed = record.get('provenance', {}).get('frames_viewed')
    if (not isinstance(viewed, list) or any(type(value) is not int for value in viewed)
            or len(viewed) != len(steps) or set(viewed) != set(steps)):
        errors.append('frames_viewed must cover each actual step exactly once')
    observations = record.get('step_observations')
    step_paths = {step['step_id']: {step['image_path'], step['ui_tree_path']} for step in annotation['steps']}
    if not isinstance(observations, list):
        errors.append('step_observations must cover every actual step')
    else:
        ids = []
        for item in observations:
            if not isinstance(item, dict):
                errors.append('step observation must be an object'); continue
            ids.append(item.get('step_id'))
            reviewer = record.get('reviewer')
            human_confirmation = (isinstance(reviewer, dict) and reviewer.get('kind') == 'human'
                                  and item.get('decision') == 'ok')
            # A person's explicit normal-step decision is itself the observation.
            # Do not manufacture prose for it or relax written AI observations.
            note = item.get('note')
            if (type(item.get('step_id')) is not int or not isinstance(note, str)
                    or (not note.strip() and not human_confirmation)):
                errors.append('step observation needs an integer step_id and nonempty note unless a human explicitly chose ok')
            references = item.get('evidence', [])
            if not isinstance(references, list):
                errors.append('step observation evidence must be a list'); continue
            for reference in references:
                if (not isinstance(reference, dict) or not isinstance(reference.get('path'), str)
                        or reference['path'] not in record.get('evidence_sha256', {})):
                    errors.append('observation references unbound evidence')
                elif reference.get('sha256') != record['evidence_sha256'][reference['path']]:
                    errors.append('observation references stale evidence')
                elif type(item.get('step_id')) is int and reference['path'] not in step_paths.get(item['step_id'], set()):
                    errors.append('observation references evidence from another step')
        if len(ids) != len(steps) or any(type(value) is not int for value in ids) or set(ids) != set(steps):
            errors.append('step observations must cover each actual step exactly once')
    for name, check in record.get('checks', {}).items():
        if not isinstance(check, dict):
            continue
        refs = check.get('evidence_steps')
        if strict or refs is not None:
            if (not isinstance(refs, list) or any(type(value) is not int or value not in steps for value in refs)
                    or len(refs) != len(set(refs))
                    or (check.get('status') in ('PASS', 'FAIL') and not refs)):
                errors.append('check needs valid, unique evidence_steps: ' + name)
    return errors


def intake(path, samples, contract_hash):
    """Import actual review records; no migration path in the no-version mode.

    Sealed historical records keep their original qc-review / qc-review-1 /
    qc-review-2 schema names and import directly; their bytes are never
    rewritten and no assessment is manufactured here.
    """
    records = {}; errors = []; migrations = []
    if not path:
        return records, errors, migrations
    try:
        data = read(path)
    except (OSError, ValueError, UnicodeError) as error:
        return {}, [{'reason': 'Cannot read review: ' + str(error)}], []
    if not isinstance(data, dict) or data.get('schema_version') not in ('qc-review', 'qc-review-1', 'qc-review-2') or not isinstance(data.get('records'), list):
        return {}, [{'reason': 'Expected qc-review records (historical qc-review-1/-2 accepted unchanged)'}], []
    byid = {row['sample_id']: row for row in samples if row.get('sample_id')}
    seen = set()
    for record in data['records']:
        if not isinstance(record, dict):
            errors.append({'reason': 'review record must be an object'}); continue
        sid = record.get('sample_id'); why = []
        if not isinstance(sid, str) or sid not in byid:
            errors.append({'sample_id': sid, 'reason': 'unknown sample'}); continue
        if sid in seen:
            errors.append({'sample_id': sid, 'reason': 'duplicate review record'}); records.pop(sid, None); continue
        seen.add(sid)
        root = Path(byid[sid]['sample_path'])
        reviewer = record.get('reviewer'); checks = record.get('checks'); provenance = record.get('provenance')
        if not isinstance(reviewer, dict) or not isinstance(checks, dict) or not isinstance(provenance, dict):
            errors.append({'sample_id': sid, 'reason': 'reviewer/checks/provenance must be objects'}); continue
        if reviewer.get('kind') not in ('ai', 'human') or not isinstance(reviewer.get('name'), str) or not reviewer['name'].strip():
            why.append('actual reviewer kind/name required; identity not authenticated')
        if set(checks) != set(SEMANTIC):
            why.append('all five semantic checks must be present; pending values are allowed')
        for name, result in checks.items():
            if not isinstance(result, dict) or result.get('status') not in STATES:
                why.append('invalid semantic decision ' + name)
            elif result['status'] in ('PASS', 'FAIL') and not decision_note_valid(result, reviewer):
                why.append('actual evidence reasoning required ' + name)
        if not isinstance(provenance.get('description'), str) or not provenance['description'].strip():
            why.append('actual source/provenance description required')
        try:
            annotation = read(root / 'annotation.json')
            if record.get('annotation_sha256') != sha(root / 'annotation.json'):
                why.append('stale/different annotation; changed annotations require a new actual review')
            if record.get('evidence_sha256') != evidence_files(root):
                why.append('incomplete/stale image or tree evidence')
            why += coverage_errors(record, annotation, strict=data['schema_version'] in ('qc-review', 'qc-review-2'))
        except (OSError, ValueError, TypeError, KeyError) as error:
            why.append('Cannot bind review evidence: ' + str(error))
        if why:
            errors.append({'sample_id': sid, 'reason': '; '.join(why)}); continue
        records[sid] = record  # Source review bytes are never rewritten.
    return records, errors, []
