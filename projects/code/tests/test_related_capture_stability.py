"""Bounded image dynamics: local original pixels, never collected customer data."""
import base64
from copy import deepcopy
from io import BytesIO
import json
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from playwright.async_api import async_playwright, Error as BrowserError
from webcollect import browser
from webcollect.evidence import audit_capture
from webcollect.task_admission import _frame,reference


def png(color='white',pixel=None):
    bitmap=Image.new('RGB',(40,30),color)
    if pixel:bitmap.putpixel(pixel,(255,0,0))
    stream=BytesIO();bitmap.save(stream,format='PNG');return stream.getvalue()


def state():
    return {'screen_resolution':[40,30],'visible_text':'操作目标与结果',
            'target':{'bbox':[0,15,9,25],'hit_valid':True,'text':'操作'},'values':[{'value':'7'}],
            'capture_readiness':{'schema_version':'webcollect-capture-readiness-1','document_ready':'complete',
                                 'fonts_ready':True,'images_ready':True},
            'capture_images':[{'element_id':'decorative','bbox':[10,0,30,10],
                               'src':'first.png','current_src':'first.png','complete':True,
                               'exclusion_basis':image_basis(),
                               'natural_width':20,'natural_height':10,'eligible':True,'exclusion_reasons':[]}]}


def image_basis(box=(10,0,30,10),viewport=(40,30)):
    return {'schema_version':'webcollect-decorative-image-basis-1',
            'attributes':{'alt':'','aria-hidden':'true','role':'presentation','title':None,'aria-label':None,'aria-labelledby':None},
            'pointer_events':'none','ancestor_exclusions':[],'unknown_paint_overlaps':[],'unbounded_paint_sources':[],
            'protected_overlap':False,'text_or_control_overlap':False,
            'clip_bbox':[0,0,*viewport],'protected_regions':[],
            'hit_samples':[{'ancestor':True,'hit_tag':'body','point':[x,y]}
                           for x in (box[0]+.5,(box[0]+box[2])/2,box[2]-.5)
                           for y in (box[1]+.5,(box[1]+box[3])/2,box[3]-.5)]}


class RelatedProofTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.create_connection','urllib.request.urlopen',
                       'webcollect.model_gateway.ModelGateway.call',
                       'webcollect.runtime.RuntimeStore.claim_next','webcollect.collect_runtime.collect_m4'):
            guard=patch(target,side_effect=AssertionError('offline fixture forbids '+target))
            guard.start();self.addCleanup(guard.stop)

    def test_only_bounded_decorative_pixels_and_source_may_change(self):
        first=state();last=deepcopy(first);last['capture_images'][0]['src']='next.png'
        proof=browser.stability_pair(first,last,png(),png(pixel=(15,5)))
        self.assertTrue(proof['accepted']);self.assertFalse(proof['full_dom_stable'])
        self.assertTrue(proof['related_dom_stable']);self.assertEqual(proof['pixel_change']['changed_pixels'],1)
        self.assertEqual(proof['pixel_change']['outside_allowed_pixels'],0)
        self.assertEqual(first['capture_images'][0]['src'],'first.png')

    def test_unknown_or_outside_pixels_are_rejected_even_with_stable_dom(self):
        for last,image in ((state(),png(pixel=(5,20))),
                           ({**state(),'capture_images':[]},png(pixel=(15,5)))):
            with self.subTest(image=image[:8]):
                self.assertFalse(browser.stability_pair(state(),last,png(),image)['accepted'])
        no_exclusion=state();no_exclusion['capture_images'][0].update(eligible=False,exclusion_reasons=['task_or_result_related'])
        proof=browser.stability_pair(no_exclusion,no_exclusion,png(),png(pixel=(15,5)))
        self.assertFalse(proof['accepted']);self.assertTrue(proof['full_dom_stable'])

    def test_loading_target_label_value_hit_and_geometry_changes_are_rejected(self):
        variants=[]
        for field,value in (('document_ready','loading'),('fonts_ready',False),('images_ready',False)):
            last=state();last['capture_readiness'][field]=value;variants.append(last)
        for field,value in (('text','其他标签'),('hit_valid',False),('bbox',[1,15,10,25])):
            last=state();last['target'][field]=value;variants.append(last)
        last=state();last['values'][0]['value']='8';variants.append(last)
        last=state();last['visible_text']='结果已改变';variants.append(last)
        last=state();last['capture_images'][0]['bbox']=[11,0,31,10];variants.append(last)
        for last in variants:
            with self.subTest(last=last):self.assertFalse(browser.stability_pair(state(),last,png(),png())['accepted'])

    def test_dom_ready_with_loaded_viewport_does_not_wait_for_background_document_load(self):
        original=state();original['capture_readiness']['document_ready']='interactive'
        proof=browser.stability_pair(original,deepcopy(original),png(),png())
        self.assertTrue(proof['accepted']);self.assertTrue(proof['loading_complete'])
        for field in ('fonts_ready','images_ready'):
            incomplete=deepcopy(original);incomplete['capture_readiness'][field]=False
            self.assertFalse(browser.stability_pair(incomplete,incomplete,png(),png())['accepted'])
        changed=deepcopy(original);changed['values'][0]['value']='8'
        self.assertFalse(browser.stability_pair(original,changed,png(),png())['accepted'])

    def test_frozen_v1_remains_strict_and_v2_cannot_be_downgraded(self):
        old={'screen_resolution':[40,30],'visible_text':'旧证据'}
        receipt={'snapshot_source':'browser_dom','coordinate_space':'screenshot_css_pixels',
                 'screenshot_sha256':browser.hashlib.sha256(png()).hexdigest(),
                 'attempts':[{'dom_stable':True,'before_fingerprint':browser.fingerprint(old),'after_fingerprint':browser.fingerprint(old)}]}
        self.assertTrue(browser.validate_capture_receipt(old,receipt,png()))
        with self.assertRaisesRegex(ValueError,'版本'):browser.validate_capture_receipt(state(),receipt,png())
        receipt['attempts'][0]['dom_stable']=False
        with self.assertRaises(ValueError):browser.validate_capture_receipt(old,receipt,png())

    def test_internally_contradictory_exclusion_facts_do_not_create_a_mask(self):
        variants=[]
        first=state();first['capture_images'][0]['exclusion_basis']['clip_bbox']=[12,0,30,10];variants.append(first)
        first=state();first['capture_images'][0]['exclusion_basis']['hit_samples'][0]['point']=[0,0];variants.append(first)
        first=state();first['target']['bbox']=[15,2,20,8];variants.append(first)
        first=state();first['capture_images'][0]['exclusion_basis']['protected_regions']=[{'bbox':[15,2,20,8],'contains_image':False,'inside_image':False}];variants.append(first)
        first=state();first['assertion_targets']=[{'bbox':[15,2,20,8]}];variants.append(first)
        for first in variants:
            with self.subTest(state=first):self.assertFalse(browser.stability_pair(first,first,png(),png(pixel=(15,5)))['accepted'])


