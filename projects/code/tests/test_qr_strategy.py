"""Controlled offline QR arithmetic/encoding and saved-pixel oracle tests."""
import base64
from hashlib import sha256
from io import BytesIO
import sys
import unittest
from PIL import Image
from webcollect.qr_strategy import URI,matches_uri,wifi_payload,verify_qr_png

# Original Core Image generated controlled fixture, independent of any website.
# Payload: CONTROLLED QR / 测试数据 / 20261027. PNG SHA256:
# 00e204050c30ad24670e12b90107734e572085998bf3f9d77443086b86328d09
CONTROLLED_QR_BASE64=(
    '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'
    '1qv9077VdV/Uqph6AgsCgrqAbksCVQFBrYqpJ7AgIKgL6LYkUBUQ1KqYegILAoK6gG5LAlUBQa2KqSewIHDNO+qCzY+2TO9s6V2u'
    'uknqM71vmrM6T+pTXU/7pvVq/+RZ7dNV74vaJakPgUEBQR3E1ZpAl4CgdknqQ2BQQFAHcbUm0CUgqF2S+hAYFBDUQVytCXQJCGqX'
    'pD4EBgW8ow7intz6tHfCqlWaP72jVuur80zX+6JOC+tPoEFAUBsQtSAwLSCo08L6E2gQENQGRC0ITAsI6rSw/gQaBAS1AVELAtMC'
    'gjotrD+BBoFr3lHTO1iDwY9apHnSO151k9Q/9Un7pj7V+tQnzVNdT/OkPtV5qv1TfXXfNH913Re1KqaewIKAoC6g25JAVUBQq2Lq'
    'CSwICOoCui0JVAUEtSqmnsCCgKAuoNuSQFVAUKti6gksCBz3jprerxZsvt0yzVl9Z0t90uapPu1bra/um+rTPKk+rac+6VxdfdK+'
    'qf/0ui/qtLD+BBoEBLUBUQsC0wKCOi2sP4EGAUFtQNSCwLSAoE4L60+gQUBQGxC1IDAtIKjTwvoTaBD4OO29qOFMWhB4TsAX9bkr'
    'daAXBQT1xVt1pucEBPW5K3WgFwUE9cVbdabnBAT1uSt1oBcFBPXFW3Wm5wQE9bkrdaAXBQT1xVt1pucEBPW5K3WgFwUE9cVbdabn'
    'BAT1uSt1oBcFBPXFW3Wm5wQE9bkrdaAXBQT1xVt1pucEBPW5K3WgFwUE9cVbdabnBAT1uSt1oBcFBPXFW3Wm5wQE9bkrdaAXBQT1'
    'xVt1pucEBPW5K3WgFwUE9cVbdabnBAT1uSt1oBcFBPXFW3Wm5wQE9bkrdaAXBQT1xVt1pucEBPW5K3WgFwUE9cVbdabnBAT1uSt1'
    'oBcFBPXFW3Wm5wQE9bkrdaAXBQT1xVt1pucEBPW5K3WgFwUE9cVbdabnBAT1uSt1oBcFBPXFW3Wm5wQE9bkrdaAXBQT1xVt1pucE'
    'BPW5K3WgFwX+DSEXSH9xvtmvAAAAAElFTkSuQmCC'
 )
CONTROLLED_PAYLOAD='CONTROLLED QR / 测试数据 / 20261027'

def controlled_frame(copies=1):
    qr=Image.open(BytesIO(base64.b64decode(CONTROLLED_QR_BASE64))).convert('RGB')
    frame=Image.new('RGB',(1280,720),'white')
    if copies==1:frame.paste(qr,(450,210))
    elif copies==2:
        frame.paste(qr,(80,210));frame.paste(qr,(850,210))
    output=BytesIO();frame.save(output,format='PNG');return output.getvalue()

