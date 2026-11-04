"""Business/task supply with advisory purpose, using disposable originals only."""
import io
import json
import unittest
from copy import deepcopy
from unittest.mock import patch

import test_producer_v10 as fixture
from site_planner import producer_task_value as value
from site_planner import page_purpose_v6 as old, producer_observation as observed
from webcollect.batch_core import OutcomeUnknown, load_json


class TaskValue(unittest.TestCase):
    def setUp(self):
        self.f = fixture.ProducerV10('test_direct_anchor_directory_is_supported')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.pool, self.ledger, self.root = self.f.pool, self.f.ledger, self.f.root
        self.edit = lambda decision: decision
        self.inputs = []

    def original(self, uri=None, html=None):
        link = self.f.link(uri)
        self.f.observation(link['uri'], html or '<main><h1>文章正文</h1><p>' + '具体业务的完整阅读材料。' * 20 + '</p></main>')
        return link

    def prepared(self, html=None):
        link = self.original(html=html)
        evidence = value.evidence_for(self.pool, self.ledger, link)
        _, _, visible = value.prepare(link, evidence, self.ledger.config.get('model'))
        return evidence, visible

    def decision(self, visible):
        quotes = [q for q, text in visible['evidence'].items()
                  if not old.legacy.generic(text.split(': ', 1)[-1])][:2]
        return {'business': 'public_business', 'business_quote_ids': quotes,
                'task_value': 'supported', 'task_hint': '阅读本页具体业务介绍并查看关键说明',
                'task_quote_ids': quotes, 'reason': '主营内容与具体阅读活动有本页证据'}

    def provider(self, request, timeout):
        body = json.loads(request.data)
        context = json.loads(body['messages'][1]['content'][0]['text'])
        self.inputs.append(context)
        decisions = {page['page_key']: self.edit(self.decision(page)) for page in context['pages']}
        raw = deepcopy(self.f.f.b.f.f.provider.opener.raw)
        raw['choices'] = [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'tool_calls': [
            {'id': 'supply', 'type': 'function', 'function': {'name': 'submit_supply_decisions',
                'arguments': json.dumps({'decisions': decisions})}}]}}]
        return io.BytesIO(json.dumps(raw).encode())

    def run_decision(self, link, scope='first'):
        provider = self.f.f.b.f.f.provider.opener
        with patch.object(provider, 'open', side_effect=self.provider):
            return value.classify(self.ledger, [link], scope, self.root, pool=self.pool)

    def test_missing_auxiliary_type_keeps_business_candidate(self):
        ev, visible = self.prepared()
        result = value.assess(self.decision(visible), ev)
        self.assertTrue(result['selected'])
        self.assertEqual(result['final_page_type'], 'UNKNOWN')
        self.assertEqual(result['task_qualification'], 'HINT_ONLY_NOT_EXECUTED')

    def test_bad_auxiliary_type_and_quotes_cannot_hold_valid_core(self):
        ev, visible = self.prepared()
        for auxiliary in [dict(page_type='invented'), dict(page_type=['内容详情']),
                          dict(page_type='内容详情', purpose_quote_ids=[{}]),
                          dict(page_type='内容详情', purpose_quote_ids=['q999'])]:
            result = value.assess({**self.decision(visible), **auxiliary}, ev)
            self.assertTrue(result['selected'], auxiliary)
            self.assertEqual(result['final_page_type'], 'UNKNOWN')

    def test_known_supported_type_remains_auxiliary(self):
        ev, visible = self.prepared()
        proposal = {**self.decision(visible), 'page_type': '内容详情',
                    'purpose_quote_ids': list(visible['evidence'])}
        self.assertEqual(value.assess(proposal, ev)['final_page_type'], '内容详情')

    def test_type_structure_failure_does_not_hold_button_only_tool(self):
        ev, visible = self.prepared('<main><h1>基础计算器</h1><button>1</button><button>+</button><button>2</button><output>3</output></main>')
        proposal = {**self.decision(visible), 'task_hint': '使用数字和运算按钮计算表达式并查看结果',
                    'page_type': '功能页', 'purpose_quote_ids': list(visible['evidence'])}
        result = value.assess(proposal, ev)
        self.assertTrue(result['selected'])
        self.assertEqual(result['final_page_type'], 'UNKNOWN')

    def test_known_type_does_not_replace_missing_task(self):
        ev, visible = self.prepared()
        base = {**self.decision(visible), 'page_type': '内容详情', 'purpose_quote_ids': list(visible['evidence'])}
        for extra in [{'task_value': 'unsupported'}, {'task_value': 'UNKNOWN'},
                      {'task_quote_ids': []}, {'task_quote_ids': ['q999']}, {'task_hint': '浏览网页'}]:
            self.assertFalse(value.assess({**base, **extra}, ev)['selected'], extra)

    def test_business_mismatch_or_unknown_does_not_enter_for_a_known_type(self):
        ev, visible = self.prepared()
        for business in ['support', 'marketing', 'mismatch', 'UNKNOWN']:
            self.assertFalse(value.assess({**self.decision(visible), 'business': business,
                'page_type': '内容详情', 'purpose_quote_ids': list(visible['evidence'])}, ev)['selected'])
        self.assertFalse(value.assess({**self.decision(visible), 'business_quote_ids': ['q999']}, ev)['selected'])

    def test_short_real_task_kept_at_low_priority_without_five_step_claim(self):
        ev, visible = self.prepared('<main><h1>活动介绍</h1><p>本期活动介绍及报名时间说明。</p></main>')
        result = value.assess({**self.decision(visible), 'task_value': 'limited'}, ev)
        self.assertTrue(result['selected'])
        self.assertEqual(result['priority'], 'low')
        self.assertEqual(result['task_qualification'], 'HINT_ONLY_NOT_EXECUTED')

    def test_legal_title_cannot_be_promoted_by_task_hint(self):
        ev, visible = self.prepared('<main><h1>免责声明</h1><p>原网站法律声明。</p></main>')
        self.assertFalse(value.assess(self.decision(visible), ev)['selected'])

    def test_missing_core_stays_unresolved(self):
        ev, visible = self.prepared()
        proposal = self.decision(visible)
        del proposal['task_value']
        result = value.assess(proposal, ev)
        self.assertFalse(result['selected'])
        self.assertEqual(result['task_value'], 'UNKNOWN')

    def test_same_paid_unknown_purpose_reused_in_another_chunk(self):
        link = self.original()
        first, receipt = self.run_decision(link)
        with patch.object(value, 'model_tool_decision', side_effect=AssertionError('no classification repair')), \
             patch.object(old, 'homepage_document', side_effect=AssertionError('no second GET')):
            second, reused = value.classify(self.ledger, [{**link, 'link_id': 'second'}], 'another', self.root, pool=self.pool)
        self.assertEqual(len(self.inputs), 1)
        self.assertEqual(first[0]['page_type'], 'UNKNOWN')
        self.assertEqual(second[0]['link_id'], 'second')
        self.assertEqual(reused['calls'], [])
        self.assertTrue(reused['records'][0]['model_calls'][0]['reused'])

    def test_invalid_auxiliary_paid_reply_is_read_only_projected_and_cached(self):
        link = self.original()
        self.edit = lambda decision: {**decision, 'page_type': 'not-an-enum', 'purpose_quote_ids': ['q999']}
        rows, receipt = self.run_decision(link)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['page_type'], 'UNKNOWN')
        self.assertEqual(receipt['calls'][0]['response_mode'], 'read_only_original_reply')
        with self.ledger.connect() as con:
            state = con.execute('SELECT state FROM model_requests WHERE id=?', (receipt['calls'][0]['request_id'],)).fetchone()[0]
        self.assertEqual(state, 'invalid_response')
        with patch.object(value, 'model_tool_decision', side_effect=AssertionError('no purpose retry')):
            self.assertEqual(value.classify(self.ledger, [link], 'again', self.root, pool=self.pool)[1]['calls'], [])

    def test_invalid_core_paid_reply_is_cached_without_retry(self):
        link = self.original()
        self.edit = lambda decision: {k: v for k, v in decision.items() if k != 'task_value'}
        rows, receipt = self.run_decision(link)
        self.assertEqual(rows, [])
        self.assertEqual(receipt['records'][0]['task_value'], 'UNKNOWN')
        with patch.object(value, 'model_tool_decision', side_effect=AssertionError('no settled repair')):
            self.assertEqual(value.classify(self.ledger, [link], 'again', self.root, pool=self.pool)[1]['calls'], [])

    def test_unknown_original_request_is_not_redispatched_or_reidentified(self):
        link = self.original()
        provider = self.f.f.b.f.f.provider.opener
        with patch.object(provider, 'open', side_effect=TimeoutError('offline pending')) as dispatch, \
             patch('webcollect.model_gateway.time.sleep'):
            with self.assertRaises(OutcomeUnknown):
                value.classify(self.ledger, [link], 'first', self.root, pool=self.pool)
            with self.ledger.connect() as con:
                original = [dict(r) for r in con.execute('SELECT * FROM model_requests')]
            self.assertEqual(len(original), 1)
            self.assertEqual(original[0]['state'], 'unknown')
            with self.assertRaises(OutcomeUnknown):
                value.classify(self.ledger, [link], 'different-chunk', self.root, pool=self.pool)
            self.assertEqual(dispatch.call_count, 1)
            with self.ledger.connect() as con:
                self.assertEqual([dict(r) for r in con.execute('SELECT * FROM model_requests')], original)
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM checkpoints WHERE run_id=?', (value.CACHE,)).fetchone()[0], 0)

    def test_no_original_document_never_fetches_or_sends_empty_material(self):
        with patch.object(observed, 'from_pool', return_value=None), \
             patch.object(old, 'homepage_document', side_effect=AssertionError('no gap GET')), \
             patch.object(value, 'model_tool_decision', side_effect=AssertionError('no empty call')):
            rows, receipt = value.classify(self.ledger, [self.f.link()], 'missing', self.root, pool=self.pool)
        self.assertEqual(rows, [])
        self.assertEqual(receipt['calls'], [])

    def test_cached_request_unsettled_keeps_original_hold(self):
        link = self.original()
        _, receipt = self.run_decision(link)
        with self.ledger.connect() as con:
            con.execute("UPDATE model_requests SET state='unknown' WHERE id=?", (receipt['calls'][0]['request_id'],))
        with patch.object(value, 'model_tool_decision', side_effect=AssertionError('no replacement')):
            with self.assertRaises(OutcomeUnknown):
                value.classify(self.ledger, [link], 'newchunk', self.root, pool=self.pool)

    def test_model_input_has_short_local_quotes_no_structure_or_purpose_request(self):
        link = self.original()
        self.run_decision(link)
        page = self.inputs[0]['pages'][0]
        self.assertNotIn('structures', page)
        self.assertNotIn('page_type', page)
        self.assertTrue(all(q.startswith('q') and len(q) < 4 for q in page['evidence']))
        self.assertEqual(self.inputs[0]['version'], value.VERSION)

    def test_low_priority_task_follows_supported_task_in_same_batch(self):
        limited = self.original('https://tools.example.org/limited', '<main><h1>简短活动</h1><p>本期活动时间介绍。</p></main>')
        supported = self.original('https://tools.example.org/supported')
        limited['link_id'], supported['link_id'] = 'limited', 'supported'
        def edit(decision):
            if not self.first_edited:
                self.first_edited = True
                return {**decision, 'task_value': 'limited'}
            return decision
        self.first_edited = False
        self.edit = edit
        with patch.object(self.f.f.b.f.f.provider.opener, 'open', side_effect=self.provider):
            rows, receipt = value.classify(self.ledger, [limited, supported], 'mixed', self.root, pool=self.pool)
        self.assertEqual(rows[0]['link_id'], supported['link_id'])
        self.assertEqual([r['priority'] for r in receipt['records']], ['low', 'normal'])

    def test_formal_v11_publishes_unknown_task_hint_without_extra_get_or_goal(self):
        home = self.f.f.home
        provider = self.f.f.b.f.f.provider.opener
        from site_planner import page_consumption
        def screen(pool, ledger, links, root):
            for link in links:
                self.original(link['uri'])
            return page_consumption.screen(pool, ledger, links, root)
        sources = [{**home, 'context_only': True, 'excluded_entry_identities': ['https://tools.example.org/old']}]
        with patch.object(observed, 'screen', side_effect=screen), \
             patch('site_planner.candidate_discovery.check_entry', side_effect=AssertionError('no publication GET')), \
             patch('site_planner.entry_access.check_entry', side_effect=AssertionError('no landing GET')), \
             patch.object(provider, 'open', side_effect=self.provider):
            report = self.f.f.b.f.run_new(home, key='v11', target=1, sources=sources, model_protocol='entry-tools-11', batch_size=1)
            replay = self.f.f.b.f.run_new(home, key='v11', target=1, sources=sources, model_protocol='entry-tools-11', batch_size=1)
        self.assertEqual(report['listed_unique_candidates'], 1, report)
        self.assertEqual(replay['new_dispatches'], {'model': 0, 'GET': 0, 'search': 0})
        row = self.pool.rows(protocols=('webcollect-data-candidate-2',))[0]
        self.assertIsNone(row['candidate']['requested_goal'])
        self.assertEqual(set(row['candidate']), {'schema_version', 'candidate_kind', 'entry_url', 'requested_goal'})
        source = row['sources'][0]
        self.assertEqual(source['page_type'], 'UNKNOWN')
        self.assertEqual(source['task_diagnostic']['task_value'], 'supported')
        self.assertEqual(source['task_diagnostic']['task_qualification'], 'HINT_ONLY_NOT_EXECUTED')
        self.assertIsNone(self.pool.consumption(row['candidate']['entry_url']))
        self.assertEqual(load_json(source['entry_http']['path'])['policy'], 'producer-entry-observed-get-2')
        claim = self.pool.claim_next('offline-worker', 'offline-request', protocols=('webcollect-data-candidate-2',))
        self.assertEqual(claim['candidate_id'], row['candidate_id'])


if __name__ == '__main__':
    unittest.main()
