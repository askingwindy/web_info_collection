"""Real controlled browser + original ledger integration; no external model in this suite."""
import asyncio
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch,AsyncMock
from PIL import Image

from site_planner.candidate_pool import CandidatePool
from site_planner.site_pool import SitePool
from site_planner.discovery_tools import DiscoveryBrowser
from site_planner import page_consumption as images,producer_observation as observed
from site_planner.producer_read_policy import VERSION,image_recheck_delay
from site_planner.producer_page_feedback import snapshot
from site_planner.producer_query_plan import next_query
from webcollect.batch_core import BatchLedger,load_json,OutcomeUnknown


class LocalLedger(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);self.root=Path(folder.name)
        config=load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')
        self.ledger=BatchLedger(self.root/'jobs.db',config,initialize=True)
        SitePool(self.root/'pool.db',initialize=True);self.pool=CandidatePool(self.root/'pool.db',install=True)


class BrowserPolicy(LocalLedger):
    def test_real_browser_success_delayed_content_images_failures_and_replay(self):
        png=io.BytesIO();Image.new('RGB',(32,32),'blue').save(png,format='PNG')
        counts={}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                counts[self.path]=counts.get(self.path,0)+1
                if self.path=='/disconnect':
                    self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
                status=int(self.path[1:]) if self.path in ('/403','/404','/521') else 200
                if self.path=='/img':
                    time.sleep(.45);data=png.getvalue();kind='image/png'
                else:
                    kind='text/html; charset=utf-8'
                    html='<main><h1>中文工具</h1><p>请输入长度并选择单位进行换算。</p><input><button>计算</button></main>'
                    if self.path=='/late':html='<main></main><script>setTimeout(()=>document.querySelector("main").innerHTML="<p>延迟到达的实际业务内容</p>",600)</script>'
                    if self.path=='/poster':html='<style>body{margin:0}img{width:100vw;height:100vh}</style><img src="/img">'
                    if self.path=='/changing':html='<style>body{margin:0}img{width:100vw;height:100vh}</style><img src="/img"><script>setTimeout(()=>document.querySelector("img").remove(),800)</script>'
                    if self.path=='/move':html+='<script>setTimeout(()=>location.replace("/static"),50)</script>'
                    data=('<!doctype html><meta charset="utf-8">'+html).encode()
                self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        for target in ('site_planner.discovery_tools.verify_public_url','site_planner.site_pool.verify_public_url',
                       'site_planner.pipeline.verify_public_url','webcollect.collect.verify_public_url'):
            allowance=patch(target);allowance.start();self.addCleanup(allowance.stop)
        results={}
        async def collect():
            async with DiscoveryBrowser(self.pool.pool,self.ledger,images.SCREEN_RUN,self.root/'evidence',
                    image_screen=True,capture_document=True,fresh_pages=True,read_policy=VERSION) as browser:
                for suffix in ('/403','/404','/521','/static','/late','/poster','/changing'):
                    results[suffix]=await browser.read(base+suffix)
                with self.assertRaises(OutcomeUnknown):await browser.read(base+'/disconnect')
                with self.assertRaises(OutcomeUnknown):await browser.read(base+'/move')
                from playwright.async_api import Error
                with patch('site_planner.producer_read_policy.wait_ready',new=AsyncMock(side_effect=Error('Execution context was destroyed, most likely because of a navigation'))):
                    with self.assertRaises(Error):await browser.read(base+'/context-navigation')
        # Localhost allowance exists only in this fixture; production URL policy is unchanged.
        with patch('site_planner.discovery_tools.verify_public_url'):
            asyncio.run(collect())
        for suffix in ('/403','/404','/521'):
            result=results[suffix];self.assertIn('http_failure',result);self.assertNotIn('image',result)
            self.assertFalse(list(Path(result['http_failure']['path']).parent.glob('*.png')))
        static=load_json(results['/static']['observation']['path'])
        self.assertEqual(static['read_timing']['readiness_reason'],'visible_content_stable')
        self.assertLess(static['read_timing']['readiness_seconds'],1.2)
        self.assertEqual(static['read_timing']['image_recheck_delay_ms'],0)
        self.assertIn('image_view_after',static)
        late=load_json(results['/late']['observation']['path'])
        self.assertIn('延迟到达的实际业务内容',late['text'])
        poster=load_json(results['/poster']['observation']['path'])
        self.assertEqual(poster['read_timing']['image_recheck_delay_ms'],1200)
        self.assertEqual(images.register(self.pool,self.ledger,results['/poster'])['status'],'NO_CONSUME')
        self.assertNotEqual(images.register(self.pool,self.ledger,results['/changing'])['status'],'NO_CONSUME')
        observed.from_pool(self.pool,self.ledger,base+'/static')
        before=dict(counts)
        links=[{'uri':base+p} for p in ('/403','/404','/521','/static','/disconnect','/move','/context-navigation')]
        with patch.object(images,'_probe',side_effect=AssertionError('original requests cannot resend')):
            admitted,records=images.screen(self.pool,self.ledger,links,self.root)
            repeated=images.screen(self.pool,self.ledger,links,self.root)
        self.assertEqual(admitted,[{'uri':base+'/static'}]);self.assertEqual(repeated[0],admitted)
        self.assertEqual(records[0]['decision']['status'],'DISCARDED')
        self.assertEqual(counts,before)
        with self.ledger.connect() as con:
            states=dict(con.execute('SELECT state,COUNT(*) FROM top_level_visits GROUP BY state'))
            self.assertEqual(con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0],0)
        self.assertEqual(states,{'failed':3,'succeeded':4,'unknown':3})
        ref=results['/521']['http_failure'];Path(ref['path']).write_text('{}')
        with self.assertRaises(ValueError):images.screen(self.pool,self.ledger,[{'uri':base+'/521'}],self.root)

    def test_second_observation_delay_preserves_image_threshold_and_unknown_inventory(self):
        for width,delay in ((94.999,0),(95,1200),(100,1200)):
            view={'schema_version':images.OBSERVATION_VERSION,'screen_resolution':[100,100],
                  'inventory_complete':True,'elements':[{'element_type':'image','visible':True,'bbox':[0,0,width,100]}]}
            self.assertEqual(image_recheck_delay(view)[0],delay)
            self.assertEqual(image_recheck_delay(view,pending_images=1)[0],1200)
            self.assertEqual(image_recheck_delay({**view,'inventory_complete':False})[0],1200)
        self.assertEqual(image_recheck_delay({})[0],1200)


