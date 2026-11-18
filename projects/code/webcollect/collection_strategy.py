"""Frozen collection strategies, one result contract and one shared save gate.

策略 1 keeps the banded/react chain (ReactSession + conditional-plan
controller) and is completely frozen. 策略 2 (screenshot_plan) plans from the
entry screenshot and revises only the remaining tail at business checkpoints.
策略 3 (stepwise) is a fully independent one-action-per-call loop maintained in
webcollect/stepwise: own prompts, protocol, records, judgement and save rules.
All produce the same internal StrategyResult facts and go through the same
save-gate entry, which dispatches on the frozen strategy; neither strategy can
relax another's checks.

A strategy ID is frozen into the task fragment before the first dispatch and
never changes mid-attempt; a failed attempt never switches strategies.
"""
from copy import deepcopy

# 策略 1: banded conditional-plan chain over ReactSession.
STRATEGY_BANDED_REACT = 'react'
# 策略 2: screenshot understanding + remaining-plan revision loop.
STRATEGY_SCREENSHOT_PLAN = 'screenshot_plan'
# 策略 3: independent stepwise one-action-per-call loop (webcollect.stepwise).
STRATEGY_STEPWISE = 'stepwise'
# 新任务缺省策略 2；策略 1 已完全冻结（见 Strategy1Forbidden），策略 3 显式选择。
DEFAULT_STRATEGY = STRATEGY_SCREENSHOT_PLAN
STRATEGIES = (STRATEGY_BANDED_REACT, STRATEGY_SCREENSHOT_PLAN, STRATEGY_STEPWISE)
# Sealed fragments frozen before the marker existed belong to the react chain;
# their identity stays react (read-only) and is never migrated to 策略 2.
_ABSENT_MARKER_STRATEGY = STRATEGY_BANDED_REACT


class Strategy1Forbidden(RuntimeError):
    """策略 1 完全冻结：任何入口在浏览器/模型/采集动作之前拒绝执行。"""

    MESSAGE = ('STRATEGY1_FORBIDDEN: 策略1(react)已完全冻结，禁止执行；'
               '历史任务保持只读，不会迁移或重跑 / collection strategy 1 is '
               'frozen; execution refused before any browser, model or '
               'collection action')

    def __init__(self, message=None):
        super().__init__(message or self.MESSAGE)

# Internal result contract shared by both strategies.
RESULT_CONTRACT = 'strategy-result'
RESULT_VERSION = RESULT_CONTRACT

FIELD = 'collection_strategy'

# Sealed historical fragments froze the pre-rename strategy ids. Their bytes
# stay unchanged and read as the same current strategies.
LEGACY_STRATEGY_IDS = {
    'webcollect-collection-banded-react-1': STRATEGY_BANDED_REACT,
    'webcollect-collection-screenshot-plan-2': STRATEGY_SCREENSHOT_PLAN,
}


def freeze(task, strategy=DEFAULT_STRATEGY):
    """Stamp a new task with its frozen strategy identity before first dispatch.

    Must run before the task id hash is finalized (same place the other
    fragment extensions are applied); never called on replay. 策略 1 is
    completely frozen: an explicit react strategy is refused here, at task
    construction, before any browser, model or collection action.
    """
    if strategy == STRATEGY_BANDED_REACT:
        raise Strategy1Forbidden()
    if strategy not in STRATEGIES:
        raise ValueError('Unknown collection strategy: ' + str(strategy))
    record = {'id': strategy, 'result_contract': RESULT_CONTRACT}
    for part in (task['fragment'], task['workflow_proposal']['spec']):
        if part.get(FIELD) not in (None, record):
            raise ValueError('Collection strategy already frozen differently')
        part[FIELD] = deepcopy(record)
        if strategy in (STRATEGY_SCREENSHOT_PLAN, STRATEGY_STEPWISE):
            # 策略 2/3 的帧取证同为 action-scoped 观察（共享宿主稳定域实现）；
            # 该协议标记是宿主观察策略声明，试点身份内容佐证按此路径核验。
            from .action_stability import ACTION_STABILITY_PROTOCOL
            if part.get('action_stability_protocol') not in (None, ACTION_STABILITY_PROTOCOL):
                raise ValueError('Action stability already frozen differently')
            part['action_stability_protocol'] = ACTION_STABILITY_PROTOCOL
    return task


def strategy_id(task):
    """Frozen strategy of this attempt; absent markers keep the react reading.

    Sealed fragments without the marker stay react (their historical identity,
    never silently migrated to 策略 2) and sealed pre-rename ids keep their
    historical strategy reading; anything else is unknown.
    """
    record = (task.get('fragment') or {}).get(FIELD) or {}
    value = record.get('id') if isinstance(record, dict) else record
    if value is None:
        return _ABSENT_MARKER_STRATEGY
    if value in STRATEGIES:
        return value
    if value in LEGACY_STRATEGY_IDS:
        return LEGACY_STRATEGY_IDS[value]
    raise ValueError('Unknown frozen collection strategy: ' + str(value))


def enabled(task):
    """是否策略 2（screenshot_plan）。含义保持不变：策略 3 用 is_stepwise 判定。"""
    return strategy_id(task) == STRATEGY_SCREENSHOT_PLAN


def is_stepwise(task):
    """是否策略 3（stepwise）：独立逐步决策循环，无策略 2 模板与合同。"""
    return strategy_id(task) == STRATEGY_STEPWISE


