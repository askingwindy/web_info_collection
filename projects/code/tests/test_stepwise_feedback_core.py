"""Stepwise feedback and candidate history use original local evidence only."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from PIL import Image

from webcollect.agent_feedback import save_attempt_feedback, unresolved_candidate_executions
from webcollect.batch_core import file_sha
from webcollect.planning import verify_evidence
from webcollect.stepwise.collection import recent_site_tasks


class StepwiseFeedbackCore(unittest.TestCase):
    def test_images_real_page_instructions_and_exact_unresolved_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / 'evidence' / 'S000001'
            (evidence / 'stepwise').mkdir(parents=True)
            original = evidence / 'stepwise' / 'observation-001.png'
            Image.new('RGB', (24, 24), 'red').save(original)
            raw = {'step_id': 1, 'operation': {'action_type': 'click', 'arguments': {}},
                   'state': {'visible_text': '原始操作前画面'},
                   'capture': {'screenshot_sha256': file_sha(original)}}
            (evidence / 'step_001.json').write_text(json.dumps(raw), encoding='utf-8')
            attempt = {'attempt_id': 'attempt-saved', 'sample_id': 'S000001', 'task_id': 'task-own'}
            rejected = save_attempt_feedback(evidence, attempt, 'rejected', 'local fixture')
            rejection = json.loads(Path(rejected['path']).read_text())
            verify_evidence([rejection['steps'][0]['image']])
            self.assertEqual(Path(rejection['steps'][0]['image']['path']).read_bytes(), original.read_bytes())
            # A remapped delivery image may already occupy this index. Never overwrite it.
            sample = root / 'samples' / 'S000001'
            (sample / 'images').mkdir(parents=True)
            packaged = sample / 'images' / 'step_001.png'
            Image.new('RGB', (24, 24), 'blue').save(packaged)
            packaged_bytes = packaged.read_bytes()
            accepted = save_attempt_feedback(evidence, attempt, 'collected_pending_review')
            accepted_row = json.loads(Path(accepted['path']).read_text())['steps'][0]
            verify_evidence([accepted_row['image']])
            self.assertEqual(packaged.read_bytes(), packaged_bytes)
            self.assertEqual(Path(accepted_row['image']['path']), original.resolve())

            instruction = '在「离线计算器」输入边长并查看面积结果'
            annotation = sample / 'annotation.json'
            annotation.write_text(json.dumps({'task_instruction': instruction}), encoding='utf-8')
            saved = evidence / 'saved_sample.json'
            saved.write_text(json.dumps({'sample_files_sha256': {'annotation.json': file_sha(annotation)}}),
                             encoding='utf-8')
            registry = root / 'registry.sqlite3'
            own_url, other_url = 'https://example.org/area', 'https://example.org/volume'
            task = {'task_id': 'task-own', 'site_uri': 'https://example.org/', 'initial_url': own_url,
                    'instruction': '统一的占位任务，不是真实回写',
                    'candidate_binding': {'candidate_id': 'candidate-own',
                                          'candidate': {'entry_url': own_url}}}
            with sqlite3.connect(registry) as con:
                con.executescript('''
                    CREATE TABLE m4_tasks(task_key TEXT, task_id TEXT, task_json TEXT);
                    CREATE TABLE m4_attempts(attempt_id TEXT, task_key TEXT, sample_id TEXT,
                        status TEXT, failure_class TEXT, root_cause TEXT,
                        evidence_json TEXT, finished_at TEXT);
                ''')
                con.execute('INSERT INTO m4_tasks VALUES(?,?,?)', ('own', 'task-own', json.dumps(task)))
                con.execute('INSERT INTO m4_attempts VALUES(?,?,?,?,?,?,?,?)',
                    ('attempt-saved', 'own', 'S000001', 'collected_pending_review', None, None,
                     json.dumps([{'path': str(saved), 'sha256': file_sha(saved)}]), '2026-11-01'))
                other_task = {**task, 'task_id': 'task-other', 'initial_url': other_url,
                              'candidate_binding': {'candidate_id': 'candidate-other',
                                                    'candidate': {'entry_url': other_url}}}
                con.execute('INSERT INTO m4_tasks VALUES(?,?,?)',
                            ('other', 'task-other', json.dumps(other_task)))
                for number in range(205):
                    con.execute('INSERT INTO m4_attempts VALUES(?,?,?,?,?,?,?,?)',
                        ('other-%d' % number, 'other', 'OTHER%d' % number,
                         'collected_pending_review', None, None, '[]', '2026-11-18'))
                con.execute('INSERT INTO m4_attempts VALUES(?,?,?,?,?,?,?,?)',
                    ('attempt-current', 'own', 'CURRENT', 'running', None, None, '[]', None))
                con.execute('INSERT INTO m4_attempts VALUES(?,?,?,?,?,?,?,?)',
                    ('attempt-other-pending', 'other', 'PENDING', 'reserved', None, None, '[]', None))
            # The page constraint runs before LIMIT, so 205 newer rows cannot hide this task.
            self.assertEqual(recent_site_tasks(registry, own_url), [instruction])
            self.assertEqual(recent_site_tasks(registry, other_url), [])

            model_path = root / 'model.sqlite3'
            with sqlite3.connect(model_path) as con:
                con.executescript('''
                    CREATE TABLE jobs(id TEXT, kind TEXT, state TEXT, payload TEXT);
                    CREATE TABLE model_requests(id TEXT, state TEXT, job_id TEXT, request_json TEXT);
                ''')
                # Pre-attempt task generation owns the candidate in its original nested payload.
                for label, candidate, state in (('unknown-own', 'candidate-own', 'unknown'),
                                                 ('reserved-own', 'candidate-own', 'reserved'),
                                                 ('unknown-other', 'candidate-other', 'unknown')):
                    payload = {'fragment_context': {'candidate_consumption': {'candidate_id': candidate}}}
                    con.execute('INSERT INTO jobs VALUES(?,?,?,?)',
                                (label, 'task-generation', 'review_required', json.dumps(payload)))
                    con.execute('INSERT INTO model_requests VALUES(?,?,?,?)', (label, state, label, '{}'))

            class Ledger:
                config = {}
                path = model_path

                @contextmanager
                def connect(self):
                    connection = sqlite3.connect(model_path.as_uri() + '?mode=ro', uri=True)
                    connection.row_factory = sqlite3.Row
                    try:
                        yield connection
                    finally:
                        connection.close()

                def timeout_retry_answered(self, con, request_id):
                    return False

            protected = (file_sha(registry), file_sha(model_path))
            unresolved = unresolved_candidate_executions(registry, task, model_ledger=Ledger(),
                                                         current_attempt_id='attempt-current')
            self.assertEqual({row['request_id'] for row in unresolved if 'request_id' in row},
                             {'unknown-own', 'reserved-own'})
            self.assertEqual({row['job_id'] for row in unresolved if 'job_id' in row},
                             {'unknown-own', 'reserved-own'})
            self.assertFalse(any(row.get('attempt_id') == 'attempt-other-pending' for row in unresolved))
            fresh = {**task, 'candidate_binding': {'candidate_id': 'candidate-fresh'}}
            self.assertEqual(unresolved_candidate_executions(registry, fresh, model_ledger=Ledger()), [])
            self.assertEqual((file_sha(registry), file_sha(model_path)), protected)
