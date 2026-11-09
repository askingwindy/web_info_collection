"""Login entries are excluded before planning; public login navigation stays public."""
import asyncio
import unittest
from unittest.mock import patch
import test_candidate_entry_engineering as consumer_fixture
import test_producer_v10 as producer_fixture
from webcollect.consumer_page_policy import login_entry_exclusion, LOGIN_ENTRY_VERSION
from webcollect.candidate_batch import first_frame_disposition
from webcollect.candidate_consumer import consume
from site_planner import producer_observation
from site_planner.candidate_discovery import _publish_entry


class LoginEntryIntegration(unittest.IsolatedAsyncioTestCase):
    def test_evidence_routes_login_entries_without_rejecting_public_login_navigation(self):
        states = [
            {'title':'登录','visible_text':'请登录后使用','elements':[{'element_type':'link','text':'公开工具'}]},
            {'landed_uri':'https://tools.example.org/account/login','title':'工具站','text':'输入账号'},
            {'title':'工具站','elements':[{'element_id':'dialog','native_role':'dialog','visible':True,'text':'请登录后使用'}]},
        ]
        for state in states:
            with self.subTest(state=state):
                self.assertEqual(login_entry_exclusion(state)['reason'],'login_page')
                self.assertEqual(first_frame_disposition(state),('abandon','login_page'))
        public={'url':'https://tools.example.org/tool','title':'公开工具','visible_text':'公开计算器 登录 更多工具',
                'elements':[{'element_id':'login','element_type':'link','visible':True,'clickable':True,'text':'登录'}]}
        self.assertIsNone(login_entry_exclusion(public))
        self.assertIsNone(first_frame_disposition(public))

    async def test_consumer_stops_login_and_mandatory_notice_before_model_action_and_attempt(self):
        for notice in (False,True):
            with self.subTest(mandatory_notice=notice):
                f=consumer_fixture.EntryEngineering('test_entry_cli_to_original_save_and_same_page')
                f.setUp();self.addCleanup(f.doCleanups)
                f.surface.state['title']='工具页' if notice else '登录'
                f.surface.state['visible_text']='登录即可免费使用\n受服务器资源影响，请先登录后再使用' if notice else '请登录后使用\n公开工具'
                if notice:
                    f.surface.state['elements'][0].update(text='立即登录',visible=True,clickable=True)
                else:
                    f.surface.state['elements'][0].update(text='公开工具',element_type='link')
                with f.io_boundaries():
                    result=await consume(f.pool,f.claim,f.ledger,output=f.output,registry=f.registry,
                        policy=f.policy_path,history_set=f.chain)
                self.assertEqual(result['disposition'],'abandon')
                self.assertEqual(result['reason'],'explicit_login_required_to_use' if notice else 'login_page')
                self.assertEqual(result['formal_attempts'],0)
                self.assertEqual(f.prompts,[]);self.assertEqual(f.surface.executed,[])
                self.assertTrue(list(f.output.glob('*/first.png')))
                self.assertEqual(f.pool.get_claim(f.claim['claim_id'])['state'],'failed')
                with f.pool.pool.connect() as con:
                    disposition=f.pool.disposition(con,f.claim['candidate_id'])
                self.assertEqual(disposition['policy_version'],LOGIN_ENTRY_VERSION)

    async def test_producer_rejects_original_login_url_before_model_and_new_publication(self):
        f=producer_fixture.ProducerV10('test_same_observation_supplies_dom_and_publication_without_get')
        f.setUp();self.addCleanup(f.doCleanups)
        link=f.link('https://tools.example.org/login');f.observation(link['uri'],'登录\n公开工具')
        with patch('site_planner.producer_observation.DiscoveryBrowser.__aenter__',side_effect=AssertionError('no second browser')):
            admitted,records=await asyncio.to_thread(producer_observation.screen,f.pool,f.ledger,[link],f.root)
        self.assertEqual(admitted,[])
        self.assertEqual(records[0]['decision']['reason'],'login_page')
        header={'row_id':'login-url','run_id':'login-fixture','batch':0,'request_id':'original',
                'response_sha256':'original','raw_index':0}
        result=_publish_entry(f.pool,f.ledger,'login-fixture',f.root,header,f.f.entry(link['uri']),f.f.source,{})
        self.assertEqual((result['result'],result['reason']),('REJECTED','login_page'))
        with f.ledger.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM top_level_visits').fetchone()[0],1)
