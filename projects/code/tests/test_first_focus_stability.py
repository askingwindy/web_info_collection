"""Real Chromium, controlled public-URL route; no provider or external network."""
import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from playwright.async_api import async_playwright
from webcollect import browser
from webcollect.action_stability import VERSION
from webcollect.batch_core import load_json
from webcollect.goal_evidence import search_focus_target
from webcollect.react_session import ReactSession, build_url_task
from webcollect.plan_protocol import PLAN_PROTOCOL as PLAN_VERSION


HTML = '''<!doctype html><meta charset="utf-8"><style>
body{margin:0;font:18px Arial;background:white;color:black}#notice{position:absolute;left:20px;top:20px;width:550px;height:60px}
main{position:absolute;left:80px;top:170px}input{width:320px;height:42px;font:18px Arial}label{display:block}button{margin-left:20px}
</style><aside id="notice">本地公告甲</aside><main><form><label for="q">搜索维基百科</label>
<input id="q" type="search" placeholder="搜索维基百科"><button>搜索</button></form><p>本地受控页面</p></main>'''


class FirstFocusBrowser(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base_root = self.root
        self.fixture_html = HTML
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(channel='chrome', headless=True)
        self.context = await self.browser.new_context(viewport={'width': 1000, 'height': 720}, device_scale_factor=1)
        await self.context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=self.fixture_html))
        self.page = await self.context.new_page()
        await self.new_session('initial')

    async def new_session(self, name, *, contracted=True, protocol=VERSION):
        from webcollect.goal_evidence import VERSION as EVIDENCE_VERSION
        from webcollect.planning import object_sha256
        self.root = self.base_root/name
        task = build_url_task(url='https://focus.example.org/', task_version='focus-fixture',
                              plan_protocol=PLAN_VERSION, action_stability_protocol=protocol)
        if contracted:
            spec = task['workflow_proposal']['spec']
            spec['goal']['structured'] = {'evidence_contract': {'version':EVIDENCE_VERSION,
                'kind':'reading','subject':'月食','aspects':['月球','地球']}}
            task['task_id'] = 'react-'+object_sha256({'url':task['initial_url'],'spec':spec})[:24]
        async def preflight(page, root):
            return {'completed_probe_count':2, 'summary':{'routing':'NORMAL_M1'}}
        self.session = ReactSession(task, self.root, lambda p: None, self.page, attempt_id=name, preflight=preflight)
        # Normal navigation + trusted capture entry, followed by its targeted probe.
        await self.session._open_entry()
        target = search_focus_target(self.session.current)
        self.assertIsNotNone(target)
        await self.session._observe(target['node'])
        self.cid = target['node']
        if contracted and not (self.session.current['controls'][self.cid].get('value') or {}).get('focused'):
            self.assertEqual(self.session.preflight_search_focus, target)

    async def asyncTearDown(self):
        await self.context.close(); await self.browser.close(); await self.pw.stop()

    async def dispatch(self):
        return await self.session._dispatch_compiled({'goal': '聚焦已核实搜索框', 'expected': '搜索框获得焦点'},
            [{'action': 'click', 'control_id': self.cid, 'goal':'聚焦已核实搜索框', 'expected':'搜索框获得焦点'}])

    async def test_slow_capture_changing_notice_dispatches_once_with_full_before_after(self):
        original = browser.viewport_png
        calls = []
        async def changing(page):
            # Capture + verification + final dispatch verification all see changes.
            if self.session.actual_dispatches == 0:
                await asyncio.sleep(14 if not calls else .15)
                await page.evaluate("n=>document.querySelector('#notice').textContent='本地公告 '+n", len(calls))
            calls.append(self.session.actual_dispatches)
            return await original(page)
        with patch('webcollect.browser.viewport_png', side_effect=changing):
            result = await self.dispatch()
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(self.session.actual_dispatches, 1)
        self.assertEqual(len(self.session.trajectory), 1)
        self.assertTrue(await self.page.locator('#q').evaluate('e=>e===document.activeElement'))
        # Trajectory carries full capture references and a recomputable local receipt.
        for ob in self.session.observation_records.values():
            self.assertTrue(Path(ob['evidence']['image']['path']).is_file())
        proofs = [load_json(p)['proof'] for p in self.root.glob('*-action-local-stability.json')]
        self.assertTrue(proofs and proofs[0]['accepted'])
        self.assertGreater(proofs[0]['pixel_change']['changed_pixels'], 0)
        self.assertEqual(proofs[0]['pixel_change']['outside_allowed_pixels'], 0)

    async def test_move_occlude_replace_reload_and_local_pixels_reject_old_action(self):
        original = browser.viewport_png
        for name, script in (
            ('move', "document.querySelector('#q').style.transform='translateX(12px)'"),
            ('replace', "document.querySelector('#q').outerHTML=document.querySelector('#q').outerHTML"),
            ('occlude', "let e=document.createElement('div');e.style='position:absolute;left:80px;top:190px;width:330px;height:50px;background:red;z-index:999';document.body.append(e)"),
            ('pixels', "document.querySelector('#q').style.background='yellow'"),
            ('reload', None),
        ):
            with self.subTest(name=name):
                await self.new_session(name)
                doc = deepcopy(self.session.current['document_identity'])
                injected = False
                async def blocked(page):
                    nonlocal injected
                    if not injected:
                        injected=True
                        if script: await page.evaluate(script)
                        else: await page.reload()
                    return await original(page)
                # Explicit one-candidate capture setting; still the normal dispatcher.
                from webcollect.collect import capture as original_capture
                async def single_capture(*args, **kwargs):
                    return await original_capture(*args, **kwargs, retries=1)
                with patch('webcollect.browser.viewport_png', side_effect=blocked), patch('webcollect.collect.capture', side_effect=single_capture):
                    result = await self.dispatch()
                self.assertEqual(result['status'], 'need_observation', result)
                self.assertEqual(self.session.actual_dispatches, 0)
                if script:
                    self.assertEqual((await browser.observe(self.page))['document_identity'], doc)

    async def test_uncontracted_search_click_uses_same_proof_and_focused_entry_does_not_add_click(self):
        await self.new_session('uncontracted', contracted=False)
        self.assertFalse(hasattr(self.session, 'preflight_search_focus'))
        result = await self.dispatch()
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(self.session.actual_dispatches, 1)
        self.fixture_html = HTML.replace('id="q"', 'id="q" autofocus')
        await self.new_session('already-focused')
        self.assertFalse(hasattr(self.session, 'preflight_search_focus'))
        row = {'action':'type','control_id':self.cid,'value':'月食','goal':'输入站内检索词','expected':'检索词显示'}
        result = await self.session._dispatch_compiled({'goal':row['goal'],'expected':row['expected']}, [row])
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(self.session.actual_dispatches, 1)
        self.assertEqual(self.session.trajectory[0]['action'], 'type')

    async def test_budget_expires_before_dispatch_and_after_dispatch_unknown_is_not_replayed(self):
        from webcollect.collect import capture_before_action
        from webcollect.react_session import ReactStop
        async def stalled(*args, **kwargs): await asyncio.sleep(.2)
        with patch('webcollect.collect.capture', side_effect=stalled):
            with self.assertRaises(TimeoutError):
                await capture_before_action(self.page, self.root, timeout=.02)
        self.assertEqual(self.session.actual_dispatches, 0)
        with patch('webcollect.browser.execute', side_effect=TimeoutError('controlled effect unknown')):
            with self.assertRaises(ReactStop): await self.dispatch()
        self.assertEqual(self.session.actual_dispatches, 1)
        self.assertTrue(self.session.unknown)
        self.assertEqual(len(self.session.trajectory), 0)

    async def test_new_dynamic_capture_allows_notice_for_both_action_protocols(self):
        self.fixture_html=HTML.replace('id="q"','id="q" autofocus')
        original=browser.viewport_png
        for name,protocol in (('scoped-typing',VERSION),):
            await self.new_session(name,protocol=protocol)
            count=0
            async def changing(page):
                nonlocal count
                if not self.session.actual_dispatches:
                    count+=1
                    await page.evaluate("n=>document.querySelector('#notice').textContent='公告 '+n",count)
                return await original(page)
            from webcollect.collect import capture as original_capture
            async def single_capture(*args,**kwargs):return await original_capture(*args,**kwargs,retries=1)
            row={'action':'type','control_id':self.cid,'value':'月食','goal':'输入站内检索词','expected':'检索词显示'}
            with patch('webcollect.browser.viewport_png',side_effect=changing),patch('webcollect.collect.capture',side_effect=single_capture):
                result=await self.session._dispatch_compiled({'goal':row['goal'],'expected':row['expected']},[row])
            self.assertEqual(self.session.actual_dispatches,1,result)
            self.assertEqual(result['status'],'ok',result)
            self.assertEqual(len(self.session.trajectory),1)
            self.assertEqual(await self.page.locator('#q').input_value(),'月食')

    async def test_v2_typing_rejects_lost_focus_value_replacement_and_occlusion(self):
        self.fixture_html=HTML.replace('id="q"','id="q" autofocus')
        original=browser.viewport_png
        for name,script in (
            ('lost-focus',"document.querySelector('#q').blur()"),
            ('changed-value',"document.querySelector('#q').value='外部修改'"),
            ('new-node',"let q=document.querySelector('#q');q.outerHTML=q.outerHTML;document.querySelector('#q').focus()"),
            ('covered',"let d=document.createElement('div');d.style='position:absolute;left:80px;top:190px;width:330px;height:50px;background:red;z-index:999';document.body.append(d)"),
        ):
            with self.subTest(name=name):
                await self.new_session(name,protocol=VERSION)
                injected=False
                async def changed(page):
                    nonlocal injected
                    if not injected:injected=True;await page.evaluate(script)
                    return await original(page)
                from webcollect.collect import capture as original_capture
                async def single_capture(*args,**kwargs):return await original_capture(*args,**kwargs,retries=1)
                row={'action':'type','control_id':self.cid,'value':'月食','goal':'输入站内检索词','expected':'检索词显示'}
                with patch('webcollect.browser.viewport_png',side_effect=changed),patch('webcollect.collect.capture',side_effect=single_capture):
                    result=await self.session._dispatch_compiled({'goal':row['goal'],'expected':row['expected']},[row])
                self.assertEqual(result['status'],'need_observation',result)
                self.assertEqual(self.session.actual_dispatches,0)

    async def test_v2_input_combobox_existing_bottom_separator_retains_readable_keyboard_target(self):
        self.fixture_html=HTML.replace('id="q"','id="q" autofocus')
        await self.new_session('input-combobox',protocol=VERSION)
        await self.page.evaluate("""() => {
          const q=document.querySelector('#q');q.setAttribute('role','combobox');q.setAttribute('aria-expanded','true');q.style.height='42.25px';
          const r=q.getBoundingClientRect(),d=document.createElement('div');
          d.style=`position:absolute;left:${r.left}px;top:${r.bottom}px;width:${r.width}px;height:1px;background:black;z-index:9`;
          document.body.append(d);
        }""")
        await self.session._observe();await self.session._observe(self.cid)
        state=load_json(self.session.current['evidence']['state']['path'])
        samples=next(r['samples'] for r in state['geometry_witnesses'] if r['element_id']==self.cid)
        self.assertFalse(all(p['ancestor'] for p in samples))
        self.assertTrue(samples[4]['ancestor'])
        self.assertTrue(next(v['value_visible'] for v in state['values'] if v['element_id']==self.cid))
        original=browser.viewport_png;count=0
        async def changing(page):
            nonlocal count
            if not self.session.actual_dispatches:
                count+=1;await page.evaluate("n=>document.querySelector('#notice').textContent='公告 '+n",count)
            return await original(page)
        row={'action':'type','control_id':self.cid,'value':'月食','goal':'输入检索词','expected':'检索词显示'}
        with patch('webcollect.browser.viewport_png',side_effect=changing):
            result=await self.session._dispatch_compiled({'goal':row['goal'],'expected':row['expected']},[row])
        self.assertEqual(result['status'],'ok',result)
        self.assertEqual(self.session.actual_dispatches,1)
        self.assertEqual(len(self.session.trajectory),1)
        self.assertEqual(await self.page.locator('#q').input_value(),'月食')

