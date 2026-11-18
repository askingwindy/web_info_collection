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
                                            STRATEGY_SCREENSHOT_PLAN,
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
        self.assertEqual(tuple(STRATEGIES), ('react', 'screenshot_plan'))
        # 策略1完全冻结：新任务缺省策略2；身份表保留react供历史只读解析。
        self.assertEqual(DEFAULT_STRATEGY, STRATEGY_SCREENSHOT_PLAN)
        import webcollect.screenshot_plan as screenshot_plan_module
        from webcollect.collection_strategy import Strategy1Forbidden, select
        frozen = {'task_id': 't', 'fragment': {}, 'workflow_proposal': {'spec': {}}}
        with self.assertRaises(Strategy1Forbidden):
            freeze(frozen, STRATEGY_BANDED_REACT)
        freeze(frozen)  # freeze default stamps 策略2 for new tasks
        self.assertEqual(strategy_id(frozen), STRATEGY_SCREENSHOT_PLAN)
        self.assertIs(select(frozen), screenshot_plan_module)
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
        task = {'task_id': 't', 'fragment': {}, 'workflow_proposal': {'spec': {}}}
        freeze(task, STRATEGY_SCREENSHOT_PLAN)
        self.assertEqual(strategy_id(task), STRATEGY_SCREENSHOT_PLAN)
        from webcollect.action_stability import ACTION_STABILITY_PROTOCOL
        self.assertEqual(task['fragment']['action_stability_protocol'], ACTION_STABILITY_PROTOCOL)
        self.assertEqual(task['workflow_proposal']['spec']['action_stability_protocol'], ACTION_STABILITY_PROTOCOL)
        self.assertNotIn('plan_protocol', task['fragment'])
        # Assembling a StrategyResult for an absent-marker task keeps the
        # historical 'react' label; sealed records are never relabeled as
        # screenshot_plan by the new-task default.
        from webcollect.batch_core import file_sha
        from webcollect.collection_strategy import strategy_result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            terminal = root / 'terminal.json'
            terminal.write_text(json.dumps({'collection_ending': {}, 'goal_evidence': {}}))
            receipt = root / 'receipt.json'
            receipt.write_text(json.dumps({'terminal': {'path': str(terminal),
                                                        'sha256': file_sha(terminal)}}))
            result = strategy_result({'fragment': {}, 'workflow_proposal': {'spec': {}}},
                                     summary={'effective_steps': 0},
                                     raw_receipt={'path': str(receipt), 'sha256': file_sha(receipt)})
            self.assertEqual(result['strategy'], {'id': STRATEGY_BANDED_REACT})
        # 模板冻结与派发解析：生成期在策略冻结旁盖章模板名；执行侧
        # （collect_runtime._react_collection 同一解析函数）按标记取对应模板
        # 包的Session/chooser；历史S2任务（有策略标记、无模板标记）仍解析到
        # 单体实现，封存收据重放不受拆分影响。
        from unittest.mock import patch
        import webcollect.screenshot_plan as screenshot_plan_module
        from webcollect.plan_protocol import ENDING_POLICY as S2_ENDING_POLICY
        from webcollect.screenshot_planners import (freeze_template, select_template,
                                                    task_template_name, template_module)
        from webcollect.screenshot_templates import generic as generic_template
        from webcollect.session_core import build_url_task
        freeze_template(task, 'generic')
        self.assertEqual(task_template_name(task), 'generic')
        freeze_template(task, 'generic')  # idempotent when unchanged
        with self.assertRaisesRegex(ValueError, 'already frozen differently'):
            freeze_template(task, 'operation')
        with self.assertRaisesRegex(ValueError, 'Unknown screenshot template'):
            freeze_template({'fragment': {}}, 'no-such-template')
        s2 = build_url_task(url='https://example.org/tool', task_version='tpl-dispatch',
                            ending_policy=S2_ENDING_POLICY)
        freeze(s2, STRATEGY_SCREENSHOT_PLAN)
        freeze_template(s2, 'generic')
        module = template_module(task_template_name(s2))
        self.assertIs(module, generic_template)
        self.assertEqual(module.Session.__module__, 'webcollect.screenshot_templates.generic.session')
        self.assertEqual(module.screenshot_chooser.__module__, 'webcollect.screenshot_templates.generic.plan')
        historical_s2 = {'fragment': {'collection_strategy': {'id': STRATEGY_SCREENSHOT_PLAN}}}
        self.assertIsNone(task_template_name(historical_s2))
        self.assertIs(template_module(task_template_name(historical_s2)), screenshot_plan_module)
        # 确定性模板选择：显式站点规则 + 目标方向 + 页面结构；无模型调用。
        calculator_state = {'elements': [
            {'element_id': 'a', 'native_role': 'input', 'visible': True, 'text': '单价'},
            {'element_id': 'b', 'native_role': 'input', 'visible': True, 'text': '数量'}],
            'capture_controls': [{'element_id': 'a', 'selector': '#price'},
                                 {'element_id': 'b', 'selector': '#qty'}],
            'text_blocks': [], 'visible_text': '计算器'}
        article_state = {'elements': [
            {'element_id': 's', 'native_role': 'input', 'visible': True, 'text': ''},
            *[{'element_id': 'h%d' % index, 'native_role': 'h2', 'visible': True}
              for index in range(3)]],
            'capture_controls': [{'element_id': 's', 'selector': '#search-input'}],
            'text_blocks': [{'visible_text': '章节' + str(index) + '：' + '正文内容' * 40}
                            for index in range(3)],
            'visible_text': '词条正文' * 400}
        name, info = select_template(goal='输入单价与数量后核对计算结果', state=calculator_state)
        self.assertEqual((name, info['source']), ('operation', 'page_match'))
        self.assertEqual(info['signals']['inputs'], 2)
        name, info = select_template(goal='搜索后阅读《月食》全文正文', state=article_state)
        self.assertEqual((name, info['source']), ('long_reading', 'page_match'))
        self.assertEqual(info['signals']['search_inputs'], 1)
        # 仅站点搜索框不把阅读任务判成operation；标题/编号本身不把页面判成operation。
        name, info = select_template(goal='搜索并阅读词条正文', state=article_state)
        self.assertEqual(name, 'long_reading')
        name, info = select_template(goal='查看第3章第5节的标题与编号', state=article_state)
        self.assertEqual(name, 'long_reading')
        name, info = select_template(goal='查看第3章第5节的标题与编号', state={'elements': []})
        self.assertEqual((name, info['source']), ('generic', 'generic_fallback'))
        # 空目标按页面结构定向。
        name, info = select_template(goal=None, state=calculator_state)
        self.assertEqual(name, 'operation')
        name, info = select_template(goal=None, state=article_state)
        self.assertEqual(name, 'long_reading')
        # 已确认站点模板优先；confirmed generic 不覆盖明确的结构匹配。
        with patch('webcollect.screenshot_planners.confirmed_templates', return_value=['operation']):
            name, info = select_template(pool=object(), application_id='app-1',
                                         goal='输入数量后核对计算结果', state=calculator_state)
            self.assertEqual((name, info['source']), ('operation', 'confirmed_site'))
            name, info = select_template(pool=object(), application_id='app-1',
                                         goal='搜索后阅读《月食》全文正文', state=article_state)
            self.assertEqual((name, info['source']), ('long_reading', 'confirmed_site_mismatch'))
            self.assertEqual(info['confirmed'], ['operation'])
            name, info = select_template(pool=object(), application_id='app-1',
                                         goal='随便看看', state={'elements': []})
            self.assertEqual((name, info['source']), ('generic', 'confirmed_site_mismatch'))
        with patch('webcollect.screenshot_planners.confirmed_templates', return_value=['generic']):
            name, info = select_template(goal='输入数量后核对计算结果', state=calculator_state)
            self.assertEqual((name, info['source']), ('operation', 'page_match'))
            name, info = select_template(pool=object(), application_id='app-2',
                                         goal='随便看看', state={'elements': []})
            self.assertEqual((name, info['source']), ('generic', 'confirmed_site'))
        # 显式 Muxtly 全站规则优先于目标、页面结构和已确认模板；中英文、
        # 分类或阅读状页面都固定 operation，其它站点仍走原有路由。
        for url in ('https://muxtly.com/zh-CN/calculators/baby-percentile',
                    'https://www.muxtly.com/en/tools/area-converter',
                    'https://muxtly.com/zh-CN/category/health'):
            with self.subTest(url=url):
                name, info = select_template(goal='搜索后阅读正文', state={**article_state, 'url': url})
                self.assertEqual((name, info['source']), ('operation', 'site_rule'))
                self.assertIn('Muxtly全站', info['reason'])
        name, info = select_template(goal='搜索后阅读正文',
                                     state={**article_state, 'url': 'https://example.org/article'})
        self.assertEqual((name, info['source']), ('long_reading', 'page_match'))
        name, _ = select_template(goal='搜索后阅读正文',
                                  state={**article_state, 'url': 'https://muxtly.com.evil.example/article'})
        self.assertEqual(name, 'long_reading')
        with patch('webcollect.screenshot_planners.confirmed_templates', return_value=['long_reading']):
            name, info = select_template(pool=object(), application_id='app-mux', goal='阅读正文',
                                         state={**article_state, 'url': 'https://muxtly.com/zh-CN/article'})
            self.assertEqual((name, info['source']), ('operation', 'site_rule'))

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
                self.assertEqual(run.call_args.kwargs['collection_strategy'], STRATEGY_SCREENSHOT_PLAN)
                pool.reset_mock(); run.reset_mock()
                from contextlib import redirect_stderr
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as exited:
                    cli.main(args + ['--collection-strategy', 'react'])
                self.assertEqual(exited.exception.code, 2)
                pool.assert_not_called(); run.assert_not_called()
                execute.return_value = {'processed': 0, 'stop_reason': 'engineering_failure'}
                self.assertEqual(cli.main(args), 2)
                pool.reset_mock(); run.reset_mock()
                objective.write_text('not JSON')
                with self.assertRaises(json.JSONDecodeError):
                    cli.main(args + ['--session-objective', str(objective)])
                pool.assert_not_called(); run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
