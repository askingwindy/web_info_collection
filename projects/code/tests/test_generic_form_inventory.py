"""Local DOM inventory tests; no website access, model or production capture."""
import json
from pathlib import Path
import tempfile
import unittest

from playwright.async_api import async_playwright

from site_planner.pipeline import INVENTORY_JS, inventory_support
from webcollect.task_generation import compile_form


URI = 'https://example.org/controlled-form'
STYLE = '''<style>body{font:20px sans-serif;margin:24px}label{display:block;margin:8px}
input,textarea,button{font:20px sans-serif;padding:7px}output{display:block;padding:8px}</style>'''


def document(content):
    return '<!doctype html><meta charset="utf-8"><title>受控矩形工具</title>' + STYLE + content


def fields(ids=('length', 'width')):
    return (f'<label for="{ids[0]}">长度（厘米）</label><input id="{ids[0]}" type="number">'
            f'<label for="{ids[1]}">宽度（厘米）</label><input id="{ids[1]}" type="number">'
            '<button id="calculate" type="button" onclick="document.querySelector(\'output\').textContent=\'矩形面积为\'+Number(document.querySelector(\'#length\').value)*Number(document.querySelector(\'#width\').value)+\'平方厘米\'">计算面积</button>')


class GenericFormInventoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(channel='chrome', headless=True)
        self.page = await self.browser.new_page(viewport={'width': 1280, 'height': 720})
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()
        self.temporary.cleanup()

    async def inventory(self, body):
        await self.page.set_content(document(body))
        value = await self.page.evaluate(INVENTORY_JS)
        value.update(page_uri=URI, elements=[])
        return value

    def compile(self, inventory, label='矩形面积计算'):
        from test_s0_task_generation import capability
        cap = capability(self.root / 'capability', uri=URI, kind='rectangle')
        cap['capabilities'] = [inventory]
        form = next(f for f in inventory['forms'] if f['label'] == label)
        editable = [f for f in form['fields'] if f['tag'] == 'input' and f.get('editable', True)]
        submit = next(f for f in form['fields'] if f['tag'] == 'button')
        spec = {'page_uri': URI, 'form_label': label,
                'goal': '在「受控矩形工具」中填写长度和宽度，计算并核对矩形面积。',
                'inputs': [{'selector': f['selector'], 'label': f['label'], 'value': v}
                           for f, v in zip(editable, ('6', '7'))],
                'submit': {'selector': submit['selector'], 'label': submit['label']},
                'completion': {'selector': inventory['result_targets'][0]['selector'],
                               'contains': '矩形面积为42平方厘米'}}
        return compile_form(cap, spec)

    async def test_role_form_is_observed_compiled_and_original_controls_execute(self):
        value = await self.inventory('<div role="form" aria-label="矩形面积计算">' + fields()
                                     + '</div><output>请填写参数后计算结果</output>')
        self.assertEqual(len(value['forms']), 1)
        task = self.compile(value)
        self.assertEqual([op['action_type'] for op in task['operations']], ['click', 'type', 'click', 'type', 'click'])
        for op in task['operations']:
            target = self.page.locator(op['selector'])
            if op['action_type'] == 'click':
                await target.click()
            else:
                await self.page.keyboard.insert_text(op['arguments']['text'])
        self.assertEqual(await self.page.locator('output').inner_text(), '矩形面积为42平方厘米')

    async def test_framework_div_form_uses_original_structural_labels(self):
        value = await self.inventory('''<div class="layui-form" aria-label="矩形面积计算">
          <div class="layui-form-item"><label class="layui-form-label">长度（厘米）</label><div class="layui-input-block"><input id="length" type="number"></div></div>
          <div class="layui-form-item"><label class="layui-form-label">宽度（厘米）</label><div class="layui-input-block"><input id="width" type="number"></div></div>
          <button id="calculate" type="button">计算面积</button></div><output>等待计算</output>''')
        self.assertEqual([f['label'] for f in value['forms'][0]['fields']], ['长度（厘米）', '宽度（厘米）', '计算面积'])
        self.assertEqual(len(self.compile(value)['operations']), 5)
        self.assertEqual(len(inventory_support(URI, [value])[1]), 1)

    async def test_framework_native_nesting_does_not_duplicate_fields(self):
        value = await self.inventory('<div class="layui-form"><form aria-label="矩形面积计算">'
                                     + fields() + '</form></div><output>等待计算</output>')
        self.assertEqual(len(value['forms']), 1)
        self.assertEqual(len(value['forms'][0]['fields']), 3)

    async def test_duplicate_names_and_ids_receive_unique_original_dom_paths(self):
        value = await self.inventory('''<div role="form" aria-label="矩形面积计算">
          <label>长度（厘米）<input id="duplicate" name="same" type="number"></label>
          <label>宽度（厘米）<input id="duplicate" name="same" type="number"></label>
          <button type="button">计算面积</button></div><output>等待计算</output>''')
        fields_ = value['forms'][0]['fields']
        selectors = [f['selector'] for f in fields_]
        self.assertEqual(len(selectors), len(set(selectors)))
        for selector in selectors:
            self.assertEqual(await self.page.locator(selector).count(), 1)
        self.assertEqual(len(self.compile(value)['operations']), 5)

    async def test_duplicate_form_labels_remain_ambiguous_instead_of_invented_names(self):
        value = await self.inventory('<div role="form" aria-label="相同名称">' + fields() + '</div>'
                                     '<div role="form" aria-label="相同名称">' + fields(('x', 'y')) + '</div>'
                                     '<output>等待计算</output>')
        self.assertEqual([f['label'] for f in value['forms']], ['相同名称', '相同名称'])
        with self.assertRaisesRegex(ValueError, 'exactly one observed form'):
            self.compile(value, label='相同名称')

    async def test_hidden_forms_controls_and_labels_are_not_promoted(self):
        value = await self.inventory('''<div role="form" style="display:none">''' + fields() + '''</div>
          <div class="layui-form" aria-label="可见表单"><label for="a" style="display:none">隐藏名称</label><input id="a" type="text">
          <label for="b">另一输入</label><input id="b" type="text" style="opacity:0"><button type="button">计算</button></div>
          <output style="display:none">隐藏结果</output>''')
        self.assertEqual(len(value['forms']), 1)
        by_selector = {f['selector']: f for f in value['forms'][0]['fields']}
        self.assertEqual(by_selector['#a']['label'], '')
        self.assertFalse(by_selector['#b']['visible'])
        self.assertEqual(inventory_support(URI, [value])[1], [])
        self.assertEqual(value['result_targets'], [])

    async def test_iframe_fields_are_not_lifted_into_top_document(self):
        nested = '<div role="form" aria-label="框内表单">' + fields() + '</div><output>框内结果</output>'
        value = await self.inventory('<iframe id="foreign"></iframe><div role="form" aria-label="顶层表单">'
                                     '<label for="one">唯一输入</label><input id="one"><button>查询</button></div>')
        await self.page.locator('iframe').evaluate('(node,html)=>node.srcdoc=html', document(nested))
        await self.page.wait_for_timeout(30)
        value = await self.page.evaluate(INVENTORY_JS)
        self.assertEqual(len(value['forms']), 1)
        self.assertEqual(value['forms'][0]['label'], '顶层表单')
        self.assertEqual(value['result_targets'], [])

    async def test_unlabelled_and_readonly_fields_do_not_claim_two_editable_inputs(self):
        value = await self.inventory('''<div role="form" aria-label="不足两输入">
          <label for="a">输入</label><input id="a"><label for="b">输出结果</label><textarea id="b" readonly></textarea>
          <button type="button">处理</button></div>''')
        self.assertEqual(inventory_support(URI, [value])[1], [])
        self.assertEqual(value['result_targets'][0]['selector'], '#b')
        output = next(f for f in value['forms'][0]['fields'] if f['selector'] == '#b')
        self.assertFalse(output['editable'])
        self.assertTrue(output['read_only'])

    async def test_aria_only_name_and_filled_placeholder_are_not_visible_labels(self):
        value = await self.inventory('''<div role="form"><input id="a" aria-label="隐藏语义名">
          <input id="b" placeholder="已不显示的占位文字" value="已有内容"><button>查询</button></div>''')
        fields_ = value['forms'][0]['fields']
        self.assertEqual([f['label'] for f in fields_[:2]], ['', ''])
        self.assertEqual(inventory_support(URI, [value])[1], [])

    async def test_hidden_labelled_output_and_arbitrary_identifier_are_not_results(self):
        value = await self.inventory('''<div id="answer-looking-id">普通内容</div>
          <label for="output" style="display:none">输出结果</label><textarea id="output"></textarea>
          <div role="status" style="visibility:hidden">隐藏状态</div>
          <div role="status" id="status">真实状态</div>''')
        self.assertEqual([(r['selector'], r['text']) for r in value['result_targets']], [('#status', '真实状态')])

    async def test_hidden_descendant_transparent_and_zero_size_labels_are_not_recovered(self):
        value = await self.inventory('''<div role="form">
          <label for="a"><span style="display:none">隐藏子文本</span></label><input id="a">
          <label for="b" style="color:transparent">透明标签</label><input id="b">
          <label for="c" style="font-size:0">零字号标签</label><input id="c">
          <button type="button">处理</button></div>''')
        self.assertEqual([f['label'] for f in value['forms'][0]['fields'][:3]], ['', '', ''])
        self.assertEqual(inventory_support(URI, [value])[1], [])

    async def test_ambiguous_labelledby_id_is_not_assigned_to_a_field(self):
        value = await self.inventory('''<div role="form"><span id="caption">第一个标签</span>
          <span id="caption">另一个标签</span><input id="a" aria-labelledby="caption"><button>处理</button></div>''')
        self.assertEqual(value['forms'][0]['fields'][0]['label'], '')

    async def test_arbitrary_div_with_controls_is_not_declared_a_form(self):
        value = await self.inventory('<div>' + fields() + '</div><output>等待计算</output>')
        self.assertEqual(value['forms'], [])


if __name__ == '__main__':
    unittest.main()
