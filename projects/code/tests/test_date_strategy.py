"""Offline observed-date adapter tests; controlled DOM is not real collection."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from webcollect.date_strategy import ADAPTER_ID, STRATEGY_ID, URI, DATE_INVENTORY_JS, matches_uri
from webcollect.task_generation import compile_form, deterministic_specs, semantic_signature
from webcollect.task_contract import validate_m4_task
from test_s0_task_generation import capability


def date_capability(root):
    row = capability(root, uri=URI)
    fields = [{'selector':selector,'tag':'input','type':'text','label':label,
               'visible':True,'enabled':True,'value':value,'label_source':'same_form_item_label'}
              for selector,label,value in [('#date1','开始日期','2026-09-27'),('#date2','结束日期','2026-10-27')]]
    fields.append({'selector':'#startCalculate','tag':'button','type':'submit','label':'计算',
                   'visible':True,'enabled':True,'value':''})
    widget = {'kind':'non-form-widget','adapter_id':ADAPTER_ID,'page_uri':URI,'label':'相差天数计算',
              'fields':fields,'result_selector':'#betweenDay','result_label':'相差',
              'result_label_selector':'#resultContainer .layui-form-item:first-child .layui-form-label'}
    row['capabilities'] = [{'page_uri':URI,'title':'日期计算器','forms':[],'widgets':[widget],
        'result_targets':[{'selector':'#betweenDay','text':'','value':'','visible':False,'readonly':True,
                           'label':'相差','business_label':'日期相差天数'}]}]
    return row


class DateStrategyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.row = date_capability(self.temp.name)

    def test_leap_day_oracle_and_seven_necessary_actions(self):
        proposal = deterministic_specs(self.row)
        self.assertEqual(proposal['strategy_rejections'], [])
        self.assertEqual(len(proposal['tasks']), 1)
        task = compile_form(self.row, proposal['tasks'][0]); validate_m4_task(task)
        self.assertEqual(task['deterministic_strategy']['id'], STRATEGY_ID)
        self.assertEqual(task['deterministic_strategy']['operator'], 'civil_end_date-civil_start_date')
        self.assertEqual([op['action_type'] for op in task['operations']],
                         ['click','hotkey','type','click','hotkey','type','click'])
        self.assertEqual([op['arguments']['text'] for op in task['operations'] if op['action_type']=='type'],
                         ['2024-02-28','2024-03-01'])
        self.assertEqual(task['final_assertions'], [
            {'selector':'#betweenDay','numbers':{'count':1,'minimum':2,'maximum_exclusive':3,'integer':True}},
            {'selector':'#betweenDay','contains':'天'},
            {'selector':'#resultContainer .layui-form-item:first-child .layui-form-label','contains':'相差'}])
        self.assertFalse(task['content_preparation']); self.assertTrue(task['stop_when_final'])

    def test_exact_uri_rejects_redirect_query_fragment_other_business(self):
        self.assertTrue(matches_uri(URI))
        for uri in (URI+'/', URI+'?x=1', URI+'#date', URI.replace('https:','http:'),
                    URI.replace('www.lddgo.net','example.org'), URI+'time'):
            self.assertFalse(matches_uri(uri),uri)
            row=deepcopy(self.row); row['capabilities'][0]['page_uri']=uri
            self.assertEqual(deterministic_specs(row)['tasks'],[])

    def test_missing_ambiguous_roles_invalid_dates_hidden_fields_are_rejected(self):
        for change in ('label','disabled','hidden','tag','source','empty','invalid','noncanonical',
                       'already_requested','extra','duplicate','submit_type','result_readonly','result_role','result_duplicate'):
            with self.subTest(change=change):
                row=deepcopy(self.row); page=row['capabilities'][0]; widget=page['widgets'][0]; field=widget['fields'][0]
                if change=='label':field['label']='结束日期'
                elif change=='disabled':field['enabled']=False
                elif change=='hidden':field['visible']=False
                elif change=='tag':field['tag']='select'
                elif change=='source':field['label_source']='guess'
                elif change=='empty':field['value']=''
                elif change=='invalid':field['value']='2026-02-30'
                elif change=='noncanonical':field['value']='20260927'
                elif change=='already_requested':field['value']='2024-02-28'
                elif change=='extra':widget['fields'].append({**field,'selector':'#extra'})
                elif change=='duplicate':widget['fields'][1]['selector']='#date1'
                elif change=='submit_type':widget['fields'][2]['type']='reset'
                elif change=='result_readonly':page['result_targets'][0]['readonly']=False
                elif change=='result_role':page['result_targets'][0]['label']='日期偏移'
                else:page['result_targets'].append(deepcopy(page['result_targets'][0]))
                self.assertEqual(deterministic_specs(row)['tasks'],[])

    def test_changed_parameters_oracle_and_submit_cannot_be_forged(self):
        spec=deterministic_specs(self.row)['tasks'][0]
        for change in ('input','number','unit','submit'):
            altered=deepcopy(spec)
            if change=='input':altered['inputs'][0]['value']='2024-02-27'
            elif change=='number':altered['completion']['number']=3
            elif change=='unit':altered['deterministic_strategy']['expected_unit']='小时'
            else:altered['submit']['selector']='#startTimeDiffer'
            with self.assertRaisesRegex(ValueError,'specification changed'):compile_form(self.row,altered)

    def test_noop_result_and_parameter_only_novelty_are_rejected(self):
        task=compile_form(self.row,deterministic_specs(self.row)['tasks'][0])
        variant=deepcopy(task); variant['operations'][2]['arguments']['text']='2023-01-01'
        self.assertEqual(semantic_signature(task),semantic_signature(variant))
        self.row['capabilities'][0]['result_targets'][0].update(text='2天',value='2天',visible=True)
        with self.assertRaisesRegex(ValueError,'already visible'):compile_form(self.row,deterministic_specs(self.row)['tasks'][0])


# The narrow observed grouping is reproduced locally; all requests are intercepted.
# Result-setting here is a controlled contract fixture, not the website's calculation implementation.
HTML='''<!doctype html><meta charset="utf-8"><title>日期计算器</title>
<style>body{font:18px sans-serif}.layui-form-item{display:flex;margin:15px}.layui-form-label{display:block;width:100px}
input{width:200px}button{padding:5px}.layui-card{margin:20px}</style>
<div class="layui-card"><div class="layui-card-header">相差天数计算</div>
<div class="layui-form-item"><label class="layui-form-label">开始日期</label><div><input id="date1" value="2026-09-27"></div></div>
<div class="layui-form-item"><label class="layui-form-label">结束日期</label><div><input id="date2" value="2026-10-27"></div></div>
<button id="startCalculate">计算</button><div id="resultContainer" style="display:none">
<div class="layui-form-item"><label class="layui-form-label">相差</label><div><input readonly id="betweenDay"></div></div>
<div class="layui-form-item"><label class="layui-form-label">相差</label><div><input readonly id="betweenComplex"></div></div>
</div></div><div class="layui-card"><button id="startTimeDiffer">计算</button></div>'''


class DateInventoryBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.p=await async_playwright().start()
        self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':1280,'height':900},service_workers='block')
        async def local_only(route):
            if route.request.is_navigation_request():await route.fulfill(status=200,content_type='text/html',body=HTML)
            else:await route.abort()
        await self.context.route('**/*',local_only)
        self.page=await self.context.new_page(); await self.page.goto(URI)

    async def asyncTearDown(self):
        await self.browser.close(); await self.p.stop()

    async def test_readonly_inventory_accepts_real_date_shape_and_hidden_empty_prospective_result(self):
        before=await self.page.content(); inventory=await self.page.evaluate(DATE_INVENTORY_JS)
        self.assertEqual(before,await self.page.content())
        self.assertEqual(inventory['widget_rejections'],[])
        self.assertEqual(len(inventory['widgets']),1)
        self.assertFalse(inventory['result_targets'][0]['visible'])
        self.assertEqual(inventory['result_targets'][0]['text'],'')
        with tempfile.TemporaryDirectory() as root:
            row=date_capability(root); row['capabilities'][0].update(inventory)
            self.assertEqual(len(compile_form(row,deterministic_specs(row)['tasks'][0])['operations']),7)

    async def test_hidden_obscured_disabled_ambiguous_or_wrong_group_controls_reject(self):
        mutations=["document.querySelector('#date1').style.display='none'",
            "document.querySelector('#date1').style.opacity='0'",
            "document.querySelector('#date1').disabled=true",
            "document.querySelector('#date1').readOnly=true",
            "document.querySelector('#date1').value='20260927'",
            "document.querySelector('#date1').insertAdjacentHTML('afterend','<input id=date1>')",
            "document.querySelector('.layui-card').insertAdjacentHTML('beforeend','<input id=extra>')",
            "document.querySelector('.layui-card-header').textContent='相差时间计算'",
            "document.querySelector('.layui-form-label').textContent='结束日期'",
            "document.querySelector('#startCalculate').textContent='提交'",
            "document.querySelector('#betweenDay').readOnly=false",
            "document.body.appendChild(document.querySelector('#betweenDay'))",
            "document.body.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;z-index:999;background:white\"></div>')"]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                await self.page.set_content(HTML); await self.page.evaluate(mutation)
                inventory=await self.page.evaluate(DATE_INVENTORY_JS)
                self.assertEqual(inventory['widgets'],[])
                self.assertTrue(inventory['widget_rejections'])

    async def test_other_origin_same_markup_is_not_date_capability(self):
        await self.page.goto('https://example.org/common/date')
        self.assertEqual(await self.page.evaluate(DATE_INVENTORY_JS),
                         {'widgets':[],'result_targets':[],'widget_rejections':[]})

    async def test_final_result_requires_visible_value_and_unit_and_role(self):
        from webcollect.collect import assert_state
        with tempfile.TemporaryDirectory() as root:
            row=date_capability(root); task=compile_form(row,deterministic_specs(row)['tasks'][0])
        conditions=task['final_assertions']
        with self.assertRaises(Exception):await assert_state(self.page,conditions)
        await self.page.evaluate("document.querySelector('#betweenDay').value='2天'")
        with self.assertRaises(Exception):await assert_state(self.page,conditions)
        await self.page.evaluate("document.querySelector('#resultContainer').style.display='block'")
        await assert_state(self.page,conditions)
        for bad in ('3天','2小时','12天'):
            await self.page.locator('#betweenDay').evaluate('(e,v)=>e.value=v',bad)
            with self.assertRaises(Exception):await assert_state(self.page,conditions)
        await self.page.locator('#betweenDay').evaluate("e=>e.value='2天'")
        await self.page.locator('#resultContainer .layui-form-label').first.evaluate("e=>e.textContent='偏移'")
        with self.assertRaises(Exception):await assert_state(self.page,conditions)


if __name__=='__main__':unittest.main()
