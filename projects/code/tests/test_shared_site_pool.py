"""Disposable shared-pool and discovery fixtures; no websites, secrets or production IO."""
import asyncio
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from PIL import Image
from webcollect.batch_core import BatchLedger, BudgetStop, OutcomeUnknown, load_json, save_json
from webcollect.site_pool_reader import read_site_pool
from site_planner.site_pool import SitePool
from site_planner.discovery_tools import glm_search, reference, DiscoveryBrowser
from site_planner import discovery_agent as agent

REPO = Path(__file__).resolve().parents[3]


class PoolTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.proof = self.root / 'proof.json'; self.proof.write_text('{"offline":true}')
        self.refs = [reference(self.proof)]
        self.pool = SitePool(self.root / 'pool.sqlite3', initialize=True)

    def record(self, uri='https://www.example.org/page', origin='glm_agent', event='one', run='run'):
        return self.pool.record({'schema_version': 'webcollect-site-discovery-1', 'origin': origin,
            'event_id': event, 'run_id': run, 'uri': uri, 'name': 'Example',
            'category_hint': '图书文化', 'source_refs': self.refs})

    def decision(self, category='图书文化', **changes):
        return {'status': 'PROMISING', 'category': category, 'reason': 'Visible original fixture',
            'task_hint': 'Find a book', 'application_name': 'Independent Fixture',
            'identity_confirmed': True, 'public_chinese': True, 'evidence_complete': True,
            'page_kind': 'TARGET_APPLICATION',
            'access': {'readable': True, 'same_application_host': True}, **changes}

    def test_two_origins_share_application_and_keep_both_discoveries(self):
        a = self.record(); b = self.record('https://example.org/page', 'codex_session')
        self.assertEqual(a['application_id'], b['application_id'])
        self.assertEqual(self.pool.stats()['applications'], 1)
        self.assertEqual(self.pool.stats()['discoveries'], 2)
        self.assertEqual(self.pool.stats()['origins'], {'glm_agent': 1, 'codex_session': 1})

    def test_idempotent_replay_and_event_conflict(self):
        a = self.record(); self.assertTrue(self.record()['replayed'])
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            self.record('https://example.org/other')
        self.assertEqual(self.pool.stats()['discoveries'], 1)

    def test_evidence_tampering_rejected_on_write_and_program2_read(self):
        self.record(); self.proof.write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'SHA'):
            self.record(event='two')
        with self.assertRaisesRegex(ValueError, 'SHA'):
            read_site_pool(self.pool.path)

    def test_alias_requires_proof_and_merge_preserves_events(self):
        a = self.record(); b = self.record('https://other.org/', event='two')
        with self.assertRaises(ValueError):
            self.pool.add_alias(a['application_id'], 'https://mobile.example.org', [])
        self.pool.add_alias(a['application_id'], 'https://mobile.example.org', self.refs)
        self.assertEqual(self.record('https://mobile.example.org/', event='three')['application_id'], a['application_id'])
        with self.assertRaisesRegex(ValueError, 'merge'):
            self.pool.add_alias(a['application_id'], 'https://other.org', self.refs)
        self.pool.merge(b['application_id'], a['application_id'], self.refs)
        self.assertEqual(self.pool.application('https://other.org')['id'], a['application_id'])
        self.assertEqual(self.pool.stats()['applications'], 1)
        self.assertEqual(self.pool.stats()['discoveries'], 3)

    def test_alias_proof_tampering_and_merge_cannot_evade_frozen_baseline(self):
        first = self.record(); base = self.pool.freeze_run('run', {'fixed': True})
        target = self.record('https://new.org/', event='two')
        self.pool.assess(target['page_id'], 'run', self.decision(), self.refs)
        self.pool.merge(first['application_id'], target['application_id'], self.refs)
        self.assertEqual(agent.run_stats(self.pool, 'run', base)['confirmed_independent_applications'], 0)
        self.proof.write_text('tampered alias/merge evidence')
        with self.assertRaisesRegex(ValueError, 'SHA'):
            self.pool.application('https://example.org/')

    def test_classification_conflict_is_unknown_and_run_scope_is_strict(self):
        p = self.record()['page_id']
        self.pool.assess(p, 'old', self.decision(), self.refs)
        self.pool.assess(p, 'run', self.decision('学习教育'), self.refs)
        rows = self.pool.rows(run_id='run')
        self.assertEqual(len(rows[0]['assessments']), 1)
        self.assertEqual(rows[0]['assessments'][0]['run_id'], 'run')
        self.assertTrue(rows[0]['category_conflict'])
        self.assertEqual(rows[0]['category'], 'UNKNOWN')
        self.assertEqual(self.pool.stats()['application_categories'], {'UNKNOWN': 1})

    def test_baseline_frozen_and_unknown_tool_never_resent(self):
        a = self.record(); base = self.pool.freeze_run('run', {'fixed': True})
        self.record('https://new.org', event='two')
        self.assertEqual(self.pool.freeze_run('run', {'fixed': True}), base)
        with self.assertRaisesRegex(ValueError, 'configuration'):
            self.pool.freeze_run('run', {'fixed': False})
        rid, _ = self.pool.reserve_tool('run', 'search', 'q', {'q': 'q'})
        with self.assertRaisesRegex(ValueError, 'UNKNOWN'):
            self.pool.reserve_tool('run', 'search', 'q', {'q': 'q'})
        self.pool.settle_tool(rid, 'unknown', {'charge': 'UNKNOWN'})
        with self.assertRaisesRegex(ValueError, 'UNKNOWN'):
            self.pool.reserve_tool('run', 'search', 'q', {'q': 'q'})
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.pool.reserve_tool('run', 'search', 'q', {'q': 'other'})

    def test_cached_tool_precedes_budget_check_and_checkpoint_conflict(self):
        rid, _ = self.pool.reserve_tool('run', 'search', 'q', {'q': 'q'}, maximum=1)
        self.pool.settle_tool(rid, 'succeeded', {'cached': True})
        self.assertEqual(self.pool.reserve_tool('run', 'search', 'q', {'q': 'q'}, maximum=1)[1], {'cached': True})
        with self.assertRaises(BudgetStop):
            self.pool.reserve_tool('run', 'search', 'new', {}, maximum=1)
        self.pool.checkpoint('run', 'stage', {'completed': True})
        with self.assertRaisesRegex(ValueError, 'Checkpoint conflict'):
            self.pool.checkpoint('run', 'stage', {'completed': False})

    def test_failed_cross_host_incomplete_and_old_assessment_do_not_reach_target(self):
        p = self.record()['page_id']
        self.pool.assess(p, 'old', self.decision(), self.refs)
        self.assertEqual(agent.run_stats(self.pool, 'run', [])['confirmed_independent_applications'], 0)
        self.pool.assess(p, 'run', self.decision(access={'readable': True, 'same_application_host': False}), self.refs)
        self.pool.assess(p, 'run', self.decision(evidence_complete=False), self.refs)
        stats = agent.run_stats(self.pool, 'run', [])
        self.assertEqual(stats['new_candidate_applications'], 1)
        self.assertEqual(stats['confirmed_independent_applications'], 0)
        self.assertFalse(agent.complete(stats, ['图书文化'], 1))

    def test_pages_do_not_duplicate_app_and_category_conflict_blocks_count(self):
        p = self.record()['page_id']; q = self.record('https://example.org/second', event='two')['page_id']
        self.pool.assess(p, 'run', self.decision(), self.refs)
        self.pool.assess(q, 'run', self.decision(), self.refs)
        self.assertEqual(agent.run_stats(self.pool, 'run', [])['confirmed_independent_applications'], 1)
        self.pool.assess(q, 'run', self.decision('学习教育'), self.refs)
        self.assertEqual(agent.run_stats(self.pool, 'run', [])['confirmed_independent_applications'], 0)

    def test_related_hosts_do_not_bypass_baseline_or_count_as_two_sites(self):
        p = self.record('https://m.example.org', event='one')['page_id']
        self.pool.assess(p, 'run', self.decision(), self.refs)
        self.assertEqual(agent.run_stats(self.pool, 'run', [{'id': 'old', 'host': 'book.example.org'}])['new_candidate_applications'], 0)
        self.assertTrue(agent.related_hosts('m.a.com.cn', 'a.com.cn'))
        self.assertFalse(agent.related_hosts('a.edu.cn', 'b.edu.cn'))

    def test_multiple_applications_count_without_mutating_identity_comparison_types(self):
        for i, uri in enumerate(('https://alpha.org/', 'https://beta.org/', 'https://gamma.org/')):
            p = self.record(uri, event=str(i))['page_id']
            self.pool.assess(p, 'run', self.decision(application_name='Same App' if i < 2 else 'Other App'), self.refs)
        stats = agent.run_stats(self.pool, 'run', [])
        self.assertEqual(stats['new_candidate_applications'], 3)
        self.assertEqual(stats['confirmed_independent_applications'], 2)
        self.assertEqual(stats['confirmed_categories'], {'图书文化': 2})

    def test_directory_mentions_and_old_schema_cannot_confirm_target_application(self):
        p = self.record()['page_id']
        self.pool.assess(p, 'run', self.decision(page_kind='DIRECTORY_OR_INTRODUCTION'), self.refs)
        old = self.decision(); old.pop('page_kind')
        self.pool.assess(p, 'run', old, self.refs)
        self.assertEqual(agent.run_stats(self.pool, 'run', [])['confirmed_independent_applications'], 0)

    def test_model_name_cannot_bypass_prior_candidate_exclusion_on_new_host(self):
        p = self.record()['page_id']
        self.pool.assess(p, 'run', self.decision(application_name='学堂在线官网'), self.refs)
        stats = agent.run_stats(self.pool, 'run', [{'id':'previous', 'host':'xuetangx.com', 'name':'学堂在线'}])
        self.assertEqual(stats['confirmed_independent_applications'], 0)
        self.assertTrue(stats['applications'][0]['baseline_name_collision'])

    def test_program2_main_is_read_only_and_cannot_grant_ready(self):
        self.record(); original = self.pool.path.read_bytes()
        with patch('webcollect.collect.collect_plan', side_effect=AssertionError('collection forbidden')):
            from webcollect.__main__ import main
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(['site-pool', '--pool', str(self.pool.path)]), 0)
            self.assertFalse(json.loads(out.getvalue())['collection_dispatched'])
        self.assertEqual(original, self.pool.path.read_bytes())
        self.assertEqual(read_site_pool(self.pool.path, purpose='capabilities')['records'], [])
        exported = self.pool.export_candidates(self.root / 'candidates.json')
        self.assertEqual(exported['records'][0]['status'], 'review_required')
        self.assertEqual(exported['sample_ids_allocated'], 0)

    def test_discovery_cannot_bind_as_capability(self):
        self.record(); path = self.root / 'fake-capability.json'
        save_json(path, {'schema_version': 'webcollect-capability-catalog-1', 'records': [{'status': 'ready'}]})
        with self.assertRaisesRegex(ValueError, 'Real capability'):
            self.pool.bind_capability(reference(path))

    def test_program2_revalidates_qualified_capability_expiry_and_original_bytes(self):
        # Reuse the established provider-protocol fixture, never a real model/site.
        from test_site_qualification_provenance import QualificationProvenance
        self.enterContext(patch('webcollect.model_gateway.socket.getaddrinfo',return_value=[('CONTROLLED-offline-DNS',)]))
        case = QualificationProvenance(); case.setUp(); self.addCleanup(case.doCleanups)
        self.record(case.record['site_uri'])
        catalog = self.root / 'qualified-fixture.json'
        save_json(catalog, {'schema_version': 'webcollect-capability-catalog-1', 'records': [case.record]})
        self.pool.bind_capability(reference(catalog))
        result = read_site_pool(self.pool.path, purpose='capabilities')
        self.assertEqual(len(result['records']), 1)
        self.assertFalse(result['collection_dispatched'])
        later = time.time() + 7200
        with patch('webcollect.planning.time.time', return_value=later):
            with self.assertRaisesRegex(ValueError, '过期'):
                read_site_pool(self.pool.path, purpose='capabilities')
        case.images[0].write_bytes(b'tampered original')
        with self.assertRaisesRegex(ValueError, 'SHA'):
            read_site_pool(self.pool.path, purpose='capabilities')

    def test_search_saves_raw_response_and_reuses_without_new_secret_or_http(self):
        raw = {'search_result': [{'link': 'https://example.org', 'title': 'fixture', 'content': '中文'}]}
        opener = MagicMock(); opener.open.return_value = io.BytesIO(json.dumps(raw).encode())
        with patch('webcollect.model_credentials.credential', return_value='offline-secret'), patch('urllib.request.build_opener', return_value=opener):
            a = glm_search(self.pool, 'run', {}, '图书', self.root, maximum=1)
        with patch('webcollect.model_credentials.credential', side_effect=AssertionError('no secret read')), patch('urllib.request.build_opener', side_effect=AssertionError('no network')):
            self.assertEqual(glm_search(self.pool, 'run', {}, '图书', self.root, maximum=1), a)
        self.assertEqual(a['cost'], 'UNKNOWN')
        self.assertEqual(load_json(a['reference']['path']), raw)
        self.assertNotIn(b'offline-secret', self.pool.path.read_bytes())

    def test_search_unknown_is_retained_and_never_resent(self):
        opener = MagicMock(); opener.open.side_effect = TimeoutError()
        with patch('webcollect.model_credentials.credential', return_value='offline-secret'), patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaises(OutcomeUnknown):
                glm_search(self.pool, 'run', {}, '图书', self.root)
            with self.assertRaisesRegex(ValueError, 'UNKNOWN'):
                glm_search(self.pool, 'run', {}, '图书', self.root)
        self.assertEqual(opener.open.call_count, 1)

    def test_search_HTTP_error_preserves_provider_code_and_original_body(self):
        from urllib.error import HTTPError
        body=json.dumps({'error':{'code':'1113','message':'CONTROLLED account balance unavailable'}}).encode()
        opener=MagicMock();opener.open.side_effect=HTTPError('https://provider.invalid',429,'controlled',{},io.BytesIO(body))
        with patch('webcollect.model_credentials.credential',return_value='offline-secret'),patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaises(OutcomeUnknown):glm_search(self.pool,'run',{},'受控余额',self.root)
            with self.assertRaises(ValueError):glm_search(self.pool,'run',{},'受控余额',self.root)
        with self.pool.connect() as con:row=con.execute('SELECT state,result FROM tool_requests').fetchone()
        result=json.loads(row['result'])
        self.assertEqual((row['state'],result['provider_code']),('unknown','1113'))
        self.assertEqual(Path(result['error_response']['path']).read_bytes(),body)
        self.assertEqual(opener.open.call_count,1)

    def test_browser_timeout_reads_same_page_and_blocks_writes(self):
        config = load_json(REPO / 'projects/code/config/batch-synthetic.json')
        ledger = BatchLedger(self.root / 'ops.sqlite3', config, initialize=True)
        browser = DiscoveryBrowser(self.pool, ledger, 'run', self.root)
        page = MagicMock(); page.route = AsyncMock(); page.goto = AsyncMock(side_effect=TimeoutError())
        page.locator.return_value.wait_for = AsyncMock(); page.wait_for_timeout = AsyncMock()
        page.evaluate = AsyncMock(return_value={'title': 'Fixture', 'landed_uri': 'https://example.org/',
            'text': '公开图书搜索', 'links': [], 'controls': []})
        async def screenshot(**kwargs): Image.new('RGB', (8,8), 'white').save(kwargs['path'])
        page.screenshot = screenshot; page.close = AsyncMock()
        browser.context = MagicMock(); browser.context.new_page = AsyncMock(return_value=page)
        result = asyncio.run(browser.read('https://example.org/'))
        self.assertTrue(result['readable']); self.assertEqual(result['navigation_error'], 'TimeoutError')
        self.assertEqual(page.goto.call_count, 1); page.close.assert_awaited_once()
        handler = page.route.call_args.args[1]
        route = MagicMock(); route.request.method = 'POST'; route.abort = AsyncMock()
        asyncio.run(handler(route)); route.abort.assert_awaited_once()
        self.assertEqual(ledger.visits()[0]['state'], 'succeeded')

    def test_browser_setup_failure_closes_started_resources(self):
        browser = DiscoveryBrowser(self.pool, None, 'run', self.root)
        pw = MagicMock(); pw.stop = AsyncMock(); pw.chromium.launch = AsyncMock(side_effect=RuntimeError('launch failed'))
        cm = MagicMock(); cm.start = AsyncMock(return_value=pw)
        with patch('playwright.async_api.async_playwright', return_value=cm):
            with self.assertRaises(RuntimeError): asyncio.run(browser.__aenter__())
        pw.stop.assert_awaited_once()

    def test_browser_io_timeout_settles_hung_evaluation_and_closes_page(self):
        config = load_json(REPO / 'projects/code/config/batch-synthetic.json')
        ledger = BatchLedger(self.root / 'ops.sqlite3', config, initialize=True)
        browser = DiscoveryBrowser(self.pool, ledger, 'run', self.root)
        page = MagicMock(); page.route = AsyncMock()
        page.goto = AsyncMock(return_value=MagicMock(status=200))
        page.locator.return_value.wait_for = AsyncMock(); page.wait_for_timeout = AsyncMock()
        async def hang(*args): await asyncio.Event().wait()
        page.evaluate = hang; page.close = AsyncMock()
        browser.context = MagicMock(); browser.context.new_page = AsyncMock(return_value=page)
        wait_for = asyncio.wait_for
        def short_io_timeout(coroutine, timeout):
            return wait_for(coroutine,.03 if timeout==60 else timeout)
        with patch('site_planner.discovery_tools.asyncio.wait_for',new=short_io_timeout):
            with self.assertRaises(TimeoutError): asyncio.run(browser.read('https://example.org/'))
        page.close.assert_awaited_once()
        self.assertEqual(ledger.visits()[0]['state'], 'failed')
        self.assertEqual(self.pool.stats()['tool_states'], [{'kind':'browser','state':'failed','count':1}])

    def test_blank_landing_preserves_original_error_page_evidence(self):
        config = load_json(REPO / 'projects/code/config/batch-synthetic.json')
        ledger = BatchLedger(self.root / 'ops.sqlite3', config, initialize=True)
        browser = DiscoveryBrowser(self.pool, ledger, 'run', self.root)
        page = MagicMock(); page.route = AsyncMock()
        page.goto = AsyncMock(side_effect=RuntimeError('page.goto: net::ERR_CONNECTION_RESET'))
        page.locator.return_value.wait_for = AsyncMock(); page.wait_for_timeout = AsyncMock()
        page.evaluate = AsyncMock(return_value={'title':'', 'landed_uri':'about:blank', 'text':'', 'controls':[], 'links':[]})
        async def screenshot(**kwargs): Image.new('RGB',(8,8),'white').save(kwargs['path'])
        page.screenshot = screenshot; page.close = AsyncMock()
        browser.context = MagicMock(); browser.context.new_page = AsyncMock(return_value=page)
        result = asyncio.run(browser.read('https://example.org/'))
        self.assertFalse(result['readable']); self.assertFalse(result['same_application_host'])
        self.assertEqual(result['navigation_error_code'], 'net::ERR_CONNECTION_RESET')
        self.assertTrue(Path(result['image']['path']).is_file())
        self.assertEqual(load_json(result['observation']['path'])['landed_uri'], 'about:blank')

    def test_resume_after_saved_assessment_reuses_model_and_browser(self):
        config = load_json(REPO / 'projects/code/config/batch-synthetic.json')
        calls = []; reads = []
        root = self.root; pool = self.pool
        class Gateway:
            def __init__(self, ledger): pass
            def call(self, job, purpose, text, schema, **kwargs):
                calls.append(purpose)
                if purpose == 'ai-search-plan': return {'queries': ['图书公开目录']}
                if purpose == 'ai-select-results': return {'indices': [0], 'reason': 'fixture'}
                return {k:v for k,v in self_decision.items() if k != 'access' and k != 'evidence_complete'}
        self_decision = {**self.decision(), 'unknowns': [], 'follow_url': ''}
        class Browser:
            def __init__(self, *args): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def read(self, uri):
                rid, old = pool.reserve_tool(config['run_id'], 'browser', uri, {'uri': uri})
                if old is not None: return old
                reads.append(uri)
                image = root / 'page.png'; Image.new('RGB',(8,8),'white').save(image)
                obs = root / 'obs.json'; save_json(obs, {'text':'中文公开图书检索', 'controls':[], 'links':[]})
                result = {'readable': True, 'same_application_host': True, 'http_status': 200,
                    'navigation_error': None, 'observation': reference(obs), 'image': reference(image)}
                pool.settle_tool(rid, 'succeeded', result); return result
        def search(*args, **kwargs):
            return {'request_id': 'fixture', 'results': [{'index': 0, 'uri': 'https://new-site.org/',
                'title': 'Fixture', 'content': '中文图书', 'reference': self.refs[0]}]}
        original = SitePool.assess
        def interrupt_after_save(p, *args):
            original(p, *args); raise KeyboardInterrupt()
        kwargs = dict(pool_path=pool.path, ledger_path=root/'ledger.sqlite3', output=root/'out',
            categories=['图书文化'], target=1, per_category=1, max_rounds=1)
        with patch.object(agent, 'ModelGateway', Gateway), patch.object(agent, 'DiscoveryBrowser', Browser), patch.object(agent, 'glm_search', search):
            with patch.object(SitePool, 'assess', interrupt_after_save):
                with self.assertRaises(KeyboardInterrupt): asyncio.run(agent.discover_ai(config, **kwargs))
            report = asyncio.run(agent.discover_ai(config, **kwargs))
            self.assertEqual(report['status'], 'TARGET_REACHED')
            self.assertEqual(len(calls), 3); self.assertEqual(len(reads), 1)
            self.assertEqual(asyncio.run(agent.discover_ai(config, **kwargs)), report)
            self.assertEqual(len(calls), 3)
        self.assertEqual(self.pool.stats()['assessments'], 1)
        self.assertEqual(report['production_attempts'], 0)

    def test_category_round_robin_does_not_starve_last_category(self):
        config = load_json(REPO / 'projects/code/config/batch-synthetic.json')
        seen = []; pool = self.pool
        categories = ['图书文化', '学习教育', '政务与公共服务查询', '健康科普', '电商浏览']
        class Gateway:
            def __init__(self, ledger): pass
            def call(self, job, purpose, text, schema, **kwargs):
                payload = json.loads(text); seen.append(payload['category'])
                return {'queries': [payload['category'] + '公开检索']}
        class Browser:
            def __init__(self, *args): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        def empty_search(p, run, model, query, output, **kwargs):
            rid, old = p.reserve_tool(run, 'search', query, {'query': query}, maximum=kwargs['maximum'])
            if old is not None: return old
            result = {'request_id': rid, 'results': []}; p.settle_tool(rid, 'succeeded', result); return result
        with patch.object(agent, 'ModelGateway', Gateway), patch.object(agent, 'DiscoveryBrowser', Browser), patch.object(agent, 'glm_search', empty_search):
            result = asyncio.run(agent.discover_ai(config, pool_path=pool.path,
                ledger_path=self.root/'ledger.sqlite3', output=self.root/'out',
                categories=categories, per_category=1, target=5, max_rounds=3, max_searches=5))
        self.assertEqual(seen, categories)
        self.assertEqual(result['status'], 'PARTIAL'); self.assertEqual(result['deficit'], 5)
