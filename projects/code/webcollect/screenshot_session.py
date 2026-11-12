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
from datetime import datetime, timezone

from .batch_core import OutcomeUnknown, SessionGLMCallLimit, BudgetStop, load_json
from .planning import object_sha256
from . import collection_strategy as _cs
from .screenshot_plan import (SYSTEM_PROMPT,
    FIRST_RULES, BRANCH_RULES, BUSINESS_MINIMUM, PREFERRED_MAXIMUM, NON_BUSINESS_ACTIONS,
    DECISIONS, READY_ENDING, RAW_ONLY_ENDINGS, NO_PROGRESS_STALL_LIMIT, submit_plan_tools,
    decision_tools, decision_schema, normalize_submit_plan, normalize_decision,
    first_plan_admission, business_actions, verify_completion, verify_final_presentation, _verify_input, narrative_grounding_gaps, supported_actions, evidence_route_gaps, first_frame_redundancy, _state_for_observation)
from .screenshot_observation import (controls_projection, interaction_affordances, body_element_ids,
    region_registry, prepare_visuals, verify_visuals, crop_visual)
from .session_core import RawSessionCore, ReactStop
from .screenshot_execution import bind_target, react_step, bind_plan_targets, resolve_control


class ScreenshotPlanSession(RawSessionCore):
    """策略 2 execution: screenshot checkpoints and remaining-plan revision."""

    def _observation_policy(self):
        from . import screenshot_native_observation
        return screenshot_native_observation

    def _compile_action(self, step):
        from .screenshot_execution import compile_step
        return compile_step(self.task, self.page_urls, step, self.current,
                            navigation_count=self.navigation_count)

    def _atomic_effect(self, *args, **kwargs):
        from .screenshot_effect import atomic_effect
        return atomic_effect(*args, **kwargs)

    def _boundary_system_prompt_sha256(self):
        # 策略 2 records its own frozen submit-plan boundary, not the native
        # tool loop's system prompt.
        return object_sha256(SYSTEM_PROMPT)

    def _boundary_tool_schema_sha256(self, contracted):
        # Same: the wire contract is submit_plan_tools for the first round and
        # per-checkpoint decision_tools, recorded here as the session boundary.
        return object_sha256(submit_plan_tools(self._allowed_actions(), fixed_goal=self._fixed_goal() or None))

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
        self.body_element_ids = {}
        self.provided_control_observations = set()
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
        self.host_input_proofs = []
        self.first_route_status = "original"
        self.verified_answers = {}
        self.verified_checks = {}
        self.provided_visual_refs = {}
        self._inspection_visual = None
        self.verified_requirement_ids = []
        self._presentation_step_pending = False
        # 完成缺项的稳定投影（kind, requirement_id）：随最近一次 complete 核验
        # 或 goal_ready 下接受的展示定位 revise 更新，纳入停滞核算；缺项减少算
        # 真实展示进展，缺项不变的重复 complete 仍有界结束。
        self._completion_gap_projection = ()
        # Evidence-route execution state (SSD 2026-11-12): the original first-plan
        # step number behind every current plan position (None for revised tail
        # steps), host-side re-anchors after a revise, the planned ending frame
        # position and the observation captured right after each executed step.
        self.route_map = []
        self.route_overrides = {}
        self.final_presentation_override = None
        self.route_frames = {}
        # A previously seen key frame may be reattached once per pending
        # requirement after it leaves the viewport; never repeat it every call.
        self.history_supplement_keys = set()

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

    def _body_ids(self):
        """Content-vs-chrome classification of the current observation's tree."""
        oid = self.current['observation_id']
        if oid not in self.body_element_ids:
            self.body_element_ids[oid] = body_element_ids(
                load_json(self.current['evidence']['state']['path']))
        return self.body_element_ids[oid]

    def _controls(self):
        """The one projection behind both the prompt list and the marked image.

        Both must agree: the yellow badge numbers drawn on the viewport are the
        `number` values the model cites, so a second, differently ordered
        projection would bind a cited number to another control.
        """
        rows = controls_projection(self.current, self._allowed_actions(),
                                   body_ids=self._body_ids())
        oid = self.current['observation_id']
        if oid not in self.provided_control_observations:
            self.provided_control_observations.add(oid)
            self.event('screenshot-controls', observation_id=oid,
                       provided_control_ids=deepcopy(self.current['provided_control_ids']),
                       provided_control_numbers=deepcopy(self.current['provided_control_numbers']),
                       interaction_affordances=interaction_affordances(rows, self._body_ids()))
        return rows

    async def _decide(self, prompt):
        """One model call at a checkpoint; UNKNOWN and stop semantics shared.

        The current clear viewport is always first. When a still-unmet
        requirement's route evidence step already executed but its frame was
        never provided, one historical key frame is attached (SSD 3.3): evidence
        only — its controls and coordinates can never dispatch an action.
        """
        self._controls()
        visuals = await prepare_visuals(self.current, self.root, self.page,
                                        first=prompt.get('phase') == 'first')
        available = list(visuals)
        if self._inspection_visual and self._inspection_visual['observation_id'] == self.current['observation_id']:
            if not any(row['ref'] == self._inspection_visual['ref'] for row in available):
                available.append(self._inspection_visual)
        limit = int(getattr(self.choose, 'max_images', len(available)))
        if limit < 1:
            raise ReactStop('blocked', '模型图片配置至少须允许一张清晰视口图', 'program')
        key_visual = await self._key_evidence_visual()
        if key_visual is not None and not any(row['ref'] == key_visual['ref'] for row in available):
            if limit < 2:
                self.event('screenshot-history-supplement', observation_id=key_visual['observation_id'],
                           requirement_id=key_visual.get('requirement_id'), dropped='IMAGE_LIMIT',
                           dispatched=False)
                prompt['history_supplement_unavailable'] = {'kind': 'IMAGE_LIMIT',
                    'configured_images': limit, 'required_images': 2,
                    'requirement_id': key_visual.get('requirement_id'),
                    'observation': key_visual['observation_id'],
                    'message': '当前图与必要历史图不能同时容纳；未提供该历史图，不得声称已经看过。可按正常导航重显证据或如实结束'}
                key_visual = None
            else:
                available.append(key_visual)
        viewport = next(row for row in available if row['scope'] == 'viewport'
                        and row['observation_id'] == self.current['observation_id'])

        def priority(row):
            if row is viewport:
                return (0, '')
            if row is self._inspection_visual:
                return (1, row['ref'])
            if row.get('observation_id') != self.current['observation_id']:
                return (2, row['ref'])
            return (3, row['ref'])

        visuals = sorted(available, key=priority)[:limit]
        prompt['_images'] = [row['path'] for row in visuals]
        prompt['visual_evidence'] = deepcopy(visuals)
        observation_ids = list(dict.fromkeys(row['observation_id'] for row in visuals))
        prompt['screenshots'] = observation_ids
        if observation_ids[0] != self.current['observation_id']:
            raise ReactStop('blocked', '当前清晰视口图必须提供', 'program')
        if len(observation_ids) > 1 and 'choices' in prompt:
            # A historical key frame is citable in the very request that carries
            # it; the host-side response validator rebuilds its enum after the
            # successful request, so only the wire tools need this extension.
            prompt['tools'] = decision_tools(prompt['choices'], prompt.get('allowed_actions'),
                                             sorted(self._referenceable_observations() | set(observation_ids)))
        provided_paths = []
        for oid in observation_ids:
            provided_paths.extend(verify_visuals(self.observation_records[oid],
                                                 [v for v in visuals if v['observation_id'] == oid]))
        if provided_paths != prompt['_images']:
            raise ReactStop('blocked', '模型图片与已核验视觉证据不一致', 'program')
        if key_visual is not None:
            self.event('screenshot-history-supplement', observation_id=key_visual['observation_id'],
                       requirement_id=key_visual.get('requirement_id'), scheduled=True,
                       reprovided=key_visual['observation_id'] in self.provided_observations,
                       dispatched=False)
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
        self.provided_visual_refs.update({visual['ref']: deepcopy(visual) for visual in visuals})
        self.provided_observations.update(observation_ids)
        if key_visual is not None:
            self.event('screenshot-history-supplement', observation_id=key_visual['observation_id'],
                requirement_id=key_visual.get('requirement_id'), provided=True,
                model_intent=self._last_model_intent, dispatched=False)
            # Consume the one-shot supplement only after a successful response;
            # an UNKNOWN/failed request must not silently lose its evidence.
            self.history_supplement_keys.add((
                key_visual['requirement_id'], key_visual['observation_id']))
        self.event('model-observations-provided', model_intent=self._last_model_intent,
                   observation_ids=observation_ids)
        return response

    # ------------------------------------------------------------------ first plan

    def _fixed_goal(self):
        objective = ((self.task.get('fragment') or {}).get('session_objective') or {}).get('objective') or {}
        return str(objective.get('description') or describe(self.requested_goal) or '').strip()

    def _allowed_actions(self):
        return supported_actions(self.task['fragment']['allowed_actions'])

    def _session_facts(self, state):
        """One factual projection for first planning and every checkpoint."""
        from .screenshot_effect import input_facts
        observed_urls = {row.get('url') for row in self.observation_records.values()}
        return {'current_url': self.current['url'],
                'page_directory': [{'page_id': f'p{index}', 'url': url,
                                    'observed': url in observed_urls}
                                   for index, url in enumerate(self.page_urls)],
                'current_inputs': {cid: {k: v for k, v in row.items() if k != 'identity'}
                                   for cid, row in input_facts(state).items()},
                'known_business_state': self._known_business_inputs(state),
                'historical_evidence': self._historical_evidence(),
                'latest_attempt': _public_attempt(self.latest_attempt),
                'action_facts': [_public_effective(row) for row in self.trajectory[-8:]],
                'last_effective_action': _public_effective(self.last_effective),
                'confirmed_progress': self._public_confirmed_progress(),
                'candidate_results': self._candidate_results(),
                'candidate_content': self._candidate_content(),
                'first_route_status': self.first_route_status,
                'missing_requirements': [row['id'] for row in self.requirements
                                         if row['id'] not in self.verified_answers]}

    def _first_prompt(self):
        state = load_json(self.current['evidence']['state']['path'])
        oid = self.current['observation_id']
        if oid not in self.region_registries:
            self.region_registries[oid] = region_registry(state)
            self.event('screenshot-regions', observation_id=oid,
                       regions=deepcopy(self.region_registries[oid]))
        controls = self._controls()
        payload = {'phase': 'first', 'attempt_id': self.attempt_id,
                   'system': SYSTEM_PROMPT,
                   'goal': self._fixed_goal() or self.requested_goal,
                   'requested_goal': _public_step(self.requested_goal),
                   'session_objective': _public_step((self.task['fragment'].get('session_objective') or {}).get('objective')),
                   'current_observation': oid, 'screenshots': [oid],
                   'page': {'url': self.current['url'],
                            'title': (state.get('title') or '')[:120],
                            'visible_excerpt': (state.get('visible_text') or '')[:600]},
                   'regions': self.region_registries[oid],
                   'controls': controls,
                   'interaction_affordances': interaction_affordances(controls, self._body_ids()),
                   'allowed_actions': self._allowed_actions(),
                   'rules': FIRST_RULES,
                   'planning_range': {'minimum': BUSINESS_MINIMUM,
                                      'preferred_maximum': PREFERRED_MAXIMUM, 'maximum': None,
                                      'note': '至少5个必要业务动作，优先5–8步，无硬上限；wait不计业务动作'},
                   'tools': submit_plan_tools(self._allowed_actions(), fixed_goal=self._fixed_goal() or None),
                   'progress': {'decisions_used': self.used['max_decisions'],
                                'effective_steps': len(self.trajectory),
                                'actual_dispatches': self.actual_dispatches}}
        payload.update(self._session_facts(state))
        if self.initial_feedback:
            payload['first_plan_feedback'] = deepcopy(self.initial_feedback)
        payload['_images'] = [self.current['evidence']['image']['path']]
        return payload

    def _frame_text(self):
        """当前观察的可见文本，用于机械校验计划叙述是否落在本帧。"""
        return load_json(self.current['evidence']['state']['path']).get('visible_text') or ''

    def _bind_targets_feedback(self, plan):
        gaps, transforms = [], []
        rows = [(f'steps[{i}]', row) for i, row in enumerate(plan.get('steps', []))]
        rows += [(f'requirements[{i}]', row) for i, row in enumerate(plan.get('requirements', []))
                 if row.get('kind') == 'input']
        for path, row in rows:
            notes = []
            try:
                bind_plan_targets({'steps': [row]}, self.current,
                    self.current.get('provided_control_ids', []), normalization=notes)
            except ValueError as error:
                gaps.append({'kind': 'TARGET_BINDING_INVALID', 'field_paths': [path + '.target'],
                             'message': path + ': ' + str(error), 'dispatched': False})
            transforms.extend({'path': path, **note} for note in notes)
        if transforms:
            self.event('screenshot-target-normalized', transforms=transforms)
        return gaps

    async def _first_plan_round(self):
        prompt = self._first_prompt()
        response = await self._decide(prompt)
        arguments = response.get('arguments') or {}
        plan, record = normalize_submit_plan(arguments, self._allowed_actions())
        self.event('screenshot-plan-normalized', phase='first',
                   normalization=record, plan=plan)
        fixed_goal = self._fixed_goal()
        if not fixed_goal and plan.get('goal'):
            from .task_instruction import generated_instruction
            formatted = generated_instruction(plan['goal'])
            if formatted != plan['goal']:
                self.event('screenshot-generated-goal-formatted', original=plan['goal'], goal=formatted)
                plan['goal'] = formatted
        if fixed_goal and not plan.get('unsuitable'):
            # Keep the wire/normalized plan above intact; the host owns this
            # immutable goal and never asks the model to reproduce its wording.
            plan = deepcopy(plan)
            plan['goal'] = fixed_goal
            self.event('screenshot-plan-goal-bound', goal=fixed_goal, source='host_fixed_goal')
        ok, feedback = first_plan_admission(
            plan, goal=fixed_goal or str(plan.get('goal') or ''))
        if ok and feedback['kind'] == 'accepted':
            if not fixed_goal and not str(plan.get('goal') or '').strip():
                ok = False
                feedback = {'kind': 'MISSING_GOAL', 'field_paths': ['goal'], 'dispatched': False,
                            'message': '自由目标首轮必须依据首屏给出具体自然目标'}
        # Semantic correction has the same one-reply budget as field repair:
        # report all independently checkable defects in that reply.
        semantic_gaps = [] if ok else [feedback]
        if feedback['kind'] not in ('PLAN_FIELDS_INVALID', 'unsuitable'):
            route_gaps = evidence_route_gaps(plan, self)
            if route_gaps:
                semantic_gaps.append({'kind': 'EVIDENCE_ROUTE_INVALID',
                    'message': '；'.join(route_gaps), 'dispatched': False})
            semantic_gaps.extend(self._bind_targets_feedback(plan))
            grounding = narrative_grounding_gaps(plan.get('steps'), self._frame_text(),
                                                 fixed_goal or str(plan.get('goal') or ''))
            if grounding:
                semantic_gaps.append({'kind': 'RATIONALE_NOT_GROUNDED', 'field_paths': ['steps'],
                    'gaps': grounding, 'message': grounding[0]['message'], 'dispatched': False})
            if not any(gap.get('kind') == 'TARGET_BINDING_INVALID' for gap in semantic_gaps):
                # 首帧事实即可确定的冗余与浅目标：反馈指出具体步，不新增模型调用。
                state = load_json(self.current['evidence']['state']['path'])
                redundancy = first_frame_redundancy(plan, self.current, state)
                if redundancy['goal_satisfied']:
                    semantic_gaps.append({'kind': 'FIRST_FRAME_GOAL_ALREADY_SATISFIED',
                        'field_paths': ['goal', 'steps'],
                        'message': '首帧已有状态已能逐项满足全部事项，自然路径不足五个必要业务动作：'
                                   '自主目标须在冻结前改选自然需要多步交互、结果可验证的目标；'
                                   '固定目标不改写，直接报告unsuitable；不得靠滚动、重复输入或额外验算凑步',
                        'dispatched': False})
                elif redundancy['redundant'] and redundancy['effective_business'] < BUSINESS_MINIMUM:
                    semantic_gaps.append({'kind': 'FIRST_FRAME_REDUNDANT_STEPS',
                        'field_paths': ['steps'], 'redundant': redundancy['redundant'],
                        'effective_business': redundancy['effective_business'],
                        'message': ('首轮含首帧已能确定的冗余步：' + '；'.join(
                            '第{}步{}({})'.format(row['step_index'] + 1, row['action'], row['reason'])
                            for row in redundancy['redundant'])
                            + '；排除后必要业务动作{}个，不足{}。先利用首屏已显示内容、默认输入与已有状态，'
                              '去除多余操作后仍自然不足五步：自主目标在冻结前改选需要多步交互的目标，'
                              '固定目标报告unsuitable，不补无用途动作'.format(
                                  redundancy['effective_business'], BUSINESS_MINIMUM)),
                        'dispatched': False})
        if semantic_gaps:
            ok = False
            feedback = {**semantic_gaps[0], 'errors': semantic_gaps,
                'message': '；'.join(dict.fromkeys(row['message'] for row in semantic_gaps))}
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
        self.requirements = deepcopy(requirements)
        self.plan = {'steps': plan['steps'], 'final_presentation_step': plan['final_presentation_step']}
        self.position = 0
        self._plan_accept_route_state(plan['steps'], plan['final_presentation_step'])
        self.initial_feedback = None
        self.plan_event = self.event('screenshot-plan', phase='first',
            goal=self.frozen_goal, requested_goal=deepcopy(self.requested_goal),
            session_objective=deepcopy((self.task['fragment'].get('session_objective') or {}).get('objective')),
            requirements=deepcopy(self.requirements), steps=deepcopy(self.plan['steps']),
            final_presentation_step=self.plan['final_presentation_step'], admission=feedback)
        if getattr(self, 'runlog', None) is not None:
            self._runlog('plan_accepted', observationId=self.current['observation_id'],
                plannedSteps=len(self.plan['steps']), requirements=len(self.requirements),
                actionKinds=feedback.get('action_kinds'), actionHistogram=feedback.get('action_histogram'))

    # ------------------------------------------------------------------ execution

    TARGET_REQUIRED_ACTIONS = ('click', 'double_click', 'right_click', 'type', 'select', 'drag')

    def _bind_target(self, step):
        """Bind a semantic target to the unique current control, if any."""
        target = step.get('target')
        if not target:
            return None
        cited = target.get('control')
        if cited:
            return resolve_control(self.current, target)
        return bind_target(self.current, target, self.observation_records)

    def _stale_citation(self, step):
        """A control cited from an earlier frame cannot be re-resolved here."""
        for key in ('target', 'end_target'):
            target = step.get(key)
            source = target.get('_source') if isinstance(target, dict) else None
            if source and source.get('document_identity') != self.current['document_identity']:
                return True
        return False

    def _action_identity(self, step, control_ids, state):
        control = ((self.current.get('controls') or {}).get(control_ids[0]) or {}) if control_ids else {}
        binding = control.get('binding') or {}
        target_identity = {key: binding.get(key) for key in ('selector', 'index', 'tag', 'href', 'form_selector')}
        return object_sha256({'action': step.get('action'),
            'target': target_identity if control_ids else step.get('target'),
            'document': state.get('document_identity'),
            'value': step.get('value'), 'keys': step.get('keys'),
            'direction': step.get('direction')})

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
        basis, sources = self._submission_basis(state, control_ids)
        old_basis = previous.get('basis') or {}
        same_scope = bool(basis['scope']) and basis['scope'] == old_basis.get('scope') and basis['document'] == old_basis.get('document')
        old_feedback = old_basis.get('feedback') or {}
        feedback_changed = any(value != old_feedback[key] if key in old_feedback else any(value.values())
                               for key, value in basis['feedback'].items())
        changed_state = same_scope and (basis['input_edits'] != old_basis.get('input_edits') or feedback_changed)
        self.event('screenshot-submit-basis', basis=basis, sources=sources, changed=changed_state)
        self._runlog('submission_basis', observationId=self.current['observation_id'], controlIds=control_ids,
            allowed=previous.get('dispatched') is False or changed_state,
            relatedEditOperations=basis['input_edits'], feedbackControls=list(basis['feedback']),
            sourceObservations=sorted(set(sources.values())))
        not_dispatched = previous.get('dispatched') is False
        if not_dispatched or changed_state:
            return None, identity
        return {'kind': 'REPEAT_SUBMISSION_WITHOUT_NEW_BASIS',
                'message': ('同一输入、同一页面状态下该提交已派发过；结果未进视口请先观察（滚动/等待），'
                            '重试须有可核验相关输入编辑或明确反馈；new_basis只是解释，不替代事实'),
                'previous': {key: previous.get(key) for key in ('operation_id', 'outcome', 'at')},
                'new_basis_required': False}, identity

    def _react_step(self, step, control_ids):
        return react_step(step, control_ids,
                          lambda endpoint: self._bind_target({'target': endpoint}))

    async def _execute_round(self):
        if self._goal_ready() and not self._presentation_step_pending:
            # 原目标全部核验后不再执行旧尾部（SSD 3.6）：进入完成核验，
            # 只缺结束展示时由模型 revise 做一次定位。
            await self._checkpoint('goal_ready')
            return
        if self.position >= len(self.plan['steps']):
            await self._checkpoint('plan_exhausted')
            return
        self._presentation_step_pending = False
        step = self.plan['steps'][self.position]
        action = step.get('action')
        try:
            matches = self._bind_target(step)
        except (KeyError, ValueError, TypeError, IndexError) as error:
            await self._checkpoint('binding', feedback={
                'kind': 'STEP_NOT_EXECUTABLE',
                'message': f'目标绑定失败：{type(error).__name__}: {error}',
                'step_position': self.position})
            return
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
        dispatch_basis, basis_sources = self._submission_basis(state, matches or [])
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
            'basis_sha256': object_sha256(dispatch_basis), 'basis': dispatch_basis, 'basis_sources': basis_sources}
        self._refresh_attempt_facts()
        if self.state != 'recording':
            return
        new_attempt = len(getattr(self, 'business_attempt_refs', [])) > attempts_before
        attempt = self.latest_attempt or {}
        advanced = (result or {}).get('status') == 'ok' and (
            not new_attempt or attempt.get('outcome') == 'VERIFIED')
        from .screenshot_effect import step_expectation
        expectation = step_expectation(step, load_json(self.current['evidence']['state']['path']),
                                       (matches or [None])[0])
        if expectation is not None:
            expectation['observation_id'] = self.current['observation_id']
            self.event('screenshot-step-expectation', **expectation)
            self._runlog('step_expectation', observationId=expectation['observation_id'],
                controlId=expectation['control'], expectedValue=expectation['expected_value'],
                actualValue=expectation['actual_value'], matched=expectation['matched'])
            self.latest_attempt = {**(self.latest_attempt or {}), 'step_expectation': expectation}
            if not expectation['matched']:
                await self._checkpoint('step_expectation_mismatch', feedback={
                    'kind': 'STEP_EXPECTATION_MISMATCH', **expectation,
                    'message': '实际编辑已保留，但最终值未达本步预期；请revise尾部或核验完成，不能沿用错误参数'})
                return
        if advanced:
            self.position += 1
            self.route_frames[self.position] = self.current['observation_id']
        route_reason = self._progress_checkpoint_reason(
            self.trajectory[-1] if len(self.trajectory) > before_effective else None) if advanced else None
        if self._checkpoint_needed(step, matches or [], result, attempt) or route_reason:
            # 成功动作已在上方推进游标；只有未建立效果的已派发动作在选择
            # continue时才需要越过当前步，避免每个成功检查点跳过下一步。
            await self._checkpoint(route_reason or self._checkpoint_reason(step, matches or [], attempt),
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
                'step': _public_step(attempt.get('step') or {}),
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
        if self._goal_ready():
            return True
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

    # ------------------------------------------------------- evidence route (SSD)

    def _plan_accept_route_state(self, steps, final_presentation_step):
        """Original first-plan step number behind each current plan position."""
        self.route_map = list(range(1, len(steps) + 1))
        self.planned_final_presentation_step = final_presentation_step
        self.final_presentation_override = None
        self.route_overrides = {}
        self.route_frames = {}

    def _requirement_by_id(self, rid):
        return next((row for row in self.requirements if row['id'] == rid), None)

    def _route_positions(self, rid):
        """Current 1-based plan positions where this requirement's route lives."""
        if rid in self.route_overrides:
            return list(self.route_overrides[rid])
        steps = ((self._requirement_by_id(rid) or {}).get('evidence_route')
                 or {}).get('observation_steps') or []
        return [index + 1 for index, number in enumerate(self.route_map) if number in steps]

    def _final_presentation_position(self):
        if self.final_presentation_override is not None:
            return self.final_presentation_override
        number = getattr(self, 'planned_final_presentation_step', None)
        for index, mapped in enumerate(self.route_map):
            if mapped == number:
                return index + 1
        return None

    def _goal_ready(self):
        return bool(self.requirements) and all(row['id'] in self.verified_answers
                                               for row in self.requirements)

    def _reanchor_routes(self):
        """A revise replaced the tail: pending evidence and the ending frame bind
        to the last new step; the sealed first plan keeps its original route."""
        tail = len(self.route_map)
        reanchored = {}
        for requirement in self.requirements:
            rid = requirement['id']
            if rid in self.verified_answers:
                continue
            positions = self._route_positions(rid)
            # Empty positions mean the route steps were replaced by this revise.
            if all(index <= self.position for index in positions):
                opportunities = [index + 1 for index, step in enumerate(self.plan['steps'])
                    if index >= self.position and step.get('action') in
                    ('scroll', 'click', 'open_url', 'back')] if requirement['kind'] == 'content' else []
                self.route_overrides[rid] = sorted(set(
                    [index for index in positions if index <= self.position] + opportunities + [tail]))
                reanchored[rid] = tail
        presentation_moved = False
        presentation = self._final_presentation_position()
        if presentation is not None and presentation <= self.position:
            self.final_presentation_override = tail
            presentation_moved = True
        if reanchored or presentation_moved:
            self.event('screenshot-route-reanchor', position=self.position,
                       requirements=reanchored, final_presentation_step=tail,
                       original_plan_preserved=True)

    @staticmethod
    def _result_rows(state):
        """Visible result-region rows: bound result regions and status/output roles."""
        bindings = {b['element_id']: b for b in state.get('capture_controls', [])}
        rows = []
        for element in state.get('elements', []):
            text = (element.get('text') or '').strip()
            if (element.get('visible') is True and text
                    and (bindings.get(element['element_id'], {}).get('result_region_selector')
                         or element.get('native_role') in ('status', 'alert', 'output'))):
                rows.append({'control': element['element_id'], 'text': text})
        return rows

    def _valid_result_rows(self, oid):
        """Causal current-document results not superseded by later edits."""
        observation = self.observation_records.get(oid)
        if (not observation or not observation.get('capture_verified')
                or observation.get('document_identity') != self.current.get('document_identity')):
            return []
        state = _state_for_observation(self, oid)
        if state is None:
            return []
        from .result_execution import _rows, result_execution_binding, submission_row
        from .screenshot_effect import input_edit_row
        from .screenshot_plan import _post_submit_causality, _result_superseded
        rows = _rows(self)
        input_rows = [row for row in rows if input_edit_row(self, row)]
        submit_rows = []
        for row in rows:
            before = _state_for_observation(self, row.get('before_observation_id'))
            if before is not None and submission_row(row, before):
                submit_rows.append(row)
        output = []
        for row in self._result_rows(state):
            node = next(element for element in state.get('elements', [])
                        if element['element_id'] == row['control'])
            binding = result_execution_binding(self, oid, state, node)
            causality = None if binding is not None else _post_submit_causality(
                self, submit_rows, input_rows, oid, state, node)
            if binding is None and causality is None:
                # A pre-existing number is not this attempt's result. Applying
                # the same causal gate as completion avoids premature checkpoints.
                continue
            proof = {'result_execution_binding': binding,
                     'post_submit_causality': causality}
            if not _result_superseded(self, rows, oid, state, node, proof):
                output.append(row)
        return output

    def _row_in_region(self, oid, cid, region):
        from .screenshot_plan import _bbox_inside
        state = _state_for_observation(self, oid)
        node = next((e for e in (state or {}).get('elements', []) if e['element_id'] == cid), {})
        return bool(node.get('bbox') and _bbox_inside(node['bbox'], region['bbox']))

    def _candidate_content(self):
        if not any(r['kind'] == 'content' and r['id'] not in self.verified_answers
                   for r in self.requirements):
            return []
        # These are source locations, never automatic answers or verified facts.
        return [{'observation': oid, 'region': row['region_id'], 'quote': row['quote'],
                 'verified': False, 'evidence_only': oid != self.current['observation_id']}
                for oid in list(self.observation_records)[-8:]
                if oid in self.provided_observations
                for row in self.region_registries.get(oid, [])]

    def _candidate_results(self):
        """Valid captured-but-unregistered results in frames the model already saw."""
        if not any(row['kind'] == 'result' and row['id'] not in self.verified_answers
                   for row in self.requirements):
            return []
        rows, seen = [], set()
        for oid in reversed(list(self.observation_records)):
            if oid not in self.provided_observations:
                continue
            for row in self._valid_result_rows(oid):
                key = (row['control'], row['text'])
                if key in seen:
                    continue
                seen.add(key)
                rows.append({'observation': oid, 'control': row['control'],
                             'text': row['text'], 'still_valid': True,
                             'regions': [region for region in self.region_registries.get(oid, [])
                                 if self._row_in_region(oid, row['control'], region)],
                             'evidence_hint': '优先用对应region；短数值不要拼接邻居标签作quote',
                             'current_frame': oid == self.current['observation_id']})
        rows.sort(key=lambda row: not row['current_frame'])
        return rows

    def _progress_checkpoint_reason(self, row):
        """Stop after route evidence, new results, or a known result leaving view."""
        pending = [r for r in self.requirements if r['id'] not in self.verified_answers]
        if not pending:
            return None
        position = self.position
        original = self.route_map[position - 1] if position <= len(self.route_map) else None
        for requirement in pending:
            route = requirement.get('evidence_route') or {}
            if (original is not None and original in (route.get('observation_steps') or [])) \
                    or position in self.route_overrides.get(requirement['id'], []):
                return 'route_observation'
        if row is not None and any(r['kind'] == 'content' for r in pending):
            before = _state_for_observation(self, row.get('before_observation_id'))
            state = _state_for_observation(self, self.current['observation_id'])
            if before is not None and state is not None:
                old = {r['quote'] for r in region_registry(before)}
                if any(r['quote'] not in old for r in region_registry(state)):
                    return 'body_evidence_visible'
        if row is None or not any(r['kind'] == 'result' for r in pending):
            return None
        before = _state_for_observation(self, row.get('before_observation_id'))
        if before is None:
            return None
        before_texts = {entry['text'] for entry in self._result_rows(before)}
        state = _state_for_observation(self, self.current['observation_id'])
        if state is not None and any(entry['text'] not in before_texts
                                     for entry in self._result_rows(state)):
            return 'key_evidence_visible'
        candidates = self._candidate_results()
        if candidates and not any(entry['current_frame'] for entry in candidates):
            return 'historical_result_pending'
        return None

    async def _key_evidence_visual(self):
        """Attach one relevant historical frame, including an already-seen result.

        A frame first supplied as the current viewport may be reattached once for
        the same pending requirement after scrolling. Its controls remain
        evidence-only and cannot dispatch a current action.
        """
        if not self.requirements:
            return None
        for requirement in self.requirements:
            rid = requirement['id']
            if rid in self.verified_answers:
                continue
            for position in reversed(self._route_positions(rid)):
                if position > self.position:
                    continue  # future route step; its frame does not exist yet
                oid = self.route_frames.get(position)
                if (not oid or oid == self.current['observation_id']
                        or (rid, oid) in self.history_supplement_keys):
                    continue
                observation = self.observation_records.get(oid)
                if not observation or not observation.get('capture_verified'):
                    continue
                state = _state_for_observation(self, oid)
                if state is None:
                    continue
                if requirement['kind'] == 'result' and not self._valid_result_rows(oid):
                    continue
                visual = (await prepare_visuals(observation, self.root))[0]
                return {**visual, 'requirement_id': rid}
        # Fallback for an unregistered result from before a tail revision.
        pending_result = next((r['id'] for r in self.requirements
                               if r['kind'] == 'result' and r['id'] not in self.verified_answers), None)
        if pending_result is None:
            return None
        for oid, observation in reversed(list(self.observation_records.items())):
            if (oid == self.current['observation_id']
                    or (pending_result, oid) in self.history_supplement_keys
                    or not observation.get('capture_verified')):
                continue
            if self._valid_result_rows(oid):
                visual = (await prepare_visuals(observation, self.root))[0]
                return {**visual, 'requirement_id': pending_result}
        return None

    # ------------------------------------------------------------------ checkpoint

    @staticmethod
    def _business_state(state):
        from .screenshot_effect import input_facts
        return {'document': state.get('document_identity'), 'url': state.get('url'),
                'inputs': {cid: {k: v for k, v in fact.items() if k in ('identity', 'value', 'checked', 'enabled')}
                           for cid, fact in input_facts(state).items()}}

    def _submission_basis(self, state, control_ids):
        from .screenshot_effect import business_scope, input_facts
        cid = control_ids[0] if control_ids else None
        scope = business_scope(state, cid)
        facts = {}
        sources = {}
        # Same-document trusted observations retain inputs outside this viewport.
        for oid, observation in self.observation_records.items():
            if observation.get('document_identity') != state.get('document_identity') or not observation.get('capture_verified'):
                continue
            original = load_json(observation['evidence']['state']['path'])
            for key, fact in input_facts(original).items():
                if scope and business_scope(original, key) == scope:
                    facts[key] = {k: v for k, v in fact.items() if k in ('identity', 'value', 'checked')}
                    sources[key] = oid
        # Explicit same-target validation feedback is a causal retry basis.
        feedback = {}
        for observation in self.observation_records.values():
            if observation.get('document_identity') != state.get('document_identity') or not observation.get('capture_verified'):
                continue
            original = load_json(observation['evidence']['state']['path'])
            for binding in original.get('capture_controls', []):
                key = binding['element_id']
                if scope and business_scope(original, key) == scope:
                    feedback[key] = {'validation_message': binding.get('validation_message') or None,
                                     'aria_invalid': binding.get('aria_invalid') == 'true'}
        from .screenshot_effect import input_edit_row
        edits = []
        for row in self.trajectory:
            observation = self.observation_records.get(row.get('before_observation_id'))
            if observation and observation.get('document_identity') == state.get('document_identity'):
                original = load_json(observation['evidence']['state']['path'])
                if scope and business_scope(original, (row.get('target') or {}).get('control_id')) == scope and input_edit_row(self, row):
                    edits.append(row.get('operation_id'))
        return {'document': state.get('document_identity'), 'scope': scope, 'inputs': facts,
                'input_edits': edits, 'feedback': feedback}, sources

    def _known_business_inputs(self, state):
        known = {}
        for observation in self.observation_records.values():
            if observation.get('document_identity') == state.get('document_identity') and observation.get('capture_verified'):
                original = load_json(observation['evidence']['state']['path'])
                known.update(self._business_state(original)['inputs'])
        results = {}
        for observation in self.observation_records.values():
            if observation.get('document_identity') != state.get('document_identity') or not observation.get('capture_verified'):
                continue
            original = load_json(observation['evidence']['state']['path'])
            bindings = {b['element_id']: b for b in original.get('capture_controls', [])}
            results.update({e['element_id']: e.get('text') for e in original.get('elements', [])
                           if e.get('visible') and (bindings.get(e['element_id'], {}).get('result_region_selector')
                               or e.get('native_role') in ('status', 'alert', 'output'))})
        public = []
        for cid, fact in known.items():
            for oid, observation in reversed(list(self.observation_records.items())):
                if observation.get('document_identity') != state.get('document_identity') or not observation.get('capture_verified'):
                    continue
                original = load_json(observation['evidence']['state']['path'])
                value = next((row for row in original.get('values', []) if row['element_id'] == cid), None)
                if value is None:
                    continue
                node = next((row for row in original.get('elements', []) if row['element_id'] == cid), {})
                public.append({'control': cid, 'label': node.get('text') or '', 'display_value': value.get('display_value'),
                    'value_visible': value.get('value_visible') is True, 'source_observation': oid, 'still_valid': True})
                break
        return {'url': state.get('url'), 'inputs': public, 'results': results}

    def _historical_evidence(self):
        """References to frames actually sent, never executable old controls."""
        rows = []
        from .screenshot_effect import input_facts
        latest = {}
        for observation in self.observation_records.values():
            if observation.get('document_identity') == self.current['document_identity'] and observation.get('capture_verified'):
                latest.update(input_facts(load_json(observation['evidence']['state']['path'])))
        for oid, observation in self.observation_records.items():
            if oid not in self.provided_observations or not observation.get('capture_verified'):
                continue
            original = load_json(observation['evidence']['state']['path'])
            from .screenshot_effect import input_facts
            inputs = input_facts(original)
            controls = observation.get('controls') or {}
            rows.append({'observation': oid, 'url': observation.get('url'),
                'current': oid == self.current['observation_id'], 'evidence_only': True,
                'inputs': [{'control': cid, 'display_value': next((row.get('display_value') for row in original.get('values', []) if row['element_id'] == cid), None),
                    'source_observation': oid,
                    'value_visible': fact.get('value_visible'),
                    'labels': controls.get(cid, {}).get('labels', []),
                    'still_valid': (fact.get('identity') == latest.get(cid, {}).get('identity')
                        and all(fact.get(key) == latest.get(cid, {}).get(key) for key in ('value', 'checked')))}
                    for cid, fact in inputs.items()
                    if cid in observation.get('provided_control_ids', [])],
                'regions': deepcopy(self.region_registries.get(oid, [])),
                'verified_quotes': [{'requirement_id': rid, 'quote': proof.get('quote')}
                    for rid, check in self.verified_checks.items() for proof in check.get('evidence', [])
                    if proof.get('observation_id') == oid]})
        return rows

    def _public_confirmed_progress(self):
        output = []
        for rid, answer in self.verified_answers.items():
            row = deepcopy(answer)
            host = any(proof.get('host_input_proof') for proof in self.verified_checks.get(rid, {}).get('evidence', []))
            row['source'] = 'host_verified_capture' if host else 'model_provided_evidence'
            row['model_has_seen'] = all(item['observation'] in self.provided_observations for item in answer['evidence'])
            output.append(row)
        return output

    def _referenceable_observations(self):
        return self.provided_observations | {row['observation_id'] for row in self.host_input_proofs}

    def _capture_input_progress(self):
        # Frozen source identity and the normal verifier own matching/expiry.
        for requirement in self.requirements:
            if requirement['kind'] != 'input':
                continue
            previous = self.verified_answers.get(requirement['id'])
            if previous:
                retained, _ = _verify_input(self, previous, requirement)
                if retained:
                    continue
            evidence = [{'observation': oid, 'control': cid}
                for oid, observation in reversed(list(self.observation_records.items()))
                if observation.get('capture_verified')
                for cid in observation.get('controls', {})]
            value = requirement.get('expected_value', requirement.get('expected_checked'))
            answer = {'requirement_id': requirement['id'], 'observed_result': str(value), 'evidence': evidence}
            check, _ = _verify_input(self, answer, requirement, trusted_capture=True)
            if check:
                proof = check['evidence'][0]
                answer['evidence'] = [{'observation': proof['observation_id'], 'control': proof['node']}]
                previous = self.verified_answers.get(requirement['id'])
                self.verified_answers[requirement['id']] = answer
                self.verified_checks[requirement['id']] = check
                if previous != answer:
                    reference = self.event('screenshot-input-progress', requirement_id=requirement['id'],
                        observation_id=proof['observation_id'], control=proof['node'],
                        answer=deepcopy(answer), check=deepcopy(check), source='host_bound_input')
                    self.host_input_proofs.append({'requirement_id': requirement['id'],
                        'observation_id': proof['observation_id'], 'control': proof['node'], 'event': reference})

    def _progress_marker(self):
        # Only frozen-goal input facts and verified evidence reset checkpoint stalls.
        # Fresh captures, document IDs and unrelated live page text are provenance,
        # not progress. Distinct validated evidence remains a real correction.
        from .screenshot_effect import input_facts
        inputs = {}
        for observation in self.observation_records.values():
            if not observation.get('capture_verified'):
                continue
            state = load_json(observation['evidence']['state']['path'])
            facts = input_facts(state)
            for requirement in self.requirements:
                if requirement['kind'] != 'input':
                    continue
                target = requirement['target']
                source = target.get('_source')
                if source:
                    matches = [cid for cid, control in observation.get('controls', {}).items()
                        if observation.get('document_identity') == source['document_identity']
                        and all((control.get('binding') or {}).get(key) == source['binding'].get(key)
                                for key in ('selector', 'index', 'tag', 'href'))]
                else:
                    matches = bind_target(observation, target)
                if len(matches) == 1 and matches[0] in facts:
                    inputs[requirement['id']] = {key: facts[matches[0]][key]
                        for key in ('value', 'checked') if key in facts[matches[0]]}
        return object_sha256({
            'goal_inputs': inputs,
            'verified_evidence': {rid: sorted(set((proof.get('quote') or '', proof.get('url') or '')
                for proof in check.get('evidence', [])))
                for rid, check in self.verified_checks.items()}})

    def _revalidate_progress(self):
        self._capture_input_progress()
        if not self.verified_answers:
            return
        requirements = [row for row in self.requirements if row['id'] in self.verified_answers]
        checks, _ = verify_completion(self, {'answers': list(self.verified_answers.values())}, requirements)
        valid = {row['requirement_id'] for row in checks if row.get('status') == 'VERIFIED'}
        self.verified_answers = {rid: answer for rid, answer in self.verified_answers.items() if rid in valid}
        self.verified_requirement_ids = sorted(valid)
        self.verified_checks = {row['requirement_id']: row for row in checks
                                if row.get('status') == 'VERIFIED'}

    def _branch_prompt(self, reason, feedback=None):
        self._revalidate_progress()
        state = load_json(self.current['evidence']['state']['path'])
        oid = self.current['observation_id']
        if oid not in self.region_registries:
            self.region_registries[oid] = region_registry(state)
            self.event('screenshot-regions', observation_id=oid,
                       regions=deepcopy(self.region_registries[oid]))
        self._dialog_checkpointed = list(self.dialogs)
        remaining = self.plan['steps'][self.position:]
        choices = list(DECISIONS)
        stale_tail = bool(remaining) and self._stale_citation(remaining[0])
        goal_ready = self._goal_ready()
        if (not remaining or stale_tail or goal_ready
                or (feedback or {}).get('kind') == 'STEP_EXPECTATION_MISMATCH'):
            choices.remove('continue')
        next_checkpoint = {'reason': reason, 'remaining_steps': len(remaining),
                           'allowed_decisions': list(choices)}
        if goal_ready:
            next_checkpoint['goal_ready'] = ('全部事项已核验：直接complete结束；结束画面缺失时用revise定位一次，'
                                             '把已核验结果滚入当前视口后complete，不重取已验证历史输入')
        if stale_tail:
            next_checkpoint['continue_unavailable'] = ('下一步引用的控件来自已变化的页面，无法沿用；'
                                                       '请revise按当前controls重新绑定尾部，或complete/give_up')
        payload = {'phase': 'branch', 'attempt_id': self.attempt_id,
                   'system': SYSTEM_PROMPT,
                   'goal': self.frozen_goal, 'requirements': _public_step(self.requirements),
                   'requested_goal': _public_step(self.requested_goal),
                   'session_objective': _public_step((self.task['fragment'].get('session_objective') or {}).get('objective')),
                   'current_observation': oid, 'screenshots': [oid],
                   'visual_evidence': {'scope': 'current_viewport', 'observation': oid,
                                       'image_sha256': self.current['evidence']['image']['sha256'],
                                       'regions': deepcopy(self.region_registries[oid])},
                   'regions': self.region_registries[oid],
                   'controls': self._controls(),
                   'allowed_actions': list(self._allowed_actions()),
                   'remaining_plan': [_public_step(row) for row in remaining],
                   'next_checkpoint': next_checkpoint,
                   'reason': reason, 'choices': choices, 'rules': BRANCH_RULES,
                   'tools': decision_tools(choices, self._allowed_actions(),
                                           sorted(self._referenceable_observations() | {oid})),
                   'progress': {'decisions_used': self.used['max_decisions'],
                                'effective_steps': len(self.trajectory),
                                'actual_dispatches': self.actual_dispatches}}
        payload.update(self._session_facts(state))
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
        allowed_actions = self._allowed_actions()
        decision, record = normalize_decision(arguments, prompt['choices'], allowed_actions)
        self.event('screenshot-decision', reason=reason, decision=decision,
                   normalization=record, position=self.position)
        if getattr(self, 'runlog', None) is not None:
            self._runlog('checkpoint', observationId=self.current['observation_id'],
                decision=decision.get('decision'), reason=reason, position=self.position,
                effectiveSteps=len(self.trajectory))
        from jsonschema import Draft202012Validator
        errors = list(Draft202012Validator(decision_schema(prompt['choices'], allowed_actions,
                           sorted(self._referenceable_observations()))).iter_errors(decision))
        if errors:
            self.event('screenshot-decision-rejected', reason='invalid_fields', message=errors[0].message)
            self.completion_feedback = {'kind': 'DECISION_FIELDS_INVALID', 'message': errors[0].message}
            # A checkpoint whose every reply repeats an out-of-choices decision
            # must count into the same no-progress guard as every other reply;
            # an unguarded early return would loop model requests forever.
            self._stall_check(decision, feedback)
            return
        choice = decision.get('decision')
        # Every decision can contribute independently verified evidence. Invalid
        # supplements cannot erase a previously verified answer for that item.
        supplied = decision.get('answers') or []
        self._revalidate_progress()
        supplement_gaps = []
        if supplied:
            merged = deepcopy(self.verified_answers)
            merged.update({row['requirement_id']: deepcopy(row) for row in supplied})
            ids = set(merged)
            subset = [row for row in self.requirements if row['id'] in ids]
            supplied_ids = [row['requirement_id'] for row in supplied]
            duplicates = [row for index, row in enumerate(supplied)
                          if row['requirement_id'] in supplied_ids[:index]]
            checks, supplement_gaps = verify_completion(self,
                {'answers': list(merged.values()) + duplicates}, subset)
            verified = {row['requirement_id'] for row in checks if row.get('status') == 'VERIFIED'}
            self.verified_answers.update({row['requirement_id']: deepcopy(row)
                                          for row in supplied if row['requirement_id'] in verified})
            self.verified_checks.update({row['requirement_id']: row for row in checks
                                         if row.get('status') == 'VERIFIED'})
            self.verified_requirement_ids = sorted(self.verified_answers)
            self.event('screenshot-progress-evidence', checks=checks, gaps=supplement_gaps,
                       verified_requirement_ids=self.verified_requirement_ids)
        if supplement_gaps:
            self.completion_feedback = {'kind': 'PROGRESS_EVIDENCE_GAPS', 'gaps': supplement_gaps}
        if choice == 'complete':
            # Completion uses a fresh synchronized host observation, not the
            # viewport captured before a potentially long model request.
            await self._observe()
            self._revalidate_progress()
            application = {**decision, 'answers': deepcopy(list(self.verified_answers.values()))}
            checks, gaps = verify_completion(self, application, self.requirements,
                                             require_calculation_coverage=True)
            final_visible, final_gaps = verify_final_presentation(self, checks, self.requirements)
            gaps = supplement_gaps + gaps + final_gaps
            self._note_completion_gaps(gaps)
            if not gaps:
                self.completion_feedback = None
                self._complete(application, checks, reason, final_visible)
                return
            self.completion_feedback = {'kind': 'COMPLETION_EVIDENCE_GAPS', 'gaps': gaps,
                'verified_requirement_ids': self.verified_requirement_ids,
                'verified_answers': deepcopy(list(self.verified_answers.values())),
                'message': '已核验答案与原引用已保留；只补缺项。后续相关输入或提交会使旧计算证明失效。'}
            self.event('screenshot-completion-rejected', gaps=gaps, dispatched=False,
                       verified_requirement_ids=self.verified_requirement_ids)
            self._runlog('completion_gaps', observationId=self.current['observation_id'],
                gaps=[gap.get('kind') for gap in gaps],
                verifiedRequirementIds=self.verified_requirement_ids)
        # Neither dispatch counts, cursor changes nor reworded plans establish
        # progress. Frozen input state and independently verified evidence establish
        # progress; capture IDs and unrelated page text never do.
        if self._stall_check(decision, feedback):
            return
        if choice == 'complete':
            return await self._checkpoint(reason, self.completion_feedback)
        if choice == 'inspect':
            reference = self.provided_visual_refs.get(decision.get('image_ref'))
            try:
                if reference is None or reference.get('observation_id') != self.current['observation_id']:
                    raise ValueError('INSPECT_REQUIRES_PROVIDED_CURRENT_IMAGE')
                if int(getattr(self.choose, 'max_images', 2)) < 2:
                    raise ValueError('INSPECT_REQUIRES_TWO_IMAGE_SLOTS: viewport and requested crop')
                self._inspection_visual = crop_visual(self.current, self.root,
                    decision.get('crop') or [], image_ref=reference['ref'])
            except ValueError as error:
                return await self._checkpoint(reason, {'kind': 'INSPECT_REQUEST_INVALID',
                    'message': str(error), 'dispatched': False})
            self.event('screenshot-inspection', visual=deepcopy(self._inspection_visual), dispatched=False)
            return await self._checkpoint(reason, {'kind': 'INSPECT_IMAGE_PROVIDED',
                'image_ref': self._inspection_visual['ref'], 'dispatched': False})
        if choice == 'continue' and feedback and feedback.get('kind') == 'STEP_EXPECTATION_MISMATCH':
            self.event('screenshot-decision-rejected', reason='expected_value_mismatch')
            return
        if choice == 'continue':
            if not self.plan['steps'][self.position:]:
                self.event('screenshot-decision-rejected', reason='continue_without_remaining_steps')
                return await self._checkpoint(reason, {'kind': 'CONTINUE_WITHOUT_STEPS',
                    'message': '剩余计划为空，不能continue；请complete、revise或give_up'})
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
            binding_gaps = self._bind_targets_feedback({'steps': steps})
            if binding_gaps:
                return await self._checkpoint(reason, {'kind': 'TARGET_BINDING_INVALID',
                    'errors': binding_gaps, 'message': '；'.join(row['message'] for row in binding_gaps),
                    'dispatched': False})
            grounding = narrative_grounding_gaps(steps, self._frame_text(), self.frozen_goal)
            if grounding:
                return await self._checkpoint(reason, {'kind': 'RATIONALE_NOT_GROUNDED',
                    'gaps': grounding, 'message': grounding[0]['message'], 'dispatched': False})
            if self.first_route_status == 'original':
                self.event('screenshot-route-deviation', position=self.position,
                    final_presentation_step=self.plan.get('final_presentation_step'),
                    reason='accepted_tail_revision')
                self.first_route_status = 'deviated'
            self._granted_new_basis = str(decision.get('new_basis') or '').strip() or None
            self.plan['steps'] = self.plan['steps'][:self.position] + steps
            self.route_map = self.route_map[:self.position] + [None] * len(steps)
            self._reanchor_routes()
            self.completion_feedback = None
            # Only a newly accepted presentation repair may bypass goal_ready,
            # for one action. The old tail never receives this permission, and
            # a repair whose first step could alter verified facts (edit,
            # submission, navigation away) is sent back to the checkpoint.
            presentation_gaps = []
            if self._goal_ready():
                presentation_gaps = verify_final_presentation(
                    self, list(self.verified_checks.values()), self.requirements)[1]
                self._note_completion_gaps(presentation_gaps)
            permitted = bool(presentation_gaps) and self._presentation_repair_permitted(steps)
            if presentation_gaps and not permitted:
                self.event('screenshot-presentation-repair-denied', position=self.position,
                           action=(steps[0].get('action') if steps else None),
                           reason='positioning_step_may_alter_verified_facts')
                self.completion_feedback = {
                    'kind': 'PRESENTATION_REPAIR_UNSAFE', 'gaps': presentation_gaps,
                    'message': '原目标已核验，只缺结束展示。请scroll定位当前结果、点击当前summary/tab或同文档锚点；'
                               '纯阅读目标有可信前向导航及已核验前页依据时可back返回。仍无安全路径则give_up；不要编辑、切换勾选、重置、重新提交或按可能编辑当前焦点的键。'}
            self._presentation_step_pending = permitted
            self.event('screenshot-plan-revision',
                       position=self.position, steps=deepcopy(steps),
                       executed_preserved=self.position)
            return
        if choice == 'give_up':
            self._range_close('AGENT_GIVE_UP', 'give_up：' + str(decision.get('reason') or '当前无可行路径'))
            return
        self.event('screenshot-decision-rejected', reason='unknown_decision', dispatched=False)
        return await self._checkpoint(reason, {'kind': 'UNKNOWN_DECISION',
            'message': '请使用当前choices中的decision；缺证时complete补证或give_up，不执行旧剩余动作'})

    def _note_completion_gaps(self, gaps):
        self._completion_gap_projection = tuple(sorted(
            (str(gap.get('kind')), str(gap.get('requirement_id') or '')) for gap in gaps or ()))

    def _presentation_repair_permitted(self, steps):
        """结束展示定位只允许确定不改变已核验事实的首步动作。

        只放行scroll/wait、当前明确的展开/页签/同文档锚点，以及有已核验
        正文来源和真实前向导航记录的back。编辑、提交、未知按钮和焦点按键
        留在检查点反馈，不推断它们不会改变已核验事实。
        """
        if not steps:
            return False
        step = steps[0]
        action = step.get('action')
        if action in ('scroll', 'wait'):
            return True
        if action == 'click':
            try:
                matches = self._bind_target(step)
            except Exception:
                return False
            if not matches or len(matches) != 1 or self._submit_like(matches):
                return False
            control = self.current['controls'].get(matches[0]) or {}
            element, binding = control.get('element') or {}, control.get('binding') or {}
            # Generic buttons can reset data, inputs can toggle conditions.
            return (not element.get('inputable') and binding.get('tag') != 'input'
                    and (element.get('native_role') in ('summary', 'tab')
                         or (binding.get('tag') == 'a' and self._same_document_anchor(binding.get('href')))))
        if action == 'back' and all(row.get('kind') == 'content' for row in self.requirements):
            # Only the last recorded forward navigation establishes a return
            # destination. A prior back/popup/unknown transition is not inferred.
            for row in reversed(self.trajectory):
                before = self.observation_records.get(row.get('before_observation_id')) or {}
                after = self.observation_records.get(row.get('after_observation_id')) or {}
                if before.get('url') == after.get('url'):
                    continue
                if row.get('action') not in ('click', 'open_url') or after.get('url') != self.current.get('url'):
                    return False
                raw_ref = row.get('raw_step') or {}
                try:
                    raw = load_json(raw_ref['path'])
                except (KeyError, ValueError, OSError):
                    return False
                if raw.get('popup_provenance') or raw.get('opened_pages'):
                    return False
                verified = {e.get('observation_id') or e.get('observation')
                            for check in self.verified_checks.values() for e in check.get('evidence') or []}
                return bool(before.get('url')) and any(
                    (self.observation_records.get(oid) or {}).get('url') == before['url'] for oid in verified)
        # Even unbound navigation keys may edit the focused number/contenteditable.
        # Scroll has an explicit viewport target and is the safe alternative.
        return False

    def _same_document_anchor(self, href):
        from urllib.parse import urljoin, urldefrag
        if not isinstance(href, str) or not href:
            return False
        current = self.current.get('url') or ''
        destination, fragment = urldefrag(urljoin(current, href))
        return bool(fragment) and destination == urldefrag(current)[0]

    def _stall_progress_marker(self):
        """停滞事实基线：冻结目标输入事实＋已核验证据＋完成缺项稳定投影。"""
        return object_sha256({'facts': self._progress_marker(),
                              'completion_gaps': list(self._completion_gap_projection)})

    def _stall_check(self, decision, feedback):
        """Shared no-progress accounting for every checkpoint reply.

        Revisited frames, reworded decisions and out-of-choices replies all
        never reset progress. Repeated complete with unchanged missing facts, or
        the consecutive stall limit, ends the attempt. Corrected revise tails
        remain executable within that same bounded allowance.
        """
        stall_marker = self._stall_progress_marker()
        if stall_marker == self._stall_marker:
            self._stall_count += 1
        else:
            self._stall_marker = stall_marker
            self._stall_count = 0
        key = object_sha256({'facts': stall_marker,
            'missing': sorted(row['id'] for row in self.requirements
                              if row['id'] not in self.verified_checks),
            'decision': decision.get('decision')})
        self.no_progress_keys[key] = self.no_progress_keys.get(key, 0) + 1
        if ((decision.get('decision') == 'complete' and self.no_progress_keys[key] >= 2)
                or self._stall_count >= NO_PROGRESS_STALL_LIMIT):
            self.event('screenshot-no-progress-stall', dispatches=self.actual_dispatches,
                       position=self.position, stall_count=self._stall_count)
            self._range_close('NO_PROGRESS_END', '连续检查点无有效动作、业务状态变化或新增有效证据，无进展结束')
            return True
        return False

    def _complete(self, application, checks, reason, final_visible):
        self.completed_at = datetime.now(timezone.utc).isoformat()
        receipt = self.event('screenshot-completion', completed_at=self.completed_at,
            final_observation_id=self.current['observation_id'], final_visible_evidence=deepcopy(final_visible),
            application=deepcopy(application), checks=deepcopy(checks),
            goal=self.frozen_goal, requested_goal=deepcopy(self.requested_goal),
            session_objective=deepcopy((self.task['fragment'].get('session_objective') or {}).get('objective')),
            requirements=deepcopy(self.requirements), checkpoint_reason=reason)
        self.verified_requirement_ids = [row['id'] for row in self.requirements]
        self.goal_evidence = {'business_goal_status': 'VERIFIED', 'checks': checks,
                              'final_visible_evidence': deepcopy(final_visible),
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


def _public_target(target):
    if not isinstance(target, dict):
        return deepcopy(target)
    return {key: deepcopy(value) for key, value in target.items() if key != '_source'}


def _public_attempt(attempt):
    if not attempt:
        return None
    return {key: attempt.get(key) for key in
            ('number', 'action', 'purpose', 'dispatched', 'effective', 'outcome', 'reason', 'step', 'step_expectation')}


def _public_effective(row):
    if not row:
        return None
    return {key: _public_step(value) if isinstance(value, dict) else deepcopy(value)
            for key, value in row.items() if key in (
                'operation_id', 'action', 'arguments', 'target', 'goal', 'semantic_goal',
                'expected_value', 'step_expectation', 'before_observation_id', 'after_observation_id',
                'observed', 'observed_changed', 'changed_fields', 'effective')}


def _public_step(value):
    if isinstance(value, dict):
        return {key: _public_step(item) for key, item in value.items() if key != '_source'}
    if isinstance(value, list):
        return [_public_step(item) for item in value]
    return deepcopy(value)



def describe(goal):
    from .session_core import describe_goal
    return describe_goal(goal)
