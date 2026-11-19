import argparse
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime
from pathlib import Path

from webcollect.batch_core import load_json, save_json
from webcollect.candidate_cohort import ReadOnlyLedger
from webcollect.site_workers import fixed_consumer_plan, launch
from webcollect.stepwise import require_image_capacity

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
                    'last_job_rowid': connection.execute('SELECT coalesce(max(rowid),0) FROM jobs').fetchone()[0],
                    'unsettled': list(connection.execute("SELECT id,job_id,state,started,finished,usage,cost,error FROM model_requests WHERE state IN ('unknown','reserved') ORDER BY id"))}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('segment', type=int)
    args = parser.parse_args()
    if args.segment < 1:
        parser.error('positive segment required')
    scope = load_json(SCOPE)
    ledger = ReadOnlyLedger(scope['consumer_db'], load_json(scope['consumer_config']))
    require_image_capacity(ledger.config, ledger=ledger)
    directory = RUN / f'run-{args.segment:02d}'
    previous = RUN / f'run-{args.segment - 1:02d}' / 'prepared-plan.json' if args.segment > 1 else None
    if args.segment == 1:
        save_json(RUN / 'before.json', before(scope))
    if args.segment > 1:
        verified = load_json(RUN / 'image-repair-20261119/live-validation/receipt.json')
        if verified['status'] != 'PASS' or not verified['prior_claims_attempts_and_unsettled_unchanged']:
            raise ValueError('Real writeback and judgement validation is missing or unsuccessful')
        with ledger.connect() as connection:
            pairs = set(connection.execute("""SELECT json_extract(j.payload,'$.phase'),json_extract(r.request_json,'$.image_count')
                FROM model_requests r JOIN jobs j ON r.job_id=j.id WHERE json_extract(j.payload,'$.attempt_id')=?
                AND r.state='succeeded' AND json_extract(r.request_json,'$.http_dispatch')=1""",
                (verified['session_id'],)).fetchall())
        if not {('writeback', 2), ('judgement', 3)} <= {tuple(pair) for pair in pairs}:
            raise ValueError('Real 2/3-image requests not proven in the bound consumer ledger')
    plan = fixed_consumer_plan(SCOPE, RUN / 'selection/cohort.json', directory, expected_pages=150, resume_from=previous)
    if previous:
        save_json(directory / 'segment-before.json', before(scope))
    save_json(directory / 'controller-start.json', {'pid': os.getpid(), 'plan_id': plan['plan_id'], 'started': datetime.now().astimezone().isoformat(),
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'workers': len(plan['workers']),
        'local_product_changes': subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',
            'projects/code/webcollect','projects/site-planner/site_planner'], cwd=ROOT, text=True).splitlines()})
    result = launch(plan)
    print(json.dumps({key: result.get(key) for key in ('plan_id', 'stop_reason', 'succeeded', 'report_integrity', 'unlaunched', 'error')}, ensure_ascii=False), flush=True)
    return 0 if result['succeeded'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
