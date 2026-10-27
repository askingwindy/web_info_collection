"""Immutable, evidence-bound capability review hand-off; never trajectory QC."""
from collections import Counter
from copy import deepcopy
from pathlib import Path

from webcollect import planning
from webcollect.batch_core import file_sha, load_json, save_json

VERSION = 'capability-review-1'
RULES = planning.CAPABILITY_REVIEW_RULES
CHECKS = tuple(RULES['checks'])


def reference(path):
    path = Path(path).resolve()
    planning.verify_evidence([{'path': str(path), 'sha256': file_sha(path)}])
    return {'path': str(path), 'sha256': file_sha(path)}


def _packet(catalog_path, selected_ids=None, *, now=None):
    catalog_path = Path(catalog_path).resolve()
    catalog = load_json(catalog_path)
    if catalog.get('schema_version') != 'webcollect-capability-catalog-1':
        raise ValueError('Expected original capability catalog')
    records = catalog.get('records')
    if not isinstance(records, list):
        raise ValueError('Catalog records must be a list')
    selected_ids = selected_ids or [r.get('capability_id') for r in records
                                    if r.get('status') == 'review_required' and r.get('capability_id')]
    if not selected_ids or len(set(selected_ids)) != len(selected_ids):
        raise ValueError('Select at least one unique complete capability')
    by_id = {}
    for r in records:
        if r.get('capability_id') in selected_ids:
            if r['capability_id'] in by_id:
                raise ValueError('Ambiguous capability ID in catalog')
            by_id[r['capability_id']] = r
    if set(by_id) != set(selected_ids):
        raise ValueError('Selected capability missing from catalog')
    items = []
    for capability_id in selected_ids:
        r = by_id[capability_id]
        planning.validate_capability(r, now=now, require_ready=False)
        if planning.timestamp(r['expires_at']) <= planning.timestamp(now):
            raise ValueError('Original capability expired; collect new observations')
        if r.get('capability_scope') != {'kind': 'exact-candidate-page',
                                       'page_uris': [r['site_uri']], 'sitewide': False}:
            raise ValueError('Review import requires an exact candidate-page scope')
        images = [deepcopy(e) for e in r['evidence'] if Path(e['path']).suffix.lower() == '.png']
        if not images:
            raise ValueError('Every reviewed page needs original PNG evidence')
        source = r.get('source')
        if (not isinstance(source, list) or not source or any(
                not isinstance(x, dict) or not isinstance(x.get('source_sha256'), str)
                or len(x['source_sha256']) != 64 or any(c not in '0123456789abcdef' for c in x['source_sha256'])
                for x in source)):
            raise ValueError('Capability source provenance/version missing')
        items.append({'binding': {'capability_id': capability_id, 'original_version': r['version'],
            'record_sha256': planning.object_sha256(r), 'site_uri': r['site_uri'],
            'inventory_sha256': planning.object_sha256(r['capabilities']),
            'source_sha256': planning.object_sha256(source),
            'source_versions': [x.get('source_sha256') for x in source],
            'rules_sha256': planning.object_sha256(RULES)},
            'mode': r['mode'], 'source': deepcopy(source), 'original_expires_at': r['expires_at'],
            'inventory': deepcopy(r['capabilities']), 'supported_actions': r['supported_actions'],
            'task_families': r['task_families'],
            'pages': [{'uri': r['site_uri'], 'images': images,
                       'mechanical_preflight': deepcopy(r['representative_pages'][0])}]})
    return {'schema_version': 'webcollect-capability-review-packet-1',
            'catalog': reference(catalog_path), 'rules': RULES,
            'implementation': {'importer': reference(__file__), 'validator': reference(planning.__file__)},
            'records': items, 'QC_approval': False}


