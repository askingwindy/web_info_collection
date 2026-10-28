"""Accounting conservation, evidence privacy and immutable audit publication."""
from copy import deepcopy
from contextlib import closing, contextmanager
from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from webcollect.model_audit import build_audit, export_audit, fingerprint, main, query_audit, read_snapshot


class ModelAuditTests(unittest.TestCase):
    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.db)) as con:
            with con:
                yield con

    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.db = self.root / 'source.sqlite3'
        self.config = {'run_id': 'test', 'budget': {'currency': 'CNY', 'max_model_cost_micros': 100},
                       'model': {'provider': 'glm', 'model': 'test-model', 'api_key_env': 'UNREAD_TEST_KEY',
                                 'rates': {'input': 1000000, 'cached_input': 500000, 'output': 2000000,
                                           'version': 'TEST-NOT-A-PRICE', 'source': 'offline fixture'}}}
        with self.connection() as con:
            con.executescript('''
                CREATE TABLE batch_meta(id INTEGER PRIMARY KEY,config TEXT,started REAL);
                CREATE TABLE jobs(id TEXT PRIMARY KEY,kind TEXT,payload TEXT,state TEXT,result TEXT);
                CREATE TABLE model_requests(id TEXT PRIMARY KEY,job_id TEXT,purpose TEXT,attempt INTEGER,
                  state TEXT,reserved_tokens INTEGER,reserved_cost INTEGER,started REAL,finished REAL,
                  usage TEXT,cost INTEGER,response TEXT,error TEXT,request_json TEXT);
            ''')
            con.execute('INSERT INTO batch_meta VALUES(1,?,1)', (json.dumps(self.config),))
        self.job('site', 'site-screen'); self.job('a', 'ai-visual'); self.job('b', 'ai-visual', 'review_required')
        self.job('setup', 'model-smoke'); self.job('unbound', 'ai-documents')
        self.request('r-site', 'site', 5, 1, 1, 7, images=2)
        self.request('r-a', 'a', 10, 2, 2, 13)
        self.request('r-b', 'b', 10, 3, 0, 16, state='invalid_response', attempt=1, images=4)
        self.request('r-unknown', 'setup', None, None, None, None, state='unknown', finished=None)
        self.request('r-unbound', 'unbound', 3, 1, 0, 5, images=1)

    def job(self, key, kind, state='done'):
        with self.connection() as con:
            con.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',
                        (key, kind, '{"secret_payload":"NEVER_EXPORT_PAYLOAD"}', state, None))

    def request(self, key, job, inp, out, cached, cost, *, state='succeeded', attempt=0, images=None, finished=3):
        usage = None if inp is None else json.dumps({'input_tokens': inp, 'output_tokens': out,
                'cached_input_tokens': cached, 'image_tokens': images,
                'provider_request_id': 'same-provider-id-do-not-deduplicate', 'returned_model': 'actual-version'})
        evidence = {'system': 'NEVER_EXPORT_SYSTEM', 'text': 'NEVER_EXPORT_PROMPT',
                    'schema': {'type': 'object', 'description': 'NEVER_EXPORT_SCHEMA'},
                    'images': [{'path': '/NEVER_EXPORT_IMAGE_PATH', 'sha256': 'a' * 64}],
                    'Authorization': 'NEVER_EXPORT_CREDENTIAL'}
        response = {'provider_response': {'id': 'provider-fallback-id', 'model': 'actual-version',
                                          'choices': [{'message': {'content': 'NEVER_EXPORT_RESPONSE'}}]}}
        with self.connection() as con:
            con.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (key, job, 'visible-stage:bound-prompt-sha', attempt, state, 200, 100, 2,
                         finished, usage, cost, json.dumps(response), None, json.dumps(evidence)))

    def manifest(self, allocate=False):
        binding = fingerprint(self.db)
        jobs = {'site': {'scope': 'site', 'scope_id': 'site-before-production-id', 'classification': 'production',
                         'related_sample_ids': ['A', 'B']},
                'a': {'scope': 'sample', 'scope_id': 'A', 'classification': 'production'},
                'b': {'scope': 'sample', 'scope_id': 'B', 'classification': 'production'},
                'setup': {'scope': 'engineering', 'scope_id': 'adapter-setup', 'classification': 'setup'}}
        if allocate:
            jobs['site']['allocation'] = {'method': 'equal_weight', 'sample_ids': ['B', 'A']}
        return {'schema_version': 'webcollect-model-attribution-1',
                'ledger_binding': {k: binding[k] for k in ('logical_sha256', 'config_sha256')}, 'jobs': jobs}

    def write_manifest(self, value):
        path = self.root / 'manifest.json'; path.write_text(json.dumps(value)); return path

    def test_shared_and_unattributed_remain_separate_without_implicit_sample_charge(self):
        audit = build_audit(read_snapshot(self.db), self.manifest())
        self.assertEqual(len(audit['requests']), 5)
        totals = audit['summary']['ledger_totals']
        self.assertEqual(totals['known_estimated_cost_micros'], 41)
        self.assertEqual(totals['estimated_cost_micros'], 'UNKNOWN')
        self.assertEqual(totals['uncertain_reserved_cost_micros'], 100)
        self.assertEqual(audit['summary']['unattributed']['known_estimated_cost_micros'], 5)
        samples = {s['sample_id']: s for s in audit['sample_summaries']}
        self.assertEqual(samples['A']['combined_explicit_estimate']['known_estimated_cost_micros'], 13)
        self.assertEqual(samples['B']['combined_explicit_estimate']['known_estimated_cost_micros'], 16)
        self.assertTrue(all(s['shared_reference_count'] == 0 for s in samples.values()))
        site = next(s for s in audit['scopes'] if s['scope'] == 'site')
        self.assertEqual(site['request_count'], 1)
        self.assertEqual(site['known_estimated_cost_micros'], 7)

    def test_explicit_equal_weight_cost_token_and_request_equivalent_conservation(self):
        audit = build_audit(read_snapshot(self.db), self.manifest(allocate=True))
        samples = {s['sample_id']: s for s in audit['sample_summaries']}
        self.assertEqual(samples['A']['allocated_shared_estimate']['known_estimated_cost_micros'], 4)
        self.assertEqual(samples['B']['allocated_shared_estimate']['known_estimated_cost_micros'], 3)
        self.assertEqual(samples['A']['allocated_shared_estimate']['input_tokens'], 3)
        self.assertEqual(samples['B']['allocated_shared_estimate']['input_tokens'], 2)
        for s in samples.values():
            self.assertEqual(s['direct']['request_count'], 1)
            self.assertEqual(s['shared_reference_count'], 1)
            self.assertEqual((s['shared_request_equivalent_numerator'], s['shared_request_equivalent_denominator']), (1, 2))
            self.assertFalse(s['allocated_tokens_are_provider_sample_measurements'])
        self.assertTrue(all(audit['summary']['conservation'].values()))
        self.assertEqual(sum(s['combined_explicit_estimate']['known_estimated_cost_micros'] for s in samples.values()) +
                         audit['summary']['retained_non_sample_scopes']['known_estimated_cost_micros'], 41)

    def test_cache_pricing_retries_invalid_responses_and_post_api_job_failure_are_retained(self):
        manifest = self.manifest()
        manifest['request_classifications'] = {'r-b': {'classification': 'repair_or_retry', 'note': 'format refusal retained'}}
        audit = build_audit(read_snapshot(self.db), manifest)
        rows = {r['request_id']: r for r in audit['requests']}
        self.assertEqual(rows['r-site']['recomputed_cost_micros'], 7)
        self.assertEqual(rows['r-a']['recomputed_cost_micros'], 13)
        self.assertEqual(rows['r-b']['request_state'], 'invalid_response')
        self.assertEqual(rows['r-b']['job_state'], 'review_required')
        self.assertEqual(rows['r-b']['classification'], 'repair_or_retry')
        self.assertEqual(rows['r-b']['scope'], 'sample')
        self.assertEqual(audit['summary']['retry_request_count'], 1)
        self.assertEqual(rows['r-unknown']['usage']['input_tokens'], 'UNKNOWN')
        self.assertEqual(rows['r-unknown']['duration_seconds'], 'UNKNOWN')
        self.assertEqual(rows['r-unknown']['provider_request_id'], 'provider-fallback-id')
        self.assertEqual(rows['r-a']['usage']['image_tokens'], 'UNKNOWN')
        self.assertEqual(audit['summary']['cash_deducted_micros'], 'UNKNOWN')

    def test_missing_cache_usage_never_becomes_zero_and_unknown_allocation_keeps_reservation(self):
        with self.connection() as con:
            con.execute('UPDATE model_requests SET usage=?,cost=NULL WHERE id=?',
                        (json.dumps({'input_tokens': 5, 'output_tokens': 1}), 'r-site'))
        audit = build_audit(read_snapshot(self.db), self.manifest(allocate=True))
        row = next(r for r in audit['requests'] if r['request_id'] == 'r-site')
        self.assertEqual(row['usage']['cached_input_tokens'], 'UNKNOWN')
        self.assertEqual(row['recomputed_cost_micros'], 'UNKNOWN')
        self.assertEqual(audit['summary']['ledger_totals']['uncertain_reserved_cost_micros'], 200)
        for sample in audit['sample_summaries']:
            self.assertEqual(sample['allocated_shared_estimate']['estimated_cost_micros'], 'UNKNOWN')
            self.assertEqual(sample['allocated_shared_estimate']['uncertain_reserved_cost_micros'], 50)
        self.assertTrue(all(audit['summary']['conservation'].values()))

    def test_cost_above_reservation_and_budget_is_reported_without_truncation(self):
        self.config['budget']['max_model_cost_micros'] = 10
        with self.connection() as con:
            con.execute('UPDATE batch_meta SET config=?', (json.dumps(self.config),))
            con.execute('UPDATE model_requests SET reserved_cost=5 WHERE id="r-a"')
        audit = build_audit(read_snapshot(self.db), self.manifest())
        row = next(r for r in audit['requests'] if r['request_id'] == 'r-a')
        self.assertEqual(row['known_estimated_cost_micros'], 13)
        self.assertTrue(row['exceeded_request_reservation'])
        self.assertTrue(audit['summary']['known_cost_exceeds_budget'])

    def test_readonly_export_is_bound_and_contains_hashes_without_text_or_credentials(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        manifest = self.write_manifest(self.manifest(allocate=True)); output = self.root / 'audit'
        audit = export_audit(self.db, manifest, output)
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).hexdigest())
        self.assertEqual(audit['source']['logical_sha256'], fingerprint(self.db)['logical_sha256'])
        self.assertEqual(audit['source']['execution_mode'], 'UNKNOWN')
        self.assertEqual(audit['summary']['execution_mode'], 'UNKNOWN')
        all_text = ''.join(p.read_text() for p in output.iterdir())
        self.assertNotIn('NEVER_EXPORT_', all_text)
        self.assertNotIn('Authorization', all_text)
        self.assertIn(hashlib.sha256(b'NEVER_EXPORT_SYSTEM').hexdigest(), all_text)
        self.assertEqual({p.name for p in output.iterdir()},
                         {'audit.json', 'summary.json', 'requests.csv', 'sample-summary.csv', 'stages.csv', 'scopes.csv'})
        with self.assertRaises(ValueError): export_audit(self.db, manifest, output)
        with self.assertRaises(ValueError): export_audit(self.db, manifest, self.db)
        with self.assertRaises(ValueError): export_audit(self.db, manifest, self.root)

    def test_missing_database_is_never_created(self):
        missing = self.root / 'missing.sqlite3'
        with self.assertRaises(ValueError): fingerprint(missing)
        self.assertFalse(missing.exists())

    def test_stale_job_result_or_config_or_manifest_bindings_are_rejected(self):
        manifest = self.write_manifest(self.manifest())
        with self.connection() as con: con.execute('UPDATE jobs SET result="changed" WHERE id="a"')
        with self.assertRaisesRegex(ValueError, 'binding drift'): export_audit(self.db, manifest, self.root / 'stale')
        self.assertFalse((self.root / 'stale').exists())
        value = self.manifest(); value['ledger_binding']['config_sha256'] = '0' * 64
        with self.assertRaises(ValueError): export_audit(self.db, self.write_manifest(value), self.root / 'config-drift')

    def test_publication_rechecks_fingerprint_without_publishing_on_mid_audit_drift(self):
        manifest = self.write_manifest(self.manifest()); snapshot = read_snapshot(self.db)
        changed = deepcopy(snapshot); changed['binding']['logical_sha256'] = '0' * 64
        with patch('webcollect.model_audit.read_snapshot', side_effect=[snapshot, changed]):
            with self.assertRaisesRegex(ValueError, 'changed during audit'):
                export_audit(self.db, manifest, self.root / 'drift')
        self.assertFalse((self.root / 'drift').exists())

    def test_invalid_attribution_and_scope_cost_override_are_rejected(self):
        for mode in ('unknown_job', 'scope_override', 'duplicate_samples', 'engineering_allocation'):
            value = self.manifest(True)
            if mode == 'unknown_job': value['jobs']['absent'] = value['jobs']['a']
            elif mode == 'scope_override': value['request_classifications'] = {'r-a': {'classification': 'setup', 'scope': 'engineering'}}
            elif mode == 'duplicate_samples': value['jobs']['site']['allocation']['sample_ids'] = ['A', 'A']
            else: value['jobs']['setup']['allocation'] = {'method': 'equal_weight', 'sample_ids': ['A']}
            with self.subTest(mode=mode), self.assertRaises(ValueError): build_audit(read_snapshot(self.db), value)

    def test_duplicate_json_nan_and_boolean_token_counts_are_rejected(self):
        manifest = self.root / 'bad-manifest.json'
        manifest.write_text('{"schema_version":"a","schema_version":"b"}')
        with self.assertRaises(ValueError): export_audit(self.db, manifest, self.root / 'duplicate')
        for usage in ('{"input_tokens":NaN}', '{"input_tokens":true}'):
            with self.connection() as con: con.execute('UPDATE model_requests SET usage=? WHERE id="r-a"', (usage,))
            with self.subTest(usage=usage), self.assertRaises(ValueError):
                build_audit(read_snapshot(self.db), self.manifest())

    def test_cost_mismatch_is_rejected_not_silently_replaced(self):
        with self.connection() as con: con.execute('UPDATE model_requests SET cost=12 WHERE id="r-a"')
        with self.assertRaisesRegex(ValueError, 'cost mismatch'):
            export_audit(self.db, self.write_manifest(self.manifest()), self.root / 'mismatch')

    def test_csv_formula_text_is_neutralized_but_json_and_numbers_remain_exact(self):
        value = self.manifest()
        value['jobs']['a']['scope_id'] = '=HYPERLINK("https://example.invalid")'
        value['request_classifications'] = {'r-a': {'classification': 'production', 'note': '\t+danger()'}}
        audit = export_audit(self.db, self.write_manifest(value), self.root / 'csv-safe')
        with (self.root / 'csv-safe/requests.csv').open(newline='') as stream:
            row = next(r for r in csv.DictReader(stream) if r['request_id'] == 'r-a')
        self.assertEqual(row['scope_id'], "'" + value['jobs']['a']['scope_id'])
        self.assertEqual(row['classification_note'], "'\t+danger()")
        self.assertEqual(row['known_estimated_cost_micros'], '13')
        self.assertEqual(next(r for r in audit['requests'] if r['request_id'] == 'r-a')['scope_id'], value['jobs']['a']['scope_id'])

    def test_nested_provider_metadata_cannot_export_response_text(self):
        with self.connection() as con:
            usage = json.loads(con.execute('SELECT usage FROM model_requests WHERE id="r-a"').fetchone()[0])
            usage.update(returned_model={'content': 'NEVER_EXPORT_NESTED'}, provider_request_id=['NEVER_EXPORT_NESTED'])
            con.execute('UPDATE model_requests SET usage=? WHERE id="r-a"', (json.dumps(usage),))
        audit = export_audit(self.db, self.write_manifest(self.manifest()), self.root / 'nested-safe')
        row = next(r for r in audit['requests'] if r['request_id'] == 'r-a')
        self.assertEqual(row['returned_model'], 'UNKNOWN')
        self.assertEqual(row['provider_request_id'], 'UNKNOWN')
        self.assertNotIn('NEVER_EXPORT_NESTED', ''.join(p.read_text() for p in (self.root / 'nested-safe').iterdir()))

    def test_site_work_before_sample_allocation_has_only_site_account(self):
        with self.connection() as con:
            con.execute('DELETE FROM model_requests WHERE id!="r-site"')
        value = self.manifest(); value['jobs'] = {'site': {'scope': 'site', 'scope_id': 'pre-id-work', 'classification': 'production'}}
        audit = export_audit(self.db, self.write_manifest(value), self.root / 'site-only')
        self.assertEqual(audit['sample_summaries'], [])
        self.assertEqual(audit['summary']['ledger_totals']['request_count'], 1)
        self.assertEqual(audit['summary']['ledger_totals']['estimated_cost_micros'], 7)
        self.assertEqual(audit['summary']['local_cached_result_reuse_count'], 'UNKNOWN')
        self.assertEqual(audit['scopes'][0]['scope'], 'site')
        self.assertIn('sample_id', (self.root / 'site-only/sample-summary.csv').read_text())

    def test_error_metadata_uses_exact_allowlist_not_identifier_or_error_suffix(self):
        cases = ('NEVER_EXPORT_CREDENTIAL', 'NEVER_EXPORT_CREDENTIAL_SecretError', 'JSONDecodeError')
        for number, error in enumerate(cases):
            with self.connection() as con:
                con.execute('UPDATE model_requests SET error=? WHERE id="r-a"', (error,))
            output = self.root / f'error-safe-{number}'
            audit = export_audit(self.db, self.write_manifest(self.manifest()), output)
            row = next(r for r in audit['requests'] if r['request_id'] == 'r-a')
            self.assertEqual(row['error_sha256'], hashlib.sha256(error.encode()).hexdigest())
            self.assertEqual(row['error_type'], 'JSONDecodeError' if error == 'JSONDecodeError' else 'REDACTED_ERROR')
            if error != 'JSONDecodeError':
                self.assertNotIn('NEVER_EXPORT_CREDENTIAL', ''.join(p.read_text() for p in output.iterdir()))

    def test_provider_text_and_free_text_purpose_are_hash_only_with_known_stage_labels(self):
        self.config['model'].update(provider='glm\nBearer NEVER_EXPORT_PROVIDER', model='NEVER_EXPORT_MODEL full prompt')
        with self.connection() as con:
            usage = json.loads(con.execute('SELECT usage FROM model_requests WHERE id="r-a"').fetchone()[0])
            usage.update(returned_model='NEVER_EXPORT_RESPONSE full prompt\nBearer SECRET_SENTINEL',
                         provider_request_id='NEVER_EXPORT_CREDENTIAL full message')
            con.execute('UPDATE batch_meta SET config=?', (json.dumps(self.config),))
            con.execute('UPDATE model_requests SET usage=?,purpose=? WHERE id="r-a"',
                        (json.dumps(usage), 'NEVER_EXPORT_PROMPT raw text:stage'))
        output = self.root / 'metadata-safe'
        audit = export_audit(self.db, self.write_manifest(self.manifest()), output)
        row = next(r for r in audit['requests'] if r['request_id'] == 'r-a')
        for key in ('provider', 'configured_model', 'returned_model', 'provider_request_id'):
            self.assertEqual(row[key], 'UNKNOWN')
            self.assertEqual(len(row['provider_metadata_sha256'][key]), 64)
        self.assertEqual(row['purpose'], 'UNKNOWN')
        self.assertEqual(row['purpose_sha256'], hashlib.sha256(b'NEVER_EXPORT_PROMPT raw text:stage').hexdigest())
        self.assertNotIn('NEVER_EXPORT_', ''.join(p.read_text() for p in output.iterdir()))
        with self.connection() as con:
            con.execute('UPDATE model_requests SET purpose=? WHERE id="r-a"', ('site-screen-v1:' + 'a' * 64,))
        audit = build_audit(read_snapshot(self.db), self.manifest())
        self.assertEqual(next(r for r in audit['requests'] if r['request_id'] == 'r-a')['purpose'], 'site-screen')

    def test_reasoning_and_provider_totals_are_audited_without_extra_token_or_cost_charge(self):
        values = {'r-site': (1, 6), 'r-a': (1, 12), 'r-b': (2, 13), 'r-unbound': (0, 4)}
        with self.connection() as con:
            con.execute('DELETE FROM model_requests WHERE id="r-unknown"')
            for request, (reasoning, total) in values.items():
                response = {'provider_response': {'usage': {'completion_tokens_details': {'reasoning_tokens': reasoning},
                                                           'total_tokens': total}}}
                con.execute('UPDATE model_requests SET response=? WHERE id=?', (json.dumps(response), request))
        audit = build_audit(read_snapshot(self.db), self.manifest(True))
        totals = audit['summary']['ledger_totals']
        self.assertEqual(totals['input_tokens'], 28)
        self.assertEqual(totals['output_tokens'], 7)
        self.assertEqual(totals['reasoning_tokens'], 4)
        self.assertEqual(totals['provider_total_tokens'], 35)
        self.assertEqual(totals['known_estimated_cost_micros'], 41)
        self.assertEqual(audit['summary']['token_inconsistency_requests'], 0)
        self.assertTrue(all(audit['summary']['conservation'].values()))
        for sample in audit['sample_summaries']:
            shared = sample['allocated_shared_estimate']
            self.assertEqual(shared['provider_total_tokens'], shared['input_tokens'] + shared['output_tokens'])
        for reasoning, total in ((3, 999), (True, False)):
            with self.connection() as con:
                response = {'provider_response': {'usage': {'completion_tokens_details': {'reasoning_tokens': reasoning},
                                                           'total_tokens': total}}}
                con.execute('UPDATE model_requests SET response=? WHERE id="r-a"', (json.dumps(response),))
            audit = build_audit(read_snapshot(self.db), self.manifest())
            row = next(r for r in audit['requests'] if r['request_id'] == 'r-a')
            self.assertEqual(row['usage']['reasoning_tokens'], 'UNKNOWN')
            self.assertEqual(row['usage']['provider_total_tokens'], 'UNKNOWN')
            self.assertEqual(set(row['token_consistency'].values()), {'INCONSISTENT'})
            self.assertEqual(audit['summary']['ledger_totals']['known_estimated_cost_micros'], 41)

    def exported_query_fixture(self, allocate=True):
        out = self.root / 'query-export'
        export_audit(self.db, self.write_manifest(self.manifest(allocate)), out)
        return out / 'audit.json'

    def test_query_separates_direct_shared_and_fractional_requests_with_exact_cny(self):
        path = self.exported_query_fixture()
        result = query_audit(path, 'A')
        self.assertEqual(result['ledger_request_count'], 5)
        self.assertEqual(result['ledger_totals']['known_estimated_cost_micros'], 41)
        self.assertEqual(result['ledger_totals']['estimated_cost_cny'], 'UNKNOWN')
        self.assertEqual(result['ledger_totals']['uncertain_reserved_cost_units'], '0.000100')
        sample = result['samples'][0]
        self.assertEqual(sample['direct_request_count'], 1)
        self.assertEqual(sample['shared_request_reference_count'], 1)
        self.assertEqual(sample['shared_request_equivalent'], {'numerator': 1, 'denominator': 2})
        self.assertEqual(sample['total_request_equivalent'], {'numerator': 3, 'denominator': 2})
        self.assertEqual(sample['direct']['estimated_cost_micros'], 13)
        self.assertEqual(sample['allocated_shared_estimate']['estimated_cost_micros'], 4)
        self.assertEqual(sample['total_explicit_estimate']['estimated_cost_cny'], '0.000017')
        self.assertEqual(sample['total_explicit_estimate']['input_tokens'], 13)
        self.assertEqual(sample['total_explicit_estimate']['image_tokens'], 'UNKNOWN')
        self.assertEqual({s['job_kind'] for s in sample['stages']}, {'ai-visual', 'site-screen'})
        all_samples = query_audit(path)
        self.assertEqual([s['sample_id'] for s in all_samples['samples']], ['A', 'B'])
        self.assertEqual(sum(s['request_count'] for s in all_samples['stages']), 5)
        self.assertEqual(all_samples['unattributed']['known_estimated_cost_micros'], 5)

    def test_query_retains_unknown_tokens_cost_and_request_job_failure_states(self):
        with self.connection() as con:
            con.execute('UPDATE model_requests SET cost=NULL,usage=NULL,state="unknown" WHERE id="r-a"')
        path = self.exported_query_fixture()
        a = query_audit(path, 'A')['samples'][0]
        self.assertEqual(a['direct']['estimated_cost_micros'], 'UNKNOWN')
        self.assertEqual(a['direct']['input_tokens'], 'UNKNOWN')
        self.assertEqual(a['direct']['cached_input_tokens'], 'UNKNOWN')
        self.assertEqual(a['total_explicit_estimate']['estimated_cost_cny'], 'UNKNOWN')
        self.assertEqual(a['total_explicit_estimate']['uncertain_reserved_cost_units'], '0.000100')
        self.assertEqual(a['unsuccessful_or_pending_requests'][0]['request_state'], 'unknown')
        b = query_audit(path, 'B')['samples'][0]
        self.assertEqual(b['direct_request_states'], {'invalid_response': 1})
        self.assertEqual(b['direct_job_states'], {'review_required': 1})
        self.assertEqual(b['unsuccessful_or_pending_requests'][0]['estimated_cost_micros'], 16)

    def test_query_rejects_unknown_sample_schema_missing_fields_and_summary_tampering(self):
        path = self.exported_query_fixture(); original = json.loads(path.read_text())
        with self.assertRaisesRegex(ValueError, 'Sample ID'):
            query_audit(path, 'not-a-sample')
        for case in ('schema', 'missing', 'request_count', 'known_cost', 'sample_cost', 'stage_cost', 'scope_count'):
            value = deepcopy(original)
            if case == 'schema': value['schema_version'] = 'unknown-v99'
            elif case == 'missing': del value['requests'][0]['usage']
            elif case == 'request_count': value['summary']['ledger_totals']['request_count'] = 6
            elif case == 'known_cost': value['summary']['ledger_totals']['known_estimated_cost_micros'] = 0
            elif case == 'sample_cost': value['sample_summaries'][0]['direct']['known_estimated_cost_micros'] = 0
            elif case == 'stage_cost': value['stages'][0]['known_estimated_cost_micros'] = 0
            else: value['scopes'][0]['request_count'] += 1
            path.write_text(json.dumps(value))
            with self.subTest(case=case), self.assertRaises(ValueError): query_audit(path)

    def test_query_rejects_duplicate_request_boolean_counts_and_mixed_currency(self):
        path = self.exported_query_fixture(); original = json.loads(path.read_text())
        for case in ('duplicate', 'boolean', 'currency', 'cost', 'reserved', 'states'):
            value = deepcopy(original)
            if case == 'duplicate': value['requests'].append(deepcopy(value['requests'][0]))
            elif case == 'boolean': value['requests'][0]['usage']['input_tokens'] = True
            elif case == 'currency': value['requests'][0]['currency'] = 'USD'
            elif case == 'cost': value['requests'][0]['known_estimated_cost_micros'] = 0
            elif case == 'reserved': value['requests'][0]['uncertain_reserved_cost_micros'] = 999
            else: value['requests'][0]['request_state'] = 'imaginary-pass'
            path.write_text(json.dumps(value))
            with self.subTest(case=case), self.assertRaises(ValueError): query_audit(path)

    def test_query_is_offline_without_database_and_cli_emits_only_validated_output(self):
        path = self.exported_query_fixture(); self.db.unlink()
        stream = io.StringIO()
        with patch('webcollect.model_audit.read_snapshot', side_effect=AssertionError('DB access forbidden')):
            with redirect_stdout(stream):
                code = main(['query', '--audit', str(path), '--sample-id', 'B'])
        self.assertEqual(code, 0)
        result = json.loads(stream.getvalue())
        self.assertEqual(result['samples'][0]['total_explicit_estimate']['estimated_cost_micros'], 19)
        self.assertEqual(result['actual_network_dispatch_count'], 'UNKNOWN')
        self.assertNotIn('NEVER_EXPORT_', stream.getvalue())
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(['query', '--audit', str(path), '--sample-id', 'absent'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stream.getvalue())['status'], 'STOP')

    def test_query_rejects_impossible_image_subset_and_match_on_unknown_tokens(self):
        path = self.exported_query_fixture(); original = json.loads(path.read_text())
        value = deepcopy(original); value['requests'][0]['usage']['image_tokens'] = 100
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Image tokens exceed input'):
            query_audit(path)
        value = deepcopy(original); value['requests'][0]['token_consistency']['reasoning_tokens'] = 'MATCH'
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'MATCH on unknown'):
            query_audit(path)

    def test_compact_query_matches_full_values_preserves_unknown_and_still_validates(self):
        path = self.exported_query_fixture()
        for unknown in (False, True):
            if unknown:
                with self.connection() as con:
                    con.execute('UPDATE model_requests SET cost=NULL,usage=NULL,state="unknown" WHERE id="r-a"')
                folder = self.root / 'unknown-compact'
                export_audit(self.db, self.write_manifest(self.manifest(True)), folder); path = folder / 'audit.json'
            full = query_audit(path, 'A'); original = full['samples'][0]
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = main(['query', '--audit', str(path), '--sample-id', 'A', '--compact'])
            self.assertEqual(code, 0)
            compact = json.loads(stream.getvalue()); sample = compact['samples'][0]
            self.assertLessEqual(len(stream.getvalue().splitlines()), 100)
            self.assertEqual(compact['audit_sha256'], full['audit_sha256'])
            self.assertEqual(compact['ledger']['requests'], full['ledger_request_count'])
            self.assertEqual(sample['direct_requests'], original['direct_request_count'])
            self.assertEqual(sample['shared_reference_count'], original['shared_request_reference_count'])
            self.assertEqual(sample['shared_request_equivalent'], '1/2')
            for name in ('direct', 'shared', 'total'):
                key = {'direct': 'direct', 'shared': 'allocated_shared_estimate', 'total': 'total_explicit_estimate'}[name]
                self.assertEqual(sample[name + '_cost_micros'], original[key]['estimated_cost_micros'])
                self.assertEqual(sample[name + '_cost_cny'], original[key]['estimated_cost_cny'])
            for token in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'image_tokens', 'reasoning_tokens', 'provider_total_tokens'):
                self.assertEqual(sample[token], original['total_explicit_estimate'][token])
            if unknown:
                self.assertEqual(sample['total_cost_cny'], 'UNKNOWN')
                self.assertEqual(sample['uncertain_reserved_micros'], 100)
        value = json.loads(path.read_text()); value['summary']['ledger_totals']['request_count'] = 999
        path.write_text(json.dumps(value)); stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(main(['query', '--audit', str(path), '--compact']), 2)
        self.assertEqual(json.loads(stream.getvalue())['status'], 'STOP')

    def test_observe_only_accounting_and_query_are_explicit_without_reinterpreting_old_caps(self):
        self.config['budget'].update(cost_control='observe_only', max_model_cost_micros=None)
        with self.connection() as con: con.execute('UPDATE batch_meta SET config=?', (json.dumps(self.config),))
        output = self.root / 'observe-audit'
        audit = export_audit(self.db, self.write_manifest(self.manifest()), output)
        self.assertEqual(audit['summary']['cost_control'], 'observe_only')
        self.assertEqual(audit['summary']['budget_max_model_cost_micros'], 'NOT_APPLICABLE')
        self.assertEqual(audit['summary']['known_cost_exceeds_budget'], 'NOT_APPLICABLE')
        self.assertEqual(audit['summary']['ledger_totals']['known_estimated_cost_micros'], 41)
        self.assertEqual(audit['summary']['ledger_totals']['estimated_cost_micros'], 'UNKNOWN')
        result = query_audit(output / 'audit.json', 'A')
        self.assertEqual(result['cost_control'], 'observe_only')
        self.assertEqual(result['budget_max_model_cost_micros'], 'NOT_APPLICABLE')
        stream = io.StringIO()
        with redirect_stdout(stream): self.assertEqual(main(['query', '--audit', str(output / 'audit.json'), '--compact']), 0)
        self.assertEqual(json.loads(stream.getvalue())['cost_control'], 'observe_only')
        old = self.config; old['budget'].pop('cost_control'); old['budget']['max_model_cost_micros'] = 100
        with self.connection() as con: con.execute('UPDATE batch_meta SET config=?', (json.dumps(old),))
        folder = self.root / 'old-capped'; audit = export_audit(self.db, self.write_manifest(self.manifest()), folder)
        audit['summary'].pop('cost_control'); audit['source'].pop('cost_control')
        (folder / 'audit.json').write_text(json.dumps(audit))
        result = query_audit(folder / 'audit.json')
        self.assertEqual(result['cost_control'], 'capped')
        self.assertEqual(result['budget_max_model_cost_micros'], 100)

    def test_query_rejects_legacy_reinterpretation_and_inconsistent_cost_control_flags(self):
        path = self.exported_query_fixture(); original = json.loads(path.read_text())
        legacy = deepcopy(original); legacy['source'].pop('cost_control'); legacy['summary'].pop('cost_control')
        legacy['summary'].pop('monetary_limit_applied')
        path.write_text(json.dumps(legacy))
        self.assertEqual(query_audit(path)['cost_control'], 'capped')
        changed = deepcopy(legacy)
        changed['summary'].update(cost_control='observe_only', budget_max_model_cost_micros='NOT_APPLICABLE')
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'Legacy source'):
            query_audit(path)
        observed = deepcopy(original)
        observed['source']['cost_control'] = 'observe_only'
        observed['summary'].update(cost_control='observe_only', budget_max_model_cost_micros='NOT_APPLICABLE',
                                   monetary_limit_applied=False, known_cost_exceeds_budget='NOT_APPLICABLE',
                                   known_plus_uncertain_reservation_exceeds_budget='NOT_APPLICABLE')
        path.write_text(json.dumps(observed))
        self.assertEqual(query_audit(path)['cost_control'], 'observe_only')
        for field, value in (('budget_max_model_cost_micros', 100), ('monetary_limit_applied', True),
                             ('monetary_limit_applied', 0), ('known_cost_exceeds_budget', False),
                             ('known_plus_uncertain_reservation_exceeds_budget', 'UNKNOWN')):
            changed = deepcopy(observed); changed['summary'][field] = value; path.write_text(json.dumps(changed))
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): query_audit(path)
        for field, value in (('budget_max_model_cost_micros', 'NOT_APPLICABLE'), ('monetary_limit_applied', False),
                             ('known_cost_exceeds_budget', 'NOT_APPLICABLE'),
                             ('known_plus_uncertain_reservation_exceeds_budget', False)):
            changed = deepcopy(original); changed['summary'][field] = value; path.write_text(json.dumps(changed))
            with self.subTest(capped_field=field), self.assertRaises(ValueError): query_audit(path)


if __name__ == '__main__':
    unittest.main()
