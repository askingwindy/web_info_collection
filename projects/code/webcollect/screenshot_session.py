"""策略 2 会话：复用 ReactSession 原子执行/取证/账本，替换决策循环。

The session reuses the entry observation, trusted capture, atomic dispatch,
effect verification, business-attempt journal and raw close-out from
ReactSession. What changes is the decision loop: one first-round submit_plan,
deterministic execution of planned steps, model checkpoints only at business
events (submit-like clicks, navigation, dialogs, binding/identity refusals,
result reading or plan exhaustion) and a verified `complete`.
"""
import asyncio
from copy import deepcopy
import json
import time

from .batch_core import OutcomeUnknown, SessionGLMCallLimit, BudgetStop, load_json
from .planning import object_sha256
from .screenshot_plan import (VERSION, COMPLETION_VERSION, NORMALIZER_VERSION, SYSTEM_PROMPT,
    FIRST_RULES, BRANCH_RULES, BUSINESS_MINIMUM, PREFERRED_MAXIMUM, NON_BUSINESS_ACTIONS,
    DECISIONS, READY_ENDING, RAW_ONLY_ENDINGS, submit_plan_tools, decision_tools,
    normalize_submit_plan, normalize_decision, first_plan_admission, business_actions,
    region_registry, verify_completion)
from .react_session import ReactSession, ReactStop