def prepare_review(catalog, output, *, capability_ids=None, now=None):
    packet = _packet(catalog, capability_ids, now=now)
    output = Path(output).resolve()
    if output == Path(catalog).resolve().parent or Path(catalog).resolve().parent in output.parents:
        raise ValueError('Review output must be outside the original catalog directory')
    packet_path = output / 'review-packet.json'
    save_json(packet_path, packet)
    template = {'schema_version': 'webcollect-capability-review-1', 'packet_sha256': file_sha(packet_path),
        'reviewer': {'id': '', 'kind': ''}, 'reviewed_at': None, 'completed': False,
        'records': [{'binding': item['binding'], 'status': None, 'reason': '', 'expires_at': None,
            'pages': [{'uri': p['uri'], 'reviewed_image_sha256': sorted({e['sha256'] for e in p['images']}),
                       'observations': '', 'checks': {name: 'NOT_REVIEWED' for name in CHECKS}}
                      for p in item['pages']]} for item in packet['records']]}
    template_path = output / 'review-template.json'
    save_json(template_path, template)
    return {'status': 'REVIEW_REQUIRED', 'packet': str(packet_path), 'template': str(template_path),
            'capabilities': len(packet['records']), 'ready_created': 0, 'network_visits': 0}


def _validate_review(packet, packet_path, review, *, now=None):
    current = planning.timestamp(now)
    if review.get('schema_version') != 'webcollect-capability-review-1' or review.get('packet_sha256') != file_sha(packet_path):
        raise ValueError('Review schema or frozen packet SHA mismatch')
    if review.get('completed') is not True:
        raise ValueError('Review has not been completed')
    reviewer = review.get('reviewer', {})
    if not isinstance(reviewer.get('id'), str) or not reviewer['id'].strip() or reviewer.get('kind') not in ('human', 'session_ai'):
        raise ValueError('Record a named human or session_ai reviewer; do not impersonate a human')
    if review.get('reviewed_at') is None:
        raise ValueError('Review timestamp required')
    reviewed = planning.timestamp(review['reviewed_at'])
    if reviewed > current:
        raise ValueError('Review timestamp is in the future')
    rows = review.get('records')
    if not isinstance(rows, list) or len(rows) != len(packet['records']):
        raise ValueError('Every selected capability needs exactly one review')
    originals = {r['capability_id']: r for r in load_json(packet['catalog']['path'])['records'] if 'capability_id' in r}
    for row, item in zip(rows, packet['records']):
        if row.get('binding') != item['binding']:
            raise ValueError('Review capability/page/inventory/source/rules binding mismatch')
        original = originals[item['binding']['capability_id']]
        if reviewed < planning.timestamp(original['observed_at']):
            raise ValueError('Review predates original observation')
        if row.get('status') not in ('ready', 'rejected', 'review_required'):
            raise ValueError('Review decision missing or invalid')
        if not isinstance(row.get('reason'), str) or not row['reason'].strip():
            raise ValueError('Every decision requires an observation-based reason')
        if row.get('expires_at') is None:
            raise ValueError('Reviewed capability expiry required')
        expiry = planning.timestamp(row['expires_at'])
        if not current < expiry <= planning.timestamp(original['expires_at']) or expiry <= reviewed:
            raise ValueError('Expiry must be live and cannot extend original observation lifetime')
        pages = row.get('pages')
        if not isinstance(pages, list) or len(pages) != len(item['pages']):
            raise ValueError('Every representative page must be reviewed')
        for page, expected in zip(pages, item['pages']):
            if page.get('uri') != expected['uri'] or page.get('reviewed_image_sha256') != sorted({e['sha256'] for e in expected['images']}):
                raise ValueError('Wrong page or incomplete original-image review')
            if not isinstance(page.get('observations'), str) or not page['observations'].strip():
                raise ValueError('Every page requires actual visual observations')
            checks = page.get('checks')
            if not isinstance(checks, dict) or set(checks) != set(CHECKS) or any(v not in ('PASS', 'FAIL', 'UNKNOWN') for v in checks.values()):
                raise ValueError('Every required check needs PASS, FAIL or UNKNOWN')
            if row['status'] == 'ready':
                mechanical = expected['mechanical_preflight']
                if (any(v != 'PASS' for v in checks.values()) or original['status'] == 'rejected'
                    or mechanical.get('accessible') is not True or mechanical.get('rendered') is not True
                    or mechanical.get('error') or mechanical.get('routing') != 'NORMAL_M1'
                    or mechanical.get('chinese_ratio', 0) < 0.7):
                    raise ValueError('Unresolved/failed checks or mechanical rejection cannot grant ready')


