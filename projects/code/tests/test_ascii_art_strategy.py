"""Controlled adapter scope tests, never production functionality proof."""
from copy import deepcopy
import tempfile
import unittest
from webcollect.ascii_art_strategy import ADAPTER_ID, URI, ASCII_ART_INVENTORY_JS, validate_observation

HTML='''<!doctype html><meta charset="utf-8"><style>
body{font:16px sans-serif}.layui-form-item{margin:10px}.layui-inline{display:inline-block;margin:10px}
.layui-form-label{display:block}select{display:none}textarea{width:600px;height:60px}input{width:140px}pre{white-space:pre}</style>
<div class="layui-form layui-form-pane">
<div class="layui-form-item"><label class="layui-form-label">文本内容</label><textarea id="inputContent">hello</textarea></div>
<div class="layui-form-item">SETTINGS</div>
<div class="layui-form-item"><div class="layui-inline"><label class="layui-form-label">行宽</label><input id="lineWidth" type="number" min="50" placeholder="可选"></div>
FORMAT</div><div class="layui-form-item"><button id="startGenerator">生成</button><button id="startCopy">复制</button><button id="startDownload">下载</button><button id="startClear">清空</button></div>
<div class="layui-form-item"><label class="layui-form-label">结果</label><pre id="transformResult"></pre></div></div>'''

def setting(sid,label,value,display):
    return f'''<div class="layui-inline"><label class="layui-form-label">{label}</label><select id="{sid}"><option value="{value}" selected>{display}</option></select><div class="layui-form-select"><input readonly value="{display}"></div></div>'''
HTML=HTML.replace('SETTINGS',''.join(setting(*x) for x in [('textFont','字体','Default','默认'),('charWidth','字符宽度','full','Full'),('charHeight','字符高度','full','Full')])).replace('FORMAT',setting('textFormat','格式化','no','无'))

class AsciiInventoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.p=await async_playwright().start();self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':1280,'height':720},service_workers='block')
        async def local_only(route):
            if route.request.is_navigation_request():await route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML)
            else:await route.abort()
        await self.context.route('**/*',local_only);self.page=await self.context.new_page();await self.page.goto(URI)

    async def asyncTearDown(self):
        await self.browser.close();await self.p.stop()

    async def test_observed_default_roles_produce_only_input_intent(self):
        before=await self.page.content();inventory=await self.page.evaluate(ASCII_ART_INVENTORY_JS)
        self.assertEqual(before,await self.page.content());self.assertEqual(inventory['widget_rejections'],[])
        page={'page_uri':URI,**inventory};widget=page['widgets'][0]
        self.assertEqual(validate_observation({'site_uri':URI},page,widget),[
            {'selector':'#inputContent','label':'文本内容','value':'HELLO'},
            {'selector':'#lineWidth','label':'行宽','value':'100'}])
        self.assertEqual(page['result_targets'][0]['raw_text'],'')

    async def test_same_markup_on_other_uri_is_out_of_scope(self):
        await self.page.goto(URI+'?different=1')
        self.assertEqual(await self.page.evaluate(ASCII_ART_INVENTORY_JS),{'widgets':[],'result_targets':[],'widget_rejections':[]})

    async def test_hidden_obstructed_changed_controls_and_settings_reject(self):
        for mutation in ["document.querySelector('#inputContent').style.opacity='0'",
            "document.querySelector('#lineWidth').style.marginTop='900px'",
            "document.querySelector('#lineWidth').min='10'",
            "document.querySelector('#inputContent').readOnly=true",
            "document.querySelector('#startGenerator').type='reset'",
            "document.querySelector('#startCopy').textContent='提交'",
            "document.querySelector('#textFont').disabled=true",
            "document.querySelector('#textFont').nextElementSibling.querySelector('input').value='未知字体'",
            "document.querySelector('#transformResult').style.whiteSpace='normal'",
            "document.querySelector('.layui-form').insertAdjacentHTML('beforeend','<input id=extra>')",
            "document.body.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;z-index:999;background:white\"></div>')"]:
            with self.subTest(mutation=mutation):
                await self.page.set_content(HTML);await self.page.evaluate(mutation)
                inventory=await self.page.evaluate(ASCII_ART_INVENTORY_JS)
                self.assertEqual(inventory['widgets'],[]);self.assertTrue(inventory['widget_rejections'])

    async def test_record_mutations_cannot_weaken_observation_contract(self):
        inventory=await self.page.evaluate(ASCII_ART_INVENTORY_JS)
        for change in ('scope','role','setting','duplicate','noop','result','nonempty'):
            with self.subTest(change=change):
                page={'page_uri':URI,**deepcopy(inventory)};widget=page['widgets'][0];cap={'site_uri':URI}
                if change=='scope':cap['site_uri']=URI+'/'
                elif change=='role':widget['fields'][1]['label']='字体'
                elif change=='setting':widget['settings'][1]['value']='fitted'
                elif change=='duplicate':widget['fields'][1]['selector']='#inputContent'
                elif change=='noop':widget['fields'][0]['value']='HELLO'
                elif change=='result':page['result_targets'][0]['preformatted']=False
                else:page['result_targets'][0]['raw_text']='existing output'
                with self.assertRaises(ValueError):validate_observation(cap,page,widget)


    async def test_compiler_uses_observed_necessary_scrolls_and_two_inputs(self):
        from webcollect.ascii_art_strategy import ascii_art_spec,compile_ascii_art
        from webcollect.task_generation import semantic_signature
        inventory=await self.page.evaluate(ASCII_ART_INVENTORY_JS)
        page={'page_uri':URI,'title':'在线生成ASCII艺术字',**inventory}
        page['widgets'][0].update(observed_scroll_y=200,viewport=[1280,720],result_document_rect=[20,836,1260,1118])
        cap={'capability_id':'CONTROLLED-ascii','version':'controlled-1','site_uri':URI,'site_category':'工具','status':'ready','capabilities':[page]}
        spec=ascii_art_spec(cap,page,page['widgets'][0],'test-1')
        task=compile_ascii_art(cap,spec)
        self.assertEqual([o['action_type'] for o in task['operations']],['scroll','click','hotkey','type','click','type','click','scroll'])
        self.assertEqual([o['execution']['distance'] for o in task['operations'] if o['action_type']=='scroll'],[200,268])
        self.assertNotIn('postconditions',task['operations'][-2])
        self.assertEqual(task['operations'][-1]['postconditions'],task['final_assertions'])
        self.assertFalse(task['content_preparation']);self.assertTrue(task['stop_when_final'])
        variant=deepcopy(task);variant['operations'][3]['arguments']['text']='OTHER'
        self.assertEqual(semantic_signature(task),semantic_signature(variant))
        for key in ('initial_scroll_y','result_scroll_y'):
            changed=deepcopy(spec);changed[key]+=1
            with self.assertRaisesRegex(ValueError,'specification changed'):compile_ascii_art(cap,changed)
        changed=deepcopy(spec);changed['completion']['contains']='ANY'
        with self.assertRaisesRegex(ValueError,'specification changed'):compile_ascii_art(cap,changed)

