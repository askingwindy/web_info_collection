"""V12 business-only selection keeps V11 originals and candidate contract intact."""
import unittest
from unittest.mock import patch

from site_planner import producer_business_value as value
from site_planner import producer_task_value as legacy, producer_observation as observed
from webcollect.batch_core import OutcomeUnknown, load_json
import test_producer_task_value as fixtures


class BusinessValue(unittest.TestCase):
    setUp = fixtures.TaskValue.setUp
    original = fixtures.TaskValue.original
    provider = fixtures.TaskValue.provider

    def prepared(self, html=None):
        link = self.original(html=html)
        evidence = value.evidence_for(self.pool, self.ledger, link)
        _, _, visible = value.prepare(link, evidence, self.ledger.config.get('model'))
        return evidence, visible

    def decision(self, visible):
        return {'business': 'public_business', 'business_quote_ids': list(visible['evidence'])[:2],
                'reason': '本页主区有真实主营内容'}

    def run_decision(self, link, scope='first'):
        with patch.object(self.f.f.b.f.f.provider.opener, 'open', side_effect=self.provider):
            return value.classify(self.ledger, [link], scope, self.root, pool=self.pool)

    def test_business_evidence_without_task_or_purpose_is_admitted(self):
        evidence, visible = self.prepared()
        result = value.assess(self.decision(visible), evidence)
        self.assertTrue(result['selected'])
        self.assertEqual(result['final_page_type'], 'UNKNOWN')
        self.assertEqual(result['business_qualification'], 'PAGE_CONTENT_ONLY_NOT_EXECUTED')
        self.assertFalse(any(k.startswith('task_') for k in result))

    def test_business_unknown_mismatch_and_bad_reference_stay_rejected(self):
        evidence, visible = self.prepared()
        for business in ['support', 'marketing', 'mismatch', 'UNKNOWN']:
            self.assertFalse(value.assess({**self.decision(visible), 'business': business}, evidence)['selected'])
        for quotes in [[], ['q999'], ['q0', 'q0']]:
            self.assertFalse(value.assess({**self.decision(visible), 'business_quote_ids': quotes}, evidence)['selected'])

    def test_known_purpose_does_not_replace_business(self):
        evidence, visible = self.prepared()
        self.assertFalse(value.assess({**self.decision(visible), 'business': 'UNKNOWN',
            'page_type': '内容详情', 'purpose_quote_ids': list(visible['evidence'])}, evidence)['selected'])

    def test_optional_bad_purpose_does_not_reject_business(self):
        evidence, visible = self.prepared()
        for extra in [{'page_type': 'invented'}, {'page_type': ['内容详情']},
                      {'page_type': '内容详情', 'purpose_quote_ids': ['q999']}]:
            result = value.assess({**self.decision(visible), **extra}, evidence)
            self.assertTrue(result['selected'])
            self.assertEqual(result['final_page_type'], 'UNKNOWN')

    def test_legal_heading_is_still_excluded(self):
        evidence, visible = self.prepared('<main><h1>隐私政策</h1><p>本网站隐私声明。</p></main>')
        self.assertFalse(value.assess(self.decision(visible), evidence)['selected'])

    def test_missing_core_does_not_retry(self):
        link = self.original()
        self.edit = lambda d: {k: v for k, v in d.items() if k != 'business_quote_ids'}
        rows, first = self.run_decision(link)
        self.assertEqual(rows, [])
        with patch.object(value, 'model_tool_decision', side_effect=AssertionError('no paid repair')):
            self.assertEqual(value.classify(self.ledger, [link], 'another', self.root, pool=self.pool)[1]['calls'], [])
        self.assertEqual(len(first['calls']), 1)

    def test_advisory_unknown_reuses_paid_original_without_another_get(self):
        link = self.original()
        rows, first = self.run_decision(link)
        with patch.object(value, 'model_tool_decision', side_effect=AssertionError('no classification retry')), \
             patch.object(legacy.previous, 'homepage_document', side_effect=AssertionError('no second GET')):
            again, receipt = value.classify(self.ledger, [{**link, 'link_id': 'another'}], 'another', self.root, pool=self.pool)
        self.assertEqual(len(rows), 1)
        self.assertEqual(again[0]['page_type'], 'UNKNOWN')
        self.assertEqual(receipt['calls'], [])
        self.assertTrue(receipt['records'][0]['model_calls'][0]['reused'])

    def test_unknown_request_is_not_resent_under_different_chunk(self):
        provider = self.f.f.b.f.f.provider.opener
        link = self.original()
        with patch.object(provider, 'open', side_effect=TimeoutError('offline unknown')) as send, \
             patch('webcollect.model_gateway.time.sleep'):
            with self.assertRaises(OutcomeUnknown):
                value.classify(self.ledger, [link], 'first', self.root, pool=self.pool)
            with self.assertRaises(OutcomeUnknown):
                value.classify(self.ledger, [link], 'another', self.root, pool=self.pool)
        self.assertEqual(send.call_count, 1)

    def test_missing_original_neither_reopens_page_nor_requests_model(self):
        with patch.object(observed, 'from_pool', return_value=None), \
             patch.object(value, 'model_tool_decision', side_effect=AssertionError('empty material')):
            rows, receipt = value.classify(self.ledger, [self.f.link()], 'missing', self.root, pool=self.pool)
        self.assertEqual(rows, [])
        self.assertEqual(receipt['calls'], [])

    def test_new_model_schema_and_material_do_not_require_consumer_task(self):
        self.run_decision(self.original())
        self.assertEqual(self.inputs[0]['version'], value.VERSION)
        self.assertFalse(any(k.startswith('task_') for k in value.CORE['properties']))
        self.assertFalse(any(k.startswith('task_') for k in self.inputs[0]['pages'][0]))
        self.assertEqual(legacy.VERSION, 'producer-business-task-1')
        self.assertIn('task_hint', legacy.CORE['required'])
        self.assertNotEqual(value.CACHE, legacy.CACHE)

    def test_v12_query_goal_focuses_on_basic_business_without_three_task_gate(self):
        from site_planner import producer_query_plan as query
        seen = []
        def decision(ledger, gateway, purpose, payload, schema):
            seen.append(payload)
            return {'queries': ['公开业务入口']}
        with patch.object(query, 'model_decision', side_effect=decision):
            query.next_query(self.pool.pool, self.ledger, 'query-v12', 'one',
                ('企业后台与开源演示站',), {'queries': {}, 'blocked': []}, [], self.root,
                independent=True, public_business=True, purpose_grounded=True,
                purpose_protocol='entry-tools-12')
        self.assertEqual(seen[0]['purpose_policy'], value.VERSION)
        self.assertIn('基本公开业务内容', seen[0]['goal'])
        self.assertNotIn('三种不同匿名后台业务入口', seen[0]['goal'])

    def test_formal_v12_publishes_four_field_candidate_with_no_task_hint_or_extra_get(self):
        home = self.f.f.home
        from site_planner import page_consumption
        def screen(pool, ledger, links, root):
            for link in links:
                self.original(link['uri'])
            return page_consumption.screen(pool, ledger, links, root)
        sources = [{**home, 'context_only': True, 'excluded_entry_identities': ['https://tools.example.org/old']}]
        with patch.object(observed, 'screen', side_effect=screen), \
             patch('site_planner.candidate_discovery.check_entry', side_effect=AssertionError('no publication GET')), \
             patch('site_planner.entry_access.check_entry', side_effect=AssertionError('no landing GET')), \
             patch.object(self.f.f.b.f.f.provider.opener, 'open', side_effect=self.provider):
            report = self.f.f.b.f.run_new(home, key='v12', target=1, sources=sources, model_protocol='entry-tools-12', batch_size=1)
            replay = self.f.f.b.f.run_new(home, key='v12', target=1, sources=sources, model_protocol='entry-tools-12', batch_size=1)
        self.assertEqual(report['listed_unique_candidates'], 1, report)
        self.assertEqual(replay['new_dispatches'], {'model': 0, 'GET': 0, 'search': 0})
        row = self.pool.rows(protocols=('webcollect-data-candidate-2',))[0]
        self.assertIsNone(row['candidate']['requested_goal'])
        self.assertEqual(set(row['candidate']), {'schema_version', 'candidate_kind', 'entry_url', 'requested_goal'})
        source = row['sources'][0]
        self.assertNotIn('task_diagnostic', source)
        self.assertNotIn('task_hint', source['purpose_evidence'])
        self.assertEqual(source['business_qualification'], 'PAGE_CONTENT_ONLY_NOT_EXECUTED')
        self.assertEqual(load_json(source['entry_http']['path'])['policy'], 'producer-entry-observed-get-2')
        self.assertEqual(self.pool.claim_next('offline', 'request', protocols=('webcollect-data-candidate-2',))['candidate_id'], row['candidate_id'])


if __name__ == '__main__':
    unittest.main()
