"""Isolated real SQLite contention; no production files, accounts or network."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from site_planner.candidate_pool import CandidatePool, VERSION
from site_planner.site_pool import SitePool
from site_planner.discovery_tools import reference
from webcollect.batch_core import save_json


def claim_and_close(args):
    path, number = args
    pool = CandidatePool(path)
    claim = pool.claim_next(f'worker-{number}', f'request-{number}')
    if claim['state'] != 'consuming':
        return claim
    for stage in ('observation', 'planning', 'execution'):
        pool.heartbeat(claim)
        pool.stage(claim, stage)
    pool.finish(claim, state='failed', reason='Isolated scheduling fixture; no business execution', stage='execution')
    return {'claim_id': claim['claim_id'], 'candidate_id': claim['candidate_id'], 'state': 'failed'}


class TwentyProcessSQLite(unittest.TestCase):
    def test_exclusive_claim_stage_heartbeat_and_close(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'pool.sqlite3'
            SitePool(path, initialize=True)
            pool = CandidatePool(path, install=True)
            proof = root / 'source.json'
            save_json(proof, {'isolated': True})
            source = {'origin': 'codex_session', 'run_id': 'isolated', 'references': [reference(proof)]}
            with patch('site_planner.entry_access.fetch_status', side_effect=lambda uri, *_: (200, uri)):
                for number in range(20):
                    pool.put({'schema_version': VERSION, 'entry_url': 'https://example.org/',
                              'name': '隔离夹具', 'parent_category': '图书文化', 'business_kind': '阅读',
                              'description': '搜索作品并查看详情', 'target': {'kind': 'search', 'entity': 'book',
                              'parameters': {'query': str(number)}}}, source)
            with ProcessPoolExecutor(max_workers=20) as executor:
                results = list(executor.map(claim_and_close, [(str(path), n) for n in range(20)]))
            self.assertEqual(len({r['candidate_id'] for r in results}), 20)
            self.assertEqual(len({r['claim_id'] for r in results}), 20)
            with sqlite3.connect(path) as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM candidate_claims WHERE state='failed'").fetchone()[0], 20)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM candidate_results').fetchone()[0], 0)
                self.assertFalse(con.execute('PRAGMA foreign_key_check').fetchall())


if __name__ == '__main__':
    unittest.main()
