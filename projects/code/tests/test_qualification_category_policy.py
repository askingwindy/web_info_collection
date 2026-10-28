"""Frozen category protocols using local provider stubs, never network calls."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, ValidationError

import test_site_qualification_provenance as provenance
from site_planner.qualification import (CANONICAL_CATEGORIES, CANONICAL_SCHEMA,
    CATEGORY_POLICY_VERSION, CATEGORY_TAXONOMY_VERSION, LEGACY_SCHEMA, SCHEMA, VERSION, qualify_catalog,
    qualification_prompt, validate_qualification)
from webcollect.batch_core import BatchLedger, file_sha, load_json, save_json
from webcollect.model_gateway import ModelGateway
from webcollect.planning import object_sha256


class QualificationCategoryPolicy(unittest.TestCase):
    def setUp(self):
        self.fixture = provenance.QualificationProvenance('runTest')
        # This is a synchronous TestCase, whose cleanup has no asyncio-runner
        # dependency. Register cleanup before setup so partial setup is covered.
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.record = self.fixture.record
        self.q = self.record['site_qualification']
        self.policy = {'category_policy': CATEGORY_POLICY_VERSION,
                       'category_taxonomy_version': CATEGORY_TAXONOMY_VERSION,
                       'category_schema_sha256': object_sha256(CANONICAL_SCHEMA)}

    def assert_rejected(self, record):
        self.fixture.assert_rejected(record)

    def legacy_record(self):
        """Exercise the original public request protocol, not a mocked checker."""
        original = load_json(self.q['source_capability']['path'])
        access = self.q['access']
        ledger = self.fixture.ledger
        jid = ledger.enqueue('site-qualification', {'version': VERSION,
            'capability_sha256': object_sha256(original), 'access_sha256': object_sha256(access)})
        job = ledger.claim('site-qualification', job_id=jid)
        decision = ModelGateway(ledger).call(job, VERSION,
            json.dumps(qualification_prompt(original, access), ensure_ascii=False), LEGACY_SCHEMA,
            images=self.fixture.images)
        ledger.finish(job, result=decision)
        path = self.fixture.root / 'legacy-decision.json'; save_json(path, decision)
        record = deepcopy(self.record); q = record['site_qualification']
        for key in self.policy:
            q.pop(key)
        q.update(job_id=jid, response={'path': str(path), 'sha256': file_sha(path)})
        return record

    def test_new_default_binds_the_same_canonical_policy_in_job_and_metadata(self):
        self.assertEqual({key: self.q[key] for key in self.policy}, self.policy)
        with self.fixture.ledger.connect() as con:
            job = json.loads(con.execute('SELECT payload FROM jobs WHERE id=?', (self.q['job_id'],)).fetchone()[0])
            request = json.loads(con.execute('SELECT request_json FROM model_requests WHERE job_id=?', (self.q['job_id'],)).fetchone()[0])
        self.assertEqual({key: job[key] for key in self.policy}, self.policy)
        self.assertEqual(request['schema'], CANONICAL_SCHEMA)
        prompt = json.loads(request['text'])
        self.assertEqual(prompt['category_policy'], CATEGORY_POLICY_VERSION)
        self.assertEqual(prompt['category_taxonomy_version'], CATEGORY_TAXONOMY_VERSION)
        self.assertEqual(prompt['canonical_categories'], list(CANONICAL_CATEGORIES))
        self.assertEqual(len(CANONICAL_CATEGORIES), 15)
        self.assertEqual(len(set(CANONICAL_CATEGORIES)), 15)
        self.assertTrue({'交通出行查询', '健康科普', '图书文化', '在线工具', '学习教育',
                         '新闻资讯', '百科与文档', '知识文库'} <= set(CANONICAL_CATEGORIES))
        self.assertTrue({'百科与文档站', '医疗健康科普', '图书影音榜单'}.isdisjoint(CANONICAL_CATEGORIES))
        self.assertEqual(validate_qualification(self.record)['status'], 'ready')

    def test_invented_subcategory_is_not_an_allowed_new_model_answer(self):
        for category in ('在线工具-数学计算', '在线工具-数学计算工具', '在线工具、学习教育',
                         '百科与文档站', '医疗健康科普', '图书影音榜单'):
            answer = deepcopy(self.fixture.decision); answer['category'] = category
            with self.subTest(category=category), self.assertRaises(ValidationError):
                Draft202012Validator(CANONICAL_SCHEMA).validate(answer)
            # Preserve what the historical unrestricted protocol actually asked.
            Draft202012Validator(LEGACY_SCHEMA).validate(answer)

    def test_new_bad_answer_is_retained_as_a_failed_protocol_call(self):
        answer = deepcopy(self.fixture.decision); answer['category'] = '在线工具-数学计算'
        self.fixture.opener.raw['choices'][0]['message']['content'] = json.dumps(answer)
        ledger = BatchLedger(self.fixture.root / 'CONTROLLED-invalid-category.sqlite3',
                             self.fixture.config, initialize=True)
        output = self.fixture.root / 'invalid-category-output'
        with self.assertRaises(ValueError):
            qualify_catalog(ledger, self.fixture.catalog, output)
        states = ledger.summary()['model_request_states']
        self.assertEqual(set(states), {'invalid_response'})
        self.assertGreaterEqual(states['invalid_response'], 1)
        self.assertFalse(list(output.glob('qualified-catalog-*.json')))

    def test_removing_or_changing_metadata_policy_cannot_downgrade_a_new_request(self):
        for change in ('remove-both', 'remove-schema', 'unknown-policy', 'unknown-taxonomy', 'changed-schema'):
            record = deepcopy(self.record); q = record['site_qualification']
            if change == 'remove-both':
                for key in self.policy: q.pop(key)
            elif change == 'remove-schema':
                q.pop('category_schema_sha256')
            elif change == 'unknown-policy':
                q['category_policy'] = 'caller-selected-unrestricted'
            elif change == 'unknown-taxonomy':
                q['category_taxonomy_version'] = 'caller-selected-parent-map'
            else:
                q['category_schema_sha256'] = '0' * 64
            with self.subTest(change=change): self.assert_rejected(record)

    def test_original_job_cannot_drop_or_select_a_different_policy(self):
        with self.fixture.ledger.connect() as con:
            original = con.execute('SELECT payload FROM jobs WHERE id=?', (self.q['job_id'],)).fetchone()[0]
        for change in ('remove-both', 'unknown-policy'):
            payload = json.loads(original)
            if change == 'remove-both':
                for key in self.policy: payload.pop(key)
            else:
                payload['category_policy'] = 'caller-selected-unrestricted'
            try:
                with self.fixture.ledger.connect() as con:
                    con.execute('UPDATE jobs SET payload=? WHERE id=?', (json.dumps(payload), self.q['job_id']))
                    con.commit()
                with self.subTest(change=change): self.assert_rejected(self.record)
            finally:
                with self.fixture.ledger.connect() as con:
                    con.execute('UPDATE jobs SET payload=? WHERE id=?', (original, self.q['job_id']))
                    con.commit()

    def test_legacy_original_request_still_validates_without_a_new_policy_badge(self):
        legacy = self.legacy_record()
        self.assertIs(SCHEMA, LEGACY_SCHEMA)
        self.assertNotIn('category_policy', legacy['site_qualification'])
        self.assertNotIn('canonical_categories', qualification_prompt(self.fixture.source, self.q['access']))
        self.assertEqual(validate_qualification(legacy)['status'], 'ready')
        legacy['site_qualification'].update(self.policy)
        self.assert_rejected(legacy)

    def test_changing_both_job_and_metadata_cannot_relabel_the_original_request(self):
        legacy = self.legacy_record(); q = legacy['site_qualification']; q.update(self.policy)
        with self.fixture.ledger.connect() as con:
            payload = json.loads(con.execute('SELECT payload FROM jobs WHERE id=?', (q['job_id'],)).fetchone()[0])
            payload.update(self.policy)
            con.execute('UPDATE jobs SET payload=? WHERE id=?', (json.dumps(payload), q['job_id']))
            con.commit()
        self.assert_rejected(legacy)

    def test_unknown_prompt_policy_is_rejected_instead_of_falling_back(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            qualification_prompt(self.fixture.source, self.q['access'], category_policy='caller-selected')


if __name__ == '__main__':
    unittest.main()
