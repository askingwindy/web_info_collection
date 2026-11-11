"""Import only the fifth semantic check for an exact merged population.

Original visual decisions are not input to, or rewritten by, this module. Human
records use the existing evidence/coverage validator. AI records are deliberately
unsupported here until a real request/result trace can be validated; a bare AI
PASS is not an alternative to that trace. No model or human service is called.
"""
from copy import deepcopy
from pathlib import Path
import json

from .contract import fingerprint
from .reporting import review_template as existing_template
from .profiles import package_files
from .reviews import evidence_files, intake, record_hash, sha
from .semantic import digest

CHECK = 'substantive_difference'
SCOPE_VERSION = 'qc-global-difference-scope-1'


def _real_path(value):
    path = Path(value).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Global comparison evidence cannot contain symlink paths')
    return path.resolve()


def _population(samples):
    rows = []; seen = set()
    for item in samples:
        sid = item.get('sample_id')
        if not isinstance(sid, str) or not sid or sid in seen:
            raise ValueError('Global comparison requires unique nonempty effective sample IDs')
        seen.add(sid)
        root = _real_path(item['sample_path']) if item.get('sample_path') else _real_path(item['annotation_path']).parent
        # Validate every child before following annotation or evidence paths;
        # evidence_files alone cannot reject a symlinked parent directory.
        package_files(root)
        path = root / 'annotation.json'; annotation = json.loads(path.read_text())
        if annotation.get('sample_id') != sid or root.name != sid:
            raise ValueError('Global comparison sample identity differs from its actual annotation')
        hashes = evidence_files(root); annotation_hash = sha(path)
        if (item.get('annotation_sha256', annotation_hash) != annotation_hash
                or item.get('evidence_sha256', hashes) != hashes):
            raise ValueError('Global comparison sample evidence changed')
        rows.append({'sample_id': sid, 'sample_path': str(root),
                     'annotation_sha256': annotation_hash, 'evidence_sha256': hashes})
    rows.sort(key=lambda item: item['sample_id'])
    members = [{key: deepcopy(row[key]) for key in ('sample_id', 'annotation_sha256', 'evidence_sha256')} for row in rows]
    return rows, {'population_sha256': digest({'schema_version': 'qc-global-population-1', 'samples': members}),
                  'members': members}


def population_binding(samples):
    """Content identity is independent of machine paths and transport copies."""
    return _population(samples)[1]


def _scope(population):
    return {'schema_version': SCOPE_VERSION, 'population_sha256': population['population_sha256'],
            'only_check_consumed': CHECK, 'rule_id': CHECK}


def _scope_matches(header, expected):
    """Current scope carries rule_id; sealed legacy scopes without it stay valid."""
    legacy = {key: expected[key] for key in ('schema_version', 'population_sha256', 'only_check_consumed')}
    return header == expected or header == legacy


