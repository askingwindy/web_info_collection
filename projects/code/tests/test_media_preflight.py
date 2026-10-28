"""Independent media facts/triage cases. No classifier output supplies truth."""
import asyncio
import json
import unittest

from playwright.async_api import async_playwright
from webcollect.media_preflight import probe_media,summarize_preflight


def assessment(action='ready'):
    return {'body':{'found':True,'visible':True,'selector':'#body','bbox':[20,80,500,280]},
            'obstruction':{'present':action in ['close_overlay','blocked']},'decision':{'action':action}}


def probe(at=100,media=None,native=None):
    return {'page_url':'https://fixture.invalid/article','document_identity':{
        'url_without_fragment':'https://fixture.invalid/article','performance_time_origin':1000},
        'observed_at_performance_ms':at,'media':media or [],'native_animations':native or [],
        'task_targets':[],'limitations':{}}


def video(time=0,paused=True,source='clip.webm'):
    return {'kind':'video','selector':'#video','bbox':[20,100,460,260],
            'current_time':time,'paused':paused,'ended':False,'autoplay':True,'ready_state':4,
            'current_src':source,'source_attribute':source,'source_object_present':False,
            'context':{'article_region_selector':'#article','heading':'水位观察','caption':'正文演示',
                       'explicit_ad_markers':[]},'task_relations':[]}


def animation(hold=False,related=False):
    return {'kind':'CSSAnimation','selector':'#decoration','bbox':[30,100,100,150] if related else [700,20,750,70],
            'play_state':'running','pending':False,'current_time':200,'playback_rate':1,'start_time':0,
            'timing':{'iterations':'Infinity','duration':4000,'direction':'normal','easing':'linear','delay':0},
            'composite':'replace','iteration_composite':'replace','pseudo_element':None,
            'keyframes':[{'computedOffset':0,'transform':'translateX(0px)','composite':'auto'},
                         {'computedOffset':.4,'transform':'translateX(20px)','composite':'auto'},
                         {'computedOffset':1,'transform':'translateX(20px)' if hold else 'translateX(40px)','composite':'auto'}],
            'context':{},'task_relations':[]}


