"""固定上一份名单中各站最先出现的十个未领页，通过正式消费者执行。"""
import argparse
import os
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ARCHIVE = Path(__file__).resolve().parent
ROOT = ARCHIVE.parents[1]
RUN = ROOT / 'results' / ARCHIVE.name
OLD = ROOT / 'results/stepwise-funnel-150-20261119/selection/cohort.json'
sys.path.insert(0, str(ARCHIVE.parent / 'stepwise-three-sites-150-20261118'))
from launch_run import before
from select_pages import HOSTS, SCOPE

from site_planner.candidate_pool import entry_identity
from webcollect.batch_core import load_json, save_json
from webcollect.candidate_cohort import ReadOnlyLedger, inspect_rows, reference
from webcollect.candidate_consumer import preflight_candidate_sources
from webcollect.site_workers import fixed_consumer_plan, launch
from webcollect.stepwise import require_image_capacity


def select():
    old = load_json(OLD)
    scope = load_json(SCOPE)
    with closing(sqlite3.connect(Path(scope['pool']).as_uri() + '?mode=ro', uri=True)) as db:
        claimed = {r[0] for r in db.execute('SELECT DISTINCT candidate_id FROM candidate_claims')}
    groups = {host: [] for host in HOSTS}
    for row in old['selected']:
        host = urlsplit(row['entry_url']).hostname.removeprefix('www.')
        if row['candidate_id'] not in claimed and len(groups[host]) < 10:
            groups[host].append(row)
    if any(len(group) != 10 for group in groups.values()):
        raise ValueError('原名单不足每站十个未领页')
    selected = [row for triple in zip(*groups.values(), strict=True) for row in triple]
    ids = [row['candidate_id'] for row in selected]
    _, inspected, _ = inspect_rows(SCOPE, candidate_ids=ids)
    current = {r['candidate_id']: r for r in inspected}
    landings = set()
    for old_row in selected:
        row = current[old_row['candidate_id']]
        if not row['eligible'] or any(row[k] != old_row[k] for k in ('entry_url', 'version', 'body', 'application_id')):
            raise ValueError('候选复核失败 ' + row['candidate_id'])
        preflight_candidate_sources(scope['registry'], row['sources'])
        landing = entry_identity(load_json(row['entry_http']['path'])['landed_uri'])
        if landing in landings:
            raise ValueError('重复实际落地 ' + landing)
        landings.add(landing)
    directory = RUN / 'selection'
    directory.mkdir(parents=True, exist_ok=False)
    audit = {'source': str(OLD.relative_to(ROOT)), 'selection': '各站按原序取前十个从未领取的候选',
             'selected_at': datetime.now().astimezone().isoformat(), 'workers': 20,
             'denominator': 30, 'per_site': {host: len(group) for host, group in groups.items()},
             'target_saved': 6, 'target_palace_saved': 1, 'replacement_allowed': False,
             'pages': [{'order': n, 'original_order': r['order'], 'candidate_id': r['candidate_id'],
                        'host': urlsplit(r['entry_url']).hostname, 'entry_url': r['entry_url']}
                       for n, r in enumerate(selected, 1)]}
    save_json(directory / 'audit.json', audit)
    save_json(ARCHIVE / 'selection.json', audit)
    rows = [dict(current[cid], order=n) for n, cid in enumerate(ids, 1)]
    save_json(directory / 'cohort.json', {**old, 'denominator': len(rows), 'selected': rows,
              'audit': reference(directory / 'audit.json'),
              'site_denominators': dict(Counter(r['application_id'] for r in rows))})


def collect(segment):
    scope = load_json(SCOPE)
    ledger = ReadOnlyLedger(scope['consumer_db'], load_json(scope['consumer_config']))
    require_image_capacity(ledger.config, ledger=ledger)
    root = RUN / f'run-{segment:02d}'
    previous = RUN / f'run-{segment-1:02d}/prepared-plan.json' if segment > 1 else None
    plan = fixed_consumer_plan(SCOPE, RUN / 'selection/cohort.json', root,
                               expected_pages=30, resume_from=previous)
    save_json(root / 'segment-before.json' if previous else RUN / 'before.json', before(scope))
    save_json(root / 'controller-start.json', {'pid': os.getpid(), 'plan_id': plan['plan_id'],
              'started': datetime.now().astimezone().isoformat(), 'workers': len(plan['workers'])})
    result = launch(plan)
    print({k: result.get(k) for k in ('plan_id','stop_reason','succeeded','report_integrity')}, flush=True)
    return 0 if result['succeeded'] else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('select', 'launch', 'observe'))
    parser.add_argument('segment', type=int, nargs='?', default=1)
    args = parser.parse_args()
    if args.action == 'select':
        select()
    elif args.action == 'launch':
        raise SystemExit(collect(args.segment))
    else:
        import observe_workers
        observe_workers.RUN = RUN
        observe_workers.main(args.segment)