def select(task):
    """Static strategy table; no discovery, plugins or service registry.

    策略 1 is completely frozen: a non-策略2/策略3 task is refused here instead
    of returning the react module. Historical sealed react fragments keep their
    read-only parsing elsewhere; they never reach an executing session.
    """
    if enabled(task):
        from . import screenshot_plan
        return screenshot_plan
    if is_stepwise(task):
        from . import stepwise
        return stepwise
    raise Strategy1Forbidden()


def _banded_strategy_module():
    """策略 1 stays the ReactSession chain; the adapter is the session itself."""
    from . import react_session
    return react_session


def outcome_facts(*, goal_status, end_reason, eligibility, save_status, details=None):
    """The four independently recorded facts of one attempt's closure.

    goal_status: unconfirmed / partial / completed
    end_reason: goal_completed / no_path / unsuitable / no_progress /
                user_stopped / protocol_error / engine_error / unknown
    eligibility: eligible / ineligible / unresolved (+ reason)
    save_status: not_saved / collected_pending_review / save_failed / unresolved
    """
    return {'goal_status': goal_status, 'end_reason': end_reason,
            'save_eligibility': eligibility, 'save_status': save_status,
            **({'details': details} if details else {})}


def save_eligibility(annotation, raw_execution):
    """The single unified save gate, statically dispatched by frozen strategy.

    原目标完成 ∧ 有效步≥5 ∧ 证据可信 ∧ 无相关未决外部效果. The formal file
    preflight, the RuntimeStore commit recheck and the client export read this
    one entry. 策略 1/2 records go through closing_policy.completion_delivery_
    decision (策略 2's ending marker is recognized inside it); 策略 3 records
    carry their own frozen `collection_strategy` marker inside raw_execution
    and are judged by stepwise.finalize — never by the 策略 2 contract.
    RuntimeStore.finish_attempt additionally verifies that marker against the
    database task's frozen strategy before trusting it.
    """
    from .closing_policy import completion_delivery_decision
    if isinstance(raw_execution, dict) and (raw_execution.get('collection_strategy') or {}).get('id') == STRATEGY_STEPWISE:
        from . import stepwise
        return stepwise.finalize.save_eligibility(annotation, raw_execution)
    return completion_delivery_decision(annotation, raw_execution)


def strategy_result(task, *, summary, raw_receipt, evidence_refs=(), usage_refs=()):
    """Assemble the shared internal StrategyResult from one attempt's facts.

    Large objects stay as existing file references with hashes; the strategy
    never re-states derived numbers as authoritative — the shared save gate
    recomputes eligibility from the sealed raw execution.
    """
    from .batch_core import load_json
    from .planning import verify_evidence
    verify_evidence([raw_receipt])
    sealed_receipt = load_json(raw_receipt['path'])
    terminal_ref = sealed_receipt.get('terminal') or {}
    verify_evidence([terminal_ref, *evidence_refs])
    terminal = load_json(terminal_ref['path'])
    ending = terminal.get('collection_ending') or {}
    goal_evidence = terminal.get('goal_evidence') or {}
    goal_status = ('completed'
                   if goal_evidence.get('business_goal_status') == 'VERIFIED'
                   else 'unconfirmed')
    explicit_end = summary.get('strategy_end_reason') or summary.get('end_reason')
    end_reason = explicit_end or (
        'goal_completed' if goal_status == 'completed'
                           and ending.get('kind') in ('AGENT_COMPLETE_VERIFIED', 'HOST_PLAN_ENDPOINT', 'VISIBLE_GOAL_REPORTED')
        else 'unsuitable' if ending.get('kind') == 'UNSUITABLE_TASK'
        else 'no_progress' if ending.get('kind') == 'NO_PROGRESS_END'
        else 'no_path' if ending.get('kind') == 'AGENT_GIVE_UP'
        else 'user_stopped' if summary.get('user_stopped') is True
        else 'unknown' if summary.get('unknown')
        else 'engine_error' if summary.get('failure_class') == 'program'
        else 'no_path' if summary.get('stop_reason') in ('blocked', 'no_path')
        else 'unknown')
    return {'result_contract': RESULT_CONTRACT,
            # Absent markers keep the historical react label; sealed records
            # are never relabeled as screenshot_plan.
            'strategy': deepcopy((task.get('fragment') or {}).get(FIELD)
                                 or {'id': _ABSENT_MARKER_STRATEGY}),
            'binding': {key: task.get(key) for key in ('task_id', 'task_version', 'site_uri') if key in task},
            'goal': {'goal_status': goal_status,
                     'evidence': deepcopy(goal_evidence) if goal_evidence else None},
            'execution': {'effective_steps': summary.get('effective_steps'),
                          'actual_dispatches': summary.get('actual_actions'),
                          'evidence_refs': list(evidence_refs)},
            'end': outcome_facts(goal_status=goal_status, end_reason=end_reason,
                                 eligibility='unresolved', save_status='not_saved'),
            'usage_refs': list(usage_refs or []), 'raw_receipt': raw_receipt}


def finalize_strategy_result(result, *, save_status, eligibility=None, details=None):
    """Replace the session-stage transient end facts with the actual outcome.

    Called only after RuntimeStore commit or a decision not to save; the
    sealed session originals are never rewritten. save_status:
    collected_pending_review / not_saved / save_failed / unresolved.
    unresolved means the commit outcome cannot be read back from the ledger;
    known eligibility remains independent of that uncertainty.
    """
    finalized = deepcopy(result)
    if eligibility is None:
        eligibility = 'eligible' if save_status == 'collected_pending_review' else 'ineligible'
    goal_status = finalized['goal']['goal_status']
    finalized['end'] = outcome_facts(goal_status=goal_status,
                                     end_reason=finalized['end']['end_reason'],
                                     eligibility=eligibility,
                                     save_status=save_status, details=details)
    return finalized
