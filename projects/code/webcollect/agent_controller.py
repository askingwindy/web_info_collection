"""Bounded fragment controller on the ordinary collector and model ledger.

The frozen goal is immutable; decisions and dispatch/result companions are new
exclusive files. Interrupted controllers cannot replay or splice a trajectory.

Controller protocol v2: target-semantic consistency between decision and
dispatch, no redundant recapture after a supplemental observation, an in-prompt
current-trajectory memory, and stage-classified decision request failures.
"""
from copy import deepcopy
import json
from pathlib import Path
from .planning import object_sha256, verify_evidence
from .batch_core import file_sha, load_json, OutcomeUnknown
from .agent_observation import project, action_availability, readable_labels, PROVEN, VERSION as OBS_VERSION, ACTIONS

VERSION = 'webcollect-fragment-controller-2'
FRAGMENT_VERSION = 'webcollect-fragment-workflow-2'
# Worst honest cost per dispatched action: 3 observations (fresh-decision
# capture, supplemental target capture, pre-dispatch rebind) and, when the
# model asks observe-then-plan, 2 decisions/model calls. Eight actions plus
# the finish decision then need 25 observations and 17 decisions/calls, so
# the caps must cover that plus bounded replan headroom.
LIMITS = {'max_actions': 8, 'max_observations': 32, 'max_decisions': 24, 'max_replans': 8, 'max_model_calls': 20}
from .semantic_workflow import obj, TEXT, TASK_SCHEMA as SEMANTIC_SCHEMA
from .fragment_workflow import STEP
TASK_SCHEMA = obj({'schema_version': {'const': FRAGMENT_VERSION}, 'task_family': TEXT,
    'instruction': TEXT, 'task_type': SEMANTIC_SCHEMA['properties']['task_type'],
    'page_id': TEXT, 'end_description': TEXT,
    'allowed_actions': {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': {'enum': sorted(ACTIONS)}},
    'budgets': obj({k: {'type': 'integer', 'minimum': 1, 'maximum': v} for k, v in LIMITS.items()})})
SCHEMA = obj({'tasks': {'type': 'array', 'maxItems': 5, 'items': TASK_SCHEMA},
    'empty_reasons': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {
            'category': {'enum': ['NO_FEASIBLE_PATH', 'MISSING_OBSERVATION', 'ENGINEERING_ERROR', 'UNRESOLVED_REQUEST']},
            'reason': TEXT, 'control_ids': {'type': 'array', 'items': TEXT}},
        'required': ['category', 'reason', 'control_ids'],
        # Models annotate their empty reasons (e.g. control_ids_note); keep the
        # semantic fields strict, accept extra string annotations verbatim.
        'additionalProperties': {'type': 'string'}}}})
DECISION_STEP = deepcopy(STEP)
DECISION_STEP['allOf'] = [
    {'if': {'properties': {'action': {'enum': actions}}}, 'then': {'required': required}}
    for actions, required in [
        (['set_value', 'type', 'select'], ['control_id', 'value']),
        (['click', 'double_click', 'right_click'], ['control_id']),
        (['scroll'], ['direction']), (['hotkey'], ['keys']), (['open_url'], ['page_id'])]]
DECISION_SCHEMA = obj({'kind': {'enum': ['plan', 'observe', 'finish', 'no_path']},
    'observation_id': TEXT, 'reason': TEXT,
    'steps': {'type': 'array', 'maxItems': 1, 'items': DECISION_STEP}, 'control_id': {'type': 'string'}})


def is_controlled(task):
    return task.get('fragment', {}).get('schema_version') == FRAGMENT_VERSION


