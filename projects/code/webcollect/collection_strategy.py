"""Frozen collection strategies, one result contract and one shared save gate.

策略 1 keeps the existing banded/react chain (ReactSession + conditional-plan
controller). 策略 2 (screenshot_plan) plans from the entry screenshot and
revises only the remaining tail at business checkpoints. Both produce the same
internal StrategyResult facts and go through the same eligibility function and
save entry; neither can relax the other's protocol.

A strategy ID is frozen into the task fragment before the first dispatch and
never changes mid-attempt. Old tasks without the marker keep their historical
(策略 1) interpretation byte-for-byte.
"""
from copy import deepcopy

# 策略 1: existing banded conditional-plan chain over ReactSession.
STRATEGY_BANDED_REACT = 'webcollect-collection-banded-react-1'
# 策略 2: screenshot understanding + remaining-plan revision loop.
STRATEGY_SCREENSHOT_PLAN = 'webcollect-collection-screenshot-plan-2'
DEFAULT_STRATEGY = STRATEGY_BANDED_REACT
STRATEGIES = (STRATEGY_BANDED_REACT, STRATEGY_SCREENSHOT_PLAN)

# Internal result contract shared by both strategies.
RESULT_VERSION = 'webcollect-strategy-result-1'

# Per-strategy protocol versions frozen together with the task.
STRATEGY_PROTOCOLS = {
    STRATEGY_BANDED_REACT: {'result_contract': RESULT_VERSION},
    STRATEGY_SCREENSHOT_PLAN: {'result_contract': RESULT_VERSION,
                               'plan_protocol': 'webcollect-screenshot-plan-2'},
}

FIELD = 'collection_strategy'


def freeze(task, strategy=DEFAULT_STRATEGY):
    """Stamp a new task with its frozen strategy identity before first dispatch.

    Must run before the task id hash is finalized (same place the other
    fragment protocol extensions are applied); never called on replay.
    """
    if strategy not in STRATEGIES:
        raise ValueError('Unknown collection strategy: ' + str(strategy))
    if strategy == STRATEGY_SCREENSHOT_PLAN:
        from .screenshot_plan import VERSION
        STRATEGY_PROTOCOLS[STRATEGY_SCREENSHOT_PLAN]['plan_protocol'] = VERSION
    record = {'id': strategy, **deepcopy(STRATEGY_PROTOCOLS[strategy])}
    for part in (task['fragment'], task['workflow_proposal']['spec']):
        if part.get(FIELD) not in (None, record):
            raise ValueError('Collection strategy already frozen differently')
        part[FIELD] = deepcopy(record)
    return task


def strategy_id(task):
    """Frozen strategy of this attempt; default keeps the historical chain."""
    record = (task.get('fragment') or {}).get(FIELD) or {}
    value = record.get('id') if isinstance(record, dict) else record
    if value is None:
        return DEFAULT_STRATEGY
    if value not in STRATEGIES:
        raise ValueError('Unknown frozen collection strategy: ' + str(value))
    return value


def enabled(task):
    return strategy_id(task) == STRATEGY_SCREENSHOT_PLAN


def select(task):
    """Static strategy table; no discovery, plugins or service registry."""
    from . import collection_strategy
    if enabled(task):
        from . import screenshot_plan
        return screenshot_plan
    return collection_strategy._banded_strategy_module()


def _banded_strategy_module():
    """策略 1 stays the ReactSession chain; the adapter is the session itself."""
    from . import react_session
    return react_session


def outcome_facts(*, goal_status, end_reason, eligibility, save_status, details=None):
    """The four independently recorded facts of one attempt's closure.

    goal_status: unconfirmed / partial / completed
    end_reason: goal_completed / no_path / unsuitable / no_progress /
                user_stopped / engine_error / unknown
    eligibility: eligible / ineligible / unresolved (+ reason)
    save_status: not_saved / collected_pending_review / save_failed
    """
    return {'schema_version': 'webcollect-strategy-outcome-1',
            'goal_status': goal_status, 'end_reason': end_reason,
            'save_eligibility': eligibility, 'save_status': save_status,
            **({'details': details} if details else {})}


def save_eligibility(annotation, raw_execution):
    """The single unified save gate for both strategies.

    原目标完成 ∧ 有效步≥5 ∧ 证据可信 ∧ 无相关未决外部效果. Both the formal
    file preflight, the RuntimeStore commit recheck and the client export read
    this one implementation (closing_policy.completion_delivery_decision);
    策略 2's ending marker is recognized inside it, so no caller branches.
    """
    from .closing_policy import completion_delivery_decision
    return completion_delivery_decision(annotation, raw_execution)


def strategy_result(task, *, summary, raw_receipt, evidence_refs=(), usage_refs=()):
    """Assemble the shared internal StrategyResult from one attempt's facts.

    Large objects stay as existing file references with hashes; the strategy
    never re-states derived numbers as authoritative — the shared save gate
    recomputes eligibility from the sealed raw execution.
    """
    from .batch_core import load_json
    from .planning import verify_evidence
    verify_evidence([raw_receipt, *evidence_refs])
    terminal = load_json(raw_receipt['path'])
    ending = terminal.get('collection_ending') or {}
    goal_evidence = terminal.get('goal_evidence') or {}
    goal_status = ('completed'
                   if goal_evidence.get('business_goal_status') == 'VERIFIED'
                   else 'unconfirmed')
    end_reason = summary.get('end_reason') or (
        'goal_completed' if ending.get('kind') == 'AGENT_COMPLETE_VERIFIED'
        else 'user_stopped' if summary.get('stop_reason') == 'blocked' and summary.get('unknown')
        else 'unknown' if summary.get('unknown') else 'no_path')
    return {'schema_version': RESULT_VERSION,
            'strategy': deepcopy((task.get('fragment') or {}).get(FIELD) or {'id': DEFAULT_STRATEGY}),
            'binding': {key: task.get(key) for key in ('task_id', 'task_version', 'site_uri')},
            'goal': {'goal_status': goal_status,
                     'evidence': deepcopy(goal_evidence) if goal_evidence else None},
            'execution': {'effective_steps': summary.get('effective_steps'),
                          'actual_dispatches': summary.get('actual_actions'),
                          'evidence_refs': list(evidence_refs)},
            'end': outcome_facts(goal_status=goal_status, end_reason=end_reason,
                                 eligibility='unresolved', save_status='not_saved'),
            'usage_refs': list(usage_refs or []), 'raw_receipt': raw_receipt}
