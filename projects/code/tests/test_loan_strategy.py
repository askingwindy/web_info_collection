"""Independent arithmetic contracts, not real mortgage-page functionality."""
from decimal import Decimal, localcontext
from fractions import Fraction
import unittest
from webcollect.loan_strategy import equal_payment_oracle,matches_uri,URI

class LoanOracleTests(unittest.TestCase):
    def test_exact_uri_excludes_other_calculators_redirect_query_and_fragment(self):
        self.assertTrue(matches_uri(URI))
        for uri in (URI.rstrip('/'),URI+'?x=1',URI+'#result',URI.replace('https:','http:'),URI.replace('9986','9428')):
            self.assertFalse(matches_uri(uri))

    def test_monthly_schedule_amortizes_independently_to_zero(self):
        result=equal_payment_oracle('12','3.05','1')
        self.assertEqual(result['principal_yuan'],'120000.00');self.assertEqual(result['months'],12)
        with localcontext() as ctx:
            ctx.prec=60
            balance=Decimal(result['principal_yuan']);interest=Decimal(0)
            payment=Decimal(result['monthly_payment_unrounded']);rate=Decimal(result['monthly_rate'])
            for _ in range(result['months']):
                installment_interest=balance*rate;interest+=installment_interest
                balance=balance+installment_interest-payment
            self.assertLess(abs(balance),Decimal('1e-45'))
            self.assertEqual(f'{interest:.2f}',result['total_interest'])

    def test_positive_rate_reference_matches_exact_rational_calculation(self):
        result=equal_payment_oracle('1','12','1')
        r=Fraction(1,100);growth=(1+r)**12
        payment=Fraction(10000)*r*growth/(growth-1)
        with localcontext() as ctx:
            ctx.prec=60
            expected=Decimal(payment.numerator)/Decimal(payment.denominator)
            self.assertEqual(result['monthly_payment'],f'{expected:.2f}')
            self.assertEqual(result['total_payment'],f'{expected*12:.2f}')

    def test_invalid_nonfinite_nonpositive_and_fractional_year_inputs_reject(self):
        for values in [('NaN','3','1'),('Infinity','3','1'),('12','0','1'),('12','-1','1'),
                       ('0','3','1'),('12','3','0'),('12','3','1.5'),('12','3','101'),('abc','3','1')]:
            with self.subTest(values=values),self.assertRaises(ValueError):equal_payment_oracle(*values)

    def test_totals_do_not_multiply_the_rounded_display_installment(self):
        result=equal_payment_oracle('12','3.05','1')
        self.assertNotEqual(Decimal(result['monthly_payment'])*12,Decimal(result['total_payment']))
        self.assertEqual(Decimal(result['total_payment'])-Decimal(result['principal_yuan']),Decimal(result['total_interest']))


from copy import deepcopy
from pathlib import Path
import json
import tempfile
from webcollect.loan_strategy import ADAPTER_ID,STRATEGY_ID,LOAN_INVENTORY_JS,loan_spec,compile_loan,verify_loan_summary

def loan_capability():
    fields=[{'selector':selector,'tag':'input','type':'number','label':label,'visible':True,'enabled':True,'value':value,
             'label_source':'native_associated_label','min':minimum,'max':'','step':step}
            for selector,label,value,minimum,step in [('#loanAmount','贷款金额（万元）','100','','0.1'),('#loanTerm','贷款期限（年）','20','1','')]]
    fields.append({'selector':'button[onclick="calculateMortgage()"]','tag':'button','type':'button','label':'立即计算','visible':True,'enabled':True,'value':''})
    rate={'selector':'#interestRate','tag':'input','type':'number','label':'年利率（%）','value':'3.05','visible':True,'enabled':True,'label_source':'native_associated_label'}
    widget={'kind':'non-form-widget','adapter_id':ADAPTER_ID,'page_uri':URI,'label':'房贷计算器','fields':fields,'fixed_rate':rate,
      'loan_mode':{'selector':'#loanModeGroup button[data-mode="normal"]','value':'normal','label':'商业贷款','visible':True,'selected':True},
      'repayment':{'selector':'#repaymentType','value':'equalPayment','label':'还款方式','display':'等额本息','visible':True,'enabled':True},
      'result_selector':'#resultContainer','result_heading':'还款概览','result_initially_visible':False,'viewport':[1280,720],'observed_scroll_y':0}
    results=[{'selector':'#'+rid,'label':label,'text':'0.00 元','visible':False,'business_label':'房贷等额本息','unit':'元'}
             for rid,label in [('monthlyPayment','月供'),('totalPayment','总还款'),('totalInterest','总利息')]]
    page={'page_uri':URI,'title':'房贷计算器 | 菜鸟工具','forms':[],'widgets':[widget],'result_targets':results}
    return {'capability_id':'CONTROLLED-mortgage','version':'fixture-1','status':'ready','site_uri':URI,'site_category':'工具','capabilities':[page]}

