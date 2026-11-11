"""2026-11-06 consumer A/B repair integration (R1-R6): offline fixtures only.

Covers the first-stage acceptance table from the repair plan: target binding
and branch semantics, plan-length facts, dynamic paint/geometry containment,
inventory recheck handling, the eight-slot single-shot A/B entry on temporary
stores, and outbound effort attribution. No real site, no real GLM, no
production pool mutation.
"""
import asyncio
from copy import deepcopy
from io import BytesIO
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock
from unittest.mock import patch

from PIL import Image, ImageDraw

from webcollect.plan_protocol import PLAN_PROTOCOL as VERSION, ENDING_POLICY
from webcollect.banded_plan import (validate_plan, bind_target, band_for_steps,
                                    remaining_step_allowance, Controller)
from webcollect import dynamic_regions
from webcollect.browser import stability_pair
import webcollect.consumer_ab as consumer_ab
from test_banded_plan import plan_for
from test_react_session import ReactHarness


CONFIG = Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json'


def _png(size, painter):
    image = Image.new('RGB', size, 'white')
    painter(ImageDraw.Draw(image))
    out = BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


class IdentityBindingTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    """R1: unique node identity with href/visibility evidence binds without text."""

    def setUp(self):
        ReactHarness.setUp(self)
        self.task = None

    async def _observed(self, name='bind'):
        from webcollect.react_session import ReactSession, build_url_task
        from webcollect.plan_protocol import ENDING_POLICY as END
        self.task = build_url_task(url=self.page.url, task_version='plan', ending_policy=END,
                                   plan_protocol=VERSION)
        ids = {'sample_id': 'S000101_sample_000001', 'site_id': 'S000101', 'batch_id': 'B20261106_101',
               'attempt_id': 'offline-bind'}
        evidence = self.root / name / 'evidence' / ids['sample_id']
        session = ReactSession(self.task, evidence / 'raw', AsyncChoose([]), self.page,
                               steps_directory=evidence, attempt_id='offline-bind')
        await session._observe()
        return session

    async def test_icon_link_binds_by_node_and_href_without_text(self):
        session = await self._observed()
        cid = sorted(session.current['controls'])[0]
        control = session.current['controls'][cid]
        control['element']['text'] = ''
        control['readable_labels'] = []
        control['binding']['href'] = 'https://example.org/doc/'
        target = {'text': '文档', 'href': 'https://example.org/doc/', 'node': cid,
                  'observation_id': session.current['observation_id']}
        self.assertEqual(bind_target(session.current, target), [cid])
        # A declared href that differs from the node's own binding is a conflict.
        self.assertEqual(bind_target(session.current, {**target, 'href': 'https://other.example/'}, session.observation_records), [])
        # A visible label that disagrees with the declaration stays a conflict.
        control['element']['text'] = '下载'
        self.assertEqual(bind_target(session.current, target, session.observation_records), [])
        control['element']['text'] = ''
        control['readable_labels'] = [{'text': '文档中心'}]
        self.assertEqual(bind_target(session.current, target, session.observation_records), [])


class AsyncChoose:
    def __init__(self, script):
        self.script = list(script)
        self.prompts = []

    async def __call__(self, prompt):
        self.prompts.append(deepcopy(prompt))
        if not self.script:
            raise AssertionError('model script exhausted')
        item = self.script.pop(0)
        return item(prompt) if callable(item) else deepcopy(item)


class BranchSemanticsTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    """R1: the 2026-11-06 spinning loops stop in a handful of calls."""

    def setUp(self):
        ReactHarness.setUp(self)
        from webcollect.react_session import build_url_task
        from webcollect.plan_protocol import ENDING_POLICY as END
        self.task = build_url_task(url=self.page.url, task_version='plan', ending_policy=END,
                                   plan_protocol=VERSION)
        self.ids = {'sample_id': 'S000102_sample_000001', 'site_id': 'S000102',
                    'batch_id': 'B20261106_102', 'attempt_id': 'offline-branch'}

    def _session(self, choose, name):
        from webcollect.react_session import ReactSession
        evidence = self.root / name / 'evidence' / self.ids['sample_id']
        return ReactSession(self.task, evidence / 'raw', choose, self.page,
                            steps_directory=evidence, attempt_id=self.ids['attempt_id'])

    @staticmethod
    def _missing_target_plan(prompt):
        plan = plan_for(prompt)
        plan['steps'][0] = {'action': 'click',
                            'target': {'text': '页脚关于我们栏目内联系我们', 'region_hint': '页脚'},
                            'purpose': '进入联系我们页', 'expected': {'kind': 'url', 'text': 'lxwm'}}
        return plan

    async def test_repeated_original_image_choice_stops_far_below_25_calls(self):
        choose = AsyncChoose([])
        choose.script = [
            (lambda prompt: {'name': 'submit_plan',
                             'arguments': self._missing_target_plan(prompt),
                             'tool_call_id': 'provider-first'})
        ]
        for _ in range(30):
            def reply(prompt):
                return {'attempt_id': prompt['attempt_id'],
                        'observation_id': prompt['observation']['observation_id'],
                        'choice': 'original', 'decision_summary': '继续按原计划执行'}
            choose.script.append(reply)
        session = self._session(choose, 'spin')
        result = await session.run()
        self.assertEqual(result['actual_actions'], 0)
        self.assertNotEqual(result.get('stop_reason'), 'ready', result)
        # First plan + first image view + one repeat refusal: bounded far below 25.
        self.assertLessEqual(len(choose.prompts), 4, [p.get('phase') for p in choose.prompts])
        image_events = [p for p in choose.prompts
                        if any(o.get('choice') == 'request_original_image' for o in (p.get('options') or []))]
        self.assertEqual(len(image_events), 1, 'image option must be offered exactly once per context')
        feedback = choose.prompts[-1].get('binding_feedback')
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback['executed_effective_steps'], 0)
        self.assertTrue(feedback['original_image_provided'])

    async def test_image_choice_renamed_in_v10_options(self):
        session = self._session(AsyncChoose([]), 'rename')
        controller = session.plan_controller
        await session._observe()
        # Direct option inspection: the offered names never contain the old one.
        options = controller.image_option(session, 'ctx')
        self.assertEqual([o['choice'] for o in options], ['request_original_image'])
        controller.provided_original_for.add((session.current['observation_id'], 'ctx'))
        self.assertEqual(controller.image_option(session, 'ctx'), [])


class PlanLengthFactTests(unittest.TestCase):
    """R2: bands are generated from step facts; remaining paths share the ceiling."""

    BASE = {'attempt_id': 'a', 'observation_id': 'o', 'goal': '核对当前页面',
            'checks': [], 'finish_when': {'kind': 'visible_text', 'text': '终点'},
            'replan_when': '缺证'}

    @staticmethod
    def _plan(n, band):
        from webcollect.banded_plan import STEP
        steps = [{'action': 'scroll', 'direction': 'down', 'purpose': f'第{i+1}步',
                  'expected': {'kind': 'scroll_changed', 'text': '滚动后位置改变'}} for i in range(n)]
        return {**PlanLengthFactTests.BASE, 'band': band, 'steps': steps}

    def test_declared_band_is_normalized_from_step_count(self):
        allowed = ('click', 'type', 'hotkey', 'scroll', 'open_url', 'back', 'select')
        for n, declared, expected in ((1, 'five', 'short'), (4, 'five', 'short'), (6, 'five', 'long'),
                                      (7, 'long', 'long'), (5, 'long', 'five')):
            plan = validate_plan(self._plan(n, declared), 'a', 'o', allowed)
            self.assertEqual(plan['band'], expected, (n, declared))
        with self.assertRaises(Exception):  # >8 steps is not a plannable trajectory.
            validate_plan(self._plan(9, 'long'), 'a', 'o', allowed)

    def test_band_for_steps_covers_save_classification_boundaries(self):
        self.assertEqual([band_for_steps(n) for n in (1, 4)], ['short', 'short'])
        self.assertEqual(band_for_steps(5), 'five')
        self.assertEqual([band_for_steps(n) for n in (6, 8)], ['long', 'long'])


