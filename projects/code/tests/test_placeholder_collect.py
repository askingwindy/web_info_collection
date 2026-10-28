"""Controlled full collection with source-linked original PNG replay, not live data.

PNG fixtures are unmodified extracts from placeholder-functional-r01. Requested
PNG SHA256: 3e3a37dea40384ae84826567eff55adba457093ad2e6cc75d3044faa4a690955.
All browser routes are locally fulfilled/aborted; real offline OCR remains active.
"""
import base64
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from webcollect.placeholder_strategy import URI,PLACEHOLDER_INVENTORY_JS,placeholder_spec,compile_placeholder,IMAGE_SELECTOR
from webcollect.placeholder_pixel import verify_placeholder_png

FIXTURES=Path(__file__).parent/'fixtures/placeholder'
def data_uri(raw):return 'data:image/png;base64,'+base64.b64encode(raw).decode()

def fixture_html(blank=False):
    initial=data_uri((FIXTURES/'initial.png').read_bytes());requested=(FIXTURES/'requested.png').read_bytes()
    if blank:
        stream=BytesIO();Image.new('RGB',(400,200),(238,238,238)).save(stream,format='PNG');requested=stream.getvalue()
    fields=''
    for n,(sid,label,value,kind) in enumerate([('width','宽度','300','number'),('height','高度','300','number'),
            ('customText','自定义文本','300X300','text'),('fontSize','字体大小','24','number')]):
        fields+=f'<div class="field" style="left:{53+n%2*290}px;top:{245+n//2*83.5}px"><label for="{sid}">{label}</label><input id="{sid}" type="{kind}" value="{value}"></div>'
    return f'''<!doctype html><meta charset="utf-8"><title>在线占位图生成工具</title><style>
body{{margin:0;font:14px Arial;color:#343a40;background:white}}h1{{position:absolute;left:40px;top:95px;font-size:22px}}nav{{padding:20px;background:#eee}}
.field{{position:fixed}}label{{display:block;margin-bottom:10px}}input,select{{box-sizing:border-box;width:280px;height:35px;padding:6px 12px;font:14px Arial;border:1px solid #bbb}}
.settings{{position:absolute;left:36px;top:177px;width:604px;height:410px;border:1px solid #ddd}}.preview{{position:absolute;left:640px;top:177px;width:604px;height:410px;border:1px solid #ddd}}
#placeholderResult{{position:fixed;left:642px;top:271.1875px;width:600px;display:flex;justify-content:center}}img{{display:block}}button{{font:14px Arial;padding:8px 12px}}
#generateBtn{{position:fixed;left:53px;top:490px}}#downloadImage{{position:fixed;left:175px;top:490px}}</style>
<nav>在线工具　在线画图　菜鸟教程　更多频道</nav><h1>在线占位图生成工具</h1>
<div class="form-row"><div class="col-md-6 border settings"><b>设置</b>{fields}
<div style="position:fixed;left:53px;top:412px"><label for="fontFamily">选择字体</label><select id="fontFamily"><option>Arial</option></select></div>
<div style="position:fixed;left:343px;top:412px"><label for="theme">选择主题</label><select id="theme"><option>gray</option></select></div>
<div id="customerThemeSet" style="display:none"><input id="bgColor" type="color"><input id="textColor" type="color"></div>
<button id="generateBtn">生成占位图</button><button id="downloadImage">下载图片</button></div>
<div class="col-md-6 border preview"><b>预览</b><div id="placeholderResult"><img class="holderjs-placeholder" src="{initial}" data-src="holder.js/300x300?size=24&amp;theme=gray&amp;text=300X300&amp;font=Arial" alt="300X300 [300x300]"></div></div></div>
<script>document.querySelector('#generateBtn').onclick=()=>{{const image=document.querySelector('img');image.src={json.dumps(data_uri(requested))};image.alt='预览图 [400x200]';image.dataset.src='holder.js/400x200?size=24&theme=gray&text=预览图&font=Arial'}};</script>'''


class PlaceholderCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.driver=await async_playwright().start();self.browser=await self.driver.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':1280,'height':720},service_workers='block');self.html=fixture_html()
        async def local(route):
            if route.request.is_navigation_request():await route.fulfill(status=200,content_type='text/html; charset=utf-8',body=self.html)
            else:await route.abort()
        await self.context.route('**/*',local)
    async def asyncTearDown(self):await self.browser.close();await self.driver.stop()
    async def task(self):
        from webcollect.task_contract import PLAN_SCHEMA
        page=await self.context.new_page();await page.goto(URI);inventory=await page.evaluate(PLACEHOLDER_INVENTORY_JS)
        self.assertEqual(inventory['widget_rejections'],[])
        observed={'page_uri':URI,'title':'在线占位图生成工具',**inventory}
        cap={'site_uri':URI,'capability_id':'CONTROLLED-placeholder','version':'test-1','site_category':'工具','status':'ready','capabilities':[observed]}
        task=compile_placeholder(cap,placeholder_spec(cap,observed,observed['widgets'][0],'test-1'))
        task.update(_plan_schema_version=PLAN_SCHEMA,initial_settle_ms=0);await page.close();return task

    async def test_ten_actions_complete_with_exact_saved_png_pixel_and_ocr_binding(self):
        from webcollect.collect import collect_one
        from webcollect.task_contract import terminal_evidence
        task=await self.task()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sample=root/'sample';evidence=root/'evidence'
            annotation=await collect_one(self.context,task,sample,evidence,{'sample_id':'CONTROLLED-placeholder'})
            self.assertEqual(len(annotation['steps']),11)
            final=json.loads((evidence/'step_011.json').read_text());row=final['final_assertions'][0]
            png=(sample/annotation['final_state_image']).read_bytes()
            self.assertEqual(row['actual'],'预览图');self.assertEqual(row['pixel_oracle']['image_sha256'],sha256(png).hexdigest())
            self.assertGreaterEqual(row['pixel_oracle']['confidence'],.9);self.assertTrue(row['pixel_oracle']['screenshot_crop_equals_generated_png'])
            self.assertEqual(json.loads((evidence/'task_contract.json').read_text())['machine_status'],'PASS')
            with self.assertRaisesRegex(ValueError,'saved PNG hash'):terminal_evidence(task,[],[row],{'screenshot_sha256':'0'*64})

    async def test_blank_image_with_correct_alt_inputs_and_dimensions_preserves_failed_pixels(self):
        from webcollect.collect import collect_one
        task=await self.task();self.html=fixture_html(blank=True)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sample=root/'sample';evidence=root/'evidence'
            with self.assertRaisesRegex(ValueError,'Blank PNG'):
                await collect_one(self.context,task,sample,evidence,{'sample_id':'CONTROLLED-placeholder-failure'})
            self.assertFalse((sample/'annotation.json').exists())
            record=json.loads((evidence/'placeholder_assertion_failure.json').read_text())
            self.assertEqual(record['screenshot_sha256'],sha256((evidence/'placeholder_assertion_failure.png').read_bytes()).hexdigest())


class PlaceholderPixelNegatives(unittest.TestCase):
    def test_fixed_threshold_wrong_text_crop_and_geometry_reject(self):
        image=(FIXTURES/'requested.png').read_bytes();source=data_uri(image)
        frame=Image.new('RGB',(1280,720),'white');frame.paste(Image.open(BytesIO(image)),(742,271));stream=BytesIO();frame.save(stream,format='PNG');png=stream.getvalue()
        positive={'width':1280,'height':720,'revision':3,'observations':[{'text':'预览图','confidence':1,'bbox':[895,353,988,384]}]}
        with patch('webcollect.placeholder_pixel.recognize_original_placeholder',return_value=positive):
            self.assertTrue(verify_placeholder_png(png,'预览图',[742,271.1875,1142,471.1875],source)['passed'])
            with self.assertRaises(ValueError):verify_placeholder_png(png,'预览图',[742,270,1142,470],source)
            with self.assertRaises(ValueError):verify_placeholder_png(png,'预览图',[742,271,1141,471],source)
        for text,confidence in [('预览田',1),('预览图',.8999)]:
            bad=deepcopy(positive);bad['observations'][0].update(text=text,confidence=confidence)
            with patch('webcollect.placeholder_pixel.recognize_original_placeholder',return_value=bad),self.assertRaises(ValueError):
                verify_placeholder_png(png,'预览图',[742,271,1142,471],source)

if __name__=='__main__':unittest.main()
