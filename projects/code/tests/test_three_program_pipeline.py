"""Controlled fixture only: automatic supply -> tasks -> existing browser/export -> queued QC."""
import asyncio
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/site-planner'),str(REPO/'projects/quality-inspector')]
from site_planner.pipeline import discover, probe
from webcollect.batch_core import BatchLedger, file_sha, load_json, save_json
from webcollect.collect import verify_public_url
from webcollect.task_generation import generate, compile_form
from webcollect.preflight import preflight_plan
from webcollect.planning import publish_plan
from webcollect.collect_runtime import collect_m4
from webcollect.production_facts import derive
from webcollect.client_package import build_client_package
from quality_inspector.ai_worker import prepare, run, report, segments, validate_review, synthetic_review
from quality_inspector.format_checks import sample_check
from quality_inspector.reviews import intake
from m4_runtime_fixtures import make_registry

HTML='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>购物合计</title>
<style>body{font:24px sans-serif;line-height:1.8;margin:32px;background:#eff4e9;color:#18382a}input,button{font:24px sans-serif;padding:12px;width:180px}label{display:block;margin:12px}#result{padding:20px;background:white;border-left:8px solid #2d7651}</style>
<h1>购物合计</h1><p>本页面是受控合成工程页面，仅用于验证自动任务与真实浏览器之间的接口，不属于正式采集数据。</p>
<p>请填写商品数量和商品单价，核对输入内容后计算购物总金额。计算结果保留在当前页面，便于核验每一步操作对应的可见状态。</p>
<form aria-label="购物金额计算" onsubmit="event.preventDefault();document.querySelector('#result').textContent='合计为'+(Number(document.querySelector('#quantity').value)*Number(document.querySelector('#price').value))+'元'">
<label for="quantity">数量</label><input id="quantity" type="number"><label for="price">单价</label><input id="price" type="number"><button id="calculate" type="submit">计算合计</button></form><div id="result">请填写数量和单价后计算合计</div></html>'''


class ThreeProgramTests(unittest.IsolatedAsyncioTestCase):
    async def test_automatic_form_through_actual_browser_and_qc_queue(self):
        retained=os.environ.get('WEBCOLLECT_THREE_PROGRAM_EVIDENCE')
        if retained:
            root=Path(retained).resolve();root.mkdir(parents=True,exist_ok=False)
        else:
            temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        uri=f'http://127.0.0.1:{server.server_port}/'
        def allow_exact_fixture(url,allowed_hosts=None):
            if urlsplit(url).netloc==urlsplit(uri).netloc and urlsplit(url).scheme=='http':return '127.0.0.1'
            return verify_public_url(url,allowed_hosts)
        config=load_json(REPO/'projects/code/config/batch-synthetic.json')
        save_json(root/'config.json',config)
        ledger=BatchLedger(root/'operations.sqlite3',config,initialize=True)
        source={'schema_version':'webcollect-site-sources-1','sources':[{
            'kind':'synthetic-directory','category':'工具','base_uri':uri,
            'html':f'<a href="{uri}">受控购物工具</a><a href="{uri}#same">重复链接</a><a href="javascript:bad()">无效地址</a>'}]}
        save_json(root/'sources.json',source);save_json(root/'mode.json',{'mode':'synthetic','not_production':True})
        (root/'fixture.html').write_text(HTML)
        with patch('site_planner.pipeline.verify_public_url',side_effect=allow_exact_fixture),patch('webcollect.collect.verify_public_url',side_effect=allow_exact_fixture):
            discovered=discover(ledger,root/'sources.json',root/'supply')
            self.assertEqual(discovered['fixed_candidate_count'],1)
            catalog=await probe(ledger,root/'supply/candidates.json',root/'probe',fixture_pages={uri:HTML})
            self.assertEqual(catalog['status_counts'],{'ready':1},json.dumps(catalog))
            before_requests=ledger.summary()['model_requests']
            resumed_catalog=await probe(ledger,root/'supply/candidates.json',root/'probe',fixture_pages={uri:HTML})
            self.assertEqual(ledger.summary()['model_requests'],before_requests)
            self.assertEqual(resumed_catalog['records'],catalog['records'])
            spec={'page_uri':uri,'form_label':'购物金额计算',
                'goal':'在「购物合计」中将「数量」填写为6、将「单价」填写为7，计算并核对合计为42元。',
                'inputs':[{'selector':'#quantity','label':'数量','value':'6'},{'selector':'#price','label':'单价','value':'7'}],
                'submit':{'selector':'#calculate','label':'计算合计'},'completion':{'selector':'#result','contains':'合计为42元'}}
            variant=deepcopy(spec);variant['inputs'][0]['value']='7';variant['goal']='在「购物合计」中将数量填写为7、单价填写为7，计算并核对合计为49元。';variant['completion']['contains']='合计为49元'
            generated=generate(ledger,catalog['catalog_file'],root/'tasks',synthetic_specs={uri:[spec,variant]})
            self.assertEqual(generated['generated_tasks'],1)
            self.assertEqual(len(generated['rejected']),1)
            plan=load_json(generated['plan_file'])
            self.assertEqual(len(plan['tasks'][0]['operations']),5)
            self.assertEqual(generated['sample_ids_allocated'],0)
            bad=deepcopy(spec);bad['inputs'][0]['selector']='#invented'
            with self.assertRaises(ValueError):compile_form(catalog['records'][0],bad)
            ledger.consume('probe_pages','controlled-e2-preflight',1)
            preflight=await preflight_plan(generated['plan_file'],root/'preflight',samples=2,interval_ms=100,preserve_order=True)
            self.assertEqual(preflight['probe_errors'],0)
            scheduled=load_json(root/'preflight/scheduled-plan.json')
            publication=publish_plan(scheduled,catalog)
            save_json(root/'publication.json',publication)
            save_json(root/'capture-policy.json',{'campaign_id':'synthetic-three-program-only','baseline_category_counts':{}})
            registry=make_registry(root/'synthetic-id-registry.sqlite3')
            collected=await collect_m4(root/'preflight/scheduled-plan.json',root/'batches/capture',registry,
                publication_path=root/'publication.json',policy_path=root/'capture-policy.json')
            self.assertEqual(collected['collected'],1,json.dumps(collected))
            resumed=await collect_m4(root/'preflight/scheduled-plan.json',root/'batches/capture',registry,
                publication_path=root/'publication.json',resume=True)
            self.assertEqual(resumed['actual_attempts'],1)
        save_json(root/'facts.json',derive(root/'batches/capture'))
        build_client_package(REPO,root/'batches/capture',root/'candidate',facts=root/'facts.json')
        sample=next((root/'candidate/samples').iterdir())
        mechanical=sample_check(sample)
        self.assertEqual(mechanical['errors'],[],json.dumps(mechanical['errors'],ensure_ascii=False))
        queued=prepare(ledger,root/'candidate',root/'ai')
        self.assertEqual(queued['queued_samples'],1,json.dumps(queued))
        worker=run(ledger)
        self.assertTrue(all(row['state']=='done' for row in worker['outcomes']),worker)
        result=report(ledger,queued['queue_file'],root/'ai-report')
        self.assertEqual(result['raw_model_records'],1)
        self.assertEqual(result['actual_ai_reviewed'],0)
        self.assertFalse(result['release_ready'])
        records,errors,_=intake(result['review_file'],[mechanical],load_json(queued['queue_file'])['contract_sha256'])
        self.assertEqual(records,{})
        self.assertTrue(errors)
        requests=ledger.summary()['model_requests'];self.assertEqual(run(ledger)['outcomes'],[])
        self.assertEqual(ledger.summary()['model_requests'],requests)
        ledger.export(root/'metering')
        # Missing evidence blocks before any new model dispatch.
        damaged=root/'damaged-candidate';shutil.copytree(root/'candidate',damaged)
        (damaged/'samples'/sample.name/'images/step_002.png').unlink()
        blocked=prepare(ledger,damaged,root/'ai-missing')
        self.assertEqual(blocked['mechanically_blocked'],1)
        self.assertEqual(blocked['queued_samples'],0)
        self.assertEqual(ledger.summary()['model_requests'],requests)
        save_json(root/'verification.json',{'scope':'SYNTHETIC controlled integration only','E0':ledger.summary(),
            'E1':{'discovery_candidates':1,'duplicate_links_collapsed':1,'screened_ready':1,'cache_resume_new_requests':0},
            'E2':{'generated_tasks':1,'parameter_only_rejected':1,'actual_fixture_attempts':resumed['actual_attempts'],
                  'effective_actions':5,'client_mechanical_errors':0,'invalid_tasks_allocated_ids':0},
            'E3':{'raw_synthetic_records':1,'actual_ai_reviews':0,'missing_evidence_prevented_model_calls':True,
                  'cached_rerun_new_requests':0,'synthetic_review_import_rejected':True},
            'production_registry_touched':False,'active_human_workspace_touched':False,'release_ready':False})

    def test_segmentation_and_omitted_frame_fail_closed(self):
        groups=segments(list(range(1,14)),5)
        self.assertEqual(groups,[[1,2,3,4,5],[5,6,7,8,9],[9,10,11,12,13]])
        self.assertEqual(set(sum(groups,[])),set(range(1,14)))
        value=synthetic_review([1,2,3]);value['step_observations'].pop()
        with self.assertRaisesRegex(ValueError,'omitted/repeated'):validate_review(value,[1,2,3])


if __name__=='__main__':unittest.main()
