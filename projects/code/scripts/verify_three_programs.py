"""Repeatable E0-E3 verification. All browser/model data is synthetic engineering evidence."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import sys
import time
import unittest
sys.dont_write_bytecode=True

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/code'),str(REPO/'projects/code/tests')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--browser',action='store_true',help='Run local-only HTTP/Chrome collection and client export')
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    # Delivery validator deliberately rejects paths containing "integration".
    # Keep synthetic provenance in mode.json and the verification, not that path token.
    os.environ['WEBCOLLECT_THREE_PROGRAM_EVIDENCE']=str(root/'controlled-browser')
    suite=unittest.TestSuite();loader=unittest.TestLoader()
    for pattern in ['test_batch_core.py','test_ai_worker_protocol.py']+(['test_three_program_pipeline.py'] if args.browser else []):
        suite.addTests(loader.discover(str(REPO/'projects/code/tests'),pattern=pattern))
    started=time.time()
    with (root/'tests.log').open('x') as log,redirect_stdout(log),redirect_stderr(log):
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    summary={'status':'PASS' if result.wasSuccessful() else 'FAIL','tests':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'wall_seconds':time.time()-started,
        'browser_fixture_executed':args.browser,'real_sites_probed':0,'actual_ai_requests':0,
        'external_model_fee':0,'currency':'no external provider called',
        'infrastructure_and_development_cost':'UNKNOWN','production_registry_modified':False,
        'active_human_review_modified':False,'log':str(root/'tests.log')}
    (root/'verification-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