class UnclassifiedPaintTests(unittest.TestCase):
    """R3: one coherent animation block no longer rejects the whole frame pair."""

    @staticmethod
    def _state(block=(0, 110, 200, 168)):
        return {'url': 'https://example.test/a', 'title': 'A', 'document_identity': {'nonce': 1},
                'scroll': [0, 0], 'screen_resolution': [300, 200], 'device_pixel_ratio': 1, 'values': [],
                'capture_readiness': {'schema_version': 'webcollect-capture-readiness-1',
                                      'document_ready': 'complete', 'fonts_ready': True, 'images_ready': True},
                'elements': [
                    {'element_id': 'main', 'native_role': 'main', 'text': '', 'bbox': [0, 0, 300, 200], 'visible': True},
                    {'element_id': 'text', 'parent_id': 'main', 'native_role': 'p', 'text': '正文内容',
                     'bbox': [0, 0, 200, 40], 'visible': True},
                    {'element_id': 'go', 'parent_id': 'main', 'native_role': 'button', 'text': '查询',
                     'bbox': [0, 170, 60, 195], 'visible': True, 'clickable': True}],
                'visible_text': '正文内容\n查询',
                'capture_controls': [], 'geometry_witnesses': [], 'capture_images': [],
                'text_blocks': [], 'paint_borders': [], 'capture_media': [],
                'dynamic_region_contract': {'schema_version': dynamic_regions.VERSION, 'regions': [],
                                            'visible_text_outside': '正文内容\n查询', 'ancestor_text_outside': {}}}

    @staticmethod
    def _pngs(block=(0, 110, 200, 168), color='blue'):
        base = lambda: _png((300, 200), lambda d: d.rectangle((0, 0, 199, 39), fill='black'))
        changed = lambda: _png((300, 200), lambda d: (d.rectangle((0, 0, 199, 39), fill='black'),
                                                     d.rectangle(block, fill=color)))
        return base(), changed()

    def test_coherent_block_without_elements_is_tolerated(self):
        before, after = self._state(), self._state()
        png_before, png_after = self._pngs()
        proof = stability_pair(before, after, png_before, png_after)
        self.assertTrue(proof['accepted'], proof.get('scope_error'))
        self.assertIn('unclassified_dynamic_paint', proof)
        self.assertGreaterEqual(proof['unclassified_dynamic_paint']['changed_pixels'], 4096)

    def test_block_overlapping_text_or_control_still_rejects(self):
        before, after = self._state(), self._state()
        png_before, png_after = self._pngs(block=(0, 0, 150, 40))
        self.assertFalse(stability_pair(before, after, png_before, png_after)['accepted'])

    def test_tiny_noise_and_oversized_change_stay_rejected(self):
        before, after = self._state(), self._state()
        png_before, png_after = self._pngs(block=(5, 5, 10, 10))
        self.assertFalse(stability_pair(before, after, png_before, png_after)['accepted'])
        before, after = self._state(), self._state()
        png_before, png_after = self._pngs(block=(0, 0, 299, 199))
        self.assertFalse(stability_pair(before, after, png_before, png_after)['accepted'])

    def test_legacy_v1_replay_keeps_original_verdict_and_schema(self):
        before, after = self._state(), self._state()
        png_before, png_after = self._pngs()
        legacy = stability_pair(before, after, png_before, png_after,
                                rule_version=dynamic_regions.STABILITY_V1)
        self.assertEqual(legacy['schema_version'], dynamic_regions.STABILITY_V1)
        self.assertNotIn('unclassified_dynamic_paint', legacy)
        self.assertFalse(legacy['accepted'])


class RecheckHandlingTests(unittest.TestCase):
    """R4: claim-race culling guard and navigation failure classification."""

    SCHEMA = '''
    CREATE TABLE data_candidates(candidate_id TEXT PRIMARY KEY, application_id TEXT, dedup_key TEXT,
      version INTEGER, body TEXT, created REAL, state TEXT);
    CREATE TABLE candidate_claims(claim_id TEXT PRIMARY KEY, candidate_id TEXT, version INTEGER, snapshot TEXT,
      worker_id TEXT, request_id TEXT, token TEXT, expires REAL, state TEXT, stage TEXT, binding TEXT,
      reason TEXT, created REAL, updated REAL, sources TEXT);
    CREATE TABLE candidate_events(id INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL, claim_id TEXT,
      kind TEXT NOT NULL, record TEXT NOT NULL, created REAL);
    '''

    def setUp(self):
        from site_planner import inventory_recheck
        self.recheck = inventory_recheck
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'pool.sqlite3'
        con = sqlite3.connect(self.path)
        con.executescript(self.SCHEMA)
        con.execute("INSERT INTO data_candidates VALUES('c1','app','k',1,?,?,'pending')",
                    (json.dumps({'entry_url': 'https://a.example/x'}), time.time()))
        con.commit(); con.close()

    def test_cull_rechecks_pending_and_claim_free_in_transaction(self):
        con = sqlite3.connect(self.path)
        con.execute("INSERT INTO candidate_claims VALUES('cl','c1',1,'{}','w','r','t',0,'consuming','claimed',NULL,NULL,0,0,NULL)")
        con.commit()
        # A claim that raced in after selection keeps the candidate untouched.
        self.assertFalse(self.recheck._cull(con, 'c1', 'dead_hard', {'http_status': 404}))
        self.assertEqual(dict(con.execute('SELECT candidate_id, state FROM data_candidates'))['c1'], 'pending')
        con.execute("DELETE FROM candidate_claims")
        con.execute("UPDATE data_candidates SET state='failed' WHERE candidate_id='c1'")
        con.commit()
        # A non-pending candidate is never re-culled.
        self.assertFalse(self.recheck._cull(con, 'c1', 'dead_hard', {'http_status': 404}))
        con.execute("UPDATE data_candidates SET state='pending' WHERE candidate_id='c1'")
        con.commit()
        self.assertTrue(self.recheck._cull(con, 'c1', 'dead_hard', {'http_status': 404}))
        states = dict(con.execute('SELECT candidate_id, state FROM data_candidates'))
        con.close()
        self.assertEqual(states, {'c1': 'failed'})

    def test_navigation_failure_classes(self):
        from playwright.async_api import Error as PlaywrightError
        verdict, _ = self.recheck._classify_navigation_failure(
            PlaywrightError('Page.goto: net::ERR_BLOCKED_BY_CLIENT at http://x/'))
        self.assertEqual(verdict, 'strike')
        verdict, _ = self.recheck._classify_navigation_failure(
            PlaywrightError('Page.goto: net::ERR_NAME_NOT_RESOLVED at http://x/'))
        self.assertEqual(verdict, 'dead_hard')
        verdict, _ = self.recheck._classify_navigation_failure(asyncio.TimeoutError())
        self.assertEqual(verdict, 'strike')

    def test_smoke_observe_failure_and_entry_403_culling_split(self):
        con = sqlite3.connect(self.path)
        con.execute("INSERT INTO data_candidates VALUES('c2','app','k2',1,?,?,'pending')",
                    (json.dumps({'entry_url': 'https://b.example/y'}), time.time()))
        con.execute("INSERT INTO data_candidates VALUES('c3','app','k3',1,?,?,'pending')",
                    (json.dumps({'entry_url': 'https://c.example/z'}), time.time()))
        con.commit(); con.close()
        smoke = {'https://a.example/x': ('browser_observe_failed', 'SnapshotFault: UNSUPPORTED_GEOMETRY', None),
                 'https://b.example/y': ('entry_403', None, 403),
                 'https://c.example/z': ('browser_empty', None, None)}
        with mock.patch.object(self.recheck, '_get_check', side_effect=lambda url, t: ('ok', 200, None)), \
             mock.patch.object(self.recheck, '_smoke', new=mock.AsyncMock(return_value=smoke)):
            self.recheck.run(self.path, limit=10, stale_hours=0, timeout=5, host_interval=0,
                             dry_run=False, smoke=3, audit=0, report_dir=None)
        con = sqlite3.connect(self.path)
        states = dict(con.execute('SELECT candidate_id, state FROM data_candidates'))
        verdicts = dict(con.execute('SELECT candidate_id, verdict FROM inventory_rechecks'))
        con.close()
        self.assertEqual(states, {'c1': 'pending', 'c2': 'failed', 'c3': 'pending'})
        self.assertEqual(verdicts['c1'], 'browser_observe_failed')
        self.assertEqual(verdicts['c2'], 'entry_403')


