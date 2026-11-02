"""Bounded-image preflight cases; temporary evidence, no site/model/production."""
from hashlib import sha256
from io import BytesIO
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image
from playwright.async_api import async_playwright

from webcollect.media_preflight import probe_media, summarize_preflight
from webcollect.preflight import inspect_page
from test_related_capture_stability import image_basis


def assessment():
    return {'body': {'found': True, 'visible': True, 'selector': '#body', 'bbox': [0, 0, 300, 200]},
            'obstruction': {'present': False}, 'decision': {'action': 'ready'}}


def image():
    return {'kind': 'image_candidate', 'selector': '#decoration', 'bbox': [150, 100, 175, 125],
            'context': {}, 'task_relations': []}


def probe(at, item=None):
    return {'page_url': 'https://offline.example.org/tool', 'document_identity': {
            'url_without_fragment': 'https://offline.example.org/tool', 'performance_time_origin': 1000},
            'observed_at_performance_ms': at, 'media': [image() if item is None else item],
            'native_animations': [], 'task_targets': [], 'limitations': {}}


def proof(changed=625):
    return {'schema_version': 'webcollect-related-stability-1', 'accepted': True,
            'full_dom_stable': False, 'related_dom_stable': True, 'loading_complete': True,
            'pixel_change': {'changed_pixels': changed, 'outside_allowed_pixels': 0,
                             'bbox': [150, 100, 175, 125] if changed else None},
            'allowed_image_regions': [{'element_id': 'offline-image-1', 'bbox': [150, 100, 175, 125]}]}


def change():
    return {'from_probe': 0, 'to_probe': 1, 'changed_pixels': 625, 'changed_fraction': 625 / 60000,
            'bbox': [150, 100, 175, 125], 'related_stability': proof(),
            'diagnostic_pair_stability': [proof(0), proof(0)]}


class RelatedImageSummaryTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.create_connection', 'urllib.request.urlopen', 'urllib.request.build_opener',
                       'webcollect.model_gateway.ModelGateway.call',
                       'webcollect.collect.collect_plan', 'webcollect.collect_runtime.collect_m4',
                       'webcollect.runtime.RuntimeStore.enqueue_plan', 'webcollect.runtime.RuntimeStore.claim_next',
                       'playwright.async_api.async_playwright'):
            guard = patch(target, side_effect=AssertionError('offline preflight forbids ' + target))
            guard.start(); self.addCleanup(guard.stop)

    def summary(self, changes=None, probes=None, assessments=None):
        return summarize_preflight(probes or [probe(100), probe(500)],
                                   assessments or [assessment()], [change()] if changes is None else changes)

    def test_proven_image_change_does_not_make_entire_body_dynamic(self):
        result = self.summary()
        self.assertEqual(result['routing'], 'NORMAL_M1')
        clue = result['pixel_change_clues'][0]
        self.assertTrue(clue['critical_geometry_overlap'])
        self.assertTrue(clue['bounded_irrelevant_image_change'])
        self.assertEqual(clue['related_stability'], proof())
        self.assertEqual(result['quality_evaluation'], 'NOT_PERFORMED')

    def test_legacy_unknown_or_incomplete_proof_cannot_lower_route(self):
        variants = []
        for field, value in [('schema_version', 'future-unknown'), ('accepted', False),
                             ('related_dom_stable', False), ('loading_complete', False),
                             ('allowed_image_regions', [])]:
            row = change(); row['related_stability'][field] = value; variants.append(row)
        row = change(); row.pop('related_stability'); variants.append(row)
        row = change(); row['related_stability']['pixel_change']['outside_allowed_pixels'] = 1; variants.append(row)
        row = change(); row['diagnostic_pair_stability'][1]['related_dom_stable'] = False; variants.append(row)
        row = change(); row.pop('diagnostic_pair_stability'); variants.append(row)
        for row in variants:
            with self.subTest(row=row):
                self.assertEqual(self.summary([row])['routing'], 'DYNAMIC_CONTENT_TRACK')

    def test_target_reference_or_opaque_result_never_uses_body_exception(self):
        for role in ('target', 'reference', 'opaque-result'):
            probes = [probe(100), probe(500)]; assessments = [assessment()]
            if role == 'target':
                for item in probes:
                    item['task_targets'] = [{'selector': '#button', 'style_viewport_visible': True,
                                              'bbox': [155, 105, 180, 130], 'visible_hit': True}]
            elif role == 'reference':
                assessments[0]['reference_content'] = {'evidence': [{'selector': '#quote', 'bbox': [155, 105, 180, 130]}]}
            else:
                for item in probes:
                    item['media'][0].update(gif_url_candidate=True, task_relations=[{
                        'target_selector': '#result', 'inside_target': True}])
            with self.subTest(role=role):
                self.assertIn(self.summary(probes=probes, assessments=assessments)['routing'],
                              ('DYNAMIC_CONTENT_TRACK', 'REVIEW_REQUIRED'))

    def test_iframe_and_truncated_inventory_still_require_review(self):
        for risk in ('iframe', 'truncation', 'covered-target'):
            probes = [probe(100), probe(500)]
            for item in probes:
                if risk == 'iframe':
                    item['media'].append({'kind': 'iframe', 'selector': '#unknown-frame', 'bbox': [200, 0, 250, 50],
                                          'context': {}, 'task_relations': []})
                elif risk == 'truncation':
                    item['limitations']['task_targets_truncated'] = True
                else:
                    item['media'][0]['task_relations'] = [{'target_selector': '#button', 'dom_hit_covers_target_point': True}]
            with self.subTest(risk=risk):
                self.assertEqual(self.summary(probes=probes)['routing'], 'REVIEW_REQUIRED')


class RelatedImageTargetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for target in ('socket.create_connection','urllib.request.urlopen','urllib.request.build_opener',
                       'webcollect.model_gateway.ModelGateway.call','playwright.async_api.async_playwright',
                       'webcollect.collect.collect_plan','webcollect.collect_runtime.collect_m4',
                       'webcollect.runtime.RuntimeStore.enqueue_plan','webcollect.runtime.RuntimeStore.claim_next'):
            guard=patch(target,side_effect=AssertionError('offline target probe forbids '+target))
            guard.start();self.addCleanup(guard.stop)

    async def test_probe_protects_final_and_intermediate_assertion_selectors(self):
        class Page:
            async def evaluate(self, script, options):
                self.options = options
                return probe(100)
        page = Page()
        task = {'operations': [{'action_type': 'click', 'selector': '#button',
                                'postconditions': [{'selector': '#intermediate', 'contains': '完成'}]}],
                'final_assertions': [{'selector': '#result', 'contains': '结果'}, {'visible_text': '文字'}]}
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            await probe_media(page, task)
        selectors = {row['selector'] for row in page.options['targets']}
        self.assertEqual(selectors, {'#button', '#intermediate', '#result'})


class RelatedImageInspectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        for target in ('socket.create_connection','urllib.request.urlopen','urllib.request.build_opener',
                       'webcollect.model_gateway.ModelGateway.call','playwright.async_api.async_playwright',
                       'webcollect.collect.collect_plan','webcollect.collect_runtime.collect_m4',
                       'webcollect.runtime.RuntimeStore.enqueue_plan','webcollect.runtime.RuntimeStore.claim_next'):
            guard=patch(target,side_effect=AssertionError('offline inspection forbids '+target))
            guard.start();self.addCleanup(guard.stop)

    def state(self,source):
        return {'screen_resolution':[300,200],'url':'https://offline.example.org/tool','visible_text':'操作和结果保持不变',
                'elements':[{'element_id':'button','text':'确认','bbox':[10,10,80,40]}],
                'capture_readiness':{'schema_version':'webcollect-capture-readiness-1','document_ready':'complete',
                                     'fonts_ready':True,'images_ready':True},
                'capture_images':[{'element_id':'decoration','bbox':[150,100,175,125],'src':source,'current_src':source,
                                   'complete':True,'natural_width':25,'natural_height':25,
                                   'eligible':True,'exclusion_reasons':[],
                                   'exclusion_basis':image_basis(box=(150,100,175,125),viewport=(300,200))}]}

    def png(self,color,extra=False):
        image=Image.new('RGB',(300,200),'white')
        image.paste(color,(150,100,175,125))
        if extra:image.putpixel((1,1),(0,0,0))
        output=BytesIO();image.save(output,format='PNG');return output.getvalue()

    async def inspect(self,case):
        first,last=self.state('first.png'),self.state('second.png')
        if case=='target-change':last['elements'][0]['text']='改变后的确认'
        if case=='loading':last['capture_readiness']['images_ready']=False
        images=[self.png('red'),self.png('red'),self.png('blue',case=='outside-pixels')]
        media=[probe(100),probe(200),probe(500),probe(600)]
        task={'task_id':'OFFLINE-preflight-related-image','site_uri':'https://offline.example.org/',
              'initial_url':'https://offline.example.org/tool',
              'operations':[{'action_type':'click','selector':'#button','postconditions':[{'selector':'#intermediate','contains':'完成'}]}],
              'final_assertions':[{'selector':'#result','contains':'结果'}]}
        page=type('OfflinePage',(),{'url':task['initial_url']})()
        with patch('webcollect.preflight.observe',AsyncMock(side_effect=[first,first,last,last])) as observed, \
             patch('webcollect.preflight.viewport_png',AsyncMock(side_effect=[(image,{'method':'offline-fixture'}) for image in images])), \
             patch('webcollect.media_preflight.probe_media',AsyncMock(side_effect=media)), \
             patch('webcollect.preflight.assess_content',AsyncMock(return_value=assessment())), \
             patch('webcollect.preflight.asyncio.sleep',AsyncMock()):
            result=await inspect_page(page,task,self.root/case,samples=2,interval_ms=100)
        for call in observed.await_args_list:
            self.assertEqual(call.kwargs['protected_selectors'],['#button','#intermediate','#result'])
        return result,images

    async def test_real_proof_is_wired_and_original_images_and_states_survive(self):
        result,images=await self.inspect('unrelated')
        self.assertIsNone(result['error'])
        self.assertEqual(result['summary']['routing'],'NORMAL_M1')
        pair=result['pixel_changes'][0]['related_stability']
        self.assertTrue(pair['accepted']);self.assertFalse(pair['full_dom_stable'])
        self.assertTrue(pair['related_dom_stable'])
        self.assertEqual(pair['png_before_sha256'],sha256(images[1]).hexdigest())
        self.assertEqual(pair['png_after_sha256'],sha256(images[2]).hexdigest())
        for index,image in enumerate(images[1:]):
            self.assertEqual((self.root/'unrelated'/f'probe_{index:03d}.png').read_bytes(),image)
        raw=json.loads((self.root/'unrelated/probe_001.json').read_text())
        self.assertEqual(raw['state_before']['capture_images'][0]['src'],'second.png')
        self.assertEqual(raw['state_after']['capture_images'][0]['src'],'second.png')
        self.assertTrue(raw['DOM_consistent_in_diagnostic_pair'])
        self.assertFalse(raw['accepted_as_formal_frame'])

    async def test_loading_target_changes_and_unknown_pixel_scope_require_review(self):
        for case in ('loading','target-change','outside-pixels'):
            with self.subTest(case=case):
                result,_=await self.inspect(case)
                self.assertIsNone(result['error'])
                self.assertEqual(result['summary']['routing'],'REVIEW_REQUIRED')
                self.assertTrue(result['summary']['related_stability_failures'])

    def test_accepted_repaint_outside_image_is_not_attributed_to_that_image(self):
        from webcollect.browser import stability_pair

        snapshot = self.state('same-animated-image')
        first = self.png('red')
        with Image.open(BytesIO(self.png('blue'))) as last:
            last.putpixel((1, 1), (252, 252, 252))
            buf = BytesIO()
            last.save(buf, 'PNG')
        temporal = stability_pair(snapshot, snapshot, first, buf.getvalue())
        self.assertTrue(temporal['accepted'])
        self.assertTrue(temporal['paint_noise_proof'])
        pair = stability_pair(snapshot, snapshot, first, first)
        comparison = {**change(), 'related_stability': temporal, 'diagnostic_pair_stability': [pair, pair]}
        summary = summarize_preflight([probe(100), probe(500)], [assessment()], [comparison])
        self.assertFalse(summary['pixel_change_clues'][0]['bounded_irrelevant_image_change'])


class RelatedImageBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.runtime=await async_playwright().start()
        self.addAsyncCleanup(self.runtime.stop)
        self.browser=await self.runtime.chromium.launch(channel='chrome',headless=True)
        self.addAsyncCleanup(self.browser.close)
        self.context=await self.browser.new_context(viewport={'width':300,'height':200})
        self.requests=[]
        async def abort(route):
            self.requests.append(route.request.url)
            await route.abort()
        await self.context.route('**/*',abort)
        self.page=await self.context.new_page()
        for target in ('webcollect.model_gateway.ModelGateway.call','webcollect.collect.collect_plan',
                       'webcollect.collect_runtime.collect_m4','webcollect.runtime.RuntimeStore.enqueue_plan',
                       'webcollect.runtime.RuntimeStore.claim_next'):
            guard=patch(target,side_effect=AssertionError('browser fixture forbids '+target))
            guard.start();self.addCleanup(guard.stop)

    def image_uri(self,color):
        output=BytesIO();Image.new('RGB',(25,25),color).save(output,format='PNG')
        return 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()

    async def test_delayed_image_is_waited_for_without_editing_page_or_approving_unloaded_pixels(self):
        await self.page.set_content('''<!doctype html><meta charset="utf-8"><h1>工程测试页面</h1>
          <button id="button">核对</button><img id="delayed" width="25" height="25" alt="测试图标">''')
        await self.page.evaluate('(src)=>setTimeout(()=>document.querySelector("#delayed").src=src,500)',self.image_uri('green'))
        task={'task_id':'OFFLINE-delay','site_uri':'https://offline.example.org/',
              'initial_url':'https://offline.example.org/','content_preparation':False,
              'operations':[{'action_type':'click','selector':'#button'}]}
        result=await inspect_page(self.page,task,self.root/'delay',samples=2,interval_ms=100)
        self.assertIsNone(result['error']);self.assertEqual(result['summary']['routing'],'NORMAL_M1')
        wait=json.loads((self.root/'delay/readiness_wait.json').read_text())
        self.assertEqual(wait['status'],'ready')
        self.assertTrue(any(row['images_ready'] is False for row in wait['observations']))
        self.assertTrue(wait['observations'][-1]['images_ready'])
        self.assertEqual(await self.page.locator('#delayed').get_attribute('style'),None)
        self.assertEqual(self.requests,[])

    async def test_default_preflight_uses_real_observer_and_preserves_bounded_image_change(self):
        first,last=self.image_uri('red'),self.image_uri('blue')
        await self.page.set_content('''<!doctype html><meta charset="utf-8"><style>
          body{margin:0;font:16px sans-serif}button{position:absolute;left:10px;top:10px}
          #result{position:absolute;left:10px;top:50px}#decoration{position:absolute;left:200px;top:100px;pointer-events:none}
          </style><button id="button">确认</button><div id="result">结果尚未生成</div>
          <img id="decoration" alt="" aria-hidden="true" role="presentation" width="25" height="25">''')
        await self.page.evaluate('(src)=>{document.querySelector("#decoration").src=src;return document.querySelector("#decoration").decode()}',first)
        task={'task_id':'LOCAL-ONLY-related-image','site_uri':'https://offline.example.org/',
              'initial_url':'https://offline.example.org/tool','instruction':'确认结果保持可见。',
              'operations':[{'action_type':'click','selector':'#button'}],
              'final_assertions':[{'selector':'#result','contains':'生成'}]}
        from webcollect.browser import viewport_png
        captured=[]
        async def fixture_viewport(page):
            # A deterministic local fixture event changes only the decorative
            # source between real DOM observations; production code performs no edit.
            if len(captured)==2:
                await page.evaluate('(src)=>{document.querySelector("#decoration").src=src;return document.querySelector("#decoration").decode()}',last)
            png,method=await viewport_png(page);captured.append(png);return png,method
        with patch('webcollect.preflight.viewport_png',side_effect=fixture_viewport):
            result=await inspect_page(self.page,task,self.root/'browser',samples=2,interval_ms=100)
        self.assertIsNone(result['error'])
        self.assertEqual(result['summary']['routing'],'NORMAL_M1',result['summary'])
        self.assertEqual(self.requests,[])
        related=result['pixel_changes'][0]['related_stability']
        self.assertTrue(related['accepted']);self.assertFalse(related['full_dom_stable'])
        self.assertGreater(related['pixel_change']['changed_pixels'],0)
        self.assertEqual(related['pixel_change']['outside_allowed_pixels'],0)
        raw=json.loads((self.root/'browser/probe_001.json').read_text())
        self.assertFalse(raw['DOM_consistent_in_diagnostic_pair'])
        self.assertEqual(raw['state_before']['capture_images'][0]['src'],first)
        self.assertEqual(raw['state_after']['capture_images'][0]['src'],last)
        self.assertEqual((self.root/'browser/probe_001.png').read_bytes(),captured[-1])
        self.assertEqual(await self.page.locator('#result').inner_text(),'结果尚未生成')


if __name__ == '__main__':
    unittest.main()
