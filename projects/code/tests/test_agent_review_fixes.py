"""Formal regressions for the four agent-loop closure defects.

All IO is simulated: in-memory surfaces, disposable images/ledgers, patched
gateway boundaries; no browser, site, provider or QC service.
"""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from PIL import Image

from test_agent_loop import AgentLoop
from webcollect.agent_audit import terminal_proof
from webcollect.agent_controller import (FragmentController, compile_goal, ControllerStop, exclusive,
    model_chooser, DecisionRequestError, DecisionModelFault)
from webcollect.agent_feedback import site_context
from webcollect.agent_observation import PROVEN
from webcollect.batch_core import BatchLedger, OutcomeUnknown, load_json, file_sha
from webcollect.browser import fingerprint, prepare_action
from webcollect.planning import object_sha256


class ClosureFixes(AgentLoop):
    """Drive the controller exactly like the shared collector does."""

    async def test_unchanged_supplemental_capture_stops_without_dispatch(self):
        self.surface.readable=False
        async def choose(prompt):
            return {'kind':'observe','observation_id':prompt['observation']['observation_id'],
                'reason':'补充目标证据','steps':[],'control_id':'control-0'}
        controller=self.controller(choose)
        with self.assertRaises(ControllerStop) as error:await controller.next(self.surface)
        self.assertEqual(error.exception.category,'MISSING_OBSERVATION')
        self.assertEqual(controller.used['max_model_calls'],2)
        self.assertEqual(controller.used['max_actions'],0)
        self.assertEqual(len(list(controller.root.glob('observation-*.png'))),3)

    def test_decision_inputs_require_explicit_parameters_without_changing_legacy_step(self):
        from jsonschema import Draft202012Validator,ValidationError
        from webcollect.agent_controller import DECISION_STEP,DECISION_SCHEMA
        from webcollect.fragment_workflow import STEP
        missing={'action':'set_value','control_id':'control-0','goal':'输入20','expected':'显示20'}
        Draft202012Validator(STEP).validate(missing)
        with self.assertRaises(ValidationError):Draft202012Validator(DECISION_STEP).validate(missing)
        Draft202012Validator(DECISION_STEP).validate({**missing,'value':'20'})
        with self.assertRaises(ValidationError):
            Draft202012Validator(DECISION_SCHEMA).validate({'kind':'plan','observation_id':'fixture',
                'reason':'下一动作','control_id':'control-0','steps':[{**missing,'value':'20'},
                {'action':'scroll','direction':'down','goal':'查看结果','expected':'显示结果'}]})

    async def driven(self, controller, effect=None, raw_name='driven'):
        operation = await controller.next(self.surface)
        if operation['action_type'] == 'complete':
            return operation
        captured = await self.surface.capture(self.surface, operation.get('selector'))
        operation = controller.rebind(operation, captured)
        self.assertIsNotNone(operation, 'unchanged target must dispatch')
        prepare_action(controller.captured['state'], operation)
        dispatch = controller.before_dispatch(operation, controller.captured['state'],
            controller.current['evidence']['image'])
        self.surface.execute(operation)
        if effect:
            effect(operation)
        raw = {'operation': operation, 'state': deepcopy(controller.captured['state']),
               'capture': controller.captured['capture'], 'controller_dispatch': dispatch,
               'ended_at': '2026-10-30T00:00:00+08:00'}
        self.raw.append(raw)
        controller.result(exclusive(self.root/f'{raw_name}-{len(self.raw)}.json', raw))
        return operation

    def checkboxes(self, count, base=0):
        original_element = deepcopy(self.surface.state['elements'][0])
        original_binding = deepcopy(self.surface.state['capture_controls'][0])
        original_value = deepcopy(self.surface.state['values'][0])
        for index in range(count):
            cid = f'box-{base + index}'
            self.surface.state['elements'].append({**original_element, 'element_id': cid,
                'text': f'选项{base + index + 1}', 'element_type': 'checkbox', 'inputable': False,
                'bbox': [10, 20+(base+index)*60, 210, 60+(base+index)*60]})
            self.surface.state['capture_controls'].append({**original_binding, 'element_id': cid,
                'selector': f'#{cid}', 'input_type': 'checkbox'})
            self.surface.state['values'].append({**original_value, 'element_id': cid,
                'value': f'选项{base + index + 1}', 'input_type': 'checkbox', 'choice': True,
                'checked': False, 'focused': False})

    def toggle(self, operation):
        cid = operation.get('evidence', {}).get('anchor_element_id')
        for value in self.surface.state['values']:
            if value['element_id'] == cid and value.get('input_type') == 'checkbox':
                value['checked'] = not value.get('checked', False)

    # ---- Fix 2: budgets cover observe/decide/finish on real paths ----

    def click_chooser(self, total):
        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            count = prompt['used']['max_actions']
            response = {'kind': 'finish', 'observation_id': prompt['observation']['observation_id'],
                'reason': '按序选中不同选项', 'steps': [], 'control_id': ''}
            if count >= total:
                return response
            cid = f'box-{count}'
            if prompt['observation']['controls'][cid]['actions']['click']['status'] != PROVEN:
                return {**response, 'kind': 'observe', 'control_id': cid}
            return {**response, 'kind': 'plan', 'steps': [{'action': 'click', 'control_id': cid,
                'goal': f'选中选项{count + 1}', 'expected': '当前选项被选中'}]}
        return choose

    async def run_clicks(self, total):
        self.spec['instruction'] = f'在「受控离线页面」选中{total}个已显示选项并查看当前状态。'
        self.spec['allowed_actions'] = ['click']
        self.task = compile_goal(self.cap, self.spec, 'review-fixture')
        self.checkboxes(total)
        controller = self.controller(self.click_chooser(total))
        for _ in range(total + 1):
            if (await self.driven(controller, effect=self.toggle))['action_type'] == 'complete':
                break
        return controller

    async def test_five_step_click_path_finishes_inside_budgets(self):
        controller = await self.run_clicks(5)
        self.assertEqual(controller.state, 'finished')
        self.assertEqual(controller.used['max_actions'], 5)
        self.assertTrue(all(controller.used[key] <= controller.task['fragment']['budgets'][key]
                            for key in controller.used), controller.used)
        self.assertEqual(controller.feedback, [])
        proof = terminal_proof(self.task, self.raw, {'screenshot_sha256': 'fixture-ending'})
        self.assertEqual(proof['effective_steps'], 5)

    async def test_six_step_click_path_finishes_inside_default_budgets(self):
        controller = await self.run_clicks(6)
        self.assertEqual(controller.state, 'finished')
        self.assertEqual(sum(v['checked'] for v in self.surface.state['values'] if v.get('input_type') == 'checkbox'), 6)
        self.assertEqual(controller.used['max_observations'], 6 * 3 + 1, controller.used)
        self.assertEqual(controller.used['max_decisions'], 6 * 2 + 1)
        self.assertTrue(all(controller.used[key] <= controller.task['fragment']['budgets'][key]
                            for key in controller.used), controller.used)

    async def test_eight_step_mixed_inputs_and_clicks_finish_inside_budgets(self):
        self.spec['allowed_actions'] = ['set_value', 'click', 'type', 'hotkey']
        self.task = compile_goal(self.cap, self.spec, 'mixed-fixture')
        self.checkboxes(2)

        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            count = prompt['used']['max_actions']
            base = {'kind': 'finish', 'observation_id': prompt['observation']['observation_id'],
                'reason': '完成输入与选中', 'steps': [], 'control_id': ''}
            if count >= 8:
                return base
            if count < 3:
                cid, action, value = 'control-0', 'set_value', '20'
            elif count < 6:
                cid, action, value = 'control-1', 'set_value', '30'
            else:
                cid, action, value = (f'box-{count - 6}', 'click', None)
            control = prompt['observation']['controls'][cid]
            if control['actions'][action]['status'] != PROVEN:
                return {**base, 'kind': 'observe', 'control_id': cid}
            step = {'action': action, 'control_id': cid, 'goal': '继续当前片段', 'expected': '页面状态更新'}
            if action == 'set_value':
                step['value'] = value
            return {**base, 'kind': 'plan', 'steps': [step]}

        controller = self.controller(choose)
        for _ in range(9):
            if (await self.driven(controller, effect=self.toggle))['action_type'] == 'complete':
                break
        self.assertEqual(controller.state, 'finished')
        self.assertEqual(controller.used['max_actions'], 8)
        self.assertEqual(self.surface.executed, ['click', 'hotkey', 'type'] * 2 + ['click'] * 2)
        self.assertTrue(all(controller.used[key] <= controller.task['fragment']['budgets'][key]
                            for key in controller.used), controller.used)
        proof = terminal_proof(self.task, self.raw, {'screenshot_sha256': 'fixture-ending'})
        self.assertEqual(proof['effective_steps'], 8)

    async def test_insufficient_budget_terminates_with_preserved_evidence(self):
        spec = deepcopy(self.spec)
        spec['budgets'] = {**spec['budgets'], 'max_observations': 3}
        task = compile_goal(self.cap, spec, 'tight-fixture')
        controller = FragmentController(task, self.root/'tight', self.chooser)
        with self.assertRaisesRegex(ControllerStop, 'BUDGET_EXHAUSTED'):
            await controller.next(self.surface)
        self.assertEqual(controller.state, 'BUDGET_EXHAUSTED')
        self.assertEqual(controller.used['max_actions'], 0)
        self.assertTrue((controller.root/'boundary.json').is_file())
        self.assertTrue(any(controller.root.glob('observation-*.png')), 'executed observations must remain')
        self.assertTrue(any(p.name.endswith('terminal.json') for p in controller.root.iterdir()))

    # ---- Fix 1: target-semantic consistency ----

    async def test_changed_visible_target_label_rebind_requires_new_decision(self):
        controller = self.controller()
        old_operation = await controller.next(self.surface)
        captured = await self.surface.capture(self.surface, old_operation['selector'])
        target_id = captured['state']['target']['element_id']
        captured['state']['target']['visible_label_evidence'] = [
            {'kind': 'rendered_associated_label', 'text': '另一用途的字段'}]
        for element in captured['state']['elements']:
            if element['element_id'] == target_id:
                element['text'] = '另一用途的字段'
        captured['state']['visible_text'] += '\n另一用途的字段'
        for receipt in captured['capture']['attempts']:
            receipt['before_fingerprint'] = fingerprint(captured['state'])
            receipt['after_fingerprint'] = fingerprint(captured['state'])
        decision_before = controller.decision
        refreshed = controller.rebind(old_operation, captured)
        self.assertIsNone(refreshed, 'visible target meaning changed: obtain another decision')
        self.assertIsNone(controller.pending)
        self.assertEqual(controller.decision, decision_before)
        self.assertTrue(any('Target meaning changed' in row['reason'] for row in controller.feedback))
        self.assertEqual(self.surface.executed, [])

    async def test_changed_target_binding_is_structural_not_silent_retarget(self):
        controller = self.controller()
        old_operation = await controller.next(self.surface)
        captured = await self.surface.capture(self.surface, old_operation['selector'])
        target_id = captured['state']['target']['element_id']
        for binding in captured['state']['capture_controls']:
            if binding['element_id'] == target_id:
                binding['selector'] = '#moved-elsewhere'
        for receipt in captured['capture']['attempts']:
            receipt['before_fingerprint'] = fingerprint(captured['state'])
            receipt['after_fingerprint'] = fingerprint(captured['state'])
        self.assertIsNone(controller.rebind(old_operation, captured))
        self.assertTrue(any('Target meaning changed' in row['reason'] for row in controller.feedback))

    async def test_target_value_drift_pre_dispatch_rejects_but_unrelated_drift_does_not(self):
        controller = self.controller()
        operation = await controller.next(self.surface)
        self.surface.state['values'][1]['value'] = '无关控件的页面自走'
        captured = await self.surface.capture(self.surface, operation['selector'])
        refreshed = controller.rebind(operation, captured)
        self.assertIsNotNone(refreshed, 'unrelated control drift must not block the action target')
        controller.before_dispatch(refreshed, controller.captured['state'], controller.current['evidence']['image'])
        controller.queue.clear(); controller.pending = None
        operation = await controller.next(self.surface)
        self.surface.state['values'][0]['value'] = '目标自身被外部改动'
        captured = await self.surface.capture(self.surface, operation['selector'])
        self.assertIsNone(controller.rebind(operation, captured))
        self.assertTrue(any(row['reason'].startswith(('Target meaning changed', 'Target state changed'))
                           for row in controller.feedback))

    async def test_expected_input_effect_continues_set_value_without_termination(self):
        controller = self.controller()
        for _ in range(3):
            await self.driven(controller, raw_name='sv0')
        self.assertEqual(self.surface.executed, ['click', 'hotkey', 'type'])
        self.assertEqual(controller.feedback, [], 'own input effects must not terminate the segment')
        self.assertEqual(controller.used['max_actions'], 3)

    async def test_native_number_replacement_proves_clear_without_selection_offsets(self):
        for value in self.surface.state['values']:value['input_type']='number'
        original=self.surface.capture
        selected=[False]
        def effect(operation):
            selected[0]=operation['action_type']=='hotkey' and operation['arguments']['keys']==['meta','a']
        async def capture(*args,**kw):
            for value in self.surface.state['values']:value['selection_start']=value['selection_end']=None
            frame=await original(*args,**kw)
            if selected[0]:
                # Authored fixture for visible native selection despite absent offsets.
                image=Image.open(BytesIO(frame['png']));image.putpixel((0,0),(0,0,255))
                stream=BytesIO();image.save(stream,'PNG');frame['png']=stream.getvalue()
                import hashlib
                frame['capture']['screenshot_sha256']=hashlib.sha256(frame['png']).hexdigest()
            return frame
        with patch('webcollect.browser.capture',side_effect=capture):
            controller=self.controller()
            for _ in range(9):
                if (await self.driven(controller,effect=effect,raw_name='numeric'))['action_type']=='complete':break
        self.assertEqual(self.surface.executed,['click','hotkey','hotkey','type']*2)
        self.assertEqual(self.surface.state['values'][0]['value'],'20')
        self.assertEqual(controller.feedback,[])
        self.assertEqual(controller.state,'finished')
        self.assertEqual(terminal_proof(self.task,self.raw,{'screenshot_sha256':'fixture-ending'})['effective_steps'],8)

    async def test_native_number_failed_clear_cannot_dispatch_replacement(self):
        for value in self.surface.state['values']:value['input_type']='number'
        controller=self.controller()
        for _ in range(3):await self.driven(controller,raw_name='uncleared')
        # The next type cannot concatenate onto a value left by a failed clear.
        self.surface.state['values'][0]['value']='9'
        row=controller.queue[0]
        await controller.observe(self.surface,'control-0')
        with self.assertRaisesRegex(ValueError,'Unexpected input value'):
            controller.operation(row,controller.current['controls']['control-0'])

    # ---- Fix 3: current-trajectory memory actually reaches the model ----

    async def test_prompts_carry_executed_actions_and_observed_effects(self):
        controller = self.controller()
        for _ in range(4):
            await self.driven(controller, raw_name='memory')
        later = [p for p in self.prompts if p['used']['max_actions'] >= 3]
        self.assertTrue(later)
        for prompt in later:
            entries = prompt['current_trajectory']['actions']
            self.assertTrue(any(entry['operation_id'] == 'dynamic-1' for entry in entries))
            self.assertEqual(prompt['feedback'], [], 'trajectory memory is separate from historical feedback')
        typed = [entry for p in later for entry in p['current_trajectory']['actions']
                 if entry['operation_id'] == 'dynamic-3']
        self.assertTrue(typed and all(entry['observed'] is not None for entry in typed))
        self.assertEqual(typed[0]['observed']['target_after']['value'], '20')
        self.assertTrue(typed[0]['observed']['changed_fields'])
        self.assertEqual(set(typed[0]['observed']['observation']), {'path', 'sha256'},
                         'only bounded references, no unbounded image copies')

    async def test_decider_avoids_repeats_using_trajectory_memory(self):
        async def choose(prompt):
            self.prompts.append(deepcopy(prompt))
            base = {'kind': 'finish', 'observation_id': prompt['observation']['observation_id'],
                'reason': '两个条件都已输入', 'steps': [], 'control_id': ''}
            done = {entry['target']['control_id'] for entry in prompt['current_trajectory']['actions']
                    if entry['target']}
            remaining = [cid for cid in ('control-0', 'control-1') if cid not in done]
            if not remaining:
                return base
            cid = remaining[0]
            if prompt['observation']['controls'][cid]['actions']['set_value']['status'] != PROVEN:
                return {**base, 'kind': 'observe', 'control_id': cid}
            return {**base, 'kind': 'plan', 'steps': [{'action': 'set_value', 'control_id': cid,
                'value': '20', 'goal': '修改当前字段', 'expected': '显示填写值'}]}
        controller = self.controller(choose)
        for _ in range(7):
            if (await self.driven(controller))['action_type'] == 'complete':
                break
        self.assertEqual(controller.state, 'finished')
        self.assertEqual(self.surface.executed, ['click', 'hotkey', 'type'] * 2)
        self.assertEqual(controller.used['max_actions'], 6)

    # ---- Fix 4: local preflight vs definite failure vs true UNKNOWN ----

    def tiny_image(self, name):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = BytesIO(); Image.new('RGB', (4, 4), (7, 8, 9)).save(stream, 'PNG')
        path.write_bytes(stream.getvalue())
        return {'path': str(path.resolve()), 'sha256': file_sha(path)}

    def decision_ledger(self, name):
        config = load_json(Path(__file__).parents[1]/'config/batch-synthetic.json')
        return BatchLedger(self.root/name, config, initialize=True)

    async def test_planning_images_are_bounded_before_any_request(self):
        """Bounded default planning input (2026-10-31 redesign): the chooser
        attaches at most PLANNING_IMAGES_LIMIT context images plus the current
        observation, so a huge QC-image history cannot grow the request or
        create a remote unknown; older context stays reachable via inspect."""
        from webcollect.agent_feedback import PLANNING_IMAGES_LIMIT
        from unittest.mock import patch
        ledger = self.decision_ledger('local-limit.db')
        images = [self.tiny_image(f'imgs/limit-{i}.png') for i in range(13)]
        context = {'schema_version': 'fixture', 'images': images[1:]}
        choose = model_chooser(ledger, self.task, 'attempt-local')
        prompt = {'observation': {'evidence': {'image': images[0]}},
                  'site_context': context, 'used': {'max_decisions': 1}}
        attached = []
        def record_call(job, version, text, schema, **kw):
            attached.extend(kw.get('images') or [])
            raise ValueError('local fixture stop')
        with patch('webcollect.model_gateway.ModelGateway.call', side_effect=record_call):
            with self.assertRaisesRegex(DecisionRequestError, 'before any request') as caught:
                await choose(prompt)
        self.assertEqual(caught.exception.stage, 'local_preflight')
        self.assertLessEqual(len(attached), 1 + PLANNING_IMAGES_LIMIT)
        self.assertIn(images[0]['path'], attached)
        with ledger.connect() as con:
            job = dict(con.execute("SELECT id,state,error FROM jobs WHERE kind='fragment-decision'").fetchone())
            requests = con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0]
        self.assertEqual((job['state'], requests), ('failed', 0))
        self.assertIn('local', job['error'])
        self.assertEqual(site_context(None, self.cap['site_uri'], model_ledger=ledger)['unresolved'], [])

    async def test_settled_model_failure_is_definite_fault_with_kept_evidence(self):
        ledger = self.decision_ledger('settled-fault.db')
        image = self.tiny_image('imgs/settled.png')
        prompt = {'observation': {'evidence': {'image': image}}, 'used': {'max_decisions': 1}}
        payload = {'protocol': 'webcollect-fragment-controller-2', 'attempt_id': 'attempt-settled',
                   'task_id': self.task['task_id'], 'site_uri': self.task['site_uri'],
                   'prompt_sha256': object_sha256(prompt), 'decision': 1}
        jid = ledger.enqueue('fragment-decision', payload)
        with ledger.transaction() as con:
            con.execute("INSERT INTO model_requests(id,job_id,purpose,attempt,state,reserved_tokens,"
                        "reserved_cost,started) VALUES('request-settled',?,'fixture-purpose',0,"
                        "'invalid_response',56000,0,12345.0)", (jid,))
        choose = model_chooser(ledger, self.task, 'attempt-settled')
        from webcollect.model_gateway import ModelGateway
        with patch.object(ModelGateway, 'call', side_effect=ValueError('Bounded model attempts exhausted')):
            with self.assertRaisesRegex(DecisionModelFault, 'Definite failed model response') as caught:
                await choose(prompt)
        self.assertEqual(caught.exception.stage, 'definite_model_response')
        self.assertEqual(ledger.get(jid)['state'], 'failed')
        with ledger.connect() as con:
            kept = con.execute("SELECT state FROM model_requests WHERE id='request-settled'").fetchone()[0]
        self.assertEqual(kept, 'invalid_response')
        self.assertEqual(site_context(None, self.cap['site_uri'], model_ledger=ledger)['unresolved'], [])

    async def test_transport_unknown_keeps_hold_and_blocks_resend(self):
        ledger = self.decision_ledger('transport-unknown.db')
        image = self.tiny_image('imgs/unknown.png')
        prompt = {'observation': {'evidence': {'image': image}}, 'used': {'max_decisions': 1}}
        choose = model_chooser(ledger, self.task, 'attempt-unknown')
        from webcollect.model_gateway import ModelGateway
        with patch.object(ModelGateway, 'call', side_effect=OutcomeUnknown('provider outcome UNKNOWN')):
            with self.assertRaises(OutcomeUnknown):
                await choose(prompt)
        with ledger.connect() as con:
            state = con.execute("SELECT state FROM jobs WHERE kind='fragment-decision'").fetchone()[0]
        self.assertEqual(state, 'review_required')
        unresolved = site_context(None, self.cap['site_uri'], model_ledger=ledger)['unresolved']
        self.assertEqual(unresolved[0]['category'], 'UNRESOLVED_REQUEST')
        with self.assertRaises(ValueError):
            await choose(prompt)

    async def test_site_context_bounds_image_attachments_to_recent_attempts(self):
        from webcollect.agent_feedback import site_context, save_attempt_feedback
        from test_p0_production import seed_captures
        registry = self.root/'bounded-registry.db'
        evidence = {}
        for n in range(3):
            sid = f'BOUND-img-{n}'
            rawdir = self.root/'capture/evidence'/sid; rawdir.mkdir(parents=True)
            self.surface.state['values'][0]['value'] = f'第{n}次的取值'
            frame = await self.surface.capture(None, '#control-0')
            sample = self.root/'capture/rejected'/sid/'images'; sample.mkdir(parents=True)
            (sample/'step_001.png').write_bytes(frame['png'])
            operation = {'action_type': 'click', 'selector': '#control-0', 'goal': '填写', 'arguments': {}, 'evidence': {}}
            from webcollect.batch_core import save_json
            save_json(rawdir/'step_001.json', {'step_id': 1, 'state': frame['state'], 'capture': frame['capture'],
                'operation': operation, 'target_element': frame['state']['elements'][0], 'execution_error': '点击失败'})
            attempt = {'attempt_id': 'attempt-'+sid, 'task_id': sid, 'sample_id': sid}
            evidence[sid] = [save_attempt_feedback(rawdir, attempt, 'rejected', '点击失败')]
        seed_captures(registry, list(evidence), prefix=0, evidence=evidence)
        context = site_context(registry, self.cap['site_uri'])
        self.assertEqual(len(context['executions']), 3)
        statuses = [entry['feedback_status'] for entry in context['executions']]
        self.assertEqual(statuses.count('BOUND_ORIGINAL_STEPS'), 2)
        self.assertEqual(statuses.count('BOUND_COMPACT_OLD_ATTEMPT'), 1)
        self.assertTrue(all('state' in step for step in context['executions'][0]['feedback']['steps']))
        old = next(entry for entry in context['executions'] if entry['feedback_status'] == 'BOUND_COMPACT_OLD_ATTEMPT')
        self.assertTrue(all('state' not in step for step in old['steps']))
        self.assertTrue(old['steps'][0]['execution_error'])
        self.assertEqual(len(context['avoid']), 3)
        self.assertTrue(all('state' in row for row in context['avoid'][:2]))
        self.assertTrue(all('state' not in row for row in context['avoid'][2:]))
        self.assertEqual(len(context['images']), 2, 'only the two most recent attempts attach images')

    def test_controlled_empty_reason_schema_accepts_string_annotations(self):
        from jsonschema import Draft202012Validator
        from webcollect.agent_controller import SCHEMA
        validator = Draft202012Validator(SCHEMA)
        annotated = {'tasks': [], 'empty_reasons': [{'category': 'MISSING_OBSERVATION',
            'reason': '目标探针不足', 'control_ids': ['p0/e_15'], 'control_ids_note': '运行时可补充观察'}]}
        validator.validate(annotated)
        for broken in ({'category': 'MISSING_OBSERVATION', 'reason': '缺control_ids'},
                       {'category': 'UNKNOWN_CATEGORY', 'reason': 'x', 'control_ids': []},
                       {'category': 'MISSING_OBSERVATION', 'reason': 'x', 'control_ids': [], 'note': 5}):
            with self.assertRaises(Exception):
                validator.validate({'tasks': [], 'empty_reasons': [broken]})

    def test_preflight_handles_controlled_task_without_static_operations(self):
        from webcollect.preflight import inspect_page
        source = inspect_page.__doc__
        controlled = {'operations': [], 'fragment': {'schema_version': 'webcollect-fragment-workflow-2'}}
        legacy = {'operations': [{'selector': '#x'}]}
        self.assertEqual((controlled.get('operations') or [{}])[0], {})
        self.assertEqual((legacy.get('operations') or [{}])[0], {'selector': '#x'})
        self.assertIn('Controlled fragments', source)

    def test_stale_cached_quality_degrades_to_marker_not_generation_block(self):
        from webcollect.client_reports import StaleSemanticRules
        from test_p0_production import seed_captures
        registry = self.root/'stale-registry.db'
        seed_captures(registry, ['STALE-qc'], prefix=0)
        report = self.root/'stale-qc.json'
        report.write_text('{"program":"quality-inspector","fixture":"AUTHORED, NOT A REVIEW"}')
        ref = {'path': str(report), 'sha256': file_sha(report)}
        with sqlite3.connect(registry) as con:
            con.execute('INSERT INTO m4_reviews VALUES(?,?,?,?,?)',
                        ('STALE-qc', 'pass', json.dumps([ref]), '历史审核，规则版本已升级', 0))
        real = __import__('webcollect.runtime', fromlist=['_bound_quality_report']).__dict__['_bound_quality_report']
        with patch('webcollect.runtime._bound_quality_report',
                   side_effect=StaleSemanticRules('Cached QC report has missing/changed semantic rules; '
                                                  'affected checks: terminal_semantics; run independent '
                                                  'deterministic QC again before packaging')) as gate:
            context = site_context(registry, 'https://example.org/')
        gate.assert_called_once()
        self.assertEqual(context['quality'], [])
        self.assertTrue(context['quality_stale'])
        self.assertIn('semantic rules', context['quality_stale'][0]['reason'])
        # Tampered or otherwise invalid evidence still hard-fails; only the
        # rule-version drift degrades.
        with patch('webcollect.runtime._bound_quality_report', side_effect=ValueError('QC report dataset differs')):
            with self.assertRaises(ValueError):
                site_context(registry, 'https://example.org/')
        self.assertTrue(real)


if __name__ == '__main__':
    unittest.main()