class SummaryTests(unittest.TestCase):
    def check(self,probes,expected,assessments=None,pixels=None):
        result=summarize_preflight(probes,assessments or [assessment()],pixels)
        self.assertEqual(result['routing'],expected)
        self.assertEqual(result['quality_evaluation'],'NOT_PERFORMED')
        self.assertEqual(result['page_actions_performed'],0)
        self.assertTrue(result['observation_limits']['finite_window_never_proves_permanent_static'])
        json.dumps(result,allow_nan=False)
        return result

    def test_clean_page_only_says_no_risk_observed_in_finite_window(self):
        self.check([probe(),probe(600)],'NORMAL_M1')

    def test_unrelated_continuous_native_motion_is_reported_without_rerouting_task(self):
        result=self.check([probe(native=[animation()])],'NORMAL_M1')
        self.assertEqual(result['native_window_advice']['status'],'unsupported')
        self.assertTrue(result['page_capture_risks'])
        self.assertEqual(result['media_evidence'][0]['media_role'],'unknown')

    def test_native_motion_in_task_geometry_needs_dynamic_track(self):
        self.check([probe(native=[animation(related=True)])],'DYNAMIC_CONTENT_TRACK')

    def test_nonvideo_time_progress_is_not_applicable_even_if_native_timeline_advances(self):
        canvas={'kind':'canvas','selector':'#canvas','bbox':[700,200,750,250],'context':{},'task_relations':[]}
        first=probe(media=[canvas],native=[animation()])
        last=probe(600,media=[canvas],native=[animation()]);last['native_animations'][0]['current_time']=700
        result=self.check([first,last],'NORMAL_M1')
        self.assertEqual({row['kind'] for row in result['media_evidence']},{'canvas','native_animation'})
        for row in result['media_evidence']:
            self.assertIsNone(row['observed_time_progress'])
            self.assertEqual(row['time_progress_scope'],'video_current_time_only')
        native=next(row for row in result['media_evidence'] if row['kind']=='native_animation')
        self.assertEqual([row['current_time'] for row in native['observations']],[200,700])

    def test_native_hold_remains_prediction_not_approval(self):
        result=self.check([probe(native=[animation(hold=True,related=True)])],'NORMAL_M1')
        self.assertEqual(result['native_window_advice']['status'],'native_window_predicted')
        self.assertTrue(result['native_window_advice']['prediction_is_not_capture_acceptance'])

    def test_multiple_native_animations_do_not_hide_unsupported_one(self):
        result=self.check([probe(native=[animation(hold=True,related=True),animation(related=True)])],
                          'DYNAMIC_CONTENT_TRACK')
        self.assertEqual(result['native_window_advice']['status'],'unsupported')

    def test_editorial_playback_advances_and_is_preserved(self):
        result=self.check([probe(media=[video(.1,False)]),probe(600,[video(.6,False)])],
                          'DYNAMIC_CONTENT_TRACK')
        row=result['media_evidence'][0]
        self.assertTrue(row['observed_time_progress'])
        self.assertEqual(row['media_role'],'editorial_candidate')
        self.assertTrue(result['observation_limits']['editorial_video_is_preserved'])

    def test_paused_poster_and_autoplay_attribute_do_not_prove_playback_or_ad(self):
        result=self.check([probe(media=[video()]),probe(600,[video()])],'NORMAL_M1')
        row=result['media_evidence'][0]
        self.assertFalse(row['observed_time_progress'])
        self.assertFalse(row['playing_state_observed'])
        self.assertNotEqual(row['media_role'],'promotional_candidate')

    def test_source_replacement_or_time_reversal_is_not_joined_as_progress(self):
        for second in [video(.7,False,'replacement.webm'),video(.01,False)]:
            with self.subTest(second=second):
                result=self.check([probe(media=[video(.5,False)]),probe(600,[second])],'REVIEW_REQUIRED')
                self.assertFalse(result['media_evidence'][0]['observed_time_progress'])

    def test_only_explicit_marker_produces_promotional_candidate(self):
        item=video(.5,False)
        item['context']['explicit_ad_markers']=[{'kind':'rendered_ad_marker','text':'广告','selector':'#label'}]
        result=self.check([probe(media=[item])],'DYNAMIC_CONTENT_TRACK')
        self.assertEqual(result['media_evidence'][0]['media_role'],'promotional_candidate')
        self.assertTrue(result['media_evidence'][0]['role_is_context_candidate_not_ground_truth'])

    def test_actual_target_dom_hit_coverage_requires_review(self):
        item=video(.2,False)
        item['task_relations']=[{'target_selector':'#button','dom_hit_covers_target_point':True}]
        self.check([probe(media=[item])],'REVIEW_REQUIRED')

    def test_cross_origin_frame_is_unknown_not_advertising(self):
        result=self.check([probe(media=[{'kind':'iframe','selector':'#frame','bbox':[20,100,450,260],
                                         'cross_origin':True,'context':{},'task_relations':[]}])],'REVIEW_REQUIRED')
        row=result['media_evidence'][0]
        self.assertEqual(row['internal_content'],'UNKNOWN_NOT_INSPECTED')
        self.assertEqual(row['media_role'],'unknown')

    def test_opaque_canvas_target_and_gif_target_need_semantic_review(self):
        for kind in ['canvas','image_candidate']:
            item={'kind':kind,'selector':'#graphic','bbox':[20,100,450,260],'gif_url_candidate':True,
                  'context':{},'task_relations':[{'target_selector':'#graphic','contains_target':True}]}
            result=self.check([probe(media=[item])],'REVIEW_REQUIRED')
            self.assertEqual(result['media_evidence'][0]['media_role'],'unknown')

    def test_aggregate_pixel_bbox_is_only_a_weak_change_clue(self):
        item={'kind':'canvas','selector':'#graphic','bbox':[20,100,450,260],'context':{},'task_relations':[]}
        result=self.check([probe(media=[item])],'DYNAMIC_CONTENT_TRACK',pixels=[
            {'changed_fraction':.02,'bbox':[10,50,750,300]}])
        row=result['media_evidence'][0]
        self.assertTrue(row['pixel_bbox_is_aggregate_weak_clue'])
        self.assertEqual(row['rendered_animation'],'UNKNOWN_WITHOUT_DECODED_CONTENT_INSPECTION')
        self.assertEqual(row['media_role'],'unknown')

    def test_safe_preparation_and_uncloseable_obstruction_are_distinct(self):
        self.check([probe()],'PREPARE_RECHECK',[assessment('close_overlay')])
        self.check([probe()],'REVIEW_REQUIRED',[assessment('blocked')])

    def test_missing_identity_timestamp_or_changed_document_never_normal(self):
        variants=[{},probe(),probe()]
        variants[1].pop('observed_at_performance_ms')
        variants[2]['document_identity']={}
        for invalid in variants:
            with self.subTest(invalid=invalid):self.check([invalid],'REVIEW_REQUIRED')
        second=probe(600);second['document_identity']['performance_time_origin']=2000
        self.check([probe(),second],'REVIEW_REQUIRED')
        self.check([probe(600),probe(100)],'REVIEW_REQUIRED')

    def test_truncated_inventory_and_empty_evidence_are_review(self):
        item=probe();item['limitations']['animations_truncated']=True
        self.check([item],'REVIEW_REQUIRED')
        self.check([],'REVIEW_REQUIRED')


class ProbeTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_does_not_return_a_low_risk_result(self):
        class Page:
            async def evaluate(self,*_):await asyncio.sleep(1)
        with self.assertRaisesRegex(TimeoutError,'不能视为无动态风险'):
            await probe_media(Page(),{},timeout=.01)


class BrowserProbeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime=await async_playwright().start()
        self.browser=await self.runtime.chromium.launch(channel='chrome',headless=True)
        self.page=await self.browser.new_page(viewport={'width':800,'height':600})

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def load(self,html):
        await self.page.set_content('<!doctype html><meta charset="utf-8"><style>body{margin:0;font:20px sans-serif}article{width:500px;margin:20px}video{width:400px;height:160px}button{font:inherit}</style>'+html)

    async def test_probe_leaves_dom_scroll_focus_and_playback_controls_untouched(self):
        await self.load('''<article id="article"><h1>广告行业观察</h1><p id="body">报道讨论广告行业的统计方法，并非推广。</p>
            <video id="poster" autoplay muted poster="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='40'%3E%3Crect width='80' height='40' fill='green'/%3E%3C/svg%3E"></video></article>
            <button id="button">确认</button><video id="hidden" style="display:none"></video>
            <script>window.controlCalls=[];for(const name of ['play','pause']){const fn=HTMLMediaElement.prototype[name];HTMLMediaElement.prototype[name]=function(...args){controlCalls.push(name);return fn.apply(this,args);};}</script>''')
        await self.page.locator('#button').focus()
        before=await self.page.content();position=await self.page.evaluate('({x:scrollX,y:scrollY,focus:document.activeElement.id})')
        requests=[];self.page.on('request',lambda request:requests.append(request.url))
        result=await probe_media(self.page,{'operations':[{'action_type':'click','selector':'#button'}]})
        self.assertEqual(before,await self.page.content())
        self.assertEqual(position,await self.page.evaluate('({x:scrollX,y:scrollY,focus:document.activeElement.id})'))
        self.assertEqual(await self.page.evaluate('controlCalls'),[])
        self.assertEqual(requests,[])
        self.assertEqual([m['selector'] for m in result['media']],['#poster'])
        self.assertTrue(result['media'][0]['paused'])
        self.assertEqual(result['media'][0]['context']['explicit_ad_markers'],[])
        self.assertEqual(result['explicit_ad_markers'],[])
        self.assertTrue(result['task_targets'][0]['visible_hit'])
        json.dumps(result,allow_nan=False)

    async def test_real_playing_video_progresses_without_probe_play_or_pause(self):
        await self.load('''<article id="article"><h1>水位变化演示</h1><p id="body">观察正文视频中的水位。</p><video id="video" autoplay muted playsinline></video></article>
            <canvas id="source" width="160" height="80" style="display:none"></canvas><script>
            const canvas=document.querySelector('#source'),v=document.querySelector('#video');let frame=0;
            const draw=()=>{const c=canvas.getContext('2d');c.fillStyle=frame++%2?'blue':'green';c.fillRect(0,0,160,80);};draw();setInterval(draw,60);
            v.srcObject=canvas.captureStream(15);
            </script>''')
        await self.page.wait_for_function('!document.querySelector("#video").paused && document.querySelector("#video").readyState>=2')
        before=await self.page.content()
        task={'operations':[{'action_type':'click','selector':'#video'}]}
        first=await probe_media(self.page,task);await self.page.wait_for_timeout(250);last=await probe_media(self.page,task)
        result=summarize_preflight([first,last],[assessment()])
        self.assertEqual(result['routing'],'DYNAMIC_CONTENT_TRACK')
        self.assertTrue(result['media_evidence'][0]['observed_time_progress'])
        self.assertEqual(result['media_evidence'][0]['media_role'],'editorial_candidate')
        self.assertFalse(await self.page.locator('#video').evaluate('(v)=>v.paused'))
        self.assertEqual(before,await self.page.content())
        self.assertTrue(first['media'][0]['source_object_tracks'])

    async def test_explicit_promotion_and_real_media_hit_coverage_are_recorded(self):
        await self.load('''<button id="target" style="position:absolute;left:100px;top:100px;width:200px;height:90px">原任务目标</button>
            <aside aria-label="广告：独立测试推广"><canvas id="cover" width="250" height="140" style="position:fixed;left:80px;top:80px;background:orange"></canvas></aside>''')
        result=await probe_media(self.page,{'operations':[{'action_type':'click','selector':'#target'}]})
        self.assertFalse(result['task_targets'][0]['visible_hit'])
        self.assertTrue(result['media'][0]['task_relations'][0]['dom_hit_covers_target_point'])
        self.assertTrue(result['media'][0]['context']['explicit_ad_markers'])
        self.assertEqual(summarize_preflight([result],[assessment()])['routing'],'REVIEW_REQUIRED')

    async def test_plain_dialog_label_is_retained_without_any_media_tag(self):
        await self.load('''<article><h1>普通正文</h1><p id="body">原始正文。</p></article>
            <section role="dialog" style="position:fixed;inset:40px;background:white"><h2>广告：阅读活动推广</h2><button>关闭</button></section>''')
        result=await probe_media(self.page,{})
        self.assertEqual(result['media'],[])
        self.assertEqual(result['explicit_ad_markers'][0]['text'],'广告：阅读活动推广')
        summary=summarize_preflight([result],[assessment('close_overlay')])
        self.assertEqual(summary['routing'],'PREPARE_RECHECK')
        self.assertTrue(summary['advertising_marker_evidence'])
        self.assertEqual(await self.page.locator('[role=dialog]').count(),1)

    async def test_cross_origin_frame_remains_uninspected_and_probe_issues_no_requests(self):
        requests=[];self.page.on('request',lambda request:requests.append(request.url))
        async def local_route(route):
            html='<iframe id="frame" src="http://localhost:8123/frame" style="width:400px;height:200px"></iframe>' if route.request.url.endswith('/main') else '<h1>Private frame</h1><video autoplay></video>'
            await route.fulfill(content_type='text/html',body=html)
        await self.page.route('**/*',local_route)
        await self.page.goto('http://127.0.0.1:8123/main')
        count=len(requests);result=await probe_media(self.page,{'operations':[{'action_type':'click','selector':'#frame'}]})
        self.assertEqual(len(requests),count)
        self.assertEqual(len(result['media']),1)
        self.assertTrue(result['media'][0]['cross_origin'])
        self.assertEqual(result['media'][0]['internal_content'],'UNKNOWN_NOT_INSPECTED')
        self.assertEqual(summarize_preflight([result],[assessment()])['routing'],'REVIEW_REQUIRED')

    async def test_native_timing_and_opaque_candidates_are_facts_not_ad_labels(self):
        await self.load('''<style>@keyframes rotate{0%{transform:rotate(0deg)}40%,100%{transform:rotate(20deg)}}
            #badge{position:fixed;left:700px;top:20px;width:30px;height:30px;background:green;animation:rotate 4s infinite linear}</style>
            <article><h1>普通正文</h1><p id="body">正文可读。</p></article><div id="badge"></div>
            <canvas id="canvas" width="80" height="40"></canvas><svg width="80" height="40"><image id="svgimage" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40'/%3E" width="40" height="40"/></svg>
            <img id="gif" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" width="20" height="20">''')
        before=await self.page.content();result=await probe_media(self.page,{})
        self.assertEqual({x['kind'] for x in result['media']},{'canvas','svg_image','image_candidate'})
        self.assertEqual(result['native_animations'][0]['timing']['iterations'],'Infinity')
        self.assertEqual(result['native_animations'][0]['context']['explicit_ad_markers'],[])
        self.assertEqual(await self.page.evaluate('document.getAnimations()[0].playState'),'running')
        self.assertEqual(before,await self.page.content())
        json.dumps(result,allow_nan=False)


if __name__=='__main__':unittest.main()
