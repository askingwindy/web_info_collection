import argparse
import asyncio
import json
from pathlib import Path
import sqlite3

from webcollect.batch_core import BatchLedger, load_json
from .pipeline import discover, probe
from .reviews import prepare_review, import_review


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'pool':
        from .site_pool import main as pool_main
        return pool_main(argv[1:])
    parser = argparse.ArgumentParser(description='Automatic website discovery and representative-page screening')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('pool', help='Shared discovery pool: init, import-events, stats, alias, merge, export')
    p = sub.add_parser('discover-ai', help='Category-only GLM search and read-only discovery; no collection')
    for name in ('config', 'pool', 'ledger', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--category', action='append', required=True, dest='categories')
    p.add_argument('--target', type=int, default=10)
    p.add_argument('--per-category', type=int, default=2)
    p.add_argument('--max-rounds', type=int, default=3)
    p.add_argument('--max-searches', type=int, default=20)
    p.add_argument('--search-engine', choices=['search_std', 'search_pro'], default='search_std')
    for command in ('discover', 'probe'):
        p = sub.add_parser(command)
        p.add_argument('--config', type=Path, required=True)
        p.add_argument('--ledger', type=Path, required=True)
        p.add_argument('--output', type=Path, required=True)
        if command == 'discover':
            p.add_argument('--sources', type=Path, required=True)
        else:
            p.add_argument('--candidates', type=Path, required=True)
    p = sub.add_parser('prepare-review', help='Freeze original capability evidence and an empty review template')
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--capability-id', action='append', dest='capability_ids')
    p = sub.add_parser('import-review', help='Import completed visual observations as new evidence-bound capabilities')
    p.add_argument('--packet', type=Path, required=True)
    p.add_argument('--review', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'discover-ai':
            from .discovery_agent import discover_ai
            result = asyncio.run(discover_ai(load_json(args.config), pool_path=args.pool,
                ledger_path=args.ledger, output=args.output, categories=args.categories,
                target=args.target, per_category=args.per_category,
                max_rounds=args.max_rounds, max_searches=args.max_searches, search_engine=args.search_engine))
        elif args.command == 'prepare-review':
            result = prepare_review(args.catalog, args.output, capability_ids=args.capability_ids)
        elif args.command == 'import-review':
            result = import_review(args.packet, args.review, args.output)
        else:
            ledger = BatchLedger(args.ledger, load_json(args.config))
            result = discover(ledger, args.sources, args.output) if args.command == 'discover' else asyncio.run(
                probe(ledger, args.candidates, args.output))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == 'discover-ai' and result.get('status') != 'TARGET_REACHED':
            return 2
        return 0 if not result.get('stopped') else 2
    except (ValueError, OSError, KeyError, TypeError,sqlite3.Error) as error:
        print(json.dumps({'status': 'STOP', 'reason': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
