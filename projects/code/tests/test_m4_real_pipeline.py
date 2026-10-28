"""Real Chrome + local HTTP fixture through all production machine gates.

Only public-origin validation accepts this exact local test endpoint. Validation,
raw capture audit, metadata, facts, client export and independent QC are real.
No synthetic file or review is accepted as production/customer evidence.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from m4_runtime_fixtures import make_registry
from webcollect.collect import verify_public_url
from webcollect.collect_runtime import collect_m4
from webcollect.planning import publish_plan
from webcollect.preflight import preflight_plan
from webcollect.production_facts import derive
from webcollect.client_package import build_client_package
from webcollect.production_quality import sha
from webcollect.storage import write_json

REPO = Path(__file__).resolve().parents[3]
HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>地理知识核验</title>
<style>body{font:24px sans-serif;line-height:1.7;margin:32px;background:#f6f4ed;color:#172d35}h1{margin:8px 0}button{display:inline-block;font:22px sans-serif;margin:10px 15px 10px 0;padding:12px;background:#dbeedb;border:2px solid #46684e}#result{background:white;padding:15px;border-left:6px solid #4b8052}</style>
<h1>地理知识核验</h1><p>这是一份受控工程页面，用于实际浏览器采集管线验证，不属于正式采集数据。</p>
<p>山地起伏影响降雨分布，河道连接上游山谷与下游平原，居民点集中在交通便利和水源充足的区域。请逐项核验地貌、降雨、河道和居民点，最后汇总核验结果。</p>
<button id="terrain" onclick="mark('terrain','地貌已核验')">核验地貌</button><button id="rain" onclick="mark('rain','降雨已核验')">核验降雨</button><button id="river" onclick="mark('river','河道已核验')">核验河道</button><button id="settlement" onclick="mark('settlement','居民点已核验')">核验居民点</button><button id="summary" onclick="if(done.size===4){document.querySelector('#result').textContent='最终核验完成：地貌、降雨、河道和居民点均已核验。'}">汇总核验结果</button>
<div id="result">等待开始逐项核验</div><script>const done=new Set();function mark(k,t){done.add(k);document.querySelector('#result').textContent=t;}</script></html>'''

class M4RealPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_chrome_five_actions_save_facts_export_and_independent_machine_qc(self):
        retained = os.environ.get('WEBCOLLECT_E2E_EVIDENCE')
        if retained:
            root=Path(retained).resolve();root.mkdir(parents=True,exist_ok=False)
        else:
            temp=tempfile.TemporaryDirectory(prefix='webcollect-controlled-pipeline-')
            self.addCleanup(temp.cleanup);root=Path(temp.name).resolve()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        uri=f'http://127.0.0.1:{server.server_port}/'
        def allow_only_fixture(url,allowed_hosts=None):
            if urlsplit(url).netloc==urlsplit(uri).netloc and urlsplit(url).scheme=='http':return '127.0.0.1'
            return verify_public_url(url,allowed_hosts)
        labels=[('terrain','核验地貌','地貌已核验'),('rain','核验降雨','降雨已核验'),('river','核验河道','河道已核验'),('settlement','核验居民点','居民点已核验'),('summary','汇总核验结果','最终核验完成')]
        operations=[{'operation_id':key,'subgoal_id':key,'action_type':'click','selector':'#'+key,
            'evidence':{'target_label':label},'goal':label,'rationale':'本项是地理知识核验的必要组成部分',
            'expected':result,'postconditions':[{'visible_text':result}],'execution':{'settle_ms':0}}
            for key,label,result in labels]
        task={'task_id':'controlled-geography-check','task_version':'real-pipeline-1','capability_id':'local-check','capability_version':'1',
            'task_family':'controlled-checklist','site_uri':uri,'site_category':'教育','app_name':'地理知识核验','initial_url':uri,
            'instruction':'在「地理知识核验」中核验地貌、降雨、河道和居民点，再汇总核验结果。',
            'task_type':['数据查看'],'stop_when_final':True,'content_preparation':False,'initial_settle_ms':0,
            'required_actions':[key for key,_,_ in labels], 'operations':operations,
            'subgoals':[{'id':key,'description':label,'evidence':[{'operation_id':key,'postcondition_index':0}]} for key,label,_ in labels],
            'final_assertions':[{'visible_text':'最终核验完成'}],'final_result':'地貌、降雨、河道和居民点均已核验。',
            'completion_judgement':'核对当前页面实际显示最终核验完成。'}
        plan={'schema_version':'webcollect-plan-m4-1','tasks':[task],'production_facts':{
            'accounts_and_privacy':'仅本地受控合成页面；无账号、无真实个人数据，不进入正式采集或客户交付集合。',
            'narrative_mode':'template','narrative_generation':'工程测试固定计划，采集器按真实可见状态生成步骤描述。',
            'prompt_stages':{name:{'mode':'template','template_version':'controlled-browser-pipeline-1','description':'固定工程夹具，非历史模型输入。'} for name in ('planning','narrative')}}}
        write_json(root/'input-plan.json',plan);(root/'fixture.html').write_text(HTML)
        write_json(root/'policy.json',{'campaign_id':'engineering-controlled-only','baseline_category_counts':{}})
        registry=make_registry(root/'controlled-registry.sqlite3');batch=root/'capture-batches'/'batch'
        with patch('webcollect.collect.verify_public_url',side_effect=allow_only_fixture):
            preflight=await preflight_plan(root/'input-plan.json',root/'preflight',samples=2,interval_ms=100,preserve_order=True)
            self.assertEqual(preflight['probe_errors'],0)
            scheduled=json.loads((root/'preflight'/'scheduled-plan.json').read_text())
            capability={'schema_version':'webcollect-site-capability-1','capability_id':'local-check','version':'1',
                'site_uri':uri,'site_category':'教育','observed_at':time.time()-1,'expires_at':time.time()+3600,
                'status':'ready','supported_actions':['click'],'task_families':['controlled-checklist'],
                'evidence':[{'path':str(root/'preflight'/'report.json'),'sha256':sha(root/'preflight'/'report.json')}]}
            publication=publish_plan(scheduled,[capability]);write_json(root/'publication.json',publication)
            result=await collect_m4(root/'preflight'/'scheduled-plan.json',batch,registry,
                publication_path=root/'publication.json',policy_path=root/'policy.json')
        write_json(root/'collection-result.json',result)
        self.assertEqual(result['collected'],1,json.dumps(result));self.assertEqual(result['actual_attempts'],1);self.assertEqual(result['rejected'],0)
        manifest=json.loads((batch/'manifest.json').read_text());sid=manifest['samples'][0]
        annotation=json.loads((batch/'samples'/sid/'annotation.json').read_text())
        self.assertEqual([s['action']['action_type'] for s in annotation['steps']],['click']*5+['complete'])
        self.assertEqual(json.loads((batch/'evidence'/sid/'structural_report.json').read_text())['structural_pass'],True)
        self.assertEqual(json.loads((batch/'evidence'/sid/'capture_audit.json').read_text())['capture_evidence_pass'],True)
        self.assertTrue((batch/'metadata.csv').is_file())
        facts=derive(batch);write_json(root/'facts.json',facts)
        self.assertEqual(facts['selection']['total_samples'],1);self.assertEqual(facts['selection']['selected_count'],1)
        exported=build_client_package(REPO,batch,root/'customer-candidate',facts=root/'facts.json',evidence_output=root/'export-evidence.json')
        sys.path.insert(0,str(REPO/'projects'/'quality-inspector'))
        from quality_inspector.engine import inspect
        from quality_inspector.reporting import write_outputs
        qc=inspect(dataset=root/'customer-candidate',inspection_stage='payload');write_outputs(qc,root/'independent-qc')
        mechanical=[c for s in qc['samples'] for c in s['checks'] if c['rule_id'].startswith('C')]
        self.assertTrue(mechanical);self.assertTrue(all(c['status']=='PASS' for c in mechanical),json.dumps(mechanical,ensure_ascii=False))
        semantic=[c for s in qc['samples'] for c in s['checks'] if c['rule_id'].startswith('REVIEW_')]
        self.assertTrue(semantic);self.assertTrue(all(c['status']=='REVIEW_REQUIRED' for c in semantic))
        write_json(root/'engineering-result.json',{'schema_version':'webcollect-controlled-real-pipeline-1','status':'PASS',
            'source':'local HTTP fixture, real Chrome','production_samples':0,'human_review':'NOT_PERFORMED',
            'customer_acceptance':'UNKNOWN','actual_browser_actions':5,'saved_samples':1,
            'pipeline':['real preflight','published M4 plan','real Chrome collect_one','validate_sample','audit_capture','metadata','production_facts','client export','independent QC delivered-file mechanical fields'],
            'only_patched_function':'webcollect.collect.verify_public_url (exact local endpoint only)',
            'mechanical_qc_status':'PASS','semantic_qc_status':'REVIEW_REQUIRED',
            'customer_package_overall_status':qc['status'],
            'evidence_files_sha256':{p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file()}})

if __name__=='__main__':unittest.main()