class EightSlotEntryTests(unittest.TestCase):
    """R5/R6: frozen roster, single-shot workers, shared ceiling, attribution."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        from site_planner.site_pool import SitePool
        from site_planner.candidate_pool import CandidatePool, VERSION2
        SitePool(self.root / 'pool.db', initialize=True)
        self.pool = CandidatePool(self.root / 'pool.db', install=True)
        self.VERSION2 = VERSION2
        self.cids = []
        for index in range(8):
            candidate = {'schema_version': VERSION2, 'candidate_kind': 'target',
                         'entry_url': f'https://site{index}.example/page',
                         'requested_goal': {'kind': 'read', 'entity': f'site{index}', 'parameters': {}}}
            proof = self.root / f'source{index}.json'
            proof.write_text(json.dumps({'CONTROLLED': 'offline draft source'}))
            from site_planner.discovery_tools import reference
            self.cids.append(self.pool.put(candidate, {'origin': 'codex_session', 'run_id': 'offline',
                                                       'references': [reference(proof)]}))
        self.draft = self.root / 'draft.json'
        self.draft.write_text(json.dumps({
            'schema_version': 'webcollect-consumer-ab-draft-1',
            'candidates': [{'candidate_id': cid, 'note': 'slot'} for cid in self.cids]}, ensure_ascii=False))
        self.output = self.root / 'collections' / 'consumer-effort-ab-offline'

    def test_prepare_freezes_eight_slots_with_group_profiles(self):
        slots, roster = consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output, seed=7)
        self.assertEqual(len(slots), 8)
        self.assertEqual({s['group'] for s in slots}, {'A', 'B'})
        self.assertEqual([s['effort_profile'] for s in slots if s['group'] == 'A'],
                         [consumer_ab.GROUP_PROFILES['A']] * 4)
        self.assertEqual([s['effort_profile'] for s in slots if s['group'] == 'B'],
                         [consumer_ab.GROUP_PROFILES['B']] * 4)
        self.assertEqual(len({s['candidate']['candidate_id'] for s in slots}), 8)
        consumer_ab._save(self.output / 'roster.json', roster)
        duplicate = self.root / 'draft2.json'
        duplicate.write_text(json.dumps({
            'schema_version': 'webcollect-consumer-ab-draft-1',
            'candidates': [{'candidate_id': cid} for cid in self.cids[:2] + self.cids[:2]]}, ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, 'distinct'):
            consumer_ab.prepare(self.root / 'pool.db', duplicate, self.output)

    def test_worker_slot_state_is_single_shot(self):
        _, roster = consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output, seed=7)
        slot = roster['slots'][0]
        state_path = consumer_ab._slot_state_path(roster['output_dir'], slot['slot'])
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({'schema_version': consumer_ab.SLOT_STATE_SCHEMA,
                                          'slot': slot['slot'], 'dispatched': False}))
        result = consumer_ab.worker(roster, slot['slot'], config=str(CONFIG),
                                    ledger_path=str(self.root / 'jobs.sqlite3'),
                                    registry=str(self.root / 'registry.db'),
                                    policy_path=str(self.root / 'policy.json'),
                                    history_set=str(self.root / 'chain.json'))
        self.assertFalse(result['dispatched'])
        self.assertEqual(result['state'], 'already_processed')

    def test_report_attributes_requests_by_claim_attempt(self):
        _, roster = consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output, seed=7)
        consumer_ab._save(self.output / 'roster.json', roster)
        slot = roster['slots'][0]
        claim = self.pool.claim_next(slot['worker_id'], slot['request_prefix'],
                                     candidate_id=slot['candidate']['candidate_id'],
                                     protocols=(self.VERSION2,))
        self.assertIn(claim.get('state'), ('consuming', None), claim)
        # Bind a formal attempt exactly as the consumer would, then place two
        # ledger requests under that attempt id.
        self.pool.stage(claim, 'execution', {'attempt_id': 'attempt-ab-1'})
        cfg = json.loads(CONFIG.read_text())
        from webcollect.batch_core import BatchLedger
        ledger = BatchLedger(self.root / 'jobs.sqlite3', cfg, initialize=True)
        jid = ledger.enqueue('react-native-decision', {'claim_id': claim['claim_id']})
        job = ledger.claim('react-native-decision', job_id=jid)
        ledger.reserve_request(job, 'webcollect-banded-conditional-plan-10:native-tool-1:hash', 0,
                               request_json={'dispatch_attempt_id': 'attempt-ab-1',
                                             'reasoning_effort': 'high', 'http_dispatch': True})
        state = {'schema_version': consumer_ab.SLOT_STATE_SCHEMA, 'slot': slot['slot'],
                 'group': slot['group'], 'candidate_id': slot['candidate']['candidate_id'],
                 'claim_id': claim['claim_id'], 'phase': 'consumed',
                 'outcome': {'state': 'reconcile'}, 'dispatched': True}
        consumer_ab._save(consumer_ab._slot_state_path(roster['output_dir'], slot['slot']), state)
        summary = consumer_ab.report(roster, self.root / 'jobs.sqlite3', self.output)
        entry = next(s for s in summary['slots'] if s['slot'] == slot['slot'])
        self.assertEqual(entry.get('request_count'), 1)
        self.assertEqual(entry['requests'][0]['effort'], 'high')
        others = [s for s in summary['slots'] if s['slot'] != slot['slot']]
        self.assertTrue(all(s.get('request_count', 0) == 0 for s in others))

    def test_shared_ledger_holds_eight_top_level_jobs_and_children_reuse_slots(self):
        from webcollect.batch_core import BatchLedger, BudgetStop
        cfg = json.loads(CONFIG.read_text())
        cfg['budget']['max_concurrent_jobs'] = 8
        ledger = BatchLedger(self.root / 'shared.sqlite3', cfg, initialize=True)
        parents = [ledger.enqueue('collection', {'slot': 'concurrency-fixture', 'index': index})
                   for index in range(9)]
        jobs = [ledger.claim('collection', job_id=jid) for jid in parents[:8]]
        self.assertTrue(all(jobs))
        with self.assertRaises(BudgetStop):
            ledger.claim('collection', job_id=parents[8])
        # A model sub-job rides its parent's slot even at the ceiling.
        jid = ledger.enqueue('react-native-decision', {'parent_job_id': jobs[0]['id']})
        child = ledger.claim('react-native-decision', job_id=jid, parent_job=jobs[0])
        self.assertTrue(child)
        ledger.finish(child)
        ledger.finish(jobs[0])
        self.assertTrue(ledger.claim('collection', job_id=parents[8]))

    def test_adjust_concurrency_is_audited_without_changing_frozen_config(self):
        from webcollect.batch_core import BatchLedger
        cfg = json.loads(CONFIG.read_text())
        cfg['budget']['max_concurrent_jobs'] = 4
        cfg_path = self.root / 'consumer-config.json'
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, sort_keys=True))
        ledger_path = self.root / 'jobs.sqlite3'
        running = BatchLedger(ledger_path, cfg, initialize=True)
        original_bytes = cfg_path.read_bytes()
        result = consumer_ab.adjust_concurrency(ledger_path, cfg_path, target=8,
                                                authorization='consumer-ab-repair-20261106 phase-2 bounded experiment')
        self.assertTrue(result['changed'])
        reopened = BatchLedger(ledger_path, cfg)
        with reopened.connect() as con:
            events = con.execute("SELECT detail FROM batch_events WHERE event='consumer_concurrency'").fetchall()
            self.assertEqual(json.loads(con.execute('SELECT config FROM batch_meta').fetchone()[0]), cfg)
        self.assertEqual(len(events), 1)
        self.assertEqual(json.loads(events[0][0])['before']['max_concurrent_jobs'], 4)
        self.assertEqual(json.loads(events[0][0])['after']['max_concurrent_jobs'], 8)
        self.assertEqual(running.max_concurrent_jobs, 8)
        self.assertEqual(reopened.max_concurrent_jobs, 8)
        self.assertEqual(cfg_path.read_bytes(), original_bytes)


class TargetedLaunchTests(unittest.TestCase):
    """Phase-2 readiness: real subprocess argv, single-shot workers on a temp
    shared pool, both failure shapes and one mocked success, then aggregation.

    No browser, no model, no production store: consume either fails at its own
    startup scope check (deterministic, before any external IO) or is patched
    to a saved result for the success close-out.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        from site_planner.site_pool import SitePool
        from site_planner.candidate_pool import CandidatePool, VERSION2
        from site_planner.discovery_tools import reference
        SitePool(self.root / 'pool.db', initialize=True)
        self.pool = CandidatePool(self.root / 'pool.db', install=True)
        self.cids = []
        for index in range(8):
            proof = self.root / f'src{index}.json'
            proof.write_text(json.dumps({'CONTROLLED': 'targeted launch'}))
            candidate = {'schema_version': VERSION2, 'candidate_kind': 'entry',
                         'entry_url': f'https://targeted{index}.example/page',
                         'requested_goal': None}
            self.cids.append(self.pool.put(candidate, {'origin': 'codex_session', 'run_id': 'offline',
                                                       'references': [reference(proof)]}))
        self.draft = self.root / 'draft.json'
        self.draft.write_text(json.dumps({
            'schema_version': 'webcollect-consumer-ab-draft-1',
            'candidates': [{'candidate_id': cid, 'capability_class': '多页导航阅读'}
                           for cid in self.cids]}, ensure_ascii=False))
        self.output = self.root / 'collections' / 'targeted-ab'
        cfg = json.loads(CONFIG.read_text())
        cfg['budget']['max_concurrent_jobs'] = 8
        self.cfg_path = self.root / 'worker-config.json'
        self.cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, sort_keys=True))
        self.ledger_path = self.root / 'jobs.db'
        from webcollect.batch_core import BatchLedger
        BatchLedger(self.ledger_path, cfg, initialize=True)
        _, roster = consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output, seed=11)
        self.roster_path = consumer_ab._save(self.output / 'roster.json', roster)
        self.roster = roster

    def _missing_binding_paths(self):
        return {'config': str(self.cfg_path), 'ledger_path': str(self.ledger_path),
                'registry': str(self.root / 'missing-registry.db'),
                'policy_path': str(self.root / 'missing-policy.json'),
                'history_set': str(self.root / 'missing-chain.json')}

    def test_real_subprocess_argv_single_shot_and_failure_closeouts(self):
        # One candidate is claimed by an outside worker first: that slot must
        # close as unclaimable without any replacement dispatch.
        raced = self.roster['slots'][3]
        self.pool.claim_next('outside-worker', 'outside/r01',
                             candidate_id=raced['candidate']['candidate_id'],
                             protocols=('webcollect-data-candidate-2',))
        launch_result = consumer_ab.launch(self.roster, experiment_dir=self.output,
                                           python=sys.executable, **self._missing_binding_paths())
        self.assertEqual(sorted(launch_result['launched']), sorted(s['slot'] for s in self.roster['slots']))
        for name, log in launch_result['logs'].items():
            self.assertEqual(log['returncode'], 0, (name, log['output']))
            self.assertNotIn('error: the following arguments are required', log['output'])
        raced_state = consumer_ab._existing_state(self.output, raced['slot'])
        self.assertFalse(raced_state['dispatched'])
        self.assertIn(raced_state['outcome']['state'], ('ALREADY_CLAIMED', 'EMPTY'))
        # Every other slot performed exactly one session attempt that failed
        # inside consume's own startup scope, before browser or model IO.
        for slot in self.roster['slots']:
            if slot['slot'] == raced['slot']:
                continue
            state = consumer_ab._existing_state(self.output, slot['slot'])
            self.assertTrue(state['dispatched'], slot['slot'])
            self.assertEqual(state['outcome']['state'], 'failed')
            self.assertEqual(state['outcome']['error_type'], 'ValueError')
            claim = self.pool.get_claim(state['claim_id'])
            self.assertEqual(claim['state'], 'failed', slot['slot'])
        # Rerunning the launch is read-only: state files refuse a second dispatch.
        rerun = consumer_ab.worker(self.roster, raced['slot'],
                                   config=self.cfg_path, ledger_path=self.ledger_path,
                                   registry='unused', policy_path='unused', history_set='unused')
        self.assertFalse(rerun['dispatched'])

    def test_success_closeout_and_report_counts_only_dispatched_requests(self):
        from webcollect.batch_core import BatchLedger
        slot = self.roster['slots'][0]
        claim = self.pool.claim_next(slot['worker_id'], slot['request_prefix'],
                                     candidate_id=slot['candidate']['candidate_id'],
                                     protocols=('webcollect-data-candidate-2',))
        self.pool.stage(claim, 'execution', {'attempt_id': 'attempt-targeted-1'})
        ledger = BatchLedger(self.ledger_path, json.loads(self.cfg_path.read_text()))
        jid = ledger.enqueue('react-native-decision', {'claim_id': claim['claim_id']})
        job = ledger.claim('react-native-decision', job_id=jid)
        reserved = ledger.reserve_request(job, 'targeted:reserved:no-dispatch', 0,
                                          request_json={'dispatch_attempt_id': 'attempt-targeted-1',
                                                        'reasoning_effort': 'high', 'http_dispatch': False})
        self.assertEqual(reserved['state'], 'new')
        jid2 = ledger.enqueue('react-native-decision', {'claim_id': claim['claim_id'], 'second': True})
        job2 = ledger.claim('react-native-decision', job_id=jid2)
        ledger.reserve_request(job2, 'targeted:dispatched', 0,
                               request_json={'dispatch_attempt_id': 'attempt-targeted-1',
                                             'reasoning_effort': 'high', 'http_dispatch': True})
        saved = {'state': 'succeeded', 'saved': True, 'result': {'result': {'sample_id': 'S1'}}}

        def consume_result(pool_, claim_, ledger_, **kwargs):
            assert claim_['claim_id'] == claim['claim_id']
            return deepcopy(saved)
        import asyncio as _asyncio
        async def consume(pool_, claim_, ledger_, **kwargs):
            return consume_result(pool_, claim_, ledger_, **kwargs)
        with patch('webcollect.candidate_consumer.consume', new=consume):
            outcome = consumer_ab.worker(self.roster, slot['slot'], config=str(self.cfg_path),
                                         ledger_path=str(self.ledger_path), registry='unused',
                                         policy_path='unused', history_set='unused')
        self.assertTrue(outcome['saved'])
        summary = consumer_ab.report(self.roster, self.ledger_path, self.output)
        entry = next(s for s in summary['slots'] if s['slot'] == slot['slot'])
        self.assertEqual(entry['request_count'], 1)          # dispatched only
        self.assertEqual(len(entry['reserved_not_dispatched']), 1)
        self.assertEqual(entry['request_states'], {'reserved': 1})
        group = summary['groups'][slot['group']]
        self.assertEqual(group['saved'], 1)
        self.assertEqual(group['requests'], 1)


