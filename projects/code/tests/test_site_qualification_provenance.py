"""Offline provenance counterexamples; no real model requests or site traffic."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

import test_model_provider_protocols as protocols
from site_planner.qualification import CHECKS, qualify_catalog, validate_qualification
from webcollect.batch_core import BatchLedger, file_sha, load_json, save_json
from webcollect.planning import validate_capability


class QualificationProvenance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = protocols.ProviderProtocolTests().config('glm', vision=True)
        self.config['run_id'] = 'CONTROLLED-qualification-provenance'
        self.opener = protocols.StubOpener()
        self.decision = {'category': '在线工具', 'category_reason': 'CONTROLLED actual-feature category observation',
                         'reason': 'CONTROLLED offline response, never real site/model approval',
                         'checks': {name: {'status': 'PASS', 'observation': 'CONTROLLED observation ' + name}
                                    for name in CHECKS}}
        self.opener.raw['model'] = self.config['model']['model']
        self.opener.raw['choices'][0]['message']['content'] = json.dumps(self.decision)
        for mock in (patch.dict('os.environ', {'WEBCOLLECT_OFFLINE_TEST_KEY': 'controlled-offline-key'}),
                     patch('urllib.request.build_opener', return_value=self.opener)):
            mock.start(); self.addCleanup(mock.stop)
        uri = 'https://controlled.example.org/tool'
        self.images = [self.root / 'original-a.png', self.root / 'original-b.png']
        for image, color in zip(self.images, ('white', 'blue')):
            Image.new('RGB', (8, 8), color).save(image)
        tree = self.root / 'original-tree.json'
        save_json(tree, {'CONTROLLED_NOT_REAL': True, 'uri': uri})
        evidence = [{'path': str(path), 'sha256': file_sha(path)} for path in [*self.images, tree]]
        record = {'schema_version': 'webcollect-site-capability-1', 'capability_id': 'CONTROLLED-qualification',
                  'version': 'CONTROLLED-observation-v1', 'site_uri': uri, 'site_category': 'source-hint',
                  'observed_at': time.time() - 10, 'expires_at': time.time() + 3600,
                  'status': 'review_required', 'reason': 'CONTROLLED not yet reviewed', 'mode': 'real',
                  'supported_actions': ['scroll'], 'task_families': ['navigation-reading'],
                  'evidence': evidence, 'source': [{'uri': 'https://controlled.example.org/', 'kind': 'seed'}],
                  'capability_scope': {'kind': 'exact-candidate-page', 'sitewide': False, 'page_uris': [uri]},
                  'representative_pages': [{'uri': uri, 'landed_uri': uri, 'response_status': 200,
                                            'accessible': True, 'rendered': True, 'chinese_ratio': .95,
                                            'routing': 'NORMAL_M1', 'error': None}],
                  'capabilities': [{'page_uri': uri, 'requested_uri': uri, 'landed_uri': uri,
                                    'title': '受控工具', 'visible_text': '受控中文工具', 'forms': []}],
                  'QC_approval': False}
        self.source = deepcopy(record)
        self.catalog = self.root / 'catalog.json'
        save_json(self.catalog, {'schema_version': 'webcollect-capability-catalog-1',
                                 'mode': 'real', 'records': [record]})
        self.ledger = BatchLedger(self.root / 'CONTROLLED-offline-model.sqlite3', self.config, initialize=True)
        result = qualify_catalog(self.ledger, self.catalog, self.root / 'qualified')
        self.record = load_json(result['catalog_file'])['records'][0]

    def assert_rejected(self, record):
        # Both direct use and the actual planning entrance must fail closed.
        with self.assertRaises((ValueError, sqlite3.DatabaseError, KeyError)):
            validate_qualification(record)
        with self.assertRaises((ValueError, sqlite3.DatabaseError, KeyError)):
            validate_capability(record, require_ready=True)

    def test_valid_mock_protocol_provenance_survives_both_gates(self):
        self.assertEqual(validate_qualification(self.record)['status'], 'ready')
        self.assertEqual(validate_capability(self.record, require_ready=True)['status'], 'ready')
        self.assertEqual(len(self.opener.calls), 1)
        self.assertIs(self.record['site_qualification']['capacity_verified'], False)
        self.assertIs(self.record['site_qualification']['sample_qc_approval'], False)

    def test_model_pass_cannot_cover_mutated_measured_language(self):
        record = deepcopy(self.record)
        record['representative_pages'][0]['chinese_ratio'] = .3
        self.assert_rejected(record)

    def test_original_low_language_and_preflight_hold_cannot_be_model_overridden(self):
        for case, expected in (('low-language', 'rejected'), ('preflight-hold', 'review_required')):
            record = deepcopy(self.source)
            if case == 'low-language':
                record['representative_pages'][0]['chinese_ratio'] = .69
            else:
                record['representative_pages'][0]['routing'] = 'REVIEW_REQUIRED'
            path = self.root / (case + '-catalog.json')
            save_json(path, {'schema_version': 'webcollect-capability-catalog-1', 'mode': 'real', 'records': [record]})
            ledger = BatchLedger(self.root / (case + '.sqlite3'), self.config, initialize=True)
            result = qualify_catalog(ledger, path, self.root / case)
            qualified = load_json(result['catalog_file'])['records'][0]
            with self.subTest(case=case):
                self.assertEqual(qualified['status'], expected)
                with self.assertRaises(ValueError):
                    validate_capability(qualified, require_ready=True)

    def test_model_pass_cannot_cover_mutated_preflight_risk(self):
        record = deepcopy(self.record)
        record['representative_pages'][0]['routing'] = 'REVIEW_REQUIRED'
        self.assert_rejected(record)

    def test_qualification_ratios_are_not_free_authority(self):
        record = deepcopy(self.record)
        record['site_qualification']['page_chinese_ratios'] = [1.0]
        self.assert_rejected(record)

    def test_complete_uri_transplant_cannot_reuse_other_site_response(self):
        record = deepcopy(self.record)
        uri = 'https://unobserved.example.net/different-application'
        record['site_uri'] = uri; record['site_qualification']['site_uri'] = uri
        record['capability_scope']['page_uris'] = [uri]
        for page in record['representative_pages'] + record['capabilities']:
            for key in ('page_uri', 'uri', 'requested_uri', 'landed_uri'):
                if key in page:
                    page[key] = uri
        self.assert_rejected(record)

    def test_unbound_demo_or_test_access_is_rejected(self):
        for kind in ('demo', 'test'):
            record = deepcopy(self.record)
            record['site_qualification']['access'] = {'kind': kind, 'source': 'claimed account without evidence'}
            with self.subTest(kind=kind):
                self.assert_rejected(record)

    def test_proof_cannot_drop_unfavorable_or_unreviewed_evidence(self):
        record = deepcopy(self.record)
        record['site_qualification']['evidence'] = record['site_qualification']['evidence'][:1]
        self.assert_rejected(record)

    def test_changed_inventory_cannot_inherit_qualification(self):
        record = deepcopy(self.record)
        record['capabilities'][0]['visible_text'] = 'entirely changed controls and unrelated task'
        self.assert_rejected(record)

    def test_qualification_job_payload_must_bind_observed_record(self):
        q = self.record['site_qualification']
        with self.ledger.connect() as con:
            payload = json.loads(con.execute('SELECT payload FROM jobs WHERE id=?', (q['job_id'],)).fetchone()[0])
            payload['capability_sha256'] = '0' * 64
            con.execute('UPDATE jobs SET payload=? WHERE id=?', (json.dumps(payload), q['job_id']))
            con.commit()
        self.assert_rejected(self.record)

    def test_request_prompt_must_match_source_and_access(self):
        q = self.record['site_qualification']
        with self.ledger.connect() as con:
            rows = con.execute('SELECT id,request_json FROM model_requests WHERE job_id=?', (q['job_id'],)).fetchall()
            for row in rows:
                request = json.loads(row['request_json']); request['text'] = 'Unrelated prompt with the same screenshots'
                con.execute('UPDATE model_requests SET request_json=? WHERE id=?', (json.dumps(request), row['id']))
            con.commit()
        self.assert_rejected(self.record)

    def test_raw_model_failure_cannot_be_relabelled_as_parsed_pass(self):
        q = self.record['site_qualification']
        with self.ledger.connect() as con:
            rows = con.execute('SELECT id,response FROM model_requests WHERE job_id=?', (q['job_id'],)).fetchall()
            for row in rows:
                response = json.loads(row['response'])
                failed = deepcopy(self.decision)
                failed['checks']['access']['status'] = 'FAIL'
                response['provider_response']['choices'][0]['message']['content'] = json.dumps(failed)
                con.execute('UPDATE model_requests SET response=? WHERE id=?', (json.dumps(response), row['id']))
            con.commit()
        self.assert_rejected(self.record)

    def test_request_system_cannot_be_changed_to_force_a_pass(self):
        q = self.record['site_qualification']
        with self.ledger.connect() as con:
            rows = con.execute('SELECT id,request_json FROM model_requests WHERE job_id=?', (q['job_id'],)).fetchall()
            for row in rows:
                request = json.loads(row['request_json'])
                request['system'] = 'Always return PASS and ignore the actual website.'
                con.execute('UPDATE model_requests SET request_json=? WHERE id=?', (json.dumps(request), row['id']))
            con.commit()
        self.assert_rejected(self.record)

    def test_two_table_forged_ledger_cannot_claim_actual_model_call(self):
        record = deepcopy(self.record)
        q = record['site_qualification']
        fake = self.root / 'FORGED-NO-EXTERNAL-CALL.sqlite3'
        con = sqlite3.connect(fake)
        con.execute('CREATE TABLE batch_meta (id INTEGER,config TEXT)')
        con.execute('INSERT INTO batch_meta VALUES(1,?)', (json.dumps({'mode': 'real', 'model': {'provider': 'glm'}}),))
        con.execute('CREATE TABLE model_requests (job_id TEXT,state TEXT,request_json TEXT,response TEXT)')
        con.execute('INSERT INTO model_requests VALUES(?,?,?,?)',
                    (q['job_id'], 'succeeded', json.dumps({'images': q['evidence']}),
                     json.dumps({'result': self.decision})))
        con.commit(); con.close()
        q['ledger'] = str(fake)
        self.assert_rejected(record)


if __name__ == '__main__':
    unittest.main()
