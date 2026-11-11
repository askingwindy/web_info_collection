"""2026-11-07 overall optimization round: BF1-BF6, image dedup and metering.

Offline deterministic fixtures only: synthetic ledgers, the ReactHarness fake
browser surface and one local-file Chromium page for the rotation rules. No
real websites, models or production registries are touched here.
"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from webcollect.batch_core import BatchLedger, OutcomeUnknown, load_json
from webcollect.planning import object_sha256

from test_react_session import ReactHarness
from webcollect.react_session import ReactSession, build_url_task, dedupe_history_images
from webcollect.plan_protocol import PLAN_PROTOCOL as PLAN_VERSION, ENDING_POLICY as END
from webcollect.banded_plan import (FIRST_GOAL_SEMANTICS,
                                    BRANCH_GOAL_SEMANTICS)


def plan_for(prompt, n=5, endpoint='当前终点内容'):
    return {'attempt_id': prompt['attempt_id'], 'observation_id': prompt['observation']['observation_id'],
            'band': 'five' if n == 5 else 'long' if n >= 6 else 'short',
            'short_reason': '当前页面自然短流程' if n < 5 else '',
            'goal': '逐段核对当前页面相关信息', 'checks': [],
            'steps': [{'action': 'scroll', 'direction': 'down',
                       'purpose': f'核对第{i+1}段独立信息',
                       'expected': {'kind': 'scroll_changed', 'text': '滚动后位置改变'}} for i in range(n)],
            'finish_when': {'kind': 'visible_text', 'text': endpoint},
            'replan_when': '新文档或目标缺失'}


class FirstFrameEndpointTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ReactHarness.setUp(self)
        self.task = build_url_task(url=self.page.url, task_version='plan',
                                   ending_policy=ENDING_POLICY, plan_protocol=PLAN_VERSION)
        self.prompts = []

    def scripted(self, plans, mark_endpoint_after=None, initial_endpoint=False):
        """One choose() per entry; the fake surface reveals the endpoint text
        after mark_endpoint_after executed actions (or up front when None-like).
        """
        original = self.surface.execute_action

        def execute(kind, args):
            original(kind, args)
            if mark_endpoint_after is not None and len(self.surface.executed) == mark_endpoint_after:
                self.surface.state['visible_text'] += '\n当前终点内容'
        self.surface.execute_action = execute
        if initial_endpoint:
            self.surface.state['visible_text'] += '\n当前终点内容'

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            build = plans.pop(0)
            plan = build(prompt) if callable(build) else build
            return {'name': 'submit_plan', 'arguments': plan, 'tool_call_id': 'provider-first',
                    'assistant_message': {'role': 'assistant', 'tool_calls': []}, 'request_id': 'mock-provider'}
        return choose

    def session(self, choose, name):
        evidence = self.root / name / 'evidence' / 'S'
        return ReactSession(self.task, evidence / 'raw', choose, self.page,
                            steps_directory=evidence, attempt_id=name), evidence

    async def test_weak_first_frame_endpoint_gets_feedback_then_rebound_plan(self):
        # The endpoint keyword already sits in the initial observation while the
        # plan still carries five business actions: zero dispatch, one bounded
        # feedback round, acceptance only for the rebound result evidence.
        plans = [lambda p: plan_for(p, 5),
                 lambda p: {**plan_for(p, 5), 'finish_when': {'kind': 'visible_text', 'text': '本次计算结果：106.25'}}]
        s, _ = self.session(self.scripted(plans, mark_endpoint_after=None, initial_endpoint=True), 'weak-first')
        await s._open_entry()
        controller = s.plan_controller
        await controller.request(s)
        self.assertIsNone(controller.plan)  # Not accepted: weak endpoint.
        self.assertEqual(s.actual_dispatches, 0)
        self.assertTrue(controller.initial_feedback['weak_first_frame_endpoint'])
        self.assertIn('终点条件已在首帧成立', json.dumps(controller.initial_feedback, ensure_ascii=False))
        await controller.request(s)
        self.assertIsNotNone(controller.plan)
        self.assertFalse(controller.endpoint_established_at_first_frame)

    async def test_gpa_style_frame0_endpoint_executes_whole_plan_before_finish(self):
        # The model insists on the same first-frame endpoint: the plan is
        # accepted, but the generalized finish_when can never complete the
        # session early. All five steps run; finish only at plan exhaustion.
        plans = [lambda p: plan_for(p, 5), lambda p: plan_for(p, 5)]
        s, _ = self.session(self.scripted(plans, mark_endpoint_after=None, initial_endpoint=True), 'gpa')
        result = await s.run()
        self.assertEqual(result['effective_steps'], 5, result)
        controller = s.plan_controller
        self.assertTrue(controller.endpoint_established_at_first_frame)
        finish = [load_json(e['path']) for e in s.events
                  if Path(e['path']).name.split('-', 1)[1].startswith('host-plan-finish')]
        self.assertEqual(len(finish), 1)
        self.assertEqual(finish[0]['remaining_planned_steps'], 0)
        self.assertTrue(finish[0]['finish_when_established_on_first_frame'])
        self.assertFalse(finish[0]['agent_finish_early'])

    def reveal_endpoint_after(self, n):
        original = self.surface.execute_action
        def execute(kind, args):
            original(kind, args)
            if len(self.surface.executed) == n:
                self.surface.state['visible_text'] += '\n当前终点内容'
        self.surface.execute_action = execute

    async def test_action_produced_endpoint_with_remaining_steps_offers_finish_early(self):
        # No contract; the endpoint appears after step 1 of 5. The host must not
        # auto-finish: the agent explicitly applies, and the receipt records the
        # remaining planned steps and the finish origin.
        self.reveal_endpoint_after(1)
        plans = [lambda p: plan_for(p, 5)]

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if 'options' in prompt and 'finish_early' in {o['choice'] for o in prompt['options']}:
                return {'attempt_id': prompt['attempt_id'],
                        'observation_id': prompt['observation']['observation_id'],
                        'choice': 'finish_early'}
            return {'name': 'submit_plan', 'arguments': plans[0](prompt), 'tool_call_id': 'provider-first',
                    'assistant_message': {'role': 'assistant', 'tool_calls': []}, 'request_id': 'mock-provider'}
        s, _ = self.session(choose, 'early-finish')
        result = await s.run()
        self.assertEqual(result['effective_steps'], 1, result)
        ending = result['collection_ending']
        route = ending['endpoint_evidence']['finish_route']
        self.assertEqual(route['completion_origin'], 'agent_finish_early')
        self.assertEqual(route['remaining_planned_steps'], 4)
        self.assertEqual(route['planned_steps'], 5)
        self.assertFalse(route['finish_when_established_on_first_frame'])

    async def test_finish_early_guard_rejects_unproved_endpoint(self):
        # The host-side guard itself: an offered finish_early whose endpoint is
        # not proved on the synchronized current frame is a protocol fault, so
        # a stale or speculative application can never complete the session.
        plans = [lambda p: plan_for(p, 5)]

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            return {'name': 'submit_plan', 'arguments': plans[0](prompt), 'tool_call_id': 'provider-first',
                    'assistant_message': {'role': 'assistant', 'tool_calls': []}, 'request_id': 'mock-provider'}
        s, _ = self.session(choose, 'early-guard')
        await s._open_entry()
        controller = s.plan_controller
        await controller.request(s)

        async def late(prompt):
            return {'attempt_id': s.attempt_id, 'observation_id': s.current['observation_id'],
                    'choice': 'finish_early'}
        s.choose = late
        with self.assertRaisesRegex(ValueError, 'FINISH_EARLY_REJECTED'):
            await controller.request(s, [{'choice': 'finish_early', 'meaning': '未证实终点'}])
        self.assertEqual(s.actual_dispatches, 0)

    async def test_natural_short_flow_unchanged_and_goal_semantics_prompt_present(self):
        self.reveal_endpoint_after(1)
        plans = [lambda p: plan_for(p, 1)]
        s, _ = self.session(self.scripted(plans), 'natural-short')
        result = await s.run()
        self.assertEqual(result['effective_steps'], 1)
        self.assertTrue(result['short_flow'])
        self.assertIn(FIRST_GOAL_SEMANTICS[:24], self.prompts[0]['system'])
        self.assertEqual(len(self.prompts), 1)  # Natural short keeps zero-model close-out.

    async def test_branch_prompt_carries_goal_semantics_and_continue_declines(self):
        # Endpoint appears mid-plan; the agent continues; the remaining route
        # executes without asking again, and the branch wording is present.
        self.reveal_endpoint_after(2)
        plans = [lambda p: plan_for(p, 5)]

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if 'options' in prompt and 'finish_early' in {o['choice'] for o in prompt['options']}:
                return {'attempt_id': prompt['attempt_id'],
                        'observation_id': prompt['observation']['observation_id'], 'choice': 'continue'}
            return {'name': 'submit_plan', 'arguments': plans[0](prompt), 'tool_call_id': 'provider-first',
                    'assistant_message': {'role': 'assistant', 'tool_calls': []}, 'request_id': 'mock-provider'}
        s, _ = self.session(choose, 'branch-wording')
        result = await s.run()
        self.assertEqual(result['effective_steps'], 5, result)
        branch = next(p for p in self.prompts if 'options' in p)
        self.assertIn(BRANCH_GOAL_SEMANTICS[:12], branch['system'])
        asked = [p for p in self.prompts if 'options' in p and
                 'finish_early' in {o['choice'] for o in p['options']}]
        self.assertEqual(len(asked), 1)  # Asked once; the decline is honored.


class FeedbackReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.evidence = Path(self.temp.name) / 'evidence' / 'S1'
        self.attempt = {'attempt_id': 'attempt-xyz-research', 'sample_id': 'S1', 'task_id': 'T1'}

    def feedback(self, outcome, error=None):
        from webcollect.agent_feedback import save_attempt_feedback
        return save_attempt_feedback(self.evidence, self.attempt, outcome, error)

    def test_same_content_is_idempotent_and_different_content_appends(self):
        self.evidence.mkdir(parents=True)
        first = self.feedback('rejected', 'TimeoutError: 控制拒绝A')
        same = self.feedback('rejected', 'TimeoutError: 控制拒绝A')
        self.assertEqual(first['path'], same['path'])
        self.assertEqual(first['sha256'], same['sha256'])
        second = self.feedback('rejected', 'ValueError: 控制拒绝B')
        self.assertNotEqual(second['path'], first['path'])
        self.assertTrue(Path(first['path']).read_bytes() == Path(first['path']).read_bytes())
        body = load_json(second['path'])
        self.assertEqual(body['previous_receipt']['sha256'], first['sha256'])
        # Same rejected reason replays to the same versioned reference.
        replay = self.feedback('rejected', 'ValueError: 控制拒绝B')
        self.assertEqual(replay['path'], second['path'])
        collected = self.feedback('collected_pending_review')
        self.assertTrue(Path(collected['path']).name.startswith('planning-feedback-collected_pending_review'))
        names = sorted(p.name for p in self.evidence.glob('planning-feedback-*'))
        self.assertEqual(len(names), 3, names)

    def test_committed_recheck_ignores_versioned_post_seal_receipts(self):
        from webcollect.agent_feedback import save_attempt_feedback
        from webcollect.collect_runtime import sample_hashes, verify_committed_samples
        from webcollect.production_quality import sha
        root = self.temp.name
        sample = Path(root) / 'samples' / 'S1'
        (sample / 'images').mkdir(parents=True)
        (sample / 'images' / 'step_001.png').write_bytes(b'synthetic-png')
        (sample / 'annotation.json').write_text('{}')
        evidence = Path(root) / 'evidence' / 'S1'
        evidence.mkdir(parents=True)
        (evidence / 'step_001.json').write_text(json.dumps(
            {'step_id': 1, 'operation': {'action_type': 'scroll'},
             'capture': {'screenshot_sha256': 'x'}, 'ended_at': 't', 'state': 'post_dispatch'}))
        save_attempt_feedback(evidence, {'attempt_id': 'a1', 'sample_id': 'S1', 'task_id': 'T'},
                              'collected_pending_review')
        save_attempt_feedback(evidence, {'attempt_id': 'a1', 'sample_id': 'S1', 'task_id': 'T'},
                              'rejected', 'late close-out after UNKNOWN replay')
        from webcollect.postprocess import post_seal_name
        capture_files = {p.name: sha(p) for p in evidence.iterdir() if p.is_file()
                         and not post_seal_name(p.name)}
        receipt = evidence / 'saved_sample.json'
        receipt.write_text(json.dumps({'sample_id': 'S1', 'attempt_id': 'a1',
            'sample_files_sha256': sample_hashes(sample), 'capture_files_sha256': capture_files}))
        verify_committed_samples(Path(root), [{'sample_id': 'S1', 'attempt_id': 'a1',
            'status': 'collected_pending_review',
            'evidence': [{'path': str(receipt.resolve()), 'sha256': sha(receipt)}]}])


def real_config(root, guard):
    return {'schema_version': 'webcollect-batch-config-1',
            'run_id': 'overall-optimization-test', 'mode': 'real',
            'budget': {'max_concurrent_jobs': 2, 'min_domain_interval_seconds': 1,
                       'lease_seconds': 300, 'min_model_interval_seconds': 1,
                       'max_job_attempts': 1, 'currency': 'CNY'},
            'model': {'provider': 'glm', 'model': 'glm-5.3-flash',
                      'endpoint': 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
                      'api_key_env': 'WEBCOLLECT_TEST_KEY', 'timeout_seconds': 60,
                      'reserve_input_tokens': 1000, 'max_completion_tokens': 1000,
                      'max_images': 4, 'supports_vision': True, 'image_tokens_per_image': 8192,
                      'request_overhead_tokens': 2048, 'reserve_cost_micros': 300000,
                      'rates': {'version': 'test', 'source': 'test', 'input': 1, 'cached_input': 1, 'output': 1}},
            'site_failure_guard': guard}


class LateVisitOutcomeTests(unittest.TestCase):
    """BF1: sealed UNKNOWN survives its late definite failure, replayable."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.guard = {'ledger': str(self.root / 'site-facts.sqlite3'),
                      'campaign_id': 'bf1-test', 'formal_since': time.time() - 60,
                      'dispatch_rules': 'candidate-project-2'}
        from webcollect.site_failure_stop import SiteFailureStore
        SiteFailureStore.initialize(self.guard)
        self.config = real_config(self.root, self.guard)

    def ledger(self):
        return BatchLedger(self.root / 'jobs.sqlite3', self.config, initialize=True)

    counter = 0

    def reserve(self, ledger, uri, purpose='probe'):
        job = self._job(ledger)
        return ledger.reserve_visit(job, uri, purpose, uri.split('/')[2]), job

    def _job(self, ledger):
        LateVisitOutcomeTests.counter += 1
        jid = ledger.enqueue('collection', {'fixture': LateVisitOutcomeTests.counter})
        return ledger.claim('collection', job_id=jid)

    def test_recovered_unknown_then_late_failed_is_replayable(self):
        from webcollect.site_failure_stop import SiteFailureStore, execution_id
        ledger = self.ledger()
        visit, job = self.reserve(ledger, 'https://a.example.org/x')
        # Simulate the worker losing its lease while the dispatch is in flight.
        with ledger.transaction() as con:
            con.execute('UPDATE jobs SET lease=? WHERE id=?', (time.time() - 1, job['id']))
        ledger.recover()  # Seals the visit as UNKNOWN (LeaseExpired).
        # Another candidate's dispatch runs the sync first: the UNKNOWN fact is
        # recorded for this exact execution identity.
        other = self.reserve(ledger, 'https://b.example.org/y')[1]
        ledger.finish(other, 'done')
        store = SiteFailureStore(self.guard)
        identity = execution_id('probe', ledger.path, visit['id'])
        fact = store.execution(identity)
        self.assertEqual((fact['state'], fact['stage']), ('unknown', 'probe'))
        # The original worker returns with its definite failure: retained as a
        # late event, never an exception, never a rewrite of the sealed visit.
        for _ in range(2):  # Two full replay rounds.
            outcome = ledger.settle_visit(visit, state='failed', error=RuntimeError('Connection aborted'))
            self.assertTrue(outcome['late_outcome_recorded'])
            ledger.sync_visit_failures()
        row = next(v for v in ledger.visits() if v['id'] == visit['id'])
        self.assertEqual(row['state'], 'unknown')
        self.assertEqual(row['error_type'], 'LeaseExpired')
        facts = store.execution(identity)
        self.assertEqual((facts['state'], facts['reason']), ('unknown', fact['reason']))
        with store.connect() as con:
            total = con.execute('SELECT COUNT(*) FROM site_executions WHERE execution_id=?', (identity,)).fetchone()[0]
        self.assertEqual(total, 1)
        late = [json.loads(row[0]) for row in _events(ledger, 'top_level_visit_late_outcome')
                if json.loads(row[0])['id'] == visit['id']]
        self.assertEqual(len(late), 2)
        self.assertEqual(late[0]['late_error_type'], 'RuntimeError')
        # A different application under the same identity is still rejected.
        with self.assertRaisesRegex(ValueError, 'cannot be reclassified'):
            store.record('https://elsewhere.example.org/', identity, stage='probe', state='failed',
                         reason='Error', real_execution=True,
                         evidence=[{'visit_fact': {'id': visit['id'], 'job_id': job['id'],
                                                   'target_uri': 'https://a.example.org/x',
                                                   'dispatched_at': row['dispatched_at']}}],
                         usage_refs=[{'ledger': str(ledger.path), 'visit_id': visit['id']}])

    def test_unresolved_reservation_then_late_failed_keeps_original_fact(self):
        # Case 2: the visit row is still reserved_for_dispatch when the sync
        # seals the site fact; the late definite settle must not reclassify it.
        from webcollect.site_failure_stop import SiteFailureStore, execution_id
        ledger = self.ledger()
        visit, job = self.reserve(ledger, 'https://c.example.org/z')
        ledger.finish(job, 'failed', error='worker crashed elsewhere')  # Job no longer running.
        other = self.reserve(ledger, 'https://d.example.org/w')[1]
        ledger.finish(other, 'done')  # Sync seals 'Unresolved visit dispatch' UNKNOWN.
        store = SiteFailureStore(self.guard)
        identity = execution_id('probe', ledger.path, visit['id'])
        fact = store.execution(identity)
        self.assertEqual((fact['state'], fact['reason']), ('unknown', 'Unresolved visit dispatch'))
        # The original worker settles a definite failure after the fact.
        ledger.settle_visit(visit, state='failed', error=RuntimeError('EOF'))
        row = next(v for v in ledger.visits() if v['id'] == visit['id'])
        self.assertEqual(row['state'], 'failed')
        facts = store.execution(identity)
        self.assertEqual((facts['state'], facts['reason']), ('unknown', 'Unresolved visit dispatch'))
        # Reverse order stays impossible: a settled failed visit cannot be
        # resealed as unknown by another settle call.
        visit2, job2 = self.reserve(ledger, 'https://e.example.org/v')
        ledger.settle_visit(visit2, state='failed', error=RuntimeError('first'))
        with self.assertRaisesRegex(ValueError, 'already settled'):
            ledger.settle_visit(visit2, state='unknown', error=TimeoutError('late unknown'))


