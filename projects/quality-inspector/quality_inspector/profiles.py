"""Explicit local pilot acceptance. Customer equivalence is never inferred."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

DHASH = {'bits': 64, 'orientation': 'horizontal', 'grayscale': 'Pillow-L',
         'resize': [9, 8], 'resampling': 'Pillow-LANCZOS', 'comparison': 'left>right',
         'bit_order': 'row-major-left-to-right-top-to-bottom-msb-first',
         'maximum_hamming_each_endpoint': 4}
SIMHASH = {'bits': 64, 'tokens': 'CJK-bigrams-or-single-character+lowercase-Latin-alphanumeric-underscore',
           'cjk_range': ['U+4E00', 'U+9FFF'], 'latin_regex': '[a-zA-Z0-9_]+',
           'lowercase': 'Python-str.lower', 'cjk_window': 2, 'single_cjk_token': True,
           'weight': 'term-frequency', 'hash': 'SHA256-first-8-bytes-big-endian',
           'tie': 0, 'maximum_hamming': 3}
PACKAGE_REVIEW_CHECKS = ['delivery_documentation', 'site_category_attribution']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def aggregate(states):
    states = list(states)
    return 'FAIL' if 'FAIL' in states else 'REVIEW_REQUIRED' if not states or 'REVIEW_REQUIRED' in states else 'PASS'


def load(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get('schema_version') != 'qc-local-profile-1':
        raise ValueError('Unsupported local acceptance profile schema')
    if data.get('scope') != 'pilot' or not isinstance(data.get('profile_id'), str) or not data['profile_id'].strip():
        raise ValueError('Profile must identify its local pilot scope')
    duplicate = data.get('duplicates', {})
    if duplicate != {'exact_images': 'zero-cross-sample-reuse',
                     'sequence': 'exact-action_type+target_text+page_name-list',
                     'dhash': DHASH, 'simhash': SIMHASH}:
        raise ValueError('Profile algorithms must match the implemented complete parameters and archived thresholds; no silent weakening')
    targets = data.get('targets')
    expected = {'minimum_samples', 'minimum_sites', 'max_category_share', 'max_viewport_specs', 'max_short_flow_share'}
    if not isinstance(targets, dict) or set(targets) != expected:
        raise ValueError('Profile must declare every pilot target')
    for name in ['minimum_samples', 'minimum_sites', 'max_viewport_specs']:
        if type(targets[name]) is not int or targets[name] < 1:
            raise ValueError('Invalid profile target ' + name)
    for name in ['max_category_share', 'max_short_flow_share']:
        if type(targets[name]) not in (int, float) or not 0 <= targets[name] <= 1:
            raise ValueError('Invalid profile share ' + name)
    if targets['max_category_share'] > 0.2 or targets['max_viewport_specs'] > 3 or targets['max_short_flow_share'] > 0.02:
        raise ValueError('Local pilot profile cannot weaken archived distribution limits')
    return {'path': str(path), 'sha256': sha(path), 'configuration': data,
            'customer_algorithm_equivalence': 'UNKNOWN', 'customer_actual_acceptance': 'UNKNOWN'}


def package_files(dataset):
    """Bind the documentary review to the actual inspected package, not a title."""
    dataset = Path(dataset).resolve()
    files = {}
    for file in sorted(dataset.rglob('*')):
        if file.is_symlink():
            raise ValueError('Package review cannot bind symlink: ' + str(file))
        if file.is_file():
            files[file.relative_to(dataset).as_posix()] = sha(file)
    return files


def package_review_template(report):
    return {'schema_version': 'qc-package-review-1',
            'baseline_sha256': report['baseline']['config_sha256'],
            'profile_sha256': report['local_profile']['sha256'],
            'package_files_sha256': report['package_files_sha256'],
            'reviewer': {'kind': '', 'name': ''}, 'provenance': {'description': ''},
            'checks': {name: {'status': 'REVIEW_REQUIRED', 'note': ''} for name in PACKAGE_REVIEW_CHECKS},
            'checklist': ['README distributions and actual counts', 'field specification',
                          'source and compliance, frequency and account declarations',
                          'synthesis/action/coordinate/change/narrative mapping',
                          'each qc_report: 17 checks, four-route counts, distributions, rejection reasons, actual review source/proportion/conclusion',
                          'site IDs/URIs correspond to actual sources; category semantics use consistent broad groups, never artificial label splitting to reduce shares',
                          'unknown rejection counts or unexecuted checks remain explicit, never fabricated as zero/PASS']}


def package_review(path, report):
    if not path:
        return {'status': 'REVIEW_REQUIRED', 'reason': 'No evidence-bound delivery-document review supplied.'}
    raw = json.loads(Path(path).read_text())
    value = raw.get('package_review') if isinstance(raw, dict) else None
    if value is None:
        return {'status': 'REVIEW_REQUIRED', 'reason': 'Existing sample reviews do not review delivery documents.'}
    errors = []
    if not isinstance(value, dict):
        return {'status': 'FAIL', 'errors': ['package_review must be an object']}
    required = {'schema_version': 'qc-package-review-1', 'baseline_sha256': report['baseline']['config_sha256'],
                'profile_sha256': report['local_profile']['sha256'], 'package_files_sha256': report['package_files_sha256']}
    for field, expected in required.items():
        if value.get(field) != expected:
            errors.append('missing/stale/different ' + field)
    reviewer = value.get('reviewer'); provenance = value.get('provenance'); checks = value.get('checks')
    if not isinstance(reviewer, dict) or reviewer.get('kind') not in ['ai', 'human'] or not isinstance(reviewer.get('name'), str) or not reviewer['name'].strip():
        errors.append('actual reviewer kind/name required; identity not authenticated')
    if not isinstance(provenance, dict) or not isinstance(provenance.get('description'), str) or not provenance['description'].strip():
        errors.append('actual review provenance required')
    if not isinstance(checks, dict) or set(checks) != set(PACKAGE_REVIEW_CHECKS):
        errors.append('complete documentary checks required')
    else:
        for name, result in checks.items():
            if not isinstance(result, dict) or result.get('status') not in ['PASS', 'FAIL', 'REVIEW_REQUIRED']:
                errors.append('invalid check status ' + name)
            elif result['status'] in ['PASS', 'FAIL'] and (not isinstance(result.get('note'), str) or not result['note'].strip()):
                errors.append('specific evidence note required ' + name)
    return {'status': 'FAIL' if errors else aggregate(v['status'] for v in checks.values()),
            'errors': errors, 'reviewer': reviewer, 'provenance': provenance, 'checks': checks,
            'reason': 'Hash-bound document review, independent from file presence and sample visual review.'}


def apply(report, profile, reviews=None):
    """Add a strict local view; preserve the legacy/customer-unknown overall status."""
    report['local_profile'] = profile
    traceability = Path(__file__).resolve().parents[1] / 'config' / 'requirements-baseline-v1.json'
    report['requirements_baseline'] = {'path': str(traceability), 'sha256': sha(traceability),
                                       'configuration': json.loads(traceability.read_text())}
    dataset = Path(report['dataset'])
    report['package_files_sha256'] = package_files(dataset)
    report['package_review'] = package_review(reviews, report)
    duplicate = report['duplicates']
    sample_checks = []
    for sample in report['samples']:
        near = any(sample['sample_id'] in pair['sample_ids'] for route in ['route3', 'route4'] for pair in duplicate[route]['candidates'])
        checks = []
        for original in sample['checks']:
            check = dict(original)
            if check['rule_id'] in ['C13', 'C14']:
                continue  # These unchanged checks are reported once in batch scope below.
            check['scope'] = 'sample'
            if check['rule_id'] == 'NEAR_DUPLICATES':
                check.update(status='REVIEW_REQUIRED' if duplicate.get('error') else 'FAIL' if near else 'PASS',
                             reason='Executed the explicitly configured local dHash/SimHash thresholds. Any hit is a duplicate; no semantic exemption.',
                             fix_suggestion='Recapture/replace duplicate candidates; preserve rejected evidence. Customer equivalence remains UNKNOWN.',
                             profile_sha256=profile['sha256'])
            checks.append(check)
        sample['local_checks'] = checks
        sample['local_acceptance_status'] = aggregate(c['status'] for c in checks)
        sample_checks += checks

    batch_checks = []
    for sample in report['samples']:
        for original in sample['checks']:
            if original['rule_id'] in ['C13', 'C14']:
                batch_checks.append(dict(original, scope='batch', sample_id=sample['sample_id']))
    batch_checks += [dict(c, scope='batch') for c in report['dataset_checks'] if c['rule_id'] == 'U02']
    roles = report['format_layer_summary']['document_roles']
    batch_checks.append({'rule_id': 'DELIVERY_DOCUMENT_ROLES', 'scope': 'batch',
                         'status': aggregate(v['status'] for v in roles.values()), 'evidence': roles})
    batch_checks.append({'rule_id': 'DELIVERY_DOCUMENT_REVIEW', 'scope': 'batch',
                         'status': report['package_review']['status'], 'evidence': report['package_review']})
    root = report['root_checksum']
    batch_checks.append({'rule_id': 'ROOT_CHECKSUM', 'scope': 'batch',
                         'status': 'PASS' if root.get('pass') is True else 'FAIL' if root.get('pass') is False else 'REVIEW_REQUIRED', 'evidence': root})

    rows = []; missing = []; sites = defaultdict(set); source_sites = defaultdict(set)
    source_missing = []; source_errors = []; source_manifests = {}
    for batch in report['batch_results']:
        manifest = Path(batch['batch']) / 'manifest.json'
        if not manifest.is_file():
            source_missing.append(str(manifest))
        else:
            try:
                source = json.loads(manifest.read_text())
                declarations = source.get('sites') if isinstance(source, dict) else None
                if not isinstance(declarations, list) or not declarations:
                    raise ValueError('No recorded site/URI/category attribution')
                source_manifests[str(manifest)] = sha(manifest)
                for entry in declarations:
                    if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k].strip() for k in ['site_id', 'uri', 'site_category']):
                        raise ValueError('Malformed site attribution')
                    from urllib.parse import urlsplit
                    uri = urlsplit(entry['uri'])
                    if uri.scheme not in ['http', 'https'] or not uri.hostname or uri.username or uri.password:
                        raise ValueError('Invalid site URI attribution')
                    source_sites[entry['site_id']].add((entry['uri'], entry['site_category']))
            except (OSError, ValueError, TypeError) as error:
                source_errors.append(str(manifest) + ': ' + str(error))
        path = Path(batch['batch']) / 'metadata.csv'
        if not path.is_file():
            missing.append(str(path)); continue
        try:
            with path.open(newline='', encoding='utf-8-sig') as file:
                for row in csv.DictReader(file):
                    if any(not isinstance(row.get(field), str) or not row[field].strip() for field in ['sample_id', 'site_id', 'site_category']):
                        missing.append(str(path) + '/' + str(row.get('sample_id')) + ': sample_id/site_id/site_category required for pilot statistics')
                    row = {field: value if isinstance(value, str) else '' for field, value in row.items()}
                    rows.append(row)
                    sites[row.get('site_id', '')].add(row.get('site_category', ''))
        except (OSError, ValueError, csv.Error) as error:
            missing.append(str(path) + ': ' + str(error))
    categories = Counter(row.get('site_category', '') for row in rows)
    uri_ids = defaultdict(set)
    for site_id, values in source_sites.items():
        if len(values) > 1:
            source_errors.append('Conflicting source URI/category for ' + site_id)
        for uri, _ in values:
            uri_ids[uri].add(site_id)
    for uri, ids in uri_ids.items():
        if len(ids) > 1:
            source_errors.append('Same source URI assigned multiple IDs: ' + uri)
    for row in rows:
        declarations = source_sites.get(row.get('site_id'))
        if not declarations:
            source_missing.append('No recorded source URI/category for ' + str(row.get('site_id')))
        elif not any(category == row.get('site_category') for _, category in declarations):
            source_errors.append('Metadata/source category mismatch for ' + str(row.get('sample_id')))
    resolutions = set(); short_count = 0
    for sample in report['samples']:
        try:
            a = json.loads((Path(sample['sample_path']) / 'annotation.json').read_text())
            resolution = a['device_info']['screen_resolution']
            if not isinstance(resolution, list) or len(resolution) != 2 or any(type(v) is not int or v <= 0 for v in resolution):
                raise ValueError('Invalid viewport specification')
            resolutions.add(tuple(resolution))
            short_count += a.get('short_flow') is True
        except (OSError, ValueError, TypeError, KeyError):
            missing.append(sample['sample_id'] + ': unreadable pilot distribution facts')
    count = report['sample_count']; targets = profile['configuration']['targets']
    stats = {'sample_count': count, 'site_count': len({row.get('site_id') for row in rows if row.get('site_id')}),
             'site_identity': 'metadata.site_id; URI identity assignment is declared by producer, not inferred from hostname',
             'categories': dict(categories), 'category_basis': 'trajectory count, no regrouping to improve ratio',
             'viewport_specs': [list(v) for v in sorted(resolutions)], 'short_flow_count': short_count,
             'missing_facts': missing, 'site_category_conflicts': {key: sorted(v) for key, v in sites.items() if len(v) > 1}}
    stats['source_attribution'] = {'status': 'FAIL' if source_errors else 'REVIEW_REQUIRED' if source_missing else 'PASS',
                                  'missing': source_missing, 'errors': source_errors,
                                  'manifest_sha256': source_manifests,
                                  'site_uri_category': {key: [list(v) for v in sorted(values)] for key, values in source_sites.items()},
                                  'semantic_category_acceptance': 'Requires evidence-bound site_category_attribution review; labels alone do not prove legitimate grouping.'}
    pilot_checks = [
        {'rule_id': 'PILOT_ACCOUNTING', 'status': 'FAIL' if missing or len(rows) != count or stats['site_category_conflicts'] else 'PASS', 'actual_rows': len(rows), 'evidence': stats},
        {'rule_id': 'PILOT_SOURCE_ATTRIBUTION', 'status': stats['source_attribution']['status'], 'evidence': stats['source_attribution']},
        {'rule_id': 'PILOT_MINIMUM_SAMPLES', 'status': 'PASS' if count >= targets['minimum_samples'] else 'FAIL', 'actual': count, 'minimum': targets['minimum_samples']},
        {'rule_id': 'PILOT_MINIMUM_SITES', 'status': 'PASS' if stats['site_count'] >= targets['minimum_sites'] else 'FAIL', 'actual': stats['site_count'], 'minimum': targets['minimum_sites']},
        {'rule_id': 'PILOT_CATEGORY_SHARE', 'status': 'PASS' if count and categories and max(categories.values()) / count <= targets['max_category_share'] else 'FAIL', 'actual_maximum': max(categories.values(), default=0) / count if count else None, 'maximum': targets['max_category_share']},
        {'rule_id': 'PILOT_VIEWPORT_SPECS', 'status': 'PASS' if resolutions and len(resolutions) <= targets['max_viewport_specs'] else 'FAIL', 'actual': len(resolutions), 'maximum': targets['max_viewport_specs']},
        {'rule_id': 'PILOT_SHORT_FLOW_SHARE', 'status': 'PASS' if count and short_count / count <= targets['max_short_flow_share'] else 'FAIL', 'actual': short_count / count if count else None, 'maximum': targets['max_short_flow_share']},
        {'rule_id': 'LOCAL_INPUT_INTEGRITY', 'status': 'FAIL' if report['baseline']['integrity'] == 'FAIL' or report['review_import']['invalid_records'] or report['partial_ai_artifact'].get('errors') or report['format_layer_summary']['package_errors'] else 'PASS'},
    ]
    for check in pilot_checks:
        check['scope'] = 'pilot'
    scopes = {'sample': {'status': aggregate(c['status'] for c in sample_checks), 'sample_count': count},
              'batch': {'status': aggregate(c['status'] for c in batch_checks), 'checks': batch_checks},
              'pilot': {'status': aggregate(c['status'] for c in pilot_checks), 'checks': pilot_checks, 'statistics': stats},
              'corpus': {'status': 'UNKNOWN', 'excluded_from_local_pilot_gate': True, 'reason': 'The inspected pilot does not prove 200000 trajectories, approximately 10000 sites, full-corpus uniqueness/distributions or external sampling acceptance.'},
              'external': {'status': 'UNKNOWN', 'excluded_from_local_pilot_gate': True, 'reason': 'Customer executable and dHash/SimHash equivalence not established; no customer PASS claimed.'}}
    report['acceptance_scopes'] = scopes
    report['local_acceptance_status'] = aggregate(scopes[scope]['status'] for scope in ['sample', 'batch', 'pilot'])
    report['local_sample_status_counts'] = dict(Counter(s['local_acceptance_status'] for s in report['samples']))
    report['local_gate_is_not_customer_acceptance'] = True
    report['local_rule_catalog'] = [
        {'id': c['rule_id'], 'scope': c['scope'], 'certainty': 'explicit_local_profile',
         'sources': ['profile SHA256 ' + profile['sha256'], 'requirements-baseline-v1.json'],
         'customer_equivalence': 'UNKNOWN'}
        for c in batch_checks + pilot_checks if c['rule_id'] not in ['C13', 'C14', 'U02']]
    return report
