"""Pure offline regressions for strategy-2 completion and closure defects.

No browser, provider request, production ledger or real collection is used.
"""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator

from webcollect.batch_core import file_sha, object_sha256
from webcollect.collection_strategy import strategy_result
from webcollect.numeric_result_evidence import process_result_text
from webcollect.screenshot_plan import (
    decision_schema,
    region_registry,
    substantive_answer_text,
    verify_completion,
)
from webcollect.screenshot_session import ScreenshotPlanSession


def _observation_session(tmp_path, text, goal, *, trajectory=(), provided=True):
    result_id = 'visible-result'
    state = {
        'document_identity': 'document-1',
        'url': 'https://example.org/',
        'elements': [
            {'element_id': 'amount', 'text': '数量', 'native_role': 'input',
             'bbox': [0, 0, 100, 30], 'visible': True},
            {'element_id': result_id, 'text': text, 'native_role': 'status',
             'bbox': [0, 50, 500, 100], 'visible': True},
        ],
        'capture_controls': [
            {'element_id': 'amount', 'tag': 'input', 'input_type': 'text',
             'form_selector': '#calculator'},
            {'element_id': result_id, 'tag': 'p', 'form_selector': '#calculator',
             'result_region_selector': '#result'},
        ],
    }
    state_path = tmp_path / 'state.json'
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    oid = 'observation-1'
    observation = {
        'capture_verified': True,
        'evidence': {
            'state': {'path': str(state_path)},
            'image': {'path': str(tmp_path / 'observation.png'), 'sha256': 'fixture'},
        },
    }
    return SimpleNamespace(
        task={'fragment': {}},
        requested_goal={'description': goal},
        trajectory=list(trajectory),
        observation_records={oid: observation},
        business_attempt_refs=[],
        provided_observations={oid} if provided else set(),
        region_registries={oid: region_registry(state)},
    ), oid


def _application(observed, oid, region='region_1'):
    return {'decision': 'complete', 'reason': '申请完成', 'answers': [{
        'requirement_id': 'r1', 'observed_result': observed,
        'evidence': [{'observation': oid, 'region': region}],
    }]}


def test_plain_prose_answer_is_accepted_without_numeric_only_rule(tmp_path):
    session, oid = _observation_session(tmp_path, '鲁迅原名周树人', '阅读正文并回答鲁迅原名')
    requirement = {'id': 'r1', 'description': '阅读正文并回答鲁迅原名'}
    assert substantive_answer_text('鲁迅原名周树人', field=requirement['description'])
    checks, gaps = verify_completion(session, _application('鲁迅原名周树人', oid), [requirement])
    assert not gaps
    assert checks[0]['status'] == 'VERIFIED'
    assert checks[0]['evidence'][0]['observation_id'] == oid


def test_reading_about_a_calculation_method_does_not_require_form_submission(tmp_path):
    goal = '阅读正文并回答文中介绍的计算方法'
    session, oid = _observation_session(tmp_path, '先计算成本，再除以收入', goal)
    requirement = {'id': 'r1', 'description': '回答文中介绍的计算方法'}
    checks, gaps = verify_completion(
        session, _application('先计算成本，再除以收入', oid), [requirement])
    assert not gaps
    assert checks[0]['status'] == 'VERIFIED'
    assert checks[0]['evidence'][0]['result_execution_binding'] is None


def test_input_focus_click_is_not_a_result_submission(tmp_path):
    rows = [
        {'operation_id': 'input-1', 'action': 'type', 'arguments': {'text': '20'},
         'target': {'control_id': 'amount'},
         'before_observation_id': 'observation-1', 'after_observation_id': 'observation-1'},
        {'operation_id': 'focus-1', 'action': 'click', 'arguments': {},
         'target': {'control_id': 'amount'},
         'before_observation_id': 'observation-1', 'after_observation_id': 'observation-1'},
    ]
    session, oid = _observation_session(
        tmp_path, '利润率：40%', '修改数量并计算本次利润率', trajectory=rows)
    requirement = {'id': 'r1', 'description': '查看本次输入对应的利润率计算结果'}
    checks, gaps = verify_completion(session, _application('利润率：40%', oid), [requirement])
    assert not checks
    assert 'RESULT_SUBMISSION_REQUIRED' in {gap['kind'] for gap in gaps}


