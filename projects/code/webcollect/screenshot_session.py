"""策略 2 会话：共享引擎核心之上，替换决策循环。

The session reuses the entry observation, trusted capture, atomic dispatch,
effect verification, business-attempt journal and raw close-out from the shared
engine core (session_core.RawSessionCore), never the 策略 1 decision loop.
What changes is the decision loop: one first-round submit_plan, deterministic
execution of planned steps, model checkpoints only at business events
(submit-like clicks, navigation, dialogs, binding/identity refusals,
result reading or plan exhaustion) and a verified `complete`.
"""
import asyncio
from copy import deepcopy
import json
import time

from .batch_core import OutcomeUnknown, SessionGLMCallLimit, BudgetStop, load_json
from .planning import object_sha256
from . import collection_strategy as _cs
from .screenshot_plan import (SYSTEM_PROMPT,
    FIRST_RULES, BRANCH_RULES, BUSINESS_MINIMUM, PREFERRED_MAXIMUM, NON_BUSINESS_ACTIONS,
    DECISIONS, READY_ENDING, RAW_ONLY_ENDINGS, NO_PROGRESS_STALL_LIMIT, submit_plan_tools,
    decision_tools, normalize_submit_plan, normalize_decision,
    first_plan_admission, business_actions, verify_completion)
from .screenshot_observation import controls_projection, region_registry
from .session_core import RawSessionCore, ReactStop
from .screenshot_execution import bind_target, react_step