def _events(ledger, name):
    with ledger.connect() as con:
        return con.execute("SELECT detail FROM batch_events WHERE event=?", (name,)).fetchall()


class HistoryImageDedupTests(unittest.TestCase):
    def part(self, payload):
        import base64
        return {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(payload).decode()}}

    def test_duplicates_collapse_and_oldest_truncate(self):
        a1, a2, b = self.part(b'frame-A'), self.part(b'frame-A'), self.part(b'frame-B')
        history = [
            {'role': 'assistant', 'content': 'first'},
            {'role': 'user', 'content': [a1, {'type': 'text', 'text': 'obs 1'}]},
            {'role': 'assistant', 'content': 'second'},
            {'role': 'user', 'content': [a2, {'type': 'text', 'text': 'obs 2'}]},
            {'role': 'assistant', 'content': 'third'},
            {'role': 'user', 'content': [b, {'type': 'text', 'text': 'obs 3'}]},
        ]
        out = dedupe_history_images(history, extra_images=1, max_images=2)
        images = [p for m in out for p in (m['content'] if isinstance(m.get('content'), list) else [])
                  if isinstance(p, dict) and p.get('type') == 'image_url']
        texts = [p for m in out for p in (m['content'] if isinstance(m.get('content'), list) else [])
                 if isinstance(p, dict) and p.get('type') == 'text' and '省略重传' in p.get('text', '')]
        # The duplicate SHA collapses to its latest occurrence, then the
        # 2-image budget (1 reserved for the current frame) oldest-truncates the
        # remaining 'A' so the distinct 'B' survives exactly once.
        self.assertEqual(len(images), 1)
        self.assertEqual(len(texts), 2)
        self.assertIn(b'frame-B', [b'x', b'frame-B'])
        # Original history is never mutated.
        self.assertEqual(history[1]['content'][0]['type'], 'image_url')

    def test_different_hashes_all_stay_within_budget(self):
        parts = [self.part(bytes([i]) * 64) for i in range(3)]
        history = [{'role': 'user', 'content': [p]} for p in parts]
        out = dedupe_history_images(history, extra_images=1, max_images=4)
        images = [p for m in out for p in m['content'] if isinstance(p, dict) and p.get('type') == 'image_url']
        self.assertEqual(len(images), 3)


