"""S0 no-model task strategies; all inventories/pages are controlled engineering fixtures."""
import asyncio
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/site-planner'),str(REPO/'projects/quality-inspector')]
from webcollect.batch_core import BatchLedger, file_sha, load_json, save_json
from webcollect.task_generation import (compile_form, deterministic_specs, generate,
    semantic_signature, task_signature)
from webcollect.planning import object_sha256, publish_plan
from m4_runtime_fixtures import make_registry


def config(mode='synthetic'):
    value=load_json(REPO/'projects/code/config/batch-no-model.json')
    value['mode']=mode
    value['run_id']='s0-controlled-task-strategy-'+mode
    return value


def capability(root,uri='https://example.org/',mode='synthetic',kind='shopping'):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    evidence=root/'inventory-fixture.json'
    if kind=='shopping':
        title,label,field_labels,submit='购物合计','购物金额计算',['数量','单价'],'计算合计'
    else:
        title,label,field_labels,submit='行程速度','速度计算',['距离（千米）','耗时（小时）'],'计算速度'
    fields=[{'selector':'#'+kind+str(n),'tag':'input','type':'number','label':name,'visible':True,
             'value':'','min':'','max':''} for n,name in enumerate(field_labels)]
    fields.append({'selector':'#'+kind+'submit','tag':'button','type':'submit','label':submit,
                   'visible':True,'value':''})
    inventory={'page_uri':uri,'title':title,'forms':[{'label':label,'fields':fields}],
               'result_targets':[{'selector':'#result','text':'请填写所需条件后计算结果'}]}
    save_json(evidence,{'fixture':True,'inventory':inventory})
    return {'schema_version':'webcollect-site-capability-1','capability_id':'controlled-'+kind,
            'version':object_sha256(inventory)[:24],'site_uri':uri,'site_category':'工具',
            'observed_at':time.time()-1,'expires_at':time.time()+3600,'status':'ready',
            'reason':'Controlled authored fixture only; not real site approval',
            'supported_actions':['click','type','hotkey'],'task_families':['form-workflow'],
            'evidence':[{'path':str(evidence.resolve()),'sha256':file_sha(evidence)}],
            'capabilities':[inventory],'mode':mode,'QC_approval':False}


def catalog(path,records,mode='synthetic'):
    save_json(path,{'schema_version':'webcollect-capability-catalog-1','mode':mode,'records':records,
                    'verification_scope':'controlled engineering inventory; never real site approval'})
    return path


class DeterministicTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_default_generates_two_business_tasks_without_model_and_resumes(self):
        records=[capability(self.root/'shopping',uri='https://example.org/shop',kind='shopping'),
                 capability(self.root/'speed',uri='https://example.org/speed',kind='speed')]
        path=catalog(self.root/'catalog.json',records)
        ledger=BatchLedger(self.root/'operations.sqlite3',config(),initialize=True)
        with patch('webcollect.model_gateway.ModelGateway',side_effect=AssertionError('must not instantiate a gateway')):
            result=generate(ledger,path,self.root/'tasks')
            resumed=generate(BatchLedger(ledger.path,config()),path,self.root/'tasks')
        self.assertEqual(result,resumed)
        self.assertEqual(result['generated_tasks'],2)
        tasks=load_json(result['plan_file'])['tasks']
        self.assertEqual(len({task_signature(t) for t in tasks}),2)
        self.assertEqual(len({semantic_signature(t) for t in tasks}),2)
        self.assertTrue(all(len(t['operations'])==5 for t in tasks))
        self.assertTrue(all({op['action_type'] for op in t['operations']}=={'click','type'} for t in tasks))
        self.assertEqual(ledger.summary()['model_requests'],0)
        self.assertEqual(result['sample_ids_allocated'],0)
        with ledger.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM generated_task_index').fetchone()[0],4)

    def test_parameter_url_and_selector_variants_are_not_distinct_business_tasks(self):
        record=capability(self.root/'base')
        page=record['capabilities'][0]
        form=deepcopy(page['forms'][0]);form['label']='购物总额计算'
        for field in form['fields']:field['selector']=field['selector']+'copy'
        page['forms'].append(form)
        path_variant=deepcopy(record)
        path_variant['capability_id']='same-calculator-at-another-path'
        path_variant['site_uri']='https://example.org/another/calculator'
        path_variant['capabilities'][0]['page_uri']=path_variant['site_uri']
        path_variant['capabilities'][0]['forms']=[deepcopy(form)]
        result=generate(BatchLedger(self.root/'ops.sqlite3',config(),initialize=True),
                        catalog(self.root/'catalog.json',[record,path_variant]),self.root/'tasks')
        self.assertEqual(result['generated_tasks'],1)
        self.assertEqual(len(result['rejected']),2)
        task=load_json(result['plan_file'])['tasks'][0]
        variant=deepcopy(task);variant['initial_url']+='?quantity=8#other';variant['site_uri']+='?mode=other'
        variant['operations'][1]['arguments']['text']='8';variant['task_id']='different-name'
        self.assertEqual(task_signature(task),task_signature(variant))
        self.assertEqual(semantic_signature(task),semantic_signature(variant))
        variant['site_uri']='https://example.org/copied/other-path'
        variant['initial_url']='https://example.org/copied/other-path'
        self.assertEqual(semantic_signature(task),semantic_signature(variant))

    def test_invalid_unknown_and_noop_forms_are_retained_without_ids(self):
        record=capability(self.root/'base')
        records=[]
        for number,mutation in enumerate(('unknown','range','noop','extra','ambiguous','short')):
            row=deepcopy(record);row['capability_id']+='-'+str(number);form=row['capabilities'][0]['forms'][0]
            if mutation=='unknown':form['label']='未知缴费表单'
            elif mutation=='range':form['fields'][0]['min']='100'
            elif mutation=='noop':form['fields'][0]['value']='6'
            elif mutation=='extra':form['fields'].append({**form['fields'][0],'selector':'#extra','label':'未知输入'})
            elif mutation=='ambiguous':row['capabilities'][0]['result_targets'].append({'selector':'#other','text':'其他结果'})
            else:form['fields'].pop(0)
            records.append(row)
        result=generate(BatchLedger(self.root/'ops.sqlite3',config(),initialize=True),
                        catalog(self.root/'catalog.json',records),self.root/'tasks')
        self.assertEqual(result['generated_tasks'],0)
        self.assertEqual(len(result['rejected']),6)
        self.assertEqual(result['sample_ids_allocated'],0)
        self.assertIsNone(result['plan_file'])

    def test_real_config_branch_reads_history_without_api_or_rates(self):
        from test_client_package import fixture as customer_fixture
        from webcollect.task_generation import _history_package_files
        record=capability(self.root/'base',mode='real')
        old=compile_form(record,deterministic_specs(record)['tasks'][0])
        history=self.root/'CONTROLLED-history.sqlite3'
        with sqlite3.connect(history) as con:
            con.execute('CREATE TABLE m4_tasks (task_json TEXT)')
            con.execute('INSERT INTO m4_tasks VALUES(?)',(json.dumps(old),))
        records=[record,capability(self.root/'speed',uri='https://example.org/speed',mode='real',kind='speed')]
        # Exercise the real history contract with a temporary, explicitly
        # synthetic customer-layout population and its own formal anchor. Do not
        # bypass read_customer_history/bind_formal_history or read production DBs.
        delivery=self.root/'controlled-delivery';package=delivery/'fixture-package'
        sample=customer_fixture(package,sid='controlled-history-001')
        save_json(package/'site-list.json',{'schema_version':'webcollect-site-list-1',
            'sites':[{'site_id':'controlled-history-site','uri':'https://history.example.org/',
                      'sample_ids':[sample.name]}],
            'samples':[{'sample_id':sample.name,'site_id':'controlled-history-site'}]})
        (package/'README.md').write_text('Synthetic frozen-history unit fixture; never production or customer evidence.\n')
        latest=delivery/'LATEST.md';latest.write_text('[Synthetic fixture](fixture-package/README.md)\n')
        frozen_files=_history_package_files(package)
        history_set=self.root/'controlled-history-set.json'
        save_json(history_set,{'schema_version':'qc-cumulative-set-1',
            'scope':'Synthetic temporary customer population for real-branch contract testing only',
            'packages':[{'path':str(package),'package_files_sha256':frozen_files}]})
        ledger=BatchLedger(self.root/'ops.sqlite3',config('real'),initialize=True)
        before=file_sha(history)
        with (patch.dict(os.environ,{},clear=True),
              patch('webcollect.model_gateway.ModelGateway',side_effect=AssertionError('model called')),
              patch('webcollect.task_generation.FORMAL_LATEST_PATH',latest)):
            catalog_path=catalog(self.root/'catalog.json',records,'real')
            with self.assertRaisesRegex(ValueError,'frozen customer packages'):
                generate(ledger,catalog_path,self.root/'tasks',history_registry=history)
            self.assertFalse((self.root/'tasks').exists())
            result=generate(ledger,catalog_path,self.root/'tasks',history_registry=history,history_set=history_set)
        self.assertEqual(result['historical_tasks_consulted'],1)
        self.assertEqual(result['generated_tasks'],1)
        self.assertEqual(len(result['rejected']),1)
        self.assertEqual(before,file_sha(history))
        self.assertEqual(ledger.summary()['model_requests'],0)
        self.assertNotIn('currency',ledger.config['budget'])
        self.assertIsNone(ledger.config['model'])
        self.assertEqual(load_json(result['plan_file'])['production_facts']['narrative_mode'],'template')
        self.assertEqual(result['historical_customer_samples_consulted'],1)
        self.assertEqual(result['history_scope']['unknown_strategy_samples'],1)
        self.assertEqual(result['history_scope']['formal_anchor']['path'],str(latest.resolve()))
        self.assertEqual(_history_package_files(package),frozen_files)

    def test_provisional_capability_creates_proposal_without_promoting_readiness(self):
        record=capability(self.root/'base');record['status']='review_required';record['reason']='Pixel semantics still unresolved'
        ledger=BatchLedger(self.root/'ops.sqlite3',config(),initialize=True)
        result=generate(ledger,catalog(self.root/'catalog.json',[record]),self.root/'tasks')
        self.assertEqual(result['generated_tasks'],1)
        self.assertTrue(result['capability_review_required'])
        self.assertEqual(record['status'],'review_required')
        self.assertTrue(load_json(result['plan_file'])['tasks'][0]['capability_review_required'])
        with self.assertRaisesRegex(ValueError,'enabled model branch'):
            generate(ledger,self.root/'catalog.json',self.root/'other',generator='model')

    def test_existing_synthetic_model_generator_is_an_explicit_compatible_option(self):
        record=capability(self.root/'base')
        spec=deterministic_specs(record)['tasks'][0]
        spec.pop('deterministic_strategy')
        spec['completion']={'selector':'#result','contains':'购物合计为42元'}
        variant=deepcopy(spec);variant['inputs'][0]['value']='8'
        variant['completion']['contains']='购物合计为56元'
        cfg=load_json(REPO/'projects/code/config/batch-synthetic.json')
        ledger=BatchLedger(self.root/'ops.sqlite3',cfg,initialize=True)
        result=generate(ledger,catalog(self.root/'catalog.json',[record]),self.root/'tasks',
                        generator='model',synthetic_specs={record['site_uri']:[spec,variant]})
        self.assertEqual(result['generated_tasks'],1)
        self.assertEqual(len(result['rejected']),1)
        self.assertEqual(ledger.summary()['model_requests'],1)
        self.assertEqual(result['generator'],'model')


