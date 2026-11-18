"""Run explicitly selected local repair tests and bind results to source bytes.

No repository-wide discovery: old reference/history suites are deliberately not
adopted. Test modules must themselves use disposable fixtures and prohibit real
provider/website/production IO. This runner never launches a product entry point.
"""
import argparse
from contextlib import redirect_stderr, redirect_stdout, ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import builtins
import io
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.dont_write_bytecode = True
sys.path[:0] = [str(REPO / value) for value in (
    'projects/code', 'projects/code/tests', 'projects/site-planner',
    'projects/quality-inspector')]


def snapshot():
    files = []
    for folder in ('projects/code/webcollect', 'projects/site-planner/site_planner',
                   'projects/quality-inspector/quality_inspector'):
        files.extend(path for path in (REPO / folder).rglob('*')
                     if path.is_file() and '__pycache__' not in path.parts)
    for folder in ('projects/code/tests', 'projects/code/scripts'):
        files.extend(path for path in (REPO / folder).rglob('*.py')
                     if path.is_file() and 'fixtures' not in path.parts and '__pycache__' not in path.parts)
    return {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


@contextmanager
def no_repository_history():
    """Fail before opening/stat-ing excluded payloads, even via a legacy fixture."""
    forbidden = [REPO / path for path in ('request/web操作采集需求/samples',
                 'request/token', 'results', 'projects/sample', 'm1-sample')]
    def checked(function):
        def call(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                name = Path(os.path.abspath(os.fsdecode(path)))
                if any(name == root or name.is_relative_to(root) for root in forbidden):
                    raise AssertionError('Offline verification forbids repository history/credential payload access')
            return function(path, *args, **kwargs)
        return call
    originals = [(builtins, 'open', builtins.open), (io, 'open', io.open)]
    originals += [(Path, name, getattr(Path, name)) for name in
                  ('open', 'stat', 'lstat', 'exists', 'is_file', 'is_dir', 'iterdir')]
    # Do not register this boundary with mock.patch: a test's patch.stopall()
    # must never disable the suite-wide history-read restriction.
    try:
        for owner, name, original in originals:
            setattr(owner, name, checked(original))
        yield
    finally:
        for owner, name, original in reversed(originals):
            setattr(owner, name, original)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--module', action='append', required=True)
    args = parser.parse_args(argv)
    for name in args.module:
        if not name.startswith('test_') or not all(part.isidentifier() for part in name.split('.')):
            raise ValueError('Select explicit test module names only')
    root = args.output.absolute()
    if root.exists(): raise FileExistsError('Verification evidence must not be overwritten')
    root.mkdir(parents=True)
    before = snapshot(); started = time.time()
    test_files = {Path(importlib.util.find_spec(name.split('.')[0]).origin) for name in args.module}
    test_hashes = {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in test_files}
    with (root / 'tests.log').open('x') as log, redirect_stdout(log), redirect_stderr(log), no_repository_history():
        suite = unittest.defaultTestLoader.loadTestsFromNames(args.module)
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    after = snapshot()
    tests_unchanged = all(hashlib.sha256((REPO / name).read_bytes()).hexdigest() == value
                          for name, value in test_hashes.items())
    summary = {'schema_version': 'webcollect-offline-repair-verification-1',
        'finished_at_utc': datetime.now(timezone.utc).isoformat(), 'modules': args.module,
        'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped), 'elapsed_seconds': time.time() - started,
        'source_files_sha256': before, 'source_unchanged_during_verification': before == after,
        'test_files_sha256': test_hashes, 'test_files_unchanged': tests_unchanged,
        'status': 'PASS' if result.wasSuccessful() and before == after and tests_unchanged else 'FAIL',
        'real_sample_acceptance': 'NOT_TESTED', 'production_resumed': False,
        'scope': 'Explicit disposable offline test fixtures only; no production qualification inferred'}
    (root / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in summary.items() if key != 'source_files_sha256'}, ensure_ascii=False))
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
