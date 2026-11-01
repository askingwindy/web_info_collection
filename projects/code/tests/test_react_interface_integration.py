"""Cross-path regressions with temporary pools, fake pages and local gateways only."""
import asyncio
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_candidate_entry_engineering as entry_tests
import test_model_provider_protocols as provider_tests
import test_react_native as native_tests
from webcollect.batch_core import BatchLedger, load_json, file_sha
from webcollect.model_gateway import ModelGateway
from webcollect.postprocess import process, session_record
from webcollect.react_session import ReactSession, build_url_task, react_chooser


class ReactInterfaceIntegration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = native_tests.NativeSessionTests('test_native_tool_round_trip_filters_permissions_keeps_private_history')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def http_fixture(self):
        f = provider_tests.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        f.setUp()
        self.addCleanup(f.doCleanups)
        config = f.config('glm', vision=True)
        ledger = BatchLedger(f.root / 'integration.sqlite3', config, initialize=True)
        return f, ledger

    async def test_last_invalid_http_response_exhausts_attempt_as_budget_without_unknown(self):
        f, ledger = self.http_fixture()
        n = self.fixture
        n.task = build_url_task(url=n.page.url, task_version='cap', budgets={'max_model_calls': 1})
        f.opener.raw['choices'] = [{'finish_reason': 'tool_calls', 'message': {
            'role': 'assistant', 'tool_calls': [{'id': 'invalid-last', 'type': 'function',
                'function': {'name': 'undeclared', 'arguments': '{}'}}]}}]
        chooser = react_chooser(ledger, n.task, 'original-capped-attempt')
        session = n.session(chooser, name='http-cap')
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'budget', result)
        self.assertFalse(result['unknown'])
        self.assertNotEqual(result['failure_class'], 'program')
        self.assertEqual(session.used['max_model_calls'], 1)
        self.assertEqual(len(f.opener.calls), 1)
        self.assertEqual(n.surface.executed, [])

    async def test_original_attempt_http_count_includes_other_job_purpose_before_new_decision(self):
        f, ledger = self.http_fixture()
        n = self.fixture
        n.task = build_url_task(url=n.page.url, task_version='cap', budgets={'max_model_calls': 1})
        job = ledger.claim('original-request', job_id=ledger.enqueue('original-request', {'fixture': True}))
        message = {'role': 'assistant', 'tool_calls': [{'id': 'prior', 'type': 'function',
            'function': {'name': 'observe', 'arguments': '{}'}}]}
        f.opener.raw['choices'] = [{'finish_reason': 'tool_calls', 'message': message}]
        gateway = ModelGateway(ledger)
        gateway.call_tool(job, 'original-purpose', 'original text', [{'type': 'function',
            'function': {'name': 'observe', 'parameters': {'type': 'object'}}}],
            system='controlled policy', attempt_id='shared-attempt', max_requests=1)
        ledger.finish(job, result={'fixture': True})
        chooser = react_chooser(ledger, n.task, 'shared-attempt')
        session = n.session(chooser, name='prior-http')
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'budget', result)
        self.assertEqual(chooser.requests_used(), 1)
        self.assertEqual(session.used['max_decisions'], 0)
        self.assertEqual(len(f.opener.calls), 1)
        with ledger.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM jobs WHERE kind='react-native-decision'").fetchone()[0], 0)

    async def test_duplicate_dispatch_reference_keeps_derived_frames_and_receipt_consistent(self):
        n = self.fixture
        session, evidence, _ = n.recorded([native_tests.scroll('查看页面下方内容'), native_tests.scroll(), native_tests.finish()])
        await session.run()
        record = session_record(evidence / 'raw')
        record['trajectory'].append(deepcopy(record['trajectory'][-1]))
        before = file_sha(evidence / 'raw/raw-receipt.json')
        with patch('webcollect.postprocess.session_record', return_value=record):
            result = process(evidence, n.root / 'duplicate-delivery' / n.ids['sample_id'], n.ids, n.manifest)
        self.assertEqual(result['status'], 'derived_saved', result)
        annotation = load_json(n.root / 'duplicate-delivery' / n.ids['sample_id'] / 'annotation.json')
        self.assertEqual(len(annotation['steps']), 3)
        self.assertEqual(load_json(evidence / 'capture_summary.json')['capture_count'], 3)
        self.assertEqual(load_json(evidence / 'step_003.json')['operation']['action_type'], 'complete')
        self.assertFalse((evidence / 'step_004.json').exists())
        self.assertEqual(file_sha(evidence / 'raw/raw-receipt.json'), before)

    async def test_unknown_last_request_is_not_hidden_by_budget_and_does_not_reopen_entry(self):
        f, ledger = self.http_fixture()
        n = self.fixture
        n.task = build_url_task(url=n.page.url, task_version='unknown-cap', budgets={'max_model_calls': 1})
        f.opener.error = TimeoutError('CONTROLLED dispatched outcome unknown')
        chooser = react_chooser(ledger, n.task, 'unknown-original')
        first = n.session(chooser, name='first-unknown')
        result = await first.run()
        self.assertTrue(result['unknown'])
        restarted = react_chooser(ledger, n.task, 'unknown-original')
        second = n.session(restarted, name='second-unknown')
        with patch.object(n.page, 'goto', side_effect=AssertionError('unresolved original must not navigate')):
            result = await second.run()
        self.assertTrue(result['unknown'], result)
        self.assertEqual(result['stop_reason'], 'blocked')
        self.assertEqual(second.used['max_decisions'], 0)
        self.assertEqual(second.used['max_model_calls'], 1)
        self.assertEqual(second.observations, [])
        self.assertEqual(len(f.opener.calls), 1)

    async def test_unrecorded_dispatched_action_cannot_be_exported_as_a_complete_fragment(self):
        n = self.fixture
        session, evidence, _ = n.recorded([native_tests.scroll('查看页面下方内容'), native_tests.finish()])
        await session.run()
        record = session_record(evidence / 'raw')
        record['terminal']['actual_actions'] += 1
        with patch('webcollect.postprocess.session_record', return_value=record):
            result = process(evidence, n.root / 'gap-delivery' / n.ids['sample_id'], n.ids, n.manifest)
        self.assertEqual(result['status'], 'processing_failed', result)
        self.assertFalse((n.root / 'gap-delivery').exists())


class EntryGatewayIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_claimed_page_to_mock_http_adapter_history_and_pending_save(self):
        f = entry_tests.EntryEngineering('test_entry_cli_to_original_save_and_same_page')
        f.setUp()
        self.addCleanup(f.doCleanups)
        actual = ModelGateway.call_tool
        histories, image_paths = [], []
        opener = provider_tests.StubOpener()
        def controlled(gateway, job, purpose, text, tools, **kwargs):
            gateway._credential = 'CONTROLLED_UNUSED'  # fake gateway key; no credential lookup
            payload = json.loads(text)
            f.prompts.append(deepcopy(payload))
            build = f.decisions.pop(0)
            decision = build(payload)
            if decision['tool_call']['name'] == 'finish':
                arguments = decision['tool_call']['arguments']
                arguments.pop('short_flow'); arguments.pop('short_flow_reason')
                arguments['evidence_refs'] = [payload['observation']['observation_id']]
            assistant = native_tests.native(lambda _: decision, 'integrated-' + str(len(f.prompts)))(payload)['assistant_message']
            histories.append(deepcopy(kwargs['history']))
            image_paths.append(kwargs['images'][0])
            opener.raw['choices'] = [{'finish_reason': 'tool_calls', 'message': assistant}]
            return actual(gateway, job, purpose, text, tools, **kwargs)
        # Keep the real consumer/runtime/session, and replace only external page
        # IO and the provider's in-memory HTTP response (no socket is opened).
        with (f.io_boundaries(), patch.object(ModelGateway, 'call_tool', new=controlled),
              patch('webcollect.model_gateway.socket.getaddrinfo', return_value=[('CONTROLLED_DNS',)]),
              patch('urllib.request.build_opener', return_value=opener)):
            def cli():
                with redirect_stdout(io.StringIO()) as output:
                    entry_tests.main(f.cli_args())
                    return json.loads(output.getvalue())
            result = await asyncio.to_thread(cli)
        self.assertEqual(result[0]['state'], 'succeeded', (result, [load_json(path) for name in ('terminal.json', 'failure.json') for path in f.output.rglob(name)]))
        self.assertEqual(result[0]['QC'], 'pending_review')
        self.assertEqual(len(f.gotos), 1)
        self.assertEqual(len(f.contexts), 1)
        f.contexts[0].new_page.assert_awaited_once()
        self.assertEqual(len(histories), 5)
        for index, history in enumerate(histories):
            self.assertEqual([m['role'] for m in history], ['user', 'assistant', 'tool'] * index)
            for offset in range(index):
                assistant, tool = history[3 * offset + 1:3 * offset + 3]
                self.assertEqual(assistant['tool_calls'][0]['id'], tool['tool_call_id'])
                self.assertEqual(assistant['reasoning_content'], 'opaque-protocol-private')
        entry_pngs = list(f.root.rglob('first.png'))
        self.assertEqual(len(entry_pngs), 1)
        self.assertEqual(Path(image_paths[0]).read_bytes(), entry_pngs[0].read_bytes())
        self.assertTrue(all(prompt['requested_goal'] is None for prompt in f.prompts))
        annotations = list(f.output.glob('*/execution/capture/samples/*/annotation.json'))
        self.assertEqual(len(annotations), 1)
        annotation = load_json(annotations[0])
        self.assertEqual(len(annotation['steps']), 7)  # six actual primitives plus complete
        self.assertFalse(annotation.get('short_flow', False))
        self.assertNotIn('opaque-protocol-private', annotations[0].read_text())
        with f.ledger.connect() as con:
            requests = [json.loads(row[0]) for row in con.execute('SELECT request_json FROM model_requests')]
        self.assertEqual(len(requests), 5)
        self.assertTrue(all(request['http_dispatch'] is True for request in requests))
        self.assertEqual(len(opener.calls), 5)  # simulated wire dispatches only
        for index, request in enumerate(opener.calls):
            payload = json.loads(request.data)
            self.assertEqual(payload['reasoning_effort'], 'max')
            self.assertEqual([message['role'] for message in payload['messages']],
                             ['system'] + ['user', 'assistant', 'tool'] * index + ['user'])
