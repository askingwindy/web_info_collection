"""Bounded fragment controller on the ordinary collector and model ledger.

The frozen goal is immutable; decisions and dispatch/result companions are new
exclusive files. Interrupted controllers cannot replay or splice a trajectory.
"""
from copy import deepcopy
import json
from pathlib import Path
from .planning import object_sha256, verify_evidence
from .batch_core import file_sha, load_json
from .agent_observation import project, action_availability, readable_labels, PROVEN, VERSION as OBS_VERSION, ACTIONS

VERSION = 'webcollect-fragment-controller-1'
FRAGMENT_VERSION = 'webcollect-fragment-workflow-2'
LIMITS = {'max_actions': 8, 'max_observations': 24, 'max_decisions': 16, 'max_replans': 8, 'max_model_calls': 12}
from .semantic_workflow import obj, TEXT, TASK_SCHEMA as SEMANTIC_SCHEMA
from .fragment_workflow import STEP
TASK_SCHEMA = obj({'schema_version': {'const': FRAGMENT_VERSION}, 'task_family': TEXT,
    'instruction': TEXT, 'task_type': SEMANTIC_SCHEMA['properties']['task_type'],
    'page_id': TEXT, 'end_description': TEXT,
    'allowed_actions': {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': {'enum': sorted(ACTIONS)}},
    'budgets': obj({k: {'type': 'integer', 'minimum': 1, 'maximum': v} for k, v in LIMITS.items()})})
SCHEMA = obj({'tasks': {'type': 'array', 'maxItems': 5, 'items': TASK_SCHEMA},
    'empty_reasons': {'type': 'array', 'items': obj({
        'category':{'enum':['NO_FEASIBLE_PATH','MISSING_OBSERVATION','ENGINEERING_ERROR','UNRESOLVED_REQUEST']},
        'reason':TEXT, 'control_ids':{'type':'array','items':TEXT}})}})
DECISION_SCHEMA = obj({'kind': {'enum': ['plan', 'observe', 'finish', 'no_path']},
    'observation_id': TEXT, 'reason': TEXT,
    'steps': {'type': 'array', 'maxItems': 1, 'items': STEP}, 'control_id': {'type': 'string'}})


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
    from .task_instruction import validate_task_instruction
    validate_task_instruction(task['instruction']); validate_task(task)
    return task


class ControllerStop(ValueError):
    failure_class = 'content'
    responsibility = 'collector'


class FragmentController:
    def __init__(self, task, directory, choose, *, frame_guard=None, site_context=None):
        validate_task(task)
        self.task = deepcopy(task); self.root = Path(directory); self.root.mkdir(parents=True, exist_ok=True)
        self.choose = choose; self.frame_guard = frame_guard; self.context = deepcopy(site_context or {})
        self.used = dict.fromkeys(LIMITS, 0); self.queue = []; self.feedback = []; self.state = 'running'
        self.sequence = 0; self.pending = None; self.last_control = None
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
        if current['url'] not in self.task['fragment']['page_urls']:
            self.stop('NO_FEASIBLE_PATH', 'Page is outside frozen source scope', observation=current)
        if self.frame_guard:
            conflicts = self.frame_guard(current['evidence']['image'])
            if conflicts:
                self.stop('DUPLICATE', 'Known screenshot conflict', conflicts=conflicts, observation=current)
        return current

    def rejection(self, reason, step=None):
        self.consume('max_replans')
        row = {'category': 'MISSING_OBSERVATION' if 'INSUFFICIENT' in reason else 'NO_FEASIBLE_PATH',
            'reason': reason, 'step': deepcopy(step), 'observation': deepcopy(self.current)}
        self.feedback.append(row); self.event('rejected-candidate', feedback=row)
        self.queue = []

    def compile_step(self, step, observation):
        """Only current-target primitives; set_value expands before budget accounting."""
        action = step['action']; cid = step.get('control_id'); c = observation['controls'].get(cid)
        allowed = set(self.task['fragment']['allowed_actions'])
        if action not in allowed:
            raise ValueError('Action outside frozen range: ' + action)
        if action in ('open_url', 'back'):
            page = step.get('page_id', '')
            pages = self.task['fragment']['page_urls']
            if not page.startswith('p') or not page[1:].isdigit() or int(page[1:]) >= len(pages):
                raise ValueError('Navigation requires observed page_id')
        if action in ('click','double_click','right_click','type','set_value','select'):
            if c is None:
                raise ValueError('INSUFFICIENT: unobserved target')
            truth = c['actions'][action]
            if truth['status'] != PROVEN:
                raise ValueError(truth['status'] + ': ' + truth['reason'])
        primitive = {'action': action, 'control_id': cid, 'goal': step['goal'], 'expected': step['expected']}
        if action == 'set_value':
            if 'value' not in step or step['value'] == c['value']['value']:
                raise ValueError('Unchanged/missing value has no effective action')
            rows = []
            if c['probe'].get('focused') is not True:
                rows.append({**primitive, 'action': 'click'})
            if c['value']['value']:
                rows.append({**primitive, 'action': 'hotkey', 'keys': ['meta', 'a'], 'select_all': True})
            rows.append({**primitive, 'action': 'type', 'value': step['value'], 'replacement': True} if step['value'] else
                        {**primitive, 'action': 'hotkey', 'keys': ['backspace'], 'replacement': True, 'value': ''})
            for row in rows:
                row['initial_value'] = c['value']['value']
            return rows
        if action == 'select':
            options = c['binding'].get('options', [])
            match = [o for o in options if o['value'] == step.get('value') and not o.get('disabled')]
            if len(match) != 1 or sum(o['label'] == match[0]['label'] for o in options) != 1:
                raise ValueError('Selection must name a unique observed enabled option')
            if step['value'] == c['value'].get('value'):
                raise ValueError('Unchanged selection is not effective')
            primitive['option'] = match[0]['label']
        return [{**primitive, **{k: step[k] for k in ('value','keys','direction','page_id') if k in step}}]

    async def next(self, page, assertions=None):
        self.assertions = assertions
        if self.state != 'running' or self.pending:
            self.stop('UNRESOLVED', 'Previous dispatch is unresolved or controller ended')
        while True:
            cid = self.queue[0].get('control_id') if self.queue else self.last_control
            await self.observe(page, cid)
            if not self.queue:
                self.consume('max_decisions'); self.consume('max_model_calls')
                prompt = {'protocol': VERSION, 'goal': self.task['instruction'], 'boundary': self.task['fragment'],
                    'observation': self.current, 'feedback': self.feedback, 'site_context': self.context,
                    'used': dict(self.used), 'instruction':
                    '只依据当前观察规划下一动作或一个语义动作（set_value可展开最多3个稳定原子步骤）；证据不足可observe补充control_id。'
                    '导航、滚动、非输入点击或展开后必须新观察再决策，不在同一短段引用后续旧目标。'
                    'set_value会展开聚焦/全选/输入；5至8实际有效动作后可finish，无完整业务门槛。'
                    'wait/complete不计步，不插入无效动作凑步；无路径报告no_path并保留原因。'}
                request = self.event('model-intent', prompt=prompt)
                try:
                    decision = await self.choose(prompt)
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
                    for step in decision['steps']:
                        compiled.extend(self.compile_step(step, self.current))
                    if self.used['max_actions'] + len(compiled) > self.task['fragment']['budgets']['max_actions']:
                        raise ValueError('Compiled actual actions exceed remaining 5-8 action range')
                    self.queue = compiled
                    self.queue_identity = {k: deepcopy(self.current[k]) for k in ('url','document_identity','scroll')}
                except ValueError as error:
                    self.rejection(str(error), decision['steps']); continue
            row = self.queue[0]
            if any(self.current[k] != v for k, v in self.queue_identity.items()):
                self.rejection('State changed after navigation/scroll; old targets invalid', row); continue
            c = self.current['controls'].get(row.get('control_id'))
            try:
                op = self.operation(row, c)
            except ValueError as error:
                self.rejection(str(error), row); continue
            self.pending = {'operation': op, 'decision': self.decision, 'observation': deepcopy(self.current)}
            return op

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
            op['evidence'].update(anchor_element_id=cid, target_label=c['readable_labels'][0]['text'])
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
        if action == 'open_url': args = {'url': self.task['fragment']['page_urls'][int(row['page_id'][1:])]}
        op['arguments'] = args
        if row.get('replacement'):
            op['postconditions'] = [{'selector': c['binding']['selector'], 'index': c['binding'].get('index',0), 'value':row['value']}]
        return op

    def rebind(self, operation, captured):
        """Fresh dispatch evidence, preserving the original selected decision.

        State changes are a new candidate decision, never silent retargeting.
        Only stable equivalent target/value/focus state can reuse a short step.
        """
        if self.pending is None or self.pending['operation'] != operation:
            self.stop('UNRESOLVED', 'No selected decision for dispatch refresh')
        before = self.captured['state']
        self.consume('max_observations')
        current = self.accept_capture(captured)
        keys = ('url','document_identity','scroll','values')
        if any(before.get(k) != captured['state'].get(k) for k in keys):
            self.rejection('State changed before dispatch; obtain a new decision', operation)
            self.pending = None
            return None
        row = self.queue[0]
        try:
            refreshed = self.operation(row, current['controls'].get(row.get('control_id')))
        except ValueError as error:
            self.rejection(str(error), operation); self.pending = None
            return None
        self.pending = {'operation':refreshed,'decision':self.decision,'observation':deepcopy(current)}
        return refreshed

    def before_dispatch(self, operation, state, image):
        if operation['action_type'] == 'complete':
            return None
        from .agent_observation import require_action
        require_action(state, operation)
        if self.pending is None or self.pending['operation'] != operation:
            self.stop('UNRESOLVED', 'Dispatch has no original decision')
        self.consume('max_actions')
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
        self.pending_effect = (deepcopy(self.captured['state']), deepcopy(self.pending['operation']))
        self.effect_png = object_sha256(self.captured['png'].hex())
        self.last_control = self.queue.pop(0).get('control_id')
        self.pending = None
        if not self.queue:
            self.last_control = None


def model_chooser(ledger, task, attempt_id):
    """Each decision has an original ledger identity; UNKNOWN is never resent."""
    from .model_gateway import ModelGateway
    gateway = ModelGateway(ledger)
    async def choose(prompt):
        payload = {'protocol': VERSION, 'attempt_id': attempt_id, 'task_id': task['task_id'], 'site_uri':task['site_uri'],
                   'prompt_sha256': object_sha256(prompt), 'decision': prompt['used']['max_decisions']}
        jid = ledger.enqueue('fragment-decision', payload)
        old = ledger.get(jid)
        if old['state'] != 'queued':
            raise ValueError('Original decision request unresolved/consumed; do not resend')
        job = ledger.claim('fragment-decision', job_id=jid)
        if not job:
            raise ValueError('Original decision could not be claimed')
        images = [prompt['observation']['evidence']['image']['path']]
        for ref in prompt.get('site_context', {}).get('images', []):
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
        except BaseException as error:
            ledger.finish(job, 'review_required', error=type(error).__name__)
            raise
    return choose


def verify_ledger_binding(plan, ledger):
    if any(is_controlled(task) for task in plan['tasks']):
        expected = plan.get('generation',{}).get('controller_ledger')
        if ledger is None or expected != {'path':str(ledger.path), 'config_sha256':object_sha256(ledger.config)}:
            raise ValueError('Dynamic plan requires its original model ledger/config; no replacement or UNKNOWN resend')
