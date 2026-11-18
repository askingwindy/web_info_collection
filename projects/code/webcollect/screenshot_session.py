"""策略 2 会话：共享引擎核心之上，替换决策循环。

The session reuses the entry observation, trusted capture, atomic dispatch,
effect verification, business-attempt journal and raw close-out from the shared
engine core (session_core.RawSessionCore), never the 策略 1 decision loop.
What changes is the decision loop: one first-round submit_plan, observed
execution of the accepted route, model checkpoints for actual deviations,
necessary evidence batches or completion, and a verified `complete`.
"""
import asyncio
from copy import deepcopy
from webcollect import workspace_json as json
import re
import time
from datetime import datetime, timezone

from .batch_core import OutcomeUnknown, SessionGLMCallLimit, BudgetStop, load_json
from .planning import object_sha256
from . import collection_strategy as _cs
from .screenshot_plan import (SYSTEM_PROMPT,
    FIRST_RULES, BRANCH_RULES, BUSINESS_MINIMUM, PREFERRED_MAXIMUM, NON_BUSINESS_ACTIONS,
    DECISIONS, READY_ENDING, RAW_ONLY_ENDINGS, NO_PROGRESS_STALL_LIMIT, submit_plan_tools,
    decision_tools, decision_schema, normalize_submit_plan, normalize_decision,
    first_plan_admission, business_actions, compile_contract, verify_completion, verify_final_presentation, _verify_input, narrative_grounding_gaps, supported_actions, evidence_route_gaps, first_frame_redundancy, _state_for_observation)
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
        self.latest_attempt_is_current_step = False
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
        self._stall_seen_markers = set()
        self._checkpoint_evidence_seen = set()
        self._stall_request_pending = False
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
        self._checkpoint_requests = set()
        self._reading_progress = set()

    # ------------------------------------------------------------------ run

    async def run(self):
        from webcollect.collection_strategy import Strategy2Frozen
        raise Strategy2Frozen()
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
        except BudgetStop as error:
            # 软时限后的网关拒绝（consumer_session_soft_deadline）是预算结束，
            # 不是工程故障；未决请求保留 UNKNOWN。
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
        prompt = project_model_prompt(prompt)
        self._controls()
        limit = int(getattr(self.choose, 'max_images', 2))
        if limit < 1:
            raise ReactStop('blocked', '模型图片配置至少须允许一张清晰视口图', 'program')
        visuals = await prepare_visuals(self.current, self.root, self.page,
                                        first=prompt.get('phase') == 'first' and limit >= 2)
        available = list(visuals)
        if self._inspection_visual and self._inspection_visual['observation_id'] == self.current['observation_id']:
            if not any(row['ref'] == self._inspection_visual['ref'] for row in available):
                available.append(self._inspection_visual)
        key_visual = None if prompt.get('phase') == 'first' else await self._key_evidence_visual()
        evidence_only_request = False
        if key_visual is not None and not any(row['ref'] == key_visual['ref'] for row in available):
            if limit < 2:
                # 单图配置：必要历史图以纯证据登记请求单独提供，不占用动作
                # 决策的当前图名额；随后的动作决策继续使用当前图。
                available = [key_visual]
                evidence_only_request = True
                self.event('screenshot-history-supplement', observation_id=key_visual['observation_id'],
                           requirement_id=key_visual.get('requirement_id'), scheduled=True,
                           mode='single_image_evidence_only',
                           reprovided=key_visual['observation_id'] in self.provided_observations,
                           dispatched=False)
            else:
                available.append(key_visual)
        viewport = next((row for row in available if row['scope'] == 'viewport'
                        and row['observation_id'] == self.current['observation_id']), None)
        if viewport is None and not evidence_only_request:
            raise ReactStop('blocked', '当前清晰视口图必须提供', 'program')

        def priority(row):
            if row is viewport:
                return (0, '')
            if row is self._inspection_visual:
                return (1, row['ref'])
            if row.get('observation_id') != self.current['observation_id']:
                return (2, row['ref'])
            return (3, row['ref'])

        visuals = sorted(available, key=priority)[:limit]
        if key_visual is not None and key_visual not in visuals:
            key_visual = None
        if key_visual is not None and 'choices' in prompt:
            # 必要历史图请求只作纯证据登记：不提供业务动作工具（无
            # remaining_plan/continue），动作决策在下一请求重新使用当前图。
            evidence_only_request = True
            prompt['choices'] = []
            prompt.pop('pending_steps', None)
            prompt.pop('remaining_plan', None)
            if 'next_checkpoint' in prompt:
                prompt['next_checkpoint']['allowed_decisions'] = list(prompt['choices'])
            prompt['evidence_only_request'] = {
                'observation': key_visual['observation_id'],
                'requirement_id': key_visual.get('requirement_id'),
                'message': '仅调用register_evidence提交引用；status为registered/insufficient/not_relevant。局部不足不结束任务。'}
        prompt['_images'] = [row['path'] for row in visuals]
        prompt['visual_evidence'] = deepcopy(visuals)
        observation_ids = list(dict.fromkeys(row['observation_id'] for row in visuals))
        prompt['screenshots'] = observation_ids
        for oid in observation_ids:
            if oid == self.current['observation_id']:
                continue
            state = _state_for_observation(self, oid)
            if state is not None and oid not in self.region_registries:
                self.region_registries[oid] = region_registry(state)
                self.event('screenshot-regions', observation_id=oid, regions=deepcopy(self.region_registries[oid]))
            history = prompt.setdefault('historical_evidence', [])
            if not any(row['observation'] == oid for row in history):
                history.append({'observation': oid, 'url': self.observation_records[oid].get('url'),
                    'provided_this_request': True, 'evidence_only': True,
                    'regions': deepcopy(self.region_registries.get(oid, []))})
        if set(observation_ids) - {self.current['observation_id']} and 'choices' in prompt:
            # A historical key frame is citable in the very request that carries
            # it; the host-side response validator rebuilds its enum after the
            # successful request, so only the wire tools need this extension.
            prompt['tools'] = decision_tools(prompt['choices'], prompt.get('allowed_actions'),
                                             sorted(self._referenceable_observations() | set(observation_ids)))
        if evidence_only_request:
            from .screenshot_plan import register_evidence_tools
            prompt['tools'] = register_evidence_tools(sorted(self._referenceable_observations() | set(observation_ids)))
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
        if prompt.get('phase') == 'branch':
            selected_evidence = [{
                'url': self.observation_records[oid].get('url'),
                'quotes': sorted({r.get('quote') or '' for r in self.region_registries.get(oid, [])
                    if any(_reading_region_relevant(requirement, r) for requirement in self.requirements
                           if requirement['id'] not in self.verified_answers)}),
                'results': sorted({r['text'] for r in self._valid_result_rows(oid)}),
                'newly_provided': oid not in self.provided_observations,
            } for oid in observation_ids]
            # Count revisits before another provider request. A newly captured
            # relevant quote/result may still need its first interpretation;
            # capture IDs and reworded plans never establish that novelty.
            def evidence_keys(item):
                return {object_sha256([item['url'], kind, quote])
                        for kind in ('quotes', 'results') for quote in item[kind]}
            for oid in self.provided_observations:
                prior_regions = self.region_registries.get(oid)
                if prior_regions is None:
                    prior_regions = region_registry(load_json(self.observation_records[oid]['evidence']['state']['path']))
                offered = {'url': self.observation_records[oid].get('url'),
                    'quotes': {r.get('quote') or '' for r in prior_regions
                        if any(_reading_region_relevant(requirement, r) for requirement in self.requirements
                               if requirement['id'] not in self.verified_answers)},
                    'results': {r['text'] for r in self._valid_result_rows(oid)}}
                self._checkpoint_evidence_seen.update(evidence_keys(offered))
            new_evidence = False
            for item in selected_evidence:
                keys = evidence_keys(item)
                if item['newly_provided'] and keys - self._checkpoint_evidence_seen:
                    new_evidence = True
                self._checkpoint_evidence_seen.update(keys)
            self._track_stall_marker(count_revisit=True)
            if new_evidence:
                self._stall_count = 0
            self._stall_request_pending = True
            if self._stall_count >= NO_PROGRESS_STALL_LIMIT:
                self._close_stall()
                return None
            request_key = object_sha256({'facts': self._checkpoint_identity(prompt.get('checkpoint_feedback')),
                                        'selected_evidence': selected_evidence,
                                        'inspection_images': [v for v in visuals if v.get('scope') == 'image_crop']})
            if request_key in getattr(self, '_checkpoint_requests', set()):
                self.event('screenshot-checkpoint-deduplicated', reason=prompt.get('reason'), position=self.position)
                self._range_close('NO_PROGRESS_END', '相同业务事实、实际证据和缺项已询问且无新依据，保留原件并结束')
                return None
            if not hasattr(self, '_checkpoint_requests'):
                self._checkpoint_requests = set()
            self._checkpoint_requests.add(request_key)
        call_kind = ('planning' if prompt.get('phase') == 'first' else
                     'evidence' if prompt.get('reason') in ('evidence_batch_boundary', 'key_evidence_visible') else
                     'completion' if prompt.get('reason') in ('plan_exhausted', 'goal_ready', 'presentation_ready',
                         'planned_evidence_complete', 'possible_goal_evidence', 'result_reading_or_plan_end',
                         'submission_checkpoint', 'navigation_checkpoint') else 'route_deviation')
        prompt['call_purpose'] = call_kind
        if self.host_limits:
            # 软时限后不再发起新的模型HTTP请求（网关按该deadline拒绝派发）；
            # 该字段只进派发上下文，不进入请求正文或模型意图存档。
            prompt['_dispatch_deadline'] = self.host_limits['started_monotonic'] + self.host_limits['soft_seconds']
        prompt = project_model_prompt(prompt)
        self._last_model_intent = self.event('model-intent', prompt=_stripped(prompt),
                                             canonical_visual_evidence=deepcopy(visuals))
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
            self.strategy_end_reason = 'protocol_error'
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
            for requirement in self.requirements:
                if any(self.route_frames.get(pos) == key_visual['observation_id']
                       for pos in self._route_positions(requirement['id'])):
                    self.history_supplement_keys.add((requirement['id'], key_visual['observation_id']))
            self.history_supplement_keys.add((key_visual['requirement_id'], key_visual['observation_id']))
        self.event('model-observations-provided', model_intent=self._last_model_intent,
                   observation_ids=observation_ids)
        self._last_evidence_only_request = evidence_only_request
        return response

    # ------------------------------------------------------------------ first plan

    def _fixed_goal(self):
        objective = ((self.task.get('fragment') or {}).get('session_objective') or {}).get('objective') or {}
        return str(objective.get('description') or describe(self.requested_goal) or '').strip()

    def _allowed_actions(self):
        return supported_actions(self.task['fragment']['allowed_actions'])

    def _session_facts(self, state):
        """One factual projection for first planning and every checkpoint."""
        observed_urls = {row.get('url') for row in self.observation_records.values()}
        return {'current_url': self.current['url'],
                'page_directory': [{'page_id': f'p{index}', 'url': url,
                                    'observed': True}
                                   for index, url in enumerate(self.page_urls) if url in observed_urls],
                'known_business_state': self._known_business_inputs(state),
                'historical_evidence': self._historical_evidence(),
                'latest_attempt': _public_attempt(self.latest_attempt),
                'latest_attempt_is_current_step': self.latest_attempt_is_current_step,
                'last_effective_action': _public_effective(self.last_effective),
                'confirmed_progress': self._public_confirmed_progress(),
                'partial_coverage': [{**deepcopy(answer), 'status': 'PARTIAL_NOT_COMPLETE'}
                    for rid, answer in getattr(self, '_partial_answers', {}).items() if rid not in self.verified_answers],
                'candidate_results': self._candidate_results(),
                'tool_capabilities': self._tool_capabilities(),
                'first_route_status': self.first_route_status,
                'missing_requirements': [row['id'] for row in self.requirements
                                         if row['id'] not in self.verified_answers]}

    def _tool_capabilities(self):
        """Host support is separate from what this particular frame has shown."""
        images = int(getattr(self.choose, 'max_images', 2))
        return {'supported_actions': list(self._allowed_actions()),
                'unsupported': ['file_upload', 'local_file_selection'],
                'max_images': images,
                'inspect': images >= 2,
                'historical_image_with_current': images >= 2,
                'instruction': '支持动作只表示宿主具有该能力；当前派发条件以controls.action_states与实际反馈为准。'
                    '未观察到的控件或后续页面不等于不支持，不得仅凭尚未看见就报告unsuitable。'
                    '不支持上传或本地文件选择，不得用type代替。历史图只有实际提供才算模型已见；'
                    '单图配置下动作决策只用当前视口图，必要历史图由宿主以纯证据登记请求单独提供（该请求无业务动作工具），'
                    '应优先在关键证据离开当前视口前登记。'}

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
                   'goal_selection': {
                       'mode': 'fixed' if self._fixed_goal() else 'autonomous',
                       'instruction': ('逐字继承宿主指定目标，不能改写；工具不返回goal。'
                           if self._fixed_goal() else
                           '当前仅指定入口URL，三个目标字段为空是正常入口：你须依据实际页面与可用交互自主选择具体可验证、自然需要至少五个必要业务动作的目标，并在submit_plan.goal提交。'
                           '先从真实控件、正文链接与可见内容选取自然完整路线，可选择有意义的计算、查询或关联正文阅读；不得先选首屏浅阅读再靠无用途滚动、往返或验算凑步。'
                           '后续页面尚未观察不是unsuitable；可在同一首轮完整路线中声明未来语义目标，观察后只修订剩余步骤。不得先试做再换目标。确无可行目标才报告unsuitable。'),
                       'freeze': '首轮接受后冻结，后续只修订剩余路线，不能换目标'},
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
        from .result_execution import visible_control_texts
        state = load_json(self.current['evidence']['state']['path'])
        return '\n'.join([state.get('visible_text') or '',
            *(text for node in state.get('elements', []) for text in visible_control_texts(state, node))])

    def _bind_targets_feedback(self, plan):
        notes = []
        try:
            bind_plan_targets(plan, self.current, self.current.get('provided_control_ids', []), normalization=notes)
        except ValueError as error:
            return [{'kind': 'TARGET_BINDING_INVALID', 'message': str(error), 'dispatched': False}]
        if notes:
            self.event('screenshot-target-normalized', transforms=notes)
        return []

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
        plan, contract_derivation = compile_contract(plan, fixed_goal or plan.get('goal'))
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
            self.strategy_end_reason = 'protocol_error'
            raise ReactStop('blocked', 'PLAN_ADMISSION_REJECTED: ' + feedback['message'], 'model')
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
        # 编译显式业务范围；不生成未来观察或展示步号。
        # 实际来源与因果仅由捕获和派发收据建立。
        compiled, derivation = plan, contract_derivation
        self.event('screenshot-contract-compiled', derivation=derivation)
        self.requirements = deepcopy(compiled['requirements'])
        self.final_requirement_ids = deepcopy(compiled.get('final_requirement_ids'))
        self.plan = {'steps': compiled['steps'], 'final_presentation_step': compiled.get('final_presentation_step')}
        self.position = 0
        self._plan_accept_route_state(compiled['steps'], compiled.get('final_presentation_step'))
        self.initial_feedback = None
        self.plan_event = self.event('screenshot-plan', phase='first',
            goal=self.frozen_goal, requested_goal=deepcopy(self.requested_goal),
            session_objective=deepcopy((self.task['fragment'].get('session_objective') or {}).get('objective')),
            requirements=deepcopy(self.requirements), steps=deepcopy(self.plan['steps']),
            final_presentation_step=self.plan['final_presentation_step'],
            final_requirement_ids=deepcopy(self.final_requirement_ids),
            contract_derivation=derivation, admission=feedback)
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

    def _navigation_destination_gap(self, step, control_ids):
        """已知不允许的目的地在派发前反馈，交回规划器修订路线。"""
        from urllib.parse import urljoin
        from .candidate_navigation import destination_allowed, excluded_article
        href = None
        if step.get('action') in ('click', 'double_click', 'right_click') and control_ids:
            binding = (self.current.get('controls', {}).get(control_ids[0]) or {}).get('binding') or {}
            href = binding.get('href')
        if not isinstance(href, str) or not href or href.startswith(('javascript:', '#', 'mailto:', 'tel:')):
            return None
        target = urljoin(self.current.get('url') or '', href)
        if target.rstrip('/') == (self.current.get('url') or '').rstrip('/'):
            return None
        if not excluded_article(self.task, target) and destination_allowed(self.task, target, self.page_urls, source=_state_for_observation(self, self.current['observation_id']), operation={**step, 'control_id': control_ids[0]}):
            return None
        return {'kind': 'NAVIGATION_DESTINATION_NOT_PERMITTED',
                'destination': target,
                'message': '该链接的目的地不在本任务许可的导航范围内（精确导航关系不授予目的地域名权限）。'
                           '请改用范围内目标或按原目标另选真实路径；无范围内路径则give_up，不重试同一路径',
                'dispatched': False}

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
        if self._presentation_step_pending:
            self._revalidate_progress()
            _, gaps = verify_final_presentation(self, list(self.verified_checks.values()), self.requirements)
            if (not self._goal_ready() or not gaps
                    or not self._presentation_repair_permitted(self.plan['steps'][self.position:])):
                self._presentation_step_pending = False
                await self._checkpoint('presentation_ready' if not gaps else 'presentation_route_invalid')
                return
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
        requires_target = action in self.TARGET_REQUIRED_ACTIONS or (action == 'scroll' and bool(step.get('target')))
        if requires_target and (not matches or len(matches) != 1):
            await self._checkpoint('binding', feedback={
                'kind': 'TARGET_NOT_UNIQUELY_BOUND',
                'message': '当前观察中目标未唯一绑定；请修订剩余计划或改选有据目标',
                'step_position': self.position, 'matches': len(matches or [])})
            return
        navigation_gap = self._navigation_destination_gap(step, matches or [])
        if navigation_gap is not None:
            # 已知不允许的目的地在派发前反馈给规划器（E），而不是派发后
            # 终止整个attempt。
            await self._checkpoint('navigation_scope', feedback=navigation_gap)
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
        self.latest_attempt_is_current_step = new_attempt
        attempt = (self.latest_attempt or {}) if new_attempt else {}
        dispatch_delta = self.actual_dispatches - before_dispatches
        effective_delta = len(self.trajectory) - before_effective
        completed_wait = (action == 'wait' and (result or {}).get('status') == 'ok'
                          and ((result or {}).get('data') or {}).get('wait_executed') is True)
        advanced = (result or {}).get('status') == 'ok' and (
            (dispatch_delta > 0 and effective_delta > 0) or completed_wait)
        self.event('screenshot-execution-cursor', position=self.position,
                   actual_dispatches_delta=dispatch_delta, effective_steps_delta=effective_delta,
                   wait_executed=completed_wait, advanced=advanced)
        if (result or {}).get('status') != 'ok':
            error = (result or {}).get('error') or {}
            refusal = {'kind': 'STEP_EXECUTION_REFUSED',
                'status': (result or {}).get('status') or 'missing_result',
                'message': str((result or {}).get('summary') or '工具未返回可确认执行结果'),
                'code': error.get('code') or (result or {}).get('code'),
                'data': deepcopy((result or {}).get('data') or {}),
                'error': deepcopy(error), 'dispatched': dispatch_delta > 0,
                'actual_dispatches_delta': dispatch_delta,
                'effective_steps_delta': effective_delta, 'business_attempt_created': new_attempt}
            await self._checkpoint('step_execution_refused', feedback=refusal,
                                   executed=dispatch_delta > 0 and not advanced)
            return
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
                                   executed=dispatch_delta > 0 and not advanced)

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
                'actual_dispatches_delta': attempt.get('actual_dispatches_delta', 0),
                'effective_steps_delta': attempt.get('effective_steps_delta', 0),
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
        if attempt.get('outcome') in ('KNOWN_NO_EFFECT', 'EFFECT_NOT_VERIFIED', 'EFFECT_UNKNOWN'):
            return True
        if (result or {}).get('status') != 'ok':
            return True
        if self._goal_ready() and not self._presentation_step_pending:
            return True
        # Capture/navigation boundaries do not invalidate an executable route.
        return self.position >= len(self.plan['steps'])

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
        # Tail revisions are execution hypotheses. Evidence is selected from
        # actual observations, never reanchored to a future tail position.
        self.route_overrides = {}
        self.final_presentation_override = None

    def _valid_result_rows(self, oid):
        """Candidate locations use the same obligations and verifier as complete."""
        from .screenshot_plan import result_candidate_rows
        return result_candidate_rows(self, oid)

    def _row_in_region(self, oid, cid, region):
        from .screenshot_plan import _evidence_nodes, _region_has_node
        state = _state_for_observation(self, oid)
        node = next((e for e in _evidence_nodes(state or {}) if e['element_id'] == cid), {})
        return _region_has_node(region, node)

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
            if oid not in self.provided_observations and oid != self.current['observation_id']:
                continue
            for row in self._valid_result_rows(oid):
                key = (row.get('requirement_id'), row['control'], row['text'])
                if key in seen:
                    continue
                seen.add(key)
                rows.append({'observation': oid, 'control': row['control'],
                             'text': row['text'], 'still_valid': True,
                             **({'requirement_id': row['requirement_id']} if row.get('requirement_id') else {}),
                             'verified_answer': False,
                             'model_has_seen': oid in self.provided_observations,
                             'regions': [region for region in self.region_registries.get(oid, [])
                                 if self._row_in_region(oid, row['control'], region)],
                             'evidence_hint': '优先用对应region；短数值不要拼接邻居标签作quote',
                             'current_frame': oid == self.current['observation_id']})
        rows.sort(key=lambda row: not row['current_frame'])
        return rows

    def _progress_checkpoint_reason(self, row):
        """Archive route frames; request interpretation at a real evidence boundary."""
        oid = self.current['observation_id']
        state = _state_for_observation(self, oid)
        if state is None:
            return None
        if oid not in self.region_registries:
            self.region_registries[oid] = region_registry(state)
            self.event('screenshot-regions', observation_id=oid,
                       regions=deepcopy(self.region_registries[oid]))
        self._capture_input_progress()
        pending = [r for r in self.requirements if r['id'] not in self.verified_answers]
        for requirement in pending:
            if requirement['kind'] != 'content' or self.position not in self._route_positions(requirement['id']):
                continue
            if not hasattr(self, '_reading_progress'):
                self._reading_progress = set()
            for region in self.region_registries[oid]:
                if _reading_region_relevant(requirement, region):
                    self._reading_progress.add((requirement['id'], self.current.get('url') or '', region['quote']))
        remaining = self.plan['steps'][self.position:]
        if not remaining:
            return None
        # Explicit required UI/content labels appearing together can indicate an
        # earlier answer boundary. This requests interpretation; it never marks
        # the labels or their neighbouring text as verified answers.
        if pending and all(r['kind'] == 'content' for r in pending):
            quotes = {region['quote'] for region in self.region_registries[oid]}
            anchors = [set(text for pair in re.findall(r'「([^」]{2,})」|“([^”]{2,})”',
                        r.get('description') or '') for text in pair if text) for r in pending]
            if all(words and all(any(word in quote for quote in quotes) for word in words) for words in anchors):
                marker = object_sha256({'requirements': [r['id'] for r in pending],
                    'quotes': sorted(quote for quote in quotes if any(
                        _reading_region_relevant(r, {'quote': quote}) for r in pending))})
                seen = getattr(self, '_content_boundaries_seen', set())
                if marker not in seen:
                    self._content_boundaries_seen = seen | {marker}
                    return 'possible_goal_evidence'
        # Once all planned evidence boundaries have been reached, interpretation
        # precedes any potentially redundant tail operation. No facts are assumed.
        routes = [self._route_positions(r['id']) for r in pending]
        if pending and all(positions and max(positions) <= self.position for positions in routes):
            return 'planned_evidence_complete'
        # Inputs have host-bound proofs and never consume interpretation image
        # slots. Count distinct relevant content, not capture IDs or duplicates.
        frames = set()
        for requirement in pending:
            if requirement['kind'] not in ('content', 'result'):
                continue
            for pos in self._route_positions(requirement['id']):
                oid = self.route_frames.get(pos)
                if pos > self.position or not oid or oid in self.provided_observations:
                    continue
                observation = self.observation_records.get(oid) or {}
                if requirement['kind'] == 'result':
                    quotes = {r['text'] for r in self._valid_result_rows(oid)}
                else:
                    quotes = {r['quote'] for r in self.region_registries.get(oid, [])
                              if _reading_region_relevant(requirement, r)}
                if quotes:
                    frames.add((observation.get('url') or '', tuple(sorted(quotes))))
        capacity = max(1, int(getattr(self.choose, 'max_images', 2)))
        if len(frames) >= capacity and remaining[0].get('action') in ('back', 'open_url', 'click'):
            return 'evidence_batch_boundary'
        if row is not None and any(r['kind'] == 'result' for r in pending):
            old = {entry['text'] for entry in self._valid_result_rows(row.get('before_observation_id'))}
            if any(entry['text'] not in old for entry in self._valid_result_rows(oid)):
                return 'key_evidence_visible'
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
            if rid in self.verified_answers or requirement['kind'] == 'input':
                continue
            for oid, observation in reversed(list(self.observation_records.items())):
                if (oid == self.current['observation_id']
                        or (rid, oid) in self.history_supplement_keys
                        or not observation.get('capture_verified')):
                    continue
                state = _state_for_observation(self, oid)
                if state is None:
                    continue
                if requirement['kind'] == 'result':
                    if not self._valid_result_rows(oid):
                        continue
                elif not any(_reading_region_relevant(requirement, region)
                             for region in self.region_registries.get(oid, [])):
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
        """One source-tagged input projection; historical capture is not a new sighting."""
        from .screenshot_effect import input_facts
        known = {}
        for oid, observation in self.observation_records.items():
            if observation.get('document_identity') != state.get('document_identity') or not observation.get('capture_verified'):
                continue
            original = load_json(observation['evidence']['state']['path'])
            elements = {row['element_id']: row for row in original.get('elements', [])}
            for cid, fact in input_facts(original).items():
                visible = fact.get('value_visible') is True
                row = {key: deepcopy(value) for key, value in fact.items()
                       if key not in ('identity', 'value') or key == 'value' and visible}
                row.update(control=cid, label=elements.get(cid, {}).get('text') or '',
                           source_observation=oid, current_frame=oid == self.current['observation_id'],
                           model_has_seen=oid in self.provided_observations)
                # Focus and selection describe only their capture frame. They
                # never license dispatch against a historical control.
                if oid != self.current['observation_id']:
                    for key in ('focused', 'selection_start', 'selection_end', 'all_text_selected'):
                        row.pop(key, None)
                known[cid] = row
        return {'url': state.get('url'), 'inputs': list(known.values()),
                'dispatch_source': '仅当前controls可作为动作目标；历史输入事实不证明当前焦点或几何条件'}

    def _historical_evidence(self):
        """Distinct provided historical sources, without duplicate inputs/answers."""
        rows, seen = [], set()
        verified = {proof.get('quote') for check in self.verified_checks.values()
                    for proof in check.get('evidence', []) if proof.get('quote')}
        for oid, observation in reversed(list(self.observation_records.items())):
            if (oid == self.current['observation_id'] or oid not in self.provided_observations
                    or not observation.get('capture_verified')):
                continue
            regions = []
            for region in self.region_registries.get(oid, []):
                key = (oid, region.get('region_id'))
                if key in seen:
                    continue
                seen.add(key)
                regions.append(deepcopy(region))
            if regions:
                rows.append({'observation': oid, 'url': observation.get('url'),
                             'model_has_seen': True, 'evidence_only': True, 'regions': regions})
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
            'coverage_units': sorted(getattr(self, '_coverage_units', set())),
            'reading_ranges': sorted(getattr(self, '_reading_progress', set())),
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
        if int(getattr(self.choose, 'max_images', 2)) < 2 and 'inspect' in choices:
            choices.remove('inspect')
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
                   'final_requirement_ids': deepcopy(getattr(self, 'final_requirement_ids', None)),
                   'requested_goal': _public_step(self.requested_goal),
                   'session_objective': _public_step((self.task['fragment'].get('session_objective') or {}).get('objective')),
                   'current_observation': oid, 'screenshots': [oid],
                   'visual_evidence': {'scope': 'current_viewport', 'observation': oid,
                                       'image_sha256': self.current['evidence']['image']['sha256'],
                                       'regions': deepcopy(self.region_registries[oid])},
                   'regions': self.region_registries[oid],
                   'controls': self._controls(),
                   'allowed_actions': list(self._allowed_actions()),
                   'pending_steps': [_public_step(row) for row in remaining],
                   'next_checkpoint': next_checkpoint,
                   'reason': reason, 'choices': choices,
                   'rules': {key: value for key, value in BRANCH_RULES.items()
                             if key != 'calculations' or any(
                                 (r.get('evidence_route') or {}).get('source_type') == 'derived_check'
                                 for r in self.requirements)},
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

    def _checkpoint_identity(self, feedback):
        def stable(value):
            if isinstance(value, dict):
                return {k: stable(v) for k, v in value.items() if k not in (
                    'observation', 'observation_id', 'current_observation', 'reason', 'message', 'rationale', 'purpose',
                    'source_observation', 'ref', 'path', 'sha256', 'step_position', 'document', 'document_identity')}
            if isinstance(value, list):
                return [stable(v) for v in value]
            return value
        states = {_stable_region_key(self.observation_records[oid], region)
            for oid, regions in self.region_registries.items() for region in regions
            if any(_reading_region_relevant(requirement, region) for requirement in self.requirements
                   if requirement['id'] not in self.verified_answers)}
        return object_sha256({'goal': self.frozen_goal, 'progress': self._stall_progress_marker(),
            'next_step': stable(_public_step(self.plan['steps'][self.position:self.position + 1])),
            'evidence': sorted(states), 'feedback': stable(feedback),
            'completion': stable(self.completion_feedback),
            'business_state': stable(self._business_state(load_json(self.current['evidence']['state']['path']))),
            'inspection': (self._inspection_visual or {}).get('ref')})

    async def _checkpoint(self, reason, feedback=None, *, executed=False):
        prompt = self._branch_prompt(reason, feedback)
        response = await self._decide(prompt)
        if response is None:  # deterministic duplicate close before a provider call
            return
        arguments = response.get('arguments') or {}
        allowed_actions = self._allowed_actions()
        evidence_only = getattr(self, '_last_evidence_only_request', False)
        if evidence_only:
            from .screenshot_plan import register_evidence_schema
            from jsonschema import Draft202012Validator
            errors = list(Draft202012Validator(register_evidence_schema(
                sorted(self._referenceable_observations()))).iter_errors(arguments))
            if errors:
                self.event('screenshot-evidence-registration', status='insufficient',
                           reason=errors[0].message, dispatched=False)
                self._last_evidence_only_request = False
                return
            decision = arguments
        else:
            decision, record = normalize_decision(arguments, prompt['choices'], allowed_actions, pending_steps=prompt.get('pending_steps', []))
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
            merged = deepcopy(getattr(self, '_partial_answers', {}))
            merged.update(deepcopy(self.verified_answers))
            for row in supplied:
                rid = row['requirement_id']
                previous = merged.get(rid, {})
                answer = deepcopy(row)
                if previous.get('evidence') and any(r['id'] == rid and r['kind'] == 'content' for r in self.requirements):
                    refs = previous['evidence'] + answer.get('evidence', [])
                    answer['evidence'] = list({object_sha256(ref): ref for ref in refs}.values())
                merged[rid] = answer
            ids = set(merged)
            subset = [row for row in self.requirements if row['id'] in ids]
            supplied_ids = [row['requirement_id'] for row in supplied]
            duplicates = [row for index, row in enumerate(supplied)
                          if row['requirement_id'] in supplied_ids[:index]]
            checks, supplement_gaps = verify_completion(self,
                {'answers': list(merged.values()) + duplicates}, subset)
            verified = {row['requirement_id'] for row in checks if row.get('status') == 'VERIFIED'}
            self.verified_answers.update({rid: deepcopy(merged[rid]) for rid in verified})
            self.verified_checks.update({row['requirement_id']: row for row in checks
                                         if row.get('status') == 'VERIFIED'})
            self.verified_requirement_ids = sorted(self.verified_answers)
            self.event('screenshot-progress-evidence', checks=checks, gaps=supplement_gaps,
                       verified_requirement_ids=self.verified_requirement_ids)
        if supplement_gaps:
            self.completion_feedback = {'kind': 'PROGRESS_EVIDENCE_GAPS', 'gaps': supplement_gaps}
        if getattr(self, '_last_evidence_only_request', False):
            self.event('screenshot-evidence-registration',
                       status=('registered' if supplied and not supplement_gaps else
                               'insufficient' if supplied else 'not_relevant'),
                       gaps=supplement_gaps, dispatched=False)
            self._last_evidence_only_request = False
            return
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
                'message': '已核验答案与原引用已保留；只补缺项。current事项在后续相关输入、提交或跳页后会失效；historical仅保留有真实阶段因果的原捕获。末帧核验全部最终结论；过程义务保留真实历史证明。'}
            self.event('screenshot-completion-rejected', gaps=gaps, dispatched=False,
                       verified_requirement_ids=self.verified_requirement_ids)
            self._runlog('completion_gaps', observationId=self.current['observation_id'],
                gaps=[gap.get('kind') for gap in gaps],
                verifiedRequirementIds=self.verified_requirement_ids)
        # Neither dispatch counts, cursor changes nor reworded plans establish
        # progress. Frozen input state and independently verified evidence establish
        # progress; capture IDs and unrelated page text never do.
        if self._stall_check(decision, feedback):
            blocked = getattr(self, '_repair_path_feedback', None)
            self._repair_path_feedback = None
            if blocked and self.state not in ('closed_by_host', 'complete'):
                return await self._checkpoint('repair_path_blocked', blocked)
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
            # as a segment, revalidated before every action. The old tail never receives this permission, and
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
            # A real HTML dialog's exact close control may return pure reading
            # evidence to its final page; unrelated/account-close buttons do not.
            if (self.requirements and all(r.get('kind') == 'content' for r in self.requirements)
                    and element.get('visible') is True and not element.get('inputable')
                    and binding.get('tag') == 'button'
                    and str(element.get('text') or '').strip() in ('关闭', 'Close', '×', '✕')
                    and binding.get('input_type') != 'submit'):
                state = load_json(self.current['evidence']['state']['path'])
                nodes = {node['element_id']: node for node in state.get('elements', [])}
                parent, seen = element.get('parent_id'), set()
                while parent and parent not in seen:
                    seen.add(parent)
                    ancestor = nodes.get(parent) or {}
                    if (ancestor.get('visible') is True
                            and ancestor.get('native_role') in ('dialog', 'alertdialog')):
                        return True
                    parent = ancestor.get('parent_id')
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

    def _track_stall_marker(self, *, count_revisit):
        marker = self._stall_progress_marker()
        if marker not in self._stall_seen_markers:
            self._stall_seen_markers.add(marker)
            self._stall_count = 0
        elif count_revisit:
            self._stall_count += 1
        self._stall_marker = marker
        return marker

    def _close_stall(self):
        self.event('screenshot-no-progress-stall', dispatches=self.actual_dispatches,
                   position=self.position, stall_count=self._stall_count)
        self._range_close('NO_PROGRESS_END', '已访问的目标事实、有效证据和缺项状态反复回访，无进展结束')

    def _stall_check(self, decision, feedback):
        """Account each checkpoint once; only genuinely new state resets stalls."""
        stall_marker = self._track_stall_marker(count_revisit=not self._stall_request_pending)
        self._stall_request_pending = False
        def stable_target(target):
            if not isinstance(target, dict):
                return target
            cid = target.get('control')
            cid = self.current.get('provided_control_numbers', {}).get(str(cid), cid)
            control = self.current.get('controls', {}).get(cid) or {}
            binding = control.get('binding') or (target.get('_source') or {}).get('binding') or {}
            return {key: binding.get(key, target.get(key)) for key in ('selector', 'index', 'tag', 'href', 'text', 'role')
                    if binding.get(key, target.get(key)) is not None}
        steps = decision.get('remaining_plan') or decision.get('steps') or []
        route = [{**{key: step[key] for key in ('action', 'value', 'expected_value', 'keys', 'direction') if key in step},
                  **{key: stable_target(step[key]) for key in ('target', 'end_target') if key in step}} for step in steps]
        key = object_sha256({'facts': stall_marker,
            'missing': sorted(row['id'] for row in self.requirements
                              if row['id'] not in self.verified_checks),
            'gap': self._completion_gap_projection,
            'repair_path': route or decision.get('decision')})
        self.no_progress_keys[key] = self.no_progress_keys.get(key, 0) + 1
        if decision.get('decision') == 'revise' and self.no_progress_keys[key] == 2:
            self._repair_path_feedback = {'kind': 'REPAIR_PATH_BLOCKED', 'dispatched': False,
                'message': '同一事项缺项、相关事实与修复路径已连续两次没有新增证据；该路径已阻断。仅可选择当前工具能执行的另一业务路径；不存在另一可行路径则give_up，不修改冻结事项。'}
            return True
        if ((self.no_progress_keys[key] >= 2)
                or self._stall_count >= NO_PROGRESS_STALL_LIMIT):
            self._close_stall()
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
    return {key: value for key, value in prompt.items()
            if key not in ('system', 'tools', '_images', '_history', '_dispatch_deadline')}


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


