"""Core no-version contract tests (2026-11-11 rewrite).

Replaces the retired 260-file suite. Only current business contracts are
asserted: stable protocol names, the single completion rule, strategy-result
close-out, candidate-pool v2 claiming, and the documented CLI entries.
All checks are offline; no real GLM, browser or production database is used.
"""
import json
import re
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from site_planner.candidate_pool import CandidatePool
from webcollect.candidate_contract import VERSION as CONSUMPTION_VERSION
from webcollect.collection_strategy import (DEFAULT_STRATEGY, RESULT_CONTRACT,
                                            STRATEGIES, STRATEGY_BANDED_REACT,
                                            STRATEGY_SCREENSHOT_PLAN, STRATEGY_STEPWISE,
                                            finalize_strategy_result, freeze,
                                            strategy_id)
from webcollect.closing_policy import MINIMUM, attempt_limit, completion_delivery_decision
from webcollect.plan_protocol import (ENDING_POLICY, PLAN_PROTOCOL, REACT_PROTOCOL,
                                      RESULT_COMPLETION_PROTOCOL, RESULT_EXECUTION_POLICY)


class PlanProtocolContract(unittest.TestCase):
    def test_stable_names_are_the_single_owner_values(self):
        self.assertEqual(PLAN_PROTOCOL, 'conditional-plan')
        self.assertEqual(ENDING_POLICY, 'goal-completion-ending')
        self.assertEqual(RESULT_EXECUTION_POLICY, 'result-execution')
        self.assertEqual(RESULT_COMPLETION_PROTOCOL, 'result-completion')
        self.assertEqual(REACT_PROTOCOL, 'react-native')
        self.assertEqual(tuple(STRATEGIES), ('react', 'screenshot_plan', 'stepwise'))
        # 策略1完全冻结：新任务缺省策略2；策略3（stepwise）显式选择。身份表
        # 保留react供历史只读解析。
        self.assertEqual(DEFAULT_STRATEGY, STRATEGY_STEPWISE)
        import webcollect.screenshot_plan as screenshot_plan_module
        import webcollect.stepwise as stepwise_module
        from webcollect.collection_strategy import (Strategy1Forbidden,
                                                    is_stepwise, select)
        frozen = {'task_id': 't', 'fragment': {}, 'workflow_proposal': {'spec': {}}}
        with self.assertRaises(Strategy1Forbidden):
            freeze(frozen, STRATEGY_BANDED_REACT)
        freeze(frozen)
        self.assertEqual(strategy_id(frozen), STRATEGY_STEPWISE)
        self.assertIs(select(frozen), stepwise_module)
        # 策略 3 显式冻结与解析：独立包路由，不挂策略2 action_stability 协议。
        third = {'task_id': 't3', 'fragment': {}, 'workflow_proposal': {'spec': {}}}
        freeze(third, STRATEGY_STEPWISE)
        self.assertEqual(strategy_id(third), STRATEGY_STEPWISE)
        self.assertTrue(is_stepwise(third))
        self.assertTrue(is_stepwise(frozen))
        self.assertIs(select(third), stepwise_module)
        # 策略 3 帧取证同为 action-scoped 观察（共享宿主稳定域实现），冻结同
        # 一观察策略标记；但不冻结任何策略 2 模板。
        from webcollect.action_stability import ACTION_STABILITY_PROTOCOL
        self.assertEqual(third['fragment']['action_stability_protocol'], ACTION_STABILITY_PROTOCOL)
        self.assertNotIn('screenshot_template', third['fragment'])
        # Absent-marker fragments keep their historical react identity; they are
        # never silently migrated to 策略 2, and selecting them is refused.
        unmarked = {'task_id': 'h', 'fragment': {}, 'workflow_proposal': {'spec': {}}}
        self.assertEqual(strategy_id(unmarked), STRATEGY_BANDED_REACT)
        with self.assertRaises(Strategy1Forbidden):
            select(unmarked)
        sealed = {'fragment': {'collection_strategy': {'id': 'webcollect-collection-banded-react-1'}}}
        self.assertEqual(strategy_id(sealed), STRATEGY_BANDED_REACT)
        unknown = {'fragment': {'collection_strategy': {'id': 'no-such-strategy'}}}
        with self.assertRaises(ValueError):
            strategy_id(unknown)
        with self.assertRaises(ValueError):
            freeze({'fragment': {}, 'workflow_proposal': {'spec': {}}}, 'no-such-strategy')
        from webcollect.dynamic_regions import VERSION, SUGGESTION_VERSION
        from webcollect.plan_protocol import DYNAMIC_REGIONS_PROTOCOL, SEARCH_SUGGESTIONS_PROTOCOL
        script = (Path(__file__).parents[1] / 'webcollect/snapshot.js').read_text()
        self.assertEqual(VERSION, DYNAMIC_REGIONS_PROTOCOL)
        self.assertEqual(SUGGESTION_VERSION, SEARCH_SUGGESTIONS_PROTOCOL)
        self.assertIn(f"const dynamicVersion='{VERSION}';", script)
        self.assertIn(f"const suggestionVersion='{SUGGESTION_VERSION}';", script)
        # 策略2拆分为三个独立模板包：路由解析按冻结模板名分发；历史封存任务
        # （无模板标记）解析到单体实现，保证重放/读回按原实现只读。
        from webcollect import screenshot_planners
        from webcollect.screenshot_templates import (generic as generic_template,
                                                      long_reading as long_reading_template,
                                                      operation as operation_template)
        self.assertEqual(screenshot_planners.TEMPLATE_NAMES,
                         ('operation', 'long_reading', 'generic'))
        self.assertEqual([operation_template.TEMPLATE_NAME, long_reading_template.TEMPLATE_NAME,
                          generic_template.TEMPLATE_NAME],
                         ['operation', 'long_reading', 'generic'])
        self.assertEqual(len({id(screenshot_planners.template_module(name))
                              for name in screenshot_planners.TEMPLATE_NAMES}), 3)
        self.assertIs(screenshot_planners.template_module(None), screenshot_plan_module)
        with self.assertRaisesRegex(ValueError, 'Unknown screenshot template'):
            screenshot_planners.template_module('no-such-template')
        # 模板包相互隔离：包内源码不得引用其它模板包（from ..）、不得引用
        # webcollect.screenshot_templates.*、也不得引用单体 screenshot_plan/
        # screenshot_session；包内只允许 .plan/.session/.observation/.execution。
        for path in sorted((Path(__file__).parents[1] / 'webcollect/screenshot_templates').glob('*/*.py')):
            for line in path.read_text(encoding='utf-8').splitlines():
                stripped = line.lstrip()
                self.assertIsNone(re.match(r'from \.\.[.\w]*', stripped), (path.name, line))
                self.assertFalse(stripped.startswith('from webcollect.screenshot_templates'), (path.name, line))
                self.assertNotIn('from .screenshot_plan import', stripped, (path.name, line))
                self.assertNotIn('from .screenshot_session import', stripped, (path.name, line))
        # 策略 3 独立边界：stepwise 包源码不得引用其它策略业务实现（策略2
        # 模板/单体、策略1链、合同与派生、导航许可），也不得引用 RawSessionCore。
        forbidden_stepwise = (
            'from .screenshot_plan import', 'from .screenshot_session import',
            'screenshot_templates', 'from .banded_plan import', 'from .react_session import',
            'from .collection_contract import', 'from .collection_evidence import',
            'from .closing_policy import completion_delivery_decision',
            'from .goal_evidence import', 'from .candidate_navigation import',
            'RawSessionCore', '_perform_primitive', 'from .postprocess import session_record',
            'from .postprocess import effective_trajectory', 'from .postprocess import process')
        for path in sorted((Path(__file__).parents[1] / 'webcollect/stepwise').glob('*.py')):
            for line in path.read_text(encoding='utf-8').splitlines():
                stripped = line.lstrip()
                if not stripped.startswith(('from ', 'import ')):
                    continue  # 只约束真实 import 语句；docstring 中的模块名是边界说明
                for token in forbidden_stepwise:
                    self.assertNotIn(token, stripped, (path.name, token, line))
        # stepwise 仅允许经宿主基础设施复用（浏览器/网关/账本/存储/反馈/索引）；
        # closing_policy 只允许取共享交付策略名常量，不允许调用其业务判定。
        allowed_hosts = ('from .. import browser', 'from .. import collection_strategy',
                         'from ..browser import', 'from ..model_gateway import',
                         'from ..batch_core import', 'from ..storage import',
                         'from ..agent_feedback import', 'from ..agent_controller import',
                         'from ..production_quality import', 'from ..runtime import',
                         'from ..planning import', 'from ..sqlite_connection import',
                         'from ..action_stability import', 'from ..action_normalization import',
                         'from ..task_instruction import', 'from ..collection_strategy import',
                         'from ..collect_runtime import', 'from ..postprocess import post_seal_name',
                         'from ..session_core import ReactStop', 'from ..failure_policy import',
                         'from ..candidate_contract import', 'from ..application_identity import aliases',
                         'from ..closing_policy import COMPLETED_GOAL_DELIVERY',
                         'from ..production_identity import actual_proof')
        for path in sorted((Path(__file__).parents[1] / 'webcollect/stepwise').glob('*.py')):
            for line in path.read_text(encoding='utf-8').splitlines():
                stripped = line.lstrip()
                if stripped.startswith('from ..'):
                    self.assertTrue(any(stripped.startswith(allowed) for allowed in allowed_hosts),
                                    (path.name, line))

    def test_saved_research_requires_frozen_production_comparison(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        import sqlite3
        from webcollect.batch_core import file_sha
        from webcollect.candidate_contract import validate_research_v2
        from webcollect.session_objective import VERSION
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            def freeze(name, value):
                path = root / name
                path.write_text(json.dumps(value))
                return {'path': str(path), 'sha256': file_sha(path)}
            objective = freeze('session-objective.json', {'schema_version': VERSION,
                'candidate_id': 'candidate', 'version': 1})
            receipt = freeze('saved.json', {'sample_id': 'sample'})
            binding = {'output': str(root), 'registry': str(root/'registry'),
                       'ledger': str(root/'ledger'), 'history_set': str(root/'manifest')}
            comparison = {'role': 'comparison', 'claim_id': 'original',
                          'sample_id': 'sample', 'save_receipt': receipt}
            auth = {'scope': 'fixed-baseline-research-only', 'candidate_id': 'candidate',
                    'version': 1, 'original_claim_id': 'original', 'objective': objective,
                    'comparisons': [comparison], 'production_counted': False,
                    'pool': str(root/'pool'), 'registry': binding['registry']}
            descriptor = {'schema_version': 'candidate-research-replay',
                'original_claim_id': 'original', 'objective': objective,
                'authorization': freeze('authorization.json', auth),
                'comparisons': [comparison], 'production_counted': False}
            con = sqlite3.connect(':memory:'); con.row_factory = sqlite3.Row
            con.execute('CREATE TABLE candidate_claims(candidate_id,claim_id,binding,state)')
            con.execute('CREATE TABLE candidate_results(candidate_id,claim_id,sample_id,record,effective)')
            saved = {'sample_id': 'sample', 'registry': binding['registry'], 'save_receipt': receipt}
            con.execute('INSERT INTO candidate_claims VALUES(?,?,?,?)',
                        ('candidate','original',json.dumps(binding),'succeeded'))
            con.execute('INSERT INTO candidate_results VALUES(?,?,?,?,1)',
                        ('candidate','original','sample',json.dumps(saved))); con.commit()
            @contextmanager
            def connect():
                yield con
            pool = SimpleNamespace(path=root/'pool', pool=SimpleNamespace(connect=connect))
            original = {'candidate_id':'candidate','claim_id':'original','version':1,
                        'state':'succeeded','binding':binding}
            validate_research_v2(descriptor, pool, original)
            self.assertEqual(con.execute('SELECT effective FROM candidate_results').fetchone()[0], 1)
            auth['comparisons'] = []; descriptor['comparisons'] = []
            descriptor['authorization'] = freeze('authorization.json', auth)
            with self.assertRaisesRegex(ValueError, 'production comparison'):
                validate_research_v2(descriptor, pool, original)
            # The browser-close proof permits only its named next research
            # request; ordinary guards use it only while that claim is active.
            from unittest.mock import patch
            from webcollect.request_quarantine import authorized_transport_research
            con.execute('ALTER TABLE candidate_claims ADD COLUMN request_id')
            con.execute('ALTER TABLE candidate_claims ADD COLUMN expires')
            con.execute('ALTER TABLE candidate_claims ADD COLUMN version')
            con.execute('UPDATE candidate_claims SET version=1');con.commit()
            with sqlite3.connect(root/'pool') as disk:
                con.backup(disk)
            facts = {'pool':str(root/'pool'),'candidate_id':'candidate',
                     'claim_id':'original','next_request_id':'run-r03/new-research','ledger':binding['ledger']}
            with sqlite3.connect(root/'registry') as registry:
                registry.execute('CREATE TABLE m4_events(event_type,attempt_id,payload_json)')
                registry.execute('INSERT INTO m4_events VALUES(?,?,?)',
                    ('planning_timeout_research_authorized','attempt',json.dumps({
                     'authorization':descriptor['authorization'],'closed_execution':facts})))
            with patch('webcollect.request_quarantine.transport_closed_execution', return_value=facts):
                self.assertTrue(authorized_transport_research(root/'registry','attempt',request_id='run-r03/new-research'))
                self.assertFalse(authorized_transport_research(root/'registry','attempt',request_id='run-r04/new-research'))
                self.assertFalse(authorized_transport_research(root/'registry','attempt'))
                own_auth=freeze('next-authorization.json',{'new_request_id':'run-r03/new-research'})
                with sqlite3.connect(root/'pool') as disk:
                    disk.execute('INSERT INTO candidate_claims VALUES(?,?,?,?,?,?,?)',
                        ('candidate','next',json.dumps({'ledger':binding['ledger'],'registry':str(root/'registry'),
                         'research_replay':{'original_claim_id':'original','production_counted':False,
                         'authorization':own_auth}}),'consuming','run-r03/new-research',9999999999,1))
                self.assertFalse(authorized_transport_research(root/'registry','attempt'))
                self.assertFalse(authorized_transport_research(root/'registry','attempt',request_id='run-r04/new-research'))
                self.assertTrue(authorized_transport_research(root/'registry','attempt',request_id='run-r03/new-research'))
                with sqlite3.connect(root/'pool') as disk:
                    disk.execute("UPDATE candidate_claims SET expires=0 WHERE claim_id='next'")
                self.assertFalse(authorized_transport_research(root/'registry','attempt',request_id='run-r03/new-research'))
            from webcollect.request_quarantine import _verify_execution_entry
            report=root/'round-03';report.mkdir()
            launch=freeze('launch-next.py',{'reviewed':'launcher'})
            worker=freeze('worker-next.py',{'reviewed':'worker'})
            entry={'run_intent':{'path':str(root/'run-intent.json')},
                   'process_start':{'path':str(report/'process.json')},'launcher':launch,'worker':worker}
            started={'command':[sys.executable,worker['path'],str(report)],'launcher':launch,'worker':worker}
            _verify_execution_entry(root/'registry','attempt',entry,report,started,transport=True)
            started['command'][1]=launch['path']
            with self.assertRaisesRegex(ValueError,'actual execution command'):
                _verify_execution_entry(root/'registry','attempt',entry,report,started,transport=True)
            con.close()


class ClosingPolicyContract(unittest.TestCase):
    """Single rule: original goal success + >= MINIMUM effective steps, no ceiling."""

    @staticmethod
    def _annotation(steps, *, status='success'):
        return {'completion_status': status,
                'steps': [{'action': {'action_type': kind}} for kind in steps]}

    @staticmethod
    def _raw(*, effective, ending_kind='HOST_PLAN_ENDPOINT', safe=True, flagged=False,
             unknown=False, stop_reason='ready'):
        return {'effective_steps': effective,
                'collection_ending': {'kind': ending_kind, 'safe_for_pending_sample': safe,
                                      'flagged': flagged, 'external_effect_unknown': unknown,
                                      'endpoint_evidence': {
                                          'image': {'path': 'x'}, 'source': 'host_plan_endpoint',
                                          'session_objective_evidence': {'completion': {
                                              'answer': {'check_answers': [{'check_index': 0}]},
                                              'original_checks': ['c0']}}}},
                'goal_evidence': {'checks': [{'status': 'VERIFIED'}]},
                'stop_reason': stop_reason, 'unknown': unknown, 'trusted_prefix': None}

    def test_five_effective_steps_with_verified_endpoint_are_eligible(self):
        annotation = {'completion_status': 'success',
                      'steps': [{'action': {'action_type': 'click'}} for _ in range(MINIMUM)]}
        raw = self._raw(effective=MINIMUM)
        decision = completion_delivery_decision(annotation, raw)
        self.assertEqual(decision['delivery_policy'], 'completed-goal-delivery')
        self.assertTrue(decision['original_goal_completed'])
        self.assertTrue(decision['delivery_eligible'])

    def test_under_five_effective_steps_cannot_be_eligible(self):
        annotation = self._annotation(['click', 'type', 'click'])
        raw = self._raw(effective=3)
        decision = completion_delivery_decision(annotation, raw)
        self.assertFalse(decision['delivery_eligible'])

    def test_more_than_ten_steps_is_not_rejected(self):
        annotation = {'completion_status': 'success',
                      'steps': [{'action': {'action_type': 'click'}} for _ in range(12)]}
        raw = self._raw(effective=12)
        decision = completion_delivery_decision(annotation, raw)
        self.assertTrue(decision['delivery_eligible'])
        self.assertEqual(decision['effective_steps'], 12)

    def test_flagged_or_unknown_endings_stay_ineligible(self):
        annotation = self._annotation(['click'] * MINIMUM)
        for raw in (self._raw(effective=MINIMUM, flagged=True),
                    self._raw(effective=MINIMUM, unknown=True),
                    self._raw(effective=MINIMUM, safe=False),
                    self._raw(effective=MINIMUM, stop_reason='no_path')):
            self.assertFalse(completion_delivery_decision(annotation, raw)['delivery_eligible'])

    def test_no_cumulative_attempt_ceiling_exists(self):
        task = {'fragment': {'ending_policy': ENDING_POLICY}}
        self.assertIsNone(attempt_limit(task))
        task['fragment']['budgets'] = {'max_actions': 40}
        self.assertEqual(attempt_limit(task), 40)


class StrategyResultContract(unittest.TestCase):
    def test_freeze_records_strategy_and_dispatch_follows(self):
        import asyncio
        from unittest.mock import patch, Mock
        from webcollect.collection_strategy import (Strategy1Forbidden, Strategy2Frozen,
            select, enabled, save_eligibility)
        from webcollect.action_stability import ACTION_STABILITY_PROTOCOL
        from webcollect import candidate_consumer, collect_runtime, task_generation, stepwise
        task = {'task_id': 't', 'fragment': {}, 'workflow_proposal': {'spec': {}}}
        freeze(task)
        self.assertEqual(strategy_id(task), STRATEGY_STEPWISE)
        self.assertIs(select(task), stepwise)
        self.assertEqual(task['fragment']['action_stability_protocol'], ACTION_STABILITY_PROTOCOL)
        self.assertNotIn('screenshot_template', task['fragment'])
        for value, error_type in ((STRATEGY_SCREENSHOT_PLAN, Strategy2Frozen),
                                  (STRATEGY_BANDED_REACT, Strategy1Forbidden)):
            legacy = {'fragment': {'collection_strategy': {'id': value}},
                      'workflow_proposal': {'spec': {}}}
            with self.assertRaises(error_type):
                freeze({'fragment': {}, 'workflow_proposal': {'spec': {}}}, value)
            with self.assertRaises(error_type):
                select(legacy)
            self.assertEqual(strategy_id(legacy), value)
            with patch.object(candidate_consumer, 'startup_check', side_effect=AssertionError('startup before refusal')):
                with self.assertRaises(error_type):
                    asyncio.run(candidate_consumer.run(None, None, worker_id='offline',
                        request_prefix='offline', collection_strategy=value))
                with self.assertRaises(error_type):
                    asyncio.run(candidate_consumer._consume(None, {}, None, output=None,
                        registry=None, policy=None, history_set=None, collection_strategy=value))
            with patch.object(collect_runtime, 'read_json', return_value={'tasks': [legacy]}), \
                 patch.object(collect_runtime, '_collect_m4_locked', side_effect=AssertionError('runtime started')):
                with self.assertRaises(error_type):
                    asyncio.run(collect_runtime.collect_m4('unused', 'unused', 'unused'))
            with self.assertRaises(error_type):
                asyncio.run(collect_runtime._react_collection(None, legacy, None,
                    None, None, None, None, ledger=None, parent_job=None, registry=None, manifest=None, index=None))
            with self.assertRaises(error_type):
                task_generation._generate_react_url(None, 'unused', url='https://example.org',
                    react_candidate={'collection_strategy': value})
            from webcollect.failure_policy import disposition
            self.assertEqual(disposition(error_type())['disposition'], 'global')
            self.assertEqual(collect_runtime.classify_failure(error_type()), 'program')
        # Historical strategy2 interpretation and the shared save decision remain read-only.
        historical = {'fragment': {'collection_strategy': {'id': STRATEGY_SCREENSHOT_PLAN}}}
        self.assertTrue(enabled(historical))
        from webcollect.screenshot_planners import template_module, task_template_name
        import webcollect.screenshot_plan as screenshot_plan
        self.assertIs(template_module(task_template_name(historical)), screenshot_plan)
        annotation = {'completion_status': 'success', 'steps': [{'action': {'action_type': 'click'}}] * 5}
        raw = ClosingPolicyContract._raw(effective=5)
        self.assertEqual(save_eligibility(annotation, raw), completion_delivery_decision(annotation, raw))
        self.assertEqual(strategy_id({'fragment': {}}), STRATEGY_BANDED_REACT)

        # Direct collect/preflight CLI paths must reject old non-M4 plans before
        # validation, output creation, browser launch or any page allocation.
        from webcollect import collect, preflight, site_scheduler, admission_cohort, __main__ as cli
        from io import StringIO
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for value, error_type in ((None, Strategy1Forbidden),
                                      (STRATEGY_BANDED_REACT, Strategy1Forbidden),
                                      (STRATEGY_SCREENSHOT_PLAN, Strategy2Frozen)):
                legacy = {} if value is None else {'fragment': {'collection_strategy': {'id': value}}}
                plan = root / 'plan.json'
                plan.write_text(json.dumps({'tasks': [legacy]}))
                output = root / 'output'
                with patch('playwright.async_api.async_playwright',
                           side_effect=AssertionError('browser before refusal')) as browser, \
                     patch.object(collect, 'collect_one',
                                  side_effect=AssertionError('page before refusal')) as collect_one, \
                     patch.object(collect, 'validate_plan') as validate, \
                     patch('sys.stderr', new_callable=StringIO) as stderr:
                    with self.assertRaises(error_type):
                        asyncio.run(collect.collect_plan(plan, output, root / 'registry.sqlite3'))
                    with self.assertRaises(error_type):
                        asyncio.run(preflight.preflight_plan(plan, output))
                    for command in ('collect', 'preflight'):
                        args = [command, '--plan', str(plan), '--output', str(output)]
                        if command == 'collect':
                            args += ['--registry', str(root / 'registry.sqlite3')]
                        self.assertEqual(cli.main(args), 2)
                    self.assertIn(error_type.MESSAGE, stderr.getvalue())
                    browser.assert_not_called()
                    collect_one.assert_not_called()
                    validate.assert_not_called()
                    self.assertFalse(output.exists())
                # Scheduler validation must reject before cohort reservation,
                # registry access, output creation or its collector is entered.
                registry = root / 'registry.sqlite3'; registry.touch()
                publication = root / 'publication.json'; publication.write_text('{}')
                policy = root / 'policy.json'; policy.write_text('{}')
                config = {'registry': str(registry), 'max_parallel_sites': 1,
                          'sites': [{'site_key': 'offline', 'batches': [{
                              'plan': str(plan), 'publication': str(publication),
                              'policy': str(policy), 'output': str(root / 'capture')}]}]}
                config_path = root / 'schedule-config.json'; config_path.write_text(json.dumps(config))
                with patch.object(site_scheduler, 'validate_policy', return_value={'max_workers': 1}), \
                     patch.object(site_scheduler, 'workspace_connect', side_effect=AssertionError('registry before refusal')) as connect, \
                     patch.object(admission_cohort, 'reserve_schedule', side_effect=AssertionError('reservation before refusal')) as reserve, \
                     patch.object(site_scheduler, 'collect_m4', side_effect=AssertionError('collection before refusal')) as collector, \
                     patch('sys.stderr', new_callable=StringIO) as stderr:
                    with self.assertRaises(error_type):
                        asyncio.run(site_scheduler.run_schedule(config, output))
                    self.assertEqual(site_scheduler.main(['--config', str(config_path), '--output', str(output)]), 2)
                    self.assertIn(error_type.MESSAGE, stderr.getvalue())
                    connect.assert_not_called()
                    reserve.assert_not_called()
                    collector.assert_not_called()
                    self.assertFalse(output.exists())

    def test_execute_allows_source_changes_without_registry_snapshot(self):
        import asyncio
        import sqlite3
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock, patch
        from webcollect import task_generation as generation
        from webcollect.batch_core import file_sha
        from webcollect.session_core import build_url_task
        task = build_url_task(url='https://example.org/tool', task_version='offline')
        freeze(task)
        from webcollect.planning import object_sha256
        task['task_id'] = 'react-' + object_sha256({'url': task['initial_url'], 'spec': task['workflow_proposal']['spec']})[:24]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'history.json'; manifest.write_text('{}')
            history = {'schema_version': 'webcollect-task-history-scope-1',
                       'manifest': {'path': str(manifest), 'sha256': file_sha(manifest)}}
            plan = {'schema_version': 'plan-m4', 'tasks': [task], 'generation': {
                'mode': 'real', 'history_scope': history, 'source_identity': {'old.py': 'old'}}}
            from webcollect.stepwise.prompt import SYSTEM_PROMPT
            plan['production_facts'] = {'accounts_and_privacy': '离线隔离夹具',
                'narrative_generation': '原始帧生成', 'narrative_mode': 'mixed',
                'prompt_stages': {'planning': {'mode': 'model', 'description': '逐步决策',
                    'prompt': SYSTEM_PROMPT}, 'narrative': {'mode': 'template',
                    'description': '原始帧生成', 'template_version': 'actual-state-describe_change'}}}
            for name, value in (('plan.json', plan), ('catalog.json', {'mode': 'real', 'records': []}),
                                ('policy.json', {'campaign_id': 'offline'})):
                (root / name).write_text(json.dumps(value))
            registry = root / 'registry.sqlite3'
            with sqlite3.connect(registry) as con:
                con.execute('CREATE TABLE m4_campaigns(campaign_id,policy_json)')
                con.execute('INSERT INTO m4_campaigns VALUES(?,?)', ('offline', '{}'))
            ledger = SimpleNamespace(config={'mode': 'real', 'model': {'max_images': 3}}, enqueue=Mock(return_value='job'),
                get=Mock(return_value={'state': 'queued'}), finish=Mock(), heartbeat=Mock())
            collected = AsyncMock(return_value={'collection_status': 'complete', 'collected': 0})
            with patch.object(generation, 'generation_source_identity', return_value={'new.py': 'new'}), \
                 patch.object(generation, 'read_customer_history', return_value=([], history)), \
                 patch.object(generation, 'bind_formal_history', side_effect=lambda value: value), \
                 patch('webcollect.current_chain.require_plan', return_value=False), \
                 patch('webcollect.current_chain.registry_snapshot', side_effect=AssertionError('full history read')), \
                 patch('webcollect.planning.publish_plan', return_value={'tasks': []}), \
                 patch('webcollect.consumer_lifecycle.claim_job', new=AsyncMock(return_value={'id': 'job'})), \
                 patch('webcollect.collect_runtime.collect_m4', collected):
                result = asyncio.run(generation.execute(ledger, root/'plan.json', root/'catalog.json',
                    root/'output', registry, root/'policy.json'))
            collected.assert_awaited_once()
            self.assertEqual(result['collection']['collected'], 0)
            self.assertEqual(ledger.finish.call_args.args[1], 'done')

            # Resume an actual scheduler run with a different current source
            # digest. Its original schedule/cohort audit binding stays intact.
            from webcollect import admission_cohort, site_scheduler
            publication = root / 'publication.json'; publication.write_text('{}')
            batch = {'plan': str(root / 'plan.json'), 'publication': str(publication),
                     'policy': str(root / 'policy.json'), 'output': str(root / 'scheduled-capture')}
            config = {'registry': str(registry), 'max_parallel_sites': 1,
                      'max_schedule_seconds': 5,
                      'sites': [{'site_key': 'offline', 'batches': [batch]}]}
            policy = {'campaign_id': 'offline', 'max_workers': 1, 'max_domain_workers': 1}
            bindings = {batch[key]: file_sha(batch[key]) for key in ('plan', 'publication', 'policy')}
            frozen = {'schema_version': site_scheduler.VERSION + '-binding', 'config': config,
                      'input_files_sha256': bindings, 'shared_policy': policy,
                      'source_files_sha256': {'old.py': 'old'}}
            schedule = root / 'schedule'; schedule.mkdir()
            original = json.dumps(frozen)
            (schedule / 'schedule.json').write_text(original)
            scheduled = AsyncMock(return_value={'collection_status': 'finished_pending_review', 'collected': 1})
            with patch.object(site_scheduler, 'validate_schedule', return_value=(config, policy, bindings)) as validate, \
                 patch.object(site_scheduler, 'source_identity', return_value={'new.py': 'new'}), \
                 patch.object(admission_cohort, 'reserve_schedule', wraps=admission_cohort.reserve_schedule) as reserve:
                resumed = asyncio.run(site_scheduler.run_schedule(config, schedule, resume=True, collector=scheduled))
                self.assertEqual(resumed['status'], 'COLLECTED_PENDING_REVIEW')
                self.assertEqual(reserve.call_args.args[0], frozen)
                self.assertEqual((schedule / 'schedule.json').read_text(), original)
                scheduled.assert_awaited_once()
                self.assertTrue(scheduled.call_args.kwargs['resume'])
                changed = {**config, 'max_schedule_seconds': 6}
                validate.return_value = changed, policy, bindings
                with self.assertRaisesRegex(ValueError, 'Schedule/config/input binding changed'):
                    asyncio.run(site_scheduler.run_schedule(changed, schedule, resume=True, collector=scheduled))
                self.assertEqual(scheduled.await_count, 1)

            # Source changes during preflight remain audit data and do not block
            # scheduling. Browser and observation are entirely offline doubles;
            # report writing, scheduling and evidence binding run normally.
            from webcollect import preflight
            page = SimpleNamespace(goto=AsyncMock())
            context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
            browser = SimpleNamespace(version='offline', new_context=AsyncMock(return_value=context), close=AsyncMock())
            driver = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
            manager = AsyncMock(); manager.__aenter__.return_value = driver
            real_digest = preflight.digest
            source_reads = []
            def changing_source_digest(path):
                if Path(path) == Path(preflight.__file__):
                    source_reads.append(str(path))
                    return ('0' if len(source_reads) == 1 else '1') * 64
                return real_digest(path)
            async def inspect_offline(page, task, folder, samples, interval_ms, check_url):
                folder.mkdir()
                frames = [{'path': f'frame-{i}.png', 'raw_path': f'frame-{i}.json'} for i in range(samples)]
                for name in ['initial.png', 'initial.json', *[name for frame in frames for name in frame.values()]]:
                    (folder / name).write_bytes(b'offline fixture')
                record = {'task_id': task['task_id'], 'task_sha256': preflight.object_digest(task),
                          'summary': {'routing': 'NORMAL_M1'}, 'requested_probe_count': samples, 'frames': frames}
                (folder / 'result.json').write_text(json.dumps(record))
                return record
            with patch('playwright.async_api.async_playwright', return_value=manager), \
                 patch.object(preflight, 'digest', side_effect=changing_source_digest), \
                 patch.object(preflight, 'inspect_page', side_effect=inspect_offline), \
                 patch.object(preflight.asyncio, 'sleep', new=AsyncMock()):
                checked = asyncio.run(preflight.preflight_plan(root / 'plan.json', root / 'preflight'))
            report = json.loads((root / 'preflight/report.json').read_text())
            self.assertEqual(report['source_changed_during_run'], ['preflight.py'])
            self.assertEqual(report['source_files_sha256']['preflight.py'], '0' * 64)
            self.assertEqual(json.loads((root / 'preflight/source-after.json').read_text())['preflight.py'], '1' * 64)
            self.assertEqual(checked['probe_errors'], 0)
            self.assertTrue(Path(checked['scheduled_plan']).is_file())
            self.assertEqual(json.loads(Path(checked['scheduled_plan']).read_text())['tasks'], plan['tasks'])
            preflight.validate_preflight_binding(json.loads(Path(checked['scheduled_plan']).read_text()))

    def test_finalize_replaces_transient_end_with_actual_outcome(self):
        result = {'result_contract': RESULT_CONTRACT,
                  'strategy': {'id': STRATEGY_BANDED_REACT},
                  'goal': {'goal_status': 'VERIFIED'},
                  'execution': {'effective_steps': 6},
                  'end': {'goal_status': 'VERIFIED', 'end_reason': 'ready',
                          'save_eligibility': 'unresolved', 'save_status': 'unresolved'}}
        saved = finalize_strategy_result(result, save_status='collected_pending_review',
                                         eligibility='eligible')
        self.assertEqual(saved['end']['save_status'], 'collected_pending_review')
        self.assertEqual(saved['end']['save_eligibility'], 'eligible')
        self.assertEqual(saved['result_contract'], 'strategy-result')
        # The sealed session originals are never rewritten by finalization.
        self.assertEqual(result['end']['save_status'], 'unresolved')

    def test_not_saved_defaults_to_ineligible(self):
        result = {'result_contract': RESULT_CONTRACT, 'strategy': {'id': 'react'},
                  'goal': {'goal_status': 'unconfirmed'},
                  'execution': {'effective_steps': 0},
                  'end': {'goal_status': 'unconfirmed', 'end_reason': 'no_path',
                          'save_eligibility': 'unresolved', 'save_status': 'unresolved'}}
        finalized = finalize_strategy_result(result, save_status='not_saved')
        self.assertEqual(finalized['end']['save_status'], 'not_saved')
        self.assertEqual(finalized['end']['save_eligibility'], 'ineligible')


class CandidatePoolContract(unittest.TestCase):
    def test_v2_body_put_and_claim_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            from site_planner.site_pool import SitePool
            SitePool(Path(tmp) / 'pool.sqlite3', initialize=True)
            pool = CandidatePool(Path(tmp) / 'pool.sqlite3', install=True)
            proof = Path(tmp) / 'source.json'
            proof.write_text(json.dumps({'CONTROLLED': 'offline fixture'}))
            from site_planner.discovery_tools import reference
            body = {'schema_version': 'webcollect-data-candidate-2', 'candidate_kind': 'target',
                    'entry_url': 'https://example.org/', 'requested_goal': {
                        'kind': 'edit', 'entity': 'fields', 'parameters': {'quantity': 1}}}
            cid = pool.put(body, {'origin': 'codex_session', 'run_id': 'offline-core-tests',
                                  'references': [reference(proof)]})
            claim = pool.claim_next('core-test-worker', 'core/0')
            self.assertEqual(claim['candidate_id'], cid)
            self.assertEqual(claim['snapshot']['schema_version'], 'webcollect-data-candidate-2')

            # The current task-generation marker must drive the Table2 entry
            # projection. A redirect/pilot URI cannot silently replace the claim.
            from webcollect.site_pool_sync import _page, _projection_candidate, _projection_uri
            projected = {'site_uri': 'https://example.org/redirected-after-entry',
                         'workflow_proposal': {'spec': {'consumer_projection': 'table2-entry'}},
                         'candidate_binding': {
                             'candidate_id': claim['candidate_id'], 'claim_id': claim['claim_id'],
                             'version': claim['version'], 'candidate': claim['snapshot']}}
            self.assertEqual(_projection_uri(projected), body['entry_url'])
            self.assertEqual(_projection_candidate(projected), {
                'candidate_id': cid, 'claim_id': claim['claim_id'], 'version': claim['version']})

            # A Table2-only entry has no prebuilt Table1 page. Its verified
            # original claim supplies the stable page identity for synchronization.
            with pool.pool.connect() as connection:
                application_id = connection.execute(
                    'SELECT application_id FROM data_candidates WHERE candidate_id=?', (cid,)).fetchone()[0]
            only_body = {**body, 'entry_url': 'https://example.org/table2-only',
                         'requested_goal': {'kind': 'edit', 'entity': 'fields',
                                            'parameters': {'quantity': 2}}}
            only_cid, _ = pool._put_v2(only_body, {'origin': 'codex_session',
                'run_id': 'offline-core-tests', 'references': [reference(proof)]},
                application_id=application_id)
            only_claim = pool.claim_next('core-test-worker', 'core/projection-only')
            self.assertEqual(only_claim['candidate_id'], only_cid)
            projected['candidate_binding'] = {
                'candidate_id': only_cid, 'claim_id': only_claim['claim_id'],
                'version': only_claim['version'], 'candidate': only_claim['snapshot']}
            page_id, _ = _page(pool.pool, only_body['entry_url'], _projection_candidate(projected))
            self.assertEqual(page_id, only_cid)

            # Two producers race for one remaining per-application NEW slot.
            # The limit is rechecked in the same transaction as publication.
            with pool.pool.connect() as connection:
                application_id = connection.execute(
                    'SELECT application_id FROM data_candidates WHERE candidate_id=?', (cid,)).fetchone()[0]
            run_id = 'offline-core-tests/entry-batch/concurrent-limit'
            pool.pool.freeze_run(run_id, {'application_new_target': 1,
                                         'application_pending_cap': 100}, inventory=False)
            source = {'origin': 'codex_session', 'run_id': 'offline-core-tests',
                      'references': [reference(proof)]}

            def publish(index):
                candidate = {'schema_version': 'webcollect-data-candidate-2',
                             'candidate_kind': 'entry',
                             'entry_url': f'https://example.org/page-{index}',
                             'requested_goal': None}
                header = {'row_id': f'row-{index}', 'run_id': run_id, 'batch': 0,
                          'request_id': f'request-{index}', 'response_sha256': f'digest-{index}',
                          'raw_index': index}
                return CandidatePool(Path(tmp) / 'pool.sqlite3').publish_row(
                    header, candidate, source, application_id=application_id)

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(publish, (1, 2)))
            self.assertEqual(sorted(item['result'] for item in outcomes), ['NEW', 'OVER_LIMIT'])
            with pool.pool.connect() as connection:
                count = connection.execute(
                    'SELECT COUNT(*) FROM data_candidates WHERE application_id=?',
                    (application_id,)).fetchone()[0]
            # Two controlled rows plus exactly one raced NEW.
            self.assertEqual(count, 3)

    def test_seeded_producer_plan_launch_keeps_sources_and_serial_prepare(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from webcollect import site_workers
        from site_planner.entry_selection import compile_entry_exclusions, entry_is_excluded
        from site_planner.candidate_discovery import _publish_entry
        from unittest.mock import Mock
        excluded_source = {'excluded_entry_patterns': [
            r'^https://zh\.wikipedia\.org/(?:wiki|zh-cn)/(?:Category|Wikipedia):']}
        patterns = compile_entry_exclusions([excluded_source])
        self.assertTrue(entry_is_excluded('https://zh.wikipedia.org/wiki/Category%3A物理学', patterns))
        self.assertFalse(entry_is_excluded('https://zh.wikipedia.org/wiki/物理学', patterns))
        fake_pool = Mock()
        fake_pool.batch_row_identity.return_value = None
        fake_pool.record_row_conclusion.side_effect = lambda *args, **kwargs: kwargs
        header = {'row_id': 'entry-exclusion'}
        rejected = _publish_entry(fake_pool, None, 'batch', None, header,
            {'entry_url': 'https://zh.wikipedia.org/wiki/Category:物理学'}, excluded_source, {})
        self.assertEqual(rejected['reason'], 'operator_entry_exclusion')
        with patch('site_planner.producer_observation.from_pool', return_value=(
                {'landed_uri': 'https://zh.wikipedia.org/wiki/Wikipedia:首页'}, {})):
            rejected = _publish_entry(fake_pool, None, 'batch', None, header,
                {'entry_url': 'https://zh.wikipedia.org/wiki/物理学'}, excluded_source, {})
        self.assertEqual(rejected['reason'], 'operator_landing_exclusion')
        with patch('site_planner.producer_observation.from_pool', return_value=None), \
             patch('site_planner.candidate_discovery.check_entry', side_effect=AssertionError('HTTP-only publication')):
            held = _publish_entry(fake_pool, None, 'batch', None, header,
                {'entry_url': 'https://zh.wikipedia.org/wiki/物理学'}, excluded_source, {})
        self.assertEqual(held['reason'], 'rendered_observation_missing')
        fake_pool.publish_row.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proof = root / 'seed.txt'
            proof.write_text('离线种子来源')
            from webcollect.batch_core import file_sha
            seeds = [{'uri': f'https://example.org/category/{i}',
                      'reference': {'path': str(proof), 'sha256': file_sha(proof)}} for i in range(2)]
            seed_file = root / 'seeds.json'
            seed_file.write_text(json.dumps(seeds))
            site = {'id': 'site', 'host': 'example.org', 'category': 'reference'}
            scope = {key: str(root / key) for key in ('pool', 'producer_config', 'producer_db', 'history_set')}
            with patch.object(site_workers, 'load_scope', return_value=(root/'scope', scope)), \
                    patch.object(site_workers, 'CandidatePool'), \
                    patch.object(site_workers, 'resolve_sites', return_value=[site]), \
                    patch.object(site_workers, 'site_statistics', return_value={
                        'cumulative_new': 0, 'application_id': 'site', 'classification_state': 'confirmed'}), \
                    patch.object(site_workers, 'producer_sources', return_value=(seeds[0], ['example.org'])):
                plan = site_workers.producer_plan(root/'scope', ['site'], pages_per_site=3,
                                                 workers=3, seed_files=[seed_file])
                self.assertEqual([w['seeds'] for w in plan['workers']],
                                 [[seeds[0]['uri']], [seeds[1]['uri']], [seeds[0]['uri']]])
                fallback = site_workers.producer_plan(root/'scope', ['site'], pages_per_site=1, workers=1)
                self.assertEqual(fallback['workers'][0]['seeds'], [seeds[0]['uri']])
                self.assertTrue(site_workers.prepare_sites(root/'scope', ['site'])['ready'])
                seed_file.write_text(json.dumps([{**seed, **excluded_source} for seed in seeds]))
                site_workers.site_statistics.return_value = {
                    'cumulative_new': 2, 'application_id': 'site', 'classification_state': 'confirmed'}
                with patch.object(site_workers, 'entry_is_excluded', side_effect=[True, False]):
                    site_workers.CandidatePool.return_value.pool.connect.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = [
                        ('nav', 'navigation'), ('article', 'content')]
                    filtered = site_workers.producer_plan(root/'scope', ['site'], pages_per_site=3,
                        workers=1, seed_files=[seed_file])
                self.assertEqual(filtered['sites'][0]['excluded_existing'], 1)
                self.assertEqual(filtered['workers'][0]['command'][
                    filtered['workers'][0]['command'].index('--application-new-target') + 1], '4')
                self.assertEqual(json.loads(filtered['workers'][0]['command'][
                    filtered['workers'][0]['command'].index('--sources') + 1])[0]['excluded_entry_patterns'],
                    excluded_source['excluded_entry_patterns'])
            plan['log_root'] = str(root/'launch')
            with patch('webcollect.collection_startup.check', return_value={'status':'PASS'}), patch('webcollect.collection_report.producer_round',return_value={'sites':[]}) as producer_report, patch.object(site_workers.subprocess, 'Popen',
                              return_value=SimpleNamespace(pid=1, wait=lambda **kw: 0, poll=lambda:0)):
                self.assertTrue(site_workers.launch(plan)['succeeded'])
                producer_report.assert_called_once()
            saved = json.loads((root/'launch/plan.json').read_text())
            for i, worker in enumerate(saved['workers']):
                path = worker['command'][worker['command'].index('--sources') + 1]
                self.assertEqual(path, worker['sources_path'])
                self.assertEqual(json.loads(Path(path).read_text()), [seeds[i % 2]])
            proof.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'evidence missing or changed'):
                site_workers.load_seed_files([seed_file])
            from webcollect.site_failure_stop import execution_id, matches_execution_id
            original_root = root.resolve() / 'original-book'
            original_root.mkdir()
            original_book = original_root / 'producer-jobs.sqlite3'
            original_book.touch()
            original_identity = execution_id('probe', original_book, 'visit-one')
            moved_root = root.resolve() / 'moved-book'
            original_root.rename(moved_root)
            original_root.symlink_to(moved_root, target_is_directory=True)
            self.assertTrue(matches_execution_id(original_identity, 'probe', original_book, 'visit-one'))
            self.assertFalse(matches_execution_id(original_identity, 'probe', original_book, 'visit-two'))


