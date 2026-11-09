"""Real local flow-inline clicks; no external site, model or production IO."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


class FractionalLinkGeometryTests(unittest.IsolatedAsyncioTestCase):
    async def test_flow_inline_click_point_and_real_occlusion(self):
        from playwright.async_api import async_playwright
        from webcollect import browser
        from webcollect.collect import capture_before_action
        from webcollect.action_stability import action_scoped_scope, CLICK_POINT_VERSION, pair
        from webcollect.agent_observation import VERSION as OBS_VERSION
        from webcollect.planning import object_sha256

        def operation(state):
            node = state['target']['element_id']
            binding = next(b for b in state['capture_controls'] if b['element_id'] == node)
            return {'action_type':'click','selector':binding['selector'],'index':binding['index'],
                    'evidence':{'observation_protocol':OBS_VERSION,'state_sha256':object_sha256(state),
                                'anchor_element_id':node,'target_label':'半影'}}

        with TemporaryDirectory() as tmp:
            output = Path(os.environ.get('WEBCOLLECT_GEOMETRY_EVIDENCE', tmp))
            output.mkdir(parents=True, exist_ok=True)
            async with async_playwright() as pw:
                chromium = await pw.chromium.launch(channel='chrome', headless=True)
                self.addAsyncCleanup(chromium.close)
                context = await chromium.new_context(viewport={'width':1280,'height':720}, device_scale_factor=1)
                html = '''<!doctype html><html lang="zh"><meta charset="utf-8"><title>流式文字链接</title>
                  <style>body{margin:0;padding:100.25px 0 0 285.140625px;font:14.14px/1.6 sans-serif}
                  figure{margin:0} p{margin-top:30px;width:145px}</style><body>
                  <figure><figcaption>原词条说明<a id="flow" href="#related">半影</a>区的后续说明。</figcaption></figure>
                  <p>说明文字说明文字甲<a id="wrapped" href="#related">半影</a>及后续说明。</p>
                  <script>window.clicks=0;document.querySelectorAll('a').forEach(a=>a.onclick=e=>{e.preventDefault();window.clicks++})</script>
                  </body></html>'''
                async def handle(route):
                    await route.fulfill(status=200,content_type='text/html',body=html)
                await context.route('**/*',handle)
                page = await context.new_page()
                await page.goto('https://local.test/flow-inline',wait_until='load')
                records = {}
                for selector in ('#flow','#wrapped'):
                    clear = await browser.observe(page,selector)
                    node = clear['target']['element_id']
                    geometry = next(g for g in clear['geometry_witnesses'] if g['element_id'] == node)
                    scope = action_scoped_scope(clear,node,'click')
                    self.assertEqual(scope['click_validation'],CLICK_POINT_VERSION)
                    self.assertNotIn('geometry',scope['basis'])  # nine probes are diagnostic
                    self.assertTrue(geometry['dispatch_point']['hit_valid'])
                    self.assertEqual(geometry['dispatch_point']['coordinate'],clear['target']['coordinate'])
                    if selector == '#wrapped':
                        self.assertTrue(any(not p['ancestor'] and p['hit_tag'] in ('p','figcaption')
                                            for p in geometry['samples']),geometry)
                        # Natural wrapping leaves the bounding-box center in
                        # whitespace. The dispatched point is a real fragment.
                        box=geometry['bbox']
                        center=[int((box[0]+box[2]-1)//2),int((box[1]+box[3]-1)//2)]
                        self.assertNotEqual(geometry['dispatch_point']['coordinate'],center)
                        archived=deepcopy(clear)
                        next(g for g in archived['geometry_witnesses'] if g['element_id']==node).pop('dispatch_point')
                        with self.assertRaisesRegex(ValueError,'hit samples'):
                            action_scoped_scope(archived,node,'click')
                    observed=await capture_before_action(page,output,selector,timeout=15,action_scope=scope)
                    self.assertTrue(observed['action_state_preflight']['matched'])
                    # Formal capture/audit and offline pair replay use the
                    # exact same new policy, not a saving-only exception.
                    browser.validate_capture_receipt(observed['state'],observed['capture'],observed['png'])
                    diagnostic=deepcopy(observed['state'])
                    row=next(g for g in diagnostic['geometry_witnesses'] if g['element_id']==node)
                    row['samples'][0].update(ancestor=False,hit_tag='figcaption')
                    self.assertTrue(pair(observed['state'],diagnostic,observed['png'],observed['png'],scope)['accepted'])
                    args,_=browser.prepare_action(observed['state'],operation(observed['state']))
                    self.assertEqual([args['x'],args['y']],geometry['dispatch_point']['coordinate'])
                    await browser.execute(page,'click',args)
                    records[selector]={'state':observed['state'],'scope':scope}
                self.assertEqual(await page.evaluate('window.clicks'),2)

                clear=await browser.observe(page,'#flow')
                node=clear['target']['element_id'];scope=action_scoped_scope(clear,node,'click')
                coordinate=clear['target']['coordinate']
                # A real painted cover on the actual click point still rejects.
                await page.evaluate('''p=>{const c=document.createElement('div');c.id='cover';
                  Object.assign(c.style,{position:'absolute',left:(p[0]-4)+'px',top:(p[1]-4)+'px',
                    width:'8px',height:'8px',background:'red',zIndex:'99'});document.body.append(c)}''',coordinate)
                centered=await browser.observe(page,'#flow')
                with self.assertRaises(ValueError):
                    action_scoped_scope(centered,node,'click')
                self.assertEqual(await page.evaluate('window.clicks'),2)
                await page.locator('#cover').evaluate('(node)=>node.remove()')

                clear=await browser.observe(page,'#flow')
                node=clear['target']['element_id'];scope=action_scoped_scope(clear,node,'click')
                png,_=await browser.viewport_png(page)
                # Cover part of the first character while leaving the actual
                # click point clear. Existing rendered-label checks still stop
                # an operation that names the full original label.
                box=await page.locator('#flow').bounding_box()
                await page.evaluate('''b=>{const c=document.createElement('div');c.id='cover';
                  Object.assign(c.style,{position:'absolute',left:(b.x+1)+'px',top:b.y+'px',
                    width:'6px',height:b.height+'px',background:'red',zIndex:'99'});document.body.append(c)}''',box)
                covered=await browser.observe(page,'#flow')
                self.assertTrue(covered['target']['hit_valid'])
                with self.assertRaisesRegex(ValueError,'READABLE_LABEL|LABEL_UNREADABLE'):
                    browser.prepare_action(covered,operation(covered))
                covered_png,_=await browser.viewport_png(page)
                self.assertFalse(pair(clear,covered,png,covered_png,scope)['accepted'])
                self.assertEqual(await page.evaluate('window.clicks'),2)
                (output/'geometry.json').write_text(json.dumps({'clear':records,'center_covered':centered,
                    'text_covered':covered,'clear_dispatched':2,'center_covered_dispatched':0,
                    'text_covered_dispatched':0},ensure_ascii=False,indent=2))
                (output/'covered.png').write_bytes(covered_png)
                await context.close()


class BackObservedDocumentTests(unittest.IsolatedAsyncioTestCase):
    async def test_interactive_pending_image_can_back_with_strict_identity_and_replay(self):
        import asyncio
        from urllib.parse import urlsplit
        from playwright.async_api import async_playwright
        from webcollect import browser
        from webcollect.collect import capture_before_action
        from webcollect.action_stability import document_scope, BACK_OBSERVED_VERSION, pair
        from webcollect.direct_article import body, url_key
        original_url='https://original.local.test/article'
        related_url='https://related.local.test/article'
        original_html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>月食原词条</title>
          <body><main><h1>月食</h1><p>原词条正文说明地球位于太阳与月球之间，月球进入地球阴影后形成月食，以下内容供返回核验。</p>
          <a href="https://related.local.test/article">月球轨道</a></main></body></html>'''
        related_html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>月球轨道</title>
          <body><main><h1>月球轨道</h1><p>关联词条正文已经显示，图片请求尚未完成也可以真实返回原词条，返回身份仍须由实际页面核对。</p>
          <img src="/pending.png" width="80" height="80"></main></body></html>'''
        with TemporaryDirectory() as tmp:
            root=Path(os.environ.get('WEBCOLLECT_BACK_EVIDENCE',tmp));root.mkdir(parents=True,exist_ok=True)
            async with async_playwright() as pw:
                chromium=await pw.chromium.launch(channel='chrome',headless=True)
                context=await chromium.new_context(viewport={'width':1280,'height':720},device_scale_factor=1)
                pending_seen=asyncio.Event();release=asyncio.Event()
                async def handle(route):
                    url=route.request.url
                    if urlsplit(url).path=='/pending.png':
                        pending_seen.set()
                        await release.wait()
                        try:await route.abort()
                        except Exception:pass  # Navigation already cancelled the held fixture resource.
                    else:
                        await route.fulfill(status=200,content_type='text/html',
                            body=original_html if urlsplit(url).hostname=='original.local.test' else related_html)
                await context.route('**/*',handle)
                try:
                    page=await context.new_page()
                    await page.goto(original_url,wait_until='load')
                    origin=await browser.observe(page)
                    await page.locator('a').click(no_wait_after=True)
                    await page.wait_for_url(related_url,wait_until='domcontentloaded')
                    await asyncio.wait_for(pending_seen.wait(),2)
                    await page.wait_for_function("document.readyState==='interactive'",timeout=2000)
                    source=await browser.observe(page)
                    self.assertEqual(source['capture_readiness']['document_ready'],'interactive')
                    self.assertFalse(source['capture_readiness']['images_ready'])
                    scope=document_scope(source,'back')
                    self.assertEqual(scope['readiness_policy'],BACK_OBSERVED_VERSION)
                    observed=await capture_before_action(page,root,timeout=12,action_scope=scope)
                    self.assertTrue(observed['action_state_preflight']['matched'])
                    browser.validate_capture_receipt(observed['state'],observed['capture'],observed['png'])
                    self.assertTrue(pair(source,source,observed['png'],observed['png'],scope)['accepted'])
                    for field in ('url','document_identity'):
                        wrong=deepcopy(source)
                        wrong[field]='https://wrong.local.test/' if field=='url' else {'performance_time_origin':-1}
                        self.assertFalse(pair(source,wrong,observed['png'],observed['png'],scope)['accepted'],field)
                    legacy=deepcopy(scope);legacy.pop('readiness_policy')
                    self.assertFalse(pair(source,source,observed['png'],observed['png'],legacy)['accepted'])
                    for action in ('scroll','hotkey','open_url'):
                        with self.assertRaisesRegex(ValueError,'loaded document'):
                            document_scope(source,action)
                    await browser.execute(page,'back',{})
                    returned=await browser.observe(page)
                    self.assertEqual(url_key(returned['url']),url_key(origin['url']))
                    self.assertEqual(returned['title'],origin['title'])
                    self.assertTrue({p['quote'] for p in body(origin)} & {p['quote'] for p in body(returned)})
                    (root/'back-evidence.json').write_text(json.dumps({'origin':origin,'source':source,
                        'scope':scope,'capture':observed['capture'],'returned':returned,
                        'back_dispatched':1,'return_verified':True},ensure_ascii=False,indent=2))
                    (root/'back-before.png').write_bytes(observed['png'])
                finally:
                    release.set()
                    await context.close()
                    await chromium.close()
