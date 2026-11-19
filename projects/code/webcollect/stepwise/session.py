"""策略 3 决策循环：每步一次调用、一个动作；预算与停止条件见 SDD §6。

不继承 RawSessionCore、不调用旧复合执行链；浏览器原子能力经 browser.execute
直接派发，效果判断由本包完成。软截止后不再发新的模型请求或业务动作。
"""
import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import browser
from ..action_stability import navigation_carrier, post_action_document_scope
from ..batch_core import BudgetStop, JobLeaseLost, OutcomeUnknown
from ..browser import EvidenceStale
from ..session_core import ReactStop
from . import finalize, observation, prompt, records

# 预算常量（SDD §6.1）：正常入口内生效，结束阶段预留。
MIN_EFFECTIVE_STEPS = 5
MAX_EFFECTIVE_STEPS = 12
MAX_BROWSER_DISPATCHES = 20
NO_EFFECT_LIMIT = 3
REPEAT_REJECT_LIMIT = 3
EXPLORE_HTTP_BUDGET = 34      # 实际 HTTP 请求；40 次总限中为回写和判定保留 6 次
DOM_OBSERVATION_SECONDS = 30  # 20 workers contend for Chrome; only the read-only observation gets this budget.
COMPLETE_REJECTION_LIMIT = 2
NAVIGATION_WAIT_MS = 5000
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
    from threading import Event

    from ..agent_controller import _job_request_count
    from ..model_gateway import ModelGateway, ProviderRejected
    from ..planning import object_sha256

    gateway = None
    cancelled = Event()

    def usage():
        with ledger.connect() as con:
            return ledger.session_http_usage(con, attempt_id)

    def guard_unresolved():
        pending = usage()['unresolved']
        if pending:
            raise OutcomeUnknown('Original attempt has an unresolved request; no new dispatch: ' + pending)

    async def call(*, phase, system, tools, user_text, images, reasoning_effort,
                   dispatch_deadline, round_index, tool_name, request_deadline=None):
        attempts = 2
        if phase == 'decision':
            attempts = min(attempts, EXPLORE_HTTP_BUDGET - usage()['used'])
            if attempts <= 0:
                raise BudgetStop('Stepwise decision HTTP budget exhausted; finalization reserve retained')
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
        except JobLeaseLost:
            raise
        except ValueError as error:
            if _job_request_count(ledger, jid):
                raise OutcomeUnknown('Original stepwise call claim has request records; reconcile') from error
            raise ReactStop('blocked', 'Stepwise call claim failed before any request: ' + str(error), 'program')
        if not job:
            raise ReactStop('blocked', 'Stepwise call could not be claimed', 'program')
        def dispatch_and_settle():
            nonlocal gateway
            try:
                if gateway is None:
                    gateway = ModelGateway(ledger, runlog=runlog)
                    gateway.stop_pending_dispatch = cancelled.is_set
                if cancelled.is_set():
                    raise InterruptedError('Stepwise call cancelled before dispatch')
                response = gateway.call_tool(job, 'stepwise:' + phase, user_text, tools,
                    system=system, images=list(images), attempts=attempts,
                    output_limit=min(2048, ledger.config['model']['max_completion_tokens']),
                    reasoning_effort=reasoning_effort, attempt_id=attempt_id,
                    dispatch_deadline=dispatch_deadline, request_deadline=request_deadline,
                    tool_choice=prompt.forced_tool_choice(tool_name))
            except InterruptedError as error:
                state = 'review_required' if _job_request_count(ledger, jid) else 'failed'
                ledger.finish(job, state, error=str(error))
                raise
            except ProviderRejected as error:
                ledger.finish(job, 'failed', error=type(error).__name__ + ': ' + str(error))
                raise
            except OutcomeUnknown as error:
                try:
                    ledger.finish(job, 'review_required', error='unknown:' + type(error).__name__)
                except JobLeaseLost as lost:
                    error.add_note(str(lost))
                raise
            except JobLeaseLost:
                raise
            except Exception as error:
                ledger.finish(job, 'review_required', error=type(error).__name__)
                raise
            ledger.finish(job, result=response)
            return response

        # The thread which receives the response settles its original job even if its browser task exits.
        pending = asyncio.get_running_loop().run_in_executor(None, dispatch_and_settle)
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            cancelled.set()
            pending.add_done_callback(lambda completed: None if completed.cancelled() else completed.exception())
            raise

    call.session_usage = usage
    call.requests_used = lambda: usage()['used']
    call.guard_unresolved = guard_unresolved
    return call


