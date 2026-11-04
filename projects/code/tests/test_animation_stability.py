"""Handwritten native-timing cases and real local CSS, never delivery data."""
import copy
from io import BytesIO
import json
import unittest
from unittest.mock import AsyncMock,patch

from PIL import Image
from playwright.async_api import async_playwright
from webcollect.browser import _native_animation_window,capture


def shaking(current=0):
    # Independent 4s fixture: first40% moves, last60% has identical transform.
    return {'kind':'CSSAnimation','play_state':'running','pending':False,'current_time':current,
            'playback_rate':1,'start_time':0,'pseudo_element':None,'composite':'replace','iteration_composite':'replace',
            'timing':{'duration':4000,'delay':0,'iterations':'Infinity','iterationStart':0,'direction':'normal','easing':'linear'},
            'keyframes':[{'computedOffset':offset,'offset':offset,'easing':'ease-in-out','composite':'auto','transform':value}
                         for offset,value in [(0,'rotate(0deg)'),(.2,'rotate(8deg)'),(.4,'rotate(0deg)'),(1,'rotate(0deg)')]],
            'target':{'tag':'div','id':'local-fixture'}}


class NativeWindowPlanning(unittest.TestCase):
    def plan(self,animations,budget=8000,required=1000):
        return _native_animation_window({'visible_animations':animations},budget,required)

    def test_next_rotation_hold_then_current_hold(self):
        plan=self.plan([shaking(0)])
        self.assertEqual(plan['status'],'native_window_predicted')
        self.assertEqual(plan['wait_ms'],1650)
        self.assertEqual(plan['common_window_relative_ms'],[1650,3950])
        current=self.plan([shaking(1700)])
        self.assertEqual(current['wait_ms'],0)
        self.assertGreaterEqual(current['common_window_relative_ms'][1],1000)

    def test_near_hold_end_waits_next_cycle(self):
        plan=self.plan([shaking(3500)])
        self.assertEqual(plan['wait_ms'],2150)
        self.assertGreaterEqual(plan['common_window_relative_ms'][1]-plan['wait_ms'],1000)

    def test_no_hold_and_unsupported_timing_cannot_promise_window(self):
        for change in ['no_hold','reverse','nonlinear','negative_rate','pending','additive','missing_property']:
            animation=shaking()
            if change=='no_hold':animation['keyframes'][-1]['transform']='rotate(90deg)'
            if change=='reverse':animation['timing']['direction']='alternate'
            if change=='nonlinear':animation['timing']['easing']='ease'
            if change=='negative_rate':animation['playback_rate']=-1
            if change=='pending':animation['pending']=True
            if change=='additive':animation['composite']='add'
            if change=='missing_property':del animation['keyframes'][-1]['transform']
            with self.subTest(change=change):
                plan=self.plan([animation]);self.assertEqual(plan['status'],'unsupported');self.assertEqual(plan['wait_ms'],0)

    def test_all_visible_animations_need_a_common_long_window(self):
        aligned=self.plan([shaking(0),shaking(0)])
        self.assertEqual(aligned['wait_ms'],1650)
        disjoint=self.plan([shaking(0),shaking(2000)])
        self.assertEqual(disjoint['status'],'no_common_window_within_budget')
        self.assertEqual(disjoint['wait_ms'],0)
        unsupported=shaking();unsupported['timing']['direction']='reverse'
        mixed=self.plan([shaking(),unsupported]);self.assertEqual(mixed['status'],'unsupported')

    def test_transition_may_end_naturally_but_budget_is_not_extended(self):
        transition={'kind':'CSSTransition','play_state':'running','pending':False,'current_time':200,
                    'playback_rate':1,'start_time':0,'timing':{'direction':'normal','easing':'ease'},'computed_timing':{'endTime':500}}
        self.assertEqual(self.plan([transition])['wait_ms'],350)
        self.assertEqual(self.plan([shaking()],budget=1000)['status'],'no_common_window_within_budget')
        self.assertTrue(self.plan([transition])['prediction_is_not_capture_acceptance'])

    def test_recent_slow_capture_needs_longer_actual_hold(self):
        plan=self.plan([shaking(2600)],required=1500)
        self.assertGreater(plan['wait_ms'],0)
        self.assertGreaterEqual(plan['common_window_relative_ms'][1]-plan['wait_ms'],1500)


class NativeWindowBudget(unittest.IsolatedAsyncioTestCase):
    async def test_window_waits_and_retry_backoff_share_one_eight_second_budget(self):
        # The read-only native timeline does not confirm the forecast in this
        # fake sequence. It still cannot extend the budget or accept mismatches.
        page=AsyncMock();page.evaluate.return_value={'visible_animations':[shaking(0)]}
        states=[{'screen_resolution':[16,12],'visible_text':str(i)} for i in range(16)]
        stream=BytesIO();Image.new('RGB',(16,12),'white').save(stream,format='PNG')
        with patch('webcollect.browser.observe',AsyncMock(side_effect=states)), \
             patch('webcollect.browser.viewport_png',AsyncMock(return_value=(stream.getvalue(),{}))), \
             patch('webcollect.browser.asyncio.sleep',AsyncMock()) as sleep:
            with self.assertRaises(ValueError) as caught:await capture(page)
        proof=caught.exception.capture
        self.assertEqual(len(proof['attempts']),8)
        self.assertTrue(all(not a['dom_stable'] for a in proof['attempts']))
        self.assertTrue(any(a['native_window_wait_ms']>0 for a in proof['attempts']))
        self.assertTrue(any(a['delay_before_ms']>0 for a in proof['attempts']))
        self.assertLessEqual(sum(call.args[0] for call in sleep.await_args_list),8.0)
        self.assertEqual(proof['natural_wait_requested_ms'],8000)
        self.assertTrue(any(a['native_window_evidence']['status']=='window_recheck_not_confirmed' for a in proof['attempts']))


