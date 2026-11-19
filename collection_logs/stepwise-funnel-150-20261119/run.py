"""Launch and account for the new fixed cohort through the original consumer CLI."""
import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

ARCHIVE = Path(__file__).resolve().parent
ROOT = ARCHIVE.parents[1]
PREVIOUS = 'stepwise-three-sites-150-20261118'
RUN = ROOT / 'results' / ARCHIVE.name
SCRIPTS = ARCHIVE.parent / PREVIOUS
sys.path.insert(0, str(SCRIPTS))

import select_pages
import launch_run
import observe_workers
import progress
import close_segment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('select','launch','observe','progress','watch','close'))
    parser.add_argument('segment', type=int, nargs='?', default=1)
    args = parser.parse_args()
    if args.action == 'select':
        select_pages.prepare(RUN, exclude_cohort=ROOT / 'results' / PREVIOUS / 'selection/cohort.json')
        rows = progress.read(RUN / 'selection/cohort.json')['selected']
        audit = progress.read(RUN / 'selection/audit.json')
        progress.write(ARCHIVE / 'selection.json', {
            'strategy':'stepwise','workers':20,'denominator':len(rows),
            'verified_never_claimed_per_site':audit['verified_never_claimed_per_site'],
            'verified_distinct_landings':audit['verified_distinct_landings'],'replacement_allowed':False,
            'pages':[dict(order=row['order'], candidate_id=row['candidate_id'], application_id=row['application_id'],
                          host=urlsplit(row['entry_url']).hostname,has_requested_goal=bool(row.get('requested_goal'))) for row in rows]})
        return 0
    for module in (launch_run, observe_workers, progress, close_segment):
        module.RUN = RUN
    progress.ARCHIVE = close_segment.ARCHIVE = ARCHIVE
    sys.argv[1:] = [str(args.segment)]
    if args.action == 'launch':
        return launch_run.main()
    if args.action == 'observe':
        return observe_workers.main(args.segment)
    if args.action == 'close':
        return close_segment.main()
    if args.action == 'watch':
        sys.argv.append('--watch')
    return progress.main()


if __name__ == '__main__':
    raise SystemExit(main())