def _selection(rows, population, sampling_plan, source_reports):
    """Reuse an explicit frozen policy; never choose new production ratios."""
    required = {row['sample_id'] for row in rows}
    if sampling_plan is None:
        return required, None
    from .delivery_sampling import verify
    from .profiles import package_files
    reference = _reference(sampling_plan)
    plan = verify(reference['path'])
    slots = {slot['current']['sample_id']: slot for slot in plan['slots']}
    if set(slots) != required or len(slots) != len(plan['slots']):
        raise ValueError('Global sampling plan must freeze the exact complete population')
    required = set()
    for row in rows:
        slot = slots[row['sample_id']]; current = slot['current']
        if (current['annotation_sha256'] != row['annotation_sha256']
                or current['evidence_sha256'] != row['evidence_sha256']
                or current['files_sha256'] != package_files(row['sample_path'])):
            raise ValueError('Global sampling plan evidence differs from the comparison population')
        if slot['ai_selected'] or slot['human_selected'] or slot['replacement_history']:
            required.add(row['sample_id'])
    if not source_reports:
        raise ValueError('Global sampling requires original QC reports to preserve AI escalations')
    covered = set(); references = []; originals = {row['sample_id']: row for row in rows}
    known = set(slots)
    for supplied in source_reports:
        source = _reference(supplied); report = json.loads(Path(source['path']).read_text())
        if report.get('program') != 'quality-inspector':
            raise ValueError('Original global-sampling QC report has stale semantic rules')
        for sample in report.get('samples', []):
            if sample.get('sample_id') in known:
                if sample.get('status') != 'PASS':
                    raise ValueError('Original sample quality issues must be resolved before global sampling')
                if any(sample.get(key) != originals[sample['sample_id']][key]
                       for key in ('annotation_sha256', 'evidence_sha256')):
                    raise ValueError('Original QC report sample bytes differ from the global population')
                covered.add(sample['sample_id'])
        for item in (report.get('semantic_sampling') or {}).get('rows', []):
            sid = item.get('sample_id')
            issue = item.get('ai_status') not in (None, 'PASS', 'NOT_SELECTED', 'NOT_REVIEWED')
            escalation = item.get('human_required') and not item.get('human_random_selected')
            if sid in known and (issue or escalation or item.get('replacement')):
                required.add(sid)
        references.append(source)
    if covered != known:
        raise ValueError('Original QC reports do not cover the exact global population')
    return required, {'sampling_plan': reference, 'plan_sha256': plan['plan_sha256'],
        'policy': deepcopy(plan['policy']), 'source_reports': references,
        'population_sha256': population['population_sha256'],
        'required_sample_ids': sorted(required), 'unselected_is_semantic_pass': False}


def review_template(samples, *, sampling_plan=None, source_reports=()):
    """Blank existing-format records; only the fifth decision will be consumed.

    Unreviewed records may be omitted from an actual export. Missing decisions
    remain pending. The other four fields remain blank compatibility fields,
    never a request to review or relabel the original visual judgments.
    """
    rows, population = _population(samples)
    required, policy = _selection(rows, population, sampling_plan, source_reports)
    value = existing_template({'scope': 'delivery', 'baseline': {'config_sha256': fingerprint()[1]}, 'samples': rows})
    value['records'] = [record for record in value['records'] if record['sample_id'] in required]
    value['global_difference_scope'] = _scope(population)
    value['comparison_population'] = population['members']
    value['sample_locations'] = {row['sample_id']: row['sample_path'] for row in rows}
    value['global_sampling'] = policy
    value['required_sample_ids'] = sorted(required)
    value['global_difference_instructions'] = (
        'Only substantive_difference is consumed. Review the exact complete effective comparison population. '
        'Keep the four original visual decisions and their reviewers unchanged; their compatibility fields here '
        'are not imported as new visual judgments. Supply actual human identity, provenance and full focal-step '
        'coverage. Do not sign a template or substitute producer success for inspection. '
        'This helper has created no review or approval; model calls and human decisions created: zero.')
    return value


def _reference(value):
    if (not isinstance(value, dict) or not isinstance(value.get('path'), str)
            or not isinstance(value.get('sha256'), str)):
        raise ValueError('Global review inputs require explicit path and SHA256 references')
    path = _real_path(value['path'])
    if not path.is_file() or sha(path) != value['sha256']:
        raise ValueError('Global review reference bytes changed')
    return {'path': str(path), 'sha256': value['sha256']}


