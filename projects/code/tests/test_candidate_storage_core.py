"""Temporary SQLite project persistence, isolated from collection output."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from site_planner.candidate_pool import CandidatePool
from site_planner.discovery_tools import reference
from site_planner.producer_authority import authorize_concurrency
from webcollect import candidate_project
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
            root = temporary / 'database' / 'sqllite' / 'prod'
            legacy = root.parent / 'producer-muxtly-wiki-200-20261111-r01'
            legacy.mkdir(parents=True)
            sentinel = legacy / 'keep.txt'
            sentinel.write_text('legacy project must remain untouched')
            output = temporary / 'results' / 'offline-project' / 'collections'
            module_file = temporary / 'projects' / 'code' / 'webcollect' / 'candidate_project.py'
            with patch.object(candidate_project, '__file__', str(module_file)):
                scope_path = initialize(None, 'offline-project', {}, offline_config(),
                                        offline_config(), output_root=output)
            launch_scope = load_json(scope_path)
            # These are the actual two role ledgers, not substitute in-memory
            # stores. Their filenames must remain compatible with with_name.
            for role in ('producer', 'consumer'):
                BatchLedger(launch_scope[role + '_db'],
                            load_json(launch_scope[role + '_config']), initialize=True)
            authorize_concurrency(scope_path, 100, 'offline 100-producer integration')
            self.assertEqual(BatchLedger(launch_scope['producer_db'],
                load_json(launch_scope['producer_config'])).max_concurrent_jobs, 100)
            # A retained layout alias still names this physical ledger. Keep
            # the original frozen run/config checks when resuming its decision.
            alias = temporary / 'old-layout'
            alias.symlink_to(root, target_is_directory=True)
            producer = BatchLedger(launch_scope['producer_db'], load_json(launch_scope['producer_config']))
            with producer.transaction() as con:
                row = con.execute("SELECT seq,detail FROM batch_events WHERE event='producer_concurrency' ORDER BY seq DESC LIMIT 1").fetchone()
                decision = json.loads(row[1])
                decision['ledger'] = str(alias / Path(producer.path).name)
                con.execute('UPDATE batch_events SET detail=? WHERE seq=?', (json.dumps(decision), row[0]))
            self.assertEqual(BatchLedger(producer.path, producer.config).max_concurrent_jobs, 100)
            with producer.transaction() as con:
                decision['ledger'] = str(temporary / 'other-ledger.sqlite3')
                con.execute('UPDATE batch_events SET detail=? WHERE seq=?', (json.dumps(decision), row[0]))
            with self.assertRaisesRegex(ValueError, 'Producer concurrency decision'):
                BatchLedger(producer.path, producer.config)
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
            claim = pool.claim_next('offline-consumer', 'offline-consumer/0')
            self.assertEqual(claim['candidate_id'], candidate_id)
            self.assertEqual(claim['snapshot'], candidate)
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
            self.assertEqual(sentinel.read_text(), 'legacy project must remain untouched')
            self.assertFalse((root / 'offline-project').exists())
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, 'already contains project files'):
                initialize(root, 'offline-project', {}, offline_config(), offline_config(),
                           output_root=temporary / 'must-not-be-created')
            self.assertFalse((temporary / 'must-not-be-created').exists())
            # Deleted output must also remain an unavailable advisory history,
            # while the current candidate still requires its original bytes.
            from webcollect.agent_feedback import site_context
            import sqlite3
            registry = temporary / 'feedback.sqlite3'
            missing = {'path': str(output / 'failure.json'), 'sha256': '0' * 64}
            with sqlite3.connect(registry) as con:
                con.execute('CREATE TABLE m4_tasks(task_key TEXT, task_json TEXT)')
                con.execute('CREATE TABLE m4_attempts(task_key TEXT, attempt_id TEXT, sample_id TEXT, status TEXT, root_cause TEXT, failure_class TEXT, evidence_json TEXT, created_at TEXT)')
                con.execute('INSERT INTO m4_tasks VALUES (?,?)', ('task', json.dumps({
                    'task_id':'task', 'site_uri':'https://example.org/',
                    'candidate_binding':{'candidate_id':'old'}})))
                con.execute('INSERT INTO m4_attempts VALUES (?,?,?,?,?,?,?,?)',
                    ('task', 'attempt', 'sample', 'rejected', 'failure', 'semantic', json.dumps([missing]), 'now'))
            with patch('webcollect.collection_context.from_registry', return_value={}):
                context = site_context(registry, 'https://example.org/', candidate_id='new')
                unavailable = context['executions'][0]
                self.assertEqual(unavailable['feedback_status'], 'UNAVAILABLE')
                self.assertEqual(unavailable['evidence_error']['classification'], 'MISSING_FILE')
                self.assertEqual(unavailable['references'], [missing])
                self.assertEqual(context['images'], [])
                self.assertEqual(context['avoid'], [])
                with self.assertRaisesRegex(ValueError, '证据路径'):
                    site_context(registry, 'https://example.org/', candidate_id='old')
                output.mkdir(parents=True)
                Path(missing['path']).write_text('{}')
                context = site_context(registry, 'https://example.org/', candidate_id='new')
                self.assertEqual(context['executions'][0]['evidence_error']['classification'], 'DIGEST_MISMATCH')


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
