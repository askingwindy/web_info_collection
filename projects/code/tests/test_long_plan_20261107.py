"""V11 long-plan ceiling and bounded replan correction; synthetic IO only."""
from copy import deepcopy
import json
import unittest

from jsonschema.exceptions import ValidationError

import test_closing_policy_v2 as closing_fixture
from test_banded_plan import plan_for
from test_react_session import ReactHarness
from webcollect.banded_plan import (
    V10_VERSION,
    VERSION as V11_VERSION,
    attempt_limit,
    choice_schema,
    tools,
    validate_plan,
)
from webcollect.closing_policy import V2_VERSION, VERSION as V3_VERSION, annotation_errors
from webcollect.model_gateway import normalize_branch, validate_branch
from webcollect.react_session import ReactSession, build_url_task, validate_task


class LongPlanPureTests(unittest.TestCase):
    def test_v10_stays_at_eight_while_only_v11_long_gets_twelve(self):
        old = build_url_task(url='https://example.org', task_version='old',
                             plan_protocol=V10_VERSION, ending_policy=V2_VERSION)
        new = build_url_task(url='https://example.org', task_version='new',
                             plan_protocol=V11_VERSION, ending_policy=V3_VERSION)
        validate_task(old)
        validate_task(new)
        self.assertEqual(attempt_limit(old, 'long'), 8)
        self.assertEqual(attempt_limit(new, 'long'), 12)
        self.assertEqual(attempt_limit(new, 'five'), 8)
        self.assertEqual(attempt_limit(new, 'short'), 8)

        prompt = {'attempt_id': 'a', 'observation': {'observation_id': 'o'}}
        ninth = plan_for(prompt, 9)
        with self.assertRaises(ValidationError):
            validate_plan(ninth, 'a', 'o', old['fragment']['allowed_actions'],
                          max_steps=attempt_limit(old, 'long'))
        twelve = plan_for(prompt, 12)
        accepted = validate_plan(twelve, 'a', 'o', new['fragment']['allowed_actions'],
                                 max_steps=attempt_limit(new, 'long'))
        self.assertEqual((accepted['band'], len(accepted['steps'])), ('long', 12))
        with self.assertRaises(ValidationError):
            validate_plan(plan_for(prompt, 12), 'a', 'o', new['fragment']['allowed_actions'],
                          max_steps=attempt_limit(new, 'five'))

    def test_prompt_tool_wire_normalize_and_host_share_the_same_limit(self):
        self.assertEqual(tools(max_steps=8)[0]['function']['parameters']['properties']['steps']['maxItems'], 8)
        first = tools(max_steps=12)[0]['function']['parameters']
        self.assertEqual(first['properties']['steps']['maxItems'], 12)
        branch = choice_schema(inherited=True, wire=True, max_steps=12)
        prompt = {'attempt_id': 'a', 'observation': {'observation_id': 'o'}}
        reply = {'choice': 'replan', 'plan': {'steps': plan_for(prompt, 12)['steps']}}
        normalized = normalize_branch(reply, {'replan_contract': {'attempt_limit': 12}})
        validate_branch(normalized, branch)
        with self.assertRaises(ValidationError):
            validate_branch({'choice': 'replan', 'plan': {'steps': plan_for(prompt, 12)['steps'] + [deepcopy(plan_for(prompt, 1)['steps'][0])]}}, branch)

    def test_after_seven_long_steps_two_goal_actions_fit_five_remaining(self):
        task = build_url_task(url='https://example.org', task_version='new',
                              plan_protocol=V11_VERSION, ending_policy=V3_VERSION)
        prompt = {'attempt_id': 'a', 'observation': {'observation_id': 'o'}}
        remaining = plan_for(prompt, 2)
        remaining['steps'] = [
            {'action': 'click', 'target': {'text': '计算面积'},
             'purpose': '触发本次面积计算', 'expected': {'kind': 'visible_text', 'text': '本次面积结果'}},
            {'action': 'scroll', 'direction': 'down',
             'purpose': '查看本次结果完整单位', 'expected': {'kind': 'scroll_changed'}},
        ]
        accepted = validate_plan(remaining, 'a', 'o', task['fragment']['allowed_actions'],
                                 remaining=12 - 7, inherited_band='long', pending_checks=True,
                                 max_steps=attempt_limit(task, 'long'))
        self.assertEqual(len(accepted['steps']), 2)


class LongPlanSessionTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    derive = closing_fixture.EndingV2Tests.derive

    def setUp(self):
        super().setUp()
        self.ids = {'sample_id': 'S000001_sample_000001', 'site_id': 'S000001',
                    'batch_id': 'B20261107_001', 'attempt_id': 'offline-long'}
        self.task = self.make_task(V11_VERSION, V3_VERSION)
        self.manifest = {'batch_id': 'B20261107_001', 'sample_kind': 'real',
                         'program_version': 'CONTROLLED', 'rule_version': '1.0.0',
                         'sites': [{'site_id': 'S000001', 'uri': self.page.url,
                                    'site_category': self.task['site_category']}],
                         'samples': [self.ids['sample_id']]}

    def make_task(self, plan_protocol, ending_policy):
        return build_url_task(url=self.page.url, task_version='long-offline',
                              plan_protocol=plan_protocol, ending_policy=ending_policy)

    def recorded(self, name, initial_steps, branches, *, endpoint_at, task=None):
        self.prompts = []
        replies = list(branches)
        original = self.surface.execute_action

        def execute(kind, args):
            original(kind, args)
            if len(self.surface.executed) == endpoint_at:
                self.surface.state['visible_text'] += '\n当前终点内容'

        self.surface.execute_action = execute

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            if len(self.prompts) == 1:
                return {'name': 'submit_plan', 'arguments': plan_for(prompt, initial_steps),
                        'tool_call_id': 'provider-first',
                        'assistant_message': {'role': 'assistant', 'tool_calls': []},
                        'request_id': 'mock-provider'}
            if not replies:
                raise AssertionError('unexpected extra model request')
            reply = replies.pop(0)
            return reply(prompt) if callable(reply) else deepcopy(reply)

        evidence = self.root / name / 'evidence' / self.ids['sample_id']
        session = ReactSession(self.task if task is None else task, evidence / 'raw', choose,
                               self.page, steps_directory=evidence, attempt_id='offline-long')
        session.context = {'band_budget': {'assigned_band': 'long'}}
        return session, evidence

    @staticmethod
    def replan(prompt, count):
        return {'choice': 'replan', 'plan': plan_for(prompt, count)}

    async def test_eleven_then_corrected_replan_finishes_twelfth_and_exports(self):
        session, evidence = self.recorded(
            'twelve', 11,
            [lambda p: self.replan(p, 2), lambda p: self.replan(p, 1)],
            endpoint_at=12)
        result = await session.run()
        marker = result['collection_ending']
        self.assertFalse(result['host_failure'], result)
        self.assertFalse(result['unknown'])
        self.assertEqual((result['effective_steps'], result['actual_actions']), (12, 12))
        self.assertEqual(len(self.surface.executed), 12)
        self.assertEqual(result['stop_reason'], 'ready')
        self.assertEqual(marker['kind'], 'HOST_PLAN_ENDPOINT')
        self.assertEqual((marker['attempt_limit'], marker['attempt_band']), (12, 'long'))
        self.assertEqual(len(self.prompts), 3)
        self.assertIn('6–12步', self.prompts[0]['system'])
        self.assertNotIn('6–8步', self.prompts[0]['system'])
        self.assertEqual(self.prompts[0]['tools'][0]['function']['parameters']['properties']['steps']['maxItems'], 12)
        # 2026-11-07 V11 hint simplification: the model reads the total from
        # attempt_limit plus its executed steps; the duplicated remaining-step
        # field and the "one step left" special wording are gone.
        self.assertNotIn('remaining_effective_limit', self.prompts[1]['replan_contract'])
        self.assertEqual(self.prompts[1]['replan_contract']['attempt_limit'], 12)
        self.assertEqual(self.prompts[1]['replan_contract']['budget_instruction'],
                         'replan只提交尚未执行的剩余目标动作，不得重复已完成动作；宿主按冻结总步数校验。')
        for prompt in self.prompts:
            self.assertNotIn('只剩1步', json.dumps(prompt, ensure_ascii=False))
        self.assertNotIn('budget_feedback', self.prompts[1])
        self.assertEqual(self.prompts[2]['budget_feedback']['proposed_steps'], 2)
        self.assertEqual(self.prompts[2]['budget_feedback']['attempt_limit'], 12)
        self.assertNotIn('remaining_effective_limit', self.prompts[2]['budget_feedback'])
        self.assertEqual(len(list((evidence / 'raw').glob('*plan-budget-feedback.json'))), 1)

        _, annotation = self.derive(evidence)
        self.assertEqual(len(annotation['steps']), 13)
        saved = annotation['steps'][-1]['tool_result']['return_value']['collection_ending']
        self.assertEqual((saved['attempt_limit'], saved['attempt_band']), (12, 'long'))
        self.assertEqual(annotation_errors(annotation), [])

    async def test_second_excess_in_same_context_stops_without_twelfth_action(self):
        session, evidence = self.recorded(
            'second-excess', 11,
            [lambda p: self.replan(p, 2), lambda p: self.replan(p, 2)],
            endpoint_at=12)
        result = await session.run()
        self.assertTrue(result['host_failure'])
        self.assertFalse(result['unknown'])
        self.assertIn('PLAN_EXCEEDS_FROZEN_REMAINING_STEPS', result['stop_summary'])
        self.assertEqual((result['effective_steps'], result['actual_actions']), (11, 11))
        self.assertEqual(len(self.surface.executed), 11)
        self.assertEqual(len(self.prompts), 3)
        self.assertEqual(len(list((evidence / 'raw').glob('*plan-budget-feedback.json'))), 1)

    async def test_v10_over_limit_has_no_v11_correction(self):
        old = self.make_task(V10_VERSION, V2_VERSION)
        session, evidence = self.recorded(
            'v10-excess', 7, [lambda p: self.replan(p, 2)], endpoint_at=8, task=old)
        result = await session.run()
        self.assertTrue(result['host_failure'])
        self.assertFalse(result['unknown'])
        self.assertIn('PLAN_EXCEEDS_FROZEN_REMAINING_STEPS', result['stop_summary'])
        self.assertEqual((result['effective_steps'], result['actual_actions']), (7, 7))
        self.assertEqual(len(self.prompts), 2)
        self.assertEqual(list((evidence / 'raw').glob('*plan-budget-feedback.json')), [])


if __name__ == '__main__':
    unittest.main()
