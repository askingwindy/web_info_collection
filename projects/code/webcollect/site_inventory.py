"""Read-only Table1/Table2 inventory for site-scoped worker planning."""
import argparse
import json
from pathlib import Path

from site_planner.candidate_pool import CandidatePool


STATES = ('pending', 'consuming', 'succeeded', 'failed', 'reconcile')


def load_scope(path):
    scope_path = Path(path).absolute()
    scope = json.loads(scope_path.read_text(encoding='utf-8'))
    if not scope.get('pool'):
        raise ValueError('Scope does not bind a candidate pool')
    return scope_path, scope


def resolve_sites(pool, selectors=()):
    """Resolve only stable application IDs or registered primary/alias hosts."""
    with pool.pool.connect() as con:
        if not selectors:
            return [dict(row) for row in con.execute(
                'SELECT * FROM applications ORDER BY created,id')]
        sites = []
        seen = set()
        for selector in selectors:
            value = selector.strip()
            if not value:
                raise ValueError('Site selector cannot be empty')
            row = con.execute('SELECT * FROM applications WHERE id=?', (value,)).fetchone()
            site = dict(row) if row else pool.pool.application(
                value if '://' in value else 'https://' + value + '/')
            if site is None:
                raise ValueError(
                    f'Unknown site {selector!r}; use an applications.id or a registered primary/alias host')
            if site['id'] in seen:
                raise ValueError(f'Site selected more than once: {site["id"]}')
            seen.add(site['id'])
            sites.append(site)
        return sites


def site_statistics(pool, site):
    with pool.pool.connect() as con:
        discovery_installed = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='application_discovery'").fetchone()
        if discovery_installed:
            discovery = con.execute(
                'SELECT homepage,classification_state,mining_state,taxonomy_version '
                'FROM application_discovery WHERE application_id=?', (site['id'],)).fetchone()
        else:
            discovery = None
        states = {state: 0 for state in STATES}
        states.update({row['state']: row['count'] for row in con.execute(
            'SELECT state,COUNT(*) AS count FROM data_candidates '
            'WHERE application_id=? GROUP BY state', (site['id'],))})
        cumulative_new = con.execute(
            "SELECT COUNT(DISTINCT c.candidate_id) FROM data_candidates c "
            "JOIN candidate_batch_rows b ON b.candidate_id=c.candidate_id "
            "WHERE c.application_id=? AND b.result='NEW'", (site['id'],)).fetchone()[0]
    return {
        'application_id': site['id'],
        'host': site['host'],
        'homepage': discovery['homepage'] if discovery else None,
        'category': site['category'],
        'classification_state': discovery['classification_state'] if discovery else 'pending',
        'mining_state': discovery['mining_state'] if discovery else 'pending',
        'cumulative_new': cumulative_new,
        **states,
    }


def inventory(scope_path, selectors=()):
    _, scope = load_scope(scope_path)
    pool = CandidatePool(scope['pool'], readonly=True)
    return {'pool': str(pool.path),
            'sites': [site_statistics(pool, site) for site in resolve_sites(pool, selectors)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--scope', type=Path, required=True)
    parser.add_argument('--site', action='append', default=[],
                        help='applications.id or registered primary/alias host; repeatable')
    args = parser.parse_args(argv)
    try:
        result = inventory(args.scope, args.site)
    except (KeyError, ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
