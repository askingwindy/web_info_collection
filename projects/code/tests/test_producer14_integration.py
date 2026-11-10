"""One bounded integration of new producer policy and original protocol readers."""
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from site_planner import producer_business_content as business, producer_eligibility as eligibility
from site_planner.qualification import CANONICAL_CATEGORIES,CATEGORY_TAXONOMY_VERSION,CANONICAL_SCHEMA,BUSINESS_CATEGORIES,BUSINESS_TAXONOMY_VERSION,_category_contract
from site_planner.entry_selection import confirmed_category,VERSION
from site_planner.discovery_tools import reference
from site_planner.application_discovery import homepage_document,RedirectBoundaryError
from site_planner.pipeline import open_public_get
from webcollect.batch_core import BatchLedger,save_json,load_json
from webcollect.planning import object_sha256
import test_grounded_producer as grounded


class Producer14Integration(unittest.TestCase):
    def fixture(self):
        f=grounded.Grounded('test_formal_CLI_seed_expansion_rules_provenance_and_restart_zero_IO')
        f.setUp();self.addCleanup(f.doCleanups);return f

    def test_old_taxonomy_and_new_consumer_category_binding(self):
        self.assertEqual(len(CANONICAL_CATEGORIES),15);self.assertNotIn('音乐',CANONICAL_SCHEMA['properties']['category']['enum'])
        self.assertIn('音乐',BUSINESS_CATEGORIES)
        self.assertEqual(_category_contract({'category_policy':'canonical-site-category-1','category_taxonomy_version':CATEGORY_TAXONOMY_VERSION,'category_schema_sha256':object_sha256(CANONICAL_SCHEMA)})[1],CANONICAL_SCHEMA)
        source={'selection_version':VERSION,'application_classification':{'version':VERSION,'taxonomy_version':BUSINESS_TAXONOMY_VERSION,'status':'EVIDENCE_BOUND_AI','parent_category':'音乐','evidence':[{'role':'identity'},{'role':'function'}]}}
        self.assertEqual(confirmed_category([source]),'音乐')

    def test_new_entrypoint_freezes_v14_without_breaking_old_v4(self):
        f=self.fixture();_,home=f.site()
        with patch('site_planner.producer_observation.screen',return_value=([],[])):
            report=f.run_new(home,key='v14',target=1,model_protocol='entry-tools-14',discovery_mode='expand',site_expansion=True,allowed_hosts=['tools.example.org'],search_engine='public',producer_optimization='observation-feedback-1',max_batches=1)
        with f.pool.pool.connect() as con:
            frozen=json.loads(con.execute('select config from runs where id=?',(report['batch_scope'],)).fetchone()[0])
        self.assertEqual(frozen['site_protocol'],'producer-site-classification-6')
        self.assertEqual(frozen['purpose_version'],business.VERSION_V3)
        self.assertEqual(frozen['page_eligibility_policy'],eligibility.VERSION)

    def test_visible_main_unit_cannot_borrow_later_dom_tail(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'obs.json';save_json(p,{'visible_text':'页面已经可见'+('甲'*70)})
            ev={'observation':reference(p),'units':[{'text':'甲'*70+'后来的不可见内容','kind':'body','region':'main'}]}
            self.assertEqual(eligibility.visible_units(ev)[0],[])

    def test_language_japanese_rejects_code_and_numbers_do_not(self):
        self.assertEqual(eligibility.assess({'visible_text':'メッセージを送る 相手に表示する名前 ルームを作成'})['status'],'REJECTED')
        self.assertNotEqual(eligibility.assess({'visible_text':'在线JSON格式化，输入内容查看结果。\n{"hello_world":12345,"active":true}\n000001'})['status'],'REJECTED')

    def test_business_information_allowed_policy_and_login_dependency_rejected(self):
        unit={'kind':'body','region':'main','text':'仅限18周岁以下客户，免收工本费。','unit_id':'u0'}
        ev={'units':[unit],'menu':{'q0':unit},'structures':[],'page_eligibility':{'status':'UNKNOWN'}}
        proposal={'business':'public_business','business_quote_ids':['q0'],'content_kind':'business_information','public_access':'public_content'}
        self.assertTrue(business.assess(proposal,ev,policy=business.VERSION_V3)['selected'])
        self.assertFalse(business.assess({**proposal,'public_access':'login_required'},ev,policy=business.VERSION_V3)['selected'])
        ev['units'].append({'kind':'heading','region':'main','text':'售后政策'})
        self.assertFalse(business.assess(proposal,ev,policy=business.VERSION_V3)['selected'])

    def test_local_http_redirect_records_observed_but_not_followed(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path=='/redirect':self.send_response(302);self.send_header('Location','http://localhost:'+str(self.server.server_port)+'/target');self.end_headers()
                else:self.send_response(200);self.end_headers();self.wfile.write(b'ok')
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);t=threading.Thread(target=server.serve_forever,daemon=True);t.start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url='http://127.0.0.1:'+str(server.server_port)+'/redirect';metrics={}
        def check(value):
            if 'localhost' in value:raise RedirectBoundaryError('explicit boundary')
        with self.assertRaises(RedirectBoundaryError):open_public_get(url,time.monotonic()+5,metrics,check)
        self.assertEqual(metrics['redirects'][0]['status'],302);self.assertFalse(metrics['redirects'][0]['followed'])
        metrics={}
        with open_public_get(url,time.monotonic()+5,metrics,lambda value:None) as response:self.assertEqual(response.read(),b'ok')
        self.assertTrue(metrics['redirects'][0]['followed'])

    def test_known_redirect_rejection_receipt_replays_without_get(self):
        f=self.fixture();ledger=BatchLedger(f.root/'redirect.db',f.f.cfg,initialize=True);uri='https://tools.example.org/'
        def fetch(url,deadline,metrics,check):
            metrics['redirects']=[{'from':uri,'to':'https://foreign.example.net/','status':302,'observed':True,'followed':False}]
            check('https://foreign.example.net/')
        with patch('site_planner.pipeline.open_public_get',side_effect=fetch) as get:
            for batch in ['one','two']:
                with self.assertRaises(ValueError):homepage_document(ledger,batch,uri,f.root,allowed_hosts=['tools.example.org'],redirect_policy='producer-redirect-boundary-2')
        self.assertEqual(get.call_count,1)
        with ledger.connect() as con:row=con.execute("select state,result from jobs where kind='application-evidence-get'").fetchone()
        self.assertEqual(row['state'],'failed');self.assertEqual(load_json(json.loads(row['result'])['path'])['observed_redirect_target'],'https://foreign.example.net/')

    def test_quarantine_preserves_claimed_and_original_evidence(self):
        f=self.fixture();_,home=f.site();f.run_new(home,key='rows',target=2)
        rows=f.pool.rows(protocols=('webcollect-data-candidate-2',));first,second=rows[:2]
        claim=f.pool.claim_next('fixture','claim',candidate_id=first['candidate_id'],protocols=('webcollect-data-candidate-2',))
        self.assertIsNotNone(claim)
        self.assertEqual(f.pool.reject_unconsumed(first['candidate_id'],'bad language',evidence=[home['reference']],only_never_claimed=True)['result'],'SKIPPED')
        self.assertEqual(f.pool.reject_unconsumed(second['candidate_id'],'confirmed售后条款',evidence=[home['reference']],only_never_claimed=True)['result'],'QUARANTINED')
        with f.pool.pool.connect() as con:self.assertEqual(con.execute('select count(*) from candidate_sources where candidate_id=?',(second['candidate_id'],)).fetchone()[0],len(second['sources']))

    def test_original_unknown_keeps_receipt_and_new_policy_cannot_resend(self):
        import test_producer_business_content as fixtures
        f=fixtures.BusinessContent('test_new_unknown_is_not_resent_under_another_chunk');f.setUp();self.addCleanup(f.doCleanups)
        link=f.original()
        with patch.object(f.f.f.b.f.f.provider.opener,'open',side_effect=TimeoutError('original unknown')) as send,patch('webcollect.model_gateway.time.sleep'):
            rows,first=business.classify(f.ledger,[link],'original',f.root,pool=f.pool)
            rows2,second=business.classify(f.ledger,[link],'new-policy',f.root,pool=f.pool,policy=business.VERSION_V3)
        self.assertEqual(send.call_count,1);self.assertEqual(rows,[]);self.assertEqual(rows2,[])
        self.assertEqual(first['records'][0]['status'],'HELD');self.assertEqual(second['records'][0]['status'],'HELD')
        self.assertTrue(second['records'][0]['original_requests'])
