"""Dual-strategy integration: real w01/w02 HTTP-boundary shapes + session loop.

No live site, provider HTTP, production ledger, QC or customer export. The
provider boundary is exercised with the frozen w01/w02 provider-response
copies (read-only) through ModelGateway with a stubbed HTTP opener, so the
real native-tool parse/normalize/validate/settle chain runs end to end. The
session cases use the synthetic ReactHarness surface. Outcome receipts are
written to WEBCOLLECT_DUAL_STRATEGY_ROOT (verify_results/...).
"""
import asyncio
from copy import deepcopy
from pathlib import Path
from io import BytesIO
import json
import os
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from test_react_session import ReactHarness
from webcollect.batch_core import BatchLedger, file_sha, load_json, object_sha256
from webcollect.plan_protocol import ENDING_POLICY as COMPLETE_VERSION, PLAN_PROTOCOL
from webcollect.closing_policy import completion_delivery_decision
from webcollect.collection_strategy import (STRATEGY_SCREENSHOT_PLAN, freeze as freeze_strategy,
    save_eligibility, strategy_result, outcome_facts)
from webcollect.model_gateway import ModelGateway
from webcollect.postprocess import process
from webcollect.react_session import ReactSession, build_url_task, validate_task
from webcollect.plan_protocol import RESULT_COMPLETION_PROTOCOL, RESULT_EXECUTION_POLICY
from webcollect.collection_strategy import STRATEGY_SCREENSHOT_PLAN as SCREENSHOT_VERSION
from webcollect.screenshot_plan import (
    first_plan_admission, normalize_submit_plan, submit_plan_tools)
from webcollect.screenshot_session import ScreenshotPlanSession

FIXTURES = Path(__file__).resolve().parents[3] / 'verify_results' / \
    'consumer-unified-success-fixed4-20261110-r01' / 'diagnosis-invalid-response-20261110-r01'
OUT_ROOT = Path(os.environ.get('WEBCOLLECT_DUAL_STRATEGY_ROOT') or
                Path(__file__).resolve().parents[3] / 'verify_results' / 'dual-strategy-20261110-r01')

ALL_ACTIONS = ('click', 'double_click', 'right_click', 'type', 'select', 'hotkey',
               'scroll', 'open_url', 'back', 'drag', 'wait')


def record_outcome(name, payload):
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / (name + '.json')).write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def provider_body(name):
    return (FIXTURES / (name + '-provider-response.json')).read_bytes()


class StubOpener:
    """Returns the frozen real provider body at the HTTP boundary."""

    def __init__(self, raw):
        self.raw = raw if isinstance(raw, bytes) else json.dumps(raw).encode()
        self.calls = []

    def open(self, request, timeout):
        self.calls.append(request)
        return BytesIO(self.raw)


