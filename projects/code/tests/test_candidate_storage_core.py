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
            # 站点模板登记：只数正式保存（candidate_results effective=1）的不同
            # 页面；同页重存不重复计数，第二模板须各自满三页才登记。
            from webcollect import template_sites
            from webcollect.planning import canonical
            claims = [claim]
            for index in (1, 2):
                pool.put({'schema_version': 'webcollect-data-candidate-2',
                          'candidate_kind': 'target', 'entry_url': f'https://example.org/page{index}',
                          'requested_goal': {'kind': 'edit', 'entity': 'fields',
                                             'parameters': {'quantity': 10 + index}}}, {'origin': 'codex_session',
                          'run_id': 'offline-project-producer', 'references': [source_ref]})
                claims.append(pool.claim_next('offline-consumer', f'offline-consumer/{index}'))
            with pool.pool.connect() as con:
                application_id = con.execute('SELECT application_id FROM data_candidates WHERE candidate_id=?',
                                             (candidate_id,)).fetchone()[0]
            self.assertFalse(template_sites.ensure_table(pool))  # pool init created it
            self.assertEqual(template_sites.confirmed_templates(pool, application_id), [])
            for index, row_claim in enumerate(claims):
                with pool.transaction() as con:
                    con.execute('INSERT INTO candidate_results VALUES(?,?,?,?,?,NULL,?)',
                        (row_claim['candidate_id'], row_claim['claim_id'], f'sample-{index}',
                         canonical({'sample_id': f'sample-{index}', 'template_name': 'long_reading'}),
                         'pending_review', 1))
            progress = template_sites.record_save(pool, claims[2],
                {'sample_id': 'sample-2', 'template_name': 'long_reading'})
            self.assertEqual(progress, {'application_id': application_id, 'template_name': 'long_reading',
                'pages': 3, 'reached_three': True, 'registered': True,
                'sample_ids': ['sample-0', 'sample-1', 'sample-2']})
            self.assertEqual(template_sites.confirmed_templates(pool, application_id), ['long_reading'])
            with pool.transaction() as con:  # same page again: one ineffective replay row
                con.execute('INSERT INTO candidate_results VALUES(?,?,?,?,?,NULL,?)',
                    (claims[2]['candidate_id'], claims[2]['claim_id'] + '-research', 'sample-2r',
                     canonical({'sample_id': 'sample-2r', 'template_name': 'long_reading'}),
                     'pending_review', 0))
            repeat = template_sites.record_save(pool, claims[2],
                {'sample_id': 'sample-2r', 'template_name': 'long_reading'})
            self.assertEqual((repeat['pages'], repeat['registered']), (3, False))
            self.assertEqual(template_sites.record_save(pool, claims[0],
                {'sample_id': 'sample-0', 'template_name': 'operation'})['registered'], False)
            self.assertEqual(template_sites.distinct_saved_pages(pool, application_id, 'operation'), 0)
            self.assertEqual(template_sites.record_save(pool, claims[0], {'sample_id': 'sample-0'})['template_name'], None)
            with pool.pool.connect(write=True) as con:  # fixture-only drop for tolerance
                con.execute('BEGIN IMMEDIATE')
                con.execute('DROP TABLE template_sites')
                con.commit()
            self.assertEqual(template_sites.confirmed_templates(pool, application_id), [])
            # An existing pool regains the additive table on the next open.
            reopened = CandidatePool(launch_scope['pool'])
            with reopened.pool.connect() as con:
                self.assertTrue(con.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='template_sites'").fetchone())
            with pool.pool.connect(write=True) as con:  # module-level ensure recreates too
                con.execute('BEGIN IMMEDIATE')
                con.execute('DROP TABLE template_sites')
                con.commit()
            self.assertTrue(template_sites.ensure_table(pool))
            # The saved pages still count; a later save re-registers the template.
            re_registered = template_sites.record_save(pool, claims[1],
                {'sample_id': 'sample-1', 'template_name': 'long_reading'})
            self.assertEqual((re_registered['pages'], re_registered['registered']), (3, True))
            self.assertEqual(template_sites.confirmed_templates(pool, application_id), ['long_reading'])
            from webcollect import workspace_json
            portable=__import__('json').loads(workspace_json.dumps({'path':str(source),'input_text':str(source),1:{'path':str(source)}}))
            self.assertEqual(portable['path'],str(source))
            self.assertEqual(portable['input_text'],str(source))
            self.assertFalse((root / '.workspace-root.json').exists())
            self.assertFalse((output / '.workspace-root.json').exists())
            self._check_literal_storage_across_roots(temporary)
            original_source = source.read_bytes()
            (output / 'temporary-run-log.txt').write_text('Disposable collection output')
            shutil.rmtree(output)

            launch_scope = load_json(scope_path)
            chain = read_chain_scope(launch_scope['history_set'])
            self._check_registry_concurrency(launch_scope, chain, temporary)
            self._check_producer_capacity_preserves_unsettled_jobs(temporary)
            self._check_pool_readers_do_not_take_writer_slots(temporary)
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
            from webcollect import workspace_json
            references = workspace_json.loads(provenance[0])['references']
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


    def _check_literal_storage_across_roots(self, temporary):
        from contextlib import closing
        from webcollect import workspace_json
        from webcollect.sqlite_connection import raw_connect
        from webcollect.workspace_paths import logical
        self.assertIs(workspace_json.dumps, json.dumps)
        self.assertIs(workspace_json.loads, json.loads)
        paths = [temporary / name for name in ('first-root', 'second-root')]
        for path in paths:
            path.mkdir()
            (path / '.workspace-root.json').write_text('{"workspace_root":"."}')
        delayed = []
        with closing(raw_connect(paths[0] / 'state.sqlite3')) as first, \
                closing(raw_connect(paths[1] / 'state.sqlite3')) as second:
            for connection, path in ((first, paths[0]), (second, paths[1]), (first, paths[0])):
                connection.execute('CREATE TABLE IF NOT EXISTS entries(path TEXT, body TEXT, data TEXT)')
                value = {'path': str(path / 'file'), 'legacy': 'workspace:/original/file'}
                connection.execute('INSERT INTO entries(path,body,data) VALUES(?,?,?)',
                                   (value['path'], value['path'], workspace_json.dumps(value)))
                row = connection.execute('SELECT path,body,data FROM entries ORDER BY rowid DESC LIMIT 1').fetchone()
                self.assertEqual(row[:2], (value['path'], value['path']))
                delayed.append((row[2], value))
                self.assertEqual(logical(path / 'file'), value['path'])
            first.executemany('INSERT INTO entries(path,body,data) VALUES(:path,:body,:data)',
                              [{'path':'workspace:/old/path', 'body':str(paths[0] / 'business-text'), 'data':'{}'}])
            self.assertEqual(first.execute('SELECT path,body FROM entries ORDER BY rowid DESC LIMIT 1').fetchone(),
                             ('workspace:/old/path', str(paths[0] / 'business-text')))
        for encoded, value in reversed(delayed):
            self.assertEqual(workspace_json.loads(encoded), value)

    def _check_pool_readers_do_not_take_writer_slots(self, temporary):
        import sqlite3
        from contextlib import closing
        from site_planner.site_pool import SitePool
        pool = SitePool(temporary / 'concurrent-pool.sqlite3', initialize=True)
        self.assertEqual(pool.enable_wal(), {'previous': 'wal', 'current': 'wal'})
        value = {'original': 'immutable'}
        pool.checkpoint('run', 'old', value)
        payload = {'uri': 'https://example.org/page'}
        request, _ = pool.reserve_tool('run', 'browser', 'settled', payload)
        pool.settle_tool(request, 'succeeded', value)
        held, _ = pool.reserve_tool('run', 'browser', 'unsettled', payload)
        connect = pool.connect
        with closing(sqlite3.connect(pool.path)) as writer, \
                patch.object(pool, 'connect', side_effect=lambda **kw: connect(**{**kw, 'timeout': 0.05})):
            writer.execute('BEGIN IMMEDIATE')
            before = writer.execute('SELECT * FROM tool_requests WHERE id=?', (held,)).fetchone()
            self.assertEqual(pool.checkpoint('run', 'old', value), value)
            self.assertEqual(pool.reserve_tool('run', 'browser', 'settled', payload), (request, value))
            with self.assertRaisesRegex(ValueError, 'UNKNOWN/failed'):
                pool.reserve_tool('run', 'browser', 'unsettled', payload)
            with self.assertRaisesRegex(ValueError, 'Checkpoint conflict'):
                pool.checkpoint('run', 'old', {'changed': True})
            self.assertEqual(writer.execute('SELECT * FROM tool_requests WHERE id=?', (held,)).fetchone(), before)
            writer.rollback()
        with closing(sqlite3.connect(pool.path)) as reader:
            reader.execute('BEGIN')
            self.assertEqual(reader.execute('SELECT count(*) FROM checkpoints').fetchone()[0], 1)
            pool.checkpoint('run', 'new', {'new': True})
            self.assertEqual(reader.execute('SELECT count(*) FROM checkpoints').fetchone()[0], 1)
            reader.rollback()
            self.assertEqual(reader.execute('SELECT count(*) FROM checkpoints').fetchone()[0], 2)

    def _check_producer_capacity_preserves_unsettled_jobs(self, temporary):
        import os
        import time
        from unittest.mock import Mock
        from webcollect.batch_core import BudgetStop, OutcomeUnknown
        from site_planner.producer_authority import claim_producer_job
        from site_planner.producer_business_content import _purpose_holds
        from site_planner.discovery_agent import model_tool_decision
        ledger = BatchLedger(temporary / 'capacity.sqlite3', offline_config(), initialize=True)
        payload = {'scope': 'old-scope', 'source_uris': ['https://example.org/unsettled']}
        frozen = {'protocol': 'native-tool-1', 'input': payload, 'tools': [],
                  'system': 'original', 'reasoning_effort': 'low'}
        old_id = ledger.enqueue('ai-target-page-purpose-1', frozen)
        ledger.claim('ai-target-page-purpose-1', job_id=old_id)
        with ledger.transaction() as con:
            con.execute('UPDATE jobs SET lease=? WHERE id=?', (time.time()-10, old_id))
            for state in ('unknown', 'reserved'):
                con.execute('INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,reserved_cost,started) VALUES(?,?,?,?,?,?,?,?)',
                            ('old-'+state, old_id, state, 1, state, 0, 0, time.time()-20))
            original_job = dict(con.execute('SELECT * FROM jobs WHERE id=?', (old_id,)).fetchone())
            original_requests = [dict(r) for r in con.execute('SELECT * FROM model_requests ORDER BY id')]
        fresh = ledger.enqueue('site-discovery-page', {'uri': 'https://example.org/fresh'})
        first = ledger.claim('site-discovery-page', job_id=fresh)
        self.assertIsNotNone(first)
        waiting = ledger.enqueue('site-discovery-page', {'uri': 'https://example.org/next'})
        with self.assertRaisesRegex(BudgetStop, 'max_concurrent_jobs'):
            ledger.claim('site-discovery-page', job_id=waiting)
        self.assertEqual(ledger.get(waiting)['attempts'], 0)
        with patch('site_planner.producer_authority.time.sleep', side_effect=lambda _: ledger.finish(first, result={})):
            second = claim_producer_job(ledger, 'site-discovery-page', job_id=waiting)
        self.assertEqual(second['id'], waiting)
        self.assertEqual({r['request_id'] for r in _purpose_holds(ledger)[payload['source_uris'][0]]},
                         {'old-unknown', 'old-reserved'})
        gateway = Mock()
        with self.assertRaises(OutcomeUnknown):
            model_tool_decision(ledger, gateway, 'ai-target-page-purpose-1', payload, [], system='original')
        gateway.call_tool.assert_not_called()
        stop = temporary / 'producer.stop'
        stop.write_text('stop after current work')
        with patch.dict(os.environ, {'WEBCOLLECT_PRODUCER_STOP_FILE': str(stop)}):
            with self.assertRaisesRegex(BudgetStop, 'producer_stop_requested'):
                claim_producer_job(ledger, 'site-discovery-page', job_id=waiting)
        with ledger.connect() as con:
            self.assertEqual(dict(con.execute('SELECT * FROM jobs WHERE id=?', (old_id,)).fetchone()), original_job)
            self.assertEqual([dict(r) for r in con.execute('SELECT * FROM model_requests ORDER BY id')], original_requests)

    def _check_registry_concurrency(self, launch, chain, temporary):
        from webcollect.runtime import RuntimeStore
        from webcollect.current_chain import registry_snapshot
        from webcollect.task_admission import registry_snapshot as task_snapshot
        store = RuntimeStore(launch['registry'], 'persistence-check')
        connect, statements = store._connect, []
        def traced(*args, **kwargs):
            con = connect(*args, **kwargs)
            con.set_trace_callback(statements.append)
            return con
        with patch.object(store, '_connect', side_effect=traced):
            store.initialize(load_json(launch['policy']))
        self.assertFalse(any(sql.lstrip().upper().startswith('CREATE ') for sql in statements))
        self.assertEqual(registry_snapshot(chain, launch['registry']), task_snapshot(launch['registry']))


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