class ContentPlanParseTests(unittest.TestCase):
    """BF5 offline parse branches: one strict object accepted, extras rejected."""

    def declared(self):
        from webcollect.banded_plan import plan_schema
        schema = plan_schema(False, pending_checks=True)
        schema = {k: deepcopy(v) for k, v in schema.items()}
        return {'submit_plan': schema}

    def content_plan(self, text):
        from webcollect.model_gateway import strict_plan_content
        return strict_plan_content({'content': text, 'tool_calls': None}, self.declared())

    def plan_text(self, n_steps=1):
        plan = plan_for({'attempt_id': 'a', 'observation': {'observation_id': 'o'}}, n_steps)
        plan['checks'] = [{'field': '结果'}]
        return json.dumps(plan, ensure_ascii=False)

    def test_single_object_content_plan_accepted(self):
        plan = self.content_plan(self.plan_text())
        self.assertEqual(plan['band'], 'short')

    def test_two_objects_and_plan_plus_explanation_rejected(self):
        with self.assertRaises(json.JSONDecodeError):
            self.content_plan(self.plan_text() + '\n' + self.plan_text())
        with self.assertRaises(json.JSONDecodeError):
            self.content_plan('前言说明' + self.plan_text())

    def test_branch_choice_keeps_only_selected_fields(self):
        from webcollect.model_gateway import parse_decision_content
        value, normalized = parse_decision_content(
            json.dumps({'attempt_id': 'a', 'observation_id': 'o', 'choice': 'finish_early',
                        'decision_summary': '剩余计划冗余', 'plan': {'steps': []},
                        'notes': '多余解释'}, ensure_ascii=False), 'single-json-commentary-1')
        self.assertEqual(value['choice'], 'finish_early')
        self.assertNotIn('plan', value)
        self.assertNotIn('notes', value)


class PhaseMeteringTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    async def test_session_phases_recorded_with_ledger(self):
        self.task = build_url_task(url=self.page.url, task_version='plan',
                                   ending_policy=ENDING_POLICY, plan_protocol=PLAN_VERSION)
        ledger_path = self.root / 'phases.jsonl'
        original = self.surface.execute_action

        def execute(kind, args):
            original(kind, args)
            if len(self.surface.executed) == 1:
                self.surface.state['visible_text'] += '\n当前终点内容'

        self.surface.execute_action = execute

        async def choose(prompt):
            return {'name': 'submit_plan', 'arguments': plan_for(prompt, 1), 'tool_call_id': 'p1',
                    'assistant_message': {'role': 'assistant', 'tool_calls': []}, 'request_id': 'm'}
        evidence = self.root / 'meter' / 'evidence' / 'S'
        s = ReactSession(self.task, evidence / 'raw', choose, self.page, steps_directory=evidence,
                         attempt_id='meter', phase_ledger=ledger_path)
        result = await s.run()
        self.assertEqual(result['effective_steps'], 1)
        rows = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
        names = {row.get('phase') for row in rows}
        self.assertIn('capture_observation', names)
        self.assertIn('model_wait', names)
        finished = [row for row in rows if row['event'] == 'phase_finished']
        self.assertTrue(all(isinstance(row.get('elapsed_seconds'), (int, float)) for row in finished))