def import_review(packet_path, review_path, output, *, now=None):
    packet_path, review_path, output = Path(packet_path).resolve(), Path(review_path).resolve(), Path(output).resolve()
    packet, review = load_json(packet_path), load_json(review_path)
    if packet.get('schema_version') != 'webcollect-capability-review-packet-1':
        raise ValueError('Invalid review packet schema')
    planning.verify_evidence([packet['catalog'], *packet['implementation'].values()])
    expected = _packet(packet['catalog']['path'], [i['binding']['capability_id'] for i in packet['records']], now=now)
    if packet != expected:
        raise ValueError('Frozen review packet no longer matches original evidence or rules')
    _validate_review(packet, packet_path, review, now=now)
    original_catalog = Path(packet['catalog']['path'])
    if output == original_catalog.parent or original_catalog.parent in output.parents:
        raise ValueError('Import output must be outside the original catalog directory')
    frozen_packet, frozen_review = output / 'review-packet.json', output / 'review-record.json'
    # Saved copies remain stable even when a reviewer later edits their working file.
    save_json(frozen_packet, packet)
    save_json(frozen_review, review)
    packet_ref, review_ref = reference(frozen_packet), reference(frozen_review)
    catalog = deepcopy(load_json(original_catalog))
    review_by_id = {row['binding']['capability_id']: row for row in review['records']}
    for record in catalog['records']:
        row = review_by_id.get(record.get('capability_id'))
        if row is None:
            continue
        original_version = record['version']
        record['status'], record['reason'], record['expires_at'] = row['status'], row['reason'], row['expires_at']
        record['prior_screening'] = deepcopy(record.get('screening'))
        record['screening'] = {'status': row['status'], 'reason': row['reason'],
            'page_observations': [p['observations'] for p in row['pages']],
            'review_source': review['reviewer']['kind'], 'reviewer': review['reviewer'],
            'reviewed_at': review['reviewed_at']}
        record['review_provenance'] = {'schema_version': 'webcollect-capability-review-provenance-1',
            'parent_version': original_version, 'catalog': packet['catalog'],
            'packet': packet_ref, 'review': review_ref}
        record['version'] = planning.object_sha256({'parent_version': original_version,
            'packet_sha256': packet_ref['sha256'], 'review_sha256': review_ref['sha256'],
            'capability_id': record['capability_id']})[:24]
        existing = {e['path'] for e in record['evidence']}
        record['evidence'] += [ref for ref in (packet['catalog'], packet_ref, review_ref) if ref['path'] not in existing]
        record['QC_approval'] = False
        planning.validate_capability(record, now=now, require_ready=record['status'] == 'ready')
    catalog['status_counts'] = dict(Counter(r['status'] for r in catalog['records']))
    catalog['capability_review'] = {'packet': packet_ref, 'review': review_ref, 'reviewed_count': len(review_by_id),
                                    'network_visits': 0, 'QC_approval': False}
    catalog['real_supply_verified'] = False
    catalog_path = output / 'catalog-reviewed.json'
    save_json(catalog_path, catalog)
    result = {'status': 'IMPORTED', 'catalog_file': str(catalog_path), 'catalog_sha256': file_sha(catalog_path),
              'reviewed_count': len(review_by_id), 'status_counts': catalog['status_counts'],
              'network_visits': 0, 'new_production_ids': 0, 'QC_approval': False}
    save_json(output / 'import-receipt.json', result)
    return result