class OutboundEffortTests(unittest.TestCase):
    """R6: the frozen A/B profile is what actually leaves the host."""

    def test_profiles_map_to_first_and_branch_efforts(self):
        from webcollect.react_session import build_url_task, validate_effort_profile
        for group, profile in consumer_ab.GROUP_PROFILES.items():
            frozen = validate_effort_profile(profile)
            task = build_url_task(url='https://example.org/x', task_version='ab',
                                  plan_protocol=VERSION, effort_profile=frozen)
            self.assertEqual(task['fragment']['reasoning_effort_profile'], frozen)


class SlotObjectiveTests(unittest.TestCase):
    """Per-slot frozen session objectives: validated at prepare, honored at launch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        from site_planner.site_pool import SitePool
        from site_planner.candidate_pool import CandidatePool, VERSION2
        from site_planner.discovery_tools import reference
        SitePool(self.root / 'pool.db', initialize=True)
        self.pool = CandidatePool(self.root / 'pool.db', install=True)
        self.VERSION2 = VERSION2
        self.cids = []
        for index in range(8):
            proof = self.root / f'src{index}.json'
            proof.write_text(json.dumps({'CONTROLLED': 'slot objective'}))
            candidate = {'schema_version': VERSION2, 'candidate_kind': 'entry',
                         'entry_url': f'https://objective{index}.example/page',
                         'requested_goal': None}
            self.cids.append(self.pool.put(candidate, {'origin': 'codex_session', 'run_id': 'offline',
                                                       'references': [reference(proof)]}))
        self.draft = self.root / 'draft.json'
        self.draft.write_text(json.dumps({
            'schema_version': 'webcollect-consumer-ab-draft-1',
            'candidates': [{'candidate_id': cid} for cid in self.cids]}, ensure_ascii=False))
        self.output = self.root / 'collections' / 'objective-ab'

    def _write_objectives(self, slots, *, corrupt=None):
        directory = self.root / 'objectives'
        directory.mkdir(parents=True, exist_ok=True)
        rows = {row['candidate_id']: row for row in self.pool.rows(protocols=(self.VERSION2,))}
        for slot in slots:
            row = rows[slot['candidate']['candidate_id']]
            body = row['candidate']
            objective = {'schema_version': 'webcollect-session-objective-1',
                         'candidate_id': row['candidate_id'], 'version': row['version'],
                         'entry_url': body['entry_url'], 'requested_goal': body.get('requested_goal'),
                         'authorization': 'offline fixture authorization',
                         'objective': {'description': f'在 {body["entry_url"]} 站内检索并阅读相关内容',
                                       'minimum_effective_steps': 5, 'preferred_band': 'five'}}
            if corrupt == slot['slot']:
                objective['candidate_id'] = 'candidate-other'
            target = directory / f'{slot["slot"]}.objective.json'
            target.write_text(json.dumps(objective, ensure_ascii=False))
            (directory / f'{slot["slot"]}.json').write_text(json.dumps(
                {'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))
        return directory

    def test_prepare_freezes_validated_objective_per_slot(self):
        slots, _ = consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output, seed=3)
        directory = self._write_objectives(slots)
        frozen_slots, roster = consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output,
                                                   seed=3, objectives_dir=directory)
        self.assertEqual([s['slot'] for s in frozen_slots], [s['slot'] for s in slots])
        for slot in roster['slots']:
            binding = slot['session_objective']
            self.assertEqual(binding['reference_file'], str(directory / f"{slot['slot']}.json"))
            self.assertEqual(binding['summary']['preferred_band'], 'five')
            self.assertEqual(binding['objective']['sha256'],
                             hashlib.sha256(Path(directory / f"{slot['slot']}.objective.json").read_bytes()).hexdigest())
        # Identity mismatch against the pool row is rejected before any freeze.
        bad = self._write_objectives(slots, corrupt=roster['slots'][0]['slot'])
        with self.assertRaisesRegex(ValueError, 'differs from original candidate identity'):
            consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output, seed=3, objectives_dir=bad)

    def test_launch_passes_each_slot_its_own_objective_file(self):
        slots, _ = consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output, seed=3)
        directory = self._write_objectives(slots)
        _, roster = consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output,
                                        seed=3, objectives_dir=directory)
        argv_by_slot = {}
        class FakeProcess:
            returncode = 0
            def communicate(self):
                return ('offline', None)
        def fake_popen(command, **_):
            argv_by_slot[command[command.index('--slot') + 1]] = command
            return FakeProcess()
        with patch.object(consumer_ab.subprocess, 'Popen', side_effect=fake_popen):
            consumer_ab.launch(roster, config='cfg', ledger_path='led', registry='reg',
                               policy_path='pol', history_set='chain',
                               python='python', experiment_dir=self.output)
        self.assertEqual(sorted(argv_by_slot), sorted(s['slot'] for s in roster['slots']))
        for slot in roster['slots']:
            argv = argv_by_slot[slot['slot']]
            self.assertIn(str(directory / f"{slot['slot']}.json"), argv, slot['slot'])
        # One shared file must not leak into a slot that froze its own binding.
        self.assertNotIn('shared.json', ' '.join(argv_by_slot[roster['slots'][0]['slot']]))

    def test_worker_cli_reconciliation_refuses_conflicting_objective(self):
        slots, _ = consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output, seed=3)
        directory = self._write_objectives(slots)
        _, roster = consumer_ab.prepare(self.root / 'pool.db', self.draft, self.output,
                                        seed=3, objectives_dir=directory)
        slot = roster['slots'][0]
        frozen = consumer_ab._slot_objective(roster, slot['slot'], None)
        self.assertEqual(frozen, slot['session_objective']['objective'])
        self.assertEqual(consumer_ab._slot_objective(roster, slot['slot'], str(directory / f"{slot['slot']}.json")),
                         frozen)
        other = roster['slots'][1]
        with self.assertRaisesRegex(ValueError, 'roster-frozen'):
            consumer_ab._slot_objective(roster, slot['slot'], str(directory / f"{other['slot']}.json"))


if __name__ == '__main__':
    unittest.main()