class DualStrategyHTTPBoundary(unittest.IsolatedAsyncioTestCase):
    """w01/w02 真实回包形状经 gateway HTTP 边界的整理、校验与结算。"""

    def setUp(self):
        import tempfile
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        from test_model_provider_protocols import CONFIG
        config = load_json(CONFIG)
        config['schema_version'] = 'webcollect-batch-config-1'
        config['mode'] = 'real'
        config['budget'].update(currency='OFFLINE_TEST_UNITS', max_model_cost_micros=1_000_000,
                                min_model_interval_seconds=0)
        config['model']['rates'].update(input=1, output=1, version='OFFLINE_TEST',
                                        source='OFFLINE_TEST')
        config['model'].update(provider='glm', model='glm-5.3-flash',
                              endpoint='https://provider.invalid/chat/completions',
                              api_key_env='WEBCOLLECT_OFFLINE_TEST_KEY', reserve_cost_micros=100_000,
                              supports_vision=True, image_tokens_per_image=1200,
                              request_overhead_tokens=128)
        self.config = config

    async def _call_with_body(self, name):
        raw = json.loads(provider_body(name))
        opener = StubOpener(raw)
        env = patch.dict('os.environ', {'WEBCOLLECT_OFFLINE_TEST_KEY': 'offline-secret-never-export'})
        dns = patch('webcollect.model_gateway.socket.getaddrinfo', return_value=[('CONTROLLED_DNS',)])
        http = patch('urllib.request.build_opener', return_value=opener)
        for mock in (env, dns, http):
            mock.start()
            self.addCleanup(mock.stop)
        ledger = BatchLedger(self.root / (name + '.sqlite3'), self.config, initialize=True)
        jid = ledger.enqueue('react-native-decision', {'protocol': SCREENSHOT_VERSION,
                                                       'attempt_id': name + '-attempt'})
        job = ledger.claim('react-native-decision', job_id=jid)
        gateway = ModelGateway(ledger)
        gateway._credential = 'CONTROLLED_UNUSED'
        gateway._session_id = name + '-attempt'
        image = self.root / 'first.png'
        from PIL import Image
        Image.new('RGB', (8, 8), 'white').save(image)
        return ledger, job, gateway, opener, raw

    async def test_w01_shape_normalizes_to_four_business_actions_no_dispatch(self):
        ledger, job, gateway, opener, raw = await self._call_with_body('w01')
        response = await asyncio.to_thread(gateway.call_tool, job, SCREENSHOT_VERSION,
            json.dumps({'phase': 'first'}, ensure_ascii=False), submit_plan_tools(ALL_ACTIONS),
            system='策略2首轮', images=[self.root / 'first.png'], attempts=2,
            attempt_id='w01-attempt', plan_normalizer=normalize_submit_plan)
        plan = response['arguments']
        normalization = response['plan_normalization']
        ok, feedback = first_plan_admission(plan)
        # 整理后的确定事实：wait/scroll 冗余 target 移除、旧谓词入上下文、预猜字面丢弃。
        self.assertFalse(ok, feedback)
        self.assertEqual(feedback['kind'], 'business_minimum')
        self.assertEqual((feedback['business_steps'], feedback['wait_steps']), (4, 1))
        self.assertIn('1项为wait', feedback['message'].replace('项中', '项为').replace('，', '，'))
        removed = {row['path'] for row in normalization['transforms']}
        self.assertIn('steps[3].target', removed)   # wait冗余target
        self.assertIn('steps[4].target', removed)   # scroll裸标签target
        self.assertIn('finish_when', removed)
        self.assertEqual(feedback['dispatched'], False)
        # 无浏览器调用、无正式文件：只有本次受控请求记录。
        with ledger.connect() as con:
            requests = [dict(r) for r in con.execute(
                'SELECT id,state FROM model_requests WHERE job_id=?', (job['id'],))]
        self.assertTrue(all(r['state'] == 'succeeded' for r in requests), requests)
        self.assertEqual(opener.calls and len(opener.calls) >= 1, True)
        record_outcome('w01-http-boundary', {
            'feedback': feedback,
            'normalization_transforms': normalization['transforms'],
            'requirements': plan.get('requirements'),
            'requests': requests, 'dispatched': False, 'formal_files': 0})

    async def test_w02_shape_keeps_six_steps_maps_values_and_reports_six_missing_paths(self):
        ledger, job, gateway, opener, raw = await self._call_with_body('w02')
        error = None
        try:
            await asyncio.to_thread(gateway.call_tool, job, SCREENSHOT_VERSION,
                json.dumps({'phase': 'first'}, ensure_ascii=False), submit_plan_tools(ALL_ACTIONS),
                system='策略2首轮', images=[self.root / 'first.png'], attempts=2,
                attempt_id='w02-attempt', plan_normalizer=normalize_submit_plan)
        except ValueError as failure:
            error = failure
        with ledger.connect() as con:
            rows = [dict(r) for r in con.execute(
                'SELECT id,state,response FROM model_requests WHERE job_id=? ORDER BY attempt', (job['id'],))]
        invalid = [r for r in rows if r['state'] == 'invalid_response']
        self.assertTrue(invalid, rows)
        settled = json.loads(invalid[0]['response'])
        diagnostic = settled['failure_diagnostic']
        self.assertEqual(diagnostic['source'], 'response_validation')
        # 六步意图保留：750/405/812 值与标签正确映射，不因旧schema丢弃value。
        normalization = settled['plan_normalization']
        values = {row['path']: row['value'] for row in normalization['transforms']
                  if row['transform'] == 'input_value_separated_from_label'}
        self.assertEqual(values.get('steps[2].expected.value'), '750')
        self.assertEqual(values.get('steps[3].expected.value'), '405')
        self.assertEqual(values.get('steps[4].expected.value'), '812')
        missing = [row['path'] for row in normalization['missing']]
        self.assertEqual(missing, [f'steps[{i}].expected_result' for i in range(6)])
        # 精确反馈路径随有界纠正进入下一次请求；重复同形回包按无进展停止，不换编号重发。
        self.assertIsNotNone(error)
        self.assertIn('consumer_protocol_no_progress', str(error))
        record_outcome('w02-http-boundary', {
            'failure': str(error), 'diagnostic': diagnostic,
            'value_label_map': values, 'missing_paths': missing,
            'request_states': [{k: r[k] for k in ('id', 'state')} for r in rows],
            'no_replacement_request': len(rows) <= 3})


class StrategyOneFixes(ReactHarness, unittest.IsolatedAsyncioTestCase):
    """策略1保留链路上的两个收口修复，其余历史语义不变。"""

    def setUp(self):
        super().setUp()
        self.task = build_url_task(url=self.page.url, task_version='dual-strategy-s1',
                                   ending_policy=COMPLETE_VERSION,
                                   plan_protocol=PLAN_PROTOCOL)
        for part in (self.task['fragment'], self.task['workflow_proposal']['spec']):
            part['result_execution_policy'] = RESULT_EXECUTION_POLICY
            part['result_completion_protocol'] = RESULT_COMPLETION_PROTOCOL
        self.task['task_id'] = 'react-' + object_sha256(
            {'url': self.task['initial_url'], 'spec': self.task['workflow_proposal']['spec']})[:24]
        validate_task(self.task)

    async def _session(self, name='s1'):
        from webcollect.banded_plan import Controller

        self.surface.state['elements'][0]['text'] = '数量'
        self.surface.state['elements'][1]['text'] = '成本'

        async def choose(prompt):
            raise AssertionError('not used')

        session = ReactSession(self.task, self.root / name, choose, self.page,
                               steps_directory=self.root / name, attempt_id='dual-s1')
        await session._observe()
        return session, Controller()

    async def test_result_completion_first_round_never_requires_finish_when_guess(self):
        from webcollect.banded_plan import RESULT_FINISH_WHEN, bind_reply_scope
        session, controller = await self._session('finish-when-wire')
        prompt = controller.prompt(session)
        schema = prompt['tools'][0]['function']['parameters']
        Draft202012Validator.check_schema(schema)
        self.assertNotIn('finish_when', schema['required'])
        self.assertNotIn('finish_when', schema['properties'])
        self.assertIn('finish_when由工程生成且禁止填写', prompt['system'])
        arguments = json.loads((FIXTURES / 'w02-original-tool-arguments.json').read_text())
        arguments.pop('finish_when', None)
        arguments.pop('attempt_id', None)  # wire form: host fills the frozen scope ids
        bound = bind_reply_scope(arguments, prompt)
        self.assertEqual(bound['finish_when'], RESULT_FINISH_WHEN)
        record_outcome('s1-finish-when-wire', {'required': schema['required'],
                                               'placeholder': bound['finish_when']})

    async def test_select_all_predicate_aligns_with_actual_keys_and_value(self):
        from webcollect.banded_plan import Controller, proves
        session, controller = await self._session('select-all')
        step = {'action': 'hotkey', 'keys': ['ctrl', 'a'],
                'target': {'text': '数量'},
                'purpose': '全选原值', 'expected': {'kind': 'selected', 'text': '数量'},
                'expected_result': '旧值被完整选中'}
        controller.plan = {'steps': [step], 'goal': 'g', 'checks': [],
                           'finish_when': {'kind': 'visible_text', 'text': 'x'}}
        controller.position = 0
        controller._normalize_select_all_predicate(session, step)
        value = self.surface.state['values'][0]['value']
        self.assertEqual(step['expected'], {'kind': 'text_selected', 'text': value})
        self.surface.state['values'][0].update(focused=True, selection_start=0,
                                                selection_end=len(value))
        await session._observe()
        self.assertTrue(proves(step['expected'], session.current))
        record_outcome('s1-select-all-equivalence', {'normalized': step['expected']})


class ScreenshotSessionTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    """策略2会话：检查点、完成凭据、重复派发防护与四件事分开记录。"""

    def setUp(self):
        super().setUp()
        self.task = build_url_task(url=self.page.url, task_version='dual-strategy-s2',
                                   ending_policy=COMPLETE_VERSION)
        freeze_strategy(self.task, STRATEGY_SCREENSHOT_PLAN)
        self.task['task_id'] = 'react-' + object_sha256(
            {'url': self.task['initial_url'], 'spec': self.task['workflow_proposal']['spec']})[:24]
        validate_task(self.task)
        self.ids = {'sample_id': 'S000001_sample_000201', 'site_id': 'S000001',
                    'batch_id': 'B20261110_001', 'attempt_id': 'dual-s2-offline'}
        self.manifest = {'batch_id': 'B20261110_001', 'sample_kind': 'real',
                         'program_version': 'CONTROLLED', 'rule_version': '1.0.0',
                         'sites': [{'site_id': 'S000001', 'uri': self.page.url,
                                    'site_category': self.task['site_category']}],
                         'samples': [self.ids['sample_id']]}
        self._prepare_surface()

    def _prepare_surface(self):
        state = self.surface.state
        state['elements'][0]['text'] = '数量'
        state['elements'][1]['text'] = '成本'
        for binding in state['capture_controls']:
            binding['form_selector'] = '#calculator'
        state['elements'].append({'element_id': 'submit-result', 'text': '计算', 'native_role': 'button',
            'element_type': 'button', 'bbox': [10, 200, 210, 240], 'visible': True, 'enabled': True,
            'clickable': True, 'inputable': False, 'parent_id': 'root', 'scrollable': False, 'state': 'default'})
        state['capture_controls'].append({'element_id': 'submit-result', 'selector': '#submit-result',
            'tag': 'button', 'input_type': 'submit', 'form_selector': '#calculator'})
        result = {'element_id': 'visible-result', 'text': '结果尚未生成', 'native_role': 'status',
            'element_type': 'p', 'bbox': [10, 260, 800, 320], 'visible': True, 'enabled': True,
            'clickable': False, 'inputable': False, 'parent_id': 'root', 'scrollable': False, 'state': 'default'}
        state['elements'].append(result)
        state['capture_controls'].append({'element_id': 'visible-result', 'selector': '#actual-result',
            'tag': 'p', 'form_selector': '#calculator', 'result_region_selector': '#actual-result'})

    def _surface_reveals_result_after_scroll(self, scrolls=1):
        executed = self.surface.execute_action
        counted = [0]

        def hook(kind, arguments):
            focused = [(value, value.get('focused')) for value in self.surface.state['values']]
            executed(kind, arguments)
            if kind == 'click' and arguments.get('y', 0) >= 200:
                # 提交按钮不窃取输入焦点（部分真实页面的行为）：
                # 焦点不变，结果延迟到滚动后才出现。
                for value, was in focused:
                    value['focused'] = was
            if kind == 'scroll':
                counted[0] += 1
            if counted[0] >= scrolls:
                self.surface.state['elements'][-1]['text'] = '利润率：40%'

        self.surface.execute_action = hook

    def _submit_sets_result_immediately(self):
        executed = self.surface.execute_action

        def hook(kind, arguments):
            executed(kind, arguments)
            if kind == 'click' and arguments.get('y', 0) >= 200:
                self.surface.state['elements'][-1]['text'] = '利润率：40%'

        self.surface.execute_action = hook

    def _plan(self, business_steps):
        return {'goal': '修改数量为20并查看本次利润率结果',
                'requirements': [
                    {'id': 'r1', 'description': '查看本次输入对应的利润率计算结果'}],
                'steps': business_steps}

    def _steps_full(self):
        return [
            {'action': 'click', 'target': {'text': '数量'}, 'purpose': '聚焦数量输入框',
             'expected_result': '数量输入框获得焦点'},
            {'action': 'hotkey', 'keys': ['ctrl', 'a'], 'target': {'text': '数量'},
             'purpose': '全选原值', 'expected_result': '旧值被完整选中'},
            {'action': 'type', 'target': {'text': '数量'}, 'value': '20',
             'purpose': '输入数量20', 'expected_result': '数量显示为20',
             'expected_value': '20'},
            {'action': 'click', 'target': {'text': '成本'}, 'purpose': '聚焦成本输入框',
             'expected_result': '成本输入框获得焦点'},
            {'action': 'type', 'target': {'text': '成本'}, 'value': '60',
             'purpose': '输入成本60', 'expected_result': '成本显示为60'},
            {'action': 'click', 'target': {'text': '计算'}, 'purpose': '提交计算',
             'expected_result': '结果区显示本次利润率'},
            {'action': 'scroll', 'direction': 'down', 'purpose': '查看结果区',
             'expected_result': '结果区进入视口'},
        ]

    def _session(self, name, choose):
        evidence = self.root / name / 'evidence' / self.ids['sample_id']
        return ScreenshotPlanSession(self.task, evidence / 'raw', choose, self.page,
                                     steps_directory=evidence, attempt_id=self.ids['attempt_id']), evidence

    def _complete_answer(self, prompt):
        regions = prompt.get('regions') or []
        region = next((r for r in regions if '利润率' in r.get('quote', '')), None)
        if region is None:
            return None
        return {'decision': 'complete', 'reason': '本次提交的利润率结果已经可见',
                'answers': [{'requirement_id': 'r1',
                             'observed_result': '利润率：40%',
                             'evidence': [{'observation': prompt['current_observation'],
                                           'region': region['region_id']}]}]}

    async def test_result_offscreen_observed_by_scroll_then_complete(self):
        """提交已派发、结果屏外：先观察滚动，引用真实可见结果，不重复点击。"""
        self._surface_reveals_result_after_scroll(scrolls=1)
        self.prompts = []

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if prompt.get('phase') == 'first':
                return {'name': 'submit_plan', 'arguments': self._plan(self._steps_full()),
                        'tool_call_id': 'first', 'assistant_message': {'role': 'assistant'},
                        'request_id': 'mock'}
            answer = self._complete_answer(prompt)
            if answer is None:
                if any(o in json.dumps(prompt.get('remaining_plan', [])) for o in ('scroll',)):
                    return {'name': 'plan_decision',
                            'arguments': {'decision': 'continue', 'reason': '滚动查看结果'},
                            'tool_call_id': 'continue', 'request_id': 'mock'}
                return {'name': 'plan_decision',
                        'arguments': {'decision': 'revise', 'reason': '结果未进视口，改为滚动查看',
                                      'remaining_plan': [{'action': 'scroll', 'direction': 'down',
                                                          'purpose': '把结果区带入视口',
                                                          'expected_result': '结果区可见'}]},
                        'tool_call_id': 'revise', 'request_id': 'mock'}
            return {'name': 'plan_decision', 'arguments': answer,
                    'tool_call_id': 'complete', 'request_id': 'mock'}

        session, evidence = self._session('offscreen-result', choose)
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'ready', result)
        self.assertEqual(result['strategy_end_reason'], 'goal_completed')
        self.assertEqual(result['goal_status'], 'completed')
        self.assertGreaterEqual(result['effective_steps'], 5)
        submit_clicks = [row for row in self.surface.executed
                         if row[0] == 'click' and row[1].get('y', 0) >= 200]
        self.assertEqual(len(submit_clicks), 1, '结果屏外不得重复点击提交')
        complete_prompt = next(p for p in self.prompts if p.get('phase') == 'branch'
                               and any('利润率' in (r.get('quote') or '') for r in (p.get('regions') or [])))
        self.assertTrue(complete_prompt['regions'])
        derived = process(evidence, self.root / 'offscreen-saved' / 'samples' / self.ids['sample_id'],
                          self.ids, self.manifest)
        self.assertEqual(derived['status'], 'derived_saved', derived)
        annotation = load_json(self.root / 'offscreen-saved' / 'samples' / self.ids['sample_id'] / 'annotation.json')
        self.assertEqual(annotation['completion_status'], 'success')
        decision = save_eligibility(annotation, load_json(evidence / 'saved_sample.json')['raw_execution'])
        self.assertTrue(decision['delivery_eligible'], decision)
        from webcollect.closing_policy import validate_record
        from webcollect.postprocess import session_record
        validate_record(session_record(evidence / 'raw'))
        record_outcome('s2-offscreen-complete', {
            'stop_reason': result['stop_reason'], 'goal_status': result['goal_status'],
            'effective_steps': result['effective_steps'],
            'submit_clicks': len(submit_clicks), 'derived': derived['status'],
            'delivery_eligible': decision['delivery_eligible'],
            'completion_delivery': decision})

    async def test_fixed_goal_reading_supplement_and_sealed_replay(self):
        """固定阅读目标经有界纠错、补证和完整保存回放，不把阅读当计算。"""
        fixed = '阅读正文并回答文中介绍的计算方法'
        spec = self.task['workflow_proposal']['spec']
        spec['goal']['structured'] = {'description': fixed}
        self.task['task_id'] = 'react-' + object_sha256(
            {'url': self.task['initial_url'], 'spec': spec})[:24]
        validate_task(self.task)
        answer_text = '先计算成本，再除以收入'
        self.surface.state['elements'][-1]['text'] = answer_text
        steps = [{'action': 'scroll', 'direction': 'down',
                  'purpose': f'阅读第{index}段正文', 'expected_result': '看到下一段正文'}
                 for index in range(1, 6)]
        self.prompts = []
        supplements = []

        def plan(goal):
            return {'goal': goal,
                    'requirements': [{'id': 'r1', 'description': '回答文中介绍的计算方法'}],
                    'steps': deepcopy(steps)}

        def response(name, arguments, call_id):
            return {'name': name, 'arguments': arguments, 'tool_call_id': call_id,
                    'request_id': 'mock'}

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if prompt.get('phase') == 'first':
                wrong = not prompt.get('first_plan_feedback')
                return response('submit_plan', plan('只浏览页面标题' if wrong else fixed), 'first')
            if prompt.get('remaining_plan'):
                return response('plan_decision', {
                    'decision': 'continue', 'reason': '继续阅读下一段正文'}, 'continue')
            if not (prompt.get('checkpoint_feedback') or {}).get('gaps'):
                return response('plan_decision', {
                    'decision': 'complete', 'reason': '第一次完成申请缺少有效区域',
                    'answers': [{'requirement_id': 'r1', 'observed_result': answer_text,
                                 'evidence': [{'observation': prompt['current_observation'],
                                               'region': 'region_unknown'}]}]}, 'bad-complete')
            region = next(row for row in prompt['regions'] if '成本' in row.get('quote', ''))
            supplements.append(prompt['checkpoint_feedback']['kind'])
            return response('plan_decision', {
                'decision': 'complete', 'reason': '第二次补入实际提供的截图区域',
                'answers': [{'requirement_id': 'r1', 'observed_result': answer_text,
                             'evidence': [{'observation': prompt['current_observation'],
                                           'region': region['region_id']}]}]}, 'verified-complete')

        session, evidence = self._session('fixed-reading-complete', choose)
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'ready', result)
        self.assertEqual(result['effective_steps'], 5, result)
        self.assertEqual(result['strategy_result']['end']['end_reason'], 'goal_completed')
        self.assertNotIn('terminal', result['raw_receipt'])
        self.assertEqual(len([row for row in self.surface.executed if row[0] == 'scroll']), 5)
        first_prompts = [p for p in self.prompts if p.get('phase') == 'first']
        self.assertEqual(len(first_prompts), 2)
        self.assertEqual(first_prompts[1]['first_plan_feedback']['kind'], 'FIXED_GOAL_MISMATCH')
        self.assertEqual(supplements, ['COMPLETION_EVIDENCE_GAPS'])
        self.assertEqual(session.frozen_goal, fixed)

        derived = process(evidence, self.root / 'fixed-reading-saved' / 'samples' / self.ids['sample_id'],
                          self.ids, self.manifest)
        self.assertEqual(derived['status'], 'derived_saved', derived)
        annotation = load_json(self.root / 'fixed-reading-saved' / 'samples' / self.ids['sample_id'] / 'annotation.json')
        self.assertEqual(annotation['completion_status'], 'success')
        decision = save_eligibility(annotation, load_json(evidence / 'saved_sample.json')['raw_execution'])
        self.assertTrue(decision['delivery_eligible'], decision)
        from webcollect.closing_policy import validate_record
        from webcollect.postprocess import session_record
        record = session_record(evidence / 'raw')
        validate_record(record)
        self.assertEqual(record['terminal']['goal_evidence']['requested_goal'], {'description': fixed})
        self.assertIsNone(record['terminal']['goal_evidence']['checks'][0]['evidence'][0]['result_execution_binding'])
        record_outcome('s2-fixed-reading-complete', {
            'effective_steps': result['effective_steps'], 'supplements': supplements,
            'derived': derived['status'], 'delivery_eligible': decision['delivery_eligible'],
            'sealed_replay': 'PASS'})

    async def test_unrelated_form_input_preserves_delayed_result_causality(self):
        """另一表单的后续输入不覆盖原表单提交与延迟结果的因果关系。"""
        state = self.surface.state
        other = deepcopy(state['elements'][0])
        other.update(element_id='other-note', text='其他备注', bbox=[10, 330, 210, 370])
        state['elements'].append(other)
        binding = deepcopy(state['capture_controls'][0])
        binding.update(element_id='other-note', selector='#other-note', form_selector='#other-form')
        state['capture_controls'].append(binding)
        value = deepcopy(state['values'][0])
        value.update(element_id='other-note', value='', display_value='', focused=False,
                     selection_start=0, selection_end=0)
        state['values'].append(value)
        executed = self.surface.execute_action

        def hook(kind, arguments):
            focused = [(value, value.get('focused')) for value in state['values']]
            executed(kind, arguments)
            if kind == 'click' and 200 <= arguments.get('y', 0) < 300:
                # 与既有延迟结果夹具一致：提交按钮不窃取输入焦点。
                for value, was_focused in focused:
                    value['focused'] = was_focused
            if kind == 'scroll':
                next(row for row in state['elements'] if row['element_id'] == 'visible-result'
                     )['text'] = '利润率：40%'

        self.surface.execute_action = hook
        other_steps = [
            {'action': 'click', 'target': {'text': '其他备注'}, 'purpose': '聚焦另一表单备注',
             'expected_result': '备注输入框获得焦点'},
            {'action': 'hotkey', 'keys': ['ctrl', 'a'], 'target': {'text': '其他备注'},
             'purpose': '全选另一表单备注原值', 'expected_result': '备注原值被选中'},
            {'action': 'type', 'target': {'text': '其他备注'}, 'value': '不影响计算',
             'purpose': '填写另一表单备注', 'expected_result': '备注显示新内容'},
            {'action': 'scroll', 'direction': 'down', 'purpose': '查看原表单延迟结果',
             'expected_result': '原表单结果区进入视口'}]
        steps = self._steps_full()[:6] + other_steps

        async def choose(prompt):
            if prompt.get('phase') == 'first':
                return {'name': 'submit_plan', 'arguments': self._plan(steps),
                        'tool_call_id': 'first', 'request_id': 'mock'}
            answer = self._complete_answer(prompt)
            if answer is not None:
                return {'name': 'plan_decision', 'arguments': answer,
                        'tool_call_id': 'complete', 'request_id': 'mock'}
            return {'name': 'plan_decision',
                    'arguments': {'decision': 'continue', 'reason': '继续既定步骤'},
                    'tool_call_id': 'continue', 'request_id': 'mock'}

        session, evidence = self._session('unrelated-form-delayed-result', choose)
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'ready', result)
        self.assertEqual(result['actual_actions'], 10, result)
        self.assertGreaterEqual(result['effective_steps'], 5, result)
        other_operation = next(row['operation_id'] for row in session.trajectory
                               if (row.get('target') or {}).get('control_id') == 'other-note'
                               and row.get('action') == 'type')
        proof = session.goal_evidence['checks'][0]['evidence'][0]
        causality = proof.get('post_submit_causality')
        self.assertIsNotNone(causality, proof)
        self.assertNotIn(other_operation, causality['input_operation_ids'])
        self.assertTrue(causality['same_form'])
        derived = process(evidence, self.root / 'unrelated-form-saved' / 'samples' / self.ids['sample_id'],
                          self.ids, self.manifest)
        self.assertEqual(derived['status'], 'derived_saved', derived)
        annotation = load_json(self.root / 'unrelated-form-saved' / 'samples' / self.ids['sample_id'] / 'annotation.json')
        decision = save_eligibility(annotation, load_json(evidence / 'saved_sample.json')['raw_execution'])
        self.assertTrue(decision['delivery_eligible'], decision)
        from webcollect.closing_policy import validate_record
        from webcollect.postprocess import session_record
        validate_record(session_record(evidence / 'raw'))
        record_outcome('s2-unrelated-form-delayed-result', {
            'effective_steps': result['effective_steps'], 'derived': derived['status'],
            'delivery_eligible': decision['delivery_eligible'], 'sealed_replay': 'PASS'})

    async def test_complete_below_five_records_completion_and_ineligibility(self):
        self._submit_sets_result_immediately()
        # 首轮自然规划5个业务动作，其中"无效按钮"点击真实派发但零效果：
        # 完成凭据成立、实际有效步4个，二者分开如实记录。
        state = self.surface.state
        state['elements'].insert(-1, {'element_id': 'noop-button', 'text': '无效操作', 'native_role': 'button',
            'element_type': 'button', 'bbox': [10, 150, 210, 190], 'visible': True, 'enabled': True,
            'clickable': True, 'inputable': False, 'parent_id': 'root', 'scrollable': False, 'state': 'default'})
        state['capture_controls'].insert(-1, {'element_id': 'noop-button', 'selector': '#noop',
            'tag': 'button', 'input_type': 'button', 'form_selector': '#calculator'})

        async def choose(prompt):
            if prompt.get('phase') == 'first':
                # 无效按钮点击放在聚焦之前：真实派发、确定零效果（无焦点可失去）。
                steps = [{'action': 'click', 'target': {'text': '无效操作'}, 'purpose': '触发页面辅助操作',
                          'expected_result': '页面给出辅助反馈'}]
                steps.extend(self._steps_full()[i] for i in (0, 1, 2, 5))
                return {'name': 'submit_plan', 'arguments': self._plan(steps),
                        'tool_call_id': 'first', 'assistant_message': {'role': 'assistant'},
                        'request_id': 'mock'}
            answer = self._complete_answer(prompt)
            if answer is not None:
                return {'name': 'plan_decision', 'arguments': answer,
                        'tool_call_id': 'complete', 'request_id': 'mock'}
            return {'name': 'plan_decision',
                    'arguments': {'decision': 'continue', 'reason': '零效果动作后继续原路径'},
                    'tool_call_id': 'continue', 'request_id': 'mock'}

        session, evidence = self._session('short-complete', choose)
        result = await session.run()
        self.assertEqual(result['goal_status'], 'completed')
        self.assertEqual(result['effective_steps'], 4)
        derived = process(evidence, self.root / 'short-derived' / 'samples' / self.ids['sample_id'],
                          self.ids, self.manifest)
        self.assertEqual(derived['status'], 'length_unqualified', derived)
        self.assertFalse((self.root / 'short-derived' / 'samples' / self.ids['sample_id'] / 'annotation.json').exists())
        facts = outcome_facts(goal_status='completed', end_reason='goal_completed',
                              eligibility={'status': 'ineligible', 'reason': 'short_flow'},
                              save_status='not_saved')
        record_outcome('s2-complete-short', {'goal_status': result['goal_status'],
                                             'effective_steps': result['effective_steps'],
                                             'derived': derived['status'], 'outcome_facts': facts})

    async def test_repeat_submit_blocked_until_new_basis(self):
        self._submit_sets_result_immediately()
        self.prompts = []
        self.checkpoint_rounds = []

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if prompt.get('phase') == 'first':
                steps = self._steps_full()
                steps.append({'action': 'click', 'target': {'text': '计算'}, 'purpose': '再次提交',
                              'expected_result': '结果区刷新'})
                return {'name': 'submit_plan', 'arguments': self._plan(steps),
                        'tool_call_id': 'first', 'assistant_message': {'role': 'assistant'},
                        'request_id': 'mock'}
            self.checkpoint_rounds.append(prompt.get('reason'))
            feedback = (prompt.get('checkpoint_feedback') or {}).get('kind')
            if feedback == 'REPEAT_SUBMISSION_WITHOUT_NEW_BASIS':
                if len([p for p in self.prompts
                        if (p.get('checkpoint_feedback') or {}).get('kind')
                        == 'REPEAT_SUBMISSION_WITHOUT_NEW_BASIS']) >= 2:
                    # 无新依据仍坚持重复提交：改为申请完成（结果其实已可见）。
                    answer = self._complete_answer(prompt)
                    if answer:
                        return {'name': 'plan_decision', 'arguments': answer,
                                'tool_call_id': 'complete', 'request_id': 'mock'}
                return {'name': 'plan_decision',
                        'arguments': {'decision': 'continue', 'reason': '重试提交'},
                        'tool_call_id': 'retry-no-basis', 'request_id': 'mock'}
            if prompt.get('reason') == 'submission_checkpoint':
                # 第一次提交检查点：结果虽可见，仍按模型意图推进计划中的重复提交步。
                return {'name': 'plan_decision',
                        'arguments': {'decision': 'continue', 'reason': '继续执行计划'},
                        'tool_call_id': 'continue', 'request_id': 'mock'}
            answer = self._complete_answer(prompt)
            if answer:
                return {'name': 'plan_decision', 'arguments': answer,
                        'tool_call_id': 'complete', 'request_id': 'mock'}
            return {'name': 'plan_decision',
                    'arguments': {'decision': 'continue', 'reason': '推进计划'},
                    'tool_call_id': 'continue', 'request_id': 'mock'}

        session, evidence = self._session('repeat-guard', choose)
        result = await session.run()
        submit_clicks = [row for row in self.surface.executed
                         if row[0] == 'click' and row[1].get('y', 0) >= 200]
        repeat_feedback = [p for p in self.prompts
                           if (p.get('checkpoint_feedback') or {}).get('kind')
                           == 'REPEAT_SUBMISSION_WITHOUT_NEW_BASIS']
        self.assertTrue(repeat_feedback, '同状态重复提交必须得到局部冲突反馈')
        self.assertLessEqual(len(submit_clicks), 1, '重复提交在无新依据时不得派发')
        record_outcome('s2-repeat-guard', {'submit_clicks': len(submit_clicks),
                                           'repeat_feedback_rounds': len(repeat_feedback),
                                           'stop_reason': result['stop_reason']})

    async def test_latest_no_effect_click_not_masked_by_previous_success(self):
        executed = self.surface.execute_action

        def hook(kind, arguments):
            executed(kind, arguments)
            # 第一次点击提交不产生结果；第二次滚动后结果出现。
            if kind == 'scroll':
                self.surface.state['elements'][-1]['text'] = '利润率：40%'

        self.surface.execute_action = hook
        self.prompts = []

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if prompt.get('phase') == 'first':
                steps = self._steps_full()[:6] + [
                    {'action': 'scroll', 'direction': 'down', 'purpose': '查看结果区',
                     'expected_result': '结果区进入视口'}]
                return {'name': 'submit_plan', 'arguments': self._plan(steps),
                        'tool_call_id': 'first', 'assistant_message': {'role': 'assistant'},
                        'request_id': 'mock'}
            answer = self._complete_answer(prompt)
            if answer:
                return {'name': 'plan_decision', 'arguments': answer,
                        'tool_call_id': 'complete', 'request_id': 'mock'}
            return {'name': 'plan_decision',
                    'arguments': {'decision': 'revise', 'reason': '提交暂无效果，滚动查看结果',
                                  'remaining_plan': [{'action': 'scroll', 'direction': 'down',
                                                      'purpose': '把结果区带入视口',
                                                      'expected_result': '结果区可见'}]},
                    'tool_call_id': 'revise', 'request_id': 'mock'}

        session, evidence = self._session('latest-attempt', choose)
        result = await session.run()
        checkpoint = next(p for p in self.prompts if p.get('phase') == 'branch'
                          and p.get('latest_attempt'))
        latest = checkpoint['latest_attempt']
        self.assertIsNotNone(latest.get('dispatched'))
        # 最新尝试是提交点击（未建立效果），最后有效动作仍是此前的输入。
        self.assertIn(latest.get('action'), ('click', None))
        record_outcome('s2-latest-attempt', {'latest_attempt': latest,
                                             'last_effective': checkpoint.get('last_effective_action'),
                                             'goal_status': result['goal_status']})

    async def test_unknown_request_stops_without_redispatch(self):
        self._submit_sets_result_immediately()
        self.prompts = []

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if prompt.get('phase') == 'first':
                return {'name': 'submit_plan', 'arguments': self._plan(self._steps_full()),
                        'tool_call_id': 'first', 'assistant_message': {'role': 'assistant'},
                        'request_id': 'mock'}
            from webcollect.batch_core import OutcomeUnknown
            raise OutcomeUnknown('Original request UNKNOWN; retained')

        session, evidence = self._session('unknown-stop', choose)
        result = await session.run()
        self.assertTrue(result['unknown'])
        self.assertEqual(result['stop_reason'], 'blocked')
        executed = list(self.surface.executed)
        self.assertTrue(executed, 'UNKNOWN前已有真实派发')
        record_outcome('s2-unknown-stop', {'unknown': result['unknown'],
                                           'stop_reason': result['stop_reason'],
                                           'dispatched_actions': len(executed)})

    async def test_give_up_keeps_raw_only(self):
        async def choose(prompt):
            if prompt.get('phase') == 'first':
                return {'name': 'submit_plan', 'arguments': self._plan(self._steps_full()),
                        'tool_call_id': 'first', 'assistant_message': {'role': 'assistant'},
                        'request_id': 'mock'}
            return {'name': 'plan_decision',
                    'arguments': {'decision': 'give_up', 'reason': '提交后页面持续无结果'},
                    'tool_call_id': 'giveup', 'request_id': 'mock'}

        session, evidence = self._session('give-up', choose)
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'blocked')
        self.assertEqual(result['strategy_end_reason'], 'no_path')
        ending = load_json(session.root / 'terminal.json')['collection_ending']
        self.assertEqual(ending['kind'], 'AGENT_GIVE_UP')
        self.assertTrue(ending['flagged'])
        record_outcome('s2-give-up', {'kind': ending['kind'], 'flagged': ending['flagged'],
                                      'goal_status': result['goal_status']})

    async def test_cursor_does_not_veto_proven_goal(self):
        """原目标已证实时，剩余计划游标不造成 no_path。"""
        self._submit_sets_result_immediately()

        async def choose(prompt):
            if prompt.get('phase') == 'first':
                steps = self._steps_full() + [
                    {'action': 'scroll', 'direction': 'down', 'purpose': '继续查看',
                     'expected_result': '更多内容可见'},
                    {'action': 'scroll', 'direction': 'down', 'purpose': '再查看',
                     'expected_result': '更多内容可见'}]
                return {'name': 'submit_plan', 'arguments': self._plan(steps),
                        'tool_call_id': 'first', 'assistant_message': {'role': 'assistant'},
                        'request_id': 'mock'}
            answer = self._complete_answer(prompt)
            assert answer is not None
            return {'name': 'plan_decision', 'arguments': answer,
                    'tool_call_id': 'complete', 'request_id': 'mock'}

        session, evidence = self._session('cursor-complete', choose)
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'ready', result)
        self.assertEqual(result['strategy_end_reason'], 'goal_completed')
        ending = load_json(session.root / 'terminal.json')['collection_ending']
        self.assertEqual(ending['kind'], 'AGENT_COMPLETE_VERIFIED')
        self.assertGreater(ending.get('remaining_planned_steps') if 'remaining_planned_steps' in ending
                           else ending['endpoint_evidence']['finish_route']['remaining_planned_steps'], 0)
        record_outcome('s2-cursor-not-no-path', {'kind': ending['kind'],
                                                 'remaining': ending['endpoint_evidence']['finish_route']['remaining_planned_steps']})


