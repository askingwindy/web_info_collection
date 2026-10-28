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


def migration_template(source_reviews, samples, target_contract):
    """Produce pending assessments only; unchanged hashes are eligibility facts."""
    source = Path(source_reviews).resolve(); raw = read(source)
    if not isinstance(raw, dict) or not isinstance(raw.get('records'), list):
        raise ValueError('Source review must contain records')
    byid = {}
    for row in raw['records']:
        if (not isinstance(row, dict) or not isinstance(row.get('sample_id'), str)
                or not row['sample_id'] or row['sample_id'] in byid):
            raise ValueError('Source review has malformed or duplicate sample IDs')
        byid[row['sample_id']] = row
    rows = []
    for sample in samples:
        sid = sample['sample_id']; record = byid.get(sid)
        if not record:
            continue
        root = Path(sample['sample_path'])
        rows.append({'sample_id': sid, 'source_record_sha256': record_hash(record),
                     'source_contract_sha256': record.get('baseline_sha256'),
                     'decision': 'REVIEW_REQUIRED', 'reason': '',
                     'authority_and_semantic_rule_assessment': '',
                     'assessor': {'kind': '', 'name': ''},
                     'eligibility': {'annotation_unchanged': record.get('annotation_sha256') == sha(root / 'annotation.json'),
                                     'evidence_unchanged': record.get('evidence_sha256') == evidence_files(root)},
                     'not_a_new_visual_review': True})
    return {'schema_version': 'qc-review-migration-1',
            'target_contract_sha256': target_contract,
            'source_review': {'path': str(source), 'sha256': sha(source)},
            'decisions': rows, 'identity_authenticated': False,
            'note': 'Pending impact assessments. Never replace old review hashes or claim new visual approval.'}


def intake(path, samples, contract_hash, migration=None):
    records = {}; errors = []; migrations = []
    if not path:
        return records, errors, migrations
    try:
        data = read(path)
    except (OSError, ValueError, UnicodeError) as error:
        return {}, [{'reason': 'Cannot read review: ' + str(error)}], []
    if not isinstance(data, dict) or data.get('schema_version') not in ('qc-review-1', 'qc-review-2') or not isinstance(data.get('records'), list):
        return {}, [{'reason': 'Expected qc-review-2 records or explicitly migrated qc-review-1'}], []
    assessments = {}
    if migration:
        try:
            value = read(migration)
            if not isinstance(value, dict) or value.get('schema_version') != 'qc-review-migration-1':
                raise ValueError('Unsupported review migration')
            if value.get('target_contract_sha256') != contract_hash:
                raise ValueError('Migration targets a different contract')
            source = value.get('source_review', {})
            if not isinstance(source, dict) or not isinstance(source.get('path'), str):
                raise ValueError('Migration source review must bind a path and hash')
            source_path = Path(source.get('path', ''))
            if not source_path.is_absolute():
                source_path = Path(migration).resolve().parent / source_path
            if source_path.resolve() != Path(path).resolve() or source.get('sha256') != sha(path):
                raise ValueError('Migration does not bind the supplied immutable source review')
            decisions = value.get('decisions')
            if not isinstance(decisions, list):
                raise ValueError('Migration decisions must be an array')
            for item in decisions:
                if (not isinstance(item, dict) or not isinstance(item.get('sample_id'), str)
                        or not item['sample_id'] or item['sample_id'] in assessments):
                    raise ValueError('Duplicate or malformed migration decision')
                assessments[item['sample_id']] = item
        except (OSError, ValueError, TypeError, KeyError) as error:
            return {}, [{'reason': str(error)}], []
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
            why += coverage_errors(record, annotation, strict=data['schema_version'] == 'qc-review-2')
        except (OSError, ValueError, TypeError, KeyError) as error:
            why.append('Cannot bind review evidence: ' + str(error))
        from .semantic import invalidate_record
        try:
            current_record = invalidate_record(record)
        except ValueError as error:
            why.append(str(error)); current_record = record
        modern = data['schema_version'] == 'qc-review-2' and 'semantic_rule_ids' in record
        # Without per-check identities an old v2 record cannot prove which
        # semantic rules it reviewed, even when the mechanical contract agrees.
        legacy = not modern
        assessment = assessments.get(sid)
        if legacy:
            if not assessment or assessment.get('decision') != 'inherit_unchanged':
                why.append('legacy/different contract needs explicit completed migration assessment')
            else:
                assessor = assessment.get('assessor', {})
                if assessment.get('source_record_sha256') != record_hash(record) or assessment.get('source_contract_sha256') != record.get('baseline_sha256'):
                    why.append('migration does not bind the unchanged source record and contract')
                if not isinstance(assessor, dict) or assessor.get('kind') not in ('ai', 'human') or not isinstance(assessor.get('name'), str) or not assessor['name'].strip():
                    why.append('migration needs actual impact assessor identity; not authenticated')
                for key in ('reason', 'authority_and_semantic_rule_assessment'):
                    if not isinstance(assessment.get(key), str) or not assessment[key].strip():
                        why.append('migration needs explicit ' + key)
                if assessment.get('not_a_new_visual_review') is not True:
                    why.append('migration must explicitly preserve the original review provenance')
        if why:
            errors.append({'sample_id': sid, 'reason': '; '.join(why)}); continue
        records[sid] = current_record  # Derived states never rewrite the source review.
        if legacy:
            migrations.append({'sample_id': sid, 'source_record_sha256': record_hash(record),
                               'source_review_sha256': sha(path), 'migration_sha256': sha(migration),
                               'assessment': assessment, 'new_visual_review_claimed': False})
    return records, errors, migrations
