"""Offline BMI adapter contracts; controlled fixtures never count as real supply."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO/'projects/site-planner'))
from site_planner.pipeline import INVENTORY_JS
from webcollect.bmi_strategy import ADAPTER_ID, BMI_URI, BMI_INVENTORY_JS
from webcollect.task_generation import (compile_form, deterministic_specs, generate,
                                       semantic_signature, task_signature)
from webcollect.task_contract import validate_m4_task
from webcollect.batch_core import BatchLedger, load_json
from test_s0_task_generation import capability, catalog, config


def bmi_capability(root):
    row = capability(root, uri=BMI_URI)
    fields, sliders = [], []
    for role, unit, base, value, minimum in [('身高','cm','height','170','1'), ('体重','kg','weight','70','10')]:
        label = role+' ('+unit+')'
        fields.append({'selector':'#'+base+'Input', 'tag':'input', 'type':'number', 'label':label,
                       'role':role, 'unit':unit, 'visible':True, 'enabled':True, 'value':value,
                       'min':minimum, 'max':'290', 'label_source':'same_input_group_text'})
        sliders.append({'selector':'#'+base, 'type':'range', 'label':label, 'visible':True,
                        'linked_input':'#'+base+'Input', 'value':value, 'min':minimum, 'max':'290'})
    fields.append({'selector':'#calculateBtn', 'tag':'button', 'type':'submit', 'label':'计算 BMI',
                   'visible':True, 'enabled':True, 'value':''})
    widget = {'kind':'non-form-widget', 'adapter_id':ADAPTER_ID, 'label':'BMI 计算器', 'page_uri':BMI_URI,
              'fields':fields, 'linked_controls':sliders, 'result_selector':'#bmiValue',
              'result_label':'您的 BMI 结果', 'result_label_selector':'#resultContainer h2',
              'result_business_label':'BMI', 'display_precision':1}
    row['capabilities'] = [{'page_uri':BMI_URI, 'title':'BMI 计算器 | 菜鸟工具', 'forms':[], 'widgets':[widget],
        'result_targets':[{'selector':'#bmiValue', 'text':'24.2', 'visible':True,
                           'label':'您的 BMI 结果', 'business_label':'BMI'}]}]
    return row


class BmiStrategyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.record = bmi_capability(self.root)

    def test_exact_arithmetic_and_seven_necessary_actions(self):
        proposal = deterministic_specs(self.record)
        self.assertEqual(proposal['strategy_rejections'], [])
        self.assertEqual(len(proposal['tasks']), 1)
        task = compile_form(self.record, proposal['tasks'][0]); validate_m4_task(task)
        self.assertEqual([op['action_type'] for op in task['operations']],
                         ['click','hotkey','type','click','hotkey','type','click'])
        self.assertEqual([op['arguments']['text'] for op in task['operations'] if op['action_type']=='type'], ['160','64'])
        self.assertEqual(task['final_result'], 'BMI 计算结果为25.0')
        self.assertEqual(task['final_assertions'][0]['numbers'],
                         {'count':1,'minimum':25,'maximum_exclusive':26,'integer':True})
        self.assertIn({'selector':'#bmiValue','contains':'25.0'}, task['final_assertions'])
        self.assertIn({'selector':'#resultContainer h2','contains':'您的 BMI 结果'}, task['final_assertions'])
        self.assertFalse(task['content_preparation'])
        self.assertTrue(task['stop_when_final'])

    def test_reject_missing_units_hidden_targets_extra_input_and_wrong_initial_state(self):
        for change in ('unit','label','hidden_field','hidden_result','extra','slider','wrong_initial_result',
                       'wrong_initial_input','already_complete','wrong_origin','wrong_precision','wrong_widget_kind'):
            with self.subTest(change=change):
                row = deepcopy(self.record); page = row['capabilities'][0]; widget = page['widgets'][0]
                field = widget['fields'][0]
                if change=='unit':field.pop('unit')
                elif change=='label':field['label']='身高'
                elif change=='hidden_field':field['visible']=False
                elif change=='hidden_result':page['result_targets'][0]['visible']=False
                elif change=='extra':widget['fields'].append({**field,'selector':'#age'})
                elif change=='slider':widget['linked_controls'][0]['value']='180'
                elif change=='wrong_initial_result':page['result_targets'][0]['text']='24.3'
                elif change=='wrong_initial_input':field['value']='0'
                elif change=='already_complete':page['result_targets'][0]['text']='25.0'
                elif change=='wrong_origin':row['site_uri']='https://example.com/front-end/9428/'
                elif change=='wrong_precision':widget['display_precision']=2
                else:widget['kind']='form'
                proposal=deterministic_specs(row)
                self.assertEqual(proposal['tasks'], [])
                self.assertTrue(proposal['strategy_rejections'])

    def test_compiler_rejects_changed_input_or_completion_oracle(self):
        spec = deterministic_specs(self.record)['tasks'][0]
        for change in ('value','number','display','selector'):
            with self.subTest(change=change):
                altered = deepcopy(spec)
                if change=='value':altered['inputs'][0]['value']='180'
                elif change=='number':altered['completion']['number']=24
                elif change=='display':altered['deterministic_strategy']['expected_display']='24.0'
                else:altered['completion']['selector']='#bmiCategory'
                with self.assertRaisesRegex(ValueError,'specification changed'):
                    compile_form(self.record, altered)

    def test_same_business_is_deduplicated_without_model_or_ids(self):
        second = deepcopy(self.record); second['capability_id']+='-duplicate'
        cfg = config(); ledger = BatchLedger(self.root/'ops.sqlite3', cfg, initialize=True)
        result = generate(ledger, catalog(self.root/'catalog.json',[self.record,second]), self.root/'tasks')
        self.assertEqual(result['generated_tasks'], 1)
        self.assertEqual(len(result['rejected']), 1)
        self.assertEqual(result['sample_ids_allocated'], 0)
        self.assertEqual(ledger.summary()['model_requests'], 0)
        task = load_json(result['plan_file'])['tasks'][0]
        variant = deepcopy(task); variant['operations'][2]['arguments']['text']='180'
        variant['initial_url'] += '?parameter=changed'
        self.assertEqual(task_signature(task),task_signature(variant))
        self.assertEqual(semantic_signature(task),semantic_signature(variant))

    def test_existing_rectangle_strategy_still_compiles(self):
        row = capability(self.root/'rectangle')
        page = row['capabilities'][0]; form = page['forms'][0]
        form['label']='矩形面积计算'
        form['fields'][0]['label']='长度（厘米）'; form['fields'][1]['label']='宽度（厘米）'
        form['fields'][2]['label']='计算面积'
        task=compile_form(row,deterministic_specs(row)['tasks'][0])
        self.assertEqual(task['deterministic_strategy']['id'],'rectangle-area-v1')
        self.assertEqual(task['final_assertions'][0]['numbers']['minimum'],42)


# A small controlled DOM matching only the actually observed widget structure.
# Every browser request is fulfilled or aborted locally; no remote request is sent.
HTML = '''<!doctype html><meta charset="utf-8"><title>BMI 计算器 | 菜鸟工具</title>
<style>body{font:18px sans-serif}.form-row{display:flex;gap:40px}.form-group{margin:15px}
.input-group{display:flex}.input-group-text{display:block;background:#ddd;padding:5px}
input[type=number]{width:150px}input[type=range],label{display:block}button{margin:15px;padding:5px}</style>
<div class="form-row"><div>
<div class="form-group"><label for="height">身高 (cm)</label><input type="range" id="height" min="1" max="290" value="170">
<div class="input-group"><div><span class="input-group-text">身高 (cm)</span></div><input type="number" id="heightInput" min="1" max="290" value="170"></div></div>
<div class="form-group"><label for="weight">体重 (kg)</label><input type="range" id="weight" min="10" max="290" value="70">
<div class="input-group"><div><span class="input-group-text">体重 (kg)</span></div><input type="number" id="weightInput" min="10" max="290" value="70"></div></div>
<button id="calculateBtn">计算 BMI</button></div><div id="resultContainer"><h2>您的 BMI 结果</h2>
<div><div id="bmiValue">24.2</div><div>BMI</div></div></div></div>'''


class BmiInventoryBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.p = await async_playwright().start()
        self.browser = await self.p.chromium.launch(channel='chrome',headless=True)
        self.context = await self.browser.new_context(viewport={'width':1280,'height':720}, service_workers='block')
        async def local_only(route):
            if route.request.is_navigation_request():
                await route.fulfill(status=200,content_type='text/html',body=HTML)
            else:await route.abort()
        await self.context.route('**/*',local_only)
        self.page = await self.context.new_page(); await self.page.goto(BMI_URI)

    async def asyncTearDown(self):
        await self.browser.close(); await self.p.stop()

    async def test_readonly_typed_widget_inventory_compiles_and_leaves_forms_separate(self):
        before=await self.page.content()
        inventory=await self.page.evaluate(INVENTORY_JS)
        self.assertEqual(before,await self.page.content())
        self.assertEqual(inventory['forms'],[])
        self.assertEqual(inventory['widget_rejections'],[])
        self.assertEqual(len(inventory['widgets']),1)
        self.assertEqual(inventory['widgets'][0]['kind'],'non-form-widget')
        with tempfile.TemporaryDirectory() as root:
            row=bmi_capability(root); inventory['page_uri']=BMI_URI; row['capabilities']=[inventory]
            self.assertEqual(len(compile_form(row,deterministic_specs(row)['tasks'][0])['operations']),7)

    async def test_dom_missing_unit_hidden_field_result_extra_control_and_label_are_rejected(self):
        mutations = ["document.querySelector('.input-group-text').textContent='身高'",
            "document.querySelector('#heightInput').style.display='none'",
            "document.querySelector('#bmiValue').style.visibility='hidden'",
            "document.querySelector('.form-row').insertAdjacentHTML('beforeend','<input id=extra>')",
            "document.querySelector('#heightInput').min='2'",
            "document.querySelector('#height').value='180'",
            "document.querySelector('#calculateBtn').textContent='提交'",
            "document.querySelector('#resultContainer h2').textContent='未知结果'",
            "document.querySelector('#weightInput').disabled=true"]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                await self.page.set_content(HTML); await self.page.evaluate(mutation)
                result=await self.page.evaluate(BMI_INVENTORY_JS)
                self.assertEqual(result['widgets'],[])
                self.assertTrue(result['widget_rejections'])

    async def test_identical_controls_on_other_origins_are_not_bmi_capabilities(self):
        await self.page.goto('https://example.org/front-end/9428/')
        result=await self.page.evaluate(BMI_INVENTORY_JS)
        self.assertEqual(result,{'widgets':[],'result_targets':[],'widget_rejections':[]})


if __name__=='__main__':unittest.main()