class NativeRelatedCapture(unittest.IsolatedAsyncioTestCase):
    async def test_peripheral_playing_video_keeps_full_frame_and_protects_target(self):
        await self.page.set_content('<style>body{margin:0}video{position:absolute;left:300px;top:70px;width:40px;height:30px}</style>'
            '<main><button id="go">核对结果</button><p>计算结果42</p></main><aside><video autoplay muted></video></aside>')
        await self.page.evaluate('''async () => {
            const canvas=document.createElement('canvas');canvas.width=40;canvas.height=30;
            const ctx=canvas.getContext('2d');ctx.fillStyle='red';ctx.fillRect(0,0,40,30);
            const v=document.querySelector('video');v.srcObject=canvas.captureStream(30);await v.play();
            window.fixtureCanvas=canvas;
        }''')
        first=await browser.observe(self.page,'#go');a=await self.page.screenshot()
        await self.page.evaluate("() => {const c=fixtureCanvas.getContext('2d');c.fillStyle='blue';c.fillRect(0,0,40,30)}")
        await self.page.wait_for_timeout(100)
        last=await browser.observe(self.page,'#go');b=await self.page.screenshot()
        self.assertNotEqual(a,b)
        self.assertTrue(first['capture_media'][0]['eligible'])
        self.assertTrue(browser.stability_pair(first,last,a,b)['accepted'])
        await self.page.locator('video').evaluate("v=>{v.style.left='0px';v.style.top='0px'}")
        blocked=await browser.observe(self.page,'#go')
        self.assertFalse(blocked['capture_media'][0]['eligible'])

    async def asyncSetUp(self):
        for target in ('webcollect.model_gateway.ModelGateway.call',
                       'webcollect.runtime.RuntimeStore.claim_next','webcollect.collect_runtime.collect_m4'):
            guard=patch(target,side_effect=AssertionError('local fixture forbids '+target))
            guard.start();self.addCleanup(guard.stop)
        self.runtime=await async_playwright().start()
        self.chrome=await self.runtime.chromium.launch(channel='chrome',headless=True)
        self.context=await self.chrome.new_context(viewport={'width':400,'height':300},service_workers='block')
        await self.context.route('**/*',lambda route:route.abort())
        self.page=await self.context.new_page()
        self.red=self.data('red');self.blue=self.data('blue')

    async def asyncTearDown(self):
        await self.context.close();await self.chrome.close();await self.runtime.stop()

    def data(self,color):
        bitmap=Image.new('RGB',(40,30),color);stream=BytesIO();bitmap.save(stream,format='PNG')
        return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()

    async def prepare(self,attrs='alt="" aria-hidden="true" role="presentation"',style='pointer-events:none'):
        await self.page.set_content('<!doctype html><meta charset="utf-8"><style>body{margin:0}button{position:absolute;left:10px;top:140px}img{position:absolute;left:300px;top:70px;width:40px;height:30px;'+style+'}</style>'
                                    '<button id="go">核对结果</button><p id="result">计算结果42</p>'
                                    '<img id="decoration" '+attrs+' src="'+self.red+'">')
        await self.page.locator('img').evaluate('(image)=>image.decode()')

    async def changing_capture(self,**options):
        real=browser.viewport_png;calls=0
        async def actual_pixels(page):
            nonlocal calls
            result=await real(page);calls+=1
            if calls==1:
                await page.locator('img').evaluate('(image,source)=>{image.src=source;return image.decode()}',self.blue)
            return result
        with patch('webcollect.browser.viewport_png',side_effect=actual_pixels):
            return await browser.capture(self.page,'#go',retries=1,**options)

    async def test_rotated_explicit_decoration_keeps_pixels_and_rejects_related_target(self):
        await self.prepare()
        await self.page.locator('img').evaluate("n=>n.style.transform='rotate(12deg)'")
        frame=await browser.capture(self.page,'#go',retries=1)
        self.assertEqual(len(frame['state']['unrelated_transform_proofs']),1)
        image=frame['state']['capture_images'][0]
        self.assertFalse(image['eligible'])
        self.assertFalse(image['geometry_proof']['actions_supported'])
        self.assertTrue(browser.validate_capture_receipt(frame['state'],frame['capture'],frame['png']))
        with self.assertRaisesRegex(BrowserError,'UNSUPPORTED_GEOMETRY'):
            await browser.capture(self.page,'#decoration',retries=1)
        await self.page.locator('img').evaluate("n=>{n.style.left='15px';n.style.top='140px'}")
        with self.assertRaisesRegex(BrowserError,'UNSUPPORTED_GEOMETRY'):
            await browser.capture(self.page,'#go',retries=1)

    async def test_native_same_tab_navigation_branches_and_external_identity(self):
        from urllib.parse import urlsplit
        from webcollect.react_session import ReactSession,build_url_task
        from webcollect.postprocess import process
        from test_react_native import native,finish
        from test_react_session import decide,act_step
        home='https://navigation.invalid/'
        branch='https://branch.invalid/details'
        documents={home:'<h1>读者服务目录</h1><a href="/details">查看借阅规则</a><br><a href="'+branch+'">查看另一服务说明</a>',
            home+'details':'<h1>借阅规则详情</h1><p>读者可以查看借阅时间和归还规则，核对实际页面内容。</p>',
            branch:'<h1>服务说明详情</h1><p>读者可以查看开放时间和服务地点，核对实际页面内容。</p>'}
        blocked=[]
        async def route(request):
            url=request.request.url
            if url not in documents:
                blocked.append(url);await request.abort();return
            await request.fulfill(content_type='text/html; charset=utf-8',body='<!doctype html><meta charset="utf-8">'+documents[url])
        await self.context.route('**/*',route)
        targets=[home+'details',None,branch,None]
        index=0
        def choose(prompt):
            nonlocal index
            if index==4:
                build=finish(summary='已查看两个服务详情并返回目录；未执行借阅业务')
            else:
                url=targets[index]
                if url:
                    page=next(p for p in prompt['boundary']['observed_pages'] if p['url']==url)
                    build=decide(goal='查看两个服务详情并返回目录' if index==0 else None,tool='act',
                        arguments=lambda p:{'observation_id':p['observation']['observation_id'],
                            'step':act_step('open_url',page_id=page['page_id'],goal='查看服务详情',expected='显示所选详情')})
                else:
                    build=decide(tool='act',arguments=lambda p:{'observation_id':p['observation']['observation_id'],
                        'step':act_step('back',goal='返回服务目录',expected='显示原目录')})
            response=native(build,'local-'+str(index))(prompt);index+=1;return response
        async def async_choose(prompt):return choose(prompt)
        with tempfile.TemporaryDirectory() as temp, patch('webcollect.collect.verify_public_url',side_effect=lambda url,*args,**kwargs:urlsplit(url).hostname):
            root=Path(temp);sid='S000111_sample_000001';evidence=root/'evidence'/sid
            task=build_url_task(url=home,task_version='offline-navigation',app_name='受控导航目录')
            session=ReactSession(task,evidence/'raw',async_choose,self.page,steps_directory=evidence)
            result=await session.run()
            self.assertEqual(result['effective_steps'],4,result)
            self.assertEqual(self.page.url,home)
            terminal=json.loads(Path(result['terminal']['path']).read_text())
            self.assertEqual(set(terminal['page_hosts'].values()),{'navigation.invalid','branch.invalid'})
            ids={'sample_id':sid,'site_id':'S000111','batch_id':'B20261102_001','attempt_id':'offline-navigation'}
            manifest={'batch_id':ids['batch_id'],'sample_kind':'real','program_version':'offline','rule_version':'1.0.0',
                'sites':[{'site_id':ids['site_id'],'uri':home,'site_category':task['site_category']}],'samples':[sid]}
            derived=process(evidence,root/'delivery'/sid,ids,manifest)
            self.assertEqual(derived['status'],'derived_saved',{**derived,'record':json.loads(Path(derived['record_ref']['path']).read_text()) if derived.get('record_ref') else None})
            annotation=json.loads((root/'delivery'/sid/'annotation.json').read_text())
            self.assertEqual({step['tool_call']['context'] for step in annotation['steps']},
                {'Web / navigation.invalid','Web / branch.invalid'})
            self.assertEqual(blocked,[])

    async def test_click_feedback_in_source_tab_and_article_in_popup_have_separate_evidence(self):
        from webcollect.react_protocol import atomic_effect

        article_url = 'https://article.invalid/borrowing'
        visits = []

        async def serve_article(route):
            visits.append(route.request.url)
            await route.fulfill(content_type='text/html; charset=utf-8', body='<h1>图书借还操作说明</h1>')

        await self.context.route(article_url, serve_article)
        await self.page.set_content(
            '<!doctype html><meta charset="utf-8"><style>'
            'a,p{display:block;width:180px;padding:8px;color:black}p,a:focus{background:lightblue}'
            'a:focus+p{background:white}</style>'
            f'<a id="entry" href="{article_url}" target="_blank">图书自助借还流程</a><p>电子读者证领取流程</p>'
        )
        before = await browser.capture(self.page, '#entry', retries=1)
        target = before['state']['target']
        x, y = target['coordinate']
        arguments = {'x': x, 'y': y}
        async with self.page.expect_popup() as popup_event:
            await browser.execute(self.page, 'click', arguments, {})
        popup = await popup_event.value
        await popup.wait_for_load_state('domcontentloaded')
        source_after = await browser.capture(self.page, '#entry', retries=1)
        landing = await browser.capture(popup, retries=1)

        for frame in (before, source_after, landing):
            self.assertTrue(browser.validate_capture_receipt(frame['state'], frame['capture'], frame['png']))
        self.assertNotEqual(before['png'], source_after['png'])
        self.assertEqual(before['state']['url'], source_after['state']['url'])
        effect = atomic_effect(before['state'], source_after['state'], 'click', arguments, target['element_id'])
        self.assertTrue(effect['verified'])
        self.assertIn('target.focused', effect['fields'])
        self.assertNotIn('图书借还操作说明', source_after['state']['visible_text'])
        self.assertEqual(landing['state']['url'], article_url)
        self.assertIn('图书借还操作说明', landing['state']['visible_text'])
        self.assertEqual(visits, [article_url])

    async def test_absent_body_reobserves_without_navigation_or_action(self):
        await self.prepare()
        await self.page.evaluate("()=>{const body=document.body;body.remove();setTimeout(()=>document.documentElement.append(body),40)}")
        with patch.object(self.page,'goto',side_effect=AssertionError('no navigation replay')), \
             patch('webcollect.browser.execute',side_effect=AssertionError('no action replay')):
            state=await browser.observe(self.page,'#go')
        self.assertIn('核对结果',state['visible_text'])

    async def test_default_capture_dispatch_and_recomputed_receipt_accept_bounded_image(self):
        await self.prepare();result=await self.changing_capture(assertions=[{'selector':'#result','contains':'42'}])
        receipt=result['capture'];attempt=receipt['attempts'][-1]
        self.assertEqual(receipt['schema_version'],browser.CAPTURE_VERSION)
        self.assertFalse(attempt['dom_stable']);self.assertTrue(attempt['stability']['accepted'])
        self.assertGreater(attempt['stability']['pixel_change']['changed_pixels'],0)
        self.assertTrue(browser.validate_capture_receipt(result['state'],receipt,result['png']))
        self.validate_actual_file_consumers(result)
        json.dumps(receipt,allow_nan=False)
        checked=await browser.verify_execution_state(self.page,result['state'],'#go',assertions=[{'selector':'#result','contains':'42'}])
        self.assertTrue(checked['matched']);self.assertFalse(checked['full_state_matched'])
        self.assertEqual(checked['state_fingerprint'],browser.fingerprint(result['state']))
        self.assertNotEqual(checked['state_fingerprint'],checked['live_state_fingerprint'])
        self.assertEqual(await self.page.locator('img').get_attribute('style'),None)
        broken=deepcopy(receipt);broken['attempts'][-1]['dom_stable']=True
        with self.assertRaises(ValueError):browser.validate_capture_receipt(result['state'],broken,result['png'])
        broken=deepcopy(receipt);broken['attempts'][-1]['comparison_png_base64']=base64.b64encode(result['png']).decode()
        with self.assertRaises(ValueError):browser.validate_capture_receipt(result['state'],broken,result['png'])
        await self.page.locator('#result').evaluate('(node)=>node.textContent="结果43"')
        with self.assertRaises(ValueError) as caught:
            await browser.verify_execution_state(self.page,result['state'],'#go',assertions=[{'selector':'#result','contains':'42'}])
        rejected=caught.exception.capture
        self.assertEqual(rejected['schema_version'],'webcollect-execution-state-rejection-1')
        self.assertFalse(rejected['action_executed']);self.assertFalse(rejected['accepted_as_formal_frame'])
        self.assertIn('visible_text',rejected['mismatch_fields'])
        self.assertEqual(base64.b64decode(rejected['original_png_base64']),result['png'])
        recomputed=browser.stability_pair(rejected['snapshot_before'],rejected['snapshot_live'],
            base64.b64decode(rejected['original_png_base64']),base64.b64decode(rejected['comparison_png_base64']),
            allow_border=rejected['allow_border'])
        self.assertEqual(recomputed,rejected['stability']);self.assertFalse(recomputed['accepted'])

    def validate_actual_file_consumers(self,result):
        # Exercise the real validation branches with local bytes only. This is
        # not an admission review, a collected sample or a QC approval.
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);sample=root/'samples'/'local-fixture';sample.mkdir(parents=True)
            proof=root/'evidence'/'local-fixture';proof.mkdir(parents=True)
            image=sample/'frame.png';image.write_bytes(result['png'])
            def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
            state_path=proof/'state.json';capture_path=proof/'capture.json'
            write(state_path,result['state']);write(capture_path,result['capture'])
            frame={'image':reference(image),'state':reference(state_path),'capture':reference(capture_path)}
            checked,_=_frame(frame,'real');self.assertEqual(checked,result['state'])
            write(sample/'tree.json',{'elements':result['state']['elements'],'screen_resolution':result['state']['screen_resolution']})
            action={'tool_name':'system','arguments':{'action':'complete'}}
            write(sample/'annotation.json',{'steps':[{'step_id':1,'image_path':'frame.png','ui_tree_path':'tree.json',
                  'tool_call':action,'action':{'action_type':'complete'}}]})
            timestamp=result['capture']['attempts'][-1]['ended_ns']/1e9+.01
            raw={'state':result['state'],'capture':result['capture'],'executed_action':action,
                 'started_at':datetime.fromtimestamp(timestamp,timezone.utc).isoformat(),
                 'ended_at':datetime.fromtimestamp(timestamp+.01,timezone.utc).isoformat(),
                 'final_assertions':[{'passed':True}]}
            write(proof/'step_001.json',raw);write(proof/'ground_truth.json',[])
            self.assertTrue(audit_capture(root,'local-fixture')['capture_evidence_pass'])
            broken=deepcopy(raw);broken['capture']['attempts'][-1]['stability']['pixel_change']['outside_allowed_pixels']=0
            broken['capture']['attempts'][-1]['stability']['related_dom_stable']=False
            write(proof/'step_001.json',broken)
            self.assertFalse(audit_capture(root,'local-fixture')['capture_evidence_pass'])
            write(capture_path,broken['capture']);frame['capture']=reference(capture_path)
            with self.assertRaises(ValueError):_frame(frame,'real')

    async def test_result_images_stay_protected_but_interactive_image_motion_is_allowed(self):
        for attrs,style,protected in (('alt="有意义的结果"','pointer-events:none',[]),
                                      ('alt="" aria-hidden="true" role="presentation"','cursor:pointer',[]),
                                      ('alt="" aria-hidden="true" role="presentation"','pointer-events:none',['#decoration'])):
            with self.subTest(attrs=attrs,protected=protected):
                await self.prepare(attrs,style)
                if style=='cursor:pointer':
                    frame=await self.changing_capture(protected_selectors=protected)
                    self.assertTrue(browser.validate_capture_receipt(frame['state'],frame['capture'],frame['png']))
                else:
                    with self.assertRaisesRegex(ValueError,'拒绝保存'):
                        await self.changing_capture(protected_selectors=protected)

    async def test_actual_gif_pixels_may_advance_without_faking_dom_change(self):
        await self.prepare()
        stream=BytesIO();frames=[Image.new('RGB',(40,30),color) for color in ('red','blue','green','yellow')]
        frames[0].save(stream,format='GIF',save_all=True,append_images=frames[1:],duration=1000,loop=0)
        source='data:image/gif;base64,'+base64.b64encode(stream.getvalue()).decode()
        await self.page.locator('img').evaluate('(image,source)=>{image.src=source;return image.decode()}',source)
        original_html=await self.page.content();real=browser.viewport_png;shots=0
        async def naturally_advancing_pixels(page):
            nonlocal shots
            result=await real(page);shots+=1
            if shots==1:await self.page.wait_for_timeout(1100)
            return result
        with patch('webcollect.browser.viewport_png',side_effect=naturally_advancing_pixels):
            result=await browser.capture(self.page,'#go',retries=1)
        attempt=result['capture']['attempts'][-1]
        self.assertTrue(attempt['dom_stable'])
        self.assertGreater(attempt['stability']['pixel_change']['changed_pixels'],0)
        self.assertTrue(attempt['stability']['accepted'])
        self.assertEqual(await self.page.content(),original_html)
        self.assertTrue(browser.validate_capture_receipt(result['state'],result['capture'],result['png']))

    async def test_loading_and_target_occlusion_never_grant_capture(self):
        await self.prepare()
        # Keep the image request genuinely pending throughout capture. A completed
        # failure on proven unrelated decoration follows a separate V6 rule.
        pending=[]
        async def hold(route):
            pending.append(route)
        await self.page.route('https://must-never-load.invalid/image.png', hold)
        await self.page.locator('img').evaluate('(image)=>{image.src="https://must-never-load.invalid/image.png"}')
        frame=await browser.capture(self.page,'#go',retries=1)
        self.assertFalse(frame['state']['capture_readiness']['images_ready'])
        self.assertTrue(browser.validate_capture_receipt(frame['state'],frame['capture'],frame['png']))
        self.assertEqual(len(pending),1)
        await pending[0].abort()
        await self.prepare();captured=await browser.capture(self.page,'#go',retries=1)
        await self.page.evaluate('''()=>{const cover=document.createElement('div');cover.style='position:absolute;left:0;top:130px;width:200px;height:100px;background:black';document.body.append(cover)}''')
        with self.assertRaises(ValueError):await browser.verify_execution_state(self.page,captured['state'],'#go')

    async def test_overlay_pixels_inside_allowed_image_do_not_require_cause_attribution(self):
        for tag in ('canvas','div'):
            with self.subTest(tag=tag):
                await self.prepare()
                await self.page.evaluate('''tag=>{const n=document.createElement(tag);n.id='unknown';n.style='position:absolute;left:304px;top:74px;width:3px;height:3px;pointer-events:none;background:green';document.body.append(n)}''',tag)
                observed=await browser.observe(self.page,'#go')
                image=observed['capture_images'][0]
                self.assertFalse(image['eligible'])
                self.assertIn('unknown_overlapping_paint',image['exclusion_reasons'])
                self.assertTrue(image['exclusion_basis']['unknown_paint_overlaps'])
                real=browser.viewport_png;shots=0
                async def changing_overlay_pixels(page):
                    nonlocal shots
                    result=await real(page);shots+=1
                    if shots==1:await page.locator('#unknown').evaluate('(node)=>node.style.background="purple"')
                    return result
                with patch('webcollect.browser.viewport_png',side_effect=changing_overlay_pixels):
                    captured=await browser.capture(self.page,'#go',retries=1)
                attempt=captured['capture']['attempts'][-1]
                self.assertTrue(attempt['dom_stable'])
                self.assertEqual(attempt['stability']['pixel_change']['outside_allowed_pixels'],0)

    async def test_changes_within_allowed_image_region_do_not_require_image_source_causality(self):
        for kind in ('shadow','pseudo'):
            with self.subTest(kind=kind):
                await self.prepare()
                await self.page.evaluate('''kind=>{const n=document.createElement('div');n.id='spill';
                  n.style='position:absolute;left:280px;top:75px;width:5px;height:5px;pointer-events:none;background:green';
                  if(kind==='shadow')n.style.boxShadow='30px 0 0 5px green';
                  else {const s=document.createElement('style');s.textContent='#spill::after{content:"";position:absolute;left:25px;top:0;width:5px;height:5px;background:green}';document.head.append(s)}
                  document.body.append(n)}''',kind)
                observed=await browser.observe(self.page,'#go');image=observed['capture_images'][0]
                self.assertFalse(image['eligible']);self.assertIn('unbounded_external_paint',image['exclusion_reasons'])
                self.assertTrue(image['exclusion_basis']['unbounded_paint_sources'])
                self.assertFalse(image['exclusion_basis']['unknown_paint_overlaps'])
                real=browser.viewport_png;shots=0
                async def changing_spill_pixels(page):
                    nonlocal shots
                    result=await real(page);shots+=1
                    if shots==1:
                        if kind=='shadow':await page.locator('#spill').evaluate('(node)=>node.style.boxShadow="30px 0 0 5px purple"')
                        else:await page.add_style_tag(content='#spill::after{background:purple}')
                    return result
                with patch('webcollect.browser.viewport_png',side_effect=changing_spill_pixels):
                    frame=await browser.capture(self.page,'#go',retries=1)
                self.assertTrue(browser.validate_capture_receipt(frame['state'],frame['capture'],frame['png']))



    async def test_native_empty_pseudo_graphic_envelope_and_semantic_negatives(self):
        await self.page.set_content("""<style>body{font:18px Arial}#graphic{position:relative;margin:80px;width:32px;height:32px;padding:0;border:0}#graphic a{position:relative;top:-24px}#graphic::before{content:'';position:absolute;left:-18px;top:-18px;margin-left:16px;margin-top:32px;width:36px;height:36px;border-radius:50%;background:blue;animation:pulse .24s ease-out infinite}@keyframes pulse{from{transform:scale(0);opacity:0}to{transform:scale(1);opacity:.5}}#target{position:absolute;left:350px;top:80px}</style><div id=graphic><a href='#next'>存</a></div><button id=target>操作目标</button><p id=next>正文事实保持原样</p>""")
        try:first=await browser.capture(self.page,retries=1)
        except browser.EvidenceStale as error:
            from webcollect.dynamic_regions import projection
            attempt=error.capture['attempts'][0];left=projection(attempt['snapshot_before']);right=projection(attempt['snapshot_after'])
            self.fail(json.dumps({'proof':{k:attempt['stability'][k] for k in ('accepted','related_dom_stable','pixel_change','target_protection')},'different':{k:[left.get(k),right.get(k)] for k in left if left.get(k)!=right.get(k)}},ensure_ascii=False))
        proofs=[r for r in first['state']['dynamic_region_contract']['regions'] if r.get('native_image_paint',{}).get('kind')=='empty-native-pseudo-graphic-1']
        self.assertEqual(len(proofs),1);self.assertTrue(proofs[0]['eligible']);self.assertTrue(proofs[0]['semantic_owner_retained'])
        await self.page.wait_for_timeout(75);second=await browser.capture(self.page,retries=1)
        self.assertTrue(browser.stability_pair(first['state'],second['state'],first['png'],second['png'])['accepted'])
        for css in ["#graphic::before{animation-timing-function:cubic-bezier(.5,2,.5,2)}","#graphic::before{content:'业务文字'}","#graphic::before{filter:blur(4px)}"]:
            style=await self.page.add_style_tag(content=css);state=await browser.observe(self.page)
            self.assertFalse(any(r.get('native_image_paint',{}).get('kind')=='empty-native-pseudo-graphic-1' for r in state['dynamic_region_contract']['regions']))
            await style.evaluate('(n)=>n.remove()')
        await self.page.add_style_tag(content='#target{left:80px;top:108px}')
        state=await browser.observe(self.page,'#target')
        self.assertTrue(any('overlaps_action_target' in r['reasons'] for r in state['dynamic_region_contract']['regions']))

    async def test_rejected_mixed_notice_still_allows_independent_ad_child_and_css_leaf(self):
        await self.page.set_content("""<style>.notice{margin:40px;width:400px}.advertisement{width:60px;height:40px;overflow:hidden;animation:colors .15s linear infinite}@keyframes colors{from{background:red}to{background:blue}}.graphic{width:30px;height:30px;background-image:linear-gradient(red,blue)}.hero{background-image:linear-gradient(white,gray)}</style><main><div class=notice><span class=calculation-output>106.25</span><div class=advertisement>广告</div></div><div class=graphic></div><p class=hero>真实正文仍须保留</p></main>""")
        first=await browser.capture(self.page,retries=1);regions=first['state']['dynamic_region_contract']['regions']
        self.assertTrue(any(r['category']=='announcement' and not r['eligible'] for r in regions))
        self.assertTrue(any(r['category']=='advertisement' and r['eligible'] for r in regions))
        self.assertTrue(any(r['category']=='dynamic_image' and r['tag']=='div' and r['eligible'] for r in regions))
        self.assertFalse(any(r['attributes'].get('class')=='hero' for r in regions))
        await self.page.wait_for_timeout(60);second=await browser.capture(self.page,retries=1)
        self.assertTrue(browser.stability_pair(first['state'],second['state'],first['png'],second['png'])['accepted'])
        await self.page.locator('.calculation-output').evaluate("n=>n.textContent='999.99'")
        third=await browser.capture(self.page,retries=1)
        self.assertFalse(browser.stability_pair(second['state'],third['state'],second['png'],third['png'])['accepted'])