def resolve(samples, global_reviews=(), *, sampling_plan=None, source_reports=()):
    """Validate original human records and derive only population-bound fifths."""
    rows, population = _population(samples); expected = _scope(population)
    required, selection = _selection(rows, population, sampling_plan, source_reports)
    contract_hash = fingerprint()[1]; decisions = {}; sources = []; source_bytes = {}
    for supplied in global_reviews:
        source = _reference(supplied)
        if source in sources:
            continue
        raw_bytes = Path(source['path']).read_bytes(); raw = json.loads(raw_bytes)
        if raw.get('schema_version') not in ('qc-review', 'qc-review-1', 'qc-review-2') or not isinstance(raw.get('records'), list):
            raise ValueError('Global comparison requires original qc-review records')
        header = raw.get('global_difference_scope')
        if header is not None and not _scope_matches(header, expected):
            raise ValueError('Global comparison population or difference rule scope changed')
        for record in raw['records']:
            local = record.get('global_difference_scope') if isinstance(record, dict) else None
            if (header is None and local is None) or (local is not None and not _scope_matches(local, expected)):
                raise ValueError('Every global decision must bind the full effective population and current difference rule')
            if record.get('reviewer', {}).get('kind') != 'human':
                raise ValueError('Global comparison import requires an actual human record; AI needs a validated request trace')
            if not isinstance(record.get('checks', {}).get(CHECK), dict):
                raise ValueError('Global comparison record uses a stale difference rule')
        accepted, errors, migrations = intake(source['path'], rows, contract_hash)
        if errors or migrations or len(accepted) != len(raw['records']):
            raise ValueError('Invalid global comparison evidence/coverage/reviewer binding: ' + json.dumps(errors, ensure_ascii=False))
        original = {record['sample_id']: record for record in raw['records']}
        for sid, record in accepted.items():
            fifth = record['checks'][CHECK]; original_hash = record_hash(original[sid])
            if sid in decisions:
                if decisions[sid]['source_record_sha256'] != original_hash:
                    raise ValueError('Conflicting global decisions require an explicit effective review selection; originals are preserved')
                decisions[sid].setdefault('identical_sources', []).append(source)
                continue
            decisions[sid] = {'sample_id': sid, 'status': fifth['status'], 'check': deepcopy(fifth),
                'source': source, 'source_record_sha256': original_hash,
                'reviewer': deepcopy(record['reviewer']), 'provenance': deepcopy(record['provenance']),
                'population_sha256': population['population_sha256'], 'rule_id': expected['rule_id'],
                'only_check_consumed': CHECK, 'visual_checks_imported': False, 'original_review_modified': False}
        sources.append(source); source_bytes[source['path']] = raw_bytes
    result = []
    for row in rows:
        sid = row['sample_id']
        result.append(decisions.get(sid, {'sample_id': sid,
            'status': 'REVIEW_REQUIRED' if sid in required else 'NOT_SELECTED',
            'reason': 'No actual full-population fifth-check decision supplied',
            'population_sha256': population['population_sha256'], 'rule_id': expected['rule_id'],
            'visual_checks_imported': False, 'original_review_modified': False}))
    # Recheck originals and the actual complete population at the exit boundary.
    if _population(samples)[1] != population or any(Path(path).read_bytes() != body for path, body in source_bytes.items()):
        raise ValueError('Global comparison evidence changed during import')
    for row in result:
        row['admission_status'] = 'PASS' if row['status'] in ('PASS', 'NOT_SELECTED') else row['status']
        row['semantic_review_claimed'] = row['status'] == 'PASS'
    if sampling_plan is not None:
        if _selection(rows, population, sampling_plan, source_reports) != (required, selection):
            raise ValueError('Global sampling inputs changed during import')
    states = [row['admission_status'] for row in result]
    status = 'FAIL' if 'FAIL' in states else 'REVIEW_REQUIRED' if not states or 'REVIEW_REQUIRED' in states else 'PASS'
    return {'schema_version': 'qc-global-difference-result-1', 'status': status,
            'population_sha256': population['population_sha256'], 'rule_id': expected['rule_id'],
            'qualified_sample_ids': [row['sample_id'] for row in result if row['admission_status'] == 'PASS'],
            'actual_fifth_pass_sample_ids': [row['sample_id'] for row in result if row['status'] == 'PASS'],
            'policy_admitted_sample_ids': [row['sample_id'] for row in result if row['status'] == 'NOT_SELECTED'],
            'global_sampling': selection,
            'failed_sample_ids': [row['sample_id'] for row in result if row['status'] == 'FAIL'],
            'pending_sample_ids': [row['sample_id'] for row in result if row['status'] == 'REVIEW_REQUIRED'],
            'decisions': result, 'sources': sources, 'only_check_consumed': CHECK,
            'visual_checks_imported': False, 'original_reviews_modified': False,
            'identity_authenticated': False, 'actual_reading_authenticated': False,
            'model_requests_dispatched': 0, 'human_decisions_created': 0}
