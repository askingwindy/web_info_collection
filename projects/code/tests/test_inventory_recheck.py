"""Offline integration for producer P0-P1: recheck culling and app cap.

No network (GET verdicts are scripted), no browser, no model. Temporary
fixtures only.
"""
import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[2] / 'site-planner')]

from site_planner import inventory_recheck
from site_planner.candidate_discovery import _app_pending_over_limit, _application_pending_cap


SCHEMA = '''
CREATE TABLE data_candidates(candidate_id TEXT PRIMARY KEY, application_id TEXT, dedup_key TEXT,
  version INTEGER, body TEXT, created REAL, state TEXT);
CREATE TABLE candidate_claims(claim_id TEXT PRIMARY KEY, candidate_id TEXT, version INTEGER, snapshot TEXT,
  worker_id TEXT, request_id TEXT, token TEXT, expires REAL, state TEXT, stage TEXT, binding TEXT,
  reason TEXT, created REAL, updated REAL, sources TEXT);
CREATE TABLE candidate_events(id INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL, claim_id TEXT,
  kind TEXT NOT NULL, record TEXT NOT NULL, created REAL);
CREATE TABLE candidate_sources(id INTEGER PRIMARY KEY, candidate_id TEXT, source_key TEXT, source TEXT, created REAL);
'''


def make_db():
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / 'pool.sqlite3'
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.commit()
    con.close()
    return tmp, path


def add_pending(path, cid, url, app='app-x'):
    con = sqlite3.connect(path)
    con.execute('INSERT INTO data_candidates VALUES(?,?,?,?,?,?,?)',
                (cid, app, cid, 1, json.dumps({'entry_url': url}), time.time(), 'pending'))
    con.commit()
    con.close()


class RecheckCullingTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.path = make_db()
        add_pending(self.path, 'c-ok', 'https://ok.example.org/a')
        add_pending(self.path, 'c-404', 'https://dead.example.org/a')
        add_pending(self.path, 'c-strike', 'https://flaky.example.org/a')
        add_pending(self.path, 'c-claimed', 'https://claimed.example.org/a')
        con = sqlite3.connect(self.path)
        con.execute("INSERT INTO candidate_claims VALUES('cl-1','c-claimed',1,'{}','w','r','t',0,'failed','done',NULL,NULL,0,0,NULL)")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def states(self):
        con = sqlite3.connect(self.path)
        rows = dict(con.execute('SELECT candidate_id, state FROM data_candidates'))
        con.close()
        return rows

    def test_verdicts_cull_and_dry_run(self):
        script = {'https://ok.example.org/a': ('ok', 200, None),
                  'https://dead.example.org/a': ('dead_hard', 404, None),
                  'https://flaky.example.org/a': ('strike', 503, None)}
        with mock.patch.object(inventory_recheck, '_get_check', side_effect=lambda url, t: script[url]):
            inventory_recheck.run(self.path, limit=10, stale_hours=0, timeout=5,
                                  host_interval=0, dry_run=True, smoke=0, audit=0, report_dir=None)
        self.assertEqual(self.states(), {'c-ok': 'pending', 'c-404': 'pending',
                                         'c-strike': 'pending', 'c-claimed': 'pending'})
        con = sqlite3.connect(self.path)
        # Dry-run has zero side effects: the auxiliary table itself is not even
        # created outside the formal write path.
        has_table = con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='inventory_rechecks'").fetchone()
        rows = con.execute('SELECT COUNT(*) FROM inventory_rechecks').fetchone()[0] if has_table else 0
        con.close()
        self.assertEqual(rows, 0)
        with mock.patch.object(inventory_recheck, '_get_check', side_effect=lambda url, t: script[url]):
            inventory_recheck.run(self.path, limit=10, stale_hours=0, timeout=5,
                                  host_interval=0, dry_run=False, smoke=0, audit=0, report_dir=None)
        states = self.states()
        self.assertEqual(states['c-404'], 'failed')      # hard dead culled immediately
        self.assertEqual(states['c-strike'], 'pending')  # first strike keeps it
        self.assertEqual(states['c-ok'], 'pending')
        self.assertEqual(states['c-claimed'], 'pending') # claimed history untouched
        with mock.patch.object(inventory_recheck, '_get_check', side_effect=lambda url, t: script[url]):
            inventory_recheck.run(self.path, limit=10, stale_hours=0, timeout=5,
                                  host_interval=0, dry_run=False, smoke=0, audit=0, report_dir=None)
        self.assertEqual(self.states()['c-strike'], 'failed')  # second consecutive strike culled
        con = sqlite3.connect(self.path)
        events = con.execute("SELECT candidate_id, kind FROM candidate_events WHERE kind='recheck_failed'").fetchall()
        con.close()
        self.assertEqual(sorted(cid for cid, _ in events), ['c-404', 'c-strike'])

    def test_recovery_resets_strike_chain(self):
        strike = {'https://ok.example.org/a': ('ok', 200, None),
                  'https://dead.example.org/a': ('ok', 200, None),
                  'https://flaky.example.org/a': ('strike', 503, None)}
        recover = dict(strike, **{'https://flaky.example.org/a': ('ok', 200, None)})
        with mock.patch.object(inventory_recheck, '_get_check', side_effect=lambda url, t: strike[url]):
            inventory_recheck.run(self.path, limit=10, stale_hours=0, timeout=5,
                                  host_interval=0, dry_run=False, smoke=0, audit=0, report_dir=None)
        with mock.patch.object(inventory_recheck, '_get_check', side_effect=lambda url, t: recover[url]):
            inventory_recheck.run(self.path, limit=10, stale_hours=0, timeout=5,
                                  host_interval=0, dry_run=False, smoke=0, audit=0, report_dir=None)
        self.assertEqual(self.states()['c-strike'], 'pending')
        with mock.patch.object(inventory_recheck, '_get_check', side_effect=lambda url, t: strike[url]):
            inventory_recheck.run(self.path, limit=10, stale_hours=0, timeout=5,
                                  host_interval=0, dry_run=False, smoke=0, audit=0, report_dir=None)
        self.assertEqual(self.states()['c-strike'], 'pending')  # ok broke the chain


class AppPendingCapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'pool.sqlite3'
        from site_planner.site_pool import SitePool
        from site_planner.candidate_pool import CandidatePool
        SitePool(self.path, initialize=True)
        self.pool = CandidatePool(self.path, install=True)
        with self.pool.pool.connect(write=True) as con:
            con.execute("INSERT OR REPLACE INTO runs VALUES('batch-1',?,?,?)",
                        (json.dumps({'application_pending_cap': 2,
                                     'current_chain_manifest': None}), '[]', time.time()))
            con.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def test_cap_reads_batch_config_and_blocks_over_limit(self):
        self.assertEqual(_application_pending_cap(self.pool, 'batch-1'), 2)
        with self.pool.pool.connect(write=True) as con:
            con.execute("INSERT OR REPLACE INTO applications VALUES('app-1','app1.example.org','样例应用','在线工具',?)",
                        (time.time(),))
            con.commit()
        for i in range(2):
            with self.pool.pool.connect(write=True) as con:
                con.execute("INSERT INTO data_candidates VALUES(?,?,?,?,?,?,?)",
                            (f'c-{i}', 'app-1', f'c-{i}', 1, '{}', time.time(), 'pending'))
                con.commit()
        header = {'row_id': 'r1', 'raw_index': 0, 'response_sha256': 'x' * 64,
                  'run_id': 'run', 'batch': 'batch-1', 'request_id': 'req-1'}
        verdict = _app_pending_over_limit(self.pool, 'batch-1', 'app-1', header, {'row': 1})
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict['result'], 'OVER_LIMIT')
        self.assertIn('APP_PENDING_CAP', verdict['reason'])
        self.assertIsNone(_app_pending_over_limit(self.pool, 'batch-1', 'app-empty', header, {'row': 1}))
        self.assertIsNone(_app_pending_over_limit(self.pool, 'batch-1', None, header, {'row': 1}))

    def test_default_cap_without_config(self):
        with self.pool.pool.connect(write=True) as con:
            con.execute("INSERT OR REPLACE INTO runs VALUES('batch-2',?,?,?)", (json.dumps({}), '[]', time.time()))
            con.commit()
        self.assertEqual(_application_pending_cap(self.pool, 'batch-2'), 100)
        self.assertEqual(_application_pending_cap(self.pool, 'missing-batch'), 100)


if __name__ == '__main__':
    unittest.main()
