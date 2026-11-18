import argparse
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime
from pathlib import Path

from webcollect.batch_core import load_json, save_json
from webcollect.site_workers import fixed_consumer_plan, launch

from select_pages import ROOT, RUN, SCOPE


def before(scope):
    result = {}
    for role in ('pool', 'consumer_db', 'producer_db', 'registry'):
        with closing(sqlite3.connect(Path(scope[role]).as_uri() + '?mode=ro', uri=True)) as connection:
            if role == 'pool':
                result['prior_claims'] = list(connection.execute('SELECT claim_id,state,stage,updated FROM candidate_claims ORDER BY claim_id'))
            elif role == 'registry':
                result['prior_attempts'] = list(connection.execute('SELECT attempt_id,status,finished_at FROM m4_attempts ORDER BY attempt_id'))
            else:
                result[role] = {'last_request_rowid': connection.execute('SELECT coalesce(max(rowid),0) FROM model_requests').fetchone()[0],
                    'unsettled': list(connection.execute("SELECT id,job_id,state,started,finished,usage,cost,error FROM model_requests WHERE state IN ('unknown','reserved') ORDER BY id"))}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('segment', type=int)
    args = parser.parse_args()
    if args.segment < 1:
        parser.error('positive segment required')
    directory = RUN / f'run-{args.segment:02d}'
    previous = RUN / f'run-{args.segment - 1:02d}' / 'prepared-plan.json' if args.segment > 1 else None
    if args.segment == 1:
        save_json(RUN / 'before.json', before(load_json(SCOPE)))
    plan = fixed_consumer_plan(SCOPE, RUN / 'selection/cohort.json', directory, expected_pages=150, resume_from=previous)
    save_json(directory / 'controller-start.json', {'pid': os.getpid(), 'plan_id': plan['plan_id'], 'started': datetime.now().astimezone().isoformat(),
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'workers': len(plan['workers'])})
    result = launch(plan)
    print(json.dumps({key: result.get(key) for key in ('plan_id', 'stop_reason', 'succeeded', 'report_integrity', 'unlaunched', 'error')}, ensure_ascii=False), flush=True)
    return 0 if result['succeeded'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
