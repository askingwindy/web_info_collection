"""Controlled full-frame label paint/surface checks, never external browsing."""
import hashlib
import json
import os
from pathlib import Path
import unittest
from playwright.async_api import async_playwright
from webcollect.browser import SNAPSHOT_JS, capture, prepare_action

STYLE='''<style>body{margin:20px;font:16px sans-serif;background:white;color:black}
.layui-form-item{display:flex;align-items:center}.layui-form-label{box-sizing:border-box;width:110px;height:40px;
padding:10px;border:1px solid #ddd;background:white}.layui-input-inline,.layui-input-block{width:190px;margin-left:-1px}
input{box-sizing:border-box;width:190px;height:40px;font:16px sans-serif}
.layui-form-text{display:block;width:600px}.layui-form-text .layui-form-label{display:block;width:600px;height:45px}
.layui-form-text .layui-input-block{width:600px;margin-left:0;margin-top:-1px}
.layui-upload-file{display:none}textarea{box-sizing:border-box;width:600px;height:120px}button{float:right}</style>'''


def markup(layout='inline', label_style='', extra='', for_target=False):
    if layout=='stacked':
        label='精度<button class="layui-btn" type="button"><i class="layui-icon">+</i>打开文件</button><input class="layui-upload-file" type="file">'
        group='layui-form-item layui-form-text';branch='layui-input-block';control='<textarea id="field"></textarea>'
    else:
        label='精度';group='layui-form-item';branch='layui-input-'+layout;control='<input id="field">'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'+STYLE+extra+f'<div class="{group}"><label id="caption" class="layui-form-label" style="{label_style}" '+('for="field"' if for_target else '')+f'>{label}</label><div class="{branch}">{control}</div></div></html>'


