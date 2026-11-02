"""Installed, content-bound customer authority; no repository lookup at runtime."""
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def authority():
    root = Path(__file__).parent
    manifest = json.loads((root / 'contract-authority.json').read_text())
    for item in manifest['documents']:
        path = root / item['resource']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Installed contract authority changed: ' + item['path'])
    return manifest


def installed_contract():
    from . import __version__
    from .format_checks import ANNOTATION, TREE, ACTIONS, catalog
    from .reviews import SEMANTIC, REVIEW_POLICY
    root = Path(__file__).parent
    documents = authority()
    return {
        'schema_version': 'webcollect-delivery-contract-2',
        'annotation': ANNOTATION, 'tree': TREE, 'actions': ACTIONS,
        'rules_version': __version__, 'authority': documents,
        'attachments': {Path(row['path']).name: row['sha256']
                        for row in documents['documents'] if row['role'] in ('annex_a', 'annex_b')},
        'rule_catalog': catalog(), 'semantic_checks': SEMANTIC,
        'review_policy': REVIEW_POLICY,
        'implementation_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                  for name in ('contract.py', 'format_checks.py', 'engine.py',
                                               'reviews.py', 'profiles.py', 'duplicates.py',
                                               'cumulative.py', 'application_capacity.py', 'checksums.py', 'layout.py',
                                               'delivery_sampling.py','production_sampling.py')},
        'customer_actual_program_executed': False,
        'customer_actual_acceptance': 'UNKNOWN',
    }


def fingerprint():
    value = installed_contract()
    # Full source hashes remain in the report for engineering provenance, not
    # in review acceptance identity. Mechanical checks still run every time.
    rules = {key: item for key, item in value.items()
             if key not in ('implementation_sha256', 'rules_version')}
    return value, digest(rules)
