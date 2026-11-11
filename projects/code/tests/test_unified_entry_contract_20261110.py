"""One isolated entry-to-runtime contract with real gateway parsing and persistence.

Only browser IO, external account availability and provider HTTP are synthetic. No success/save,
postprocess, candidate claim, protocol normalization or RuntimeStore is patched.
"""
import asyncio
from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

import test_candidate_entry_engineering as entry_tests
from test_model_provider_protocols import StubOpener
from webcollect.batch_core import BatchLedger, file_sha, load_json, save_json
from webcollect.closing_policy import completion_delivery_decision
from webcollect.collect_runtime import runtime_scope
from webcollect.model_gateway import ModelGateway
from webcollect.plan_protocol import ENDING_POLICY as COMPLETE_VERSION
from webcollect.runtime import RuntimeStore


class UnifiedEntryContract(unittest.IsolatedAsyncioTestCase):
    async def test_claim_v6_gateway_execution_derivation_and_formal_pending_receipt(self):
        f = entry_tests.EntryEngineering('test_entry_cli_to_original_save_and_same_page')
        f._callCleanup = unittest.TestCase._callCleanup.__get__(f)
        f.setUp()
        self.addCleanup(f.doCleanups)
        # Frozen task dispatch profile must override modern-plan default low.
        f.ledger.config['model'].update(provider='glm', supports_vision=True,
            image_tokens_per_image=1200, request_overhead_tokens=128, reasoning_effort='high')
        # A new disposable ledger owns this GLM config; never mutate a frozen DB.
        f.ledger = BatchLedger(f.root / 'unified-glm.sqlite3', f.ledger.config, initialize=True)
        f.cfg_path = f.root / 'unified-glm-config.json'
        save_json(f.cfg_path, f.ledger.config)
        f.surface.state['capture_readiness'] = {
            'schema_version': 'webcollect-capture-readiness-1',
            'document_ready': 'complete', 'fonts_ready': True, 'images_ready': True}
        # The declared check region is backed by the synthetic paragraph's
        # captured selector, just as in the complete-goal session fixtures.
        # The current strategy-1 completion route requires a real input+submit
        # causality chain: one submit control, one shared form, and a result
        # region whose text appears only after the submission.
        state = f.surface.state
        state['elements'].append({'element_id': 'submit-control', 'text': '计算',
            'native_role': 'button', 'element_type': 'button', 'bbox': [10, 200, 210, 240],
            'visible': True, 'enabled': True, 'clickable': True, 'inputable': False,
            'parent_id': 'root', 'scrollable': False, 'state': 'default'})
        state['capture_controls'].append({'element_id': 'submit-control', 'selector': '#submit-control',
                                          'index': 0, 'tag': 'button', 'input_type': 'submit',
                                          'form_selector': '#calculator'})
        for binding in state['capture_controls']:
            if binding['element_id'] in ('control-0', 'control-1'):
                binding['form_selector'] = '#calculator'
        result_binding = next(b for b in state['capture_controls'] if b['element_id'] == 'control-2')
        result_binding.update(selector='html > body > main > p', form_selector='#calculator',
                              result_region_selector='#actual-result')
        original_capture = f.capture
        async def captured(*args, **kwargs):
            import base64
            from webcollect.browser import CAPTURE_VERSION, fingerprint, stability_pair
            frame = await original_capture(*args, **kwargs)
            state, png = frame['state'], frame['png']
            # The current action-scoped dispatch proof needs per-element hit
            # samples; the synthetic surface is fully visible and unobstructed.
            state['geometry_witnesses'] = [{'element_id': e['element_id'],
                'samples': [{'point': [i % 3, i // 3], 'ancestor': True} for i in range(9)]}
                for e in state['elements']]
            proof = stability_pair(state, state, png, png)
            encoded = base64.b64encode(png).decode('ascii')
            attempt = frame['capture']['attempts'][0]
            attempt.update(snapshot_before=state, snapshot_after=state, snapshot_final=state,
                original_png_base64=encoded, comparison_png_base64=encoded,
                stability=proof, final_stability=proof,
                dom_stable=proof['full_dom_stable'], before_fingerprint=fingerprint(state),
                after_fingerprint=fingerprint(state))
            frame['capture']['schema_version'] = CAPTURE_VERSION
            frame['html'] = await args[0].content()
            return frame
        f.capture = captured
        count = 12  # intentionally above both the preferred eight and old ten
        executed = f.surface.execute_action
        def browser_action(kind, arguments):
            executed(kind, arguments)
            if kind == 'click':
                from pathlib import Path as _P
                _P('/tmp/unified-clicks.jsonl').open('a').write(json.dumps(arguments) + '\n')
            if kind == 'click' and (arguments or {}).get('y', 0) >= 200:
                # The submission produces the result text; before it, the page
                # never shows the declared endpoint content.
                f.surface.state['visible_text'] += '\n当前终点内容'
                result_row = next(e for e in f.surface.state['elements']
                                  if e['element_id'] == 'control-2')
                result_row['text'] += '\n当前终点内容'
                from pathlib import Path as _P
                _P('/tmp/unified-submit-state.json').write_text(json.dumps(
                    {'visible_text': f.surface.state['visible_text'],
                     'result_text': result_row['text']}, ensure_ascii=False))
        f.surface.execute_action = browser_action
        opener = StubOpener()
        original = ModelGateway.call_tool
        wire_tools = []
        def provider_response(gateway, job, purpose, text, tools, **kwargs):
            gateway._session_id = kwargs.get('attempt_id')
            gateway._credential = 'CONTROLLED_UNUSED'
            prompt = json.loads(text)
            prompt['system'] = kwargs['system']
            f.prompts.append(prompt)
            wire_tools.append(tools)
            name = 'submit_plan'
            form_steps = [
                {'action': 'click', 'target': {'text': '查询条件'},
                 'expected': {'kind': 'focused', 'text': '查询条件'}},
                {'action': 'hotkey', 'keys': ['ctrl', 'a'],
                 'expected': {'kind': 'text_selected', 'text': '10'}},
                {'action': 'type', 'target': {'text': '查询条件'}, 'value': '20',
                 'expected': {'kind': 'value', 'text': '20'}},
                {'action': 'click', 'target': {'text': '确认查询'},
                 'expected': {'kind': 'focused', 'text': '确认查询'}},
                {'action': 'hotkey', 'keys': ['ctrl', 'a'],
                 'expected': {'kind': 'text_selected', 'text': '10'}},
                {'action': 'type', 'target': {'text': '确认查询'}, 'value': '30',
                 'expected': {'kind': 'value', 'text': '30'}},
                {'action': 'click', 'target': {'text': '计算'},
                 'expected': {'kind': 'visible_text', 'text': '当前终点内容'}}]
            scrolls = [{'action': 'scroll', 'direction': 'down',
                        'expected': {'kind': 'scroll_changed', 'text': '滚动后位置改变'}}
                       for _ in range(count - len(form_steps))]
            arguments = {
                'goal': '输入两个查询数值并提交，核对当前终点内容',
                'checks': [{'field': '终点事实', 'page': 'p0', 'region': '正文',
                            'visible_text': '当前终点内容'}],
                'steps': [dict(step, purpose='完成本次输入、提交并核对终点内容',
                               rationale='原目标要求输入并提交后核对真实结果，本步是其中的必要动作。',
                               expected_result='当前操作得到可见反馈，最终核对本次提交后的终点内容。')
                          for step in form_steps + scrolls],
            }
            assistant = {'role': 'assistant', 'content': None,
                'reasoning_content': 'opaque-unified-private',
                'tool_calls': [{'id': f'unified-{len(f.prompts)}', 'type': 'function',
                    'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)}}]}
            opener.raw['choices'] = [{'finish_reason': 'tool_calls', 'message': assistant}]
            return original(gateway, job, purpose, text, tools, **kwargs)
        original_message = ModelGateway.call_message
        def provider_message(gateway, job, purpose, text, schema, **kwargs):
            # Branch round: the placeholder endpoint is only closable through an
            # explicit finish_result naming catalog evidence from the same run.
            gateway._session_id = kwargs.get('attempt_id')
            gateway._credential = 'CONTROLLED_UNUSED'
            prompt = json.loads(text)
            prompt['system'] = kwargs['system']
            f.prompts.append(prompt)
            catalog = prompt.get('result_evidence_catalog') or []
            if not any(o.get('choice') == 'finish_result' for o in prompt.get('options') or []):
                from pathlib import Path as _P
                _P('/tmp/unified-branch-debug.json').write_text(json.dumps(
                    {'options': prompt.get('options'), 'catalog': catalog,
                     'branch_reason': prompt.get('branch_reason'),
                     'current_step': prompt.get('current_step'),
                     'last_actual_result': prompt.get('last_actual_result'),
                     'executed_steps': prompt.get('executed_steps'),
                     'attempt_facts': prompt.get('attempt_facts'),
                     'prompt_keys': sorted(prompt)}, ensure_ascii=False, indent=2))
                reply = {'choice': 'stop', 'decision_summary': '调试：无完成选项'}
            else:
                source = next(row for row in catalog if '当前终点内容' in row['quote'])
                reply = {'choice': 'finish_result',
                         'decision_summary': '原目标检查已有本次提交后的实际输出',
                         'result_answer': {'check_answers': [{'check_index': 0,
                                                              'evidence_ids': [source['evidence_id']]}]}}
            opener.raw = {'id': 'unified-branch-response', 'model': 'glm-5.3-flash',
                          'choices': [{'finish_reason': 'stop', 'message': {
                              'role': 'assistant', 'content': json.dumps(reply, ensure_ascii=False)}}],
                          'usage': {'prompt_tokens': 60, 'completion_tokens': 15,
                                    'prompt_tokens_details': {'cached_tokens': 0}}}
            return original_message(gateway, job, purpose, text, schema, **kwargs)
        args = f.cli_args() + ['--first-plan-effort', 'high', '--branch-effort', 'high']
        def invoke():
            with redirect_stdout(io.StringIO()) as output:
                entry_tests.main(args)
                return json.loads(output.getvalue())
        with (patch.dict('os.environ', {'CONTROLLED_UNUSED_KEY': 'offline-test-only'}),
              patch('webcollect.key_health.pool_available', return_value=True),
              f.io_boundaries(mock_gateway=False, legacy_protocol=False),
              patch.object(ModelGateway, 'call_tool', new=provider_response),
              patch.object(ModelGateway, 'call_message', new=provider_message),
              patch('webcollect.model_gateway.socket.getaddrinfo', return_value=[('CONTROLLED_DNS',)]),
              patch('urllib.request.build_opener', return_value=opener)):
            result = (await asyncio.to_thread(invoke))[0]
        failures = [load_json(p) for p in f.output.rglob('failure.json')]
        request_errors = []
        with f.ledger.connect() as con:
            request_errors = [tuple(row) for row in con.execute('SELECT state,error FROM model_requests')]
        self.assertEqual(result['state'], 'succeeded', (result, failures, request_errors))
        self.assertEqual(result['QC'], 'pending_review')
        self.assertEqual(len(f.gotos), 1)
        self.assertEqual(len(f.contexts), 1)
        self.assertEqual(len(f.surface.executed), count)
        first = f.prompts[0]
        self.assertIsNone(first['planning_range']['cumulative_maximum'])
        self.assertIsNone(first['planning_range']['initial_complete_path_maximum'])
        self.assertEqual(first['planning_range']['initial_complete_path_preferred_maximum'], 8)
        schema = wire_tools[0][0]['function']['parameters']
        self.assertEqual(schema['properties']['steps']['minItems'], 5)
        self.assertNotIn('maxItems', schema['properties']['steps'])
        self.assertTrue(opener.calls)
        for index, request in enumerate(opener.calls):
            payload = json.loads(request.data)
            self.assertEqual(payload['reasoning_effort'], 'high')
            # Assert the final HTTP body as well as the gateway input: a clean
            # task/prompt is insufficient if the adapter adds an old ceiling.
            self.assertEqual(payload['messages'][0]['role'], 'system')
            for system in (f.prompts[index]['system'], payload['messages'][0]['content']):
                self.assertNotRegex(system, r'累计(?:最多|不得超过|不能超过)\s*(?:8|10)\s*(?:步|个)')
                self.assertNotRegex(system, r'(?:无法|不能|不在|超过)[^。；\n]{0,20}5[–—~-]8[^。；\n]{0,35}(?:stop|停止|放弃)')
                self.assertNotRegex(system, r'5[–—~-]8[^。；\n]{0,25}(?:无法完成|不能完成)[^。；\n]{0,20}(?:stop|停止|放弃)')
            transmitted = next((tool['function']['parameters'] for tool in payload.get('tools') or []
                               if tool['function']['name'] == 'submit_plan'), None) if index == 0 else None
            if transmitted is not None:
                self.assertEqual(transmitted['properties']['steps']['minItems'], 5)
                self.assertNotIn('maxItems', transmitted['properties']['steps'])
        annotations = list(f.output.glob('*/execution/capture/samples/*/annotation.json'))
        self.assertEqual(len(annotations), 1)
        sample = annotations[0].parent
        annotation = load_json(annotations[0])
        self.assertEqual(annotation['completion_status'], 'success')
        self.assertEqual(len([s for s in annotation['steps'] if s['action']['action_type'] != 'complete']), count)
        self.assertIn('当前终点内容', annotation['final_result'])
        self.assertNotIn('opaque-unified-private', annotations[0].read_text())
        capture = sample.parent.parent
        saved = load_json(capture / 'evidence' / sample.name / 'saved_sample.json')
        self.assertEqual(saved['raw_execution']['effective_steps'], count)
        self.assertEqual(saved['raw_execution']['collection_ending']['protocol'], COMPLETE_VERSION)
        self.assertTrue(completion_delivery_decision(annotation, saved['raw_execution'])['delivery_eligible'])
        self.assertEqual(saved['sample_files_sha256']['annotation.json'], file_sha(annotations[0]))
        store = RuntimeStore(f.registry, runtime_scope(capture))
        attempts = store.attempt_ledger()['attempts']
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]['status'], 'collected_pending_review')
        self.assertEqual(attempts[0]['attempt_id'], saved['attempt_id'])
        self.assertEqual(attempts[0]['sample_id'], saved['sample_id'])
        binding = f.pool.get_claim(f.claim['claim_id'])['binding']
        self.assertEqual(binding['attempt_id'], saved['attempt_id'])
        with f.ledger.connect() as con:
            states = [row[0] for row in con.execute('SELECT state FROM model_requests')]
        self.assertEqual(states, ['succeeded'] * len(opener.calls))
