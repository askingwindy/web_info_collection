"""Bounded single-shot consumer effort A/B experiment over the formal entry.

Reuses candidate_consumer.consume(..., effort_profile=...), the original
CandidatePool, the shared consumer BatchLedger, the Runtime registry and the
current chain's allowed collections roots. Group A runs first_plan=high with
low branches, group B high/high; four workers per group start together, each
bound to one frozen candidate for exactly one collection session, then exits.

Deliberately NOT inherited from the 2026-11-06 ABCD driver: no per-group
50-page loop, no top-up or replacement candidates, no shared time-window
request attribution, no separate ledgers. Model attribution recomputes from
the ledger's own job/attempt records: group -> worker -> candidate -> claim ->
attempt/job -> request.
"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import random
import subprocess
import sys
import time

GROUP_PROFILES = {
    'A': {'first_plan': 'high', 'branch': 'low'},
    'B': {'first_plan': 'high', 'branch': 'high'},
}
ROSTER_SCHEMA = 'webcollect-consumer-ab-roster-1'
SLOT_STATE_SCHEMA = 'webcollect-consumer-ab-slot-state-1'
WORKERS_PER_GROUP = 4


def _save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError('Refusing to overwrite frozen experiment file: ' + str(path))
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8')
    return path


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def slot_name(group, index):
    return f'{group}{index}'


def source_digest():
    """Digest of the consumer/producer sources the roster is frozen against.

    Phase 2 compares this before launching: a changed tree needs a fresh
    review, not a silent roster replay.
    """
    import hashlib
    entries = []
    for package in ('webcollect',):
        base = Path(__file__).resolve().parent / package
        for path in sorted(base.rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.js'):
                entries.append((str(path.relative_to(base.parent)),
                                hashlib.sha256(path.read_bytes()).hexdigest()))
    for package_root in ('site-planner/site_planner',):
        base = Path(__file__).resolve().parents[2] / package_root
        if base.is_dir():
            for path in sorted(base.rglob('*.py')):
                if path.is_file():
                    entries.append((package_root + '/' + str(path.relative_to(base)),
                                    hashlib.sha256(path.read_bytes()).hexdigest()))
    return {'algorithm': 'sha256-per-file', 'files': len(entries),
            'digest': hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()}


def _bind_slot_objective(objectives_dir, slot, member, body):
    """Validate one <slot>.json evidence reference against the frozen candidate.

    Reuses the formal session_objective binding rules (identity match plus a
    five/long objective with an explicit effective-step minimum) against the
    pool row instead of a live claim; consume re-validates the same bytes
    against the real claim at run time.
    """
    from .session_objective import bind
    reference_path = Path(objectives_dir) / f'{slot}.json'
    if not reference_path.is_file():
        raise ValueError(f'Objectives directory misses the frozen binding for slot {slot}')
    binding = bind(_load(reference_path), {'candidate_id': member['candidate_id'],
                                           'version': member['version'], 'snapshot': body})
    objective = binding['objective']
    return {'reference_file': str(reference_path), 'objective': binding['reference'],
            'summary': {'minimum_effective_steps': objective['minimum_effective_steps'],
                        'preferred_band': objective['preferred_band'],
                        'kind': objective.get('kind')}}


def prepare(pool_path, draft_path, output_dir, *, seed=20261106, objectives_dir=None):
    """Freeze the eight-slot roster from a read-only candidate draft.

    The draft lists distinct published Table2 candidates; this stage only
    records identity, pairing and effort assignment. No claim, no page visit,
    no model call happens here. An objectives directory freezes one validated
    session_objective evidence reference per slot.
    """
    from site_planner.candidate_pool import CandidatePool
    pool = CandidatePool(pool_path)
    draft = _load(draft_path)
    if draft.get('schema_version') != 'webcollect-consumer-ab-draft-1' or not isinstance(draft.get('candidates'), list):
        raise ValueError('Draft must use webcollect-consumer-ab-draft-1 with a candidates list')
    rows = pool.rows(protocols=('webcollect-data-candidate-2',))
    by_id = {row['candidate_id']: row for row in rows}
    selected = []
    for entry in draft['candidates']:
        cid = entry.get('candidate_id')
        row = by_id.get(cid)
        if row is None:
            raise ValueError(f'Draft candidate not in published Table2 pool: {cid}')
        body = row.get('candidate') or {}
        if entry.get('version') is not None and entry['version'] != row.get('version'):
            raise ValueError(f'Draft candidate version differs from pool: {cid}')
        selected.append({'candidate_id': cid, 'version': row.get('version'),
                         'application_id': row.get('application_id'),
                         'entry_url': body.get('entry_url'),
                         'requested_goal': body.get('requested_goal'),
                         'candidate_kind': body.get('candidate_kind'),
                         'capability_class': entry.get('capability_class'),
                         'category_hint': entry.get('category_hint'),
                         'note': entry.get('note')})
    if len({s['candidate_id'] for s in selected}) != len(selected):
        raise ValueError('Draft candidates must be distinct')
    if len(selected) != 2 * WORKERS_PER_GROUP:
        raise ValueError(f'Draft must carry exactly {2 * WORKERS_PER_GROUP} candidates, got {len(selected)}')
    # Pairing: the draft supplies its pairing order (adjacent pairs), the seed
    # only decides which member of each pair lands in A first.
    rng = random.Random(seed)
    slots = []
    for pair_index in range(WORKERS_PER_GROUP):
        pair = selected[2 * pair_index:2 * pair_index + 2]
        if rng.random() < 0.5:
            pair = pair[::-1]
        for group, member in zip(('A', 'B'), pair):
            worker = f'consumer-ab-{slot_name(group, pair_index + 1)}'
            slot = {'slot': slot_name(group, pair_index + 1), 'group': group,
                    'worker_id': worker, 'request_prefix': f'{worker}/r01',
                    'effort_profile': deepcopy(GROUP_PROFILES[group]),
                    'candidate': member}
            if objectives_dir is not None:
                body = next(r.get('candidate') or {} for r in rows if r['candidate_id'] == member['candidate_id'])
                slot['session_objective'] = _bind_slot_objective(objectives_dir, slot['slot'], member, body)
            slots.append(slot)
    roster = {'schema_version': ROSTER_SCHEMA, 'pool': str(Path(pool_path).resolve()),
              'output_dir': str(Path(output_dir).resolve()), 'seed': seed,
              'source_digest': source_digest(),
              'group_profiles': deepcopy(GROUP_PROFILES), 'slots': slots,
              'prepared_at': time.time(),
              'policy': 'One claim and at most one formal collection session per slot; '
                        'failure, unclaimable or UNKNOWN never takes a second candidate; '
                        'restart reads state only and never re-dispatches.'}
    return slots, roster


def _slot_state_path(output_dir, slot):
    return Path(output_dir) / 'slots' / f'{slot}.json'


def _existing_state(output_dir, slot):
    path = _slot_state_path(output_dir, slot)
    if not path.exists():
        return None
    state = _load(path)
    if state.get('schema_version') != SLOT_STATE_SCHEMA:
        raise ValueError('Unknown slot state schema: ' + str(path))
    return state


def worker(roster, slot_name_value, *, config, ledger_path, registry, policy_path,
           history_set, qc_policy=None, skip_wechat_articles=False, session_objective=None):
    """Run one slot to its single collection session, then stop.

    A slot with existing state is read-only: the restart verifies the original
    receipt and never dispatches a new collection.
    """
    import asyncio
    from site_planner.candidate_pool import CandidatePool, VERSION2
    from webcollect.batch_core import BatchLedger, BudgetStop, OutcomeUnknown
    from webcollect.candidate_consumer import consume
    slot = next((s for s in roster['slots'] if s['slot'] == slot_name_value), None)
    if slot is None:
        raise ValueError('Roster slot not found: ' + slot_name_value)
    output_dir = Path(roster['output_dir'])
    state_path = _slot_state_path(output_dir, slot['slot'])
    if state_path.exists():
        prior = _load(state_path)
        return {'slot': slot['slot'], 'state': 'already_processed', 'prior': prior,
                'dispatched': False}
    pool = CandidatePool(roster['pool'])
    ledger = BatchLedger(ledger_path, _load(config))
    claim = pool.claim_next(slot['worker_id'], slot['request_prefix'],
                            candidate_id=slot['candidate']['candidate_id'], protocols=(VERSION2,))
    if claim.get('state') in ('EMPTY', 'ALREADY_CLAIMED'):
        # The outcome is always a record so the report reader never has to
        # branch on shape; the unclaimable reason is preserved verbatim.
        _save(state_path, {'schema_version': SLOT_STATE_SCHEMA, 'slot': slot['slot'],
                           'group': slot['group'], 'candidate_id': slot['candidate']['candidate_id'],
                           'phase': 'claim', 'outcome': {'state': claim['state'],
                                                         'reason': 'Frozen candidate not claimable; no replacement'},
                           'claim_id': None,
                           'finished_at': time.time(), 'dispatched': False})
        return {'slot': slot['slot'], 'state': claim['state'], 'dispatched': False}
    group_output = output_dir / 'collections' / slot['group']
    started = time.time()
    try:
        result = asyncio.run(consume(pool, claim, ledger, output=str(group_output),
                                     registry=registry, policy=policy_path, history_set=history_set,
                                     qc_policy=qc_policy,
                                     **({'skip_wechat_articles': True} if skip_wechat_articles else {}),
                                     **({'session_objective': session_objective} if session_objective is not None else {}),
                                     effort_profile=slot['effort_profile']))
        outcome = {'state': result.get('state'), 'stage': result.get('stage'),
                   'saved': bool(result.get('saved')), 'result': result}
    except (BudgetStop, OutcomeUnknown) as error:
        current = pool.get_claim(claim['claim_id'])
        if current['state'] == 'consuming':
            pool.finish(claim, state='reconcile', stage=current['stage'], reason=str(error))
        outcome = {'state': 'reconcile', 'error_type': type(error).__name__, 'reason': str(error)}
    except BaseException as error:
        outcome = {'state': 'failed', 'error_type': type(error).__name__, 'reason': str(error)[:500]}
        # Mirror the ordinary consumer runner's failure close-out: a claim that
        # never reached consume's own reconciliation is finished explicitly,
        # never left for an accidental re-dispatch.
        current = pool.get_claim(claim['claim_id'])
        if current['state'] == 'consuming':
            pool.finish(claim, state='failed', stage=current['stage'],
                        reason=type(error).__name__ + ': ' + str(error)[:300])
    current = pool.get_claim(claim['claim_id'])
    _save(state_path, {'schema_version': SLOT_STATE_SCHEMA, 'slot': slot['slot'],
                       'group': slot['group'], 'worker_id': slot['worker_id'],
                       'candidate_id': slot['candidate']['candidate_id'],
                       'claim_id': claim['claim_id'], 'phase': 'consumed',
                       'outcome': outcome, 'claim_state': current['state'],
                       'claim_stage': current.get('stage'),
                       'effort_profile': slot['effort_profile'],
                       'started_at': started, 'finished_at': time.time(), 'dispatched': True})
    return {'slot': slot['slot'], **outcome}


def _slot_requests(ledger_path, claim):
    """Exact model attribution from the ledger's own records.

    The claim's binding records the bound formal attempt; native requests carry
    that attempt id in request_json.dispatch_attempt_id. No time windows.
    Reserved-but-never-dispatched rows are reported separately: only HTTP
    dispatches count as real requests.
    """
    import sqlite3
    binding = claim.get('binding') or {}
    attempt_id = binding.get('attempt_id')
    if not attempt_id:
        return {'requests': [], 'reserved_not_dispatched': []}
    con = sqlite3.connect(f"file:{Path(ledger_path).resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id,job_id,purpose,state,usage,error,started,finished,"
            "json_extract(request_json,'$.reasoning_effort') AS effort,"
            "json_extract(request_json,'$.dispatch_attempt_id') AS attempt,"
            "coalesce(json_extract(request_json,'$.http_dispatch'),1) AS http_dispatch "
            "FROM model_requests WHERE json_extract(request_json,'$.dispatch_attempt_id')=? "
            "ORDER BY started", (attempt_id,)).fetchall()
        all_rows = [dict(row) for row in rows]
        dispatched = [row for row in all_rows if row['http_dispatch']]
        reserved = [row for row in all_rows if not row['http_dispatch']]
        return {'requests': dispatched, 'reserved_not_dispatched': reserved}
    finally:
        con.close()


def _outcome_record(state):
    """Slot outcomes are records; a bare string is normalized, never trusted."""
    outcome = (state or {}).get('outcome') if isinstance(state, dict) else None
    if isinstance(outcome, dict):
        return outcome
    if isinstance(outcome, str) and outcome:
        return {'state': outcome}
    return {}


def report(roster, ledger_path, experiment_dir):
    """Per-slot outcomes plus group attribution from original ledger records."""
    from site_planner.candidate_pool import CandidatePool
    pool = CandidatePool(roster['pool'])
    slots = []
    for slot in roster['slots']:
        state = _existing_state(roster['output_dir'], slot['slot'])
        entry = {'slot': slot['slot'], 'group': slot['group'],
                 'candidate_id': slot['candidate']['candidate_id'],
                 'worker_id': slot['worker_id']}
        if state is None:
            entry['status'] = 'not_run'
        else:
            outcome = _outcome_record(state)
            claim = pool.get_claim(state['claim_id']) if state.get('claim_id') else None
            entry.update(status='processed', claim_state=state.get('claim_state'),
                         outcome=outcome, saved=bool(outcome.get('saved')))
            if claim:
                attributed = _slot_requests(ledger_path, claim)
                entry['requests'] = attributed['requests']
                entry['reserved_not_dispatched'] = attributed['reserved_not_dispatched']
                entry['request_count'] = len(entry['requests'])
                entry['request_states'] = {row['state']: sum(1 for r in entry['requests'] if r['state'] == row['state'])
                                           for row in entry['requests']}
        slots.append(entry)
    summary = {}
    for group, profile in GROUP_PROFILES.items():
        rows = [s for s in slots if s['group'] == group]
        outcomes = [_outcome_record({'outcome': s.get('outcome')}) for s in rows]
        summary[group] = {'profile': profile, 'denominator': len(rows),
                          'claimed': sum(1 for s in rows if s.get('status') == 'processed'),
                          'saved': sum(1 for s in rows if s.get('saved')),
                          'requests': sum(s.get('request_count', 0) for s in rows),
                          'unknown_requests': sum(1 for s in rows for r in s.get('requests', []) if r['state'] == 'unknown'),
                          'statuses': {st: sum(1 for o in outcomes if o.get('state') == st)
                                       for st in {str(o.get('state')) for o in outcomes} - {'None'}}}
    return {'schema_version': 'webcollect-consumer-ab-report-1', 'slots': slots, 'groups': summary,
            'generated_at': time.time()}


def adjust_concurrency(ledger_path, config_path, *, target, authorization):
    """Set a live consumer limit (None means worker-controlled), not config."""
    from webcollect.batch_core import BatchLedger
    from webcollect.planning import object_sha256
    config = _load(config_path)
    ledger = BatchLedger(ledger_path, config)  # Validates against the frozen row first.
    if target is not None and (type(target) is not int or target < 1):
        raise ValueError('Target concurrency must be a positive integer or None')
    if not isinstance(authorization, str) or not authorization.strip():
        raise ValueError('Consumer concurrency adjustment requires its reason')
    with ledger.transaction() as con:
        ledger.require_consumer_ledger(con)
        row = con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()
        if json.loads(row[0]) != config:
            raise ValueError('Ledger configuration changed during adjustment')
        before = ledger._job_concurrency_limit(con)
        changed = before != target or ledger.consumer_concurrency(con) is None
        if changed:
            ledger.event(con, 'consumer_concurrency', {
                'schema_version': 'webcollect-consumer-concurrency-1',
                'ledger': str(ledger.path), 'run_id': config['run_id'],
                'config_sha256': object_sha256(config),
                'max_concurrent_jobs': target,
                'before': {'max_concurrent_jobs': before},
                'after': {'max_concurrent_jobs': target},
                'authorization': authorization})
    # Existing workers using this implementation read the next claim's setting
    # from SQLite. Old Python processes retain their loaded implementation.
    return {'ledger': str(ledger.path), 'before': before, 'after': target, 'changed': changed,
            'configuration_changed': False,
            'worker_config_required': str(Path(config_path).resolve())}


def launch(roster, *, config, ledger_path, registry, policy_path, history_set,
           qc_policy=None, session_objective=None, python=None, experiment_dir=None):
    """Start all eight single-slot workers as one simultaneous launch window.

    session_objective is either a shared reference-file path or a
    {slot name: reference-file path} map; a slot frozen with its own objective
    in the roster always wins over any shared value.
    """
    import os
    python = python or sys.executable
    roster_path = Path(experiment_dir) / 'roster.json'
    # The module CLI takes --pool before the subcommand; every worker shares
    # the roster's frozen pool binding, and PYTHONPATH must reach the child.
    command_base = [python, '-m', 'webcollect.consumer_ab', '--pool', str(roster['pool']),
                    'worker', '--roster', str(roster_path), '--config', config,
                    '--ledger', ledger_path, '--registry', registry,
                    '--policy', policy_path, '--history-set', history_set]
    per_slot = session_objective if isinstance(session_objective, dict) else {}
    shared = session_objective if isinstance(session_objective, str) else None
    environment = dict(os.environ)
    existing = environment.get('PYTHONPATH')
    package_roots = [str(Path(__file__).resolve().parents[2]),
                     str(Path(__file__).resolve().parents[2] / 'site-planner'),
                     str(Path(__file__).resolve().parents[2] / 'quality-inspector')]
    environment['PYTHONPATH'] = os.pathsep.join(
        ([existing] if existing else []) + [root for root in package_roots if root not in (existing or '')])
    processes = {}
    started = time.time()
    for slot in roster['slots']:
        command = list(command_base)
        objective_file = ((slot.get('session_objective') or {}).get('reference_file')
                          or per_slot.get(slot['slot']) or shared)
        if objective_file:
            command += ['--session-objective', str(objective_file)]
        if qc_policy:
            command += ['--qc-policy', qc_policy]
        processes[slot['slot']] = subprocess.Popen(
            command + ['--slot', slot['slot']], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=environment)
    logs = {}
    for name, process in processes.items():
        output, _ = process.communicate()
        logs[name] = {'returncode': process.returncode, 'output': (output or '')[-4000:]}
    return {'launched': sorted(processes), 'started_at': started,
            'finished_at': time.time(), 'logs': logs}


def _slot_objective(roster, slot_name_value, supplied_file):
    """Reconcile the CLI objective file with the roster-frozen binding.

    The frozen reference wins when both are present; a differing CLI file is an
    error, never a silent override of the frozen experiment goal.
    """
    slot = next((s for s in roster['slots'] if s['slot'] == slot_name_value), None)
    frozen = ((slot or {}).get('session_objective') or {}).get('objective')
    supplied = _load(supplied_file) if supplied_file else None
    if frozen is not None and supplied is not None and supplied != frozen:
        raise ValueError('Session objective differs from the roster-frozen binding: ' + slot_name_value)
    return supplied if supplied is not None else frozen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--pool', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare_p = sub.add_parser('prepare')
    prepare_p.add_argument('--draft', required=True)
    prepare_p.add_argument('--output-dir', required=True)
    prepare_p.add_argument('--seed', type=int, default=20261106)
    prepare_p.add_argument('--objectives-dir',
                           help='Directory of <slot>.json evidence references to freeze per slot')
    prepare_p.add_argument('--roster-out', required=True)
    worker_p = sub.add_parser('worker')
    for name in ('roster', 'config', 'ledger', 'registry', 'policy', 'history-set'):
        worker_p.add_argument('--' + name, required=True)
    worker_p.add_argument('--qc-policy')
    worker_p.add_argument('--session-objective',
                          help='Frozen session objective binding reference shared by the slots')
    worker_p.add_argument('--slot', required=True)
    run_p = sub.add_parser('run')
    for name in ('roster', 'config', 'ledger', 'registry', 'policy', 'history-set'):
        run_p.add_argument('--' + name, required=True)
    run_p.add_argument('--qc-policy')
    run_p.add_argument('--session-objective',
                       help='Frozen session objective binding reference passed to every worker')
    status_p = sub.add_parser('status')
    status_p.add_argument('--roster', required=True)
    status_p.add_argument('--ledger')
    status_p.add_argument('--report-out')
    adjust_p = sub.add_parser('adjust-concurrency')
    adjust_p.add_argument('--config', required=True)
    adjust_p.add_argument('--ledger', required=True)
    concurrency = adjust_p.add_mutually_exclusive_group(required=True)
    concurrency.add_argument('--target', type=int)
    concurrency.add_argument('--unlimited', action='store_true', help='let launched consumer workers determine concurrency')
    adjust_p.add_argument('--authorization', required=True)
    args = parser.parse_args(argv)

    if args.command == 'prepare':
        slots, roster = prepare(args.pool, args.draft, args.output_dir, seed=args.seed,
                                objectives_dir=args.objectives_dir)
        _save(args.roster_out, roster)
        print(json.dumps({'roster': args.roster_out, 'slots': [s['slot'] for s in slots]}, ensure_ascii=False))
    elif args.command == 'worker':
        roster = _load(args.roster)
        result = worker(roster, args.slot, config=args.config, ledger_path=args.ledger,
                        registry=args.registry, policy_path=args.policy, history_set=args.history_set,
                        qc_policy=args.qc_policy,
                        session_objective=_slot_objective(roster, args.slot, args.session_objective))
        print(json.dumps(result, ensure_ascii=False, default=str))
    elif args.command == 'run':
        roster = _load(args.roster)
        launch_result = launch(roster, config=args.config, ledger_path=args.ledger,
                               registry=args.registry, policy_path=args.policy,
                               history_set=args.history_set, qc_policy=args.qc_policy,
                               session_objective=args.session_objective,
                               experiment_dir=Path(args.roster).parent)
        summary = report(roster, args.ledger, Path(args.roster).parent)
        out = Path(args.roster).parent / 'run-report.json'
        if out.exists():
            raise ValueError('Refusing to overwrite the single-shot run report')
        _save(out, {'launch': launch_result, 'report': summary})
        print(json.dumps({'report': str(out), 'groups': summary['groups']}, ensure_ascii=False, default=str))
    elif args.command == 'status':
        roster = _load(args.roster)
        summary = report(roster, args.ledger, Path(args.roster).parent) if args.ledger else {
            'slots': [{'slot': s['slot'], 'status': 'processed' if _existing_state(roster['output_dir'], s['slot']) else 'not_run'}
                      for s in roster['slots']]}
        text = json.dumps(summary, ensure_ascii=False, indent=1, default=str)
        if args.report_out:
            Path(args.report_out).write_text(text, encoding='utf-8')
        print(text)
    elif args.command == 'adjust-concurrency':
        print(json.dumps(adjust_concurrency(args.ledger, args.config, target=args.target,
                                            authorization=args.authorization), ensure_ascii=False))


if __name__ == '__main__':
    main()