class CompactRepaintNoiseTests(unittest.TestCase):
    """v3 compact-repaint tolerance; fixtures mirror the real 108ai divider case
    (15 px, RGB ±2, 361x5 strip on input/result-box top edges), rebuilt
    synthetically because offline verification may not read production dirs."""

    def _real_like_state(self):
        base = state(); base['capture_images'] = []; base['screen_resolution'] = [1280, 720]
        base['visible_text'] = '单位换算器 2.54'
        base['elements'] = [
            {'element_id': 'e_i', 'element_type': 'input', 'text': '数值', 'bbox': [500, 45, 831, 89],
             'visible': True, 'enabled': True, 'clickable': True, 'inputable': True},
            {'element_id': 'e_t', 'element_type': 'text', 'text': '2.54', 'bbox': [857, 45, 1187, 98],
             'visible': True, 'enabled': True, 'clickable': False, 'inputable': False}]
        base['values'] = [{'element_id': 'e_i', 'value': '2.54', 'focused': False, 'readonly': False,
                           'display_value': '2.54', 'value_visible': True}]
        return base

    def _real_like_pair(self):
        from PIL import ImageDraw
        first = Image.new('RGB', (1280, 720), (249, 251, 252))
        last = first.copy()
        # Sparse antialias jitter: 15 of the strip's pixels shift by 2 per channel,
        # mirroring the real saved evidence without reading production dirs.
        for x in range(500, 515):
            last.putpixel((x, 46), (247, 249, 251))
        streams = []
        for bitmap in (first, last):
            stream = BytesIO(); bitmap.save(stream, format='PNG'); streams.append(stream.getvalue())
        return streams

    def test_divider_strip_tolerated_on_retry_only(self):
        state = self._real_like_state()
        original, comparison = self._real_like_pair()
        proof = browser.stability_pair(state, state, original, comparison, allow_border=True)
        self.assertTrue(proof['accepted'])
        self.assertTrue(proof['full_dom_stable'])
        self.assertGreaterEqual(proof['pixel_change']['changed_pixels'], 1)
        self.assertEqual(proof['pixel_change']['outside_allowed_pixels'], 0)
        noise = proof.get('paint_noise_proof', [])
        # The default rule version stamps its own noise-rule label; v4 receipts
        # carry compact-repaint-noise-v2 (tag/window-aware paint guard).
        self.assertEqual({entry['rule'] for entry in noise}, {'compact-repaint-noise-v2'})
        for kwargs, label in ((dict(allow_border=False), 'v3-first-attempt'),
                              (dict(allow_border=True, rule_version=browser.STABILITY_V2), 'v2-receipt')):
            with self.subTest(rule=label):
                proof = browser.stability_pair(state, state, original, comparison, **kwargs)
                self.assertFalse(proof['accepted'])
                self.assertNotIn('paint_noise_proof', proof)

    def _guarded_state(self, text_box=((10, 5), (30, 15))):
        base = state(); base['capture_images'] = []; base['elements'] = [
            {'element_id': 'e_1', 'text': '结果文本', 'bbox': [text_box[0][0], text_box[0][1], text_box[1][0], text_box[1][1]],
             'visible': True, 'clickable': False, 'inputable': False}]
        return base

    def _strip_pair(self, delta=2):
        first = Image.new('RGB', (40, 30), (240, 240, 240))
        last = first.copy()
        for x in range(14, 26):
            last.putpixel((x, 2), (240 - delta, 240 - delta, 240 - delta))
        streams = []
        for bitmap in (first, last):
            stream = BytesIO(); bitmap.save(stream, format='PNG'); streams.append(stream.getvalue())
        return streams

    def test_noise_inside_paint_surface_still_rejected(self):
        original, comparison = self._strip_pair(delta=2)
        paint_state = self._guarded_state()
        paint_state['elements'] = [
            {'element_id': 'e_9', 'element_type': 'canvas', 'text': '', 'bbox': [0, 0, 40, 10],
             'visible': True, 'clickable': False, 'inputable': False}]
        proof = browser.stability_pair(paint_state, paint_state, original, comparison, allow_border=True)
        self.assertFalse(proof['accepted'])
        # Away from paint surfaces, low amplitude passes even next to DOM text.
        proof = browser.stability_pair(self._guarded_state(), self._guarded_state(), original, comparison, allow_border=True)
        self.assertTrue(proof['accepted'])

    def test_v4_guards_tag_keyed_and_window_paint_surfaces(self):
        """Snapshot reality: canvas/video/iframe tags default to element_type
        'text' and opaque frames become 'window'; v4 must guard them anyway."""
        original, comparison = self._strip_pair(delta=2)
        for label, extra in (('canvas-tag', {'native_role': 'canvas'}),
                             ('video-tag', {'native_role': 'video'}),
                             ('iframe-tag', {'native_role': 'iframe'}),
                             ('opaque-window', {'element_type': 'window', 'native_role': 'iframe'})):
            with self.subTest(case=label):
                paint_state = self._guarded_state()
                paint_state['elements'] = [
                    {'element_id': 'e_9', 'element_type': 'text', 'text': '', 'bbox': [0, 0, 40, 10],
                     'visible': True, 'clickable': False, 'inputable': False, **extra}]
                # v4 (current default) rejects repaint inside the paint surface.
                proof = browser.stability_pair(paint_state, paint_state, original, comparison, allow_border=True)
                self.assertFalse(proof['accepted'])
                # A v3 receipt keeps its exact original element_type-only guard,
                # which never covered tag-keyed paint surfaces: the same strip
                # stayed tolerable there. Recorded v3 PASS receipts reproduce.
                v3 = browser.stability_pair(paint_state, paint_state, original, comparison,
                                            allow_border=True, rule_version=browser.STABILITY_V3)
                self.assertTrue(v3['accepted'])
                self.assertEqual({entry['rule'] for entry in v3.get('paint_noise_proof', [])},
                                 {'compact-repaint-noise-v1'})

    def test_amplitude_component_and_count_limits_hold(self):
        base = self._guarded_state()
        for label, delta, limit in (('amplitude', 40, None), ('count', 2, 5)):
            with self.subTest(case=label):
                first = Image.new('RGB', (40, 30), (240, 240, 240))
                last = first.copy()
                columns = range(0, 40, 8) if label == 'count' else range(14, 26)
                for x in columns:
                    last.putpixel((x, 2), (240 - delta,) * 3)
                streams = []
                for bitmap in (first, last):
                    stream = BytesIO(); bitmap.save(stream, format='PNG'); streams.append(stream.getvalue())
                proof = browser.stability_pair(base, base, streams[0], streams[1], allow_border=True)
                self.assertFalse(proof['accepted'])


if __name__=='__main__':unittest.main()
