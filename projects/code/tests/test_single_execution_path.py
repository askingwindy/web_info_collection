"""Single collection protocol with temporary ledgers and mocked browser IO only.

No browser process, model gateway, HTTP request, or historical package is used.
The real collect_one/runtime write their raw evidence and committed receipts.
"""
import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image
from webcollect import collect, task_generation
from webcollect.batch_core import BatchLedger, file_sha, load_json, save_json
from webcollect.browser import fingerprint
from webcollect.collect_runtime import collect_m4, runtime_scope, verify_committed_samples
from webcollect.current_chain import initialize_chain, read_chain_history
from webcollect.evidence import audit_capture
from webcollect.planning import object_sha256, publish_plan
from webcollect.preflight import _files, digest, object_digest, schedule_plan
from webcollect.production_identity import VERSION as IDENTITY_VERSION
from webcollect.runtime import RuntimeStore
from webcollect.site_failure_stop import SiteFailureStore, SiteStopped
import m4_runtime_fixtures as fixtures
from test_s0_task_generation import capability, catalog, config


class HistoryDeferralTests(unittest.TestCase):
    def test_empty_current_population_requires_no_semantic_admission(self):
        task = {'site_uri': 'https://example.org/unknown'}
        self.assertIsNone(task_generation.customer_history_decision(task, []))

    def test_nonempty_unknown_business_is_an_explicit_post_collection_qc_check(self):
        task = {'site_uri': 'https://new.example/unknown'}
        history = [{'sample_id': 'CONTROLLED-current', 'origin': 'https://example.org',
                    'strategy_id': None, 'semantic_signature': None}]
        result = task_generation.customer_history_decision(task, history)
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['history_sample_ids'], ['CONTROLLED-current'])

    def test_same_strategy_alone_requires_actual_difference_review(self):
        task = {'site_uri': 'https://example.org/', 'deterministic_strategy': {'id': 'controlled'}}
        old = {'sample_id': 'CONTROLLED-current', 'origin': 'https://elsewhere.example',
               'strategy_id': 'controlled', 'semantic_signature': task_generation.semantic_signature(task)}
        self.assertEqual(task_generation.customer_history_decision(task, [old])['status'], 'REVIEW_REQUIRED')

    def test_generation_retains_uncertain_task_without_admission_or_rehearsal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = capability(root / 'cap')
            source = catalog(root / 'catalog.json', [record])
            ledger = BatchLedger(root / 'operations.sqlite3', config(), initialize=True)
            decision = {'status': 'REVIEW_REQUIRED', 'reason': 'Controlled unresolved comparison',
                        'history_sample_ids': ['CONTROLLED-current']}
            with patch.object(task_generation, 'read_customer_history', return_value=([], {'controlled': True})), \
                 patch.object(task_generation, 'customer_history_decision', return_value=decision), \
                 patch('webcollect.model_gateway.ModelGateway', side_effect=AssertionError('No model')), \
                 patch('webcollect.task_admission.attach', side_effect=AssertionError('No admission')), \
                 patch('webcollect.browser_planner.observe_task', side_effect=AssertionError('No rehearsal')):
                result = task_generation.generate(ledger, source, root / 'tasks', history_set=root / 'unused.json')
            self.assertEqual(result['generated_tasks'], 1)
            self.assertEqual(result['pending'], [])
            plan = load_json(result['plan_file'])
            check = plan['generation']['post_collection_quality_reviews'][0]
            self.assertEqual(check['status'], 'REVIEW_REQUIRED')
            self.assertEqual(check['task_sha256'], object_sha256(plan['tasks'][0]))
            self.assertEqual(ledger.summary()['model_requests'], 0)


class SingleCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.chain_manifest = self.root / 'chain.json'
        self.registry = self.root / 'results' / 'registry.sqlite3'
        self.scope = initialize_chain(self.chain_manifest, self.registry, chain_id='CONTROLLED-single',
                                      current_result_roots=[self.root / 'results'])
        self.actions = []
        self.page = MagicMock(url='https://example.org/')
        self.page.goto = AsyncMock()
        self.page.evaluate = AsyncMock(return_value=1)
        self.page.wait_for_timeout = AsyncMock()
        self.page.close = AsyncMock()
        self.context = MagicMock(pages=[self.page])
        self.context.new_page = AsyncMock(return_value=self.page)
        self.context.close = AsyncMock()
        browser = MagicMock(version='CONTROLLED-mock-no-browser-process')
        browser.new_context = AsyncMock(return_value=self.context)
        browser.close = AsyncMock()
        playwright = MagicMock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=playwright)
        manager.__aexit__ = AsyncMock(return_value=False)
        from webcollect.metadata import export_metadata
        self.real_metadata = export_metadata
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target, value in [
            ('playwright.async_api.async_playwright', MagicMock(return_value=manager)),
            ('webcollect.collect_runtime.contract_identity', MagicMock(return_value={'controlled_contract': True})),
            ('webcollect.collect_runtime.validate_sample', MagicMock(return_value={'structural_pass': True})),
            ('webcollect.metadata.export_metadata', MagicMock(side_effect=self.metadata)),
            ('webcollect.model_gateway.ModelGateway', MagicMock(side_effect=AssertionError('No model calls'))),
            ('webcollect.browser_planner.observe_task', AsyncMock(side_effect=AssertionError('No rehearsal'))),
            ('webcollect.task_generation.verify_task_admissions', MagicMock(side_effect=AssertionError('No admission'))),
            ('webcollect.task_admission.verify_collection_entry', MagicMock(side_effect=AssertionError('No admission'))),
            ('webcollect.observed_workflow.verify_entry', MagicMock(side_effect=AssertionError('No admission'))),
            ('webcollect.collect.capture', AsyncMock(side_effect=self.capture)),
            ('webcollect.collect.observe', AsyncMock(side_effect=lambda *a, **kw: self.state())),
            ('webcollect.collect.verify_execution_state', AsyncMock(side_effect=lambda page, state, *a, **kw:
                {'matched': True, 'state_fingerprint': fingerprint(state)})),
            ('webcollect.collect.execute', AsyncMock(side_effect=self.execute_action)),
            ('webcollect.collect.assess_content', AsyncMock(return_value={'page_url': self.page.url,
                'decision': {'action': 'ready', 'reason': 'CONTROLLED clear page'}})),
            ('webcollect.collect.describe_change', MagicMock(return_value='合成页面显示下一段必要内容。')),
        ]:
            self.stack.enter_context(patch(target, value))

    def metadata(self, batch, path):
        manifest = load_json(Path(batch) / 'manifest.json')
        sites = {row['sample_id']: row['site_id'] for row in manifest['attempts']}
        Path(path).write_text('sample_id,site_id\n' + ''.join(
            sid + ',' + sites[sid] + '\n' for sid in manifest['samples']))

    def state(self):
        count = len(self.actions)
        return {'url': self.page.url, 'title': '离线受控阅读页面', 'screen_resolution': [1280, 720],
            'device_pixel_ratio': 1, 'scroll': [0, count * 100], 'values': [], 'target': None,
            'elements': [{'element_id': 'heading', 'parent_id': 'root', 'element_type': 'text',
                'native_role': 'h1', 'text': '离线受控阅读页面', 'bbox': [10, 10, 250, 40],
                'visible': True, 'enabled': True, 'clickable': False, 'inputable': False,
                'scrollable': False, 'state': 'default'}],
            'visible_text': '全部内容均为临时合成离线夹具，每次必要滚动显示下一段正文。' +
                ('受控完成事实' if count == 5 else '还有后续必要内容'),
            'text_blocks': [], 'embedded_frames': []}

    async def capture(self, page, selector=None, index=0, assertions=None, **kwargs):
        started = time.time_ns()
        state = self.state()
        if assertions:
            state['assertion_targets'] = [None for _ in assertions]
        output = BytesIO()
        Image.new('RGB', (1280, 720), (len(self.actions) * 30, 40, 60)).save(output, 'PNG')
        png = output.getvalue()
        return {'state': state, 'png': png, 'capture': {
            'snapshot_source': 'browser_dom', 'coordinate_space': 'screenshot_css_pixels',
            'observer_sha256': hashlib.sha256(collect.SNAPSHOT_JS.encode()).hexdigest(),
            'screenshot_sha256': hashlib.sha256(png).hexdigest(),
            'attempts': [{'started_ns': started, 'ended_ns': time.time_ns(), 'dom_stable': True,
                'before_fingerprint': fingerprint(state), 'after_fingerprint': fingerprint(state)}]}}

    async def execute_action(self, page, action, arguments, execution=None):
        if action != 'complete':
            self.actions.append(action)

    def prepared(self, identity=False):
        with patch('m4_runtime_fixtures.NOW', time.time()):
            plan, _ = fixtures.make_plan(self.root / 'planning')
        task = plan['tasks'][0]
        task['initial_settle_ms'] = 0
        if identity:
            anchor = self.root / 'original-page-anchor'
            anchor.mkdir()
            original = self.state()
            image = anchor / 'page.png'; Image.new('RGB', (1280, 720), 'white').save(image)
            state = anchor / 'state.json'; save_json(state, original)
            capture = anchor / 'capture.json'
            save_json(capture, {'screenshot_sha256': file_sha(image),
                'observer_sha256': hashlib.sha256(collect.SNAPSHOT_JS.encode()).hexdigest(),
                'snapshot_source': 'browser_dom', 'coordinate_space': 'screenshot_css_pixels',
                'attempts': [{'dom_stable': True, 'before_fingerprint': fingerprint(original),
                              'after_fingerprint': fingerprint(original)}]})
            ref = lambda path: {'path': str(path), 'sha256': file_sha(path)}
            task['pilot_identity'] = {'version': IDENTITY_VERSION,
                'application': {'canonical_uri': 'https://example.org/', 'name': task['app_name'],
                                'evidence': [ref(state)]},
                'task_page': {'canonical_uri': 'https://example.org/', 'aliases': ['https://example.org/'],
                    'kind': 'content', 'description': '合成离线阅读页面',
                    'anchor': {'image': ref(image), 'state': ref(state), 'capture': ref(capture)}},
                'shared_pages': []}
        plan['generation'] = {'mode': 'real', 'history_scope': self.scope,
                              'source_identity': task_generation.generation_source_identity()}
        # Rebuild only temporary preflight file bindings after adding metadata.
        folder = self.root / 'planning' / 'preflight'
        original = {k: v for k, v in plan.items() if k != 'media_preflight'}
        (folder / 'input-plan.json').write_text(json.dumps(original, ensure_ascii=False))
        report = load_json(folder / 'report.json')
        report['input_plan_sha256'] = digest(folder / 'input-plan.json')
        for row, task in zip(report['records'], original['tasks']):
            row['task_sha256'] = object_digest(task)
            (folder / row['evidence_directory'] / 'result.json').write_text(json.dumps(
                {k: v for k, v in row.items() if k != 'evidence_directory'}, ensure_ascii=False))
        report['evidence_files_sha256'] = {k: v for k, v in _files(folder).items()
            if k not in {'report.json', 'scheduled-plan.json', 'manifest.json', 'SHA256SUMS'}}
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False))
        plan = schedule_plan(original, report['records'], folder / 'report.json', digest(folder / 'report.json'), True)
        capability = {'schema_version': 'webcollect-site-capability-1', 'capability_id': 'task-cap',
            'version': '1', 'site_uri': 'https://example.org/', 'site_category': '工具',
            'observed_at': time.time() - 100, 'expires_at': time.time() + 1000, 'status': 'ready',
            'supported_actions': ['scroll'], 'task_families': ['controlled-reading'],
            'evidence': fixtures.evidence(self.root / 'capability.txt')}
        publication = publish_plan(plan, [capability])
        self.plan = plan
        self.plan_path = self.root / 'plan.json'; save_json(self.plan_path, plan)
        self.publication_path = self.root / 'publication.json'; save_json(self.publication_path, publication)
        self.policy = {'campaign_id': 'CONTROLLED-single', 'baseline_category_counts': {}}
        if identity:
            self.policy['pilot_identity_required'] = True
            stop = SiteFailureStore.initialize({'ledger': str(self.root / 'current-stop.sqlite3'),
                'campaign_id': self.policy['campaign_id'], 'formal_since': time.time() - 1})
            self.policy['site_failure_guard'] = stop.binding
        self.policy_path = self.root / 'policy.json'; save_json(self.policy_path, self.policy)
        self.output = self.root / 'results' / 'run'
        return capability

    async def collect(self, resume=False):
        return await collect_m4(self.plan_path, self.output / 'capture', self.registry,
            publication_path=self.publication_path, policy_path=None if resume else self.policy_path,
            resume=resume)

    async def assert_single_saved_run(self, identity):
        self.prepared(identity)
        first = await self.collect()
        self.assertEqual(self.actions, ['scroll'] * 5)
        self.assertEqual(first['collected'], 1, first)
        self.assertEqual(first['qualified_samples'], 0)
        capture = self.output / 'capture'
        saved_manifest = load_json(capture / 'manifest.json')
        sample_id = saved_manifest['samples'][0]
        evidence = capture / 'evidence' / sample_id
        raw = [load_json(evidence / f'step_{n:03}.json') for n in range(1, 7)]
        self.assertEqual([row['operation']['action_type'] for row in raw], ['scroll'] * 5 + ['complete'])
        self.assertTrue(audit_capture(capture, sample_id)['capture_evidence_pass'])
        self.assertEqual(load_json(evidence / 'task_contract.json')['semantic_status'], 'REVIEW_REQUIRED')
        store = RuntimeStore(self.registry, runtime_scope(capture))
        self.assertEqual(store.snapshot()['tasks'][0]['status'], 'collected_pending_review')
        verify_committed_samples(capture, store.attempt_ledger()['attempts'])
        before = {str(path): file_sha(path) for path in evidence.iterdir() if path.is_file()}
        resumed = await self.collect(resume=True)
        self.assertEqual(self.actions, ['scroll'] * 5)
        self.assertEqual(resumed['actual_attempts'], 1)
        self.assertEqual(resumed['qualified_samples'], 0)
        self.assertEqual(before, {str(path): file_sha(path) for path in evidence.iterdir() if path.is_file()})
        self.assertEqual(len(read_chain_history(self.chain_manifest)[0]), 1)

    async def test_delivery_collects_once_and_resume_reuses_complete_pending_evidence(self):
        await self.assert_single_saved_run(True)

    async def test_current_chain_cannot_omit_identity_or_original_guard_before_browser(self):
        self.prepared(False)
        with patch('playwright.async_api.async_playwright', side_effect=AssertionError('No browser before identity')):
            with self.assertRaisesRegex(ValueError, 'requires page identity'):
                await self.collect()
        self.assertEqual(self.actions, [])

    async def test_identity_bound_plan_uses_same_collector_without_admission_or_rehearsal(self):
        await self.assert_single_saved_run(True)

    async def test_invalid_explicit_legacy_admission_is_not_silently_promoted(self):
        self.prepared(True)
        bad = deepcopy(self.plan)
        bad['tasks'][0]['workflow_admission'] = {'QC_approval': False, 'packet': {'path': '/missing'}}
        with self.assertRaises(ValueError):
            collect.validate_plan(bad)
        self.assertEqual(self.actions, [])
        self.assertEqual(read_chain_history(self.chain_manifest)[0], [])

    def assert_plan_action_bounds(self, identity):
        from webcollect.production_identity import before_action
        self.prepared(identity)
        for count in (4, 11):
            bad = deepcopy(self.plan)
            operations = bad['tasks'][0]['operations']
            bad['tasks'][0]['operations'] = [dict(deepcopy(operations[n % 5]), operation_id='action-' + str(n))
                                            for n in range(count)]
            with self.subTest(count=count), self.assertRaises(ValueError):
                collect.validate_plan(bad)
        task = self.plan['tasks'][0]
        rows = [{'ended_at': 'CONTROLLED', 'operation': {'action_type': 'scroll'}} for _ in range(10)]
        with self.assertRaisesRegex(ValueError, '5-10'):
            before_action(task, rows, 'scroll')
        with self.assertRaisesRegex(ValueError, '5-10'):
            before_action(task, rows[:4], 'complete')
        before_action(task, rows[:5], 'complete')

    async def test_delivery_has_the_same_4_and_11_action_rejections(self):
        self.assert_plan_action_bounds(False)

    async def test_identity_bound_plan_has_the_same_4_and_11_action_rejections(self):
        self.assert_plan_action_bounds(True)

    async def test_shard_policy_guard_precedes_initialization_and_browser(self):
        self.prepared(False)
        with patch('webcollect.batch_protocol.verify_shard_policy', side_effect=ValueError('CONTROLLED shard policy mismatch')) as guard, \
             patch('playwright.async_api.async_playwright', side_effect=AssertionError('No browser before policy')) as browser:
            with self.assertRaisesRegex(ValueError, 'shard policy mismatch'):
                await self.collect()
        self.assertEqual(guard.call_args.args[0], self.registry)
        self.assertEqual(guard.call_args.args[1]['campaign_id'], self.policy['campaign_id'])
        browser.assert_not_called()
        self.assertFalse((self.output / 'capture' / 'bootstrap.json').exists())
        self.assertEqual(self.actions, [])

    async def test_shard_policy_is_rechecked_before_resume_dispatch(self):
        self.prepared(True)
        await self.collect()
        with patch('webcollect.batch_protocol.verify_shard_policy', side_effect=ValueError('CONTROLLED changed shard policy')) as guard, \
             patch('playwright.async_api.async_playwright', side_effect=AssertionError('No resumed browser')) as browser:
            with self.assertRaisesRegex(ValueError, 'changed shard policy'):
                await self.collect(resume=True)
        guard.assert_called_once()
        browser.assert_not_called()
        self.assertEqual(self.actions, ['scroll'] * 5)

    async def test_failure_is_preserved_and_never_qualified(self):
        self.prepared(True)
        async def broken(page, action, *args, **kwargs):
            if action != 'complete':
                self.actions.append(action)
                raise ValueError('CONTROLLED ambiguous result')
        with patch('webcollect.collect.execute', AsyncMock(side_effect=broken)):
            result = await self.collect()
        self.assertEqual(result['collected'], 0)
        self.assertEqual(result['qualified_samples'], 0)
        self.assertEqual(result['rejected'], 1)
        store = RuntimeStore(self.registry, runtime_scope(self.output / 'capture'))
        self.assertEqual(store.snapshot()['attempts'][0]['status'], 'rejected')
        self.assertTrue(list((self.output / 'capture' / 'evidence').glob('*/failure.json')))
        self.assertFalse(list((self.output / 'capture' / 'samples').glob('*/annotation.json')))

    async def test_unknown_outcome_blocks_dispatch_without_reexecuting(self):
        self.prepared(True)
        stop = SiteFailureStore.initialize({'ledger': str(self.root / 'stop.sqlite3'),
            'campaign_id': self.policy['campaign_id'], 'formal_since': time.time() - 1})
        stop.record(self.plan['tasks'][0], 'CONTROLLED-unknown', stage='observation', state='unknown',
            reason='CONTROLLED response outcome unknown', real_execution=True,
            evidence=[{'controlled': True}], usage_refs=[])
        self.policy['site_failure_guard'] = stop.binding
        self.policy_path.write_text(json.dumps(self.policy))
        result = await self.collect()
        self.assertEqual(self.actions, [])
        self.assertEqual(result['actual_attempts'], 0)
        self.assertEqual(result['qualified_samples'], 0)
        with self.assertRaises(SiteStopped):
            stop.guard(self.plan['tasks'][0])

    async def execute_shared_entry(self, identity, *, configure_after=False, register_before_qc=False):
        capability = self.prepared(True)
        # The actual execute->collect_m4->collect_one path is used; only read-only
        # preflight IO and the separately owned candidate exporter are fixtures.
        RuntimeStore(self.registry, 'CONTROLLED-authorized').initialize(self.policy)
        catalog_path = self.root / 'catalog.json'
        save_json(catalog_path, {'schema_version': 'webcollect-capability-catalog-1',
                                'mode': 'real', 'records': [capability]})
        ledger_config = config('real')
        ledger_config['site_failure_guard'] = self.policy['site_failure_guard']
        ledger = BatchLedger(self.root / 'operations.sqlite3', ledger_config, initialize=True)
        original = {k: v for k, v in self.plan.items() if k != 'media_preflight'}
        self.plan_path.write_text(json.dumps(original, ensure_ascii=False))
        async def fixture_preflight(source, output, **kwargs):
            shutil.copytree(self.root / 'planning' / 'preflight', output)
            save_json(output / 'scheduled-plan.json', self.plan)
        def fixture_candidate(repo, source, target, **kwargs):
            target.mkdir()
            (target / 'CONTROLLED.txt').write_text('Temporary candidate exporter fixture only')
        nav = MagicMock(); nav.goto = AsyncMock()
        with patch('webcollect.preflight.preflight_plan', AsyncMock(side_effect=fixture_preflight)), \
             patch('webcollect.navigation.BatchNavigation', return_value=nav), \
             patch('webcollect.production_facts.derive', return_value={'controlled': True}), \
             patch('webcollect.client_package.build_client_package', side_effect=fixture_candidate), \
             patch('webcollect.qc_handoff.prepare_qc_inputs', side_effect=AssertionError('No implicit QC')):
            result = await task_generation.execute(ledger, self.plan_path, catalog_path,
                self.output, self.registry, self.policy_path)
        self.assertEqual(self.actions, ['scroll'] * 5)
        self.assertEqual(result['qc_status'], 'qc_configuration_required')
        self.assertFalse(result['QC_approval'])
        self.assertEqual(result['collection']['qualified_samples'], 0)
        checks = load_json(result['pending_quality_checks']['path'])
        self.assertEqual(checks['plan_sha256'], file_sha(self.plan_path))
        self.assertEqual(checks['checks'], [])
        self.assertTrue(checks['requires_independent_QC'])
        self.assertEqual(ledger.summary()['model_requests'], 0)
        if register_before_qc:
            from webcollect.current_chain import append_current_result
            store = RuntimeStore(self.registry, runtime_scope(self.output / 'capture'))
            attempt = store.snapshot()['attempts'][0]
            annotation = self.output / 'capture' / 'samples' / attempt['sample_id'] / 'annotation.json'
            append_current_result(self.chain_manifest, annotation, site_uri=self.plan['tasks'][0]['site_uri'],
                                  task_key=attempt['task_key'])
            population = read_chain_history(self.chain_manifest)[0]
            self.assertEqual(len(population), 1)
            self.assertEqual(task_generation._without_own_saved_results(original, self.registry, self.output, population), [])
            unrelated = {**population[0], 'sample_id': 'CONTROLLED-unrelated'}
            self.assertEqual(task_generation._without_own_saved_results(original, self.registry, self.output, [unrelated]), [unrelated])
            for forged in ({**population[0], 'annotation_sha256': '0' * 64},
                           {**population[0], 'annotation_path': str(self.root / 'unrelated' / 'annotation.json')}):
                with self.subTest(forged=forged), self.assertRaisesRegex(ValueError, 'differs from the original'):
                    task_generation._without_own_saved_results(original, self.registry, self.output, [forged])
        if configure_after:
            # All collection/preflight functions must remain untouched when
            # explicit sampling configuration arrives after the saved result.
            with patch('webcollect.preflight.preflight_plan', AsyncMock(side_effect=AssertionError('No repeat preflight'))), \
                 patch('webcollect.collect_runtime.collect_m4', AsyncMock(side_effect=AssertionError('No repeat collection'))), \
                 patch('webcollect.qc_handoff.prepare_qc_inputs', return_value={'QC_approval': False}) as freeze:
                configured = await task_generation.execute(ledger, self.plan_path, catalog_path,
                    self.output, self.registry, self.policy_path, resume=True,
                    qc_policy={'ai_percent': 20, 'human_percent': 10, 'seed': 'CONTROLLED-later'})
            self.assertEqual(configured['qc_status'], 'QC_NOT_RUN')
            self.assertFalse(configured['QC_approval'])
            self.assertEqual(self.actions, ['scroll'] * 5)
            self.assertEqual(freeze.call_args.kwargs['collection_checks'], result['pending_quality_checks'])

    async def test_qc_configuration_after_saved_run_never_replays_collection(self):
        await self.execute_shared_entry(False, configure_after=True)

    async def test_registered_own_result_can_later_freeze_qc_without_self_duplicate_or_replay(self):
        await self.execute_shared_entry(False, configure_after=True, register_before_qc=True)

    async def test_real_qc_handoff_freezes_original_saved_pending_evidence_once(self):
        from webcollect.qc_handoff import prepare_qc_inputs
        from quality_inspector.profiles import package_files
        self.prepared(True)
        collected = await self.collect()
        self.assertEqual(collected['collected'], 1)
        capture = self.output / 'capture'
        checks_path = self.output / 'pending-quality-checks.json'
        save_json(checks_path, {'schema_version': 'webcollect-pending-quality-checks-1',
            'plan_sha256': file_sha(self.plan_path), 'history_scope': self.scope,
            'source': 'frozen-history-recomputed-at-execution', 'checks': [],
            'QC_approval': False, 'requires_independent_QC': True})
        check_ref = {'path': str(checks_path), 'sha256': file_sha(checks_path)}
        before = package_files(capture)
        from quality_inspector.format_checks import run as check_formats
        formats = check_formats(None, capture)
        self.assertTrue(all(row['confirmed_format_pass'] for row in formats['samples']),
                        json.dumps(formats['samples'], ensure_ascii=False))
        result = prepare_qc_inputs(capture, self.chain_manifest, self.output / 'qc-inputs',
            ai_percent=25, human_percent=10, seed='CONTROLLED-real-handoff', collection_checks=check_ref)
        reused = prepare_qc_inputs(capture, self.chain_manifest, self.output / 'qc-inputs',
            ai_percent=25, human_percent=10, seed='CONTROLLED-real-handoff', collection_checks=check_ref)
        self.assertEqual(result, reused)
        self.assertEqual(result['original_denominator'], 1)
        self.assertFalse(result['QC_approval'])
        self.assertEqual(result['external_model_calls'], 0)
        self.assertEqual(package_files(capture), before)
        mapping = load_json(result['collection_checks']['path'])
        self.assertEqual(mapping['source'], check_ref)
        self.assertEqual(len(mapping['sample_bindings']), 1)
        self.assertEqual(self.actions, ['scroll'] * 5)
        self.assertEqual(len(read_chain_history(self.chain_manifest)[0]), 1)

    async def test_actual_structure_metadata_export_and_handoff_preserve_saved_bytes(self):
        from webcollect.validate import validate_sample
        from webcollect.client_package import build_client_package
        from webcollect.production_facts import derive
        from webcollect.qc_handoff import prepare_qc_inputs
        self.prepared(True)
        with patch('webcollect.collect_runtime.validate_sample', side_effect=validate_sample), \
             patch('webcollect.metadata.export_metadata', side_effect=self.real_metadata):
            collected = await self.collect()
        self.assertEqual(collected['collected'], 1)
        self.assertEqual(collected['qualified_samples'], 0)
        capture = self.output / 'capture'
        facts = self.output / 'facts.json'; save_json(facts, derive(capture))
        candidate = self.output / 'candidate'
        exported = build_client_package(Path(__file__).resolve().parents[3], capture, candidate, facts=facts)
        self.assertEqual(exported['independent_qc_status'], 'NOT_RUN')
        result = prepare_qc_inputs(candidate, self.chain_manifest, self.output / 'actual-qc-inputs',
            ai_percent=25, human_percent=10, seed='CONTROLLED-unmocked-format-export')
        self.assertEqual(result['original_denominator'], 1)
        self.assertFalse(result['QC_approval'])
        self.assertEqual(self.actions, ['scroll'] * 5)

    async def test_same_artifact_collection_independent_fixture_qc_final_and_zip(self):
        """Explicit SYNTHETIC protocol approvals, never actual AI/human acceptance."""
        import sys
        import zipfile
        from quality_inspector import engine
        from quality_inspector.profiles import DEFAULT_DELIVERY_PROFILE, package_files
        from quality_inspector.reporting import review_template
        from webcollect.validate import validate_sample
        from webcollect.client_package import build_client_package
        from webcollect.client_reports import finalize_client_package, archive_client_package
        from webcollect.production_facts import derive
        from webcollect.qc_handoff import prepare_qc_inputs
        repo = Path(__file__).resolve().parents[3]
        sys.path.insert(0, str(repo / 'projects/quality-inspector/tests'))
        from delivery_scope_fixture import freeze_scope
        self.prepared(True)
        site_store = SiteFailureStore.initialize({'ledger': str(self.root / 'site-status.sqlite3'),
            'campaign_id': self.policy['campaign_id'], 'formal_since': time.time() - 1})
        self.policy['site_failure_guard'] = site_store.binding
        self.policy_path.write_text(json.dumps(self.policy))
        with patch('webcollect.collect_runtime.validate_sample', side_effect=validate_sample), \
             patch('webcollect.metadata.export_metadata', side_effect=self.real_metadata):
            collected = await self.collect()
        self.assertEqual(collected['collected'], 1)
        self.assertEqual(collected['qualified_samples'], 0)
        capture = self.output / 'capture'
        raw_before = package_files(capture)
        facts = self.output / 'facts.json'; save_json(facts, derive(capture))
        candidate = self.output / 'candidate'
        build_client_package(repo, capture, candidate, facts=facts)
        candidate_before = package_files(candidate)
        handoff = prepare_qc_inputs(candidate, self.chain_manifest, self.output / 'qc-inputs',
            ai_percent=25, human_percent=10, seed='CONTROLLED-single-artifact')
        self.assertFalse(handoff['QC_approval'])
        profile = load_json(DEFAULT_DELIVERY_PROFILE)
        profile.update(profile_id='SYNTHETIC-SINGLE-ARTIFACT-ONLY',
            authority='Explicit one-case category exception in a disposable offline protocol test, never production acceptance')
        profile['targets'].update(expected_samples=1, category_share='report-only')
        profile_path = self.output / 'SYNTHETIC-profile.json'; save_json(profile_path, profile)
        with patch.object(engine, 'baseline_load', side_effect=AssertionError('No baseline/sample library reads')), \
             patch('webcollect.model_gateway.ModelGateway.call', side_effect=AssertionError('No real model dispatch')) as model:
            pending = engine.inspect(None, candidate, profile=profile_path, inspection_stage='payload')
            review = review_template(pending)
            review.pop('package_review', None)
            for row in review['records']:
                steps = [step['step_id'] for step in load_json(candidate / 'samples' / row['sample_id'] / 'annotation.json')['steps']]
                row['reviewer'] = {'kind': 'ai', 'name': 'SYNTHETIC PROTOCOL ONLY - NO ACTUAL MODEL REVIEW'}
                row['provenance'] = {'description': 'Authored synthetic binding fixture; no human or model viewed this package.',
                                     'frames_viewed': steps}
                row['step_observations'] = [{'step_id': step, 'note': 'SYNTHETIC protocol expectation for step ' + str(step)} for step in steps]
                row['checks'] = {name: {'status': 'PASS', 'note': 'Authored SYNTHETIC protocol expectation only.',
                                       'evidence_steps': steps} for name in engine.SEMANTIC}
            document = review['delivery_document_review']
            document['reviewer'] = {'kind': 'ai', 'name': 'SYNTHETIC DOCUMENT FIXTURE - NO ACTUAL MODEL REVIEW'}
            document['provenance'] = {'description': 'Authored synthetic document-binding fixture, never production acceptance.'}
            for check in document['checks'].values():
                check.update(status='PASS', note='Explicit SYNTHETIC document expectation only.', evidence=[
                    {'path': 'README.md', 'sha256': document['payload_files_sha256']['README.md'],
                     'detail': 'SYNTHETIC fixture reference to this actual temporary payload file.'}])
            reviews_path = self.output / 'SYNTHETIC-reviews.json'; save_json(reviews_path, review)
            payload = engine.inspect(None, candidate, profile=profile_path, reviews=reviews_path, inspection_stage='payload')
            self.assertEqual(payload['delivery_status'], 'PASS', json.dumps(payload.get('dataset_checks'), ensure_ascii=False))
            payload_path = self.output / 'payload-report.json'; save_json(payload_path, payload)
            effective, cross = freeze_scope(self.output / 'scope', [candidate])
            finalized = finalize_client_package(repo, candidate, payload_path, self.output / 'final',
                effective_set=effective, cross_package_report=cross)
            final = engine.inspect(None, finalized['output'], profile=profile_path,
                                   reviews=reviews_path, inspection_stage='final')
            self.assertEqual(final['delivery_status'], 'PASS')
            self.assertTrue(final['release_ready'])
            final_path = self.output / 'final-report.json'; save_json(final_path, final)
            archived = archive_client_package(finalized['output'], final_path, self.output / 'SYNTHETIC-offline.zip',
                effective_set=effective, cross_package_report=cross)
            with zipfile.ZipFile(archived['archive']) as archive:
                final_root = Path(finalized['output'])
                self.assertEqual(len(archive.namelist()), len(package_files(final_root)))
                for name in archive.namelist():
                    self.assertEqual(archive.read(name),
                        (final_root / Path(name).relative_to(final_root.name)).read_bytes())
            model.assert_not_called()
        self.assertEqual(self.actions, ['scroll'] * 5)
        self.assertEqual(raw_before, package_files(capture))
        self.assertEqual(candidate_before, package_files(candidate))
        self.assertEqual(len(read_chain_history(self.chain_manifest)[0]), 1)
        store = RuntimeStore(self.registry, runtime_scope(capture))
        self.assertEqual(store.snapshot()['tasks'][0]['status'], 'collected_pending_review')
        site_store.sync_successes(self.registry, self.policy['campaign_id'])
        self.assertEqual(site_store.status(self.plan['tasks'][0])['qualified_success_count'], 0)
        fake = self.output / 'not-a-quality-report.json'
        save_json(fake, {'pretend': 'PASS', 'sample_id': load_json(capture / 'manifest.json')['samples'][0]})
        with self.assertRaises(ValueError):
            store.record_review(load_json(capture / 'manifest.json')['samples'][0], 'pass',
                [{'path': str(fake), 'sha256': file_sha(fake)}], 'SYNTHETIC invalid evidence must not grant success')
        self.assertEqual(site_store.status(self.plan['tasks'][0])['qualified_success_count'], 0)
        # Only the actual bound independent fixture report, not pending capture,
        # can record first valid data in this disposable test ledger.
        report_ref = {'path': str(payload_path), 'sha256': file_sha(payload_path)}
        store.record_review(load_json(capture / 'manifest.json')['samples'][0], 'pass', [report_ref],
                            'SYNTHETIC fixture QC pass; never real human/model acceptance')
        self.assertEqual(site_store.status(self.plan['tasks'][0])['qualified_success_count'], 1)
        for n in range(3):
            site_store.record(self.plan['tasks'][0], 'CONTROLLED-after-success-' + str(n), stage='formal',
                state='failed', reason='SYNTHETIC later failure', real_execution=True,
                evidence=[report_ref], usage_refs=[])
        status = site_store.status(self.plan['tasks'][0])
        self.assertEqual(status['state'], 'succeeded')
        self.assertFalse(status['unavailable_before_first_valid'])
        self.assertTrue(status['dispatch_blocked'])  # Existing post-success limit was not weakened.
        portable = site_store.export_facts()
        receiving = SiteFailureStore.initialize({**site_store.binding, 'ledger': str(self.root / 'other-machine.sqlite3')})
        receiving.import_facts(portable)
        imported = receiving.status(self.plan['tasks'][0])
        self.assertEqual(imported['qualified_success_count'], 0)
        self.assertEqual(imported['source_reported_success_count'], 1)
        self.assertTrue(imported['dispatch_blocked'])

    async def test_pilot_uses_same_execute_entry_with_explicit_qc_only(self):
        await self.execute_shared_entry(True)

    async def test_delivery_uses_same_execute_entry_with_explicit_qc_only(self):
        await self.execute_shared_entry(False)


