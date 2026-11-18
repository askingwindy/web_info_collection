"""Shared raw-execution engine core for both collection strategies.

This module owns the strategy-neutral facts of one browser session: entry
navigation, trusted observations, atomic dispatch, effect verification, the
business-attempt journal, budgets and the append-only raw close-out. Strategy 1
(ReactSession, react_session.py) and 策略 2 (ScreenshotPlanSession,
screenshot_session.py) both subclass RawSessionCore and add their own decision
loop; neither strategy loads the other's loop module. Delivery samples are
derived offline by webcollect.postprocess; this module never grants review
states and never lets model text act as a tool result.
"""
import asyncio
from copy import deepcopy
from webcollect import workspace_json as json
import time
from pathlib import Path
from urllib.parse import urlsplit

from .planning import object_sha256, verify_evidence
from .batch_core import file_sha, load_json, OutcomeUnknown, BudgetStop, SessionGLMCallLimit
from .agent_observation import project, require_action, PROVEN, ACTIONS, CONTROL_ACTIONS, VERSION as OBS_VERSION
from .agent_controller import exclusive, compile_step, DecisionRequestError, DecisionModelFault

from .plan_protocol import (REACT_SESSION_PROTOCOL, REACT_PROTOCOL, REFERENCE_PROTOCOL, EFFECTIVE_ACTION_RULE,
                            NAVIGATION_PROTOCOL, DELAYED_NAVIGATION_PROTOCOL, PLANNING_INTENT_PROTOCOL,
                            ENDING_POLICY, PLAN_PROTOCOL, WIKI_READING_COMPLETION, DIRECT_COMPLETION_PROTOCOL,
                            RESULT_EXECUTION_POLICY, RESULT_COMPLETION_PROTOCOL, NUMERIC_RESULT_EVIDENCE_POLICY,
                            TRUSTED_PREFIX_POLICY, ACTION_STABILITY_PROTOCOL, FRAGMENT_POLICY, READING_PLAN_COMPLETION_POLICY,
                            PLAN_EXECUTION_POLICY)
from .react_protocol import (VERSION as NATIVE_VERSION, SYSTEM as NATIVE_SYSTEM,
                             RULE_VERSION, REFERENCE_PROTOCOL, rule_sources, native_tools, native_decision, atomic_effect)

REACT_VERSION = REACT_SESSION_PROTOCOL
STOP_REASONS = ('ready', 'no_path', 'budget', 'blocked')
INSPECT_KINDS = ('html', 'control', 'history', 'feedback')

SYSTEM_PROMPT = NATIVE_SYSTEM

# Archived session-1 task contract.
DEFAULT_BUDGETS = {'max_actions': 10, 'max_observations': 24, 'max_decisions': 10,
                'max_model_calls': 10, 'max_replans': 8, 'max_queries': 10,
                'max_no_progress': 5, 'max_seconds': 900}
BUDGET_KEYS = tuple(DEFAULT_BUDGETS)
# Explicit finite task limits remain part of a historical task's signed scope.
# The real-GLM ceiling is applied when the session binds its model ledger.
GOAL_BUDGETS = dict.fromkeys(BUDGET_KEYS)
RESERVE = {'max_actions': 1, 'max_observations': 2}
ALLOWED_TOOL_ACTIONS = ('click', 'double_click', 'right_click', 'type', 'set_value', 'select',
                        'hotkey', 'scroll', 'open_url', 'back', 'drag', 'wait')

_HTML_EXCERPT_CHARS = 1500
_INSPECT_MAX_CHARS = 8000
# Real-run v9 fact: a search-results page needs more than the legacy 15s
# snapshot budget tuned for small fragment pages. Heavy agent pages keep a
# hard bound so a stalled page still rejects only its own task.
REACT_OBSERVE_TIMEOUT_SECONDS = 45


def obj(properties, **extra):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False, **extra}


TEXT = {'type': 'string', 'minLength': 1}
NULLABLE_TEXT = {'type': ['string', 'null']}

GOAL_UPDATE = obj({'description': TEXT, 'basis_observation_id': TEXT, 'reason': TEXT})

ACTION_ARGUMENTS = {
    'click': {'control_id': TEXT}, 'double_click': {'control_id': TEXT}, 'right_click': {'control_id': TEXT},
    'type': {'control_id': TEXT, 'value': TEXT}, 'set_value': {'control_id': TEXT, 'value': TEXT},
    'select': {'control_id': TEXT, 'value': TEXT}, 'scroll': {'direction': {'enum': ['up', 'down', 'left', 'right']}},
    'hotkey': {'keys': {'type': 'array', 'minItems': 1, 'items': TEXT}, 'control_id': NULLABLE_TEXT},
    'open_url': {'page_id': TEXT}, 'back': {},
    'drag': {'control_id': TEXT, 'end_control_id': TEXT},
    'wait': {'duration_ms': {'type':'integer','minimum':1,'maximum':60000}},
}


def is_react_task(task):
    return task.get('fragment', {}).get('schema_version') == REACT_VERSION


class ReactStop(Exception):
    """Host-side terminal stop; run() always closes the raw journal first."""

    def __init__(self, stop_reason, reason, failure_class='collector', unknown=False, **facts):
        super().__init__(reason)
        self.stop_reason = stop_reason
        self.reason = reason
        self.failure_class = failure_class
        self.unknown = unknown
        self.facts = facts


def struct_goal(task):
    """Read-only structured business goal; null for URL-only entries."""
    if 'candidate_binding' in task:
        candidate = task['candidate_binding']['candidate']
        if candidate.get('schema_version') == 'webcollect-data-candidate-2':
            return deepcopy(candidate.get('requested_goal')) if candidate.get('candidate_kind') == 'target' else None
        return deepcopy(candidate)
    goal = (task.get('workflow_proposal') or {}).get('spec', {}).get('goal') or {}
    return deepcopy(goal['structured']) if isinstance(goal, dict) and goal.get('structured') else None


def describe_goal(goal):
    """Short natural description of the structured goal, no JSON splicing."""
    if not goal:
        return None
    if isinstance(goal, str):
        return goal
    if not isinstance(goal, dict):
        return None
    parts = []
    if goal.get('entity'):
        parts.append('「' + str(goal['entity']) + '」')
    if goal.get('kind'):
        parts.append(str(goal['kind']))
    if goal.get('parameters'):
        parts.extend(str(key) + '为「' + str(value) + '」' for key, value in goal['parameters'].items())
    if goal.get('name'):
        parts.append('「' + str(goal['name']) + '」')
    if goal.get('description'):
        parts.append(str(goal['description']))
    return '，'.join(parts) if parts else None


EFFORT_LEVELS = ('low', 'high', 'max')


def validate_effort_profile(profile):
    """glm-5.3 cannot disable thinking (provider error 1210); low/high/max are
    the only dispatch levels, so a frozen profile maps each phase to one."""
    if (not isinstance(profile, dict) or set(profile) != {'first_plan', 'branch'}
            or any(profile[key] not in EFFORT_LEVELS for key in ('first_plan', 'branch'))):
        raise ValueError('reasoning effort profile must map first_plan/branch to low/high/max')
    return {'first_plan': profile['first_plan'], 'branch': profile['branch']}


def build_url_task(*, url, task_version, site_category=None, app_name=None, task_family='navigation-reading',
                   allowed_actions=None, instruction=None, site_uri=None, budgets=None, pilot_identity=None,
                   registration='1', decision_protocol=NATIVE_VERSION, allow_controlled_exception=False, skip_wechat_articles=False,
                   reference_protocol=REFERENCE_PROTOCOL, ending_policy=None, plan_protocol=None, action_stability_protocol=None,
                   trusted_prefix_protocol=None, effort_profile=None):
    """Host-built identity for a URL-only entry; no model call, no frozen plan.

    `registration` is the explicit re-registration version: it enters the
    frozen spec (hence task_id/task_key/page claim) so a sanctioned replan of
    the same entry is a new transparent version, never a silent duplicate.
    """
    if plan_protocol is not None and ending_policy is None:
        from .plan_protocol import ENDING_POLICY
        ending_policy = ENDING_POLICY
    if site_category is None:
        site_category = 'UNKNOWN' if decision_protocol == NATIVE_VERSION else '综合'
    from .collect import verify_public_url
    from .task_instruction import validate_task_instruction
    verify_public_url(url)
    actions = sorted(set(allowed_actions or ALLOWED_TOOL_ACTIONS) & set(ALLOWED_TOOL_ACTIONS))
    if not actions:
        raise ValueError('React entry needs at least one supported action')
    host = verify_public_url(site_uri or url)
    name = app_name or host
    natural = instruction or (f'在「{name}」执行连续、合法、可验证的真实网页操作（如搜索、筛选、浏览详情），'
                              '完成一条可交付的操作轨迹')
    validate_task_instruction(natural)
    default_budgets = GOAL_BUDGETS
    frozen_budgets = {**default_budgets, **(budgets or {})}
    spec = {'entry_url': url, 'goal': {'structured': None, 'instruction': natural},
            'allowed_actions': actions, 'budgets': dict(frozen_budgets),
            'registration': str(registration)}
    if decision_protocol == NATIVE_VERSION:
        spec['decision_protocol'] = decision_protocol
        spec['navigation_protocol'] = NAVIGATION_PROTOCOL
        spec['delayed_navigation_protocol'] = DELAYED_NAVIGATION_PROTOCOL
        spec['planning_intent_protocol'] = PLANNING_INTENT_PROTOCOL
        from .reading_progress import VERSION as READING_PROTOCOL
        from .plan_protocol import ENDING_POLICY
        spec['reading_progress_protocol'] = READING_PROTOCOL
        spec['ending_policy'] = ending_policy or ENDING_POLICY
        if reference_protocol is not None:
            spec['reference_protocol'] = reference_protocol
        if skip_wechat_articles:
            spec['skip_wechat_articles'] = True
        spec['effective_action_rule'] = RULE_VERSION
        spec['rule_sources'] = rule_sources()
        spec['allow_controlled_exception'] = bool(allow_controlled_exception)
    task = {'task_id': 'react-' + object_sha256({'url': url, 'spec': spec})[:24],
        'task_version': task_version, 'capability_id': 'react-url-' + object_sha256({'url': url})[:16],
        'capability_version': REACT_VERSION, 'site_uri': site_uri or url, 'site_category': site_category,
        'task_family': task_family, 'initial_url': url, 'app_name': name, 'instruction': natural,
        'task_type': ['数据查看'], 'operations': [], 'required_actions': [], 'subgoals': [],
        'final_assertions': [], 'final_result': natural, 'completion_judgement': natural,
        'stop_when_final': False, 'content_preparation': False,
        'fragment': {'schema_version': REACT_SESSION_PROTOCOL, 'controller_version': REACT_SESSION_PROTOCOL,
            'policy_version': FRAGMENT_POLICY, 'business_completion': 'NOT_CLAIMED',
            'quality_policy_version': 'qc-sampling', 'budgets': dict(frozen_budgets),
            'allowed_actions': actions, 'page_urls': [url], 'entry_mode': 'url',
            'operation_template': 'react-session'},
        'workflow_proposal': {'schema_version': REACT_SESSION_PROTOCOL, 'spec': spec,
            'evidence': [], 'semantic_status': 'REVIEW_REQUIRED'}}
    task['fragment']['decision_protocol'] = decision_protocol
    if decision_protocol == NATIVE_VERSION:
        task['fragment']['navigation_protocol'] = spec['navigation_protocol']
        task['fragment']['delayed_navigation_protocol'] = spec['delayed_navigation_protocol']
        task['fragment']['planning_intent_protocol'] = spec['planning_intent_protocol']
        for extension in ('reading_progress_protocol','ending_policy'):
            task['fragment'][extension] = spec[extension]
        if 'reference_protocol' in spec:
            task['fragment']['reference_protocol'] = spec['reference_protocol']
        if skip_wechat_articles:
            task['fragment']['skip_wechat_articles'] = True
        task['fragment']['effective_action_rule'] = RULE_VERSION
        task['fragment']['allow_controlled_exception'] = bool(allow_controlled_exception)
        task['fragment']['policy_version'] = FRAGMENT_POLICY
    if plan_protocol is not None:
        from .plan_protocol import PLAN_PROTOCOL as CURRENT_PLAN, READING_PLAN_COMPLETION_POLICY, PLAN_EXECUTION_POLICY
        if decision_protocol != NATIVE_VERSION or plan_protocol != CURRENT_PLAN:
            raise ValueError('Unknown conditional plan protocol')
        for part in (spec, task['fragment']): part['plan_protocol'] = plan_protocol
        for part in (spec, task['fragment']):
            part['reading_completion_policy'] = READING_PLAN_COMPLETION_POLICY
            part['plan_execution_policy'] = PLAN_EXECUTION_POLICY
    if action_stability_protocol is not None:
        from .plan_protocol import ACTION_STABILITY_PROTOCOL
        if action_stability_protocol != ACTION_STABILITY_PROTOCOL or plan_protocol is None:
            raise ValueError('Unknown action stability protocol')
        for part in (spec, task['fragment']): part['action_stability_protocol'] = action_stability_protocol
    if effort_profile is not None:
        if decision_protocol != NATIVE_VERSION:
            raise ValueError('reasoning effort profile requires a native decision task')
        frozen_profile = validate_effort_profile(effort_profile)
        for part in (spec, task['fragment']): part['reasoning_effort_profile'] = deepcopy(frozen_profile)
    if plan_protocol is not None or effort_profile is not None:
        task['task_id'] = 'react-' + object_sha256({'url': url, 'spec': spec})[:24]
    if trusted_prefix_protocol is not None:
        from .plan_protocol import TRUSTED_PREFIX_POLICY
        if trusted_prefix_protocol != TRUSTED_PREFIX_POLICY:
            raise ValueError('Unknown trusted prefix protocol')
        for part in (spec, task['fragment']): part['trusted_prefix_protocol'] = trusted_prefix_protocol
        task['task_id'] = 'react-' + object_sha256({'url': url, 'spec': spec})[:24]
    if pilot_identity is not None:
        task['pilot_identity'] = deepcopy(pilot_identity)
    validate_task(task)
    return task



def configure_candidate_protocols(task):
    """Stamp new candidate compilation before its caller's final hash/validation.

    Call after applying an optional session objective, so its explicit contract
    keeps precedence over ordinary Wiki completion. Never called on load/replay.
    """
    from .wiki_reading import configure
    from .numeric_result_evidence import VERSION as NUMERIC_POLICY
    configure(task)
    for part in (task['fragment'],task['workflow_proposal']['spec']):
        part['numeric_result_evidence_policy']=NUMERIC_POLICY