class ScreenshotPlanSession(ReactSession):
    """策略 2 execution: screenshot checkpoints and remaining-plan revision."""

    def __init__(self, task, directory, choose, page, **kwargs):
        super().__init__(task, directory, choose, page, **kwargs)
        self.plan = None
        self.frozen_goal = None
        self.requirements = []
        self.position = 0
        self.plan_version = 0
        self.plan_event = None
        self.initial_feedback = None
        self.completion_feedback = None
        self.latest_attempt = None
        self.last_effective = None
        self.dispatch_identities = {}
        self.no_progress_keys = {}
        self.no_progress_dispatches = {}
        self.region_registries = {}
        self.latest_document_identity = None
        self._dialog_checkpointed = []
        self._granted_new_basis = None
        self.completion_endpoint_basis = None
        self.strategy_end_reason = None
        self.extra_ready_endings = (READY_ENDING,)

    # ------------------------------------------------------------------ run

    async def run(self):
        stop = None
        try:
            if self.native or self.glm_session_id:
                self._check_request_budget()
            await self._open_entry()
            while self.state == 'recording':
                if self._left('max_seconds') <= 0:
                    self.stop_reason, self.stop_summary = 'budget', '宿主时间预算耗尽，保留已执行内容'
                    self.state = 'closed_by_host'
                    break
                if self.plan is None:
                    await self._first_plan_round()
                else:
                    await self._execute_round()
        except SessionGLMCallLimit as error:
            self.stop_details = error.details
            self.stop_reason, self.stop_summary = 'budget', str(error)
            self.state = 'closed_by_host'
        except ReactStop as error:
            stop = error
            if self.stop_reason is None:
                self.stop_reason, self.stop_summary = error.stop_reason, error.reason
                self.failure_class = error.failure_class
                self.unknown = self.unknown or error.unknown
            self.state = 'closed_by_host'
        except asyncio.CancelledError as error:
            # 用户停止立即生效：不再派发动作或调用；原账由既有 UNKNOWN/取消规则收口。
            self.strategy_end_reason = 'user_stopped'
            self.stop_reason, self.stop_summary = 'blocked', '会话被用户停止，保留已执行内容'
            self.unknown = True
            self.failure_class = 'interrupted'
            self.state = 'closed_by_host'
            self._close()
            raise
        except BaseException as error:
            stop = ReactStop('blocked', type(error).__name__ + ': ' + str(error), 'program')
            self.stop_reason, self.stop_summary = 'blocked', str(stop)
            self.failure_class = 'program'
            self.state = 'closed_by_host'
        self.host_failure = stop is not None
        receipt = self._close()
        return self._strategy_summary(receipt)

    def _strategy_summary(self, receipt):
        ending = getattr(self, 'collection_ending', None) or {}
        return {'host_failure': self.host_failure, 'stop_reason': self.stop_reason,
                'stop_summary': self.stop_summary,
                'strategy': {'id': 'webcollect-collection-screenshot-plan-2', 'protocol': VERSION},
                'strategy_end_reason': (self.strategy_end_reason
                    or ('goal_completed' if ending.get('kind') == READY_ENDING
                        else 'unsuitable' if ending.get('kind') == 'UNSUITABLE_TASK'
                        else 'no_progress' if ending.get('kind') == 'NO_PROGRESS_END'
                        else 'no_path' if ending.get('kind') == 'AGENT_GIVE_UP'
                        else 'unknown' if self.unknown else None)),
                'goal_status': ('completed'
                                if (getattr(self, 'goal_evidence', None) or {}).get('business_goal_status') == 'VERIFIED'
                                else 'unconfirmed'),
                'failure_class': self.failure_class, 'unknown': self.unknown,
                'effective_steps': len(self.trajectory), 'actual_actions': self.actual_dispatches,
                'short_flow': self.short_flow, 'short_flow_reason': self.short_flow_reason,
                **({'collection_ending': getattr(self, 'collection_ending', None)}
                   if self._v2() else {}),
                'raw_receipt': receipt,
                'terminal': {'path': str(self.root / 'terminal.json'),
                             'sha256': file_sha_of(self.root / 'terminal.json')}}

    # ------------------------------------------------------------------ decide

    async def _decide(self, prompt):
        """One model call at a checkpoint; UNKNOWN and stop semantics shared."""
        self._last_model_intent = self.event('model-intent', prompt=_stripped(prompt))
        self._consume('max_decisions')
        guard = getattr(self.choose, 'guard_unresolved', None)
        if guard:
            guard()
        try:
            with self._phase('model_wait', decision=self.used['max_decisions']):
                response = await self.choose(prompt)
        except OutcomeUnknown as error:
            self.unknown = True
            raise ReactStop('blocked', '决策请求结果未知，保留 UNKNOWN 不重发：' + str(error),
                            'interrupted', unknown=True) from error
        except (SessionGLMCallLimit, BudgetStop, ReactStop, asyncio.CancelledError):
            raise
        except Exception as error:
            raise ReactStop('blocked', type(error).__name__ + ': ' + str(error), 'model') from error
        finally:
            counter = getattr(self.choose, 'requests_used', None)
            if counter is not None and (self.native or self.glm_session_id):
                used = counter()
                if self.native:
                    self.used['max_model_calls'] = used
                if self.glm_session_id:
                    self.glm_http_requests = used
        return response

    # ------------------------------------------------------------------ first plan

    def _first_prompt(self):
        state = load_json(self.current['evidence']['state']['path'])
        if self.current['observation_id'] not in self.region_registries:
            self.region_registries[self.current['observation_id']] = region_registry(state)
            self.event('screenshot-regions', observation_id=self.current['observation_id'],
                       regions=deepcopy(self.region_registries[self.current['observation_id']]))
        goal = self.requested_goal
        payload = {'protocol': VERSION, 'phase': 'first', 'attempt_id': self.attempt_id,
                   'system': SYSTEM_PROMPT,
                   'goal': goal, 'page': {'url': self.current['url'],
                                          'title': (state.get('title') or '')[:120],
                                          'visible_excerpt': (state.get('visible_text') or '')[:600]},
                   'regions': self.region_registries[self.current['observation_id']],
                   'allowed_actions': [action for action in self.task['fragment']['allowed_actions']],
                   'rules': FIRST_RULES,
                   'planning_range': {'minimum': BUSINESS_MINIMUM,
                                      'preferred_maximum': PREFERRED_MAXIMUM, 'maximum': None,
                                      'note': '至少5个必要业务动作，优先5–8步，无硬上限；wait不计业务动作'},
                   'tools': submit_plan_tools(self.task['fragment']['allowed_actions']),
                   'progress': {'decisions_used': self.used['max_decisions'],
                                'effective_steps': len(self.trajectory),
                                'actual_dispatches': self.actual_dispatches}}
        if self.initial_feedback:
            payload['first_plan_feedback'] = deepcopy(self.initial_feedback)
        payload['_images'] = [self.current['evidence']['image']['path']]
        return payload

    async def _first_plan_round(self):
        prompt = self._first_prompt()
        response = await self._decide(prompt)
        arguments = response.get('arguments') or {}
        plan, record = normalize_submit_plan(arguments, self.task['fragment']['allowed_actions'])
        self.event('screenshot-plan-normalized', phase='first', version=NORMALIZER_VERSION,
                   normalization=record, plan=plan)
        ok, feedback = first_plan_admission(plan)
        if not ok:
            if self.initial_feedback is None:
                # 同一观察下的有界纠正：给精确反馈再请求一次，不派发任何动作。
                self.initial_feedback = feedback
                self.event('screenshot-plan-rejected', feedback=feedback, dispatched=False)
                return
            self.event('screenshot-plan-rejected', feedback=feedback, dispatched=False, final=True)
            self._range_close('UNSUITABLE_TASK', feedback['message'])
            return
        if feedback['kind'] == 'unsuitable':
            self.event('screenshot-plan-unsuitable', reason=feedback['unsuitable'])
            self._range_close('UNSUITABLE_TASK', '模型报告自然路径不适合：' + str(feedback['unsuitable'].get('reason') or ''))
            return
        requirements = plan.get('requirements') or []
        if not requirements:
            self.initial_feedback = self.initial_feedback or {
                'kind': 'missing_requirements', 'field_paths': ['requirements'],
                'message': '缺少完成事项requirements；每项一条原目标必须看到的结果'}
            self.event('screenshot-plan-rejected', feedback=self.initial_feedback, dispatched=False)
            return
        self.frozen_goal = plan.get('goal') or describe(self.requested_goal) or self.working_goal
        if self.working_goal is None:
            self.working_goal = self.frozen_goal
        self.requirements = [{'id': row['id'], 'description': row['description']} for row in requirements]
        self.plan = {'steps': plan['steps']}
        self.position = 0
        self.plan_version = 1
        self.initial_feedback = None
        self.plan_event = self.event('screenshot-plan', phase='first', version=self.plan_version,
            goal=self.frozen_goal, requirements=deepcopy(self.requirements),
            steps=deepcopy(self.plan['steps']), admission=feedback)

    # ------------------------------------------------------------------ execution

    TARGET_REQUIRED_ACTIONS = ('click', 'double_click', 'right_click', 'type', 'select', 'drag')

    def _bind_target(self, step):
        """Bind a semantic target to the unique current control, if any."""
        from .banded_plan import bind_target
        target = step.get('target')
        if not target:
            return None
        return bind_target(self.current, target, self.observation_records)

    def _action_identity(self, step, control_ids, state):
        binding = {}
        if control_ids:
            control = self.current['controls'].get(control_ids[0]) or {}
            binding = control.get('binding') or {}
        return object_sha256({
            'action': step.get('action'),
            'target': (step.get('target') or {}).get('text'),
            'form': binding.get('form_selector'),
            'document': state.get('document_identity'),
            'value': step.get('value'), 'keys': step.get('keys'),
            'direction': step.get('direction'),
            'target_state': (state.get('document_identity'), (step.get('target') or {}).get('text'))})

    def _repeat_guard(self, step, control_ids, state, new_basis):
        """同身份动作不重复派发；重试须有可对应实际变化的新依据。"""
        identity = self._action_identity(step, control_ids, state)
        previous = self.dispatch_identities.get(identity)
        if previous is None:
            return None, identity
        changed_state = previous.get('state_sha256') != object_sha256(state)
        not_dispatched = previous.get('dispatched') is False
        if not_dispatched or (new_basis and changed_state):
            return None, identity
        return {'kind': 'REPEAT_SUBMISSION_WITHOUT_NEW_BASIS',
                'message': ('同一输入、同一页面状态下该动作已派发过；结果未进视口请先观察（滚动/等待），'
                            '重试必须在new_basis说明修正了输入、重新定位了目标或页面明确反馈'),
                'previous': {key: previous.get(key) for key in ('operation_id', 'outcome', 'at')},
                'new_basis_required': True}, identity

    def _react_step(self, step, control_ids):
        from .banded_plan import execution_keys
        action = step['action']
        actual = {'action': action, 'goal': step.get('purpose') or action,
                  'expected': step.get('expected_result') or step.get('purpose') or action,
                  'rationale': step.get('purpose'), 'expected_result': step.get('expected_result')}
        for key in ('value', 'keys', 'direction', 'page_id', 'duration_ms'):
            if key in step:
                actual[key] = step[key]
        if action == 'hotkey' and isinstance(actual.get('keys'), list):
            # 与策略1相同的宿主平台映射（ctrl+a→meta+a on darwin）。
            actual['keys'] = execution_keys(actual['keys'])
        if action in ('click', 'double_click', 'right_click', 'drag', 'type', 'select'):
            actual['control_id'] = control_ids[0]
        if action == 'hotkey':
            # 原生协议要求显式可空的 control_id；焦点前提由当前焦点核实。
            actual['control_id'] = control_ids[0] if control_ids else None
        if action == 'drag':
            endpoint = step.get('end_target') or {}
            matches = self._bind_target({'target': endpoint}) or []
            if len(matches) != 1:
                raise ValueError('DRAG_DESTINATION_NOT_UNIQUELY_BOUND')
            actual['end_control_id'] = matches[0]
        return actual

    async def _execute_round(self):
        if self.position >= len(self.plan['steps']):
            await self._checkpoint('plan_exhausted')
            return
        step = self.plan['steps'][self.position]
        action = step.get('action')
        matches = self._bind_target(step)
        requires_target = action in self.TARGET_REQUIRED_ACTIONS
        if requires_target and (not matches or len(matches) != 1):
            await self._checkpoint('binding', feedback={
                'kind': 'TARGET_NOT_UNIQUELY_BOUND',
                'message': '当前观察中目标未唯一绑定；请修订剩余计划或改选有据目标',
                'step_position': self.position, 'matches': len(matches or [])})
            return
        state = load_json(self.current['evidence']['state']['path'])
        new_basis = self._granted_new_basis
        conflict, identity = self._repeat_guard(step, matches or [], state, new_basis)
        if conflict:
            await self._checkpoint('repeat_submission', feedback=conflict)
            return
        self._granted_new_basis = None
        try:
            actual = self._react_step(step, matches or [])
        except ValueError as error:
            await self._checkpoint('binding', feedback={'kind': 'STEP_NOT_EXECUTABLE',
                                                        'message': str(error), 'step_position': self.position})
            return
        before_dispatches = self.actual_dispatches
        before_effective = len(self.trajectory)
        attempts_before = len(getattr(self, 'business_attempt_refs', []))
        self.latest_document_identity = self.current['document_identity']
        result = await self._tool_act({'observation_id': self.current['observation_id'], 'step': actual})
        if ((result or {}).get('status') == 'rejected'
                and 'MISSING_TARGET_PROBE' in str((result or {}).get('summary', ''))
                and (matches or []) and matches[0] in self.current['controls']):
            # 工程自行补一次定向观察（与策略1控制器相同的唯一控件探针），
            # 不把可确定的目标资格问题推给模型。
            await self._observe(matches[0])
            actual = self._react_step(step, matches)
            result = await self._tool_act({'observation_id': self.current['observation_id'], 'step': actual})
        self.dispatch_identities[identity] = {
            'operation_id': (self.trajectory[-1]['operation_id']
                             if len(self.trajectory) > before_effective else None),
            'dispatched': self.actual_dispatches > before_dispatches,
            'outcome': None, 'at': time.time(),
            'state_sha256': object_sha256(load_json(self.current['evidence']['state']['path']))}
        self._refresh_attempt_facts()
        if self.state != 'recording':
            return
        new_attempt = len(getattr(self, 'business_attempt_refs', [])) > attempts_before
        attempt = self.latest_attempt or {}
        advanced = (result or {}).get('status') == 'ok' and (
            not new_attempt or attempt.get('outcome') == 'VERIFIED')
        if advanced:
            self.position += 1
        if self._checkpoint_needed(step, matches or [], result, attempt):
            await self._checkpoint(self._checkpoint_reason(step, matches or [], attempt),
                                   executed=new_attempt)

    def _refresh_attempt_facts(self):
        """latest_attempt 与 last_effective_action 分开维护。"""
        refs = getattr(self, 'business_attempt_refs', [])
        if refs:
            attempt = load_json(refs[-1]['path'])
            self.latest_attempt = {'number': attempt.get('number'),
                'action': (attempt.get('step') or {}).get('action'),
                'purpose': (attempt.get('step') or {}).get('goal'),
                'dispatched': attempt.get('actual_dispatches_delta', 0) > 0,
                'effective': attempt.get('effective_steps_delta', 0) > 0,
                'outcome': attempt.get('outcome'), 'reason': str(attempt.get('reason') or '')[:200],
                'ref': refs[-1]}
            if self.dispatch_identities and attempt.get('outcome'):
                last_identity = next(reversed(self.dispatch_identities))
                self.dispatch_identities[last_identity]['outcome'] = attempt.get('outcome')
        elif self.state == 'recording' and self.actual_dispatches == 0:
            self.latest_attempt = None
        self.last_effective = deepcopy(self.trajectory[-1]) if self.trajectory else None

    def _submit_like(self, control_ids):
        import re
        if not control_ids:
            return False
        control = self.current['controls'].get(control_ids[0]) or {}
        binding = control.get('binding') or {}
        label = (control.get('element') or {}).get('text') or ''
        return bool(binding.get('input_type') in ('submit', 'button') and (
            binding.get('tag') == 'button' or re.search(r'计算|計算|提交|生成|转换|轉換|换算|求解|搜索|calculate|compute|submit|convert|solve|search', label, re.I)))

    def _checkpoint_needed(self, step, control_ids, result, attempt):
        if self.state != 'recording':
            return False
        if attempt.get('outcome') in ('KNOWN_NO_EFFECT', 'EFFECT_NOT_VERIFIED', 'EFFECT_UNKNOWN'):
            return True
        if (result or {}).get('status') != 'ok':
            return True
        if self.dialogs and len(self.dialogs) > len(self._dialog_checkpointed):
            return True
        if step.get('action') == 'click' and self._submit_like(control_ids):
            return True
        if self._document_changed():
            return True
        remaining = self.plan['steps'][self.position:]
        if not remaining or all(row.get('action') in ('wait', 'scroll') for row in remaining):
            return True
        return False

    def _document_changed(self):
        return bool(self.latest_document_identity and self.current
                    and self.current['document_identity'] != self.latest_document_identity)

    def _checkpoint_reason(self, step, control_ids, attempt):
        if attempt.get('outcome') in ('KNOWN_NO_EFFECT', 'EFFECT_NOT_VERIFIED', 'EFFECT_UNKNOWN'):
            return 'action_not_established'
        if step.get('action') == 'click' and self._submit_like(control_ids):
            return 'submission_checkpoint'
        if self._document_changed():
            return 'navigation_checkpoint'
        return 'result_reading_or_plan_end'

    # ------------------------------------------------------------------ checkpoint

    def _branch_prompt(self, reason, feedback=None):
        state = load_json(self.current['evidence']['state']['path'])
        oid = self.current['observation_id']
        if oid not in self.region_registries:
            self.region_registries[oid] = region_registry(state)
            self.event('screenshot-regions', observation_id=oid,
                       regions=deepcopy(self.region_registries[oid]))
        self._dialog_checkpointed = list(self.dialogs)
        remaining = self.plan['steps'][self.position:]
        choices = list(DECISIONS)
        if not remaining:
            choices.remove('continue')
        payload = {'protocol': VERSION, 'phase': 'branch', 'attempt_id': self.attempt_id,
                   'system': SYSTEM_PROMPT,
                   'goal': self.frozen_goal, 'requirements': deepcopy(self.requirements),
                   'current_observation': oid, 'screenshots': [oid],
                   'regions': self.region_registries[oid],
                   'latest_attempt': _public_attempt(self.latest_attempt),
                   'last_effective_action': _public_effective(self.last_effective),
                   'confirmed_progress': [row.get('goal') for row in self.trajectory[-6:]],
                   'missing_requirements': [row['id'] for row in self.requirements
                                            if row['id'] not in (getattr(self, 'verified_requirement_ids', None) or [])],
                   'remaining_plan': [{'action': row.get('action'), 'purpose': row.get('purpose'),
                                       'target': deepcopy(row.get('target'))} for row in remaining],
                   'reason': reason, 'choices': choices, 'rules': BRANCH_RULES,
                   'tools': decision_tools(choices),
                   'progress': {'decisions_used': self.used['max_decisions'],
                                'effective_steps': len(self.trajectory),
                                'actual_dispatches': self.actual_dispatches}}
        if self.completion_feedback:
            payload['completion_feedback'] = deepcopy(self.completion_feedback)
        if feedback:
            payload['checkpoint_feedback'] = deepcopy(feedback)
        payload['_images'] = [self.current['evidence']['image']['path']]
        return payload

    async def _checkpoint(self, reason, feedback=None, *, executed=False):
        prompt = self._branch_prompt(reason, feedback)
        response = await self._decide(prompt)
        arguments = response.get('arguments') or {}
        decision, record = normalize_decision(arguments, prompt['choices'])
        self.event('screenshot-decision', reason=reason, decision=decision,
                   normalization=record, position=self.position,
                   plan_version=self.plan_version)
        key = object_sha256({'observation': self.current['observation_id'], 'reason': reason,
                             'decision': decision.get('decision'),
                             'remaining': self.plan['steps'][self.position:]})
        self.no_progress_keys[key] = self.no_progress_keys.get(key, 0) + 1
        if self.no_progress_keys[key] >= 2 and self.actual_dispatches == self.no_progress_dispatches.get(key, self.actual_dispatches):
            self._range_close('NO_PROGRESS_END', '同一事实与反馈下重复相同决策且无新证据，无进展结束')
            return
        self.no_progress_dispatches[key] = self.actual_dispatches
        choice = decision.get('decision')
        if choice == 'continue':
            if not self.plan['steps'][self.position:]:
                self.event('screenshot-decision-rejected', reason='continue_without_remaining_steps')
                return await self._checkpoint(reason, {'kind': 'CONTINUE_WITHOUT_STEPS',
                    'message': '剩余计划为空，不能continue；请complete、revise或give_up'})
            if feedback and feedback.get('kind') == 'REPEAT_SUBMISSION_WITHOUT_NEW_BASIS':
                basis = str(decision.get('new_basis') or '').strip()
                if not basis:
                    self.event('screenshot-decision-rejected', reason='repeat_without_new_basis')
                    return
                self._granted_new_basis = basis
                return
            if executed and self.position < len(self.plan['steps']):
                # continue确认剩余路径仍适用：越过已派发的当前步（含未证实效果），
                # 继续下一步；重试当前动作必须revise并给新依据。
                self.position += 1
            return
        if choice == 'revise':
            steps = decision.get('remaining_plan')
            if not steps:
                self.event('screenshot-decision-rejected', reason='empty_revision')
                return await self._checkpoint(reason, {'kind': 'EMPTY_REVISION',
                    'message': 'revise必须给出未执行尾部；直接结束用complete或give_up'})
            self.plan['steps'] = self.plan['steps'][:self.position] + steps
            self.plan_version += 1
            self.event('screenshot-plan-revision', version=self.plan_version,
                       position=self.position, steps=deepcopy(steps),
                       executed_preserved=self.position)
            return
        if choice == 'complete':
            checks, gaps = verify_completion(self, decision, self.requirements)
            if gaps:
                self.completion_feedback = {'kind': 'COMPLETION_EVIDENCE_GAPS', 'gaps': gaps,
                    'message': '完成申请缺证；在同一或历史观察中补引用，不重放已完成的输入与提交'}
                self.event('screenshot-completion-rejected', gaps=gaps)
                return
            self._complete(decision, checks, reason)
            return
        if choice == 'give_up':
            self._range_close('AGENT_GIVE_UP', 'give_up：' + str(decision.get('reason') or '当前无可行路径'))
            return
        self.event('screenshot-decision-rejected', reason='unknown_decision')

    def _complete(self, application, checks, reason):
        receipt = self.event('screenshot-completion', protocol=COMPLETION_VERSION,
            application=deepcopy(application), checks=deepcopy(checks),
            requirements=deepcopy(self.requirements), checkpoint_reason=reason)
        self.verified_requirement_ids = [row['id'] for row in self.requirements]
        self.goal_evidence = {'business_goal_status': 'VERIFIED', 'checks': checks,
                              'screenshot_completion': receipt,
                              'completion_protocol': COMPLETION_VERSION}
        self.completion_endpoint_basis = {'source': 'host_screenshot_completion',
            'completion': receipt, 'image': deepcopy(self.current['evidence']['image']),
            'finish_route': {'completion_origin': 'agent_complete',
                             'planned_steps': len(self.plan['steps']),
                             'executed_effective_steps': len(self.trajectory),
                             'remaining_planned_steps': max(0, len(self.plan['steps']) - self.position)}}
        self.event('goal-evidence', **deepcopy(self.goal_evidence))
        self._range_close(READY_ENDING, '原目标事项均由可见证据逐项绑定并核验')

    # ------------------------------------------------------------------ helpers

    def _range_close(self, kind, reason, **kwargs):
        if kind == READY_ENDING and self.completion_endpoint_basis is None:
            raise ValueError('COMPLETE_ENDING_REQUIRES_VERIFIED_COMPLETION')
        super()._range_close(kind, reason, **kwargs)
        if kind in RAW_ONLY_ENDINGS:
            self.strategy_end_reason = ('unsuitable' if kind == 'UNSUITABLE_TASK'
                                        else 'no_progress' if kind == 'NO_PROGRESS_END' else 'no_path')


def file_sha_of(path):
    from .batch_core import file_sha
    return file_sha(path)


def _stripped(prompt):
    return {key: value for key, value in prompt.items() if key not in ('system', 'tools', '_images', '_history')}


def _public_attempt(attempt):
    if not attempt:
        return None
    return {key: attempt.get(key) for key in
            ('number', 'action', 'purpose', 'dispatched', 'effective', 'outcome', 'reason')}


def _public_effective(row):
    if not row:
        return None
    return {'operation_id': row.get('operation_id'), 'action': row.get('action'),
            'goal': row.get('goal') or row.get('semantic_goal'),
            'after_observation_id': row.get('after_observation_id')}


def describe(goal):
    from .react_session import describe_goal
    return describe_goal(goal)