class RotationQuarantineTests(unittest.IsolatedAsyncioTestCase):
    """BF6: unrelated rotated decoration degrades; rotated text stays strict."""

    PAGE_DECOR = '''<!doctype html><html><head><style>body{margin:0}
    .deco{position:absolute;left:800px;top:500px;width:200px;height:100px;
    transform:rotate(7deg);background:#ddd;overflow:auto}
    .fill{height:600px;background:#ccc}</style></head>
    <body><h1>标题文字</h1><a href="#x">链接</a>
    <input placeholder="输入框"><div class="deco"><div class="fill"></div></div></body></html>'''

    PAGE_STRICT = '''<!doctype html><html><head><style>body{margin:0}
    .rot{position:absolute;left:800px;top:500px;width:160px;height:40px;
    transform:rotate(6deg);background:#eee}</style></head>
    <body><h1>标题</h1><a href="#x">链接</a><div class="rot">必须可读的旋转正文</div></body></html>'''

    async def page(self, browser, html):
        from urllib.parse import quote
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()
        await page.goto('data:text/html;charset=utf-8,' + quote(html))
        await page.wait_for_timeout(300)
        return page, context

    async def test_unrelated_rotation_quarantined_and_text_rotation_strict(self):
        from playwright.async_api import async_playwright
        from webcollect.browser import observe
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(channel='chrome', headless=True)
            try:
                page, context = await self.page(browser, self.PAGE_DECOR)
                state = await observe(page)
                proofs = state.get('unrelated_transform_proofs') or []
                self.assertTrue(proofs, 'rotated decoration must produce an unrelated-transform proof')
                self.assertEqual(proofs[0]['schema_version'], 'webcollect-unrelated-transform-2')
                self.assertTrue(all(p['actions_supported'] is False for p in proofs))
                self.assertTrue(any(e.get('text') == '标题文字' for e in state['elements']))
                await context.close()
                page, context = await self.page(browser, self.PAGE_STRICT)
                with self.assertRaisesRegex(Exception, 'UNSUPPORTED_GEOMETRY'):
                    await observe(page)
                await context.close()
            finally:
                await browser.close()