class QrPayloadTests(unittest.TestCase):
    def test_exact_scope_and_fixed_wifi_payload(self):
        self.assertTrue(matches_uri(URI))
        for value in [URI.rstrip('/'),URI+'?changed=1',URI+'#canvas',URI.replace('https:','http:')]:self.assertFalse(matches_uri(value))
        self.assertEqual(wifi_payload('示例网络','12345678'),'WIFI:T:WPA;S:示例网络;P:12345678;;')

    def test_reserved_characters_are_escaped_in_fields(self):
        self.assertEqual(wifi_payload('实验;室','pass:word'),'WIFI:T:WPA;S:实验\\;室;P:pass\\:word;;')

    def test_invalid_wifi_inputs_and_settings_reject(self):
        for args in [('', '12345678'),('长'*11,'12345678'),('示例网络','123'),('示例\n网络','12345678'),
                     ('示例网络','12345678','nopass'),('示例网络','12345678','WPA','false')]:
            with self.subTest(args=args),self.assertRaises(ValueError):wifi_payload(*args)

@unittest.skipUnless(sys.platform=='darwin','Offline installed Apple Vision decoder is macOS specific')
class QrPixelOracleTests(unittest.TestCase):
    def test_exact_payload_from_original_frame_and_image_hash(self):
        png=controlled_frame();result=verify_qr_png(png,CONTROLLED_PAYLOAD,[450,210,762,522])
        self.assertTrue(result['passed']);self.assertEqual(result['image_sha256'],sha256(png).hexdigest())
        self.assertEqual(result['evidence_source'],'original_saved_png_pixels')
        self.assertFalse(result['expected_text_supplied_to_decoder'])
        self.assertEqual(len(result['decoded']),1)

    def test_wrong_payload_rejects_despite_valid_qr_image(self):
        with self.assertRaisesRegex(ValueError,'payload differs'):
            verify_qr_png(controlled_frame(),'WRONG PAYLOAD',[450,210,762,522])

    def test_blank_and_ambiguous_multiple_codes_reject(self):
        for copies in (0,2):
            with self.subTest(copies=copies),self.assertRaisesRegex(ValueError,'exactly one'):
                verify_qr_png(controlled_frame(copies),CONTROLLED_PAYLOAD,[0,0,1280,720])

    def test_valid_code_outside_observed_canvas_rejects(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            verify_qr_png(controlled_frame(),CONTROLLED_PAYLOAD,[0,0,400,400])

    def test_clipped_canvas_wrong_viewport_and_invalid_png_reject(self):
        for box in ([450,210,1300,800],[0,0,float('nan'),500],[-1,0,1280,720]):
            with self.subTest(box=box),self.assertRaises(ValueError):
                verify_qr_png(controlled_frame(),CONTROLLED_PAYLOAD,box)
        with self.assertRaisesRegex(ValueError,'viewport changed'):
            verify_qr_png(base64.b64decode(CONTROLLED_QR_BASE64),CONTROLLED_PAYLOAD,[0,0,312,312])
        with self.assertRaisesRegex(ValueError,'original PNG'):
            verify_qr_png(b'not png',CONTROLLED_PAYLOAD,[0,0,312,312])



# Core layout/native labels calibrated from qr-functional-dev-r01, served only
# by a local intercepted route. The QR pixels are independently Core Image
# generated with the fixed WiFi payload; these are never real production data.
WIFI_FIXTURE_BASE64='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'
QR_HTML=r'''<!doctype html><meta charset="utf-8"><title>在线二维码生成器 | 菜鸟工具</title>
<style>body{margin:0;font:14px Arial;background:white}nav{height:64px;background:#eee;padding-left:24px;line-height:64px}h1{position:absolute;left:40px;top:94px;font-size:22px}#rnqr-typeTabs{position:absolute;left:80px;top:216px;width:620px;display:flex;flex-wrap:wrap;gap:8px}button{font:14px Arial;height:38px;border:0;padding:8px 13px}.rnqr-active{background:#f3f7f5}#rnqr-typeTabs .rnqr-active{background:#506b5d;color:white}.rnqr-form{display:none}.rnqr-form.rnqr-active{display:block}.rnqr-field{position:absolute;top:330px;left:80px;width:302px;display:block}.rnqr-field>span{display:block;margin-bottom:8px}input,textarea,select{font:14px Arial;box-sizing:border-box;border:1px solid #aaa;padding:10px}input,select{height:44px;width:302px}.pass{left:395px}.enc{top:415px}#rnqr-text-content{width:616px;height:134px}.rnqr-switch-field{position:absolute;top:415px;left:395px}.rnqr-switch{display:block;position:relative;width:44px;height:25px;margin-top:8px;background:#ddd;border-radius:20px}.rnqr-switch input{position:absolute;inset:0;width:44px;height:25px;opacity:0}.rnqr-switch i{position:absolute;top:3px;left:3px;width:19px;height:19px;background:white;border-radius:50%}.rnqr-style-panel{position:absolute;top:538px;left:80px;background:#eee;width:616px;padding:16px;box-sizing:border-box}#rnqr-qrCanvas{position:absolute;left:817px;top:255px;width:320px;height:320px}#rnqr-qrEmpty{position:absolute;left:779px;top:241px;width:396px;height:348px;background:white;display:flex;align-items:center;justify-content:center}#rnqr-qrEmpty[hidden]{display:none}#rnqr-stats{position:absolute;left:756px;top:628px;width:442px;display:flex;justify-content:space-between}#rnqr-stats>div{width:90px;text-align:center;border:1px solid #ddd;padding:9px 0}#rnqr-stats span,#rnqr-stats b{display:block;margin-bottom:8px}#rnqr-historyCount{display:none}.note{position:absolute;top:695px;left:756px}</style>
<nav>WEB在线工具　在线画图　SVG在线工具　AI数据分析　菜鸟教程　AI导航　更多频道</nav><h1>在线二维码生成器</h1>
<div id="rn-qr-tool" data-initialized="1"><div id="rnqr-typeTabs"><button data-type="text" class="rnqr-active" type="button">文本 / 网址</button><button data-type="wifi" type="button">WiFi</button><button data-type="vcard" type="button">名片</button><button data-type="email" type="button">邮件</button><button data-type="sms" type="button">短信</button><button data-type="tel" type="button">电话</button><button data-type="geo" type="button">定位</button><button data-type="event" type="button">日程</button></div>
<div class="rnqr-form rnqr-active" data-form="text"><label class="rnqr-field"><span>内容</span><textarea id="rnqr-text-content" placeholder="输入任意文本，或以 https:// 开头的网址"></textarea></label></div>
<div class="rnqr-form" data-form="wifi"><label class="rnqr-field"><span>网络名称 SSID</span><input id="rnqr-wifi-ssid" type="text" placeholder="MyWiFi"></label><label class="rnqr-field pass"><span>密码</span><input id="rnqr-wifi-pass" type="text" placeholder="无密码网络请选择“无密码”"></label><label class="rnqr-field enc"><span>加密方式</span><select id="rnqr-wifi-enc"><option value="WPA">WPA / WPA2</option><option value="WEP">WEP</option><option value="nopass">无密码</option></select></label><div class="rnqr-switch-field"><span>隐藏网络</span><label class="rnqr-switch"><input type="checkbox" id="rnqr-wifi-hidden"><i></i></label></div></div>
<details class="rnqr-style-panel"><summary>外观设置</summary></details><canvas id="rnqr-qrCanvas" width="320" height="320"></canvas><div id="rnqr-qrEmpty">请填写内容以生成二维码</div><div id="rnqr-stats"><div><span>版本</span><b id="rnqr-statVersion">—</b></div><div><span>矩阵</span><b id="rnqr-statModules">—</b></div><div><span>容错</span><b id="rnqr-statEc">—</b></div><div><span>字符</span><b id="rnqr-statChars">—</b></div></div><b id="rnqr-historyCount">0</b><p class="note">添加 Logo 或修改颜色后，请扫码确认识别效果。</p></div>
<script>const DRAW_QR=true;const picture=new Image();picture.src='data:image/png;base64,__IMAGE__';document.querySelectorAll('#rnqr-typeTabs button').forEach(b=>b.onclick=()=>{document.querySelector('#rnqr-typeTabs .rnqr-active').classList.remove('rnqr-active');b.classList.add('rnqr-active');document.querySelector('.rnqr-form.rnqr-active').classList.remove('rnqr-active');document.querySelector('.rnqr-form[data-form=wifi]').classList.add('rnqr-active')});function render(){if(document.querySelector('#rnqr-wifi-ssid').value&&document.querySelector('#rnqr-wifi-pass').value){document.querySelector('#rnqr-qrEmpty').hidden=true;let c=document.querySelector('canvas').getContext('2d');c.fillStyle='white';c.fillRect(0,0,320,320);if(DRAW_QR)c.drawImage(picture,0,0,320,320);document.querySelector('#rnqr-statChars').textContent='30'}}document.querySelectorAll('.rnqr-form[data-form=wifi] input').forEach(e=>e.oninput=render);</script>'''.replace('__IMAGE__',WIFI_FIXTURE_BASE64)

class QrCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.driver=await async_playwright().start();self.browser=await self.driver.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':1280,'height':720},service_workers='block')
        self.html=QR_HTML
        async def local(route):
            if route.request.is_navigation_request():await route.fulfill(status=200,content_type='text/html; charset=utf-8',body=self.html)
            else:await route.abort()
        await self.context.route('**/*',local)
    async def asyncTearDown(self):await self.browser.close();await self.driver.stop()
    async def task(self):
        from webcollect.qr_strategy import QR_INVENTORY_JS,qr_spec,compile_qr
        from webcollect.task_contract import PLAN_SCHEMA
        page=await self.context.new_page();await page.goto(URI);before=await page.content();inv=await page.evaluate(QR_INVENTORY_JS)
        self.assertEqual(before,await page.content());self.assertEqual(inv['widget_rejections'],[])
        p={'page_uri':URI,'title':'在线二维码生成器 | 菜鸟工具',**inv};cap={'capability_id':'CONTROLLED-qr','version':'test-1','status':'ready','site_uri':URI,'site_category':'工具','capabilities':[p]}
        task=compile_qr(cap,qr_spec(cap,p,p['widgets'][0],'test-1'));task.update(_plan_schema_version=PLAN_SCHEMA,initial_settle_ms=0)
        self.assertEqual(len(task['operations']),5);await page.close();return task
    async def test_complete_five_actions_binds_decoded_original_saved_png(self):
        from pathlib import Path
        import json,tempfile
        from webcollect.collect import collect_one
        task=await self.task()
        with tempfile.TemporaryDirectory() as root:
            sample=Path(root)/'sample';evidence=Path(root)/'evidence'
            annotation=await collect_one(self.context,task,sample,evidence,{'sample_id':'CONTROLLED-qr'})
            self.assertEqual(len(annotation['steps']),6)
            contract=json.loads((evidence/'task_contract.json').read_text());self.assertEqual(contract['machine_status'],'PASS');self.assertEqual(contract['semantic_status'],'REVIEW_REQUIRED')
            final=json.loads((evidence/'step_006.json').read_text());row=next(a for a in final['final_assertions'] if 'qr_png_payload' in a['expected'])
            image=(sample/annotation['final_state_image']).read_bytes()
            self.assertEqual(row['pixel_oracle']['image_sha256'],sha256(image).hexdigest())
            self.assertEqual(row['actual'],'WIFI:T:WPA;S:示例网络;P:12345678;;')
            self.assertEqual(final['final_assertions_binding']['screenshot_sha256'],sha256(image).hexdigest())
    async def test_blank_canvas_cannot_pass_from_dom_statistics_and_preserves_exact_failure_png(self):
        from pathlib import Path
        import json,tempfile
        from webcollect.collect import collect_one
        task=await self.task();self.html=QR_HTML.replace('const DRAW_QR=true','const DRAW_QR=false')
        with tempfile.TemporaryDirectory() as root:
            sample=Path(root)/'sample';evidence=Path(root)/'evidence'
            with self.assertRaisesRegex(ValueError,'exactly one'):
                await collect_one(self.context,task,sample,evidence,{'sample_id':'CONTROLLED-qr-failure'})
            self.assertFalse((sample/'annotation.json').exists())
            rejected=json.loads((evidence/'qr_assertion_failure.json').read_text())
            self.assertEqual(rejected['screenshot_sha256'],sha256((evidence/'qr_assertion_failure.png').read_bytes()).hexdigest())
            self.assertEqual(json.loads((evidence/'task_contract.json').read_text())['machine_status'],'FAIL')

if __name__=='__main__':unittest.main()
