"""Targeted S0 verification; local fixtures never count as production evidence."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import sys
import time
import unittest

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / 'projects/code'), str(REPO / 'projects/code/tests'),
                str(REPO / 'projects/quality-inspector')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--browser', action='store_true', help='Also exercise local controlled Chrome fixtures')
    parser.add_argument('--components', nargs='+', choices=['runtime', 'tasks', 'qc', 'compat'],
                        default=['runtime', 'tasks', 'qc', 'compat'])
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ['WEBCOLLECT_S0_RUNTIME_EVIDENCE'] = str(root / 'runtime')
    os.environ['WEBCOLLECT_S0_QC_EVIDENCE'] = str(root / 'qc')
    os.environ.pop('WEBCOLLECT_S0_TASK_EVIDENCE', None)
    if args.browser:
        os.environ['WEBCOLLECT_S0_TASK_EVIDENCE'] = str(root / 'controlled-tasks')
    cases = {
        'runtime': ['test_s0_runtime.NoModelRuntimeTests'] +
                   (['test_s0_runtime.NoModelProbeTests'] if args.browser else []),
        'tasks': ['test_s0_task_generation.DeterministicTaskTests'] +
                 (['test_s0_task_generation.DeterministicBrowserTests'] if args.browser else []),
        'qc': ['test_s0_sampling', 'test_s0_packet'],
        'compat': ['test_batch_core', 'test_ai_worker_protocol'],
    }
    results = []
    started = time.monotonic()
    for component in dict.fromkeys(args.components):
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in cases[component])
        part_started = time.monotonic()
        with (root / (component + '.log')).open('x') as log, redirect_stdout(log), redirect_stderr(log):
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        results.append({'component': component, 'status': 'PASS' if result.wasSuccessful() else 'FAIL',
                        'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                        'skipped': len(result.skipped), 'wall_seconds': time.monotonic() - part_started})
    # Measure persisted dispatches instead of inferring them from a test count.
    import sqlite3
    dispatches = []
    for path in sorted(root.rglob('*.sqlite3')):
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='model_requests'").fetchone():
                continue
            config = json.loads(con.execute('SELECT config FROM batch_meta').fetchone()[0])
            count = con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0]
            dispatches.append({'path': str(path), 'mode': config['mode'],
                               'model_enabled': config['model'] is not None, 'recorded_requests': count})
    summary = {'status': 'PASS' if all(row['status'] == 'PASS' for row in results) else 'FAIL',
               'scope': 'S0 targeted engineering tests; no production collection or real AI judgments',
               'components': results, 'tests': sum(row['tests'] for row in results),
               'wall_seconds': time.monotonic() - started, 'controlled_browser_requested': args.browser,
               'persisted_dispatches': dispatches,
               'no_model_request_count': sum(r['recorded_requests'] for r in dispatches if not r['model_enabled']),
               'real_sites_probed': 0, 'external_model_requests': 0,
               'external_model_fee': 0, 'infrastructure_and_development_cost': 'UNKNOWN',
               'production_registry_modified': False, 'active_human_review_modified': False,
               'customer_acceptance': 'UNKNOWN'}
    (root / 'verification-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary['status'] == 'PASS' and summary['no_model_request_count'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
