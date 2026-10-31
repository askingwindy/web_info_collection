"""Controlled browser regressions for saved-frame truth and unified pixel actions."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from playwright.async_api import async_playwright
from webcollect.browser import capture, prepare_action, execute, verify_execution_state
from webcollect.collect import assert_state, collect_one, completion_from_assertions, describe_change
from webcollect.production_quality import contract_identity


class ProducerContractBrowser(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime=await async_playwright().start()
        self.browser=await self.runtime.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':640,'height':480},device_scale_factor=1)
        self.page=await self.context.new_page()

    async def asyncTearDown(self):
        await self.browser.close();await self.runtime.stop()

    async def test_native_number_replacement_has_pixel_selection_and_proved_clear(self):
        await self.context.route('**/*',lambda route:route.abort())
        await self.page.set_content('''<!doctype html><meta charset="utf-8">
        <label for="longitude">经度：</label><input id="longitude" type="number" value="116.20321">''')
        frame=await capture(self.page,'#longitude');args,_=prepare_action(frame['state'],{'action_type':'click'})
        await execute(self.page,'click',args,{'settle_ms':0})
        focused=await capture(self.page,'#longitude')
        await execute(self.page,'hotkey',{'keys':['meta','a']},{'settle_ms':0})
        selected=await capture(self.page,'#longitude')
        value=next(v for v in selected['state']['values'] if v['focused'])
        self.assertIsNone(value['selection_start']);self.assertIsNone(value['selection_end'])
        self.assertNotEqual(selected['png'],focused['png'])
        await execute(self.page,'hotkey',{'keys':['backspace']},{'settle_ms':0})
        cleared=await capture(self.page,'#longitude')
        self.assertEqual(next(v for v in cleared['state']['values'] if v['focused'])['value'],'')
        await execute(self.page,'type',{'text':'121.47'},{'settle_ms':0})
        typed=await capture(self.page,'#longitude')
        self.assertEqual(next(v for v in typed['state']['values'] if v['focused'])['value'],'121.47')

    async def test_isolated_label_or_layui_prefix_needs_paint_and_unique_target(self):
        await self.context.route('**/*',lambda route:route.abort())
        css='<style>body{font:14px Arial}.pair{display:flex}label,.layui-input-prefix{display:block;padding:10px;color:#222}input{width:200px}</style>'
        for label in ['<label>电阻值</label>','<div class="layui-input-prefix">电阻值</div>']:
            await self.page.set_content(css+'<div class="pair">'+label+'<input id="target"></div>')
            state=(await capture(self.page,'#target'))['state']
            self.assertIn('电阻值',[r['text'] for r in state['target']['visible_label_evidence']])
        for html in ['<label>电阻值</label><input id="target"><input>',
                     '<span>电阻值</span><input id="target">',
                     '<label style="opacity:0">电阻值</label><input id="target">',
                     '<label for="another">电阻值</label><input id="target">']:
            await self.page.set_content(css+'<div class="pair">'+html+'</div>')
            state=(await capture(self.page,'#target'))['state']
            self.assertNotIn('电阻值',[r['text'] for r in state['target']['visible_label_evidence']])

    async def test_numeric_field_with_backed_readonly_unit_renderer_has_unique_outer_label(self):
        await self.context.route('**/*',lambda route:route.abort())
        css='<style>body{font:14px Arial}.layui-form-resItem{display:flex}label.layui-form-label{box-sizing:border-box;width:110px;flex:none;height:36px;padding:8px;color:#222}.layui-input-res{position:relative}.res-label{position:absolute;left:4px;color:#aaa;pointer-events:none}input{height:36px}select{display:none}</style>'
        html='''<div class="layui-form-resItem"><label class="layui-form-label">电阻值(R)</label>
          <div class="layui-input-res"><input id="target"><label class="res-label">电阻阻值</label></div>
          <select><option selected>Ω</option></select><div class="layui-form-select"><input readonly value="Ω"></div></div>'''
        await self.page.set_content(css+html)
        state=(await capture(self.page,'#target'))['state']
        self.assertIn('电阻值(R)',[r['text'] for r in state['target']['visible_label_evidence']],
            await self.page.evaluate("() => [...document.querySelectorAll('.layui-form-resItem *')].map(e=>({tag:e.tagName,cls:e.className,rect:e.getBoundingClientRect().toJSON(),display:getComputedStyle(e).display,value:e.value,text:e.children.length?'':e.textContent}))"))
        for change in [html.replace('readonly',''),html.replace('value="Ω"','value="kΩ"'),
                       html.replace('class="res-label"','class="res-label" style="background:black"'),
                       html.replace('<input id="target">','<input id="target" value="123">'),
                       html.replace('<select>','<select style="display:block">'),
                       html.replace('<input id="target">','<input id="target"><input>')]:
            await self.page.set_content(css+change)
            state=(await capture(self.page,'#target'))['state']
            self.assertNotIn('电阻值(R)',[r['text'] for r in state['target']['visible_label_evidence']])

    async def test_empty_rotated_decoration_does_not_block_unrotated_target(self):
        await self.context.route('**/*',lambda route:route.abort())
        await self.page.set_content('''<!doctype html><meta charset="utf-8">
        <div style="width:12px;height:12px;transform:rotate(15deg);background:green"></div>
        <label>查询条件<input id="query" style="" value="公开条件"></label>''')
        original=await self.page.content()
        state=(await capture(self.page,'#query'))['state']
        self.assertTrue(state['target']['hit_valid'])
        self.assertEqual(await self.page.content(),original)
        await self.page.set_content('<button id="rotated" style="transform:rotate(15deg)">旋转控件</button>')
        with self.assertRaisesRegex(Exception,'UNSUPPORTED_GEOMETRY'):await capture(self.page,'#rotated')

    async def test_scaled_overflow_clip_keeps_real_target_and_actual_click_pixels_at_both_dprs(self):
        for dpr in (1,2):
            context=await self.browser.new_context(viewport={'width':640,'height':480},device_scale_factor=dpr)
            try:
                page=await context.new_page()
                await page.set_content('''<!doctype html><meta charset="utf-8"><style>body{margin:0}
                #clip{position:absolute;left:40px;top:30px;width:150px;height:100px;border:5px solid;
                  overflow:hidden;transform-origin:0 0;transform:translate(30px,20px) scale(2)}
                #hit{position:absolute;left:90px;top:20px;width:100px;height:30px}</style>
                <div id="clip"><button id="hit" onclick="window.clickPoint=[event.clientX,event.clientY]">核对</button></div>''')
                observation=await capture(page,'#hit');state=observation['state']
                args,element=prepare_action(state,{'action_type':'click'})
                rect=await page.locator('#clip').bounding_box()
                self.assertEqual(element['bbox'][2],int(rect['x']+310))
                self.assertEqual(element['bbox'][2]-element['bbox'][0],120)
                self.assertEqual(Image.open(BytesIO(observation['png'])).size,(640,480))
                await verify_execution_state(page,state,'#hit')
                await execute(page,'click',args,{'settle_ms':0})
                self.assertEqual(await page.evaluate('window.clickPoint'),[args['x'],args['y']])
            finally:await context.close()

    async def test_complex_transform_and_iframe_task_dependency_are_explicitly_rejected(self):
        for html,message in [('<button style="transform:rotate(10deg)">旋转控件</button>','UNSUPPORTED_GEOMETRY'),
                             ('<button style="transform:skewX(10deg)">倾斜控件</button>','UNSUPPORTED_GEOMETRY')]:
            await self.page.set_content('<!doctype html><meta charset="utf-8">'+html)
            before=await self.page.content()
            with self.assertRaisesRegex(Exception,message):await capture(self.page)
            self.assertEqual(await self.page.content(),before)
        await self.page.set_content('<p>主页面文字</p><iframe style="display:none"></iframe>')
        self.assertIn('主页面文字',(await capture(self.page))['state']['visible_text'])

    async def test_non_task_frame_retains_real_opaque_geometry_without_invented_child_text(self):
        await self.page.set_content('''<p>主页面内容</p><iframe title="广告容器" style="width:200px;height:90px" srcdoc="<button>框内内容不冒充主文档真值</button>"></iframe><button id="outside">主页面按钮</button>''')
        state=(await capture(self.page,'#outside'))['state']
        frames=state['embedded_frames'];self.assertEqual(len(frames),1)
        container=next(e for e in state['elements'] if e['element_id']==frames[0]['element_id'])
        self.assertEqual((container['element_type'],container['native_role'],container['text']),('window','iframe',''))
        self.assertFalse(container['clickable']);self.assertEqual(frames[0]['subtree'],'opaque_unread')
        self.assertNotIn('框内内容',state['visible_text'])
        prepare_action(state,{'action_type':'click'})
        with self.assertRaisesRegex(Exception,'UNSUPPORTED_FRAME'):await capture(self.page,'iframe')
        with self.assertRaisesRegex(Exception,'UNSUPPORTED_FRAME'):await capture(self.page,assertions=[{'selector':'iframe','contains':'框内内容'}])
        box=container['bbox']
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_FRAME'):
            prepare_action(state,{'action_type':'scroll','arguments':{'x':box[0]+1,'y':box[1]+1,'direction':'down'}})

    async def test_axis_aligned_half_turn_and_reflected_overflow_keep_true_clipping(self):
        for transform in ('rotate(180deg)','scale(-2,2)','rotate(90deg)','rotate(-90deg) scale(2)'):
            await self.page.set_content('''<!doctype html><meta charset="utf-8"><style>body{margin:0}
            #clip{position:absolute;left:200px;top:140px;width:150px;height:100px;border:5px solid;overflow:hidden;transform:'''+transform+'''}
            #hit{position:absolute;left:90px;top:20px;width:100px;height:30px}</style>
            <div id="clip"><button id="hit" onclick="window.realClick=[event.clientX,event.clientY]">核对</button></div>''')
            state=(await capture(self.page,'#hit'))['state'];args,element=prepare_action(state,{'action_type':'click'})
            clip=await self.page.locator('#clip').bounding_box()
            self.assertGreaterEqual(element['bbox'][0],int(clip['x']))
            self.assertLessEqual(element['bbox'][2],int(clip['x']+clip['width']))
            await execute(self.page,'click',args,{'settle_ms':0})
            self.assertEqual(await self.page.evaluate('window.realClick'),[args['x'],args['y']])

    async def test_individual_nonuniform_scale_and_quarter_turn_clip_on_actual_pixel_axes(self):
        await self.page.set_content('''<!doctype html><meta charset="utf-8"><style>body{margin:0}
        #clip{position:absolute;left:360px;top:50px;width:150px;height:100px;
          border:5px solid;overflow:hidden;transform-origin:0 0;scale:2 1;
          transform:rotate(90deg)}
        #hit{position:absolute;left:90px;top:20px;width:100px;height:30px}</style>
        <div id="clip"><button id="hit" onclick="window.realClick=[event.clientX,event.clientY]">核对</button></div>''')
        state=(await capture(self.page,'#hit'))['state'];args,element=prepare_action(state,{'action_type':'click'})
        # Local X maps to viewport Y, whose scale is one, not two.
        clip=await self.page.locator('#clip').bounding_box()
        self.assertEqual(element['bbox'][3],int(clip['y']+155))
        self.assertEqual(element['bbox'][3]-element['bbox'][1],60)
        await execute(self.page,'click',args,{'settle_ms':0})
        self.assertEqual(await self.page.evaluate('window.realClick'),[args['x'],args['y']])

    async def test_any_changed_target_truth_or_surrounding_state_blocks_dispatch(self):
        for mutation in ["n.disabled=true", "n.textContent='其他按钮'",
                         "n.style.left='90px';n.style.width='120px'", "document.querySelector('p').textContent='页面已更新'"]:
            await self.page.set_content('<p>当前页面</p><button id="hit" style="position:absolute;left:100px;top:100px;width:100px;height:40px">核对</button>')
            state=(await capture(self.page,'#hit'))['state']
            await self.page.locator('#hit').evaluate('(n)=>{'+mutation+'}')
            with self.assertRaisesRegex(ValueError,'陈旧坐标'):await verify_execution_state(self.page,state,'#hit')

    async def test_saved_terminal_assertions_and_live_state_cannot_diverge_silently(self):
        conditions=[{'selector':'#result','contains':'核对完成'},{'visible_text':'核对完成'}]
        await self.page.set_content('<h1>结果页面</h1><p id="result">核对完成</p>')
        frame=await capture(self.page,assertions=conditions)
        await self.page.locator('#result').evaluate("n=>n.textContent='任务尚未完成'")
        # The saved frame retains its own facts; it must not borrow the new page.
        self.assertTrue(all(r['passed'] for r in await assert_state(self.page,conditions,captured_state=frame['state'])))
        with self.assertRaisesRegex(ValueError,'陈旧坐标'):
            await verify_execution_state(self.page,frame['state'],assertions=conditions)
        with self.assertRaises(ValueError):await assert_state(self.page,conditions)

    async def test_date_type_is_rejected_without_silent_fill_or_value_change(self):
        await self.page.set_content('<label for="day">日期</label><input type="date" id="day" value="2026-10-24">')
        await self.page.locator('#day').focus()
        state=(await capture(self.page,'#day'))['state']
        with self.assertRaisesRegex(ValueError,'不以 fill 替代'):
            prepare_action(state,{'action_type':'type','arguments':{'text':'2026-10-25'}})
        with self.assertRaisesRegex(ValueError,'不以 fill 替代'):
            await execute(self.page,'type',{'text':'2026-10-25'},{'settle_ms':0})
        self.assertEqual(await self.page.locator('#day').input_value(),'2026-10-24')

    async def test_select_assertion_uses_machine_value_but_completion_names_visible_label(self):
        await self.page.set_content('<label for="choice">文字大小</label><select id="choice"><option value="internal-size-lg" selected>大号</option></select>')
        conditions=[{'selector':'#choice','value':'internal-size-lg'}]
        frame=await capture(self.page,assertions=conditions)
        assertions=await assert_state(self.page,conditions,captured_state=frame['state'])
        self.assertEqual(assertions[0]['actual'],'internal-size-lg')
        self.assertEqual(assertions[0]['display_actual'],'大号')
        description=completion_from_assertions(assertions)
        self.assertIn('大号',description);self.assertNotIn('internal-size-lg',description)
        await verify_execution_state(self.page,frame['state'],assertions=conditions)

    async def test_number_list_assertion_reads_visible_input_value_and_rejects_wrong_values(self):
        await self.page.set_content('<label for="numbers">输出结果</label><textarea id="numbers">8972,7799,3116</textarea>')
        conditions=[{'selector':'#numbers','numbers':{'count':3,'minimum':1000,'maximum_exclusive':10000,'integer':True,'unique':True}}]
        frame=await capture(self.page,assertions=conditions)
        checked=await assert_state(self.page,conditions,captured_state=frame['state'])
        self.assertEqual(checked[0]['actual'],'8972,7799,3116')
        await self.page.locator('#numbers').evaluate("e=>e.value='8972,8972,3116'")
        with self.assertRaises(ValueError):await assert_state(self.page,conditions)

    async def test_clipped_or_internally_overflowing_native_value_is_not_visible_evidence(self):
        for style,value in [('position:absolute;top:-20px;height:60px','编号号，批次号'),
                            ('height:30px;width:150px','第1行\n第2行\n第3行\n第4行')]:
            await self.page.set_content('<!doctype html><meta charset="utf-8"><label for="out">结果</label><textarea id="out" style="'+style+'"></textarea><button id="run" style="position:absolute;top:120px">替换</button>')
            before=(await capture(self.page,'#run'))['state']
            await self.page.locator('#out').evaluate('(e,v)=>e.value=v',value)
            conditions=[{'selector':'#out','value':value}]
            after=(await capture(self.page,assertions=conditions))['state']
            self.assertFalse(next(v for v in after['values'] if v['value']==value)['value_visible'])
            self.assertNotIn(value,after['visible_text'])
            with self.assertRaises(ValueError):await assert_state(self.page,conditions,captured_state=after)
            description=describe_change(before,after,{'action_type':'click'},next(e for e in before['elements'] if e['text']=='替换'))
            self.assertNotIn(value,description)

    async def test_button_contains_uses_visible_label_instead_of_submit_value(self):
        await self.page.set_content('<!doctype html><meta charset="utf-8"><button id="resume" value="internal-submit-value">继续</button>')
        conditions=[{'selector':'#resume','contains':'继续'}]
        frame=await capture(self.page,assertions=conditions)
        result=await assert_state(self.page,conditions,captured_state=frame['state'])
        self.assertEqual(result[0]['actual'],'继续')
        self.assertIsNone(frame['state']['assertion_targets'][0]['value'])

    async def test_complete_prose_uses_visible_whole_sentences_and_balanced_quotes_only(self):
        await self.page.set_content('''<!doctype html><meta charset="utf-8"><style>body{margin:0}
        p{position:absolute;top:-16px;font-size:16px;line-height:20px;margin:0;width:620px}</style>
        <p>这一句在视口上方不能用来描述当前看到的内容。<br>完整清晰的后续中文句子能独立解释滚动结果。<br>“第一句引语完整。第二句引语继续后闭合。”</p>''')
        frame=await capture(self.page);block=frame['state']['text_blocks'][0]
        self.assertFalse(block['starts_visible'])
        self.assertNotIn('这一句在视口上方不能用来描述当前看到的内容。',block['complete_sentences'])
        self.assertIn('完整清晰的后续中文句子能独立解释滚动结果。',block['complete_sentences'])
        self.assertIn('“第一句引语完整。第二句引语继续后闭合。”',block['complete_sentences'])
        self.assertNotIn('“第一句引语完整。',block['complete_sentences'])

    async def test_collect_rechecks_final_assertion_in_saved_frame_and_names_actual_final_page(self):
        url='https://producer-contract.invalid/task'
        prose='当前页面展示中文结果，请核对任务执行后的真实页面状态。'*8
        html='<meta charset="utf-8"><title>不应引用的标签页标题</title><h1>受控结果页面</h1><p>'+prose+'</p><button id="finish" onclick="document.querySelector(\'#result\').textContent=\'核对完成\'">执行核对</button><p id="result">等待核对</p>'
        await self.context.route(url,lambda route:route.fulfill(content_type='text/html; charset=utf-8',body=html))
        task={'task_id':'controlled','initial_url':url,'site_uri':url,'app_name':'受控页面','instruction':'点击核对并确认结果',
              'task_type':['数据查看'],'initial_settle_ms':0,'stop_when_final':False,'content_preparation':{'mode':'off'},
              'operations':[{'action_type':'click','selector':'#finish','goal':'执行核对','rationale':'当前可见核对按钮',
                             'expected':'显示核对完成','execution':{'settle_ms':0}}],
              'final_assertions':[{'visible_text':'核对完成'},{'selector':'#result','contains':'核对完成'}],
              'final_result':'计划完成','completion_judgement':'计划核对'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            annotation=await collect_one(self.context,task,root/'good',root/'good-evidence',{'sample_id':'S000001_sample_000001'})
            last=annotation['steps'][-1]
            self.assertIn('受控结果页面',last['user_goal']);self.assertIn('核对完成',last['user_goal'])
            self.assertNotIn('不应引用的标签页标题',last['user_goal'])
            import json
            raw=json.loads((root/'good-evidence/step_002.json').read_text())
            self.assertEqual(raw['final_assertions_binding']['image_path'],last['image_path'])
            self.assertEqual(raw['final_assertions_binding']['screenshot_sha256'],raw['capture']['screenshot_sha256'])
            self.assertTrue(raw['state_preflight']['matched'])
            async def changed_before_capture(page,*args,**kwargs):
                if kwargs.get('assertions'):
                    await page.locator('#result').evaluate("n=>n.textContent='任务尚未完成'")
                return await capture(page,*args,**kwargs)
            with patch('webcollect.collect.capture',changed_before_capture):
                with self.assertRaisesRegex(ValueError,'目标文字未在实际视口'):
                    await collect_one(self.context,task,root/'bad',root/'bad-evidence',{'sample_id':'S000001_sample_000002'})
            self.assertFalse((root/'bad/annotation.json').exists())


class ProducerContractIdentity(unittest.TestCase):
    def test_terminal_numeric_facts_are_concrete(self):
        description=completion_from_assertions([{'expected':{'number':800},'actual':'800','passed':True},
            {'expected':{'time_seconds':{'minimum':60,'maximum':90}},'actual':'00:01:20','passed':True},
            {'expected':{'checked':True},'actual':True,'passed':True,'target_text':'大号字体'}])
        for text in ('800','00:01:20','大号字体'):self.assertIn(text,description)

    def test_contract_hashes_real_current_authority_paths(self):
        repo=Path(__file__).resolve().parents[3]
        identity=contract_identity(repo)
        self.assertIn('request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md',identity['authority_files_sha256'])
        self.assertNotIn('request/需求书-Web浏览器自动化操作轨迹数据集.md',identity['authority_files_sha256'])