class FrameworkLabelSurfaces(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.p=await async_playwright().start();self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.page=await self.browser.new_page(viewport={'width':1280,'height':720},color_scheme='light')
        self.requests=[]
        await self.page.route('**/*',lambda route:route.abort())
        self.page.on('request',lambda request:self.requests.append(request.url))

    async def asyncTearDown(self):
        await self.browser.close();await self.p.stop()

    async def test_grouped_low_contrast_button_with_three_identical_captions(self):
        from webcollect.agent_observation import action_availability
        from webcollect.browser import execute
        groups = ''.join(f'<section><h3>{title}</h3><div><button>读</button>'
                         f'<button id="{key}"><b>写</b><small>写</small></button></div></section>'
                         for key,title in [('owner','所有者'),('group','组'),('others','其他用户')])
        await self.page.set_content('''<meta charset=utf-8><style>
            body{font:16px sans-serif;background:white}section{display:inline-block;padding:10px}
            button{width:70px;height:76px;color:#9ca3af;background:#f3f4f6}
            b,small{display:block}b{font-size:18px;font-weight:700}small{opacity:.8}
            </style>''' + groups + '<output>755</output><script>group.onclick=()=>document.querySelector("output").value="775"</script>')
        before = (await capture(self.page,'#group'))['state']
        target = before['target']
        label, = target['visible_label_evidence']
        self.assertEqual((label['kind'],label['group'],label['text']),('rendered_grouped_button','组','写'))
        element = next(e for e in before['elements'] if e['element_id']==target['element_id'])
        self.assertEqual(action_availability(before,element,{'tag':'button'},{},target,'click')['status'],'PROVEN')
        args,_ = prepare_action(before,{'action_type':'click','evidence':{'target_label':'写'}})
        await execute(self.page,'click',args,{})
        after = (await capture(self.page))['state']
        self.assertIn('755',before['visible_text'])
        self.assertIn('775',after['visible_text'])
        for mutation in ('group.disabled=true','group.style.color="#f3f4f6"',
                         'group.parentNode.append(group.cloneNode(true))',
                         'group.innerHTML=\'<b style="visibility:hidden">写</b>\'',
                         'group.parentNode.style.position="relative";group.insertAdjacentHTML("afterend",\'<i style="position:absolute;inset:0;background:white;pointer-events:none"></i>\')'):
            with self.subTest(mutation=mutation):
                original = await self.page.content()
                await self.page.evaluate(mutation)
                state = await self.page.evaluate(SNAPSHOT_JS,{'selector':'#group'})
                self.assertFalse((state.get('target') or {}).get('visible_label_evidence'))
                await self.page.set_content(original)
        self.assertEqual(self.requests,[])

    async def test_number_select_all_proves_selection_only_in_the_focused_field(self):
        from webcollect.react_protocol import atomic_effect
        from webcollect.browser import execute
        await self.page.set_content('<p>200</p><label>数量<input type=number value=200></label>')
        await self.page.locator('input').click()
        before = (await capture(self.page,'input'))['state']
        cid = before['target']['element_id']
        args = {'keys':['meta','a']}
        await execute(self.page,'hotkey',args,{})
        selected = (await capture(self.page,'input'))['state']
        self.assertEqual(atomic_effect(before,selected,'hotkey',args,cid)['fields'],['target.all_text_selected'])
        self.assertFalse(atomic_effect(selected,selected,'hotkey',args,cid)['verified'])
        await self.page.evaluate('''()=>{const s=getSelection(),r=document.createRange();
          r.selectNodeContents(document.querySelector('p'));s.removeAllRanges();s.addRange(r)}''')
        other = (await capture(self.page,'input'))['state']
        self.assertFalse(atomic_effect(before,other,'hotkey',args,cid)['verified'])
        self.assertFalse(next(v for v in other['values'] if v['element_id']==cid)['all_text_selected'])
        from types import SimpleNamespace
        from webcollect.agent_controller import compile_step
        from webcollect.react_session import ReactSession
        from webcollect.react_protocol import VERSION as native_protocol
        task = {'fragment':{'allowed_actions':['set_value'],'decision_protocol':native_protocol}}
        value = next(v for v in before['values'] if v['element_id']==cid)
        control = {'probe':before['target'],'value':value,'actions':{'set_value':{'status':'PROVEN'}}}
        rows = compile_step(task,[],{'action':'set_value','control_id':cid,'value':'350','goal':'修改数量','expected':'350'},
                            {'controls':{cid:control}})
        self.assertEqual([r['action'] for r in rows],['hotkey','type'])
        host = SimpleNamespace(task=task,current={'observation_id':'local'},used={'max_actions':1})
        with self.assertRaisesRegex(ValueError,'CURRENT_FULL_SELECTION'):
            ReactSession._build_operation(host,rows[-1],other,{})
        await self.page.locator('input').click()
        await execute(self.page,'hotkey',args,{})
        now = (await capture(self.page,'input'))['state']
        op = ReactSession._build_operation(host,rows[-1],now,{})
        native_args,_ = prepare_action(now,op)
        await execute(self.page,'type',native_args,{})
        self.assertEqual(await self.page.locator('input').input_value(),'350')

    async def test_unassociated_horizontal_form_labels_are_bound_within_one_visible_row(self):
        style = '<style>.row{display:flex;gap:12px}label,input{box-sizing:border-box;height:38px}label{width:150px}</style>'
        def row(n):
            return f'<div class="row"><label class="control-label">L{n}</label><div><input class="form-control" id="r{n}"></div></div>'
        html = style+'<form class="form-horizontal">'+row(1)+row(2)+'</form>'
        for selector, expected in [('#r1','L1'),('#r2','L2')]:
            await self.page.set_content(html)
            result = await capture(self.page,selector)
            target = result['state']['target']
            self.assertEqual(target['visible_label_evidence'],[{'kind':'rendered_adjacent_input_group_label','text':expected}])
            prepare_action(result['state'],{'action_type':'click','evidence':{'target_label':expected}})
        for change in ('document.querySelector("label").htmlFor="r2"',
                       'r1.after(document.createElement("input"))',
                       'document.querySelector("label").style.opacity="0"'):
            await self.page.set_content(html)
            await self.page.evaluate(change)
            state = await self.page.evaluate(SNAPSHOT_JS,{'selector':'#r1'})
            self.assertEqual(state['target']['visible_label_evidence'],[])

    async def check(self,html,accepted,case):
        await self.page.set_content(html);before=await self.page.content()
        await self.page.evaluate(SNAPSHOT_JS,{'selector':'#field'})
        self.assertEqual(await self.page.content(),before)
        observed=await capture(self.page,'#field');state=observed['state']
        self.assertEqual(self.requests,[])
        operation={'action_type':'click','arguments':{},'evidence':{'target_label':'精度'}}
        if accepted:
            self.assertEqual(state['target']['text'],'精度')
            prepare_action(state,operation)
        else:
            with self.assertRaisesRegex(ValueError,'M4_TARGET_LABEL_UNREADABLE'):
                prepare_action(state,operation)
        if parent:=os.environ.get('WEBCOLLECT_FRAMEWORK_SURFACE_ARTIFACTS'):
            directory=Path(parent)/self._testMethodName/case;directory.mkdir(parents=True,exist_ok=False)
            (directory/'fixture.html').write_text(before)
            (directory/'frame.png').write_bytes(observed['png'])
            (directory/'state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
            (directory/'proof.json').write_text(json.dumps({'capture':observed['capture'],'accepted':accepted,
                'network_requests':self.requests,'dom_unchanged':True,'controlled_fixture_only':True},ensure_ascii=False,indent=2))
        return state

    async def test_golden_block_inline_and_stacked_including_explicit_upload_for(self):
        for layout in ('block','inline','stacked'):
            await self.check(markup(layout),True,layout)
            await self.check(markup(layout,for_target=True),True,layout+'-explicit-for')

    async def test_white_on_white_and_actual_text_fill_are_checked(self):
        for layout in ('block','inline','stacked'):
            await self.check(markup(layout,'color:white;-webkit-text-fill-color:white'),False,layout+'-white')
            await self.check(markup(layout,'color:black;-webkit-text-fill-color:white'),False,layout+'-fill-white')
            await self.check(markup(layout,'color:white;-webkit-text-fill-color:black'),True,layout+'-fill-black')
            await self.check(markup(layout,'color:rgba(0,0,0,.01);-webkit-text-fill-color:rgba(0,0,0,.01)'),False,layout+'-faint')

    async def test_white_on_black_and_composited_uniform_background_are_supported(self):
        for layout in ('block','inline','stacked'):
            await self.check(markup(layout,'color:white;background:black'),True,layout+'-white-black')
            await self.check(markup(layout,'color:white;background:rgba(255,255,255,.25)',
                                   '<style>body{background:black}</style>'),True,layout+'-alpha-background')
            await self.check(markup(layout,'color:white;background:rgba(255,255,255,.95)',
                                   '<style>body{background:black}</style>'),False,layout+'-low-contrast-background')

    async def test_hidden_aria_only_wrong_for_and_complex_ancestor_stay_rejected(self):
        for layout in ('block','inline','stacked'):
            await self.check(markup(layout,'opacity:0'),False,layout+'-hidden')
            await self.check(markup(layout).replace('>精度',' aria-label="精度">'),False,layout+'-aria-only')
            await self.check(markup(layout,for_target=True).replace('for="field"','for="foreign"')+
                             '<input id="foreign" style="display:none">',False,layout+'-wrong-for')
            await self.check(markup(layout,extra='<style>body{opacity:.5}</style>'),False,layout+'-ancestor-opacity')
            await self.check(markup(layout,'background-image:linear-gradient(black,white)'),False,layout+'-complex-background')

    async def test_thin_foreign_strip_between_old_grid_probes_is_rejected(self):
        for layout in ('block','inline','stacked'):
            html=markup(layout);await self.page.set_content(html)
            box=await self.page.locator('#field').bounding_box()
            cover=f'<div style="position:fixed;left:{box["x"]+3}px;top:{box["y"]+2}px;width:2px;height:{box["height"]-4}px;background:red;z-index:99"></div>'
            await self.check(html+cover,False,layout)

    async def test_foreign_paint_on_the_shared_one_pixel_border_is_not_exempt(self):
        for layout in ('block','inline','stacked'):
            html=markup(layout);await self.page.set_content(html)
            a=await self.page.locator('#caption').bounding_box();b=await self.page.locator('#field').bounding_box()
            left=max(a['x'],b['x']);right=min(a['x']+a['width'],b['x']+b['width'])
            top=max(a['y'],b['y']);bottom=min(a['y']+a['height'],b['y']+b['height'])
            self.assertGreater(right-left,0);self.assertGreater(bottom-top,0)
            cover=f'<div style="position:fixed;left:{left}px;top:{top}px;width:{right-left}px;height:{bottom-top}px;background:red;z-index:99"></div>'
            await self.check(html+cover,False,layout)

    async def test_pointer_events_none_painted_label_and_field_covers_are_rejected(self):
        for layout in ('block','inline','stacked'):
            html=markup(layout);await self.page.set_content(html)
            for name,selector in (('caption','#caption'),('field','#field')):
                box=await self.page.locator(selector).bounding_box()
                cover=f'<div style="position:fixed;left:{box["x"]+5}px;top:{box["y"]+5}px;width:30px;height:20px;background:white;z-index:99;pointer-events:none"></div>'
                await self.check(html+cover,False,layout+'-'+name)

    async def test_transparent_foreign_backgrounds_behind_or_pointerless_do_not_block(self):
        for layout in ('block','inline','stacked'):
            for name,css in (('behind','z-index:-1'),('pointerless','z-index:99;pointer-events:none')):
                await self.check(markup(layout)+'<div style="position:fixed;inset:0;background:transparent;'+css+'"></div>',True,layout+'-'+name)

    async def test_ancestor_pointerless_generated_paint_rejects_but_empty_clearfix_is_supported(self):
        for layout in ('block','inline','stacked'):
            await self.check(markup(layout,extra='<style>.layui-form-item{position:relative}.layui-form-item::after{content:"";position:absolute;inset:0;background:white;z-index:99;pointer-events:none}</style>'),False,layout+'-painted-after')
            await self.check(markup(layout,extra='<style>.layui-form-item::after{content:" ";display:block;clear:both;height:0;visibility:hidden}</style>'),True,layout+'-clear-fix')

    async def test_explicit_associated_label_and_placeholder_cannot_bypass_occluded_field(self):
        for layout in ('block','inline','stacked'):
            html=markup(layout,for_target=True)
            if layout!='stacked':html=html.replace('<input id="field">','<input id="field" placeholder="精度">')
            await self.page.set_content(html);box=await self.page.locator('#field').bounding_box()
            cover=f'<div style="position:fixed;left:{box["x"]+100}px;top:{box["y"]+10}px;width:2px;height:20px;background:red;z-index:99"></div>'
            await self.check(html+cover,False,layout)

    async def generic(self,content,case):
        html='<!doctype html><meta charset="utf-8"><style>body{margin:20px;font:16px sans-serif;background:white;color:black}input,textarea,select{font:16px sans-serif}</style>'+content
        await self.page.set_content(html);before=await self.page.content()
        state=await self.page.evaluate(SNAPSHOT_JS,{'selector':'#field'})
        self.assertEqual(await self.page.content(),before);self.assertEqual(self.requests,[])
        if parent:=os.environ.get('WEBCOLLECT_FRAMEWORK_SURFACE_ARTIFACTS'):
            directory=Path(parent)/self._testMethodName/case;directory.mkdir(parents=True,exist_ok=False)
            (directory/'fixture.html').write_text(before)
            (directory/'frame.png').write_bytes(await self.page.screenshot())
            (directory/'state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
        return state

    async def test_plain_associated_label_and_body_prose_use_actual_text_fill(self):
        for name,css,visible in [('white','color:white',False),('actual-fill','color:black;-webkit-text-fill-color:white',False),
                                 ('white-black','color:white;background:black',True),('faint','color:rgba(0,0,0,.01)',False)]:
            state=await self.generic(f'<p style="{css}">普通中文正文</p><label for="field" style="{css}">精度</label><input id="field">',name)
            if visible:
                self.assertIn('普通中文正文',state['visible_text'])
                prepare_action(state,{'action_type':'click','arguments':{},'evidence':{'target_label':'精度'}})
            else:
                self.assertNotIn('普通中文正文',state['visible_text']);self.assertNotIn('精度',state['visible_text'])
                with self.assertRaisesRegex(ValueError,'M4_TARGET_LABEL_UNREADABLE'):
                    prepare_action(state,{'action_type':'click','arguments':{},'evidence':{'target_label':'精度'}})

    async def test_native_value_same_colour_cannot_supply_visible_chinese_or_label(self):
        for tag,control in [('input','<input id="field" value="中文输入值" style="{css}">'),
                            ('textarea','<textarea id="field" style="{css}">中文输入值</textarea>'),
                            ('select','<select id="field" style="{css}"><option>中文输入值</option></select>')]:
            for name,css,visible in [('white','color:white;background:white',False),
                                     ('actual-fill','color:black;-webkit-text-fill-color:white;background:white',False),
                                     ('white-black','color:white;background:black',True)]:
                state=await self.generic(control.format(css=css),tag+'-'+name)
                value=next(v for v in state['values'] if v['element_id']==state['target']['element_id'])
                self.assertEqual(value['value_visible'],visible)
                if visible:self.assertTrue(any(item['text']=='中文输入值' for item in state['target']['visible_label_evidence']))
                else:
                    self.assertNotIn('中文输入值',state['visible_text'])
                    self.assertFalse(any(item['text']=='中文输入值' for item in state['target']['visible_label_evidence']))

    async def test_unprovable_complex_background_does_not_supply_plain_text_or_native_value(self):
        state=await self.generic('<div style="background-image:linear-gradient(black,white)"><p>未证明背景的中文正文</p><label for="field">精度</label><input id="field" value="未证明原生值" style="background:transparent"></div>','gradient')
        self.assertNotIn('未证明背景的中文正文',state['visible_text'])
        self.assertNotIn('精度',state['visible_text']);self.assertNotIn('未证明原生值',state['visible_text'])
        self.assertFalse(next(v for v in state['values'] if v['element_id']==state['target']['element_id'])['value_visible'])


if __name__=='__main__':unittest.main()
