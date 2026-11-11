"""Temporary SQLite project persistence, isolated from collection output."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from site_planner.candidate_pool import CandidatePool
from site_planner.discovery_tools import reference
from webcollect.batch_core import BatchLedger, load_json
from webcollect.candidate_project import initialize
from webcollect.current_chain import (check_project_guard, check_project_pool,
                                      current_evidence_roots, read_chain_scope)
from webcollect.planning import verify_evidence


def offline_config():
    return {'run_id': 'template', 'mode': 'synthetic', 'model': None,
            'budget': {'max_concurrent_jobs': 1, 'min_domain_interval_seconds': 1,
                       'lease_seconds': 30, 'max_job_attempts': 1}}


class CandidateStorageCore(unittest.TestCase):
    def test_deleting_collection_output_preserves_project_candidates_and_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            root = temporary / 'database' / 'sqllite' / 'offline-project'
            output = temporary / 'results' / 'offline-project' / 'collections'
            scope_path = initialize(root, 'offline-project', {}, offline_config(),
                                    offline_config(), output_root=output)
            launch_scope = load_json(scope_path)
            # These are the actual two role ledgers, not substitute in-memory
            # stores. Their filenames must remain compatible with with_name.
            for role in ('producer', 'consumer'):
                BatchLedger(launch_scope[role + '_db'],
                            load_json(launch_scope[role + '_config']), initialize=True)
            pool = CandidatePool(launch_scope['pool'])
            source = root / 'producer-evidence' / 'source.json'
            source.parent.mkdir()
            source.write_text(json.dumps({'CONTROLLED': 'offline source evidence'}))
            source_ref = reference(source)
            candidate = {'schema_version': 'webcollect-data-candidate-2',
                         'candidate_kind': 'target', 'entry_url': 'https://example.org/',
                         'requested_goal': {'kind': 'edit', 'entity': 'fields',
                                            'parameters': {'quantity': 1}}}
            candidate_id = pool.put(candidate, {'origin': 'codex_session',
                'run_id': 'offline-project-producer', 'references': [source_ref]})
            original_source = source.read_bytes()
            (output / 'temporary-run-log.txt').write_text('Disposable collection output')
            shutil.rmtree(output)

            launch_scope = load_json(scope_path)
            chain = read_chain_scope(launch_scope['history_set'])
            readonly_pool = CandidatePool(launch_scope['pool'], readonly=True)
            self.assertTrue(check_project_pool(chain, readonly_pool.pool))
            for role in ('producer', 'consumer'):
                config = load_json(launch_scope[role + '_config'])
                check_project_guard(chain, config['site_failure_guard'],
                                    launch_scope[role + '_db'], role=role)
                self.assertEqual(Path(launch_scope[role + '_db']).parent, root)
            self.assertEqual({path.name for path in root.glob('*.sqlite3')}, {
                'candidate-pool.sqlite3', 'production-registry.sqlite3',
                'site-facts.sqlite3', 'producer-jobs.sqlite3', 'consumer-jobs.sqlite3'})
            with readonly_pool.pool.connect() as connection:
                saved = connection.execute('SELECT body FROM data_candidates WHERE candidate_id=?',
                                           (candidate_id,)).fetchone()
                provenance = connection.execute('SELECT source FROM candidate_sources WHERE candidate_id=?',
                                                (candidate_id,)).fetchone()
            self.assertEqual(json.loads(saved[0]), candidate)
            references = json.loads(provenance[0])['references']
            verify_evidence(references)
            self.assertEqual(references, [source_ref])
            self.assertEqual(current_evidence_roots(chain)[0], root)
            self.assertEqual(source.read_bytes(), original_source)
            self.assertFalse(output.exists())

    def test_disposable_roots_are_rejected_before_scope_or_database_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            for disposable in ('results', 'verify_results'):
                root = temporary / disposable / 'project'
                with self.assertRaisesRegex(ValueError, 'Persistent project root'):
                    initialize(root, 'offline-project', {}, offline_config(),
                               offline_config(), output_root=temporary / 'output')
                self.assertFalse(root.exists())
            self.assertFalse(list(temporary.rglob('scope.json')))
            self.assertFalse(list(temporary.rglob('*.sqlite3')))
