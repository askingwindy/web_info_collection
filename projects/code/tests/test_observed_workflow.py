"""Controlled original-frame protocol tests; no external site/model/production."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image

from webcollect.batch_core import load_json, save_json
from webcollect.browser import fingerprint, prepare_action
from webcollect.observed_workflow import (CHECKS, DIFFERENCES, attach, compile_task, derive_capability,
    admit_capability, prepare_admission, review_schema, scope_pages, source_identity, static_identity, validate_derived_capability)
from webcollect.planning import _scoped_page_uris, object_sha256, validate_capability
from webcollect.task_admission import context, reference


URI = 'https://example.org/calculator'


class ObservedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.now = time.time()
        self.sources = source_identity()
        self.registry = self.root / 'CONTROLLED-original.sqlite3'
        con = sqlite3.connect(self.registry)
        con.execute('CREATE TABLE m4_tasks(scope_id TEXT,campaign_id TEXT,task_json TEXT)')
        con.close()
        manifest = self.root / 'CONTROLLED-history.json'; save_json(manifest, {'controlled': True})
        anchor = self.root / 'CONTROLLED-LATEST.md'; anchor.write_text('Controlled history anchor, not production')
        scope = {'schema_version': 'webcollect-task-history-scope-1', 'manifest': reference(manifest), 'formal_anchor': reference(anchor)}
        self.ctx = context(scope, [{'sample_id': 'CONTROLLED-old-1', 'origin': 'https://example.org', 'strategy_id': None}], self.registry)
        self.trace_ref, self.cap = self.make_trace('base')

    def frame(self, folder, name, number, *, target=0, left='', right='', focus=0,
              terminal=False, uri=URI, assertion=None):
        elements = []
        for i, label in enumerate(('长度', '宽度', '计算面积'), 1):
            elements.append({'element_id': 'e' + str(i), 'text': label, 'element_type': 'input' if i < 3 else 'button',
                             'native_role': 'input' if i < 3 else 'button', 'visible': True, 'enabled': True,
                             'inputable': i < 3, 'clickable': True, 'bbox': [i * 10, 10, i * 10 + 8, 20],
                             'state': 'focused' if focus == i else 'normal'})
        state = {'fixture': True, 'mode': 'synthetic', 'url': uri, 'title': '受控矩形面积',
                 'screen_resolution': [80, 60], 'elements': elements, 'scroll': [0, 0],
                 'values': [{'element_id': 'e1', 'input_type': 'text', 'value': left},
                            {'element_id': 'e2', 'input_type': 'text', 'value': right}],
                 'visible_text': '长度\n宽度\n计算面积\n' + left + '\n' + right + '\n' + ('矩形面积为42平方厘米' if terminal else '等待计算'),
                 'target': None, 'embedded_frames': []}
        if target:
            element = elements[target - 1]
            state['target'] = {'element_id': element['element_id'], 'coordinate': [target * 10 + 3, 15],
                'bbox': element['bbox'], 'text': element['text'], 'enabled': True, 'focused': focus == target,
                'hit_valid': True, 'visible_label_evidence': [{'kind': 'rendered_associated_label', 'text': element['text']}],
                'value': left if target == 1 else right if target == 2 else None}
        if assertion is not None:
            state['assertion_targets'] = assertion
        image = folder / (name + '.png'); Image.new('RGB', (80, 60), (number * 20, 30, 50)).save(image)
        state_path = folder / (name + '.state.json'); save_json(state_path, state)
        capture_path = folder / (name + '.capture.json')
        save_json(capture_path, {'fixture': True, 'screenshot_sha256': reference(image)['sha256'],
            'observer_sha256': self.sources['snapshot.js'], 'snapshot_source': 'browser_dom',
            'coordinate_space': 'screenshot_css_pixels', 'attempts': [{'dom_stable': True,
                'before_fingerprint': fingerprint(state), 'after_fingerprint': fingerprint(state)}]})
        return {'image': reference(image), 'state': reference(state_path), 'capture': reference(capture_path)}

    def make_trace(self, name):
        folder = self.root / name; folder.mkdir()
        intent = folder / 'intent.json'
        save_json(intent, {'schema_version': 'webcollect-observed-workflow-intent-1', 'mode': 'synthetic',
            'created_at': self.now - 100, 'site_uri': URI, 'site_category': '在线工具', 'app_name': '受控矩形工具',
            'instruction': '在「受控矩形工具」中填写长度六厘米、宽度七厘米，计算并核对矩形面积。',
            'task_type': ['填写表单', '数据查看'], 'final_result': '显示矩形面积为42平方厘米',
            'completion_judgement': '最终页面可见「矩形面积为42平方厘米」。'})
        settings = [dict(left='', right='', focus=0), dict(left='', right='', focus=1),
                    dict(left='6', right='', focus=1), dict(left='6', right='', focus=2),
                    dict(left='6', right='7', focus=2), dict(left='6', right='7', focus=3, terminal=True)]
        actions = [('click', 1, {}), ('type', 1, {'text': '6'}), ('click', 2, {}),
                   ('type', 2, {'text': '7'}), ('click', 3, {})]
        transitions = []
        for index, (action, target, arguments) in enumerate(actions):
            before = self.frame(folder, f'before-{index}', index, target=target, **settings[index])
            after = self.frame(folder, f'after-{index}', index + 1, **settings[index + 1])
            operation = {'action_type': action, 'selector': '#field' + str(target), 'index': 0,
                         'arguments': arguments, 'goal': '执行必要的受控步骤',
                         'rationale': '该步骤用于完成事前冻结的任务', 'expected': '页面显示相应真实变化'}
            actual, _ = prepare_action(load_json(before['state']['path']), operation)
            receipt = folder / f'execution-{index}.json'
            save_json(receipt, {'schema_version': 'webcollect-observed-workflow-transition-1', 'mode': 'synthetic',
                'operation': operation, 'before_frame_sha256': object_sha256(before),
                'after_frame_sha256': object_sha256(after), 'started_at': self.now - 60 + index * 2,
                'ended_at': self.now - 59 + index * 2, 'status': 'success',
                'state_preflight': {'matched': True, 'state_fingerprint': fingerprint(load_json(before['state']['path']))},
                'arguments': actual, 'source_identity': {k: self.sources[k] for k in ('browser.py', 'snapshot.js')}})
            transitions.append({'before': before, 'operation': operation, 'after': after, 'execution': reference(receipt)})
        path = folder / 'trace.json'
        save_json(path, {'schema_version': 'webcollect-observed-workflow-trace-1', 'mode': 'synthetic',
                        'intent': reference(intent), 'transitions': transitions,
                        'final_assertions': [{'visible_text': '矩形面积为42平方厘米'}]})
        proof = folder / 'capability-proof.txt'; proof.write_text('Controlled capability evidence')
        cap = {'schema_version': 'webcollect-site-capability-1', 'mode': 'synthetic',
            'capability_id': 'CONTROLLED-cap-' + name, 'version': '1', 'site_uri': URI,
            'site_category': '在线工具', 'observed_at': self.now - 120, 'expires_at': self.now + 1000,
            'status': 'ready', 'supported_actions': ['click', 'type', 'select', 'scroll', 'hotkey'],
            'task_families': ['observed-workflow'], 'evidence': [reference(proof)],
            'capability_scope': {'kind': 'exact-candidate-page', 'page_uris': [URI], 'sitewide': False},
            'capabilities': [{'page_uri': URI}], 'representative_pages': [{'uri': URI, 'chinese_ratio': 1}]}
        return reference(path), cap

    def altered(self, mutate):
        value = load_json(self.trace_ref['path']); mutate(value)
        path = self.root / ('altered-' + object_sha256(value)[:12] + '.json'); save_json(path, value)
        return reference(path)

    def review(self, capability=None, trace_ref=None, name='admission'):
        result = prepare_admission(capability or self.cap, trace_ref or self.trace_ref, self.ctx,
            self.root / name, mode='synthetic', producer_context_id='CONTROLLED-producer')
        packet = load_json(result['packet']['path']); review = load_json(result['review_template'])
        review.update(completed=True, reviewer={'kind': 'session_ai', 'id': 'CONTROLLED-reviewer', 'context_id': 'independent-control'},
                      reviewed_at=packet['created_at'], expires_at=packet['created_at'] + 60,
                      checks={k: 'PASS' for k in CHECKS}, reason='Controlled protocol fixture, not an actual review.')
        for item in review['step_observations']:
            item['observation'] = 'Controlled fixture checks original action and before/after pair.'
        for item in review['history_comparisons']:
            item.update(relation='DISTINCT', reason='Controlled whole-history comparison fixture.',
                        differences={k: 'Controlled evidence for ' + k for k in DIFFERENCES})
        return result['packet'], self.write_review(result['packet'], review, name)

    def write_review(self, packet_ref, review, name):
        packet = load_json(packet_ref['path']); value = deepcopy(review); value.pop('provenance', None)
        source = self.root / (name + '-source.json')
        save_json(source, {'schema_version': 'webcollect-controlled-task-review-source-1', 'fixture': True,
            'reviewer': value['reviewer'], 'packet_sha256': packet_ref['sha256'], 'completed': True,
            'reviewed_at': value['reviewed_at'], 'actual_external_model_call': False,
            'reviewed_frame_sha256': sorted({frame['image']['sha256'] for frame in packet['frames']}),
            'reviewed_tree_sha256': sorted({frame['state']['sha256'] for frame in packet['frames']}),
            'review_body_sha256': object_sha256(value)})
        value['provenance'] = reference(source)
        path = self.root / (name + '-review.json'); save_json(path, value)
        return reference(path)

    def test_original_transitions_compile_without_business_or_qc_claim(self):
        task = compile_task(self.cap, self.trace_ref)
        self.assertEqual(len(task['operations']), 5)
        self.assertEqual(task['required_actions'], [op['operation_id'] for op in task['operations']])
        self.assertFalse(task['observed_workflow']['QC_approval'])
        self.assertNotIn('workflow_admission', task)
        self.assertNotIn('deterministic_strategy', task)
        with self.assertRaisesRegex(ValueError, 'not received independent'):
            static_identity(task)

    def test_wait_padding_and_free_strategy_identity_are_rejected(self):
        bad = self.altered(lambda trace: trace['transitions'][0]['operation'].update(action_type='wait'))
        with self.assertRaisesRegex(ValueError, 'unsupported observation action'):
            compile_task(self.cap, bad)
        bad = self.altered(lambda trace: trace['transitions'][0]['operation'].update(strategy={'id': 'invented'}))
        with self.assertRaisesRegex(ValueError, 'invented strategy'):
            compile_task(self.cap, bad)
        bad = self.altered(lambda trace: trace['transitions'].pop())
        with self.assertRaisesRegex(ValueError, 'five actual explicit'):
            compile_task(self.cap, bad)

    def test_missing_execution_and_changed_arguments_cannot_compile(self):
        bad = self.altered(lambda trace: trace['transitions'][0]['execution'].update(sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'missing or changed'):
            compile_task(self.cap, bad)
        bad = self.altered(lambda trace: trace['transitions'][1]['operation']['arguments'].update(text='99'))
        with self.assertRaisesRegex(ValueError, 'exact successful original operation'):
            compile_task(self.cap, bad)

    def test_state_jump_and_wrong_original_label_are_rejected(self):
        trace = load_json(self.trace_ref['path'])
        bad = self.altered(lambda value: value['transitions'][1].update(before=trace['transitions'][0]['before']))
        with self.assertRaisesRegex(ValueError, 'unrecorded intermediate'):
            compile_task(self.cap, bad)
        bad = self.altered(lambda value: value['transitions'][0]['operation'].update(evidence={'target_label': '编造控件'}))
        with self.assertRaisesRegex(ValueError, 'control name differs'):
            compile_task(self.cap, bad)

    def test_real_mode_cannot_accept_controlled_original_frames(self):
        bad = self.altered(lambda trace: trace.update(mode='real'))
        intent = load_json(load_json(bad['path'])['intent']['path']); intent['mode'] = 'real'
        path = self.root / 'real-intent.json'; save_json(path, intent)
        value = load_json(bad['path']); value['intent'] = reference(path)
        path = self.root / 'real-trace.json'; save_json(path, value)
        with self.assertRaisesRegex(ValueError, 'controlled frame'):
            compile_task({**self.cap, 'mode': 'real'}, reference(path))

    def test_terminal_assertion_must_be_visible_and_not_already_held(self):
        bad = self.altered(lambda trace: trace.update(final_assertions=[{'visible_text': '看不到的结果'}]))
        with self.assertRaisesRegex(ValueError, 'not visible'):
            compile_task(self.cap, bad)
        bad = self.altered(lambda trace: trace.update(final_assertions=[{'visible_text': '长度'}]))
        with self.assertRaisesRegex(ValueError, 'already held'):
            compile_task(self.cap, bad)

    def test_numbers_use_original_visible_synchronized_output(self):
        trace = load_json(self.trace_ref['path']); final = load_json(trace['transitions'][-1]['after']['state']['path'])
        predicate = {'selector': '#result', 'numbers': {'count': 1, 'minimum': 42, 'maximum_exclusive': 43, 'integer': True}}
        target = {'selector': '#result', 'index': 0, 'visible': True, 'text': '矩形面积为42平方厘米', 'value': None}
        folder = self.root / 'number-final'; folder.mkdir()
        final_ref = self.frame(folder, 'final', 5, left='6', right='7', focus=3, terminal=True, assertion=[target])
        path = self.root / 'number-trace.json'
        save_json(path, {**trace, 'final_assertions': [predicate], 'final_observation': final_ref})
        task = compile_task(self.cap, reference(path))
        self.assertEqual(task['final_assertions'], [predicate])
        value = load_json(path); value['final_assertions'][0]['numbers']['minimum'] = 43
        value['final_assertions'][0]['numbers']['maximum_exclusive'] = 44
        failed = self.root / 'bad-number-trace.json'; save_json(failed, value)
        with self.assertRaisesRegex(ValueError, 'differs from original final'):
            compile_task(self.cap, reference(failed))

    def test_readonly_terminal_capture_cannot_hide_an_extra_change(self):
        trace = load_json(self.trace_ref['path']); folder = self.root / 'changed-final'; folder.mkdir()
        trace['final_observation'] = self.frame(folder, 'final', 5, left='99', right='7', focus=3, terminal=True)
        path = self.root / 'changed-final-trace.json'; save_json(path, trace)
        with self.assertRaisesRegex(ValueError, 'unrecorded state change'):
            compile_task(self.cap, reference(path))

    def test_independent_admission_requires_all_steps_history_and_four_differences(self):
        task = compile_task(self.cap, self.trace_ref); packet, review = self.review()
        admitted = attach(task, packet, review, self.ctx, mode='synthetic')
        self.assertTrue(static_identity(admitted))
        self.assertFalse(admitted['workflow_admission']['QC_approval'])
        original = load_json(review['path']); altered = deepcopy(original)
        altered['history_comparisons'][0]['differences']['operation_path'] = ''
        changed = self.write_review(packet, altered, 'missing-path')
        with self.assertRaisesRegex(ValueError, 'goal/path/state/result'):
            attach(task, packet, changed, self.ctx, mode='synthetic')

    def test_self_review_unknown_business_id_and_partial_review_cannot_admit(self):
        task = compile_task(self.cap, self.trace_ref); packet, review = self.review()
        value = load_json(review['path']); value['reviewer']['context_id'] = 'CONTROLLED-producer'
        changed = self.write_review(packet, value, 'self')
        with self.assertRaisesRegex(ValueError, 'independent reviewer'):
            attach(task, packet, changed, self.ctx, mode='synthetic')
        value = load_json(review['path']); value['registered_business_id'] = 'invented'
        changed = self.write_review(packet, value, 'invented')
        with self.assertRaisesRegex(ValueError, 'caller-selected identity'):
            attach(task, packet, changed, self.ctx, mode='synthetic')
        value = load_json(review['path']); value['step_observations'].pop()
        changed = self.write_review(packet, value, 'partial')
        with self.assertRaisesRegex(ValueError, 'every transition'):
            attach(task, packet, changed, self.ctx, mode='synthetic')

    def test_history_drift_and_expired_admission_stop_new_dispatch(self):
        task = compile_task(self.cap, self.trace_ref); packet, review = self.review()
        with self.assertRaisesRegex(ValueError, 'history changed'):
            attach(task, packet, review, {**self.ctx, 'customer_history_sha256': 'changed'}, mode='synthetic')
        with self.assertRaisesRegex(ValueError, 'expired'):
            attach(task, packet, review, self.ctx, mode='synthetic', now=self.now + 200)

    def test_model_schema_preserves_full_ordered_history_and_each_original_frame(self):
        from jsonschema import Draft202012Validator
        packet, review = self.review()
        value = load_json(review['path']); value.pop('provenance')
        schema = review_schema(packet)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)
        value['step_observations'].pop()
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(value)))

    def qualified_parent(self):
        original = deepcopy(self.cap)
        original['task_families'] = ['form-workflow']
        source = self.root / 'unqualified-parent.json'; save_json(source, original)
        decision = {'category': '在线工具', 'category_reason': 'Controlled fixture category',
                    'reason': 'Controlled qualification fixture',
                    'checks': {name: {'status': 'PASS', 'observation': 'Controlled observation'} for name in
                               ('visible_chinese', 'chinese_navigation_controls', 'category', 'compliance', 'access')}}
        response = self.root / 'qualification-response.json'; save_json(response, decision)
        qualified = {**original, 'version': 'qualified-1', 'reason': decision['reason']}
        qualified['site_qualification'] = {'schema_version': 'site-qualification-1', 'mode': 'synthetic',
            'site_uri': URI, 'site_category': '在线工具', 'status': 'ready', 'source_capability': reference(source),
            'response': reference(response), 'decision_sha256': object_sha256(decision), 'evidence': original['evidence'],
            'page_chinese_ratios': [1], 'preflight_blocked': False,
            'access': {'kind': 'public', 'source': 'Controlled fixture, no login'},
            'actual_external_model_call': False, 'capacity_verified': False, 'sample_qc_approval': False}
        path = self.root / 'qualified-parent.json'; save_json(path, qualified)
        return reference(path)

    def test_derived_capability_retains_parent_and_requires_real_independent_disposition(self):
        parent = self.qualified_parent(); before = Path(parent['path']).read_bytes()
        derived = derive_capability(parent, self.trace_ref)
        self.assertEqual(derived['status'], 'review_required')
        self.assertNotIn('site_qualification', derived)
        self.assertEqual(derived['task_families'], ['observed-workflow'])
        self.assertEqual(_scoped_page_uris(derived), {URI})
        with self.assertRaisesRegex(ValueError, 'manually promoted'):
            validate_capability({**derived, 'status': 'ready'})
        path = self.root / 'derived.json'; save_json(path, derived)
        packet, review = self.review(derived, name='derived-admission')
        ready = admit_capability(reference(path), packet, review, self.ctx, mode='synthetic')
        self.assertEqual(ready['status'], 'ready')
        validate_capability(ready)
        self.assertEqual(Path(parent['path']).read_bytes(), before)

    def test_old_exact_page_scope_is_not_relaxed_for_new_workflow_kind(self):
        changed = deepcopy(self.cap)
        changed['capability_scope']['page_uris'].append('https://example.org/unobserved')
        with self.assertRaisesRegex(ValueError, '精确页面能力范围'):
            validate_capability(changed, require_ready=False)
        changed = deepcopy(self.cap)
        changed['capability_scope'] = {'kind': 'observed-workflow-pages', 'page_uris': [URI], 'sitewide': False}
        changed['observed_workflow_trace'] = self.trace_ref
        changed['capabilities'].append({'page_uri': 'https://example.org/unobserved'})
        with self.assertRaisesRegex(ValueError, 'inventories and representatives'):
            validate_capability(changed, require_ready=False)

    def rewrite_frame(self, frame, mutate):
        value = load_json(frame['state']['path']); mutate(value)
        Path(frame['state']['path']).write_text(json.dumps(value, ensure_ascii=False))
        frame['state'] = reference(frame['state']['path'])
        return value

    def rewrite_receipt(self, transition):
        value = load_json(transition['execution']['path'])
        value.update(operation=transition['operation'], before_frame_sha256=object_sha256(transition['before']),
                     after_frame_sha256=object_sha256(transition['after']))
        before = load_json(transition['before']['state']['path'])
        value['arguments'] = prepare_action(before, transition['operation'])[0]
        value['state_preflight'] = {'matched': True, 'state_fingerprint': fingerprint(before)}
        Path(transition['execution']['path']).write_text(json.dumps(value, ensure_ascii=False))
        transition['execution'] = reference(transition['execution']['path'])

    def test_multi_page_scope_is_exactly_the_original_observed_transition_pages(self):
        trace = load_json(self.trace_ref['path']); other = 'https://example.org/calculator/details'
        for i, transition in enumerate(trace['transitions']):
            if i:
                self.rewrite_frame(transition['before'], lambda state: state.update(url=other))
            self.rewrite_frame(transition['after'], lambda state: state.update(url=other))
            self.rewrite_receipt(transition)
        path = self.root / 'multi-page-trace.json'; save_json(path, trace); bound = reference(path)
        with self.assertRaisesRegex(ValueError, 'left the actual observed'):
            compile_task(self.cap, bound)
        cap = deepcopy(self.cap)
        cap.update(capability_scope={'kind': 'observed-workflow-pages', 'page_uris': [URI, other], 'sitewide': False},
                   observed_workflow_trace=bound,
                   capabilities=[{'page_uri': uri} for uri in (URI, other)],
                   representative_pages=[{'uri': uri} for uri in (URI, other)])
        task = compile_task(cap, bound)
        self.assertEqual(task['initial_url'], URI)
        self.assertEqual(scope_pages(bound), [URI, other])
        self.assertEqual(_scoped_page_uris(cap), {URI, other})
        cap['capability_scope']['page_uris'].append('https://example.org/unobserved')
        with self.assertRaisesRegex(ValueError, 'actual observed original'):
            compile_task(cap, bound)

    def test_native_select_is_compiled_from_its_actual_recorded_control(self):
        trace = load_json(self.trace_ref['path']); transition = trace['transitions'][3]
        transition['operation'].update(action_type='select', arguments={'option': '七厘米'})
        def native_select(state):
            state['elements'][1].update(element_type='select', native_role='select', inputable=False)
        self.rewrite_frame(transition['before'], native_select)
        self.rewrite_frame(transition['after'], native_select)
        # The preceding/following snapshots describe the same original state;
        # selected target metadata alone must never simulate page continuity.
        self.rewrite_frame(trace['transitions'][2]['after'], native_select)
        self.rewrite_frame(trace['transitions'][4]['before'], native_select)
        self.rewrite_frame(trace['transitions'][4]['after'], native_select)
        for row in trace['transitions'][2:]:
            self.rewrite_receipt(row)
        path = self.root / 'select-trace.json'; save_json(path, trace)
        task = compile_task(self.cap, reference(path))
        self.assertEqual(task['operations'][3]['action_type'], 'select')
        self.assertEqual(task['operations'][3]['evidence']['target_label'], '宽度')

    def test_future_intent_and_changed_viewport_do_not_compile(self):
        trace = load_json(self.trace_ref['path']); intent = load_json(trace['intent']['path'])
        intent['created_at'] = self.now + 1
        path = self.root / 'future-intent.json'; save_json(path, intent)
        trace['intent'] = reference(path)
        path = self.root / 'future-trace.json'; save_json(path, trace)
        with self.assertRaisesRegex(ValueError, 'intent was not frozen'):
            compile_task(self.cap, reference(path))
        trace = load_json(self.trace_ref['path'])
        self.rewrite_frame(trace['transitions'][1]['before'], lambda state: state.update(screen_resolution=[90, 60]))
        path = self.root / 'viewport-trace.json'; save_json(path, trace)
        with self.assertRaisesRegex(ValueError, 'PNG/tree dimensions'):
            compile_task(self.cap, reference(path))

    def test_hidden_numeric_output_cannot_become_a_terminal_oracle(self):
        trace = load_json(self.trace_ref['path']); folder = self.root / 'hidden-number-final'; folder.mkdir()
        target = {'selector': '#result', 'index': 0, 'visible': True, 'text': '',
                  'value': '100 120 150 180 200', 'value_visible': False}
        trace['final_observation'] = self.frame(folder, 'final', 5, left='6', right='7', focus=3,
                                                terminal=True, assertion=[target])
        trace['final_assertions'] = [{'selector': '#result', 'numbers': {
            'count': 5, 'minimum': 100, 'maximum_exclusive': 201, 'integer': True}}]
        path = self.root / 'hidden-number-trace.json'; save_json(path, trace)
        with self.assertRaisesRegex(ValueError, 'hidden terminal control'):
            compile_task(self.cap, reference(path))

    def test_direct_entry_reads_real_history_path_api_before_rejecting_controlled_packet(self):
        """Exercise the actual path-only parser, not a permissive mocked reader."""
        from webcollect.observed_workflow import verify_entry
        from webcollect.task_generation import read_customer_history, bind_formal_history, _history_package_files
        delivery = self.root / 'controlled-delivery'; package = delivery / 'formal'
        sample = package / 'samples' / 'CONTROLLED-old-source'; sample.mkdir(parents=True)
        save_json(sample / 'annotation.json', {'sample_id': sample.name, 'steps': []})
        (package / 'README.md').write_text('Controlled historical population fixture; not a client delivery')
        save_json(package / 'site-list.json', {'schema_version': 'webcollect-site-list-1',
            'sites': [{'site_id': 'CONTROLLED-site', 'uri': 'https://example.org/previous',
                       'sample_ids': [sample.name]}],
            'samples': [{'sample_id': sample.name, 'site_id': 'CONTROLLED-site'}]})
        manifest = self.root / 'actual-path-history-set.json'
        save_json(manifest, {'schema_version': 'qc-cumulative-set-1', 'packages': [
            {'path': str(package), 'package_files_sha256': _history_package_files(package)}]})
        latest = delivery / 'LATEST.md'; latest.write_text('[Controlled formal fixture](formal/README.md)\n')
        actual_history, scope = read_customer_history(manifest)
        self.assertEqual([row['sample_id'] for row in actual_history], [sample.name])
        packet, review = self.review()
        task = attach(compile_task(self.cap, self.trace_ref), packet, review, self.ctx, mode='synthetic')
        with patch('webcollect.task_generation.FORMAL_LATEST_PATH', latest):
            scope = bind_formal_history(scope)
            plan = {'tasks': [task], 'observed_workflow_generation': {'mode': 'real',
                'source_identity': source_identity(), 'history_scope': scope}}
            # Reaching this mode-specific refusal proves the genuine history
            # parser/anchor gate accepted the original Path argument first.
            with self.assertRaisesRegex(ValueError, 'real/controlled admission mode mismatch'):
                verify_entry(plan, self.registry, self.root / 'capture')


if __name__ == '__main__':
    unittest.main()
