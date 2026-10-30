"""Program 2's read-only shared-pool interface; contains no collection dispatch."""
import argparse
import json


def read_site_pool(path, *, purpose='candidates', categories=None, include_unavailable=False, fragment_planning=False):
    from site_planner.site_pool import SitePool, page_uri
    from .planning import validate_capability, verify_evidence
    from .batch_core import load_json
    pool = SitePool(path, readonly=True)
    if purpose not in ('candidates', 'capabilities'):
        raise ValueError('Select candidates or validated capabilities')
    rows = pool.rows()
    if not include_unavailable:
        rows = [r for r in rows if r['collection']['dispatch_allowed'] or fragment_planning and
                not r['collection'].get('sync_pending') and r['collection']['status'] not in ('quality_revoked','qc_failed')]
    if categories:
        from site_planner.site_pool import category
        for name in categories:
            category(name)
        rows = [r for r in rows if r['category'] in categories]
    if purpose == 'candidates':
        return {'schema_version': 'webcollect-shared-pool-handoff-1', 'purpose': purpose,
                'records': rows, 'execution_verified': 'NOT_RUN', 'collection_dispatched': False}
    allowed = {r['page_id']: r['uri'] for r in rows}
    records = {}
    with pool.connect() as con:
        for row in con.execute('SELECT page_id,reference FROM capabilities ORDER BY created,id'):
            if row['page_id'] not in allowed:
                continue
            ref = json.loads(row['reference']); verify_evidence([ref])
            catalog = load_json(ref['path'])
            if catalog.get('schema_version') != 'webcollect-capability-catalog-1':
                raise ValueError('Capability catalog schema changed')
            for record in catalog['records']:
                if page_uri(record['site_uri']) == allowed[row['page_id']]:
                    if record.get('mode') != 'real' or not ({'site_qualification', 'review_provenance'} & record.keys()):
                        raise ValueError('Existing real qualification/review evidence required')
                    validate_capability(record, require_ready=True)
                    records[(record['capability_id'], record['version'])] = record
    return {'schema_version': 'webcollect-capability-catalog-1', 'mode': 'real',
            'records': list(records.values()), 'pool': str(pool.path),
            'collection_dispatched': False, 'sample_ids_allocated': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool', required=True)
    parser.add_argument('--purpose', choices=['candidates', 'capabilities'], default='candidates')
    parser.add_argument('--category', action='append', dest='categories')
    parser.add_argument('--include-unavailable', action='store_true', help='Include tracked/ineligible pages for read-only audit')
    parser.add_argument('--fragment-planning', action='store_true', help='Read known synchronized pages for new source-bound fragment proposals; never dispatch')
    args = parser.parse_args(argv)
    print(json.dumps(read_site_pool(args.pool, purpose=args.purpose, categories=args.categories,
                                   include_unavailable=args.include_unavailable,fragment_planning=args.fragment_planning), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