def build_candidate_task(capability, task_version, budgets=None, collection_strategy=None):
    """Load the claimed candidate goal as requested_goal; the loop keeps the claim."""
    from .candidate_contract import validate_observation
    binding = validate_observation(capability)
    candidate = binding['candidate']
    candidate_name = capability['capabilities'][0].get('title') or '当前网页'
    candidate_description = describe_goal(candidate.get('requested_goal'))
    natural = (f'在「{candidate_name}」围绕{candidate_description}执行相关的连续真实网页操作'
               if candidate_description else f'在「{candidate_name}」依据可见功能确定具体目标并执行连续真实网页操作')
    actions = sorted(set(capability.get('supported_actions') or []) & set(ALLOWED_TOOL_ACTIONS))
    if not actions:
        raise ValueError('Candidate capability supports none of the react actions')
    from .plan_protocol import ENDING_POLICY as CLOSE_POLICY, PLAN_PROTOCOL, ACTION_STABILITY_PROTOCOL as FOCUS_PROTOCOL
    from .collection_strategy import STRATEGY_SCREENSHOT_PLAN, STRATEGY_BANDED_REACT
    # 新任务缺省策略2；显式react在freeze处构造期即被拒绝（早于浏览器/模型）。
    strategy = collection_strategy or STRATEGY_SCREENSHOT_PLAN
    if strategy == STRATEGY_SCREENSHOT_PLAN:
        # 策略 2 explicitly selected: no conditional-plan protocol, so no band /
        # finish_when / predicate-enum gates apply; the screenshot session owns
        # its own loop while the complete-goal save rules stay identical.
        task = build_url_task(url=capability['site_uri'], task_version=task_version,
            ending_policy=CLOSE_POLICY, site_category=capability['site_category'],
            app_name=candidate_name,
            task_family=(capability.get('task_families') or ['navigation-reading'])[0],
            allowed_actions=actions, instruction=natural, budgets=budgets, pilot_identity=None)
    else:
        task = build_url_task(url=capability['site_uri'], task_version=task_version, ending_policy=CLOSE_POLICY,
            plan_protocol=PLAN_PROTOCOL, action_stability_protocol=FOCUS_PROTOCOL,
            site_category=capability['site_category'],
            app_name=candidate_name,
            task_family=(capability.get('task_families') or ['navigation-reading'])[0],
            allowed_actions=actions, instruction=natural, budgets=budgets, pilot_identity=None)
    from .collection_strategy import freeze as freeze_strategy
    if strategy == STRATEGY_SCREENSHOT_PLAN:
        freeze_strategy(task, strategy)
    else:
        for part in (task['fragment'],task['workflow_proposal']['spec']):
            part['result_execution_policy']=RESULT_EXECUTION_POLICY
            part['result_completion_protocol']=RESULT_COMPLETION_PROTOCOL
        configure_candidate_protocols(task)
        freeze_strategy(task, STRATEGY_BANDED_REACT)
    task['task_id']='react-'+object_sha256({'url':task['initial_url'],'spec':task['workflow_proposal']['spec']})[:24]
    task['capability_id'] = capability['capability_id']
    task['capability_version'] = capability['version']
    task['candidate_binding'] = deepcopy(binding)
    task['fragment']['entry_mode'] = 'candidate'
    task['fragment']['candidate_attempt'] = binding['claim_id']
    task['final_result'] = (f'查看围绕{candidate_description}操作后的实际状态；完整业务完成未声明。'
                            if candidate_description else '查看本段真实操作后的实际状态；完整业务完成未声明。')
    task['completion_judgement'] = task['final_result']
    task['workflow_proposal']['evidence'] = [deepcopy(ref) for ref in (capability.get('evidence') or [])]
    if capability.get('pilot_identity'):
        task['pilot_identity'] = deepcopy(capability['pilot_identity'])
    from .candidate_contract import validate_task_binding
    validate_task_binding(task)
    validate_task(task)
    return task


def build_capability_task(capability, pilot_identity, task_version, budgets=None, registration='1'):
    """React entry bound to an existing qualified capability and page identity.

    The loop semantics stay URL-only (requested_goal null, working goal built
    from the live first observation); the capability supplies the authorized
    page, action whitelist, evidence chain and (via the identity file) the
    pilot page ownership this campaign requires.
    """
    from .planning import validate_capability
    validate_capability(capability, require_ready=False)
    page = capability['capabilities'][0]
    url = capability['site_uri']
    app_name = (pilot_identity or {}).get('application', {}).get('name') or \
        page.get('title') or url
    actions = sorted(set(capability.get('supported_actions') or []) & set(ALLOWED_TOOL_ACTIONS))
    if not actions:
        raise ValueError('Qualified capability supports none of the react actions')
    task = build_url_task(url=url, task_version=task_version,
        site_category=capability['site_category'], app_name=app_name,
        task_family=(capability.get('task_families') or ['navigation-reading'])[0],
        allowed_actions=actions, instruction=None, site_uri=url, budgets=budgets,
        pilot_identity=pilot_identity, registration=registration)
    task['capability_id'] = capability['capability_id']
    task['capability_version'] = capability['version']
    task['fragment']['entry_mode'] = 'capability'
    task['workflow_proposal']['evidence'] = [deepcopy(ref) for ref in (capability.get('evidence') or [])]
    # 新任务一律冻结策略2（与build_candidate_task同一freeze路径）；策略1在
    # freeze处拒绝。策略标记先入spec，再按惯例重算task_id。
    from .collection_strategy import freeze as freeze_strategy, STRATEGY_SCREENSHOT_PLAN
    freeze_strategy(task, STRATEGY_SCREENSHOT_PLAN)
    task['task_id'] = 'react-' + object_sha256({'url': url, 'spec': task['workflow_proposal']['spec']})[:24]
    if pilot_identity:
        from .production_identity import validate_identity
        validate_identity(task)
    validate_task(task)
    return task


def validate_task(task):
    from jsonschema import Draft202012Validator
    from .task_instruction import validate_task_instruction
    fragment = task.get('fragment', {})
    if fragment.get('schema_version') != REACT_VERSION or fragment.get('controller_version') != REACT_VERSION:
        raise ValueError('React task requires its protocol boundary')
    if (fragment.get('business_completion') != 'NOT_CLAIMED' or task.get('stop_when_final') is not False
            or task.get('content_preparation') is not False
            or task.get('operations') != [] or task.get('required_actions') != []
            or task.get('final_assertions') != []):
        raise ValueError('React boundary must stay a dynamic raw-execution scope')
    if (fragment.get('reference_protocol') not in (None, REFERENCE_PROTOCOL)
            or (fragment.get('reference_protocol') is not None and fragment.get('decision_protocol') != NATIVE_VERSION)):
        raise ValueError('Unknown observation reference protocol')
    budgets = fragment.get('budgets')
    native = fragment.get('decision_protocol') == NATIVE_VERSION
    if fragment.get('decision_protocol') not in (None, NATIVE_VERSION):
        raise ValueError('Unknown React decision protocol')
    if (not isinstance(budgets, dict) or set(budgets) != set(BUDGET_KEYS)
            or any(type(limit) is not int or limit < 1 for limit in budgets.values() if limit is not None)
            or False):
        raise ValueError('React budgets exceed the frozen protocol limits')
    actions = fragment.get('allowed_actions')
    if not isinstance(actions, list) or not actions or any(action not in ALLOWED_TOOL_ACTIONS for action in actions):
        raise ValueError('React task needs a nonempty supported action whitelist')
    spec = (task.get('workflow_proposal') or {}).get('spec') or {}
    for extension in ('delayed_navigation_protocol','planning_intent_protocol','reading_progress_protocol','ending_policy','plan_protocol','session_objective','action_stability_protocol','trusted_prefix_protocol','reading_completion_policy','plan_execution_policy','wiki_reading_completion_protocol','numeric_result_evidence_policy','result_execution_policy','result_completion_protocol','collection_strategy'):
        if spec.get(extension) != fragment.get(extension):
            raise ValueError('Mismatched frozen React extension: ' + extension)
    from .collection_strategy import strategy_id as _frozen_strategy
    _frozen_strategy(task)  # Absent markers keep the react-chain reading; sealed
    # pre-rename strategy ids map to the same current strategies; unknown ids fail.
    if fragment.get('wiki_reading_completion_protocol') not in (None, WIKI_READING_COMPLETION):
        raise ValueError('Unknown ordinary Wiki reading completion protocol')
    if fragment.get('wiki_reading_completion_protocol') and fragment.get('plan_protocol') != PLAN_PROTOCOL:
        raise ValueError('Wiki completion requires the conditional plan')
    if fragment.get('result_completion_protocol') not in (None, RESULT_COMPLETION_PROTOCOL):
        raise ValueError('Unknown ordinary result completion protocol')
    if fragment.get('result_completion_protocol') and fragment.get('result_execution_policy') != RESULT_EXECUTION_POLICY:
        raise ValueError('Result completion requires frozen result-execution evidence')
    if fragment.get('result_execution_policy') not in (None, RESULT_EXECUTION_POLICY):
        raise ValueError('Unknown result execution policy')
    if fragment.get('result_execution_policy') and fragment.get('plan_protocol') != PLAN_PROTOCOL:
        raise ValueError('Result execution policy requires the conditional plan')
    if fragment.get('numeric_result_evidence_policy') not in (None, NUMERIC_RESULT_EVIDENCE_POLICY):
        raise ValueError('Unknown numeric result evidence policy')
    if fragment.get('session_objective'):
        from .session_objective import bind
        binding=fragment['session_objective']
        claim=load_json(task['candidate_binding']['claim_reference']['path'])
        if bind(binding['reference'],claim)!=binding:raise ValueError('Frozen session objective was changed')
    from .goal_evidence import contract_for, validate_contract
    contract = contract_for(task)
    if contract is not None:
        validate_contract(contract)
    if fragment.get('plan_protocol') not in (None, PLAN_PROTOCOL) or (fragment.get('plan_protocol') and fragment.get('decision_protocol') != NATIVE_VERSION):
        raise ValueError('Invalid frozen plan protocol')
    if fragment.get('reading_completion_policy') is not None:
        if (fragment['reading_completion_policy'] != READING_PLAN_COMPLETION_POLICY
                or fragment.get('plan_protocol') != PLAN_PROTOCOL
                or fragment.get('ending_policy') != ENDING_POLICY):
            raise ValueError('Unknown frozen reading completion policy or incompatible task')
    if fragment.get('plan_execution_policy') is not None:
        if (fragment['plan_execution_policy'] != PLAN_EXECUTION_POLICY
                or fragment.get('plan_protocol') != PLAN_PROTOCOL
                or fragment.get('ending_policy') != ENDING_POLICY
                or fragment.get('reading_completion_policy') != READING_PLAN_COMPLETION_POLICY):
            raise ValueError('Unknown frozen plan execution policy or incompatible task')
    if fragment.get('action_stability_protocol') not in (None, ACTION_STABILITY_PROTOCOL):
        raise ValueError('Unknown frozen action stability protocol')
    if fragment.get('trusted_prefix_protocol') not in (None, TRUSTED_PREFIX_POLICY):
        raise ValueError('Unknown frozen trusted prefix protocol')
    if fragment.get('ending_policy') == ENDING_POLICY:
        if fragment.get('trusted_prefix_protocol') is not None or fragment.get('allow_controlled_exception'):
            raise ValueError('Complete-goal tasks cannot enable trusted-prefix or controlled-exception delivery')
    if fragment.get('reasoning_effort_profile') is not None:
        if not native:
            raise ValueError('reasoning_effort_profile requires a native decision task')
        if validate_effort_profile(fragment['reasoning_effort_profile']) != spec.get('reasoning_effort_profile'):
            raise ValueError('Invalid frozen reasoning effort profile')
    if fragment.get('plan_protocol') and fragment.get('ending_policy') != ENDING_POLICY:
        raise ValueError('Conditional plan and ending policy do not match')
    if fragment.get('ending_policy') not in (None, ENDING_POLICY):
        raise ValueError('Unknown frozen ending policy')
    if 'glm_http_call_limit' in spec or 'glm_http_call_limit' in fragment:
        # 读侧双接受：历史冻结值25与当前上限40都合法，仅改写仍被拒绝。
        legacy_limits = (SessionGLMCallLimit.limit, 25)
        if not native or any(type(part.get('glm_http_call_limit')) is not int or
                             part['glm_http_call_limit'] not in legacy_limits for part in (fragment, spec)):
            raise ValueError('Invalid signed ReAct GLM session limit')
    if native and (spec.get('decision_protocol') != fragment.get('decision_protocol')
                   or fragment.get('effective_action_rule') != EFFECTIVE_ACTION_RULE
                   or spec.get('effective_action_rule') != fragment.get('effective_action_rule')
                   or spec.get('budgets') != budgets
                   or spec.get('allowed_actions') != actions
                   or spec.get('allow_controlled_exception') != fragment.get('allow_controlled_exception')
                   or spec.get('navigation_protocol') != fragment.get('navigation_protocol')
                   or spec.get('skip_wechat_articles') != fragment.get('skip_wechat_articles')
                   or spec.get('reference_protocol') != fragment.get('reference_protocol')):
        raise ValueError('Native React policy/budgets differ from frozen spec')
    if task['task_id'] != 'react-' + object_sha256({'url': spec.get('entry_url'), 'spec': spec})[:24]:
        raise ValueError('React task identity must bind its URL and spec')
    if task.get('initial_url') != spec.get('entry_url'):
        raise ValueError('React entry URL differs from its frozen spec')
    validate_task_instruction(task['instruction'])
    if 'candidate_binding' in task:
        from .candidate_contract import validate_task_binding
        validate_task_binding(task)
    evidence = task['workflow_proposal'].get('evidence') or []
    if evidence:
        verify_evidence(evidence)
    return task


def compact_observation(observation, allowed_actions=None, *, bounded=False):
    """Prompt-facing projection: ids, excerpt, control truth; details via inspect."""
    allowed = set(allowed_actions) if allowed_actions is not None else set(ACTIONS)
    controls = {}
    for cid, control in observation['controls'].items():
        value = control['value'] or {}
        controls[cid] = {
            'labels': [row['text'] for row in control['readable_labels']][:4],
            'tag': control['binding'].get('tag'),
            'value_state': {k: value.get(k) for k in ('value', 'checked', 'focused') if k in value},
            'actions': {action: (truth['status'] if truth['status'] == 'PROVEN'
                                 else truth['status'] + '/' + truth['reason'])
                        for action, truth in control['actions'].items() if action in allowed},
        }
        if bounded:
            # Tree text is a search hint, never a rendered-label proof.
            controls[cid]['text_hint'] = (control.get('element', {}).get('text') or '')[:100]
            controls[cid]['hint_is_action_evidence'] = False
            if any(t.get('reason') == 'MISSING_TARGET_PROBE' for a, t in control['actions'].items() if a in allowed):
                controls[cid]['next_evidence'] = 'observe(focus_control_id=' + cid + ')'
        if control.get('probe'):
            probe = control['probe']
            controls[cid]['focused_region'] = {
                'bbox': probe.get('bbox'), 'hit_valid': probe.get('hit_valid'),
                'enabled': probe.get('enabled'), 'labels': control['readable_labels'][:4]}
        if control.get('navigation_skip'):
            controls[cid]['navigation_skip'] = control['navigation_skip']
    total_controls = len(controls)
    if bounded:
        controls = dict(sorted(controls.items(), key=lambda item: ('focused_region' not in item[1],
            not any(value == PROVEN for value in item[1]['actions'].values()),
            not bool(item[1]['labels']), item[0]))[:24])
    return {
        'observation_id': observation['observation_id'],
        'url': observation['url'],
        'document_identity': observation['document_identity'],
        'viewport': observation['viewport'],
        'scroll': observation['scroll'],
        'capture_verified': observation['capture_verified'],
        'summary': (observation.get('visible_text') or '')[:600],
        'html_excerpt': '' if bounded else (observation.get('html') or '')[:_HTML_EXCERPT_CHARS],
        'image_ref': observation['evidence']['image']['path'],
        'controls': controls,
        'page_actions': [action for action in observation['page_actions'] if action in allowed],
        'control_coverage': {'shown': len(controls), 'total': total_controls,
                             'remaining_via': 'inspect(kind=search, observation_id, query) or inspect(kind=control, observation_id, target_id)'},
        **({'projection_version': 'consumer-observation-hints-1',
            'material_boundary': {'shown': '同步原图、可见文字前600字符、最多24个控件摘要',
                'recoverable': 'inspect(search/control/html) 分页找回原观察材料；控件文字线索及HTML不提升actions',
                'probe_policy': '仅MISSING_TARGET_PROBE用定向observe；遮挡、歧义、旧观察仍须原规则核验'}} if bounded else {}),
        'coverage': observation.get('coverage'),
        'duplicate_hint': observation.get('duplicate_hint') or [],
    }