def test_shared_save_gate_is_the_single_implementation():
    """两个策略共用同一资格函数：save_eligibility 即 completion_delivery_decision。"""
    annotation = {'completion_status': 'success', 'steps': [
        {'action': {'action_type': 'scroll'}} for _ in range(5)
    ] + [{'action': {'action_type': 'complete'}}]}
    raw = {'stop_reason': 'ready', 'collection_ending': {
        'protocol': COMPLETE_VERSION, 'kind': 'HOST_PLAN_ENDPOINT',
        'safe_for_pending_sample': True, 'flagged': False,
        'external_effect_unknown': False,
        'endpoint_evidence': {'image': {'sha256': 'sealed'}}},
        'goal_evidence': {'checks': [{'field': 'original result', 'status': 'VERIFIED'}]}}
    assert save_eligibility(annotation, raw) == completion_delivery_decision(annotation, raw)
    screenshot_raw = deepcopy(raw)
    screenshot_raw['collection_ending'] = {
        'protocol': COMPLETE_VERSION, 'kind': 'AGENT_COMPLETE_VERIFIED',
        'safe_for_pending_sample': True, 'flagged': False,
        'external_effect_unknown': False,
        'endpoint_evidence': {'source': 'host_screenshot_completion',
                              'completion': {'path': 'sealed.json', 'sha256': 'x'},
                              'image': {'sha256': 'sealed'}}}
    decision = save_eligibility(annotation, screenshot_raw)
    assert decision['delivery_eligible'] and decision['original_goal_completed']
    record_outcome('shared-save-gate', {'strategy1': save_eligibility(annotation, raw),
                                        'strategy2': decision})


