"""V6 complete-goal integration: disposable browser and evidence only.

No live site, model request, production ledger, QC or customer export is used.
"""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from test_react_session import ReactHarness
from webcollect.banded_plan import Controller
from webcollect.batch_core import file_sha, load_json, object_sha256
from webcollect.closing_policy import (
    COMPLETED_GOAL_DELIVERY, annotation_errors, completion_delivery_decision,
)
from webcollect.plan_protocol import ENDING_POLICY, PLAN_PROTOCOL, WIKI_READING_COMPLETION
from webcollect.postprocess import process, derive
from webcollect.react_session import ReactSession, build_url_task


def completed(count=5):
    annotation = {'completion_status': 'success', 'steps': [
        {'action': {'action_type': 'scroll'}} for _ in range(count)
    ] + [{'action': {'action_type': 'complete'}}]}
    raw = {'stop_reason': 'ready', 'collection_ending': {
        'protocol': ENDING_POLICY, 'kind': 'HOST_PLAN_ENDPOINT',
        'safe_for_pending_sample': True, 'flagged': False,
        'external_effect_unknown': False,
        'endpoint_evidence': {'image': {'sha256': 'sealed'}},
    }, 'goal_evidence': {'checks': [{'field': 'original result', 'status': 'VERIFIED'}]}}
    return annotation, raw


def test_v6_delivery_has_minimum_but_no_cumulative_maximum():
    for count, eligible in ((0, False), (4, False), (5, True), (12, True)):
        annotation, raw = completed(count)
        decision = completion_delivery_decision(annotation, raw)
        assert decision['delivery_policy'] == COMPLETED_GOAL_DELIVERY
        assert decision['delivery_eligible'] is eligible
    annotation, raw = completed(5)
    annotation['completion_status'] = 'controlled_exception'
    assert not completion_delivery_decision(annotation, raw)['delivery_eligible']
    annotation, raw = completed(5)
    raw['collection_ending']['flagged'] = True
    assert not completion_delivery_decision(annotation, raw)['delivery_eligible']


def test_attempt_feedback_loads_the_sealed_event(tmp_path):
    verified = tmp_path / 'verified.json'
    failed = tmp_path / 'failed.json'
    verified.write_text(json.dumps({'kind': 'business-attempt', 'outcome': 'VERIFIED'}))
    failed.write_text(json.dumps({
        'kind': 'business-attempt', 'number': 7, 'outcome': 'NOT_DISPATCHED',
        'step': {'action': 'type', 'target': {'text': '数量'}, 'value': '20'},
        'actual_dispatches_delta': 0, 'effective_steps_delta': 0,
        'reason': 'TYPE_REQUIRES_CURRENT_FOCUS',
    }))
    refs = [{'path': str(path), 'sha256': file_sha(path)} for path in (verified, failed)]
    session = type('Session', (), {'business_attempt_refs': refs})()
    assert Controller()._attempt_facts(session) == [{
        'number': 7, 'outcome': 'NOT_DISPATCHED', 'action': 'type',
        'target': {'text': '数量'}, 'value': '20',
        'actual_dispatches_delta': 0, 'effective_steps_delta': 0,
        'dispatched': False, 'effective': False,
        'reason': 'TYPE_REQUIRES_CURRENT_FOCUS',
    }]