class CliEntriesSmoke(unittest.TestCase):
    """Explicit objective files reach the consumer without executing collection."""

    def test_consumer_objective_file_binding(self):
        import hashlib
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import Mock, patch
        from webcollect import candidate_consumer as cli

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.json'; config.write_text('{}')
            objective = root / 'objective.json'
            objective.write_text('{"objective":{"description":"固定目标"}}', encoding='utf-8')
            args = ['--pool', str(root / 'pool'), 'run', '--config', str(config),
                    '--ledger', str(root / 'ledger'), '--output', str(root / 'output'),
                    '--registry', str(root / 'registry'), '--policy', str(root / 'policy'),
                    '--history-set', str(root / 'manifest'), '--worker-id', 'fixed',
                    '--request-prefix', 'fixed', '--limit', '1']
            with patch('webcollect.collection_startup.check', return_value={'status':'PASS'}), patch.object(cli, 'CandidatePool') as pool, patch.object(cli, 'BatchLedger'), \
                    patch.object(cli, 'run', new_callable=Mock) as run, patch.object(cli.asyncio, 'run', return_value={}) as execute, \
                    redirect_stdout(StringIO()):
                # Replace the async entry itself: no coroutine, probe, browser or ledger IO.
                run.side_effect = lambda *a, **kw: kw
                cli.main(args + ['--session-objective', str(objective)])
                self.assertEqual(run.call_args.kwargs['session_objective'], {
                    'path': str(objective.resolve()),
                    'sha256': hashlib.sha256(objective.read_bytes()).hexdigest()})
                self.assertEqual(cli.main(args), 0)
                self.assertIsNone(run.call_args.kwargs['session_objective'])
                # 策略1冻结：CLI缺省策略2；显式react在argparse层exit 2，
                # 未触达CandidatePool构造或任何浏览器/模型路径。
                self.assertEqual(run.call_args.kwargs['collection_strategy'], STRATEGY_STEPWISE)
                pool.reset_mock(); run.reset_mock()
                from contextlib import redirect_stderr
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as exited:
                    cli.main(args + ['--collection-strategy', 'react'])
                self.assertEqual(exited.exception.code, 2)
                pool.assert_not_called(); run.assert_not_called()
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as exited:
                    cli.main(args + ['--collection-strategy', 'screenshot_plan'])
                self.assertEqual(exited.exception.code, 2)
                pool.assert_not_called(); run.assert_not_called()
                execute.return_value = {'processed': 0, 'stop_reason': 'engineering_failure'}
                self.assertEqual(cli.main(args), 2)
                pool.reset_mock(); run.reset_mock()
                objective.write_text('not JSON')
                with self.assertRaises(json.JSONDecodeError):
                    cli.main(args + ['--session-objective', str(objective)])
                pool.assert_not_called(); run.assert_not_called()


