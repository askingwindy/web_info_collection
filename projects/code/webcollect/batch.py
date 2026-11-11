"""Shared run configuration, budget ledger and diagnostics CLI."""
import argparse
import json
from pathlib import Path
import sqlite3

from .batch_core import BatchLedger, load_json, validate_config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('validate-config', 'init', 'status', 'recover'):
        p = sub.add_parser(command)
        p.add_argument('--config', required=True, type=Path)
        if command != 'validate-config':
            p.add_argument('--ledger', required=True, type=Path)
        if command == 'status':
            p.add_argument('--output', type=Path)
    smoke = sub.add_parser('model-smoke', help='One budgeted original-image/JSON/usage protocol check')
    smoke.add_argument('--config', required=True, type=Path)
    smoke.add_argument('--ledger', required=True, type=Path)
    smoke.add_argument('--image', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        config = validate_config(load_json(args.config))
        if args.command == 'validate-config':
            missing = []
            if config['model'] is not None and config['mode'] == 'real':
                from .model_credentials import credential
                try:
                    credential(config['model'])
                except ValueError as error:
                    missing.append(str(error))  # Resolver errors always suppress credential content.
            result = {'configuration': 'VALID', 'mode': config['mode'], 'missing': missing,
                      'model_enabled': config['model'] is not None,
                      'real_model_verified': False, 'fee_currency': config['budget'].get('currency')}
        elif args.command == 'model-smoke':
            from .model_gateway import ModelGateway
            from .batch_core import file_sha, BudgetStop, OutcomeUnknown
            ledger = BatchLedger(args.ledger, config)
            jid = ledger.enqueue('model-smoke', {'image': str(args.image.resolve()), 'sha256': file_sha(args.image),
                                               'protocol': 'image-json-usage'})
            job = ledger.claim('model-smoke', job_id=jid)
            if job:
                schema = {'type': 'object', 'properties': {'visible_observation': {'type': 'string'}},
                          'required': ['visible_observation'], 'additionalProperties': False}
                try:
                    result = ModelGateway(ledger).call(job, 'image-smoke', 'Describe visible content in the image in JSON.', schema,
                        images=[args.image], attempts=1, synthetic_response={'visible_observation': 'SYNTHETIC protocol response, not a visual judgment'})
                    ledger.finish(job, result=result)
                except BudgetStop:
                    ledger.finish(job, 'queued'); raise
                except Exception as error:
                    ledger.finish(job, 'review_required', error=type(error).__name__); raise
            result = ledger.summary()
        else:
            ledger = BatchLedger(args.ledger, config, initialize=args.command == 'init')
            if args.command == 'recover':
                ledger.recover()
            result = ledger.export(args.output) if getattr(args, 'output', None) else ledger.summary()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
        print(json.dumps({'status': 'STOP', 'reason': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
