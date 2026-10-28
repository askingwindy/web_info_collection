"""Visible original framework labels, with no accessible-name shortcut."""
import unittest
from playwright.async_api import async_playwright
from webcollect.browser import capture,prepare_action

STYLE='''<style>body{margin:20px;font:16px sans-serif}.layui-form-item{display:flex;align-items:center}
.layui-form-label{box-sizing:border-box;width:110px;padding:10px;border:1px solid #ddd}
.layui-input-inline{width:190px;margin-left:-1px}input{box-sizing:border-box;width:190px;height:40px;font:16px sans-serif}
.layui-form-mid{margin-left:10px}</style>'''
ROW='''<div class="layui-form-item"><label class="layui-form-label">精度</label>
<div class="layui-input-inline"><input type="number" id="precision"></div>
<div class="layui-form-mid layui-word-aux">计算结果小数点后保留位数，0至15</div></div>'''

class InlineFrameworkLabels(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.p=await async_playwright().start()
        self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.page=await self.browser.new_page(viewport={'width':1280,'height':720})

    async def asyncTearDown(self):
        await self.browser.close();await self.p.stop()

    async def check(self,markup,accepted):
        await self.page.set_content('<!doctype html><meta charset="utf-8">'+STYLE+markup)
        f=await capture(self.page,'#precision')
        op={'action_type':'click','arguments':{},'evidence':{'target_label':'精度'}}
        if accepted:
            args,proof=prepare_action(f['state'],op)
            self.assertTrue(f['state']['target']['visible_label_evidence'])
            self.assertIn('精度',[x['text'] for x in f['state']['target']['visible_label_evidence']])
        else:
            with self.assertRaises(ValueError):prepare_action(f['state'],op)

    async def test_actual_inline_shape_with_plain_hint(self):
        await self.check(ROW,True)
        await self.check(ROW.replace('<div class="layui-form-mid layui-word-aux">计算结果小数点后保留位数，0至15</div>',''),True)

    async def test_unrelated_hint_second_control_or_ambiguous_label_reject(self):
        for altered in (ROW.replace('layui-form-mid layui-word-aux','unrelated-prose'),
                        ROW.replace('计算结果小数点后保留位数，0至15','<input aria-label="另一输入">'),
                        ROW.replace('</label>','</label><label class="layui-form-label">另一名称</label>'),
                        ROW.replace('layui-form-mid layui-word-aux"','layui-form-mid layui-word-aux" role="button"')):
            await self.check(altered,False)

    async def test_hidden_accessible_only_or_obscured_label_reject(self):
        for altered in (ROW.replace('class="layui-form-label"','class="layui-form-label" style="opacity:0"'),
                        ROW.replace('>精度</label>',' aria-label="精度"></label>'),
                        ROW+'<div style="position:fixed;left:25px;top:25px;width:90px;height:30px;background:white;z-index:999"></div>'):
            await self.check(altered,False)

    async def test_stacked_textarea_uses_only_original_label_not_file_button(self):
        markup='''<style>.layui-form-text{display:block;width:600px}.layui-form-text .layui-form-label{display:block;width:600px;height:45px}
        .layui-form-text .layui-input-block{width:600px;margin-top:-1px}.layui-upload-file{display:none}textarea{width:598px;height:120px}
        button{float:right}</style><div class="layui-form-item layui-form-text">
        <label class="layui-form-label">输入坐标<button type="button" class="layui-btn"><i class="layui-icon">+</i>打开文件</button>
        <input class="layui-upload-file" type="file"></label><div class="layui-input-block"><textarea id="coords">1,2</textarea></div></div>'''
        await self.page.set_content('<!doctype html><meta charset="utf-8">'+STYLE+markup)
        f=await capture(self.page,'#coords')
        self.assertEqual(f['state']['target']['text'],'输入坐标')
        self.assertIn({'kind':'rendered_adjacent_input_group_label','text':'输入坐标'},f['state']['target']['visible_label_evidence'])
        prepare_action(f['state'],{'action_type':'click','arguments':{},'evidence':{'target_label':'输入坐标'}})
        for changed in (markup.replace('打开文件</button>','打开文件</button><button type="button" class="layui-btn">另一个</button>'),
                        markup.replace('.layui-upload-file{display:none}','.layui-upload-file{display:block}'),
                        markup.replace('margin-top:-1px','margin-top:-3px'),
                        markup.replace('height:45px','height:45px;opacity:0')):
            await self.page.set_content('<!doctype html><meta charset="utf-8">'+STYLE+changed)
            bad=await capture(self.page,'#coords')
            with self.assertRaises(ValueError):
                prepare_action(bad['state'],{'action_type':'click','arguments':{},'evidence':{'target_label':'输入坐标'}})

if __name__=='__main__':unittest.main()