def test_final_solution_cannot_impersonate_a_step_by_step_process(tmp_path):
    session, oid = _observation_session(tmp_path, 'x = 1', '逐步求解方程并展示求解过程')
    requirement = {'id': 'r1', 'description': '展示逐步求解过程'}
    assert not process_result_text('x = 1', requirement['description'])
    checks, gaps = verify_completion(session, _application('x = 1', oid), [requirement])
    assert not checks
    assert 'PROCESS_STEPS_NOT_SUBSTANTIVE' in {gap['kind'] for gap in gaps}


def test_completion_cannot_cite_an_observation_never_supplied_to_the_model(tmp_path):
    session, oid = _observation_session(
        tmp_path, '鲁迅原名周树人', '阅读正文并回答鲁迅原名', provided=False)
    requirement = {'id': 'r1', 'description': '阅读正文并回答鲁迅原名'}
    checks, gaps = verify_completion(session, _application('鲁迅原名周树人', oid), [requirement])
    assert not checks
    assert 'OBSERVATION_NOT_PROVIDED' in {gap['kind'] for gap in gaps}


def test_decision_schema_requires_evidence_anchor_and_preserves_the_action_whitelist():
    schema = decision_schema(['revise', 'complete'], ['scroll'])
    Draft202012Validator.check_schema(schema)
    variants = schema['properties']['remaining_plan']['items']['oneOf']
    assert {row['properties']['action']['const'] for row in variants} == {'scroll'}
    evidence = schema['properties']['answers']['items']['properties']['evidence']['items']
    assert set(evidence['required']) == {'observation'}
    # The anchor is an issued region id or a verbatim visible-text quote.
    assert evidence['anyOf'] == [{'required': ['region']}, {'required': ['quote']}]


def _first_plan_session(goal, replies):
    session = ScreenshotPlanSession.__new__(ScreenshotPlanSession)
    session.task = {'fragment': {'allowed_actions': ['scroll']}}
    session.requested_goal = {'description': goal}
    session.working_goal = None
    session.initial_feedback = None
    session.plan = None
    session.plan_version = 0
    session.events = []
    session.event = lambda kind, **payload: session.events.append({'kind': kind, **payload}) or payload
    session._first_prompt = lambda: {}
    session._range_close = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError('a corrected fixed goal must not close the session'))

    async def decide(prompt):
        return {'arguments': replies.pop(0)}

    session._decide = decide
    return session


def _five_step_plan(goal):
    return {
        'goal': goal,
        'requirements': [{'id': 'r1', 'description': '阅读并回答原目标事项'}],
        'steps': [{'action': 'scroll', 'direction': 'down', 'purpose': f'阅读第{i}段',
                   'expected_result': '看到下一段正文'} for i in range(5)],
    }


def test_fixed_goal_conflict_gets_bounded_feedback_without_replacing_goal():
    fixed = '阅读指定条目并回答原名'
    session = _first_plan_session(fixed, [_five_step_plan('另选一个任务'), _five_step_plan(fixed)])
    asyncio.run(session._first_plan_round())
    assert session.plan is None
    assert session.initial_feedback['kind'] == 'FIXED_GOAL_MISMATCH'
    assert session.initial_feedback['dispatched'] is False
    asyncio.run(session._first_plan_round())
    assert session.frozen_goal == fixed
    assert session.working_goal == fixed
    assert session.plan_event['requested_goal'] == {'description': fixed}