class PageFeedback(LocalLedger):
    def visit(self,suffix,state,status=None,code=None):
        uri='https://feedback.example.org/'+suffix
        jid=self.ledger.enqueue('site-discovery-page',{'uri':uri});job=self.ledger.claim('site-discovery-page',job_id=jid)
        from site_planner.pipeline import reserve_visit
        visit=reserve_visit(self.ledger,job,uri,'discovery-read')
        self.ledger.settle_visit(visit,state=state,response_status=status,landed_uri=uri)
        self.ledger.finish(job,result={'navigation_error_code':code})

    def test_summary_separates_outcomes_and_freezes_original_planner_input(self):
        self.visit('good','succeeded',200);self.visit('bad','failed',521)
        self.visit('unknown','unknown',code='net::ERR_SSL_PROTOCOL_ERROR')
        summary,ref=snapshot(self.ledger,self.root)
        host=summary['hosts'][0]
        self.assertEqual([host[k] for k in ('http_succeeded','confirmed_http_failed','unknown')],[1,1,1])
        self.assertEqual(len(load_json(ref['path'])['visits']),3)
        state={'queries':{},'blocked':{}}
        options=dict(independent=True,purpose_grounded=True,purpose_protocol='entry-tools-13',page_feedback=True)
        with patch('site_planner.producer_query_plan.model_decision',side_effect=OutcomeUnknown('controlled interruption')):
            with self.assertRaises(OutcomeUnknown):next_query(self.pool.pool,self.ledger,'run','one',['在线工具'],state,[],self.root,**options)
        frozen=self.pool.pool.checkpoint('run','category-query-plan/one/input')
        self.assertEqual(frozen['version'],'producer-category-query-4')
        self.assertEqual(frozen['page_visit_feedback'],summary)
        self.visit('new','failed',403)
        plan={'queries':['中文在线面积换算','公开长度转换工具']}
        with patch('site_planner.producer_query_plan.model_decision',return_value=plan) as model:
            result=next_query(self.pool.pool,self.ledger,'run','one',['在线工具'],state,[],self.root,**options)
            replay=next_query(self.pool.pool,self.ledger,'run','one',['在线工具'],state,[],self.root,**options)
        self.assertEqual(model.call_count,1);self.assertEqual(model.call_args.args[3],frozen)
        self.assertEqual(result,replay)
        self.assertEqual(result['reason']['rule'],'producer-category-query-4')
        self.assertEqual(self.pool.pool.checkpoint('run','category-query-plan/one/input'),frozen)
        with self.ledger.connect() as con:self.assertEqual(con.execute("SELECT COUNT(*) FROM top_level_visits WHERE state='unknown'").fetchone()[0],1)


class OptimizationBatch(unittest.TestCase):
    def test_opt_in_freezes_and_resume_does_not_switch_or_dispatch(self):
        import test_producer_pipeline_overlap as fixture
        f=fixture.PipelineOverlap('runTest');f.setUp();self.addCleanup(f.doCleanups)
        home=f.home();seen=[]
        def screen(pool,ledger,links,root,**options):
            seen.append(options);return f.settle_screen(pool,ledger,links,root)
        opener=f.f.f.b.f.f.provider.opener
        options=dict(target=2,batch_size=2,max_batches=1)
        with patch.object(observed,'screen',side_effect=screen),patch.object(opener,'open',side_effect=f.provider):
            report=f.run_overlap(home,key='opt',producer_optimization='observation-feedback-1',**options)
            before=len(seen);replay=f.run_overlap(home,key='opt',**options)
            self.assertEqual(len(seen),before)
            self.assertEqual(replay['new_dispatches'],{'model':0,'GET':0,'search':0})
            self.assertEqual(report['listed_unique_candidates'],2,report)
            self.assertTrue(all(s=={'read_policy':VERSION} for s in seen))
            self.assertEqual(f.frozen_config(f.run_id('opt'))['producer_optimization'],'observation-feedback-1')
            f.run_overlap(home,key='legacy',**options)
            with self.assertRaisesRegex(ValueError,'Frozen producer_optimization'):
                f.run_overlap(home,key='legacy',producer_optimization='observation-feedback-1',**options)
            with self.assertRaisesRegex(ValueError,'requires entry-tools-13'):
                f.run_overlap(home,key='wrong',producer_optimization='observation-feedback-1',**options)


if __name__=='__main__':unittest.main()
