"""浏览器证据测试使用本地 HTML 夹具，不计入真实采集样本。"""
import asyncio
from pathlib import Path
import tempfile
import unittest
from playwright.async_api import async_playwright
from webcollect.browser import capture,prepare_action,execute
from webcollect.collect import assert_state,validate_plan,chinese_ratio
from webcollect.storage import allocate

HTML='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><body>
<label for="name">姓名</label><input id="name" placeholder="请输入姓名">
<button id="send" onclick="document.getElementById('result').textContent='欢迎'+document.getElementById('name').value">确定</button>
<p id="result">结果待显示</p><div style="display:none">不可见内容</div>
<div style="position:absolute;left:-10px;top:80px;width:50px;height:40px" id="clip">裁剪文字</div>
<div style="height:1200px"></div><button id="below">下方控件</button>
</body></html>'''

class BrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.p=await async_playwright().start()
        self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':1280,'height':720},device_scale_factor=2)
        self.page=await self.context.new_page()
        await self.page.set_content(HTML)

    async def asyncTearDown(self):
        await self.browser.close();await self.p.stop()

    async def test_visible_snapshot_clip_and_dpr(self):
        r=await capture(self.page,'#clip')
        self.assertEqual(r['state']['device_pixel_ratio'],2)
        self.assertEqual(r['state']['screen_resolution'],[1280,720])
        self.assertEqual(r['state']['target']['coordinate'][0],19)
        texts=[e['text'] for e in r['state']['elements']]
        self.assertNotIn('不可见内容',texts)
        self.assertNotIn('下方控件',texts)
        self.assertTrue(all(a['dom_stable'] for a in r['capture']['attempts']))

    async def test_no_hidden_focus_or_scroll(self):
        r=await capture(self.page,'#name')
        with self.assertRaises(ValueError):prepare_action(r['state'],{'action_type':'type','arguments':{'text':'测试'}})
        r=await capture(self.page,'#below')
        with self.assertRaises(ValueError):prepare_action(r['state'],{'action_type':'click'})
        self.assertEqual(await self.page.evaluate('scrollY'),0)

    async def test_real_keyboard_sequence_and_result(self):
        r=await capture(self.page,'#name')
        args,e=prepare_action(r['state'],{'action_type':'click'})
        self.assertEqual(e['text'],'姓名')
        await execute(self.page,'click',args,{'settle_ms':0})
        r=await capture(self.page,'#name')
        args,_=prepare_action(r['state'],{'action_type':'type','arguments':{'text':'张三'}})
        await execute(self.page,'type',args,{'settle_ms':0})
        r=await capture(self.page,'#send')
        args,_=prepare_action(r['state'],{'action_type':'click'})
        await execute(self.page,'click',args,{'settle_ms':0})
        passed=await assert_state(self.page,[{'selector':'#result','contains':'欢迎张三'}])
        self.assertTrue(passed[0]['passed'])

    async def test_final_assertions_cannot_use_offscreen_dom(self):
        with self.assertRaises(ValueError):await assert_state(self.page,[{'selector':'#below','contains':'下方控件'}])

    async def test_adjacent_real_dom_label_without_for(self):
        await self.page.set_content('<div><label>精度</label><div><input id="precision"></div></div>')
        result=await capture(self.page,'#precision')
        _,element=prepare_action(result['state'],{'action_type':'click'})
        self.assertEqual(element['text'],'精度')

    async def test_readonly_display_is_not_placeholder_or_editable(self):
        await self.page.set_content('<input id="unit" role="combobox" readonly placeholder="请选择" value="千米">')
        result=await capture(self.page,'#unit')
        _,element=prepare_action(result['state'],{'action_type':'click'})
        self.assertEqual(element['text'],'千米')
        self.assertFalse(element['inputable'])
        with self.assertRaises(ValueError):prepare_action(result['state'],{'action_type':'type','arguments':{'text':'米'}})

    async def test_readonly_output_keeps_label_and_is_not_choice(self):
        await self.page.set_content('<div><label>结果</label><input readonly id="answer" value="2.50"></div>')
        state=(await capture(self.page,'#answer'))['state']
        _,element=prepare_action(state,{'action_type':'click'})
        self.assertEqual(element['text'],'结果')
        value=next(v for v in state['values'] if v['element_id']==element['element_id'])
        self.assertFalse(value['choice'])

    async def test_node_identity_survives_insertion(self):
        before=await capture(self.page,'#name')
        await self.page.evaluate("document.body.insertAdjacentHTML('afterbegin','<p>新增提示</p>')")
        after=await capture(self.page,'#name')
        self.assertEqual(before['state']['target']['element_id'],after['state']['target']['element_id'])

    async def test_bad_parameters_rejected_before_browser_action(self):
        state=(await capture(self.page,'#send'))['state']
        with self.assertRaises(ValueError):prepare_action(state,{'action_type':'click','arguments':{'selector':'#send'}})
        with self.assertRaises(ValueError):prepare_action(state,{'action_type':'scroll','arguments':{'x':2000,'y':100,'direction':'down'}})

    async def test_native_select_atomic_mapping(self):
        await self.page.set_content('<label for="unit">单位</label><select id="unit"><option value="m">米</option><option value="km">千米</option></select>')
        state=(await capture(self.page,'#unit'))['state']
        args,element=prepare_action(state,{'action_type':'select','arguments':{'option':'千米'}})
        self.assertEqual(element['text'],'单位')
        await execute(self.page,'select',args,{'settle_ms':0})
        self.assertEqual(await self.page.locator('#unit').input_value(),'km')
        state=(await capture(self.page,'#unit'))['state']
        self.assertEqual(next(v for v in state['values'] if v['element_id']==state['target']['element_id'])['display_value'],'千米')

    async def test_capture_evidence_and_tampering(self):
        import functools
        from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
        import threading
        from webcollect.collect import collect_one
        from webcollect.evidence import audit_capture
        from webcollect.validate import read_json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            html=HTML.replace('<button id="send"', '<label for="city">城市</label><input id="city"><button id="send"')
            (root/'page.html').write_text(html)
            class QuietHandler(SimpleHTTPRequestHandler):
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(root)))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                operations=[]
                for action,selector,arguments in [('click','#name',{}),('type','#name',{'text':'张三'}),('click','#city',{}),('type','#city',{'text':'北京'}),('click','#send',{})]:
                    operations.append({'action_type':action,'selector':selector,'arguments':arguments,'goal':'验证页面操作','rationale':'页面中可见目标控件','expected':'页面显示预期结果','execution':{'settle_ms':0}})
                task={'initial_url':f'http://127.0.0.1:{server.server_port}/page.html','initial_settle_ms':0,'operations':operations,
                    'final_assertions':[{'selector':'#result','contains':'欢迎张三'}],'final_result':'页面显示欢迎张三','task_id':'local-fixture',
                    'completion_judgement':'结果中可见欢迎张三','instruction':'本地夹具测试，不是交付数据','task_type':['填写表单'],'app_name':'本地夹具'}
                ids={'sample_id':'S000001_sample_000001'}
                await collect_one(self.context,task,root/'batch/samples'/ids['sample_id'],root/'batch/evidence'/ids['sample_id'],ids)
                result=audit_capture(root/'batch',ids['sample_id'])
                self.assertTrue(result['capture_evidence_pass'],result)
                self.assertEqual(result['steps_checked'],6)
                annotation=root/'batch/samples'/ids['sample_id']/'annotation.json'
                import json
                data=read_json(annotation);data['steps'][0]['tool_call']['arguments']['x']+=1
                annotation.write_text(json.dumps(data))
                self.assertFalse(audit_capture(root/'batch',ids['sample_id'])['capture_evidence_pass'])
            finally:
                server.shutdown();server.server_close();thread.join()

    async def test_native_date_type_cannot_silently_use_fill_even_after_explicit_focus(self):
        await self.page.set_content('<label for="date">日期</label><input id="date" type="date" value="2026-10-22">')
        state=(await capture(self.page,'#date'))['state']
        with self.assertRaises(ValueError):prepare_action(state,{'action_type':'type','arguments':{'text':'2026-10-01'}})
        args,_=prepare_action(state,{'action_type':'click'})
        await execute(self.page,'click',args,{'settle_ms':0})
        state=(await capture(self.page,'#date'))['state']
        with self.assertRaisesRegex(ValueError,'不以 fill 替代'):
            prepare_action(state,{'action_type':'type','arguments':{'text':'2026-10-01'}})
        self.assertEqual(await self.page.locator('#date').input_value(),'2026-10-22')

    async def test_already_complete_task_does_not_pad_five_actions(self):
        from urllib.parse import quote
        from webcollect.collect import collect_one
        from webcollect.validate import validate_sample
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sample_id='S000001_sample_000001'
            operation={'action_type':'click','selector':'button','arguments':{},'goal':'不应执行额外动作','rationale':'仅用于回归测试','expected':'不应点击'}
            task={'initial_url':'data:text/html,'+quote('<meta charset="utf-8"><p id="done">已完成</p><button>测试</button>'),
                'initial_settle_ms':0,'operations':[operation]*5,'final_assertions':[{'selector':'#done','contains':'已完成'}],
                'final_result':'页面显示已完成','completion_judgement':'页面可见已完成','task_id':'already-done-fixture',
                'instruction':'本地夹具测试，不是交付数据','task_type':['数据查看'],'app_name':'本地夹具'}
            sample=root/'samples'/sample_id
            annotation=await collect_one(self.context,task,sample,root/'evidence'/sample_id,{'sample_id':sample_id})
            self.assertEqual([s['action']['action_type'] for s in annotation['steps']],['complete'])
            checked=validate_sample(sample,'integration')
            self.assertFalse(checked['structural_pass'])
            self.assertIn('effective_steps',{item['code'] for item in checked['issues']})

    async def test_overflow_clips_hidden_elements_and_text(self):
        await self.page.set_content('<div style="height:32px;overflow:hidden"><div style="height:100px;line-height:30px">可见文字<br>不应出现</div><button id="hidden">隐藏按钮</button></div>')
        state=(await capture(self.page,'#hidden'))['state']
        self.assertIsNone(state['target'])
        self.assertNotIn('不应出现',state['visible_text'])
        self.assertNotIn('隐藏按钮',state['visible_text'])
        self.assertIn('可见文字',state['visible_text'])

    async def test_root_scrollport_does_not_clip_to_scrolled_document_top(self):
        await self.page.set_content('<style>html{overflow-x:hidden}</style><div style="height:900px">顶部文字</div><button id="bottom">底部按钮</button>')
        await self.page.mouse.wheel(0,850)
        await self.page.wait_for_timeout(150)
        state=(await capture(self.page,'#bottom'))['state']
        self.assertGreater(state['scroll'][1],0)
        self.assertIsNotNone(state['target'])
        self.assertIn('底部按钮',state['visible_text'])

    async def test_layui_radio_state_comes_from_backing_native_input(self):
        await self.page.set_content('<input type="radio" checked title="整数" style="display:none"><div class="layui-form-radio layui-form-radioed" style="cursor:pointer">整数</div>')
        state=(await capture(self.page,'.layui-form-radio'))['state']
        element=next(e for e in state['elements'] if e['element_id']==state['target']['element_id'])
        self.assertEqual((element['element_type'],element['text'],element['state']),('radio','整数','checked'))

    async def test_language_text_does_not_duplicate_button_child_names(self):
        await self.page.set_content('<button><span>中文</span></button><p>test</p>')
        state=(await capture(self.page))['state']
        self.assertEqual(state['visible_text'].count('中文'),1)

    async def test_body_propagated_overflow_uses_viewport_clip(self):
        await self.page.set_content('<!doctype html><style>body{margin:0;height:100vh;overflow:auto}</style><div style="height:760px">顶部文字</div><button id="bottom">底部按钮</button><div style="height:800px"></div>')
        await self.page.evaluate('window.scrollTo(0,300)')
        state=(await capture(self.page,'#bottom'))['state']
        self.assertIsNotNone(state['target'])
        self.assertIn('底部按钮',state['visible_text'])
        self.assertTrue(state['target']['hit_valid'])

    async def test_body_own_overflow_still_clips_when_root_not_visible(self):
        await self.page.set_content('<!doctype html><style>html{overflow:auto}body{margin:0;height:100px;overflow:hidden}</style><div style="height:150px">顶部文字</div><button id="bottom">隐藏按钮</button>')
        state=(await capture(self.page,'#bottom'))['state']
        self.assertIsNone(state['target'])
        self.assertNotIn('隐藏按钮',state['visible_text'])

    async def test_checked_assertions_require_actual_visible_radio_state(self):
        await self.page.set_content('<label><input id="small" name="size" type="radio" checked>小</label><label><input id="large" name="size" type="radio">大</label>')
        await assert_state(self.page,[{'selector':'#small','checked':True},{'selector':'#large','checked':False}])
        with self.assertRaises(ValueError):await assert_state(self.page,[{'selector':'#large','checked':True}])
        state=(await capture(self.page,'#large'))['state']
        arguments,_=prepare_action(state,{'action_type':'click'})
        await execute(self.page,'click',arguments,{'settle_ms':0})
        await assert_state(self.page,[{'selector':'#large','checked':True},{'selector':'#small','checked':False}])

    async def test_expected_navigation_waits_for_delayed_document(self):
        async def delayed(route):
            await asyncio.sleep(0.8)
            await route.fulfill(content_type='text/html',body='<html><meta charset="utf-8"><body><h1 id="loaded">已到达新页面</h1></body></html>')
        await self.page.route('https://fixture.invalid/target',delayed)
        await self.page.set_content('<a id="next" href="https://fixture.invalid/target">进入下一页</a>')
        state=(await capture(self.page,'#next'))['state']
        arguments,_=prepare_action(state,{'action_type':'click'})
        await execute(self.page,'click',arguments,{'wait_navigation':True,'settle_ms':0})
        await assert_state(self.page,[{'selector':'#loaded','contains':'已到达新页面'}])

    async def test_visible_radio_label_reflects_associated_hidden_control(self):
        await self.page.set_content('<input id="large" type="radio" style="opacity:0"><label for="large"><span>大</span></label>')
        selector='label[for="large"]'
        state=(await capture(self.page,selector))['state']
        arguments,element=prepare_action(state,{'action_type':'click'})
        self.assertEqual(element['text'],'大')
        self.assertEqual(element['element_type'],'radio')
        self.assertEqual(element['state'],'unchecked')
        await execute(self.page,'click',arguments,{'settle_ms':0})
        await assert_state(self.page,[{'selector':selector,'checked':True}])
        state=(await capture(self.page,selector))['state']
        self.assertEqual(next(e for e in state['elements'] if e['element_id']==state['target']['element_id'])['state'],'checked')

    async def test_css_zero_clip_and_assistive_text_are_not_visible(self):
        await self.page.set_content('<p>可见文字</p><div id="clipped" style="position:absolute;clip:rect(1px,1px,1px,1px);overflow:hidden">不可见的辅助文本</div>')
        state=(await capture(self.page,'#clipped'))['state']
        self.assertIsNone(state['target'])
        self.assertNotIn('不可见的辅助文本',state['visible_text'])

    async def test_temporal_disabled_and_textarea_assertions(self):
        await self.page.set_content('<input id="locked" disabled><div id="clock">00:01:28</div><textarea id="output">转换结果</textarea>')
        results=await assert_state(self.page,[{'selector':'#locked','disabled':True},{'selector':'#clock','time_seconds':{'minimum':61,'maximum':89}},{'selector':'#output','contains':'转换结果'}])
        self.assertTrue(all(r['passed'] for r in results))
        await self.page.locator('#clock').evaluate("e=>e.textContent='00:00:75'")
        with self.assertRaises(ValueError):await assert_state(self.page,[{'selector':'#clock','time_seconds':{'minimum':61,'maximum':89}}])

    async def test_numeric_text_and_slider_semantics(self):
        await self.page.set_content('<div id="number">800</div><label for="slider">身高</label><input type="range" id="slider" value="50">')
        self.assertTrue((await assert_state(self.page,[{'selector':'#number','number':800}]))[0]['passed'])
        with self.assertRaises(ValueError):await assert_state(self.page,[{'selector':'#number','number':80}])
        state=(await capture(self.page,'#slider'))['state']
        element=next(e for e in state['elements'] if e['element_id']==state['target']['element_id'])
        self.assertEqual(element['element_type'],'slider')
        self.assertFalse(element['inputable'])

    async def test_target_occlusion_is_rejected(self):
        await self.page.evaluate("document.body.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;background:white;z-index:999\">遮挡</div>')")
        r=await capture(self.page,'#name')
        with self.assertRaises(ValueError):prepare_action(r['state'],{'action_type':'click'})

class CollectionRulesTests(unittest.TestCase):
    def test_ratio_not_presence_of_one_chinese_character(self):
        self.assertLess(chinese_ratio('中abcdefghijklmnop'),0.7)
        self.assertEqual(chinese_ratio('中文界面 123!'),1)
        self.assertLess(chinese_ratio('中θφασρά'),0.7)

    def test_shared_batch_allocation(self):
        with tempfile.TemporaryDirectory() as directory:
            registry=Path(directory)/'registry.sqlite3'
            a=allocate(registry,'https://example.invalid/a','工具','real')
            b=allocate(registry,'https://example.invalid/b','工具','real',batch_id=a['batch_id'])
            self.assertEqual(a['batch_id'],b['batch_id'])
            self.assertNotEqual(a['sample_id'],b['sample_id'])
            with self.assertRaises(ValueError):allocate(registry,'https://example.invalid/b','工具','integration',batch_id=a['batch_id'])

    def test_existing_batches_require_correct_registry(self):
        import json
        from webcollect.storage import verify_existing_registry
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);batch=root/'old';(batch/'samples').mkdir(parents=True)
            registry=root/'registry.sqlite3'
            with self.assertRaises(ValueError):verify_existing_registry(registry,root)
            ids=allocate(registry,'https://example.invalid/a','工具','real')
            (batch/'manifest.json').write_text(json.dumps({**ids,'sample_kind':'real','samples':[ids['sample_id']],
                'sites':[{'site_id':ids['site_id'],'uri':'https://example.invalid/a','site_category':'工具'}]}))
            verify_existing_registry(registry,root)
            other=root/'wrong.sqlite3'
            allocate(other,'https://example.invalid/wrong','工具','real')
            with self.assertRaises(ValueError):verify_existing_registry(other,root)

    def test_random_result_constraints(self):
        from webcollect.collect import check_numbers
        spec={'count':3,'minimum':10,'maximum_exclusive':20,'unique':True,'integer':True}
        self.assertTrue(check_numbers('10\n15\n19',spec))
        for text in ['10 10 15','10 15 20','10 15','10 15.5 19']:
            self.assertFalse(check_numbers(text,spec))

    def test_real_origin_rejects_local_fixtures_and_unplanned_redirects(self):
        from webcollect.collect import verify_public_url
        for url in ['file:///tmp/fixture.html','data:text/html,test','http://localhost/','http://127.0.0.1/','http://192.168.1.1/','https://example.invalid/','https://user:password@example.com/']:
            with self.assertRaises(ValueError):verify_public_url(url)
        self.assertEqual(verify_public_url('https://www.python.org/'), 'www.python.org')
        with self.assertRaises(ValueError):verify_public_url('https://other.example.com/',{'www.python.org'})

    def test_plan_rejects_zero_steps(self):
        with self.assertRaises(ValueError):validate_plan({'tasks':[]})