class LoanStrategyTests(unittest.TestCase):
    def test_compiler_seven_necessary_actions_three_independent_exact_amounts(self):
        cap=loan_capability();page=cap['capabilities'][0];spec=loan_spec(cap,page,page['widgets'][0],'test-1');task=compile_loan(cap,spec)
        self.assertEqual([o['action_type'] for o in task['operations']],['click','hotkey','type','click','hotkey','type','click'])
        self.assertEqual([o['arguments']['text'] for o in task['operations'] if o['action_type']=='type'],['12','1'])
        self.assertEqual(task['deterministic_strategy']['id'],STRATEGY_ID)
        self.assertEqual(task['operations'][-1]['postconditions'],task['final_assertions'])
        self.assertEqual([r['text'] for r in spec['results']],['10165.98 元','121991.73 元','1991.73 元'])
        self.assertFalse(task['content_preparation']);self.assertTrue(task['stop_when_final'])

    def test_changed_fixed_settings_results_roles_limits_and_state_reject(self):
        for change in ('scope','rate','mode','repayment','label','limit','value','visible','result_unit','result_visible','duplicate'):
            with self.subTest(change=change):
                cap=loan_capability();page=cap['capabilities'][0];w=page['widgets'][0]
                if change=='scope':cap['site_uri']=URI+'?changed=1'
                elif change=='rate':w['fixed_rate']['value']='2.85'
                elif change=='mode':w['loan_mode']['value']='provident'
                elif change=='repayment':w['repayment']['value']='equalPrincipal'
                elif change=='label':w['fields'][0]['label']='金额'
                elif change=='limit':w['fields'][0]['min']='1'
                elif change=='value':w['fields'][0]['value']='12'
                elif change=='visible':w['fields'][0]['visible']=False
                elif change=='result_unit':page['result_targets'][0]['unit']='万元'
                elif change=='result_visible':w['result_initially_visible']=True
                else:page['result_targets'].append(deepcopy(page['result_targets'][0]))
                with self.assertRaises(ValueError):loan_spec(cap,page,w,'test-1')

    def test_compiler_rejects_changed_amount_or_forged_oracle_and_parameter_novelty(self):
        from webcollect.task_generation import semantic_signature
        cap=loan_capability();page=cap['capabilities'][0];spec=loan_spec(cap,page,page['widgets'][0],'test-1');task=compile_loan(cap,spec)
        variant=deepcopy(task);variant['operations'][2]['arguments']['text']='15'
        self.assertEqual(semantic_signature(task),semantic_signature(variant))
        for path in ('input','oracle','result'):
            changed=deepcopy(spec)
            if path=='input':changed['inputs'][0]['value']='15'
            elif path=='oracle':changed['deterministic_strategy']['oracle']['monthly_payment']='1.00'
            else:changed['results'][0]['text']='1.00 元'
            with self.assertRaisesRegex(ValueError,'specification changed'):compile_loan(cap,changed)

    def test_exact_summary_rejects_wrong_units_decimals_extra_fields_and_wrong_interest(self):
        expected={'monthlyPayment':'10165.98 元','totalPayment':'121991.73 元','totalInterest':'1991.73 元'}
        self.assertTrue(verify_loan_summary(expected))
        for changed in ({**expected,'monthlyPayment':'10165.98 万元'},{**expected,'monthlyPayment':'10165.9 元'},
                        {**expected,'totalInterest':'1991.74 元'},{**expected,'extra':'allowed'}):
            self.assertFalse(verify_loan_summary(changed))