class CompleteGoalV6SessionTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.task = build_url_task(
            url=self.page.url, task_version='complete-v6-fixture',
            ending_policy=ENDING_POLICY, plan_protocol=PLAN_PROTOCOL,
        )
        self.ids = {
            'sample_id': 'S000001_sample_000001', 'site_id': 'S000001',
            'batch_id': 'B20261110_001', 'attempt_id': 'complete-v6-offline',
        }
        self.manifest = {
            'batch_id': 'B20261110_001', 'sample_kind': 'real',
            'program_version': 'CONTROLLED', 'rule_version': '1.0.0',
            'sites': [{'site_id': 'S000001', 'uri': self.page.url,
                       'site_category': self.task['site_category']}],
            'samples': [self.ids['sample_id']],
        }

    def recorded(self, count, *, trailing_wait=False, wiki=False):
        self.prompts = []
        # The synthetic terminal paragraph belongs to the fixture's main body.
        # Its captured selector must substantiate the plan's 正文 region.
        self.surface.state['capture_controls'][-1]['selector'] = 'html > body > main > p'
        original = self.surface.execute_action
        scrolled = [0]

        def execute(kind, args):
            original(kind, args)
            if kind == 'scroll':
                scrolled[0] += 1
            if scrolled[0] == count and not self.surface.state['visible_text'].endswith('当前终点内容'):
                self.surface.state['visible_text'] += '\n当前终点内容'
                self.surface.state['elements'][-1]['text'] += '\n当前终点内容'

        self.surface.execute_action = execute

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            first = len(self.prompts) == 1
            if not first:
                raise AssertionError('Stable planned path must not call the model again')
            start = 0
            size = count
            steps = [{
                'action': 'scroll', 'direction': 'down',
                'purpose': f'核对第{i + 1}段独立信息',
                'expected': {'kind': 'scroll_changed', 'text': '滚动后位置改变'},
                'rationale': '原目标要求逐段核对，本步读取下一段独立正文。',
                'expected_result': '滚动后露出下一段正文，供后续核对原目标。',
            } for i in range(start, start + size)]
            if trailing_wait and (first and count <= 8 or not first):
                steps.append({
                    'action': 'wait', 'duration_ms': 50,
                    'purpose': '等待已触发的正文渲染',
                    'expected': {'kind': 'visible_text', 'text': '当前终点内容'},
                    'rationale': '最后一段正文已触发渲染，需要短暂等待稳定终态。',
                    'expected_result': '等待后当前终点内容保持可见，不再追加业务动作。',
                })
            plan = {
                'goal': '逐段核对当前页面相关信息',
                'checks': [{'field': '终点事实', 'page': 'p0', 'region': '正文',
                            'visible_text': '当前终点内容'}],
                'steps': steps,
                'finish_when': {'kind': 'visible_text', 'text': '当前终点内容'},
            }
            if not first:
                return {'attempt_id': prompt['attempt_id'],
                        'observation_id': prompt['observation']['observation_id'],
                        'choice': 'replan', 'plan': plan}
            return {
                'name': 'submit_plan', 'arguments': plan,
                'tool_call_id': 'provider-first',
                'assistant_message': {'role': 'assistant', 'tool_calls': []},
                'request_id': 'mock-provider',
            }

        task = deepcopy(self.task)
        if wiki:
            task['fragment']['wiki_reading_completion_protocol'] = WIKI_READING_COMPLETION
            spec = task['workflow_proposal']['spec']
            spec['wiki_reading_completion_protocol'] = WIKI_READING_COMPLETION
            task['task_id'] = 'react-' + object_sha256({'url': spec['entry_url'], 'spec': spec})[:24]
        evidence = self.root / f'v6-{count}-{trailing_wait}-{wiki}' / 'evidence' / self.ids['sample_id']
        session = ReactSession(
            task, evidence / 'raw', choose, self.page,
            steps_directory=evidence, attempt_id='complete-v6-offline',
        )
        return session, evidence

    def derive(self, evidence, name):
        destination = self.root / name / 'samples' / self.ids['sample_id']
        result = process(evidence, destination, self.ids, self.manifest)
        return result, destination

    async def test_first_wire_and_wiki_schema_keep_v6_range(self):
        session, _ = self.recorded(5, wiki=True)
        await session._observe()
        prompt = session.plan_controller.prompt(session)
        schema = prompt['tools'][0]['function']['parameters']
        Draft202012Validator.check_schema(schema)
        assert schema['properties']['steps']['minItems'] == 5
        assert 'maxItems' not in schema['properties']['steps']
        assert prompt['planning_range']['cumulative_maximum'] is None
        assert '累计最多10有效动作' not in prompt['system']

    async def test_five_verified_steps_save_one_formal_sample(self):
        session, evidence = self.recorded(5)
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'ready', result)
        self.assertEqual(result['effective_steps'], 5, result)
        derived, destination = self.derive(evidence, 'saved-five')
        self.assertEqual(derived['status'], 'derived_saved', derived)
        annotation = load_json(destination / 'annotation.json')
        self.assertEqual(annotation['completion_status'], 'success')
        self.assertNotIn('short_flow', annotation)
        self.assertEqual(annotation_errors(annotation), [])
        self.assertTrue((evidence / 'saved_sample.json').is_file())
        receipt = load_json(evidence / 'saved_sample.json')
        self.assertTrue(completion_delivery_decision(annotation, receipt['raw_execution'])['delivery_eligible'])
        self.assertIn('当前终点内容', annotation['final_result'])
        self.assertIn('终点事实', annotation['completion_judgement'])
        self.assertNotEqual(annotation['completion_judgement'], '原目标已完成，' + annotation['final_result'])

    async def test_twelve_verified_steps_are_not_rejected_for_length(self):
        session, evidence = self.recorded(12)
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'ready', result)
        self.assertEqual(result['effective_steps'], 12, result)
        derived, destination = self.derive(evidence, 'saved-twelve')
        self.assertEqual(derived['status'], 'derived_saved', derived)
        annotation = load_json(destination / 'annotation.json')
        self.assertEqual(len([s for s in annotation['steps']
                              if s['action']['action_type'] != 'complete']), 12)
        self.assertEqual(annotation_errors(annotation), [])

    async def test_initial_four_step_plan_is_rejected_without_formal_files(self):
        session, evidence = self.recorded(4, trailing_wait=True)
        result = await session.run()
        self.assertIn('ORDINARY_INITIAL_PATH_REQUIRES_FIVE_OR_MORE_NECESSARY_ACTIONS', result['stop_summary'])
        self.assertEqual(result['effective_steps'], 0, result)
        derived, destination = self.derive(evidence, 'rejected-four')
        self.assertNotEqual(derived['status'], 'derived_saved', derived)
        self.assertFalse((destination / 'annotation.json').exists())
        self.assertFalse((evidence / 'saved_sample.json').exists())

    async def test_controlled_exception_never_create_formal_files(self):
        session, evidence = self.recorded(5)
        result = await session.run()
        self.assertEqual(result['effective_steps'], 5, result)
        with patch('webcollect.postprocess.terminal_outcome',
                   return_value=('controlled_exception', '受控异常仅内部留证')):
            derived, destination = self.derive(evidence, 'rejected-exception')
        self.assertEqual(derived['status'], 'completion_unqualified', derived)
        self.assertFalse((destination / 'annotation.json').exists())
        self.assertFalse((evidence / 'saved_sample.json').exists())


def test_zero_and_four_effective_rows_do_not_create_formal_projection(tmp_path):
    task = build_url_task(url='https://example.org', task_version='short-fixture',
                          ending_policy=ENDING_POLICY, plan_protocol=PLAN_PROTOCOL)
    for count in (0, 4):
        destination = tmp_path / str(count)
        with patch('webcollect.postprocess.effective_trajectory', return_value=[{'action': 'scroll'}] * count):
            result = derive(task, {}, destination, {}, {})
        assert result['status'] in ('no_actions', 'length_unqualified')
        assert not destination.exists()


def test_unsettled_and_prefix_never_qualify():
    for key in ('unknown', 'external_effect_unknown', 'trusted_prefix'):
        annotation, raw = completed(12)
        raw[key] = True
        assert not completion_delivery_decision(annotation, raw)['delivery_eligible']
