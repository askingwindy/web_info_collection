"""策略 3 决策循环：每步一次调用、一个动作；预算与停止条件见 SDD §6。

不继承 RawSessionCore、不调用旧复合执行链；浏览器原子能力经 browser.execute
直接派发，效果判断由本包完成。软截止后不再发新的模型请求或业务动作。
"""
import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import browser
from ..action_stability import post_action_document_scope
from ..batch_core import BudgetStop, OutcomeUnknown
from ..browser import EvidenceStale
from ..session_core import ReactStop
from . import observation, prompt, records

# 预算常量（SDD §6.1）：正常入口内生效，结束阶段预留。
MIN_EFFECTIVE_STEPS = 5
MAX_EFFECTIVE_STEPS = 12
MAX_BROWSER_DISPATCHES = 15
NO_EFFECT_LIMIT = 3
REPEAT_REJECT_LIMIT = 3
EXPLORE_HTTP_BUDGET = 34      # 探索阶段请求上限，预留终态决策与结束加工
WAIT_DURATION_MS = 1000
SCROLL_DISTANCE = 480


class StepwiseStop(Exception):
    """策略 3 自身的有界停止（非程序故障）；携带 stop_reason/failure_class。"""

    def __init__(self, stop_reason, stop_summary, failure_class=None, unknown=False):
        super().__init__(stop_reason + ': ' + str(stop_summary))
        self.stop_reason = stop_reason
        self.stop_summary = stop_summary
        self.failure_class = failure_class
        self.unknown = unknown


def stepwise_caller(ledger, task, attempt_id, *, parent_job=None, runlog=None):
    """策略 3 的模型调用封装：唯一 stepwise-decision job kind，单层网关纠正。

    三类调用（决策/回写/判定）共用同一 attempt 身份与请求账；tool_choice
    强制选择本次声明的唯一函数。
    """
    from copy import deepcopy

    from ..agent_controller import _job_request_count
    from ..model_gateway import ModelGateway, ProviderRejected
    from ..planning import object_sha256

    gateway = None

    def usage():
        with ledger.connect() as con:
            return ledger.session_http_usage(con, attempt_id)

    def guard_unresolved():
        pending = usage()['unresolved']
        if pending:
            raise OutcomeUnknown('Original attempt has an unresolved request; no new dispatch: ' + pending)

    async def call(*, phase, system, tools, user_text, images, reasoning_effort,
                   dispatch_deadline, round_index, tool_name, request_deadline=None):
        nonlocal gateway
        payload = {'protocol': 'stepwise', 'attempt_id': attempt_id,
                   'task_id': task['task_id'], 'site_uri': task['site_uri'],
                   'phase': phase, 'round': round_index,
                   'prompt_sha256': object_sha256({'text': user_text, 'images': images})}
        if parent_job is not None:
            payload['parent_job_id'] = parent_job['id']
        jid = ledger.enqueue('stepwise-decision', payload)
        old = ledger.get(jid)
        if old['state'] == 'done' and old.get('result') is not None:
            return deepcopy(old['result'])
        if old['state'] != 'queued' or old['attempts']:
            raise OutcomeUnknown('Original stepwise call unresolved; reconcile before retry')
        guard_unresolved()
        try:
            job = ledger.claim('stepwise-decision', job_id=jid,
                               **({'parent_job': parent_job} if parent_job is not None else {}))
        except ValueError as error:
            if _job_request_count(ledger, jid):
                raise OutcomeUnknown('Original stepwise call claim has request records; reconcile') from error
            raise ReactStop('blocked', 'Stepwise call claim failed before any request: ' + str(error), 'program')
        if not job:
            raise ReactStop('blocked', 'Stepwise call could not be claimed', 'program')
        try:
            if gateway is None:
                gateway = ModelGateway(ledger, runlog=runlog)
            output_limit = min(2048, ledger.config['model']['max_completion_tokens'])
            response = await asyncio.to_thread(
                gateway.call_tool, job, 'stepwise:' + phase, user_text, tools,
                system=system, images=list(images), attempts=2,
                output_limit=output_limit, reasoning_effort=reasoning_effort,
                attempt_id=attempt_id, dispatch_deadline=dispatch_deadline,
                request_deadline=request_deadline,
                tool_choice=prompt.forced_tool_choice(tool_name))
            ledger.finish(job, result=response)
            return response
        except ProviderRejected as error:
            ledger.finish(job, 'failed', error=type(error).__name__ + ': ' + str(error))
            raise
        except OutcomeUnknown as error:
            ledger.finish(job, 'review_required', error='unknown:' + type(error).__name__)
            raise
        except BaseException as error:
            ledger.finish(job, 'review_required', error=type(error).__name__)
            raise

    call.session_usage = usage
    call.requests_used = lambda: usage()['used']
    call.guard_unresolved = guard_unresolved
    return call


