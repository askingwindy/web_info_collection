"""从同一份运行范围启动一个 V2 角色。其余参数原样传给该角色的 CLI。"""
import argparse
import json
import os
from pathlib import Path
import shlex
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--scope', type=Path, required=True, help='本轮 scope.json，与监视器共用')
    parser.add_argument('--dry-run', action='store_true', help='只打印命令，不启动角色')
    parser.add_argument('role', choices=('producer', 'consumer', 'monitor'))
    args, extra = parser.parse_known_args()
    try:
        scope = json.loads(args.scope.read_text(encoding='utf-8'))
        if args.role == 'monitor':
            entry = ['webcollect.candidate_monitor']
            bound = {'--scope': str(args.scope.absolute())}
        elif args.role == 'producer':
            entry = ['site_planner.candidate_discovery', 'produce-entries']
            run_id, separator, batch_key = scope['batch'].rpartition('/entry-batch/')
            if not (separator and run_id and batch_key):
                raise ValueError('batch 应为 <生产者 run_id>/entry-batch/<batch-key>')
            if not args.dry_run:
                config = json.loads(Path(scope['producer_config']).read_text(encoding='utf-8'))
                if config['run_id'] != run_id:
                    raise ValueError('scope.batch 与生产者配置的 run_id 不一致')
            bound = {'--config': scope['producer_config'], '--ledger': scope['producer_db'],
                     '--pool': scope['pool'], '--history-set': scope['history_set'], '--batch-key': batch_key}
        else:
            entry = ['webcollect.candidate_consumer', 'run']
            bound = {'--protocol': 'entry', '--pool': scope['pool'], '--producer-batch': scope['batch'],
                     '--config': scope['consumer_config'], '--ledger': scope['consumer_db'],
                     '--output': scope['output'], '--registry': scope['registry'],
                     '--policy': scope['policy'], '--history-set': scope['history_set'],
                     '--worker-id': scope['consumer_worker'], '--request-prefix': scope['request_prefix']}
            if scope.get('qc_policy'):
                bound['--qc-policy'] = scope['qc_policy']
    except (KeyError, ValueError, OSError) as error:
        parser.error(str(error))
    for option in extra:
        if option.partition('=')[0] in bound:
            parser.error(f'{option.partition("=")[0]} 已由 scope 绑定')
    command = [sys.executable, '-B', '-u', '-m', *entry, *extra]
    for option, value in bound.items():
        command.extend([option, value])
    if args.dry_run:
        print(shlex.join(command))
        return
    projects = Path(__file__).resolve().parents[2]
    paths = [str(projects / package) for package in ('code', 'site-planner', 'quality-inspector')]
    if os.environ.get('PYTHONPATH'):
        paths.append(os.environ['PYTHONPATH'])
    os.execve(sys.executable, command, {**os.environ, 'PYTHONPATH': os.pathsep.join(paths)})


if __name__ == '__main__':
    main()