# Core controls and result hierarchy reproduce the recorded real mortgage DOM.
# CSS uses measured positions; these pages are served locally and never collected
# as production. Fixed-rate arithmetic is independently tested above.
LOAN_HTML='''<!doctype html><meta charset="utf-8"><title>房贷计算器 | 菜鸟工具</title><style>
body{margin:0;min-height:1000px;font:16px Arial}h1{position:absolute;left:40px;top:90px}.calculator-container{position:absolute;left:240px;top:211px;width:800px}
label{display:block}.form-group{position:relative}.form-control{font:16px Arial;height:45px;width:336px;box-sizing:border-box;padding:10px}
#loanModeGroup{margin-top:8px;display:flex;height:37px}button{font:14px Arial;padding:8px 12px}#loanModeGroup .active{background:#444;color:white}
#singleLoanGroup{position:absolute;left:20px;top:104px}#singleRateGroup{position:absolute;left:405px;top:104px}
.input-group{display:flex;margin-top:8px}.input-group-prepend{width:35px}.input-group-text{display:block;height:45px;background:#eee}
.term-group{position:absolute;left:20px;top:197px}.repay-group{position:absolute;left:405px;top:197px}.repay-group select{margin-top:8px;width:375px}
#combineContainer{display:none}.calc-group{position:absolute;left:20px;top:314px;width:760px}.calc-group button{width:760px;height:41px}
#resultContainer{position:absolute;left:20px;top:379px;width:760px;display:none;background:#e9f8f0;padding:20px;box-sizing:border-box}
.card-title{font:18px Arial;margin:0 0 15px}.row.mb-4{display:flex;gap:30px}.col-md-4{width:218px}p.mb-1{font:14px Arial;margin:0 0 8px}h4{font:22px Arial;margin:0}
</style><h1>房贷计算器</h1><div class="calculator-container"><div style="margin-left:20px;margin-top:20px"><label>贷款模式</label>
<div id="loanModeGroup"><button type="button" class="active" data-mode="normal">商业贷款</button><button type="button" data-mode="provident">公积金贷款</button><button type="button" data-mode="combine">组合贷款</button></div></div>
<div class="form-group" id="singleLoanGroup"><label for="loanAmount">贷款金额（万元）</label><div class="input-group"><div class="input-group-prepend"><span class="input-group-text">¥</span></div><input id="loanAmount" type="number" value="100" step="0.1" placeholder="请输入贷款金额" class="form-control"></div></div>
<div class="form-group" id="singleRateGroup"><label for="interestRate">年利率（%）</label><div class="input-group"><div class="input-group-prepend"><span class="input-group-text"></span></div><input id="interestRate" type="number" value="3.05" step="0.01" placeholder="请输入利率" class="form-control"></div></div>
<div id="combineContainer"><input id="loanAmountCommercial" value="70"><input id="interestRateCommercial" value="3.05"><input id="loanAmountProvident" value="30"><input id="interestRateProvident" value="2.85"></div>
<div class="form-group term-group"><label for="loanTerm">贷款期限（年）</label><div class="input-group"><div class="input-group-prepend"><span class="input-group-text"></span></div><input id="loanTerm" type="number" value="20" min="1" placeholder="请输入年限" class="form-control"></div></div>
<div class="form-group repay-group"><label for="repaymentType">还款方式</label><select id="repaymentType" class="form-control"><option value="equalPayment">等额本息</option><option value="equalPrincipal">等额本金</option></select></div>
<div class="form-group calc-group"><button type="button" onclick="calculateMortgage()">立即计算</button></div>
<div class="card result-card" id="resultContainer"><div class="card-body"><h5 class="card-title">还款概览</h5><div class="row mb-4">
<div class="col-md-4"><p class="mb-1">月供</p><h4 id="monthlyPayment">0.00 元</h4></div>
<div class="col-md-4"><p class="mb-1">总还款</p><h4 id="totalPayment">0.00 元</h4></div>
<div class="col-md-4"><p class="mb-1">总利息</p><h4 id="totalInterest">0.00 元</h4></div></div></div></div></div>
<script>function calculateMortgage(){const p=Number(document.getElementById('loanAmount').value)*10000,r=Number(document.getElementById('interestRate').value)/1200,n=Number(document.getElementById('loanTerm').value)*12;const payment=p*r*Math.pow(1+r,n)/(Math.pow(1+r,n)-1);document.getElementById('monthlyPayment').textContent=payment.toFixed(2)+' 元';document.getElementById('totalPayment').textContent=(payment*n).toFixed(2)+' 元';document.getElementById('totalInterest').textContent=(payment*n-p).toFixed(2)+' 元';document.getElementById('resultContainer').style.display='block'}</script>'''

class LoanBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.p=await async_playwright().start();self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(viewport={'width':1280,'height':720},service_workers='block')
        async def local_only(route):
            if route.request.is_navigation_request():await route.fulfill(status=200,content_type='text/html; charset=utf-8',body=LOAN_HTML)
            else:await route.abort()
        await self.context.route('**/*',local_only);self.page=await self.context.new_page();await self.page.goto(URI)

    async def asyncTearDown(self):await self.browser.close();await self.p.stop()

    async def task(self):
        before=await self.page.content();inventory=await self.page.evaluate(LOAN_INVENTORY_JS)
        self.assertEqual(before,await self.page.content());self.assertEqual(inventory['widget_rejections'],[])
        cap=loan_capability();page=cap['capabilities'][0];page.update(inventory)
        return compile_loan(cap,loan_spec(cap,page,page['widgets'][0],'controlled-test-1'))

    async def test_real_shape_inventory_and_full_m4_collect_one(self):
        from webcollect.collect import collect_one
        from webcollect.task_contract import PLAN_SCHEMA
        task=await self.task();task.update(_plan_schema_version=PLAN_SCHEMA,initial_settle_ms=0)
        with tempfile.TemporaryDirectory() as root:
            sample=Path(root)/'CONTROLLED-loan';evidence=Path(root)/'evidence'
            annotation=await collect_one(self.context,task,sample,evidence,{'sample_id':'CONTROLLED-loan'})
            self.assertEqual(len(annotation['steps']),8)
            self.assertEqual([s['action']['action_type'] for s in annotation['steps']],['click','hotkey','type','click','hotkey','type','click','complete'])
            contract=json.loads((evidence/'task_contract.json').read_text())
            self.assertEqual(contract['machine_status'],'PASS');self.assertEqual(contract['semantic_status'],'REVIEW_REQUIRED')
            self.assertEqual(len(contract['executed_operation_ids']),7)
            self.assertEqual(len(list((sample/'images').glob('*.png'))),8)

    async def test_hidden_obscured_wrong_mode_unbound_label_and_extra_controls_reject(self):
        for mutation in ["document.querySelector('#loanAmount').style.opacity='0'",
            "document.querySelector('#loanAmount').readOnly=true",
            "document.querySelector('label[for=loanAmount]').htmlFor='unrelated'",
            "document.querySelector('#interestRate').value='2.85'",
            "document.querySelector('#repaymentType').value='equalPrincipal'",
            "document.querySelector('#loanModeGroup button').classList.remove('active')",
            "document.querySelector('.calculator-container').insertAdjacentHTML('beforeend','<input id=extra>')",
            "document.querySelector('#monthlyPayment').previousElementSibling.textContent='总利息'",
            "document.body.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;z-index:999;background:white\"></div>')"]:
            with self.subTest(mutation=mutation):
                await self.page.set_content(LOAN_HTML);await self.page.evaluate(mutation)
                inventory=await self.page.evaluate(LOAN_INVENTORY_JS)
                self.assertEqual(inventory['widgets'],[]);self.assertTrue(inventory['widget_rejections'])

    async def test_exact_values_roles_units_and_visible_saved_result_are_required(self):
        from webcollect.browser import observe,prepare_action,execute
        from webcollect.collect import assert_state
        task=await self.task()
        for op in task['operations']:
            state=await observe(self.page,op.get('selector'));args,_=prepare_action(state,op)
            if op.get('selector') in ('#loanAmount','#loanTerm'):
                self.assertTrue(any(row['kind']=='rendered_associated_label' and row['text']==op['evidence']['target_label'] for row in state['target']['visible_label_evidence']))
            await execute(self.page,op['action_type'],args,op.get('execution'))
        await assert_state(self.page,task['final_assertions'])
        for bad in ('110165.98 元','10165.99 元','10165.98 美元'):
            await self.page.locator('#monthlyPayment').evaluate('(e,v)=>e.textContent=v',bad)
            with self.assertRaises(ValueError):await assert_state(self.page,task['final_assertions'])
        await self.page.locator('#monthlyPayment').evaluate("e=>e.textContent='10165.98 元'")
        await self.page.locator('#totalPayment').evaluate("e=>e.style.visibility='hidden'")
        with self.assertRaises(ValueError):await assert_state(self.page,task['final_assertions'])

if __name__=='__main__':unittest.main()