class QCSourceAuditContract(unittest.TestCase):
    def test_source_changes_preserve_jobs_and_fingerprint_cache(self):
        from unittest.mock import Mock, patch
        from PIL import Image
        from quality_inspector import duplicates, sampling
        from webcollect.batch_core import file_sha
        from webcollect.planning import object_sha256
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); dataset = root / 'samples'; dataset.mkdir()
            image = dataset / 'frame.png'; Image.new('RGB', (16, 16), 'white').save(image)
            annotation = dataset / 'annotation.json'
            body = {'sample_id':'sample', 'task_instruction':'核对结果', 'final_result':'结果',
                    'steps':[{'step_id':1, 'page_name':'页面', 'image_path':'frame.png',
                              'ui_tree_path':'tree.json',
                              'action':{'action_type':'click', 'target_text':'查看'}}]}
            annotation.write_text(json.dumps(body)); cache = root / 'fingerprints.json'
            original_sha = duplicates.sha
            def source_sha(marker):
                return lambda path: marker if Path(path) == Path(duplicates.__file__) else original_sha(path)
            with patch.object(duplicates, 'sha', side_effect=source_sha('old-source')):
                initial = duplicates.analyze_inputs([annotation], cache=cache)
            with patch.object(duplicates, 'sha', side_effect=source_sha('new-source')), \
                    patch.object(duplicates, 'dhash', side_effect=AssertionError('cache must be reused')):
                reused = duplicates.analyze_inputs([annotation], cache=cache)
            self.assertEqual(reused['search']['cache_hits'], 1)
            self.assertEqual(initial['rows'], reused['rows'])
            body['task_instruction'] = '核对另一项结果'; annotation.write_text(json.dumps(body))
            changed = duplicates.analyze_inputs([annotation], cache=cache)
            self.assertEqual(changed['search']['cache_hits'], 0)

            profile = root / 'profile.json'; profile.write_text('{}')
            plan = {'schema_version':'webcollect-sampling-plan-1', 'state_directory':str(root / 'state'),
                    'contract_sha256':sampling.fingerprint()[1],
                    'profile':{'path':str(profile), 'sha256':file_sha(profile)},
                    'dataset':str(dataset), 'candidate_package_sha256':sampling.package_files(dataset),
                    'policy':dict(sampling.DEFAULT_POLICY),
                    'implementation_sha256':{'source':'before'}, 'producer_implementation_sha256':{'source':'before'}}
            plan['plan_sha256'] = object_sha256(plan)
            plan_path = root / 'plan.json'; plan_path.write_text(json.dumps(plan))
            ledger = Mock(path=root / 'ledger.sqlite3')
            identities = []
            ledger.enqueue.side_effect = lambda kind, payload: identities.append(payload) or object_sha256([kind,payload])
            ledger.get.return_value = {'state':'done', 'result':{'plan_file':str(plan_path)}}
            for source in ('before', 'after'):
                with patch.object(sampling, 'implementation', return_value={'source':source}), \
                        patch.object(sampling, 'producer_implementation', return_value={'source':source}):
                    self.assertEqual(sampling.prepare(ledger, dataset, root / 'out', profile=profile),
                                     {'plan_file':str(plan_path)})
            self.assertEqual(identities[0], identities[1]); ledger.claim.assert_not_called()
            self.assertNotIn('implementation', identities[0]); self.assertNotIn('producer', identities[0])
            annotation.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Candidate set changed'):
                sampling.verify_plan(plan)



if __name__ == '__main__':
    unittest.main()