class NativeWindowChrome(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime=await async_playwright().start()
        self.browser=await self.runtime.chromium.launch(channel='chrome',headless=True)
        self.page=await self.browser.new_page(viewport={'width':800,'height':600})

    async def asyncTearDown(self):
        await self.browser.close();await self.runtime.stop()

    async def test_pulsing_bookmark_is_captured_in_its_natural_zero_scale_phase(self):
        from webcollect.browser import validate_capture_receipt, verify_execution_state
        await self.page.set_content('''<style>
        #bookmark{position:relative;margin:80px;width:42px;height:32px}
        #bookmark::before{content:"";position:absolute;left:0;top:20px;width:32px;height:32px;
          border-radius:100%;background:blue;animation:pulse 3s infinite ease-out}
        @keyframes pulse{0%{transform:scale(0);opacity:0}25%{transform:scale(0);opacity:.1}
        50%{transform:scale(.1);opacity:.3}75%{transform:scale(.5);opacity:.5}100%{transform:scale(1);opacity:0}}
        </style><main><h1>资料库</h1><button id="bookmark">收藏</button></main>''')
        await self.page.wait_for_timeout(850)
        result=await capture(self.page)
        attempts=result['capture']['attempts']
        self.assertEqual(len(attempts[-1]['png_phase_waits']),2)
        self.assertTrue(validate_capture_receipt(result['state'],result['capture'],result['png']))
        self.assertTrue((await verify_execution_state(self.page,result['state']))['matched'])
        self.assertLessEqual(result['capture']['natural_wait_requested_ms'],8000)
        self.assertEqual(await self.page.evaluate('document.getAnimations()[0].playState'),'running')

    async def test_periodic_motion_waits_for_natural_hold_without_pausing(self):
        await self.page.set_content('''<!doctype html><meta charset="utf-8"><style>
          body{font:20px sans-serif}#moving{width:100px;height:100px;background:#ddf;position:absolute;right:30px;top:100px;animation:fixture-motion 4s infinite}
          @keyframes fixture-motion{0%{transform:rotate(0deg)}20%{transform:rotate(8deg)}40%,100%{transform:rotate(0deg)}}
          </style><p>独立手写的公开正文保持原状。</p><div id="moving">实际可见动画</div>''')
        await self.page.wait_for_timeout(40)
        html=await self.page.content()
        result=await capture(self.page)
        self.assertGreaterEqual(result['capture']['natural_wait_requested_ms'],1000)
        self.assertLessEqual(result['capture']['natural_wait_requested_ms'],8000)
        attempts=result['capture']['attempts'];self.assertTrue(attempts[-1]['dom_stable'])
        self.assertEqual(attempts[-1]['before_fingerprint'],attempts[-1]['after_fingerprint'])
        native=[o['native'] for a in attempts for o in a['native_window_evidence']['observations']]
        self.assertTrue(any(a['timing']['iterations']=='Infinity' for n in native for a in n['visible_animations']))
        self.assertEqual(await self.page.content(),html)
        self.assertEqual(await self.page.evaluate('document.getAnimations()[0].playState'),'running')
        current=await self.page.evaluate('document.getAnimations()[0].currentTime')
        await self.page.wait_for_timeout(30)
        self.assertGreater(await self.page.evaluate('document.getAnimations()[0].currentTime'),current)
        self.assertEqual(await self.page.evaluate('[scrollX,scrollY]'),[0,0])
        json.dumps({'state':result['state'],'capture':result['capture']},allow_nan=False)

    async def test_visible_continuous_motion_has_no_hold_and_is_rejected(self):
        await self.page.set_content('''<!doctype html><meta charset="utf-8"><style>
          #moving{width:100px;height:80px;position:absolute;top:100px;left:0;background:#fdd;animation:continuous-motion 4s linear infinite}
          @keyframes continuous-motion{from{transform:translateX(0px)}to{transform:translateX(600px)}}
          </style><p>正文保持原状。</p><div id="moving">持续自然移动</div>''')
        await self.page.wait_for_timeout(40);html=await self.page.content()
        with self.assertRaisesRegex(ValueError,'拒绝保存') as caught:
            await capture(self.page,retries=3)
        self.assertEqual(len(caught.exception.capture['attempts']),3)
        self.assertLessEqual(caught.exception.capture['natural_wait_requested_ms'],8000)
        self.assertTrue(all(not a['dom_stable'] for a in caught.exception.capture['attempts']))
        self.assertTrue(all(a['native_window_wait_ms']==0 for a in caught.exception.capture['attempts']))
        self.assertTrue(all(a['native_window_evidence']['observations'][0]['plan']['status']=='unsupported' for a in caught.exception.capture['attempts']))
        self.assertEqual(await self.page.content(),html)
        self.assertEqual(await self.page.evaluate('document.getAnimations()[0].playState'),'running')
        json.dumps(caught.exception.capture,allow_nan=False)


if __name__=='__main__':unittest.main()
