"""Offline transport integration; mock persisted usage, never model approval."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_document_text_qc as support
from quality_inspector import document_text_qc as lane, document_request_dedup as transport
from quality_inspector import delivery_pipeline as pipeline
from test_document_request_dedup import long_prompt


class DocumentTransportTests(unittest.TestCase):
    def setUp(self):
        self.case = support.DocumentTextQCTests()
        self.case.setUp(); self.addCleanup(self.case.doCleanups)
        self.root = self.case.root
        prompt = long_prompt()
        document = self.case.case.dataset / '合成方式说明.md'
        document.write_text(document.read_text() + '\n```text\n' + prompt + '\n```\n')
        with patch('urllib.request.build_opener', side_effect=AssertionError('No network permitted')):
            self.case.parent(readonly_claim={'fixture_notice': 'CONTROLLED transport test only'})
        self.facts = self.root / 'facts.json'
        self.facts.write_text(json.dumps({'prompt_stages': [{'stages': {'planning': {
            'mode': 'model', 'prompt': prompt}}}]}, ensure_ascii=False, indent=2))
        self.ledger = self.case.ledger('transport')
        self.document = lane.prepare(self.ledger, self.case.parent_receipt, self.case.parent_status,
            self.root / 'document-prepare', supporting_files=[self.facts])
        self.source_bytes = {Path(module.__file__): Path(module.__file__).read_bytes()
                             for module in (lane, pipeline.ai_worker)}
        self.original_receipt = Path(self.document['receipt']).read_bytes()

    def prepare(self):
        return transport.prepare_transport(self.document['receipt'], self.root / 'transport-prepare')

    def run_transport(self, prepared, gateway=None):
        with patch('urllib.request.build_opener', side_effect=AssertionError('No network permitted')):
            return transport.run_transport(prepared['receipt'], self.root / 'transport-run',
                gateway_factory=gateway or self.case.case.PassingProtocolGateway)

    def rows(self):
        return transport._transport_requests(self.ledger, self.document['job_id'])

    def test_one_compact_request_bound_usage_and_original_lane_bytes_unchanged(self):
        prepared = self.prepare()
        self.assertEqual(prepared['external_model_calls'], 0)
        self.assertEqual(self.rows(), [])
        self.assertGreater(prepared['request']['metrics']['replacement_count'], 0)
        self.assertTrue(prepared['request']['content_sources'][0]['content_id'].startswith('sha256:'))
        result = self.run_transport(prepared)
        self.assertEqual(result['document_review_status'], 'AI_PASS')
        self.assertFalse(result['release_ready'])
        self.assertEqual(len(self.rows()), 1)
        original, schema = lane._request(self.ledger.get(self.document['job_id'])['payload'])
        persisted = json.loads(self.rows()[0]['request_json'])
        restored = transport.restore_request(persisted['text'], expected_sha256=transport._sha(original))
        self.assertEqual(restored.encode(), original.encode())
        self.assertEqual(persisted['schema'], schema)
        self.assertEqual(persisted['images'], [])
        self.assertEqual(json.loads(persisted['text'])['documents'], json.loads(original)['documents'])
        self.assertEqual(result['requests'][0]['request_id'], self.rows()[0]['id'])
        self.assertEqual(result['requests'][0]['input_tokens'], 100)
        self.assertEqual(result['requests'][0]['output_tokens'], 20)
        self.assertEqual(result['requests'][0]['reasoning_tokens'], 'UNKNOWN')
        self.assertFalse(result['requests'][0]['reasoning_added_to_output'])
        self.assertEqual(Path(self.document['receipt']).read_bytes(), self.original_receipt)
        self.assertTrue(all(path.read_bytes() == before for path, before in self.source_bytes.items()))
        lane.verify(self.document['receipt'])
        with self.assertRaisesRegex(ValueError, 'already dispatched'):
            self.run_transport(prepared)
        self.assertEqual(len(self.rows()), 1)

    def test_previous_claim_or_any_previous_request_cannot_prepare_transport(self):
        job = self.ledger.claim(lane.KIND, job_id=self.document['job_id'])
        self.ledger.finish(job, 'queued')
        with self.assertRaisesRegex(ValueError, 'never-claimed'):
            self.prepare()
        self.assertFalse((self.root / 'transport-prepare').exists())

    def test_reserved_and_unknown_requests_are_never_resent_or_counted_zero(self):
        prepared = self.prepare()
        class UnknownGateway:
            def __init__(inner, ledger): inner.ledger = ledger
            def call(inner, job, purpose, text, schema, **kwargs):
                ref = inner.ledger.reserve_request(job, purpose + ':CONTROLLED-UNKNOWN', 0,
                    request_json={'text': text, 'schema': schema, 'images': []})
                inner.ledger.settle_request(ref['id'], state='unknown', error='CONTROLLED interrupted request')
                raise RuntimeError('CONTROLLED uncertain outcome')
        result = self.run_transport(prepared, UnknownGateway)
        self.assertEqual(result['document_review_status'], 'AI_REVIEW_REQUIRED')
        self.assertEqual(result['requests'][0]['input_tokens'], 'UNKNOWN')
        self.assertTrue(result['requests'][0]['usage_missing'])
        with self.assertRaisesRegex(ValueError, 'already dispatched'):
            self.run_transport(prepared)
        self.assertEqual(len(self.rows()), 1)

    def test_second_binding_and_tampered_receipt_are_rejected_before_dispatch(self):
        prepared = self.prepare()
        with self.assertRaisesRegex(ValueError, 'already has'):
            transport.prepare_transport(self.document['receipt'], self.root / 'other-transport')
        path = Path(prepared['receipt']); value = json.loads(path.read_text())
        value['request']['binding']['wire_text_sha256'] = '0' * 64
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'receipt or implementation'):
            self.run_transport(prepared)
        self.assertEqual(self.rows(), [])

    def test_unsettled_reserved_request_blocks_rerun_and_retains_unknown_usage(self):
        prepared = self.prepare()
        class ReservedGateway:
            def __init__(inner, ledger): inner.ledger = ledger
            def call(inner, job, purpose, text, schema, **kwargs):
                inner.ledger.reserve_request(job, purpose + ':CONTROLLED-RESERVED', 0,
                    request_json={'text': text, 'schema': schema, 'images': []})
                raise RuntimeError('CONTROLLED interrupted before settlement')
        result = self.run_transport(prepared, ReservedGateway)
        self.assertEqual(result['requests'][0]['state'], 'reserved')
        self.assertEqual(result['requests'][0]['input_tokens'], 'UNKNOWN')
        with self.assertRaisesRegex(ValueError, 'already dispatched'):
            self.run_transport(prepared)
        self.assertEqual(len(self.rows()), 1)

    def test_plaintext_cannot_be_reserved_as_the_compact_wire(self):
        prepared = self.prepare()
        class PlaintextGateway:
            def __init__(inner, ledger): inner.ledger = ledger
            def call(inner, job, purpose, text, schema, **kwargs):
                original, _ = lane._request(job['payload'])
                return inner.ledger.reserve_request(job, purpose + ':CONTROLLED-WRONG', 0,
                    request_json={'text': original, 'schema': schema, 'images': []})
        result = self.run_transport(prepared, PlaintextGateway)
        self.assertEqual(result['document_review_status'], 'AI_REVIEW_REQUIRED')
        self.assertEqual(self.rows(), [])

    def test_status_and_prepare_never_construct_gateway_or_read_credentials(self):
        with patch('webcollect.model_gateway.ModelGateway', side_effect=AssertionError('No model construction')), \
                patch('os.environ.get', side_effect=AssertionError('No credentials read')):
            prepared = self.prepare()
            result = transport.status_transport(prepared['receipt'], self.root / 'status-only')
        self.assertEqual(result['requests'], [])
        self.assertEqual(result['document_review_status'], 'AI_REVIEW_REQUIRED')


if __name__ == '__main__': unittest.main()
