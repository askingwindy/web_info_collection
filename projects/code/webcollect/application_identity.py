"""Evidence-bound application aliases; never infer ownership from domain similarity."""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .planning import verify_evidence


def host_key(uri):
    from .production_identity import page_url
    parsed = urlsplit(uri)
    if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        uri = urlunsplit((parsed.scheme, parsed.netloc, '/', '', ''))
    return page_url(uri)


def aliases(reference):
    if reference is None:
        return {}
    from .batch_core import load_json
    verify_evidence([reference])
    value = load_json(reference['path'])
    if set(value) != {'schema_version', 'applications'} or value['schema_version'] != 'webcollect-application-aliases-1':
        raise ValueError('Explicit evidence-bound application alias registry required')
    mapping = {}
    for row in value['applications']:
        if set(row) != {'canonical_uri', 'aliases', 'evidence'} or not row['aliases'] or row['canonical_uri'] not in row['aliases']:
            raise ValueError('Application canonical URI must be an observed alias')
        verify_evidence(row['evidence'])
        canonical = host_key(row['canonical_uri'])
        for uri in row['aliases']:
            parsed = urlsplit(uri)
            if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
                raise ValueError('Application aliases must be whole hosts, not task pages')
            key = host_key(uri)
            if key in mapping and mapping[key] != canonical:
                raise ValueError('One observed host cannot belong to two applications')
            mapping[key] = canonical
    return mapping


def canonical_key(uri, reference=None):
    key = host_key(uri)
    return aliases(reference).get(key, key)
