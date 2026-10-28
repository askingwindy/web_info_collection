"""Controlled full real-schema admission path; no site or model is contacted.

Fixtures are generated locally and never form production/customer evidence.
Only browser capture is mocked in overlap tests: publication, original-history
parsing, independent-review bindings, admission and SQLite guards run normally.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import m4_runtime_fixtures as runtime_fixture
import test_observed_workflow as workflow_fixture
import test_site_concurrency as concurrency_fixture
from webcollect.admission_cohort import reserve_schedule
from webcollect.batch_core import load_json
from webcollect.browser import fingerprint
from webcollect.collect_runtime import runtime_scope, source_identity as collection_sources
from webcollect.observed_workflow import (CHECKS, DIFFERENCES, attach, compile_task,
    prepare_admission, source_identity, verify_entry)
from webcollect.planning import object_sha256, publish_plan
from webcollect.preflight import SOURCE_FILES, _files, digest, schedule_plan
from webcollect.runtime import RuntimeStore
from webcollect.site_scheduler import run_schedule, validate_schedule
from webcollect.task_admission import context, reference
from webcollect.task_generation import _history_package_files, bind_formal_history, read_customer_history


def fixture_json(path, value):
    """Only locally authored temporary fixtures may be rewritten by a test."""
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


class CohortTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Reuse only browser/collector test setup, not its legacy admissions.
        self.browser_fixture = concurrency_fixture.ConcurrentSitesTests('runTest')
        await self.browser_fixture.asyncSetUp(cleanup_owner=self)
        self.root, self.registry = self.browser_fixture.root, self.browser_fixture.registry
        self.fixture = workflow_fixture.ObservedWorkflowTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.root = self.root
        self.fixture.registry = self.registry
        self.fixture.sources = source_identity()
        self.policy = self.browser_fixture.policy
        self.origin = RuntimeStore(self.registry, 'CONTROLLED-original-history')
        self.origin.initialize(self.policy)
        with patch('m4_runtime_fixtures.NOW', time.time()):
            self.old_plan, self.old_publication = runtime_fixture.make_plan(
                self.root / 'original-history-plan', task_prefix='old-history', uri='https://example.com/history')
        self.origin.enqueue_plan(self.old_plan, self.old_publication)
        delivery = self.root / 'CONTROLLED-delivery'; package = delivery / 'formal'
        sample = package / 'samples' / 'CONTROLLED-old-source'; sample.mkdir(parents=True)
        fixture_json(sample / 'annotation.json', {'sample_id': sample.name, 'steps': []})
        (package / 'README.md').write_text('Controlled protocol population, not an actual delivery')
        fixture_json(package / 'site-list.json', {'schema_version': 'webcollect-site-list-1',
            'sites': [{'site_id': 'CONTROLLED-site', 'uri': 'https://example.com/history', 'sample_ids': [sample.name]}],
            'samples': [{'sample_id': sample.name, 'site_id': 'CONTROLLED-site'}]})
        manifest = self.root / 'CONTROLLED-history-set.json'
        fixture_json(manifest, {'schema_version': 'qc-cumulative-set-1', 'packages': [
            {'path': str(package), 'package_files_sha256': _history_package_files(package)}]})
        latest = delivery / 'LATEST.md'; latest.write_text('[Controlled formal fixture](formal/README.md)\n')
        history, history_scope = read_customer_history(manifest)
        patcher = patch('webcollect.task_generation.FORMAL_LATEST_PATH', latest)
        patcher.start(); self.addCleanup(patcher.stop)
        self.history_scope = bind_formal_history(history_scope)
        self.fixture.ctx = context(self.history_scope, history, self.registry)
        self.plans, self.publications = [], []
        self.config = deepcopy(self.browser_fixture.config)
        for i, (domain, labels, terminal) in enumerate((
                ('example.org', ('长度', '宽度', '计算面积'), '矩形面积为42平方厘米'),
                ('example.net', ('速度', '时间', '计算路程'), '总路程为42公里'))):
            task, cap = self.real_schema_workflow('workflow-' + str(i), 'https://' + domain + '/calculator', labels, terminal)
            plan, publication = self.published('published-' + str(i), task, cap)
            self.plans.append(plan); self.publications.append(publication)
            batch = self.config['sites'][i]['batches'][0]
            fixture_json(batch['plan'], plan); fixture_json(batch['publication'], publication)

    def real_schema_workflow(self, name, uri, labels, terminal):
        """Locally authored protocol fixtures: actual validators, no real site."""
        trace_ref, cap = self.fixture.make_trace(name)
        trace = load_json(trace_ref['path']); trace['mode'] = 'real'
        intent = load_json(trace['intent']['path'])
        intent.update(mode='real', site_uri=uri, app_name='受控' + labels[2] + '工具',
            instruction='在「受控工具」中填写两个必要输入，点击「' + labels[2] + '」并核对可见结果。',
            final_result='显示' + terminal, completion_judgement='最终页面可见「' + terminal + '」。')
        fixture_json(trace['intent']['path'], intent); trace['intent'] = reference(trace['intent']['path'])
        old_labels = ('长度', '宽度', '计算面积')
        for transition in trace['transitions']:
            for kind in ('before', 'after'):
                frame = transition[kind]
                state = load_json(frame['state']['path']); state.pop('fixture'); state['mode'] = 'real'
                state.update(url=uri, title='受控' + labels[2])
                for old, new in zip(old_labels, labels):
                    state['visible_text'] = state['visible_text'].replace(old, new)
                state['visible_text'] = state['visible_text'].replace('矩形面积为42平方厘米', terminal)
                for element, label in zip(state['elements'], labels):
                    element['text'] = label
                if state.get('target'):
                    target = state['target']; target['text'] = labels[int(target['element_id'][1:]) - 1]
                    target['visible_label_evidence'][0]['text'] = target['text']
                fixture_json(frame['state']['path'], state)
                capture = load_json(frame['capture']['path']); capture.pop('fixture')
                capture['attempts'][-1].update(before_fingerprint=fingerprint(state), after_fingerprint=fingerprint(state))
                fixture_json(frame['capture']['path'], capture)
                transition[kind] = {key: reference(frame[key]['path']) for key in ('image', 'state', 'capture')}
            receipt = load_json(transition['execution']['path'])
            receipt.update(mode='real', before_frame_sha256=object_sha256(transition['before']),
                after_frame_sha256=object_sha256(transition['after']))
            receipt['state_preflight']['state_fingerprint'] = fingerprint(load_json(transition['before']['state']['path']))
            fixture_json(transition['execution']['path'], receipt)
            transition['execution'] = reference(transition['execution']['path'])
        trace['final_assertions'] = [{'visible_text': terminal}]
        fixture_json(trace_ref['path'], trace); trace_ref = reference(trace_ref['path'])
        cap.update(mode='real', site_uri=uri, capability_scope={'kind': 'exact-candidate-page', 'page_uris': [uri], 'sitewide': False},
                   capabilities=[{'page_uri': uri}], representative_pages=[{'uri': uri, 'chinese_ratio': 1}])
        result = prepare_admission(cap, trace_ref, self.fixture.ctx, self.root / (name + '-admission'),
                                   mode='real', producer_context_id='CONTROLLED-local-author')
        packet = load_json(result['packet']['path']); review = load_json(result['review_template'])
        review.update(completed=True, reviewer={'kind': 'session_ai', 'id': 'CONTROLLED-independent-review-fixture',
            'context_id': 'CONTROLLED-review-context'}, reviewed_at=packet['created_at'], expires_at=packet['created_at'] + 600,
            checks={key: 'PASS' for key in CHECKS}, reason='Controlled protocol fixture only; no actual AI or human review.')
        for row in review['step_observations']:
            row['observation'] = 'Controlled original-frame protocol observation.'
        for row in review['history_comparisons']:
            row.update(relation='DISTINCT', reason='Controlled whole-history protocol comparison.',
                       differences={key: 'Controlled fixture distinction for ' + key for key in DIFFERENCES})
        source = self.root / (name + '-review-source.json')
        fixture_json(source, {'schema_version': 'webcollect-independent-task-review-source-1',
            'reviewer': review['reviewer'], 'packet_sha256': result['packet']['sha256'], 'completed': True,
            'reviewed_at': review['reviewed_at'], 'actual_external_model_call': False,
            'reviewed_frame_sha256': sorted({frame['image']['sha256'] for frame in packet['frames']}),
            'reviewed_tree_sha256': sorted({frame['state']['sha256'] for frame in packet['frames']}),
            'review_body_sha256': object_sha256({key: value for key, value in review.items() if key != 'provenance'})})
        review['provenance'] = reference(source)
        review_path = self.root / (name + '-review.json'); fixture_json(review_path, review)
        return attach(compile_task(cap, trace_ref), result['packet'], reference(review_path), self.fixture.ctx, mode='real'), cap

    def published(self, name, task, cap):
        folder = self.root / name; folder.mkdir()
        plan = {'schema_version': 'webcollect-plan-m4-1', 'tasks': [task],
                'production_facts': deepcopy(self.old_plan['production_facts']),
                'observed_workflow_generation': {'mode': 'real', 'source_identity': source_identity(),
                                                 'history_scope': self.history_scope}}
        fixture_json(folder / 'input-plan.json', plan)
        directory = folder / 'task_001'; directory.mkdir()
        for filename in ('initial.png', 'initial.json', 'frame_001.png', 'frame_001.json', 'frame_002.png', 'frame_002.json'):
            (directory / filename).write_text('CONTROLLED preflight binding protocol fixture; not an actual image')
        record = {'schema_version': 'webcollect-page-preflight-1', 'task_id': task['task_id'],
                  'task_sha256': object_sha256(task), 'summary': {'routing': 'NORMAL_M1'}, 'requested_probe_count': 2,
                  'frames': [{'path': f'frame_{i:03d}.png', 'raw_path': f'frame_{i:03d}.json'} for i in (1, 2)],
                  'synthetic_fixture_not_delivery': True}
        fixture_json(directory / 'result.json', record)
        record = {**record, 'evidence_directory': directory.name}
        import webcollect.preflight as preflight
        report = {'schema_version': 'webcollect-preflight-report-1', 'records': [record],
            'input_plan_sha256': digest(folder / 'input-plan.json'), 'fixed_task_denominator': 1,
            'source_changed_during_run': [], 'source_files_sha256': {
                name: digest(Path(preflight.__file__).parent / name) for name in SOURCE_FILES}, 'evidence_files_sha256': _files(folder)}
        report_path = folder / 'report.json'; fixture_json(report_path, report)
        plan = schedule_plan(plan, [record], report_path, digest(report_path), True)
        return plan, publish_plan(plan, [cap])

    def reserve(self, config=None, name='cohort-schedule'):
        config, policy, bindings = validate_schedule(config or self.config)
        output = self.root / name; output.mkdir()
        frozen = {'schema_version': 'webcollect-site-schedule-1-binding', 'config': config,
                  'input_files_sha256': bindings, 'shared_policy': policy, 'source_files_sha256': collection_sources()}
        fixture_json(output / 'schedule.json', frozen)
        return reserve_schedule(frozen, output / 'schedule.json')

    def store(self, index):
        batch = self.config['sites'][index]['batches'][0]
        store = RuntimeStore(self.registry, runtime_scope(batch['output'])); store.initialize(self.policy)
        return store

    def add_unbound(self):
        with patch('m4_runtime_fixtures.NOW', time.time()):
            plan, publication = runtime_fixture.make_plan(self.root / 'unbound-plan', task_prefix='foreign', uri='https://foreign.example.org/')
        store = RuntimeStore(self.registry, 'CONTROLLED-unbound-scope'); store.initialize(self.policy)
        store.enqueue_plan(plan, publication)

    def counts(self):
        with closing(sqlite3.connect(self.registry)) as con:
            return tuple(con.execute('SELECT (SELECT COUNT(*) FROM m4_tasks),(SELECT COUNT(*) FROM m4_attempts)').fetchone())

    def allocation_ledger(self):
        with closing(sqlite3.connect(self.registry)) as con:
            return {table: list(con.execute('SELECT * FROM ' + table)) for table in ('sites', 'batches', 'allocations')}

    async def test_without_cohort_peer_enqueue_still_blocks_new_admission(self):
        first = self.store(0); first.enqueue_plan(self.plans[0], self.publications[0])
        with self.assertRaisesRegex(ValueError, 'history drift'):
            verify_entry(self.plans[1], self.registry, self.config['sites'][1]['batches'][0]['output'])
        self.assertEqual(self.counts(), (2, 0))

    async def test_two_new_admission_collectors_overlap_and_resume_without_new_ids(self):
        active, peak = 0, 0; both = asyncio.Event()
        async def capture(*args):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            if active == 2:
                both.set()
            await asyncio.wait_for(both.wait(), 5)
            await self.browser_fixture.capture(*args)
            active -= 1
        with patch('webcollect.collect.collect_one', capture):
            result = await run_schedule(self.config, self.root / 'scheduler-run')
        self.assertEqual(result['status'], 'COLLECTED_PENDING_REVIEW', result)
        self.assertEqual(peak, 2)
        self.assertEqual(result['admission_cohort']['sample_ids_allocated'], 0)
        self.assertEqual(result['admission_cohort']['peer_comparison'], 'ENGINEERING_SIGNATURE_GUARDS_ONLY')
        self.assertEqual(self.counts(), (3, 2))
        async def fail_capture(*args):
            self.fail('Saved admitted captures must not execute twice on bound resume')
        with patch('webcollect.collect.collect_one', fail_capture):
            resumed = await run_schedule(self.config, self.root / 'scheduler-run', resume=True)
        self.assertEqual(resumed['status'], 'COLLECTED_PENDING_REVIEW')
        self.assertEqual(self.counts(), (3, 2))

    async def test_atomic_prebinding_allocates_no_task_or_sample_ids_and_is_idempotent(self):
        original_ids = self.allocation_ledger()
        receipt = self.reserve()
        self.assertEqual(receipt['tasks_prebound'], 2)
        self.assertEqual(self.counts(), (1, 0))
        frozen_path = self.root / 'cohort-schedule' / 'schedule.json'
        self.assertEqual(reserve_schedule(load_json(frozen_path), frozen_path), receipt)
        self.assertEqual(self.counts(), (1, 0))
        self.assertEqual(self.allocation_ledger(), original_ids)

    async def test_competing_cohort_reservations_commit_exactly_one_and_no_numbers(self):
        configs = [deepcopy(self.config), deepcopy(self.config)]
        for i, config in enumerate(configs):
            for j, site in enumerate(config['sites']):
                site['batches'][0]['output'] = str(self.root / f'competing-{i}-{j}')
        barrier = threading.Barrier(2)
        def attempt(index):
            barrier.wait()
            try:
                return self.reserve(configs[index], 'racing-schedule-' + str(index))['cohort_id']
            except ValueError as error:
                self.assertIn('already reserved', str(error))
                return None
        original_ids = self.allocation_ledger()
        with ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(value is not None for value in outcomes), 1)
        with closing(sqlite3.connect(self.registry)) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM m4_admission_cohorts').fetchone()[0], 1)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM m4_admission_members').fetchone()[0], 2)
        self.assertEqual(self.allocation_ledger(), original_ids)

    async def test_cancelled_admitted_cohort_keeps_reservations_and_uses_new_resume_ids(self):
        both = asyncio.Event(); started = 0
        async def interrupted(*args):
            nonlocal started
            await self.browser_fixture.capture(*args)
            started += 1
            if started == 2:
                both.set()
            await asyncio.sleep(30)
        with patch('webcollect.collect.collect_one', interrupted):
            running = asyncio.create_task(run_schedule(self.config, self.root / 'cancelled-scheduler'))
            await asyncio.wait_for(both.wait(), 5)
            running.cancel()
            cancelled = await running
        self.assertEqual(cancelled['status'], 'PAUSED')
        self.assertEqual(cancelled['admission_cohort']['tasks_prebound'], 2)
        before = [self.store(index).snapshot()['attempts'][0] for index in range(2)]
        self.assertEqual({row['status'] for row in before}, {'rejected'})
        with patch('webcollect.collect.collect_one', self.browser_fixture.capture):
            resumed = await run_schedule(self.config, self.root / 'cancelled-scheduler', resume=True)
        self.assertEqual(resumed['status'], 'COLLECTED_PENDING_REVIEW', resumed)
        self.assertEqual(resumed['admission_cohort']['cohort_id'], cancelled['admission_cohort']['cohort_id'])
        self.assertEqual(self.counts(), (3, 4))
        after = [row for index in range(2) for row in self.store(index).snapshot()['attempts']]
        self.assertEqual(len({row['sample_id'] for row in after}), 4)
        self.assertEqual(sum(row['status'] == 'collected_pending_review' for row in after), 2)

    async def test_unbound_row_after_reservation_stops_entry_enqueue_and_allocation(self):
        self.reserve()
        first = self.store(0); first.enqueue_plan(self.plans[0], self.publications[0])
        self.add_unbound()
        second = self.store(1)
        with self.assertRaisesRegex(ValueError, 'history drift'):
            verify_entry(self.plans[1], self.registry, self.config['sites'][1]['batches'][0]['output'])
        with self.assertRaisesRegex(ValueError, 'history drift'):
            second.enqueue_plan(self.plans[1], self.publications[1])
        with self.assertRaisesRegex(ValueError, 'history drift'):
            first.claim_next('worker', request_id='before-new-number')
        self.assertEqual(self.counts(), (3, 0))

    async def test_modified_reserved_peer_is_not_filtered(self):
        self.reserve()
        first = self.store(0); first.enqueue_plan(self.plans[0], self.publications[0])
        altered = deepcopy(self.plans[0]['tasks'][0]); altered['instruction'] += '已被外部改写'
        with closing(sqlite3.connect(self.registry)) as con, con:
            con.execute('UPDATE m4_tasks SET task_json=? WHERE scope_id=?', (json.dumps(altered), first.scope_id))
        with self.assertRaisesRegex(ValueError, 'exact tasks/metadata'):
            verify_entry(self.plans[1], self.registry, self.config['sites'][1]['batches'][0]['output'])
        self.assertEqual(self.counts(), (2, 0))

    async def test_removed_original_history_is_not_excused_by_peer_reservation(self):
        self.reserve()
        with closing(sqlite3.connect(self.registry)) as con, con:
            con.execute('DELETE FROM m4_tasks WHERE scope_id=?', (self.origin.scope_id,))
        with self.assertRaisesRegex(ValueError, 'history drift'):
            self.store(0).enqueue_plan(self.plans[0], self.publications[0])
        self.assertEqual(self.counts(), (0, 0))

    async def test_second_cohort_cannot_reuse_reserved_semantics_under_new_scope(self):
        first = self.reserve()
        changed = deepcopy(self.config)
        for index, site in enumerate(changed['sites']):
            site['batches'][0]['output'] = str(self.root / ('unstarted-reuse-' + str(index)))
        with self.assertRaisesRegex(ValueError, 'already reserved'):
            self.reserve(changed, 'cohort-conflict')
        with closing(sqlite3.connect(self.registry)) as con, con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM m4_admission_cohorts').fetchone()[0], 1)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM m4_admission_reservations').fetchone()[0], first['tasks_prebound'])
        self.assertEqual(self.counts(), (1, 0))

    async def test_same_meaning_peer_on_another_uri_cannot_enter_one_cohort(self):
        task, cap = self.real_schema_workflow('parameter-variant', 'https://example.edu/calculator',
                                            ('长度', '宽度', '计算面积'), '矩形面积为42平方厘米')
        plan, publication = self.published('published-variant', task, cap)
        batch = self.config['sites'][1]['batches'][0]
        fixture_json(batch['plan'], plan); fixture_json(batch['publication'], publication)
        with self.assertRaisesRegex(ValueError, 'duplicate meaning'):
            self.reserve()
        self.assertEqual(self.counts(), (1, 0))

    async def test_mixed_legacy_and_new_admission_schedule_is_explicitly_rejected(self):
        batch = self.config['sites'][1]['batches'][0]
        fixture_json(batch['plan'], self.old_plan); fixture_json(batch['publication'], self.old_publication)
        with self.assertRaisesRegex(ValueError, 'mixed observed-workflow/legacy/form'):
            self.reserve()
        self.assertEqual(self.counts(), (1, 0))

    async def test_changed_frozen_cohort_proof_stops_dispatch(self):
        self.reserve()
        path = self.root / 'cohort-schedule' / 'schedule.json'
        altered = load_json(path); altered['shared_policy']['max_workers'] = 7; fixture_json(path, altered)
        with self.assertRaisesRegex(ValueError, 'schedule proof missing or changed'):
            self.store(0).enqueue_plan(self.plans[0], self.publications[0])
        self.assertEqual(self.counts(), (1, 0))

    async def test_drift_after_start_prevents_success_but_preserves_failure_record(self):
        self.reserve()
        first = self.store(0); first.enqueue_plan(self.plans[0], self.publications[0])
        attempt = first.claim_next('worker', request_id='original-attempt')
        first.start_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'])
        self.add_unbound()
        refs = runtime_fixture.evidence(self.root / 'failure-proof', 'CONTROLLED interrupted evidence')
        with self.assertRaisesRegex(ValueError, 'history drift'):
            first.finish_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], 'collected_pending_review', evidence=refs)
        failed = first.finish_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'], 'rejected',
                                     failure_class='semantic', root_cause='history drift', evidence=refs)
        self.assertEqual(failed['status'], 'rejected')
        self.assertEqual(self.counts(), (3, 1))

    async def test_customer_anchor_manifest_and_package_drift_cannot_commit_success(self):
        self.reserve()
        first = self.store(0); first.enqueue_plan(self.plans[0], self.publications[0])
        attempt = first.claim_next('worker', request_id='customer-drift')
        first.start_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'])
        refs = runtime_fixture.evidence(self.root / 'customer-drift-proof')
        paths = [Path(self.history_scope['formal_anchor']['path']), Path(self.history_scope['manifest']['path']),
                 Path(self.history_scope['packages'][0]['path']) / 'README.md']
        for path in paths:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b'\n')
                    with self.assertRaisesRegex(ValueError, 'history|historical|evidence missing or changed'):
                        first.finish_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'],
                                             'collected_pending_review', evidence=refs)
                    self.assertEqual(first.snapshot()['attempts'][0]['status'], 'running')
                finally:
                    path.write_bytes(original)
        saved = first.finish_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'],
                                     'collected_pending_review', evidence=refs)
        self.assertEqual(saved['status'], 'collected_pending_review')

    async def test_full_customer_sha_reads_are_outside_writer_and_heartbeat_does_not_repeat_them(self):
        import webcollect.task_generation as generation
        actual = generation._history_package_files; checks = []
        def verify_unlocked(path):
            # A second writer can acquire the ledger while full file SHA reads
            # occur. It changes nothing and immediately rolls back.
            with closing(sqlite3.connect(self.registry, timeout=0)) as con:
                con.execute('BEGIN IMMEDIATE'); con.rollback()
            checks.append(str(path))
            return actual(path)
        self.reserve()
        first = self.store(0)
        with patch('webcollect.task_generation._history_package_files', side_effect=verify_unlocked):
            first.enqueue_plan(self.plans[0], self.publications[0])
            attempt = first.claim_next('worker', request_id='outside-writer')
            first.start_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'])
            before = len(checks)
            first.heartbeat(attempt['attempt_id'], 'worker', attempt['lease_token'])
            self.assertEqual(len(checks), before)
            first.finish_attempt(attempt['attempt_id'], 'worker', attempt['lease_token'],
                'collected_pending_review', evidence=runtime_fixture.evidence(self.root / 'outside-writer-proof'))
        self.assertGreaterEqual(len(checks), 8)

    async def test_customer_file_change_after_read_invalidates_content_proof_before_enqueue(self):
        self.reserve()
        first = self.store(0); original = first._customer_history_proof
        path = Path(self.history_scope['packages'][0]['path']) / 'README.md'
        def race(plan=None):
            proof = original(plan)
            path.write_text('CONTROLLED mutation between content read and writer transaction')
            return proof
        with patch.object(first, '_customer_history_proof', side_effect=race):
            with self.assertRaisesRegex(ValueError, 'content proof expired'):
                first.enqueue_plan(self.plans[0], self.publications[0])
        self.assertEqual(self.counts(), (1, 0))

    async def test_deleted_own_task_rows_cannot_pass_as_an_empty_resume(self):
        self.reserve()
        first = self.store(0); first.enqueue_plan(self.plans[0], self.publications[0])
        with closing(sqlite3.connect(self.registry)) as con, con:
            con.execute('DELETE FROM m4_tasks WHERE scope_id=?', (first.scope_id,))
        with self.assertRaisesRegex(ValueError, 'exact tasks/metadata'):
            first.claim_next('worker', request_id='deleted-own')
        self.assertEqual(self.counts(), (1, 0))

    async def test_duplicated_peer_projection_with_different_metadata_is_not_filtered(self):
        self.reserve()
        first = self.store(0); first.enqueue_plan(self.plans[0], self.publications[0])
        with closing(sqlite3.connect(self.registry)) as con, con:
            con.row_factory = sqlite3.Row
            row = dict(con.execute('SELECT * FROM m4_tasks WHERE scope_id=?', (first.scope_id,)).fetchone())
            row.update(task_key='CONTROLLED-copy-key', task_id='CONTROLLED-copy-id')
            con.execute('INSERT INTO m4_tasks VALUES(' + ','.join('?' for _ in row) + ')', tuple(row.values()))
            con.execute('INSERT INTO m4_plan_tasks VALUES(?,?,?,?)',
                        (first.scope_id, self.publications[0]['plan_sha256'], row['task_key'], 1))
        with self.assertRaisesRegex(ValueError, 'exact tasks/metadata'):
            verify_entry(self.plans[1], self.registry, self.config['sites'][1]['batches'][0]['output'])
        self.assertEqual(self.counts(), (3, 0))

    async def test_peer_immutable_metadata_and_plan_task_ordinal_are_bound(self):
        self.reserve()
        first = self.store(0); first.enqueue_plan(self.plans[0], self.publications[0])
        for statement, parameters in (
                ('UPDATE m4_tasks SET task_sha256=? WHERE scope_id=?', ('bad-hash', first.scope_id)),
                ('UPDATE m4_plan_tasks SET ordinal=? WHERE scope_id=?', (42, first.scope_id))):
            with closing(sqlite3.connect(self.registry)) as con:
                con.execute('SAVEPOINT controlled_mutation')
                con.execute(statement, parameters)
                # The same transaction guard must see its own uncommitted
                # corruption; another connection cannot mask this mutation.
                from webcollect.admission_cohort import guard_scope
                with self.assertRaisesRegex(ValueError, 'metadata|ordinal'):
                    guard_scope(con, self.registry, first.scope_id)
                con.execute('ROLLBACK TO controlled_mutation'); con.execute('RELEASE controlled_mutation')
        self.assertEqual(self.counts(), (2, 0))

    async def test_missing_membership_never_downgrades_reserved_scope_to_unbound(self):
        self.reserve()
        first = self.store(0)
        with closing(sqlite3.connect(self.registry)) as con, con:
            con.execute('DELETE FROM m4_admission_members WHERE scope_id=?', (first.scope_id,))
        with self.assertRaisesRegex(ValueError, 'membership missing'):
            verify_entry(self.plans[0], self.registry, self.config['sites'][0]['batches'][0]['output'])
        with self.assertRaisesRegex(ValueError, 'membership missing'):
            first.enqueue_plan(self.plans[0], self.publications[0])
        self.assertEqual(self.counts(), (1, 0))

    async def test_missing_member_and_signature_rows_still_cannot_erase_binding(self):
        self.reserve()
        first = self.store(0)
        with closing(sqlite3.connect(self.registry)) as con, con:
            con.execute('DELETE FROM m4_admission_members WHERE scope_id=?', (first.scope_id,))
            con.execute('DELETE FROM m4_admission_reservations WHERE scope_id=?', (first.scope_id,))
        with self.assertRaisesRegex(ValueError, 'cohort still declares a missing member'):
            first.enqueue_plan(self.plans[0], self.publications[0])
        self.assertEqual(self.counts(), (1, 0))


class CohortFixtureIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_nested_fixture_restores_every_global_patch_on_its_cleanup_owner(self):
        import playwright.async_api as api
        import webcollect.collect_runtime as runtime
        import webcollect.evidence as capture_evidence
        import webcollect.metadata as metadata
        targets = [(api, 'async_playwright'), (runtime, 'validate_sample'),
                   (capture_evidence, 'audit_capture'), (metadata, 'export_metadata')]
        original = [getattr(module, name) for module, name in targets]
        nested = concurrency_fixture.ConcurrentSitesTests('runTest')
        with ExitStack() as stack:
            owner = SimpleNamespace(addCleanup=stack.callback)
            await nested.asyncSetUp(cleanup_owner=owner)
            self.assertIsNone(nested._asyncioRunner)
            self.assertEqual(nested._cleanups, [])
            for (module, name), expected in zip(targets, original):
                self.assertIsNot(getattr(module, name), expected)
        for (module, name), expected in zip(targets, original):
            self.assertIs(getattr(module, name), expected)
        self.assertFalse(nested.root.exists())


if __name__ == '__main__':
    unittest.main()