class AsciiOracleAndCompilerTests(unittest.TestCase):
    def glyphs(self):
        from webcollect.ascii_art_strategy import parse_ascii_figlet
        rows=['flf2a$ 2 1 8 0 1 0','controlled font fixture']
        for code in range(32,127):rows.extend([chr(code)+'$@',chr(code)+'$@@'])
        return parse_ascii_figlet('\n'.join(rows))

    def test_independent_full_layout_parses_endmarkers_and_hardblanks(self):
        from webcollect.ascii_art_strategy import render_full_ascii
        self.assertEqual(render_full_ascii(self.glyphs(),'HELO',100),'H E L O \nH E L O ')
        with self.assertRaises(ValueError):render_full_ascii(self.glyphs(),'HELLO',5)
        with self.assertRaises(ValueError):render_full_ascii(self.glyphs(),'汉',100)

    def test_parser_rejects_incomplete_bad_direction_and_unequal_rows(self):
        from webcollect.ascii_art_strategy import parse_ascii_figlet
        for data in ('not-a-font','flf2a$ 6 5 10 0 0 0\n@',
                     'flf2a$ 2 1 8 0 0 1\n'+('a@\na@@\n'*95),
                     'flf2a$ 2 1 8 0 0 0\n'+('a@\nab@@\n'*95)):
            with self.assertRaises((ValueError,IndexError)):parse_ascii_figlet(data)

    def test_exact_glyph_pattern_rejects_changed_letter_spacing_and_blank_output(self):
        from webcollect.ascii_art_strategy import expected_hello,verify_ascii_result_text
        value=expected_hello();self.assertTrue(verify_ascii_result_text(value))
        for bad in ('',value.replace('_','-',1),value.replace('  ',' ',1),value+' EXTRA',None):
            self.assertFalse(verify_ascii_result_text(bad))

    def test_frozen_font_excerpts_form_expected_five_letters(self):
        from webcollect.ascii_art_strategy import expected_hello,STANDARD_GLYPHS,render_full_ascii,FONT_SHA256
        self.assertEqual(set(STANDARD_GLYPHS),set('HELO'))
        self.assertEqual(len(FONT_SHA256),64)
        self.assertNotEqual(expected_hello(),render_full_ascii(STANDARD_GLYPHS,'HELOL'))
        self.assertEqual(len(expected_hello().split('\n')),6)