def exclusive(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush()
        import os
        os.fsync(stream.fileno())
    return {'path': str(path.resolve()), 'sha256': file_sha(path)}


def validate_task(task):
    from jsonschema import Draft202012Validator
    spec = task['workflow_proposal']['spec']
    Draft202012Validator(TASK_SCHEMA).validate(spec)
    if (task['fragment'].get('controller_version') != VERSION or task['operations'] != []
            or task['required_actions'] != [] or task['final_assertions'] != []
            or task.get('stop_when_final') is not False or task.get('content_preparation') is not False
            or spec['budgets']['max_actions'] < 5 or task['fragment']['budgets'] != spec['budgets']):
        raise ValueError('Invalid immutable dynamic fragment boundary')
    if (not task.get('task_version') or task['fragment']['allowed_actions'] != spec['allowed_actions']
            or any(k in task for k in ('task_admission','workflow_admission'))):
        raise ValueError('Controller cannot replace a legacy admission or change frozen action range')
    if 'candidate_binding' in task:
        from .candidate_contract import validate_task_binding
        validate_task_binding(task)
    verify_evidence(task['workflow_proposal']['evidence'])
    return task


def compile_goal(capability, spec, version):
    from jsonschema import Draft202012Validator
    from .semantic_workflow import observation
    Draft202012Validator(TASK_SCHEMA).validate(spec)
    anchors, states, _ = observation(capability, allow_empty=True)
    pages = {f'p{i}': state for i, state in enumerate(states)}
    if spec['page_id'] not in pages or spec['task_family'] not in capability['task_families']:
        raise ValueError('Goal requires an observed starting page and family')
    if not (set(spec['allowed_actions']) - {'set_value'}) <= set(capability['supported_actions']):
        raise ValueError('Goal action range exceeds observed executor capability')
    if 'set_value' in spec['allowed_actions'] and not {'click','type','hotkey'} <= set(capability['supported_actions']):
        raise ValueError('set_value requires all native replacement primitives')
    start = pages[spec['page_id']]
    task = {'task_id': 'controlled-' + object_sha256({'capability': capability['capability_id'], 'spec': spec, 'anchors': anchors})[:24],
        'task_version': version, 'capability_id': capability['capability_id'], 'capability_version': capability['version'],
        'site_uri': capability['site_uri'], 'site_category': capability['site_category'], 'task_family': spec['task_family'],
        'initial_url': start['url'], 'app_name': capability['capabilities'][int(spec['page_id'][1:])]['title'], 'instruction': spec['instruction'], 'task_type': spec['task_type'],
        'operations': [], 'required_actions': [], 'subgoals': [], 'final_assertions': [],
        'final_result': spec['end_description'], 'completion_judgement': spec['end_description'],
        'stop_when_final': False, 'content_preparation': False,
        'fragment': {'schema_version': FRAGMENT_VERSION, 'controller_version': VERSION,
            'policy_version': 'legal-web-actions-fragment-1', 'business_completion': 'NOT_CLAIMED',
            'quality_policy_version': 'qc-sampling-v1-20261030', 'budgets': deepcopy(spec['budgets']),
            'allowed_actions': deepcopy(spec['allowed_actions']), 'page_urls': [s['url'] for s in states],
            'start_state_sha256': object_sha256({k: start.get(k) for k in ('url','visible_text','scroll','values')}),
            'operation_template': 'dynamic-bounded-fragment'},
        'workflow_proposal': {'schema_version': FRAGMENT_VERSION, 'spec': deepcopy(spec),
            'evidence': [a[k] for a in anchors for k in sorted(a)], 'semantic_status': 'REVIEW_REQUIRED'}}
    if 'candidate_observation' in capability:
        from .candidate_contract import validate_observation, validate_task_binding, fragment_ending
        task['candidate_binding'] = deepcopy(validate_observation(capability))
        if spec['end_description']!=fragment_ending(task['candidate_binding']['candidate']):
            raise ValueError('Candidate ending must preserve the original claimed goal without extra business requirements')
        task['fragment']['ending_policy']='candidate-fragment-ending-1'
        task['fragment']['navigation_protocol'] = 'candidate-observed-navigation-1'
        task['fragment']['candidate_attempt'] = task['candidate_binding']['claim_id']
        validate_task_binding(task, capability)
    from .task_instruction import validate_task_instruction
    validate_task_instruction(task['instruction']); validate_task(task)
    return task


class ControllerStop(ValueError):
    failure_class = 'content'
    responsibility = 'collector'


class DecisionRequestError(ValueError):
    """Definite decision-request failure; no UNKNOWN hold and no resend.

    stage 'local_preflight' proves zero reserved requests (nothing was sent,
    nothing was charged); stage 'definite_model_response' means the request
    was settled with an actual definite outcome before failing.
    """
    stage = 'local_preflight'


class DecisionModelFault(DecisionRequestError):
    stage = 'definite_model_response'


def target_projection(observation, control_id):
    """Action-relevant identity of one control: binding, role, labels, state.

    Labels carry the readable meaning the decision was made against; the value
    state (value/checked/focus/selection) is what the decided action changes.
    """
    if not control_id or observation is None:
        return None
    control = observation['controls'].get(control_id)
    if control is None:
        return None
    value = control['value'] or {}
    return {'binding': {k: control['binding'].get(k) for k in ('selector', 'index', 'tag', 'href')},
            'element': {k: control['element'].get(k) for k in ('element_type', 'inputable', 'clickable')},
            'input_type': value.get('input_type'),
            'labels': sorted((row['kind'], row['text']) for row in control['readable_labels']),
            'value_state': {k: value.get(k) for k in ('value', 'checked', 'focused', 'selection_start', 'selection_end')}}


def projection_change(before, after):
    """Semantic identity drift a fresh capture can reveal; None means stable.

    Structural changes (selector/role) and label changes never pass silently.
    A placeholder<->value label swap is only meaningful together with a value
    change and is therefore classified by the caller with that evidence.
    """
    if before is None and after is None:
        return None
    if before is None or after is None:
        return 'TARGET_MISSING'
    for key in ('binding', 'element', 'input_type'):
        if before[key] != after[key]:
            return 'STRUCTURAL'
    if before['labels'] != after['labels']:
        return 'LABEL_MEANING'
    return None


def _input_driven_labels(before, after):
    native = {'visible_native_value', 'visible_placeholder'}
    stable = lambda value: [row for row in value['labels'] if row[0] not in native]
    return (stable(before) == stable(after)
            and before['value_state'] != after['value_state'])


class FragmentController:
    def __init__(self, task, directory, choose, *, frame_guard=None, site_context=None):
        validate_task(task)
        self.task = deepcopy(task); self.root = Path(directory); self.root.mkdir(parents=True, exist_ok=True)
        self.choose = choose; self.frame_guard = frame_guard; self.context = deepcopy(site_context or {})
        self.used = dict.fromkeys(LIMITS, 0); self.queue = []; self.feedback = []; self.state = 'running'
        self.sequence = 0; self.pending = None; self.last_control = None
        self.needs_observation = True; self.trajectory = []
        self.navigation_count = 0
        self.queue_targets = []; self.queue_compiled_at = 0
        self.page_urls = list(task['fragment']['page_urls'])
        # Existing journal (even just an intent) is unresolved, never replayed.
        self.binding = exclusive(self.root/'boundary.json', {'protocol': VERSION, 'task': task})

    def event(self, kind, **payload):
        self.sequence += 1
        return exclusive(self.root/f'{self.sequence:04}-{kind}.json', {'kind': kind, 'protocol': VERSION,
            'boundary': self.binding, 'used': dict(self.used), **payload})

    def stop(self, category, reason, **details):
        if self.state == 'running':
            self.state = category
            self.event('terminal', category=category, reason=reason, **details)
        error = ControllerStop(category + ': ' + reason)
        error.category = category
        raise error

    def consume(self, key):
        if self.used[key] >= self.task['fragment']['budgets'][key]:
            self.stop('BUDGET_EXHAUSTED', key)
        self.used[key] += 1

    def _left(self, key):
        return self.task['fragment']['budgets'][key] - self.used[key]

    def reserve_dispatch(self):
        """Dispatching needs its rebind capture plus a later finish cycle."""
        for key, need in (('max_observations', 2), ('max_decisions', 1), ('max_model_calls', 1)):
            if self._left(key) < need:
                self.stop('BUDGET_EXHAUSTED', key + ' (completion headroom before dispatch)')

    async def observe(self, page, control_id=None):
        from .browser import capture
        self.consume('max_observations')
        # Resolve only from the last saved observation; IDs alone never cross a document.
        binding = None
        if control_id:
            binding = self.current['controls'].get(control_id, {}).get('binding') if hasattr(self, 'current') else None
            if not binding:
                self.stop('MISSING_OBSERVATION', 'Unknown supplemental control', control_id=control_id)
        captured = await capture(page, (binding or {}).get('selector'), (binding or {}).get('index', 0),
            assertions=getattr(self, 'assertions', None) or None)
        return self.accept_capture(captured)

    def accept_capture(self, captured):
        effect_operation = self.pending_effect[1] if getattr(self, 'pending_effect', None) else None
        n = self.used['max_observations']; stem = self.root/f'observation-{n:03}'
        with stem.with_suffix('.png').open('xb') as stream:
            stream.write(captured['png'])
        evidence = {'image': {'path': str(stem.with_suffix('.png').resolve()), 'sha256': file_sha(stem.with_suffix('.png'))},
            'state': exclusive(stem.with_suffix('.json'), captured['state']),
            'capture': exclusive(stem.with_suffix('.capture.json'), captured['capture'])}
        current = project(captured['state'], evidence)
        if not current['capture_verified']:
            self.stop('MISSING_OBSERVATION', 'Synchronized capture proof is missing', observation=current)
        if not current['document_identity']:
            self.stop('MISSING_OBSERVATION', 'Document identity is missing', observation=current)
        self.current = current; self.captured = captured
        previous = getattr(self, '_previous_identity', None)
        identity = (current['url'], current['document_identity'])
        if previous is not None and previous != identity:
            self.navigation_count += 1
        self._previous_identity = identity
        if getattr(self, 'pending_effect', None):
            before, operation = self.pending_effect
            after = captured['state']
            keys = ('url','document_identity','scroll','values','visible_text','elements')
            changed = any(before.get(k) != after.get(k) for k in keys)
            if not changed and object_sha256(captured['png'].hex()) == self.effect_png:
                self.stop('NO_EFFECTIVE_ACTION', 'Executed action produced no observed change', operation=operation, observation=current)
            if operation['action_type'] == 'scroll' and before.get('scroll') == after.get('scroll'):
                self.stop('NO_EFFECTIVE_ACTION', 'Scroll did not move current viewport', operation=operation, observation=current)
            self.event('action-effect', operation=operation, observation=current, changed=changed)
            self.pending_effect = None
            self._record_observed_effect(operation, before, after, keys, changed, current)
        if 'candidate_binding' in self.task:
            from .candidate_navigation import extend
            try:
                extend(self.task, self.page_urls, captured['state'], effect_operation)
            except ValueError as error:
                self.stop('MISSING_OBSERVATION', str(error), observation=current)
        if current['url'] not in self.page_urls:
            self.stop('NO_FEASIBLE_PATH', 'Page is outside frozen source scope', observation=current)
        if self.frame_guard:
            conflicts = self.frame_guard(current['evidence']['image'])
            if conflicts:
                self.stop('DUPLICATE', 'Known screenshot conflict', conflicts=conflicts, observation=current)
        return current

    def _record_observed_effect(self, operation, before, after, keys, changed, current):
        """Attach the actually observed result to this trajectory entry.

        'expected' is the decision's claim; 'observed' is only what the fresh
        capture proved. Unresolved entries keep observed=None.
        """
        entry = next((row for row in reversed(self.trajectory)
                      if row['operation_id'] == operation['operation_id'] and row['observed'] is None), None)
        if entry is None:
            return
        control = current['controls'].get(operation.get('evidence', {}).get('anchor_element_id'))
        entry['observed'] = {'state_changed': changed,
            'changed_fields': [k for k in keys if before.get(k) != after.get(k)],
            'target_after': ({k: (control['value'] or {}).get(k)
                              for k in ('value', 'checked', 'focused')} if control else None),
            'observation': deepcopy(current['evidence']['image'])}

    def rejection(self, reason, step=None):
        self.consume('max_replans')
        row = {'category': 'MISSING_OBSERVATION' if 'INSUFFICIENT' in reason else 'NO_FEASIBLE_PATH',
            'reason': reason, 'step': deepcopy(step), 'observation': deepcopy(self.current)}
        self.feedback.append(row); self.event('rejected-candidate', feedback=row)
        self.queue = []; self.queue_targets = []


    def compile_step(self, step, observation):
        return compile_step(self.task, self.page_urls, step, observation, self.navigation_count)

    async def next(self, page, assertions=None):
        self.assertions = assertions
        if self.state != 'running' or self.pending:
            self.stop('UNRESOLVED', 'Previous dispatch is unresolved or controller ended')
        while True:
            if self.queue:
                row = self.queue[0]; cid = row.get('control_id')
                if self.needs_observation:
                    # One targeted capture resolves the previous action's effect
                    # and refreshes this row; no separate page recapture after it.
                    await self.observe(page, cid)
                    self.needs_observation = False
                if any(self.current[k] != v for k, v in self.queue_identity.items()):
                    self.rejection('State changed after navigation/scroll; old targets invalid', row); continue
                before = self.queue_targets[0] if self.queue_targets else None
                after = target_projection(self.current, cid)
                explained = any(entry.get('target', {}) and entry['target'].get('control_id') == cid
                                for entry in self.trajectory[self.queue_compiled_at:])
                change = projection_change(before, after)
                if change == 'LABEL_MEANING' and _input_driven_labels(before, after) and explained:
                    change = None  # placeholder<->value swap from this control's own executed input
                state_changed = before is not None and after is not None and before['value_state'] != after['value_state']
                if change or (state_changed and not explained):
                    self.rejection(('Target meaning changed; obtain a new decision' if change
                                    else 'Target state changed unexpectedly; obtain a new decision'), row)
                    continue
                try:
                    op = self.operation(row, self.current['controls'].get(cid))
                except ValueError as error:
                    self.rejection(str(error), row); continue
                self.reserve_dispatch()
                self.pending = {'operation': op, 'decision': self.decision,
                    'observation': deepcopy(self.current), 'compiled_at': len(self.trajectory)}
                return op
            if self.needs_observation or not hasattr(self, 'current'):
                await self.observe(page, self.last_control)
                self.needs_observation = False
            self.consume('max_decisions'); self.consume('max_model_calls')
            prompt = {'protocol': VERSION, 'goal': self.task['instruction'], 'boundary': self.task['fragment'],
                'observation': self.current,
                'observed_pages': [{'page_id':f'p{i}','url':url} for i,url in enumerate(self.page_urls)],
                'current_trajectory': {'note': '本条轨迹已执行动作与实际观察结果；expected是决策预期，observed是实际观察；'
                    '与feedback（历史尝试反馈）分开，据此避免重复已完成动作。',
                    'actions': deepcopy(self.trajectory),
                    'progress': {'executed_actual_actions': self.used['max_actions'], 'minimum_required': 5,
                        'maximum': self.task['fragment']['budgets']['max_actions'],
                        'remaining_intent': self.task['final_result']}},
                'feedback': self.feedback, 'site_context': self.context, 'used': dict(self.used), 'instruction':
                    '只依据当前观察规划下一动作或一个语义动作（set_value可展开最多4个稳定原子步骤）；证据不足可observe补充control_id。'
                    'kind=plan时steps必须恰好1项：只返回下一项语义动作，后续动作等待新观察；'
                    'observe/finish/no_path时steps为空数组。不能把set_value和scroll放在同次steps中。'
                    '目标给出单位且页面有单位选择器时，优先使用对应单位，使本段条件可直接核对；单位切换后重新观察。'
                    '导航、滚动、非输入点击或展开后必须新观察再决策，不在同一短段引用后续旧目标。'
                    'set_value/type/select必须在step内给出control_id和value，不能只在reason描述数值；'
                    'set_value会展开聚焦/全选/输入；5至8实际有效动作后可finish，无完整业务门槛。'
                    '可以在业务中间状态结束本段，未执行的候选条件不能声称完成；不必把全部参数塞进本段。'
                    'wait/complete不计步，不插入无效动作凑步；无路径报告no_path并保留原因。'}
            request = self.event('model-intent', prompt=prompt)
            try:
                decision = await self.choose(prompt)
            except DecisionRequestError as error:
                self.stop('ENGINEERING_ERROR' if error.stage == 'local_preflight' else 'MODEL_FAULT',
                          str(error), original_request=request)
            except BaseException as error:
                self.stop('UNRESOLVED', type(error).__name__, original_request=request)
            from jsonschema import Draft202012Validator
            try:
                Draft202012Validator(DECISION_SCHEMA).validate(decision)
                if decision['observation_id'] != self.current['observation_id']:
                    raise ValueError('Decision observation binding changed')
            except Exception as error:
                self.stop('ENGINEERING_ERROR', str(error), original_response=decision)
            self.decision = self.event('decision', decision=decision, observation=self.current)
            kind = decision['kind']
            if kind == 'finish':
                if self.used['max_actions'] < 5:
                    self.stop('NO_FEASIBLE_PATH', 'Fewer than five actual actions; no padding')
                self.state = 'finished'; self.event('finish', observation=self.current)
                return {'action_type':'complete','arguments':{'status':'success'},'goal':'结束当前操作片段',
                        'rationale':decision['reason'],'expected':self.task['final_result']}
            if kind == 'no_path':
                self.stop('NO_FEASIBLE_PATH', decision['reason'], observation=self.current)
            if kind == 'observe':
                await self.observe(page, decision['control_id'] or None)
                cid = decision['control_id'] or None
                controls = [cid] if cid else sorted(self.current['controls'])
                semantic = {k: self.current.get(k) for k in ('url', 'document_identity', 'scroll')}
                semantic['targets'] = [(c, target_projection(self.current, c),
                    self.current['controls'].get(c, {}).get('actions')) for c in controls]
                key = (self.used['max_actions'], cid, object_sha256(semantic))
                repeated = getattr(self, '_supplemental_repeats', {})
                repeated[key] = repeated.get(key, 0) + 1
                self._supplemental_repeats = repeated
                if repeated[key] >= 2:
                    self.stop('MISSING_OBSERVATION', 'Repeated supplemental observation added no action evidence',
                              control_id=cid, observation=self.current)
                # The supplemental capture is itself fresh; decide on it directly.
                self.needs_observation = False
                self.last_control = decision['control_id'] or None
                continue
            try:
                if not decision['steps']:
                    raise ValueError('Empty plan')
                compiled = []
                # Multiple semantic writes can change focus/values. Until
                # observed, only a single set_value (1-3 primitives) is stable.
                if len(decision['steps']) > 1:
                    raise ValueError('Stable short segment is one semantic write expanded into native primitives')
                step = decision['steps'][0]
                try:
                    compiled.extend(self.compile_step(step, self.current))
                except ValueError as error:
                    # An unprobed target is exactly what one supplemental capture
                    # resolves; gather it once instead of bouncing a rejection
                    # back to the model for the same missing evidence.
                    cid = step.get('control_id')
                    probe_missing = (cid in self.current['controls']
                                     and self.current['controls'][cid].get('probe') is None)
                    if not (str(error).startswith('INSUFFICIENT') and probe_missing
                            and self._left('max_observations') >= 4):
                        raise
                    await self.observe(page, cid)
                    self.needs_observation = False
                    compiled.extend(self.compile_step(step, self.current))
                if self.used['max_actions'] + len(compiled) > self.task['fragment']['budgets']['max_actions']:
                    raise ValueError('Compiled actual actions exceed remaining 5-8 action range')
                # A new action must still be completable: per-primitive rebind
                # captures, a finish observation and one finish decision/model
                # call; report a smaller candidate instead of dispatching into
                # a guaranteed budget stop.
                for key, need in (('max_observations', 2 * len(compiled) + 1),
                                  ('max_decisions', 1), ('max_model_calls', 1)):
                    if self._left(key) < need:
                        raise ValueError('Compiled plan exceeds remaining ' + key + ' for completion')
                self.queue = compiled
                self.queue_identity = {k: deepcopy(self.current[k]) for k in ('url','document_identity','scroll')}
                self.queue_targets = [target_projection(self.current, row.get('control_id')) for row in compiled]
                self.queue_compiled_at = len(self.trajectory)
            except ValueError as error:
                self.rejection(str(error), decision['steps']); continue

    def operation(self, row, c):
        action = row['action']; cid = row.get('control_id')
        if c and 'initial_value' in row and c['value'].get('value') != row['initial_value']:
            raise ValueError('Unexpected input value changed inside short segment')
        if row.get('replacement') and row.get('initial_value'):
            value = c['value']
            if (not c['probe'].get('focused') or value.get('selection_start') != 0
                    or value.get('selection_end') != len(row['initial_value'])):
                raise ValueError('Replacement requires freshly observed full selection')
        op = {'operation_id': f"dynamic-{self.used['max_actions']+1}", 'subgoal_id': 'fragment',
            'action_type': action, 'goal': row['goal'], 'rationale': row['goal'], 'expected': row['expected'],
            'evidence': {'observation_protocol': OBS_VERSION, 'state_sha256': self.current['state_sha256'],
                'observation_id': self.current['observation_id']}}
        if action in ('click','double_click','right_click','type','select'):
            if not c or c['actions'][action]['status'] != PROVEN:
                raise ValueError('INSUFFICIENT: current target action is not proved')
            op.update(selector=c['binding']['selector'], index=c['binding'].get('index', 0))
            op['evidence'].update(anchor_element_id=cid, target_label=c['readable_labels'][0]['text'] if c['readable_labels'] else '')
        sources = self.context.get('actual_feedback', self.context)
        for failure in sources.get('avoid', []):
            old = failure.get('operation', {})
            if (old.get('action_type') == action and old.get('selector') == op.get('selector')
                    and failure.get('image',{}).get('sha256') == self.current['evidence']['image']['sha256']):
                raise ValueError('Known same-state execution failure: '+failure['reason'])
        args = {}
        if action == 'type': args = {'text': row['value']}
        if action == 'select': args = {'option': row['option']}
        if action == 'hotkey':
            if not row.get('keys'):
                raise ValueError('Explicit keys required')
            if cid and (not c or not c.get('probe') or not c['probe'].get('focused')):
                raise ValueError('Hotkey requires observed current focus')
            if cid:
                op['evidence']['focused_element_id'] = cid
                op.update(selector=c['binding']['selector'], index=c['binding'].get('index',0))
            args = {'keys': row['keys']}
        if action == 'scroll':
            if row.get('direction') not in ('up','down','left','right'):
                raise ValueError('Explicit scroll direction required')
            args = {'direction': row['direction']}
        if action == 'open_url': args = {'url': self.page_urls[int(row['page_id'][1:])]}
        op['arguments'] = args
        if row.get('replacement'):
            op['postconditions'] = [{'selector': c['binding']['selector'], 'index': c['binding'].get('index',0), 'value':row['value']}]
        return op

    def rebind(self, operation, captured):
        """Fresh dispatch evidence, preserving the original selected decision.

        Page-level navigation/scroll drift invalidates the candidate. Target
        changes are judged against the action-relevant projection the decision
        was compiled from: structure, readable labels and value state must be
        stable, because nothing was dispatched in between. A target whose
        meaning moved needs a new decision, never a silent relabeling.
        """
        if self.pending is None or self.pending['operation'] != operation:
            self.stop('UNRESOLVED', 'No selected decision for dispatch refresh')
        self.consume('max_observations')
        current = self.accept_capture(captured)
        if any(self.pending['observation'][k] != captured['state'].get(k)
               for k in ('url', 'document_identity', 'scroll')):
            self.rejection('Page navigated/scrolled before dispatch; obtain a new decision', operation)
            self.pending = None
            return None
        row = self.queue[0]; cid = row.get('control_id')
        before = target_projection(self.pending['observation'], cid)
        after = target_projection(current, cid)
        since = self.pending.get('compiled_at', len(self.trajectory))
        explained = any(entry.get('target', {}) and entry['target'].get('control_id') == cid
                        for entry in self.trajectory[since:])
        change = projection_change(before, after)
        if change == 'LABEL_MEANING' and _input_driven_labels(before, after) and explained:
            change = None
        state_changed = before is not None and after is not None and before['value_state'] != after['value_state']
        if change:
            self.rejection('Target meaning changed before dispatch; obtain a new decision', operation)
            self.pending = None
            return None
        if state_changed and not explained:
            self.rejection('Target state changed before dispatch; obtain a new decision', operation)
            self.pending = None
            return None
        try:
            refreshed = self.operation(row, current['controls'].get(row.get('control_id')))
        except ValueError as error:
            self.rejection(str(error), operation); self.pending = None
            return None
        self.pending = {'operation':refreshed,'decision':self.decision,'observation':deepcopy(current),
            'compiled_at': len(self.trajectory)}
        return refreshed

    def before_dispatch(self, operation, state, image):
        if 'candidate_binding' in self.task:
            from .candidate_contract import guard_claim
            guard_claim(self.task)
        if operation['action_type'] == 'complete':
            return None
        from .agent_observation import require_action
        require_action(state, operation)
        if self.pending is None or self.pending['operation'] != operation:
            self.stop('UNRESOLVED', 'Dispatch has no original decision')
        self.consume('max_actions')
        verify_evidence([image])
        # Sample directories move to rejected/ on failure. Keep this original
        # frame in the immutable evidence directory so dispatch refs stay valid.
        stable=self.root/f'dispatch-frame-{self.used["max_actions"]:03}.png'
        with stable.open('xb') as stream:stream.write(Path(image['path']).read_bytes())
        image={'path':str(stable.resolve()),'sha256':image['sha256']}
        verify_evidence([image])
        ref = self.event('dispatch-intent', **self.pending,
            actual_image=self.current['evidence']['image'], formal_frame=image)
        self.pending['dispatch'] = ref
        return ref

    def result(self, raw_reference, *, error=None):
        if self.pending is None:
            return
        verify_evidence([raw_reference])
        self.event('execution-result', dispatch=self.pending.get('dispatch'), raw=raw_reference, error=error)
        if error:
            self.stop('EXECUTION_FAILED', error, raw=raw_reference, operation=self.pending['operation'])
        operation = self.pending['operation']
        cid = operation.get('evidence', {}).get('anchor_element_id')
        self.trajectory.append({'operation_id': operation['operation_id'], 'action': operation['action_type'],
            'arguments': deepcopy(operation.get('arguments',{})),
            'goal': operation['goal'], 'expected': operation['expected'],
            'arguments': deepcopy(operation.get('arguments', {})),
            'target': ({'control_id': cid, 'label': operation['evidence'].get('target_label'),
                        'selector': operation.get('selector')} if cid else None),
            'observed': None})
        self.pending_effect = (deepcopy(self.captured['state']), deepcopy(operation))
        self.effect_png = object_sha256(self.captured['png'].hex())
        self.last_control = self.queue.pop(0).get('control_id')
        self.queue_targets = self.queue_targets[1:]
        self.pending = None
        self.needs_observation = True
        if not self.queue:
            self.last_control = None


class SelectionValueMismatch(ValueError):
    """A current observed option disproves the unexecuted planned value."""


class PlanPreconditionError(ValueError):
    """Known zero-dispatch correction for the explicit plan-execution policy."""
    def __init__(self,code,message):
        super().__init__(message)
        self.code=code


def compile_step(task, page_urls, step, observation, navigation_count=0):
    """Only current-target primitives; set_value expands before budget accounting.

    Shared by the frozen controller protocol and the react session loop.
    `back` binds to the session's own navigation history, never an invented
    page_id; only `open_url` names an observed page.
    """
    action = step['action']; cid = step.get('control_id'); c = observation['controls'].get(cid)
    allowed = set(task['fragment']['allowed_actions'])
    if action not in allowed:
        raise ValueError('Action outside frozen range: ' + action)
    if action == 'open_url':
        page = step.get('page_id', '')
        if not page.startswith('p') or not page[1:].isdigit() or int(page[1:]) >= len(page_urls):
            raise ValueError('Navigation requires observed page_id')
    if action == 'back':
        if 'page_id' in step:
            raise ValueError('back binds session history; page_id is not accepted')
        if navigation_count < 1:
            raise ValueError('INSUFFICIENT: no session navigation to go back from')
    if action in ('click','double_click','right_click','drag','type','set_value','select'):
        if c is None:
            raise ValueError('INSUFFICIENT: unobserved target')
        truth = c['actions'][action]
        if truth['status'] != PROVEN:
            from .plan_execution import enabled as current_plan
            if current_plan(task) and action=='type' and truth.get('reason')=='TYPE_REQUIRES_CURRENT_FOCUS':
                raise PlanPreconditionError('TYPE_REQUIRES_CURRENT_FOCUS','Input must be focused by a real click before type')
            raise ValueError(truth['status'] + ': ' + truth['reason'])
    if action=='drag':
        endpoint=observation['controls'].get(step.get('end_control_id'))
        if not endpoint or endpoint['element'].get('visible') is not True or not endpoint['binding'].get('selector'):
            raise ValueError('INSUFFICIENT: unobserved drag destination')
        if step['end_control_id']==cid:raise ValueError('Drag requires distinct observed endpoints')
    primitive = {'action': action, 'control_id': cid, 'goal': step['goal'], 'expected': step['expected']}
    for name in ('rationale','expected_result'):
        if name in step:primitive[name]=step[name]
    if action == 'set_value':
        if 'value' not in step or step['value'] == c['value']['value']:
            raise ValueError('Unchanged/missing value has no effective action')
        rows = []
        if c['probe'].get('focused') is not True:
            rows.append({**primitive, 'action': 'click'})
        if c['value']['value'] and not (c['value'].get('input_type') == 'number'
                and c['probe'].get('focused') is True and c['value'].get('all_text_selected') is True):
            rows.append({**primitive, 'action': 'hotkey', 'keys': ['meta', 'a'], 'select_all': True})
        # On a native session the browser can bind a full numeric selection
        # even without offsets. Validate it again immediately before typing.
        from .react_protocol import VERSION as native_protocol
        number = bool(c['value']['value']) and c['value'].get('input_type') == 'number'
        selected_replacement = (number and bool(step['value']) and 'all_text_selected' in c['value']
                                and task['fragment'].get('decision_protocol') == native_protocol)
        numeric_clear = number and not selected_replacement
        if numeric_clear:
            rows.append({**primitive, 'action':'hotkey', 'keys':['backspace']})
        rows.append({**primitive, 'action': 'type', 'value': step['value'], 'replacement': True} if step['value'] else
                    {**primitive, 'action': 'hotkey', 'keys': ['backspace'], 'replacement': True, 'value': ''})
        for row in rows:
            row['initial_value'] = c['value']['value']
        if selected_replacement:
            rows[-1]['replace_selected_number'] = c['value']['value']
        if numeric_clear:
            if step['value']:
                rows[-1]['initial_value']=''
            else:
                rows.pop()  # The explicit clear is itself the requested result.
        return rows
    if action == 'select':
        options = c['binding'].get('options', [])
        match = [o for o in options if o['value'] == step.get('value') and not o.get('disabled')]
        if len(match) != 1 or sum(o['label'] == match[0]['label'] for o in options) != 1:
            from .plan_execution import enabled as current_plan
            if current_plan(task):
                raise PlanPreconditionError('SELECT_OPTION_NOT_PROVEN','Select must use a unique observed enabled option value; inspect current option labels and values')
            raise SelectionValueMismatch('Selection must name a unique observed enabled option')
        if step['value'] == c['value'].get('value'):
            from .plan_execution import enabled as current_plan
            if current_plan(task):
                raise PlanPreconditionError('UNCHANGED_SELECTION','Unchanged selection is not effective')
            raise ValueError('Unchanged selection is not effective')
        primitive['option'] = match[0]['label']
    return [{**primitive, **{k: step[k] for k in ('value','keys','direction','page_id','end_control_id','duration_ms') if k in step}}]

def _job_request_count(ledger, job_id):
    with ledger.connect() as con:
        return con.execute('SELECT COUNT(*) FROM model_requests WHERE job_id=?', (job_id,)).fetchone()[0]


def model_chooser(ledger, task, attempt_id, *, parent_job=None):
    """Each decision has an original ledger identity; UNKNOWN is never resent.

    Failures are classified by the actual request stage: a local preflight
    error provably precedes any reservation (zero model_requests rows for the
    job, nothing sent or charged); a settled definite failure keeps its real
    request evidence; anything that cannot prove it never reached the wire
    stays an UNKNOWN hold.
    """
    from .model_gateway import ModelGateway
    gateway = ModelGateway(ledger)
    async def choose(prompt):
        payload = {'protocol': VERSION, 'attempt_id': attempt_id, 'task_id': task['task_id'], 'site_uri':task['site_uri'],
                   'prompt_sha256': object_sha256(prompt), 'decision': prompt['used']['max_decisions']}
        if parent_job is not None: payload['parent_job_id']=parent_job['id']
        jid = ledger.enqueue('fragment-decision', payload)
        old = ledger.get(jid)
        if old['state'] != 'queued':
            raise ValueError('Original decision request unresolved/consumed; do not resend')
        try:
            job = ledger.claim('fragment-decision', job_id=jid, **({'parent_job':parent_job} if parent_job is not None else {}))
        except ValueError as error:
            if _job_request_count(ledger,jid):
                raise OutcomeUnknown('Original decision claim has request records; reconcile') from error
            with ledger.transaction() as con:
                changed=con.execute("UPDATE jobs SET state='failed',error=? WHERE id=? AND state='queued' AND attempts=0",
                                    ('local-claim:'+type(error).__name__,jid)).rowcount
                if changed:ledger.event(con,'decision_local_claim_failure',{'job_id':jid,'reason':str(error),'requests_sent':0})
            if not changed:raise OutcomeUnknown('Decision claim ownership unresolved') from error
            raise DecisionRequestError('Local decision claim failed before any request: '+str(error)) from error
        if not job:
            raise ValueError('Original decision could not be claimed')
        images = [prompt['observation']['evidence']['image']['path']]
        from .agent_feedback import PLANNING_IMAGES_LIMIT
        context_images = prompt.get('site_context', {}).get('images', [])
        for ref in context_images[:PLANNING_IMAGES_LIMIT]:
            verify_evidence([ref]); images.append(ref['path'])
        try:
            # Keep normal synchronous ModelGateway accounting, off event loop
            # so the original production lease heartbeat stays alive.
            import asyncio
            response = await asyncio.to_thread(gateway.call, job, VERSION, json.dumps(prompt, ensure_ascii=False),
                DECISION_SCHEMA, images=list(dict.fromkeys(images)), attempts=1,
                output_limit=min(4096, ledger.config['model']['max_completion_tokens']))
            ledger.finish(job, result=response)
            return response
        except OutcomeUnknown as error:
            # Sent-or-chargeable outcome unresolved: retain the hold; no resend.
            ledger.finish(job, 'review_required', error='unknown:' + type(error).__name__)
            raise
        except ValueError as error:
            if _job_request_count(ledger, job['id']):
                ledger.finish(job, 'failed', error='settled:' + type(error).__name__)
                raise DecisionModelFault('Definite failed model response (request settled, no resend): ' + str(error)) from error
            ledger.finish(job, 'failed', error='local:' + type(error).__name__)
            raise DecisionRequestError('Local decision preflight failed before any request: ' + str(error)) from error
        except BaseException as error:
            # Cannot prove the request never reached the provider: UNKNOWN hold.
            ledger.finish(job, 'review_required', error=type(error).__name__)
            raise
    return choose


def verify_ledger_binding(plan, ledger):
    from .react_session import is_react_task
    if any(is_controlled(task) or is_react_task(task) for task in plan['tasks']):
        expected = plan.get('generation',{}).get('controller_ledger')
        if ledger is None or expected != {'path':str(ledger.path), 'config_sha256':object_sha256(ledger.config)}:
            raise ValueError('Dynamic plan requires its original model ledger/config; no replacement or UNKNOWN resend')