def test_second_different_completion_supplement_is_verified_before_no_progress():
    session = ScreenshotPlanSession.__new__(ScreenshotPlanSession)
    session.task = {'fragment': {'allowed_actions': ['scroll']}}
    session.plan = {'steps': []}
    session.position = 0
    session.plan_version = 1
    session.requirements = [{'id': 'r1', 'description': '阅读正文并回答原名'}]
    session.current = {'observation_id': 'observation-1'}
    session.actual_dispatches = 0
    session.no_progress_keys = {}
    session.no_progress_dispatches = {}
    session._stall_marker = None
    session._stall_count = 0
    session.completion_feedback = None
    session.prompts = []

    def branch_prompt(reason, feedback=None):
        prompt = {'choices': ['revise', 'complete', 'give_up'], 'reason': reason,
                  'feedback': deepcopy(feedback)}
        session.prompts.append(prompt)
        return prompt

    replies = [
        {'decision': 'complete', 'reason': '第一次补证', 'answers': [{'observed_result': '错误引用'}]},
        {'decision': 'complete', 'reason': '第二次补证', 'answers': [{'observed_result': '正确正文'}]},
    ]

    async def decide(prompt):
        return {'arguments': replies.pop(0)}

    session._branch_prompt = branch_prompt
    session._decide = decide
    session.event = lambda *args, **kwargs: {}
    session._range_close = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError('different supplementary evidence must not close as no-progress')
    )
    session._complete = lambda application, checks, reason: setattr(session, 'completed_checks', checks)
    verified = []

    def verify(_session, decision, _requirements):
        verified.append(decision['answers'][0]['observed_result'])
        if len(verified) == 1:
            return [], [{'kind': 'NO_BOUND_EVIDENCE', 'message': '补齐引用'}]
        return [{'status': 'VERIFIED'}], []

    with patch('webcollect.screenshot_session.verify_completion', verify):
        asyncio.run(session._checkpoint('plan_exhausted'))
    assert verified == ['错误引用', '正确正文']
    assert session.completed_checks == [{'status': 'VERIFIED'}]
    assert len(session.prompts) == 2
    assert session.prompts[0]['reason'] == session.prompts[1]['reason'] == 'plan_exhausted'
    assert session.prompts[1]['feedback']['kind'] == 'COMPLETION_EVIDENCE_GAPS'


def test_repeat_guard_does_not_treat_scroll_or_input_focus_as_submission():
    session = ScreenshotPlanSession.__new__(ScreenshotPlanSession)
    session.current = {'controls': {}}
    state = {'document_identity': 'document-1'}
    scroll = {'action': 'scroll', 'direction': 'down', 'target': {'text': '正文'}}
    identity = session._action_identity(scroll, [], state)
    session.dispatch_identities = {identity: {
        'dispatched': True, 'state_sha256': object_sha256(state), 'operation_id': 'old',
    }}
    conflict, _ = session._repeat_guard(scroll, [], state, None)
    assert conflict is None

    session.current = {'controls': {'amount': {
        'binding': {'tag': 'input', 'input_type': 'text'},
        'element': {'text': '数量'},
    }}}
    focus = {'action': 'click', 'target': {'text': '数量'}}
    identity = session._action_identity(focus, ['amount'], state)
    session.dispatch_identities = {identity: {
        'dispatched': True, 'state_sha256': object_sha256(state), 'operation_id': 'old',
    }}
    conflict, _ = session._repeat_guard(focus, ['amount'], state, None)
    assert conflict is None

    session.current = {'controls': {'submit': {
        'binding': {'tag': 'button', 'input_type': 'submit'},
        'element': {'text': '计算'},
    }}}
    submit = {'action': 'click', 'target': {'text': '计算'}}
    identity = session._action_identity(submit, ['submit'], state)
    session.dispatch_identities = {identity: {
        'dispatched': True, 'state_sha256': object_sha256(state), 'operation_id': 'old',
    }}
    conflict, _ = session._repeat_guard(submit, ['submit'], state, None)
    assert conflict['kind'] == 'REPEAT_SUBMISSION_WITHOUT_NEW_BASIS'


def test_strategy_result_does_not_turn_every_unknown_into_user_stop(tmp_path):
    terminal_path = tmp_path / 'terminal.json'
    terminal_path.write_text(json.dumps({'collection_ending': {'kind': 'RAW_PENDING'}}), encoding='utf-8')
    terminal_ref = {'path': str(terminal_path), 'sha256': file_sha(terminal_path)}
    receipt_path = tmp_path / 'raw-receipt.json'
    receipt_path.write_text(json.dumps({'terminal': terminal_ref}), encoding='utf-8')
    # The live in-memory receipt is only a file reference; terminal lives inside it.
    receipt = {'path': str(receipt_path), 'sha256': file_sha(receipt_path)}
    task = {'task_id': 'task', 'task_version': 'fixture', 'site_uri': 'https://example.org/',
            'fragment': {}}
    summary = {'stop_reason': 'blocked', 'unknown': True, 'failure_class': 'interrupted',
               'effective_steps': 0, 'actual_actions': 0}
    result = strategy_result(task, summary=summary, raw_receipt=receipt)
    assert result['end']['end_reason'] == 'unknown'
    stopped = strategy_result(task, summary={**summary, 'strategy_end_reason': 'user_stopped'},
                              raw_receipt=receipt)
    assert stopped['end']['end_reason'] == 'user_stopped'