# Controlled layout preserves the original textarea-above-label and inline-number
# nesting, plus the measured 1280x720 document coordinates. It is not a live page.
COMPAT_HTML='''<!doctype html><meta charset="utf-8"><title>在线生成ASCII艺术字</title><style>
html,body{margin:0;width:1280px;min-height:1450px;font:14px Arial}*{box-sizing:border-box}
.layui-form-label{display:block;background:#fafafa;border:1px solid #ddd;height:38px;padding:10px 15px}
input,textarea{font:14px Arial;color:#000;border:1px solid #ddd;background:white;padding:9px 10px}
textarea{resize:none;width:1240px;height:250px}input{height:38px;width:190px}
.text-item{position:absolute;left:20px;top:321px;width:1240px}.text-item .layui-form-label{width:1240px}
.settings{position:absolute;left:20px;top:625px;height:38px;display:flex;gap:24px}
.layui-inline{display:flex}.layui-inline>.layui-form-label{width:110px}.layui-input-inline{width:190px}
select{display:none}.layui-form-select{width:190px}.width-item{position:absolute;left:20px;top:683px;display:flex;gap:24px}
.buttons{position:absolute;left:20px;top:741px}button{height:38px;padding:0 18px;margin-right:10px}
.result-item{position:absolute;left:20px;top:798px;width:1240px}.result-item>.layui-form-label{width:1240px}
pre{margin:0;white-space:pre;overflow:auto;font:13.3333px monospace;width:1240px;height:282px;padding:15px;border:1px solid #ddd}
</style><div style="position:absolute;left:20px;top:18px">Open API　文库　字符　转换　加密　网络　更多　登录</div><div style="position:absolute;left:20px;top:78px">首页　字符　工具</div><div style="position:absolute;left:980px;top:78px">6 评论　收藏　复制链接　分享</div><h1 style="position:absolute;left:20px;top:100px;margin:0;font-size:24px">在线生成ASCII艺术字</h1><div style="position:absolute;left:20px;top:153px">标签　ascii　生活工具</div><div class="layui-form layui-form-pane">
<div class="layui-form-item layui-form-text text-item"><label class="layui-form-label">文本内容</label><div class="layui-input-block"><textarea id="inputContent">hello</textarea></div></div>
<div class="layui-form-item settings">SETTINGS</div>
<div class="layui-form-item width-item"><div class="layui-inline"><label class="layui-form-label">行宽</label><div class="layui-input-inline"><input id="lineWidth" type="number" min="50" placeholder="可选"></div></div>FORMAT</div>
<div class="layui-form-item buttons"><button id="startGenerator">生成</button><button id="startCopy">复制</button><button id="startDownload">下载</button><button id="startClear">清空</button></div>
<div class="layui-form-item layui-form-text result-item"><label class="layui-form-label">结果</label><div class="layui-input-block"><pre id="transformResult"></pre></div></div></div>'''

def compat_setting(sid,label,value,display):
    return f'<div class="layui-inline"><label class="layui-form-label">{label}</label><div class="layui-input-inline"><select id="{sid}"><option value="{value}" selected>{display}</option></select><div class="layui-form-select"><input readonly value="{display}"></div></div></div>'
COMPAT_HTML=COMPAT_HTML.replace('SETTINGS',''.join(compat_setting(*x) for x in [('textFont','字体','Default','默认'),('charWidth','字符宽度','full','Full'),('charHeight','字符高度','full','Full')])).replace('FORMAT',compat_setting('textFormat','格式化','no','无'))

# Literal topics and document coordinates from the saved real original frame:
# supply-r01/probe/a48f1248be70c8c3fa0bd686d340aae8cae79a561b9cbdf8539519922e30831f/
# page-0/attempt-001/probe_000.png, SHA256 28aed5d1a23de11d3320555aa1b1e48aeffa48231e601a516d6346cc52e5254a.
# This explicit controlled calibration covers the observed topics-present state.
# The topics-absent state separately checks that letter ratios are diagnostic.
CALIBRATED_TOPIC_HTML=''.join(
    f'<span style="position:absolute;left:{x}px;top:{y}px;font:16px Arial;color:#1673ff">{text}</span>'
    for x,y,text in [(92,225,'深入探索'),(200,225,'定制平面设计'),(346,225,'学习编程课程'),
                    (492,225,'学习计算机课'),(638,225,'字体'),(93,262,'选购商业字体'),
                    (239,262,'预约艺术展览'),(385,262,'Font'),(466,262,'查找吉他谱'),(596,262,'咨询网络安全')])

class AsciiCollectorCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        from webcollect.ascii_art_strategy import expected_hello
        self.p=await async_playwright().start();self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':1280,'height':720},service_workers='block')
        self.fixture_html=COMPAT_HTML
        async def local_only(route):
            if route.request.is_navigation_request():await route.fulfill(status=200,content_type='text/html; charset=utf-8',body=self.fixture_html)
            else:await route.abort()
        await self.context.route('**/*',local_only);self.page=await self.context.new_page();await self.page.goto(URI)
        await self.page.evaluate("art=>document.querySelector('#startGenerator').onclick=()=>{document.querySelector('#transformResult').textContent=art}",expected_hello())

    async def asyncTearDown(self):
        await self.browser.close();await self.p.stop()

    async def make_task(self):
        from webcollect.ascii_art_strategy import ascii_art_spec,compile_ascii_art
        await self.page.mouse.move(1100,650);await self.page.mouse.wheel(0,80);await self.page.wait_for_timeout(250)
        inventory=await self.page.evaluate(ASCII_ART_INVENTORY_JS)
        self.assertEqual(inventory['widget_rejections'],[])
        page={'page_uri':URI,'title':'在线生成ASCII艺术字',**inventory}
        cap={'capability_id':'CONTROLLED-original-ascii-shape','version':'controlled-1','site_uri':URI,'site_category':'工具','status':'ready','capabilities':[page]}
        spec=ascii_art_spec(cap,page,page['widgets'][0],'controlled-test-1')
        task=compile_ascii_art(cap,spec)
        await self.page.mouse.wheel(0,-80);await self.page.wait_for_timeout(250)
        return task

    async def test_native_anchors_and_all_compiled_operations_pass_current_collector(self):
        from webcollect.browser import observe,prepare_action,execute
        from webcollect.collect import assert_state
        from webcollect.ascii_art_strategy import verify_ascii_result_text
        task=await self.make_task();anchors=[]
        with self.assertRaises(ValueError):await assert_state(self.page,task['final_assertions'])
        for op in task['operations']:
            state=await observe(self.page,op.get('selector'))
            arguments,_=prepare_action(state,op)
            if op.get('selector') in ('#inputContent','#lineWidth'):
                anchors.append((op['selector'],op['evidence']['target_label'],state['target']['visible_label_evidence']))
            await execute(self.page,op['action_type'],arguments,op.get('execution'))
            if op.get('postconditions'):await assert_state(self.page,op['postconditions'])
        self.assertEqual({anchor[1] for anchor in anchors},{'hello','可选'})
        self.assertTrue(all(any(row['text']==anchor[1] and row['kind'] in ('visible_native_value','visible_placeholder') for row in anchor[2]) for anchor in anchors))
        await assert_state(self.page,task['final_assertions'])
        self.assertTrue(verify_ascii_result_text(await self.page.locator('#transformResult').text_content()))
        self.assertEqual(await self.page.evaluate('scrollY'),task['operations'][0]['execution']['distance']+task['operations'][-1]['execution']['distance'])

    async def test_collect_one_keeps_low_letter_ratio_as_pending_language_diagnostic(self):
        import json
        from pathlib import Path
        from webcollect.collect import collect_one
        from webcollect.task_contract import PLAN_SCHEMA
        from webcollect.ascii_art_strategy import expected_hello
        task=await self.make_task();task.update(_plan_schema_version=PLAN_SCHEMA,initial_settle_ms=0)
        await self.context.add_init_script("document.addEventListener('DOMContentLoaded',()=>{document.querySelector('#startGenerator').onclick=()=>{document.querySelector('#transformResult').textContent="+json.dumps(expected_hello())+"}})")
        with tempfile.TemporaryDirectory() as root:
            sample=Path(root)/'CONTROLLED-no-topics';evidence=Path(root)/'evidence'
            await collect_one(self.context,task,sample,evidence,{'sample_id':'CONTROLLED-no-topics'})
            summary=json.loads((evidence/'capture_summary.json').read_text())
            self.assertLess(summary['minimum_chinese_character_ratio'],.70)
            self.assertTrue(summary['chinese_ratio_diagnostic_only'])
            self.assertEqual(summary['language_review'],'pending')
            self.assertFalse((evidence/'eligibility_failure.json').exists())
            self.assertTrue((sample/'annotation.json').exists())
            self.assertTrue((sample/'images/step_001.png').exists())
            self.assertEqual(json.loads((evidence/'task_contract.json').read_text())['semantic_status'],'REVIEW_REQUIRED')

    async def test_full_collect_one_saves_m4_frames_and_terminal_contract(self):
        import json
        from pathlib import Path
        from webcollect.collect import collect_one
        from webcollect.task_contract import PLAN_SCHEMA
        from webcollect.ascii_art_strategy import expected_hello
        self.fixture_html=COMPAT_HTML+CALIBRATED_TOPIC_HTML
        await self.page.goto(URI)
        task=await self.make_task();task.update(_plan_schema_version=PLAN_SCHEMA,initial_settle_ms=0)
        await self.context.add_init_script("document.addEventListener('DOMContentLoaded',()=>{document.querySelector('#startGenerator').onclick=()=>{document.querySelector('#transformResult').textContent="+json.dumps(expected_hello())+"}})")
        with tempfile.TemporaryDirectory() as root:
            sample=Path(root)/'CONTROLLED-ascii-only';evidence=Path(root)/'evidence'
            annotation=await collect_one(self.context,task,sample,evidence,{'sample_id':'CONTROLLED-ascii-only'})
            self.assertEqual(annotation['completion_status'],'success')
            self.assertEqual(len(annotation['steps']),9)
            self.assertEqual(annotation['steps'][-1]['action']['action_type'],'complete')
            contract=json.loads((evidence/'task_contract.json').read_text())
            self.assertEqual(contract['machine_status'],'PASS')
            self.assertEqual(contract['semantic_status'],'REVIEW_REQUIRED')
            self.assertEqual(len(contract['executed_operation_ids']),8)
            self.assertEqual(len(list((sample/'images').glob('*.png'))),9)
            self.assertEqual(len(list((sample/'ui_tree').glob('*.json'))),9)

    async def test_visible_stacked_label_is_supported_but_role_only_or_ambiguous_inline_rejects(self):
        from webcollect.browser import observe,prepare_action,execute
        task=await self.make_task();scroll=task['operations'][0]
        state=await observe(self.page);args,_=prepare_action(state,scroll);await execute(self.page,'scroll',args,scroll['execution'])
        state=await observe(self.page,'#inputContent')
        op={'action_type':'click','selector':'#inputContent','evidence':{'target_label':'文本内容'}}
        self.assertIn({'kind':'rendered_adjacent_input_group_label','text':'文本内容'},
                      state['target']['visible_label_evidence'])
        prepare_action(state,op)
        # The new structural proof supports this genuinely visible label.
        # A role/name alone, with that proof removed, remains insufficient.
        role_only=deepcopy(state);role_only['target']['visible_label_evidence']=[]
        with self.assertRaisesRegex(ValueError,'M4_TARGET_LABEL_UNREADABLE'):
            prepare_action(role_only,op)
        state=await observe(self.page,'#lineWidth')
        with self.assertRaisesRegex(ValueError,'M4_TARGET_LABEL_UNREADABLE'):
            prepare_action(state,{'action_type':'click','selector':'#lineWidth','evidence':{'target_label':'行宽'}})

    async def test_visible_result_rejects_clipping_wrong_symbols_and_collapsed_lines(self):
        from webcollect.browser import observe,prepare_action,execute
        from webcollect.collect import assert_state
        from webcollect.ascii_art_strategy import expected_hello,verify_ascii_result_text
        task=await self.make_task()
        for op in task['operations']:
            state=await observe(self.page,op.get('selector'));args,_=prepare_action(state,op)
            await execute(self.page,op['action_type'],args,op.get('execution'))
        await assert_state(self.page,task['final_assertions'])
        await self.page.locator('#transformResult').evaluate("e=>e.style.width='1400px'")
        with self.assertRaises(ValueError):await assert_state(self.page,task['final_assertions'])
        await self.page.locator('#transformResult').evaluate("e=>e.style.width='1240px'")
        await self.page.locator('#transformResult').evaluate("e=>e.textContent=e.textContent.replace('_','-')")
        with self.assertRaises(ValueError):await assert_state(self.page,task['final_assertions'])
        collapsed=' '.join(expected_hello().split())
        self.assertFalse(verify_ascii_result_text(collapsed))

if __name__=='__main__':unittest.main()