def compact_trajectory(trajectory):
    return [{'operation_id': row['operation_id'], 'action': row['action'],
             'goal': row['goal'], 'expected': row['expected'],
             'observed_changed': row.get('observed_changed'),
             'effective': row.get('effective', True),
             'actual_change': row.get('effect_evidence') or row.get('observed')}  for row in trajectory]


def _raw_files(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): file_sha(p)
            for p in sorted(root.rglob('*')) if p.is_file()}


class RawSessionCore:
    """Owns one browser page from entry navigation to raw-execution close.

    The decision loop is deliberately absent: each strategy subclass supplies
    its own. Strategy-1 only overrides never load 策略 2 modules and vice versa;
    the shared facts below stay byte-identical for both.
    """

    def _observation_policy(self):
        from . import agent_observation
        return agent_observation

    def _compile_action(self, step):
        return compile_step(self.task, self.page_urls, step, self.current,
                            navigation_count=self.navigation_count)

    def _atomic_effect(self, before, after, action, arguments, control_id, **kwargs):
        return atomic_effect(before, after, action, arguments, control_id, **kwargs)

    def _make_plan_controller(self):
        """策略 1 installs its conditional-plan controller here; 策略 2 does not."""
        return None

    def _boundary_system_prompt_sha256(self):
        return object_sha256(NATIVE_SYSTEM)

    def _boundary_tool_schema_sha256(self, contracted):
        return object_sha256(native_tools(self.task['fragment']['allowed_actions'],
            self.task['fragment']['decision_protocol'],
            self.task['fragment'].get('reference_protocol')))

    def __init__(self, task, directory, choose, page, *, steps_directory=None, navigation=None,
                 url_check=None, preflight=None, frame_guard=None, site_context=None,
                 entry_observation=None, attempt_id=None, phase_ledger=None, host_limits=None,
                 runlog=None):
        validate_task(task)
        self.task = deepcopy(task)
        self.native = self.task['fragment'].get('decision_protocol') == NATIVE_VERSION
        from .goal_evidence import contract_for
        contracted = bool(contract_for(task))
        self.plan_controller = self._make_plan_controller()
        self.entry_observation = entry_observation
        self.history = []
        self.tool_call_ids = set()
        self.pending_tool_call_id = None
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.steps_directory = Path(steps_directory) if steps_directory else (self.root / 'steps' if self.native else None)
        if self.steps_directory:
            self.steps_directory.mkdir(parents=True, exist_ok=True)
        self.choose = choose
        self.page = page
        self.navigation = navigation
        self.url_check = url_check
        self.preflight = preflight
        self.frame_guard = frame_guard
        self.context = deepcopy(site_context or {})
        self.attempt_id = attempt_id or str(self.root.resolve())
        # Optional display-only run log; None keeps every strategy-1 session
        # byte-identical in behavior. Log fields never enter business identity.
        self.runlog = runlog
        # Optional phase metering into the output's metering/phases.jsonl; the
        # session never creates or requires a platform of its own.
        self.phase_ledger = Path(phase_ledger) if phase_ledger else None
        self.active_reference = None
        self.budgets = (dict.fromkeys(BUDGET_KEYS)
            if self.task['fragment'].get('ending_policy') == ENDING_POLICY
            else deepcopy(self.task['fragment']['budgets']))
        self.glm_session_id = getattr(choose, 'glm_session_id', None)
        self.glm_http_requests = None
        if self.native and self.glm_session_id:
            self.budgets['max_model_calls'] = choose.request_limit
        self.stop_details = None
        self.requested_goal = struct_goal(self.task)
        self.working_goal = None
        self.current = None
        self.goal_updates = []
        self.used = {key: 0 for key in BUDGET_KEYS}
        self.state = 'recording'
        self.stop_reason = None
        self.stop_summary = None
        self.short_flow = False
        self.short_flow_reason = None
        self.unknown = False
        self.failure_class = 'collector'
        self.observations = []
        self.observation_records = {}
        self.focus_history = set()
        self.trajectory = []
        self.last_tool_result = None
        self.last_decision_summary = None
        self.sequence = 0
        self.no_progress = 0
        self.read_evidence = set()
        self.navigation_count = 0
        self.actual_dispatches = 0
        self.started = time.monotonic()
        # 会话软时限/收尾宽限对ending-policy任务同样生效（修复ENDING_POLICY
        # 丢弃host_limits的接线）：软时限后停止新增业务动作与模型请求。
        self.host_limits = deepcopy(host_limits) if host_limits else None
        self.page_urls = list(self.task['fragment']['page_urls'])
        self.dialogs = []
        self.excluded_links_seen = set()
        self.events = []
        from .browser import record_native_dialog
        record_native_dialog(self.page, self.dialogs)
        self.binding = exclusive(self.root / 'boundary.json',
            {'protocol': REACT_VERSION, 'task': self.task, 'budgets': self.budgets,
             'language_exclusion_policy': __import__('webcollect.page_language',fromlist=['VERSION']).VERSION,
             **({'host_limits': self.host_limits} if self.host_limits else {}),
             'system_prompt_sha256': self._boundary_system_prompt_sha256(),
             'decision_protocol': self.task['fragment']['decision_protocol'] if self.native else REACT_VERSION,
             **({'attempt_id': self.attempt_id} if contracted or self.task['fragment'].get('result_completion_protocol')==RESULT_COMPLETION_PROTOCOL else {}),
             **({'first_plan_reasoning_effort': getattr(choose,'first_plan_reasoning_effort',None),
                 'branch_reasoning_effort': getattr(choose,'branch_reasoning_effort',None)} if self.native else {}),
             **({'first_plan_timeout_seconds': choose.first_plan_timeout_seconds}
                if getattr(choose,'first_plan_timeout_seconds',None) else {}),
             **({'tool_schema_sha256': self._boundary_tool_schema_sha256(contracted),
                 'effective_action_rule': RULE_VERSION,
                 # The recorded effort is the value actually dispatched, not the
                 # frozen config default; per-phase values live in the fields above.
                 'reasoning_effort': getattr(choose,'first_plan_reasoning_effort',None) or 'max'} if self.native else {})})
        # The append-only trajectory ledger exists from the start so the raw
        # receipt can bind it even for a zero-action honest closure.
        (self.root / 'trajectory.jsonl').touch(exist_ok=False)

    def _compact(self, observation):
        if not self.native:
            result = compact_observation(observation)
            result.pop('control_coverage', None)
            return result
        result = compact_observation(observation, self.task['fragment']['allowed_actions'], bounded=self.native)
        if self.navigation_count < 1:
            result['page_actions'] = [name for name in result['page_actions'] if name != 'back']
        return result

    def _phase(self, name, **scope):
        """Reuse telemetry.phase when a ledger is bound; otherwise a no-op."""
        from contextlib import nullcontext
        from .telemetry import phase as _telemetry_phase
        if self.phase_ledger is None:
            return nullcontext()
        return _telemetry_phase(self.phase_ledger, name,
                                scope={'attempt_id': self.attempt_id, **scope})

    # ------------------------------------------------------------------ journal

    def event(self, kind, **payload):
        self.sequence += 1
        record = exclusive(self.root / f'{self.sequence:04}-{kind}.json',
            {'kind': kind, 'protocol': REACT_VERSION, 'boundary': self.binding,
             'used': {k: self.used[k] for k in BUDGET_KEYS}, **payload})
        self.events.append(record)
        return record

    def _runlog(self, event, **fields):
        log = getattr(self, 'runlog', None)
        if log is not None:
            log.info(event, **fields)

    def append_trajectory(self, row):
        self.trajectory.append(row)
        with (self.root / 'trajectory.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
            stream.flush()

    # ------------------------------------------------------------------ budget

    def _left(self, key):
        if key == 'max_seconds':
            remaining = (float('inf') if self.budgets[key] is None else
                         self.budgets[key] - (time.monotonic() - self.started))
            if self.host_limits:
                remaining = min(remaining, self.host_limits['soft_seconds']
                    - (time.monotonic() - self.host_limits['started_monotonic']))
            return max(0.0, remaining)
        if self.budgets[key] is None:
            return float('inf')
        return self.budgets[key] - self.used[key]

    def _consume(self, key, amount=1):
        if key == 'max_seconds':
            return
        if self._left(key) < amount:
            raise ReactStop('budget', '预算耗尽：' + key)
        self.used[key] += amount

    # ------------------------------------------------------------------ observing

    @staticmethod
    def _probe_key(observation):
        """A probe is new evidence only on a changed page state; value edits,
        navigations and site-side mutations all shift the state hash."""
        return observation['state_sha256']

    async def _capture_observation(self, selector, index):
        """Trusted capture; a mid-snapshot navigation gets one settled retry.

        The observed v13 fact: clicking a search button navigates while the
        effect snapshot's evaluate is in flight and Playwright destroys its
        execution context. The action already happened; re-observing the
        settled page is honest effect evidence and never re-executes anything.
        """
        from .browser import capture
        number = self.used['max_observations']
        action_scope = None
        from .action_stability import ACTION_STABILITY_PROTOCOL as ACTION_SCOPED_RULE, post_action_document_scope
        evidence_protocol=self.task['fragment'].get('action_stability_protocol')
        if evidence_protocol == ACTION_SCOPED_RULE:
            # Minimal post-action observation: the captured document is internally
            # settled; the action effect itself is proven by the per-action
            # predicates, never by two whole-page screenshots agreeing.
            trigger=getattr(self,'_navigation_trigger',None)
            if self.current:
                source=(getattr(self,'_navigation_source',None) if trigger else None) or load_json(self.current['evidence']['state']['path'])
                action_scope=post_action_document_scope(source,trigger,version=evidence_protocol)
            else:
                # An entry observation has no action target; keep its document
                # identity proof without any whole-frame rule.
                action_scope=post_action_document_scope({'url':self.page.url},version=evidence_protocol)
                action_scope['purpose']='entry_observation'
        options={'action_scope':action_scope} if action_scope else {}
        after_dispatch = bool(getattr(self,'_navigation_trigger',None))
        for attempt in (0, 1):
            try:
                with self._phase('capture_observation', observation=self.used['max_observations'],
                                 selector=selector, retry=attempt):
                    return await capture(self.page, selector, index or 0, timeout=REACT_OBSERVE_TIMEOUT_SECONDS,
                        total_timeout=REACT_OBSERVE_TIMEOUT_SECONDS, **options)
            except Exception as error:
                reason = str(error)
                navigation_race = ('execution context was destroyed' in reason.lower()
                                   and 'navigation' in reason.lower())
                if after_dispatch and attempt == 0 and navigation_race:
                    self.event('capture-navigation-retry', reason=reason,
                               retry=1, dispatched_again=False)
                    try:
                        await asyncio.wait_for(self.page.wait_for_load_state('domcontentloaded'), timeout=20)
                    except Exception as settle_error:
                        error = settle_error
                    else:
                        continue
                ref=exclusive(self.root/f'capture-rejection-{number:03}.json',
                    {'error_type':type(error).__name__,'reason':str(error),'diagnostic':getattr(error,'capture',None),
                     'after_dispatch':after_dispatch,'actual_actions':self.actual_dispatches,
                     'effective_steps':len(self.trajectory),'accepted_as_formal_frame':False})
                self.event('capture-rejected',evidence=ref,after_dispatch=after_dispatch)
                raise ReactStop('blocked','CAPTURE_AFTER_ACTION_UNVERIFIED: '+str(error) if after_dispatch else 'CAPTURE_REJECTED: '+str(error),
                    'interrupted' if after_dispatch else getattr(error,'responsibility','collector' if 'UNSUPPORTED_GEOMETRY' in str(error) else 'program'),
                    unknown=after_dispatch,capture_rejection=ref) from error

    async def _observe(self, focus_control_id=None):
        """Fresh trusted observation in the same session; old act bindings die."""
        from .browser import capture
        if focus_control_id == 'null':
            return self._rejected('observe', 'NULL_STRING: 整页观察请传 JSON null，不能传字符串 "null"',
                data={'next_tool':{'name':'observe','arguments':{'focus_control_id':None}},
                      'actual_actions_delta':0, 'effective_steps_delta':0})
        self._consume('max_observations')
        selector = index = None
        requested_key = None
        control = None
        if focus_control_id is not None:
            control = self.current['controls'].get(focus_control_id)
            if control is None:
                return self._rejected('observe', '未知补充观察控件：' + focus_control_id)
            # One probe per control per document: a repeated focus produces no
            # new evidence and burned five decision rounds in a real run.
            if (focus_control_id, self._probe_key(self.current)) in self.focus_history:
                acquired = (control.get('probe') or {}).get('element_id') == focus_control_id
                return self._rejected('observe',
                    '重复定向观察被拒绝：' + ('当前帧已取得该控件的真实探针。' if acquired else
                    '当前帧仅已尝试，尚未取得该控件的匹配探针。') +
                    '相同状态与绑定再次观察没有新依据；请按实际缺项修订路径，事实变化后再观察，无法继续则如实未完成结束。',
                    data={'target_probe': {'control_id': focus_control_id, 'acquired': acquired}})
            selector, index = control['binding'].get('selector'), control['binding'].get('index', 0)
            requested_key = self._probe_key(self.current)
        for refresh in (0, 1):
            source_document = self.current.get('document_identity') if self.current else None
            old_binding = deepcopy(control.get('binding') or {}) if control else {}
            if focus_control_id is not None:
                # Record the attempted source frame separately from any proof
                # actually obtained in the fresh frame.
                self.focus_history.add((focus_control_id, requested_key))
            captured = await self._capture_observation(selector, index)
            html = await self.page.content()
            observation = self._accept(captured, html, focus_control_id)
            probe = captured['state'].get('target') or {}
            acquired = focus_control_id is not None and probe.get('element_id') == focus_control_id
            if acquired:
                self.focus_history.add((focus_control_id, self._probe_key(observation)))
            fresh = observation['controls'].get(focus_control_id) if focus_control_id is not None else None
            fresh_binding = (fresh or {}).get('binding') or {}
            if (focus_control_id is not None and not acquired and refresh == 0 and control and fresh
                    and source_document == observation.get('document_identity')
                    and fresh_binding.get('selector') and old_binding.get('selector') != fresh_binding['selector']
                    and all(old_binding.get(key) == fresh_binding.get(key) for key in ('tag', 'href'))
                    and control.get('element', {}).get('native_role') == fresh.get('element', {}).get('native_role')):
                self.event('target-probe-binding-refresh', control_id=focus_control_id,
                    old_binding=old_binding, new_binding=fresh_binding, dispatched=False,
                    retry=1, reason='same captured node; positional selector changed; no probe acquired')
                self._consume('max_observations')
                control = fresh
                selector, index = fresh_binding['selector'], fresh_binding.get('index', 0)
                requested_key = self._probe_key(observation)
                continue
            if focus_control_id is not None:
                self.event('target-probe-result', control_id=focus_control_id,
                    probe_acquired=acquired, dispatched=False, refreshed_binding=refresh > 0)
            break
        return self._ok('observe', summary='新观察 ' + observation['observation_id'][:12],
                        data={'observation': self._compact(observation),
                              **({'target_probe': {'control_id': focus_control_id, 'acquired': acquired}}
                                 if focus_control_id is not None else {})})

    def _accept(self, captured, html, focus_control_id=None):
        n = self.used['max_observations']
        stem = self.root / f'observation-{n:03}'
        with stem.with_suffix('.png').open('xb') as stream:
            stream.write(captured['png'])
        stem.with_suffix('.html').write_text(html, encoding='utf-8')
        evidence = {'image': {'path': str(stem.with_suffix('.png').resolve()), 'sha256': file_sha(stem.with_suffix('.png'))},
            'state': exclusive(stem.with_suffix('.json'), captured['state']),
            'capture': exclusive(stem.with_suffix('.capture.json'), captured['capture']),
            'html': {'path': str(stem.with_suffix('.html').resolve()), 'sha256': file_sha(stem.with_suffix('.html'))}}
        verify_evidence(list(evidence.values()))
        observation = self._observation_policy().project(captured['state'],
            {k: evidence[k] for k in ('image', 'state', 'capture')},
            extended_actions=bool(self.task['fragment'].get('plan_protocol')))
        if not observation['capture_verified'] or not observation['document_identity']:
            raise ReactStop('blocked', '同步取证证明缺失', 'program')
        observation['html'] = html
        observation['html_ref'] = evidence['html']
        observation['coverage'] = {'visible_text_chars': len(captured['state'].get('visible_text') or ''),
            'html_chars': len(html), 'hidden_dom_is_not_visible_evidence': True,
            'focus_control_id': focus_control_id, 'supplemental': focus_control_id is not None}
        # Sealed historical tasks keep their original navigation literal; new
        # tasks freeze the stable protocol name only.
        if self.task['fragment'].get('navigation_protocol') in (NAVIGATION_PROTOCOL, 'observed-navigation-2'):
            from .candidate_navigation import extend, excluded_article, NAV_ACTIONS
            trigger = getattr(self, '_navigation_trigger', None)
            pending = getattr(self, '_pending_navigation', None)
            if self.current and self.current['url'] != observation['url'] and not trigger and pending:
                from .candidate_navigation import delayed_landing
                proof = delayed_landing(pending['operation'], pending['source'],
                    load_json(self.current['evidence']['state']['path']), captured['state'],
                    same_tab=self.page is pending['page'],
                    no_other_action=self.actual_dispatches == pending['dispatches'],
                    no_new_tab=tuple(getattr(getattr(self.page,'context',None),'pages',[self.page])) == pending['pages'])
                if proof:
                    proof.update(from_observation_id=self.current['observation_id'],
                                 to_observation_id=observation['observation_id'],
                                 source_observation_id=pending['source_observation_id'])
                    if not hasattr(self,'delayed_navigations'):self.delayed_navigations=[]
                    self.delayed_navigations.append(proof)
                    self.event('delayed-navigation', proof=proof)
                    trigger=pending['operation']
                self._pending_navigation=None
            if self.task['fragment'].get('skip_wechat_articles'):
                for cid, control in observation['controls'].items():
                    href = control['binding'].get('href')
                    if excluded_article(self.task, href):
                        control['navigation_skip'] = 'ARTICLE_OUTSIDE_RUN_SCOPE'
                        for action in ('click','double_click'):
                            control['actions'][action] = {'status':'UNAVAILABLE','reason':'ARTICLE_OUTSIDE_RUN_SCOPE'}
                        key = (observation['url'], href)
                        if key not in self.excluded_links_seen:
                            self.excluded_links_seen.add(key)
                            self.event('navigation-skipped', source_url=key[0], target_url=href, control_id=cid,
                                link_text=control['element'].get('text'), evidence=evidence, reason='ARTICLE_OUTSIDE_RUN_SCOPE', dispatched=False)
                if trigger and excluded_article(self.task, observation['url']):
                    self.event('navigation-excluded-landing', source_url=self.current['url'], landed_url=observation['url'],
                               trigger=trigger['operation_id'], evidence=evidence, reason='ARTICLE_OUTSIDE_RUN_SCOPE', dispatched=True)
            if self.current and self.current['url'] != observation['url'] and (not trigger or trigger['action_type'] not in NAV_ACTIONS):
                raise ReactStop('no_path', 'NAVIGATION_WITHOUT_TRIGGER: observed URL changed without a recorded action', 'collector')
            try:
                extend(self.task,self.page_urls,captured['state'],trigger,
                    source=(pending['source'] if pending and trigger is pending.get('operation') else getattr(self,'_navigation_source',None)),
                    proof=getattr(self,'_navigation_proof',None))
            except ValueError as error:
                raise ReactStop('no_path', str(error), 'collector') from error
        duplicate_hint = []
        if self.frame_guard:
            duplicate_hint = self.frame_guard(evidence['image'])
        observation['duplicate_hint'] = duplicate_hint
        if self.observations:
            previous = self.observation_records[self.observations[-1]]
            if (previous['document_identity'] != observation['document_identity']
                    or previous['url'] != observation['url']):
                self.navigation_count += 1
        self.observations.append(observation['observation_id'])
        self.observation_records[observation['observation_id']] = observation
        self.event('observation', observation_id=observation['observation_id'],
            url=observation['url'], page_host=urlsplit(observation['url']).hostname, evidence=evidence, duplicate_hint=duplicate_hint,
            effective_steps=len(self.trajectory))
        self._runlog('processing', stage='observation', observationId=observation['observation_id'],
            effectiveSteps=len(self.trajectory))
        self.current = observation
        from .page_language import assess
        language = assess(captured['state'], prior_states=[
            load_json(o['evidence']['state']['path']) for oid,o in self.observation_records.items()
            if oid != observation['observation_id'] and o.get('document_identity') == observation['document_identity']])
        if language['excluded']:
            self.event('language-excluded', assessment=language, evidence=evidence,
                       action_replayed=False)
            raise ReactStop('blocked', 'NON_CHINESE_PAGE: rendered Chinese not evidenced', 'collector')
        return observation

    # ------------------------------------------------------------------ tool results

    def _ok(self, tool, *, summary, data, evidence_refs=()):
        return {'tool': tool, 'status': 'ok', 'observation_id': self.current['observation_id'],
                'summary': summary, 'data': data, 'evidence_refs': list(evidence_refs), 'error': None}

    def _rejected(self, tool, reason, *, data=None):
        code = next((code for code in ('NULL_STRING','MISSING_TARGET_PROBE','MISSING_READABLE_LABEL_EVIDENCE','STALE_OBSERVATION') if code in reason), 'TOOL_REJECTED')
        next_tool = {'name':'inspect','arguments':{'kind':'html','observation_id':self.current['observation_id']}}
        cid = (data or {}).get('control_id')
        if code == 'MISSING_TARGET_PROBE' and cid in self.current['controls']:
            next_tool = {'name':'observe','arguments':{'focus_control_id':cid}}
        if (data or {}).get('next_tool'):
            next_tool = data['next_tool']
        if not hasattr(self, 'failure_facts'):
            self.failure_facts = []
        self.failure_facts.append({'tool': tool, 'reason': reason,
                                   'observation_id': self.current['observation_id']})
        self._runlog('tool_rejected', tool=tool, observationId=self.current['observation_id'], reason=reason)
        return {'tool': tool, 'status': 'rejected', 'observation_id': self.current['observation_id'],
                'summary': reason, 'data': data or {}, 'evidence_refs': [],
                'error': ({'code': code,
                           'observation_id':self.current['observation_id'],
                           'next_tool': next_tool}
                          if self.task['fragment'].get('decision_protocol') == NATIVE_VERSION else None)}

    def _need_observation(self, tool, reason, *, data=None):
        return {'tool': tool, 'status': 'need_observation', 'observation_id': self.current['observation_id'],
                'summary': reason, 'data': data or {}, 'evidence_refs': [], 'error': None}

    # ------------------------------------------------------------------ act

    def _validate_step(self, step):
        from jsonschema import Draft202012Validator
        from .collection_strategy import enabled as _screenshot_task
        screenshot_task = _screenshot_task(self.task)
        extended = bool(self.task['fragment'].get('plan_protocol')) or screenshot_task
        action = step.get('action')
        if action in ('drag','wait') and not extended:
            raise ValueError('EXTENDED_ACTION_REQUIRES_PLAN_PROTOCOL')
        if action not in self.task['fragment']['allowed_actions']:
            raise ValueError('动作不在本任务允许范围内：' + str(action))
        schema = obj({'action': {'enum': list(ALLOWED_TOOL_ACTIONS)}, 'goal': TEXT, 'expected': TEXT,
                      **{k: v for k, v in ACTION_ARGUMENTS.get(action, {}).items()}})
        if extended:
            schema['properties'].update(rationale=TEXT,expected_result=TEXT)
            schema['required'].extend(['rationale','expected_result'])
        if screenshot_task and action == 'scroll':
            # Optional current container; absence still denotes page scrolling.
            schema['properties']['control_id'] = TEXT
        if screenshot_task and action in ('type', 'select'):
            schema['properties']['expected_value'] = {'type': 'string', 'maxLength': 500}
            schema['required'].append('expected_value')
            if action == 'select':
                schema['properties']['value'] = {'type': 'string', 'maxLength': 500}
        try:
            Draft202012Validator(schema).validate(step)
        except Exception as error:
            raise ValueError('动作参数不合法：' + str(error).splitlines()[0]) from None
        if self.task['fragment'].get('decision_protocol') == NATIVE_VERSION:
            variants = native_tools(self.task['fragment']['allowed_actions'])[2]['function']['parameters']['properties']['step']
            if extended:
                for variant in variants['oneOf']:
                    variant['properties'].update(rationale=TEXT,expected_result=TEXT)
                    variant['required'].extend(['rationale','expected_result'])
            if screenshot_task:
                for variant in variants['oneOf']:
                    if variant['properties']['action'].get('const') == 'scroll' or variant['properties']['action'].get('enum') == ['scroll']:
                        variant['properties']['control_id'] = TEXT
                    if variant['properties']['action'].get('const') in ('type', 'select') or variant['properties']['action'].get('enum') in (['type'], ['select']):
                        variant['properties']['expected_value'] = {'type': 'string', 'maxLength': 500}
                        variant['required'].append('expected_value')
                        if action == 'select':
                            variant['properties']['value'] = {'type': 'string', 'maxLength': 500}
            try:
                Draft202012Validator(variants).validate(step)
            except Exception as error:
                raise ValueError('ACTION_SCHEMA: ' + str(error).splitlines()[0]) from None
        if action == 'back' and self.navigation_count < 1:
            raise ValueError('当前会话尚无可返回的导航历史，不能执行 back')

    def _v2(self):
        from .closing_policy import enabled
        return enabled(self.task)

    def _action_raw_path(self, step_id):
        if self._v2():
            return self.steps_directory/'action-attempts'/f'business-{self._active_business_attempt:03}-primitive-{self.used["max_actions"]:03}.json'
        return self.steps_directory/f'step_{step_id:03}.json'

    def _range_close(self, kind, reason, *, unknown=False, force_pending=False):
        """Host finish without another model request or browser action."""
        from .closing_policy import attempt_limit, no_effect_proven
        POLICY=self.task['fragment']['ending_policy']
        band=getattr(self.plan_controller,'frozen_band',None) if self.plan_controller else None
        limit=attempt_limit(self.task,band)
        refs=getattr(self,'business_attempt_refs',[])
        attempts=[load_json(ref['path']) for ref in refs]
        tail_dispatches=self.actual_dispatches-len(self.trajectory)
        final_id=self.current['observation_id'] if self.current else None
        final_state=load_json(self.current['evidence']['state']['path']) if self.current else {}
        safe=bool(self.trajectory and final_state.get('visible_text') and not unknown and not self.unknown and not force_pending)
        terminal_bridge=None
        if safe:
            from .reading_progress import same_view
            from .action_stability import action_scoped_view_stable
            prefix=load_json(self.observation_records[self.trajectory[-1]['after_observation_id']]['evidence']['state']['path'])
            if self.task['fragment'].get('action_stability_protocol'):
                # Action-scoped ending: the final frame keeps the same document,
                # scroll and visible reading material; unrelated decorative
                # image/overlay membership changes are not endpoint changes.
                safe=action_scoped_view_stable(prefix,final_state)
            else:
                safe=same_view(prefix,final_state)
            from .direct_completion import enabled as explicit,bridge_evidence
            if not safe and explicit(self.task) and kind=='HOST_PLAN_ENDPOINT' and not tail_dispatches:
                terminal_bridge=bridge_evidence(self.task,
                    self.observation_records[self.trajectory[-1]['after_observation_id']]['evidence'],self.current['evidence'],
                    target_ids=[(r.get('target') or {}).get('control_id') for r in self.trajectory],unverified_tail=tail_dispatches)
                safe=terminal_bridge['proof']['accepted'] is True
        # Tail dispatches fully accounted for by definite attempt outcomes
        # (known zero effect or definite failure) are not unknown effects;
        # model-request UNKNOWN and browser-effect UNKNOWN stay separate facts.
        accounted = sum(a['actual_dispatches_delta'] for a in attempts)
        tail_known = (bool(attempts) and accounted == self.actual_dispatches
                      and all(a['outcome'] != 'EFFECT_UNKNOWN' for a in attempts)
                      and not unknown and not self.unknown)
        if True:
            raws=[load_json(ref['path']) for attempt in attempts for ref in attempt.get('raw_steps',[])]
            dispatched=[raw for raw in raws if raw.get('dispatched') is True]
            omitted=[raw for raw in dispatched if not (raw.get('action_executed') is True
                and raw.get('postconditions_checked') is True
                and raw.get('react',{}).get('effect_evidence',{}).get('verified') is True)]
            from .collection_strategy import enabled as _screenshot_strategy
            screenshot_task=_screenshot_strategy(self.task)
            def _tail_accounted(raw):
                if no_effect_proven(raw,self.observation_records):return True
                if not screenshot_task:return False
                # 模板包各自实现尾部核算；历史任务（无模板标记）解析到单体实现。
                from .screenshot_planners import template_module, task_template_name
                return template_module(task_template_name(self.task)).tail_effect_observed(raw,self)
            tail_known=(tail_known and len(dispatched)==self.actual_dispatches
                and len(omitted)==tail_dispatches
                and all(_tail_accounted(raw) for raw in omitted))
            if tail_dispatches and not tail_known:safe=False
        unknown=bool(unknown or self.unknown or (tail_dispatches and not safe and not tail_known))
        # 策略 2 adds its own verified-completion ending; every other strategy-2
        # ending kind stays flagged/raw-only exactly like the historical kinds.
        ready_kinds=('VISIBLE_GOAL_REPORTED','HOST_PLAN_ENDPOINT','HOST_BOUNDARY_RETURN',
                    *getattr(self,'extra_ready_endings',()))
        flagged=kind not in ready_kinds
        if kind=='AGENT_COMPLETE_VERIFIED' and getattr(self,'completion_endpoint_basis',None) is None:
            raise ValueError('COMPLETE_ENDING_REQUIRES_VERIFIED_COMPLETION')
        self.collection_ending={'protocol':POLICY,'kind':kind,'flagged':flagged,'reason':reason,
            'attempt_limit':limit,'attempt_band':band,
            'business_attempts':len(refs),'actual_atomic_dispatches':self.actual_dispatches,
            'verified_effective_steps':len(self.trajectory),'unverified_tail_dispatches':tail_dispatches,
            'zero_dispatch_attempts':sum(a['actual_dispatches_delta']==0 for a in attempts),
            'finish_count':1,'finish_origin':'host' if kind!='VISIBLE_GOAL_REPORTED' else 'agent',
            **({'plan_protocol':self.task['fragment']['plan_protocol'],
                'endpoint_evidence':self.plan_controller.endpoint_basis(self)} if kind=='HOST_PLAN_ENDPOINT' else {}),
            **({'collection_strategy':deepcopy(self.task['fragment'].get('collection_strategy')),
                'endpoint_evidence':deepcopy(self.completion_endpoint_basis)}
               if kind=='AGENT_COMPLETE_VERIFIED' else {}),
            **({'plan_protocol':self.task['fragment']['plan_protocol'],
                'boundary_return_evidence':__import__('webcollect.consumer_page_policy',fromlist=['ending_evidence']).ending_evidence(
                    self.task,self.trajectory,{oid:load_json(o['evidence']['state']['path']) for oid,o in self.observation_records.items()},final_id)
               } if kind=='HOST_BOUNDARY_RETURN' else {}),
            'finish_is_business_action':False,'wait_is_business_action':False,
            'goal_completion':('VERIFIED' if kind=='AGENT_COMPLETE_VERIFIED' else
                               'AGENT_REPORTED_VISIBLE_GOAL' if kind=='VISIBLE_GOAL_REPORTED' else 'NOT_CLAIMED'),
            'external_effect_unknown':unknown,
            'last_model_intent':getattr(self,'_last_model_intent',None),'last_decision':getattr(self,'_last_decision',None),
            'safe_for_pending_sample':bool(safe),'attempt_refs':refs,
            **({'direct_terminal_bridge':terminal_bridge} if terminal_bridge else {}),
            'final_observation_id':final_id,'final_evidence':deepcopy(self.current['evidence']) if self.current else None,
            'last_attempt':attempts[-1] if attempts else None,
            'raw_only_pending':not safe}
        self.event('range-finish',collection_ending=self.collection_ending)
        self.stop_reason='budget' if kind in ('EIGHT_ATTEMPT_LIMIT','TWELVE_ATTEMPT_LIMIT','TEN_EFFECTIVE_STEP_LIMIT') else 'ready' if kind in ready_kinds else 'blocked'
        self.stop_summary=reason
        self.unknown=self.unknown or unknown
        self.state='finished' if safe else 'closed_pending_reconciliation'

    def _record_business_attempt(self, step, number, before_dispatch, before_effective, *, result=None, failure=None):
        raw_paths=sorted((self.steps_directory/'action-attempts').glob(f'business-{number:03}-*.json')) if self.steps_directory else []
        raw_refs=[{'path':str(p.resolve()),'sha256':file_sha(p)} for p in raw_paths]
        unknown=bool(self.unknown or (failure and failure.unknown))
        dispatch_delta=self.actual_dispatches-before_dispatch;effective_delta=len(self.trajectory)-before_effective
        harmless_no_effect=False
        if dispatch_delta>effective_delta and raw_refs and self.current:
            from .closing_policy import no_effect_proven
            if True:
                raws=[load_json(ref['path']) for ref in raw_refs]
                omitted=[raw for raw in raws if raw.get('dispatched') is True
                    and not (raw.get('action_executed') is True and raw.get('postconditions_checked') is True
                             and raw.get('react',{}).get('effect_evidence',{}).get('verified') is True)]
                harmless_no_effect=(len(omitted)==dispatch_delta-effective_delta
                    and all(no_effect_proven(raw,self.observation_records) for raw in omitted))
            else:
                from .reading_progress import same_view
                tail=load_json(raw_refs[-1]['path'])
                harmless_no_effect=(tail.get('operation',{}).get('action_type')=='scroll'
                    and tail.get('action_executed') is True and tail.get('react',{}).get('after_observation_id')==self.current['observation_id']
                    and same_view(tail['state'],load_json(self.current['evidence']['state']['path'])))
        outcome=('EFFECT_UNKNOWN' if unknown else 'VERIFIED' if effective_delta==dispatch_delta and dispatch_delta>0 and not failure
                 else 'KNOWN_NO_EFFECT' if harmless_no_effect
                 else 'NOT_DISPATCHED' if dispatch_delta==0 else 'EFFECT_NOT_VERIFIED')
        reason=failure.reason if failure else (result or {}).get('summary','业务动作已处理')
        ref=self.event('business-attempt',number=number,step=deepcopy(step),
            decision_number=self.used['max_decisions'],model_tool_call_id=self.pending_tool_call_id,
            request_reference=deepcopy(self.active_reference),model_intent=getattr(self,'_last_model_intent',None),
            decision=getattr(self,'_last_decision',None),raw_steps=raw_refs,
            actual_dispatches_delta=dispatch_delta,effective_steps_delta=effective_delta,outcome=outcome,reason=reason)
        if not hasattr(self,'business_attempt_refs'):self.business_attempt_refs=[]
        self.business_attempt_refs.append(ref)
        from .closing_policy import attempt_limit
        band=getattr(self.plan_controller,'frozen_band',None) if self.plan_controller else None
        limit=attempt_limit(self.task,band)
        if limit is not None and 5<=number<=limit and outcome!='VERIFIED':
            self._range_close(outcome,reason,unknown=unknown)
        elif limit is not None and number==limit and self.plan_controller is None:
            self._range_close('ACTION_BUDGET_LIMIT',f'已达到{limit}次业务动作尝试；未获得目标完成确认，保存真实末态待审')

    async def _tool_act(self, arguments):
        if arguments.get('step',{}).get('action')=='wait':return await self._perform_act(arguments)
        if not self._v2():return await self._perform_act(arguments)
        try:
            if set(arguments)!= {'observation_id','step'} or self.working_goal is None or arguments['observation_id']!=self.current['observation_id']:
                return await self._perform_act(arguments)
            self._validate_step(arguments['step'])
        except (ValueError,KeyError,TypeError):return await self._perform_act(arguments)
        self._awaiting_primitive_attempt=False
        self._last_primitive_failure=None
        before_count=len(getattr(self,'business_attempt_refs',[]))
        result=None;failure=None
        try:result=await self._perform_act(arguments)
        except ReactStop as error:failure=error
        if self.state!='recording':
            return result or self._ok('act',summary=self.stop_summary,data={'collection_ending':self.collection_ending})
        # Each compiled primitive is counted by _execute_primitive. Only a
        # refusal before entering that function needs a zero-dispatch row here.
        if failure is not None and self._last_primitive_failure is failure:raise failure
        if (self._awaiting_primitive_attempt or (len(getattr(self,'business_attempt_refs',[]))==before_count
                and (failure or (result or {}).get('status')!='ok'))):
            number=len(getattr(self,'business_attempt_refs',[]))+1
            self._active_business_attempt=number
            self._record_business_attempt(arguments['step'],number,self.actual_dispatches,len(self.trajectory),result=result,failure=failure)
        if self.state!='recording':
            return self._ok('act',summary=self.stop_summary,data={'collection_ending':self.collection_ending})
        if failure:raise failure
        return result

    async def _perform_act(self, arguments):
        from jsonschema import Draft202012Validator
        if self.working_goal is None:
            return self._rejected('act', '尚未建立工作目标；先依据观察提交 goal_update（可与本工具同轮），或继续查询/观察')
        try:
            Draft202012Validator(obj({'observation_id': TEXT, 'step': {'type': 'object'}})).validate(arguments)
        except Exception as error:
            # Real-run v16 lesson: four of ten decision rounds were burned on
            # action fields flattened into arguments instead of nested in step.
            hint = ''
            if 'step' in str(error) and any(k in arguments for k in
                    ('action', 'control_id', 'value', 'keys', 'direction')):
                hint = ('；动作字段必须嵌套在 step 对象内，形如 '
                        '{"observation_id":"当前观察id","step":{"action":"...","control_id":"...","value":"...","goal":"...","expected":"..."}}')
            return self._rejected('act', 'act 参数不合法：' + str(error).splitlines()[0] + hint)
        step = arguments['step']
        from .direct_article import enabled as direct_article, session_trace, before_action
        if direct_article(self.task):
            try:
                proof=session_trace(self)
                before_action(self.task,load_json(self.current['evidence']['state']['path']),step.get('action'),step,step.get('control_id'),pending=proof['pending_return'])
            except ValueError as error:return self._rejected('act',str(error))
        from .consumer_page_policy import enabled as page_policy, boundary, allowed_exit
        if page_policy(self.task):
            current_state=load_json(self.current['evidence']['state']['path'])
            if boundary(current_state) and not allowed_exit(current_state,step.get('action'),step.get('control_id')):
                return self._rejected('act','PAGE_BOUNDARY: 下一步仅允许该边界支持的真实返回或取消')
        try:
            self._validate_step(step)
        except ValueError as error:
            return self._rejected('act', str(error))
        if arguments['observation_id'] != self.current['observation_id']:
            return self._need_observation('act',
                '动作绑定的是旧观察；旧观察不可派发，请基于当前观察重新决策',
                data={'actual_actions_delta': 0, 'effective_steps_delta': 0,
                      'bound_observation_id': arguments['observation_id']})
        if step['action']=='wait':
            from .browser import execute
            before=self.current
            record=self.event('wait-dispatch',action='wait',arguments={'duration_ms':step['duration_ms']},
                before_observation_id=before['observation_id'],purpose=step['goal'],expected=step['expected'],
                semantic_rationale=step.get('rationale'),semantic_expected_result=step.get('expected_result'),effective_step_delta=0)
            await execute(self.page,'wait',{}, {'duration_ms':step['duration_ms'],'settle_ms':0})
            await self._observe()
            self.event('wait-result',dispatch=record,before_observation_id=before['observation_id'],
                after_observation_id=self.current['observation_id'],before_evidence=before['evidence'],
                after_evidence=self.current['evidence'],effective_step_delta=0)
            self._runlog('wait_executed', observationId=self.current['observation_id'],
                durationMs=step['duration_ms'], effectiveSteps=len(self.trajectory))
            return self._ok('act',summary='必要等待已执行并保存前后观察，不计有效动作',data={'actual_actions_delta':0,'effective_steps_delta':0,'wait_executed':True})
        try:
            compiled = self._compile_action(step)
        except ValueError as error:
            reason = '编译拒绝：' + str(error)
            cid = step.get('control_id')
            control = self.current['controls'].get(cid)
            availability = (control or {}).get('actions', {}).get(step['action'], {})
            if (str(error) == 'INSUFFICIENT: MISSING_TARGET_PROBE' and control
                    and availability.get('reason') == 'MISSING_TARGET_PROBE'):
                return self._rejected('act', reason + f'。请用 observe(focus_control_id={cid}) 获取当前控件的定向观察。',
                    data={'control_id': cid, 'next_tool': {'name': 'observe', 'arguments': {'focus_control_id': cid}},
                          'original_rejection': str(error), 'actual_actions_delta': 0,
                          'effective_steps_delta': 0})
            return self._rejected('act', reason, data={'control_id':cid} if cid else None)
        needed = len(compiled) + RESERVE['max_actions']
        if self._left('max_actions') < needed:
            return self._rejected('act',
                f'剩余动作预算不足以完成该动作并保留结束额度（剩 {self._left("max_actions")}，'
                f'需 {needed}）；请选择更小的动作或 finish')
        if self._left('max_observations') < len(compiled) * (2 if self.native else 1) + RESERVE['max_observations']:
            raise ReactStop('budget', '观察预算不足以完成取证并保留结束额度')
        return await self._dispatch_compiled(step, compiled)

    def _build_operation(self, row, dispatch_state, dispatch_observation):
        """Dispatch-time control truth from the refreshed capture itself.

        Later primitives of a compound step cannot rely on the decision
        observation: the post-action effect capture is a full-page view. The
        probe-bearing refreshed state is the authoritative availability input,
        exactly what require_action re-checks below.
        """
        policy = self._observation_policy()
        action_availability, readable_labels = policy.action_availability, policy.readable_labels
        action = row['action']
        cid = row.get('control_id')
        control = None
        from .candidate_navigation import excluded_article
        if action == 'open_url' and excluded_article(self.task,self.page_urls[int(row['page_id'][1:])]):
            raise ValueError('ARTICLE_OUTSIDE_RUN_SCOPE')
        if action == 'hotkey' and 'enter' in [key.lower() for key in row.get('keys',[])]:
            focused = {e['element_id'] for e in dispatch_state['elements'] if e.get('state') == 'focused'}
            if any(b['element_id'] in focused and excluded_article(self.task,b.get('href'))
                   for b in dispatch_state.get('capture_controls',[])):
                raise ValueError('ARTICLE_OUTSIDE_RUN_SCOPE')
        if cid:
            element = next((e for e in dispatch_state['elements'] if e['element_id'] == cid), None)
            binding = next((b for b in dispatch_state.get('capture_controls', [])
                            if b['element_id'] == cid), None)
            value = next((v for v in dispatch_state.get('values', [])
                          if v['element_id'] == cid), {})
            probe = dispatch_state.get('target')
            if probe and probe.get('element_id') != cid:
                probe = None
            truth = action_availability(dispatch_state, element, binding, value, probe, action)
            if truth['status'] != PROVEN:
                raise ValueError(truth['status'] + ': ' + truth['reason'] + '（' + str(cid) + '）')
            if action == 'type' and getattr(policy, 'STRATEGY', None) == 'screenshot_plan':
                from .screenshot_execution import validate_input_precondition
                validate_input_precondition(row, value, probe)
            if action in ('click','double_click') and excluded_article(self.task,binding.get('href')):
                raise ValueError('ARTICLE_OUTSIDE_RUN_SCOPE')
            control = {'binding': binding, 'labels': readable_labels(probe)}
        operation = {'operation_id': f'react-{self.used["max_actions"] + 1}',
            'subgoal_id': 'react', 'action_type': action,
            'goal': row['goal'], 'rationale': row.get('rationale') or row['goal'], 'expected': row['expected'],
            'evidence': {'observation_protocol': policy.VERSION,
                **({'collection_strategy': policy.STRATEGY} if getattr(policy, 'STRATEGY', None) else {}),
                'state_sha256': object_sha256(dispatch_state),
                'observation_id': self.current['observation_id']}}
        if cid:
            operation.update(selector=control['binding']['selector'],
                             index=control['binding'].get('index', 0))
            operation['evidence'].update(anchor_element_id=cid,
                target_label=control['labels'][0]['text'] if control['labels'] else '')
        if action == 'type':
            operation['arguments'] = {'text': row['value']}
            if 'replace_selected_number' in row:
                operation['evidence']['replace_selected_number'] = row['replace_selected_number']
        elif action == 'select':
            operation['arguments'] = {'option': row['option']}
        elif action == 'hotkey':
            operation['arguments'] = {'keys': row['keys']}
            if cid:
                operation['evidence']['focused_element_id'] = cid
        elif action == 'scroll':
            operation['arguments'] = {'direction': row['direction']}
            if cid:
                container = (control or {}).get('binding', {}).get('scroll_container') or {}
                axis = 'y' if row['direction'] in ('up', 'down') else 'x'
                if not container.get('visible') or axis not in container.get('axes', []):
                    raise ValueError('SCROLL_CONTAINER_NOT_CURRENTLY_SCROLLABLE')
                operation['evidence']['scroll_container'] = deepcopy(container)
        elif action == 'drag':
            endpoint_id=row['end_control_id']
            endpoint=next((e for e in dispatch_state['elements'] if e['element_id']==endpoint_id),None)
            end_binding=next((b for b in dispatch_state.get('capture_controls',[]) if b['element_id']==endpoint_id),None)
            if not endpoint or endpoint.get('visible') is not True or not endpoint.get('enabled') or not endpoint.get('bbox') or not end_binding:
                raise ValueError('DRAG_DESTINATION_NOT_CURRENTLY_VISIBLE')
            box=endpoint['bbox'];width,height=dispatch_state['screen_resolution']
            if not (0<=box[0]<box[2]<=width and 0<=box[1]<box[3]<=height):raise ValueError('DRAG_DESTINATION_OUTSIDE_VIEWPORT')
            operation['arguments']={'end_x':int((box[0]+box[2])/2),'end_y':int((box[1]+box[3])/2)}
            operation['evidence']['drag_destination']={'element_id':endpoint_id,'selector':end_binding['selector'],
                'index':end_binding.get('index',0),'bbox':deepcopy(box),'observation_id':self.current['observation_id']}
        elif action == 'open_url':
            operation['arguments'] = {'url': self.page_urls[int(row['page_id'][1:])]}
        else:
            operation['arguments'] = {}
        if row.get('replacement') is not None:
            operation['replacement'] = row['replacement']
        policy.require_action(dispatch_state, operation)
        return operation

    async def _dispatch_compiled(self, step, compiled, *, _refresh=0, _deadline=None):
        from .browser import EvidenceStale, execute, prepare_action, verify_execution_state
        from .collect import capture_before_action
        if self.host_limits and self._left('max_seconds') <= 0:
            raise ReactStop('budget', '宿主安全收尾时限已到，不再派发新动作')
        from .production_identity import before_action
        _deadline=_deadline or time.monotonic()+REACT_OBSERVE_TIMEOUT_SECONDS
        executed = []
        prior_raws = []
        for row in compiled:
            if self._v2() and self.state!='recording':
                return self._ok('act',summary=self.stop_summary,data={'collection_ending':self.collection_ending})
            self._awaiting_primitive_attempt=self._v2()
            cid = row.get('control_id')
            selector = index = None
            if cid:
                control = self.current['controls'].get(cid)
                if control is None:
                    return self._need_observation('act', f'目标控件 {cid} 不在当前观察中，请重新观察', data=self._deltas(executed))
                selector, index = control['binding'].get('selector'), control['binding'].get('index', 0)
            action_scope = None
            from .action_stability import ACTION_STABILITY_PROTOCOL, action_scoped_scope, document_scope
            focus_protocol = self.task['fragment'].get('action_stability_protocol')
            if focus_protocol == ACTION_STABILITY_PROTOCOL:
                # Action-relevant minimal evidence: every ordinary action gets a
                # target-level (click/type/hotkey) or document-level
                # (scroll/back/open_url) scope; unrelated overlay/announcement
                # repaints never block dispatch.
                for scope_refresh in range(2):
                    try:
                        scoped_state = load_json(self.current['evidence']['state']['path'])
                        if row['action'] in ('click', 'type') and cid:
                            action_scope = action_scoped_scope(scoped_state, cid, row['action'], version=focus_protocol)
                        elif row['action'] == 'hotkey':
                            focused = [key for key, c in self.current['controls'].items()
                                       if (c.get('value') or {}).get('focused') is True]
                            if len(focused) == 1 and not any(str(k).lower() in ('esc','escape') for k in row.get('keys', [])):
                                action_scope = action_scoped_scope(scoped_state, focused[0], 'hotkey', version=focus_protocol)
                            else:
                                action_scope = document_scope(scoped_state, 'hotkey', version=focus_protocol)
                        elif row['action'] in ('scroll', 'back', 'open_url'):
                            action_scope = document_scope(scoped_state, row['action'], version=focus_protocol)
                        else:
                            action_scope = None
                        break
                    except ValueError as error:
                        from .action_stability import ActionScopeError
                        failure_data = self._deltas(executed)
                        failure_data['action_precondition'] = (error.feedback() if isinstance(error, ActionScopeError) else
                            {'action': row['action'], 'control_id': cid, 'action_dispatched': False,
                             'dispatch_status': 'NOT_DISPATCHED', 'missing_requirements': [str(error)],
                             'recovery': 'observe_or_revise'})
                        self.event('action-scoped-evidence-failed', **failure_data['action_precondition'])
                        # A targeted probe for this exact state is already
                        # authoritative. Repeating it cannot repair editability,
                        # focus or value paint, and _observe would reject it.
                        has_current_probe = bool(cid and (control.get('probe') or {}).get('element_id') == cid)
                        if scope_refresh or has_current_probe:
                            return self._need_observation('act', '动作级局部证据不足：' + str(error),
                                                          data=failure_data)
                        refresh_key = (self._probe_key(self.current), row['action'], cid)
                        refreshed = getattr(self, '_scope_refresh_history', set())
                        if refresh_key in refreshed:
                            return self._need_observation('act', '同一观察下动作证据仍不足：' + str(error),
                                                          data=failure_data)
                        refreshed.add(refresh_key)
                        self._scope_refresh_history = refreshed
                        old_binding = dict(control['binding']) if cid else None
                        await self._observe(cid)
                        refreshed.add((self._probe_key(self.current), row['action'], cid))
                        if cid:
                            control = self.current['controls'].get(cid)
                            if control is None or control['binding'] != old_binding:
                                return self._need_observation('act', '刷新后目标绑定变化，请按新观察选择目标',
                                                              data=self._deltas(executed))
                            selector, index = control['binding'].get('selector'), control['binding'].get('index', 0)
                self.event('action-scoped-evidence', action=row['action'], target=cid,
                           scope_purpose=(action_scope or {}).get('purpose'), action_dispatched=False)
            try:
                observation = await capture_before_action(self.page, self.root, selector, index or 0,
                    include_html=self.native, timeout=max(.1,_deadline-time.monotonic()), **({'action_scope': action_scope} if action_scope else {}))
            except EvidenceStale as error:
                self.event('action-evidence-failed',error_type=type(error).__name__,
                    detail=str(error),timing=getattr(error,'action_refresh',None),
                    observation_id=self.current['observation_id'],target=cid,action_dispatched=False)
                self._consume('max_replans')
                return self._need_observation('act', '派发前页面状态过期；本次该原子动作零派发',
                                              data=self._deltas(executed))
            except Exception as error:
                self.event('action-evidence-failed',error_type=type(error).__name__,
                    detail=str(error),timing=getattr(error,'action_refresh',None),
                    observation_id=self.current['observation_id'],target=cid,action_dispatched=False)
                raise ReactStop('blocked', '派发前取证失败：' + type(error).__name__ + ': ' + str(error), 'program') from error
            self.event('action-evidence-ready',timing=observation.get('action_refresh'),
                       observation_id=self.current['observation_id'],target=cid)
            state = observation['state']
            if self.url_check:
                self.url_check(state['url'])
            drift_keys = ('url', 'document_identity', 'scroll', 'values', 'elements', 'visible_text') if self.native else ('url', 'document_identity', 'scroll')
            current_state = load_json(self.current['evidence']['state']['path'])
            from .dynamic_regions import enabled as dynamic_enabled,projection as content_projection
            current_content=content_projection(current_state,protect=[cid]);new_content=content_projection(state,protect=[cid])
            raw_drift=[key for key in drift_keys if current_state.get(key)!=state.get(key)]
            drift = [key for key in drift_keys if current_content.get(key)!=new_content.get(key)]
            if dynamic_enabled(current_state):
                self.event('dynamic-region-dispatch-drift',raw_changed_fields=raw_drift,related_changed_fields=drift,original_observation=self.current['evidence'])
            if action_scope or dynamic_enabled(current_state):
                from .browser import stability_pair
                proof = stability_pair(current_state, state,
                    Path(self.current['evidence']['image']['path']).read_bytes(), observation['png'], action_scope=action_scope)
                self.event('action-local-stability', proof=proof, before=self.current['evidence'],
                    capture=observation['capture'], action_dispatched=False)
                if proof['accepted']:
                    drift=[]
                    observation['action_scope']=action_scope
                else:
                    drift.append('first_focus_target_or_pixels')
            if cid:
                previous_labels = (current_state.get('target') or {}).get('visible_label_evidence', [])
                grouped = [label for label in previous_labels if label.get('kind') == 'rendered_grouped_button']
                if grouped and grouped != [label for label in (state.get('target') or {}).get('visible_label_evidence', [])
                                            if label.get('kind') == 'rendered_grouped_button']:
                    drift.append('grouped_button_label')
            if drift:
                self._consume('max_replans')
                data = self._deltas(executed)
                if self.native:
                    # It is already a verified full PNG/tree capture. Publish
                    # it as a new observation instead of trapping the model on
                    # the stale ID/probe. No action is sent on this branch.
                    self._consume('max_observations')
                    previous_controls=self.current['controls']
                    fresh = self._accept(observation, observation['html'], cid)
                    if cid and (fresh['controls'].get(cid, {}).get('probe') or {}).get('element_id') == cid:
                        self.focus_history.add((cid, self._probe_key(fresh)))
                    data.update(refreshed_observation_id=fresh['observation_id'],
                                drift_fields=drift, observation=self._compact(fresh))
                    # Recompile only an unchanged, uniquely identified physical target
                    # against this fresh full capture. No old evidence is dispatched.
                    refresh_cid=cid
                    if not refresh_cid and row['action']=='hotkey':
                        focused=[key for key,c in self.current['controls'].items() if (c.get('value') or {}).get('focused') is True]
                        if len(focused)==1:refresh_cid=focused[0]
                    old_control=previous_controls.get(refresh_cid) if refresh_cid else None
                    new_control=fresh['controls'].get(refresh_cid) if refresh_cid else None
                    if (_refresh<2 and time.monotonic()<_deadline and len(compiled)==1 and refresh_cid and set(drift)<= {'elements','visible_text'}
                            and old_control and new_control
                            and all(old_control.get(k)==new_control.get(k) for k in ('element','binding','value'))
                            and all(current_state.get(k)==state.get(k) for k in ('url','document_identity','scroll','values'))):
                        self.event('pre-dispatch-target-refresh',target=cid,refresh=_refresh+1,
                                   old_observation_state=current_state.get('document_identity'),
                                   new_observation_id=fresh['observation_id'],action_dispatched=False,drift_fields=drift)
                        return await self._dispatch_compiled(step,compiled,_refresh=_refresh+1,_deadline=_deadline)
                return self._need_observation(
                    'act', '页面在派发前发生变化（' + ','.join(drift) + '）；本次零派发，已保存当前取证，请基于新观察重新决策',
                    data=data)
            if self.native:
                self._consume('max_observations')
                self._accept(observation, observation['html'], cid)
            try:
                operation = self._build_operation(row, state, observation)
                arguments, element = prepare_action(state, operation)
                operation['arguments'] = arguments
            except ValueError as error:
                self._consume('max_replans')
                return self._rejected('act', '执行前校验拒绝：' + str(error), data=self._deltas(executed))
            before_action(self.task, prior_raws, operation['action_type'])
            self._consume('max_actions')
            stable = self.root / f'dispatch-frame-{self.used["max_actions"]:03}.png'
            with stable.open('xb') as stream:
                stream.write(observation['png'])
            dispatch = self.event('dispatch-intent', operation=operation, step_goal=step['goal'],
                formal_frame={'path': str(stable.resolve()), 'sha256': file_sha(stable)},
                decision_basis_observation=self.current['observation_id'],
                executed_so_far=[r['action'] for r in executed])
            result = await self._execute_primitive(step, row, operation, observation,
                                                   arguments, element, dispatch, executed, prior_raws)
            if result is not None:
                return result
        return self._ok('act', summary='复合动作完成，全部原子操作已执行',
                        data=self._deltas(executed, full=True),
                        evidence_refs=[r['dispatch']['path'] for r in self.trajectory[-len(executed):]])

    def _deltas(self, executed, full=False):
        data = {'actual_actions_delta': len(executed), 'effective_steps_delta': len(executed),
                'executed_primitives': [row['action'] for row in executed]}
        from .react_protocol import effect_feedback
        data['effects'] = [effect_feedback(row) for row in self.trajectory[-len(executed):]] if executed else []
        data['business_completion'] = 'NOT_CLAIMED'
        if full:
            data['observation'] = self._compact(self.current)
        return data

    async def _execute_primitive(self, step, row, operation, observation, arguments, element,
                                 dispatch, executed, prior_raws):
        if not self._v2():
            return await self._perform_primitive(step,row,operation,observation,arguments,element,dispatch,executed,prior_raws)
        self._awaiting_primitive_attempt=False
        number=len(getattr(self,'business_attempt_refs',[]))+1
        from .closing_policy import attempt_limit
        band=getattr(self.plan_controller,'frozen_band',None) if self.plan_controller else None
        limit=attempt_limit(self.task,band)
        reached = limit is not None and number>limit
        if reached:
            self._range_close('ACTION_BUDGET_LIMIT',f'已达本任务{limit}步上限，不再派发下一业务动作')
            return self._ok('act',summary=self.stop_summary,data={'collection_ending':self.collection_ending})
        self._active_business_attempt=number
        before_dispatch=self.actual_dispatches;before_effective=len(self.trajectory)
        result=None;failure=None
        try:
            result=await self._perform_primitive(step,row,operation,observation,arguments,element,dispatch,executed,prior_raws)
        except ReactStop as error:failure=error
        self._record_business_attempt({'action':operation['action_type'],'goal':step['goal'],'expected':step['expected']},
            number,before_dispatch,before_effective,result=result,failure=failure)
        if self.state!='recording':
            return self._ok('act',summary=self.stop_summary,data={'collection_ending':self.collection_ending})
        if failure:
            self._last_primitive_failure=failure
            self._runlog('action_failed', actionId=operation['operation_id'],
                action=operation['action_type'], reason=str(getattr(failure, 'args', failure))[:200],
                stopReason=getattr(failure, 'reason', None))
            raise failure
        return result

    async def _perform_primitive(self, step, row, operation, observation, arguments, element,
                                 dispatch, executed, prior_raws):
        """Dispatch exactly once. Returns a tool result, or None to continue the queue."""
        from .browser import EvidenceStale, execute, verify_execution_state
        from .collect import now
        state = observation['state']
        step_id = len(self.trajectory) + 1
        self._runlog('action_started', actionId=operation['operation_id'],
            action=operation['action_type'], observationId=self.current['observation_id'],
            stepId=step_id)
        raw = {'step_id': step_id, 'state': state, 'capture': observation['capture'],
               'operation': deepcopy(operation), 'target_element': deepcopy(element),
               'started_at': now(), 'executed_action': {'tool_name': operation['action_type'],
                                                        'arguments': deepcopy(arguments)},
               'controller_dispatch': dispatch,
               'react': {'decision_summary': self.last_decision_summary,
                         'before_observation_id': self.current['observation_id'],
                         'semantic_goal': step['goal'], 'semantic_expected': step['expected'],
                         **({'semantic_rationale':step['rationale'],'semantic_expected_result':step['expected_result']}
                            if 'rationale' in step else {}),
                         'primitive': row['action'], 'primitive_index': len(executed) + 1}}
        if operation['action_type'] == 'scroll' and operation.get('evidence', {}).get('scroll_container'):
            # The customer contract gives scroll a pointer, not a control label.
            # Keep the actual container in operation.evidence and the full state;
            # target_element remains the exported control-action ground truth.
            raw['target_element'] = None
        self.dialogs.clear()
        dispatch_started = False
        form_watcher = None
        http_watcher = None
        try:
            if observation.get('action_scope') and observation['action_scope']['action']!=operation['action_type']:
                raise EvidenceStale('局部证据动作类型改变；本动作零派发')
            remaining = min(REACT_OBSERVE_TIMEOUT_SECONDS,
                observation.get('action_deadline_monotonic', time.monotonic()+REACT_OBSERVE_TIMEOUT_SECONDS)-time.monotonic())
            if remaining <= 0:
                raise TimeoutError('派发前总取证期限已耗尽；本动作零派发')
            preflight_state = observation.get('action_state_preflight')
            if preflight_state is not None and (preflight_state.get('stability') or {}).get('action_scope') != observation.get('action_scope'):
                preflight_state = None
            if preflight_state is None:
                try:
                    preflight_state = await asyncio.wait_for(verify_execution_state(self.page, state,
                        operation.get('selector'), operation.get('index', 0), timeout=remaining,
                        **({'action_scope':observation['action_scope']} if observation.get('action_scope') else {})), timeout=remaining)
                except TimeoutError as error:
                    raise TimeoutError('派发前取证超时；本动作零派发') from error
            raw['state_preflight'] = {**preflight_state, 'phase': 'pre_dispatch'}
            if operation['action_type']=='drag':
                from .browser import verify_drag_destination
                await verify_drag_destination(self.page,operation['evidence']['drag_destination'],arguments)
            if self._left('max_seconds') <= 0:
                raise ReactStop('budget', '会话软截止已到；本动作零派发')
            pages_before = set(self.page.context.pages)
            from .candidate_navigation import exact_destination
            from .navigation import arm_http_navigation
            if exact_destination(state,operation):
                http_watcher = arm_http_navigation(self.page)
            from .plan_evidence import arm_native_form, finish_native_form
            form_watcher = await arm_native_form(self.page, operation, state)
            # Every awaited evidence operation may cross the session deadline.
            # Recheck immediately before the first browser action side effect.
            if self._left('max_seconds') <= 0:
                raise ReactStop('budget', '会话软截止已到；本动作零派发')
            if observation.get('action_deadline_monotonic', float('inf')) <= time.monotonic():
                raise TimeoutError('派发前总取证期限已耗尽；本动作零派发')
            dispatch_started = True
            self.actual_dispatches += 1
            try:
                popup_source = getattr(self, '_popup_sources', {}).get(self.page)
                if (operation['action_type'] == 'back' and popup_source is not None
                        and self.task['fragment'].get('plan_protocol') == PLAN_PROTOCOL):
                    raw['return_navigation'] = {'method': 'switch_to_opener',
                        'from_url': self.page.url, 'source_url': popup_source.url,
                        'popup_provenance': deepcopy(self._popup_provenances[self.page])}
                    await asyncio.wait_for(popup_source.bring_to_front(), timeout=20)
                    self.page = popup_source
                else:
                    if operation['action_type'] == 'back':
                        raw['return_navigation'] = {'method': 'go_back', 'from_url': self.page.url}
                    try:
                        await execute(self.page, operation['action_type'], arguments, {})
                    finally:
                        if form_watcher:
                            raw['native_form_submit'] = await asyncio.wait_for(
                                finish_native_form(self.page, form_watcher), timeout=2)
            except Exception as error:
                from playwright.async_api import TimeoutError as PlaywrightTimeout
                if operation['action_type'] != 'back' or not isinstance(error, PlaywrightTimeout):
                    raise
                # go_back exceeded its navigation wait after the dispatch. The
                # navigation may still have landed; re-observe this live page
                # instead of guessing an unknown effect. No second back is sent.
                raw['back_navigation_timeout'] = str(error)
                self.event('back-navigation-timeout', operation=operation,
                           error=str(error), dispatch=dispatch, re_dispatch=False)
                try:
                    await self.page.wait_for_load_state('domcontentloaded',
                        timeout=REACT_OBSERVE_TIMEOUT_SECONDS * 1000)
                except Exception:
                    pass  # the capture below classifies the observable state honestly
            if self.dialogs:
                raise ValueError('发生未记录的浏览器原生弹窗：' + str(self.dialogs))
            new_pages = set(self.page.context.pages) - pages_before
            if len(new_pages) > 1:
                raise ValueError('一次动作打开多个页面，需单独适配并记录')
            if new_pages:
                from .plan_evidence import verify_popup
                from .screenshot_execution import navigation_carrier
                opened = next(iter(new_pages))
                raw['popup_diagnostic'] = {'source_node': operation.get('evidence', {}).get('anchor_element_id'),
                    'link_carrier': navigation_carrier(state, operation.get('evidence', {}).get('anchor_element_id')),
                    'opened_url_before_verification': opened.url, 'landing_verified': False}
                try:
                    raw['popup_provenance'] = await verify_popup(self.page,opened,operation,state,
                        form_watcher=form_watcher,http_watcher=http_watcher)
                    raw['popup_diagnostic']['landing_verified'] = True
                finally:
                    raw['popup_diagnostic']['opened_url_after_verification'] = opened.url
                    if form_watcher and form_watcher.get('popup_proof'):
                        raw['popup_provenance'] = deepcopy(form_watcher['popup_proof'])
                if True:
                    if not hasattr(self, '_popup_sources'):
                        self._popup_sources = {}
                    self._popup_sources[next(iter(new_pages))] = self.page
                    if not hasattr(self, '_popup_provenances'):
                        self._popup_provenances = {}
                    self._popup_provenances[next(iter(new_pages))] = deepcopy(raw['popup_provenance'])
            elif new_pages and self.task['fragment'].get('decision_protocol') == NATIVE_VERSION:
                raw['opened_pages'] = [p.url for p in new_pages]
                raw.update(dispatched=True, action_executed=True, phase='post_dispatch',
                           execution_error='TOOL_CAPABILITY_UNAVAILABLE: tab switching/back is not supported in this protocol')
                self._write_raw(step_id, raw)
                raise ReactStop('blocked', raw['execution_error'], 'collector', capability_missing='tab_switch')
            if new_pages:
                self.page = next(iter(new_pages))
                await asyncio.wait_for(self.page.wait_for_load_state('domcontentloaded'), timeout=20)
                from .browser import record_native_dialog
                record_native_dialog(self.page, self.dialogs)
                raw['opened_page_url'] = self.page.url
            from .candidate_navigation import exact_destination
            expected_url = exact_destination(state, operation)
            if expected_url and self.page.url not in (state['url'], expected_url):
                from .navigation import finish_http_navigation
                raw['http_navigation'] = await finish_http_navigation(http_watcher,self.page,expected_url,
                    source_url=state['url'],operation_id=operation['operation_id'])
                if raw.get('popup_provenance'):
                    raw['popup_provenance']['http_navigation'] = deepcopy(raw['http_navigation'])
        except ReactStop as error:
            if not dispatch_started:
                raw.update(execution_error=str(error),phase='pre_dispatch',dispatched=False,action_executed=False)
                self._write_raw(step_id,raw)
            raise
        except EvidenceStale as error:
            # Proved pre-dispatch staleness: nothing was sent for this primitive.
            raw['execution_error'] = 'pre_dispatch EVIDENCE_STALE: ' + str(error)
            raw['phase'] = 'pre_dispatch'
            raw['dispatched'] = False
            raw['action_executed'] = False
            self._write_raw(step_id, raw)
            self._consume('max_replans')
            return self._need_observation('act', '派发前控件状态过期；本次该原子动作零派发',
                                          data=self._deltas(executed))
        except asyncio.CancelledError:
            raw.update(phase='dispatch' if dispatch_started else 'pre_dispatch',
                       dispatched=dispatch_started, action_executed=None if dispatch_started else False,
                       execution_error='cancelled')
            self._write_raw(step_id, raw)
            self.unknown = self.unknown or dispatch_started
            raise
        except BaseException as error:
            # After dispatch the real effect may be unknown; never auto-resend.
            if self._v2() and not dispatch_started:
                raw.update(execution_error=str(error),phase='pre_dispatch',dispatched=False,action_executed=False)
                self._write_raw(step_id,raw)
                raise ReactStop('blocked','派发前失败，零派发：'+str(error),'collector') from error
            raw['execution_error'] = str(error)
            raw['native_dialogs'] = deepcopy(self.dialogs)
            raw['phase'] = 'dispatch'
            raw['dispatched'] = True
            raw['action_executed'] = None
            self._write_raw(step_id, raw)
            self.event('execution-unknown', operation=operation, error=str(error), dispatch=dispatch)
            self.unknown = True
            raise ReactStop('blocked', '派发后结果未知（UNKNOWN），不自动补发：' + str(error),
                            'interrupted', unknown=True) from error
        finally:
            from .navigation import close_http_navigation
            close_http_navigation(http_watcher)
            if form_watcher:
                from .plan_evidence import close_native_form
                close_native_form(form_watcher)
                raw['native_form_requests'] = deepcopy(form_watcher['request_log'])
                self._write_raw(step_id, raw)
        raw['dispatched'] = True
        raw['action_executed'] = True
        raw['phase'] = 'post_dispatch'
        raw['ended_at'] = now()
        self._write_raw(step_id, raw)
        try:
            await self._after_action(step, row, operation, observation, arguments, dispatch, raw)
        finally:
            # The dispatch already happened; its record survives even when the
            # effect phase stops the whole session.
            self._write_raw(step_id, raw)
        prior_raws.append(raw)
        executed.append(row)
        return None

    async def _after_action(self, step, row, operation, dispatch_observation, arguments, dispatch, raw):
        """Real post-dispatch effect capture; trajectory and scope grow here."""
        from .batch_core import file_sha as _sha
        before_state = dispatch_observation['state']
        before_id = self.current['observation_id']
        before_image = self.current['evidence']['image']
        self._pending_navigation = None
        if self.task['fragment'].get('delayed_navigation_protocol') == DELAYED_NAVIGATION_PROTOCOL:
            self._pending_navigation = {'operation':deepcopy(raw['operation']), 'source':deepcopy(before_state),
                'source_observation_id':before_id, 'page':self.page, 'pages':tuple(getattr(getattr(self.page,'context',None),'pages',[self.page])),
                'dispatches':self.actual_dispatches}
        self._navigation_trigger = raw['operation']
        self._navigation_source = before_state
        self._navigation_proof = raw.get('popup_provenance') or raw.get('http_navigation')
        try:
            await self._observe()
        finally:
            self._navigation_trigger = None
            self._navigation_source = None
        controller=self.plan_controller
        if controller is not None and controller.plan and controller.position<len(controller.plan['steps']):
            from .banded_plan import proves
            expected=controller.plan['steps'][controller.position]['expected']
            anchor=operation.get('evidence',{}).get('anchor_element_id') or operation.get('evidence',{}).get('focused_element_id')
            # Await the semantic result on this already dispatched operation.
            # Every interim original capture remains archived; no action or
            # model request is repeated, and the final raw after-frame is the
            # observed result used by ordinary effect verification below.
            for refresh in range(2):
                if proves(expected,self.current,before_state,anchor,numeric=True):break
                if self._left('max_observations')<=RESERVE['max_observations'] or self._left('max_seconds')<=.1:break
                self.event('plan-result-wait',operation_id=operation['operation_id'],expected=expected,
                    previous_observation_id=self.current['observation_id'],refresh=refresh+1,wait_ms=100,dispatched_again=False)
                await asyncio.sleep(.1)
                self._navigation_trigger=raw['operation']
                self._navigation_source=before_state
                try:await self._observe()
                finally:
                    self._navigation_trigger=None
                    self._navigation_source=None
        after = self.current
        if after['url'] != before_state['url']:
            self._pending_navigation = None
        after_state = load_json(after['evidence']['state']['path'])
        if 'expected_value' in step:
            from .screenshot_effect import step_expectation
            expectation = step_expectation(step, after_state,
                operation.get('evidence', {}).get('anchor_element_id') or operation.get('evidence', {}).get('focused_element_id'))
            raw['react']['step_expectation'] = expectation
            raw['react']['expected_value'] = step['expected_value']
        effect = self._atomic_effect(before_state, after_state, operation['action_type'], arguments,
                               operation.get('evidence', {}).get('anchor_element_id') or
                               operation.get('evidence', {}).get('focused_element_id'),
                               rule_version=self.task['fragment'].get('effective_action_rule', RULE_VERSION))
        from .direct_article import enabled as direct_article, session_trace, transition
        if direct_article(self.task):
            try:
                proof=session_trace(self)
                transition(self.task,before_state,after_state,operation['action_type'],arguments,operation.get('evidence',{}).get('anchor_element_id'),pending=proof['pending_return'])
            except ValueError as error:
                raw['react']['after_observation_id']=after['observation_id']
                raise ReactStop('blocked',str(error),'collector',operation=operation['operation_id']) from error
        keys = ('url', 'document_identity', 'scroll', 'scroll_containers', 'values', 'visible_text', 'elements')
        from .dynamic_regions import projection as content_projection
        raw_changed_fields=[key for key in keys if before_state.get(key)!=after_state.get(key)]
        old_content,new_content=content_projection(before_state),content_projection(after_state)
        changed_fields = [key for key in keys if old_content.get(key) != new_content.get(key)]
        png_changed = _sha(Path(after['evidence']['image']['path'])) != before_image['sha256']
        changed = bool(changed_fields) or png_changed
        zero_scroll = operation['action_type'] == 'scroll' and (
            not effect['verified'] if operation.get('evidence', {}).get('scroll_container')
            else before_state.get('scroll') == after_state.get('scroll'))
        if ((self.plan_controller is not None
                or __import__('webcollect.collection_strategy',fromlist=['enabled']).enabled(self.task))
                and (not effect['verified'] or zero_scroll or not changed)):
            # Bind the observed no-effect frame first; the classification stays
            # definite whether or not the session continues. A known zero-effect
            # action stays the model's decision: the pending-effect branch offers
            # replan/original/stop. Zero effective steps, dispatch retained.
            # 策略 2 shares this: a submit whose result is not yet visible is a
            # business checkpoint (observe/scroll), never a hard session stop.
            raw['react'].update(after_observation_id=after['observation_id'], effect_evidence=effect,
                                zero_effect=True)
            self.event('action-zero-effect', operation=operation['operation_id'],
                       action=operation['action_type'], effect_evidence=effect,
                       after_observation_id=after['observation_id'], session_continues=True)
            return
        if self.native and not effect['verified']:
            raw['react'].update(after_observation_id=after['observation_id'], effect_evidence=effect)
            raise ReactStop('blocked', 'NO_EFFECTIVE_ACTION: 动作缺少对应的可核验效果', 'collector',
                            operation=operation['operation_id'])
        if zero_scroll:
            raise ReactStop('blocked', 'NO_EFFECTIVE_ACTION: 滚动未移动当前视口', 'collector',
                            operation=operation['operation_id'])
        if not changed:
            raise ReactStop('blocked', 'NO_EFFECTIVE_ACTION: 已执行动作未产生可观察变化', 'collector',
                            operation=operation['operation_id'])
        # Keep the authorized page scope explicit; new URLs must be earned by
        # an actual navigation from this session. Both branches share the
        # candidate_navigation permission entry (E: 统一导航许可).
        if after['url'] not in self.page_urls:
            if 'candidate_binding' in self.task:
                from .candidate_navigation import extend
                try:
                    extend(self.task, self.page_urls, after_state, raw['operation'],
                           source=before_state, proof=raw.get('popup_provenance') or raw.get('http_navigation'))
                except ValueError as error:
                    raise ReactStop('no_path', str(error), 'collector',
                                    operation=operation['operation_id']) from error
            else:
                from .candidate_navigation import admit_landing
                landing = admit_landing(self.task, self.page_urls, after['url'], raw['operation'],
                                        source=before_state, proof=raw.get('popup_provenance') or raw.get('http_navigation'))
                if landing == 'out_of_scope':
                    raise ReactStop('no_path', '页面离开授权站点范围：' + after['url'], 'collector',
                                    operation=operation['operation_id'])
                if landing == 'capacity':
                    raise ReactStop('blocked', '页面范围数量达到上限', 'collector')
        cid = operation.get('evidence', {}).get('anchor_element_id')
        control = after['controls'].get(cid) if cid else None
        observed = {'state_changed': changed, 'changed_fields': changed_fields,'raw_changed_fields':raw_changed_fields,
            'target_after': ({k: (control['value'] or {}).get(k)
                              for k in ('value', 'checked', 'focused')} if control else None),
            'observation': deepcopy(after['evidence']['image'])}
        if self.task['fragment'].get('reference_protocol') == REFERENCE_PROTOCOL:
            from .react_protocol import content_effect, control_state_transition
            observed['target_owner_transition'] = control_state_transition(before_state, after_state, cid)
            ids = content_effect(before_state, after_state, cid) if 'visible_content' in effect['fields'] else []
            observed['visible_result_changes'] = [{'element_id':e['element_id'], 'text':e.get('text','')[:200]}
                for e in after_state.get('elements', []) if e['element_id'] in ids][:8]
        raw['react']['after_observation_id'] = after['observation_id']
        raw['react']['observed'] = observed
        raw['react']['effect_evidence'] = effect
        raw['postconditions_checked'] = True
        row_record = {'operation_id': operation['operation_id'], 'action': operation['action_type'],
            'arguments': deepcopy(arguments), 'goal': operation['goal'], 'expected': operation['expected'],
            'target': ({'control_id': cid, 'label': operation['evidence'].get('target_label'),
                        'selector': operation.get('selector')} if cid else None),
            'before_observation_id': before_id, 'after_observation_id': after['observation_id'],
            'dispatch': {'path': dispatch['path'], 'sha256': dispatch['sha256']},
            'effective': True, 'effect_evidence': effect, 'observed_changed': changed, 'changed_fields': changed_fields,
            'observed': observed,
            'semantic_goal': step['goal'], 'semantic_expected': step['expected'],
                         **({'semantic_rationale':step['rationale'],'semantic_expected_result':step['expected_result']}
                            if 'rationale' in step else {}),
            'primitive': row['action'],
            **({'expected_value': step['expected_value'], 'step_expectation': raw['react']['step_expectation']}
               if 'expected_value' in step else {})}
        if raw.get('return_navigation'):
            row_record['return_navigation'] = deepcopy(raw['return_navigation'])
        if self.task['fragment'].get('reading_progress_protocol') and len(self.trajectory) >= 2:
            from .reading_progress import same_view, control_return
            first,last=self.trajectory[-2:]
            origin=load_json(self.observation_records[first['before_observation_id']]['evidence']['state']['path'])
            middle=load_json(self.observation_records[first['after_observation_id']]['evidence']['state']['path'])
            returned=load_json(self.observation_records[last['after_observation_id']]['evidence']['state']['path'])
            if same_view(origin,returned) and first['action']==last['action']=='scroll':
                if control_return(origin,middle,returned,raw['operation']):
                    self.event('reading-control-return', restored_observation_id=last['after_observation_id'],
                               next_operation_id=operation['operation_id'],target=cid)
        if self.steps_directory is not None:
            self._write_raw(len(self.trajectory) + 1, raw)
            row_record['raw_step'] = {'path': str(self._action_raw_path(len(self.trajectory)+1).resolve()),
                                      'sha256': file_sha(self._action_raw_path(len(self.trajectory)+1))}
        self.append_trajectory(row_record)
        self._runlog('action_finished', actionId=operation['operation_id'],
            action=operation['action_type'], outcome='verified',
            observationId=after['observation_id'], effectiveSteps=len(self.trajectory))
        if self.task['fragment'].get('reading_progress_protocol') and len(self.trajectory) >= 2:
            from .reading_progress import same_view
            prior = self.trajectory[-2]
            origin = load_json(self.observation_records[prior['before_observation_id']]['evidence']['state']['path'])
            from .consumer_page_policy import enabled as page_policy, returned_pair
            boundary_return=page_policy(self.task) and returned_pair(origin,before_state,after_state,prior,row_record)
            if (same_view(origin, after_state) and not (
                    row_record['action'] == 'back' and prior['action'] in ('click','double_click','open_url','hotkey','type','select')
                    and before_state['url'] != after_state['url']) and not boundary_return):
                # Keep a pending return until the next actual control action
                # proves why this viewport was restored. Finish alone cannot
                # waive it; sealed postprocessing validates the whole sequence.
                self.event('reading-return-pending', reason='两步回到同一原始状态；须由下一真实控件动作证明用途，不能凑步或凭摘要放行')
        self.event('action-effect', operation=operation['operation_id'],
                   before_observation_id=before_id, after_observation_id=after['observation_id'],
                   changed_fields=changed_fields)

    def _write_raw(self, step_id, raw):
        """Append-only live record; the effect phase enriches the same row
        atomically before any receipt references it."""
        if self.steps_directory is None:
            return
        from .collect import checkpoint_json
        path=self._action_raw_path(step_id)
        path.parent.mkdir(parents=True,exist_ok=True)
        checkpoint_json(path, raw)

    def _check_request_budget(self):
        reader = getattr(self.choose, 'session_usage', None)
        if reader is not None:
            usage = reader()
            if self.glm_session_id:
                self.glm_http_requests = usage['used']
            if self.native:
                self.used['max_model_calls'] = usage['used']
            if usage['unresolved']:
                raise ReactStop('blocked', '原尝试请求待核实，保留 UNKNOWN 不重发：' + usage['unresolved'],
                                'interrupted', unknown=True)
        else:
            counter = getattr(self.choose, 'requests_used', None)
            if counter is not None:
                self.used['max_model_calls'] = counter()
            guard = getattr(self.choose, 'guard_unresolved', None)
            if guard is not None:
                try:
                    guard()
                except OutcomeUnknown as error:
                    raise ReactStop('blocked', str(error), 'interrupted', unknown=True) from error
        if self.native and self._left('max_model_calls') <= 0:
            raise ReactStop('budget', '实际请求预算耗尽')

    async def _open_entry(self):
        if self.entry_observation is not None:
            entry = self.entry_observation
            self.entry_observation = None
            if self.url_check:
                self.url_check(self.page.url)
            captured, html = entry['captured'], entry['html']
            # Same Page: validate the supplied synchronization receipt before
            # accepting it. A changed/invalid entry is refreshed, never navigated.
            from .browser import validate_capture_receipt, verify_execution_state
            try:
                validate_capture_receipt(captured['state'], captured['capture'], captured['png'])
                if captured['state']['url'] != self.page.url:
                    raise ValueError('Entry observation URL changed')
            except Exception:
                await self._observe()
            else:
                self._consume('max_observations')
                self._accept(captured, html)
            await self._run_preflight()
            return
        try:
            if self.navigation is not None:
                await self.navigation.goto(self.page, self.task['initial_url'],
                                           purpose='react-entry:' + self.task['task_id'])
            else:
                await self.page.goto(self.task['initial_url'], wait_until='domcontentloaded', timeout=30000)
            await self.page.wait_for_timeout(1000)
        except ReactStop:
            raise
        except Exception as error:
            raise ReactStop('blocked', '入口导航失败：' + str(error), 'network') from error
        if self.url_check:
            self.url_check(self.page.url)
        await self._observe()
        await self._run_preflight()

    async def _run_preflight(self):
        from .plan_protocol import ACTION_STABILITY_PROTOCOL
        if self.task['fragment'].get('action_stability_protocol') == ACTION_STABILITY_PROTOCOL:
            self.event('preflight-reused-action-evidence', independent_probe_dispatched=False)
            return
        # Tasks without action-scoped evidence have no independent preflight
        # probe anymore; the ordinary observation pipeline governs them.
        self.event('preflight-skipped-no-action-scoped-evidence')

    def _close(self):
        if getattr(self, '_raw_receipt', None) is not None:
            return self._raw_receipt
        if self.state == 'recording':
            self.state = 'closed_by_host'
        from .postprocess import flow_classification
        self.short_flow, self.short_flow_reason = flow_classification(len(self.trajectory))
        if self._v2() and not getattr(self,'collection_ending',None):
            original_stop=self.stop_reason
            from .closing_policy import attempt_limit, no_effect_proven
            band=getattr(self.plan_controller,'frozen_band',None) if self.plan_controller else None
            limit=attempt_limit(self.task,band)
            counted=len(getattr(self,'business_attempt_refs',[]))
            budget_prefix=(limit is not None and original_stop=='budget' and not self.unknown and not getattr(self,'host_failure',False)
                           and 5<=counted<=limit and bool(self.trajectory))
            # Every dispatch accounted for by a definite attempt outcome keeps
            # the closeout definite: a known zero-effect tail never turns the
            # whole range into an effect UNKNOWN by closure default.
            refs=getattr(self,'business_attempt_refs',[])
            definite_tail=(not self.unknown and bool(refs)
                and sum(load_json(r['path'])['actual_dispatches_delta'] for r in refs)==self.actual_dispatches
                and all(load_json(r['path'])['outcome']!='EFFECT_UNKNOWN' for r in refs))
            if definite_tail:
                raws=[load_json(raw_ref['path']) for ref in refs
                      for raw_ref in load_json(ref['path']).get('raw_steps',[])]
                dispatched=[raw for raw in raws if raw.get('dispatched') is True]
                omitted=[raw for raw in dispatched if not (raw.get('action_executed') is True
                    and raw.get('postconditions_checked') is True
                    and raw.get('react',{}).get('effect_evidence',{}).get('verified') is True)]
                definite_tail=(len(dispatched)==self.actual_dispatches
                    and len(omitted)==self.actual_dispatches-len(self.trajectory)
                    and all(no_effect_proven(raw,self.observation_records) for raw in omitted))
            self._range_close('MODEL_BUDGET_LIMIT' if budget_prefix else 'HOST_INTERRUPTED' if definite_tail else 'RAW_PENDING',
                              self.stop_summary or '未获得可保存的可信结束依据',unknown=self.unknown,
                              force_pending=not (budget_prefix or definite_tail))
            self.stop_reason=original_stop
        terminal = {'protocol': REACT_VERSION, 'state': self.state, 'stop_reason': self.stop_reason,
            **({'completed_at': self.completed_at} if getattr(self, 'completed_at', None) else {}),
            **({'collection_ending':self.collection_ending} if self._v2() else {}),
            'host_failure':getattr(self,'host_failure',False),
            **({'glm_http_requests':self.glm_http_requests} if self.glm_http_requests is not None else {}),
            **({'stop_details': self.stop_details} if self.stop_details else {}),
            'stop_summary': self.stop_summary, 'short_flow': self.short_flow,
            'short_flow_reason': self.short_flow_reason, 'unknown': self.unknown,
            'page_hosts': {o['observation_id']: urlsplit(o['url']).hostname
                           for o in self.observation_records.values()},
            'failure_class': self.failure_class, 'effective_steps': len(self.trajectory),
            'actual_actions': self.actual_dispatches, 'observations': list(self.observations),
            'final_observation_id': self.observations[-1] if self.observations else None,
            'trajectory': [row['operation_id'] for row in self.trajectory],
            'goal_updates': self.goal_updates, 'working_goal': self.working_goal,
            **({'goal_evidence':(self.plan_controller.fact_progress(self) if self.plan_controller
                                 else deepcopy(getattr(self,'goal_evidence',None)))}
               if (self.plan_controller or getattr(self,'goal_evidence',None)) else {}),
            'delayed_navigations': getattr(self,'delayed_navigations',[]),
            'planning_intents': getattr(self,'planning_intents',[]),
            'used': {k: self.used[k] for k in BUDGET_KEYS},
            'elapsed_seconds': time.monotonic() - self.started}
        terminal_ref = exclusive(self.root / 'terminal.json', terminal)
        files = _raw_files(self.root)
        receipt = exclusive(self.root / 'raw-receipt.json',
            {'protocol': REACT_VERSION, 'terminal': terminal_ref,
             'files_sha256': {name: files[name] for name in files
                              if name not in ('raw-receipt.json',)},
             'file_count': len(files), 'boundary': self.binding, 'raw_saved': True,
             'not_a_delivery_sample': True, 'qc_pass': False})
        self._raw_receipt = receipt
        return receipt

    # ------------------------------------------------------------------ records for postprocess

    def record(self):
        return {'protocol': REACT_VERSION, 'task': self.task, 'root': str(self.root),
                'observations': {key: {'evidence': self.observation_records[key]['evidence'],
                                       'html_ref': self.observation_records[key]['html_ref'],
                                       'state_path': self.observation_records[key]['evidence']['state']['path'],
                                       'image_path': self.observation_records[key]['evidence']['image']['path'],
                                       'url': self.observation_records[key]['url']}
                                 for key in self.observations},
                'trajectory': deepcopy(self.trajectory), 'goal_updates': deepcopy(self.goal_updates),
                **({'stop_details': self.stop_details} if self.stop_details else {}),
                'stop_reason': self.stop_reason, 'stop_summary': self.stop_summary,
                'short_flow': self.short_flow, 'short_flow_reason': self.short_flow_reason,
                'unknown': self.unknown, 'failure_class': self.failure_class}