HTMLS={
'shopping':'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>购物合计</title>
<style>body{font:24px sans-serif;line-height:1.8;margin:32px;background:#eff4e9;color:#18382a}label{display:block}input,button{font:24px sans-serif;padding:12px;width:180px}#result{padding:20px;background:white}</style>
<h1>购物合计</h1><p>本页为受控合成工程页面，仅验证确定性任务与浏览器执行接口，不属于正式采集。请填写商品数量和商品单价，计算并核对购物总金额。</p>
<form aria-label="购物金额计算" onsubmit="event.preventDefault();document.querySelector('#result').textContent='购物合计为'+(Number(document.querySelector('#shopping0').value)*Number(document.querySelector('#shopping1').value))+'元'">
<label for="shopping0">数量</label><input id="shopping0" type="number"><label for="shopping1">单价</label><input id="shopping1" type="number"><button id="shoppingsubmit" type="submit">计算合计</button></form><div id="result">请填写所需条件后计算结果</div></html>''',
'speed':'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>行程速度</title>
<style>body{font:25px serif;line-height:1.7;margin:35px;background:#dfeaf9;color:#19385a}label{display:block}input,button{font:25px serif;padding:14px;width:210px}#result{padding:24px;background:#fff2ce}</style>
<h1>行程速度</h1><p>本页为受控合成工程页面，仅验证另一业务目标和控件组合。请填写行程距离与所用时间，计算并核对平均速度，所有过程保留在当前页面。</p>
<form aria-label="速度计算" onsubmit="event.preventDefault();document.querySelector('#result').textContent='平均速度为'+(Number(document.querySelector('#speed0').value)/Number(document.querySelector('#speed1').value))+'千米/小时'">
<label for="speed0">距离（千米）</label><input id="speed0" type="number"><label for="speed1">耗时（小时）</label><input id="speed1" type="number"><button id="speedsubmit" type="submit">计算速度</button></form><div id="result">请填写所需条件后计算结果</div></html>'''}


class DeterministicBrowserTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(os.environ.get('WEBCOLLECT_S0_TASK_EVIDENCE'),'enable explicit local controlled browser evidence')
    async def test_two_no_model_tasks_through_existing_runtime_and_export(self):
        from playwright.async_api import async_playwright
        from site_planner.pipeline import INVENTORY_JS
        from webcollect.collect import verify_public_url
        from webcollect.preflight import preflight_plan
        from webcollect.collect_runtime import collect_m4
        from webcollect.production_facts import derive
        from webcollect.client_package import build_client_package
        from quality_inspector.format_checks import sample_check
        root=Path(os.environ['WEBCOLLECT_S0_TASK_EVIDENCE']).resolve();root.mkdir(parents=True,exist_ok=False)
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.strip('/') not in HTMLS:
                    self.send_response(404);self.end_headers();return
                body=HTMLS[self.path.strip('/')].encode();self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        def allow_fixture(url,allowed_hosts=None):
            if urlsplit(url).netloc==urlsplit(base).netloc and urlsplit(url).scheme=='http':return '127.0.0.1'
            return verify_public_url(url,allowed_hosts)
        records=[]
        async with async_playwright() as p:
            browser=await p.chromium.launch(channel='chrome',headless=True)
            page=await browser.new_page(viewport={'width':1280,'height':720})
            for kind,html in HTMLS.items():
                uri=base+'/'+kind;await page.goto(uri);inventory=await page.evaluate(INVENTORY_JS);inventory['page_uri']=uri
                row=capability(root/kind,uri=uri,kind=kind)
                row['capabilities']=[inventory]
                (root/kind/'fixture.html').write_text(html)
                await page.screenshot(path=str(root/kind/'inventory.png'))
                row['evidence'].extend({'path':str(path.resolve()),'sha256':file_sha(path)} for path in
                                      (root/kind/'fixture.html',root/kind/'inventory.png'))
                records.append(row)
            await browser.close()
        catalog_file=catalog(root/'catalog.json',records)
        cfg=config();save_json(root/'config.json',cfg)
        ledger=BatchLedger(root/'operations.sqlite3',cfg,initialize=True)
        with patch('webcollect.model_gateway.ModelGateway',side_effect=AssertionError('Model must not be instantiated')),patch(
                'webcollect.collect.verify_public_url',side_effect=allow_fixture):
            generated=generate(ledger,catalog_file,root/'tasks')
        self.assertEqual(generated['generated_tasks'],2,generated)
        plan=load_json(generated['plan_file'])
        with patch('webcollect.collect.verify_public_url',side_effect=allow_fixture):
            await preflight_plan(generated['plan_file'],root/'preflight',samples=2,interval_ms=100,preserve_order=True)
            scheduled=load_json(root/'preflight/scheduled-plan.json')
            save_json(root/'publication.json',publish_plan(scheduled,load_json(catalog_file)))
            save_json(root/'capture-policy.json',{'campaign_id':'controlled-s0-deterministic-only','baseline_category_counts':{}})
            registry=make_registry(root/'CONTROLLED-id-registry.sqlite3')
            captured=await collect_m4(root/'preflight/scheduled-plan.json',root/'batches/capture',registry,
                                     publication_path=root/'publication.json',policy_path=root/'capture-policy.json')
            self.assertEqual(captured['collected'],2,captured)
            resumed=await collect_m4(root/'preflight/scheduled-plan.json',root/'batches/capture',registry,
                                    publication_path=root/'publication.json',resume=True)
            self.assertEqual(resumed['actual_attempts'],2)
        save_json(root/'facts.json',derive(root/'batches/capture'))
        build_client_package(REPO,root/'batches/capture',root/'candidate',facts=root/'facts.json')
        checks=[sample_check(path) for path in sorted((root/'candidate/samples').iterdir())]
        self.assertTrue(all(not check['errors'] for check in checks),checks)
        self.assertEqual(ledger.summary()['model_requests'],0)
        ledger.export(root/'metering')
        save_json(root/'verification.json',{'status':'PASS','scope':'controlled synthetic Chrome pages only; not production',
            'generated_tasks':2,'business_strategies':[task['deterministic_strategy']['id'] for task in plan['tasks']],
            'effective_actions_per_task':[len(task['operations']) for task in plan['tasks']],
            'actual_attempts':resumed['actual_attempts'],'resume_new_attempts':0,'mechanical_errors':sum(len(row['errors']) for row in checks),
            'model_requests_measured':ledger.summary()['model_requests'],'external_model_cost_micros':ledger.summary()['model_cost_micros'],
            'production_registry_modified':False,'active_human_workspace_modified':False,'release_ready':False})
