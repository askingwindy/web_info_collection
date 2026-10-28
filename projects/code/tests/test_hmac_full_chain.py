"""Five HMAC actions / six original frames on saved-real-CSS local fixtures.

Every browser request is intercepted; no production registry or real-site run.
The fixture computes with browser WebCrypto while the task oracle uses Python.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from playwright.async_api import async_playwright
from webcollect.collect import collect_one
from webcollect.hmac_strategy import URI, KEY, MESSAGE, hmac_sha256
from webcollect.task_contract import PLAN_SCHEMA
from test_hmac_strategy import compiled

HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>HMACSHA256 在线加密工具 | 菜鸟工具</title>
<style>body{margin:0;background:white;color:#343a40;font:14px/21px -apple-system,"system-ui","Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif}
nav{position:absolute;left:20px;top:20px;height:40px;word-spacing:15px}.card-header{position:absolute;left:40px;top:124px;display:flex;align-items:center;gap:20px;height:35px}h4{font-size:18px;margin:0}.algorithm-badge{color:white;background:#17a2b8;padding:0 10px}
.form-row{position:absolute;left:36px;top:185.59375px;width:1208px;height:328.25px}
.panel-title{position:absolute;left:22px;top:15px}.result-title{left:626px}
.input-group{position:absolute;left:22px;top:68.25px;width:560px;height:36px;display:flex}
.input-group-prepend{position:absolute;left:0;top:0;width:72px;height:36px;display:flex}.input-group-text{box-sizing:border-box;display:flex;align-items:center;width:72px;height:36px;padding:6px 10px;background:#e9ecef;border:1px solid #ced4da}
#pwd{box-sizing:border-box;position:absolute;left:71px;top:0;width:448.25px;height:35px;padding:6px 12px;border:1px solid #ced4da;background:white;color:#495057;font:14px/21px -apple-system,"system-ui","Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;overflow:clip}
#pwd::placeholder{color:#7c8791;opacity:1}.input-group-append{position:absolute;left:518.25px;top:0;width:41.75px;height:36px}.input-group-append button{box-sizing:border-box;width:41.75px;height:36px}
#message_source{box-sizing:border-box;position:absolute;left:22px;top:120.25px;width:560px;height:131px;padding:6px 12px;border:1px solid #ced4da;background:white;color:#495057;font:13px/19.5px Consolas,monospace;resize:vertical}
#message_source::placeholder{color:#7c8791;opacity:1}#btn-encrypt{position:absolute;left:22px;top:267.25px;height:36px;padding:6px 12px}#clear{position:absolute;left:100px;top:267.25px;height:36px}
#upperText{position:absolute;left:1118px;top:17px}label[for=upperText]{position:absolute;left:1138px;top:15px;font-size:12px}
#hash_result{box-sizing:border-box;position:absolute;left:626px;top:68.25px;width:560px;height:160px;padding:16px;border:1px solid #e4d7c5;background:white;overflow:auto;word-break:break-all;white-space:pre-wrap;font:16px/27.2px Courier New,Consolas,monospace}
#result-info{position:absolute;left:642px;top:240px}#result-time{position:absolute;left:1050px;top:240px}.copy{position:absolute;left:626px;top:277px}footer{position:absolute;left:40px;top:550px;width:1180px;line-height:32px;word-spacing:18px}</style>
<nav>WEB在线工具 在线画图 SVG在线工具 AI数据分析 菜鸟教程 AI 导航 更多频道</nav>
<div class="card"><div class="card-header"><h4>HMACSHA256 在线加密工具</h4><span class="algorithm-badge">HMAC</span></div>
<div class="form-row"><div class="panel-title">输入要加密的数据</div><div class="panel-title result-title">加密结果</div>
<div class="input-group"><div class="input-group-prepend"><span class="input-group-text"><i class="fas fa-key"></i> 密钥</span></div>
<input type="password" id="pwd" placeholder="请输入密钥" autocomplete="new-password">
<div class="input-group-append"><button type="button" title="显示/隐藏密钥"><i class="fas fa-eye"></i></button></div></div>
<textarea id="message_source" rows="6" placeholder="请输入需要加密的字符串"></textarea>
<button id="btn-encrypt" type="button" onclick="CryptoTool.hash('hmacsha256')">加密</button><button id="clear" type="button">清空</button>
<input id="upperText" type="checkbox"><label for="upperText">转为大写</label>
<div id="hash_result" class="placeholder-text">等待输入…</div><span id="result-info">—</span><span id="result-time"></span><div class="copy">复制结果　下载</div></div></div>
<footer>加密工具列表　29　全部　29　对称加密　7　哈希算法　8　HMAC　6　密钥派生　2　编码方式　6<br>对称加密　哈希算法　密钥派生　编码方式</footer>
<script>window.CryptoTool={hash:async function(type){if(type!=='hmacsha256')throw Error('fixture supports only observed HMAC-SHA256');
 const enc=new TextEncoder(),key=await crypto.subtle.importKey('raw',enc.encode(document.querySelector('#pwd').value),{name:'HMAC',hash:'SHA-256'},false,['sign']);
 const raw=await crypto.subtle.sign('HMAC',key,enc.encode(document.querySelector('#message_source').value));
 const result=[...new Uint8Array(raw)].map(x=>x.toString(16).padStart(2,'0')).join('');
 document.querySelector('#hash_result').textContent=result;document.querySelector('#hash_result').className='has-result';
 document.querySelector('#result-info').textContent=result.length+' 字符 / '+result.length+' 字节';}};</script></html>'''


class HmacFullChainTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_real_css_five_actions_six_frames_all_narratives_and_terminal_are_bound(self):
        retained = os.environ.get('WEBCOLLECT_HMAC_LOCAL_CHAIN_EVIDENCE')
        if retained:
            root = Path(retained).resolve()
            root.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        (root / 'fixture.html').write_text(HTML)
        (root / 'scope.json').write_text(json.dumps({'scope': 'controlled intercepted local browser fixture only; no real source access',
            'business': 'HMAC-SHA256', 'production_registry_modified': False, 'production_ids_allocated': 0,
            'external_model_requests': 0, 'not_part_of_formal_1000': True}, ensure_ascii=False, indent=2) + '\n')
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel='chrome', headless=True)
            self.addAsyncCleanup(browser.close)
            context = await browser.new_context(viewport={'width': 1280, 'height': 720}, locale='zh-CN', timezone_id='Asia/Shanghai')
            await context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body=HTML))
            task = compiled()
            task['_plan_schema_version'] = PLAN_SCHEMA
            task['initial_settle_ms'] = 0
            annotation = await collect_one(context, task, root / 'sample', root / 'evidence', {'sample_id': 'CONTROLLED_hmac_fullchain_000001'})
            self.assertEqual([step['action']['action_type'] for step in annotation['steps']], ['click', 'type', 'click', 'type', 'click', 'complete'])
            self.assertEqual(len(list((root / 'sample/images').glob('*.png'))), 6)
            self.assertEqual(len(list((root / 'sample/ui_tree').glob('*.json'))), 6)
            for n in range(1, 6):
                evidence = json.loads((root / f'evidence/step_{n:03}_narrative.json').read_text())
                self.assertEqual(evidence['machine_status'], 'PASS', (n, evidence))
                self.assertTrue(evidence['exportable'])
                self.assertEqual(evidence['unsupported_quotes'], [])
                self.assertNotIn(KEY, evidence['proposed_text'])
            self.assertIn(hmac_sha256(MESSAGE, KEY), annotation['final_result'])
            self.assertNotIn(KEY, annotation['final_result'])
            contract = json.loads((root / 'evidence/task_contract.json').read_text())
            self.assertEqual(contract['machine_status'], 'PASS')
            self.assertEqual(contract['semantic_status'], 'REVIEW_REQUIRED')
            self.assertEqual(contract['narrative_review_required_steps'], [])
            self.assertEqual(len(contract['executed_operation_ids']), 5)
            capture_summary = json.loads((root / 'evidence/capture_summary.json').read_text())
            self.assertGreaterEqual(capture_summary['minimum_chinese_character_ratio'], .7)
            self.assertEqual(capture_summary['capture_count'], 6)
            self.assertEqual(capture_summary['preparation_actions'], 0)
            summary = {'status': 'PASS', 'scope': 'controlled local intercepted browser only; no real source execution',
                       'effective_actions': 5, 'original_png_frames': 6, 'ui_trees': 6, 'bound_narratives': 5,
                       'minimum_chinese_character_ratio': capture_summary['minimum_chinese_character_ratio'],
                       'machine_contract_status': contract['machine_status'], 'semantic_status': 'REVIEW_REQUIRED',
                       'final_digest': hmac_sha256(MESSAGE, KEY), 'external_model_requests': 0, 'new_production_ids': 0,
                       'files_sha256': {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                        for path in sorted(root.rglob('*')) if path.is_file()}}
            (root / 'verification-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
