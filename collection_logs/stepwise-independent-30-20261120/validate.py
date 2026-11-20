"""使用既有三站消费者和核账入口，单独冻结与核账第二个 30 页验证批次。"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parent
ROOT = ARCHIVE.parents[1]
RUN = ROOT / 'results' / ARCHIVE.name
PREVIOUS = 'stepwise-save30-20261120'
sys.path.insert(0, str(ARCHIVE.parent / PREVIOUS))
import run as campaign

campaign.ARCHIVE, campaign.RUN = ARCHIVE, RUN
from account import accounting
from progress import read, write
from site_planner.candidate_pool import entry_identity


def identities(cohort_path):
    rows = read(cohort_path)['selected']
    return ({row['candidate_id'] for row in rows},
            {entry_identity(read(Path(row['entry_http']['path']))['landed_uri']) for row in rows})


def freeze():
    cohort = RUN / 'selection/cohort.json'
    if not cohort.is_file():
        campaign.select()
    new_ids, new_landings = identities(cohort)
    comparisons = {}
    for name in ('stepwise-three-sites-150-20261118', PREVIOUS):
        old_ids, old_landings = identities(ROOT / 'results' / name / 'selection/cohort.json')
        comparisons[name] = {'candidate_overlap': len(new_ids & old_ids),
                             'verified_landing_overlap': len(new_landings & old_landings)}
    if len(new_ids) != 30 or len(new_landings) != 30 or any(any(v.values()) for v in comparisons.values()):
        raise ValueError('候选或实际落地与独立批次要求不符')
    audit_path = ARCHIVE / 'cohort-check.json'
    setup = {'selected_at': read(ARCHIVE / 'selection.json')['selected_at'],
             'strategy': 'stepwise', 'denominator': 30, 'target_saves': 6, 'target_palace_saves': 1,
             'unique_landings': len(new_landings), 'comparison': comparisons, 'workers': 20}
    if audit_path.is_file():
        frozen = read(audit_path)
        if any(frozen.get(key) != value for key, value in setup.items()):
            raise ValueError('本次复核与领取前冻结的独立批次不一致')
        setup = frozen
    else:
        setup['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        write(audit_path, setup)
    print(json.dumps(setup, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('select', 'launch', 'observe', 'status', 'final'))
    parser.add_argument('segment', type=int, default=1, nargs='?')
    args = parser.parse_args()
    if args.action == 'select':
        freeze()
    elif args.action == 'launch':
        read(ARCHIVE / 'cohort-check.json')
        raise SystemExit(campaign.collect(args.segment))
    elif args.action == 'observe':
        import observe_workers
        observe_workers.RUN = RUN
        observe_workers.main(args.segment)
    else:
        result = accounting(final=args.action == 'final')
        if args.action == 'final':
            write(ARCHIVE / 'accounting.json', result)
        print(json.dumps({k: result[k] for k in ('at','per_site','claim_states','observed_peak',
                          'integrity','target_passed','funnel') if k in result}, ensure_ascii=False))