class ScreenshotPlanSession(RawSessionCore):
    """策略 2 execution: screenshot checkpoints and remaining-plan revision."""

    def _boundary_system_prompt_sha256(self):
        # 策略 2 records its own frozen submit-plan boundary, not the native
        # tool loop's system prompt.
        return object_sha256(SYSTEM_PROMPT)

    def _boundary_tool_schema_sha256(self, contracted):
        # Same: the wire contract is submit_plan_tools for the first round and
        # per-checkpoint decision_tools, recorded here as the session boundary.
        return object_sha256(submit_plan_tools(self.task['fragment']['allowed_actions']))

    def __init__(self, task, directory, choose, page, **kwargs):
        super().__init__(task, directory, choose, page, **kwargs)
        self.plan = None
        self.frozen_goal = None
        self.requirements = []
        self.position = 0
        self.plan_event = None
        self.initial_feedback = None
        self.completion_feedback = None
        self.latest_attempt = None
        self.last_effective = None
        self.dispatch_identities = {}
        self.no_progress_keys = {}
        self.no_progress_dispatches = {}
        self.region_registries = {}
        # Only observations whose image was carried by a successful request can
        # support completion. The same set is rebuilt from sealed model intents.
        self.provided_observations = set()
        self.latest_document_identity = None
        self._dialog_checkpointed = []
        self._granted_new_basis = None
        self.completion_endpoint_basis = None
        self.strategy_end_reason = None
        self.extra_ready_endings = (READY_ENDING,)
        self._stall_marker = None
        self._stall_count = 0

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
            # 用户停止立即生效；只有明确的内部硬截止可继续既有封存收尾。
            internal_deadline = bool(error.args and error.args[0] == 'consumer_session_hard_deadline')
            self.strategy_end_reason = 'unknown' if internal_deadline else 'user_stopped'
            self.stop_reason, self.stop_summary = 'blocked', '会话被取消，保留已执行内容'
            self.unknown = True
            self.failure_class = 'interrupted'
            self.state = 'closed_by_host'
            self._runlog('cancelled', internalDeadline=internal_deadline,
                effectiveSteps=len(self.trajectory), unknown=True)
            if not internal_deadline or not self.host_limits or time.monotonic() < (
                    self.host_limits['started_monotonic'] + self.host_limits['hard_seconds']):
                self._close()
                raise
        except BaseException as error:
            stop = ReactStop('blocked', type(error).__name__ + ': ' + str(error), 'program')
            self.stop_reason, self.stop_summary = 'blocked', str(stop)
            self.failure_class = 'program'
            self.state = 'closed_by_host'
        self.host_failure = stop is not None
        receipt = self._close()
        self._runlog('session_end', stopReason=self.stop_reason,
            effectiveSteps=len(self.trajectory), actualActions=self.actual_dispatches,
            unknown=bool(self.unknown), failureClass=self.failure_class)
        return self._strategy_summary(receipt)

    def _strategy_summary(self, receipt):
        ending = getattr(self, 'collection_ending', None) or {}
        summary = {'host_failure': self.host_failure, 'stop_reason': self.stop_reason,
                'stop_summary': self.stop_summary,
                'strategy': {'id': _cs.STRATEGY_SCREENSHOT_PLAN},
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
        summary['strategy_result'] = _cs.strategy_result(self.task, summary=summary, raw_receipt=receipt)
        return summary

    # ------------------------------------------------------------------ decide

    async def _decide(self, prompt):
        """One model call at a checkpoint; UNKNOWN and stop semantics shared."""
        observation_ids = list(dict.fromkeys(prompt.get('screenshots') or []))
        expected_images = [self.observation_records[oid]['evidence']['image']['path']
                           for oid in observation_ids if oid in self.observation_records]
        if (not observation_ids or len(expected_images) != len(observation_ids)
                or list(prompt.get('_images') or []) != expected_images):
            raise ReactStop('blocked', '截图观察编号与实际请求图片不一致', 'program')
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
        self.provided_observations.update(observation_ids)
        self.event('model-observations-provided', model_intent=self._last_model_intent,
                   observation_ids=observation_ids)
        return response

    # ------------------------------------------------------------------ first plan

    def _fixed_goal(self):
        objective = ((self.task.get('fragment') or {}).get('session_objective') or {}).get('objective') or {}
        return str(objective.get('description') or describe(self.requested_goal) or '').strip()

    def _first_prompt(self):
        state = load_json(self.current['evidence']['state']['path'])
        oid = self.current['observation_id']
        if oid not in self.region_registries:
            self.region_registries[oid] = region_registry(state)
            self.event('screenshot-regions', observation_id=oid,
                       regions=deepcopy(self.region_registries[oid]))
        payload = {'phase': 'first', 'attempt_id': self.attempt_id,
                   'system': SYSTEM_PROMPT,
                   'goal': self._fixed_goal() or self.requested_goal,
                   'requested_goal': deepcopy(self.requested_goal),
                   'session_objective': deepcopy((self.task['fragment'].get('session_objective') or {}).get('objective')),
                   'current_observation': oid, 'screenshots': [oid],
                   'page': {'url': self.current['url'],
                            'title': (state.get('title') or '')[:120],
                            'visible_excerpt': (state.get('visible_text') or '')[:600]},
                   'regions': self.region_registries[oid],
                   'controls': controls_projection(self.current, self.task['fragment']['allowed_actions']),
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
        self.event('screenshot-plan-normalized', phase='first',
                   normalization=record, plan=plan)
        ok, feedback = first_plan_admission(plan)
        fixed_goal = self._fixed_goal()
        if ok and feedback['kind'] == 'accepted':
            if fixed_goal and plan.get('goal') != fixed_goal:
                ok = False
                feedback = {'kind': 'FIXED_GOAL_MISMATCH', 'field_paths': ['goal'], 'dispatched': False,
                            'expected_goal': fixed_goal,
                            'message': '固定requested_goal/session_objective必须原样继承，不得替换、缩小或改写'}
            elif not fixed_goal and not str(plan.get('goal') or '').strip():
                ok = False
                feedback = {'kind': 'MISSING_GOAL', 'field_paths': ['goal'], 'dispatched': False,
                            'message': '自由目标首轮必须依据首屏给出具体自然目标'}
        if not ok:
            if self.initial_feedback is None:
                # 同一观察下的有界纠正：给精确反馈再请求一次，不派发任何动作。
                self.initial_feedback = feedback
                self.event('screenshot-plan-rejected', feedback=feedback, dispatched=False)
                if getattr(self, 'runlog', None) is not None:
                    self._runlog('plan_rejected', observationId=self.current['observation_id'],
                        reason=feedback.get('kind'), retriable=True)
                return
            self.event('screenshot-plan-rejected', feedback=feedback, dispatched=False, final=True)
            if getattr(self, 'runlog', None) is not None:
                self._runlog('plan_rejected', observationId=self.current['observation_id'],
                    reason=feedback.get('kind'), retriable=False)
            self._range_close('UNSUITABLE_TASK', feedback['message'])
            return
        if feedback['kind'] == 'unsuitable':
            self.event('screenshot-plan-unsuitable', reason=feedback['unsuitable'])
            if getattr(self, 'runlog', None) is not None:
                self._runlog('plan_rejected', observationId=self.current['observation_id'],
                    reason='unsuitable', retriable=False)
            self._range_close('UNSUITABLE_TASK', '模型报告自然路径不适合：' + str(feedback['unsuitable'].get('reason') or ''))
            return
        requirements = plan.get('requirements') or []
        if not requirements:
            self.initial_feedback = self.initial_feedback or {
                'kind': 'missing_requirements', 'field_paths': ['requirements'],
                'message': '缺少完成事项requirements；每项一条原目标必须看到的结果'}
            self.event('screenshot-plan-rejected', feedback=self.initial_feedback, dispatched=False)
            if getattr(self, 'runlog', None) is not None:
                self._runlog('plan_rejected', observationId=self.current['observation_id'],
                    reason='missing_requirements', retriable=True)
            return
        self.frozen_goal = fixed_goal or plan['goal']
        if self.working_goal is None:
            self.working_goal = self.frozen_goal
        self.requirements = [{'id': row['id'], 'description': row['description']} for row in requirements]
        self.plan = {'steps': plan['steps']}
        self.position = 0
        self.initial_feedback = None
        self.plan_event = self.event('screenshot-plan', phase='first',
            goal=self.frozen_goal, requested_goal=deepcopy(self.requested_goal),
            session_objective=deepcopy((self.task['fragment'].get('session_objective') or {}).get('objective')),
            requirements=deepcopy(self.requirements), steps=deepcopy(self.plan['steps']), admission=feedback)
        if getattr(self, 'runlog', None) is not None:
            self._runlog('plan_accepted', observationId=self.current['observation_id'],
                plannedSteps=len(self.plan['steps']), requirements=len(self.requirements))

    # ------------------------------------------------------------------ execution

    TARGET_REQUIRED_ACTIONS = ('click', 'double_click', 'right_click', 'type', 'select', 'drag')

    def _bind_target(self, step):
        """Bind a semantic target to the unique current control, if any."""
        target = step.get('target')
        if not target:
            return None
        cited = target.get('control')
        if cited:
            # Host-issued current-frame id from the controls list: the identity
            # is unique by construction; visibility still binds against the
            # same observation as a semantic target would.
            control = (self.current.get('controls') or {}).get(cited) or {}
            if (control.get('element') or {}).get('visible') is True:
                return [cited]
            return []
        return bind_target(self.current, target, self.observation_records)

    def _action_identity(self, step, control_ids, state):
        binding = {}
        if control_ids:
            control = self.current['controls'].get(control_ids[0]) or {}
            binding = control.get('binding') or {}
        return object_sha256({
            'action': step.get('action'),
            'target': (step.get('target') or {}).get('text') or (step.get('target') or {}).get('control'),
            'form': binding.get('form_selector'),
            'document': state.get('document_identity'),
            'value': step.get('value'), 'keys': step.get('keys'),
            'direction': step.get('direction'),
            'target_state': (state.get('document_identity'),
                             (step.get('target') or {}).get('text') or (step.get('target') or {}).get('control'))})

    def _repeat_guard(self, step, control_ids, state, new_basis):
        """Only real submissions need a new basis; observation actions may repeat."""
        identity = self._action_identity(step, control_ids, state)
        action = step.get('action')
        submit = ((action == 'click' and self._submit_like(control_ids))
                  or (action == 'hotkey' and 'enter' in str(step.get('keys') or []).lower()))
        if not submit:
            return None, identity
        previous = self.dispatch_identities.get(identity)
        if previous is None:
            return None, identity
        changed_state = previous.get('state_sha256') != object_sha256(state)
        not_dispatched = previous.get('dispatched') is False
        if not_dispatched or (new_basis and changed_state):
            return None, identity
        return {'kind': 'REPEAT_SUBMISSION_WITHOUT_NEW_BASIS',
                'message': ('同一输入、同一页面状态下该提交已派发过；结果未进视口请先观察（滚动/等待），'
                            '重试必须在new_basis说明修正了输入、重新定位了目标或页面明确反馈'),
                'previous': {key: previous.get(key) for key in ('operation_id', 'outcome', 'at')},
                'new_basis_required': True}, identity

    def _react_step(self, step, control_ids):
        return react_step(step, control_ids,
                          lambda endpoint: self._bind_target({'target': endpoint}))

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
            # 成功动作已在上方推进游标；只有未建立效果的已派发动作在选择
            # continue时才需要越过当前步，避免每个成功检查点跳过下一步。
            await self._checkpoint(self._checkpoint_reason(step, matches or [], attempt),
                                   executed=new_attempt and not advanced)

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
        from .result_execution import is_submission
        if not control_ids:
            return False
        control = self.current['controls'].get(control_ids[0]) or {}
        return is_submission('click', {}, control.get('binding') or {}, control.get('element') or {})

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
        payload = {'phase': 'branch', 'attempt_id': self.attempt_id,
                   'system': SYSTEM_PROMPT,
                   'goal': self.frozen_goal, 'requirements': deepcopy(self.requirements),
                   'requested_goal': deepcopy(self.requested_goal),
                   'session_objective': deepcopy((self.task['fragment'].get('session_objective') or {}).get('objective')),
                   'current_observation': oid, 'screenshots': [oid],
                   'visual_evidence': {'scope': 'current_viewport', 'observation': oid,
                                       'image_sha256': self.current['evidence']['image']['sha256'],
                                       'regions': deepcopy(self.region_registries[oid])},
                   'regions': self.region_registries[oid],
                   'controls': controls_projection(self.current, self.task['fragment']['allowed_actions']),
                   'allowed_actions': list(self.task['fragment']['allowed_actions']),
                   'latest_attempt': _public_attempt(self.latest_attempt),
                   'last_effective_action': _public_effective(self.last_effective),
                   'current_actions': [_public_effective(row) for row in self.trajectory[-8:]],
                   'confirmed_progress': [row.get('goal') for row in self.trajectory[-6:]],
                   'missing_requirements': [row['id'] for row in self.requirements
                                            if row['id'] not in (getattr(self, 'verified_requirement_ids', None) or [])],
                   'remaining_plan': [{'action': row.get('action'), 'purpose': row.get('purpose'),
                                       'target': deepcopy(row.get('target'))} for row in remaining],
                   'next_checkpoint': {'reason': reason, 'remaining_steps': len(remaining),
                                       'allowed_decisions': list(choices)},
                   'reason': reason, 'choices': choices, 'rules': BRANCH_RULES,
                   'tools': decision_tools(choices, self.task['fragment']['allowed_actions'],
                                           sorted(self.provided_observations | {oid})),
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
        allowed_actions = self.task['fragment']['allowed_actions']
        decision, record = normalize_decision(arguments, prompt['choices'], allowed_actions)
        self.event('screenshot-decision', reason=reason, decision=decision,
                   normalization=record, position=self.position)
        if getattr(self, 'runlog', None) is not None:
            self._runlog('checkpoint', observationId=self.current['observation_id'],
                decision=decision.get('decision'), reason=reason, position=self.position,
                effectiveSteps=len(self.trajectory))
        # A different answer, citation, new_basis or revised tail is new work,
        # not a repeated no-progress decision. Only the whole identical decision
        # on the same observation and feedback is bounded.
        key = object_sha256({'observation': self.current['observation_id'], 'reason': reason,
                             'decision': decision, 'remaining': self.plan['steps'][self.position:],
                             'checkpoint_feedback': feedback,
                             'completion_feedback': self.completion_feedback})
        self.no_progress_keys[key] = self.no_progress_keys.get(key, 0) + 1
        if self.no_progress_keys[key] >= 2 and self.actual_dispatches == self.no_progress_dispatches.get(key, self.actual_dispatches):
            self._range_close('NO_PROGRESS_END', '同一事实与反馈下重复相同完整决策且无新证据，无进展结束')
            return
        self.no_progress_dispatches[key] = self.actual_dispatches
        # Independent bound: reworded revises or repeated completion attempts with
        # neither a new dispatch nor plan-cursor progress are a stall, even when
        # each decision's content differs.
        stall_marker = (self.actual_dispatches, self.position)
        if stall_marker == self._stall_marker:
            self._stall_count += 1
        else:
            self._stall_marker = stall_marker
            self._stall_count = 0
        if self._stall_count >= NO_PROGRESS_STALL_LIMIT:
            self.event('screenshot-no-progress-stall', dispatches=self.actual_dispatches,
                       position=self.position, stall_count=self._stall_count)
            self._range_close('NO_PROGRESS_END',
                              '连续检查点无新派发且计划游标无进展，无进展结束')
            return
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
            self.completion_feedback = None
            self.event('screenshot-plan-revision',
                       position=self.position, steps=deepcopy(steps),
                       executed_preserved=self.position)
            return
        if choice == 'complete':
            checks, gaps = verify_completion(self, decision, self.requirements)
            if gaps:
                verified_now = [row['requirement_id'] for row in checks if row.get('status') == 'VERIFIED']
                if verified_now:
                    # 已核验的部分证据保留：补证只需针对剩余缺项，不重放已完成事项。
                    self.verified_requirement_ids = sorted(set(
                        getattr(self, 'verified_requirement_ids', None) or []) | set(verified_now))
                self.completion_feedback = {'kind': 'COMPLETION_EVIDENCE_GAPS', 'gaps': gaps,
                    'verified_requirement_ids': list(getattr(self, 'verified_requirement_ids', None) or []),
                    'verified': [{'requirement_id': row['requirement_id'],
                                  'observed': str(row.get('observed_visible_text') or '')[:120]}
                                 for row in checks if row.get('status') == 'VERIFIED'],
                    'message': '完成申请缺证；已证实事项无需重复举证，只需为缺项在同一或历史观察中补引用，不重放已完成的输入与提交'}
                self.event('screenshot-completion-rejected', gaps=gaps, dispatched=False,
                           verified_requirement_ids=list(getattr(self, 'verified_requirement_ids', None) or []))
                if getattr(self, 'runlog', None) is not None:
                    self._runlog('completion_gaps', observationId=self.current['observation_id'],
                        gaps=[gap.get('kind') for gap in gaps],
                        verifiedRequirementIds=list(getattr(self, 'verified_requirement_ids', None) or []))
                # Stay at this checkpoint. Returning to the main loop could
                # execute an obsolete remaining action before the supplement.
                return await self._checkpoint(reason, self.completion_feedback)
            self.completion_feedback = None
            self._complete(decision, checks, reason)
            return
        if choice == 'give_up':
            self._range_close('AGENT_GIVE_UP', 'give_up：' + str(decision.get('reason') or '当前无可行路径'))
            return
        self.event('screenshot-decision-rejected', reason='unknown_decision', dispatched=False)
        return await self._checkpoint(reason, {'kind': 'UNKNOWN_DECISION',
            'message': '请使用当前choices中的decision；缺证时complete补证或give_up，不执行旧剩余动作'})

    def _complete(self, application, checks, reason):
        receipt = self.event('screenshot-completion',
            application=deepcopy(application), checks=deepcopy(checks),
            goal=self.frozen_goal, requested_goal=deepcopy(self.requested_goal),
            session_objective=deepcopy((self.task['fragment'].get('session_objective') or {}).get('objective')),
            requirements=deepcopy(self.requirements), checkpoint_reason=reason)
        self.verified_requirement_ids = [row['id'] for row in self.requirements]
        self.goal_evidence = {'business_goal_status': 'VERIFIED', 'checks': checks,
                              'goal': self.frozen_goal, 'requested_goal': deepcopy(self.requested_goal),
                              'session_objective': deepcopy((self.task['fragment'].get('session_objective') or {}).get('objective')),
                              'screenshot_completion': receipt}
        self.completion_endpoint_basis = {'source': 'host_screenshot_completion',
            'completion': receipt, 'image': deepcopy(self.current['evidence']['image']),
            'finish_route': {'completion_origin': 'agent_complete',
                             'planned_steps': len(self.plan['steps']),
                             'executed_effective_steps': len(self.trajectory),
                             'remaining_planned_steps': max(0, len(self.plan['steps']) - self.position)}}
        self.event('goal-evidence', **deepcopy(self.goal_evidence))
        if getattr(self, 'runlog', None) is not None:
            self._runlog('goal_verified', observationId=self.current['observation_id'],
                requirements=len(self.requirements), effectiveSteps=len(self.trajectory))
        self._range_close(READY_ENDING, '原目标事项均由可见证据逐项绑定并核验')

    # ------------------------------------------------------------------ helpers

    def _range_close(self, kind, reason, **kwargs):
        if kind == READY_ENDING and self.completion_endpoint_basis is None:
            raise ValueError('COMPLETE_ENDING_REQUIRES_VERIFIED_COMPLETION')
        super()._range_close(kind, reason, **kwargs)
        self._runlog('range_close', kind=kind, reason=str(reason)[:200],
            unknown=bool(getattr(self, 'unknown', False)))
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
    from .session_core import describe_goal
    return describe_goal(goal)
