import json
import sqlite3
from collections import Counter, deque
from contextlib import closing
from pathlib import Path
from urllib.parse import unquote, urlsplit

from site_planner.candidate_pool import entry_identity
from site_planner.entry_selection import compile_entry_exclusions, entry_is_excluded
from webcollect.batch_core import load_json, save_json
from webcollect.candidate_cohort import VERSION, inspect_rows, reference
from webcollect.candidate_consumer import preflight_candidate_sources


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'results' / 'stepwise-three-sites-150-20261118'
SCOPE = ROOT / 'database/sqllite/prod/scope.json'
HOSTS = ('zh.wikipedia.org', 'muxtly.com', 'dpm.org.cn')


def page_family(host, entry):
    url = urlsplit(entry)
    path = unquote(url.path).rstrip('/')
    if url.hostname not in (host, 'www.' + host) or not path or url.query:
        return None
    if host == HOSTS[0]:
        prefix, _, title = path[1:].partition('/')
        return 'article' if prefix in ('wiki', 'zh-cn', 'zh-hans') and title and ':' not in title and title not in ('首页', '首頁', 'Wikipedia') else None
    if host == HOSTS[1]:
        return 'tool' if path.startswith('/zh-CN/') else None
    return path.lstrip('/').split('/')[0]


def prepare(run=RUN, *, exclude_cohort=None):
    scope = load_json(SCOPE)
    directory = run / 'selection'
    directory.mkdir(parents=True, exist_ok=False)
    old = load_json(exclude_cohort)['selected'] if exclude_cohort else []
    old_ids = {row['candidate_id'] for row in old}
    old_landings = {entry_identity(load_json(row['entry_http']['path'])['landed_uri']) for row in old}
    chosen = {host: [] for host in HOSTS}
    skipped = Counter()
    with closing(sqlite3.connect(Path(scope['pool']).as_uri() + '?mode=ro', uri=True)) as connection:
        for host in HOSTS:
            groups = {}
            for candidate, entry in connection.execute('''SELECT d.candidate_id,json_extract(d.body,'$.entry_url')
                FROM data_candidates d JOIN applications a ON a.id=d.application_id
                WHERE a.host=? AND d.state='pending' AND NOT EXISTS
                (SELECT 1 FROM candidate_claims c WHERE c.candidate_id=d.candidate_id)
                AND NOT EXISTS (SELECT 1 FROM candidate_events e WHERE e.candidate_id=d.candidate_id AND e.kind='disposition')
                ORDER BY d.created DESC,d.candidate_id''', (host,)):
                if candidate in old_ids:
                    continue
                family = page_family(host, entry)
                if family:
                    groups.setdefault(family, deque()).append(candidate)
            ordered = deque()
            while any(groups.values()):
                ordered.extend(group.popleft() for group in groups.values() if group)
            landing_ids = set()
            while len(chosen[host]) < 50 and ordered:
                batch = [ordered.popleft() for _ in range(min(50 - len(chosen[host]), len(ordered)))]
                _, inspected, audit = inspect_rows(SCOPE, candidate_ids=batch)
                by_id = {row['candidate_id']: row for row in inspected}
                for candidate in batch:
                    row = by_id[candidate]
                    if not row['eligible']:
                        skipped[(host, row['rejection']['reason'][:120])] += 1
                        continue
                    preflight_candidate_sources(scope['registry'], row['sources'])
                    landing = load_json(row['entry_http']['path'])['landed_uri']
                    identity = entry_identity(landing)
                    patterns = compile_entry_exclusions(row['sources'])
                    if identity in landing_ids or identity in old_landings or urlsplit(landing).hostname not in (host, 'www.' + host) or any(entry_is_excluded(url, patterns) for url in (row['entry_url'], landing)):
                        skipped[(host, 'duplicate, out-of-scope or excluded landing')] += 1
                        continue
                    landing_ids.add(identity)
                    chosen[host].append(row)
                print(host, len(chosen[host]), 'eligible unique pages', flush=True)
            if len(chosen[host]) != 50:
                raise RuntimeError(f'Insufficient verified pages: {host}: {len(chosen[host])}')
    rows = [row for triplet in zip(*(chosen[host] for host in HOSTS), strict=True) for row in triplet]
    counts = dict(Counter(row['application_id'] for row in rows))
    if len(counts) != 3 or set(counts.values()) != {50} or len({row['candidate_id'] for row in rows}) != 150:
        raise RuntimeError('Selection totals differ from authorization')
    audit_path = directory / 'audit.json'
    save_json(audit_path, {'scope': audit['scope'], 'manifest': audit['manifest'], 'protocol': VERSION,
        'verified_never_claimed_per_site': {host: len(rows) for host, rows in chosen.items()},
        'selection_exclusions': [{'site': host, 'reason': reason, 'count': count} for (host, reason), count in skipped.items()],
        'verified_distinct_landings': len(rows), 'replacement_allowed': False, 'dispatches': 0})
    save_json(directory / 'cohort.json', {'schema_version': 'consumer-multibatch-cohort', 'selection_protocol': VERSION,
        'scope': audit['scope'], 'manifest': audit['manifest'], 'pool': scope['pool'], 'registry': scope['registry'],
        'consumer_ledger': scope['consumer_db'], 'denominator': len(rows), 'site_denominators': counts,
        'selected': [dict(row, order=index) for index, row in enumerate(rows, 1)], 'audit': reference(audit_path),
        'replacement_allowed': False})
    print(json.dumps(counts), flush=True)


if __name__ == '__main__':
    prepare()