class ProtectedSelectorTests(unittest.IsolatedAsyncioTestCase):
    def test_future_results_are_protected_without_becoming_current_assertions(self):
        task = {'final_assertions': [{'selector': '#result', 'contains': '完成'}], 'operations': [
            {'postconditions': [{'selector': '#future-chart', 'contains': '结果'}, {'visible_text': '正文'}]},
            {'postconditions': [{'selector': '#result', 'contains': '完成'}]}]}
        self.assertEqual(collect.task_protected_selectors(task), ['#future-chart', '#result'])
        self.assertEqual(len(task['final_assertions']), 1)

    async def test_terminal_refresh_passes_read_only_protection_to_all_capture_checks(self):
        from test_complete_refresh import frame, CONDITIONS
        observation = frame()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(collect, 'capture', AsyncMock(return_value=observation)) as capture, \
             patch.object(collect, 'verify_execution_state', AsyncMock(return_value={'matched': True})) as verify, \
             patch.object(collect.asyncio, 'sleep', AsyncMock()):
            await collect.capture_complete(object(), Path(directory), assertions=CONDITIONS,
                                           protected_selectors=['#future-result'])
        self.assertEqual(capture.await_args.kwargs['protected_selectors'], ['#future-result'])
        self.assertEqual(verify.await_args.kwargs['protected_selectors'], ['#future-result'])
        self.assertEqual(capture.await_args.kwargs['assertions'], CONDITIONS)