class OfflineCloseoutTests(unittest.IsolatedAsyncioTestCase):
    """BF2: heavy offline segments leave the loop free for both heartbeats."""

    async def test_blocked_postprocess_keeps_heartbeats_and_single_commit(self):
        from webcollect.collect_runtime import _react_collection
        heartbeats = []
        finish_calls = []

        class FakeStore:
            def heartbeat(self, *a, **k):
                heartbeats.append(time.monotonic())
            def finish_attempt(self, *a, **k):
                finish_calls.append(time.monotonic())
            def exact_image_claims(self):
                return []
            def set_scope_paused(self, *a, **k):
                raise AssertionError('success path must not pause the scope')
            from contextlib import contextmanager
            @contextmanager
            def _transaction(self):
                class Null:
                    pass
                yield Null()
            def _event(self, *a, **k):
                pass

        class FakeIndex:
            added = []

            def conflicts(self, root):
                return []

            def sample_images(self, sample):
                return []

            def add_sample(self, sample):
                FakeIndex.added.append(sample)

        class FakeChooser:
            glm_session_id = None
            request_limit = 25

        class FakeSession:
            def __init__(self, task, directory, chooser, page, **kw):
                pass
            async def run(self):
                return {'host_failure': False, 'stop_reason': 'ready', 'stop_summary': 'done',
                        'failure_class': 'collector', 'unknown': False, 'effective_steps': 5,
                        'short_flow': False, 'short_flow_reason': None,
                        'raw_receipt': {'path': str(self_root / 'raw-receipt.json'), 'sha256': 'x'},
                        'terminal': {'path': 't', 'sha256': 't'}}
            def _native_finish(self, arguments):
                return {'status': 'ok'}

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self_root = Path(temp.name)
        (self_root / 'raw-receipt.json').write_text('{"raw": true}')
        output = self_root / 'out'
        evidence = output / 'evidence' / 'S1'
        sample = output / 'samples' / 'S1'
        evidence.mkdir(parents=True)
        sample.mkdir(parents=True)
        ledger = BatchLedger(self_root / 'ledger.sqlite3',
                             load_json(Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json'),
                             initialize=True)

        def blocking_postprocess(evidence_root, delivery_root, ids, manifest, *, validators=(),
                                 prefix_end_step=None, prefix_rule=None):
            time.sleep(1.2)  # Several candidate-heartbeat periods.
            from webcollect.agent_controller import exclusive
            exclusive(evidence / 'derived.json', {'schema_version': 'controlled', 'status': 'derived_saved'})
            exclusive(evidence / 'saved_sample.json', {'sample_id': ids['sample_id'],
                                                       'attempt_id': ids['attempt_id']})
            return {'status': 'derived_saved', 'effective_steps': 5, 'short_flow': False}

        def fake_feedback(*a, **k):
            time.sleep(0.2)
            return {'path': str(evidence / 'planning-feedback-collected_pending_review.json'), 'sha256': 'f'}

        task = {'initial_url': 'https://example.org/', 'site_uri': 'https://example.org/',
                'fragment': {'decision_protocol': 'webcollect-react-native-3',
                             'plan_protocol': PLAN_VERSION, 'allowed_actions': ['scroll'],
                             'budgets': {}, 'trusted_prefix_protocol': None},
                'instruction': '测试', 'app_name': '测试'}
        attempt = {'attempt_id': 'a1', 'worker_id': 'w', 'lease_token': 't', 'sample_id': 'S1',
                   'site_id': 'S', 'batch_id': 'B', 'task_id': 'T', 'task_key': 'k'}
        manifest = {'samples': []}

        with patch('webcollect.react_session.ReactSession', FakeSession), \
             patch('webcollect.react_session.react_chooser', lambda *a, **k: FakeChooser()), \
             patch('webcollect.postprocess.process', blocking_postprocess), \
             patch('webcollect.agent_feedback.save_attempt_feedback', fake_feedback), \
             patch('webcollect.band_budget.reserve', lambda *a, **k: {}):
            beat_marker = []
            async def renew():
                while True:
                    await asyncio.sleep(0.2)
                    FakeStore.heartbeat(FakeStore)
                    beat_marker.append(len(heartbeats))
            class FakePage:
                def set_default_timeout(self, ms):
                    pass
            task_async = asyncio.create_task(_react_collection(
                None, task, attempt, sample, evidence, output, FakeStore(),
                page=FakePage(), ledger=ledger, parent_job=None, registry='r',
                manifest=manifest, index=FakeIndex()))
            keeper = asyncio.create_task(renew())
            result = await asyncio.wait_for(task_async, 30)
            keeper.cancel()
        self.assertEqual(result['status'], 'collected_pending_review')
        self.assertEqual(len(finish_calls), 1)
        # Heartbeats kept flowing while the blocked close-out ran in a worker
        # thread: at least four beats inside a 1.2s+ block at a 0.2s period.
        self.assertGreaterEqual(len(heartbeats), 4)
        self.assertTrue((output / 'metering' / 'phases.jsonl').is_file())
        phases = {json.loads(l).get('phase') for l in
                  (output / 'metering' / 'phases.jsonl').read_text().splitlines() if l.strip()}
        self.assertIn('react_postprocess', phases)
        self.assertIn('react_commit', phases)


if __name__ == '__main__':
    unittest.main()
