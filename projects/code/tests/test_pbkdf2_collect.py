"""Full collect_one control test using saved PBKDF2 DOM structure and footprint.

The card markup is an unmodified fragment of the saved original DOM (SHA256
c76ec7bd3549944080ed86fb5085b298de12aa6b3bd49acb760716530e6e30cc). CSS below replays observed control geometry and the Bootstrap small-input
font/box shape; it is an authored controlled page, not an original page replay.
All routes are fulfilled/aborted locally. WebCrypto computes PBKDF2 independently
of the Python task oracle; no production ID, account, registry or model is used.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from webcollect.pbkdf2_strategy import (URI, TITLE, PASSWORD, SALT, PBKDF2_INVENTORY_JS,
                                       pbkdf2_spec, compile_pbkdf2, pbkdf2_hex)

ORIGINAL_CARD_HTML = '<div class="card">\n      <!-- ── 工具栏 ── -->\n      <div class="card-header d-flex align-items-center flex-wrap" style="gap:6px;">\n        <h4 class="mb-0 mr-2" style="font-size:18px;">\n          <i class="fa fa-cogs"></i> PBKDF2 在线加密工具        </h4>\n        <span class="badge badge-secondary algorithm-badge">密钥派生</span>      </div>\n\n      <div class="card-body">\n        <div class="form-row">\n\n          <!-- ═ 左侧：输入区 ═ -->\n          <div class="col-md-6">\n            <div class="border rounded p-3 mb-2 bg-white h-100">\n\n              <div class="panel-title">\n                <i class="fas fa-user-cog text-secondary"></i>\n                输入要加密的数据\n              </div>\n\n              <!-- 密钥输入 -->\n              <div class="form-group" style="display:none;">\n                <div class="input-group">\n                  <div class="input-group-prepend">\n                    <span class="input-group-text"><i class="fas fa-key mr-1"></i> 密钥</span>\n                  </div>\n                  <input type="password" class="form-control" id="pwd" placeholder="请输入密钥" autocomplete="new-password" style="">\n                  <div class="input-group-append">\n                    <button class="btn btn-outline-secondary" type="button" onclick="togglePwd()" id="togglePwdBtn" title="显示/隐藏密钥">\n                      <i class="fas fa-eye" id="togglePwdIcon"></i>\n                    </button>\n                  </div>\n                </div>\n              </div>\n\n              <!-- SHA-3 输出长度 -->\n              <div id="sha3_options" class="advanced-options" style="display:none;">\n                <h6><i class="fas fa-sliders-h mr-1"></i>SHA-3 输出长度</h6>\n                <select class="form-control form-control-sm" id="sha3_output_length">\n                  <option value="512">512 位（默认）</option>\n                  <option value="384">384 位</option>\n                  <option value="256">256 位</option>\n                  <option value="224">224 位</option>\n                </select>\n              </div>\n\n              <!-- RC4Drop 配置 -->\n              <div id="rc4drop_options" class="advanced-options" style="display:none;">\n                <h6><i class="fas fa-sliders-h mr-1"></i>RC4Drop 参数</h6>\n                <div class="form-group mb-0">\n                  <label for="rc4_drop_words" class="small mb-1">丢弃字数（默认 192）</label>\n                  <input type="number" class="form-control form-control-sm" id="rc4_drop_words" value="192" min="1" style="">\n                  <small class="text-muted">丢弃初始密钥流，防止密钥流泄露</small>\n                </div>\n              </div>\n\n              <!-- PBKDF2 / EvpKDF 字段 -->\n              <div id="pbkdf_fields" class="advanced-options" style="">\n                <h6><i class="fas fa-sliders-h mr-1"></i>密钥派生参数</h6>\n                <div class="form-group">\n                  <div class="input-group input-group-sm">\n                    <div class="input-group-prepend">\n                      <span class="input-group-text">盐（salt）</span>\n                    </div>\n                    <input type="text" class="form-control" id="salt" placeholder="请输入盐值" style="">\n                  </div>\n                </div>\n                <div class="form-group">\n                  <div class="input-group input-group-sm">\n                    <div class="input-group-prepend">\n                      <span class="input-group-text">迭代次数</span>\n                    </div>\n                    <input type="number" class="form-control" id="iterations" value="1000" min="1" placeholder="迭代次数" style="">\n                  </div>\n                </div>\n                <div class="form-group mb-0">\n                  <label class="small mb-1">密钥长度</label>\n                  <select class="form-control form-control-sm" id="key_size">\n                    <option value="4">128 位</option>\n                    <option value="8">256 位</option>\n                    <option value="16">512 位</option>\n                  </select>\n                </div>\n              </div>\n\n              <!-- 对称加密高级选项 -->\n              <div class="advanced-options" style="display:none;">\n                <h6><i class="fas fa-sliders-h mr-1"></i>高级加密选项</h6>\n                <div class="form-group">\n                  <label class="small mb-1">加密模式</label>\n                  <select class="form-control form-control-sm" id="encrypt_mode">\n                    <option value="CBC">CBC — 密码块链接（推荐）</option>\n                    <option value="CFB">CFB — 密码反馈</option>\n                    <option value="CTR">CTR — 计数器模式</option>\n                    <option value="OFB">OFB — 输出反馈</option>\n                    <option value="ECB">ECB — 电子密码本（不安全）</option>\n                  </select>\n                </div>\n                <div class="form-group mb-0">\n                  <label class="small mb-1">填充方式</label>\n                  <select class="form-control form-control-sm" id="padding">\n                    <option value="Pkcs7">Pkcs7（推荐）</option>\n                    <option value="Iso97971">Iso97971</option>\n                    <option value="AnsiX923">AnsiX923</option>\n                    <option value="Iso10126">Iso10126</option>\n                    <option value="ZeroPadding">ZeroPadding</option>\n                    <option value="NoPadding">NoPadding</option>\n                  </select>\n                </div>\n              </div>\n\n              <!-- 文本输入 -->\n              <div class="form-group">\n                <textarea id="message_source" class="form-control" rows="6" spellcheck="false" placeholder="请输入需要加密的字符串" style="font-family: Consolas, monospace; font-size: 13px; resize: vertical;"></textarea>\n              </div>\n\n              <!-- 操作按钮 -->\n              <div class="btn-group" role="group">\n                                  <button type="button" class="btn btn-primary" id="btn-encrypt" onclick="CryptoTool.hash(\'pbkdf2\')">\n                    <span class="btn-spinner spinner-border spinner-border-sm mr-1" role="status"></span>\n                    <span class="btn-text"><i class="fas fa-lock mr-1"></i>加密</span>\n                  </button>\n                                                  <button type="button" class="btn btn-outline-secondary" onclick="CryptoTool.empty()">\n                  <i class="fas fa-undo mr-1"></i>清空\n                </button>\n              </div>\n\n            </div><!-- /.border -->\n          </div><!-- /.col-md-6 left -->\n\n          <!-- ═ 右侧：结果区 ═ -->\n          <div class="col-md-6">\n            <div class="border rounded p-3 mb-2 bg-white h-100 d-flex flex-column">\n\n              <div class="panel-title d-flex align-items-center justify-content-between">\n                <span>\n                  <i class="fas fa-check-circle text-secondary"></i>\n                  加密结果\n                </span>\n                <div class="form-check mb-0">\n                  <input class="form-check-input" type="checkbox" id="upperText" style="">\n                  <label class="form-check-label small font-weight-normal" for="upperText">\n                    转为大写\n                  </label>\n                </div>\n              </div>\n\n              <!-- 结果卡片 -->\n              <div class="card result-card border flex-grow-1 mb-3">\n                <div class="card-body" style="overflow-y:auto; max-height:240px;">\n                  <div id="hash_result" class="placeholder-text">等待输入…</div>\n                </div>\n                <!-- 字节长度信息 -->\n                <div class="card-footer py-1 px-3 text-muted d-flex align-items-center justify-content-between" style="font-size:12px; background:#f8f9fa;">\n                  <span id="result-info">—</span>\n                  <span id="result-time" class="text-muted"></span>\n                </div>\n              </div>\n\n              <!-- 操作按钮 -->\n              <div class="btn-group" role="group">\n                <button type="button" class="btn btn-outline-dark" id="copycode">\n                  <i class="fas fa-clone mr-1"></i>复制结果\n                </button>\n                <button type="button" class="btn btn-outline-secondary" id="downloadResult">\n                  <i class="fas fa-download mr-1"></i>下载\n                </button>\n              </div>\n\n            </div><!-- /.border -->\n          </div><!-- /.col-md-6 right -->\n\n        </div><!-- /.form-row -->\n      </div><!-- /.card-body -->\n    </div>'

FOOTPRINT_CSS = '''
*{box-sizing:border-box}body{margin:0;background:#fff;color:#343a40;font:14px/21px -apple-system,"system-ui","Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif}
.card-header h4{position:fixed;left:41px;top:131px;margin:0;font-size:18px;line-height:22px}
.algorithm-badge{position:fixed;left:268px;top:131px;font-size:12px;line-height:21px}
.panel-title{position:fixed;left:58px;top:202px;width:560px;height:38px;font-size:15px;font-weight:600}
#pbkdf_fields{position:fixed;left:58px;top:249px;width:560px;height:204px}
#pbkdf_fields h6{position:fixed;left:75px;top:268px;width:526px;height:17px;margin:0;font-size:12.25px;line-height:17px}
#pbkdf_fields .input-group-text{position:fixed;left:75px;box-sizing:border-box;height:28.375px;border:1px solid #ced4da;padding:4px 8px;font-size:12.25px;line-height:18.375px;background:#e9ecef}
#pbkdf_fields .form-group:nth-of-type(1) .input-group-text{top:292.4375px;width:76.40625px}
#pbkdf_fields .form-group:nth-of-type(2) .input-group-text{top:336.8125px;width:67px}
#pbkdf_fields input{position:fixed;box-sizing:border-box;height:28.375px;border:1px solid #ced4da;padding:4px 8px;background:white;color:#495057;font:12.25px/18.375px inherit}
#salt{left:149.40625px;top:292.4375px;width:451.59375px;font-size:12.25px!important;line-height:18.375px!important}
#iterations{left:141px;top:336.8125px;width:460px;font-size:12.25px!important;line-height:18.375px!important}
#pbkdf_fields .form-group>label{position:fixed;left:75px;top:384px;font-size:12.25px;line-height:20px}
#key_size{position:fixed;left:75px;top:407.78125px;width:526px;height:28.375px;background:white;border:1px solid #ced4da;padding:4px 8px;font:12.25px/18.375px inherit}
input::placeholder,textarea::placeholder{color:#6c757d;opacity:1}
#message_source{position:fixed;left:58px;top:465.15625px;width:560px;height:131px;border:1px solid #ced4da;padding:6px 12px;background:white;color:#495057;font:13px/19.5px Consolas,monospace!important}
#btn-encrypt{position:fixed;left:58px;top:612.15625px;width:70.25px;height:36px;border:1px solid #007bff;padding:6px 12px;background:#007bff;color:white;font:14px/21px inherit}
button[onclick="CryptoTool.empty()"]{position:fixed;left:127.25px;top:612.15625px;width:72px;height:36px}
.form-row>.col-md-6:nth-child(2)>.border>div:first-child>span{position:fixed;left:662px;top:202px;width:79px;height:27px;font-size:18px;line-height:27px}
#upperText{position:fixed;left:1154px;top:207.390625px;width:13px;height:13px;margin:0}
label[for=upperText]{position:fixed;left:1172px;top:202px;font-size:12.25px}
.result-card{position:fixed;left:662px;top:249px;width:560px;height:310px;border:1px solid #dee2e6;display:flex;flex-direction:column}
.result-card>.card-body{flex:1 1 auto;min-height:1px;padding:20px}.result-card>.card-footer{height:30px;flex:none}
#hash_result{position:fixed;left:683px;top:274px;width:518px;min-height:33px;word-break:break-all}
#hash_result.placeholder-text{font-size:22px;line-height:33px;color:#adb5bd}#hash_result.has-result{font:14px/21px Consolas,monospace;color:#212529}
#result-info{position:fixed;left:679px;top:499px;font-size:12px}#result-time{position:fixed;left:1100px;top:499px;font-size:12px}
#copycode{position:fixed;left:662px;top:620.15625px;width:294.5px;height:36px}#downloadResult{position:fixed;left:955.5px;top:620.15625px;width:266.5px;height:36px}
'''
WEBCRYPTO_HANDLER = '''
window.CryptoJS={algo:{SHA256:{},SHA1:{}}};
CryptoJS.algo.PBKDF2={cfg:{hasher:CryptoJS.algo.SHA256,iterations:250000,keySize:4}};
CryptoJS.PBKDF2=function(){};
window.CryptoTool={hash:async function(type){
 if(type!=='pbkdf2')throw new Error('controlled PBKDF2 only');
 const encoder=new TextEncoder(),password=document.querySelector('#message_source').value,salt=document.querySelector('#salt').value;
 const key=await crypto.subtle.importKey('raw',encoder.encode(password),'PBKDF2',false,['deriveBits']);
 const bytes=new Uint8Array(await crypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',salt:encoder.encode(salt),iterations:Number(document.querySelector('#iterations').value)},key,Number(document.querySelector('#key_size').value)*32));
 const text=[...bytes].map(value=>value.toString(16).padStart(2,'0')).join('');
 document.querySelector('#hash_result').textContent=text;document.querySelector('#hash_result').className='has-result';
 document.querySelector('#result-info').textContent=text.length+' 字符 / '+text.length+' 字节';
 document.querySelector('#result-time').textContent='受控派生完成';
}};
'''


def fixture_html():
    # No remote stylesheet, font, script, image or original inline handler code
    # is fetched/executed. Markup and measured layout are the fixture evidence.
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>' + TITLE + '</title>'
            + '<style>' + FOOTPRINT_CSS + '</style>' + ORIGINAL_CARD_HTML
            + '<script>' + WEBCRYPTO_HANDLER + '</script></html>')


class Pbkdf2FullControlledCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(channel='chrome', headless=True)
        self.context = await self.browser.new_context(viewport={'width':1280,'height':720}, service_workers='block')
        self.local_routes = []
        async def local_only(route):
            self.local_routes.append({'url':route.request.url,'navigation':route.request.is_navigation_request()})
            if route.request.is_navigation_request():
                await route.fulfill(status=200,content_type='text/html; charset=utf-8',body=fixture_html())
            else:
                await route.abort()
        await self.context.route('**/*',local_only)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def test_collect_one_preserves_six_frames_narrative_bindings_and_visible_terminal_schema(self):
        from webcollect.collect import collect_one
        from webcollect.task_contract import PLAN_SCHEMA
        from webcollect.validate import validate_sample
        page=await self.context.new_page();await page.goto(URI)
        inventory=await page.evaluate(PBKDF2_INVENTORY_JS)
        self.assertEqual(inventory['widget_rejections'],[])
        observed={'page_uri':URI,'title':TITLE,'forms':[],'elements':[],**inventory}
        capability={'site_uri':URI,'capability_id':'CONTROLLED-pbkdf2-full-collector',
                    'version':'controlled-real-dom-shape-1','site_category':'工具','status':'review_required',
                    'capabilities':[observed]}
        task=compile_pbkdf2(capability,pbkdf2_spec(capability,observed,observed['widgets'][0],'controlled-test-1'))
        task.update(_plan_schema_version=PLAN_SCHEMA,initial_settle_ms=0)
        await page.close()
        receipt={'scope':'CONTROLLED LOCAL FIXTURE ONLY; no real production sample or ID allocation',
                 'sample_id':'S999999_sample_900001','identifier_is_unallocated_schema_fixture':True,
                 'formal_samples':0,'real_site_visits':0,'model_requests':0,'actual_cash_deduction':'UNKNOWN',
                 'fixture_computation':'WebCrypto PBKDF2-HMAC-SHA256 independent of Python task oracle',
                 'fixture_library_identity':'Authored CryptoJS cfg shim exercises inventory identity checks; original saved CryptoJS separately cross-checked in library-oracle-verification.json',
                 'semantic_status':'REVIEW_REQUIRED','status':'IN_PROGRESS'}
        with tempfile.TemporaryDirectory(prefix='CONTROLLED-pbkdf2-collect-') as directory:
            root=Path(directory);sample=root/receipt['sample_id'];evidence=root/'CONTROLLED-evidence'
            try:
                annotation=await collect_one(self.context,task,sample,evidence,{'sample_id':receipt['sample_id']})
                self.assertEqual(annotation['completion_status'],'success')
                self.assertEqual([s['action']['action_type'] for s in annotation['steps']],
                                 ['click','type','click','type','click','complete'])
                self.assertEqual(len(list((sample/'images').glob('*.png'))),6)
                self.assertEqual(len(list((sample/'ui_tree').glob('*.json'))),6)
                checked=validate_sample(sample,'integration')
                self.assertTrue(checked['structural_pass'],json.dumps(checked,ensure_ascii=False))
                self.assertEqual(checked['effective_steps'],5)
                self.assertEqual(checked['total_steps'],6)
                self.assertFalse(checked['delivery_ready'])
                contract=json.loads((evidence/'task_contract.json').read_text())
                self.assertEqual(contract['machine_status'],'PASS')
                self.assertEqual(contract['semantic_status'],'REVIEW_REQUIRED')
                self.assertEqual(len(contract['executed_operation_ids']),5)
                self.assertEqual(contract['review_binding']['annotation_sha256'],hashlib.sha256((sample/'annotation.json').read_bytes()).hexdigest())
                summary=json.loads((evidence/'capture_summary.json').read_text())
                self.assertEqual(summary['capture_count'],6)
                self.assertGreaterEqual(summary['minimum_chinese_character_ratio'],.7)
                for step in annotation['steps']:
                    number=step['step_id'];raw_path=evidence/f'step_{number:03}.json'
                    raw=json.loads(raw_path.read_text())
                    png=(sample/step['image_path']).read_bytes()
                    self.assertEqual(raw['capture']['screenshot_sha256'],hashlib.sha256(png).hexdigest())
                    tree_file=sample/step['ui_tree_path']
                    self.assertEqual(contract['review_binding']['evidence_sha256'][step['ui_tree_path']],hashlib.sha256(tree_file.read_bytes()).hexdigest())
                    if number<=5:
                        narrative=json.loads((evidence/f'step_{number:03}_narrative.json').read_text())
                        self.assertEqual(narrative['source_raw_sha256'],hashlib.sha256(raw_path.read_bytes()).hexdigest())
                        self.assertEqual(narrative['machine_status'],'PASS')
                        self.assertEqual(narrative['semantic_status'],'REVIEW_REQUIRED')
                        self.assertEqual(narrative['unsupported_quotes'],[])
                        self.assertTrue(narrative['exportable'])
                        self.assertEqual(narrative['after_frame']['screenshot_sha256'],
                                         hashlib.sha256((sample/annotation['steps'][number]['image_path']).read_bytes()).hexdigest())
                final=json.loads((evidence/'step_006.json').read_text())
                expected=pbkdf2_hex(PASSWORD,SALT,1000,4,hash_name='sha256')
                self.assertEqual(final['final_assertions'][0]['actual'],expected)
                self.assertTrue(all(row['passed'] for row in final['final_assertions']))
                self.assertEqual(final['final_assertions'][-1]['display_actual'],'128 位')
                self.assertEqual(final['final_assertions_binding']['screenshot_sha256'],hashlib.sha256((sample/annotation['final_state_image']).read_bytes()).hexdigest())
                self.assertTrue(all(route['url']==URI and route['navigation'] for route in self.local_routes))
                receipt.update(status='PASS',frames=6,trees=6,effective_actions=5,narrative_bindings=5,
                               minimum_chinese_ratio=summary['minimum_chinese_character_ratio'],
                               schema_status='PASS',machine_contract='PASS',local_fulfilled_navigations=len(self.local_routes))
            except Exception as error:
                receipt.update(status='FAIL',error_type=type(error).__name__,error=str(error),
                               frames=len(list((sample/'images').glob('*.png'))) if sample.exists() else 0)
                raise
            finally:
                (root/'CONTROLLED-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
                destination=os.environ.get('WEBCOLLECT_PBKDF2_COLLECT_EVIDENCE')
                if destination:
                    output=Path(destination)/self._testMethodName
                    output.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copytree(root,output)


if __name__=='__main__':
    unittest.main()