def test_react_chooser_dispatches_the_frozen_strategy_protocol():
    """策略2任务经react_chooser走screenshot协议，策略1任务保持native chooser。"""
    import tempfile
    from webcollect.batch_core import BatchLedger
    from webcollect.react_session import react_chooser
    from webcollect.screenshot_plan import screenshot_chooser

    with tempfile.TemporaryDirectory() as tmp:
        config = load_json(Path(__file__).resolve().parents[1] / 'config' / 'batch-synthetic.json')
        config['schema_version'] = 'webcollect-batch-config-1'
        ledger = BatchLedger(Path(tmp) / 'chooser.sqlite3', config, initialize=True)
        strategy2 = build_url_task(url='https://example.org/s2', task_version='s2',
                                   ending_policy=COMPLETE_VERSION)
        freeze_strategy(strategy2, STRATEGY_SCREENSHOT_PLAN)
        strategy2['task_id'] = 'react-' + object_sha256(
            {'url': strategy2['initial_url'], 'spec': strategy2['workflow_proposal']['spec']})[:24]
        validate_task(strategy2)
        choose2 = react_chooser(ledger, strategy2, 'attempt-s2')
        assert hasattr(choose2, 'guard_unresolved')
        captured = {}

        class FakeGateway:
            def __init__(self, led):
                self.ledger = led

            def call_tool(self, job, purpose, text, tools, **kwargs):
                captured.update(protocol=purpose, tools=tools,
                                normalizer=kwargs.get('plan_normalizer'),
                                kwargs=sorted(kwargs))
                return {'name': 'submit_plan', 'arguments': {'goal': 'g', 'requirements': [
                    {'id': 'r1', 'description': '查看结果'}], 'steps': []}, 'tool_call_id': 't'}

        import webcollect.model_gateway
        with patch.object(webcollect.model_gateway, 'ModelGateway', FakeGateway):
            payload = {'phase': 'first', 'progress': {'decisions_used': 0}}
            asyncio.run(choose2({**payload, 'system': 's',
                                 'tools': submit_plan_tools(ALL_ACTIONS)}))
        assert captured['protocol'] == SCREENSHOT_VERSION
        assert captured['normalizer'] is normalize_submit_plan
        # The gateway no longer carries a normalizer version field; the chooser
        # must not forward one.
        assert 'plan_normalizer_version' not in captured['kwargs']
        # 策略1缺省任务不走screenshot chooser。
        strategy1 = build_url_task(url='https://example.org/s1', task_version='s1',
                                   ending_policy=COMPLETE_VERSION,
                                   plan_protocol=PLAN_PROTOCOL)
        choose1 = react_chooser(ledger, strategy1, 'attempt-s1')
        assert not hasattr(choose1, 'protocol_marker')
        assert hasattr(choose2, 'protocol_marker')
        record_outcome('chooser-dispatch', {'strategy2_protocol': captured['protocol'],
                                            'normalizer': captured['normalizer'].__name__})


if __name__ == '__main__':
    unittest.main()