def _stable_region_key(observation, region):
    return object_sha256({'url': observation.get('url'), 'quote': region.get('quote')})


def project_model_prompt(prompt):
    """Compact the model view only; persisted capture/decision originals survive."""
    result = deepcopy(prompt)
    if result.get('phase') == 'branch' and 'remaining_plan' in result:
        result['pending_steps'] = result.pop('remaining_plan')
    result.pop('action_facts', None)  # latest attempt and last effective stay explicit
    result.pop('candidate_content', None)  # current/historical regions own these sources
    result['page_directory'] = [row for row in result.get('page_directory', []) if row.get('observed', True)]
    for control in result.get('controls') or []:
        states = control.get('action_states')
        if isinstance(states, dict):
            meaningful = {action: status for action, status in states.items()
                          if status not in ('', None, 'INSUFFICIENT')}
            if meaningful:
                control['action_states'] = meaningful
            else:
                control.pop('action_states', None)
            result['action_state_default'] = '省略的action_states状态为INSUFFICIENT或空；不代表PROVEN可执行'
    controls_by_number = {row.get('number'): row for row in result.get('controls') or []}
    visual = result.get('visual_evidence')
    if isinstance(visual, dict) and visual.get('regions') == result.get('regions'):
        visual.pop('regions', None)
    if isinstance(visual, list):
        for image in visual:
            if image.get('observation_id') != result.get('current_observation'):
                continue
            for mapping in image.get('control_mapping') or []:
                control = controls_by_number.get(mapping.get('number'))
                if control and control.get('control') == mapping.get('control'):
                    mapping.pop('control', None)
                    if mapping.get('bbox') == control.get('bbox'):
                        mapping.pop('bbox', None)
                    image['control_mapping_source'] = 'number引用当前controls；badge仅为角标图像位置'
    confirmed = result.get('confirmed_progress') or []
    verified_quotes = {e.get('quote') for answer in confirmed for e in answer.get('evidence', []) if e.get('quote')}
    seen, history = set(), []
    for source in reversed(result.get('historical_evidence') or []):
        if source.get('current'):
            continue
        regions = []
        for region in source.get('regions', []):
            key = (source.get('observation'), region.get('region_id'), region.get('quote'))
            if key in seen:
                continue
            seen.add(key)
            regions.append(region)
        if regions:
            history.append({key: source[key] for key in ('observation', 'url', 'evidence_only',
                'model_has_seen', 'provided_this_request') if key in source} | {'regions': regions})
    result['historical_evidence'] = list(reversed(history))
    # One source directory per request. Views retain source identities, never
    # become an execution input or merge identical text from different sources.
    catalog = {}
    def catalog_regions(rows, observation):
        for region in rows or []:
            key = str(observation) + ':' + str(region.get('region_id'))
            catalog.setdefault(key, {'observation': observation, **deepcopy(region)})
    catalog_regions(result.get('regions'), result.get('current_observation'))
    for source in result.get('historical_evidence') or []:
        catalog_regions(source.get('regions'), source.get('observation'))
        source['region_refs'] = [str(source.get('observation')) + ':' + str(r.get('region_id'))
                                 for r in source.pop('regions', [])]
    for candidate in result.get('candidate_results') or []:
        catalog_regions(candidate.get('regions'), candidate.get('observation'))
        candidate['region_refs'] = [str(candidate.get('observation')) + ':' + str(r.get('region_id'))
                                    for r in candidate.pop('regions', [])]
        candidate.pop('text', None)
    if catalog:
        result.pop('regions', None)
        result['fact_directory'] = list(catalog.values())
    for progress in result.get('confirmed_progress') or []:
        for proof in progress.get('evidence') or []:
            proof.pop('quote', None)
        progress.pop('observed_result', None)
    rules = result.get('rules')
    if isinstance(rules, dict) and not any((r.get('evidence_route') or {}).get('source_type') == 'derived_check'
                                         for r in result.get('requirements', [])):
        rules.pop('calculations', None)
    return result


def _reading_region_relevant(requirement, region):
    """Conservative lexical relevance for stall accounting, never answer proof."""
    description = requirement.get('description') or ''
    quote = region.get('quote') or ''
    anchors = re.findall(r'「([^」]{2,})」|“([^”]{2,})”', description)
    if any(text in quote for pair in anchors for text in pair if text):
        return True
    # Four-character ranges preserve named concepts without treating common
    # single characters, a new capture or unrelated banners as reading progress.
    for word in re.findall(r'[A-Za-z][A-Za-z0-9_-]{3,}|[\u3400-\u9fff]{4,}', description):
        if word.isascii() and word.lower() in quote.lower():
            return True
        if not word.isascii() and any(word[i:i + 4] in quote for i in range(len(word) - 3)):
            return True
    return False