class QcPolicyTests(unittest.TestCase):
    def test_explicit_policy_is_file_only_and_passes_bound_checks(self):
        with patch('webcollect.qc_handoff.prepare_qc_inputs', return_value={'QC_approval': False}) as freeze:
            result = task_generation._prepare_qc_handoff('/candidate', '/current-chain', Path('/new-inputs'),
                {'ai_percent': 15, 'human_percent': 5, 'seed': 'CONTROLLED'}, {'path': '/checks', 'sha256': 'x'})
        freeze.assert_called_once_with('/candidate', '/current-chain', Path('/new-inputs'),
            ai_percent=15, human_percent=5, seed='CONTROLLED', collection_checks={'path': '/checks', 'sha256': 'x'})
        self.assertEqual(result['qc_status'], 'QC_NOT_RUN')

    def test_no_policy_never_defaults_to_full_ai(self):
        with patch('webcollect.qc_handoff.prepare_qc_inputs', side_effect=AssertionError('No implicit sampling')):
            self.assertEqual(task_generation._prepare_qc_handoff('/candidate', '/chain', '/qc', None, {})['qc_status'],
                             'qc_configuration_required')
        for bad in ({}, {'ai_percent': 100, 'human_percent': 0},
                    {'ai_percent': True, 'human_percent': 0, 'seed': 's'},
                    {'ai_percent': float('nan'), 'human_percent': 0, 'seed': 's'},
                    {'ai_percent': 1, 'human_percent': 0, 'seed': ''}):
            with self.subTest(policy=bad), self.assertRaises(ValueError):
                task_generation._qc_policy(bad)


if __name__ == '__main__':
    unittest.main()