def exception_classification(error):
    """确定异常责任；只分类，不重试或改写已派发请求。"""
    from playwright.async_api import Error as BrowserError
    from ..model_gateway import ProviderFinishIncomplete

    if (isinstance(error, ProviderFinishIncomplete)
            or isinstance(error, ValueError)
            and str(error).startswith(('bounded_', 'consumer_protocol_no_progress'))):
        return 'protocol_error', 'model'
    failure_class = getattr(error, 'failure_class', None)
    if failure_class:
        return 'error', failure_class
    if isinstance(error, BrowserError) and 'UNSUPPORTED_GEOMETRY' in str(error):
        return 'capture_stale', 'collector'
    if isinstance(error, BrowserError) and 'net::ERR_' in str(error):
        return 'error', 'network'
    return 'error', 'program'


class StepwiseSession:
    """一次 attempt 的逐步循环；全部原始记录落盘后才允许结束加工。"""

    def __init__(self, task, evidence, call, page, *, attempt_id, host_limits=None,
                 requested_goal=None, site_tasks=(), runlog=None, entry_ready=False):
        self.task = task
        self.evidence = Path(evidence)
        self.journal = records.Journal(self.evidence)
        self.root = self.journal.root
        self.call = call
        self.page = page
        self.attempt_id = attempt_id
        self.host_limits = host_limits or {}
        self.requested_goal = requested_goal
        self.site_tasks = list(site_tasks)
        self.runlog = runlog
        self.entry_ready = bool(entry_ready)
        self.mode = 'specified' if requested_goal is not None else 'autonomous'
        self.allowed_hosts = observation.allowed_hosts(task)

        self.goal = None
        self.note = ''
        self.history = []
        self.feedback = ''
        self.decision_round = 0
        self.explore_calls = 0
        self.dispatches = 0
        self.effective = 0
        self.no_effect_run = 0
        self.repeat_reject_run = 0
        self.last_reject_key = None
        self.dispatch_rows = []
        self.delivery_seq = 0
        self.failed_dispatches = []
        self.complete_decision = None
        self.complete_completed_at = None
        self.context_trims = []

        self.stop_reason = None
        self.stop_summary = None
        self.failure_class = None
        self.unknown = False
        self.current = None
        self._raw_receipt = None

    # ------------------------------------------------------------ 时间预算
    def _soft_deadline(self):
        if not self.host_limits:
            return None
        return self.host_limits['started_monotonic'] + self.host_limits['soft_seconds']

    def _hard_deadline(self):
        if not self.host_limits:
            return None
        return self.host_limits['started_monotonic'] + self.host_limits['hard_seconds']

    def _soft_deadline_hit(self):
        deadline = self._soft_deadline()
        return deadline is not None and time.monotonic() >= deadline

    def _stop(self, reason, summary, failure_class=None, unknown=False):
        raise StepwiseStop(reason, summary, failure_class=failure_class, unknown=unknown)

    # ------------------------------------------------------------ 主循环
    async def run(self):
        try:
            await self._open()
            await self._loop()
        except StepwiseStop as stop:
            self.stop_reason = stop.stop_reason
            self.stop_summary = stop.stop_summary
            self.failure_class = stop.failure_class
            self.unknown = stop.unknown
        except asyncio.CancelledError:
            raise
        except OutcomeUnknown as error:
            self.stop_reason, self.stop_summary = 'unknown', str(error)
            self.failure_class, self.unknown = 'unknown', True
        except ReactStop as error:
            self.stop_reason = 'blocked'
            self.stop_summary = str(error)
            self.failure_class = getattr(error, 'failure_class', None) or 'program'
        except BudgetStop as error:
            self.stop_reason = 'http_budget'
            self.stop_summary = str(error)
            self.failure_class = 'model'
        except (EvidenceStale, browser.SnapshotFault) as error:
            self.stop_reason = 'capture_stale'
            self.stop_summary = type(error).__name__ + ': ' + str(error)
            self.failure_class = ('collector' if isinstance(error, EvidenceStale)
                                  or 'UNSUPPORTED_GEOMETRY' in str(error) else 'program')
        except Exception as error:
            self.stop_reason, self.failure_class = exception_classification(error)
            self.stop_summary = type(error).__name__ + ': ' + str(error)
        receipt = self._close()
        return self._summary(receipt)

    async def _open(self):
        """入口帧：复用消费者已打开的页面；以策略 3 作用域同步捕获首帧。"""
        self.journal.write_boundary(self.task, mode=self.mode,
                                    requested_goal=self.requested_goal,
                                    site_tasks=self.site_tasks)
        if not self.entry_ready:
            await self.page.goto(self.task['initial_url'], wait_until='domcontentloaded',
                                 timeout=30000)
        self.current = self.journal.add_frame(await self._capture())

    async def _capture(self):
        scope = self._frame_scope(self.page.url)
        return await browser.capture(self.page, action_scope=scope)

    def _frame_scope(self, url):
        # 帧取证作用域沿用宿主观察语义（post_action_document：观察性配对，
        # 不授予派发许可）；策略 3 不引入新的稳定域协议。
        return post_action_document_scope({'url': url})

    async def _loop(self):
        pending_result = None   # 上一次实际派发行，等待下一次合法决策的 last_step_result
        while True:
            if self._soft_deadline_hit():
                self._stop('soft_deadline', '软截止到达，停止新增模型请求与业务动作', 'collector')
            complete_only = (self.effective >= MAX_EFFECTIVE_STEPS
                             or self.dispatches >= MAX_BROWSER_DISPATCHES
                             or self.explore_calls >= EXPLORE_HTTP_BUDGET)
            frame = self.current
            rows = observation.actionable_rows(frame['state'])
            numbered = prompt.numbered_png(Path(frame['png']).read_bytes(), rows)
            self.journal.renumbered_copy(frame, numbered)
            user_text, trimmed = prompt.build_decision_message(
                mode=self.mode, requested_goal_text=self._requested_text(),
                task_goal=self.goal, progress=self._progress_text(), rows=rows,
                state=frame['state'], history=self.history,
                feedback=('宿主提示：只能结束（返回complete）。' if complete_only else '')
                + self.feedback,
                note=self.note, site_tasks=self.site_tasks, complete_only=complete_only)
            if trimmed:
                self.context_trims.extend([{'round': self.decision_round + 1, **item} for item in trimmed])
                if self.runlog is not None:
                    self.runlog.info('context_trimmed', round=self.decision_round + 1,
                                     blocks=[item['block'] for item in trimmed])
            self.explore_calls += 1
            response = await self.call(
                phase='decision', system=self._system_prompt(),
                tools=prompt.next_action_tools(autonomous=self.mode == 'autonomous'),
                user_text=user_text, images=[frame['refs']['numbered']['path']],
                reasoning_effort='low', dispatch_deadline=self._soft_deadline(),
                request_deadline=self._hard_deadline(),
                round_index=self.decision_round + 1, tool_name='next_action')
            arguments = response.get('arguments') or {}
            self.decision_round += 1
            invalid = self._validate_decision(arguments, complete_only)
            # 目标/笔记变化与决策原文先落盘（含被拒绝的决策）。
            goal_before = self.goal
            if invalid is None and self.mode == 'autonomous':
                goal = arguments.get('task_goal')
                if isinstance(goal, str) and goal.strip() and goal.strip() != self.goal:
                    self.goal = goal.strip()[:prompt.LIMIT_TASK_GOAL * 2]
            note_before = self.note
            if invalid is None and isinstance(arguments.get('note'), str):
                note = arguments['note']
                self.note = note.strip()[:prompt.LIMIT_NOTE] if note else ''
            self.journal.add_decision(
                round_index=self.decision_round, frame_id=frame['frame_id'],
                request_id=response.get('request_id'), arguments=arguments,
                goal_before=goal_before, goal_after=self.goal,
                note_before=note_before, note_after=self.note,
                model_ref={'request_id': response.get('request_id'),
                           'tool_call_id': response.get('tool_call_id')},
                **({'rejected': invalid} if invalid else {}))
            if invalid:
                self._record_reject(frame, invalid, arguments)
                continue
            # last_step_result 绑定它实际观察的上一派发后帧（下一次合法决策）。
            if pending_result is not None:
                pending_result['step_result'] = str(arguments.get('last_step_result') or '')[:600]
                pending_result['result_round'] = self.decision_round
                pending_result = None
            if arguments['action'] == 'complete':
                if await self._handle_complete(frame, arguments):
                    return
                continue
            try:
                operation, element = observation.bind_action(frame['state'], rows, arguments)
            except observation.ActionRejected as rejected:
                self._record_reject(frame, rejected.reason, arguments)
                continue
            try:
                await browser.verify_execution_state(
                    self.page, frame['state'], action_scope=self._frame_scope(frame['state'].get('url')))
            except EvidenceStale:
                self.current = self.journal.add_frame(await self._capture())
                self.feedback = '画面已变化，上一决策作废；请按当前画面重新决策。'
                continue
            outcome = await self._dispatch(frame, operation, element, arguments)
            if outcome == 'delivered':
                pending_result = self.dispatch_rows[-1]
                self.current = self.journal.frames[pending_result['after_frame']]
            elif outcome == 'recaptured':
                self.current = self.journal.frames[self.failed_dispatches[-1]['after_frame']]
            # 'failed'：画面未捕获，当前帧保持不变，反馈已写。

    # ------------------------------------------------------------ 决策校验
    def _validate_decision(self, arguments, complete_only):
        if not isinstance(arguments, dict):
            return 'DECISION_NOT_OBJECT'
        for field in ('last_step_result', 'page_name', 'precondition', 'thought',
                      'user_goal', 'action', 'expected_result'):
            if field not in arguments:
                return 'MISSING_FIELD:' + field
        if arguments.get('action') not in observation.SUPPORTED_ACTIONS:
            return 'UNKNOWN_ACTION'
        if self.mode == 'autonomous':
            goal = arguments.get('task_goal')
            if not (isinstance(goal, str) and goal.strip() and goal.strip() != '同上'):
                return 'TASK_GOAL_REQUIRED'
        if self.decision_round > 1 and not str(arguments.get('last_step_result') or '').strip():
            return 'LAST_STEP_RESULT_REQUIRED'
        if complete_only and arguments.get('action') != 'complete':
            return 'COMPLETE_ONLY_EXPECTED'
        return None

    def _record_reject(self, frame, reason, arguments):
        key = prompt.compact_json({
            'view': observation.business_view(frame['state']),
            'action': arguments.get('action') if isinstance(arguments, dict) else None,
            'element': arguments.get('element') if isinstance(arguments, dict) else None,
            'text': arguments.get('text') if isinstance(arguments, dict) else None,
            'keys': arguments.get('keys') if isinstance(arguments, dict) else None,
            'direction': arguments.get('direction') if isinstance(arguments, dict) else None,
            'option': arguments.get('option') if isinstance(arguments, dict) else None})
        if key == self.last_reject_key:
            self.repeat_reject_run += 1
        else:
            self.repeat_reject_run = 1
            self.last_reject_key = key
        if self.repeat_reject_run >= REPEAT_REJECT_LIMIT:
            self._stop('repeat_reject', '同视图同一动作连续 %d 次派发前拒绝' % REPEAT_REJECT_LIMIT, 'model')
        self.feedback = '上一决策被拒绝：%s。请修正后重试。' % reason

    # ------------------------------------------------------------ complete
    async def _handle_complete(self, frame, arguments):
        """核对终态帧一致后接受 complete；过时则重新捕获并重新决策。返回是否接受。"""
        try:
            await browser.verify_execution_state(
                self.page, frame['state'], action_scope=self._frame_scope(frame['state'].get('url')))
        except EvidenceStale:
            self.current = self.journal.add_frame(await self._capture())
            self.feedback = '画面已变化，complete 作废；请按当前画面重新决策。'
            return False
        self.complete_decision = arguments
        self.complete_completed_at = datetime.now(timezone.utc).isoformat()
        if arguments.get('status') != 'success':
            self._stop('complete_infeasible', '模型声明任务无法完成', 'collector')
        if self.effective < MIN_EFFECTIVE_STEPS:
            self._stop('short_flow',
                       '有效动作不足 %d（实际 %d），如实短流程结束，不保存不补动作'
                       % (MIN_EFFECTIVE_STEPS, self.effective), 'collector')
        self.stop_reason = 'complete_success'
        self.stop_summary = '模型完成声明已核对终态帧'
        return True

    # ------------------------------------------------------------ 派发与效果
    async def _dispatch(self, frame, operation, element, arguments):
        """执行一次浏览器动作并记录。返回 delivered / failed / recaptured。"""
        seq, dispatch, dispatch_ref = self.journal.begin_dispatch(
            frame_id=frame['frame_id'], operation=operation, element=element)
        self.dispatches += 1
        action = operation['action_type']
        execution = {}
        if action == 'scroll':
            execution['distance'] = SCROLL_DISTANCE
        if action == 'wait':
            execution['duration_ms'] = WAIT_DURATION_MS
        execution_error = None
        unknown_dispatch = False
        try:
            await browser.execute(self.page, action, dict(operation['arguments']), execution)
        except TimeoutError as error:
            execution_error, unknown_dispatch = 'dispatch_unknown:' + str(error), True
        except Exception as error:
            if type(error) is ValueError:
                execution_error = 'dispatch_failed:' + type(error).__name__ + ': ' + str(error)
            else:
                # A transport/program exception may occur after dispatch.
                # Preserve the dispatch and its unsettled action result first.
                record = self.journal.finish_step(
                    seq=seq, dispatch_ref=dispatch_ref, operation=operation, element=element,
                    dispatched=True, action_executed=None,
                    execution_error=type(error).__name__ + ': ' + str(error),
                    before_frame=frame['frame_id'], after_frame=None, effect='dispatch_error',
                    effective=False, omittable=False, omit_reason='dispatch_error',
                    postconditions_checked=False)
                self._remember_failed_dispatch(seq, record, None)
                raise
        if unknown_dispatch:
            # 派发结果未知：保留 unknown，不重做点击或输入。
            record = self.journal.finish_step(
                seq=seq, dispatch_ref=dispatch_ref, operation=operation, element=element,
                dispatched=True, action_executed=None, execution_error=execution_error,
                before_frame=frame['frame_id'], after_frame=None, effect='unknown',
                effective=False, omittable=False, omit_reason='dispatch_result_unknown',
                postconditions_checked=False)
            self._remember_failed_dispatch(seq, record, None)
            self._stop('unknown_dispatch', '浏览器派发结果未知，保留原始记录不重发',
                       'unknown', unknown=True)
            return  # 不可达：_stop 必然抛出
        after_frame = None
        postconditions_checked = False
        try:
            captured = await self._capture()
            after = self.journal.add_frame(captured)
            after_frame = after['frame_id']
            postconditions_checked = True
        except Exception as error:
            record = self.journal.finish_step(
                seq=seq, dispatch_ref=dispatch_ref, operation=operation, element=element,
                dispatched=True, action_executed=execution_error is None,
                execution_error=(execution_error + '; ' if execution_error else '')
                                + 'after_capture:' + type(error).__name__ + ': ' + str(error),
                before_frame=frame['frame_id'], after_frame=None, effect='capture_failed',
                effective=False, omittable=False, omit_reason='after_capture_failed',
                postconditions_checked=False)
            self._remember_failed_dispatch(seq, record, None)
            raise
        if execution_error:
            # 派发失败：留证、反馈，不计交付；不存在的 select 选项已在派发前拒绝。
            record = self.journal.finish_step(
                seq=seq, dispatch_ref=dispatch_ref, operation=operation, element=element,
                dispatched=True, action_executed=False, execution_error=execution_error,
                before_frame=frame['frame_id'], after_frame=after_frame,
                effect='dispatch_failed', effective=False, omittable=False,
                omit_reason=execution_error, postconditions_checked=postconditions_checked,
                after_state=self.journal.frames[after_frame]['state'] if after_frame else None)
            self._remember_failed_dispatch(seq, record, after_frame)
            self.feedback = '动作派发失败：%s。请换一种方式。' % execution_error[:120]
            return 'recaptured' if after_frame else 'failed'
        # 落地范围与排除检查（重定向/popup 落地后再检查）。
        after_state = self.journal.frames[after_frame]['state']
        issue = observation.exclusion_issues(after_state.get('url'), after_state)
        if issue is None and not observation.destination_allowed(after_state.get('url'),
                                                                 self.allowed_hosts):
            issue = 'out_of_scope:' + str(after_state.get('url'))
        if issue:
            record = self.journal.finish_step(
                seq=seq, dispatch_ref=dispatch_ref, operation=operation, element=element,
                dispatched=True, action_executed=True, execution_error=None,
                before_frame=frame['frame_id'], after_frame=after_frame,
                effect='landing_rejected', effective=False, omittable=False,
                omit_reason=issue, postconditions_checked=postconditions_checked,
                after_state=after_state)
            self._remember_failed_dispatch(seq, record, after_frame)
            self._stop('landing_rejected', '落地页超出候选范围或触发排除规则：' + issue, 'collector')
        # 效果判断：wait 不计有效步；确认无效果才可省略。
        before_state = frame['state']
        document_changed = observation.document_changed(before_state, after_state)
        omittable, omit_reason = observation.action_omittable(before_state, after_state, action)
        effective = action != 'wait' and not omittable
        if omittable:
            self.no_effect_run += 1
        else:
            self.no_effect_run = 0
        if effective:
            self.effective += 1
        delivery_index = None
        if not omittable:
            self.delivery_seq += 1
            delivery_index = self.delivery_seq
        record = self.journal.finish_step(
            seq=seq, dispatch_ref=dispatch_ref, operation=operation, element=element,
            dispatched=True, action_executed=True, execution_error=None,
            before_frame=frame['frame_id'], after_frame=after_frame,
            effect=('document_changed' if document_changed else
                    'no_effect' if omittable else 'view_changed'),
            effective=effective, omittable=omittable, omit_reason=omit_reason,
            postconditions_checked=postconditions_checked,
            delivery_index=delivery_index, after_state=after_state)
        row = {'dispatch_seq': seq,
               'step_file': 'step_%03d.json' % (delivery_index or seq),
               'dispatch_file': 'dispatch-%03d.json' % seq,
               'frame_id': frame['frame_id'],
               'after_frame': after_frame,
               'operation': operation, 'element': element,
               'decision': dict(arguments),
               'dispatched_at': dispatch['dispatched_at'],
               'ended_at': record['ended_at'],
               'effective': effective, 'omittable': omittable,
               'omit_reason': omit_reason, 'step_result': '', 'result_round': None}
        self.dispatch_rows.append(row)
        self._history_append(row, document_changed)
        if self.no_effect_run >= NO_EFFECT_LIMIT:
            self._stop('no_effect', '连续 %d 次确认无效果' % NO_EFFECT_LIMIT, 'model')
        self.feedback = ''
        return 'delivered'

    def _remember_failed_dispatch(self, seq, record, after_frame):
        self.failed_dispatches.append({
            'dispatch_seq': seq,
            'step_file': str((self.root / ('failed-%03d.json' % seq)).resolve()),
            'after_frame': after_frame, 'ended_at': record['ended_at'],
            'action_executed': record['action_executed'],
            'error': record['execution_error']})

    def _history_append(self, row, document_changed):
        action = row['operation']['action_type']
        arguments = row['operation']['arguments']
        target = ''
        if row['element'] is not None:
            target = (row['element'].get('text') or '').strip()[:40]
        if action == 'type':
            detail = '输入「%s」' % str(arguments.get('text', ''))[:40]
        elif action == 'scroll':
            detail = '向%s滚动' % arguments.get('direction', '')
        elif action == 'hotkey':
            detail = '按「%s」' % '+'.join(arguments.get('keys') or [])
        elif action in ('back', 'wait'):
            detail = action
        elif action == 'select':
            detail = '在「%s」选择「%s」' % (target, str(arguments.get('option', ''))[:40])
        else:
            detail = '点击' + ('「%s」' % target if target else '')
        result = ('页面已切换' if document_changed else
                  '画面无实质变化' if row['omittable'] else '画面已变化')
        self.history.append(('%s，%s' % (detail, result))[:prompt.LIMIT_HISTORY_RECENT])
        self.history = self.history[-prompt.LIMIT_HISTORY_ITEMS:]

    # ------------------------------------------------------------ 文本辅助
    def _system_prompt(self):
        if self.mode == 'specified':
            return prompt.specified_system_prompt()
        return prompt.SYSTEM_PROMPT

    def _requested_text(self):
        if self.mode != 'specified':
            return None
        from . import finalize
        return finalize.specified_instruction(self.requested_goal,
                                              self.task.get('app_name') or self.task.get('site_uri'))

    def _progress_text(self):
        base = '已派发 %d 次，有效动作 %d（保存需 %d–%d）；连续无效果 %d。' % (
            self.dispatches, self.effective, MIN_EFFECTIVE_STEPS, MAX_EFFECTIVE_STEPS,
            self.no_effect_run)
        if self.mode == 'autonomous' and self.goal:
            base += '当前任务：' + self.goal
        return base

    # ------------------------------------------------------------ 收口
    def delivery_plan(self):
        delivered = [row for row in self.dispatch_rows if not row['omittable']]
        omitted = [{'dispatch_seq': row['dispatch_seq'], 'reason': row['omit_reason']}
                   for row in self.dispatch_rows if row['omittable']]
        return delivered, omitted

    def _close(self):
        delivered, omitted = self.delivery_plan()
        steps_payload = [{'step_file': row['step_file'], 'dispatched': True,
                          'after_frame': row['after_frame'], 'ended_at': row['ended_at'],
                          'effective': row['effective'], 'omittable': row['omittable']}
                         for row in self.dispatch_rows]
        steps_payload += [{'step_file': item['step_file'],
                           'dispatched': True, 'action_executed': item['action_executed'],
                           'after_frame': item.get('after_frame'),
                           'ended_at': item['ended_at'], 'effective': False,
                           'omittable': False, 'failed': True}
                          for item in self.failed_dispatches]
        terminal = {'schema_version': 'stepwise-terminal-1',
                    'strategy': {'id': 'stepwise'},
                    'mode': self.mode,
                    'task_goal': self.goal,
                    'requested_goal': self.requested_goal,
                    'stop_reason': self.stop_reason,
                    'stop_summary': self.stop_summary,
                    'failure_class': self.failure_class,
                    'unknown': self.unknown,
                    'effective_steps': self.effective,
                    'actual_dispatches': self.dispatches,
                    'decision_rounds': self.decision_round,
                    'explore_calls': self.explore_calls,
                    'complete_decision': self.complete_decision,
                    'completed_at': self.complete_completed_at,
                    'final_frame': self.current['frame_id'] if self.current else None,
                    'steps': steps_payload,
                    'context_trims': self.context_trims,
                    'sealed_at': datetime.now(timezone.utc).isoformat()}
        if self.stop_reason == 'complete_success' and self.current is not None:
            self.journal.finish_complete_step(
                delivery_index=self.delivery_seq + 1,
                state=self.current['state'],
                decision=self.complete_decision or {},
                completed_at=self.complete_completed_at,
                frame=self.current)
        terminal_ref = self.journal.write_terminal(terminal)
        self.journal.write_delivery_map(
            [{'step_id': index, 'dispatch_file': row['dispatch_file'],
              'step_file': row['step_file'], 'frame_id': row['frame_id'],
              'after_frame': row['after_frame'], 'result_round': row['result_round']}
             for index, row in enumerate(delivered, 1)],
            {'frame_id': self.current['frame_id'] if self.current else None,
             'decision': self.complete_decision,
             'completed_at': self.complete_completed_at},
            omitted)
        self._raw_receipt = self.journal.seal(terminal_ref)
        return self._raw_receipt

    def _summary(self, receipt):
        from ..collection_strategy import outcome_facts
        goal_status = 'completed' if self.stop_reason == 'complete_success' else 'unconfirmed'
        end_reason = {'complete_success': 'goal_completed',
                      'complete_infeasible': 'no_path',
                      'short_flow': 'no_path',
                      'no_effect': 'no_progress',
                      'repeat_reject': 'no_progress',
                      'soft_deadline': 'user_stopped'}.get(self.stop_reason, 'unknown')
        if self.unknown:
            end_reason = 'unknown'
        return {'strategy': {'id': 'stepwise'},
                'stop_reason': self.stop_reason,
                'stop_summary': self.stop_summary,
                'failure_class': self.failure_class,
                'unknown': self.unknown,
                'host_failure': False,
                'effective_steps': self.effective,
                'actual_actions': self.dispatches,
                'short_flow': self.stop_reason == 'short_flow',
                'mode': self.mode,
                'task_goal': self.goal,
                'raw_receipt': receipt,
                'end': outcome_facts(goal_status=goal_status, end_reason=end_reason,
                                     eligibility='unresolved', save_status='not_saved')}