def exception_classification(error):
    """确定异常责任；只分类，不重试或改写已派发请求。"""
    from playwright.async_api import Error as BrowserError, TimeoutError as BrowserTimeout
    from ..model_gateway import ProviderFinishIncomplete

    failure_class = getattr(error, 'failure_class', None)
    if failure_class == 'interrupted' or isinstance(error, InterruptedError):
        return 'interrupted', 'interrupted'
    if failure_class:
        return 'error', failure_class
    if isinstance(error, BudgetStop):
        return 'http_budget', 'model'
    if isinstance(error, (TimeoutError, BrowserTimeout)):
        return 'capture_timeout', 'collector'
    if (isinstance(error, ProviderFinishIncomplete)
            or isinstance(error, ValueError)
            and str(error).startswith(('bounded_', 'consumer_protocol_no_progress'))):
        return 'protocol_error', 'model'
    if isinstance(error, BrowserError) and 'UNSUPPORTED_GEOMETRY' in str(error):
        return 'capture_stale', 'collector'
    if isinstance(error, BrowserError) and 'net::ERR_' in str(error):
        return 'error', 'network'
    return 'error', 'program'


def frames_pixels_equal(left, right):
    """Compare the clean captured pixels, independent of PNG encoding metadata."""
    from PIL import Image

    with Image.open(left['png']) as first, Image.open(right['png']) as second:
        return (first.size == second.size
                and first.convert('RGB').tobytes() == second.convert('RGB').tobytes())


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
        self.mode = 'specified' if requested_goal else 'autonomous'
        self.allowed_hosts = observation.allowed_hosts(task)

        self.goal = None
        self.initial_goal = None
        self.task_modifications = 0
        self.complete_rejections = []
        self.infeasible_rejections = 0
        self.unsafe_omissions = []
        self._popup_sources = {}
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

    def _requests_used(self):
        counter = getattr(self.call, 'requests_used', None)
        return int(counter()) if counter is not None else self.explore_calls

    def _can_continue(self):
        return (self.dispatches < MAX_BROWSER_DISPATCHES
                and self.effective < MAX_EFFECTIVE_STEPS
                and self._requests_used() < EXPLORE_HTTP_BUDGET - 2
                and not self._soft_deadline_hit())

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
        except asyncio.CancelledError as error:
            self.stop_reason, self.failure_class = 'runner_cancelled', 'interrupted'
            self.stop_summary = '采集中断，保留已派发动作与原请求'
            try:
                self._close()
            except Exception as close_error:
                error.add_note('Stepwise cancellation seal failed: ' + str(close_error))
            raise
        except OutcomeUnknown as error:
            self.stop_reason, self.stop_summary = 'unknown', str(error)
            self.failure_class, self.unknown = 'unknown', True
        except ReactStop as error:
            self.stop_reason = 'blocked'
            self.stop_summary = str(error)
            self.failure_class = getattr(error, 'failure_class', None) or 'program'
        except BudgetStop as error:
            self.stop_reason, self.failure_class = exception_classification(error)
            self.stop_summary = str(error)
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
        scope = post_action_document_scope({'url': self.page.url})
        return await browser.capture(self.page, action_scope=scope, timeout=DOM_OBSERVATION_SECONDS)

    async def _verify_frame(self, frame):
        scope = frame['capture']['attempts'][-1]['stability']['action_scope']
        await browser.verify_execution_state(self.page, frame['state'], action_scope=scope, timeout=DOM_OBSERVATION_SECONDS)
        self.last_reject_key = None
        self.repeat_reject_run = 0

    def _landing_issue(self, state):
        url = state.get('url')
        if not url or not observation.destination_allowed(url, self.allowed_hosts):
            return 'out_of_scope:' + str(url)
        return observation.exclusion_issues(url, state)

    def _repeated_read_move(self, frame, operation, element):
        def move(op, el):
            if op['action_type'] == 'scroll':
                return ('scroll', (op.get('arguments') or {}).get('direction'), (el or {}).get('element_id'))
            if op['action_type'] == 'click' and ((el or {}).get('text') or '').strip() in ('回到顶部', '返回顶部', '回顶部'):
                return ('top', (el or {}).get('element_id'))
            return None

        proposed = move(operation, element)
        if proposed is None:
            return False
        for row in reversed(self.dispatch_rows):
            past = move(row['operation'], row.get('element'))
            if past is None:
                break
            if past == proposed and observation.view_equal(frame['state'], self.journal.frames[row['frame_id']]['state']):
                return True
        return False

    async def _loop(self):
        pending_result = None   # 上一次实际派发行，等待下一次合法决策的 last_step_result
        while True:
            if self._soft_deadline_hit():
                self._stop('soft_deadline', '软截止到达，停止新增模型请求与业务动作', 'collector')
            used = self._requests_used()
            complete_only = not self._can_continue()
            if complete_only and self.effective < MIN_EFFECTIVE_STEPS:
                self._stop('short_flow', '剩余派发或探索请求预算不足以继续，当前有效动作 %d；不再请求终态'
                           % self.effective, 'collector')
            if used >= EXPLORE_HTTP_BUDGET:
                self._stop('http_budget', '探索 HTTP 请求预算已用完；未获得可接受的 complete', 'model')
            frame = self.current
            issue = self._landing_issue(frame['state'])
            if issue:
                self._stop('landing_rejected', issue, 'collector')
            rows = observation.actionable_rows(frame['state'])
            numbered = prompt.numbered_png(Path(frame['png']).read_bytes(), rows)
            self.journal.renumbered_copy(frame, numbered)
            user_text, trimmed = prompt.build_decision_message(
                mode=self.mode, requested_goal_text=self._requested_text(),
                task_goal=self.goal, progress=self._progress_text(), rows=rows,
                state=frame['state'], history=self.history,
                feedback=('宿主提示：只能结束（返回complete）。' if complete_only else '')
                + self.feedback,
                note=self.note, site_tasks=self.site_tasks, complete_only=complete_only,
                pending_result=pending_result is not None)
            if trimmed:
                self.context_trims.extend([{'round': self.decision_round + 1, **item} for item in trimmed])
                if self.runlog is not None:
                    self.runlog.info('context_trimmed', round=self.decision_round + 1,
                                     blocks=[item['block'] for item in trimmed])
            self.explore_calls += 1
            frame_name = prompt.frame_page_name(frame['state'])
            response = await self.call(
                phase='decision', system=self._system_prompt(),
                tools=prompt.next_action_tools(autonomous=self.mode == 'autonomous', frame_name=frame_name),
                user_text=user_text, images=[frame['refs']['numbered']['path']],
                reasoning_effort='low', dispatch_deadline=self._soft_deadline(),
                request_deadline=self._hard_deadline(),
                round_index=self.decision_round + 1, tool_name='next_action')
            original = response.get('arguments') or {}
            arguments = ({**original, 'page_name': frame_name}
                         if frame_name and isinstance(original, dict) else original)
            self.decision_round += 1
            goal_before, note_before = self.goal, self.note
            accepted = False
            try:
                invalid = self._validate_decision(arguments, complete_only, pending_result=pending_result is not None)
                if not invalid:
                    problems = finalize.decision_citations_check(arguments, frame['state'],
                        previous_action=pending_result is not None)
                    if problems:
                        invalid = 'CURRENT_FRAME_CITATION: ' + '；'.join(problems)
                if invalid:
                    self._record_reject(frame, invalid, arguments)
                    continue
                try:
                    operation, element = observation.bind_action(frame['state'], rows, arguments)
                except observation.ActionRejected as rejected:
                    self._record_reject(frame, rejected.reason, arguments)
                    continue
                if arguments['action'] == 'complete':
                    if not await self._handle_complete(frame, arguments):
                        continue
                else:
                    issue = self._proposed_action_issue(frame, operation, element)
                    if issue:
                        self._record_reject(frame, issue, arguments)
                        continue
                    try:
                        await self._verify_frame(frame)
                    except EvidenceStale:
                        self.current = self.journal.add_frame(await self._capture())
                        self.feedback = '画面已变化，上一决策作废；请按当前画面重新决策。'
                        continue
                self._accept_context(arguments, pending_result)
                pending_result = None
                accepted = True
            finally:
                self.journal.add_decision(
                    round_index=self.decision_round, frame_id=frame['frame_id'],
                    request_id=response.get('request_id'), arguments=original,
                    goal_before=goal_before, goal_after=self.goal,
                    note_before=note_before, note_after=self.note,
                    model_ref={'request_id': response.get('request_id'),
                               'tool_call_id': response.get('tool_call_id')},
                    accepted=accepted, frame_page_name=frame_name)
            if arguments['action'] == 'complete':
                return
            outcome = await self._dispatch(frame, operation, element, arguments)
            if outcome == 'delivered':
                pending_result = self.dispatch_rows[-1]
                self.current = self.journal.frames[pending_result['after_frame']]
            elif outcome == 'recaptured':
                self.current = self.journal.frames[self.failed_dispatches[-1]['after_frame']]
            # 'failed'：画面未捕获，当前帧保持不变，反馈已写。

    # ------------------------------------------------------------ 决策校验
    def _proposed_action_issue(self, frame, operation, element):
        if self._repeated_read_move(frame, operation, element):
            return 'READ_VIEW_ALREADY_VISITED: 同一画面已执行过此操作。选择尚未取得的业务事实，或结束任务。'
        if operation['action_type'] in ('click', 'double_click'):
            link = self._link_carrier(frame, element)
            if link:
                from urllib.parse import urljoin, urlsplit
                destination = urljoin(frame['state'].get('url') or '', link['href'])
                scheme = urlsplit(destination).scheme
                if scheme not in ('http', 'https', 'javascript'):
                    return 'NAVIGATION_SCHEME_NOT_PERMITTED:' + scheme
                if scheme in ('http', 'https'):
                    exclusion = observation.exclusion_issues(destination, {})
                    if exclusion or not observation.destination_allowed(destination, self.allowed_hosts):
                        return 'NAVIGATION_DESTINATION_NOT_PERMITTED:' + str(exclusion or destination)
        return None

    def _accept_context(self, arguments, pending_result):
        if self.mode == 'autonomous':
            goal = arguments['task_goal'].strip()
            if self.initial_goal is None:
                self.initial_goal = goal
            elif goal != self.goal:
                self.task_modifications += 1
                if self.runlog is not None:
                    self.runlog.info('task_goal_changed', round=self.decision_round,
                                     taskModifications=self.task_modifications)
            self.goal = goal
        if isinstance(arguments.get('note'), str):
            self.note = arguments['note'].strip()[:prompt.LIMIT_NOTE]
        if pending_result is not None:
            result = arguments['last_step_result'].strip()
            pending_result.update(step_result=result, result_round=self.decision_round)
            if self.history:
                self.history[-1] += '。实际观察：' + result

    def _validate_decision(self, arguments, complete_only, *, pending_result=False):
        if not isinstance(arguments, dict):
            return 'DECISION_NOT_OBJECT'
        for field in ('last_step_result', 'page_name', 'precondition', 'thought',
                      'user_goal', 'action', 'expected_result'):
            if field not in arguments:
                return 'MISSING_FIELD:' + field
        if arguments.get('action') not in observation.SUPPORTED_ACTIONS:
            return 'UNKNOWN_ACTION'
        if arguments.get('action') == 'complete' and arguments.get('status') not in ('success', 'infeasible'):
            return 'COMPLETE_STATUS_REQUIRED: success 或 infeasible'
        if self.mode == 'autonomous':
            goal = arguments.get('task_goal')
            if not (isinstance(goal, str) and goal.strip() and goal.strip() != '同上'):
                return 'TASK_GOAL_REQUIRED'
        if pending_result and not str(arguments.get('last_step_result') or '').strip():
            return 'LAST_STEP_RESULT_REQUIRED: 上一实际动作已派发，请依据本帧填写其可见结果'
        if complete_only and arguments.get('action') != 'complete':
            return 'COMPLETE_ONLY_EXPECTED'
        return None

    def _record_reject(self, frame, reason, arguments):
        from ..agent_controller import exclusive
        key = prompt.compact_json({
            'view': observation.business_view(frame['state']),
            'reason': 'CURRENT_FRAME_CITATION' if reason.startswith('CURRENT_FRAME_CITATION:') else reason,
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
        exclusive(self.root / ('decision-rejection-%03d.json' % self.decision_round),
                  {'round': self.decision_round, 'frame_id': frame['frame_id'],
                   'reason': reason, 'consecutive': self.repeat_reject_run,
                   'created_at': datetime.now(timezone.utc).isoformat()})
        if self.repeat_reject_run >= REPEAT_REJECT_LIMIT:
            self._stop('repeat_reject', '同视图同一动作连续 %d 次派发前拒绝' % REPEAT_REJECT_LIMIT, 'model')
        if reason.startswith('CURRENT_FRAME_CITATION:'):
            self.feedback = '请从本帧正文复制连续短原文；无法辨认时用自己的话描述实际变化。' + reason
        else:
            self.feedback = '上一决策被拒绝：%s。请修正后重试。' % reason

    # ------------------------------------------------------------ complete
    def _reject_complete(self, frame, arguments, reason):
        from ..agent_controller import exclusive

        rejection = {'round': self.decision_round, 'frame_id': frame['frame_id'],
                     'status': arguments['status'], 'reason': reason,
                     'effective_steps': self.effective, 'task_goal': self.goal,
                     'rejection_index': len(self.complete_rejections) + 1,
                     'rejected_at': datetime.now(timezone.utc).isoformat()}
        exclusive(self.root / ('complete-rejection-%03d.json' % rejection['rejection_index']),
                  rejection)
        self.complete_rejections.append(rejection)
        if self.runlog is not None:
            self.runlog.info('complete_rejected', round=self.decision_round,
                             reason=reason, effectiveSteps=self.effective,
                             completeRejections=len(self.complete_rejections),
                             taskModifications=self.task_modifications)
        if reason == 'short_flow':
            self.feedback = ('当前有效动作 %d 个，不足 %d 个。请把 task_goal 扩展为包含已完成操作、'
                             '并在同一业务主题上自然延续的更大任务，继续操作；最终任务必须能解释'
                             '第 1 步起的全部已执行动作。若当前任务已读完且没有新的业务事实，直接再返回 complete，宿主按短流程留证。'
                             % (self.effective, MIN_EFFECTIVE_STEPS))
        else:
            self.feedback = ('当前任务无法完成的声明暂未接受。如果任务走不通，请改成基于已执行动作'
                             '能够完成的任务，然后继续；新任务仍须覆盖第 1 步起的全部已执行动作。'
                             '若确实没有合理任务，可以再次返回 infeasible。')
        return False

    async def _handle_complete(self, frame, arguments):
        """Accept an observed terminal, or give autonomous tasks a bounded extension."""
        try:
            await self._verify_frame(frame)
        except EvidenceStale:
            self.current = self.journal.add_frame(await self._capture())
            self.feedback = '画面已变化，complete 作废；请按当前画面重新决策。'
            return False
        if arguments.get('status') not in ('success', 'infeasible'):
            self._record_reject(frame, 'COMPLETE_STATUS_REQUIRED', arguments)
            return False
        can_extend = (self.mode == 'autonomous' and self._can_continue()
                      and len(self.complete_rejections) < COMPLETE_REJECTION_LIMIT)
        if arguments['status'] == 'infeasible':
            if can_extend and self.infeasible_rejections == 0:
                self.infeasible_rejections += 1
                return self._reject_complete(frame, arguments, 'complete_infeasible')
            self._stop('complete_infeasible', '模型声明任务无法完成', 'collector')
        if self.effective < MIN_EFFECTIVE_STEPS:
            same_short = any(r['reason'] == 'short_flow' and r['effective_steps'] == self.effective
                             for r in self.complete_rejections)
            if can_extend and not same_short:
                return self._reject_complete(frame, arguments, 'short_flow')
            self._stop('short_flow', '有效动作不足 %d（实际 %d），无法继续扩展或已达 complete 驳回上限'
                       % (MIN_EFFECTIVE_STEPS, self.effective), 'collector')
        # The next retained before-frame (or complete frame) must still show the
        # preceding retained action. Omitted actions may not hide a duplicate.
        delivered, _ = self.delivery_plan()
        if any(row['operation']['action_type'] != 'wait' and not row['effective']
               for row in delivered):
            self._stop('unproven_effect', '保留动作中仍有未确认可见效果的非 wait 动作，不能安全省略或保存',
                       'collector')
        delivery_frames = [self.journal.frames[row['frame_id']] for row in delivered] + [frame]
        if any(frames_pixels_equal(left, right)
               for left, right in zip(delivery_frames, delivery_frames[1:])):
            self._stop('unchanged_delivery', '相邻交付原图像素相同，不能证明保留动作的可见效果', 'collector')
        self.complete_decision = dict(arguments)
        self.complete_completed_at = datetime.now(timezone.utc).isoformat()
        self.stop_reason = 'complete_success'
        self.stop_summary = '模型完成声明已核对终态帧'
        return True

    # ------------------------------------------------------------ 派发与效果
    @staticmethod
    def _link_carrier(frame, element):
        if element is None:
            return None
        return navigation_carrier(frame['state'], element['element_id'])

    async def _execute_observed(self, frame, operation, element, execution):
        """Observe one dispatch's popup/navigation before taking its after-frame."""
        from playwright.async_api import TimeoutError as BrowserTimeout

        source = self.page
        action = operation['action_type']
        opener = self._popup_sources.get(source)
        if action == 'back' and opener is not None and not opener.is_closed():
            await asyncio.wait_for(opener.bring_to_front(), timeout=10)
            self.page = opener
            return {'method': 'switch_to_opener', 'source_url': source.url,
                    'landing_url': self.page.url}
        if action not in ('click', 'double_click'):
            await browser.execute(source, action, dict(operation['arguments']), execution)
            return None
        opened = []
        changed = asyncio.Event()

        def on_popup(page):
            opened.append(page)
            changed.set()

        def on_navigation(frame):
            if frame == source.main_frame:
                changed.set()

        # The listeners are installed before dispatch. A popup is attributed to
        # this source page, not to unrelated pages that share a browser context.
        source.on('popup', on_popup)
        source.on('framenavigated', on_navigation)
        link = self._link_carrier(frame, element)
        try:
            await browser.execute(source, action, dict(operation['arguments']), execution)
            from urllib.parse import urldefrag, urljoin, urlsplit
            href = (link or {}).get('href') or ''
            destination = urljoin(frame['state'].get('url') or '', href)
            same_document_anchor = ('#' in href and urldefrag(destination)[0]
                                    == urldefrag(frame['state'].get('url') or '')[0])
            navigable = bool(href and urlsplit(destination).scheme in ('http', 'https')
                             and not same_document_anchor)
            if not changed.is_set():
                try:
                    await asyncio.wait_for(changed.wait(),
                                           timeout=NAVIGATION_WAIT_MS / 1000 if navigable else 1)
                except TimeoutError:
                    pass  # Observation timeout does not resend a successful click.
            if len(opened) > 1:
                raise StepwiseStop('multiple_popups', '一次点击打开多个新标签，不能确定唯一后续页面',
                                   failure_class='collector')
            if opened:
                self.page = opened[0]
                self._popup_sources[self.page] = source
                await asyncio.wait_for(self.page.bring_to_front(), timeout=10)
            if changed.is_set():
                try:
                    await self.page.wait_for_load_state('domcontentloaded', timeout=NAVIGATION_WAIT_MS)
                except BrowserTimeout:
                    pass  # capture owns readiness; a slow load never triggers another click.
            return {'method': 'popup' if opened else 'same_tab',
                    'source_url': frame['state'].get('url'), 'landing_url': self.page.url,
                    'href': href or None, 'navigation_expected': navigable,
                    'navigation_observed': changed.is_set()}
        finally:
            source.remove_listener('popup', on_popup)
            source.remove_listener('framenavigated', on_navigation)

    async def _restore_landing(self, frame, rejected, source_page, rejected_seq, issue):
        """Keep the rejected landing and the host's return as separate real actions."""
        from ..agent_controller import exclusive

        operation = {'action_type': 'back', 'arguments': {},
                     'evidence': {'collection_strategy': 'stepwise', 'host_recovery': True,
                                  'rejected_dispatch': rejected_seq}}
        seq, dispatch, dispatch_ref = self.journal.begin_dispatch(
            frame_id=rejected['frame_id'], operation=operation, element=None)
        self.dispatches += 1
        method = 'switch_to_source' if self.page is not source_page else 'go_back'
        after = None
        recovery_error = None
        recovery_action_completed = False
        try:
            if method == 'switch_to_source':
                bad_page = self.page
                if source_page.is_closed():
                    raise ValueError('原页面已关闭，无法恢复')
                await asyncio.wait_for(source_page.bring_to_front(), timeout=10)
                self.page = source_page
                await asyncio.wait_for(bad_page.close(), timeout=10)
                self._popup_sources.pop(bad_page, None)
            else:
                await browser.execute(self.page, 'back', {}, {})
            recovery_action_completed = True
            after = self.journal.add_frame(await self._capture())
            state = after['state']
            if (state.get('url') != frame['state'].get('url')
                    or not observation.destination_allowed(state.get('url'), self.allowed_hosts)
                    or observation.exclusion_issues(state.get('url'), state)):
                raise ValueError('恢复后的页面不匹配原页面或仍在排除范围')
        except Exception as error:
            recovery_error = error
        record = self.journal.finish_step(
            seq=seq, dispatch_ref=dispatch_ref, operation=operation, element=None,
            dispatched=True, action_executed=True if recovery_action_completed else None,
            execution_error=(type(recovery_error).__name__ + ': ' + str(recovery_error)
                             if recovery_error else None),
            before_frame=rejected['frame_id'], after_frame=after['frame_id'] if after else None,
            effect='host_recovery', effective=False, omittable=False,
            omit_reason='rejected_landing_return', postconditions_checked=after is not None,
            after_state=after['state'] if after else None)
        self._remember_failed_dispatch(seq, record, after['frame_id'] if after else None)
        recovery = {'rejected_dispatch': rejected_seq, 'recovery_dispatch': seq,
                    'method': method, 'issue': issue,
                    'source_frame': frame['frame_id'], 'rejected_frame': rejected['frame_id'],
                    'restored_frame': after['frame_id'] if after else None,
                    'restored': recovery_error is None,
                    'action_executed': recovery_action_completed,
                    'error': record['execution_error']}
        exclusive(self.root / ('host-recovery-%03d.json' % seq), recovery)
        self.unsafe_omissions.append(recovery)
        if recovery_error is not None:
            self.current = after or rejected
            from playwright.async_api import TimeoutError as BrowserTimeout
            if isinstance(recovery_error, (TimeoutError, BrowserTimeout)):
                if recovery_action_completed:
                    self._stop('capture_timeout', '宿主返回动作已完成，恢复后截图超时：'
                               + str(recovery_error), 'collector')
                self._stop('unknown_dispatch', '宿主返回动作结果未知，保留原始记录不重发',
                           'unknown', unknown=True)
            self._stop('landing_recovery_failed', '越界后的恢复失败，保留原始落地与恢复记录：'
                       + str(recovery_error), 'collector')
        self.feedback = ('上一动作落地页被拒绝：%s。已返回原页面，请改用当前页内允许的操作。'
                         '原动作和宿主恢复均已单独留证，不计有效步。' % issue[:180])
        return 'recaptured'

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
        navigation = None
        source_page = self.page
        try:
            navigation = await self._execute_observed(frame, operation, element, execution)
            if navigation is not None:
                from ..agent_controller import exclusive
                exclusive(self.root / ('navigation-%03d.json' % seq), navigation)
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
        issue = self._landing_issue(after_state)
        if issue:
            record = self.journal.finish_step(
                seq=seq, dispatch_ref=dispatch_ref, operation=operation, element=element,
                dispatched=True, action_executed=True, execution_error=None,
                before_frame=frame['frame_id'], after_frame=after_frame,
                effect='landing_rejected', effective=False, omittable=False,
                omit_reason=issue, postconditions_checked=postconditions_checked,
                after_state=after_state)
            self._remember_failed_dispatch(seq, record, after_frame)
            return await self._restore_landing(frame, after, source_page, seq, issue)
        # 效果判断：wait 不计有效步；确认无效果才可省略。
        before_state = frame['state']
        document_changed = observation.document_changed(before_state, after_state)
        omittable, omit_reason = observation.action_omittable(before_state, after_state, action)
        semantic_changed = not observation.view_equal(before_state, after_state)
        pixels_changed = not frames_pixels_equal(frame, after)
        if (navigation and navigation.get('navigation_expected')
                and not navigation.get('navigation_observed')
                and before_state.get('url') == after_state.get('url')
                and not semantic_changed and not pixels_changed):
            record = self.journal.finish_step(
                seq=seq, dispatch_ref=dispatch_ref, operation=operation, element=element,
                dispatched=True, action_executed=True, execution_error=None,
                before_frame=frame['frame_id'], after_frame=after_frame,
                effect='navigation_unconfirmed', effective=False, omittable=False,
                omit_reason='navigation_unconfirmed', postconditions_checked=True, after_state=after_state)
            self._remember_failed_dispatch(seq, record, after_frame)
            self.current = after
            self._stop('navigation_unconfirmed', '链接点击已执行，但有界等待后落地仍未证实；保留原件，不再次点击',
                       'collector')
        effective = action != 'wait' and semantic_changed and pixels_changed
        # A proven semantic change without a visible pixel change is retained
        # for provenance but cannot increase the delivery's effective count.
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
        if omittable:
            self.feedback = '这一步没有确认到业务变化，不计入有效步；已连续 %d/%d 次无效果。' % (
                self.no_effect_run, NO_EFFECT_LIMIT)
        elif not effective:
            self.feedback = '这一步尚未确认语义与画面均有变化，不计入有效步；原始动作证据已保留。'
        else:
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
        result = ('这一步不计入有效步，连续无效果 %d/%d' % (self.no_effect_run, NO_EFFECT_LIMIT)
                  if row['omittable'] else
                  '尚未确认可见效果，这一步不计入有效步' if not row['effective'] else
                  '页面已切换' if document_changed else '画面已变化')
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
        base = '已派发 %d/%d 次，有效 %d 个，结束前至少需要 %d 个（最多 %d）；连续无效果 %d/%d；实际 HTTP 请求 %d/%d。' % (
            self.dispatches, MAX_BROWSER_DISPATCHES, self.effective, MIN_EFFECTIVE_STEPS, MAX_EFFECTIVE_STEPS,
            self.no_effect_run, NO_EFFECT_LIMIT, self._requests_used(), EXPLORE_HTTP_BUDGET)
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
                    'initial_goal': self.initial_goal,
                    'task_modifications': self.task_modifications,
                    'complete_rejection_count': len(self.complete_rejections),
                    'complete_rejections': self.complete_rejections,
                    'unsafe_omissions': self.unsafe_omissions,
                    'requested_goal': self.requested_goal,
                    'stop_reason': self.stop_reason,
                    'stop_summary': self.stop_summary,
                    'failure_class': self.failure_class,
                    'unknown': self.unknown,
                    'effective_steps': self.effective,
                    'actual_dispatches': self.dispatches,
                    'decision_rounds': self.decision_round,
                    'explore_calls': self.explore_calls,
                    'explore_http_requests': self._requests_used(),
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
                      'landing_rejected': 'unsuitable',
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
                'initial_goal': self.initial_goal,
                'task_modifications': self.task_modifications,
                'complete_rejection_count': len(self.complete_rejections),
                'complete_rejections': self.complete_rejections,
                'unsafe_omissions': self.unsafe_omissions,
                'explore_http_requests': self._requests_used(),
                'raw_receipt': receipt,
                'end': outcome_facts(goal_status=goal_status, end_reason=end_reason,
                                     eligibility='unresolved', save_status='not_saved')}
