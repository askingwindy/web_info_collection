"""Offline integration close-out for the no-version round (2026-11-11 r02).

Offline only: no real GLM, no browser. The consumer CLI runs as a real
subprocess against an empty pool with the full original wiring (real-mode
config, current chain, site failure guard, RuntimeStore policy); its model
endpoint points at an unroutable host and is never called because the pool
is empty. Strategy build entries run through task_generation.generate for
both frozen strategies. The DB switch script runs in dry-run on a copied
backup. Unavailable real chains are recorded NOT_RUN, never claimed passed.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'projects/code'), str(ROOT / 'projects/site-planner'),
                str(ROOT / 'projects/quality-inspector')]
PY = str(ROOT / 'projects/code/.venv/bin/python')
ENV = {**os.environ, 'PYTHONPATH': 'projects/code:projects/site-planner:projects/quality-inspector',
       'CONTROLLED_UNUSED_KEY': 'offline-test-only'}
OUT = ROOT / 'verify_results/noversion-offline-integration-20261111-r02'
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
report = {}


def step(name, ok, detail):
    report[name] = {'ok': bool(ok), 'detail': detail}
    print(('PASS ' if ok else 'FAIL ') + name, str(detail)[:400], flush=True)


def make_real_config():
    cfg = json.loads((ROOT / 'projects/code/config/batch-synthetic.json').read_text())
    cfg['mode'] = 'real'
    cfg['model'].update(provider='chat-completions', endpoint='https://model.invalid',
                        api_key_env='CONTROLLED_UNUSED_KEY')
    cfg['model']['reserve_cost_micros'] = 1
    cfg['model']['rates'].update(input=1, output=1)
    cfg['budget'].update(max_model_cost_micros=10000, currency='CNY',
                         min_model_interval_seconds=1, min_domain_interval_seconds=1)
    cfg['budget']['max_concurrent_jobs'] = 1
    return cfg


# 1. consumer CLI subprocess, empty pool -> honest empty inventory, SIGINT stop
consumer_work = OUT / 'consumer-work'
consumer_work.mkdir()
try:
    from site_planner.site_pool import SitePool
    from site_planner.candidate_pool import CandidatePool
    from webcollect.batch_core import BatchLedger
    from webcollect.current_chain import initialize_chain
    from webcollect.runtime import RuntimeStore
    from webcollect.site_failure_stop import SiteFailureStore
    SitePool(consumer_work / 'pool.sqlite3', initialize=True)
    CandidatePool(consumer_work / 'pool.sqlite3', install=True)
    chain = consumer_work / 'chain.json'
    registry = consumer_work / 'registry.db'
    initialize_chain(chain, registry, chain_id='OFFLINE-r02',
                     current_result_roots=[consumer_work / 'results'])
    guard = SiteFailureStore.initialize({'ledger': str(consumer_work / 'stop.db'),
                                         'campaign_id': 'OFFLINE-r02',
                                         'formal_since': time.time() - 1}).binding
    policy = {'campaign_id': 'OFFLINE-r02', 'baseline_category_counts': {},
              'pilot_identity_required': True, 'site_failure_guard': guard}
    RuntimeStore(registry, 'authorized').initialize(policy)
    policy_file = consumer_work / 'policy.json'
    policy_file.write_text(json.dumps(policy))
    cfg = make_real_config()
    cfg['site_failure_guard'] = guard
    cfg_file = consumer_work / 'config.json'
    cfg_file.write_text(json.dumps(cfg))
    ledger_path = consumer_work / 'jobs.sqlite3'
    BatchLedger(ledger_path, cfg, initialize=True)
    cmd = [PY, '-m', 'webcollect.candidate_consumer', 'run',
           '--pool', str(consumer_work / 'pool.sqlite3'), '--config', str(cfg_file),
           '--ledger', str(ledger_path), '--output', str(consumer_work / 'out'),
           '--registry', str(registry), '--policy', str(policy_file),
           '--history-set', str(chain), '--worker-id', 'int-worker',
           '--request-prefix', 'int', '--limit', '1']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=ENV, cwd=ROOT)
    deadline = time.monotonic() + 90
    empty_seen = error_seen = False
    events_file = consumer_work / 'out' / 'int-worker-events.jsonl'
    while time.monotonic() < deadline:
        if events_file.exists():
            text = events_file.read_text()
            if 'inventory_empty' in text:
                empty_seen = True
                break
            if 'consumer_error' in text:
                error_seen = text[:400]
                break
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
    detail = {'exit': proc.returncode, 'inventory_empty_event': bool(empty_seen),
              'consumer_error': error_seen or None}
    step('consumer_cli_empty_inventory', empty_seen and not error_seen, detail)
except Exception as error:
    import traceback
    (OUT / 'consumer-error.txt').write_text(traceback.format_exc())
    step('consumer_cli_empty_inventory', False, f'{type(error).__name__}: {error}')

# 2. both strategy build entries produce tasks without retired literals
RETIRED = ('webcollect-collection-', 'webcollect-result-completion-1',
           'candidate-research-replay-1', 'candidate-research-replay-2',
           'candidate-research-replay-3', 'closing-policy-v2')
try:
    from webcollect.batch_core import BatchLedger, file_sha
    from webcollect.collection_strategy import (STRATEGY_BANDED_REACT,
                                                STRATEGY_SCREENSHOT_PLAN, strategy_id)
    from webcollect.current_chain import initialize_chain
    from webcollect.task_generation import generate
    results = {}
    for strategy in (STRATEGY_BANDED_REACT, STRATEGY_SCREENSHOT_PLAN):
        work = OUT / f'strategy-{strategy}'
        work.mkdir()
        chain = work / 'chain.json'
        registry = work / 'registry.db'
        initialize_chain(chain, registry, chain_id='OFFLINE-r02',
                         current_result_roots=[work / 'results'])
        ledger = BatchLedger(work / 'jobs.sqlite3', make_real_config(), initialize=True)
        catalog = work / 'catalog.json'
        catalog.write_text(json.dumps({
            'schema_version': 'capability-catalog', 'mode': 'real',
            'records': [{'schema_version': 'site-capability', 'capability_id': 'cap-r02',
                         'version': 'react', 'site_uri': 'https://example.org/',
                         'site_category': '在线工具', 'mode': 'real',
                         'status': 'review_required', 'reason': 'integration offline',
                         'supported_actions': ['click', 'type', 'hotkey', 'set_value', 'scroll'],
                         'task_families': ['navigation-reading'],
                         'capabilities': [], 'evidence': []}]}))
        claim_body = {'candidate_id': 'cid-r02', 'claim_id': 'cl-r02', 'version': 1,
                      'pool': str(work / 'pool.sqlite3'),
                      'snapshot': {'schema_version': 'webcollect-data-candidate-2',
                                   'candidate_kind': 'entry',
                                   'entry_url': 'https://example.org/',
                                   'requested_goal': None},
                      'sources': []}
        claim_path = work / 'claim.json'
        claim_path.write_text(json.dumps(claim_body, ensure_ascii=False))
        claim_ref = {'path': str(claim_path), 'sha256': file_sha(claim_path)}
        gen = generate(ledger, catalog, work / 'planning', generator='react-url',
                       history_registry=registry, history_set=chain,
                       react_url='https://example.org/', react_goal=None,
                       react_candidate={'claim': {'candidate_id': 'cid-r02',
                                                  'claim_id': 'cl-r02', 'version': 1,
                                                  'snapshot': {'schema_version': 'webcollect-data-candidate-2',
                                                               'candidate_kind': 'entry',
                                                               'entry_url': 'https://example.org/',
                                                               'requested_goal': None}},
                                        'claim_reference': claim_ref,
                                        'collection_strategy': strategy})
        tasks_count = gen.get('generated_tasks')
        plan = json.loads((work / 'planning' / 'plan.json').read_text()) if (work / 'planning' / 'plan.json').exists() else {}
        plan_tasks = plan.get('tasks') or []
        blob = json.dumps({'gen': gen, 'plan': plan}, ensure_ascii=False, default=str)
        results[strategy] = {'generated_tasks': tasks_count,
                             'planned_tasks': len(plan_tasks),
                             'task_strategies': sorted({strategy_id(t) for t in plan_tasks}),
                             'retired_literals': [lit for lit in RETIRED if lit in blob]}
    step('strategy_build_entries',
         all(v['planned_tasks'] >= 1 for v in results.values())
         and all(v['task_strategies'] == [k] for k, v in results.items())
         and all(not v['retired_literals'] for v in results.values()), results)
except Exception as error:
    import traceback
    (OUT / 'strategy-build-error.txt').write_text(traceback.format_exc())
    step('strategy_build_entries', False, f'{type(error).__name__}: {error}')

# 3. finalized runtime objects carry no retired version contract
try:
    from webcollect.collection_strategy import RESULT_CONTRACT, finalize_strategy_result
    finalized = finalize_strategy_result(
        {'result_contract': RESULT_CONTRACT, 'strategy': {'id': 'react'},
         'goal': {'goal_status': 'VERIFIED'}, 'execution': {'effective_steps': 6},
         'end': {'goal_status': 'VERIFIED', 'end_reason': 'ready',
                 'save_eligibility': 'unresolved', 'save_status': 'unresolved'}},
        save_status='collected_pending_review', eligibility='eligible')
    blob = json.dumps(finalized)
    retired_hits = [lit for lit in RETIRED if lit in blob]
    step('finalized_object_no_version_contract', not retired_hits,
         {'retired_literals': retired_hits, 'end': finalized['end']})
except Exception as error:
    step('finalized_object_no_version_contract', False, f'{type(error).__name__}: {error}')

# 4. switch script dry-run on a copied small backup (production DB untouched)
try:
    bak = ROOT / 'verify_results/noversion-switch-20261111-r01/site-facts.sqlite3.bak'
    work = OUT / 'switch-work'
    work.mkdir()
    copy = work / 'site-facts.copy.sqlite3'
    shutil.copyfile(bak, copy)
    done = subprocess.run([PY, str(ROOT / 'projects/code/scripts/switch_noversion_db_20261111.py'),
                           str(copy)], capture_output=True, text=True, timeout=600, env=ENV)
    step('switch_script_dry_run_site_facts', done.returncode == 0,
         {'exit': done.returncode, 'integrity_ok': 'ok' in done.stdout,
          'stderr': done.stderr[-200:]})
except Exception as error:
    step('switch_script_dry_run_site_facts', False, f'{type(error).__name__}: {error}')

report['not_run'] = {
    'real_glm_collection': '本授权明确不做真实采集',
    'producer_fixed_page': '本授权明确不做生产者固定页',
    'four_consumer_candidates': '本授权明确不派消费者候选',
    'ai_qc_dispatch': '本授权明确不做 AI QC 派发',
    'qc_handoff_with_real_sample': '无离线保存样本可用；真实样本交接待真实轮',
    'customer_export': '无已审集合，按门禁 NOT_CLAIMED',
}

(OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
fails = [k for k, v in report.items() if isinstance(v, dict) and v.get('ok') is False]
print('REPORT', OUT / 'report.json', 'fails:', fails)
sys.exit(1 if fails else 0)
