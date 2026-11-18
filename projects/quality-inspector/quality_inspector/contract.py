"""Installed, content-bound customer authority; no repository lookup at runtime."""
import hashlib
from webcollect import workspace_json as json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def authority():
    root = Path(__file__).parent
    manifest = json.loads((root / 'contract-authority.json').read_text(encoding='utf-8'))
    roles = [item['role'] for item in manifest['documents']]
    if (manifest.get('schema_version') not in ('installed-authority','qc-installed-authority-1')
            or len(roles) != len(set(roles)) or roles != manifest.get('source_precedence')
            or not {'clarification', 'site_trajectory_scope', 'trajectory_supplement',
                    'qc_sampling', 'requirement', 'annex_a', 'annex_b'} <= set(roles)):
        raise ValueError('Incomplete installed contract authority or precedence')
    for item in manifest['documents']:
        relative = Path(item['resource'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'authority':
            raise ValueError('Installed contract authority resource outside package')
        path = root / relative
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Installed contract authority changed: ' + item['path'])
    return manifest


def installed_contract():
    from .format_checks import ANNOTATION, TREE, ACTIONS, catalog
    from .reviews import SEMANTIC, REVIEW_POLICY
    from .category_coverage import POLICY as CATEGORY_COVERAGE_POLICY
    root = Path(__file__).parent
    documents = authority()
    return {
        'schema_version': 'webcollect-delivery-contract-2',
        'annotation': ANNOTATION, 'tree': TREE, 'actions': ACTIONS,
        'authority': documents,
        'attachments': {Path(row['path']).name: row['sha256']
                        for row in documents['documents'] if row['role'] in ('annex_a', 'annex_b')},
        'rule_catalog': catalog(), 'semantic_checks': SEMANTIC,
        'review_policy': REVIEW_POLICY,
        'category_coverage_policy': CATEGORY_COVERAGE_POLICY,
        'implementation_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                  for name in ('contract.py', 'format_checks.py', 'engine.py',
                                               'reviews.py', 'profiles.py', 'duplicates.py',
                                               'cumulative.py', 'category_coverage.py', 'application_capacity.py', 'checksums.py', 'layout.py',
                                               'delivery_sampling.py','production_sampling.py')},
        'customer_actual_program_executed': False,
        'customer_actual_acceptance': 'UNKNOWN',
    }


def fingerprint():
    value = installed_contract()
    # Full source hashes remain in the report for engineering provenance, not
    # in review acceptance identity. Mechanical checks still run every time.
    rules = {key: item for key, item in value.items()
             if key != 'implementation_sha256'}
    return value, digest(rules)
