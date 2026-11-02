"""Controlled pilot gates: original temporary protocol fixtures, no production/model."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from webcollect.batch_core import file_sha, load_json
from webcollect.production_identity import (VERSION, REVIEW_CHECKS, accept, actual_proof,
    allocation_uri, before_action, guard, page_url, require_actions, reserve,
    state_allowed, validate_identity, validate_plan, verify_saved)
from webcollect.runtime import RuntimeStore, validate_policy
from webcollect.observed_workflow import compile_task, prepare_admission, review_schema
from webcollect.task_admission import reference
from webcollect.storage import allocate_in_transaction
import test_observed_workflow as workflow_fixture
import m4_runtime_fixtures as runtime_fixture


class PilotIdentityTests(unittest.TestCase):
    def test_native_content_hydration_preserves_original_body_in_same_document(self):
        from webcollect.react_session import build_url_task
        from webcollect.batch_core import save_json
        task=build_url_task(url=workflow_fixture.URI,task_version='hydration',app_name='受控矩形工具')
        task['mode']='synthetic'
        state=load_json(self.anchor['state']['path'])
        state.update(title='中文问答',visible_text='这是关于维护版本兼容许可与性能的原始中文正文。'*4,
                     document_identity={'performance_time_origin':123,'url_without_fragment':workflow_fixture.URI})
        state_path=self.root/'hydrated-anchor-state.json';save_json(state_path,state)
        capture=load_json(self.anchor['capture']['path'])
        from webcollect.browser import fingerprint
        capture['attempts'][-1].update(before_fingerprint=fingerprint(state),after_fingerprint=fingerprint(state))
        capture_path=self.root/'hydrated-anchor-capture.json';save_json(capture_path,capture)
        anchor={**self.anchor,'state':reference(state_path),'capture':reference(capture_path)}
        task['pilot_identity']=self.identity(anchor=anchor);task['pilot_identity']['task_page']['kind']='content'
        task['candidate_binding']={'candidate':{'entry_url':workflow_fixture.URI}}
        actual=deepcopy(state);actual['visible_text']='新增导航栏\n'+state['visible_text']+'\n新增后续正文'
        actual['elements'] += [{'element_id':'nav','native_role':'button','text':'搜索','visible':True}]
        validate_identity(task,observed_states=[actual])
        for field,value in [('document_identity',{'performance_time_origin':456}),('visible_text','另一篇中文正文。'*10)]:
            bad={**actual,field:value}
            with self.assertRaisesRegex(ValueError,'corroborate'):validate_identity(task,observed_states=[bad])

    def setUp(self):
        self.fixture = workflow_fixture.ObservedWorkflowTests('runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.trace, self.cap = self.fixture.trace_ref, self.fixture.cap
        trace = load_json(self.trace['path'])
        self.anchor = trace['transitions'][0]['before']
        self.task = compile_task(self.cap, self.trace)
        self.task['pilot_identity'] = self.identity()

    def identity(self, uri=workflow_fixture.URI, *, anchor=None):
        return {'version': VERSION,
                'application': {'canonical_uri': 'https://example.org/', 'name': '受控矩形工具',
                                'evidence': [self.anchor['state']]},
                'task_page': {'canonical_uri': uri, 'aliases': [uri], 'kind': 'function',
                              'description': '受控矩形面积计算页面', 'anchor': anchor or self.anchor},
                'shared_pages': []}

    def rows(self, n=5):
        state = load_json(self.anchor['state']['path'])
        return [{'ended_at': 'controlled-finished', 'operation': {'action_type': 'click'},
                 'operation_origin': 'preparation' if i == 0 else 'planned',
                 'state': deepcopy(state)} for i in range(n)]

    def connection(self):
        con = sqlite3.connect(':memory:'); con.row_factory = sqlite3.Row
        con.execute('CREATE TABLE m4_tasks(task_key TEXT,task_json TEXT)')
        con.execute('BEGIN IMMEDIATE')
        self.addCleanup(con.close)
        return con

    def test_url_parameter_fragment_scheme_and_trailing_slash_variants_collide(self):
        self.assertEqual(page_url('HTTPS://Example.org:443/calculator/?q=2#other'), page_url(workflow_fixture.URI))
        self.assertEqual(page_url('http://example.org:80/calculator'), page_url(workflow_fixture.URI))

    def test_whole_application_cannot_be_a_page_path(self):
        self.task['pilot_identity']['application']['canonical_uri'] = workflow_fixture.URI
        with self.assertRaisesRegex(ValueError, 'whole public host'):
            validate_identity(self.task)

    def test_multihost_task_page_requires_frozen_application_alias_evidence(self):
        from webcollect.batch_core import save_json
        task = deepcopy(self.task)
        task['pilot_identity']['application']['canonical_uri'] = 'https://canonical.example/'
        with self.assertRaisesRegex(ValueError, 'ownership'):
            validate_identity(task)
        source = self.root / 'same-application.json'
        save_json(source, {'schema_version': 'webcollect-application-aliases-1', 'applications': [{
            'canonical_uri': 'https://canonical.example/',
            'aliases': ['https://canonical.example/', 'https://example.org/'],
            'evidence': [self.anchor['state']]}]})
        task['pilot_identity']['application']['application_registry'] = reference(source)
        self.assertEqual(validate_identity(task)['application_key'], '//canonical.example/')
        source.write_text(source.read_text() + '\n')
        with self.assertRaises(ValueError): validate_identity(task)

    def test_shared_entry_is_allowed_and_does_not_claim_the_task_page(self):
        self.task['initial_url'] = 'https://example.org/'
        self.task['pilot_identity']['shared_pages'] = [{'uri': self.task['initial_url'], 'role': 'entry',
            'reason': '受控入口只导航到实际任务页', 'evidence': [self.anchor['state']]}]
        start = deepcopy(self.rows()[0]['state']); start['url'] = self.task['initial_url']
        validate_identity(self.task, observed_states=[start, self.rows()[0]['state']])
        state_allowed(self.task, start)
        self.assertEqual(validate_identity(self.task)['task_page_urls'], [page_url(workflow_fixture.URI)])

    def test_actual_result_cannot_be_excluded_as_shared(self):
        self.test_shared_entry_is_allowed_and_does_not_claim_the_task_page()
        final = deepcopy(self.rows()[0]['state']); final['url'] = 'https://example.org/'
        with self.assertRaisesRegex(ValueError, 'result page'):
            actual_proof(self.task, self.rows(), final_state=final)

    def test_unknown_page_is_blocked_before_action(self):
        state = deepcopy(self.rows()[0]['state']); state['url'] = 'https://example.org/unapproved'
        with self.assertRaisesRegex(ValueError, 'no independently reviewed'):
            state_allowed(self.task, state)

    def test_task_page_cannot_be_declared_shared(self):
        self.task['pilot_identity']['shared_pages'] = [{'uri': workflow_fixture.URI, 'role': 'intermediate',
            'reason': '控制性反例', 'evidence': [self.anchor['state']]}]
        with self.assertRaisesRegex(ValueError, 'cannot hide'):
            validate_identity(self.task)

    def test_no_arbitrary_page_or_application_keys_are_accepted(self):
        self.task['pilot_identity']['task_page']['page_key'] = 'invented-distinct-page'
        with self.assertRaisesRegex(ValueError, 'task page'):
            validate_identity(self.task)

    def test_original_anchor_hash_is_rechecked(self):
        self.task['pilot_identity']['task_page']['anchor']['state']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            validate_identity(self.task)

    def test_bounds_four_five_ten_eleven(self):
        for n in (5, 10):
            require_actions(self.task, n, final=True)
        for n in (4, 11):
            with self.subTest(n=n), self.assertRaisesRegex(ValueError, '5-10'):
                require_actions(self.task, n, final=True)

    def test_preparation_cannot_execute_eleventh_operation(self):
        before_action(self.task, self.rows(9), 'scroll')
        with self.assertRaisesRegex(ValueError, '5-10'):
            before_action(self.task, self.rows(10), 'scroll')
        before_action(self.task, self.rows(10), 'complete')

    def test_wait_complete_and_failed_actions_do_not_pad_minimum(self):
        rows = self.rows(4)
        rows += [{'ended_at': 'finished', 'operation': {'action_type': 'wait'}},
                 {'ended_at': 'finished', 'operation': {'action_type': 'complete'}},
                 {'execution_error': 'controlled failure', 'operation': {'action_type': 'click'}}]
        with self.assertRaisesRegex(ValueError, '5-10'):
            before_action(self.task, rows, 'complete')

    def test_original_page_claim_is_idempotent_but_not_a_new_version(self):
        con = self.connection()
        reserve(con, 'original-task', self.task); reserve(con, 'original-task', self.task)
        guard(con, 'original-task', self.task)
        with self.assertRaisesRegex(ValueError, 'already owned'):
            reserve(con, 'another-version', self.task)
        self.assertTrue(con.in_transaction)

    def test_acceptance_retains_one_effective_sample(self):
        con = self.connection(); reserve(con, 'task', self.task)
        accept(con, 'task', self.task, 'CONTROLLED-sample-1')
        accept(con, 'task', self.task, 'CONTROLLED-sample-1')
        with self.assertRaisesRegex(ValueError, 'another accepted'):
            accept(con, 'task', self.task, 'CONTROLLED-retry-2')

    def test_transaction_rollback_leaves_no_orphan_page_or_app_claims(self):
        con = self.connection(); reserve(con, 'task', self.task)
        con.rollback()
        self.assertIsNone(con.execute("SELECT 1 FROM sqlite_master WHERE name='m4_pilot_page_claims'").fetchone())

    def test_shared_entry_can_support_different_task_pages_with_one_site_id(self):
        con = self.connection(); reserve(con, 'task1', self.task)
        folder = self.root / 'different-business'; folder.mkdir()
        anchor = self.fixture.frame(folder, 'anchor', 1, uri='https://example.org/other')
        value = load_json(anchor['state']['path']); value['title'] = '受控速度计算'
        Path(anchor['state']['path']).write_text(json.dumps(value)); anchor['state'] = reference(anchor['state']['path'])
        other = deepcopy(self.task); other['initial_url'] = 'https://example.org/other'
        other['pilot_identity'] = self.identity(other['initial_url'], anchor=anchor)
        reserve(con, 'task2', other)
        # Exercise the original allocator in this same transaction.
        from webcollect.storage import ensure_registry_schema
        # Schema setup precedes the allocation transaction, as production does.
        con.rollback(); ensure_registry_schema(con); con.execute('BEGIN IMMEDIATE')
        first = allocate_in_transaction(con, allocation_uri(self.task), '工具', 'real', '20261028')
        second = allocate_in_transaction(con, allocation_uri(other), '工具', 'real', '20261028', first['batch_id'])
        self.assertEqual(first['site_id'], second['site_id'])
        self.assertNotEqual(first['sample_id'], second['sample_id'])

    def test_different_path_same_observed_function_is_a_collision(self):
        con = self.connection(); reserve(con, 'task1', self.task)
        other = deepcopy(self.task)
        other['pilot_identity']['task_page']['aliases'].append('https://example.org/renamed')
        other['pilot_identity']['task_page']['canonical_uri'] = 'https://example.org/renamed'
        with self.assertRaisesRegex(ValueError, 'already owned'):
            reserve(con, 'task2', other)

    def test_original_legacy_page_cannot_be_silently_ignored(self):
        con = self.connection()
        con.execute('INSERT INTO m4_tasks VALUES(?,?)', ('old', json.dumps({'site_uri': workflow_fixture.URI})))
        with self.assertRaisesRegex(ValueError, 'original legacy registry'):
            reserve(con, 'task', self.task)

    def test_campaign_opt_in_is_explicit_and_cannot_be_false(self):
        self.assertNotIn('pilot_identity_required', validate_policy({}))
        self.assertIs(validate_policy({'pilot_identity_required': True})['pilot_identity_required'], True)
        with self.assertRaises(ValueError):
            validate_policy({'pilot_identity_required': False})
        with self.assertRaisesRegex(ValueError, 'every new pilot task'):
            validate_plan({'schema_version': 'webcollect-plan-m4-1', 'tasks': [{}]}, required=True)

    def test_non_m4_pilot_cannot_use_legacy_direct_allocation(self):
        self.task['workflow_admission'] = {}
        with self.assertRaisesRegex(ValueError, 'strict M4'):
            validate_plan({'tasks': [self.task]})

    def test_runtime_enqueue_claim_and_start_bind_original_transaction(self):
        import time
        from webcollect.planning import object_sha256
        registry = runtime_fixture.make_registry(self.root / 'CONTROLLED-runtime.sqlite3')
        store = RuntimeStore(registry, 'CONTROLLED-pilot-scope')
        store.initialize({'campaign_id': 'CONTROLLED-pilot', 'pilot_identity_required': True})
        task = deepcopy(self.task); task['workflow_admission'] = {}
        plan = {'schema_version': 'webcollect-plan-m4-1', 'tasks': [task]}
        publication = {'plan_sha256': object_sha256(plan), 'publication_sha256': 'CONTROLLED-publication', 'tasks': [
            {'task_id': task['task_id'], 'task_version': task['task_version'], 'capability_expires_at': time.time() + 3600}]}
        # This isolates transaction hooks from unrelated publication/model
        # provenance fixtures. Original admission has separate full regressions.
        with patch('webcollect.runtime.verify_publication'), patch.object(store, '_customer_history_proof', return_value={}), \
             patch('webcollect.admission_cohort.guard_enqueue'), patch('webcollect.admission_cohort.guard_scope'):
            store.enqueue_plan(plan, publication)
            a = store.claim_next('controlled-worker', request_id='controlled-request')
            self.assertEqual(store.claim_next('controlled-worker', request_id='controlled-request')['sample_id'], a['sample_id'])
            store.start_attempt(a['attempt_id'], 'controlled-worker', a['lease_token'])
            with store._connect(readonly=True) as con:
                self.assertEqual(con.execute('SELECT uri FROM sites').fetchone()[0], 'https://example.org/')
            # A lost page claim fences a repeated request as well as dispatch.
            with store._transaction() as con:
                con.execute('DELETE FROM m4_pilot_page_claims')
            with self.assertRaisesRegex(ValueError, 'ownership missing'):
                store.claim_next('controlled-worker', request_id='controlled-request')

    def test_runtime_campaign_blocks_identity_omission_before_queue_write(self):
        registry = runtime_fixture.make_registry(self.root / 'CONTROLLED-required.sqlite3')
        store = RuntimeStore(registry, 'CONTROLLED-required')
        store.initialize({'campaign_id': 'CONTROLLED-required', 'pilot_identity_required': True})
        with patch('webcollect.runtime.verify_publication'), patch.object(store, '_customer_history_proof', return_value={}):
            with self.assertRaisesRegex(ValueError, 'every new pilot task'):
                store.enqueue_plan({'tasks': [{}]}, {'plan_sha256': 'controlled'})
        self.assertEqual(store.snapshot()['tasks'], [])

    def test_pilot_identity_is_frozen_into_trace_and_new_review_checks(self):
        trace = load_json(self.trace['path']); intent_path = Path(trace['intent']['path'])
        intent = load_json(intent_path); intent['pilot_identity'] = self.identity()
        intent_path.write_text(json.dumps(intent)); trace['intent'] = reference(intent_path)
        Path(self.trace['path']).write_text(json.dumps(trace)); ref = reference(self.trace['path'])
        task = compile_task(self.cap, ref)
        self.assertEqual(task['pilot_identity'], intent['pilot_identity'])
        result = prepare_admission(self.cap, ref, self.fixture.ctx, self.root / 'pilot-review',
            mode='synthetic', producer_context_id='controlled-producer')
        checks = review_schema(result['packet'])['properties']['checks']['properties']
        self.assertTrue(set(REVIEW_CHECKS) <= set(checks))
        trace['transitions'] *= 3
        Path(self.trace['path']).write_text(json.dumps(trace))
        with self.assertRaisesRegex(ValueError, '5-10'):
            compile_task(self.cap, reference(self.trace['path']))

    def test_saved_receipt_rederives_actual_page_and_action_counts(self):
        sid = 'CONTROLLED-sample'; out = self.root / 'capture'
        evidence = out / 'evidence' / sid; sample = out / 'samples' / sid
        evidence.mkdir(parents=True); sample.mkdir(parents=True)
        raw = self.rows() + [{**self.rows()[0], 'operation': {'action_type': 'complete'}}]
        for i, row in enumerate(raw, 1):
            (evidence / f'step_{i:03}.json').write_text(json.dumps(row))
        annotation = {'sample_id': sid, 'steps': [{'action': {'action_type': row['operation']['action_type']}} for row in raw]}
        (sample / 'annotation.json').write_text(json.dumps(annotation))
        proof = actual_proof(self.task, raw)
        (evidence / 'pilot_identity.json').write_text(json.dumps({**proof,
            'annotation_sha256': file_sha(sample / 'annotation.json')}))
        receipt = evidence / 'saved_sample.json'
        saved = {'sample_id': sid, 'sample_files_sha256': {'annotation.json': file_sha(sample / 'annotation.json')},
                 'capture_files_sha256': {p.name: file_sha(p) for p in evidence.iterdir()}}
        receipt.write_text(json.dumps(saved)); verify_saved(self.task, sid, [reference(receipt)])
        original = deepcopy(saved)
        saved['capture_files_sha256'].pop('step_001.json')
        receipt.write_text(json.dumps(saved))
        with self.assertRaisesRegex(ValueError, 'every consecutive original raw step'):
            verify_saved(self.task, sid, [reference(receipt)])
        saved = original; receipt.write_text(json.dumps(saved))
        # Preserve exact receipt: changing the annotation after saving is caught.
        annotation['steps'].append({'action': {'action_type': 'click'}})
        (sample / 'annotation.json').write_text(json.dumps(annotation))
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            verify_saved(self.task, sid, [reference(receipt)])


if __name__ == '__main__':
    unittest.main()
